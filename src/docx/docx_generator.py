"""DOCX generation for RAWRS.

Converts the canonical markdown produced by src/markdown/markdown_builder.py
into a remediation-ready DOCX file: H1-H6 headings mapped to Word's
built-in heading styles (so they appear in the Navigation Pane), page
breaks preserving PDF page boundaries, and centered inline images with
captions.

**P4b: prose, headings and pages come from the ContentStream, not from
the markdown.** What stood here said the markdown string - not the
Document model - was the source of truth for body structure, because it
was the artifact a reviewer edited. That stopped being true when every
reviewer edit became a correction on the semantic object (W-1/W-2b): the
model now holds the reviewed text, and the markdown is one rendering of
it, not the record. So this module resolves each ``PARAGRAPH`` node to
its ``Paragraph`` and each ``HEADING``/``PAGE_MARKER`` node to its
``Heading`` **by id**, in traversal order, and emits a page break because
another ``Page`` exists rather than because a ``<!-- pagebreak -->``
comment appeared.

What still comes from the markdown, and is out of scope here: images and
their captions, tables, lists, note definitions, and the whole of any
page with no ``TextBlock`` (41 of the benchmark corpus' 161 - see
``is_stream_page``). Those lines keep their positions around the prose
run, which is why ``markdown_content`` is still a parameter.

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

Footnote/endnote wiring (Phase K): this module renders whatever
``[^label]`` inline references and ``[^label]: body`` definitions
already exist in the markdown (src/markdown/markdown_builder.py decides
where those go; this module only renders them) as native OOXML notes in
their own document part. python-docx 1.2.0 has no public API for that
part, so it is built directly via docx.oxml/lxml - the same documented
pattern already used for the docPr alt-text attributes above.

**Which kind of note that is, is not a markdown question (L4b).**
``Footnote.note_type`` on the Semantic Document is the answer, and
_NoteRegistries is the only place this module asks it. The label in
``[^label]`` is used purely as an identity to look the note up by -
exactly the role ``<!-- table-id: ... -->`` already plays for tables -
so note type is never inferred from placement, section headings,
rendered text or the shape of the markdown. Before L4b there was no
such lookup and no endnotes part: every note, whatever the document
said it was, became a ``w:footnoteReference`` in word/footnotes.xml,
and Word rendered a document's endnotes at the foot of its pages. The
benchmark's human-remediated DOCX files put all 54 of their notes in
word/endnotes.xml, so that loss was measurable as well as wrong.

Everything else about note rendering still comes from parsing the
markdown - where a reference sits in the prose, and which definitions
exist at all. That is the remaining debt this milestone deliberately
did not take on; see docs/KNOWN_LIMITATIONS.md.

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
from typing import Dict, List, NamedTuple, Optional, Tuple, Union

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
from src.models.content_stream import ContentKind
from src.structure.content_stream import build_content_stream
from src.models.contracts import Document, Footnote, FrontMatter, NoteType
from src.models.inline_format import format_runs
from src.models.note_references import resolve_note_references
from src.structure.paragraph_assembly import absorbed_block_ids
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

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


class _NotePartSpec(NamedTuple):
    """The OOXML vocabulary for one kind of note part (L4b).

    Word models footnotes and endnotes identically and names every
    element differently: two parts, two relationship types, two content
    types, and matching element/style names throughout. This gathers
    that naming in one place so ``_build_notes_xml()`` and
    ``_attach_notes_part()`` are written once rather than duplicated per
    kind - which is how the endnote part came to be missing before L4b:
    there was one hard-coded footnote implementation and nowhere for a
    second kind to exist.
    """

    partname: str
    content_type: str
    relationship_type: str
    root_tag: str  # "footnotes" / "endnotes"
    item_tag: str  # "footnote"  / "endnote"
    auto_number_tag: str  # "footnoteRef" / "endnoteRef"
    reference_tag: str  # "footnoteReference" / "endnoteReference"
    reference_style: str  # Word's built-in character style for the marker


_FOOTNOTE_PART = _NotePartSpec(
    partname="/word/footnotes.xml",
    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml",
    relationship_type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes",
    root_tag="footnotes",
    item_tag="footnote",
    auto_number_tag="footnoteRef",
    reference_tag="footnoteReference",
    reference_style="FootnoteReference",
)

_ENDNOTE_PART = _NotePartSpec(
    partname="/word/endnotes.xml",
    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml",
    relationship_type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/endnotes",
    root_tag="endnotes",
    item_tag="endnote",
    auto_number_tag="endnoteRef",
    reference_tag="endnoteReference",
    reference_style="EndnoteReference",
)


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


class _NoteRegistries:
    """One registry per note part, plus the Semantic Document's answer
    about which part each note belongs in (L4b).

    ``Footnote.note_type`` is that answer, and this is the only place the
    projection asks the question. The markdown label is used purely as an
    identity - the same role ``<!-- table-id: ... -->`` already plays for
    tables - so nothing here reads placement, section headings or
    rendered text to decide what a note *is*. A label with no matching
    Footnote (a fixture, hand-written markdown, a direct generate_docx()
    call) is a footnote, which is exactly what every note was before this
    milestone: unknown provenance changes nothing.
    """

    def __init__(self, notes: List[Footnote]) -> None:
        self.footnotes = _FootnoteRegistry()
        self.endnotes = _FootnoteRegistry()
        self._endnote_labels = {
            note.label for note in notes if note.note_type == NoteType.ENDNOTE
        }

    def part_for(self, label: str) -> _NotePartSpec:
        return _ENDNOTE_PART if label in self._endnote_labels else _FOOTNOTE_PART

    def registry_for(self, label: str) -> _FootnoteRegistry:
        return self.endnotes if label in self._endnote_labels else self.footnotes


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
# List-id anchor comment emitted by markdown_builder immediately before each
# rendered list block (src/models/list_block.py). Purely a no-op marker here
# — the bullet/numbered lines themselves already flow through the existing
# FEATURE_016C list-style rendering below, so there is no ListBlock lookup
# to perform; this pattern exists only so the comment itself is skipped
# rather than rendered as literal body text.
_LIST_ID_COMMENT_PATTERN = re.compile(r"^<!-- list-id: (.+) -->$")

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


def _stream_page_markers(document: Document, stream) -> Dict[int, object]:
    """Each page's marker heading, resolved from its ``PAGE_MARKER`` node.

    P4b. The marker used to be recovered by matching ``^#{6}\\s`` against the
    first line of a page's markdown. A page's identity is not a line shape —
    it is the ``Heading`` the traversal placed at the top of that page, and
    ``Heading.text`` already carries whatever printed label the page
    numbering policy resolved (feature_009/FEATURE_018).
    """
    by_id = {str(h.id): h for h in (getattr(document, "headings", []) or [])}
    return {
        node.page_number: by_id[node.object_id]
        for node in stream.nodes
        if node.kind is ContentKind.PAGE_MARKER and node.object_id in by_id
    }


def _stream_prose(document: Document, stream) -> Dict[int, List[Tuple[str, object]]]:
    """Each page's prose as ``("heading"|"paragraph", object)``, in stream order.

    P4b. This is the whole of "the stream owns order" for DOCX: a page's
    headings and paragraphs come out in the traversal's sequence, resolved by
    identity, and nothing here reads a markdown line, a block position or a
    ``document_order`` counter.

    Two filters, both of which the Markdown projection already applies and
    neither of which is a placement decision:

    * **absorbed beats heading** (ADR-020 §3) — a heading detected from a line
      a table, note body, caption or the front matter already carries does not
      render, because the object that owns the line emits it. Dropping this
      re-emitted 8 suppressed headings when P3b tried it on the Markdown side.
    * **the front-matter title** (FE-0-005) — the title is an H1 in
      ``document.headings`` *and* a front-matter block; ``_front_matter_groups``
      renders it, so the heading must not render it a second time.
    """
    headings = {
        str(h.id): h
        for h in (getattr(document, "headings", []) or [])
        if not h.is_page_marker
    }
    paragraphs = {
        str(p.id): p
        for p in (getattr(document, "paragraphs", []) or [])
        if p.id is not None
    }
    blocks_by_page: Dict[int, list] = {}
    for block in getattr(document, "blocks", []) or []:
        blocks_by_page.setdefault(block.page_number, []).append(block)
    absorbed = {
        page: absorbed_block_ids(document, page, page_blocks)
        for page, page_blocks in blocks_by_page.items()
    }
    front_matter = getattr(document, "front_matter", None)
    title = getattr(front_matter, "title", None) if front_matter is not None else None

    prose: Dict[int, List[Tuple[str, object]]] = {}
    for node in stream.nodes:
        if node.kind is ContentKind.PARAGRAPH:
            paragraph = paragraphs.get(node.object_id)
            if paragraph is not None:
                prose.setdefault(node.page_number, []).append(("paragraph", paragraph))
        elif node.kind is ContentKind.HEADING:
            heading = headings.get(node.object_id)
            if heading is None:
                continue
            if title is not None and heading.text == title:
                continue
            if heading.source_block_id in absorbed.get(node.page_number, ()):
                continue
            prose.setdefault(node.page_number, []).append(("heading", heading))
    return prose


def _add_stream_paragraph(
    docx_document: DocxDocument,
    paragraph_object,
    blocks_by_id: Dict[str, object],
    notes_by_anchor_text: Dict[str, List[Footnote]],
    registries: _NoteRegistries,
) -> None:
    """One ``Paragraph`` as OOXML runs, with no markdown in between.

    Emphasis comes from ``format_runs`` and note positions from
    ``resolve_note_references`` — the two rules P4a moved to the model
    (``src/models/inline_format.py``, ``src/models/note_references.py``), so
    this module never inspects ``TextBlock.spans[].font_flags`` and never
    looks for ``[^label]`` in rendered text.

    ``source_block_ids`` names the lines the paragraph was assembled from,
    which is what both rules need: the blocks answer "is this emphasised",
    and only the notes anchored to *those* lines are offered for
    substitution, so a neighbouring paragraph's marker cannot be claimed here.

    The bullet/numbered test is the one thing kept from the markdown path
    (FEATURE_016C): it is a DOCX *presentation* decision about how a
    paragraph is styled, not a question about what the paragraph is, so §2's
    "retain genuinely DOCX presentation mechanics" applies. It runs against
    ``Paragraph.text`` instead of a rendered line.
    """
    contributing = [
        blocks_by_id[block_id]
        for block_id in paragraph_object.source_block_ids
        if block_id in blocks_by_id
    ]
    notes = [
        note
        for block in contributing
        for note in notes_by_anchor_text.get(block.text, [])
    ]

    text = paragraph_object.text
    style: Optional[str] = None
    bullet_match = _BULLET_LIST_PATTERN.match(text)
    numbered_match = None if bullet_match else _NUMBERED_LIST_PATTERN.match(text)
    if bullet_match:
        text, style = bullet_match.group(2), "List Bullet"
    elif numbered_match:
        text, style = numbered_match.group(2), "List Number"

    if style is None:
        docx_paragraph = docx_document.add_paragraph()
    else:
        try:
            docx_paragraph = docx_document.add_paragraph(style=style)
        except KeyError:
            docx_paragraph = docx_document.add_paragraph()

    for run in format_runs(text, contributing):
        _add_runs_with_note_references(
            docx_paragraph, run.text, notes, registries, bold=run.bold, italic=run.italic
        )


def _add_runs_with_note_references(
    docx_paragraph: Paragraph,
    text: str,
    notes: List[Footnote],
    registries: _NoteRegistries,
    bold: bool = False,
    italic: bool = False,
) -> None:
    """``text`` as runs, with each note's printed marker replaced by a native
    reference run.

    The model says where each marker is (``NoteReference.start``/``.length``)
    and which note it is; ``registries`` says which part it belongs in, from
    ``Footnote.note_type`` (L4b). Applied in ascending position because the
    slices are taken from the original string rather than rewritten into it.
    """
    position = 0
    for reference in resolve_note_references(text, notes):
        if reference.start < position:
            continue  # overlapping claim; the earlier reference already owns it
        _add_plain_run(
            docx_paragraph, text[position : reference.start], bold=bold, italic=italic
        )
        _add_note_reference_run(docx_paragraph, reference.label, registries)
        position = reference.start + reference.length
    _add_plain_run(docx_paragraph, text[position:], bold=bold, italic=italic)


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

    # P4b: the traversal, not the markdown, says what order this document's
    # prose is in, which pages exist and where each page begins.
    stream = build_content_stream(document)
    stream_pages = sorted({node.page_number for node in stream.nodes})
    page_markers = _stream_page_markers(document, stream)
    prose_by_page = _stream_prose(document, stream)
    pages_with_blocks = {b.page_number for b in document.blocks}
    blocks_by_id = {b.block_id: b for b in document.blocks}
    notes_by_anchor_text: Dict[str, List[Footnote]] = {}
    for note in document.footnotes:
        notes_by_anchor_text.setdefault(note.anchor_text, []).append(note)
    has_endnotes = any(note.note_type == NoteType.ENDNOTE for note in document.footnotes)

    content_lines = [line.strip() for line in markdown_content.splitlines() if line.strip()]
    pending_caption_after_image = False
    in_front_matter_zone = False
    front_matter_groups = _front_matter_groups(document)
    front_matter_kinds = [role for role, _ in front_matter_groups]
    front_matter_index = 0
    note_registries = _NoteRegistries(document.footnotes)
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

    # --- page identity and the prose run, both from the stream (P4b) ------- #
    page_cursor = 0
    current_page: Optional[int] = None
    marker_line_pending = False
    marker_from_node = [False]  # one-element box: rebound inside open_page()
    prose_emitted = False

    def open_page() -> None:
        """Begin the page the traversal says comes next.

        The OOXML page break is emitted here rather than at the markdown's
        ``<!-- pagebreak -->``: a break exists because there is another page
        in the document, which is a fact about ``Page``, not about a comment.
        A trailing break is impossible by construction — past the last page
        there is nothing to open — which is what the old explicit
        ``is_trailing_break`` test was for.
        """
        nonlocal current_page, marker_line_pending, prose_emitted, in_front_matter_zone
        current_page = stream_pages[page_cursor] if page_cursor < len(stream_pages) else None
        marker_line_pending = False
        prose_emitted = False
        in_front_matter_zone = False
        if current_page is None:
            # Past the last page. What follows is the generated endnotes
            # section, which has always started on a fresh page — and whether
            # one exists at all is a fact about this document's notes, not
            # about how many lines trail the final page break.
            if page_cursor > 0 and has_endnotes:
                docx_document.add_page_break()
            return
        if page_cursor > 0:
            docx_document.add_page_break()
        # Every page's markdown opens with a marker line, so one is expected
        # either way; what differs is who renders it.
        marker_line_pending = True
        marker = page_markers.get(current_page)
        if marker is not None:
            _add_heading(docx_document, marker.level.value, marker.text)
            marker_from_node[0] = True
        else:
            # No PAGE_MARKER node: no marker exists in document.headings, so
            # markdown_builder synthesized one for this page (a direct
            # build_markdown() call, a fixture, a Document that never ran
            # heading detection). Its line is the only record of it, and
            # dropping it would lose a page label the stream never saw.
            marker_from_node[0] = False
        if page_cursor == 0 and front_matter_kinds:
            in_front_matter_zone = True

    def is_stream_page() -> bool:
        """Whether this page's prose comes from the traversal.

        False for the 41 of 161 corpus pages with no ``TextBlock`` (§7): with
        no blocks there are no paragraphs, so the traversal places nothing and
        the markdown line path — the only thing that ever rendered those
        pages — keeps rendering them. Requiring an actual paragraph, not
        merely a non-empty entry, is also what keeps a Mathpix-imported
        document on its existing path: those paragraphs record a
        ``source_line`` and no blocks, so the traversal deliberately places
        none of them.
        """
        if current_page is None or current_page not in pages_with_blocks:
            return False
        return any(kind == "paragraph" for kind, _ in prose_by_page.get(current_page, []))

    def emit_prose() -> None:
        """This page's headings and paragraphs, once, in traversal order."""
        nonlocal prose_emitted
        if prose_emitted:
            return
        prose_emitted = True
        for kind, obj in prose_by_page.get(current_page, []):
            if kind == "heading":
                _add_heading(docx_document, obj.level.value, obj.text)
            else:
                _add_stream_paragraph(
                    docx_document, obj, blocks_by_id, notes_by_anchor_text, note_registries
                )

    # A Document with no pages, blocks or headings — a direct generate_docx()
    # call over hand-written markdown — yields an empty traversal. There is
    # then nothing to consume, and the markdown line path is the whole
    # renderer, exactly as it was before P4b.
    stream_knows_pages = bool(stream_pages)
    if stream_knows_pages:
        open_page()

    for index, line in enumerate(content_lines):
        # Table-summary and table-id accessibility comments — handled
        # separately; never rendered as body text.
        if _TABLE_SUMMARY_COMMENT_PATTERN.match(line):
            continue

        if _LIST_ID_COMMENT_PATTERN.match(line):
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
            # A page fence, no longer a page fact: the break itself and the
            # page's identity are emitted by open_page() from the traversal.
            if stream_knows_pages:
                page_cursor += 1
                open_page()
            elif index < len(content_lines) - 1:
                # No traversal to ask; the markdown's fence is the only page
                # signal there is. A break after the last line would only add
                # a blank trailing page in Word.
                docx_document.add_page_break()
            pending_caption_after_image = False
            pending_table_id = None
            continue

        heading_match = _HEADING_PATTERN.match(line)
        if heading_match:
            pending_caption_after_image = False
            if marker_line_pending:
                marker_line_pending = False
                if marker_from_node[0]:
                    continue  # already rendered from this page's PAGE_MARKER node
                if len(heading_match.group(1)) == 6:
                    # The synthesized marker. Only an H6 qualifies: under a
                    # suppressing page-numbering policy a page has no marker
                    # line at all, and its first heading is content the
                    # stream owns — which the fall-through below hands over.
                    _add_heading(docx_document, 6, heading_match.group(2).strip())
                    continue
            if is_stream_page():
                in_front_matter_zone = False
                emit_prose()
                continue
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            _add_heading(docx_document, level, text)
            in_front_matter_zone = False
            continue

        if in_front_matter_zone:
            kind, text = front_matter_groups[front_matter_index]
            front_matter_index += 1
            _add_front_matter_line(docx_document, kind, text)
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
            _add_note_definition(
                note_registries,
                label=footnote_def_match.group(1),
                body_text=footnote_def_match.group(2),
            )
            pending_caption_after_image = False
            continue

        # P4b: on a page the traversal covers, every remaining line is prose,
        # and prose is rendered from the stream — once, at the first such
        # line, so anything the markdown put before it (an image and its
        # caption) keeps its position and anything after it (tables, note
        # definitions) keeps its own.
        if is_stream_page():
            emit_prose()
            pending_caption_after_image = False
            continue

        # Semantic list rendering (FEATURE_016C): detect bullet or numbered
        # list items before falling through to plain body paragraph.
        bullet_match = _BULLET_LIST_PATTERN.match(line)
        if bullet_match:
            _add_list_paragraph(
                docx_document, bullet_match.group(2), "List Bullet", note_registries
            )
            pending_caption_after_image = False
            continue

        numbered_match = _NUMBERED_LIST_PATTERN.match(line)
        if numbered_match:
            _add_list_paragraph(
                docx_document, numbered_match.group(2), "List Number", note_registries
            )
            pending_caption_after_image = False
            continue

        _add_body_paragraph(docx_document, line, note_registries)
        pending_caption_after_image = False

    # Flush any pipe table still open at end of document.
    flush_pipe_table()

    # L4b: one part per note kind, and only for kinds this document
    # actually has. An endnote emitted into the footnotes part is not a
    # cosmetic difference — Word would render it at the foot of a page.
    if note_registries.footnotes.has_entries():
        _attach_notes_part(docx_document, note_registries.footnotes, _FOOTNOTE_PART)
    if note_registries.endnotes.has_entries():
        _attach_notes_part(docx_document, note_registries.endnotes, _ENDNOTE_PART)

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
    paragraph: Paragraph, text: str, registries: _NoteRegistries
) -> None:
    """Parse ``***...***`` / ``**...**`` / ``*...*`` inline markers in
    ``text`` and emit each segment as a formatted run (016G). Footnote
    references within a formatted segment inherit the segment's bold/italic.
    """
    for segment_text, is_bold, is_italic in _parse_inline_format(text):
        _add_text_with_note_references(
            paragraph, segment_text, registries, bold=is_bold, italic=is_italic
        )


def _add_body_paragraph(
    docx_document: DocxDocument, text: str, registries: _NoteRegistries
) -> None:
    paragraph = docx_document.add_paragraph()
    _add_body_text_with_inline_format(paragraph, text, registries)


def _add_list_paragraph(
    docx_document: DocxDocument,
    text: str,
    style: str,
    registries: _NoteRegistries,
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
    _add_text_with_note_references(paragraph, text, registries)


def _add_text_with_note_references(
    paragraph: Paragraph,
    text: str,
    registries: _NoteRegistries,
    bold: bool = False,
    italic: bool = False,
) -> None:
    """Add ``text`` to ``paragraph`` as one or more runs, splitting out
    any ``[^label]`` footnote/endnote references (Phase K) into their
    own native OOXML reference run. Text with no references at all
    renders as exactly one plain run - unchanged from this function's
    pre-Phase-K behavior.

    The label locates the note; ``registries`` answers what kind it is,
    from ``Footnote.note_type`` (L4b). This function does not decide.

    ``bold`` / ``italic`` are forwarded to every plain-text run so that
    callers that have already parsed inline format markers (016G) can
    propagate formatting within each already-classified segment. Note
    reference runs are not affected — they use Word's built-in
    reference character style for their kind.
    """
    position = 0
    has_reference = False
    for match in _FOOTNOTE_REFERENCE_PATTERN.finditer(text):
        has_reference = True
        if match.start() > position:
            _add_plain_run(paragraph, text[position : match.start()], bold=bold, italic=italic)
        _add_note_reference_run(paragraph, match.group(1), registries)
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


def _add_note_reference_run(
    paragraph: Paragraph, label: str, registries: _NoteRegistries
) -> None:
    """A native OOXML ``w:footnoteReference`` or ``w:endnoteReference``
    run, whichever this note's ``NoteType`` calls for (L4b).

    Word auto-numbers and renders the printed superscript digit from the
    referenced entry in the corresponding part; no explicit text content
    is needed here.  Word's built-in character style for the marker is
    requested via ``w:rStyle`` with an explicit ``w:vertAlign
    superscript`` as a fallback in case the style is not defined in the
    template.
    """
    part = registries.part_for(label)
    note_id = registries.registry_for(label).get_or_assign_id(label)

    run = OxmlElement("w:r")
    run_properties = OxmlElement("w:rPr")

    style = OxmlElement("w:rStyle")
    style.set(qn("w:val"), part.reference_style)
    run_properties.append(style)

    vert_align = OxmlElement("w:vertAlign")
    vert_align.set(qn("w:val"), "superscript")
    run_properties.append(vert_align)

    run.append(run_properties)

    note_ref = OxmlElement(f"w:{part.reference_tag}")
    note_ref.set(qn("w:id"), str(note_id))
    run.append(note_ref)

    paragraph._p.append(run)


def _add_note_definition(
    registries: _NoteRegistries, label: str, body_text: str
) -> None:
    """Register a note body for inclusion in its own part.

    Native OOXML notes live in a separate document part, not as
    paragraphs in the main body.  No paragraph is added here; the body
    text is stored in the registry its ``NoteType`` selects, and the
    parts are built and attached after the main rendering loop
    completes.
    """
    registries.registry_for(label).register_body(label, _safe_run_text(body_text))


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


def _build_notes_xml(entries: List[Tuple[int, str]], part: _NotePartSpec) -> bytes:
    """Build the raw XML bytes for ``word/footnotes.xml`` or
    ``word/endnotes.xml`` — one implementation, ``part`` names the
    vocabulary (L4b; see _NotePartSpec).

    ``entries`` is a list of ``(id, body_text)`` pairs in ascending id
    order.  IDs -1 and 0 are the Word-required separator entries, which
    both parts need; user notes start at 1.  Each part carries its own
    id space, so a footnote and an endnote may both be id 1 — the
    printed number a reader sees comes from Word's auto-number element
    (``w:footnoteRef``/``w:endnoteRef``), never from text written here.
    """
    W = _W_NS
    WP = "{%s}" % W

    def w(tag: str) -> str:
        return WP + tag

    root = etree.Element(w(part.root_tag), nsmap={"w": W})

    for fn_type, fn_id, child_tag in (
        ("separator", -1, "separator"),
        ("continuationSeparator", 0, "continuationSeparator"),
    ):
        fn_el = etree.SubElement(root, w(part.item_tag))
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
        fn_el = etree.SubElement(root, w(part.item_tag))
        fn_el.set(w("id"), str(fn_id))

        p = etree.SubElement(fn_el, w("p"))

        # Auto-number marker rendered by Word
        ref_r = etree.SubElement(p, w("r"))
        ref_rPr = etree.SubElement(ref_r, w("rPr"))
        rStyle = etree.SubElement(ref_rPr, w("rStyle"))
        rStyle.set(w("val"), part.reference_style)
        vert = etree.SubElement(ref_rPr, w("vertAlign"))
        vert.set(w("val"), "superscript")
        etree.SubElement(ref_r, w(part.auto_number_tag))

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


def _attach_notes_part(
    docx_document: DocxDocument, registry: _FootnoteRegistry, part: _NotePartSpec
) -> None:
    """Build a note part from its registry and attach it to the document
    package with the correct OPC relationship and content type.  Word
    requires all three (the XML file, the relationship from
    ``document.xml``, and the content-type override) to recognise the
    part — and needs them once per kind, which is why an endnote emitted
    into the footnotes part is not a cosmetic difference: Word would
    place it at the foot of a page and call it a footnote.
    """
    xml_bytes = _build_notes_xml(registry.ordered_entries(), part)
    notes_part = Part(
        partname=PackURI(part.partname),
        content_type=part.content_type,
        blob=xml_bytes,
        package=docx_document.part.package,
    )
    docx_document.part.relate_to(notes_part, part.relationship_type)


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


def _front_matter_groups(document: Document) -> List[Tuple[str, str]]:
    """(role, text) per front-matter block, from the ContentStream (L5'a).

    One entry per block src/markdown/markdown_builder.py emits, in the
    same order, because this module still consumes that module's lines
    positionally - see the module docstring's note on remaining debt.
    What L5'a changes is where the *semantics* come from: the role is read
    off ``FrontMatterItem.role`` and the text off ``FrontMatterItem.text``,
    both placed by the traversal. This module no longer mirrors another
    module's if-authors/if-affiliations gating, and no longer asks
    ``document.front_matter`` what a line is.

    Empty when the traversal placed nothing - a Document whose provider
    recorded no source blocks, or one built before items existed - which
    routes this module to the legacy path exactly as before.
    """
    front_matter = getattr(document, "front_matter", None)
    items = {str(item.id): item for item in (getattr(front_matter, "items", []) or [])}
    if not items:
        return []

    grouped: Dict[str, List[str]] = {}
    order: List[str] = []
    for node in build_content_stream(document).nodes:
        if node.kind is not ContentKind.FRONT_MATTER:
            continue
        item = items.get(node.object_id)
        if item is None:
            continue
        role = item.role.value
        if role not in grouped:
            grouped[role] = []
            order.append(role)
        grouped[role].append(item.text)

    joiner = {"title": " ", "author": ", ", "affiliation": "; "}
    return [(role, joiner[role].join(grouped[role])) for role in order]


def _front_matter_kinds(document: Document) -> List[str]:
    return [role for role, _ in _front_matter_groups(document)]


def _add_front_matter_line(
    docx_document: DocxDocument, kind: str, text: str
) -> None:
    if kind == "title":
        _add_title(docx_document, text)
    elif kind == "author":
        _add_byline(docx_document, text)
    else:
        _add_affiliation(docx_document, text)


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
