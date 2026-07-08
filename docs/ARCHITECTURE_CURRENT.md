# RAWRS Architecture — Current State

## Purpose

`ARCHITECTURE.md` describes the *canonical* architecture — the intended design, frozen by stakeholder agreement. This document describes what the code **actually does today**, including the two places it deliberately deviates from the canonical order, and the modules added since `ARCHITECTURE.md` was last written. Where the two disagree, `ARCHITECTURE.md` still governs *intent*; this file governs *fact*.

---

## Actual Pipeline Order (`src/pipeline/phase1_pipeline.py`)

`run_pipeline(pdf_path, mmd_path=None)` has two Stage 2 paths. `mmd_path=None` (default) is the PDF-native path; all stages run. When `mmd_path` is supplied (Phase M-1 Mathpix import path), Stage 2 is replaced by `MathpixImportProvider.import_document()` and stages 3a/3b/5 are skipped (Mathpix already extracted headings, footnotes, and tables).

```
1. Parse PDF                                            (src/parser/pdf_parser.py)
2. Extract Text / Route / OCR  [PDF-native path, mmd_path=None]
   2a. Direct text extraction (Phase A)                 (src/ocr/extractor.py)
   2b. Route pages DIRECT_TEXT vs OCR_REQUIRED (D.0)     (src/ocr/router.py)
   2c. Docling OCR on OCR_REQUIRED pages (D.1)           (src/ocr/docling_engine.py)
   2d. Surya OCR fallback on pages Docling left empty (D.2)  (src/ocr/surya_engine.py)
   — OR —
2. Mathpix Import  [mmd_path=<file>.mmd path]
   MathpixImportProvider.import_document()              (src/mathpix/ingestor.py)
   mmd_parser.parse_mmd() → P2Document → Document      (src/mathpix/mmd_parser.py)
3. Detect Structure (Phase H)                            (src/structure/structure_detector.py)
   3a. [PDF-native only] Detect Footnotes/Endnotes (Phase K)
                                                           (src/footnotes/footnote_detector.py)
   3b. [PDF-native only] Extract Front Matter (Phase M)
                                                           (src/frontmatter/front_matter_extractor.py)
   3c. [PDF-native only] Extract Tables (FEATURE_015)
                                                           (src/tables/table_extractor.py)
4. Extract Images (Phase C filtering, F.1 bbox, F.2 caption linking, F.3 alt-text placeholder)
                                                           (src/images/image_extractor.py)
5. [PDF-native only] Detect Headings (Phase B)            (src/headings/heading_detector.py)
6. Generate Markdown (paragraph reconstruction, bug_001)
                                                           (src/markdown/markdown_builder.py, src/structure/paragraph_grouper.py)
7. Generate DOCX                                          (src/docx/docx_generator.py)
8. Run Validation (Phase I.1 reading-order check included) (src/validation/validator.py)
```

### Two known deviations from `ARCHITECTURE.md`'s canonical order

`ARCHITECTURE.md` states: `Parser → OCR → Structure Detection → Heading Detection → Image Extraction → Markdown Generation → Validation → DOCX Generation → Output`.

The actual code order differs in two places, **both deliberate and tracked, neither accidental**:

1. **Image Extraction runs before Heading Detection** (canonical order has Heading Detection first).
2. **Validation runs after DOCX Generation** (canonical order has Validation before DOCX Generation).

Both were identified during the benchmark reconciliation work and a realignment was recommended (see `DECISIONS_LOG.md`, "Phase G" in the historical roadmap) but never implemented — nothing technically blocks it, it simply hasn't been picked up. Anyone changing pipeline order should update both this file and `ARCHITECTURE.md`'s diagram together, and re-run the full benchmark before merging, since validation's pre/post-DOCX position changes which issues are visible to a human reviewer before vs. after the DOCX artifact exists.

---

## Module Inventory (as of this audit)

`ARCHITECTURE.md`'s "Core Modules" section predates several modules that now exist. Full current inventory:

| Module | Location | Added | Responsibility |
|---|---|---|---|
| Parser | `src/parser/pdf_parser.py` | original | PDF loading, page extraction |
| OCR — direct extraction | `src/ocr/extractor.py` | Phase A | PyMuPDF native text extraction |
| OCR — routing | `src/ocr/router.py` | Phase D.0 | Per-page DIRECT_TEXT / OCR_REQUIRED classification |
| OCR — Docling | `src/ocr/docling_engine.py`, `src/ocr/docling_config.py` | Phase D.1 | Primary OCR engine, full-page mode |
| OCR — Surya | `src/ocr/surya_engine.py`, `src/ocr/surya_config.py` | Phase D.2 | Fallback OCR engine. On CPU-only hosts (this deployment), `surya-ocr` (pinned `0.20.0`) internally spawns the upstream `llama-server` binary and runs the `surya-2.gguf` model through it via a local HTTP API — a real external runtime prerequisite. See `OCR_RULES.md` and `DECISIONS_LOG.md` Part 4. |
| Structure | `src/structure/structure_detector.py`, `src/structure/layout_signals.py` | Phase H | Persists per-line bbox/font/bold/order (+ `source_block_index`, added for bug_001) into `Document.blocks` |
| Paragraph Reconstruction | `src/structure/paragraph_grouper.py` | bug_001 | Joins same-`source_block_index` lines into paragraphs (bbox-based multi-column false-merge guard), consumed by Markdown Generation |
| Footnotes | `src/footnotes/footnote_detector.py` | Phase K | Footnote/endnote detection and marker↔body linking. **Known gap:** only recognizes a literal Unicode superscript-digit glyph as a marker — see `KNOWN_LIMITATIONS.md` and `feature_005_span_level_text_model` |
| Heading Detection | `src/headings/heading_detector.py` | original, re-signaled in benchmark reconciliation, fallback tier added in bug_002 | H1–H6 detection, layout-signal based, plus a last-resort distinct-recurring-font/sole-line-block fallback tier |
| Image Extraction | `src/images/image_extractor.py` | original, filtering/caption/alt-text added Phases C/F | Extraction, filtering, figure/caption linking, alt-text placeholders. CMYK JPEG fix + embedding verification added FEATURE_016E (`Image.embedded_in_docx`, IMAGE_005). |
| Markdown Generation | `src/markdown/markdown_builder.py` | original, paragraph reconstruction added in bug_001 | Canonical markdown, paragraph joining, footnote syntax, alt-text embedding |
| Text Sanitization | `src/utils/text_sanitization.py`, `src/models/sanitization.py` | XML Sanitization Architecture C | Layer 1 of a 3-layer defense removing XML-illegal characters at every point text enters the Document model; `Document.sanitization_events` is the audit trail Layer 2 (`DOC_004`) discloses |
| DOCX Generation | `src/docx/docx_generator.py` | original, Layer 3 sanitization guard (`_safe_run_text()`) added | Heading styles, page markers/breaks, image+alt-text wiring, footnote bookmark/hyperlink wiring |
| Table Extraction | `src/tables/table_extractor.py`, `src/tables/evidence.py`, `src/tables/detectors/` | FEATURE_015/015.1, 2026-06-29 | PyMuPDF `find_tables(strategy='lines')` auto-detection; merged cell detection; `Table`, `TableRow`, `TableCell` models; stage 3 integration. |
| AI Alt Text | `src/ai/alt_text_generator.py`, `src/ai/provider.py`, `src/ai/providers/`, `src/ai/registry.py`, `src/ai/quality.py` | FEATURE_012, 2026-06-28 | On-demand Qwen2.5-VL interface; provider abstraction; stub for testing. |
| AI Table Analysis | `src/ai/table_analyzer.py` | FEATURE_015, 2026-06-29 | On-demand AI table structure suggestions. |
| Validation | `src/validation/validator.py` | original, extended through Phase I.1 + tables + FEATURE_016 | 29 rule IDs across document/heading/page/image/OCR/note/table/metadata checks |
| Config | `src/config/page_numbering.py` | 2026-06-28 | `PageNumberingMode` enum + `PageNumberingPolicy` dataclass; single `resolve_marker_text()` decision method. Consumed by `detect_headings()`, `build_markdown()`, and `run_pipeline()` as an optional `page_numbering_policy` parameter (default `None` → legacy behavior preserved). |
| AI alt text | `src/ai/alt_text_generator.py` | FEATURE_012, 2026-06-28 | On-demand Qwen2.5-VL alt text generation. Never called automatically by the pipeline — only by `POST /images/{id}/generate-alt-text` when a human reviewer explicitly requests it. Lazy model loading (first call only). `RAWRS_AI_STUB=1` returns deterministic stubs for testing without model weights. |
| Pipeline orchestration | `src/pipeline/phase1_pipeline.py` | original | Wires all stages; writes markdown/docx/report/dataset outputs |
| API (platform layer) | `src/api/main.py`, `routes.py`, `jobs.py`, `schemas.py` | added 2026-06; extended FEATURE_012/015/016 | FastAPI HTTP interface. In-memory job tracking. Endpoints for upload, validation, headings, images (alt text review), footnotes, tables, reading order, metadata, pages, markdown, docx download. DOCX download re-generates from current in-memory Document state on request. |
| Frontend (platform layer) | `frontend/` | added 2026-06; extended FEATURE_012/015/016 | Next.js/React/TypeScript/Tailwind. Per-document workspace tabs: Validation, Headings, Images & alt text, Footnotes & endnotes, Tables, OCR, Markdown, Reading Order, Metadata. Full review workflows for each entity type. |
| Mathpix import — MMD parser | `src/mathpix/mmd_parser.py` | Phase M-1, 2026-06-30 | State-machine MMD → P2Document. Handles: `\title{}`, `\section*{}`, `\subsection*{}`, `\subsubsection*{}`, `\author{}`, `\begin{figure}`, `\begin{tabular}`, `\begin{table}`, `\begin{abstract}`, pipe tables, bullet/numbered lists, `\footnotetext{N}{body}`, inline footnote refs via math_transformer. |
| Mathpix import — ingestor | `src/mathpix/ingestor.py` | Phase M-1, 2026-06-30 | `MathpixImportProvider` — maps P2Document into RAWRS Document Model. Sets `source="mathpix"` on headings/footnotes, `extraction_source="mathpix"` on tables, `ExtractionMethod.MATHPIX_IMPORT` on pages. Proportional page assignment (Phase M-2 will refine using DOCX H6 markers). |
| Import layer | `src/importers/base.py`, `src/importers/__init__.py` | Phase M-1, 2026-06-30 | `ImportProvider` Protocol (`@runtime_checkable`) — provider-agnostic interface. `MathpixImportProvider` is provider #1. Future: ABBYY, Azure Doc AI, Google Doc AI, Docling. |
| Pre-M-1 mathpix skeleton | `src/mathpix/latex_env_parser.py`, `src/mathpix/math_transformer.py`, `src/models/phase2_document.py` | started 2026-06-29 | MMD tokenizer, inline math transformer, P2Document model. Now consumed by Phase M-1 (mmd_parser uses math_transformer; ingestor maps P2Document → Document). |

### Shared Models (`src/models/`)

Phase 1 models (used by `src/models/contracts.py` canonical re-export layer):

`bounding_box.py`, `contracts.py`, `correction.py` (CorrectionRecord + CorrectionStatus — audit trail for proposed corrections, added Phase M-1), `document.py`, `figure.py`, `footnote.py`, `front_matter.py`, `heading.py`, `image.py`, `lifecycle.py`, `metadata.py`, `page.py`, `paragraph.py` (transient — not stored on `Document`), `sanitization.py`, `span.py`, `table.py`, `text_block.py`, `validation_issue.py`.

Intermediate model (consumed by Phase M-1 ingestor, not stored in Document):

`phase2_document.py` — `P2Document`, `P2Block`, `P2BlockType`, `P2Heading`, `P2Table`, `P2Figure`, `P2Footnote`, `P2FrontMatter`, `P2ValidationIssue`. Added 2026-06-29; used as the MMD parsing target by `mmd_parser.py`.

---

## Platform layer (corrected — this section previously said it didn't exist)

**This section previously stated that `docs/TECH_STACK.md`'s target stack (React/TypeScript/Vite frontend, FastAPI backend) had not been built, that `src/main.py` was empty, that `requirements.txt` had no `fastapi`/`uvicorn`/`python-multipart`, and that there was no frontend directory. None of that is still true, and it should not be relied on.**

As of this reconciliation pass:

* `src/api/main.py`, `routes.py`, `jobs.py`, `schemas.py` exist — a real FastAPI app, confirmed by direct inspection and by starting it and exercising it over real HTTP in the same session this correction was made.
* `requirements.txt` now includes `fastapi`, `uvicorn[standard]`, `python-multipart`.
* `frontend/` exists — but is **not** the stack `docs/TECH_STACK.md` names. The actual dependencies (`frontend/package.json`): `next`, `react`, `react-dom`, `react-markdown`, with `tailwindcss`/`typescript`/`eslint` as dev dependencies. No Vite, no Zustand, no shadcn/ui, no react-pdf, no Lucide React — `TECH_STACK.md` itself is out of scope for this reconciliation pass to correct further, so this discrepancy is recorded here rather than silently resolved.
* `src/main.py` is still empty — it was never the real entry point; `src/api/main.py` is.

`run_pipeline(pdf_path)` in `phase1_pipeline.py` remains the actual processing engine and is still callable directly (e.g. from a test or a script) — the platform layer is a real HTTP/UI wrapper around it, not a replacement for it. **This section previously stated the platform layer provided no review/approve/correct action — that has not been true since FEATURE_016 and is even less true now.** As of Phase M-2 (see below), the platform is a full review-and-correction workspace, not just a viewer: reviewers approve/reject/edit headings, footnotes, images, tables, reading order, page labels, and metadata, and accept/reject/edit AI-proposed cross-source corrections via the Corrections API. Job tracking remains an in-memory dict (no database — consistent with the "no databases" architectural constraint) that does not survive a process restart. See `CURRENT_STATE.md` and `KNOWN_LIMITATIONS.md`.

### Cross-source verification engine (Phase M-2, added 2026-07-01 through 2026-07-08)

A generic `src/verification/` package, not present when this file's Module Inventory below was last written:

| Module | Location | Responsibility |
|---|---|---|
| Base/registry | `src/verification/base.py`, `src/verification/engine.py` | `SemanticVerifier` abstract base (`build_pdf_matcher`/`to_canonical`/`classify`/`rule_table`/`apply`/`revert`); `VerificationEngine` registry each verifier module self-registers into |
| Identity matching | `src/verification/matching.py` | `MultiSignalMatcher`/`WeightedSignal` — generic weighted multi-signal "is this the same real-world object across two sources" matching |
| Merge decision | `src/verification/merge.py` | `MergeAction` (KEEP/REPAIR/RECOVER/REMOVE) + `decide_from_evidence()` |
| Evidence fusion | `src/verification/evidence.py` | `EvidenceSignal`/`EvidenceBundle` — weighted-mean confidence, promoted from `src/tables/` (FEATURE_015.2) to a shared primitive; `src/tables/evidence.py` re-exports it unchanged |
| Registered verifiers | `src/verification/figures.py`, `headings.py`, `lists.py`, `callouts.py` | Four asset types cross-checked against the PDF: figures (first, migrated from Phase M-1), headings (typography/whitespace/running-header evidence signals), lists, callouts (no PDF-side detector yet — evaluated on label-pattern + anchoring-heading-integrity evidence only) |
| Benchmark aggregation | `src/verification/benchmark_report.py` | Per-asset-type + whole-document `mathpix_accuracy`/`recovery_rate` summary, wired into the existing JSON validation report |
| Semantic object base | `src/models/semantic_object.py`, `src/models/callout.py` | `SemanticObject` base model (id/bbox/`verification_status`/`confidence`/`lifecycle_status`) `Heading`/`ListBlock`/`Table`/`Callout` all extend |
| Page Label Manager | `src/structure/page_label_resolver.py` | `resolve_page_labels()` — override > reviewer-defined section > detected `printed_label` precedence for `Page.page_label` (FEATURE_018) |
| Targeted OCR | `src/ocr/targeted.py` | Region-scoped OCR (`ocr_region()`) for a verifier with ambiguous evidence on a scanned page — infrastructure only, not yet called by any verifier's `classify()` |
| AI subsystem redesign | `src/ai/providers/qwen.py`, `requirements-ai.txt` | AI deps split into an optional `requirements-ai.txt`; `_check_resources()` runs a synchronous RAM/VRAM preflight at backend startup, reported via `GET /api/ai/status` |

Frontend: the tab-per-object-type `DocumentWorkspace` was replaced with a `WorkspaceShell` (`frontend/components/workspace/`) — persistent PDF/Markdown/DOCX center-pane switcher, `SemanticNavTree` left rail, `ContextInspectorRail`/`ObjectInspectorFrame` right rail driven by object selection, collapsible `BottomPanel`. New panels: `CalloutPanel`, `ListPanel`, `PageLabelManagerPanel`, `CorrectionHistoryList`, `EvidenceBreakdown`, `PdfViewer`, `ThemeToggle`/`ThemeProvider`. See `PHASE_STATUS.md`'s "Phase M-2" section and `DECISIONS_LOG.md` Parts 23–24 for full detail, including the theming-token migration and two dev-environment bugs (Next.js `allowedDevOrigins`, a React Rules-of-Hooks violation) found and fixed 2026-07-08.

---

## Architectural Constraints (unchanged from `ARCHITECTURE.md`)

Local-first, no cloud dependencies, no databases, no microservices, no containers, no AI agents in Phase 1. Nothing built since `ARCHITECTURE.md` was written violates these in spirit — Docling and Surya are both local, no internet-hosted inference is used, and RAWRS's own `src/` code makes no network calls.

**One nuance worth stating plainly, found by the Surya Backend Architecture Audit:** Surya's CPU-path execution does involve a local HTTP server. `surya-ocr` itself (not RAWRS's code) spawns a `llama-server` subprocess and talks to it over loopback HTTP (OpenAI-compatible chat completions). This is a localhost-only process the third-party package manages internally, not a network service RAWRS calls out to, and it does not violate "no cloud dependencies" or "no microservices" as those constraints were intended (no remote host, no persistent service RAWRS itself maintains) — but it is a real, additional local process and a real external binary dependency that "Docling and Surya are both local libraries" understates. Surya also does a one-time model download from Hugging Face Hub (the `surya-2.gguf`/`surya-2-mmproj.gguf` pair), same as Docling's own model downloads — a setup-time network call, not a per-document one.

**A second nuance, now that the platform layer (above) exists:** FastAPI/Uvicorn (`src/api/`) is a single local HTTP server process serving one Python pipeline, not a microservice architecture — no message queue, no separate service boundaries, no remote deployment target. The frontend (`frontend/`) talks to it over `localhost` only, with CORS explicitly restricted to the dev frontend's own origin. Job tracking is an in-memory dict (`src/api/jobs.py`), not a database. Neither violates "no cloud dependencies," "no databases," or "no microservices" in spirit — same reasoning as the Surya nuance above: a local process serving a local pipeline to a local frontend is not the kind of remote/persistent/multi-service architecture these constraints were written to rule out.
