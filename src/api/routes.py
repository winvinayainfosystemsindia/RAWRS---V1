"""API routes for the RAWRS frontend.

Every handler either (a) manages job lifecycle (upload/list/status) or
(b) re-shapes an existing PipelineResult/Document field into a
schemas.py response - no handler computes a new domain fact RAWRS
doesn't already produce. Sub-resource endpoints (validation/images/
footnotes/pages/markdown) all require the job to be COMPLETE or FAILED
(i.e. result is populated); while QUEUED/PROCESSING they return 409 so
the frontend's polling loop has an unambiguous "not ready yet" signal
distinct from 404 "no such job".
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from loguru import logger

from src.api.jobs import Job, JobStatus, create_job, get_job, list_jobs, start_job, _lock
from src.api.schemas import (
    BlockOut,
    BulkActionRequest,
    CellUpdateRequest,
    CorrectionAction,
    CorrectionActionRequest,
    CorrectionOut,
    CorrectionsResponse,
    EvidenceItemOut,
    EvidenceSignalOut,
    ExportReadinessOut,
    FigureOut,
    FootnoteOut,
    FootnoteReviewRequest,
    FootnotesResponse,
    HeadingOut,
    HeadingReviewRequest,
    HeadingsResponse,
    ImageOut,
    ImageReviewRequest,
    ImagesResponse,
    JobSummary,
    MarkdownResponse,
    MetadataOut,
    MetadataUpdateRequest,
    PageOcrInfoOut,
    PageReadingOrderOut,
    PagesResponse,
    ReadinessCategoryDetailOut,
    ReadinessCategoryOut,
    ReadinessReportOut,
    ReadingOrderPatchRequest,
    ReadingOrderResponse,
    ReviewAction,
    TableAISuggestionsOut,
    TableCellOut,
    TableOut,
    TableReviewRequest,
    TableRowOut,
    TablesResponse,
    UploadResponse,
    ValidationIssueOut,
    ValidationResponse,
)
from src.models.contracts import Document, HeadingLevel, HeadingReviewStatus, FootnoteReviewStatus, Severity
from src.models.correction import CorrectionRecord, CorrectionStatus
from src.models.figure import AltTextStatus
from src.validation.readiness import compute_readiness
from src.verification.engine import UnknownAssetTypeError, engine

router = APIRouter(prefix="/api")


# --- Upload / job lifecycle -------------------------------------------------


_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".tif", ".tiff")


@router.post("/documents", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    mmd_file: Optional[UploadFile] = File(None),
    image_files: List[UploadFile] = File(default=[]),
    enable_ocr: bool = True,
) -> UploadResponse:
    if file.filename is None or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf files are accepted.")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    mmd_bytes: Optional[bytes] = None
    if mmd_file is not None and mmd_file.filename:
        name = mmd_file.filename.lower()
        if not (name.endswith(".mmd") or name.endswith(".md")):
            raise HTTPException(status_code=400, detail="MMD file must be a .mmd or .md file.")
        mmd_bytes = await mmd_file.read()
        if not mmd_bytes:
            mmd_bytes = None  # treat empty file the same as not supplied

    image_payload: List[tuple] = []
    for image_file in image_files:
        if not image_file.filename:
            continue
        if not image_file.filename.lower().endswith(_IMAGE_EXTENSIONS):
            raise HTTPException(
                status_code=400,
                detail=f"'{image_file.filename}' is not a supported image type.",
            )
        data = await image_file.read()
        if data:
            image_payload.append((image_file.filename, data))

    job = create_job(file.filename, pdf_bytes, mmd_bytes=mmd_bytes, image_files=image_payload)
    start_job(job.job_id, enable_ocr=enable_ocr)
    return UploadResponse(job_id=job.job_id, filename=job.filename, status=job.status)


@router.get("/documents", response_model=List[JobSummary])
def list_documents() -> List[JobSummary]:
    return [_to_summary(job) for job in list_jobs()]


@router.get("/documents/{job_id}", response_model=JobSummary)
def get_document(job_id: str) -> JobSummary:
    job = _require_job(job_id)
    return _to_summary(job)


# --- Review sub-resources ----------------------------------------------------


@router.get("/documents/{job_id}/validation", response_model=ValidationResponse)
def get_validation(job_id: str) -> ValidationResponse:
    document = _require_document(job_id)
    issues = document.validation_issues if document else []

    issues_out = [
        ValidationIssueOut(
            severity=issue.severity.value,
            rule_id=issue.rule_id,
            message=issue.message,
            page_number=issue.page_number,
            suggested_action=issue.suggested_action,
        )
        for issue in issues
    ]
    return ValidationResponse(
        issues=issues_out,
        error_count=sum(1 for i in issues if i.severity == Severity.ERROR),
        warning_count=sum(1 for i in issues if i.severity == Severity.WARNING),
        info_count=sum(1 for i in issues if i.severity == Severity.INFO),
    )


@router.get("/documents/{job_id}/images", response_model=ImagesResponse)
def get_images(job_id: str) -> ImagesResponse:
    document = _require_document(job_id)
    images = document.images if document else []
    return ImagesResponse(images=[_image_out(img, job_id) for img in images])


@router.get("/documents/{job_id}/images/{image_id}/file")
def get_image_file(job_id: str, image_id: str) -> FileResponse:
    document = _require_document(job_id)
    image = next((img for img in (document.images if document else []) if img.image_id == image_id), None)
    if image is None:
        raise HTTPException(status_code=404, detail=f"No image '{image_id}' on this document.")
    if image.extraction_failed:
        raise HTTPException(status_code=404, detail="This image failed extraction; no file exists.")

    from pathlib import Path

    path = Path(image.file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image file is missing from disk.")
    return FileResponse(path)


@router.post("/documents/{job_id}/images/{image_id}/generate-alt-text", response_model=ImageOut)
def generate_image_alt_text(job_id: str, image_id: str) -> ImageOut:
    """On-demand AI alt text generation for a single image.

    AI generation is NEVER triggered automatically — only when the human
    reviewer explicitly clicks "Generate AI Alt Text" in the review UI,
    which calls this endpoint. The image file must be on disk; extraction_failed
    images return 422. Returns the updated ImageOut with AI fields populated
    and alt_text_status set to AI_GENERATED.
    """
    from src.ai.alt_text_generator import AltTextGenerationError, AltTextRequest, generate_alt_text

    document = _require_document(job_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No document for this job.")
    image = next((img for img in document.images if img.image_id == image_id), None)
    if image is None:
        raise HTTPException(status_code=404, detail=f"No image '{image_id}' on this document.")
    if image.extraction_failed or not image.file_path:
        raise HTTPException(status_code=422, detail="Cannot generate alt text: image extraction failed.")
    if not Path(image.file_path).is_file():
        raise HTTPException(status_code=422, detail="Image file is missing from disk.")

    nearby_text = _load_nearby_text(job_id, image_id)
    request = AltTextRequest(
        image_path=image.file_path,
        caption=image.figure.caption if image.figure else None,
        figure_label=image.figure.label if image.figure else None,
        nearby_text=nearby_text,
        page_number=image.page_number,
    )
    try:
        result = generate_alt_text(request)
    except AltTextGenerationError as exc:
        logger.error("Alt text generation failed for image {}: {}", image_id, exc)
        raise HTTPException(status_code=503, detail=f"AI generation failed: {exc}") from exc

    with _lock:
        if image.figure is None:
            from src.models.figure import Figure
            image.figure = Figure()
        image.figure.ai_description = result.description
        image.figure.ai_purpose = result.purpose
        image.figure.ai_visible_text = result.visible_text
        image.figure.ai_confidence = result.confidence
        image.figure.ai_warnings = result.warnings
        image.figure.alt_text_status = AltTextStatus.AI_GENERATED
        from src.models.lifecycle import ObjectLifecycleStatus
        image.lifecycle_status = ObjectLifecycleStatus.AI_PROCESSED

    return _image_out(image, job_id)


@router.patch("/documents/{job_id}/images/{image_id}", response_model=ImageOut)
def review_image(job_id: str, image_id: str, body: ImageReviewRequest) -> ImageOut:
    """Apply a human review action to a single image.

    Action → alt_text_status transition and alt_text mutation:
      approve       → APPROVED  ; alt_text = body.alt_text or ai_description
      reject        → REJECTED  ; alt_text unchanged
      mark_decorative → DECORATIVE ; alt_text = ""
      mark_complex  → COMPLEX   ; alt_text = "[Complex image — requires extended description]"
      skip          → SKIPPED   ; alt_text unchanged
      edit          → AI_GENERATED ; alt_text = body.alt_text (stores edited draft)
    """
    document = _require_document(job_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No document for this job.")
    image = next((img for img in document.images if img.image_id == image_id), None)
    if image is None:
        raise HTTPException(status_code=404, detail=f"No image '{image_id}' on this document.")

    action = body.action
    if action in (ReviewAction.APPROVE, ReviewAction.EDIT) and body.alt_text == "":
        raise HTTPException(
            status_code=422,
            detail="Alt text cannot be empty for approve/edit. Use mark_decorative for intentionally decorative images.",
        )

    with _lock:
        if image.figure is None:
            from src.models.figure import Figure
            image.figure = Figure()
        _apply_review_action(image.figure, action, body.alt_text)
        from src.models.lifecycle import ObjectLifecycleStatus
        if action == ReviewAction.APPROVE:
            image.lifecycle_status = ObjectLifecycleStatus.APPROVED
        elif action in (ReviewAction.REJECT, ReviewAction.MARK_DECORATIVE,
                        ReviewAction.MARK_COMPLEX, ReviewAction.SKIP, ReviewAction.EDIT):
            image.lifecycle_status = ObjectLifecycleStatus.HUMAN_REVIEWED

    return _image_out(image, job_id)


@router.post("/documents/{job_id}/images/bulk-action", response_model=ImagesResponse)
def bulk_review_images(job_id: str, body: BulkActionRequest) -> ImagesResponse:
    """Apply a review action to multiple images at once.

    Unknown image_ids are silently skipped (not an error — the list may
    have been built from stale frontend state). Returns ALL images for
    this document, not just the ones modified.
    """
    document = _require_document(job_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No document for this job.")

    image_id_set = set(body.image_ids)
    with _lock:
        for image in document.images:
            if image.image_id not in image_id_set:
                continue
            if image.figure is None:
                from src.models.figure import Figure
                image.figure = Figure()
            _apply_review_action(image.figure, body.action, alt_text=None)

    images_out = [_image_out(img, job_id) for img in document.images]
    return ImagesResponse(images=images_out)


@router.get("/documents/{job_id}/tables", response_model=TablesResponse)
def get_tables(job_id: str) -> TablesResponse:
    document = _require_document(job_id)
    tables = document.tables if document else []
    return TablesResponse(tables=[_table_out(t) for t in tables])


@router.post("/documents/{job_id}/tables", response_model=TableOut)
def create_table(job_id: str, body: TableReviewRequest) -> TableOut:
    """Manually create a table on a document.

    Used when automated detection missed a table (e.g. borderless academic
    tables). Creates an empty table with one header row and one data row,
    then applies any caption/summary from the request. The reviewer
    edits cell content via PATCH /tables/{table_id}.
    """
    from src.models.table import Table, TableCell, TableRow, TableStatus

    document = _require_document(job_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No document for this job.")

    with _lock:
        new_id = f"table-manual-{len(document.tables)}"
        header_row = TableRow(
            cells=[TableCell(text="", row_index=0, col_index=0, is_header=True)],
            is_header_row=True,
        )
        data_row = TableRow(
            cells=[TableCell(text="", row_index=1, col_index=0)],
            is_header_row=False,
        )
        table = Table(
            table_id=new_id,
            page_number=1,
            row_count=2,
            col_count=1,
            rows=[header_row, data_row],
            caption=body.caption,
            summary=body.summary,
            status=TableStatus.MANUALLY_CREATED,
            extraction_source="manual",
        )
        document.tables.append(table)

    return _table_out(table)


@router.patch("/documents/{job_id}/tables/{table_id}", response_model=TableOut)
def review_table(job_id: str, table_id: str, body: TableReviewRequest) -> TableOut:
    """Update a table's accessibility metadata.

    Applies caption, summary, header_row_indices, header_col_count, and/or
    individual cell text updates (cells list).
    header_row_indices replaces the current is_header_row assignments.
    header_col_count is the number of leading columns that are row headers (0 or 1).
    cells is a list of {row_index, col_index, text} updates applied to existing cells.
    Partial updates: omit a field to leave it unchanged.
    """
    from src.models.table import TableStatus

    document = _require_document(job_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No document for this job.")
    table = next((t for t in document.tables if t.table_id == table_id), None)
    if table is None:
        raise HTTPException(status_code=404, detail=f"No table '{table_id}' on this document.")

    with _lock:
        if body.caption is not None:
            table.caption = body.caption
        if body.summary is not None:
            table.summary = body.summary
        if body.header_row_indices is not None:
            header_set = set(body.header_row_indices)
            for row in table.rows:
                is_hdr = row.cells[0].row_index in header_set if row.cells else False
                row.is_header_row = is_hdr
                for cell in row.cells:
                    cell.is_header = cell.row_index in header_set
        if body.header_col_count is not None:
            table.header_col_count = body.header_col_count
            header_set = set(body.header_row_indices) if body.header_row_indices is not None else {
                row.cells[0].row_index for row in table.rows if row.is_header_row and row.cells
            }
            for row in table.rows:
                for cell in row.cells:
                    cell.is_row_header = (
                        cell.col_index < body.header_col_count
                        and cell.row_index not in header_set
                    )
        if body.cells is not None:
            cell_lookup = {(u.row_index, u.col_index): u.text for u in body.cells}
            for row in table.rows:
                for cell in row.cells:
                    new_text = cell_lookup.get((cell.row_index, cell.col_index))
                    if new_text is not None:
                        cell.text = new_text
        table.status = TableStatus.REVIEWED
        from src.models.lifecycle import ObjectLifecycleStatus
        table.lifecycle_status = ObjectLifecycleStatus.HUMAN_REVIEWED

    return _table_out(table)


@router.post("/documents/{job_id}/tables/{table_id}/analyze", response_model=TableOut)
def analyze_table(job_id: str, table_id: str) -> TableOut:
    """Run AI analysis on a single table (on demand).

    AI analysis is NEVER triggered automatically — only when the human
    reviewer explicitly clicks "Analyze with AI" in the Tables workspace.
    The result is stored in table.ai_suggestions and returned.  The
    reviewer must still approve/edit any suggested values; AI suggestions
    never automatically update caption/summary/header configuration.

    Returns 503 when the AI model is unavailable (weights not downloaded,
    CUDA error, etc.).  Returns 422 when the table has no cells.
    """
    from src.ai.table_analyzer import TableAnalysisRequest, TableAnalysisError, analyze_table as _analyze
    from src.models.table import TableAISuggestions

    document = _require_document(job_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No document for this job.")
    table = next((t for t in document.tables if t.table_id == table_id), None)
    if table is None:
        raise HTTPException(status_code=404, detail=f"No table '{table_id}' on this document.")
    if not table.rows:
        raise HTTPException(status_code=422, detail="Table has no rows; cannot analyze.")

    cells = [
        [cell.text for cell in row.cells]
        for row in table.rows
    ]
    header_row_count = sum(1 for row in table.rows if row.is_header_row)
    request = TableAnalysisRequest(
        table_id=table.table_id,
        page_number=table.page_number,
        row_count=table.row_count,
        col_count=table.col_count,
        header_row_count=header_row_count,
        header_col_count=table.header_col_count,
        cells=cells,
        existing_caption=table.caption,
        image_path=None,
    )

    try:
        result = _analyze(request)
    except TableAnalysisError as exc:
        logger.error("Table AI analysis failed for table {}: {}", table_id, exc)
        raise HTTPException(status_code=503, detail=f"AI analysis failed: {exc}") from exc

    with _lock:
        table.ai_suggestions = TableAISuggestions(
            table_type=result.table_type,
            suggested_caption=result.suggested_caption,
            suggested_summary=result.suggested_summary,
            header_rows_detected=result.header_rows_detected,
            header_cols_detected=result.header_cols_detected,
            warnings=result.warnings,
            confidence=result.confidence,
        )

    return _table_out(table)


@router.delete("/documents/{job_id}/tables/{table_id}", status_code=204)
def delete_table(job_id: str, table_id: str) -> None:
    """Remove a table from a document.

    Useful for discarding false-positive auto-detections or manually-
    created tables that are no longer needed.
    """
    document = _require_document(job_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No document for this job.")
    original_count = len(document.tables)
    with _lock:
        document.tables = [t for t in document.tables if t.table_id != table_id]
    if len(document.tables) == original_count:
        raise HTTPException(status_code=404, detail=f"No table '{table_id}' on this document.")


@router.get("/documents/{job_id}/headings", response_model=HeadingsResponse)
def get_headings(job_id: str) -> HeadingsResponse:
    """Return all content headings (H1–H5). Page markers (H6) are excluded."""
    document = _require_document(job_id)
    headings = [h for h in (document.headings if document else []) if not h.is_page_marker]
    headings_out = [
        HeadingOut(
            document_order=h.document_order,
            level=int(h.level),
            text=h.text,
            page_number=h.page_number,
            is_page_marker=h.is_page_marker,
            review_status=h.review_status.value,
            reviewer_note=h.reviewer_note,
        )
        for h in headings
    ]
    return HeadingsResponse(headings=headings_out)


@router.patch("/documents/{job_id}/headings/{document_order}", response_model=HeadingOut)
def review_heading(job_id: str, document_order: int, body: HeadingReviewRequest) -> HeadingOut:
    """Apply a human review action to a single heading.

    Actions:
      approve  → APPROVED; level and text unchanged unless also provided.
      reject   → REJECTED; marks as false positive heading.
    level (1–5) + text may be updated independently of action.
    Page markers (H6) are excluded from review and return 404.
    """
    document = _require_document(job_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No document for this job.")
    heading = next(
        (h for h in document.headings if h.document_order == document_order and not h.is_page_marker),
        None,
    )
    if heading is None:
        raise HTTPException(status_code=404, detail=f"No content heading at document_order {document_order}.")

    with _lock:
        if body.level is not None:
            if body.level < 1 or body.level > 5:
                raise HTTPException(status_code=422, detail="Heading level must be 1–5 (H6 reserved for page markers).")
            heading.level = HeadingLevel(body.level)
            if heading.review_status == HeadingReviewStatus.DETECTED:
                heading.review_status = HeadingReviewStatus.LEVEL_CHANGED
        if body.text is not None:
            if not body.text.strip():
                raise HTTPException(status_code=422, detail="Heading text must not be blank.")
            heading.text = body.text.strip()
        if body.action == "approve":
            heading.review_status = HeadingReviewStatus.APPROVED
        elif body.action == "reject":
            heading.review_status = HeadingReviewStatus.REJECTED
        elif body.action is not None:
            raise HTTPException(status_code=422, detail=f"Unknown action '{body.action}'. Use 'approve' or 'reject'.")
        if body.reviewer_note is not None:
            heading.reviewer_note = body.reviewer_note

    return HeadingOut(
        document_order=heading.document_order,
        level=int(heading.level),
        text=heading.text,
        page_number=heading.page_number,
        is_page_marker=heading.is_page_marker,
        review_status=heading.review_status.value,
        reviewer_note=heading.reviewer_note,
    )


@router.get("/documents/{job_id}/footnotes", response_model=FootnotesResponse)
def get_footnotes(job_id: str) -> FootnotesResponse:
    document = _require_document(job_id)
    notes = document.footnotes if document else []

    notes_out = [
        FootnoteOut(
            footnote_id=note.footnote_id,
            note_type=note.note_type.value,
            number=note.number,
            marker=note.marker,
            anchor_page_number=note.anchor_page_number,
            body=note.body,
            body_page_number=note.body_page_number,
            review_status=note.review_status.value,
            reviewer_note=note.reviewer_note,
        )
        for note in notes
    ]
    return FootnotesResponse(footnotes=notes_out)


@router.patch("/documents/{job_id}/footnotes/{footnote_id}", response_model=FootnoteOut)
def review_footnote(job_id: str, footnote_id: str, body: FootnoteReviewRequest) -> FootnoteOut:
    """Apply a human review action to a single footnote/endnote.

    Actions:
      approve → APPROVED.
      reject  → REJECTED (false positive detection).
    body (text) may be corrected; sets status to EDITED.
    """
    document = _require_document(job_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No document for this job.")
    note = next((n for n in document.footnotes if n.footnote_id == footnote_id), None)
    if note is None:
        raise HTTPException(status_code=404, detail=f"No footnote '{footnote_id}' on this document.")

    with _lock:
        if body.body is not None:
            if not body.body.strip():
                raise HTTPException(status_code=422, detail="Footnote body must not be blank.")
            note.body = body.body.strip()
            note.review_status = FootnoteReviewStatus.EDITED
        if body.action == "approve":
            note.review_status = FootnoteReviewStatus.APPROVED
        elif body.action == "reject":
            note.review_status = FootnoteReviewStatus.REJECTED
        elif body.action is not None:
            raise HTTPException(status_code=422, detail=f"Unknown action '{body.action}'. Use 'approve' or 'reject'.")
        if body.reviewer_note is not None:
            note.reviewer_note = body.reviewer_note

    return FootnoteOut(
        footnote_id=note.footnote_id,
        note_type=note.note_type.value,
        number=note.number,
        marker=note.marker,
        anchor_page_number=note.anchor_page_number,
        body=note.body,
        body_page_number=note.body_page_number,
        review_status=note.review_status.value,
        reviewer_note=note.reviewer_note,
    )


@router.get("/documents/{job_id}/metadata", response_model=MetadataOut)
def get_metadata(job_id: str) -> MetadataOut:
    """Return document metadata including reviewer-set accessibility properties."""
    document = _require_document(job_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No document for this job.")
    m = document.metadata
    return MetadataOut(
        filename=m.filename,
        page_count=m.page_count,
        image_count=m.image_count,
        language=m.language,
        title=m.title,
        author=m.author,
        subject=m.subject,
    )


@router.patch("/documents/{job_id}/metadata", response_model=MetadataOut)
def update_metadata(job_id: str, body: MetadataUpdateRequest) -> MetadataOut:
    """Update accessibility properties on the document metadata.

    These values are written into the DOCX CoreProperties on the next
    download/re-generation (language → dc:language, title → dc:title,
    author → dc:creator, subject → dc:subject).
    """
    document = _require_document(job_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No document for this job.")

    with _lock:
        if body.language is not None:
            document.metadata.language = body.language or None
        if body.title is not None:
            document.metadata.title = body.title or None
        if body.author is not None:
            document.metadata.author = body.author or None
        if body.subject is not None:
            document.metadata.subject = body.subject or None

    m = document.metadata
    return MetadataOut(
        filename=m.filename,
        page_count=m.page_count,
        image_count=m.image_count,
        language=m.language,
        title=m.title,
        author=m.author,
        subject=m.subject,
    )


@router.get("/documents/{job_id}/pages", response_model=PagesResponse)
def get_pages(job_id: str) -> PagesResponse:
    document = _require_document(job_id)
    pages = document.pages if document else []

    pages_out = [
        PageOcrInfoOut(
            page_number=page.page_number,
            page_type=page.page_type.value if page.page_type else None,
            extraction_method=page.extraction_method.value if page.extraction_method else None,
            ocr_confidence=page.ocr_confidence.value if page.ocr_confidence else None,
            has_text=bool((page.cleaned_text or page.raw_text).strip()),
            printed_label=page.printed_label,
        )
        for page in pages
    ]
    return PagesResponse(pages=pages_out)


@router.get("/documents/{job_id}/markdown", response_model=MarkdownResponse)
def get_markdown(job_id: str) -> MarkdownResponse:
    job = _require_job(job_id)
    if job.result is None or job.result.markdown_path is None or not job.result.markdown_path.is_file():
        raise HTTPException(status_code=404, detail="Markdown has not been generated for this document.")
    return MarkdownResponse(content=job.result.markdown_path.read_text(encoding="utf-8"))


# --- Reading order review (FEATURE_016B) ------------------------------------


def _block_out(block) -> BlockOut:
    return BlockOut(
        block_order=block.order,
        corrected_order=block.corrected_order,
        text=block.text[:200],
        page_number=block.page_number,
        bbox_x0=block.bbox.x0,
        bbox_y0=block.bbox.y0,
        bbox_x1=block.bbox.x1,
        bbox_y1=block.bbox.y1,
    )


@router.get("/documents/{job_id}/reading-order", response_model=ReadingOrderResponse)
def get_reading_order(job_id: str) -> ReadingOrderResponse:
    """Return pages that need reading order review.

    Includes pages with a PAGE_003 validation issue (reading order anomaly
    detected by Phase I.1) plus any page already reviewed (reading_order_status
    != UNREVIEWED). Blocks within each page are sorted by effective order
    (corrected_order when set, otherwise PyMuPDF extraction order).
    """
    from src.models.page import ReadingOrderStatus

    document = _require_document(job_id)
    if document is None:
        return ReadingOrderResponse(pages=[])

    page_003_pages = {
        issue.page_number
        for issue in document.validation_issues
        if issue.rule_id == "PAGE_003" and issue.page_number is not None
    }

    blocks_by_page: Dict[int, List] = {}
    for block in document.blocks:
        blocks_by_page.setdefault(block.page_number, []).append(block)

    result_pages = []
    for page in sorted(document.pages, key=lambda p: p.page_number):
        if page.page_number not in page_003_pages and page.reading_order_status == ReadingOrderStatus.UNREVIEWED:
            continue
        sorted_blocks = sorted(
            blocks_by_page.get(page.page_number, []),
            key=lambda b: b.corrected_order if b.corrected_order is not None else b.order,
        )
        result_pages.append(
            PageReadingOrderOut(
                page_number=page.page_number,
                reading_order_status=page.reading_order_status.value,
                blocks=[_block_out(b) for b in sorted_blocks],
            )
        )

    return ReadingOrderResponse(pages=result_pages)


@router.patch("/documents/{job_id}/pages/{page_num}/reading-order", response_model=PageReadingOrderOut)
def update_reading_order(job_id: str, page_num: int, body: ReadingOrderPatchRequest) -> PageReadingOrderOut:
    """Approve or manually reorder the text blocks on a page.

    action='approve': confirms the current block order is correct, sets
        reading_order_status=APPROVED. block_sequence is ignored.
    action='reorder': sets corrected_order on each block per block_sequence
        (a list of TextBlock.order values in the desired new reading sequence).
        Sets reading_order_status=CORRECTED. The next markdown/DOCX generation
        will sort this page's blocks by corrected_order.
    """
    from src.models.page import ReadingOrderStatus

    document = _require_document(job_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No document for this job.")

    page = next((p for p in document.pages if p.page_number == page_num), None)
    if page is None:
        raise HTTPException(status_code=404, detail=f"Page {page_num} not found.")

    page_blocks = [b for b in document.blocks if b.page_number == page_num]

    with _lock:
        if body.action == "approve":
            page.reading_order_status = ReadingOrderStatus.APPROVED
        elif body.action == "reorder":
            if not body.block_sequence:
                raise HTTPException(
                    status_code=422,
                    detail="block_sequence is required for action='reorder'.",
                )
            block_by_order = {b.order: b for b in page_blocks}
            for new_pos, orig_order in enumerate(body.block_sequence):
                block = block_by_order.get(orig_order)
                if block is not None:
                    block.corrected_order = new_pos
            page.reading_order_status = ReadingOrderStatus.CORRECTED
        else:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown action '{body.action}'. Use 'approve' or 'reorder'.",
            )

    sorted_blocks = sorted(
        page_blocks,
        key=lambda b: b.corrected_order if b.corrected_order is not None else b.order,
    )
    return PageReadingOrderOut(
        page_number=page_num,
        reading_order_status=page.reading_order_status.value,
        blocks=[_block_out(b) for b in sorted_blocks],
    )


# --- Export readiness (FEATURE_015.2 PART F) ---------------------------------


@router.get("/documents/{job_id}/export-readiness", response_model=ExportReadinessOut)
def get_export_readiness(job_id: str) -> ExportReadinessOut:
    """Return a pre-export accessibility readiness report.

    Evaluates every reviewable object category and reports whether all
    required accessibility checks have been addressed. This is the final
    gate before a document is considered ready for accessible export.

    ready=True only when all categories are complete (no outstanding
    WARNING-level issues for any category). INFO-level issues (footnotes
    detected, metadata missing, etc.) do not block readiness.

    This endpoint is non-blocking: DOCX download works regardless of
    readiness score. Use this report to guide the reviewer toward any
    remaining gaps before distributing the document.
    """
    from src.models.table import TableStatus
    from src.models.figure import AltTextStatus
    from src.models.heading import HeadingReviewStatus
    from src.models.footnote import FootnoteReviewStatus
    from src.models.page import ReadingOrderStatus

    document = _require_document(job_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No document for this job.")

    categories: dict = {}
    category_complete: list = []

    # --- Tables ---
    tables = document.tables
    table_issues = []
    table_approved = sum(
        1 for t in tables if t.status == TableStatus.REVIEWED
    )
    unreviewed = [t for t in tables if t.status == TableStatus.AUTO_DETECTED]
    if unreviewed:
        table_issues.append(f"{len(unreviewed)} auto-detected table(s) not yet reviewed")
    no_caption = [t for t in tables if not t.caption]
    if no_caption:
        table_issues.append(f"{len(no_caption)} table(s) missing accessibility caption")
    no_summary = [t for t in tables if not t.summary]
    if no_summary:
        table_issues.append(f"{len(no_summary)} table(s) missing WCAG H73 summary")
    no_headers = [t for t in tables if not any(row.is_header_row for row in t.rows)]
    if no_headers:
        table_issues.append(f"{len(no_headers)} table(s) with no header row")
    low_conf = [t for t in tables if t.status == TableStatus.AUTO_DETECTED and t.confidence < 0.7]
    if low_conf:
        table_issues.append(f"{len(low_conf)} table(s) with low detection confidence (<70%) — verify cell content")
    tables_complete = not table_issues
    category_complete.append(tables_complete)
    categories["tables"] = ReadinessCategoryOut(
        complete=tables_complete,
        total=len(tables),
        approved=table_approved,
        issues=table_issues,
    ).model_dump()

    # --- Images ---
    images = document.images
    img_issues = []
    img_approved = sum(
        1 for img in images
        if img.figure and img.figure.alt_text_status in (
            AltTextStatus.APPROVED, AltTextStatus.DECORATIVE,
            AltTextStatus.COMPLEX, AltTextStatus.REJECTED,
        )
    )
    _IMG_COMPLETE = {
        AltTextStatus.APPROVED, AltTextStatus.DECORATIVE,
        AltTextStatus.COMPLEX, AltTextStatus.REJECTED,
        AltTextStatus.SKIPPED, AltTextStatus.HUMAN_REVIEWED,
    }
    img_pending = [
        img for img in images
        if not img.extraction_failed
        and (img.figure is None or img.figure.alt_text_status not in _IMG_COMPLETE)
    ]
    if img_pending:
        img_issues.append(f"{len(img_pending)} image(s) with unreviewed alt text")
    images_complete = not img_issues
    category_complete.append(images_complete)
    categories["images"] = ReadinessCategoryOut(
        complete=images_complete,
        total=len(images),
        approved=img_approved,
        issues=img_issues,
    ).model_dump()

    # --- Headings ---
    content_headings = [h for h in document.headings if not h.is_page_marker]
    heading_issues = []
    heading_approved = sum(
        1 for h in content_headings
        if h.review_status == HeadingReviewStatus.APPROVED
    )
    from src.models.heading import HeadingLevel
    h1_headings = [h for h in content_headings if h.level == HeadingLevel.H1]
    if not h1_headings:
        heading_issues.append("No H1 heading — document title not identified")
    rejected = [h for h in content_headings if h.review_status == HeadingReviewStatus.REJECTED]
    if rejected:
        heading_issues.append(f"{len(rejected)} heading(s) marked as false positive (rejected)")
    headings_complete = not heading_issues
    category_complete.append(headings_complete)
    categories["headings"] = ReadinessCategoryOut(
        complete=headings_complete,
        total=len(content_headings),
        approved=heading_approved,
        issues=heading_issues,
    ).model_dump()

    # --- Footnotes ---
    footnotes = document.footnotes
    fn_approved = sum(
        1 for fn in footnotes if fn.review_status == FootnoteReviewStatus.APPROVED
    )
    fn_issues = []
    # Footnotes are informational — never block readiness
    fn_complete = True
    category_complete.append(fn_complete)
    categories["footnotes"] = ReadinessCategoryOut(
        complete=fn_complete,
        total=len(footnotes),
        approved=fn_approved,
        issues=fn_issues,
    ).model_dump()

    # --- Reading order ---
    page_003_pages = {
        issue.page_number
        for issue in document.validation_issues
        if issue.rule_id == "PAGE_003" and issue.page_number is not None
    }
    ro_issues = []
    ro_reviewed = sum(
        1 for p in document.pages
        if p.page_number in page_003_pages
        and p.reading_order_status != ReadingOrderStatus.UNREVIEWED
    )
    unreviewed_ro = len([
        p for p in document.pages
        if p.page_number in page_003_pages
        and p.reading_order_status == ReadingOrderStatus.UNREVIEWED
    ])
    if unreviewed_ro:
        ro_issues.append(
            f"{unreviewed_ro} page(s) with reading order anomalies not yet reviewed"
        )
    ro_complete = not ro_issues
    category_complete.append(ro_complete)
    categories["reading_order"] = ReadinessCategoryOut(
        complete=ro_complete,
        total=len(page_003_pages),
        approved=ro_reviewed,
        issues=ro_issues,
    ).model_dump()

    # --- Metadata ---
    meta = document.metadata
    meta_issues = []
    if not meta.language:
        meta_issues.append("No document language set (required for screen reader voice selection)")
    if not meta.title:
        meta_issues.append("No document title set (required for WCAG 2.4.2)")
    meta_complete = not meta_issues
    category_complete.append(meta_complete)
    categories["metadata"] = ReadinessCategoryOut(
        complete=meta_complete,
        total=2,
        approved=2 - len(meta_issues),
        issues=meta_issues,
    ).model_dump()

    complete_count = sum(1 for c in category_complete if c)
    overall_score = complete_count / len(category_complete) if category_complete else 0.0
    ready = all(category_complete)

    return ExportReadinessOut(
        ready=ready,
        overall_score=round(overall_score, 4),
        categories=categories,
    )


# --- Accessibility Readiness (generic, rule-id-prefix-based) ---------------


@router.get("/documents/{job_id}/readiness", response_model=ReadinessReportOut)
def get_readiness(job_id: str) -> ReadinessReportOut:
    """Backend-driven accessibility readiness, grouped by rule_id prefix.

    Every current and future verifier's ValidationIssues count toward this
    automatically (see src/validation/readiness.py) — the frontend renders
    whatever this reports and never needs its own rule_id -> category map.
    """
    document = _require_document(job_id)
    if document is None:
        return ReadinessReportOut(ready=True, overall_score=1.0, categories=[])

    report = compute_readiness(document)
    return ReadinessReportOut(
        ready=report.ready,
        overall_score=round(report.overall_score, 4),
        categories=[
            ReadinessCategoryDetailOut(
                category=c.category,
                label=c.label,
                error_count=c.error_count,
                warning_count=c.warning_count,
                info_count=c.info_count,
                ready=c.ready,
            )
            for c in report.categories
        ],
    )


# --- Generic Corrections (Document Merge Layer reviewer surface) -----------


def _correction_out(correction: CorrectionRecord) -> CorrectionOut:
    return CorrectionOut(
        correction_id=correction.correction_id,
        object_type=correction.object_type,
        object_id=correction.object_id,
        field=correction.field,
        problem=correction.reason or correction.field,
        current_value=correction.original_value,
        suggested_value=correction.proposed_value,
        reason=correction.reason,
        confidence=correction.confidence,
        evidence=[EvidenceItemOut(signal=e.signal, detail=e.detail) for e in correction.evidence_items],
        status=correction.status.value,
        created_at=correction.created_at,
        reviewer_notes=correction.reviewer_notes,
    )


@router.get("/documents/{job_id}/corrections", response_model=CorrectionsResponse)
def get_corrections(
    job_id: str, object_type: Optional[str] = None, status: Optional[str] = None
) -> CorrectionsResponse:
    document = _require_document(job_id)
    if document is None:
        return CorrectionsResponse(corrections=[])

    corrections = document.corrections
    if object_type is not None:
        corrections = [c for c in corrections if c.object_type == object_type]
    if status is not None:
        corrections = [c for c in corrections if c.status.value == status]

    return CorrectionsResponse(corrections=[_correction_out(c) for c in corrections])


@router.patch("/documents/{job_id}/corrections/{correction_id}", response_model=CorrectionOut)
def review_correction(job_id: str, correction_id: str, body: CorrectionActionRequest) -> CorrectionOut:
    """Apply a standardized reviewer action to one correction.

    accept        -> engine.apply_correction() mutates the document; ACCEPTED.
    reject        -> REJECTED, no mutation ("no, this was wrong").
    edit          -> proposed_value replaced from the request, then applied; EDITED.
    ignore        -> IGNORED, no mutation ("don't ask again", distinct from reject).
    needs_review  -> PENDING_REVIEW (explicit escalation).
    undo          -> engine.revert_correction() rolls back an ACCEPTED/EDITED
                     mutation via the owning verifier's revert(); REVERTED.

    This is the one endpoint every current and future verifier's reviewer
    step uses — no new per-object-type PATCH endpoint is needed again.
    """
    document = _require_document(job_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No document for this job.")
    correction = next((c for c in document.corrections if c.correction_id == correction_id), None)
    if correction is None:
        raise HTTPException(status_code=404, detail=f"No correction '{correction_id}' on this document.")

    with _lock:
        try:
            if body.action == CorrectionAction.ACCEPT:
                engine.apply_correction(document, correction)
                correction.status = CorrectionStatus.ACCEPTED
            elif body.action == CorrectionAction.REJECT:
                correction.status = CorrectionStatus.REJECTED
            elif body.action == CorrectionAction.EDIT:
                if body.proposed_value is None:
                    raise HTTPException(status_code=422, detail="proposed_value is required for action='edit'.")
                correction.proposed_value = body.proposed_value
                engine.apply_correction(document, correction)
                correction.status = CorrectionStatus.EDITED
            elif body.action == CorrectionAction.IGNORE:
                correction.status = CorrectionStatus.IGNORED
            elif body.action == CorrectionAction.NEEDS_REVIEW:
                correction.status = CorrectionStatus.PENDING_REVIEW
            elif body.action == CorrectionAction.UNDO:
                engine.revert_correction(document, correction)
                correction.status = CorrectionStatus.REVERTED
        except UnknownAssetTypeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        if body.reviewer_notes is not None:
            correction.reviewer_notes = body.reviewer_notes
        correction.reviewed_at = datetime.now(timezone.utc)

    return _correction_out(correction)


# --- Downloads ---------------------------------------------------------------


@router.get("/documents/{job_id}/download/markdown")
def download_markdown(job_id: str) -> FileResponse:
    job = _require_job(job_id)
    return _download(job.result.markdown_path if job.result else None, job.filename, ".md")


@router.get("/documents/{job_id}/download/docx")
def download_docx(job_id: str) -> FileResponse:
    """Download the DOCX.

    If any image has been reviewed (alt_text_status != PENDING_REVIEW),
    re-generate the DOCX from current in-memory state so the download
    reflects approved alt texts. The original docx_path file written
    during the pipeline run is kept as-is (it's the pre-review backup).
    """
    job = _require_job(job_id)
    if job.result is None:
        raise HTTPException(status_code=404, detail="This output was not generated for this document.")

    document = job.result.document
    needs_regen = document is not None and any(
        img.figure
        and img.figure.alt_text_status is not None
        and img.figure.alt_text_status != AltTextStatus.PENDING_REVIEW
        for img in document.images
    )

    if needs_regen and document is not None:
        from src.markdown.markdown_builder import build_markdown
        from src.docx.docx_generator import generate_docx
        tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        tmp.close()
        regen_path = Path(tmp.name)
        try:
            fresh_markdown = build_markdown(document)
            generate_docx(document, fresh_markdown, output_path=regen_path)
        except Exception as exc:
            logger.error("DOCX re-generation failed for job {}: {}", job_id, exc)
            regen_path = job.result.docx_path  # fall back to original
        stem = job.filename.rsplit(".", 1)[0] if "." in job.filename else job.filename
        return FileResponse(regen_path, filename=f"{stem}.docx")

    return _download(job.result.docx_path, job.filename, ".docx")


@router.get("/documents/{job_id}/download/report")
def download_report(job_id: str) -> FileResponse:
    job = _require_job(job_id)
    return _download(job.result.report_path if job.result else None, job.filename, ".report.json")


# --- Helpers ------------------------------------------------------------------


def _require_job(job_id: str) -> Job:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No document found for id '{job_id}'.")
    return job


def _require_document(job_id: str) -> Optional[Document]:
    job = _require_job(job_id)
    if job.status in (JobStatus.QUEUED, JobStatus.PROCESSING):
        raise HTTPException(status_code=409, detail="Document is still processing.")
    return job.result.document if job.result else None


def _download(path, filename: str, suffix: str) -> FileResponse:
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="This output was not generated for this document.")
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return FileResponse(path, filename=f"{stem}{suffix}")


def _image_out(image, job_id: str) -> ImageOut:
    """Build an ImageOut from an Image model, including AI fields."""
    figure_out = None
    if image.figure is not None:
        f = image.figure
        figure_out = FigureOut(
            label=f.label,
            number=f.number,
            caption=f.caption,
            alt_text=f.alt_text,
            alt_text_status=f.alt_text_status.value if f.alt_text_status else None,
            ai_description=f.ai_description,
            ai_purpose=f.ai_purpose,
            ai_visible_text=f.ai_visible_text,
            ai_confidence=f.ai_confidence,
            ai_warnings=list(f.ai_warnings),
        )
    return ImageOut(
        image_id=image.image_id,
        page_number=image.page_number,
        width=image.width,
        height=image.height,
        url=None if image.extraction_failed else f"/api/documents/{job_id}/images/{image.image_id}/file",
        extraction_failed=image.extraction_failed,
        figure=figure_out,
    )


def _apply_review_action(figure, action: ReviewAction, alt_text: Optional[str]) -> None:
    """Mutate a Figure in-place for a review action. Called under _lock."""
    _COMPLEX_PLACEHOLDER = "[Complex image — requires extended description]"

    if action == ReviewAction.APPROVE:
        figure.alt_text = alt_text if alt_text is not None else figure.ai_description
        figure.alt_text_status = AltTextStatus.APPROVED
    elif action == ReviewAction.REJECT:
        figure.alt_text_status = AltTextStatus.REJECTED
    elif action == ReviewAction.MARK_DECORATIVE:
        figure.alt_text = ""
        figure.alt_text_status = AltTextStatus.DECORATIVE
    elif action == ReviewAction.MARK_COMPLEX:
        figure.alt_text = _COMPLEX_PLACEHOLDER
        figure.alt_text_status = AltTextStatus.COMPLEX
    elif action == ReviewAction.SKIP:
        figure.alt_text_status = AltTextStatus.SKIPPED
    elif action == ReviewAction.EDIT:
        figure.alt_text = alt_text
        figure.alt_text_status = AltTextStatus.AI_GENERATED


def _load_nearby_text(job_id: str, image_id: str) -> List[str]:
    """Load nearby text for an image from the alt_text dataset sidecar."""
    job = get_job(job_id)
    if job is None or job.result is None or job.result.alt_text_dataset_path is None:
        return []
    dataset_path = job.result.alt_text_dataset_path
    if not dataset_path.is_file():
        return []
    try:
        data = json.loads(dataset_path.read_text(encoding="utf-8"))
        for record in data.get("images", []):
            if record.get("image_id") == image_id:
                return record.get("nearby_text", [])
    except Exception:
        pass
    return []


def _table_out(table) -> TableOut:
    rows_out = [
        TableRowOut(
            cells=[
                TableCellOut(
                    text=cell.text,
                    row_index=cell.row_index,
                    col_index=cell.col_index,
                    row_span=cell.row_span,
                    col_span=cell.col_span,
                    is_header=cell.is_header,
                    is_row_header=cell.is_row_header,
                    header_level=cell.header_level,
                )
                for cell in row.cells
            ],
            is_header_row=row.is_header_row,
        )
        for row in table.rows
    ]
    ai_out = None
    if table.ai_suggestions is not None:
        s = table.ai_suggestions
        ai_out = TableAISuggestionsOut(
            table_type=s.table_type,
            suggested_caption=s.suggested_caption,
            suggested_summary=s.suggested_summary,
            header_rows_detected=s.header_rows_detected,
            header_cols_detected=s.header_cols_detected,
            warnings=list(s.warnings),
            confidence=s.confidence,
        )
    evidence_out = [
        EvidenceSignalOut(
            name=sig["name"],
            score=sig["score"],
            weight=sig["weight"],
            note=sig["note"],
        )
        for sig in (table.evidence_signals or [])
    ]
    # Build confidence explanation from evidence bundle
    from src.tables.evidence import EvidenceBundle
    explanation = None
    if table.evidence_signals:
        bundle = EvidenceBundle.from_dict_list(table.evidence_signals)
        explanation = bundle.explanation

    return TableOut(
        table_id=table.table_id,
        page_number=table.page_number,
        row_count=table.row_count,
        col_count=table.col_count,
        rows=rows_out,
        caption=table.caption,
        summary=table.summary,
        status=table.status.value,
        extraction_source=table.extraction_source,
        header_col_count=table.header_col_count,
        confidence=table.confidence,
        ai_suggestions=ai_out,
        evidence_signals=evidence_out,
        lifecycle_status=table.lifecycle_status.value if hasattr(table.lifecycle_status, "value") else str(table.lifecycle_status),
        confidence_explanation=explanation,
    )


def _to_summary(job: Job) -> JobSummary:
    document = job.result.document if job.result else None
    issues = document.validation_issues if document else []

    return JobSummary(
        job_id=job.job_id,
        filename=job.filename,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_seconds=job.result.duration_seconds if job.result else None,
        error_message=job.error_message,
        failed_stage=job.result.failed_stage if job.result else None,
        page_count=len(document.pages) if document else None,
        image_count=len(document.images) if document else None,
        heading_count=len(document.headings) if document else None,
        footnote_count=len(document.footnotes) if document else None,
        error_count=sum(1 for i in issues if i.severity == Severity.ERROR) if document else None,
        warning_count=sum(1 for i in issues if i.severity == Severity.WARNING) if document else None,
        info_count=sum(1 for i in issues if i.severity == Severity.INFO) if document else None,
        markdown_available=bool(job.result and job.result.markdown_path and job.result.markdown_path.is_file()),
        docx_available=bool(job.result and job.result.docx_path and job.result.docx_path.is_file()),
        report_available=bool(job.result and job.result.report_path and job.result.report_path.is_file()),
        has_front_matter=bool(document and document.front_matter and document.front_matter.title is not None),
    )
