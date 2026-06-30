"""OCR routing layer for RAWRS (Phase D.0).

Classifies each page's already-extracted text (from
src/ocr/extractor.py's direct-extraction pass) as DIRECT_TEXT or
OCR_REQUIRED, and records the routing decision made as a result. This
is purely a classification/decision layer - per this phase's explicit
scope, no OCR engine (Docling/Surya) is integrated here. OCR_REQUIRED
pages are routed to a placeholder (ExtractionMethod.OCR_PENDING) that
performs no extraction; a future phase wires a real engine in at
exactly that point, without needing to touch this routing decision or
its callers.

Classification is based on the actual extracted text's quality, not
PDF metadata (e.g. an embedded "is scanned" flag, page count, producer
string, etc.):

- Empty or too-short text => OCR_REQUIRED. Nothing usable was
  extracted, regardless of what the PDF claims about itself.
- Text dominated by control characters or the Unicode replacement
  character (U+FFFD) => OCR_REQUIRED. A broken font ToUnicode mapping
  can produce non-empty but unusable/garbled text - metadata alone
  cannot detect this, only the extracted characters themselves can.
- Otherwise => DIRECT_TEXT.

Both checks were validated against all 4 benchmark PDFs' actual
extracted text (see BENCHMARK_RECONCILIATION_AND_PHASE1_PLAN.md Phase
D): every real prose page scores perfectly clean (no false positives
from legitimate typography - em dashes, curly quotes, accented
characters are all printable and pass), while every page with no
extractable text is correctly flagged.

See docs/OCR_RULES.md ("Page Classification and Routing") for the
documented rule this implements.
"""

from loguru import logger

from src.models.contracts import (
    Document,
    ExtractionMethod,
    Page,
    PageType,
    RoutingDecision,
)

# A page with fewer non-whitespace characters than this is treated as
# having no usable direct text, regardless of character quality.
_MIN_TEXT_LENGTH = 20

# A page's text is treated as unusable/garbled when more than this
# fraction of its characters are control characters or the Unicode
# replacement character - the signature of a broken font encoding,
# not legitimate extracted prose.
_MAX_UNUSABLE_CHAR_RATIO = 0.10


def route_pages(document: Document) -> Document:
    """Classify every page and record its routing decision.

    Args:
        document: A Document whose pages have already been through
            direct text extraction (src/ocr/extractor.py). Reads
            Page.cleaned_text/raw_text only - does not re-open the
            source PDF and performs no OCR. Safe to call even if
            extraction left every page empty (e.g. a fully scanned
            PDF); every page is still classified.

    Returns:
        The same Document instance. Each page gets page_type,
        extraction_method, and routing_decision populated.
        Page.ocr_confidence is left untouched for DIRECT_TEXT pages
        (still whatever direct extraction set, typically HIGH); for
        OCR_REQUIRED pages it is cleared to None, since a blanket
        "text exists" confidence value set earlier no longer applies
        once that text has been judged unusable here - None means "not
        yet known", which a future OCR phase is responsible for setting
        once it actually runs.
    """
    logger.info("Routing pages for '{}'", document.source_pdf_path)

    direct_count = 0
    ocr_required_count = 0

    for page in document.pages:
        page_type = classify_page(page)
        page.page_type = page_type

        if page_type == PageType.DIRECT_TEXT:
            page.extraction_method = ExtractionMethod.DIRECT_TEXT_EXTRACTION
            page.routing_decision = RoutingDecision.ROUTE_TO_DIRECT_EXTRACTION
            direct_count += 1
        else:
            page.extraction_method = ExtractionMethod.OCR_PENDING
            page.routing_decision = RoutingDecision.ROUTE_TO_OCR_PLACEHOLDER
            page.ocr_confidence = None
            ocr_required_count += 1

        logger.info("Page {} → {}", page.page_number, page_type.value.upper())

    logger.info(
        "Routing complete for '{}': {} page(s) DIRECT_TEXT, {} page(s) OCR_REQUIRED",
        document.source_pdf_path,
        direct_count,
        ocr_required_count,
    )
    return document


def classify_page(page: Page) -> PageType:
    """Classify a single page's already-extracted text.

    Deterministic, rule-based, no AI: a length check and a character-
    quality check, both applied to text that has already been
    extracted - never PDF metadata.
    """
    text = page.cleaned_text or page.raw_text
    stripped = text.strip()

    if len(stripped) < _MIN_TEXT_LENGTH:
        return PageType.OCR_REQUIRED

    if _unusable_char_ratio(stripped) > _MAX_UNUSABLE_CHAR_RATIO:
        return PageType.OCR_REQUIRED

    return PageType.DIRECT_TEXT


def _unusable_char_ratio(text: str) -> float:
    """Fraction of characters that are control characters or the
    Unicode replacement character - the signature of a broken font
    encoding rather than legitimate extracted prose. Newlines/tabs are
    expected formatting, not corruption, and are not penalized.
    """
    if not text:
        return 0.0
    unusable = sum(
        1 for ch in text if ch == "�" or (not ch.isprintable() and ch not in "\n\t")
    )
    return unusable / len(text)
