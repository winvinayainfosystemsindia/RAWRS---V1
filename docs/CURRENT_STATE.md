# RAWRS Current State

**As of:** this documentation reconciliation audit (June 2026), updated again in a follow-up reconciliation pass the same month covering XML Sanitization Architecture C, bug_001 (paragraph reconstruction), bug_002 (heading fallback tier), and the platform layer (backend/frontend) coming into existence.
**Read this first** if you want a one-page answer to "what does RAWRS actually do right now."

For per-phase detail, see `PHASE_STATUS.md`. For pipeline/module detail, see `ARCHITECTURE_CURRENT.md`. For what's intentionally missing, see `KNOWN_LIMITATIONS.md`. For why things are the way they are, see `DECISIONS_LOG.md`.

---

## What RAWRS is today

An **accessibility remediation platform**: a local-first, deterministic Python pipeline that can accept either a PDF alone (native extraction + OCR), or a PDF plus a Mathpix MMD file (Mathpix as primary extraction source, RAWRS provides verification, enrichment, and accessibility output). The pipeline entry point is `run_pipeline(pdf_path, mmd_path=None)` in `src/pipeline/phase1_pipeline.py`.

`mmd_path=None` (default): `PDF → text extraction → OCR → Document Model → Markdown + accessible DOCX + validation report`

`mmd_path=<path>.mmd`: `PDF + Mathpix MMD → import into Document Model → RAWRS verification → Markdown + accessible DOCX + validation report`

In both paths, the RAWRS Document Model is the single canonical representation. Mathpix extraction is import-only; the raw MMD is discarded after ingestion. The original PDF is evidence only (used for future verification phases M-2/M-3). Every proposed correction is recorded as a `CorrectionRecord` (audit trail: original_value → proposed_value → status) — Mathpix extraction is never silently overwritten.

**Platform layer:** A FastAPI backend (`src/api/`) and a Next.js frontend (`frontend/`) both exist on top of this pipeline — see "Platform layer" below. This corrects this file's own prior claim of "no server, no UI, no API," which was accurate when last written and is not accurate now.

## What it can do, end to end

* Extract real text from born-digital PDFs directly (no OCR needed) — Phase A.
* Classify pages and run Docling, then Surya as a fallback, on pages that actually need OCR — Phases D.0–D.2. On this CPU-only deployment, the Surya fallback runs by spawning a real upstream `llama-server` (llama.cpp) process and serving the `surya-2.gguf` vision-language model through it — confirmed by a dedicated Surya Backend Architecture Audit. This is a genuine external runtime prerequisite (the `llama-server` binary must be installed and resolvable on the host), not merely a Python dependency. See `OCR_RULES.md` and `DECISIONS_LOG.md` (Part 4).
* Persist per-line layout data (position, font size, bold) for every page — Phase H.
* Detect footnotes and endnotes, link markers to bodies, and preserve that relationship into both Markdown and DOCX (via bookmark/hyperlink, not native Word footnotes) — Phase K.
* Filter out background/decorative/duplicate images, keeping only meaningful figures — Phase C.
* Detect figure captions near images and link them — Phase F.2.
* Generate a deterministic placeholder alt-text string for every retained image and mark it pending human review — Phase F.3, wired into both Markdown and DOCX — Phase F.4.
* Log every image's metadata/context/placeholder alt text to a JSON dataset file for future model training — Phase F.5.
* Detect H1–H6 headings using font-size-rank + bold + layout signals (not just numbering patterns), plus a last-resort fallback tier (bug_002) for headings rendered in a distinct embedded font subset that the bold-gate can't see (font≠body, recurs ≥2×, sole-line PyMuPDF block, size≥body size) — and map them all to Word's native Heading 1–6 styles so Word's Navigation Pane works — Phase B.
* Apply a configurable page-numbering policy (`PageNumberingPolicy` in `src/config/page_numbering.py`) controlling whether H6 page markers are emitted, and with what text — four modes: `AUTO` (detected printed labels only, no synthetic fallback), `MANUAL_RANGE`, `MANUAL_NUMBER_OVERRIDE`, `DISABLED`. Backward-compatible: the legacy behavior (every page gets a marker, `printed_label or str(page_number)`) is preserved when no policy is passed.
* Reconstruct paragraphs from PyMuPDF's line-level extraction (bug_001) — joins same-block lines via `source_block_index` + bbox x-continuity, with a vertical-gap fallback, instead of rendering one markdown block per raw PDF line.
* Sanitize XML-illegal characters out of all extracted text at three independent layers (source, validation disclosure, DOCX export guard) so a broken PDF font/ToUnicode mapping can no longer crash DOCX generation — XML Sanitization Architecture C.
* Flag (not fix) reading-order anomalies — backward jumps and overlapping blocks — Phase I.1.
* Run 19 distinct validation rules across document/heading/page/image/OCR/note categories and produce a structured report.

## Test suite

**Current authoritative figure (2026-06-30): 1296 passed, 0 failed, 7 skipped** (full suite, all markers). Phase M-1 added 44 tests (`tests/test_mathpix_ingestor.py`); FEATURE_015.3 production sign-off confirmed 1239 passed, 0 failed before Phase M-1. See `PHASE_STATUS.md` for the per-feature test history.

## What it can do, end to end (additions since last update)

* **Import a Mathpix MMD file as the primary extraction source** — `run_pipeline(pdf_path, mmd_path="path/to/file.mmd")`. The `MathpixImportProvider` (`src/mathpix/ingestor.py`) parses the MMD via a state-machine parser (`src/mathpix/mmd_parser.py`), populates all `Document` fields (headings, footnotes, tables, front matter, page text), and marks each with `source="mathpix"`. All downstream stages (Markdown, DOCX, validation, review workspaces) are unaware of the extraction source — they read only the Document Model.
* **Record an audit trail for every proposed correction** — `Document.corrections: List[CorrectionRecord]`. Each `CorrectionRecord` carries: `object_type`, `field`, `original_value`, `proposed_value`, `status` (PROPOSED/AUTO_APPLIED/ACCEPTED/REJECTED/PENDING_REVIEW), `evidence`, `reason`, `provider`. Populated by Phase M-2/M-3 cross-source verification. Empty list in Phase M-1.

## What does NOT exist yet

* **AI alt text is on-demand, not automatic.** The pipeline generates deterministic placeholder alt text. The Qwen2.5-VL interface (`src/ai/alt_text_generator.py`) is built. `torch`, `transformers`, and `qwen-vl-utils` are now installed in the venv (installed 2026-06-29). A one-time model weight download is still required before real AI generation works (run the backend once with a real image to trigger the download). In `RAWRS_AI_STUB=1` mode, a deterministic stub is used (all tests run this way). Human review actions (Approve/Reject/Decorative/Complex/Skip/Edit) are fully implemented — AI generation is always on-demand, never automatic.
* **No equation or multi-column reconstruction.** Span-level text architecture (`feature_005_span_level_text_model`) is not implemented — no inline equations, superscripts (except as detected footnote markers), or subscripts. **FEATURE_015 (2026-06-29):** Tables with visible PDF borders are now auto-detected and rendered (see Platform layer section). Borderless tables (academic journal style — common in e.g. Brinkman) return 0 auto-detections and require manual creation via the Tables workspace tab.
* **Reading-order correction is human-initiated only.** Phase I.1 (PAGE_003 validation) detects anomalies. FEATURE_016B adds a Reading Order workspace where reviewers can drag-reorder blocks and approve pages. Automatic reordering is not performed — the pipeline never reorders without human instruction.
* **No dataset directories beyond `alt_text_dataset/`** — `ocr_dataset/`, `heading_dataset/`, `footnote_dataset/`, `validation_dataset/` are named as future work in the project handover but have zero corresponding code today.
* **Native Word footnotes/endnotes not implemented.** RAWRS encodes footnotes as a superscript run inside a `w:hyperlink`/`w:bookmark` pair — a real, clickable, traversable internal reference, but the note body renders as ordinary body text, not inside Word's auto-numbered footnote pane. Also: footnote/endnote detection (PDF-native path) only recognizes a marker encoded as a literal Unicode superscript glyph; the more common real-world encoding (plain digit, smaller font, PyMuPDF superscript flag) is not detected. Root-caused as span-level information loss in `TextBlock` — see `KNOWN_LIMITATIONS.md` and the `feature_005` design review.
* **Mathpix footnote anchor positions are placeholders (Phase M-1 gap).** In the Mathpix import path, inline footnote references (e.g. `[1]`) are imported with `anchor_page_number=1` and `anchor_text=marker`. Phase M-2 will resolve the actual page using the DOCX's H6 page markers. See `KNOWN_LIMITATIONS.md`.
* **Phase M-2 through M-5 not yet implemented.** Cross-source verification (heading level cross-check, footnote recovery, table recovery), API endpoint for Mathpix MMD upload, and the FEATURE_014 cross-source comparison panel are all pending.

## Platform layer (corrects this file's own prior claim)

A FastAPI backend (`src/api/main.py`, `routes.py`, `jobs.py`, `schemas.py`) and a Next.js/React/TypeScript/Tailwind frontend (`frontend/`) both exist and are functional — confirmed by direct inspection and by exercising the backend over real HTTP. **This is a different stack from the one `docs/TECH_STACK.md` names** (Vite/Zustand/shadcn/react-pdf/Lucide React) — `TECH_STACK.md` itself is out of scope for this update (see the explicit do-not-modify list this update was scoped against), so this discrepancy is recorded here rather than silently resolved.

What's actually built: an upload page, a per-document workspace page with tabs for Validation, Headings, Images & alt text, Footnotes & endnotes, Tables, OCR, Markdown, Reading Order, Metadata, plus download buttons for the markdown/docx/report files. **FEATURE_012 (2026-06-28):** The Images tab now has full human review actions — per-image card with Generate AI Alt Text / Approve / Reject / Mark Decorative / Mark Complex / Skip / Edit buttons, an ImageDetailPanel sidebar showing AI structured output (Description / Purpose / Visible Text / Confidence / Warnings), and a BulkActions toolbar for multi-select operations. The DOCX download re-generates the DOCX from current in-memory state when any image has been reviewed, so approved alt texts flow into the downloaded file. Three new API endpoints: `POST generate-alt-text`, `PATCH /images/{id}`, `POST /images/bulk-action`. **FEATURE_015 (2026-06-29):** A Tables tab auto-detects tables with visible PDF borders via PyMuPDF `find_tables(strategy='lines')` and renders them as pipe tables in Markdown and `docx.add_table()` in DOCX. Reviewers can add caption text and a WCAG H73 accessibility summary per table, toggle header rows via the TableDetailPanel sidebar, and manually create tables for borderless academic tables the detector missed. Four new API endpoints: `GET /tables`, `POST /tables`, `PATCH /tables/{id}`, `DELETE /tables/{id}`. Job tracking is in-memory only (`src/api/jobs.py`) and does not survive a process restart.

## New modules (Phase M-1)

| Module | Location | Role |
|---|---|---|
| Import layer | `src/importers/base.py`, `src/importers/__init__.py` | `ImportProvider` Protocol — provider-agnostic interface; Mathpix is provider #1 |
| MMD parser | `src/mathpix/mmd_parser.py` | State-machine MMD → `P2Document`; handles LaTeX heading macros, figures, tabular, pipe tables, abstract, lists, footnotetext, inline math |
| Mathpix ingestor | `src/mathpix/ingestor.py` | `MathpixImportProvider` — maps P2Document into the RAWRS Document Model |
| CorrectionRecord | `src/models/correction.py` | `CorrectionRecord` + `CorrectionStatus` — full audit trail for proposed corrections |

## Dependencies actually installed (`requirements.txt`)

`pydantic`, `pymupdf`, `loguru`, `python-docx`, `docling`, `surya-ocr` (pinned to `==0.20.0` — see `DECISIONS_LOG.md` Part 4 for why), `beautifulsoup4`, `fastapi`, `uvicorn[standard]`, `python-multipart`. Dev-only (`requirements-dev.txt`): `pytest`, `pytest-cov`.

**Update: `fastapi`/`uvicorn`/`python-multipart` are now present** — this corrects this file's own prior claim that they were absent. The frontend's actual dependencies (`frontend/package.json`): `next`, `react`, `react-dom`, `react-markdown`, with `tailwindcss`/`typescript`/`eslint` as dev dependencies — notably **not** the Vite/Zustand/shadcn/react-pdf/Lucide-React stack `docs/TECH_STACK.md` names (out of scope for this update to reconcile further).

Not in `requirements.txt` but required on this host for Surya to function at all: a real `llama-server` (llama.cpp) binary, resolvable via the `LLAMA_CPP_BINARY` environment variable or PATH. This is an external runtime prerequisite, the same category as having Python itself installed — `pip` cannot express or install it.

Still notably absent despite being named in `docs/TECH_STACK.md`'s target stack: `black`, `ruff`, `mypy`. The "Code Quality" section of `TECH_STACK.md` is still aspirational, not currently enforced by any installed tooling.

## Engagement model

This is a single-developer, local-only Phase 1 codebase being driven through iterative AI-assisted sessions (see `DECISIONS_LOG.md` Part 3 for the standing strategic agreements that govern how that work proceeds — deterministic-first, human-review-always, dataset-collection-from-day-one, near-zero-cost, preserve-previous-behavior).
