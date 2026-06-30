"""Page model for RAWRS document structure.

See docs/PAGE_RULES.md and docs/OCR_RULES.md for the rules this model
exists to support.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class OCRConfidence(str, Enum):
    """Page-level OCR confidence category.

    Phase 1 tracks OCR confidence at the page level only (approved
    architecture decision #3); finer-grained per-region confidence is
    deferred to a future phase.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PageType(str, Enum):
    """Result of deterministic page-level extraction-quality classification.

    Added in Phase D.0 (OCR routing foundation). See src/ocr/router.py
    for the classification logic and docs/OCR_RULES.md for the
    rationale. Optional and defaulted to None so existing Page
    construction sites are unaffected.
    """

    DIRECT_TEXT = "direct_text"
    OCR_REQUIRED = "ocr_required"


class ExtractionMethod(str, Enum):
    """Which mechanism actually produced (or will produce) a page's text.

    OCR_PENDING was a placeholder used before Phase D.1: Phase 1 had no
    OCR engine wired in yet (see docs/OCR_RULES.md). DOCLING (added in
    Phase D.1) is set once Docling has actually been run for a page,
    regardless of whether it recovered any text - so a page that was
    attempted but recovered nothing is still distinguishable from one
    that was never tried (still OCR_PENDING). SURYA (added in Phase
    D.2) follows the same "attempted, regardless of outcome" rule: it
    is set once Surya has run as the fallback for a page Docling left
    empty, even if Surya itself recovers nothing.
    """

    DIRECT_TEXT_EXTRACTION = "direct_text_extraction"
    OCR_PENDING = "ocr_pending"
    DOCLING = "docling"
    SURYA = "surya"
    MATHPIX_IMPORT = "mathpix_import"


class ReadingOrderStatus(str, Enum):
    """Review status of a page's reading order (016B).

    UNREVIEWED: no human has looked at this page's order yet.
    APPROVED: human confirmed the current (or corrected) order is right.
    CORRECTED: human manually reordered the blocks via the workspace.

    Only pages flagged by PAGE_003 (or already-reviewed ones) are surfaced
    in the reading-order workspace; others stay UNREVIEWED silently.
    """

    UNREVIEWED = "unreviewed"
    APPROVED = "approved"
    CORRECTED = "corrected"


class RoutingDecision(str, Enum):
    """The route src/ocr/router.py / src/ocr/docling_engine.py /
    src/ocr/surya_engine.py actually sent a page down.

    Kept as a distinct field from PageType so OCR_REQUIRED pages can be
    split across multiple concrete routes (Docling, or a Surya fallback
    when Docling fails or recovers nothing, or in future manual review)
    without changing what "OCR_REQUIRED" itself means.
    """

    ROUTE_TO_DIRECT_EXTRACTION = "route_to_direct_extraction"
    ROUTE_TO_OCR_PLACEHOLDER = "route_to_ocr_placeholder"
    ROUTE_TO_DOCLING = "route_to_docling"
    ROUTE_TO_SURYA = "route_to_surya"


class Page(BaseModel):
    """A single page of a parsed PDF document.

    Headings and images detected on this page are not duplicated here;
    they live on Document.headings / Document.images (each tagged with
    ``page_number``), which is the single source of truth per
    CLAUDE_INSTRUCTIONS.md's "Do not create duplicate data structures"
    rule. Consumers filter by ``page_number`` when a per-page view is
    needed.

    ``page_type``, ``extraction_method``, and ``routing_decision`` are
    populated by src/ocr/router.py (Phase D.0) after direct text
    extraction has run. All three are optional and default to None, so
    every existing construction of Page (parser output, before routing
    has run) remains valid unchanged. ``ocr_confidence`` continues to
    serve as the "extraction confidence" signal - a separate, redundant
    confidence field was deliberately not added; see router.py for how
    it is reconciled with the routing decision.

    ``printed_label`` (feature_009) is the page number actually printed
    on this page (e.g. "3", "xlv"), as opposed to ``page_number``'s
    physical position in the PDF - distinct concepts that frequently
    diverge (a chapter excerpt's physical page 1 is rarely the book's
    printed page 1; front matter is often roman numerals). Populated by
    src/structure/structure_detector.py from the same per-page text
    scan that already builds Document.blocks, so this field is None for
    any Page built before that stage has run, for any page with no
    confidently-detected printed number (e.g. a scanned page with no
    text layer, or a page where the candidate is ambiguous), and for
    every existing Page construction site that predates this field -
    its absence must always be read as "use page_number instead," never
    as "this page has no printed number at all."
    """

    page_number: int = Field(..., ge=1)
    raw_text: str = ""
    cleaned_text: str = ""
    ocr_confidence: Optional[OCRConfidence] = None
    footnote_references: List[str] = Field(default_factory=list)
    endnote_references: List[str] = Field(default_factory=list)
    page_type: Optional[PageType] = None
    extraction_method: Optional[ExtractionMethod] = None
    routing_decision: Optional[RoutingDecision] = None
    printed_label: Optional[str] = None
    # Physical page width in PDF points (populated by structure_detector.py
    # from pdf_page.rect.width). Used by docx_generator.py to detect whether
    # an image is centered, left-, or right-aligned relative to the page.
    # None for any Page built before this field existed.
    width_pt: Optional[float] = None
    # 016B reading order review status. UNREVIEWED until a human either
    # approves the auto-detected order or manually reorders the blocks.
    reading_order_status: ReadingOrderStatus = ReadingOrderStatus.UNREVIEWED
