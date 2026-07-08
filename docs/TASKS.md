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
* [x] frontend/ (Next.js/React/TypeScript/Tailwind) — upload page + per-document workspace with 9 tabs: Validation, Headings, Images & alt text, Footnotes & endnotes, Tables, OCR, Markdown, Reading Order, Metadata
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
* [ ] Theming sweep — several pre-existing panels still hardcode raw Tailwind colors, not yet on the new theme-token system (see PHASE_STATUS.md Phase M-2)

---

Not yet started (see `KNOWN_LIMITATIONS.md`): equation remediation, multi-column reconstruction, cross-page paragraph stitching, span-level text model (`feature_005_span_level_text_model` — design review complete, no code written).
