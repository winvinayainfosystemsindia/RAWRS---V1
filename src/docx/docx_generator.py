"""DOCX generation for RAWRS.

Converts the canonical markdown produced by src/markdown/markdown_builder.py
into a remediation-ready DOCX file: H1-H6 headings mapped to Word's
built-in heading styles (so they appear in the Navigation Pane), page
breaks preserving PDF page boundaries, and centered inline images with
captions.

Per docs/ARCHITECTURE.md, the markdown string - not the Document model -
is the source of truth for body structure (headings, paragraphs, image
references, page markers): it is the editable intermediate artifact a
human reviewer may have touched before DOCX conversion, so this module
parses it rather than re-deriving structure from Document.headings/
Document.images directly. The Document model is used only for deriving
the default output filename.

Per docs/PHASE1_SCOPE.md, out of scope: alt text *generation*,
accessibility tagging, table remediation, equation remediation, and any
AI/OCR processing. Alt text *metadata wiring* (Phase F.4) is in scope
and implemented here: this module sets the docPr descr/title attributes
from whatever alt text already exists in the markdown's
``![alt](path)`` syntax - it never derives, infers, or generates that
text itself; src/images/image_extractor.py (Phase F.3) is solely
responsible for what alt text content exists, via a fixed,
deterministic placeholder template, never AI.

Front matter (Front-Matter Semantic Extraction): when
Document.front_matter has a title, the title/author(s)/affiliation(s)
markdown block src/markdown/markdown_builder.py renders immediately
after page 1's H6 marker is styled distinctly here (Word's built-in
"Title"/"Subtitle" paragraph styles, then explicit font overrides on
top, the same "always set formatting explicitly" convention already
used throughout this module) - not parsed back out of the markdown
text by pattern alone, since a bold/italic *line shape* is ambiguous
with arbitrary user content elsewhere in a document; this module reads
Document.front_matter directly (it already receives the full Document,
not just the markdown string) and only ever applies this special
handling immediately after the very first heading (page 1's marker),
exactly the span of lines src/markdown/markdown_builder.py is
documented to put it in.

Footnote/endnote wiring (Phase K) follows the same principle: this
module renders whatever ``[^label]`` inline references and
``[^label]: body`` definitions already exist in the markdown
(src/markdown/markdown_builder.py decides what those are; this module
only renders them) as a real, internally-linked DOCX
marker-to-note-body relationship - a superscript run wrapped in a
``w:hyperlink`` pointing at a ``w:bookmark`` on the matching definition
paragraph. python-docx 1.2.0 has no public API for either OOXML
construct, so both are built directly via docx.oxml - the same
documented, well-known pattern already used for the docPr alt-text
attributes above, not a novel technique.

XML Sanitization Architecture (Layer 3): a production PDF crashed this
module with "All strings must be XML compatible..." (a ValueError from
lxml itself) - root-cause audit found that extracted text reaching
this module's text/attribute-setting calls is never guaranteed clean.
src/utils/text_sanitization.py (Layer 1) now sanitizes at every point
text first enters the Document model, and src/validation/validator.py
(DOC_004, Layer 2) discloses every place it had to act. _safe_run_text()
below is the third, last-resort layer: every call site in this module
that sets OOXML text content or an attribute from text that ultimately
originated in extracted content runs through it. In normal operation
it is a no-op (Layer 1 already cleaned the text) - it logs loudly via
logger.error() if it ever actually changes something, since that
indicates a text-creation path was added somewhere that Layer 1 was
not wired into, which is itself the signal to go fix that gap, not a
reason to remove this guard.
"""

import io
import itertools
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.shared import Emu, Inches, Pt, RGBColor
from docx.text.paragraph import Paragraph
from loguru import logger
from lxml import etree
from PIL import Image as PILImage

from src.markdown.markdown_builder import PAGE_BREAK_MARKER
from src.models.contracts import Document, FrontMatter
from src.utils.text_sanitization import sanitize_xml_text

DEFAULT_OUTPUT_DIR = Path("outputs/docx")

_FONT_NAME = "Times New Roman"
_BODY_FONT_SIZE_PT = 12
_FOOTNOTE_FONT_SIZE_PT = 10
_BLACK = RGBColor(0, 0, 0)
_MAX_IMAGE_WIDTH = Inches(6.5)  # content width on a Letter page with 1" margins

# Per docs/HEADING_RULES.md Formatting Rules: H1=16pt, H2=14pt, H3-H6=12pt,
# all bold, black, Times New Roman.
_HEADING_FONT_SIZES_PT = {1: 16, 2: 14, 3: 12, 4: 12, 5: 12, 6: 12}

# Front-Matter Semantic Extraction: deliberately larger than any
# Heading-N size above - a document's title is its own distinct
# typographic tier, not competing with the heading hierarchy.
_TITLE_FONT_SIZE_PT = 20
_BYLINE_FONT_SIZE_PT = 14

_FOOTNOTES_RELATIONSHIP_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes"
)
_FOOTNOTES_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"
)
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


class _FootnoteRegistry:
    """Accumulates footnote bodies keyed by markdown label and assigns
    sequential OOXML w:id integers (starting at 1; -1 and 0 are
    reserved for Word's separator/continuationSeparator entries).

    IDs are assigned on first encounter — either an inline ``[^label]``
    reference or a ``[^label]: body`` definition, whichever appears
    first.  The complete registry is consumed once after the main
    rendering loop to build ``word/footnotes.xml``.
    """

    def __init__(self) -> None:
        self._next_id: int = 1
        self._ids: Dict[str, int] = {}
        self._bodies: Dict[str, str] = {}

    def get_or_assign_id(self, label: str) -> int:
        if label not in self._ids:
            self._ids[label] = self._next_id
            self._next_id += 1
        return self._ids[label]

    def register_body(self, label: str, body_text: str) -> None:
        self.get_or_assign_id(label)
        self._bodies[label] = body_text

    def ordered_entries(self) -> List[Tuple[int, str]]:
        """(id, body_text) pairs in ascending id order, for labels that
        have a registered body."""
        pairs = [
            (self._ids[lbl], body)
            for lbl, body in self._bodies.items()
        ]
        return sorted(pairs, key=lambda p: p[0])

    def has_entries(self) -> bool:
        return bool(self._bodies)


_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")
_IMAGE_PATTERN = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)$")
_CAPTION_PATTERN = re.compile(r"^\*(.+)\*$")

# An inline footnote/endnote reference, e.g. "[^p3-1]" - label content
# is opaque here (src/markdown/markdown_builder.py owns its format);
# this module only needs to split text around it and recover the
# human-visible printed number (the digits after the label's last "-").
_FOOTNOTE_REFERENCE_PATTERN = re.compile(r"\[\^([^\]]+)\]")
_FOOTNOTE_DEFINITION_PATTERN = re.compile(r"^\[\^([^\]]+)\]:\s*(.+)$")
_LABEL_DISPLAY_NUMBER_PATTERN = re.compile(r"-(\d+)$")
_BOOKMARK_NAME_SANITIZE_PATTERN = re.compile(r"[^A-Za-z0-9_]")

# Pipe table: any line starting and ending with | (may have inner cells).
# Separator row: | --- | --- | (only dashes, spaces, colons between pipes).
_PIPE_TABLE_ROW_PATTERN = re.compile(r"^\|.+\|$")
_PIPE_TABLE_SEPARATOR_PATTERN = re.compile(r"^\|[\s\-:|]+\|$")
# Accessibility summary comment emitted by markdown_builder for tables.
# Skipped in the pipe-table fallback path; consumed by _add_semantic_table
# via the Table model (not re-parsed from markdown).
_TABLE_SUMMARY_COMMENT_PATTERN = re.compile(r"^<!-- table-summary: .+ -->$")
# Table-id anchor comment emitted by markdown_builder immediately before each
# table block.  Carries the table_id so this module can look up the full
# Table model and delegate to _add_semantic_table() instead of the plain
# string-parsing _add_pipe_table() path.
_TABLE_ID_COMMENT_PATTERN = re.compile(r"^<!-- table-id: (.+) -->$")

# Semantic list detection (FEATURE_016C): lines starting with a bullet
# character or a numbered/lettered prefix are rendered with Word's built-in
# "List Bullet" / "List Number" paragraph styles instead of a plain body
# paragraph.  The marker is stripped so Word's own list auto-numbering/
# auto-bullet is the only visible marker (no doubled "• •" artefacts).
#
# Bullet patterns: Unicode bullet chars that are unambiguous list markers.
# Numbered patterns: "1.", "a.", "i." followed by a whitespace character.
# Dashes ("- ") are included as bullet markers only when the entire rest of
# the line is non-empty, to avoid mis-classifying the separator "---" or
# Markdown-isms that happen to start with "- ".
_BULLET_LIST_PATTERN = re.compile(
    r"^([•▪▸▶◦○◉●→⁃✓✗✔✘\-])\s+(.+)$", re.UNICODE
)
_NUMBERED_LIST_PATTERN = re.compile(
    r"^(\d+|[a-z]|[ivxlcdm]+)\.\s+(.+)$", re.IGNORECASE
)

# Inline formatting markers emitted by markdown_builder._apply_inline_format
# (016G): ***bold+italic***, **bold**, *italic*. Longest marker tried first
# so ***...*** is never partially consumed by the shorter patterns.
_INLINE_FORMAT_PATTERN = re.compile(
    r"\*\*\*(?P<bold_italic>.+?)\*\*\*"
    r"|\*\*(?P<bold>.+?)\*\*"
    r"|\*(?P<italic>.+?)\*",
    re.DOTALL,
)


def generate_docx(
    document: Document,
    markdown_content: str,
    output_path: Optional[Union[str, Path]] = None,
) -> Path:
    """Generate a DOCX file from markdown content.

    Args:
        document: The Document the markdown was generated from. Used
            only to derive the default output filename
            (outputs/docx/<source-pdf-stem>.docx) when output_path is
            not given.
        markdown_content: Markdown produced by
            src.markdown.markdown_builder.build_markdown.
        output_path: Where to write the .docx file. Defaults to
            outputs/docx/<source-pdf-stem>.docx.

    Returns:
        The path the DOCX file was written to.
    """
    resolved_path = _resolve_output_path(document, output_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Generating DOCX for '{}'", document.source_pdf_path)

    docx_document = DocxDocument()
    _apply_default_style(docx_document)
    _apply_core_properties(docx_document, document)

    # Build file_path maps for alignment and decorative status from Document.images.
    image_alignment_map = _build_image_alignment_map(document)
    decorative_paths = _build_decorative_set(document)
    # Lookup for IMAGE_005: maps file_path → Image so embedding results can
    # be recorded on the model for post-generation validation.
    images_by_path = {img.file_path: img for img in document.images}

    content_lines = [line.strip() for line in markdown_content.splitlines() if line.strip()]
    pending_caption_after_image = False
    in_front_matter_zone = False
    front_matter_kinds = _front_matter_kinds(document.front_matter)
    front_matter_index = 0
    footnote_registry = _FootnoteRegistry()
    pipe_table_rows: list = []
    pipe_table_header_count = 0
    pending_table_id: Optional[str] = None
    # Build id→Table lookup for semantic rendering (FEATURE_015.1).
    tables_by_id = {t.table_id: t for t in document.tables}

    def flush_pipe_table() -> None:
        nonlocal pipe_table_rows, pipe_table_header_count, pending_table_id
        if not pipe_table_rows:
            return
        table_model = tables_by_id.get(pending_table_id) if pending_table_id else None
        if table_model is not None:
            _add_semantic_table(docx_document, table_model)
        else:
            _add_pipe_table(docx_document, pipe_table_rows, pipe_table_header_count)
        pipe_table_rows = []
        pipe_table_header_count = 0
        pending_table_id = None

    for index, line in enumerate(content_lines):
        # Table-summary and table-id accessibility comments — handled
        # separately; never rendered as body text.
        if _TABLE_SUMMARY_COMMENT_PATTERN.match(line):
            continue

        # Pipe table rows accumulate until a non-table line triggers flush.
        if _PIPE_TABLE_ROW_PATTERN.match(line):
            if _PIPE_TABLE_SEPARATOR_PATTERN.match(line):
                # Separator row marks all rows seen so far as header rows.
                pipe_table_header_count = len(pipe_table_rows)
            else:
                pipe_table_rows.append(line)
            continue

        # Any non-table-row line: flush a pending pipe table first.
        flush_pipe_table()

        # Table-id anchor: record which table model the next pipe rows
        # belong to.  flush_pipe_table() above already handled any
        # previously pending table.
        table_id_match = _TABLE_ID_COMMENT_PATTERN.match(line)
        if table_id_match:
            pending_table_id = table_id_match.group(1)
            pending_caption_after_image = False
            continue

        # *Caption* line that belongs to a pending semantic table: skip
        # here — _add_semantic_table() will render it from the Table model.
        # Only skipped when we're between a table-id comment and the first
        # pipe row (pipe_table_rows is empty and pending_table_id is set).
        if pending_table_id is not None and not pipe_table_rows:
            caption_match = _CAPTION_PATTERN.match(line)
            if caption_match:
                continue

        if line == PAGE_BREAK_MARKER:
            is_trailing_break = index == len(content_lines) - 1
            if not is_trailing_break:
                # A break after the very last page's content would only
                # produce a spurious blank trailing page in Word, since
                # there is no further page to align with.
                docx_document.add_page_break()
            pending_caption_after_image = False
            in_front_matter_zone = False
            pending_table_id = None
            continue

        heading_match = _HEADING_PATTERN.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            _add_heading(docx_document, level, text)
            pending_caption_after_image = False
            # Front matter (if any) renders immediately after page 1's
            # H6 marker - see module docstring. Only that exact position
            # ever opens the zone, so later headings elsewhere never do.
            in_front_matter_zone = (
                level == 6 and index == 0 and front_matter_index < len(front_matter_kinds)
            )
            continue

        if in_front_matter_zone:
            kind = front_matter_kinds[front_matter_index]
            front_matter_index += 1
            _add_front_matter_line(docx_document, kind, document.front_matter)
            in_front_matter_zone = front_matter_index < len(front_matter_kinds)
            continue

        image_match = _IMAGE_PATTERN.match(line)
        if image_match:
            # Phase F.4: group(1) is the markdown alt text - already
            # present in the parsed line, previously discarded here.
            # Reading it from markdown (not re-deriving it from Document)
            # keeps this module's existing principle intact: markdown,
            # not the Document model, is body structure's source of truth.
            img_path = image_match.group(2)
            alignment = image_alignment_map.get(img_path, WD_ALIGN_PARAGRAPH.CENTER)
            is_decorative = img_path in decorative_paths
            embedded = _add_image(
                docx_document,
                img_path,
                alt_text=image_match.group(1),
                alignment=alignment,
                decorative=is_decorative,
            )
            image_obj = images_by_path.get(img_path)
            if image_obj is not None:
                image_obj.embedded_in_docx = embedded
            pending_caption_after_image = True
            continue

        caption_match = _CAPTION_PATTERN.match(line)
        if pending_caption_after_image and caption_match:
            _add_caption(docx_document, caption_match.group(1))
            pending_caption_after_image = False
            continue

        footnote_def_match = _FOOTNOTE_DEFINITION_PATTERN.match(line)
        if footnote_def_match:
            _add_footnote_definition(
                footnote_registry,
                label=footnote_def_match.group(1),
                body_text=footnote_def_match.group(2),
            )
            pending_caption_after_image = False
            continue

        # Semantic list rendering (FEATURE_016C): detect bullet or numbered
        # list items before falling through to plain body paragraph.
        bullet_match = _BULLET_LIST_PATTERN.match(line)
        if bullet_match:
            _add_list_paragraph(
                docx_document, bullet_match.group(2), "List Bullet", footnote_registry
            )
            pending_caption_after_image = False
            continue

        numbered_match = _NUMBERED_LIST_PATTERN.match(line)
        if numbered_match:
            _add_list_paragraph(
                docx_document, numbered_match.group(2), "List Number", footnote_registry
            )
            pending_caption_after_image = False
            continue

        _add_body_paragraph(docx_document, line, footnote_registry)
        pending_caption_after_image = False

    # Flush any pipe table still open at end of document.
    flush_pipe_table()

    if footnote_registry.has_entries():
        _attach_footnotes_part(docx_document, footnote_registry)

    docx_document.save(str(resolved_path))
    logger.info("Saved DOCX to '{}'", resolved_path)
    return resolved_path


def _safe_run_text(text: str) -> str:
    """Last-resort defense-in-depth guard (XML Sanitization Architecture,
    Layer 3) - see module docstring. Strips any character illegal in
    OOXML/XML that somehow still reached this point, even though
    Layer 1 (src/utils/text_sanitization.py) should already have
    removed it upstream. Logs loudly when it actually changes
    something, since that should never happen in normal operation.
    """
    cleaned, removed = sanitize_xml_text(text)
    if removed:
        logger.error(
            "DOCX export safety guard removed {} XML-invalid character(s) ({}) that "
            "should have been sanitized upstream (Layer 1): {!r}",
            len(removed),
            ", ".join(removed),
            text[:80],
        )
    return cleaned


def _resolve_output_path(document: Document, output_path: Optional[Union[str, Path]]) -> Path:
    if output_path is not None:
        return Path(output_path)
    stem = Path(document.source_pdf_path).stem
    return DEFAULT_OUTPUT_DIR / f"{stem}.docx"


def _apply_core_properties(docx_document: DocxDocument, document: Document) -> None:
    """Write reviewer-set accessibility properties into DOCX CoreProperties.

    These map to Dublin Core / OPC standard fields that Word, NVDA, and
    JAWS can all read: dc:language, dc:title, dc:creator, dc:subject.
    Only set when the reviewer has explicitly provided a value via the
    Metadata panel (FEATURE_016F) — never overwrite with a blank string.
    """
    props = docx_document.core_properties
    m = document.metadata
    if m.title:
        props.title = m.title
    if m.author:
        props.author = m.author
    if m.subject:
        props.subject = m.subject
    if m.language:
        props.language = m.language


def _apply_default_style(docx_document: DocxDocument) -> None:
    normal_style = docx_document.styles["Normal"]
    normal_style.font.name = _FONT_NAME
    normal_style.font.size = Pt(_BODY_FONT_SIZE_PT)
    normal_style.font.color.rgb = _BLACK


def _add_heading(docx_document: DocxDocument, level: int, text: str) -> None:
    """Add a heading using Word's built-in "Heading N" style.

    Built-in Heading 1-9 styles are what Word's Navigation Pane reads
    directly - no additional outline-level configuration is needed.
    Font overrides are applied on top per docs/HEADING_RULES.md.
    """
    text = _safe_run_text(text)
    paragraph = docx_document.add_heading(text, level=level)
    if not paragraph.runs:
        # add_heading() creates zero runs for empty/whitespace-only text,
        # which would otherwise leave the paragraph with no run to apply
        # formatting to - it would then render with Word's built-in
        # Heading-N theme defaults (wrong font/size/color) instead of
        # docs/HEADING_RULES.md's required formatting.
        paragraph.add_run(text)
    if level == 6:
        # H6 page markers must inherit Heading 6 style defaults with no
        # run-property overrides - matching the benchmark human-remediated
        # DOCX convention (bare numeric text, no rpr element).
        return
    size_pt = _HEADING_FONT_SIZES_PT[level]
    for run in paragraph.runs:
        run.font.name = _FONT_NAME
        run.font.size = Pt(size_pt)
        run.font.bold = True
        run.font.color.rgb = _BLACK


def _parse_inline_format(text: str) -> List[Tuple[str, bool, bool]]:
    """Split ``text`` at ``***...***`` / ``**...**`` / ``*...*`` markers.

    Returns a list of ``(segment_text, is_bold, is_italic)`` tuples. Segments
    between markers are plain (False, False). Markers emitted by
    markdown_builder._apply_inline_format (016G) only; not a general
    CommonMark parser.
    """
    segments: List[Tuple[str, bool, bool]] = []
    pos = 0
    for m in _INLINE_FORMAT_PATTERN.finditer(text):
        if m.start() > pos:
            segments.append((text[pos : m.start()], False, False))
        if m.group("bold_italic") is not None:
            segments.append((m.group("bold_italic"), True, True))
        elif m.group("bold") is not None:
            segments.append((m.group("bold"), True, False))
        else:
            segments.append((m.group("italic"), False, True))
        pos = m.end()
    if pos < len(text):
        segments.append((text[pos:], False, False))
    return segments


def _add_body_text_with_inline_format(
    paragraph: Paragraph, text: str, registry: _FootnoteRegistry
) -> None:
    """Parse ``***...***`` / ``**...**`` / ``*...*`` inline markers in
    ``text`` and emit each segment as a formatted run (016G). Footnote
    references within a formatted segment inherit the segment's bold/italic.
    """
    for segment_text, is_bold, is_italic in _parse_inline_format(text):
        _add_text_with_footnote_references(
            paragraph, segment_text, registry, bold=is_bold, italic=is_italic
        )


def _add_body_paragraph(
    docx_document: DocxDocument, text: str, registry: _FootnoteRegistry
) -> None:
    paragraph = docx_document.add_paragraph()
    _add_body_text_with_inline_format(paragraph, text, registry)


def _add_list_paragraph(
    docx_document: DocxDocument,
    text: str,
    style: str,
    registry: _FootnoteRegistry,
) -> None:
    """Add a list item using Word's built-in 'List Bullet' or 'List Number'
    paragraph style (FEATURE_016C semantic list accessibility).

    Screen readers announce "list of N items" when entering a sequence of
    paragraphs with Word list styles, and "bullet" / number for each item.
    Plain paragraphs with a leading '•' character receive no such announcement.

    Falls back to a plain body paragraph if the style is absent from the
    template, to avoid crashing on minimal documents.
    """
    try:
        paragraph = docx_document.add_paragraph(style=style)
    except KeyError:
        paragraph = docx_document.add_paragraph()
    _add_text_with_footnote_references(paragraph, text, registry)


def _add_text_with_footnote_references(
    paragraph: Paragraph,
    text: str,
    registry: _FootnoteRegistry,
    bold: bool = False,
    italic: bool = False,
) -> None:
    """Add ``text`` to ``paragraph`` as one or more runs, splitting out
    any ``[^label]`` footnote/endnote references (Phase K) into their
    own native OOXML ``w:footnoteReference`` run. Text with no
    references at all renders as exactly one plain run - unchanged from
    this function's pre-Phase-K behavior.

    ``bold`` / ``italic`` are forwarded to every plain-text run so that
    callers that have already parsed inline format markers (016G) can
    propagate formatting within each already-classified segment.
    Footnote reference runs are not affected — they use the built-in
    ``FootnoteReference`` character style.
    """
    position = 0
    has_reference = False
    for match in _FOOTNOTE_REFERENCE_PATTERN.finditer(text):
        has_reference = True
        if match.start() > position:
            _add_plain_run(paragraph, text[position : match.start()], bold=bold, italic=italic)
        _add_footnote_reference_run(paragraph, match.group(1), registry)
        position = match.end()

    if position < len(text) or not has_reference:
        _add_plain_run(paragraph, text[position:], bold=bold, italic=italic)


def _add_plain_run(
    paragraph: Paragraph, text: str, bold: bool = False, italic: bool = False
) -> None:
    if not text:
        return
    run = paragraph.add_run(_safe_run_text(text))
    run.font.name = _FONT_NAME
    run.font.size = Pt(_BODY_FONT_SIZE_PT)
    run.font.bold = bold
    run.font.italic = True if italic else None
    run.font.color.rgb = _BLACK


def _add_footnote_reference_run(
    paragraph: Paragraph, label: str, registry: _FootnoteRegistry
) -> None:
    """A native OOXML ``w:footnoteReference`` run.

    Word auto-numbers and renders the printed superscript digit from the
    referenced ``w:footnote`` entry in ``word/footnotes.xml``; no
    explicit text content is needed here.  The ``FootnoteReference``
    character style is requested via ``w:rStyle`` (Word's built-in style
    for footnote markers) with an explicit ``w:vertAlign superscript``
    as a fallback in case the style is not defined in the template.
    """
    fn_id = registry.get_or_assign_id(label)

    run = OxmlElement("w:r")
    run_properties = OxmlElement("w:rPr")

    style = OxmlElement("w:rStyle")
    style.set(qn("w:val"), "FootnoteReference")
    run_properties.append(style)

    vert_align = OxmlElement("w:vertAlign")
    vert_align.set(qn("w:val"), "superscript")
    run_properties.append(vert_align)

    run.append(run_properties)

    footnote_ref = OxmlElement("w:footnoteReference")
    footnote_ref.set(qn("w:id"), str(fn_id))
    run.append(footnote_ref)

    paragraph._p.append(run)


def _add_footnote_definition(
    registry: _FootnoteRegistry, label: str, body_text: str
) -> None:
    """Register a footnote body for inclusion in ``word/footnotes.xml``.

    Native OOXML footnotes live in a separate document part, not as
    paragraphs in the main body.  No paragraph is added here; the body
    text is stored in the registry and the part is built and attached
    after the main rendering loop completes.
    """
    registry.register_body(label, _safe_run_text(body_text))


def _add_bookmark(paragraph: Paragraph, name: str, bookmark_id: int) -> None:
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bookmark_id))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bookmark_id))
    paragraph._p.append(start)
    paragraph._p.append(end)


def _bookmark_name(label: str) -> str:
    """Word bookmark names must start with a letter and contain only
    letters/digits/underscores - sanitized from the markdown label
    (e.g. "p3-1" -> "footnote_p3_1"), consistently between reference
    and definition so the two always match."""
    return "footnote_" + _BOOKMARK_NAME_SANITIZE_PATTERN.sub("_", label)


def _display_number(label: str) -> str:
    """The human-visible printed number embedded in a footnote label
    (e.g. "p3-1" -> "1") - falls back to the raw label if it doesn't
    match the expected shape, rather than raising on arbitrary markdown
    text this module didn't itself generate."""
    match = _LABEL_DISPLAY_NUMBER_PATTERN.search(label)
    return match.group(1) if match else label


def _build_footnotes_xml(entries: List[Tuple[int, str]]) -> bytes:
    """Build the raw XML bytes for ``word/footnotes.xml``.

    ``entries`` is a list of ``(id, body_text)`` pairs in ascending id
    order.  IDs -1 and 0 are the Word-required separator footnotes;
    user footnotes start at 1.  The ``w:footnoteRef`` element in each
    body paragraph is Word's auto-number placeholder — it renders the
    correct printed number without any hard-coded text.
    """
    W = _W_NS
    WP = "{%s}" % W

    def w(tag: str) -> str:
        return WP + tag

    root = etree.Element(w("footnotes"), nsmap={"w": W})

    for fn_type, fn_id, child_tag in (
        ("separator", -1, "separator"),
        ("continuationSeparator", 0, "continuationSeparator"),
    ):
        fn_el = etree.SubElement(root, w("footnote"))
        fn_el.set(w("type"), fn_type)
        fn_el.set(w("id"), str(fn_id))
        p = etree.SubElement(fn_el, w("p"))
        pPr = etree.SubElement(p, w("pPr"))
        spacing = etree.SubElement(pPr, w("spacing"))
        spacing.set(w("after"), "0")
        spacing.set(w("line"), "240")
        spacing.set(w("lineRule"), "auto")
        r = etree.SubElement(p, w("r"))
        etree.SubElement(r, w(child_tag))

    for fn_id, body_text in entries:
        fn_el = etree.SubElement(root, w("footnote"))
        fn_el.set(w("id"), str(fn_id))

        p = etree.SubElement(fn_el, w("p"))

        # Auto-number marker rendered by Word
        ref_r = etree.SubElement(p, w("r"))
        ref_rPr = etree.SubElement(ref_r, w("rPr"))
        rStyle = etree.SubElement(ref_rPr, w("rStyle"))
        rStyle.set(w("val"), "FootnoteReference")
        vert = etree.SubElement(ref_rPr, w("vertAlign"))
        vert.set(w("val"), "superscript")
        etree.SubElement(ref_r, w("footnoteRef"))

        # Body text run
        body_r = etree.SubElement(p, w("r"))
        body_rPr = etree.SubElement(body_r, w("rPr"))
        rFonts = etree.SubElement(body_rPr, w("rFonts"))
        rFonts.set(w("ascii"), _FONT_NAME)
        rFonts.set(w("hAnsi"), _FONT_NAME)
        sz_el = etree.SubElement(body_rPr, w("sz"))
        sz_el.set(w("val"), str(_FOOTNOTE_FONT_SIZE_PT * 2))
        szCs_el = etree.SubElement(body_rPr, w("szCs"))
        szCs_el.set(w("val"), str(_FOOTNOTE_FONT_SIZE_PT * 2))
        color_el = etree.SubElement(body_rPr, w("color"))
        color_el.set(w("val"), "000000")

        t = etree.SubElement(body_r, w("t"))
        t.set(_XML_SPACE, "preserve")
        t.text = " " + body_text  # leading space after auto-numbered ref mark

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _attach_footnotes_part(
    docx_document: DocxDocument, registry: _FootnoteRegistry
) -> None:
    """Build ``word/footnotes.xml`` from the registry and attach it to
    the document package with the correct OPC relationship and content
    type.  Word requires all three (the XML file, the relationship from
    ``document.xml``, and the content-type override) to recognise the
    footnotes part.
    """
    xml_bytes = _build_footnotes_xml(registry.ordered_entries())
    footnotes_part = Part(
        partname=PackURI("/word/footnotes.xml"),
        content_type=_FOOTNOTES_CONTENT_TYPE,
        blob=xml_bytes,
        package=docx_document.part.package,
    )
    docx_document.part.relate_to(footnotes_part, _FOOTNOTES_RELATIONSHIP_TYPE)


def _build_image_alignment_map(document: Document) -> Dict[str, WD_ALIGN_PARAGRAPH]:
    """Return a file_path → WD_ALIGN_PARAGRAPH map derived from each Image's bbox.

    Detects left / center / right alignment by comparing the image center
    against the page's physical width (Page.width_pt). Falls back to CENTER
    when bbox or width_pt is absent (e.g. older pipeline runs or test fixtures).
    A 10% tolerance band around page center is treated as centered.
    """
    page_width_by_num: Dict[int, float] = {}
    for page in document.pages:
        if page.width_pt:
            page_width_by_num[page.page_number] = page.width_pt

    result: Dict[str, WD_ALIGN_PARAGRAPH] = {}
    for image in document.images:
        if image.bbox is None or image.page_number not in page_width_by_num:
            result[image.file_path] = WD_ALIGN_PARAGRAPH.CENTER
            continue
        page_width = page_width_by_num[image.page_number]
        image_center = image.bbox.x0 + (image.bbox.x1 - image.bbox.x0) / 2
        margin = page_width * 0.10
        if abs(image_center - page_width / 2) <= margin:
            result[image.file_path] = WD_ALIGN_PARAGRAPH.CENTER
        elif image_center < page_width / 2:
            result[image.file_path] = WD_ALIGN_PARAGRAPH.LEFT
        else:
            result[image.file_path] = WD_ALIGN_PARAGRAPH.RIGHT
    return result


def _build_decorative_set(document: Document) -> set:
    """Return the set of file_paths for images marked as DECORATIVE by the reviewer."""
    from src.models.figure import AltTextStatus
    result = set()
    for image in document.images:
        if (
            image.figure is not None
            and image.figure.alt_text_status == AltTextStatus.DECORATIVE
        ):
            result.add(image.file_path)
    return result


def _add_pipe_table(
    docx_document: DocxDocument,
    rows: list,
    header_row_count: int,
) -> None:
    """Render accumulated pipe-table rows as a DOCX table.

    rows is a list of raw pipe-table line strings, e.g. "| A | B |".
    header_row_count is how many of the first rows are header rows
    (i.e. came before the separator in the markdown).

    Cells within each row are split on " | " after stripping the outer
    pipes.  A pipe character escaped as "\\|" in the markdown is
    restored to a literal "|" in the cell text.
    """
    if not rows:
        return

    parsed: list = []
    for row_line in rows:
        # Strip leading/trailing whitespace and outer pipes, then split.
        inner = row_line.strip().lstrip("|").rstrip("|")
        cells = [c.strip().replace("\\|", "|") for c in inner.split("|")]
        parsed.append(cells)

    if not parsed:
        return

    num_cols = max(len(r) for r in parsed)
    if num_cols == 0:
        return

    try:
        table = docx_document.add_table(rows=len(parsed), cols=num_cols, style="Table Grid")
    except KeyError:
        # "Table Grid" not in this template — fall back to unstyled.
        table = docx_document.add_table(rows=len(parsed), cols=num_cols)

    for row_idx, cell_texts in enumerate(parsed):
        is_header = row_idx < header_row_count
        docx_row = table.rows[row_idx]
        for col_idx in range(num_cols):
            text = cell_texts[col_idx] if col_idx < len(cell_texts) else ""
            cell = docx_row.cells[col_idx]
            para = cell.paragraphs[0]
            para.clear()
            run = para.add_run(_safe_run_text(text))
            run.font.name = _FONT_NAME
            run.font.size = Pt(_BODY_FONT_SIZE_PT)
            run.font.color.rgb = _BLACK
            run.bold = is_header


def _add_caption(docx_document: DocxDocument, text: str) -> None:
    paragraph = docx_document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(_safe_run_text(text))
    run.font.name = _FONT_NAME
    run.font.size = Pt(_BODY_FONT_SIZE_PT)
    run.font.italic = True
    run.font.color.rgb = _BLACK


def _front_matter_kinds(front_matter: Optional[FrontMatter]) -> List[str]:
    """Which of "title"/"author"/"affiliation" lines
    src/markdown/markdown_builder.py's _render_front_matter_blocks()
    actually emitted, in order - mirrors that function's own
    if-authors/if-affiliations gating exactly, so this module consumes
    precisely as many lines as were rendered, never more or fewer."""
    if front_matter is None or not front_matter.title:
        return []
    kinds = ["title"]
    if front_matter.authors:
        kinds.append("author")
    if front_matter.affiliations:
        kinds.append("affiliation")
    return kinds


def _add_front_matter_line(
    docx_document: DocxDocument, kind: str, front_matter: Optional[FrontMatter]
) -> None:
    if front_matter is None:
        return
    if kind == "title":
        _add_title(docx_document, front_matter.title or "")
    elif kind == "author":
        _add_byline(docx_document, ", ".join(front_matter.authors))
    else:
        _add_affiliation(docx_document, "; ".join(front_matter.affiliations))


def _add_title(docx_document: DocxDocument, text: str) -> None:
    """A document's title - Word's built-in "Title" style (so it reads
    correctly in Word's outline/accessibility tooling) plus this
    module's usual explicit font override on top, the same two-step
    pattern _add_heading() already uses for "Heading N"."""
    paragraph = docx_document.add_paragraph(style="Title")
    run = paragraph.add_run(_safe_run_text(text))
    run.font.name = _FONT_NAME
    run.font.size = Pt(_TITLE_FONT_SIZE_PT)
    run.font.bold = True
    run.font.color.rgb = _BLACK


def _add_byline(docx_document: DocxDocument, text: str) -> None:
    """An author byline - Word's built-in "Subtitle" style plus an
    explicit italic font override."""
    paragraph = docx_document.add_paragraph(style="Subtitle")
    run = paragraph.add_run(_safe_run_text(text))
    run.font.name = _FONT_NAME
    run.font.size = Pt(_BYLINE_FONT_SIZE_PT)
    run.font.italic = True
    run.font.color.rgb = _BLACK


def _add_affiliation(docx_document: DocxDocument, text: str) -> None:
    """An author's institutional affiliation - plain body-sized text,
    visually distinct from the byline above it only by not being
    italic/larger, matching how the markdown rendering of this same
    line (src/markdown/markdown_builder.py) is unformatted plain text
    too."""
    paragraph = docx_document.add_paragraph()
    run = paragraph.add_run(_safe_run_text(text))
    run.font.name = _FONT_NAME
    run.font.size = Pt(_BODY_FONT_SIZE_PT)
    run.font.bold = False
    run.font.color.rgb = _BLACK


def _add_image(
    docx_document: DocxDocument,
    image_path: str,
    alt_text: str = "",
    alignment: WD_ALIGN_PARAGRAPH = WD_ALIGN_PARAGRAPH.CENTER,
    decorative: bool = False,
) -> bool:
    """Insert an image inline with text at the specified alignment.

    alignment defaults to CENTER (existing behavior). Pass a value from
    _build_image_alignment_map() to match the image's original PDF position.

    decorative=True sets descr="" and title="" explicitly so screen readers
    skip the image. When False (default), non-empty alt_text is set on descr
    and title; an empty alt_text leaves both unset (existing behavior).

    Missing or unreadable image files are logged and skipped rather
    than raised, so one bad image reference does not abort generation
    of the rest of the document.

    Returns True when the image was successfully embedded, False when it was
    skipped (file not found or add_picture raised). The caller records this
    result on the Image model so IMAGE_005 validation can surface silent drops.
    """
    path = Path(image_path)
    if not path.is_file():
        logger.warning("Image file not found, skipping insertion: {}", path)
        return False

    paragraph = docx_document.add_paragraph()
    paragraph.alignment = alignment
    run = paragraph.add_run()

    picture_source = _docx_compatible_picture_source(path)

    try:
        picture = run.add_picture(picture_source)
    except Exception as exc:  # python-docx raises various error types on bad images
        logger.warning("Failed to insert image '{}': {}", path, exc)
        return False

    if picture.width > _MAX_IMAGE_WIDTH:
        aspect_ratio = picture.height / picture.width
        picture.width = _MAX_IMAGE_WIDTH
        picture.height = Emu(int(_MAX_IMAGE_WIDTH * aspect_ratio))

    if decorative:
        doc_properties = picture._inline.docPr
        doc_properties.set("descr", "")
        doc_properties.set("title", "")
    elif alt_text:
        safe_alt_text = _safe_run_text(alt_text)
        doc_properties = picture._inline.docPr
        doc_properties.set("descr", safe_alt_text)
        doc_properties.set("title", safe_alt_text)

    return True


def _add_semantic_table(docx_document: DocxDocument, table) -> None:
    """Render a Table model as a fully accessible DOCX table.

    Unlike _add_pipe_table() which parses markdown pipe strings, this
    function reads the Table model directly to produce:
      - Caption as a centered italic paragraph above the table (same
        style as figure captions; placed before the table so Word's
        document order matches the visual order).
      - w:tblHeader on every header row so NVDA/JAWS/Narrator/VoiceOver
        announce column context when a user navigates into a data cell.
      - Bold formatting on is_header and is_row_header cells.
      - Merged cells via cell.merge() for col_span / row_span > 1.
      - Summary as a small italic paragraph below the table (the WCAG
        H73-equivalent prose description for complex tables).
    """
    if table.caption:
        _add_caption(docx_document, table.caption)

    if not table.rows:
        return

    row_count = len(table.rows)
    col_count = max(table.col_count, 1)

    try:
        docx_table = docx_document.add_table(rows=row_count, cols=col_count, style="Table Grid")
    except KeyError:
        docx_table = docx_document.add_table(rows=row_count, cols=col_count)

    for row_idx, table_row in enumerate(table.rows):
        docx_row = docx_table.rows[row_idx]
        if table_row.is_header_row:
            _set_row_tbl_header(docx_row)
        for col_idx in range(col_count):
            cell = (
                table_row.cells[col_idx]
                if col_idx < len(table_row.cells)
                else None
            )
            text = cell.text if cell else ""
            is_bold = bool(cell and (cell.is_header or cell.is_row_header))
            docx_cell = docx_row.cells[col_idx]
            para = docx_cell.paragraphs[0]
            para.clear()
            run = para.add_run(_safe_run_text(text))
            run.font.name = _FONT_NAME
            run.font.size = Pt(_BODY_FONT_SIZE_PT)
            run.font.color.rgb = _BLACK
            run.bold = is_bold

    _apply_cell_merges(docx_table, table)

    if table.summary:
        _add_table_summary(docx_document, table.summary)


def _set_row_tbl_header(docx_row) -> None:
    """Set w:tblHeader on a table row so screen readers announce column context.

    w:tblHeader is the OOXML attribute that tells NVDA, JAWS, Narrator,
    and VoiceOver that this row contains column headers.  Without it,
    navigating cells announces only the cell value — blind users lose
    all column context.  python-docx has no public API for this; we
    build it directly on the row's w:trPr element.
    """
    tr = docx_row._tr
    trPr = tr.find(qn("w:trPr"))
    if trPr is None:
        trPr = OxmlElement("w:trPr")
        tr.insert(0, trPr)
    tbl_header = OxmlElement("w:tblHeader")
    trPr.append(tbl_header)


def _apply_cell_merges(docx_table, table) -> None:
    """Apply col_span / row_span from the Table model via python-docx merge().

    cell.merge(other) merges the rectangular region from cell (top-left)
    to other (bottom-right).  Only cells where span > 1 trigger a merge;
    auto-detected tables have all spans = 1 so this is a no-op for them.
    Manually-created tables edited by a reviewer can have spans set.
    """
    row_count = len(table.rows)
    col_count = table.col_count

    for row_idx, table_row in enumerate(table.rows):
        for cell in table_row.cells:
            col_idx = cell.col_index
            col_span = cell.col_span if cell.col_span else 1
            row_span = cell.row_span if cell.row_span else 1
            if col_span <= 1 and row_span <= 1:
                continue
            end_row = min(row_idx + row_span - 1, row_count - 1)
            end_col = min(col_idx + col_span - 1, col_count - 1)
            if end_row == row_idx and end_col == col_idx:
                continue
            try:
                start_cell = docx_table.cell(row_idx, col_idx)
                end_cell = docx_table.cell(end_row, end_col)
                start_cell.merge(end_cell)
            except Exception as exc:
                logger.warning(
                    "Table cell merge failed at ({},{})→({},{}): {}",
                    row_idx, col_idx, end_row, end_col, exc,
                )


def _add_table_summary(docx_document: DocxDocument, summary_text: str) -> None:
    """Render the WCAG H73-equivalent summary as a small italic paragraph below the table.

    The summary is intended for screen reader users who need a prose
    description of a complex table before (or after) navigating its cells.
    It is rendered visibly below the table rather than hidden, because DOCX
    has no native table-summary attribute equivalent to HTML's summary="…"
    and this approach is the WCAG-recommended technique for Word documents.
    """
    paragraph = docx_document.add_paragraph()
    run = paragraph.add_run(_safe_run_text(f"Table summary: {summary_text}"))
    run.font.name = _FONT_NAME
    run.font.size = Pt(10)
    run.font.italic = True
    run.font.color.rgb = RGBColor(0x44, 0x44, 0x44)


def _docx_compatible_picture_source(path: Path) -> Union[str, io.BytesIO]:
    """Return whatever run.add_picture() should be given for this file.

    CMYK Image DOCX Embedding Repair: python-docx recognizes a JPEG only
    by a literal "JFIF"/"Exif" marker at byte offset 6
    (docx.image.image._ImageHeaderFactory/SIGNATURES) - it has no
    Pillow/libjpeg dependency of its own. Some PDF producers (confirmed
    on the Brinkman regression PDF's 3 figure/decorative images) emit
    CMYK JPEGs with only an Adobe APP14 marker and no JFIF segment at
    all, which that signature check cannot recognize, so
    run.add_picture() previously raised UnrecognizedImageError for an
    otherwise perfectly readable image - markdown rendering was always
    unaffected, since it never runs the file through python-docx.

    Only CMYK images are affected by this; RGB (or any other mode)
    files are returned as the original path string, completely
    unchanged from before this repair. The converted bytes exist only
    in memory for this one call - the original file on disk is never
    written to, so image extraction, markdown rendering, and the
    Image/Figure models (which only ever reference the file's path) are
    all unaffected.

    Deliberately no channel-inversion step: visual verification against
    all 3 of Brinkman's real CMYK images confirmed a plain CMYK->RGB
    convert already renders correct colors for this corpus - the
    widely-cited "Adobe CMYK JPEGs decode inverted" workaround does NOT
    apply here, and was confirmed (not assumed) to produce wrong
    (near-black) output if applied. See the CMYK Image DOCX Embedding
    Audit for the comparison.
    """
    try:
        with PILImage.open(path) as pil_image:
            if pil_image.mode != "CMYK":
                return str(path)
            rgb_image = pil_image.convert("RGB")
    except Exception as exc:
        logger.warning("Could not inspect image color mode for '{}': {}", path, exc)
        return str(path)

    buffer = io.BytesIO()
    rgb_image.save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer
