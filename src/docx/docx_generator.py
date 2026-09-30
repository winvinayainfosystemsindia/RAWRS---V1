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

Tables joined the stream at P4c-1, notes at P4c-2, images and their
captions at P4c-3. What still comes from the markdown, and is out of
scope here: lists, the ``## Endnotes`` heading, and the prose of any page
with no ``TextBlock`` (41 of the benchmark corpus' 161 - see
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple, Union

from docx import Document as DocxDocument

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.shared import Emu, Inches, Pt, RGBColor
from docx.text.paragraph import Paragraph
from loguru import logger
from lxml import etree
from PIL import Image as PILImage

from src.docx.remediation_text import (
    URL_PATTERN,
    is_bullet_glyph,
    is_label,
    remediate_heading,
    remediate_prose,
)
from src.docx.equation_render import EquationRender
from src.markdown.markdown_builder import PAGE_BREAK_MARKER
from src.models.content_stream import ContentKind
from src.structure.content_stream import build_content_stream
from src.models.contracts import Document, ExtractionMethod, Footnote, FrontMatter, NoteType
from src.models.inline_format import format_runs
from src.models.note_references import resolve_note_references
from src.structure.paragraph_assembly import absorbed_block_ids
from src.utils.mathpix_crop import crop_box
from src.utils.text_sanitization import sanitize_xml_text

DEFAULT_OUTPUT_DIR = Path("outputs/docx")

_FONT_NAME = "Times New Roman"
_BODY_FONT_SIZE_PT = 12
_FOOTNOTE_FONT_SIZE_PT = 10
_BLACK = RGBColor(0, 0, 0)
_MAX_IMAGE_WIDTH = Inches(6.5)  # content width on a Letter page with 1" margins
_DEFAULT_LANGUAGE = "en-US"
_HYPERLINK_COLOR = "0563C1"
# Deepest level a content heading may take; Heading 6 is the page number.
_MAX_CONTENT_HEADING_LEVEL = 5

# Per docs/HEADING_RULES.md Formatting Rules: H1=16pt, H2=14pt, H3-H6=12pt,
# all bold, black, Times New Roman.
_HEADING_FONT_SIZES_PT = {1: 16, 2: 14, 3: 12, 4: 12, 5: 12, 6: 12}


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
    projection asks the question, so nothing here reads placement, section
    headings or rendered text to decide what a note *is*.

    P4c-2: a note is keyed by ``Footnote.footnote_id`` — its identity. It
    used to be keyed by ``Footnote.label``, which src/models/footnote.py says
    in as many words is not identity: the label is derived from the printed
    number and the body page, so a reviewer's renumbering rewrites it while
    the note stays the same note. ``key_for_label`` exists for the one caller
    that still starts from a rendered ``[^label]`` — hand-written markdown and
    the blockless/list text paths — and maps it back onto identity when the
    model holds a matching note. A key with no matching Footnote (a fixture, a
    direct generate_docx() call) is a footnote, which is exactly what every
    note was before L4b: unknown provenance changes nothing.
    """

    def __init__(self, notes: List[Footnote]) -> None:
        self.footnotes = _FootnoteRegistry()
        self.endnotes = _FootnoteRegistry()
        # Threaded to every body-text emitter because the registries already
        # are; set by generate_docx() only when the document has equations.
        self.equations: Optional[EquationRender] = None
        self._endnote_keys = {
            self.key_for(note) for note in notes if note.note_type == NoteType.ENDNOTE
        }
        self._keys_by_label: Dict[str, str] = {}
        for note in notes:
            self._keys_by_label.setdefault(note.label, self.key_for(note))

    @staticmethod
    def key_for(note: Footnote) -> str:
        """A note's identity, or its label when it has none — a Footnote built
        without ``footnote_id`` (an older fixture, a provider that assigns no
        id) still has to reach a part."""
        return note.footnote_id or note.label

    def key_for_label(self, label: str) -> str:
        """The identity behind a rendered ``[^label]``, when the model holds
        one. An unknown label keys itself, so hand-written markdown still
        renders its notes."""
        return self._keys_by_label.get(label, label)

    def part_for(self, key: str) -> _NotePartSpec:
        return _ENDNOTE_PART if key in self._endnote_keys else _FOOTNOTE_PART

    def registry_for(self, key: str) -> _FootnoteRegistry:
        return self.endnotes if key in self._endnote_keys else self.footnotes


class _HeadingLevels:
    """The Word level each content heading renders at, so the outline has no gaps.

    The checklist wants "heading levels in hierarchical order": Level 1 is the
    document's name, and no heading may skip a level below the one before it.
    Detected levels are font-size ranks, so a chapter whose largest type is
    its section headings arrives starting at H3, and a sidebar can jump
    H2 -> H4. Two steps fix both without inventing structure:

    * **rank**: the document's distinct content levels, in order, become
      consecutive Word levels - starting at 2 when the front-matter title is
      rendered as Heading 1, else at 1;
    * **clamp**: a heading is never more than one level deeper than the
      heading before it.

    Heading 6 is the page number and never passes through here.
    """

    def __init__(self, raw_levels: List[int], title_is_h1: bool) -> None:
        self._top = 2 if title_is_h1 else 1
        distinct = sorted({level for level in raw_levels if 1 <= level <= 6})
        self._rank = {
            level: min(self._top + index, _MAX_CONTENT_HEADING_LEVEL)
            for index, level in enumerate(distinct)
        }
        self._previous = self._top - 1

    def title(self) -> int:
        self._previous = 1
        return 1

    def content(self, raw_level: int) -> int:
        level = self._rank.get(raw_level, min(raw_level, _MAX_CONTENT_HEADING_LEVEL))
        level = max(self._top, min(level, self._previous + 1))
        self._previous = level
        return level


_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")
_IMAGE_PATTERN = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)$")
_CAPTION_PATTERN = re.compile(r"^\*(.+)\*$")

# An inline footnote/endnote reference, e.g. "[^p3-1]" - label content
# is opaque here (src/markdown/markdown_builder.py owns its format); this
# module only needs to split text around it, and only on the two paths that
# have no Paragraph to ask instead (list items, blockless prose). The printed
# number is Word's own auto-number element, never parsed out of the label.
_FOOTNOTE_REFERENCE_PATTERN = re.compile(r"\[\^([^\]]+)\]")
_FOOTNOTE_DEFINITION_PATTERN = re.compile(r"^\[\^([^\]]+)\]:\s*(.+)$")
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
_EQUATION_ID_COMMENT_PATTERN = re.compile(r"^<!-- equation-id: (.+) -->$")

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


def _stream_images(
    document: Document, stream, prose_pages: set
) -> Tuple[Dict[int, List[object]], Dict[int, List[object]]]:
    """Each page's images, in traversal order, in one of two emission slots.

    P4c-3. An ``IMAGE`` node names its ``Image`` by ``image_id``, which is
    what the markdown's ``![alt](path)`` line never carried: that line said
    only *that* an image was there and where its file was, and the path then
    stood in as identity for three separate lookups (alignment, decorative
    state, ``embedded_in_docx``). Two images sharing a path would have shared
    all three.

    Two slots, because two is all the corpus needs: of 122 images, 120 sit
    before every prose node on their page and 2 after all of them — **none**
    between two prose nodes. So an image is emitted either at the head of its
    page's prose run or at page close, which is the slot the markdown line
    already occupied.

    A page whose prose the traversal does not carry (``prose_pages`` excludes
    all 24 blockless pages, which hold 118 of the 122 images) has no prose to
    be ordered against, so every image on it closes the page. Keying emission
    on that condition instead — on ``is_stream_page()`` — would drop those 118
    entirely, which is why placement consults it and emission never does.

    An image whose extraction failed has a node but no file, and
    ``_render_images`` has always skipped it; a node walk that did not would
    try to embed nothing and record ``embedded_in_docx=False`` against it.
    """
    images_by_id = {
        str(image.image_id): image
        for image in (getattr(document, "images", []) or [])
        if not image.extraction_failed
    }
    before_prose: Dict[int, List[object]] = {}
    at_close: Dict[int, List[object]] = {}
    prose_seen: set = set()
    for node in stream.nodes:
        if node.kind in (ContentKind.PARAGRAPH, ContentKind.HEADING):
            prose_seen.add(node.page_number)
            continue
        if node.kind is not ContentKind.IMAGE:
            continue
        image = images_by_id.get(node.object_id)
        if image is None:
            continue
        page = node.page_number
        slot = (
            before_prose
            if page in prose_pages and page not in prose_seen
            else at_close
        )
        slot.setdefault(page, []).append(image)
    return before_prose, at_close


def _add_stream_image(
    docx_document: DocxDocument,
    image,
    decorative_ids: set,
    page_widths: Optional[Dict[int, float]] = None,
) -> None:
    """One ``Image``, then its caption, both read off the object the node named.

    The caption needs no node of its own: ``Figure`` is a field of ``Image``
    (architecture decision #4), so the association is in the model and cannot
    dangle — exactly the shape ``_add_semantic_table`` already uses for
    ``Table.caption``. Recovering it from the markdown meant recognising a
    caption by its *line shape*, and ``^\\*(.+)\\*$`` also matches a bold
    ``**Title**`` line: the corpus has 20 such lines against 2 real captions,
    and only the "directly after an image" adjacency kept the other 18 from
    being eaten.
    """
    figure = getattr(image, "figure", None)
    image.embedded_in_docx = _add_image(
        docx_document,
        image.file_path,
        alt_text=(getattr(figure, "alt_text", None) or "") if figure else "",
        decorative=image.image_id in decorative_ids,
        printed_size=_printed_size(image, page_widths or {}),
    )
    if figure is not None and figure.caption:
        _add_caption(docx_document, figure.caption)


class _Segment(NamedTuple):
    """A slice ``[start, end)`` of one ``Paragraph``'s text. A rendered Word
    paragraph is one or more of these, so a sentence the PDF split across a
    page or a column can be written as the one sentence it is."""

    paragraph: object
    start: int
    end: int

    @property
    def text(self) -> str:
        return self.paragraph.text[self.start : self.end]


# A paragraph ending in one of these has said what it had to say.
_TERMINAL_PATTERN = re.compile(r"[.?!:;…][\"'”’)\]]*$")
# The end of the first sentence in a paragraph: terminal punctuation followed
# by the start of another sentence, not an abbreviation's inner stop.
_SENTENCE_END_PATTERN = re.compile(
    r"[.?!…][\"'”’)\]]*(?=\s+[A-Z0-9\"“(‘]|\s*$)"
)
_JOINING_WORDS = frozenset(
    "a an the of to in on at by for from with and or but nor as that which who whom whose "
    "is are was were be been being has have had this these those its their our his her "
    "into onto upon than then so such not also more most very".split()
)
# Shorter than this and a "paragraph" is a label (a heading the detector did
# not claim, a caption), which ends without punctuation by nature.
_MIN_CONTINUED_WORDS = 4


def _continues(tail: str, head: str) -> bool:
    """Whether ``head`` finishes the sentence ``tail`` left open."""
    tail, head = tail.rstrip(), head.lstrip()
    if not tail or not head or _TERMINAL_PATTERN.search(tail):
        return False
    if len(tail.split()) < _MIN_CONTINUED_WORDS:
        return False
    last_word = re.sub(r"\W", "", tail.split()[-1]).lower()
    return head[0].islower() or tail[-1] in ",-–—" or last_word in _JOINING_WORDS


def _stitch_prose(
    prose_by_page: Dict[int, List[Tuple[str, object]]],
    pages_in_order: List[int],
    pages_ending_in_other_content: set,
) -> Dict[int, List[Tuple[str, object]]]:
    """The checklist's two sentence rules, applied to the traversal's prose.

    * "Eliminate ... sentence breaks": two consecutive paragraphs on a page
      where the first stops mid-sentence and the second finishes it (a column
      break, a figure the text flowed around) render as one Word paragraph.
    * "The sentences should not be incomplete at the end of the page.
      Complete the sentence by taking it from next page": when a page's last
      paragraph stops mid-sentence, the next page's first paragraph gives up
      its first sentence to it, and keeps the rest.

    Nothing is re-ordered or rewritten - each piece is a ``_Segment`` of the
    model's own text, and the model is untouched. A page that closes with a
    table or figure does not hand its last sentence on, because that text is
    not what ends the page.
    """
    stitched: Dict[int, List[Tuple[str, object]]] = {}
    open_unit: Optional[List[_Segment]] = None
    for page in pages_in_order:
        units: List[Tuple[str, object]] = []
        bullet_pending = False
        for kind, obj in prose_by_page.get(page, []):
            if kind == "heading":
                units.append((kind, obj))
                bullet_pending = False
                continue
            if is_bullet_glyph(obj.text):
                # The glyph is the list marker; Word's list style draws its own.
                bullet_pending = True
                continue
            segment = _Segment(obj, 0, len(obj.text))
            if bullet_pending:
                units.append(("list_item", [segment]))
                bullet_pending = False
                continue
            previous = units[-1][1] if units and units[-1][0] in _PROSE_UNITS else None
            if previous is not None and _continues(_segments_text(previous), obj.text):
                previous.append(segment)
                continue
            if not units and open_unit is not None and _continues(_segments_text(open_unit), obj.text):
                match = _SENTENCE_END_PATTERN.search(obj.text)
                remainder = obj.text[match.end():] if match else ""
                if match is None or not remainder.strip():
                    open_unit.append(segment)
                    continue
                open_unit.append(_Segment(obj, 0, match.end()))
                rest = match.end() + len(remainder) - len(remainder.lstrip())
                segment = _Segment(obj, rest, len(obj.text))
            units.append(("paragraph", [segment]))
        stitched[page] = units
        open_unit = None if page in pages_ending_in_other_content else _open_sentence(units)
    return stitched


_PROSE_UNITS = ("paragraph", "list_item")


def _open_sentence(units: List[Tuple[str, object]]) -> Optional[List[_Segment]]:
    """The unit whose sentence a page leaves open: its last prose unit, looking
    past any trailing labels (a figure's "Source: Maslow (1954)" line ends a
    page without being the text that runs on), but never past a heading."""
    for kind, value in reversed(units):
        if kind not in _PROSE_UNITS:
            return None
        if not is_label(_segments_text(value)):
            return value
    return None


_NOT_PROSE_LINE = re.compile(r"^(#|!\[|\||<!--|\[\^|[-*•]\s|\d+[.)]\s)")
# A page may end inside a list item, whose sentence runs on just like prose;
# only headings, figures, tables, comments and note definitions end a thought.
_CANNOT_RUN_ON = re.compile(r"^(#|!\[|\||<!--|\[\^|\$\$)")
# A figure or table label as OCR reads it - plain text at the top of the page
# ("FIGURE 3.4 CYCLES OF RESEARCH QUESTION DEVELOPMENT"), not the sentence
# that runs on from the page before.
_FIGURE_LABEL_LINE = re.compile(r"^(figure|fig\.|table|chart|box|plate)\s*\d", re.IGNORECASE)
# A whole-line italic caption ("*FIGURE 3.1 CONCEPT MAP ...*").
_CAPTION_LINE = re.compile(r"^\*[^*].*\*$")


def _complete_sentences_across_page_breaks(lines: List[str]) -> List[str]:
    """The checklist's page-end rule for pages rendered from Markdown lines -
    Mathpix imports and OCR'd scans - where ``_stitch_prose`` cannot reach,
    because those pages have no traversal.

    When the last line of prose before a page break stops mid-sentence and the
    first line of prose on the next page (after its page number) finishes it,
    that first sentence moves up to the previous page and the rest stays. A
    page that ends in a figure, table, list or heading hands nothing on, and
    neither does one whose next page starts with a heading.
    """
    lines = list(lines)
    for index, line in enumerate(lines):
        if line != PAGE_BREAK_MARKER:
            continue
        # The open sentence is the last text before the break - looking past a
        # figure and its caption, which often close a page while the paragraph
        # above them runs on to the next.
        before = index - 1
        while before >= 0 and (lines[before].startswith("![") or _CAPTION_LINE.match(lines[before])):
            before -= 1
        if before < 0 or _CANNOT_RUN_ON.match(lines[before]) or is_label(lines[before]):
            continue
        # A plain-text equation is an ordinary-looking line; the anchor just
        # above it is the only thing that says it is not a sentence to finish.
        if before >= 1 and lines[before - 1].startswith("<!-- equation-id:"):
            continue
        after = index + 1
        while after < len(lines) and (
            lines[after].startswith("######")
            or lines[after].startswith("![")
            or _CAPTION_LINE.match(lines[after])
            or _FIGURE_LABEL_LINE.match(lines[after])
        ):
            after += 1
        if after >= len(lines) or _NOT_PROSE_LINE.match(lines[after]) or lines[after] == PAGE_BREAK_MARKER:
            continue
        if not _continues(lines[before], lines[after]):
            continue
        head = lines[after]
        match = _SENTENCE_END_PATTERN.search(head)
        moved, rest = (head, "") if match is None else (head[: match.end()], head[match.end():].strip())
        joiner = "" if lines[before].endswith("-") else " "
        lines[before] = f"{lines[before]}{joiner}{moved.strip()}"
        lines[after] = rest
    return [line for line in lines if line]


def _segments_text(segments: List[_Segment]) -> str:
    return " ".join(segment.text.strip() for segment in segments)


def _add_stream_paragraph(
    docx_document: DocxDocument,
    segments: List[_Segment],
    blocks_by_id: Dict[str, object],
    notes_by_anchor_text: Dict[str, List[Footnote]],
    registries: _NoteRegistries,
    style: Optional[str] = None,
) -> None:
    """One Word paragraph from one or more ``Paragraph`` slices, as OOXML runs,
    with no markdown in between.

    Emphasis comes from ``format_runs`` and note positions from
    ``resolve_note_references`` — the two rules P4a moved to the model
    (``src/models/inline_format.py``, ``src/models/note_references.py``), so
    this module never inspects ``TextBlock.spans[].font_flags`` and never
    looks for ``[^label]`` in rendered text. References are resolved against
    the whole paragraph's text, then each slice writes the ones inside it, so
    a note keeps its place when its sentence moves to the previous page.

    ``source_block_ids`` names the lines the paragraph was assembled from,
    which is what both rules need: the blocks answer "is this emphasised",
    and only the notes anchored to *those* lines are offered for
    substitution, so a neighbouring paragraph's marker cannot be claimed here.

    **A paragraph is not a list item (P4c-4′).** This function used to
    re-match ``Paragraph.text`` against the bullet/numbered patterns and style
    the result ``List Bullet``/``List Number``. It *invented* a list where no
    ``ListBlock`` existed, and then deleted the evidence (a reference entry
    lost its printed ``12.``). A real ``ListBlock`` remains the only source of
    list semantics; it renders through ``_render_lists`` and the anchored
    branch of the line loop.
    """
    try:
        docx_paragraph = docx_document.add_paragraph(style=style)
    except KeyError:  # a template without the list style: plain, never lost
        docx_paragraph = docx_document.add_paragraph()
    written = ""
    for segment in segments:
        paragraph_object = segment.paragraph
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
        start = segment.start + (len(segment.text) - len(segment.text.lstrip()))
        end = segment.start + len(segment.text.rstrip())
        if start >= end:
            continue
        if written and not written.endswith("-"):
            _add_formatted_run(docx_paragraph, " ", bold=False, italic=False)
        references = [
            r for r in resolve_note_references(text, notes) if start <= r.start < end
        ]
        position = start
        for run in format_runs(text[start:end], contributing):
            run_end = position + len(run.text)
            _add_window_with_note_references(
                docx_paragraph, text, position, run_end, references, registries,
                bold=run.bold, italic=run.italic,
            )
            position = run_end
        written = text[start:end]


def _add_window_with_note_references(
    docx_paragraph: Paragraph,
    text: str,
    start: int,
    end: int,
    references: list,
    registries: _NoteRegistries,
    bold: bool = False,
    italic: bool = False,
) -> None:
    """``text[start:end]`` as runs, with each note's printed marker replaced
    by a native reference run.

    The model says where each marker is (``NoteReference.start``/``.length``,
    positions in the whole ``text``) and which note it is; ``registries``
    says which part it belongs in, from ``Footnote.note_type`` (L4b). Applied
    in ascending position because the slices are taken from the original
    string rather than rewritten into it.
    """
    position = start
    for reference in references:
        if reference.start < position or reference.start >= end:
            continue  # outside this window, or an overlapping claim already owned
        _add_plain_run(docx_paragraph, text[position : reference.start], bold=bold, italic=italic)
        _add_note_reference_run(
            docx_paragraph, registries.key_for(reference.note), registries
        )
        position = min(reference.start + reference.length, end)
    _add_plain_run(docx_paragraph, text[position:end], bold=bold, italic=italic)


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
    _apply_default_style(docx_document, _document_language(document))
    _apply_core_properties(docx_document, document)

    # Alignment and decorative status, both keyed by Image.image_id (P4c-3).
    # They were always read off the model; only the key was the file path.
    decorative_ids = _build_decorative_set(document)
    # The remaining use of the path as a name: a markdown image line on a
    # document the traversal never placed images for, which is the only path
    # that still has nothing but the line to identify the Image by.
    images_by_path = {img.file_path: img for img in document.images}
    page_widths = {p.page_number: p.width_pt for p in document.pages if getattr(p, "width_pt", None)}

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

    content_lines = _complete_sentences_across_page_breaks(
        [line.strip() for line in markdown_content.splitlines() if line.strip()]
    )
    pending_caption_after_image = False
    in_front_matter_zone = False
    front_matter_groups = _front_matter_groups(document)
    front_matter_kinds = [role for role, _ in front_matter_groups]
    front_matter_index = 0
    # Ranked from the model's headings; hand-written markdown has none, and
    # its own heading lines are then the only record of the levels in use.
    heading_levels = _HeadingLevels(
        [h.level.value for h in document.headings if not h.is_page_marker]
        or [
            len(match.group(1))
            for match in map(_HEADING_PATTERN.match, content_lines)
            if match and len(match.group(1)) < 6
        ],
        title_is_h1="title" in front_matter_kinds,
    )
    note_registries = _NoteRegistries(document.footnotes)
    if document.equations:
        note_registries.equations = EquationRender(
            document, lambda paragraph, text: _add_formatted_run(paragraph, text, False, False)
        )
    equation_skip_index = -1
    pipe_table_rows: list = []
    pipe_table_header_count = 0
    pending_table_id: Optional[str] = None
    stream_table_caption_pending = False
    # Build id→Table lookup for semantic rendering (FEATURE_015.1).
    tables_by_id = {t.table_id: t for t in document.tables}
    # P4c-1: which tables each page renders, resolved from its TABLE nodes by
    # ``Table.table_id``. The markdown's ``<!-- table-id: ... -->`` comment
    # carried exactly this and nothing else; the traversal carries it now.
    stream_tables_by_page: Dict[int, List[object]] = {}
    for node in stream.nodes:
        if node.kind is not ContentKind.TABLE:
            continue
        table = tables_by_id.get(node.object_id)
        if table is not None:
            stream_tables_by_page.setdefault(node.page_number, []).append(table)
    # P4c-2: which notes each page defines, resolved from its NOTE_DEFINITION
    # nodes by ``Footnote.footnote_id``. The traversal already knows both
    # placements — a footnote at the page its marker sits on, an endnote at the
    # document's last page — which is exactly what the markdown's per-page
    # ``[^label]: body`` lines and its "## Endnotes" section spelled out.
    notes_by_id = {n.footnote_id: n for n in document.footnotes if n.footnote_id}
    stream_notes_by_page: Dict[int, List[Footnote]] = {}
    for node in stream.nodes:
        if node.kind is not ContentKind.NOTE_DEFINITION:
            continue
        note = notes_by_id.get(node.object_id)
        if note is not None:
            stream_notes_by_page.setdefault(node.page_number, []).append(note)
    # Once the traversal places this document's notes, a definition line
    # carries nothing this module still asks — and it cannot be matched against
    # the notes by label either, because the markdown may have been built
    # before a reviewer renumbered. So the lines are dropped wholesale, except
    # for a note the traversal could *not* place (a Footnote with no id, a
    # provider that emits no node), whose line is still its only record.
    stream_placed_keys = {
        _NoteRegistries.key_for(note)
        for notes in stream_notes_by_page.values()
        for note in notes
    }
    notes_come_from_stream = bool(stream_placed_keys)
    unplaced_note_labels = {
        note.label
        for note in document.footnotes
        if _NoteRegistries.key_for(note) not in stream_placed_keys
    }
    # P4c-3: which images each page renders and in which of the two slots,
    # resolved from its IMAGE nodes by ``Image.image_id``.
    stream_prose_pages = {
        page
        for page, entries in prose_by_page.items()
        if page in pages_with_blocks and any(kind == "paragraph" for kind, _ in entries)
    }
    images_before_prose, images_at_close = _stream_images(
        document, stream, stream_prose_pages
    )
    prose_units = _stitch_prose(
        prose_by_page,
        stream_pages,
        pages_ending_in_other_content=set(stream_tables_by_page) | set(images_at_close),
    )
    # An image the traversal placed is rendered from its node, so its markdown
    # line is a restatement and is dropped — along with the ``*caption*`` line
    # after it, which _add_stream_image() has already emitted from
    # Figure.caption. A line naming a path no placed image has is not this
    # document's to drop: hand-written markdown keeps rendering it.
    stream_image_paths = {
        image.file_path
        for slots in (images_before_prose, images_at_close)
        for page_images in slots.values()
        for image in page_images
    }
    # The index of the one line that may be a dropped image's caption. An
    # index rather than a flag: it clears itself on the next line, so no
    # branch in the loop below has to remember to reset it.
    stream_caption_index = -1
    # P4c-4′: the lines a ``ListBlock`` actually wrote. ``_render_lists``
    # emits one ``<!-- list-id: … -->`` anchor followed by exactly one line
    # per item, so a resolvable anchor names a window, and a line outside
    # every window is prose no matter what it starts with. An index rather
    # than a flag for the same reason as above: it needs no reset.
    lists_by_id = {str(lst.id): lst for lst in (document.lists or []) if lst.id}
    ocr_pages = {
        page.page_number
        for page in document.pages
        if page.extraction_method in (ExtractionMethod.DOCLING, ExtractionMethod.SURYA)
    }
    list_line_limit = -1

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

    def tables_from_stream() -> bool:
        """Whether this page's tables come from its TABLE nodes.

        False for a page whose tables the traversal never placed — a Document
        with no ``Page`` rows for that page, or hand-written markdown handed
        straight to this function. Those keep the pipe-table fallback, which
        is the only reason it still exists.
        """
        return current_page is not None and current_page in stream_tables_by_page

    def emit_images(slot: Dict[int, List[object]]) -> None:
        """This page's images from one slot, once — popped, so the page-close
        sweep cannot re-emit what the prose run already placed."""
        for image in slot.pop(current_page, []):
            _add_stream_image(docx_document, image, decorative_ids, page_widths)

    def close_page() -> None:
        """Emit this page's images and tables and register its notes, where
        the traversal put them.

        Images first, then tables: that is the order
        ``markdown_builder._render_page`` renders them in for a page whose
        images the body placed, and the 24 blockless pages that hold 118 of
        the corpus' 122 images have no tables to be ordered against. A leading
        image still unemitted here belongs to a page whose prose run never
        fired — markdown carrying fewer lines than the traversal has pages —
        and comes out ahead of the rest rather than being lost.

        A ``TABLE`` node is emitted after the page's body entries, so a page's
        tables belong at its end — which is also exactly where
        ``markdown_builder._render_page`` appends them. Nothing here consults a
        line: the node names the table, and ``_add_semantic_table`` renders it
        from the model, as it already did.

        A ``NOTE_DEFINITION`` node sits at the same place for a footnote, and
        at the last page for an endnote. Registering here rather than at the
        markdown's definition line keeps the id order the registry has always
        had: a note's inline reference is emitted with this page's prose, so it
        still claims its id before its body arrives (P4c-2).
        """
        emit_images(images_before_prose)
        emit_images(images_at_close)
        for table in stream_tables_by_page.get(current_page, []):
            _add_semantic_table(docx_document, table)
        for note in stream_notes_by_page.get(current_page, []):
            _add_note_definition(
                note_registries, key=_NoteRegistries.key_for(note), body_text=note.body
            )

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
        return current_page in stream_prose_pages

    def emit_prose() -> None:
        """This page's headings and paragraphs, once, in traversal order,
        behind whichever of its images the traversal put ahead of them."""
        nonlocal prose_emitted
        if prose_emitted:
            return
        prose_emitted = True
        emit_images(images_before_prose)
        for kind, obj in prose_units.get(current_page, []):
            if kind == "heading":
                _add_heading(docx_document, heading_levels.content(obj.level.value), obj.text)
            else:
                _add_stream_paragraph(
                    docx_document, obj, blocks_by_id, notes_by_anchor_text, note_registries,
                    style="List Bullet" if kind == "list_item" else None,
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

        # An equation is rendered from the Equation its id names (docs/
        # EQUATION_DESIGN.md); the line after the anchor restates it and is
        # dropped. An id the model does not know drops only the comment, so the
        # restating line still shows as text rather than the equation vanishing.
        if index == equation_skip_index:
            continue
        equation_id_match = _EQUATION_ID_COMMENT_PATTERN.match(line)
        if equation_id_match:
            renderer = note_registries.equations
            if renderer is not None and renderer.display(docx_document, equation_id_match.group(1)):
                equation_skip_index = index + 1
            pending_caption_after_image = False
            continue

        list_id_match = _LIST_ID_COMMENT_PATTERN.match(line)
        if list_id_match:
            # P4c-4′: the anchor stopped being a no-op. It is the only thing
            # that says the next few lines are a list rather than prose that
            # happens to start with a marker character.
            listed = lists_by_id.get(list_id_match.group(1))
            if listed is not None:
                list_line_limit = index + 1 + len(listed.items)
            continue

        # The caption of an image the traversal placed. Checked here, ahead of
        # every other branch, because a caption line is only recognisable by
        # its position: on its own it is an italic line like any other.
        if index == stream_caption_index and _CAPTION_PATTERN.match(line):
            continue

        # Pipe table rows. P4c-1: on a page whose tables the traversal placed,
        # these carry nothing this module still asks — the grid, the header
        # rows, the merges and the caption all come off the Table model — so
        # they are dropped rather than reassembled into one.
        if _PIPE_TABLE_ROW_PATTERN.match(line):
            if tables_from_stream():
                continue
            if _PIPE_TABLE_SEPARATOR_PATTERN.match(line):
                # Separator row marks all rows seen so far as header rows.
                pipe_table_header_count = len(pipe_table_rows)
            else:
                pipe_table_rows.append(line)
            continue

        # Any non-table-row line: flush a pending pipe table first.
        flush_pipe_table()

        # Table-id anchor. It existed so this module could recover *which*
        # Table a run of pipe rows was; the TABLE node answers that now, and
        # on a stream page the comment is consumed and nothing more. Off the
        # stream it still names the model for flush_pipe_table().
        table_id_match = _TABLE_ID_COMMENT_PATTERN.match(line)
        if table_id_match:
            if tables_from_stream():
                stream_table_caption_pending = True
            else:
                pending_table_id = table_id_match.group(1)
            pending_caption_after_image = False
            continue

        # *Caption* line that belongs to a semantic table: skip here —
        # _add_semantic_table() renders it from Table.caption. Only the line
        # directly after a table-id comment qualifies, so an italic paragraph
        # elsewhere is untouched.
        if stream_table_caption_pending or (pending_table_id is not None and not pipe_table_rows):
            stream_table_caption_pending = False
            if _CAPTION_PATTERN.match(line):
                continue

        if line == PAGE_BREAK_MARKER:
            # A page fence, no longer a page fact: the break itself and the
            # page's identity are emitted by open_page() from the traversal.
            if stream_knows_pages:
                close_page()
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
            # An H6 line is a page number (docs/PAGE_RULES.md), never content.
            _add_heading(docx_document, 6 if level == 6 else heading_levels.content(level), text)
            in_front_matter_zone = False
            continue

        if in_front_matter_zone:
            kind, text = front_matter_groups[front_matter_index]
            front_matter_index += 1
            if kind == "title":
                heading_levels.title()
            _add_front_matter_line(docx_document, kind, text)
            in_front_matter_zone = front_matter_index < len(front_matter_kinds)
            continue

        image_match = _IMAGE_PATTERN.match(line)
        if image_match:
            img_path = image_match.group(2)
            if img_path in stream_image_paths:
                # P4c-3: the IMAGE node names this image, and it is emitted
                # from the Image the node named - with its caption - so the
                # line restates three of that object's fields and nothing else.
                # On a page whose prose the traversal does not carry (a scan,
                # a Mathpix import) the line is the only record of *where* the
                # figure sits, so it is emitted here rather than at page close:
                # at page close O'Leary's four top-of-page figures landed below
                # the text they head.
                if not is_stream_page():
                    waiting = images_at_close.get(current_page, [])
                    placed = next((img for img in waiting if img.file_path == img_path), None)
                    if placed is not None:
                        waiting.remove(placed)
                        _add_stream_image(docx_document, placed, decorative_ids, page_widths)
                stream_caption_index = index + 1
                pending_caption_after_image = False
                continue
            # No node placed this image, so the line is all there is to go on:
            # its alt text is group(1) and its path names the Image, if the
            # model holds one at all.
            image_obj = images_by_path.get(img_path)
            image_id = getattr(image_obj, "image_id", None)
            embedded = _add_image(
                docx_document,
                img_path,
                alt_text=image_match.group(1),
                decorative=image_id in decorative_ids,
                printed_size=_printed_size(image_obj, page_widths) if image_obj is not None else None,
            )
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
            # P4c-2: the body and the part come off the Footnote the traversal
            # named; this line is then a restatement of it and is dropped. Only
            # a label the stream never placed is still read from here.
            if not notes_come_from_stream or (
                footnote_def_match.group(1) in unplaced_note_labels
            ):
                _add_note_definition(
                    note_registries,
                    key=note_registries.key_for_label(footnote_def_match.group(1)),
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

        # Semantic list rendering (FEATURE_016C): a bullet or numbered line
        # is styled as a list item before falling through to a plain body
        # paragraph — but only where something says a list is there.
        #
        # P4c-4′. Two things can say it. A ``ListBlock`` the traversal placed,
        # whose anchor opened the window above: that is how all 202 of the
        # corpus' Mathpix list items reach DOCX, and it is why the Mathpix
        # path keeps rendering from lines at all — its prose is not in the
        # ContentStream, so there is no node walk to replace them with. Or a
        # markdown with no traversal behind it (hand-written, a fixture, a
        # direct generate_docx() call), where the line's shape is the only
        # record of the list there is; that is FEATURE_016C's own case and it
        # is unchanged.
        #
        # What is no longer enough is the shape alone on a document that has a
        # model: `✓ Is the question doable?` is a paragraph O'Leary's Mathpix
        # import placed as prose, and it became a bulleted list item purely
        # because ``✓`` is in the character class — twice, against a model
        # holding 50 items and a package rendering 52.
        # A scanned page is the third: Docling's layout model labelled the
        # line a list item, and its "- "/"1. " prefix is how that label
        # survives into the page text.
        line_may_be_a_list_item = (
            index < list_line_limit or not stream_knows_pages or current_page in ocr_pages
        )
        bullet_match = _BULLET_LIST_PATTERN.match(line) if line_may_be_a_list_item else None
        if bullet_match:
            _add_list_paragraph(
                docx_document, bullet_match.group(2), "List Bullet", note_registries
            )
            pending_caption_after_image = False
            continue

        numbered_match = (
            _NUMBERED_LIST_PATTERN.match(line) if line_may_be_a_list_item else None
        )
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
    # A last page the markdown did not close with a page break still owes its
    # tables. close_page() is a no-op once the cursor has run past the last
    # page, so this cannot double-render one.
    if stream_knows_pages:
        close_page()
        # A note whose page the line loop never closed — markdown carrying more
        # page fences than the traversal has pages — would otherwise be lost
        # from its part entirely. register_body() is by label, so a note already
        # registered above is unchanged by this.
        for page_notes in stream_notes_by_page.values():
            for note in page_notes:
                _add_note_definition(
                note_registries, key=_NoteRegistries.key_for(note), body_text=note.body
            )
        # Same case for an image: a page the line loop never closed would drop
        # it from the document entirely, and its markdown line was dropped as a
        # restatement. Rendered late is recoverable; not rendered is not.
        for slot in (images_before_prose, images_at_close):
            for page_images in list(slot.values()):
                for image in page_images:
                    _add_stream_image(
                        docx_document, image, decorative_ids, page_widths
                    )

    _drop_dangling_note_references(docx_document, note_registries)

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


def _drop_dangling_note_references(docx_document: DocxDocument, registries: _NoteRegistries) -> None:
    """Remove any footnote/endnote reference whose note has no body.

    A ``[^label]`` in the markdown whose definition never reached a registry
    (a label the model does not know, a definition line an edit deleted)
    still gets a reference run and an id - but no body, and when no note of
    that kind has a body the part is not written at all. The result points
    at a note that does not exist: Word reports the file as damaged, and
    mammoth (the in-app preview) cannot render it. A reference with nothing
    to show is dropped, loudly, rather than shipping a broken document.
    """
    body = docx_document.element.body
    for registry, tag in ((registries.footnotes, "footnoteReference"), (registries.endnotes, "endnoteReference")):
        present = {str(note_id) for note_id, _ in registry.ordered_entries()}
        for reference in list(body.iter(qn(f"w:{tag}"))):
            if reference.get(qn("w:id")) in present:
                continue
            run = reference.getparent()
            run.getparent().remove(run)
            logger.warning("Dropped a {} with no note body (w:id={})", tag, reference.get(qn("w:id")))


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


# PDF "Author" values that name a machine or a template, not a person.
_PLACEHOLDER_AUTHORS = frozenset({"user", "admin", "administrator", "owner", "author", "unknown", "default"})


def _pdf_info(pdf_path: str) -> Dict[str, str]:
    """Title/author/subject/language the source PDF itself declares, blank
    where it declares nothing usable. A missing or unreadable PDF (fixtures,
    a regenerated document whose upload was cleaned up) declares nothing."""
    info = {"title": "", "author": "", "subject": "", "language": ""}
    try:
        import fitz

        with fitz.open(pdf_path) as pdf:
            meta = pdf.metadata or {}
            lang = pdf.xref_get_key(pdf.pdf_catalog(), "Lang")
    except Exception:
        return info
    info["title"] = (meta.get("title") or "").strip()
    author = (meta.get("author") or "").strip()
    if author.lower() not in _PLACEHOLDER_AUTHORS and not re.search(
        r"microsoft|adobe|acrobat|pdf|word|scanner", author, re.IGNORECASE
    ):
        info["author"] = author
    info["subject"] = (meta.get("subject") or "").strip()
    if lang and lang[0] == "string":
        info["language"] = lang[1].strip("()")
    return info


def _looks_like_a_filename(title: str) -> bool:
    """A PDF "Title" that is really the name of the file it was printed from
    ("Zina O Leary_The_essential_guide_to_doing_research.pdf")."""
    return bool(re.search(r"\.(pdf|docx?|pptx?|txt)$", title.strip(), re.IGNORECASE)) or title.count("_") >= 2


def _named_in_document(author: str, document: Document) -> bool:
    """Whether the PDF's "Author" is someone the document itself names.

    That field records whoever made the PDF - on a scan, the person who
    printed it ("Sharad Sure" on O'Leary's chapter, a book by Zina O'Leary).
    Putting a stranger's name in the author field is both wrong and a privacy
    leak the checklist asks to remove, so the name is only trusted when its
    surname appears in the document's own text.
    """
    surname = author.strip().split()[-1] if author.strip() else ""
    if len(surname) < 2:
        return False
    text = " ".join(
        [page.cleaned_text or page.raw_text or "" for page in document.pages]
        + [paragraph.text for paragraph in getattr(document, "paragraphs", []) or []]
        + [heading.text for heading in document.headings]
    )
    return re.search(rf"\b{re.escape(surname)}\b", text, re.IGNORECASE) is not None


def _apply_core_properties(docx_document: DocxDocument, document: Document) -> None:
    """Title, Author, Subject and Language, as the submission checklist asks.

    A reviewer-set value (the Metadata panel, FEATURE_016F) always wins.
    Otherwise each field falls back to what the document itself says - its
    front matter, then the PDF's own properties - and the title finally to
    the first heading or the file name, so a document never ships untitled.
    An author nobody stated stays blank for a person to fill: inventing one
    would be worse than the gap.

    python-docx's template also carries "python-docx" as author and
    "generated by python-docx" as a comment; both are tool information the
    checklist says to remove, so they are always cleared.
    """
    props = docx_document.core_properties
    m = document.metadata
    front = getattr(document, "front_matter", None)
    pdf = _pdf_info(document.source_pdf_path)
    first_heading = next(
        (h.text for h in document.headings if not h.is_page_marker and h.text.strip()), ""
    )
    title = (
        m.title
        or getattr(front, "title", None)
        or (pdf["title"] if not _looks_like_a_filename(pdf["title"]) else "")
        or first_heading
        or Path(document.source_pdf_path).stem
    )
    props.title = _safe_run_text(title)
    props.author = _safe_run_text(
        m.author
        or ", ".join(getattr(front, "authors", None) or [])
        or (pdf["author"] if _named_in_document(pdf["author"], document) else "")
    )
    props.subject = _safe_run_text(m.subject or pdf["subject"] or title)
    props.language = m.language or pdf["language"] or _DEFAULT_LANGUAGE
    props.comments = ""
    props.last_modified_by = ""
    props.keywords = ""
    props.revision = 1
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    props.created = now
    props.modified = now


def _document_language(document: Document) -> str:
    return (
        document.metadata.language
        or _pdf_info(document.source_pdf_path)["language"]
        or _DEFAULT_LANGUAGE
    )


def _apply_default_style(docx_document: DocxDocument, language: str = "en-US") -> None:
    """Every style in Times New Roman, and headings as the checklist's table.

    Setting fonts on runs alone is not enough: Word's built-in Heading,
    Title, Caption and TOC styles name *theme* fonts (``w:asciiTheme``),
    which override a plain font name, and Heading 6 is italic and blue. The
    H6 page markers carry no run formatting of their own, so before this
    they rendered in the theme's heading font, italic, 243F60 - three
    checklist violations on every page. Fixing the styles makes every
    paragraph right whatever its runs say.
    """
    styles = docx_document.styles.element
    for rfonts in styles.iter(qn("w:rFonts")):
        for attr in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
            rfonts.attrib.pop(qn(f"w:{attr}"), None)
        for attr in ("ascii", "hAnsi", "cs", "eastAsia"):
            rfonts.set(qn(f"w:{attr}"), _FONT_NAME)

    defaults = styles.find(qn("w:docDefaults"))
    if defaults is None:
        defaults = OxmlElement("w:docDefaults")
        styles.insert(0, defaults)
    rpr_default = defaults.find(qn("w:rPrDefault"))
    if rpr_default is None:
        rpr_default = OxmlElement("w:rPrDefault")
        defaults.insert(0, rpr_default)
    rpr = rpr_default.find(qn("w:rPr"))
    if rpr is None:
        rpr = OxmlElement("w:rPr")
        rpr_default.append(rpr)
    for tag, attrs in (
        ("w:rFonts", {a: _FONT_NAME for a in ("ascii", "hAnsi", "cs", "eastAsia")}),
        ("w:lang", {"val": language, "eastAsia": language, "bidi": language}),
    ):
        element = rpr.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            rpr.append(element)
        for attr, value in attrs.items():
            element.set(qn(f"w:{attr}"), value)

    normal_style = docx_document.styles["Normal"]
    normal_style.font.name = _FONT_NAME
    normal_style.font.size = Pt(_BODY_FONT_SIZE_PT)
    normal_style.font.color.rgb = _BLACK

    for level, size in _HEADING_FONT_SIZES_PT.items():
        _set_style_font(docx_document, f"Heading {level}", size, bold=True, italic=False)
    _set_style_font(docx_document, "Title", _HEADING_FONT_SIZES_PT[1], bold=True, italic=False)
    _set_style_font(docx_document, "Subtitle", _BODY_FONT_SIZE_PT, bold=False, italic=True)
    _set_style_font(docx_document, "Caption", _BODY_FONT_SIZE_PT, bold=False, italic=True)
    _set_style_font(docx_document, "TOC Heading", _BODY_FONT_SIZE_PT, bold=True, italic=False)


def _set_style_font(
    docx_document: DocxDocument, name: str, size_pt: int, bold: bool, italic: bool
) -> None:
    try:
        style = docx_document.styles[name]
    except KeyError:
        return
    style.font.name = _FONT_NAME
    style.font.size = Pt(size_pt)
    style.font.bold = bold
    style.font.italic = italic
    style.font.color.rgb = _BLACK


def _add_heading(docx_document: DocxDocument, level: int, text: str) -> None:
    """Add a heading using Word's built-in "Heading N" style.

    Built-in Heading 1-9 styles are what Word's Navigation Pane reads
    directly - no additional outline-level configuration is needed.
    Font overrides are applied on top per docs/HEADING_RULES.md.

    A content heading's text is written the checklist's way - numbered
    headings as ``6.1 - INTRODUCTION``, spacing and initialisms fixed. A page
    number (level 6) is a label and is written exactly as printed.
    """
    text = _safe_run_text(text if level == 6 else remediate_heading(text))
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
    equations = registries.equations
    for segment_text, is_bold, is_italic in _parse_inline_format(text):
        if equations is None:
            _add_text_with_note_references(
                paragraph, segment_text, registries, bold=is_bold, italic=is_italic
            )
            continue
        for kind, payload in equations.split_inline(segment_text):
            if kind == "text":
                _add_text_with_note_references(
                    paragraph, payload, registries, bold=is_bold, italic=is_italic
                )
            elif kind == "equation":
                equations.add_inline(paragraph, payload)
            else:
                equations.add_reference(paragraph, payload)


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
        _add_note_reference_run(
            paragraph, registries.key_for_label(match.group(1)), registries
        )
        position = match.end()

    if position < len(text) or not has_reference:
        _add_plain_run(paragraph, text[position:], bold=bold, italic=italic)


def _add_plain_run(
    paragraph: Paragraph, text: str, bold: bool = False, italic: bool = False
) -> None:
    """Body text as the checklist wants it read: spacing, units and
    initialisms fixed (``remediate_prose``), and every web address a live
    hyperlink rather than inert text."""
    if not text:
        return
    text = remediate_prose(text)
    position = 0
    for match in URL_PATTERN.finditer(text):
        _add_formatted_run(paragraph, text[position : match.start()], bold, italic)
        _add_hyperlink(paragraph, match.group(0), bold, italic)
        position = match.end()
    _add_formatted_run(paragraph, text[position:], bold, italic)


def _add_formatted_run(paragraph: Paragraph, text: str, bold: bool, italic: bool):
    if not text:
        return None
    run = paragraph.add_run(_safe_run_text(text))
    run.font.name = _FONT_NAME
    run.font.size = Pt(_BODY_FONT_SIZE_PT)
    run.font.bold = bold
    run.font.italic = True if italic else None
    run.font.color.rgb = _BLACK
    return run


def _add_hyperlink(paragraph: Paragraph, address: str, bold: bool, italic: bool) -> None:
    """``address`` as an external ``w:hyperlink``. Its display text stays the
    address as printed, so the document still matches the PDF word for word;
    the target gains a scheme when the print had none (``www.``)."""
    target = address if re.match(r"https?://", address, re.IGNORECASE) else f"http://{address}"
    relationship_id = paragraph.part.relate_to(target, RT.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)
    run = _add_formatted_run(paragraph, address, bold, italic)
    run.font.color.rgb = RGBColor.from_string(_HYPERLINK_COLOR)
    run.font.underline = True
    paragraph._p.remove(run._r)
    hyperlink.append(run._r)
    paragraph._p.append(hyperlink)


def _add_note_reference_run(
    paragraph: Paragraph, key: str, registries: _NoteRegistries
) -> None:
    """A native OOXML ``w:footnoteReference`` or ``w:endnoteReference``
    run, whichever this note's ``NoteType`` calls for (L4b).

    ``key`` is the note's identity (P4c-2), from ``_NoteRegistries.key_for``
    or, on the markdown fallback paths, ``key_for_label``.

    Word auto-numbers and renders the printed superscript digit from the
    referenced entry in the corresponding part; no explicit text content
    is needed here.  Word's built-in character style for the marker is
    requested via ``w:rStyle`` with an explicit ``w:vertAlign
    superscript`` as a fallback in case the style is not defined in the
    template.
    """
    part = registries.part_for(key)
    note_id = registries.registry_for(key).get_or_assign_id(key)

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
    registries: _NoteRegistries, key: str, body_text: str
) -> None:
    """Register a note body for inclusion in its own part.

    Native OOXML notes live in a separate document part, not as
    paragraphs in the main body.  No paragraph is added here; the body
    text is stored in the registry its ``NoteType`` selects, and the
    parts are built and attached after the main rendering loop
    completes.

    ``key`` is the note's identity (P4c-2), so a body and the references to
    it meet on ``footnote_id`` rather than on a printed label.
    """
    registries.registry_for(key).register_body(key, _safe_run_text(remediate_prose(body_text)))


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


def _build_decorative_set(document: Document) -> set:
    """Return the image_ids of images marked DECORATIVE by the reviewer."""
    from src.models.figure import AltTextStatus
    result = set()
    for image in document.images:
        if (
            image.figure is not None
            and image.figure.alt_text_status == AltTextStatus.DECORATIVE
        ):
            result.add(image.image_id)
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

    grid = [[row[c] if c < len(row) else "" for c in range(num_cols)] for row in parsed]
    header_rows = set(range(header_row_count)) or {0}
    for row_idx in range(len(grid)):
        docx_row = table.rows[row_idx]
        if row_idx in header_rows:
            _set_row_tbl_header(docx_row)
        for col_idx in range(num_cols):
            _write_cell(docx_row.cells[col_idx], grid[row_idx][col_idx], row_idx in header_rows)
    _add_table_summary(docx_document, _describe_table(grid, header_rows))


def _add_caption(docx_document: DocxDocument, text: str) -> None:
    """A centered caption in Word's own "Caption" style - the style Word's
    Insert Caption applies, which is what the checklist asks for, and what
    lets Word list figures and tables."""
    try:
        paragraph = docx_document.add_paragraph(style="Caption")
    except KeyError:
        paragraph = docx_document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(_safe_run_text(remediate_prose(text)))
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
    """A document's title is its Heading 1.

    The remediation checklist's heading table says so in as many words -
    "Level 1 (Book Name): Times New Roman 16, Black, Bold" - and a title in
    Word's "Title" style is invisible to the Navigation Pane and to a
    screen reader's heading list, so the outline began one level down."""
    _add_heading(docx_document, 1, text)


def _add_byline(docx_document: DocxDocument, text: str) -> None:
    """An author byline - Word's built-in "Subtitle" style plus an
    explicit italic font override."""
    paragraph = docx_document.add_paragraph(style="Subtitle")
    run = paragraph.add_run(_safe_run_text(remediate_prose(text)))
    run.font.name = _FONT_NAME
    run.font.size = Pt(_BODY_FONT_SIZE_PT)
    run.font.italic = True
    run.font.color.rgb = _BLACK


def _add_affiliation(docx_document: DocxDocument, text: str) -> None:
    """An author's institutional affiliation - plain body-sized text,
    visually distinct from the byline above it only by not being
    italic/larger, matching how the markdown rendering of this same
    line (src/markdown/markdown_builder.py) is unformatted plain text
    too."""
    paragraph = docx_document.add_paragraph()
    run = paragraph.add_run(_safe_run_text(remediate_prose(text)))
    run.font.name = _FONT_NAME
    run.font.size = Pt(_BODY_FONT_SIZE_PT)
    run.font.bold = False
    run.font.color.rgb = _BLACK


def _add_image(
    docx_document: DocxDocument,
    image_path: str,
    alt_text: str = "",
    decorative: bool = False,
    printed_size: Optional[Tuple[int, int]] = None,
) -> bool:
    """Insert an image inline with text, centered.

    ``printed_size`` (EMU width, height) is how big the picture was on the PDF
    page (see ``_printed_size``); without it the picture keeps its pixel size,
    capped at the text width.

    The checklist says "All images should be center-aligned and inline with
    text", so there is no alignment to choose: an earlier version mirrored
    the image's horizontal position on the PDF page, which put figures
    flush left or right in the Word file.

    decorative=True marks the picture decorative the way Word's own "Mark as
    decorative" does (the ``a16:decorative`` docPr extension) and clears
    descr/title, so screen readers skip it and Word's Accessibility Checker
    does not report it as missing alt text. Otherwise non-empty alt_text is
    set on descr and title.

    Missing or unreadable image files are logged and skipped rather
    than raised, so one bad image reference does not abort generation
    of the rest of the document - and leave no empty paragraph behind.

    Returns True when the image was successfully embedded, False when it was
    skipped (file not found or add_picture raised). The caller records this
    result on the Image model so IMAGE_005 validation can surface silent drops.
    """
    path = Path(image_path)
    if not path.is_file():
        logger.warning("Image file not found, skipping insertion: {}", path)
        return False

    paragraph = docx_document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()

    picture_source = _docx_compatible_picture_source(path)

    try:
        picture = run.add_picture(picture_source)
    except Exception as exc:  # python-docx raises various error types on bad images
        logger.warning("Failed to insert image '{}': {}", path, exc)
        paragraph._p.getparent().remove(paragraph._p)
        return False

    if printed_size is not None:
        picture.width, picture.height = Emu(printed_size[0]), Emu(printed_size[1])
    if picture.width > _MAX_IMAGE_WIDTH:
        aspect_ratio = picture.height / picture.width
        picture.width = _MAX_IMAGE_WIDTH
        picture.height = Emu(int(_MAX_IMAGE_WIDTH * aspect_ratio))

    doc_properties = picture._inline.docPr
    if decorative:
        doc_properties.set("descr", "")
        doc_properties.set("title", "")
        _mark_decorative(doc_properties)
    elif alt_text:
        safe_alt_text = _safe_run_text(alt_text)
        doc_properties.set("descr", safe_alt_text)
        doc_properties.set("title", safe_alt_text)

    return True


_EMU_PER_POINT = 12700
_LETTER_WIDTH_PT = 612.0


def _printed_size(image, page_widths: Dict[int, float]) -> Optional[Tuple[int, int]]:
    """How big the picture was printed on the PDF page, in EMU - so the Word
    page shows it at the same share of the page as the PDF did, instead of
    stretching every figure to the full text width.

    A Mathpix crop states its own box (``src/utils/mathpix_crop.py``): its
    share of the page's width, applied to the page's width in points. Any
    other image has the rectangle PyMuPDF found it drawn at. Height follows
    the width at the picture's own proportions, which for a Mathpix crop are
    exactly the printed ones. None when neither is known.
    """
    page_width_pt = page_widths.get(getattr(image, "page_number", 0), _LETTER_WIDTH_PT)
    box = crop_box(getattr(image, "file_path", None))
    if box is not None and box.width and box.height:
        width_pt = box.width_fraction() * page_width_pt
        return int(width_pt * _EMU_PER_POINT), int(width_pt * box.height / box.width * _EMU_PER_POINT)
    bbox = getattr(image, "bbox", None)
    if bbox is not None and bbox.x1 > bbox.x0 and bbox.y1 > bbox.y0:
        return int((bbox.x1 - bbox.x0) * _EMU_PER_POINT), int((bbox.y1 - bbox.y0) * _EMU_PER_POINT)
    return None


_DECORATIVE_EXT_URI = "{C183D7F6-B498-43B3-948B-1728B52AA6E4}"
_A16_DECORATIVE_NS = "http://schemas.microsoft.com/office/drawing/2017/decorative"
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _mark_decorative(doc_properties) -> None:
    """Word 365's "Mark as decorative": an ``a:extLst`` on ``wp:docPr``
    carrying ``adec:decorative val="1"``."""
    ext_list = etree.SubElement(doc_properties, f"{{{_A_NS}}}extLst")
    ext = etree.SubElement(ext_list, f"{{{_A_NS}}}ext")
    ext.set("uri", _DECORATIVE_EXT_URI)
    flag = etree.SubElement(ext, f"{{{_A16_DECORATIVE_NS}}}decorative", nsmap={"adec": _A16_DECORATIVE_NS})
    flag.set("val", "1")


def _add_semantic_table(docx_document: DocxDocument, table) -> None:
    """Render a Table model as an accessible DOCX table, checklist-style.

      - Caption as a centered paragraph in Word's Caption style above the
        table, so Word's document order matches the visual order.
      - w:tblHeader ("Repeat Header Row") on every header row so screen
        readers announce column context. A table whose model marks no header
        row gets its first row marked: every data table has one, and Word's
        Accessibility Checker fails a table without it.
      - **No merged cells.** The remediation checklist says "no merged cells
        involved, instead repeat the words": a spanning cell's text is
        written into every cell it covers, so a screen reader reading any
        cell hears its heading, and the reading order is a plain grid.
      - A summary below the table, always: the reviewer's when there is one,
        otherwise a factual description of its shape and column headings.
    """
    if table.caption:
        _add_caption(docx_document, table.caption)

    if not table.rows:
        return

    row_count = len(table.rows)
    col_count = max(table.col_count, 1, *(len(r.cells) for r in table.rows))
    grid = _table_text_grid(table, row_count, col_count)
    header_rows = {i for i, row in enumerate(table.rows) if row.is_header_row} or {0}

    try:
        docx_table = docx_document.add_table(rows=row_count, cols=col_count, style="Table Grid")
    except KeyError:
        docx_table = docx_document.add_table(rows=row_count, cols=col_count)

    for row_idx, table_row in enumerate(table.rows):
        docx_row = docx_table.rows[row_idx]
        if row_idx in header_rows:
            _set_row_tbl_header(docx_row)
        for col_idx in range(col_count):
            cell = next((c for c in table_row.cells if c.col_index == col_idx), None)
            is_bold = row_idx in header_rows or bool(cell and (cell.is_header or cell.is_row_header))
            _write_cell(docx_row.cells[col_idx], grid[row_idx][col_idx], is_bold)

    _add_table_summary(docx_document, table.summary or _describe_table(grid, header_rows))


def _table_text_grid(table, row_count: int, col_count: int) -> List[List[str]]:
    """Each grid position's text, with a spanning cell's words repeated into
    every position it covers (the checklist's alternative to merging)."""
    grid = [["" for _ in range(col_count)] for _ in range(row_count)]
    for row_idx, table_row in enumerate(table.rows):
        for position, cell in enumerate(table_row.cells):
            col_idx = cell.col_index if cell.col_index is not None else position
            if col_idx >= col_count:
                continue
            row_span = max(cell.row_span or 1, 1)
            col_span = max(cell.col_span or 1, 1)
            for r in range(row_idx, min(row_idx + row_span, row_count)):
                for c in range(col_idx, min(col_idx + col_span, col_count)):
                    if not grid[r][c]:  # a covered cell the model left empty takes the span's words
                        grid[r][c] = cell.text
    return grid


def _describe_table(grid: List[List[str]], header_rows: set) -> str:
    """A factual summary for a table nobody has described: its size and, when
    its header row has text, the column headings in order. It states only
    what the table itself says, so it can never be wrong about the content."""
    rows, cols = len(grid), len(grid[0]) if grid else 0
    summary = f"Table with {rows} rows and {cols} columns."
    headings = [text.strip() for text in grid[min(header_rows)] if text.strip()] if grid else []
    if headings:
        summary += " Column headings: " + "; ".join(headings) + "."
    statistics = _numeric_column_statistics(grid, header_rows)
    if statistics:
        summary += " " + " ".join(statistics)
    return summary


_NUMBER_IN_CELL = re.compile(r"^[-−]?\d[\d,]*(?:\.\d+)?%?$|^[-−]?\.\d+%?$")
# A screen reader user hears a summary before the table; four columns of
# statistics is already a paragraph.
_MAX_SUMMARISED_COLUMNS = 4
_MIN_NUMERIC_VALUES = 2


def _numeric_column_statistics(grid: List[List[str]], header_rows: set) -> List[str]:
    """For each numeric column, its highest and lowest value and which row each
    belongs to - "Score: highest 45% (Kerala), lowest 12% (Bihar)." - so a
    listener knows what the numbers say before hearing them cell by cell.
    Stated only from the table's own cells; a column that is not wholly
    numeric (years mixed with notes, say) is left out rather than guessed at.
    """
    if not grid:
        return []
    header = grid[min(header_rows)]
    body = [row for index, row in enumerate(grid) if index not in header_rows]
    sentences: List[str] = []
    for column in range(1, len(header)):
        values = []
        for row in body:
            text = row[column].strip() if column < len(row) else ""
            if not text:
                continue
            if not _NUMBER_IN_CELL.match(text):
                values = []
                break
            number = float(text.replace(",", "").replace("%", "").replace("−", "-"))
            values.append((number, text, row[0].strip()))
        if len(values) < _MIN_NUMERIC_VALUES or not header[column].strip():
            continue
        highest, lowest = max(values), min(values)
        sentences.append(
            f"{header[column].strip()}: highest {highest[1]}{_row_name(highest[2])}, "
            f"lowest {lowest[1]}{_row_name(lowest[2])}."
        )
        if len(sentences) == _MAX_SUMMARISED_COLUMNS:
            break
    return sentences


def _row_name(label: str) -> str:
    return f" ({label})" if label else ""


def _write_cell(docx_cell, text: str, bold: bool) -> None:
    para = docx_cell.paragraphs[0]
    para.clear()
    run = para.add_run(_safe_run_text(remediate_prose(text)))
    run.font.name = _FONT_NAME
    run.font.size = Pt(_BODY_FONT_SIZE_PT)
    run.font.color.rgb = _BLACK
    run.bold = bold


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
    if trPr.find(qn("w:tblHeader")) is None:
        trPr.append(OxmlElement("w:tblHeader"))


def _add_table_summary(docx_document: DocxDocument, summary_text: str) -> None:
    """Render the WCAG H73-equivalent summary as a paragraph below the table.

    The summary is intended for screen reader users who need a prose
    description of a table before (or after) navigating its cells. It is
    rendered visibly rather than hidden, because DOCX has no native
    table-summary attribute equivalent to HTML's summary="...", and in the
    document's body text (Times New Roman 12, black) like any other text.
    """
    paragraph = docx_document.add_paragraph()
    run = paragraph.add_run(_safe_run_text(remediate_prose(f"Table summary: {summary_text}")))
    run.font.name = _FONT_NAME
    run.font.size = Pt(_BODY_FONT_SIZE_PT)
    run.font.italic = True
    run.font.color.rgb = _BLACK


def _python_docx_reads(path: Path) -> bool:
    """Whether python-docx can parse this file's header as it stands.

    Asked of python-docx's own ``SIGNATURES`` table rather than a copy of
    it, because the question *is* "what will ``add_picture`` accept" and a
    second list here would drift from the first. An import or read failure
    answers False, which routes the file through normalisation — the safe
    direction, since normalisation itself is guarded.
    """
    try:
        from docx.image import SIGNATURES

        with path.open("rb") as stream:
            header = stream.read(32)
    except Exception:  # unreadable file, or a python-docx without SIGNATURES
        return False
    return any(
        header[offset : offset + len(signature)] == signature
        for _, offset, signature in SIGNATURES
    )


# Modes whose pixels JPEG cannot store. PNG is the accepted format that
# carries them, and Pillow raises OSError rather than silently flattening,
# so this is a real fork and not a preference.
_ALPHA_CAPABLE_MODES = frozenset({"RGBA", "LA", "PA", "P"})
# Modes JPEG stores directly, so they need no conversion before saving.
_JPEG_NATIVE_MODES = frozenset({"RGB", "L", "1"})


def _docx_compatible_picture_source(path: Path) -> Union[str, io.BytesIO]:
    """Return whatever run.add_picture() should be given for this file.

    python-docx recognizes an image only by a literal signature —
    ``\\x89PNG``/``GIF8``/``BM``/``MM\\x00*``/``II*\\x00`` at offset 0, or
    ``JFIF``/``Exif`` at offset 6 for a JPEG
    (docx.image.image._ImageHeaderFactory / SIGNATURES). It has no
    Pillow/libjpeg dependency of its own, so a perfectly readable image
    whose container lacks the expected marker raises
    UnrecognizedImageError. Markdown was never affected, since it never
    runs a file through python-docx.

    **The marker, not the colour mode, is what fails.** This function was
    written for the CMYK case (the Brinkman regression PDF's 3 figures, which
    carry an Adobe APP14 marker and no JFIF segment) and its guard tested
    ``mode == "CMYK"`` — so it repaired that case only, and only because
    converting to RGB and re-saving through Pillow writes a JFIF header as a
    side effect. Measured on the Mathpix corpus: 18 of 18 supplied figures are
    plain **RGB** JPEGs beginning ``FF D8 FF DB`` with no JFIF or Exif
    segment, so every one of them fell straight past that guard and was
    dropped from the DOCX — 0 drawings, 0 media parts, 18 empty paragraphs.

    So the question asked here is now the real one: *can python-docx read
    this file?* If it can, the original path is returned untouched and
    nothing is re-encoded. If it cannot, the image is normalised once,
    through the Pillow path that already existed, into a format python-docx
    does accept:

    * **alpha- or palette-capable modes -> PNG.** JPEG cannot store them at
      all (Pillow raises OSError), and PNG is lossless, so transparency
      survives rather than being flattened.
    * **everything else -> JPEG**, converting to RGB first for any mode JPEG
      cannot store directly. CMYK lands here and takes exactly the path it
      always took (``convert("RGB")`` then a default-quality JPEG save), so
      its bytes are unchanged — and CMYK *must* go to JPEG rather than PNG,
      because PNG cannot represent it at all.

    The converted bytes exist only in memory for this one call - the file on
    disk is never written to, so image extraction, markdown rendering, and
    the Image/Figure models (which only ever reference the file's path) are
    all unaffected. Pixel dimensions are preserved by every branch, so
    ``_MAX_IMAGE_WIDTH`` scaling and the rendered aspect ratio are unchanged.

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
            # CMYK first, and before the readable check, so this mode keeps
            # byte-for-byte the behaviour it has had since the CMYK repair
            # whatever its container says.
            if pil_image.mode == "CMYK":
                normalized, image_format = pil_image.convert("RGB"), "JPEG"
            elif _python_docx_reads(path):
                return str(path)
            elif (
                pil_image.mode in _ALPHA_CAPABLE_MODES
                or "transparency" in pil_image.info
            ):
                normalized, image_format = pil_image, "PNG"
            elif pil_image.mode in _JPEG_NATIVE_MODES:
                normalized, image_format = pil_image, "JPEG"
            else:
                normalized, image_format = pil_image.convert("RGB"), "JPEG"

            buffer = io.BytesIO()
            normalized.save(buffer, format=image_format)
    except Exception as exc:
        # A file Pillow cannot read either. Hand back the path so
        # _add_image() reports the failure exactly as it always has.
        logger.warning("Could not normalize image for DOCX embedding '{}': {}", path, exc)
        return str(path)

    buffer.seek(0)
    return buffer
