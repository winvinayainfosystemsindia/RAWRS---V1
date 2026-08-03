"""Markdown generation for RAWRS.

Converts a populated Document model into a single canonical markdown
string: H1-H6 headings (with H6 reserved for page markers), image
references, footnote/endnote references and definitions, and page-break
markers, in document reading order.

Per docs/ARCHITECTURE.md, this module sits after Heading Detection and
Image Extraction in the pipeline, and consumes their output as-is - it
does not detect headings, extract images, detect footnotes, run OCR,
perform validation, or generate alt text/DOCX output.

Design note on page markers: Heading Detection (src/headings/) already
creates exactly one H6 marker Heading per page in document.headings.
This module renders those existing markers rather than re-generating
new ones from page numbers, since doing both would produce duplicate
page markers - a violation of the Phase 1 "one page marker per page"
rule. If a marker is unexpectedly missing for a page, one is
synthesized here as a fallback so output remains valid, and a warning
is logged.

Design note on ordering: Heading.document_order is the source of truth
for heading order. P-IMG gave Image the same two facts - source_block_id
(the line it follows) and document_order - resolved once in
src/structure/relationships.py, so images now render where the model
says they sit rather than after all of a page's body text. That page-end
slot was never right; it was the only thing the model could express. It
survives as the fallback for images the model cannot place: no bbox
(the Mathpix path), an unlinked Document that never ran Stage 5c, or a
page with no TextBlock data to anchor against (the OCR line-by-line
path).

Design note on footnotes/endnotes (Phase K): standard Pandoc-style
markdown footnote syntax is ``[^label]`` inline plus a matching
``[^label]: body`` definition. The visible printed number RAWRS
detected (Footnote.number) is not by itself a safe markdown label,
because footnote numbering conventionally resets per page - two
different footnotes from two different pages can share the same
printed "1". ``Footnote.label`` (src/models/footnote.py) is the
page-qualified label (``p{page}-{number}``) that is unique across the
whole document while keeping the original printed number visible inside
it, so the human-meaningful number survives even though the underlying
label isn't itself the bare number. P2 moved that formula onto the model:
what a note calls itself is a property of the note, not of Markdown, and
this module previously owned it while the DOCX projection recovered it by
parsing this module's output. Footnote definitions render immediately
after the page that anchors them (print convention: a footnote belongs
with its page); endnote definitions are collected into a single
"## Endnotes" section at the end of the document, since by definition
they are detached from any one page.

Design note on front matter (Front-Matter Semantic Extraction): a
document's title/author(s)/affiliation(s) (Document.front_matter - see
src/frontmatter/front_matter_extractor.py) previously had no rendering
treatment at all and were silently flattened into ordinary body text.
When present, they render as a small, distinct block (bold title,
italic author line, plain affiliation line) immediately after page 1's
H6 marker, deliberately not as a competing H1 heading - the existing
H1 (e.g. a "Article"-style kicker line, unaffected by this module)
still renders exactly as before. Their exact source lines are
suppressed from page 1's ordinary body rendering the same way a
footnote body's or a figure caption's source line already is -
omitting that step would render them a second time, the same
duplication class already fixed twice elsewhere in this module. P2
moved that suppression into the model: on the paragraph path the
absorbed lines simply never become part of a Paragraph (see
src/structure/paragraph_assembly.py); the line-by-line fallback below
still resolves them by text, since it has no blocks to key on.

Design note on paragraph reconstruction (see
samples/regressions/bug_001_brinkman_word_splitting/notes_md/ for the
audit and design review this implements): paragraphs are no longer
reconstructed here. P2 moved grouping - and the "is this line prose?"
rule it depends on - into src/structure/paragraph_assembly.py, which
runs once in the pipeline (Stage 5c) and stores its result on
Document.paragraphs. _render_page_body_with_paragraphs is now a
projection of those objects: it emits a paragraph when it reaches the
block that paragraph starts at. A Document that never ran Stage 5c gets
them assembled on the way in (see build_markdown), so there is one
implementation of the rule and not a render-time copy of it.
Pages with no blocks (e.g. OCR-recovered pages - Structure Detection
only reads a PDF's native text layer, never Docling/Surya output, see
structure_detector.py) still fall back to
_render_page_body_line_by_line, the original one-line-per-block
behavior, unchanged - there is no bbox data to ground paragraph
reconstruction in for those pages, so they keep their own text-keyed
suppression sets.

Design note on formatting fidelity (016G): when a paragraph is emitted,
_render_paragraph looks up its contributing TextBlocks by id
(Paragraph.source_block_ids) and checks whether every one of their spans (TextBlock.spans, feature_005) are uniformly bold and/or
italic — non-superscript spans only, since a footnote marker's
superscript span is decoration, not body-text formatting. A uniformly
bold paragraph wraps its text in ``**...**``; italic in ``*...*``; both
in ``***...***``. When a block has no span data, TextBlock.is_bold is
the bold fallback (the majority-vote line-level signal already populated
by structure_detector.py); italic has no line-level equivalent so blocks
without spans never assert italic. The paragraph text is always
substituted for footnote markers AFTER the format wrapper is applied,
keeping the anchor_text lookup correct (it's still a substring of the
wrapped text, at a predictable offset). This path only operates in the
paragraph-reconstruction path (_render_page_body_with_paragraphs) where
TextBlock data exists — the OCR/line-by-line fallback has no span data
and emits plain text unchanged.
"""

import re
from typing import Dict, List, Optional, Set, Tuple

from loguru import logger

from src.config.page_numbering import PageNumberingPolicy
from src.models.contracts import (
    Document,
    Footnote,
    FrontMatter,
    Heading,
    HeadingLevel,
    Image,
    ListBlock,
    ListType,
    NoteType,
    Page,
    Paragraph,
    Table,
    TextBlock,
)
from src.architecture.contract import GeneratedObject, Limitation, ProjectionContract
from src.structure.paragraph_assembly import (
    NOTES_SECTION_HEADING_PATTERN,
    absorbed_block_ids,
    assemble_paragraphs,
    headings_by_anchor,
    paragraph_starts,
)

# Public so downstream stages (e.g. src/docx/docx_generator.py) that parse
# this module's markdown output can match the exact same token rather than
# duplicating it as an independent magic string.
PAGE_BREAK_MARKER = "<!-- pagebreak -->"

# What this projection cannot do, declared in advance (ADR-020 PI-1/PI-2/PI-6,
# enforced by src/architecture/invariants.py AI-7 and read by
# src/benchmark/projection.py). An absence or an invention that is not listed
# here is a violation, not a quirk — which is the point: the pre-P2 renderer
# discarded 20 headings precisely because nothing forced it to say so.
#
# Deliberately NOT listed: the synthesized page marker in _find_page_marker().
# It fires on 0 of 161 corpus pages, and leaving it undeclared means the
# checker reports it loudly as an invented object if it ever does.
PROJECTION_CONTRACT = ProjectionContract(
    format_id="markdown",
    generates=(
        GeneratedObject(
            kind="heading",
            identity="Endnotes",
            reason=(
                "Endnote definitions are collected into one section at the end of "
                "the document, and the model has no object for that section's "
                "heading. _render_endnotes_section() writes it. Retired when the "
                "endnote section becomes a model object."
            ),
        ),
    ),
    limitations=(
        Limitation(
            code="front_matter_title_rendered_as_block",
            kind="heading",
            reason=(
                "The document title is an H1 in document.headings and is also the "
                "front matter's title. _render_front_matter_blocks() owns its "
                "rendering (FE-0-005), so the heading deliberately does not render "
                "a second time. The model records no 'this heading is the title' "
                "fact, so the projection currently decides it."
            ),
        ),
        Limitation(
            code="absorbed_by_another_object",
            kind="heading",
            reason=(
                "A heading whose anchor block a table, note body, caption, front "
                "matter or the endnotes section already carries is not emitted: "
                "absorbed beats heading (ADR-020 §3). The authorizing fact is a "
                "recorded containment edge, so this is a model decision the "
                "projection obeys, not one it makes."
            ),
        ),
    ),
)

# P2: the endnotes section-heading rule now lives in
# src/structure/paragraph_assembly.py, where the paragraph assembler needs
# the same answer. Aliased rather than duplicated - the line-by-line
# fallback path below still applies it to raw text.
_NOTES_SECTION_HEADING_PATTERN = NOTES_SECTION_HEADING_PATTERN


def _group_tables_by_page(tables: List[Table]) -> Dict[int, List[Table]]:
    grouped: Dict[int, List[Table]] = {}
    for table in tables:
        grouped.setdefault(table.page_number, []).append(table)
    return grouped


def _group_paragraphs_by_page(paragraphs: List[Paragraph]) -> Dict[int, List[Paragraph]]:
    """Both paths since P2: the Mathpix import supplies its own Paragraphs
    (with source_line positions), and Stage 5c assembles them for native
    documents. Formerly Mathpix-only, which is why a non-empty list used to
    be usable as a path discriminator - see build_markdown for what
    replaced that."""
    grouped: Dict[int, List[Paragraph]] = {}
    for para in paragraphs:
        grouped.setdefault(para.page_number, []).append(para)
    return grouped


def _group_lists_by_page(lists: List[ListBlock]) -> Dict[int, List[ListBlock]]:
    grouped: Dict[int, List[ListBlock]] = {}
    for lst in lists:
        grouped.setdefault(lst.page_number, []).append(lst)
    for page_lists in grouped.values():
        page_lists.sort(key=lambda lst: lst.document_order)
    return grouped


def _render_lists(lists: List[ListBlock]) -> List[str]:
    """Render each ListBlock as a real markdown list — the fix for
    "lists becoming paragraphs" (see src/mathpix/ingestor.py's
    _group_list_items_to_lists and src/verification/lists.py). Renders
    after this page's body text and tables, mirroring _render_tables()'s
    same per-page-only positioning (list content no longer has an
    in-body-flow anchor once excluded from page.cleaned_text). The
    ``<!-- list-id: {id} -->`` anchor is a no-op comment for the DOCX
    generator's benefit — the rendered bullet/numbered lines themselves
    already flow through its existing FEATURE_016C list-style rendering,
    with no need for the DOCX side to look up the ListBlock model at all.
    """
    blocks: List[str] = []
    for lst in lists:
        if not lst.items:
            continue
        blocks.append(f"<!-- list-id: {lst.id} -->")
        marker = "-" if lst.list_type == ListType.BULLET else "1."
        lines = [f"{'  ' * item.level}{marker} {item.text}" for item in lst.items]
        blocks.append("\n".join(lines))
    return blocks


def _render_pipe_table(table: Table) -> str:
    """Render a Table as a GitHub-flavoured Markdown pipe table.

    The first row is treated as the header when TableRow.is_header_row
    is True (the default for auto-detected tables with >1 row, and
    whatever the reviewer set for manually-created ones).  The separator
    row (|---|---|) is inserted after the last header row.
    """
    if not table.rows:
        return ""

    lines = []
    header_done = False
    for row in table.rows:
        cell_texts = [cell.text.replace("|", "\\|").replace("\n", " ") for cell in row.cells]
        lines.append("| " + " | ".join(cell_texts) + " |")
        if row.is_header_row and not header_done:
            sep = "| " + " | ".join("---" for _ in row.cells) + " |"
            lines.append(sep)
            header_done = True

    # If no header row was marked, insert separator after the first row
    # so output is always valid GitHub Markdown.
    if not header_done and len(lines) >= 1:
        col_count = len(table.rows[0].cells) if table.rows else 1
        sep = "| " + " | ".join("---" for _ in range(col_count)) + " |"
        lines.insert(1, sep)

    return "\n".join(lines)


def build_markdown(
    document: Document,
    page_numbering_policy: Optional[PageNumberingPolicy] = None,
) -> str:
    """Build the canonical markdown representation of a Document.

    Args:
        document: A Document with pages, headings (including H6 page
            markers from Heading Detection), and images (from Image
            Extraction) already populated.
        page_numbering_policy: The same policy that was passed to
            detect_headings() for this document.  Used only by the
            fallback marker-synthesis path inside _find_page_marker()
            — when the policy is active and says no marker for a page,
            the fallback is also suppressed so the two call sites remain
            consistent.  When None (default), the legacy fallback
            behaviour is preserved.

    Returns:
        A single markdown string covering every page in order, or an
        empty string if the document has no pages.
    """
    logger.info("Building markdown for '{}'", document.source_pdf_path)

    if not document.pages:
        logger.warning("Document '{}' has no pages; returning empty markdown", document.source_pdf_path)
        return ""

    images_by_page = _group_images_by_page(document.images)
    notes_by_anchor_page = _group_notes_by_anchor_page(document.footnotes)
    notes_by_body_page = _group_notes_by_body_page(document.footnotes)
    blocks_by_page = _group_blocks_by_page(document.blocks)
    tables_by_page = _group_tables_by_page(document.tables)
    lists_by_page = _group_lists_by_page(document.lists)
    # P2: paragraphs come from the model. Stage 5c stores them; a Document
    # that never ran it (a direct build_markdown() call, a fixture) gets
    # them assembled here rather than this module keeping its own grouping
    # logic for that case — same function, same answer, one implementation.
    paragraphs = document.paragraphs or assemble_paragraphs(document)
    paragraphs_by_page = _group_paragraphs_by_page(paragraphs)
    has_endnotes = any(note.note_type == NoteType.ENDNOTE for note in document.footnotes)
    sorted_pages = sorted(document.pages, key=lambda page: page.page_number)

    # FEATURE_020 — a document that came through the Mathpix import path
    # (src/mathpix/ingestor.py) gets its body rendered as a projection of
    # Document's own semantic objects (_render_page_semantic()), sorted
    # by source_line, instead of _render_page_body_line_by_line()'s
    # exact-text-match reinsertion — which can never match, since
    # heading/list/table text is deliberately excluded from
    # page.cleaned_text (see _assign_page_text()) to avoid double-
    # rendering. document.paragraphs is only ever populated on that
    # path (empty for RAWRS-native — see Paragraph's docstring), so its
    # presence is the signal; a document with real Mathpix headings but
    # zero paragraph blocks still counts via the second check.
    # P2: ask the document who imported it. ``Document.import_provider`` is
    # set by the ingestion path itself and is the same field the correction
    # rail already reads, so a projection no longer infers provenance from
    # the shape of the objects it was handed. The heuristic below stays as
    # the fallback for a Document assembled without it (fixtures, direct
    # build_markdown() calls), where inferring is still better than
    # guessing wrong.
    # P2: ``bool(document.paragraphs)`` is no longer a Mathpix signal —
    # Stage 5c now assembles paragraphs on the native path too, which is the
    # point of moving grouping into the model. The discriminator becomes the
    # two things only an import can produce: a declared provider, or objects
    # carrying a position in a source .mmd. ``import_provider`` alone is not
    # enough on its own, because a Document built straight from the ingestor
    # (unit tests, a re-render of stored objects) never passed through the
    # pipeline line that sets it — and setting it on the *native* path is not
    # an option, since six verifiers read a falsy import_provider as
    # "single-source document, nothing to reconcile against".
    is_mathpix_import = (
        getattr(document, "import_provider", None) == "mathpix"
        or any(h.source == "mathpix" for h in document.headings)
        or any(p.source_line is not None for p in paragraphs)
    )

    sections = [
        _render_page(
            document,
            page,
            document.headings,
            images_by_page.get(page.page_number, []),
            notes_by_anchor_page.get(page.page_number, []),
            notes_by_body_page.get(page.page_number, []),
            has_endnotes,
            blocks_by_page.get(page.page_number, []),
            document.front_matter,
            page_numbering_policy,
            tables_by_page.get(page.page_number, []),
            lists_by_page.get(page.page_number, []),
            paragraphs_by_page.get(page.page_number, []),
            is_mathpix_import,
        )
        for page in sorted_pages
    ]

    endnotes_section = _render_endnotes_section(document.footnotes)
    if endnotes_section:
        sections.append(endnotes_section)

    markdown = "\n\n".join(sections)

    logger.info(
        "Built markdown for '{}': {} page(s), {} character(s)",
        document.source_pdf_path,
        len(sorted_pages),
        len(markdown),
    )
    return _normalize(markdown)


def _group_images_by_page(images: List[Image]) -> Dict[int, List[Image]]:
    grouped: Dict[int, List[Image]] = {}
    for image in images:
        grouped.setdefault(image.page_number, []).append(image)
    return grouped


def _render_front_matter_blocks(front_matter: Optional[FrontMatter]) -> List[str]:
    """Front-Matter Semantic Extraction: title (bold)/author(s)
    (italic)/affiliation(s) (plain), each its own markdown block - or
    no blocks at all when extraction found no confident title (the
    expected outcome for a PDF with no title page; see
    src/frontmatter/front_matter_extractor.py). Deliberately not a
    competing H1 heading - sits alongside, not instead of, whatever H1
    heading detection already produced."""
    if front_matter is None or not front_matter.title:
        return []
    blocks = [f"**{front_matter.title}**"]
    if front_matter.authors:
        blocks.append(f"*{', '.join(front_matter.authors)}*")
    if front_matter.affiliations:
        blocks.append("; ".join(front_matter.affiliations))
    return blocks


def _front_matter_source_texts(front_matter: Optional[FrontMatter]) -> Set[str]:
    """Every exact source line front_matter_extractor absorbed into
    title/author(s)/affiliation(s), for suppression from ordinary body
    rendering - the same exact-line-matching technique already used for
    footnote bodies and figure captions (see ``suppressed_body_lines``
    in both page-body renderers below)."""
    if front_matter is None:
        return set()
    return set(
        front_matter.title_source_texts
        + front_matter.author_source_texts
        + front_matter.affiliation_source_texts
    )


def _caption_source_texts(images: List[Image]) -> Set[str]:
    """Caption-duplication fix: every matched caption's exact source
    line (Figure.caption_source_text - src/images/image_extractor.py),
    for suppression from ordinary body rendering - the same
    exact-line-matching technique already used for footnote bodies
    (see ``suppressed_body_lines`` below). A Figure with no matched
    caption, or built before this field existed, contributes nothing."""
    return {
        image.figure.caption_source_text
        for image in images
        if image.figure is not None and image.figure.caption_source_text
    }


def _all_blocks_bold(blocks: List[TextBlock]) -> bool:
    """True when every block's non-superscript spans are all bold (016G).

    Falls back to TextBlock.is_bold for blocks with no span data.
    Returns False for an empty list or any block that cannot confirm bold.
    """
    if not blocks:
        return False
    for block in blocks:
        if block.spans:
            body_spans = [s for s in block.spans if not (s.font_flags & 1)]
            if not body_spans:
                continue  # all spans are superscripts — not decisive for body formatting
            if not all(s.font_flags & 16 for s in body_spans):
                return False
        elif block.is_bold is True:
            continue
        else:
            return False
    return True


def _all_blocks_italic(blocks: List[TextBlock]) -> bool:
    """True when every block's non-superscript spans are all italic (016G).

    No line-level italic fallback exists (TextBlock has no is_italic field),
    so blocks with no span data always return False.
    """
    if not blocks:
        return False
    for block in blocks:
        if block.spans:
            body_spans = [s for s in block.spans if not (s.font_flags & 1)]
            if not body_spans:
                continue
            if not all(s.font_flags & 2 for s in body_spans):
                return False
        else:
            return False  # no span data — cannot confirm italic
    return True


def _apply_inline_format(text: str, contributing_blocks: List[TextBlock]) -> str:
    """Wrap ``text`` in bold/italic markdown markers when contributing blocks
    are uniformly formatted (016G). Returns ``text`` unchanged when blocks
    have mixed or unknown formatting."""
    if not contributing_blocks:
        return text
    is_bold = _all_blocks_bold(contributing_blocks)
    is_italic = _all_blocks_italic(contributing_blocks)
    if is_bold and is_italic:
        return f"***{text}***"
    if is_bold:
        return f"**{text}**"
    if is_italic:
        return f"*{text}*"
    return text


def _group_blocks_by_page(blocks: List[TextBlock]) -> Dict[int, List[TextBlock]]:
    """Document.blocks (Phase H), grouped by page and order-sorted -
    the input _render_page_body_with_paragraphs needs for paragraph
    reconstruction (src/structure/paragraph_grouper.py). A page with no
    entries here (e.g. an OCR-recovered page - Structure Detection only
    reads a PDF's native text layer) signals "no bbox data available"
    to _render_page_body, which then falls back to the original
    one-line-per-block rendering for that page."""
    grouped: Dict[int, List[TextBlock]] = {}
    for block in blocks:
        grouped.setdefault(block.page_number, []).append(block)
    for page_blocks in grouped.values():
        page_blocks.sort(
            key=lambda block: block.corrected_order if block.corrected_order is not None else block.order
        )
    return grouped


def _group_notes_by_anchor_page(footnotes: List[Footnote]) -> Dict[int, List[Footnote]]:
    """Both footnotes and endnotes, grouped by the page their inline
    marker is on (not where their body is) - every page needs to know
    which notes to substitute markers for, regardless of note_type."""
    grouped: Dict[int, List[Footnote]] = {}
    for note in footnotes:
        grouped.setdefault(note.anchor_page_number, []).append(note)
    return grouped


def _group_notes_by_body_page(footnotes: List[Footnote]) -> Dict[int, List[Footnote]]:
    """Both footnotes and endnotes, grouped by the page their body's
    original source line physically appears on - for footnotes this is
    the same page as the anchor; for endnotes it's typically a
    different page (the Notes/Endnotes section). Used to suppress that
    raw line from also being rendered as plain body text once a proper
    footnote definition has taken its place."""
    grouped: Dict[int, List[Footnote]] = {}
    for note in footnotes:
        grouped.setdefault(note.body_page_number, []).append(note)
    return grouped


def _substitute_markers(text: str, notes: List[Footnote]) -> str:
    """Replace every note's footnote/endnote marker in ``text`` with its
    markdown reference (``[^label]``).

    ``text`` may be a single source line, or a paragraph built by
    joining several lines together (src/structure/paragraph_grouper.py)
    - notes are grouped by their own ``anchor_text`` (the specific
    source line each marker actually came from, since one joined
    paragraph can combine markers from several different lines, and a
    multi-paragraph run, src/markdown/markdown_builder.py's
    the line-by-line path, passes a note list that may include notes
    belonging to a different block). A note whose ``anchor_text`` does
    not appear in ``text`` at all is skipped entirely for this call - it belongs to a different
    paragraph from the same run, and must never touch this one.

    For a note whose anchor line *is* present, ``anchor_offset``
    (feature_005/bug_005) is applied relative to that line's location
    for an exact, position-based replacement. If the offset is missing
    or no longer valid, the fallback is a blind ``str.replace`` bounded
    to *just that line's own text*, not the whole (possibly multi-line)
    paragraph - because a plain-digit marker (bug_005's span-based
    detection signal) is a common substring that can occur elsewhere in
    a different line of the same paragraph by pure coincidence (a year,
    a page reference, an unrelated count), unlike the literal Unicode
    superscript glyph the original unbounded
    ``str.replace(marker, ..., 1)`` approach safely assumed was rare
    enough not to collide with anywhere in the text at all.

    All resolved replacements are applied in descending absolute-position
    order so a replacement's length change never invalidates a
    still-pending offset (every remaining one is strictly to its left).
    """
    by_anchor: Dict[str, List[Footnote]] = {}
    for note in notes:
        by_anchor.setdefault(note.anchor_text, []).append(note)

    resolved: List[Tuple[Optional[int], Footnote]] = []
    for anchor_text, group in by_anchor.items():
        anchor_position = text.find(anchor_text)
        if anchor_position == -1:
            continue  # this note's source line isn't in this paragraph at all - not ours
        for note in group:
            offset = (
                anchor_position + note.anchor_offset if note.anchor_offset is not None else None
            )
            resolved.append((offset, note))

    resolved.sort(key=lambda item: item[0] if item[0] is not None else -1, reverse=True)
    for absolute, note in resolved:
        label = f"[^{note.label}]"
        if (
            absolute is not None
            and 0 <= absolute <= len(text) - len(note.marker)
            and text[absolute : absolute + len(note.marker)] == note.marker
        ):
            text = text[:absolute] + label + text[absolute + len(note.marker) :]
            continue
        # Offset unknown/invalid, but the anchor line is confirmed
        # present (checked above) - bound the fallback replace to just
        # that line's own region, re-located fresh in case an earlier
        # replacement in this same call already shifted positions.
        anchor_position = text.find(note.anchor_text)
        if anchor_position == -1:
            continue  # already consumed by another replacement; nothing left to do
        region_end = anchor_position + len(note.anchor_text)
        region = text[anchor_position:region_end].replace(note.marker, label, 1)
        text = text[:anchor_position] + region + text[region_end:]
    return text


def _render_page(
    document: Document,
    page: Page,
    headings: List[Heading],
    page_images: List[Image],
    anchor_notes: List[Footnote],
    body_notes: List[Footnote],
    has_endnotes: bool,
    page_blocks: List[TextBlock],
    front_matter: Optional[FrontMatter],
    page_numbering_policy: Optional[PageNumberingPolicy] = None,
    page_tables: Optional[List[Table]] = None,
    page_lists: Optional[List[ListBlock]] = None,
    page_paragraphs: Optional[List[Paragraph]] = None,
    is_mathpix_import: bool = False,
) -> str:
    """Render one page's marker (when policy permits), front matter
    (page 1 only), headings, body text, footnotes, tables, lists, and
    images."""
    if page_tables is None:
        page_tables = []
    if page_lists is None:
        page_lists = []
    if page_paragraphs is None:
        page_paragraphs = []
    marker = _find_page_marker(headings, page, page_numbering_policy)
    page_front_matter = front_matter if page.page_number == 1 else None

    # FE-0-005: the document title is an H1 in document.headings (both
    # ingestion paths), but _render_front_matter_blocks() already renders
    # it — deliberately as a bold block that "sits alongside, not
    # instead of, whatever H1 heading detection already produced".
    # Excluding it here keeps the front-matter block the single owner of
    # the title's *rendering* while the H1 remains in the model for
    # structure and validation. Without this the semantic (Mathpix)
    # renderer, which projects headings by source_line, emits the title
    # a second time.
    _fm_title = page_front_matter.title if page_front_matter else None
    content_headings = sorted(
        (
            h for h in headings
            if h.page_number == page.page_number
            and not h.is_page_marker
            and not (_fm_title is not None and h.text == _fm_title)
        ),
        key=lambda h: h.document_order,
    )

    blocks: List[str] = []
    if marker is not None:
        blocks.append(_render_heading(marker))
    blocks.extend(_render_front_matter_blocks(page_front_matter))
    blocks.extend(
        _render_page_body(
            document,
            page,
            content_headings,
            anchor_notes,
            body_notes,
            has_endnotes,
            page_blocks,
            page_images,
            page_front_matter,
            page_tables,
            page_lists,
            page_paragraphs,
            is_mathpix_import,
        )
    )
    # _render_page_semantic() (the Mathpix-import path) already
    # interleaves tables/lists/images into the body at their true
    # source_line position — appending them again here would double-
    # render. The other two body paths never touch them, so they still
    # need this fixed after-body append.
    if not is_mathpix_import:
        blocks.extend(_render_tables(page_tables))
        blocks.extend(_render_lists(page_lists))
        # Images are placed by the body renderer when it has blocks to anchor
        # them to (Image.source_block_id). The line-by-line OCR fallback has
        # none, so it keeps the historical page-end slot.
        if not page_blocks:
            blocks.extend(_render_images(page_images))
    blocks.append(PAGE_BREAK_MARKER)

    return "\n\n".join(blocks)


def _find_page_marker(
    headings: List[Heading],
    page: Page,
    page_numbering_policy: Optional[PageNumberingPolicy] = None,
) -> Optional[Heading]:
    """Return the page marker for this page, or None if the active policy
    suppresses markers for it.

    When a policy is active and the marker is missing from ``headings``
    (e.g. because detect_headings() correctly chose not to create one
    under AUTO or DISABLED mode), the fallback synthesis path also
    respects the policy rather than silently reinstating the marker.

    When no policy is supplied (legacy callers / direct build_markdown()
    calls without detect_headings()) the original behaviour is preserved:
    synthesize a fallback marker for every page so output remains valid.
    """
    for heading in headings:
        if heading.page_number == page.page_number and heading.is_page_marker:
            return heading

    # No pre-existing marker in document.headings.
    if page_numbering_policy is not None:
        # Ask the policy whether a marker should exist here at all.
        marker_text = page_numbering_policy.resolve_marker_text(
            page.page_number, page.page_label or page.printed_label
        )
        if marker_text is None:
            return None  # policy suppresses this page — no fallback
        # Policy permits a marker but detect_headings() didn't create one.
        # Synthesize it so markdown output stays consistent.
        logger.warning(
            "No page marker found for page {} in document.headings; synthesizing one",
            page.page_number,
        )
        return Heading(
            level=HeadingLevel.H6,
            text=marker_text,
            page_number=page.page_number,
            document_order=0,
            is_page_marker=True,
        )

    # Legacy path (no policy): always synthesize so output remains valid.
    # feature_009/FEATURE_018: prefer the reviewed page_label, falling back
    # to the detected printed_label, then the physical page number.
    logger.warning(
        "No page marker found for page {} in document.headings; synthesizing one",
        page.page_number,
    )
    page_label = page.page_label or page.printed_label or str(page.page_number)
    return Heading(
        level=HeadingLevel.H6,
        text=page_label,
        page_number=page.page_number,
        document_order=0,
        is_page_marker=True,
    )


def _render_page_body(
    document: Document,
    page: Page,
    content_headings: List[Heading],
    anchor_notes: List[Footnote],
    body_notes: List[Footnote],
    has_endnotes: bool,
    page_blocks: List[TextBlock],
    page_images: List[Image],
    front_matter: Optional[FrontMatter],
    page_tables: Optional[List[Table]] = None,
    page_lists: Optional[List[ListBlock]] = None,
    page_paragraphs: Optional[List[Paragraph]] = None,
    is_mathpix_import: bool = False,
) -> List[str]:
    """Dispatch to one of three body-rendering strategies.

    FEATURE_020: Mathpix-imported documents get _render_page_semantic(),
    a projection of Document's own semantic objects sorted by
    source_line — the exact-text-match reinsertion the other two paths
    rely on can never succeed for Mathpix content (heading/list/table
    text is deliberately excluded from page.cleaned_text — see
    _assign_page_text() — to avoid double-rendering it).

    Otherwise: the geometry-grounded paragraph-reconstruction path when
    this page has TextBlock data (Phase H - born-digital pages), falling
    back to the original one-line-per-block rendering when it doesn't
    (e.g. OCR-recovered pages - Structure Detection never reads
    Docling/Surya output, only a PDF's native text layer, so those
    pages have no bbox signal to ground paragraph reconstruction in).
    See module docstring's "Design note on paragraph reconstruction".
    """
    if page_tables is None:
        page_tables = []
    if page_lists is None:
        page_lists = []
    if page_paragraphs is None:
        page_paragraphs = []
    if is_mathpix_import:
        return _render_page_semantic(
            content_headings, page_paragraphs, page_lists, page_tables, page_images, anchor_notes,
        )
    if page_blocks:
        return _render_page_body_with_paragraphs(
            document, page, content_headings, anchor_notes, page_blocks,
            page_paragraphs, page_images,
        )
    return _render_page_body_line_by_line(
        page, content_headings, anchor_notes, body_notes, has_endnotes, page_images, front_matter
    )


def _render_page_body_line_by_line(
    page: Page,
    content_headings: List[Heading],
    anchor_notes: List[Footnote],
    body_notes: List[Footnote],
    has_endnotes: bool,
    page_images: List[Image],
    front_matter: Optional[FrontMatter],
) -> List[str]:
    """Render a page's text, re-inserting detected headings at their
    original position by scanning the same text Heading Detection used,
    substituting any footnote/endnote markers in place (Phase K),
    suppressing each note body's own raw source line (replaced by a
    proper footnote definition - otherwise the note's text would appear
    twice), suppressing each matched figure caption's own raw source
    line (caption-duplication fix - otherwise the caption would render
    once here and a second time, italicized, attached to its image by
    _render_images()), suppressing each front-matter title/author/
    affiliation source line (Front-Matter Semantic Extraction - the
    same duplication risk, since _render_front_matter_blocks() already
    rendered them as their own distinct block), and, when endnotes
    exist, the literal "Notes"/"Endnotes" section-heading line (replaced
    by the "## Endnotes" section this module generates itself), and
    appending this page's footnote definitions (not endnote definitions
    - those are collected at the end of the document).

    content_headings must already be in document_order (== line
    encounter order), since each line is matched against the next
    pending heading in sequence. anchor_notes/body_notes' anchor_text/
    body_source_text values are matched the same way: against the exact
    line src/structure/structure_detector.py (Phase H) read for that
    note - the same exact-line-matching assumption
    src/headings/heading_detector.py's layout signal already relies on.

    This is the original, unmodified-since-Phase-K rendering path - one
    markdown block per raw PDF line, no paragraph joining - kept as the
    fallback for pages with no TextBlock data (see _render_page_body).
    """
    text = page.cleaned_text or page.raw_text
    pending = list(content_headings)
    notes_by_anchor_text: Dict[str, List[Footnote]] = {}
    for note in anchor_notes:
        notes_by_anchor_text.setdefault(note.anchor_text, []).append(note)
    # Continuation-line absorption fix: suppress every line
    # src/footnotes/footnote_detector.py absorbed into a note's body
    # (not just its first line), or the absorbed continuation text
    # would otherwise render twice - once as part of the note's proper
    # [^label]: definition, once again as an orphaned plain-text line.
    suppressed_body_lines = {note.body_source_text for note in body_notes}
    suppressed_body_lines.update(
        line for note in body_notes for line in note.body_continuation_source_texts
    )
    suppressed_body_lines.update(_caption_source_texts(page_images))
    suppressed_body_lines.update(_front_matter_source_texts(front_matter))

    blocks: List[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line in suppressed_body_lines:
            continue

        if has_endnotes and _NOTES_SECTION_HEADING_PATTERN.match(line):
            continue

        if pending and line == pending[0].text:
            blocks.append(_render_heading(pending.pop(0)))
            continue

        line = _substitute_markers(line, notes_by_anchor_text.get(line, []))
        blocks.append(line)

    for note in sorted(anchor_notes, key=lambda n: n.number):
        if note.note_type == NoteType.FOOTNOTE:
            blocks.append(f"[^{note.label}]: {note.body}")

    return blocks


# A missing source_line sorts last, not first — an object RAWRS couldn't
# place precisely (e.g. a table whose mmd block had no line info) should
# fall to the end of the page rather than jump to the front and disturb
# everything that *does* have a real position.
_UNPOSITIONED = float("inf")


def _render_page_semantic(
    content_headings: List[Heading],
    page_paragraphs: List[Paragraph],
    page_lists: List[ListBlock],
    page_tables: List[Table],
    page_images: List[Image],
    anchor_notes: List[Footnote],
) -> List[str]:
    """FEATURE_020 — render a Mathpix-imported page as a projection of
    Document's own semantic objects, not a reconstruction from scanned
    text. Replaces _render_page_body_line_by_line()'s exact-text-match
    reinsertion, which structurally cannot work for this path: heading/
    list/table text is deliberately excluded from page.cleaned_text (see
    _assign_page_text()) to avoid double-rendering, so there is never a
    line left in the text stream for a heading to match against.

    Every object type carrying its own source_line (see Heading/
    ListBlock/Table's docstrings) is merged into one true document-order
    sequence and rendered by its own type — the single mechanism that
    fixes both headings vanishing (no exact-text match ever succeeds)
    and lists/tables clustering after all body text instead of at their
    real position (the forensic audit's DEF-02 and DEF-05: always the
    same missing mechanism, not two separate bugs). Images have no
    source_line yet (Image was not in this feature's scope) and sort
    last, matching their existing page-end placement — not a regression,
    just not yet improved.

    Callouts are deliberately not rendered as a distinct block here —
    see Callout's own docstring ("rendering is a deliberately separate,
    later piece of work"): their anchoring Heading already renders
    correctly via the heading branch below.
    """
    items: List[Tuple[float, int, object]] = []
    for order, h in enumerate(content_headings):
        items.append((h.source_line if h.source_line is not None else _UNPOSITIONED, order, h))
    offset = len(items)
    for order, p in enumerate(page_paragraphs):
        items.append((p.source_line if p.source_line is not None else _UNPOSITIONED, offset + order, p))
    offset += len(page_paragraphs)
    for order, lst in enumerate(page_lists):
        items.append((lst.source_line if lst.source_line is not None else _UNPOSITIONED, offset + order, lst))
    offset += len(page_lists)
    for order, table in enumerate(page_tables):
        items.append((table.source_line if table.source_line is not None else _UNPOSITIONED, offset + order, table))
    offset += len(page_tables)
    for order, image in enumerate(page_images):
        items.append((_UNPOSITIONED, offset + order, image))

    items.sort(key=lambda item: (item[0], item[1]))

    blocks: List[str] = []
    for _, _, obj in items:
        if isinstance(obj, Heading):
            blocks.append(_render_heading(obj))
        elif isinstance(obj, Paragraph):
            blocks.append(obj.text)
        elif isinstance(obj, ListBlock):
            blocks.extend(_render_lists([obj]))
        elif isinstance(obj, Table):
            blocks.extend(_render_tables([obj]))
        elif isinstance(obj, Image):
            blocks.extend(_render_images([obj]))

    for note in sorted(anchor_notes, key=lambda n: n.number):
        if note.note_type == NoteType.FOOTNOTE:
            blocks.append(f"[^{note.label}]: {note.body}")

    return blocks


def _render_page_body_with_paragraphs(
    document: Document,
    page: Page,
    content_headings: List[Heading],
    anchor_notes: List[Footnote],
    page_blocks: List[TextBlock],
    page_paragraphs: List[Paragraph],
    page_images: Optional[List[Image]] = None,
) -> List[str]:
    """Project a page whose lines the model has already grouped.

    P2 turned this from a decision into a projection. It used to hold the
    whole "is this line prose?" cascade — six suppression rules, four of
    them keyed on text — accumulate the survivors into a run, and call
    ``group_into_paragraphs`` on each run at render time, discarding the
    Paragraphs immediately afterwards. All of that now lives in
    src/structure/paragraph_assembly.py and runs once, in Stage 5c.

    What is left is the projection's actual job: walk the page in order and
    emit what the model already decided is there. Three cases, in order:

      1. something already carries this line     -> emit nothing
      2. a heading was detected from this block   -> emit the heading
      3. a paragraph begins at this block         -> emit the paragraph
      4. otherwise                                -> already emitted; skip

    Case 1 keeps the precedence the renderer has always had — absorbed
    beats heading — without naming the six rules that decide it; the model
    hands over the resolved set. Case 4 is a line inside a paragraph that
    was emitted at that paragraph's first block.

    Headings are looked up by block, not taken from a queue. The old
    "next pending heading" queue stalled permanently whenever a heading's
    line was suppressed for some other reason, swallowing every later
    heading on the page — two such cascades on the benchmark corpus.

    The one remaining fallback is lockstep drift. Text lines are walked in
    parallel with ``page_blocks``, one block consumed per non-blank line; if
    a line and its block disagree, or the blocks run out, the line renders
    standalone exactly as it did before P2 rather than being attributed to
    the wrong block.
    """
    notes_by_anchor_text: Dict[str, List[Footnote]] = {}
    for note in anchor_notes:
        notes_by_anchor_text.setdefault(note.anchor_text, []).append(note)

    starts = paragraph_starts(page_paragraphs)
    blocks_by_id: Dict[str, TextBlock] = {b.block_id: b for b in page_blocks}
    # Images sit where the model says they sit (Image.source_block_id), not
    # after everything else. An image whose anchor is None precedes all body
    # text on its page — a real position, so it renders first.
    images_after, images_first = _images_by_anchor(page_images or [])
    absorbed = absorbed_block_ids(document, page.page_number, page_blocks)
    by_anchor = headings_by_anchor(document, page.page_number)
    # Headings the model could not anchor to a block keep the pre-P2
    # sequential text match, which is all that can place them.
    pending = [h for h in content_headings if h.source_block_id is None]

    # 016B: When any block has a corrected_order set, derive text lines from
    # the already-sorted page_blocks instead of cleaned_text. The corrected
    # block sequence IS the intended reading order; cleaned_text's original
    # line order is the very bug being fixed. In the corrected path each
    # text line maps 1:1 to its TextBlock (no lockstep drift possible).
    if any(b.corrected_order is not None for b in page_blocks):
        raw_text_lines = [b.text for b in page_blocks]
    else:
        raw_text_lines = (page.cleaned_text or page.raw_text).splitlines()

    blocks: List[str] = []
    block_cursor = 0
    emitted_images: Set[str] = set()

    def emit_images(bucket: List[Image]) -> None:
        for image in bucket:
            blocks.extend(_render_images([image]))
            emitted_images.add(image.image_id)

    emit_images(images_first)

    for raw_line in raw_text_lines:
        line = raw_line.strip()
        if not line:
            continue

        source_block = page_blocks[block_cursor] if block_cursor < len(page_blocks) else None
        block_cursor += 1

        if source_block is not None and source_block.text == line:
            anchored = images_after.get(source_block.block_id)
            if source_block.block_id in absorbed:
                if anchored:
                    emit_images(anchored)
                continue
            heading = by_anchor.get(source_block.block_id)
            if heading is None and pending and line == pending[0].text:
                heading = pending.pop(0)
            if heading is not None:
                blocks.append(_render_heading(heading))
            else:
                paragraph = starts.get(source_block.block_id)
                if paragraph is not None:
                    blocks.append(
                        _render_paragraph(paragraph, blocks_by_id, notes_by_anchor_text)
                    )
            # After whatever this block produced — a heading, a paragraph, or
            # nothing — so an image anchored to a heading's line still lands.
            if anchored:
                emit_images(anchored)
            continue

        blocks.append(_substitute_markers(line, notes_by_anchor_text.get(line, [])))

    # Everything the walk did not place: an unlinked image (the page-end slot
    # it has always had), and any image whose anchor block was never reached —
    # a suppressed line, a page whose lockstep ran out. PI-1 admits no third
    # state between materialized and diagnosed, so nothing may be left here.
    emit_images(
        [
            image
            for image in (page_images or [])
            if image.image_id not in emitted_images and not image.extraction_failed
        ]
    )

    for note in sorted(anchor_notes, key=lambda n: n.number):
        if note.note_type == NoteType.FOOTNOTE:
            blocks.append(f"[^{note.label}]: {note.body}")

    return blocks


def _images_by_anchor(page_images: List[Image]) -> Tuple[Dict[str, List[Image]], List[Image]]:
    """The page's placeable images, as (after-this-block, before-all-body).

    Only images the model positioned appear here. One the model said nothing
    about — no bbox to anchor from, or a Document that never ran Stage 5c —
    is deliberately absent, and the caller's closing sweep gives it the
    page-end slot it has always had. Within a bucket, ``document_order``
    decides.
    """
    after: Dict[str, List[Image]] = {}
    first: List[Image] = []
    for image in sorted(page_images, key=lambda i: i.document_order or 0):
        if image.extraction_failed or image.document_order is None:
            continue
        if image.source_block_id is None:
            first.append(image)
        else:
            after.setdefault(image.source_block_id, []).append(image)
    return after, first


def _render_paragraph(
    paragraph: Paragraph,
    blocks_by_id: Dict[str, TextBlock],
    notes_by_anchor_text: Dict[str, List[Footnote]],
) -> str:
    """One assembled paragraph as a markdown block.

    Formatting fidelity (016G) and footnote markers both need the
    paragraph's contributing lines, and ``source_block_ids`` names them, so
    neither has to be recovered from the joined text. Only the notes
    anchored to *this* paragraph's own lines are offered for substitution —
    ``_substitute_markers`` would filter the rest out by anchor text
    anyway, but not handing them over in the first place removes the chance
    of a coincidental substring match from a neighbouring paragraph.
    """
    contributing = [
        blocks_by_id[bid] for bid in paragraph.source_block_ids if bid in blocks_by_id
    ]
    notes = [note for block in contributing for note in notes_by_anchor_text.get(block.text, [])]
    return _substitute_markers(_apply_inline_format(paragraph.text, contributing), notes)


def _render_endnotes_section(footnotes: List[Footnote]) -> str:
    """A single "## Endnotes" section collecting every endnote
    definition, in number order, appended at the end of the document -
    endnotes are by definition detached from any one page, so unlike
    footnotes they have no natural per-page home."""
    endnotes = sorted(
        (note for note in footnotes if note.note_type == NoteType.ENDNOTE),
        key=lambda note: note.number,
    )
    if not endnotes:
        return ""

    blocks = ["## Endnotes"]
    blocks.extend(f"[^{note.label}]: {note.body}" for note in endnotes)
    return "\n\n".join(blocks)


def _render_tables(tables: List[Table]) -> List[str]:
    """Render auto-detected or manually-created tables as pipe tables.

    Each table emits a ``<!-- table-id: {table_id} -->`` anchor comment
    first.  The DOCX generator (src/docx/docx_generator.py) parses this
    comment to look up the full Table model from Document.tables so it
    can emit ``w:tblHeader``, merged cells, caption, and summary — all
    the accessibility attributes that a pipe-table string alone cannot
    carry.

    Each table optionally includes its caption as a *italicised* line
    above the pipe table (matching the figure caption convention), and
    its accessibility summary as an HTML comment below it (invisible to
    sighted readers, but preserved for downstream consumers and DOCX
    generation). Tables with no rows produce nothing.
    """
    blocks = []
    for table in tables:
        pipe = _render_pipe_table(table)
        if not pipe:
            continue
        blocks.append(f"<!-- table-id: {table.table_id} -->")
        if table.caption:
            blocks.append(f"*{table.caption}*")
        blocks.append(pipe)
        if table.summary:
            blocks.append(f"<!-- table-summary: {table.summary} -->")
    return blocks


def _render_images(images: List[Image]) -> List[str]:
    blocks: List[str] = []
    for image in images:
        if image.extraction_failed:
            logger.warning(
                "Skipping failed image extraction in markdown output: {}", image.image_id
            )
            continue

        # Phase F.4: alt text comes from Figure.alt_text (always populated
        # for a successfully-extracted image as of Phase F.3 - a
        # deterministic placeholder when no caption was matched, never
        # AI-generated) rather than the caption label, so markdown's
        # single alt slot carries the accessibility description, not
        # just the figure's print label.
        alt_text = image.figure.alt_text if image.figure and image.figure.alt_text else ""
        blocks.append(f"![{alt_text}]({image.file_path})")

        if image.figure and image.figure.caption:
            blocks.append(f"*{image.figure.caption}*")

    return blocks


def _render_heading(heading: Heading) -> str:
    return f"{'#' * heading.level.value} {heading.text}"


def _normalize(markdown: str) -> str:
    """Collapse runs of 3+ newlines to a single blank line and ensure a
    single trailing newline, so output is well-formed markdown."""
    collapsed = re.sub(r"\n{3,}", "\n\n", markdown)
    return collapsed.strip() + "\n"
