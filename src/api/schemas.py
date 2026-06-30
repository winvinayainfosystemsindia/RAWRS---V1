"""JSON response shapes for the RAWRS API.

Every field here is a direct re-exposure of an existing src/models/
field - this module defines no new domain concepts, only how existing
ones are shaped for HTTP/JSON. Where a model field is a raw filesystem
path (Image.file_path), the response substitutes a servable URL instead
(see routes.py's image-serving route) since a browser cannot read the
backend's local disk directly.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from src.api.jobs import JobStatus


class JobSummary(BaseModel):
    job_id: str
    filename: str
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    failed_stage: Optional[str] = None

    # Populated once status is COMPLETE or FAILED-with-partial-document;
    # None while still queued/processing.
    page_count: Optional[int] = None
    image_count: Optional[int] = None
    heading_count: Optional[int] = None
    footnote_count: Optional[int] = None
    error_count: Optional[int] = None
    warning_count: Optional[int] = None
    info_count: Optional[int] = None

    markdown_available: bool = False
    docx_available: bool = False
    report_available: bool = False
    has_front_matter: bool = False


class ValidationIssueOut(BaseModel):
    severity: str
    rule_id: str
    message: str
    page_number: Optional[int] = None
    suggested_action: Optional[str] = None


class ValidationResponse(BaseModel):
    issues: List[ValidationIssueOut]
    error_count: int
    warning_count: int
    info_count: int


class FigureOut(BaseModel):
    label: Optional[str] = None
    number: Optional[int] = None
    caption: Optional[str] = None
    alt_text: Optional[str] = None
    alt_text_status: Optional[str] = None
    # AI structured response fields — None until generate-alt-text is called
    ai_description: Optional[str] = None
    ai_purpose: Optional[str] = None
    ai_visible_text: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_warnings: List[str] = []


class ImageOut(BaseModel):
    image_id: str
    page_number: int
    width: Optional[int] = None
    height: Optional[int] = None
    url: Optional[str] = None
    extraction_failed: bool
    figure: Optional[FigureOut] = None


class ImagesResponse(BaseModel):
    images: List[ImageOut]


class ReviewAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    MARK_DECORATIVE = "mark_decorative"
    MARK_COMPLEX = "mark_complex"
    SKIP = "skip"
    EDIT = "edit"


class ImageReviewRequest(BaseModel):
    action: ReviewAction
    alt_text: Optional[str] = None  # required when action is approve (with custom text) or edit


class BulkActionRequest(BaseModel):
    image_ids: List[str]
    action: ReviewAction   # approve/reject/mark_decorative/skip only (not edit)


class FootnoteOut(BaseModel):
    footnote_id: Optional[str] = None
    note_type: str
    number: int
    marker: str
    anchor_page_number: int
    body: str
    body_page_number: int
    review_status: str = "detected"
    reviewer_note: Optional[str] = None


class FootnotesResponse(BaseModel):
    footnotes: List[FootnoteOut]


class PageOcrInfoOut(BaseModel):
    page_number: int
    page_type: Optional[str] = None
    extraction_method: Optional[str] = None
    ocr_confidence: Optional[str] = None
    has_text: bool
    printed_label: Optional[str] = None


class PagesResponse(BaseModel):
    pages: List[PageOcrInfoOut]


class MarkdownResponse(BaseModel):
    content: str


class UploadResponse(BaseModel):
    job_id: str
    filename: str
    status: JobStatus


class TableAISuggestionsOut(BaseModel):
    table_type: Optional[str] = None
    suggested_caption: Optional[str] = None
    suggested_summary: Optional[str] = None
    header_rows_detected: int = 0
    header_cols_detected: int = 0
    warnings: List[str] = []
    confidence: float = 0.0


class TableCellOut(BaseModel):
    text: str
    row_index: int
    col_index: int
    row_span: int = 1
    col_span: int = 1
    is_header: bool = False
    is_row_header: bool = False
    header_level: int = 0


class TableRowOut(BaseModel):
    cells: List[TableCellOut]
    is_header_row: bool = False


class EvidenceSignalOut(BaseModel):
    name: str
    score: float
    weight: float
    note: str


class TableOut(BaseModel):
    table_id: str
    page_number: int
    row_count: int
    col_count: int
    rows: List[TableRowOut]
    caption: Optional[str] = None
    summary: Optional[str] = None
    status: str
    extraction_source: str
    header_col_count: int = 0
    confidence: float = 1.0
    ai_suggestions: Optional[TableAISuggestionsOut] = None
    evidence_signals: List[EvidenceSignalOut] = []
    lifecycle_status: str = "DETECTED"
    confidence_explanation: Optional[str] = None


class TablesResponse(BaseModel):
    tables: List[TableOut]


class CellUpdateRequest(BaseModel):
    row_index: int
    col_index: int
    text: str


class TableReviewRequest(BaseModel):
    caption: Optional[str] = None
    summary: Optional[str] = None
    header_row_indices: Optional[List[int]] = None
    header_col_count: Optional[int] = None
    cells: Optional[List[CellUpdateRequest]] = None


# --- Headings (FEATURE_016A) -------------------------------------------------


class HeadingOut(BaseModel):
    document_order: int
    level: int
    text: str
    page_number: int
    is_page_marker: bool
    review_status: str
    reviewer_note: Optional[str] = None


class HeadingsResponse(BaseModel):
    headings: List[HeadingOut]


class HeadingReviewRequest(BaseModel):
    level: Optional[int] = None       # corrected level (1–5 only; 6 rejected)
    text: Optional[str] = None        # corrected heading text
    action: Optional[str] = None      # "approve" | "reject"
    reviewer_note: Optional[str] = None


# --- Footnotes review (FEATURE_016D) -----------------------------------------


class FootnoteReviewRequest(BaseModel):
    body: Optional[str] = None        # corrected note body text
    action: Optional[str] = None      # "approve" | "reject"
    reviewer_note: Optional[str] = None


# --- Metadata / document accessibility properties (FEATURE_016F) -------------


class MetadataOut(BaseModel):
    filename: str
    page_count: int
    image_count: int
    language: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None


class MetadataUpdateRequest(BaseModel):
    language: Optional[str] = None    # IETF BCP 47 tag, e.g. "en-US"
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None


# --- Reading order review (FEATURE_016B) ------------------------------------


class BlockOut(BaseModel):
    block_order: int               # TextBlock.order (immutable, PyMuPDF extraction order)
    corrected_order: Optional[int] = None
    text: str                      # truncated to 200 chars for display
    page_number: int
    bbox_x0: float
    bbox_y0: float
    bbox_x1: float
    bbox_y1: float


class PageReadingOrderOut(BaseModel):
    page_number: int
    reading_order_status: str      # "unreviewed" | "approved" | "corrected"
    blocks: List[BlockOut]         # sorted by effective order (corrected_order ?? order)


class ReadingOrderResponse(BaseModel):
    pages: List[PageReadingOrderOut]


class ReadingOrderPatchRequest(BaseModel):
    action: str                         # "approve" | "reorder"
    block_sequence: Optional[List[int]] = None  # TextBlock.order values in desired sequence


# --- Export readiness / accessibility gate (FEATURE_015.2 PART F) -----------


class ReadinessCategoryOut(BaseModel):
    """Readiness summary for one accessibility category."""

    complete: bool
    total: int = 0
    approved: int = 0
    issues: List[str] = []


class ExportReadinessOut(BaseModel):
    """Pre-export accessibility readiness report.

    ready: True only when all categories are complete (no outstanding
           WARNING-level accessibility issues). Informational issues
           (INFO severity) do not block readiness.
    overall_score: fraction of categories that are complete (0.0–1.0).
    categories: per-category readiness breakdown.
    """

    ready: bool
    overall_score: float
    categories: dict  # str → ReadinessCategoryOut (Dict not used for JSON compat)
