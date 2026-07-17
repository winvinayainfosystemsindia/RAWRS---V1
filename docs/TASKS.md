# RAWRS Development Tasks

> **This file is a quick module checklist only.** It was last accurate before Phases D.0–D.2, H, F.1–F.5, K, and I.1 were built, then again before the XML Sanitization Architecture, bug_001 (paragraph reconstruction), bug_002 (heading fallback tier), bug_005 (span-level footnote fix), and bug_006 (front-matter extraction) work — every box below is now checked because every listed module exists and is tested. **For real implementation status, gaps, and caveats per phase, use `PHASE_STATUS.md` instead of this file.**

## Foundation Models

* [x] document.py
* [x] page.py
* [x] heading.py
* [x] image.py
* [x] metadata.py
* [x] validation_issue.py
* [x] bounding_box.py
* [x] text_block.py
* [x] figure.py
* [x] footnote.py
* [x] paragraph.py (bug_001 — deliberately transient, not stored on `Document`)
* [x] sanitization.py (XML Sanitization Architecture — `Document.sanitization_events`)
* [x] contracts.py (canonical re-export layer)

## Parser

* [x] pdf_parser.py

## OCR

* [x] extractor.py (Phase A — direct text extraction)
* [x] router.py (Phase D.0 — page routing)
* [x] docling_engine.py / docling_config.py (Phase D.1)
* [x] surya_engine.py / surya_config.py (Phase D.2)

## Structure

* [x] structure_detector.py / layout_signals.py (Phase H)
* [x] paragraph_grouper.py (bug_001 — paragraph reconstruction, see PHASE_STATUS.md "Phase L")
* [x] Overlap guard calibration (feature_010 — see PHASE_STATUS.md "Phase L" and DECISIONS_LOG.md Part 15)
* [x] Page.printed_label detection (feature_009 — see PHASE_STATUS.md "Phase H" and DECISIONS_LOG.md Part 14)
* [x] Configurable Page Numbering Policy (4 modes: AUTO/MANUAL_RANGE/MANUAL_NUMBER_OVERRIDE/DISABLED — see PHASE_STATUS.md "Phase H" and DECISIONS_LOG.md Part 16)

## Footnotes

* [x] footnote_detector.py (Phase K — see PHASE_STATUS.md for the confirmed superscript-marker detection-coverage gap)

## Front Matter

* [x] front_matter_extractor.py / front_matter.py (bug_006/feature_006 — see PHASE_STATUS.md "Phase M")
* [x] Front-matter generalization beyond Brinkman (feature_008 — see DECISIONS_LOG.md Part 13)

## Headings

* [x] heading_detector.py (Phase B — see PHASE_STATUS.md for the formatting-check caveat and bug_002's fallback tier)
* [x] Wrapped heading continuation repair (bug_007/feature_007 — see PHASE_STATUS.md "Phase B" and DECISIONS_LOG.md Part 12)

## Images

* [x] image_extractor.py (Phases C, F.1, F.2, F.3)
* [x] AI alt text generation — on-demand only, FEATURE_012 (src/ai/alt_text_generator.py, Qwen2.5-VL interface + RAWRS_AI_STUB stub)
* [x] Human review workflow — FEATURE_012 (AltTextStatus 8 values, 3 new API endpoints, ImageCard/ImageDetailPanel/BulkActions frontend components)

## Markdown

* [x] markdown_builder.py

## Validation

* [x] validator.py (19 rule IDs — see PHASE_STATUS.md for the full table and known gaps)

## Utilities

* [x] text_sanitization.py (XML Sanitization Architecture, Layer 1 — see PHASE_STATUS.md)

## DOCX

* [x] docx_generator.py (Layer 3 sanitization guard, `_safe_run_text()`, included)

## Pipeline

* [x] phase1_pipeline.py (Phase F.5 dataset writing included)

## Platform (API / Frontend)

* [x] src/api/ (FastAPI: main.py, routes.py, jobs.py, schemas.py) — all review endpoints (headings, images, footnotes, tables, reading order, metadata)
* [x] frontend/ (Next.js/React/TypeScript/Tailwind) — upload page + per-document `WorkspaceShell` (nav rail + PDF/Markdown/DOCX center switcher + Context Inspector; superseded the old 9-tab layout at Phase M-2 — see `PHASE_STATUS.md`)
* [x] src/ai/ (alt_text_generator.py, table_analyzer.py, provider.py, providers/, registry.py, quality.py)
* [x] src/tables/ (table_extractor.py, evidence.py, detectors/)

## Accessibility Remediation (FEATURE_016)

* [x] 016A — Heading review workspace (HeadingReviewStatus, HEADING_005, GET/PATCH headings API, HeadingGrid frontend)
* [x] 016B — Reading order workspace (ReadingOrderStatus, corrected_order, GET/PATCH reading-order API, ReadingOrderPanel frontend)
* [x] 016C — DOCX list rendering (List Bullet/Number styles, marker stripping — rendering only, no semantic list model)
* [x] 016D — Footnote review workspace (FootnoteReviewStatus, footnote_id, PATCH footnotes API, FootnoteTable rewrite)
* [x] 016E — Image DOCX embedding verification (CMYK JPEG fix, Image.embedded_in_docx, IMAGE_005)
* [x] 016F — Document properties workspace (Metadata.language/title/author/subject, GET/PATCH metadata API, MetadataPanel, META_001/META_002)
* [x] 016G — Formatting fidelity (bold/italic inline detection → Markdown markers → DOCX runs)
* [ ] 016C full model — List/ListItem models, list_detector.py, list review API, review workspace UI (DEFERRED)

## Phase 2 — Mathpix MMD Pipeline (SUPERSEDED)

This F-011..F-020 skeleton (below) was never continued past the two files marked done. The actual Mathpix integration shipped through a different, since-completed path: Phase M-1 Mathpix Import Layer → Phase M-2 Cross-Source Verification Engine (`FEATURE_017`–`020`) — see `PHASE_STATUS.md`. In particular `src/mathpix/mmd_parser.py` (listed unchecked below) has existed and been tested since Phase M-1; this section's checkboxes were never updated to match. Left as-is for the historical record rather than rewritten.

* [x] src/models/phase2_document.py — Phase2Document model
* [x] src/mathpix/__init__.py
* [x] src/mathpix/latex_env_parser.py — F-014 MMD tokenizer
* [x] src/mathpix/math_transformer.py — F-017 inline math transformer
* [ ] src/mathpix/mmd_parser.py — F-011 main MMD → P2Document parser
* [ ] src/mathpix/docx_supplement.py — F-012 DOCX heading levels + page markers
* [ ] src/mathpix/front_matter_normalizer.py — F-013 \title/\author/affiliation
* [ ] src/mathpix/table_transformer.py — F-015a tabular → P2Table
* [ ] src/mathpix/figure_transformer.py — F-016 figure env → P2Figure
* [ ] src/mathpix/heading_normalizer.py — F-018a false-positive heading removal
* [ ] src/mathpix/running_header_detector.py — F-018b ≥3-occurrence safe-mode flag
* [ ] src/pipeline/phase2_pipeline.py — entry point
* [ ] src/phase2_markdown/ — Markdown renderer
* [ ] src/phase2_docx/ — DOCX renderer (F-019 heading hierarchy + F-020 metadata)
* [ ] src/phase2_validation/ — validation rules
* [ ] tests/test_phase2_*.py — test suite

## Cross-Source Verification Engine (Phase M-2 — FEATURE_017–020)

* [x] src/verification/ — SemanticVerifier engine, matching, merge, evidence fusion
* [x] src/verification/figures.py / headings.py / lists.py / callouts.py — 4 registered asset types
* [x] src/models/callout.py, src/models/semantic_object.py
* [x] src/structure/page_label_resolver.py — Page Label Manager (FEATURE_018)
* [x] src/ocr/targeted.py — region-scoped OCR (infrastructure, not yet called by any verifier)
* [x] src/verification/benchmark_report.py — cross-source accuracy aggregation
* [x] AI subsystem: requirements-ai.txt split + RAM/VRAM preflight (src/ai/providers/qwen.py)
* [x] frontend/components/workspace/ — WorkspaceShell redesign
* [x] Theming sweep — 19 pre-existing panels migrated onto the theme-token system 2026-07-08 (see PHASE_STATUS.md Phase M-2 / DECISIONS_LOG.md Part 24)
* [x] Fixed: Next.js dev-server `allowedDevOrigins` blocking HMR and silently dropping upload form state (DECISIONS_LOG.md Part 24, Bug 1)
* [x] Fixed: Rules of Hooks violation crashing every document workspace page (DECISIONS_LOG.md Part 24, Bug 2)

## Phase 1 IDE Redesign (2026-07-08/09 — see PHASE_STATUS.md and DECISIONS_LOG.md Part 25)

* [x] Fixed: DocxPreview/Markdown never refreshed on document_version change after job completion (Live Projection Model)
* [x] TableGrid.tsx/HeadingGrid.tsx wired into workspace nav (previously built, never imported anywhere)
* [x] ImageGrid filters (Missing Alt/Needs Review/Accepted/Rejected/Decorative/Low Res) + doc-wide bulk AI generation
* [x] ObjectInspectorFrame converted to tabs (Properties/Evidence/History/AI/Actions)
* [x] Upload screen polish — hover-reveal Remove, truncated filenames with tooltips
* [x] Resizable Outline/PDF/Markdown/Inspector panel layout (react-resizable-panels 3.0.6), viewport-filling body height (2026-07-10)
* [x] Focus Mode (toolbar toggle, collapses nav+rail via Panel.collapse()) + PDF+DOCX / Markdown+DOCX split presets — skipped F11/dblclick triggers, see PHASE_STATUS.md (2026-07-10)
* [x] Reading Order numbered overlay on PdfViewer (badges only, always-visible on the main PDF pane — see PHASE_STATUS.md for why a PDF+ReadingOrderPanel split view was out of scope) (2026-07-10)
* [x] Persistent Validation Issue backend (issue_id/status/timestamps + PATCH /validation-issues/{id}, ignore/defer/reopen) (2026-07-10)

## Phase M-3 — Cross-Source Intelligence Engine extension (see PHASE_STATUS.md)

Extends the existing Phase M-2 verification engine (`src/verification/`) to asset types it doesn't cover yet — no new architecture, per the plan at the top of this milestone's PHASE_STATUS.md entry.

* [x] M-3.1 — FootnoteVerifier, the 5th registered asset type. Resolves `src/mathpix/ingestor.py::_p2footnote_to_footnote()`'s `anchor_page_number=1` placeholder via PDF-side cross-check against `src/footnotes/footnote_detector.py`. `FOOTNOTE_VERIFY_001-003`. 1500 passed / 0 failed full suite (2026-07-10).
* [x] M-3.2 — TableVerifier, the 6th registered asset type. Cross-checks Mathpix tables against `src/tables/table_extractor.py::extract_tables()`. `TABLE_VERIFY_001-007`. 1514 passed / 0 failed full suite; table-detection benchmark unchanged from baseline (2026-07-11).
* [x] M-3.3 — Benchmark & Quality Metrics extension: Accessibility Score, Manual Corrections Remaining, Repair Rate, Object Counts, Confidence Distribution (`src/verification/benchmark_report.py`), DOCX Fidelity (`src/verification/docx_fidelity.py`, new). Human Minutes Saved deliberately deferred — no telemetry to ground it. 15 new tests; 1518 passed / 1 pre-existing unrelated OCR failure (2026-07-11).

**Phase M-3 complete** (M-3.1, M-3.2, M-3.3 all done). Phase review pending before M-4.

## Phase M-4 — Reviewer Workspace & Queue Navigation (see PHASE_STATUS.md)

* [x] M-4.1 — ReviewerWorkspace shell: status tabs, filters, search, sort over `document.corrections`; fills the "Review Queue" slot `OutputWorkspace.tsx` reserved under `SOON_TABS`. `frontend/components/ReviewerWorkspace.tsx` (new), `frontend/lib/correctionFilters.ts` (new, extracted from `CorrectionsPanel.tsx`).
* [x] M-4.2 — Reviewer Queue Navigation: `CorrectionOut` gained derived `rule_id`/`severity`/`page_number`; selecting a queue item syncs `SelectionContext`/`PdfViewportContext`. 2 infinite-render-loop bugs fixed (caught via live browser verification, not unit tests).
* [x] M-4.3 — Proposal Review Experience: keyboard-first review (`n`/`p`/`a`/`r`/`i`/`u`/`e`/`j`/`/`), same Corrections API the mouse buttons already call.
* [x] M-4.4 — Minimal correction telemetry: `CorrectionTelemetryEvent` appended to `CorrectionRecord.telemetry_events` on every reviewer action; collection only, not yet exposed via the API.

**Phase M-4 complete** (M-4.1, M-4.2, M-4.3, M-4.4 all done).

## Phase M-5 — Targeted OCR Evidence Integration (see PHASE_STATUS.md)

Wires the previously-unused `src/ocr/targeted.py::ocr_region()` (FEATURE_019) into `HeadingVerifier` as an evidence-of-last-resort `EvidenceSignal`.

* [x] M-5.1 — Targeted OCR as one more `EvidenceSignal` in `HeadingVerifier`, gated to only run when the fused bundle is already ambiguous (`_OCR_AMBIGUOUS_CONFIDENCE_THRESHOLD = 0.5`).
* [x] M-5.2 — Real-corpus validation benchmark (`docs/m52_ocr_evidence_benchmark.json`) across all 10 benchmark PDFs; surfaced 2 real bugs (text-resolution misses, a Surya `full_page` API mismatch) fixed by M-5.3/M-5.4.
* [x] M-5.3 — `TextResolver` (`src/verification/text_resolution.py`, new): generic tiered text-to-key resolution (exact/normalized/containment/fuzzy), wired into `headings.py`'s typography/whitespace/OCR signals.
* [x] M-5.4 — Targeted OCR compatibility fix: `ocr_region()`'s `full_page=False` → `True` (the old comment had the Surya 0.20.0 semantics backwards).
* [x] Found + fixed while closing out this phase: `build_recognition_predictor()` (`src/ocr/surya_config.py`) had no caching, so `ocr_region()` rebuilt the entire Surya model once per ambiguous heading (measured 26,160s/5 calls for one document, post-M-5.4). Fixed with `@lru_cache(maxsize=1)` on the shared factory function — process-wide, no call-site changes needed. Confirmed via an uncontended re-run: the same call dropped from ~87min to ~64s.
* [x] Found + fixed: `tests/test_targeted_ocr.py` still asserted the pre-M-5.4 `full_page=False` call shape; updated to `full_page=True`. Full suite: **1558 passed, 7 skipped, 0 failed**.
* [x] Found + fixed: `ocr_region()` had no timeout around the Surya `predictor(...)` call (see M-5.4.1 below — closed the same session it was found).

**Phase M-5 complete** (M-5.1, M-5.2, M-5.3, M-5.4, plus the predictor-caching fix and stale-test fix, all done).

## Phase M-5.4.1 — OCR Reliability & Resilience (see PHASE_STATUS.md)

Reliability-only follow-up: closes the timeout gap flagged at the end of Phase M-5. No verifier/evidence-signal changes.

* [x] Root-caused: `ocr_region()`'s Surya-facing call (predictor construction + inference) had no bound; the observed hang (1h23m, force-killed) was on an already-warm predictor, isolating it to the inference call itself (though `lru_cache`'s internal lock means a cold-construction hang would carry the same risk — addressed by the same fix).
* [x] Fixed: `_run_with_timeout()` (new, `src/ocr/targeted.py`) runs the Surya-facing call on a fresh `daemon=True` thread per invocation, bounded by `queue.Queue.get(timeout=...)`. Fresh thread per call (not a shared pool) so one real hang can't wedge every later call; `daemon=True` so an abandoned thread never blocks process exit (unlike `ThreadPoolExecutor`, which joins its workers at `atexit`).
* [x] Configurable: `DEFAULT_OCR_TIMEOUT_SECONDS`, env var `RAWRS_TARGETED_OCR_TIMEOUT_SECONDS`, default 120s; also an explicit `ocr_region(..., timeout_seconds=...)` parameter.
* [x] Raises `TargetedOCRTimeoutError(TargetedOCRError)` on expiry — zero changes needed in `src/verification/headings.py`, whose existing `except TargetedOCRError` already degrades to "no signal."
* [x] 6 new tests (5 in `tests/test_targeted_ocr.py`, 1 end-to-end in `tests/test_heading_verifier.py` through the real `ocr_region()`, not a mock) — all passing. Critical regression test: repeated hangs don't compound (each costs only its own timeout).
* [x] Benchmark re-run: full 10-document corpus **completed** (previously required a manual kill after 1h23m stuck). FolkPedagogy: 5 OCR calls, 0 timeouts triggered, ~101.5s avg latency (real CPU-bound inference cost, not a bug), findings unchanged.
* [ ] Full-suite pytest re-run attempted twice post-fix, interrupted partway both times (68%, then 24%) by an apparent session/environment constraint on long background jobs — zero failures seen in either partial run; last clean full run (pre-this-phase) was 1558 passed/7 skipped/0 failed. Follow-up: re-run to completion when the environment allows it.
* [ ] Remaining debt: abandoned timed-out threads aren't truly cancelled (Python can't force-stop a thread); real per-call OCR latency (~100s) is inherent CPU-bound inference cost, not addressed here (out of scope for a reliability-only ticket).

**Phase M-5.4.1 complete.** Not proceeding to M-5.5 per the ticket — stopped for approval.

## Phase F-1 — Frontend Completion Audit (see PHASE_STATUS.md, docs/FRONTEND_COMPLETION_AUDIT_2026-07-13.md)

* [x] 39-area frontend audit, no code changed. Headline finding: zero automated accessibility testing, zero frontend test files of any kind existed before this phase.

**Phase F-1 complete.** Recommendation approved — accessibility verification treated as a gate, leading into Phase F-2.1.

## Phase F-2.1 — Frontend Accessibility Foundation (see PHASE_STATUS.md, docs/ACCESSIBILITY_TESTING.md)

* [x] Accessibility testing infrastructure: `jest` + `jest-environment-jsdom` + `@testing-library/react`/`jest-dom` + `jest-axe`, wired via `next/jest` (`frontend/jest.config.js`, `jest.setup.ts`, `"test": "jest"` script).
* [x] `next.config.ts` gained `transpilePackages: ["react-resizable-panels"]` — required for `next/jest` to transform this ESM-only dependency at all (there is no direct `transformIgnorePatterns` override under `next/jest`).
* [x] 6 accessibility tests, one per Phase F-2.1's minimum scope (Landing/Upload, Document Workspace, Reviewer Workspace, Image Workspace, Validation Center, Corrections Center) — `frontend/__tests__/a11y/*.a11y.test.tsx`. **6/6 passing, 0 violations** (empty-state baseline).
* [x] Verification: `npx jest` (6/6), `npx tsc --noEmit` (clean), `npx next build` (clean).
* [x] Manual keyboard-only + accessibility-tree validation on Landing/Upload and Document Workspace, performed live against both dev servers (see Phase F-2.2 below) — the item above is superseded, not still open.
* [x] `docs/ACCESSIBILITY_TESTING.md` (new) — how to run, scope limits, how to add a new test, config gotchas.

**Phase F-2.1 complete.** Not proceeding to keyboard parity, search unification, responsive layout, or workspace redesign per the ticket — stopped for approval.

## Phase F-2.2 — Manual Accessibility Validation (see PHASE_STATUS.md, docs/ACCESSIBILITY_TESTING.md)

* [x] Live keyboard-only + accessibility-tree validation (Chrome DevTools Protocol, not a real screen reader — disclosed explicitly) against both dev servers with real processed documents.
* [x] Confirmed working: skip link, landing-page heading/landmark structure, real keyboard-focus visibility, logical initial tab order, `OutputWorkspace`'s already-correct ARIA tabs pattern.
* [x] Found + fixed: zero heading elements on the Document Workspace — added a visually-hidden `<h1>`. Found + fixed: static/generic `document.title` on every document page — added a per-document `useEffect`.
* [ ] Backlog (not fixed, larger than this milestone's scope): `WorkspaceShell`/`SemanticNavTree` view-switcher buttons lack ARIA tabs semantics; internal panel headings still aren't real heading elements; Reviewer Workspace keyboard shortcuts and Validation/Corrections/Image populated-data states not re-verified live this session.
* [x] Verification: `npx jest` (6/6), `npx tsc --noEmit` (clean), `npx next build` (clean) — re-run after the two fixes.

**Phase F-2.2 complete.** Not proceeding to search unification, responsive design, or UI redesign per the ticket — stopped for approval.

## Phase F-3.1 — Keyboard Workflow Parity (see PHASE_STATUS.md)

* [x] `frontend/lib/hooks/useListReviewKeyboard.ts` (new) — shared keyboard-nav hook extracted from `ReviewerWorkspace`'s existing pattern.
* [x] `ReviewerWorkspace.tsx` refactored to use the shared hook — same shortcuts, zero behavior change, proves the abstraction.
* [x] Investigated all 9 named target workspaces; found Reading Order already has full keyboard-accessible reordering (assumption disproven before building anything redundant); found Validation/Image/Tables workspaces don't share the reference implementation's flat-list shape, so a concrete (not vague) per-workspace recommendation was written for each instead of a shallow retrofit.
* [ ] Validation Center, Image Workspace, Tables Workspace keyboard parity — specific implementation plan documented in PHASE_STATUS.md, not yet built.
* [ ] Outline Navigation / Inspector / Document Workspace view-switcher — needs a second, separate `useArrowKeyTabs`-style hook (a tabs pattern, not a list pattern); ties to the Phase F-2.2 ARIA-tabs backlog item. Not yet built.
* [x] Deliberately not recommended: Corrections Center (redundant with ReviewerWorkspace's existing full keyboard coverage of the same data) and a standalone Focus Mode shortcut (already one click away, no evidence of need).
* [x] Verification: `npx jest` (6/6, unchanged), `npx tsc --noEmit` (clean), `npx next build` (clean).
* [ ] Live keyboard-only walkthrough of the refactored ReviewerWorkspace — not re-performed this session (cumulative cost); disclosed honestly, not claimed.

**Phase F-3.1 complete.** Not proceeding to search unification, responsive layout, or workspace redesign per the ticket — stopped for approval.

## Phase F-3.2 — Shared Tab Navigation Infrastructure (see PHASE_STATUS.md)

* [x] Audited all tab-like widgets against a real test (content-switching vs. list-filtering); found 4 genuine tabs consumers (2 named in the ticket + 2 more found by auditing), correctly excluded 2 filter-style widgets that only look tab-like.
* [x] `frontend/lib/hooks/useArrowKeyTabs.ts` (new) — WAI-ARIA APG Tabs pattern: roving tabindex, arrow-key + Home/End nav, real focus management.
* [x] Retrofitted `WorkspaceShell` center-view switcher, `SemanticNavTree` mode selector, `ObjectInspectorFrame` tabs, `OutputWorkspace` tab bar.
* [x] Found + fixed a real bug: `ObjectInspectorFrame` used `aria-current` (wrong attribute — that's for pagination/breadcrumbs) with no `role="tab"`/`"tablist"` at all.
* [x] Verification: `npx jest` (6/6, unchanged), `npx tsc --noEmit` (clean), `npx next build` (clean).
* [ ] Live keyboard-only walkthrough of the 4 migrated consumers — not performed this session (cumulative cost); disclosed honestly, not claimed. Standard WAI-ARIA pattern, not a novel design.

**Phase F-3.2 complete.** Not proceeding to search, responsive work, or component redesign per the ticket — stopped for approval.

---

Not yet started (see `KNOWN_LIMITATIONS.md`): equation remediation, multi-column reconstruction, cross-page paragraph stitching, span-level text model (`feature_005_span_level_text_model` — design review complete, no code written).

---

## Phase F-5.0 / R-1.0 / R-2.0 — Stabilization Audit, Large Document Mode Design, RAWRS Design Bible v1.0

* [x] F-5.0 — Frontend Stabilization Audit (`docs/FRONTEND_STABILIZATION_AUDIT_2026-07-14.md`). No code changed.
* [x] R-1.0 — Large Document Mode Design & Architecture (`docs/LARGE_DOCUMENT_MODE_DESIGN_2026-07-15.md`). No code changed.
* [x] R-2.0 — RAWRS Design Bible v1.0 (`docs/RAWRS_DESIGN_BIBLE_v1.0.md`), reconciling 3 Stitch design explorations against the shipped frontend and every prior audit. `PRODUCT.md` written. No code changed.

* [x] R-1.1 — Global Reviewer Toolbar, Navigation Chips & Validation Center Score (`docs/PHASE_STATUS.md` "Phase R-1.1"). Search/Export/page-indicator/running-score toolbar, quick-jump nav chips, Validation Center ARIA severity tabs + readiness banner, Review Queue promoted to default bottom-panel tab, PDF scroll-to-highlight. Bug found + fixed live: readiness banner was unreachable in the (most common) zero-issues state. Landed together with F-4.3's persistence work and F-4.5's Footnotes/Lists/Callouts coverage-parity wiring, which had been implemented but never logged as committed-ready in a prior session.
* [x] Reviewer Experience Audit (`docs/REVIEWER_EXPERIENCE_AUDIT_2026-07-17.md`) — live-tested critique of the shipped frontend across 18 axes; found the duplicate "Overview" control, the 3x-redundant validation surfaces, the keyboard tab-order regression, and the toolbar/Overview-panel hierarchy gaps that R-2 below fixes. Challenged the Design Bible's V3-palette-migration recommendation (§26/§39) — argued for keeping the shipped GitHub-derived colors, adopting only the token architecture. No code changed.
* [x] R-2 — Reviewer Experience Refinement (`docs/PHASE_STATUS.md` "Phase R-2"), all 7 milestones from the audit: (M1) removed the duplicate Overview control, (M2) toolbar now precedes nav chips in tab order (new `WorkspaceShell` `quickNav` slot), (M3) toolbar hierarchy (readiness/score/status grouped left, promoted styling reusing the existing readiness-banner pattern), (M4) Overview panel reordered so Manual Review/Automatic Repairs lead and the internal pipeline checklist is demoted to a collapsed "Processing Log", (M5) `ContextInspectorRail`'s duplicate `ValidationIssueTable` replaced with a summary + navigate-to-canonical-view button, (M6) `aria-expanded` added to both disclosure toggles, (M7) `PdfViewer`'s raw pdfjs error replaced with a reviewer-facing message (raw error still `console.error`-logged). `tsc`/`jest` (6/6)/`next build` clean; live-verified end-to-end on a real processed job. No color values or new dependencies introduced.
* [x] R-3 — Visual System Completion (`docs/PHASE_STATUS.md` "Phase R-3"). `frontend/components/icons.tsx` (new): 19 hand-authored inline-SVG icons matching Bible §25's outline visual language — a disclosed substitution for the literal Material Symbols ligature font (FOUC/dependency risk avoided, same technique every existing icon in the app already uses). Icons added to all 13 NavChips, Search/Export/Focus Mode, and the readiness Check/Warning pairing (toolbar Score badge + Validation Center banner, now visually consistent). Consolidated the 2 duplicated chevron-toggle SVGs into one `ChevronDownIcon`. Fixed a real readability bug found live: active NavChip count badges had poor contrast against the accent background. Normalized the one `rounded-md` outlier to `rounded`. Audited typography/empty-loading-state conventions and confirmed them already sound per prior audits — no unnecessary rewrite. No color values, workflow, architecture, or branding changed; no new dependencies. `tsc`/`jest` (6/6)/`next build` clean; live-verified on a real processed job.
* [x] Frontend Completion Review — evaluated all 15 requested axes against the Bible, the Audit, and R-1.1–R-3's shipped state; scored 84/100; recommended one final narrowly-scoped reliability milestone (not a freeze, not another UX phase) before handing engineering effort to infrastructure/viewer/backend work. No code changed.
* [x] R-4 — Frontend Reliability Hardening (`docs/PHASE_STATUS.md` "Phase R-4"), the final frontend milestone: (M1) `app/error.tsx` implemented — the single most-repeated overdue item across every prior review, now closed; reuses the existing danger-banner pattern, logs raw errors to console only. (M2) Investigated and fixed the `react-resizable-panels` "Panel id and order" warning — confirmed via the actually-installed v3.0.6 README (not a mismatched newer-version doc) that this is a real correctness risk for `WorkspaceShell`'s conditionally-rendered rail/center panels, not a false positive; added stable `id`/`order` to every `Panel` in both `PanelGroup`s. (M3) Extended `jest-axe` coverage for everything R-2/R-3 shipped without it (NavChips + toolbar icons, the readiness banner + severity tabs, and a new `context-inspector-rail.a11y.test.tsx` for the rail's validation-summary surface) — suite grew 6/6 → 9 tests/7 files, all clean. (M4) Live-verified console cleanliness through the primary reviewer workflow, and additionally proved the error boundary catches a real thrown error (not just that it typechecks) via a reversible monkey-patch test. `tsc`/`jest`/`next build` clean throughout.
* [x] Frontend frozen (`docs/FRONTEND_FREEZE.md`, new) — records why (R-1.1 through R-4 closed every concrete, live-reproduced defect found across 3 audits), acceptance criteria achieved, conditions that justify breaking the freeze, and every deferred item on the record (context-preserving editing, keyboard-coverage expansion, Triple Compare, Command Palette, Repair Action Plan, real screen-reader validation, performance measurement).
* [x] V-1 — Viewer Stabilization (`docs/PHASE_STATUS.md` "Phase V-1"). Found the entire dev corpus (29 jobs) has 0 bbox-bearing objects and every source PDF 404s, blocking any visual overlay verification — resolved by uploading a real benchmark PDF through the app's own existing upload flow to get a genuinely testable job. Traced coordinate flow end-to-end: confirmed `BoundingBox` (top-left-origin PDF points, direct from PyMuPDF, no transform) matches react-pdf's own rendering convention exactly, cross-checked against real extracted coordinates. Live-verified reading-order overlay alignment on 2 pages at 2 zoom levels, page navigation sync, and Outline→Inspector sync — all correct. Found and fixed 2 real bugs: a zoom-button stale-closure bug (`PdfViewportContext.tsx`/`PdfViewer.tsx` — rapid clicks silently dropped increments) and a systemic invalid-nested-`<p>` React hydration error affecting all 6 object-type detail panels (`ObjectInspectorFrame.tsx`, root-caused and fixed once instead of patched 6 times). `tsc`/`jest`/`next build` clean; both fixes reproduced live before and re-confirmed after. Image/table overlay mapping, page rotation, Markdown line-sync, and PDF-overlay-click selection remain untested — disclosed as data-availability gaps, not skipped work.
* [x] RW-1 — Reviewer Workflow Improvement (`docs/PHASE_STATUS.md` "Phase RW-1"), evidence-backed only: (1/2) confirmed via backend grep that `footnotes.py`/`headings.py`/`lists.py`/`tables.py` all `json.dumps()` structured payloads directly into `CorrectionItem.suggested_value`/`current_value` — the exact "Missing Endnote" raw-JSON problem the mission named, not hypothetical. Built `lib/correctionPreview.ts` (new) to parse all 5 real shapes into a friendly field list; `CorrectionHistoryList.tsx` now shows a headline + "Detected on page N" + friendly fields instead of raw JSON, with all technical fields (rule id, ids, raw values) behind a collapsed "Developer Details ▼" placed after the action buttons (never blocking Accept/Reject). (3/7) `ReadinessPanel.tsx` rebuilt into a full Accessibility Center — real aggregate Critical/Warnings/Passed/Manual-Review counts, WCAG-style per-category breakdown, "Review →" jump links — with zero fabricated data: a category absent from `GET /readiness` is shown as a real "Passed" (backend-truthful, per `compute_readiness`'s own logic), and categories with no rule coverage at all (Reading Order as its own score, Navigation, Language) are named explicitly in an "Awaiting Accessibility Rules Engine" note, never invented. (4/5) terminology pass ("Detected"/"Suggested fix", "Accept & Edit"). Extracted `lib/validationCategories.ts` (new) so the Accessibility Center reuses `ValidationIssueTable.tsx`'s existing category registry instead of duplicating it. `tsc`/`jest` (7/7, 9/9)/`next build` clean. Verified the 5 real payload shapes parse correctly via direct algorithm execution against the literal backend encode-function output (no job in this dev environment has ever produced a cross-source correction — disclosed data-availability gap); live-verified the Accessibility Center against a real 6-issue, 50%-readiness document. Deferred: the Accessibility Rules Engine itself (out of scope by the mission's own instruction — UI prepared to consume it, not built here).

**Roadmap produced by the Design Bible (§41/§46), ranked highest ROI first:**

* [ ] **Milestone 1**: `app/error.tsx` route-level error boundary (Bible §34) — trivial, zero design ambiguity, most overdue item in the project (flagged since F-1, six milestones ago). Still not started.
* [ ] **Milestone 2**: Context-preserving editing — source-strip/Peek affordance in Special-View grids (Bible §9), resolving the F-4.2/F-4.4 OPEN item.
* [ ] **Milestone 3**: Keyboard-coverage completion — `currentIndex`/roving-focus prerequisite for Validation Center + Image/Table/Heading grids (Bible §21), closing the F-3.1-disclosed gap.
* [ ] **Milestone 4**: Validation Center — AI Confidence slider filter + running compliance score in header (Bible §10).
* [ ] **Milestone 5**: Triple Compare (3-way split) + cross-pane synchronized highlight (Bible §7) — gate behind a performance benchmark first (Bible §38).
* [ ] **Milestone 6**: Large Document Mode, per R-1.0's own plan (Bible §30) — benchmark first.
* [ ] **Milestone 7**: Repair Action Plan (Bible §9) + generalized Screen Reader Announcement (Bible §19) — both need a small backend data-shape confirmation first (Bible §40).
* [ ] **Milestone 8**: Command Palette (Bible §20).
* [ ] **Milestone 9**: Export consolidation, empty/loading-state cleanup (Bible §32-35).
* [ ] Postponed, needs a product decision not an engineering one: Settings/Profile scope, light/dark dual-theme scope, responsive-viewport messaging (Bible §3, §26, §29).

Every milestone above runs the full plan → implement → test → benchmark → verify → document → wait-for-approval cycle (Bible §44) — no milestone begins until the previous one is verified and approved.
