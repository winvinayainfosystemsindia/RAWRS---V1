/**
 * Typed client for the RAWRS API (src/api/ - FastAPI).
 *
 * Every type here mirrors a response shape defined in src/api/schemas.py,
 * which in turn re-exposes real src/models/ fields. Nothing in this file
 * invents a field the backend doesn't actually return.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export type JobStatus = "queued" | "processing" | "complete" | "failed";

export interface JobSummary {
  job_id: string;
  filename: string;
  status: JobStatus;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  error_message: string | null;
  failed_stage: string | null;
  page_count: number | null;
  image_count: number | null;
  heading_count: number | null;
  footnote_count: number | null;
  error_count: number | null;
  warning_count: number | null;
  info_count: number | null;
  markdown_available: boolean;
  docx_available: boolean;
  report_available: boolean;
  has_front_matter: boolean;
  document_version: number | null;
  markdown_generated_at_version: number | null;
  docx_generated_at_version: number | null;
}

export interface BoundingBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export type Severity = "error" | "warning" | "info";

export type ValidationIssueStatus = "open" | "ignored" | "deferred";

export interface ValidationIssue {
  issue_id: string;
  severity: Severity;
  rule_id: string;
  message: string;
  page_number: number | null;
  suggested_action: string | null;
  status: ValidationIssueStatus;
  reviewed_at: string | null;
}

export interface ValidationIssueActionRequest {
  action: "ignore" | "defer" | "reopen";
}

export interface ValidationResponse {
  issues: ValidationIssue[];
  error_count: number;
  warning_count: number;
  info_count: number;
}

export type AltTextStatus =
  | "pending_review"
  | "human_reviewed"
  | "ai_generated"
  | "approved"
  | "rejected"
  | "decorative"
  | "complex"
  | "skipped";

export type ReviewAction =
  | "approve"
  | "reject"
  | "mark_decorative"
  | "mark_complex"
  | "skip"
  | "edit";

export interface Figure {
  label: string | null;
  number: number | null;
  caption: string | null;
  alt_text: string | null;
  alt_text_status: AltTextStatus | null;
  // AI structured response — null until generate-alt-text is called
  ai_description: string | null;
  ai_purpose: string | null;
  ai_visible_text: string | null;
  ai_confidence: number | null;
  ai_warnings: string[];
}

export interface ImageItem {
  image_id: string;
  page_number: number;
  width: number | null;
  height: number | null;
  url: string | null;
  extraction_failed: boolean;
  figure: Figure | null;
  bbox: BoundingBox | null;
}

export interface ImagesResponse {
  images: ImageItem[];
}

export type NoteType = "footnote" | "endnote";
export type FootnoteReviewStatus = "detected" | "approved" | "edited" | "rejected";

export interface FootnoteItem {
  footnote_id: string | null;
  note_type: NoteType;
  number: number;
  marker: string;
  anchor_page_number: number;
  body: string;
  body_page_number: number;
  review_status: FootnoteReviewStatus;
  reviewer_note: string | null;
  anchor_text: string | null;
  body_source_text: string | null;
}

export interface FootnotesResponse {
  footnotes: FootnoteItem[];
}

export interface FootnoteReviewRequest {
  body?: string | null;
  action?: "approve" | "reject" | null;
  reviewer_note?: string | null;
}

export type HeadingReviewStatus = "detected" | "approved" | "level_changed" | "rejected";

export interface HeadingItem {
  document_order: number;
  level: number;
  text: string;
  page_number: number;
  is_page_marker: boolean;
  review_status: HeadingReviewStatus;
  reviewer_note: string | null;
  bbox: BoundingBox | null;
  source_line: number | null;
}

export interface HeadingsResponse {
  headings: HeadingItem[];
}

export interface HeadingReviewRequest {
  level?: number | null;
  text?: string | null;
  action?: "approve" | "reject" | null;
  reviewer_note?: string | null;
}

export interface MetadataItem {
  filename: string;
  page_count: number;
  image_count: number;
  language: string | null;
  title: string | null;
  author: string | null;
  subject: string | null;
}

export interface MetadataUpdateRequest {
  language?: string | null;
  title?: string | null;
  author?: string | null;
  subject?: string | null;
}

export type PageType = "direct_text" | "ocr_required";
export type ExtractionMethod = "direct_text_extraction" | "ocr_pending" | "docling" | "surya";
export type OcrConfidence = "high" | "medium" | "low";

export interface PageOcrInfo {
  page_number: number;
  page_type: PageType | null;
  extraction_method: ExtractionMethod | null;
  ocr_confidence: OcrConfidence | null;
  has_text: boolean;
  printed_label: string | null;
}

export interface PagesResponse {
  pages: PageOcrInfo[];
}

export interface MarkdownResponse {
  content: string;
}

export type TableStatus = "auto_detected" | "manually_created" | "reviewed";

export interface TableAISuggestions {
  table_type: string | null;
  suggested_caption: string | null;
  suggested_summary: string | null;
  header_rows_detected: number;
  header_cols_detected: number;
  warnings: string[];
  confidence: number;
}

export interface TableCell {
  text: string;
  row_index: number;
  col_index: number;
  row_span: number;
  col_span: number;
  is_header: boolean;
  is_row_header: boolean;
  header_level: number;
}

export interface TableRow {
  cells: TableCell[];
  is_header_row: boolean;
}

export interface TableItem {
  table_id: string;
  page_number: number;
  row_count: number;
  col_count: number;
  rows: TableRow[];
  caption: string | null;
  summary: string | null;
  status: TableStatus;
  extraction_source: string;
  header_col_count: number;
  confidence: number;
  ai_suggestions: TableAISuggestions | null;
  bbox: BoundingBox | null;
  source_line: number | null;
}

export interface TablesResponse {
  tables: TableItem[];
}

export interface CellUpdate {
  row_index: number;
  col_index: number;
  text: string;
}

export interface TableReviewRequest {
  caption?: string | null;
  summary?: string | null;
  header_row_indices?: number[] | null;
  header_col_count?: number | null;
  cells?: CellUpdate[] | null;
}

export type ListType = "bullet" | "numbered";

export interface ListItemEntry {
  text: string;
  level: number;
}

export interface ListItem {
  id: string | null;
  list_type: ListType;
  items: ListItemEntry[];
  page_number: number;
  document_order: number;
  source_line: number | null;
  bbox: BoundingBox | null;
}

export interface ListsResponse {
  lists: ListItem[];
}

export interface CalloutItem {
  id: string | null;
  callout_type: string;
  label: string;
  heading_id: string | null;
  page_number: number | null;
  document_order: number;
  source_line: number | null;
  bbox: BoundingBox | null;
}

export interface CalloutsResponse {
  callouts: CalloutItem[];
}

export interface UploadResponse {
  job_id: string;
  filename: string;
  status: JobStatus;
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // response body wasn't JSON - keep statusText
    }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  baseUrl: API_BASE_URL,

  async uploadDocument(
    file: File,
    mmdFile?: File,
    imageFiles?: File[],
    enableOcr = true
  ): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append("file", file);
    if (mmdFile) {
      formData.append("mmd_file", mmdFile);
    }
    for (const imageFile of imageFiles ?? []) {
      formData.append("image_files", imageFile);
    }
    return request<UploadResponse>(`/api/documents?enable_ocr=${enableOcr}`, {
      method: "POST",
      body: formData,
    });
  },

  listDocuments(): Promise<JobSummary[]> {
    return request<JobSummary[]>("/api/documents");
  },

  getDocument(jobId: string): Promise<JobSummary> {
    return request<JobSummary>(`/api/documents/${jobId}`);
  },

  getValidation(jobId: string): Promise<ValidationResponse> {
    return request<ValidationResponse>(`/api/documents/${jobId}/validation`);
  },

  getImages(jobId: string): Promise<ImagesResponse> {
    return request<ImagesResponse>(`/api/documents/${jobId}/images`);
  },

  getFootnotes(jobId: string): Promise<FootnotesResponse> {
    return request<FootnotesResponse>(`/api/documents/${jobId}/footnotes`);
  },

  getLists(jobId: string): Promise<ListsResponse> {
    return request<ListsResponse>(`/api/documents/${jobId}/lists`);
  },

  getCallouts(jobId: string): Promise<CalloutsResponse> {
    return request<CalloutsResponse>(`/api/documents/${jobId}/callouts`);
  },

  sourcePdfUrl(jobId: string): string {
    return `${API_BASE_URL}/api/documents/${jobId}/source-pdf`;
  },

  getPages(jobId: string): Promise<PagesResponse> {
    return request<PagesResponse>(`/api/documents/${jobId}/pages`);
  },

  getMarkdown(jobId: string): Promise<MarkdownResponse> {
    return request<MarkdownResponse>(`/api/documents/${jobId}/markdown`);
  },

  imageUrl(jobId: string, imageId: string): string {
    return `${API_BASE_URL}/api/documents/${jobId}/images/${imageId}/file`;
  },

  downloadUrl(jobId: string, kind: "markdown" | "docx" | "report"): string {
    return `${API_BASE_URL}/api/documents/${jobId}/download/${kind}`;
  },

  generateAltText(jobId: string, imageId: string): Promise<ImageItem> {
    return request<ImageItem>(
      `/api/documents/${jobId}/images/${imageId}/generate-alt-text`,
      { method: "POST" }
    );
  },

  reviewImage(
    jobId: string,
    imageId: string,
    action: ReviewAction,
    altText?: string
  ): Promise<ImageItem> {
    return request<ImageItem>(`/api/documents/${jobId}/images/${imageId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, alt_text: altText ?? null }),
    });
  },

  bulkReviewImages(
    jobId: string,
    imageIds: string[],
    action: ReviewAction
  ): Promise<ImagesResponse> {
    return request<ImagesResponse>(`/api/documents/${jobId}/images/bulk-action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_ids: imageIds, action }),
    });
  },

  getTables(jobId: string): Promise<TablesResponse> {
    return request<TablesResponse>(`/api/documents/${jobId}/tables`);
  },

  reviewTable(
    jobId: string,
    tableId: string,
    body: TableReviewRequest
  ): Promise<TableItem> {
    return request<TableItem>(`/api/documents/${jobId}/tables/${tableId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  createTable(jobId: string, body: TableReviewRequest): Promise<TableItem> {
    return request<TableItem>(`/api/documents/${jobId}/tables`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  async deleteTable(jobId: string, tableId: string): Promise<void> {
    const response = await fetch(
      `${API_BASE_URL}/api/documents/${jobId}/tables/${tableId}`,
      { method: "DELETE" }
    );
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = await response.json();
        if (typeof body?.detail === "string") detail = body.detail;
      } catch { /* empty body */ }
      throw new ApiError(response.status, detail);
    }
  },

  analyzeTable(jobId: string, tableId: string): Promise<TableItem> {
    return request<TableItem>(
      `/api/documents/${jobId}/tables/${tableId}/analyze`,
      { method: "POST" }
    );
  },

  getHeadings(jobId: string): Promise<HeadingsResponse> {
    return request<HeadingsResponse>(`/api/documents/${jobId}/headings`);
  },

  reviewHeading(
    jobId: string,
    documentOrder: number,
    body: HeadingReviewRequest
  ): Promise<HeadingItem> {
    return request<HeadingItem>(`/api/documents/${jobId}/headings/${documentOrder}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  reviewFootnote(
    jobId: string,
    footnoteId: string,
    body: FootnoteReviewRequest
  ): Promise<FootnoteItem> {
    return request<FootnoteItem>(`/api/documents/${jobId}/footnotes/${footnoteId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  getMetadata(jobId: string): Promise<MetadataItem> {
    return request<MetadataItem>(`/api/documents/${jobId}/metadata`);
  },

  updateMetadata(jobId: string, body: MetadataUpdateRequest): Promise<MetadataItem> {
    return request<MetadataItem>(`/api/documents/${jobId}/metadata`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  getReadingOrder(jobId: string): Promise<ReadingOrderResponse> {
    return request<ReadingOrderResponse>(`/api/documents/${jobId}/reading-order`);
  },

  updateReadingOrder(
    jobId: string,
    pageNum: number,
    body: ReadingOrderPatchRequest
  ): Promise<PageReadingOrder> {
    return request<PageReadingOrder>(
      `/api/documents/${jobId}/pages/${pageNum}/reading-order`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    );
  },

  getCorrections(
    jobId: string,
    filters?: { objectType?: string; status?: string }
  ): Promise<CorrectionsResponse> {
    const params = new URLSearchParams();
    if (filters?.objectType) params.set("object_type", filters.objectType);
    if (filters?.status) params.set("status", filters.status);
    const qs = params.toString();
    return request<CorrectionsResponse>(
      `/api/documents/${jobId}/corrections${qs ? `?${qs}` : ""}`
    );
  },

  reviewCorrection(
    jobId: string,
    correctionId: string,
    body: CorrectionActionRequest
  ): Promise<CorrectionItem> {
    return request<CorrectionItem>(
      `/api/documents/${jobId}/corrections/${correctionId}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    );
  },

  reviewValidationIssue(
    jobId: string,
    issueId: string,
    body: ValidationIssueActionRequest
  ): Promise<ValidationIssue> {
    return request<ValidationIssue>(
      `/api/documents/${jobId}/validation-issues/${issueId}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    );
  },

  getReadiness(jobId: string): Promise<ReadinessReport> {
    return request<ReadinessReport>(`/api/documents/${jobId}/readiness`);
  },

  getAiStatus(): Promise<AiStatus> {
    return request<AiStatus>("/api/ai/status");
  },

  getPageLabels(jobId: string): Promise<PageLabelsResponse> {
    return request<PageLabelsResponse>(`/api/documents/${jobId}/page-labels`);
  },

  overridePageLabel(jobId: string, pageNum: number, label: string): Promise<PageLabel> {
    return request<PageLabel>(`/api/documents/${jobId}/page-labels/${pageNum}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "override", label }),
    });
  },

  resetPageLabel(jobId: string, pageNum: number): Promise<PageLabel> {
    return request<PageLabel>(`/api/documents/${jobId}/page-labels/${pageNum}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "reset" }),
    });
  },

  setPageLabelSections(
    jobId: string,
    sections: PageLabelSectionRequest[]
  ): Promise<PageLabelsResponse> {
    return request<PageLabelsResponse>(`/api/documents/${jobId}/page-label-sections`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sections }),
    });
  },
};

// --- Generic Corrections (Document Merge Layer reviewer surface) ----------

export type CorrectionAction =
  | "accept"
  | "reject"
  | "edit"
  | "ignore"
  | "needs_review"
  | "undo";

export interface EvidenceSignal {
  name: string;
  score: number;
  weight: number;
  note: string;
}

export interface CorrectionItem {
  correction_id: string;
  object_type: string;
  object_id: string | null;
  field: string;
  problem: string;
  current_value: string;
  suggested_value: string;
  reason: string;
  confidence: number | null;
  evidence: EvidenceSignal[];
  status: string;
  created_at: string;
  reviewer_notes: string | null;
  rule_id: string | null;
  severity: string | null;
  page_number: number | null;
}

export interface CorrectionsResponse {
  corrections: CorrectionItem[];
}

export interface CorrectionActionRequest {
  action: CorrectionAction;
  proposed_value?: string | null;
  reviewer_notes?: string | null;
}

// --- Accessibility Readiness (backend-driven) ------------------------------

export interface ReadinessCategoryDetail {
  category: string;
  label: string;
  error_count: number;
  warning_count: number;
  info_count: number;
  ready: boolean;
}

export interface ReadinessReport {
  ready: boolean;
  overall_score: number;
  categories: ReadinessCategoryDetail[];
}

export type ReadingOrderStatus = "unreviewed" | "approved" | "corrected";

export interface BlockItem {
  block_order: number;
  corrected_order: number | null;
  text: string;
  page_number: number;
  bbox_x0: number;
  bbox_y0: number;
  bbox_x1: number;
  bbox_y1: number;
}

export interface PageReadingOrder {
  page_number: number;
  reading_order_status: ReadingOrderStatus;
  blocks: BlockItem[];
}

export interface ReadingOrderResponse {
  pages: PageReadingOrder[];
}

export interface ReadingOrderPatchRequest {
  action: "approve" | "reorder";
  block_sequence?: number[];
}

// --- AI status --------------------------------------------------------------

export interface AiStatus {
  provider: string;
  available: boolean;
  unavailable_reason: string | null;
  capabilities: string[];
}

// --- Page Label Manager (FEATURE_018) ---------------------------------------

export type PageLabelStatus = "detected" | "approved" | "overridden";
export type PageLabelStyle = "arabic" | "roman_lower" | "roman_upper" | "none";

export interface PageLabel {
  page_number: number;
  printed_label: string | null;
  label_confidence: number | null;
  label_conflict: boolean;
  page_label: string | null;
  page_label_status: PageLabelStatus;
}

export interface PageLabelSection {
  start_page: number;
  end_page: number;
  style: PageLabelStyle;
  start_number: number;
  prefix: string;
  suffix: string;
}

export type PageLabelSectionRequest = PageLabelSection;

export interface PageLabelsResponse {
  pages: PageLabel[];
  sections: PageLabelSection[];
}

export { ApiError };
