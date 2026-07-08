"""Surya OCR fallback integration for RAWRS (Phase D.2).

Runs Surya against pages where src/ocr/docling_engine.py (Phase D.1)
already ran Docling but left the page empty - either because Docling
failed to convert it, or because Docling converted it but recovered no
text. docling_engine.py deliberately collapses both outcomes into the
same observable state (extraction_method=DOCLING, text fields empty),
so that single state is exactly this module's trigger condition; no
separate "did Docling raise vs. return nothing" signal is needed or
tracked.

Per docs/OCR_RULES.md ("Page Classification and Routing"), Surya is the
fallback engine, never primary: DIRECT_TEXT pages and pages Docling
already recovered text for are never touched here. If Surya also fails
or recovers nothing, that page is left exactly as Docling left it
(still empty) but with extraction_method updated to SURYA to record
that the fallback was attempted - never silently substituted with
anything else, matching docling_engine.py's own failure-handling
pattern.

Confidence: Surya-recovered text is OCRConfidence.LOW, one rung below
Docling's MEDIUM. Both are OCR-derived and per docs/OCR_RULES.md never
reach HIGH (reserved for direct extraction's certainty), but text that
only a fallback engine could recover - after the primary engine already
failed on the same page - warrants the extra scrutiny OCR_RULES.md
calls for ("Low-confidence regions should be flagged for validation
review").

All Surya-specific configuration (predictor construction, rasterization
DPI) lives in src/ocr/surya_config.py - nothing here builds a predictor
or rasterizes a page directly, so there is exactly one place to change
Surya's settings.
"""

from pathlib import Path
from time import perf_counter
from typing import List, Optional

from bs4 import BeautifulSoup
from loguru import logger

from src.models.contracts import (
    Document,
    ExtractionMethod,
    OCRConfidence,
    Page,
    RoutingDecision,
    SanitizationEvent,
)
from src.ocr.docling_engine import OCRTimingMetrics
from src.ocr.extractor import normalize_whitespace
from src.ocr.surya_config import build_recognition_predictor, render_page_to_image
from src.utils.text_sanitization import sanitize_xml_text


class SuryaOCRError(Exception):
    """Raised when the source PDF cannot be opened for OCR at all, or
    Surya's predictor cannot be initialized."""


def run_surya_ocr(document: Document, metrics: Optional[OCRTimingMetrics] = None) -> Document:
    """Run Surya OCR as a fallback for every Docling-attempted page left empty.

    Args:
        document: A Document that has already been through
            src/ocr/docling_engine.py (Phase D.1). Only pages with
            extraction_method == ExtractionMethod.DOCLING and empty
            cleaned_text are processed - every other page (DIRECT_TEXT,
            still OCR_PENDING, Docling-succeeded, or already
            SURYA-processed) is left completely untouched.
        metrics: Optional OCRTimingMetrics to record per-page durations
            into. Pass a dedicated instance (not the one passed to
            run_docling_ocr) - both record by page_number, and sharing
            one instance across both engines would let a Surya timing
            overwrite Docling's measurement for the same page.

    Returns:
        The same Document instance. For each previously-Docling-empty page:
        - Surya recovers non-empty text: raw_text/cleaned_text
          populated, ocr_confidence=LOW (see module docstring),
          extraction_method=SURYA, routing_decision=ROUTE_TO_SURYA.
        - Surya recovers nothing, or the page fails to convert: text
          fields stay empty, ocr_confidence stays None,
          extraction_method is still set to SURYA (it WAS attempted),
          so this is distinguishable from a page never tried at all.
        page_type is never changed - OCR_REQUIRED remains an accurate
        historical classification regardless of the fallback's outcome.

        If there are no candidate pages at all, returns immediately
        without ever constructing a Surya predictor (zero added cost
        for documents Docling fully resolved on its own).

    Raises:
        FileNotFoundError: If document.source_pdf_path does not exist
            and there is at least one candidate page to process.
        SuryaOCRError: If the PDF exists but Surya's predictor cannot
            be initialized.
    """
    if metrics is None:
        metrics = OCRTimingMetrics()

    candidate_pages = [
        page
        for page in document.pages
        if page.extraction_method == ExtractionMethod.DOCLING and not page.cleaned_text.strip()
    ]
    if not candidate_pages:
        logger.info(
            "No Docling-empty pages pending for '{}'; skipping Surya fallback entirely",
            document.source_pdf_path,
        )
        return document

    pdf_path = Path(document.source_pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Source PDF not found: {pdf_path}")

    logger.info(
        "Running Surya OCR fallback for '{}': {} page(s) pending",
        pdf_path,
        len(candidate_pages),
    )

    try:
        predictor = build_recognition_predictor()
    except Exception as exc:
        raise SuryaOCRError(f"Failed to initialize Surya for '{pdf_path}': {exc}") from exc

    for page in candidate_pages:
        events = _run_single_page(predictor, pdf_path, page, metrics)
        document.sanitization_events.extend(events)

    logger.info(
        "Surya OCR fallback complete for '{}': {} page(s), avg {:.2f}s/page, total {:.2f}s",
        document.source_pdf_path,
        metrics.page_count,
        metrics.average_seconds,
        metrics.total_seconds,
    )
    return document


def _run_single_page(
    predictor, pdf_path: Path, page: Page, metrics: OCRTimingMetrics
) -> List[SanitizationEvent]:
    """Convert one page via Surya and update it in place.

    Failures are caught and logged rather than raised, so one bad page
    does not abort the fallback for the rest of the document - matches
    the same pattern src/ocr/docling_engine.py uses.

    Returns:
        A list (possibly empty) of SanitizationEvent for any
        XML-illegal character removed from this page's recovered text
        (XML Sanitization Architecture, Layer 1) - see
        docling_engine.py's identical pattern for why this is returned
        rather than appended directly to a Document.
    """
    page_number = page.page_number
    start = perf_counter()

    try:
        image = render_page_to_image(pdf_path, page_number)
        [result] = predictor([image], full_page=True)
        text = page_result_to_text(result)
    except Exception as exc:
        duration = perf_counter() - start
        metrics.record(page_number, duration)
        logger.warning(
            "Page {} → Surya OCR failed after {:.2f}s: {}", page_number, duration, exc
        )
        page.extraction_method = ExtractionMethod.SURYA
        page.routing_decision = RoutingDecision.ROUTE_TO_SURYA
        return []

    duration = perf_counter() - start
    metrics.record(page_number, duration)

    page.extraction_method = ExtractionMethod.SURYA
    page.routing_decision = RoutingDecision.ROUTE_TO_SURYA

    stripped = text.strip()
    if stripped:
        page.raw_text = text
        cleaned, removed = sanitize_xml_text(normalize_whitespace(text))
        page.cleaned_text = cleaned
        page.ocr_confidence = OCRConfidence.LOW
        logger.info(
            "Page {} → Surya OCR in {:.2f}s ({} chars recovered)",
            page_number,
            duration,
            len(stripped),
        )
        if removed:
            return [
                SanitizationEvent(
                    page_number=page_number, field="page_text", removed_codepoints=removed
                )
            ]
    else:
        logger.info(
            "Page {} → Surya OCR in {:.2f}s (no text recovered)", page_number, duration
        )

    return []


def page_result_to_text(result) -> str:
    """Flatten a Surya PageOCRResult into reading-order plain text.

    Each non-skipped block's html is per-block markup (e.g. <p>...</p>)
    - strip tags via BeautifulSoup rather than hand-rolling a parser.
    Skipped blocks (figures, etc. - see Surya's SKIP_CANON_LABELS) carry
    no text and are omitted, not just blank.

    Public (not module-private) because src/ocr/targeted.py's region-
    scoped OCR (FEATURE_019) reuses it — PageOCRResult has the exact same
    shape (.blocks[].html/.skipped/.reading_order) whether the predictor
    was called with full_page=True (this module's whole-page path) or
    full_page=False (a small, already-isolated region).
    """
    ordered_blocks = sorted(result.blocks, key=lambda block: block.reading_order)
    paragraphs = []
    for block in ordered_blocks:
        if block.skipped or not block.html:
            continue
        text = BeautifulSoup(block.html, "html.parser").get_text().strip()
        if text:
            paragraphs.append(text)
    return "\n\n".join(paragraphs)
