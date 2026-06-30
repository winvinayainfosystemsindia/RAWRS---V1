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
for heading order. Image has no equivalent ordering field (see prior
architectural review), so images are placed after all of a page's
headings and body text, in document.images list order - the closest
approximation available without adding a new field to the Image model.

Design note on footnotes/endnotes (Phase K): standard Pandoc-style
markdown footnote syntax is ``[^label]`` inline plus a matching
``[^label]: body`` definition. The visible printed number RAWRS
detected (Footnote.number) is not by itself a safe markdown label,
because footnote numbering conventionally resets per page - two
different footnotes from two different pages can share the same
printed "1". _footnote_label() builds a page-qualified label
(``p{page}-{number}``) that is unique across the whole document while
keeping the original printed number visible inside it, so the
human-meaningful number survives even though the underlying label
isn't itself the bare number. Footnote definitions render immediately
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
footnote body's or a figure caption's source line already is (see
``suppressed_body_lines`` below) - omitting that step would render
them a second time, the same duplication class already fixed twice
elsewhere in this module.

Design note on paragraph reconstruction (see
samples/regressions/bug_001_brinkman_word_splitting/notes_md/ for the
audit and design review this implements): when document.blocks
(src/structure/structure_detector.py, Phase H) has entries for a page,
_render_page_body_with_paragraphs reconstructs paragraphs from them via
src/structure/paragraph_grouper.py instead of rendering one markdown
block per raw PDF line. Heading/footnote detection still run their
existing exact-line scan over page.cleaned_text first, unchanged; only
the runs of plain body lines between those events are paragraph-joined.
Pages with no blocks for them (e.g. OCR-recovered pages - Structure
Detection only reads a PDF's native text layer, never Docling/Surya
output, see structure_detector.py) fall back to
_render_page_body_line_by_line, the original one-line-per-block
behavior, unchanged - paragraph reconstruction is additive, not a
replacement of that path, since there is no bbox data to ground it for
those pages.

Design note on formatting fidelity (016G): when flush_run() produces a
paragraph from a run of TextBlocks, it checks whether every contributing
block's spans (TextBlock.spans, feature_005) are uniformly bold and/or
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
    NoteType,
    Page,
    Table,
    TextBlock,
)
from src.structure.paragraph_grouper import group_into_paragraphs

# Public so downstream stages (e.g. src/docx/docx_generator.py) that parse
# this module's markdown output can match the exact same token rather than
# duplicating it as an independent magic string.
PAGE_BREAK_MARKER = "<!-- pagebreak -->"

# Matches the literal section-heading line src/footnotes/footnote_detector.py
# (Phase K) used to find the start of an endnotes section - same rule,
# applied here only to suppress that one source line once this module
# has already generated its own "## Endnotes" section to replace it.
_NOTES_SECTION_HEADING_PATTERN = re.compile(r"^(notes|endnotes)$", re.IGNORECASE)


def _group_tables_by_page(tables: List[Table]) -> Dict[int, List[Table]]:
    grouped: Dict[int, List[Table]] = {}
    for table in tables:
        grouped.setdefault(table.page_number, []).append(table)
    return grouped


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
    has_endnotes = any(note.note_type == NoteType.ENDNOTE for note in document.footnotes)
    sorted_pages = sorted(document.pages, key=lambda page: page.page_number)

    sections = [
        _render_page(
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


def _footnote_label(note: Footnote) -> str:
    """A markdown footnote label unique across the whole document (see
    module docstring) - the printed number stays visible inside it."""
    return f"p{note.body_page_number}-{note.number}"


def _substitute_markers(text: str, notes: List[Footnote]) -> str:
    """Replace every note's footnote/endnote marker in ``text`` with its
    markdown reference (``[^label]``).

    ``text`` may be a single source line, or a paragraph built by
    joining several lines together (src/structure/paragraph_grouper.py)
    - notes are grouped by their own ``anchor_text`` (the specific
    source line each marker actually came from, since one joined
    paragraph can combine markers from several different lines, and a
    multi-paragraph run, src/markdown/markdown_builder.py's
    ``flush_run()``, passes the *same* full note list to *every*
    resulting paragraph even though each note belongs to exactly one of
    them). A note whose ``anchor_text`` does not appear in ``text`` at
    all is skipped entirely for this call - it belongs to a different
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
        label = f"[^{_footnote_label(note)}]"
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
) -> str:
    """Render one page's marker (when policy permits), front matter
    (page 1 only), headings, body text, footnotes, tables, and images."""
    if page_tables is None:
        page_tables = []
    marker = _find_page_marker(headings, page, page_numbering_policy)
    content_headings = sorted(
        (h for h in headings if h.page_number == page.page_number and not h.is_page_marker),
        key=lambda h: h.document_order,
    )
    page_front_matter = front_matter if page.page_number == 1 else None

    blocks: List[str] = []
    if marker is not None:
        blocks.append(_render_heading(marker))
    blocks.extend(_render_front_matter_blocks(page_front_matter))
    blocks.extend(
        _render_page_body(
            page,
            content_headings,
            anchor_notes,
            body_notes,
            has_endnotes,
            page_blocks,
            page_images,
            page_front_matter,
            page_tables,
        )
    )
    blocks.extend(_render_tables(page_tables))
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
            page.page_number, page.printed_label
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
    # feature_009: same printed-label preference as heading_detector.py.
    logger.warning(
        "No page marker found for page {} in document.headings; synthesizing one",
        page.page_number,
    )
    page_label = page.printed_label or str(page.page_number)
    return Heading(
        level=HeadingLevel.H6,
        text=page_label,
        page_number=page.page_number,
        document_order=0,
        is_page_marker=True,
    )


def _render_page_body(
    page: Page,
    content_headings: List[Heading],
    anchor_notes: List[Footnote],
    body_notes: List[Footnote],
    has_endnotes: bool,
    page_blocks: List[TextBlock],
    page_images: List[Image],
    front_matter: Optional[FrontMatter],
    page_tables: Optional[List[Table]] = None,
) -> List[str]:
    """Dispatch to the geometry-grounded paragraph-reconstruction path
    when this page has TextBlock data (Phase H - born-digital pages),
    falling back to the original one-line-per-block rendering when it
    doesn't (e.g. OCR-recovered pages - Structure Detection never reads
    Docling/Surya output, only a PDF's native text layer, so those
    pages have no bbox signal to ground paragraph reconstruction in).
    See module docstring's "Design note on paragraph reconstruction".
    """
    if page_tables is None:
        page_tables = []
    if page_blocks:
        return _render_page_body_with_paragraphs(
            page,
            content_headings,
            anchor_notes,
            body_notes,
            has_endnotes,
            page_blocks,
            page_images,
            front_matter,
            page_tables,
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
            blocks.append(f"[^{_footnote_label(note)}]: {note.body}")

    return blocks


def _render_page_body_with_paragraphs(
    page: Page,
    content_headings: List[Heading],
    anchor_notes: List[Footnote],
    body_notes: List[Footnote],
    has_endnotes: bool,
    page_blocks: List[TextBlock],
    page_images: List[Image],
    front_matter: Optional[FrontMatter],
    page_tables: Optional[List[Table]] = None,
) -> List[str]:
    """Geometry-grounded counterpart to _render_page_body_line_by_line:
    same heading/footnote/caption exact-line scan and suppression
    (unchanged - see that function's docstring for the matching
    assumption), but consecutive plain-body lines are accumulated into
    a run and paragraph-joined (src/structure/paragraph_grouper.py)
    instead of each becoming its own markdown block.

    Matching a scanned text line back to its TextBlock is purely
    positional (page_blocks is order-sorted; one non-blank text line
    consumes exactly one TextBlock, in lockstep, regardless of whether
    that line turns out to be a heading/suppressed/body line) - not
    text-equality lookup, so duplicate-text lines can never be
    mismatched. A defensive text-equality check still guards each
    consumption; on the rare mismatch (positional drift between
    page.cleaned_text and document.blocks for this page), the run is
    flushed and that line renders standalone rather than risk grouping
    it under the wrong bbox.
    """
    if page_tables is None:
        page_tables = []
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
    # Table suppression: TextBlock indices whose bbox overlaps a detected
    # table's bbox are skipped in the rendering loop below — their text
    # already appears in the pipe-table rendering added by _render_tables().
    table_suppressed_indices = _table_suppressed_blocks(page_tables, page_blocks)

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
    run: List[TextBlock] = []
    run_notes: List[Footnote] = []
    block_cursor = 0

    def flush_run() -> None:
        nonlocal run, run_notes
        if not run:
            return
        blocks_by_order: Dict[int, TextBlock] = {b.order: b for b in run}
        for paragraph in group_into_paragraphs(run):
            contributing = [blocks_by_order[o] for o in paragraph.source_orders if o in blocks_by_order]
            formatted = _apply_inline_format(paragraph.text, contributing)
            blocks.append(_substitute_markers(formatted, run_notes))
        run = []
        run_notes = []

    for raw_line in raw_text_lines:
        line = raw_line.strip()
        if not line:
            continue

        source_block = page_blocks[block_cursor] if block_cursor < len(page_blocks) else None
        current_cursor = block_cursor
        block_cursor += 1

        if current_cursor in table_suppressed_indices:
            flush_run()
            continue

        if line in suppressed_body_lines:
            flush_run()
            continue

        if has_endnotes and _NOTES_SECTION_HEADING_PATTERN.match(line):
            flush_run()
            continue

        if pending and line == pending[0].text:
            flush_run()
            blocks.append(_render_heading(pending.pop(0)))
            continue

        line_notes = notes_by_anchor_text.get(line, [])
        if source_block is not None and source_block.text == line:
            run.append(source_block)
            run_notes.extend(line_notes)
        else:
            flush_run()
            blocks.append(_substitute_markers(line, line_notes))

    flush_run()

    for note in sorted(anchor_notes, key=lambda n: n.number):
        if note.note_type == NoteType.FOOTNOTE:
            blocks.append(f"[^{_footnote_label(note)}]: {note.body}")

    return blocks


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
    blocks.extend(f"[^{_footnote_label(note)}]: {note.body}" for note in endnotes)
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


def _table_suppressed_blocks(page_tables: List[Table], page_blocks: List[TextBlock]) -> Set[int]:
    """Indices into page_blocks whose bbox overlaps with any table bbox.

    When PyMuPDF detects a table, its bbox covers the table's page area.
    Any TextBlock that falls inside (or overlaps) that area originally
    came from the table cells, so it should be suppressed from body-text
    rendering — otherwise cell text would appear twice: once as raw body
    lines, once as the pipe-table rendering below.

    Only tables with a non-None bbox participate (manually-created tables
    have no source bbox to check against).

    Returns a set of indices (into page_blocks) to skip.
    """
    if not page_tables:
        return set()
    suppressed: Set[int] = set()
    for table in page_tables:
        if table.bbox is None:
            continue
        tbx = table.bbox
        for idx, block in enumerate(page_blocks):
            b = block.bbox
            if b is None:
                continue
            # Overlap check: rectangles intersect when neither is completely
            # outside the other in either axis.
            if b.x0 < tbx.x1 and b.x1 > tbx.x0 and b.y0 < tbx.y1 and b.y1 > tbx.y0:
                suppressed.add(idx)
    return suppressed


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
