"""Structure Detection for RAWRS (Phase H: foundation only).

Populates Document.blocks with one TextBlock per text line on every
page, persisting the bbox/font-size/bold-flag layout signal that
src/headings/heading_detector.py already computes (via
src/structure/layout_signals.py, shared by both modules) for its own
heading-classification purposes, and that
src/images/image_extractor.py separately computes (image bbox, for
background-image filtering) and discards. This module is the first
place either signal is captured rather than thrown away. See
docs/ARCHITECTURE.md ("Structure Detection") for this stage's place in
the canonical pipeline, between OCR and Heading Detection.

Explicitly out of scope for this phase (see BENCHMARK_GAP_ANALYSIS.md
§4.2, BENCHMARK_RECONCILIATION_AND_PHASE1_PLAN.md §3, and the Phase H
architecture audit): reading-order reconstruction, multi-column
detection, table/equation/footnote detection, and cross-page paragraph
stitching. TextBlock.order records the sequence PyMuPDF emitted each
line in, scoped to its own page - never validated, corrected, related
across pages, or reordered here. Later phases read Document.blocks as
their starting point; nothing in the existing pipeline (text
extraction, OCR, heading detection, image extraction, markdown
generation, validation, DOCX generation) reads it yet, so this stage is
purely additive and changes no existing output.

Mirrors src/headings/heading_detector.py's own _build_layout_index
defensive pattern: if the source PDF cannot be opened, this never
raises - it logs a warning and returns the document with
document.blocks left empty, since this stage's output is optional
metadata, not something any other stage currently depends on. A page
with no extractable native text layer (e.g. a fully scanned page -
this stage reads the PDF's own text layer via PyMuPDF, the same source
heading_detector.py's layout signal uses, not Docling/Surya's
OCR-recovered Page.cleaned_text) simply contributes zero blocks; that
is expected, not an error.

XML Sanitization Architecture (Layer 1): TextBlock.text is sanitized
here, at the one point every TextBlock is constructed - this is the
single call site that protects src/images/image_extractor.py's figure
captions and src/footnotes/footnote_detector.py's footnote/endnote
text, both of which read TextBlock.text downstream without further
extraction. This is a genuinely separate fix from src/ocr/extractor.py's
equivalent (Page.cleaned_text): the root-cause audit found that this
module re-reads the PDF independently via page.get_text("dict") rather
than reusing Page.cleaned_text, so sanitizing one does not sanitize
the other - see the XML Sanitization Architecture Review
(docs/DECISIONS_LOG.md) for the full text-flow map this was derived
from.
"""

import re
from pathlib import Path
from typing import List, Optional, Tuple

import fitz  # PyMuPDF
from loguru import logger

from src.models.contracts import BoundingBox, Document, SanitizationEvent, Span, TextBlock
from src.structure.layout_signals import line_layout
from src.utils.text_sanitization import sanitize_xml_text

# feature_009: a printed page number (or roman-numeral front-matter
# label) is a short, isolated line consisting of nothing but digits or
# roman-numeral letters - confirmed against the benchmark corpus (see
# samples/regressions/feature_009_printed_page_number_preservation/
# notes_md/printed_page_number_audit.md SS2): "3", "81", "xlv", "I".
# Capped at 4 digits to stay well clear of years/citations/statistics
# that might otherwise land in a margin zone by coincidence.
_PRINTED_LABEL_PATTERN = re.compile(r"^[ivxlcdmIVXLCDM]+$|^\d{1,4}$")

# A printed page number conventionally sits in the page's top or bottom
# margin - confirmed corpus-wide at roughly the top/bottom 12% of page
# height (e.g. Calderhead/Fullan&Hargreaves: y0=21.0 on an ~792pt-tall
# page). Position varies between left/right/center within the same
# document (recto/verso typesetting) and even top vs. bottom (a
# chapter-opening page often prints its number at the bottom while
# every following page prints it at the top) - so both margins and any
# horizontal position must be checked, not one fixed corner.
_MARGIN_ZONE_RATIO = 0.12


def detect_structure(document: Document) -> Document:
    """Extract and persist per-page layout structure into document.blocks.

    Also populates each Page's printed_label (feature_009) as a side
    effect of the same per-page scan - this stage's docstring's
    historical "purely additive metadata, nothing depends on it yet"
    claim no longer holds for that one field: src/headings/heading_detector.py
    and src/markdown/markdown_builder.py's H6 page-marker generation
    now read it (falling back to page_number when it's None, so a
    document processed before this stage ran, or a page with no
    confident candidate, behaves exactly as before).

    Args:
        document: A Document with source_pdf_path pointing to a
            readable PDF. Independently re-opens the PDF for layout
            data, following the same pattern already used by
            src/headings/heading_detector.py and
            src/images/image_extractor.py - the Page model is
            unchanged by this stage.

    Returns:
        The same Document instance with document.blocks populated: one
        TextBlock per non-blank text line found on each page, in the
        order PyMuPDF emitted them (see TextBlock.order). Never raises -
        if the PDF cannot be opened at all, logs a warning and returns
        the document with document.blocks left empty.
    """
    logger.info("Detecting structure for '{}'", document.source_pdf_path)

    pdf_path = Path(document.source_pdf_path)
    if not pdf_path.is_file():
        logger.warning("Source PDF not found for structure detection: {}", pdf_path)
        return document

    try:
        pdf_document = fitz.open(pdf_path)
    except Exception as exc:  # PyMuPDF raises various error types on bad input
        logger.warning("Could not open PDF for structure detection '{}': {}", pdf_path, exc)
        return document

    blocks: List[TextBlock] = []
    try:
        for page in document.pages:
            page_index = page.page_number - 1
            if page_index < 0 or page_index >= pdf_document.page_count:
                continue  # Document.pages has no matching PDF page; nothing to extract
            pdf_page = pdf_document[page_index]
            page_blocks, page_events, printed_label = _extract_page_blocks(
                pdf_page, page.page_number
            )
            blocks.extend(page_blocks)
            document.sanitization_events.extend(page_events)
            page.printed_label = printed_label
            page.width_pt = pdf_page.rect.width
    finally:
        pdf_document.close()

    document.blocks = blocks

    logger.info(
        "Structure detection complete for '{}': {} block(s) across {} page(s)",
        document.source_pdf_path,
        len(blocks),
        len(document.pages),
    )
    return document


def _extract_page_blocks(
    page: fitz.Page, page_number: int
) -> Tuple[List[TextBlock], List[SanitizationEvent], Optional[str]]:
    """Extract one TextBlock per non-blank line on a single page, in
    the order PyMuPDF emitted them (block, then line, within that
    block) - page-scoped, not a document-wide or corrected order.

    Also detects this page's printed page-number label (feature_009),
    from the same already-parsed page_dict - no second PDF read.

    Returns:
        (text_blocks, sanitization_events, printed_label) - the second
        element (XML Sanitization Architecture, Layer 1) records any
        XML-illegal character removed from a line's text before it
        became a TextBlock; see module docstring for why this is the
        one call site that protects figure captions and
        footnote/endnote text. ``printed_label`` is None whenever no
        confident candidate was found - see _detect_printed_label().
    """
    page_dict = page.get_text("dict")
    text_blocks: List[TextBlock] = []
    events: List[SanitizationEvent] = []
    order = 0

    for source_block_index, block in enumerate(page_dict.get("blocks", [])):
        for line_dict in block.get("lines", []):
            parsed = line_layout(line_dict)
            if parsed is None:
                continue
            text, font_size, is_bold, _char_count = parsed
            x0, y0, x1, y1 = line_dict["bbox"]

            clean_text, removed = sanitize_xml_text(text)
            if removed:
                events.append(
                    SanitizationEvent(
                        page_number=page_number, field="text_block", removed_codepoints=removed
                    )
                )

            text_blocks.append(
                TextBlock(
                    page_number=page_number,
                    text=clean_text,
                    bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
                    order=order,
                    font_size=font_size,
                    is_bold=is_bold,
                    source_block_index=source_block_index,
                    spans=_extract_spans(line_dict),
                )
            )
            order += 1

    printed_label = _detect_printed_label(page_dict, page.rect.height)
    return text_blocks, events, printed_label


def _detect_printed_label(page_dict: dict, page_height: float) -> Optional[str]:
    """feature_009: the page number actually printed on this page, read
    independently of TextBlock/order above (this only needs each raw
    line's text and y-position, not the sanitized/layout-parsed form).

    A candidate is a short, isolated, purely-numeric-or-roman-numeral
    line in the top or bottom _MARGIN_ZONE_RATIO of the page (any
    horizontal position - see module-level comment on
    _MARGIN_ZONE_RATIO for why both margins and every horizontal
    position must be checked). Per-page only - no per-document offset
    is computed or assumed (a multi-chapter excerpt can splice
    non-contiguous original page ranges together, where a single global
    offset would be wrong for part of the document - confirmed against
    FolkPedagogy_Bruner in the audit). Returns None - falling back to
    the page's physical page_number downstream - whenever zero or more
    than one candidate is found, rather than guessing between ambiguous
    candidates (confirmed necessary against sockett_profession.pdf,
    which has pages with two conflicting candidates).
    """
    candidates: List[str] = []
    for block in page_dict.get("blocks", []):
        for line_dict in block.get("lines", []):
            spans = line_dict.get("spans", [])
            if not spans:
                continue
            text = "".join(span.get("text", "") for span in spans).strip()
            if not text or len(text) > 6 or not _PRINTED_LABEL_PATTERN.match(text):
                continue
            y0, y1 = line_dict["bbox"][1], line_dict["bbox"][3]
            in_margin = y0 < page_height * _MARGIN_ZONE_RATIO or y1 > page_height * (
                1 - _MARGIN_ZONE_RATIO
            )
            if in_margin:
                candidates.append(text)

    if len(candidates) == 1:
        return candidates[0]
    return None


def _extract_spans(line_dict: dict) -> List[Span]:
    """Build this line's Span list from PyMuPDF's own span dicts (feature_005).

    A faithful, additive record alongside TextBlock's existing
    line-level (font_size, is_bold) summary - see Span's own docstring
    and docs/DECISIONS_LOG.md Part 8 for why this exists and why it does
    not replace either field. Span text is sanitized the same way line
    text is (XML Sanitization Architecture, Layer 1), but a removed
    character is not re-recorded as a second SanitizationEvent here: a
    span's text is always a sub-range of its parent line's text, so the
    line-level event already discloses the same underlying character -
    the same "don't double-record" reasoning already applied to
    src/headings/heading_detector.py's own independent layout-index
    read of the same lines.
    """
    spans: List[Span] = []
    for span in line_dict.get("spans", []):
        text = span.get("text", "")
        if not text:
            continue
        clean_text, _ = sanitize_xml_text(text)
        x0, y0, x1, y1 = span["bbox"]
        spans.append(
            Span(
                text=clean_text,
                font_name=span.get("font", ""),
                font_size=span["size"],
                font_flags=span.get("flags", 0),
                baseline_y=span["origin"][1],
                bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
            )
        )
    return spans
