# FEATURE_012 Design — AI-Assisted Image Remediation & Human Review Workspace

**Status:** Design approved — ready for implementation  
**Date:** 2026-06-28  
**Prerequisites cleared:** XML sanitization (2026-06-23), figure integrity audit (checklist audit), reading-flow defect (2026-06-25)

---

## 1. Scope and non-goals

**In scope:**
- New `AltTextStatus` values to represent the review workflow state machine
- New AI response fields on `Figure` (description / purpose / visible text / confidence / warnings)
- Backend: 3 new API endpoints (generate, patch review, bulk action)
- AI integration module: `src/ai/alt_text_generator.py` with Qwen2.5-VL behind a clean interface
- Frontend: ImageCard with action buttons, ImageDetailPanel, BulkActions toolbar
- Approved alt text flowing into existing Markdown and DOCX output
- DOCX image alignment detection (center vs left/right from bbox)

**Out of scope / deferred (with rationale):**
- Table remediation — does not reuse image work; entirely different pipeline branch; deferred. See Section 9.
- Long-description / `aria-describedby` DOCX wiring — deferred until a Word native footnote strategy is decided (same blocker as DOCX footnotes)
- Subscripts / equations / multi-column — separate features with their own gating
- Dataset re-training loop — dataset collection already exists (`alt_text_dataset/`); training is out of Phase 1 scope

---

## 2. Model changes — `src/models/figure.py`

### 2a. AltTextStatus extensions (additive only, backward-compatible)

```python
class AltTextStatus(str, Enum):
    # Existing values — unchanged semantics
    PENDING_REVIEW = "pending_review"   # placeholder set at extraction, no AI yet
    HUMAN_REVIEWED = "human_reviewed"   # legacy terminal state (kept for compat)

    # New values — review workflow states
    AI_GENERATED = "ai_generated"       # AI ran, human hasn't acted yet
    APPROVED = "approved"               # human approved (possibly after editing)
    REJECTED = "rejected"               # human rejected, available for regeneration
    DECORATIVE = "decorative"           # human confirmed: no alt text needed
    COMPLEX = "complex"                 # human flagged: needs long description
    SKIPPED = "skipped"                 # human explicitly deferred this image
```

Adding new enum values is backward-compatible: existing code that reads PENDING_REVIEW or HUMAN_REVIEWED continues to work. The frontend's `AltTextStatusBadge` component needs new cases for the new values.

### 2b. New fields on Figure

```python
class Figure(BaseModel):
    # ... existing fields unchanged ...

    # AI structured response — all None until generate-alt-text is called
    ai_description: Optional[str] = None
    ai_purpose: Optional[str] = None
    ai_visible_text: Optional[str] = None
    ai_confidence: Optional[float] = None   # 0.0–1.0; None = not yet generated
    ai_warnings: List[str] = Field(default_factory=list)
```

**How alt_text is managed during the workflow:**
- `PENDING_REVIEW`: `alt_text` = placeholder string (set by image_extractor.py, unchanged)
- `AI_GENERATED`: `alt_text` = still the placeholder; `ai_description` holds AI text (human hasn't approved yet)
- `APPROVED`: `alt_text` = whatever text the human approved or edited (may differ from `ai_description`)
- `REJECTED`: `alt_text` = still the placeholder; `ai_description` still holds the rejected text
- `DECORATIVE`: `alt_text` = `""` (empty string — intentional, means "decorative, no description")
- `COMPLEX`: `alt_text` = `"[Complex image — requires extended description]"` (signal for DOCX generator)
- `SKIPPED`: `alt_text` = still the placeholder (reviewer chose not to act now)

**Why `alt_text` is the approved/final value and `ai_description` is the AI draft:**  
The Markdown builder and DOCX generator both already consume `Figure.alt_text`. No change is needed in those outputs — they will automatically use the approved text once the reviewer approves. The AI description is a draft, never automatically promoted.

---

## 3. New API module — `src/ai/alt_text_generator.py`

### 3a. Interface (stable regardless of model choice)

```python
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class AltTextRequest:
    image_path: str
    caption: Optional[str]
    figure_label: Optional[str]
    nearby_text: List[str]     # up to 5 nearby TextBlock texts from the PDF
    page_number: int

@dataclass
class AltTextResult:
    description: str
    purpose: str
    visible_text: str
    confidence: float           # 0.0–1.0
    warnings: List[str] = field(default_factory=list)

def generate_alt_text(request: AltTextRequest) -> AltTextResult:
    """Invoke the local vision model and return a structured result.
    
    Raises AltTextGenerationError on any failure (model not loaded,
    image unreadable, inference timeout, parse failure).
    """
    ...

class AltTextGenerationError(Exception):
    pass
```

### 3b. Qwen2.5-VL invocation

**New dependency:** `transformers`, `qwen-vl-utils`, `torch` (or `torchvision`). Add to `requirements.txt`. Note: this is a large download; first run requires internet access for model weights (same category as Docling/Surya model downloads — a setup-time prerequisite, not a per-document network call).

**Prompt template:**
```
You are an accessibility expert writing alt text for a document figure.

Figure context:
- Label: {figure_label or "Unknown"}
- Caption: {caption or "None provided"}  
- Nearby document text: {nearby_text joined with "; "}

Respond in exactly this format (no other text):
DESCRIPTION: <one or two sentences describing what the image shows>
PURPOSE: <why this image appears in the document — what it illustrates or supports>
VISIBLE_TEXT: <any text visible in the image itself, or "None">
CONFIDENCE: <a number from 0.0 to 1.0>
WARNINGS: <comma-separated concerns about image quality or complexity, or "None">
```

**Parse logic:** Split on newlines, extract each `KEY: value` pair. Any parse failure raises `AltTextGenerationError` with a descriptive message. Confidence clamped to `[0.0, 1.0]`. WARNINGS split on comma and stripped; if "None", stored as `[]`.

**Model loading:** Load once at first call and cache in module-level variable. Not loaded at import time (import is cheap; model load is expensive). Use `torch.no_grad()` for inference.

### 3c. Stub for testing

When `RAWRS_AI_STUB=1` environment variable is set (or Qwen2.5-VL is not installed), `generate_alt_text` returns a deterministic fake result based on the image_id. This lets all API and frontend tests run without the model installed. Test fixtures use this stub.

---

## 4. API changes — `src/api/schemas.py`

### 4a. Extended FigureOut

```python
class FigureOut(BaseModel):
    # Existing fields — unchanged
    label: Optional[str] = None
    number: Optional[int] = None
    caption: Optional[str] = None
    alt_text: Optional[str] = None
    alt_text_status: Optional[str] = None

    # New AI fields — all None until generate-alt-text called
    ai_description: Optional[str] = None
    ai_purpose: Optional[str] = None
    ai_visible_text: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_warnings: List[str] = Field(default_factory=list)
```

Consumers that don't know about these fields simply ignore them (OpenAPI additive extension rule). Existing `GET /images` response still validates.

### 4b. New request schemas

```python
class ReviewAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    MARK_DECORATIVE = "mark_decorative"
    MARK_COMPLEX = "mark_complex"
    SKIP = "skip"
    EDIT = "edit"

class ImageReviewRequest(BaseModel):
    action: ReviewAction
    alt_text: Optional[str] = None  # required when action == "edit" or "approve" with custom text

class BulkActionRequest(BaseModel):
    image_ids: List[str]
    action: ReviewAction             # approve/reject/mark_decorative/skip only (not edit)
```

---

## 5. API changes — `src/api/routes.py`

### 5a. POST generate-alt-text

```python
@router.post("/documents/{job_id}/images/{image_id}/generate-alt-text", response_model=ImageOut)
def generate_image_alt_text(job_id: str, image_id: str) -> ImageOut:
```

Logic:
1. `_require_document(job_id)` — 404 if job missing, 409 if still processing
2. Find `image` in `document.images` — 404 if not found
3. If `image.extraction_failed` or `image.file_path` missing/not on disk — 422
4. Build `AltTextRequest` from image fields (caption from figure, nearby_text from dataset JSON if available, else `[]`)
5. Call `generate_alt_text(request)` — wrap in try/except `AltTextGenerationError`, return 503 on failure
6. Under `_lock`: mutate `image.figure.ai_description`, `.ai_purpose`, `.ai_visible_text`, `.ai_confidence`, `.ai_warnings`, `.alt_text_status = AltTextStatus.AI_GENERATED`
7. Return updated `ImageOut`

**NOTE:** This call blocks until the model produces output. For MVP, the frontend should show a spinner and tolerate a 10–30 second response time. No job-queue abstraction needed — this is a deliberate per-image on-demand call, not a background batch.

**Nearby text loading:** The alt_text dataset JSON file (one JSON-Lines file per PDF, written by `phase1_pipeline.py`) contains a `nearby_text` field per image. Route handler reads this file, finds the entry matching `image_id`, and extracts `nearby_text`. If the dataset file is missing or the entry is not found, `nearby_text = []` (graceful degradation, not an error).

### 5b. PATCH review

```python
@router.patch("/documents/{job_id}/images/{image_id}", response_model=ImageOut)
def review_image(job_id: str, image_id: str, body: ImageReviewRequest) -> ImageOut:
```

Logic — mutation table:

| action | alt_text_status | alt_text |
|---|---|---|
| approve (no custom text) | APPROVED | `ai_description` (the current AI text) |
| approve (with alt_text) | APPROVED | `body.alt_text` |
| reject | REJECTED | unchanged (stays as placeholder or prior value) |
| mark_decorative | DECORATIVE | `""` |
| mark_complex | COMPLEX | `"[Complex image — requires extended description]"` |
| skip | SKIPPED | unchanged |
| edit | AI_GENERATED | `body.alt_text` (stores edited text in `alt_text`; keeps AI draft in `ai_description`) |

Validation: `action == "approve" or "edit"` with `body.alt_text` = empty string → 422 ("Alt text cannot be empty for approve/edit; use mark_decorative if intentionally empty").

### 5c. POST bulk-action

```python
@router.post("/documents/{job_id}/images/bulk-action", response_model=ImagesResponse)
def bulk_review_images(job_id: str, body: BulkActionRequest) -> ImagesResponse:
```

Applies the same mutation logic as PATCH review to each listed image_id. Returns all updated images (not just the ones in `image_ids`). Unknown image_ids are silently skipped (not an error — the list may have been built from stale frontend state).

---

## 6. In-memory mutation pattern

All three new endpoints mutate `job.result.document.images[i].figure` in-place. Pattern:

```python
with _lock:
    job = get_job(job_id)
    image = next((img for img in job.result.document.images if img.image_id == image_id), None)
    # ... mutate image.figure fields ...
```

Pydantic v1 models are mutable by default (no `Config.frozen = True` on Figure or Image). This pattern is safe under the existing `_lock` — the same lock already used for job status updates.

**Persistence note:** Since job state is in-memory only, review actions do not survive a process restart. This is consistent with the "no databases" constraint and the existing limitation that "jobs do not survive a restart." It is explicitly accepted as a known limitation, consistent with `KNOWN_LIMITATIONS.md`'s framing of the platform layer as deliberately minimal.

---

## 7. Frontend changes

### 7a. `frontend/lib/api.ts` additions

```typescript
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
  // existing fields
  label: string | null;
  number: number | null;
  caption: string | null;
  alt_text: string | null;
  alt_text_status: AltTextStatus | null;
  // new fields
  ai_description: string | null;
  ai_purpose: string | null;
  ai_visible_text: string | null;
  ai_confidence: number | null;
  ai_warnings: string[];
}

// New API methods:
api.generateAltText(jobId: string, imageId: string): Promise<ImageItem>
api.reviewImage(jobId: string, imageId: string, action: ReviewAction, altText?: string): Promise<ImageItem>
api.bulkReviewImages(jobId: string, imageIds: string[], action: ReviewAction): Promise<ImagesResponse>
```

### 7b. `frontend/components/Badge.tsx` — extend AltTextStatusBadge

New badge colours:
- `ai_generated` → blue "AI generated — review needed"
- `approved` → green "Approved"
- `rejected` → red "Rejected"
- `decorative` → gray "Decorative"
- `complex` → amber "Complex — needs long description"
- `skipped` → gray "Skipped"

### 7c. `frontend/components/ImageCard.tsx` (NEW — replaces inline `<li>` in ImageGrid)

A single card component (extracts current ImageGrid `<li>` content + adds actions).

Props: `image: ImageItem`, `isSelected: boolean`, `onSelect: () => void`, `onActionComplete: (updated: ImageItem) => void`

Card body:
- Image preview (existing)
- Caption (existing)
- AltTextStatusBadge (existing, now with new values)
- Action buttons (NEW) — shown based on current status:
  - `PENDING_REVIEW`: "Generate AI Alt Text" button only
  - `AI_GENERATED`: "Approve" (green), "Edit", "Reject" (red), "Mark Decorative", "Skip"
  - `APPROVED`: "Re-generate", "Edit", "Mark Decorative"
  - `REJECTED`: "Re-generate", "Mark Decorative", "Skip"
  - `DECORATIVE`: "Un-mark" (reverts to PENDING_REVIEW), "Generate AI Alt Text"
  - `COMPLEX`: "Edit", "Generate AI Alt Text"
  - `SKIPPED`: "Generate AI Alt Text", "Mark Decorative"

Button loading state: while a network call is in-flight for this card, show a spinner and disable all buttons on this card only.

### 7d. `frontend/components/ImageDetailPanel.tsx` (NEW)

Shown to the right of (or below on mobile) the image grid when an image is selected.

Sections:
1. **Preview** — large image (same `resolveImageUrl` pattern)
2. **Figure info** — label, number, page number, caption
3. **Alt text** — current `alt_text` value in a textarea (editable); submit button sends PATCH with action="edit"
4. **AI analysis** (shown when `ai_description != null`) — Description, Purpose, Visible Text, Confidence (as a percentage bar), Warnings (as a warning list)
5. **Actions** — same buttons as ImageCard but with more room; includes "Approve this text" (uses the textarea's current content)
6. **Close** button — deselects the image

### 7e. `frontend/components/BulkActions.tsx` (NEW)

Appears above the image grid when 1+ images are selected via checkbox.

Props: `selectedIds: string[]`, `onActionComplete: (updated: ImageItem[]) => void`

Contains: "Approve All", "Mark All Decorative", "Skip All", "Reject All" buttons. Checkbox for select-all. Shows count of selected images. Each button calls `api.bulkReviewImages(...)`.

### 7f. Changes to `frontend/components/ImageGrid.tsx`

Replace the current grid's `<li>` inline content with `<ImageCard>` components. Add `selectedImageId` state and a side-by-side layout (grid left, detail panel right when selected). Add checkbox column.

### 7g. Changes to `frontend/app/documents/[id]/DocumentWorkspace.tsx`

The `images` state array is mutated locally when `onActionComplete` fires:

```typescript
function handleImageUpdated(updated: ImageItem) {
  setResults(prev => {
    if (!prev) return prev;
    return {
      ...prev,
      images: prev.images.map(img =>
        img.image_id === updated.image_id ? updated : img
      ),
    };
  });
}
```

No additional polling required — the backend mutation is synchronous, and the returned `ImageOut` is the canonical updated state.

---

## 8. Output flow — approved alt text to Markdown and DOCX

**No changes needed in `markdown_builder.py` or `docx_generator.py`.**

Both already read `image.figure.alt_text`. When the reviewer approves text, the in-memory `Figure.alt_text` is updated (Section 6 above). The next time the user downloads the DOCX or Markdown, the endpoint reads from the current in-memory state, which now has the approved text.

**DOCX re-generation:** The current `/download/docx` endpoint serves a static file written during the pipeline run. That file was generated before any review actions. Two approaches:

A. **Re-generate DOCX on demand** (recommended): `GET /download/docx` checks whether any images have been reviewed since the initial run, and if so, calls `build_docx(document)` fresh into a temp file and serves that. Simplest signal: check if any `figure.alt_text_status` in `document.images` is not `PENDING_REVIEW`.

B. **Always regenerate** (simpler, slightly slower): Always call `build_docx(document)` in the download handler. Since DOCX generation is fast (< 1s for typical documents), this is acceptable.

**Recommendation: Option B.** Avoids a staleness check and ensures the download always reflects the current review state. The static `.docx_path` written during the pipeline run becomes the original/pre-review backup.

**DOCX alignment:** Detect image alignment from `Image.bbox` and set the paragraph alignment accordingly in `docx_generator.py`:

```python
def _detect_alignment(image: Image, page_width_pt: float) -> WD_ALIGN_PARAGRAPH:
    if image.bbox is None or page_width_pt <= 0:
        return WD_ALIGN_PARAGRAPH.CENTER   # safe default
    image_center = image.bbox.x + image.bbox.width / 2
    margin = page_width_pt * 0.1
    if abs(image_center - page_width_pt / 2) < margin:
        return WD_ALIGN_PARAGRAPH.CENTER
    return WD_ALIGN_PARAGRAPH.LEFT if image_center < page_width_pt / 2 else WD_ALIGN_PARAGRAPH.RIGHT
```

Page width is available from `Document.pages[i].width_pt` — add `width_pt: Optional[float] = None` to the `Page` model and populate it from `pdf_page.rect.width` in `pdf_parser.py` or `structure_detector.py`. This is a 3-line addition.

**DOCX decorative image handling:** When `alt_text_status == DECORATIVE` (i.e., `alt_text == ""`), set the DOCX `<pic:cNvPr descr="">` attribute to empty string AND add `<pic:cNvPr title="">`. Screen readers treat an empty `alt` as decorative. This is already possible with the existing `_add_image_alt_text()` helper.

---

## 9. Table remediation design review (no implementation)

**Question:** Should table detection and remediation be implemented as part of FEATURE_012, since it shares the "image remediation" framing?

**Finding:** No. Image remediation is about visual bitmap content requiring a vision model. Table remediation is about structured text layout requiring a layout/structure model. The only shared concern is the DOCX output step; the detection pipeline, review UI, and accessibility output are entirely different:

- Image → vision model → alt text → `<pic:cNvPr descr="">` in DOCX
- Table → layout analysis → cell text extraction → `<w:tbl>` element in DOCX

There is no code sharing between these two paths. Building table remediation now would add a full new pipeline stage, a new model (`Table`), a new frontend tab, and new DOCX generation logic — all unrelated to image work.

**Recommended path for table remediation (future):**
1. Use PyMuPDF's `page.find_tables()` (available in PyMuPDF ≥ 1.23.0 — check installed version)
2. Add `Table` model to `src/models/`
3. Run table detection in a new Phase T stage (after structure_detector, before heading_detector)
4. Render tables as `<w:tbl>` in DOCX and as Markdown pipe tables in Markdown output

**Verdict: Defer table remediation entirely. Do not start without a separate scope decision.**

---

## 10. Blast radius — what stays untouched

The following files are NOT modified by FEATURE_012:

- `src/parser/`, `src/ocr/`, `src/structure/`, `src/headings/`, `src/markdown/`, `src/footnotes/` — zero changes
- `src/pipeline/phase1_pipeline.py` — AI generation is on-demand, never in the pipeline
- `src/images/image_extractor.py` — placeholder generation stays as-is; new fields default to None
- `src/validation/validator.py` — IMAGE_004 (pending review) still fires for PENDING_REVIEW; new statuses are not validated (yet)
- All existing tests — additive model fields + new enum values are backward-compatible

**Modified files (minimal):**
- `src/models/figure.py` — new enum values + 5 new Figure fields (all Optional with defaults)
- `src/models/page.py` — add `width_pt: Optional[float] = None` (for alignment detection)
- `src/api/schemas.py` — extend FigureOut, add 3 new request schemas
- `src/api/routes.py` — add 3 new endpoint functions + re-generation logic in download_docx
- `src/docx/docx_generator.py` — add alignment detection from bbox
- `frontend/lib/api.ts` — extend Figure type + 3 new api methods
- `frontend/components/Badge.tsx` — new status badge cases
- `frontend/components/ImageGrid.tsx` — use ImageCard, add checkbox/selection state

**New files:**
- `src/ai/__init__.py`
- `src/ai/alt_text_generator.py`
- `frontend/components/ImageCard.tsx`
- `frontend/components/ImageDetailPanel.tsx`
- `frontend/components/BulkActions.tsx`
- `tests/test_alt_text_generator.py`
- `tests/test_image_review_api.py`

---

## 11. Test strategy

**Benchmark-first:** Before any implementation, verify the benchmark suite still passes (877 baseline). After each step, re-run `pytest -m "not real_docling and not real_surya"` to confirm no regression.

**For `test_alt_text_generator.py`:**
- Set `RAWRS_AI_STUB=1` to use the stub
- Test: stub returns deterministic result for same image_id
- Test: `AltTextGenerationError` raised when image file missing
- Test: confidence clamped to [0.0, 1.0]
- Test: WARNINGS="None" produces `warnings = []`
- Test: structured prompt contains caption and figure label

**For `test_image_review_api.py`:**
- Build a synthetic job in the in-memory `_jobs` dict with one image in PENDING_REVIEW
- Test each action (approve/reject/decorative/complex/skip/edit) against the PATCH endpoint
- Test generate-alt-text populates AI fields and sets AI_GENERATED status
- Test bulk-action applies to all listed images
- Test that unknown image_ids in bulk-action are silently skipped (not 404)
- Test that generate-alt-text on an extraction_failed image returns 422
- Test that DOCX download re-generates when any image is not PENDING_REVIEW

**For existing tests:**
- `Figure(...)` with no new fields still constructs correctly (all have defaults)
- `AltTextStatus.PENDING_REVIEW` and `.HUMAN_REVIEWED` still resolve correctly
- `FigureOut` without AI fields still serializes correctly

---

## 12. Accessibility compliance

- Approved non-empty alt text → `<pic:cNvPr descr="...">` (already wired)
- Decorative (empty) alt text → `<pic:cNvPr descr="" title="">` explicitly
- Complex alt text marker → `<pic:cNvPr descr="[Complex image — requires extended description]">` with IMAGE_COMPLEX validation warning (new rule ID `IMAGE_005` — add to validator.py)
- Pending/AI-generated/rejected alt text → `IMAGE_004` still fires (not yet human-approved)

**New validation rule `IMAGE_005`:** If `alt_text_status == COMPLEX`, emit a WARNING: "Image marked as complex — a long description has not been added to the document body. Consider adding a detailed description as a paragraph following the figure."

---

## 13. Checklist mapping

The WinVinaya remediation standard checklist items this feature closes:

- "AI Alt Text" — from deferred/not_impl → implementable after this feature
- "Human review of all image alt texts" — workflow now exists
- "Images included in DOCX at correct position and size" — alignment detection added
- "Decorative images correctly marked" — DECORATIVE status + empty DOCX alt text

Items remaining open after this feature:
- "Long descriptions for complex figures" — COMPLEX status flags it; actual long-description wiring deferred
- "Table remediation" — deferred (Section 9)

---

## 14. Implementation order (dependency-safe sequence)

1. **Model changes** (`figure.py`, `page.py`) — no dependencies
2. **AI module** (`src/ai/`) + stub — no dependencies
3. **API schemas** (`schemas.py`) — needs model changes
4. **API routes** (`routes.py`) — needs schemas + AI module
5. **DOCX alignment** (`docx_generator.py`) — needs `page.width_pt`
6. **DOCX re-generation** (in `routes.py` download handler) — needs API routes
7. **Frontend: Badge + api.ts** — independent of backend once schema is finalized
8. **Frontend: ImageCard** — needs Badge
9. **Frontend: ImageDetailPanel** — needs ImageCard
10. **Frontend: BulkActions + ImageGrid** — needs ImageCard + BulkActions
11. **DocumentWorkspace wiring** — needs all frontend components
12. **Tests** — after each stage above

Run benchmark suite after steps 1, 4, 6, and 11.
