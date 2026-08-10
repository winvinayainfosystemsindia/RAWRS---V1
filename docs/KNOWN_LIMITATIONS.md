# RAWRS Known Limitations

## Purpose

Everything in this file is a **deliberate, decided scope boundary or a confirmed gap** — not a bug to file, and not something to "just go fix" without a scope conversation first. Where a limitation was a conscious decision, see `DECISIONS_LOG.md` for the reasoning. Where it's a gap discovered during this audit (documentation said "complete," code says otherwise), that's noted explicitly so it doesn't get mistaken for an intentional boundary.

---

## Consciously deferred — no benchmark coverage / requires architecture sign-off

These are not implemented, on purpose, and should not be started without a scope decision:

* **Table remediation — IMPLEMENTED (FEATURE_015/015.1/015.2/015.3).** Auto-detection via `find_tables(strategy='lines')` (VectorBorderDetector), `HorizontalRuleDetector` (booktabs 3-line academic tables), `SpanAlignmentDetector`, and `ColumnAlignmentDetector` (text-only descriptor grids). Merged cell support, DOCX semantic rendering, TABLE_001–007 validation, AI suggestions, screen reader simulation, full frontend workspace. **Remaining gaps:**
  * **Cross-page table detection not implemented** — tables spanning page boundaries (e.g. Brinkman Tables 2 and 5) are not auto-detected. Each page is treated independently. Requires cross-page geometry tracking; out of scope for Phase 1. Reviewer must create these via "manual table creation" workflow.
  * **"Row 0 is header" heuristic for spatial detections** — `_detect_header_rows()` in `table_extractor.py` unconditionally marks row 0 as the header row for any spatial-analysis table. For Brinkman-style booktabs tables, row 0 is the embedded caption ("Table 3. Teachers' beliefs..."), not the column headers. TABLE_003 does NOT fire because a header row technically exists; reviewer must verify the header assignment in the Tables workspace.
  * **Borderless tables not fitting HorizontalRule/SpanAlignment patterns** (prose-dense, irregular row spacing) still require manual creation. Docling ML-based table detection (for `OCR_REQUIRED` pages) is deferred.
* **Equation remediation** — no equation-handling code exists anywhere in `src/`.
* **Multi-column reconstruction** — no multi-column detection or reconstruction exists.
* **Cross-page paragraph stitching** — a paragraph that spans a page boundary is never rejoined; each `Page`'s text is treated as fully separate. Fixing this would require rethinking how `Page`-level text and `Document`-level page markers interact, which touches the frozen `Page`/`Document` model — flagged in the original benchmark reconciliation as needing its own architecture sign-off, never picked up since.
* **Reading-order reconstruction** — Phase I.1 implements detection (`PAGE_003`). FEATURE_016B adds human-initiated correction via the Reading Order workspace (drag-reorder, approve). Automatic reordering by the pipeline is not implemented and is not planned — per-document human review is the intended workflow. See `DECISIONS_LOG.md` Part 19.
* **AI-generated alt text is on-demand, not automatic.** The Qwen2.5-VL interface (`src/ai/alt_text_generator.py`) is built. The dependencies (`torch`, `transformers`, `qwen-vl-utils`, `psutil`) are **not** in `requirements.txt` — they live in the optional `requirements-ai.txt`, since AI is a pluggable capability the platform must run fully without (see the AI subsystem redesign: startup-time provider initialization with a RAM/VRAM preflight in `src/ai/providers/qwen.py`, `GET /api/ai/status`). The model weights require a one-time download on first real load. All tests run via `RAWRS_AI_STUB=1` stub. Human review workflow (FEATURE_012) is fully implemented with 8 review states. AI generation is always on-demand — reviewers click "Generate AI Alt Text" per image, never auto-run by the pipeline.
* **Page Label Manager (FEATURE_018) regenerates Markdown and DOCX only.** RAWRS has no standalone table of contents, no dedicated navigation pane, no page-number bookmarks, and no PDF export anywhere in the codebase today — building any of those is a separate, larger feature, not part of page-label management. `Page.page_label` (see `PAGE_RULES.md`) is the canonical, reviewer-approved source of truth for a page's final label; any future TOC/nav/PDF-export feature must read it, not re-detect a label independently. One piece of this already comes for free: DOCX's H1–H6 → Word built-in heading style mapping (`docx_generator.py`) means Word's own Navigation Pane already reflects correct page labels once Markdown regenerates, with no separate nav code.
* **Span-level text model (`feature_005_span_level_text_model`)** — `TextBlock` is deliberately line-granularity (one scalar font size, one scalar bold flag per line); PDF span-level data (font name, per-character size/flags, baseline position) that PyMuPDF itself extracts is discarded before any downstream module sees it. A complete design review recommends an additive `Span` model embedded in `TextBlock` (over a parallel `Document.spans` list or a new pipeline stage), with a 4-step migration path — but, consistent with this file's own framing, this is recorded as a reviewed, scope-sign-off-required initiative, not something to start without that sign-off. See `DECISIONS_LOG.md` for the full review. This is the direct prerequisite for closing **bug_005** (footnote/endnote detection, below), and a likely prerequisite (not a full solution by itself) for any future equation/scientific-notation/chemistry-notation work.

## Confirmed gaps found during this audit (not previously documented as limitations)

These differ from the list above: they were described elsewhere as "complete" without this caveat, or weren't called out at all.

* **Heading detection never checks font color or absolute font size against the source PDF.** `docx_generator.py` unconditionally applies black, 16/14/12pt formatting to every heading *in the output*, but `heading_detector.py` has no color signal and uses font size only in relative rank order (largest unique size in the document → H1, etc.), never against an absolute threshold. A document whose true headings were, say, dark blue and 13pt (this actually happened in one benchmark sample) is still detected correctly via rank/bold/isolation — but nothing about color or absolute size is "checked" in the sense of validating the source.
* **bug_003 (positional H1) — CLOSED (L3.2).** Previously: heading detection assumed the document's first non-blank line is always its title, so on one benchmark PDF a journal section kicker label ("Article") won the H1 slot ahead of the real title. Now: evidence decides that a line is a heading and the title position only ranks one that already is (`src/headings/heading_signals.py`). Measured over `samples/benchmark/pdfs/`: 89 content headings → 86, removing exactly the 3 H1s that rested on position alone ("Article", "xlv", and a sentence of body prose) and preserving all 5 corroborated titles unchanged. **New consequence, by design:** a document whose title line carries no typographic support now has *no* H1 rather than a wrong one, and `HEADING_002` reports the absence. This applies to layout-free input (OCR text with no readable font information) as a class.
* **bug_005 — Footnote/endnote detection only recognizes a literal Unicode superscript-digit glyph as a marker (confirmed gap — downgrades Phase K from "VERIFIED COMPLETE" to "PARTIALLY IMPLEMENTED" in `PHASE_STATUS.md`).** A marker encoded the more common real-world way — a plain digit at a smaller font size with PyMuPDF's own superscript flag bit set and a raised baseline — is silently not detected. Confirmed directly on a real regression PDF: 0 of 3 actual footnotes detected end to end. Root-caused as span-level information loss in `TextBlock` (see "Span-level text model" above), not a defect in `footnote_detector.py`'s own logic. **Status: Open. Blocking: `feature_005_span_level_text_model` implementation** — the same root cause also affects superscripts, subscripts, equations, scientific notation, and chemistry notation generally, not just footnotes/endnotes specifically; see `DECISIONS_LOG.md` Part 8 for the full per-category breakdown.
* **OCR validation coverage is narrower than `docs/VALIDATION_RULES.md` implies — partially closed since this was first written.** `OCR_001` (low-confidence Surya-recovered page) and `OCR_002` (excessive unusable-character ratio) now exist and close most of that doc's "OCR Validation" category. Broken-word detection still has no rule ID. `PAGE_003` (reading-order anomalies) remains a separate, Page/Structure-oriented check, not an OCR-quality one.
* **Figure-level validation is incomplete.** `docs/VALIDATION_RULES.md`'s "Figure Validation" category (missing captions, unlinked figure references, missing figure numbering) has no corresponding rule ID. `IMAGE_004` covers alt-text review status, but not caption/numbering completeness.
* **CMYK JPEG DOCX embedding gap — CLOSED (FEATURE_016E).** Previously: `python-docx`'s `add_picture()` raised `UnrecognizedImageError` on CMYK JPEGs, and no validation rule detected the failure. Now: `_docx_compatible_picture_source()` converts CMYK to RGB before embedding, `Image.embedded_in_docx` tracks the result, and `IMAGE_005` (WARNING) fires when an extraction-success image fails to embed. This gap is resolved.
* **Typographic ligature glyphs are preserved as raw Unicode instead of being decomposed to ASCII pairs.** Confirmed 95 occurrences (ﬀ/ﬁ/ﬂ/ﬃ) in one real regression PDF's generated output. No decomposition step exists anywhere in the text-normalization path. Low complexity, no architecture change required to fix — not yet picked up.
* **DOCX notes are native Word notes, and since L4b they are the right *kind* of note.** This entry previously said they were a superscript run inside a `w:hyperlink` pointing at a `w:bookmark`; that mechanism is gone. Notes are real OOXML entries in their own document part. L4b added the second part: `Footnote.note_type` selects `word/footnotes.xml` (`w:footnoteReference`) or `word/endnotes.xml` (`w:endnoteReference`), each with its own relationship, content-type override and Word separator entries. Before it, every note — including every endnote — went into the footnotes part, so Word rendered a document's endnotes at the foot of its pages. Proven by `PI-6` (`src/benchmark/projection.check_docx_notes`), which reads the generated package.
* **The DOCX renderer still reconstructs everything except note type from Markdown (follow-up debt, deliberately not taken on in L4b).** `generate_docx(document, markdown_content)` parses the markdown string for headings, paragraphs, lists, images, captions, page breaks, pipe tables, and both note references and note definitions. L4b removed exactly one reconstruction: *which kind of note this is*, which now comes from `Footnote.note_type` via a label lookup — the same role `<!-- table-id: ... -->` already plays for tables. Everything else remains markdown-derived, and the note *placement* (where a reference sits in the prose, which definitions exist at all) still is. Retiring the rest is the P3/P4 work the ContentStream docstring describes: render both projections from `build_content_stream()` instead of having DOCX re-parse Markdown's output.
* **Mathpix footnote anchor positions are placeholders (Phase M-1, gap closed by Phase M-2).** In the Mathpix import path (`mmd_path` supplied to `run_pipeline()`), inline footnote references (e.g. `[1]`) are imported by `MathpixImportProvider` with `anchor_page_number=1` and `anchor_text=marker`. This is a known placeholder: the Mathpix MMD format records footnote bodies via `\footnotetext{N}{body}` but does not encode the page or character position of the corresponding inline reference. Phase M-2 will use the Mathpix DOCX's H6 page markers to resolve the actual anchor page. Until then, all Mathpix footnote anchors point to page 1.
* **Mathpix page assignment is proportional, not exact (Phase M-1, gap closed by Phase M-2).** `MathpixImportProvider` assigns each MMD block to a page using `math.ceil(source_line / total_lines * page_count)` — a position ratio, not a true page boundary. Phase M-2 will replace this with exact page mapping using H6 page markers embedded in the Mathpix DOCX.
* **`PAGE_001` fires as a false positive under `AUTO` or `DISABLED` page numbering policy.** `validator.py`'s `_check_page_markers()` does not receive the active `PageNumberingPolicy` and therefore cannot distinguish an intentionally suppressed marker from an accidentally omitted one. Under `AUTO` mode, pages with no detected `printed_label` have no H6 marker by design; `PAGE_001` (severity ERROR) fires for each of them anyway. Fix requires threading the policy into `validate_document()`. Deferred — see `DECISIONS_LOG.md` Part 16.
* **Review workspaces exist for images, headings, footnotes, reading order, and metadata (FEATURE_012 + FEATURE_016).** `AltTextStatus` has 8 values; `HeadingReviewStatus` has 4; `FootnoteReviewStatus` has 4; `ReadingOrderStatus` has 3. All have corresponding API endpoints and frontend panels. What remains without a review loop: table cell text (can be edited via the Tables workspace), paragraph body text, cross-document field corrections, and marking a validation finding as "intentional/acceptable".

* **The validation queue and the readiness gate both double-count cross-source `_VERIFY_` findings.** Every cross-source finding is emitted twice from the same `Finding` (`verification/engine.py`): once as an actionable `CorrectionRecord` (Corrections workspace, accept/reject changes output) and once as a read-only `ValidationIssue` mirror with `suggested_action=None` hardcoded (`engine.py` `findings_to_validation_issues`, via `validator.py`). Runtime discovery over the 10-doc corpus found **385 of 550 queue issues (70%)** are these mirrors. **Partially addressed (2026-07-27):** `ValidationIssueTable.tsx` now partitions the queue on `suggested_action` — actionable issues stay in the main queue, mirrors collapse into a "Verification Findings" section (default queue 550→165). This is presentation-only; **the readiness gate is unchanged and still counts the WARNING-severity mirrors** (`readiness.py` `compute_readiness` counts error+warning), so `IMAGE_VERIFY_002` (×105) and `LIST_VERIFY_002` (×53) keep "Export Ready" red until ~300 cross-source warnings clear — even though they are managed as `CorrectionRecord`s, not from the queue. Deferred (higher-risk, backend): make export readiness key on unresolved `CorrectionRecord`s, not their ValidationIssue mirrors.
* **`IMAGE_VERIFY_002` ("image not in the Mathpix package") false-positives — partially mitigated (2026-07-27).** Scanned PDFs store each page as several full-width raster bands; each band was treated as a content image and fired `IMAGE_VERIFY_002`. `image_extractor.py`'s `_page_reconstruction_indices()` now detects and filters those tiling bands (verified on the corpus: Bryman −89, Bruner −460 bands; zero collateral on figure-bearing docs). **Residual gap:** a genuine born-digital embedded figure that is absent from the Mathpix package still fires `IMAGE_VERIFY_002` correctly-by-design — this is a true cross-source discrepancy, surfaced as a correction, not a bug.

## Confirmed ground-truth inconsistencies (benchmark, not RAWRS)

These were found by comparing RAWRS against a 4-PDF benchmark set and are **properties of that benchmark set**, not RAWRS defects. Recorded here so nobody re-discovers them as if new:

* "REFERENCES" was treated as a heading in one benchmark document and as plain text in another, for the same literal keyword. RAWRS resolved this with a fixed rule (see `DECISIONS_LOG.md` C6) that will only match one of the two inconsistent samples by construction.
* Page markers were present in some benchmark samples and entirely absent in others, despite `docs/PAGE_RULES.md`'s original unconditional "every page" rule. RAWRS originally kept the unconditional rule (C2) and treated the marker-less samples as benchmark defects. **Now resolved (2026-06-28):** the configurable page-numbering policy (`DECISIONS_LOG.md` Part 16) makes this correct — `AUTO` mode emits only genuinely detected printed numbers and produces no marker on pages where none is printed, which is the right behavior for those benchmark samples.
* One benchmark sample's expected DOCX had zero page breaks despite its own expected Markdown having page-break markers — an internal inconsistency within that one sample's own ground truth, not something RAWRS should replicate (C3).
* The benchmark's own expected Markdown and expected DOCX for the same source document structurally disagreed with each other (title-block merging, image reference counts) in at least one sample — evidence that "Markdown as source of truth" wasn't literally how that particular benchmark pair was produced. RAWRS's own pipeline still enforces this principle for its own output (C8).

## Out of scope by explicit project constraint (not a gap — never planned for Phase 1)

* Accessibility tagging / PDF-UA-equivalent structure tags.
* Knowledge graphs.
* AI model training infrastructure (dataset *collection* is in scope and built; *training* is not).
* Multi-agent systems.
* Paid/cloud APIs in the production pipeline.
* Databases, containers, microservices.

## Platform layer (corrected — no longer absent)

**This section previously said "no frontend, no backend API, no review dashboard, no upload mechanism." That is no longer true and should not be relied on.** A FastAPI backend (`src/api/`) and a Next.js/React/TypeScript/Tailwind frontend (`frontend/`) both exist — confirmed by direct inspection and by exercising the backend over real HTTP. See `CURRENT_STATE.md` for what's actually built (upload page, per-document tabbed workspace, download buttons, in-memory-only job tracking with no database).

**FEATURE_012 and FEATURE_016 implemented review workspaces for images, headings, footnotes, reading order, and metadata.** The full workspace has tabs: Validation, Headings, Images & alt text, Footnotes & endnotes, Tables, OCR, Markdown, Reading Order, Metadata. The DOCX download re-generates from current in-memory state when any field has been reviewed. What remains genuinely absent: paragraph body text corrections, validation-finding acknowledgement (marking a finding as intentional/acceptable), and any persistence across process restarts (job tracking is in-memory only).

---

## Architectural debt as of the 2026-08-03 freeze

Recorded during the Architecture Freeze consolidation. Each is a **known, measured**
gap between the architecture the ADRs describe and the code that exists. None is a
regression; several became visible only once ADR-020's projection gate existed.

### Blocks or complicates P3

| Debt | Measured | Why it matters for P3 |
|---|---|---|
| **The line-by-line OCR render path still owns a text-keyed suppression cascade.** `_render_page_body_line_by_line` has no `TextBlock` data, so it cannot key on ids and keeps `_front_matter_source_texts`/`_caption_source_texts`/the notes regex. | **41 of 161 corpus pages (25%)** | P3 renders from `ContentStream`, which is built from blocks. Those pages have none, so either the stream degrades for a quarter of the corpus or the OCR path must first produce blocks. **This is the single largest obstacle to P3.** |
| **`Image` has no ordering field.** `_render_images()` appends images at page end because the model cannot say where they go. | **122 of 122 corpus images unpositioned** | `build_content_stream` emits `IMAGE` nodes after body content for the same reason. P3 would freeze that approximation into the stream. |
| **`Heading` has no "this is the document title" fact.** The renderer decides the front-matter title heading does not render (FE-0-005). | fires on every titled document | A renderer-owned semantic decision (PI-6). P3 must either move it into the model or carry it forward as an exception. |
| **`## Endnotes` is generated by the renderer.** No model object holds it. | 1 finding, brinkman | Reported by ADR-020's checker as `renderer_generated_object`. P3's stream has no node to emit for it. |

### Correction-rail leaks

| Debt | Detail |
|---|---|
| `src/mathpix/ingestor.py::_register_figures` extends `verification_findings` directly | Import-time figure findings never become `CorrectionRecord`s, so they cannot be applied, rejected or undone. Contradicts ADR-016. |
| The page-label handler records a `CorrectionRecord` but mutates the document directly | Its `revert()` would need a `page_label` verifier that does not exist. |
| `ImportProvider` (`src/importers/base.py`) is implemented only by Mathpix | The protocol is real but unexercised; a second provider is the only way to know it generalises. |

### Model ambiguities

| Debt | Detail |
|---|---|
| `SemanticObject.confidence` carries two meanings | The detector writes detection strength; the cross-source verifier overwrites it with match confidence. Documented on `Heading.evidence_items`; read that field when detection strength is what you mean. |
| `_apply_inline_format` derives bold/italic from spans at render time | Presentation computed from model data. `Paragraph.is_bold`/`is_italic` would move it, and P4 needs it moved anyway — DOCX currently recovers it by re-parsing `**`. |
| ~~The lockstep positional cursor (`block_cursor`) survives in the Markdown path~~ | **Retired by P3b (2026-08-10).** The paragraph path walks the `ContentStream` instead. Re-measured immediately before removal: 0 drift, 0 lines past the last block, 0 blocks left behind, over the 120 block-bearing pages. The line-by-line fallback for the other 41 pages still walks text, having no blocks to walk instead. |

### Detector defects surfaced by ADR-020 (not projection defects)

| Debt | Measured |
|---|---|
| Table bbox over-capture claims lines the table's own cells do not carry | 2 tables (NoE p24 drops `Unverifiable`; brinkman p9 drops 4 `n¼` tokens) |
| Front-matter author splitting drops connective words | 1 document (`Michael Fullan and Andy Hargreaves` → `Michael Fullan, Andy Hargreaves`) |
| Heading false positives previously masked by the pre-P2 queue stall | 3 (`Chapter 3);` — a mid-sentence cross-reference the detector's own comments already name as a known trap; `"ox.o..IA1.M· ~` and `NuN 14k` — OCR garbage from a scanned title page) |

### Benchmark

| Debt | Detail |
|---|---|
| `running_header_suppression_accuracy` is structurally binary | The benchmark DOCX has zero repeated-line candidates, so `leak == r` always and the metric can only read 0.0 or 1.0. |
| `TestStructureDetectionDoesNotChangeExistingOutputs`'s markdown assertion is vacuous | Both runs write the same path, so the second overwrites the first and both reads return the same bytes. The heading and validation assertions in that test are sound; the markdown one proves nothing. |
