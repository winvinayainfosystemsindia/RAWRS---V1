"""Docling OCR integration for RAWRS (Phase D.1).

Runs Docling against pages classified OCR_REQUIRED by
src/ocr/router.py (Phase D.0), and only those pages - DIRECT_TEXT
pages are never touched here, preserving the existing direct-extraction
path exactly as-is. If Docling fails or recovers nothing for a page,
that page is left as-is here (still empty, extraction_method set to
DOCLING to record the attempt) - never silently substituted with
anything else. src/ocr/surya_engine.py (Phase D.2) is the module
responsible for retrying exactly that state with a fallback engine;
this module has no knowledge of Surya and is unchanged by its
existence.

All Docling-specific configuration (pipeline options, environment
workarounds) lives in src/ocr/docling_config.py - nothing here
constructs pipeline options directly, so there is exactly one place to
change Docling's settings.

Performance: Docling's full-page OCR pipeline (required - see
docling_config.py) is CPU-bound and slow. Measured against this
project's own scanned benchmark PDF: roughly 1-3 minutes per page (see
BENCHMARK_RECONCILIATION_AND_PHASE1_PLAN.md Phase D.1 for the measured
figures). This module measures and exposes per-page timing via
OCRTimingMetrics so that cost is visible, not hidden inside a
black-box call.
"""

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Dict, List, Optional

from loguru import logger

from src.models.contracts import (
    Document,
    ExtractionMethod,
    OCRConfidence,
    Page,
    RoutingDecision,
    SanitizationEvent,
)
from src.ocr.docling_config import build_converter
from src.ocr.extractor import normalize_whitespace
from src.utils.text_sanitization import sanitize_xml_text


class DoclingOCRError(Exception):
    """Raised when the source PDF cannot be opened for OCR at all."""


@dataclass
class OCRTimingMetrics:
    """Per-page Docling OCR timing, collected by run_docling_ocr().

    Not a Pydantic model - this is observability/performance data, not
    part of the canonical Document/Page contract in src/models/.
    """

    per_page_seconds: Dict[int, float] = field(default_factory=dict)

    def record(self, page_number: int, seconds: float) -> None:
        self.per_page_seconds[page_number] = seconds

    @property
    def page_count(self) -> int:
        return len(self.per_page_seconds)

    @property
    def total_seconds(self) -> float:
        return sum(self.per_page_seconds.values())

    @property
    def average_seconds(self) -> float:
        if not self.per_page_seconds:
            return 0.0
        return self.total_seconds / self.page_count


def run_docling_ocr(document: Document, metrics: Optional[OCRTimingMetrics] = None) -> Document:
    """Run Docling OCR on every OCR_REQUIRED page not yet processed.

    Args:
        document: A Document that has already been through
            src/ocr/extractor.py (direct extraction) and
            src/ocr/router.py (routing). Only pages with
            extraction_method == ExtractionMethod.OCR_PENDING are
            processed - every other page (DIRECT_TEXT, or already
            DOCLING-processed) is left completely untouched.
        metrics: Optional OCRTimingMetrics to record per-page durations
            into. Pass the same instance across calls to accumulate
            metrics across documents; omit to discard them (timing is
            still logged either way).

    Returns:
        The same Document instance. For each previously-OCR_PENDING page:
        - Docling recovers non-empty text: raw_text/cleaned_text
          populated, ocr_confidence=MEDIUM (OCR-derived, inherently
          less certain than direct extraction's HIGH),
          extraction_method=DOCLING, routing_decision=ROUTE_TO_DOCLING.
        - Docling recovers nothing, or the page fails to convert: text
          fields stay empty, ocr_confidence stays None,
          extraction_method is still set to DOCLING (it WAS attempted),
          so this is distinguishable from a page never tried at all.
        page_type is never changed - OCR_REQUIRED remains an accurate
        historical classification regardless of OCR's outcome.

        If there are no pending pages at all, returns immediately
        without ever constructing a Docling converter (zero added cost
        for fully born-digital documents).

    Raises:
        FileNotFoundError: If document.source_pdf_path does not exist
            and there is at least one pending page to process.
        DoclingOCRError: If the PDF exists but Docling cannot be
            initialized, or cannot open it at all.
    """
    if metrics is None:
        metrics = OCRTimingMetrics()

    pending_pages = [
        page for page in document.pages if page.extraction_method == ExtractionMethod.OCR_PENDING
    ]
    if not pending_pages:
        logger.info(
            "No OCR_REQUIRED pages pending for '{}'; skipping Docling entirely",
            document.source_pdf_path,
        )
        return document

    pdf_path = Path(document.source_pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Source PDF not found: {pdf_path}")

    logger.info(
        "Running Docling OCR for '{}': {} page(s) pending", pdf_path, len(pending_pages)
    )

    try:
        converter = build_converter()
    except Exception as exc:
        raise DoclingOCRError(f"Failed to initialize Docling for '{pdf_path}': {exc}") from exc

    for page in pending_pages:
        events = _run_single_page(converter, pdf_path, page, metrics)
        document.sanitization_events.extend(events)

    logger.info(
        "Docling OCR complete for '{}': {} page(s), avg {:.2f}s/page, total {:.2f}s",
        document.source_pdf_path,
        metrics.page_count,
        metrics.average_seconds,
        metrics.total_seconds,
    )
    return document


def _run_single_page(
    converter, pdf_path: Path, page: Page, metrics: OCRTimingMetrics
) -> List[SanitizationEvent]:
    """Convert one page via Docling and update it in place.

    Failures are caught and logged rather than raised, so one bad page
    does not abort OCR for the rest of the document - matches the
    "handle failures gracefully" pattern already used throughout this
    pipeline (e.g. src/images/image_extractor.py).

    Returns:
        A list (possibly empty) of SanitizationEvent for any
        XML-illegal character removed from this page's recovered text
        (XML Sanitization Architecture, Layer 1) - returned rather than
        appended directly to a Document, since this function only ever
        receives a single Page, not the Document it belongs to.
    """
    page_number = page.page_number
    start = perf_counter()

    try:
        result = converter.convert(pdf_path, page_range=(page_number, page_number))
        text = result.document.export_to_text()
    except Exception as exc:
        duration = perf_counter() - start
        metrics.record(page_number, duration)
        logger.warning(
            "Page {} → Docling OCR failed after {:.2f}s: {}", page_number, duration, exc
        )
        page.extraction_method = ExtractionMethod.DOCLING
        page.routing_decision = RoutingDecision.ROUTE_TO_DOCLING
        return []

    duration = perf_counter() - start
    metrics.record(page_number, duration)

    page.extraction_method = ExtractionMethod.DOCLING
    page.routing_decision = RoutingDecision.ROUTE_TO_DOCLING

    stripped = text.strip()
    if stripped:
        page.raw_text = text
        cleaned, removed = sanitize_xml_text(normalize_whitespace(text))
        page.cleaned_text = cleaned
        page.ocr_confidence = OCRConfidence.MEDIUM
        logger.info(
            "Page {} → Docling OCR in {:.2f}s ({} chars recovered)",
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
            "Page {} → Docling OCR in {:.2f}s (no text recovered)", page_number, duration
        )

    return []
