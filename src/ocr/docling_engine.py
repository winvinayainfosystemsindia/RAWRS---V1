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
from typing import Dict, List, Optional, Tuple

from loguru import logger

from src.models.contracts import (
    Document,
    ExtractionMethod,
    OCRConfidence,
    OCRLayoutItem,
    OCRReread,
    Page,
    RoutingDecision,
    SanitizationEvent,
)
from src.ocr import cache as ocr_cache
from src.ocr.docling_config import build_converter
from src.ocr.extractor import normalize_whitespace
from src.ocr.quality import is_garbled
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

    # A page cached from an earlier run of the same PDF needs no engine at all;
    # a document whose every page is cached never loads Docling's models.
    cached = {page.page_number: _cached_page(pdf_path, page.page_number) for page in pending_pages}
    converter = None
    if any(entry is None for entry in cached.values()):
        try:
            converter = build_converter()
        except Exception as exc:
            raise DoclingOCRError(f"Failed to initialize Docling for '{pdf_path}': {exc}") from exc

    for page in pending_pages:
        events = _run_single_page(converter, pdf_path, page, metrics, cached=cached[page.page_number])
        document.sanitization_events.extend(events)

    logger.info(
        "Docling OCR complete for '{}': {} page(s), avg {:.2f}s/page, total {:.2f}s",
        document.source_pdf_path,
        metrics.page_count,
        metrics.average_seconds,
        metrics.total_seconds,
    )
    return document


def ocr_page_texts(pdf_path: Path) -> List[str]:
    """OCR text of every page, one string per page (index 0 is page 1).

    For callers that only need to know what text is on which page - the
    Mathpix import of a scanned PDF aligns its blocks to these, because a scan
    has no text layer to align against. A page that fails yields "", which the
    alignment treats as proving nothing; a converter that cannot start yields
    an empty list, which means no evidence at all.
    """
    try:
        import fitz

        with fitz.open(str(pdf_path)) as pdf:
            page_count = pdf.page_count
        cached = {n: _cached_page(pdf_path, n) for n in range(1, page_count + 1)}
        converter = build_converter() if any(e is None for e in cached.values()) else None
    except Exception as exc:
        logger.warning("OCR page texts unavailable for '{}': {}", pdf_path, exc)
        return []
    texts: List[str] = []
    for page_number in range(1, page_count + 1):
        try:
            texts.append(_convert_page(converter, pdf_path, page_number, cached[page_number]).text)
        except Exception as exc:
            logger.warning("OCR of page {} failed: {}", page_number, exc)
            texts.append("")
    return texts


# (label, raw text, raw Docling level) of one title/section-header item; the
# level is read only for section headers, exactly as the heading code uses it.
HeaderItem = Tuple[str, str, Optional[object]]
# (raw text, [x0, y0, x1, y1] in PDF points, top-left origin) of one item.
TextItem = Tuple[str, List[float]]


@dataclass(frozen=True)
class _DoclingPage:
    """Docling's raw output for one page - all RAWRS reads from a conversion,
    and therefore all the OCR cache needs to keep (src/ocr/cache.py)."""

    text: str
    # None when the structure could not be read: the page keeps its text and
    # loses its headings, exactly as before the cache existed.
    header_items: Optional[List[HeaderItem]]
    # Every text-bearing item with where it sits; the garble check runs over
    # these so a garbled paragraph can be cropped and read again.
    text_items: Optional[List[TextItem]] = None
    # The whole layout, furniture and pictures included (OCRLayoutItem fields
    # as plain dicts, so the cache can keep them).
    layout_items: Optional[List[Dict]] = None
    from_cache: bool = False


def _cached_page(pdf_path: Path, page_number: int) -> Optional[_DoclingPage]:
    entry = ocr_cache.lookup("docling", pdf_path, page_number)
    if entry is None or any(key not in entry for key in ("header_items", "text_items", "layout_items")):
        return None
    items = entry["header_items"]
    text_items = entry["text_items"]
    return _DoclingPage(
        text=entry["text"],
        header_items=None if items is None else [(i[0], i[1], i[2]) for i in items],
        text_items=None if text_items is None else [(i[0], list(i[1])) for i in text_items],
        layout_items=entry["layout_items"],
        from_cache=True,
    )


def _convert_page(
    converter, pdf_path: Path, page_number: int, cached: Optional[_DoclingPage] = None
) -> _DoclingPage:
    """One page through Docling, or its cached result. Raises what the
    conversion raises; a failure is never cached."""
    if cached is not None:
        return cached
    result = converter.convert(pdf_path, page_range=(page_number, page_number))
    page = _DoclingPage(
        result.document.export_to_text(),
        _header_items(result.document),
        _text_items(result.document),
        _layout_items(result.document),
    )
    ocr_cache.store(
        "docling",
        pdf_path,
        page_number,
        {
            "text": page.text,
            "header_items": page.header_items,
            "text_items": page.text_items,
            "layout_items": page.layout_items,
        },
    )
    return page


def _layout_items(docling_document) -> Optional[List[Dict]]:
    """Every positioned item of the page in reading order - body and
    furniture, pictures with the text Docling read inside them as their
    children. None when the structure cannot be read, which costs the page
    its structure, never its text."""
    try:
        from docling_core.types.doc.document import ContentLayer

        items: List[Dict] = []
        picture_depth: Optional[int] = None
        for item, depth in docling_document.iterate_items(
            traverse_pictures=True,
            included_content_layers={ContentLayer.BODY, ContentLayer.FURNITURE},
        ):
            text, _ = sanitize_xml_text(normalize_whitespace(getattr(item, "text", "") or ""))
            text = text.strip()
            if picture_depth is not None and depth > picture_depth:
                if text:
                    items[-1]["children"].append(text)
                continue
            picture_depth = None
            provenance = getattr(item, "prov", None) or []
            if not provenance:
                continue
            label = str(getattr(getattr(item, "label", None), "value", "") or "")
            prov = provenance[0]
            height = docling_document.pages[prov.page_no].size.height
            box = prov.bbox.to_top_left_origin(page_height=height)
            items.append({
                "label": label,
                "text": text,
                "bbox": [box.l, box.t, box.r, box.b],
                "furniture": getattr(item, "content_layer", None) == ContentLayer.FURNITURE,
                "children": [],
            })
            if label == "picture":
                picture_depth = depth
        return items
    except Exception as exc:  # structure is a bonus on top of the text
        logger.warning("Could not read Docling layout: {}", exc)
        return None


def _text_items(docling_document) -> Optional[List[TextItem]]:
    """Every item with text and a position, raw - None when the structure
    cannot be read, which costs the page its re-reading, never its text."""
    try:
        items: List[TextItem] = []
        for item, _ in docling_document.iterate_items():
            text = getattr(item, "text", "") or ""
            provenance = getattr(item, "prov", None) or []
            if not text.strip() or not provenance:
                continue
            prov = provenance[0]
            height = docling_document.pages[prov.page_no].size.height
            box = prov.bbox.to_top_left_origin(page_height=height)
            items.append((text, [box.l, box.t, box.r, box.b]))
        return items
    except Exception as exc:  # positions are a bonus on top of the text
        logger.warning("Could not read Docling item positions: {}", exc)
        return None


def _garbled_regions(text_items: Optional[List[TextItem]], cleaned_text: str) -> List[OCRReread]:
    """The items whose recognition looks garbled (src/ocr/quality.py), as
    re-reading candidates. Only an item found verbatim in the page text is
    kept - its reading replaces exactly that text, so anything else could
    never be placed."""
    regions: List[OCRReread] = []
    for raw_text, bbox in text_items or []:
        text, _ = sanitize_xml_text(raw_text)
        text = text.strip()
        if text and text in cleaned_text and is_garbled(text):
            regions.append(OCRReread(original=text, bbox=bbox))
    return regions


# Docling numbers section headers from 1; the document title sits above them.
_MAX_OCR_HEADING_LEVEL = 5


def _layout_heading_levels(docling_document, cleaned_text: str) -> Dict[str, int]:
    """Docling's title and section headers on this page, keyed by the line of
    ``cleaned_text`` each one became: the title at level 1, a section header
    at its Docling level + 1.

    Only a header whose text is a whole line of the page's text is kept - the
    heading detector matches headings to lines, so anything else could never
    be placed. Any failure reading the structure costs the page its headings,
    never its text.
    """
    return _heading_levels_from_items(_header_items(docling_document), cleaned_text)


def _header_items(docling_document) -> Optional[List[HeaderItem]]:
    """The title/section-header items of a Docling document, raw - the part of
    a conversion the cache keeps so heading levels are recomputed, never stored.
    None when the structure cannot be read."""
    try:
        items: List[HeaderItem] = []
        for item, _ in docling_document.iterate_items():
            label = getattr(getattr(item, "label", None), "value", None)
            if label not in ("title", "section_header"):
                continue
            # Raw: converted to int only where the original code did, after the
            # line match, so an odd level on an unplaced header changes nothing.
            level = getattr(item, "level", 1) if label == "section_header" else None
            items.append((label, getattr(item, "text", "") or "", level))
        return items
    except Exception as exc:  # structure is a bonus on top of the text
        logger.warning("Could not read Docling layout headings: {}", exc)
        return None


def _heading_levels_from_items(items: Optional[List[HeaderItem]], cleaned_text: str) -> Dict[str, int]:
    if items is None:
        return {}
    try:
        lines = {line.strip() for line in cleaned_text.splitlines() if line.strip()}
        levels: Dict[str, int] = {}
        for label, raw_text, raw_level in items:
            text, _ = sanitize_xml_text(normalize_whitespace(raw_text))
            text = text.strip()
            if text not in lines:
                continue
            level = 1 if label == "title" else min(int(raw_level or 1) + 1, _MAX_OCR_HEADING_LEVEL)
            levels.setdefault(text, level)
        return levels
    except Exception as exc:  # structure is a bonus on top of the text
        logger.warning("Could not read Docling layout headings: {}", exc)
        return {}


def _run_single_page(
    converter,
    pdf_path: Path,
    page: Page,
    metrics: OCRTimingMetrics,
    cached: Optional[_DoclingPage] = None,
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
        converted = _convert_page(converter, pdf_path, page_number, cached)
        text = converted.text
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
        page.ocr_heading_levels = _heading_levels_from_items(converted.header_items, cleaned)
        # Headings are matched to page lines by their text, so a heading line
        # is never a re-reading candidate: changing it would orphan the match.
        page.ocr_rereads = [
            region
            for region in _garbled_regions(converted.text_items, cleaned)
            if region.original not in page.ocr_heading_levels
        ]
        page.ocr_layout = [OCRLayoutItem(**item) for item in converted.layout_items or []]
        page.ocr_confidence = OCRConfidence.MEDIUM
        logger.info(
            "Page {} → Docling OCR in {:.2f}s ({} chars recovered{})",
            page_number,
            duration,
            len(stripped),
            ", cached" if converted.from_cache else "",
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
