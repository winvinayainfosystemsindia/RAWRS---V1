# RAWRS Phase Status

## Purpose

The authoritative, per-phase implementation status of RAWRS, reconciled directly against source code and the live test suite (not against a handover document or aspirational plan). This file supersedes `TASKS.md` as the place to check "is X actually done."

**Verdict legend:**

* **VERIFIED COMPLETE** — implemented, tested, behaves as described.
* **PARTIALLY IMPLEMENTED** — real implementation exists but some sub-claim is missing, untested, or narrower than described.
* **DOCUMENTATION OUTDATED** — the implementation is fine; a *description* of it (in a doc, comment, or prior handover) is wrong.
* **IMPLEMENTATION MISSING** — claimed, not built.

Last reconciled against a full local test run: **486 passed, 1 skipped, 0 failed** (`pytest`, all markers included, ~27 min including real Docling/Surya OCR calls against benchmark PDFs). **Superseded by a later reconciliation pass** covering XML Sanitization Architecture C, bug_001 (paragraph reconstruction), and bug_002 (heading fallback tier): the fast subset (`pytest -m "not real_docling and not real_surya"`) was directly re-verified at **567 passed, 1 skipped, 5 deselected, 0 failed**. The full suite (including the slow real-OCR-marked tests) was **not** re-run in that later pass — treat the `486` full-suite figure as stale, not reconfirmed, until someone actually re-runs `pytest` with no marker filters.

---

## Phase A — Direct Text Extraction

**Verdict: VERIFIED COMPLETE**

PyMuPDF native text extraction for born-digital PDFs. Pages with extractable text get `OCRConfidence.HIGH` (no recognition uncertainty); pages with no usable text are left untouched (`ocr_confidence = None`) and remain candidates for OCR.

* Code: `src/ocr/extractor.py` (confidence assignment at the point text is extracted), `src/models/page.py` (`OCRConfidence` enum).
* Tests: `tests/test_ocr.py` (empty-page-stays-pending case; born-digital-PDF-gets-HIGH case).

---

## Phase D.0 — OCR Routing

**Verdict: VERIFIED COMPLETE**

Every page is classified `DIRECT_TEXT` or `OCR_REQUIRED` *before* any OCR engine runs, based on the page's already-extracted text (length < 20 chars, or >10% control/replacement-character ratio → `OCR_REQUIRED`). Classification is per page, not per document — a single PDF can mix both types.

* Code: `src/ocr/router.py` (`classify_page`, `route_pages`), `src/models/page.py` (`PageType` enum).
* Tests: `tests/test_router.py` (unit tests per classification rule; mixed-document scenarios proving per-page independence).

---

## Phase D.1 — Docling OCR

**Verdict: VERIFIED COMPLETE**

Docling is the primary engine for `OCR_REQUIRED` pages, explicitly using `force_full_page_ocr=True`. Recovered text gets `OCRConfidence.MEDIUM`.

* Code: `src/ocr/docling_config.py` (the flag, with an inline comment recording *why*: Docling's default layout-driven OCR returned zero text on real benchmark pages confirmed to contain genuine prose), `src/ocr/docling_engine.py`.
* Tests: `tests/test_docling_engine.py`, including a `@pytest.mark.real_docling` test against an actual benchmark PDF (not mocked).

---

## Phase D.2 — Surya Fallback OCR

**Verdict: VERIFIED COMPLETE — with a corrected, independently-traced backend description (see below)**

Surya runs only on pages Docling left empty (never on `DIRECT_TEXT` pages or pages Docling already recovered text for). CPU-based. Recovered text gets `OCRConfidence.LOW` (one rung below Docling, since it's only invoked after the primary engine already failed on that page).

* Code: `src/ocr/surya_engine.py`, `src/ocr/surya_config.py`.
* Tests: `tests/test_surya_engine.py` (fallback-only-when-Docling-empty cases; LOW confidence assignment).
* **Backend, corrected by a dedicated Surya Backend Architecture Audit:** RAWRS's own code (`surya_config.py`, `surya_engine.py`) calls only `surya.recognition.RecognitionPredictor` and `surya.inference.SuryaInferenceManager` — it never references llama.cpp directly, and `requirements.txt` has no `llama-cpp-python` entry, which is true and was correctly observed by an earlier pass. **However, that pass stopped there and incorrectly concluded Surya does not use llama.cpp at all.** Tracing into the installed `surya-ocr==0.20.0` package itself shows otherwise: `SuryaInferenceManager` auto-selects an inference backend per host (`vllm` if an NVIDIA GPU is present, `llamacpp` otherwise), and on this project's CPU-only deployment that resolves to `llamacpp` — which spawns the real upstream `llama-server` binary and serves the `surya-2.gguf` vision-language model through it over a local OpenAI-compatible HTTP API. This was confirmed with live evidence on the actual deployment host: a `LLAMA_CPP_BINARY` environment variable pointing at a real `llama-server.exe`, a cached `surya-2.gguf` + `surya-2-mmproj.gguf` model pair downloaded from Hugging Face Hub, and a `llama-server` runtime log showing genuine per-token generation timing for a completed OCR request. The earlier "not llama.cpp" correction in this file, `OCR_RULES.md`, `TECH_STACK.md`, and `DECISIONS_LOG.md` was itself wrong and has now been reversed. See `OCR_RULES.md` for the full trace and `DECISIONS_LOG.md` for the recorded history of both the original claim and this reversal.
* **Why the original audit missed this:** it verified "no llama.cpp reference in RAWRS's own `src/`" (true) and treated that as equivalent to "Surya doesn't use llama.cpp" (false) — without dereferencing into what the installed package version actually does at runtime. `surya-ocr` is unpinned in `requirements.txt`; the installed 0.20.0 is a VLM-backed rewrite ("Surya2") with a fundamentally different architecture from classical Surya, which this project's documentation had not caught up to. See "Dependency Changes" in the corresponding audit response for the version pin now in place.

---

## Phase B — Heading Detection

**Verdict: PARTIALLY IMPLEMENTED**

* **H1–H6 support:** implemented. `HeadingLevel` enum covers all six levels; `_classify_line()` in `src/headings/heading_detector.py` routes lines to H1–H5 or generates the H6 page marker.
* **Detection signal:** font-size-rank (largest unique size in the document → H1, next → H2, …) plus bold-relative-to-body-text and line isolation, from `src/structure/layout_signals.py`. Numbering/keyword patterns (`Unit N`, `Chapter N`, `3.1`) fire as a secondary/override signal. A fixed keyword list (References/Bibliography/Appendix/Acknowledgements) always promotes to H2 regardless of layout signal (see `DECISIONS_LOG.md` C5/C6).
* **bug_002 — fallback tier (new since this phase was last verified):** a fifth, last-resort tier in `_classify_line()`/`_is_fallback_heading()`, reached only when numbering/H1-slot/keyword/bold have all declined, for headings rendered in a distinct embedded font subset that the bold-gate can't see (no `"bold"` substring, no PyMuPDF bold flag). Fires only when font≠document-body-font AND the (font, size) pair recurs ≥2× **among sole-line-PyMuPDF-block contributions only** AND the line is itself a sole-line block AND its size ≥ the document's body size AND it isn't the H1-slot line AND it has an alphabetic character. The sole-line-block-only recurrence count and the size≥body-size condition were both added after real regressions were found during implementation (a non-sole-line masthead line inflating recurrence for an unrelated byline; table/figure captions and table-footnote lines otherwise satisfying every other gate identically to real headings) — not designed upfront. Independent `_build_fallback_tier_index()` PDF pass; does not touch the shared `line_layout()`/`LineLayout` signal `structure_detector.py` also depends on.
* **Navigation Pane support:** implemented and verified — `docx_generator.py` maps every heading to Word's built-in `Heading 1`–`Heading 6` paragraph styles via `add_heading()`, which is exactly what Word's Navigation Pane reads.
* **Bold formatting check:** implemented as a detection signal (`layout_signals.span_is_bold`).
* **"Correct sizes" / "Black text" checks — gap:** these are only *applied* when generating DOCX output (`docx_generator.py` sets 16pt/14pt/12pt and `RGBColor(0,0,0)` on every heading run unconditionally). Neither is ever *inspected on the source PDF* during detection — `heading_detector.py` has no font-color signal at all, and font size is used only in relative rank order, never against an absolute pt threshold. A heading detected from a non-black or oddly-sized source span would still be detected and then unconditionally reformatted to black/16-14-12pt in the output. Describing this as "black text check" / "correct sizes check" during *detection* is not accurate.
* **"Validated against benchmark PDFs" — caveat:** benchmark tests (`tests/test_headings.py`) verify heading presence and correct level classification against real PDFs, but do not verify that formatting rules existed in the source PDF being detected.
* **Known open gap (bug_003, not yet fixed):** the H1-positional-slot rule assumes the document's first non-blank line is always the title. On at least one real regression PDF, that line is a journal section-type kicker label ("Article") printed above the real title, which wins the H1 slot instead of the title. Not fixed as part of bug_002's scope.
* **bug_007 — fixed 2026-06-25:** an incomplete edit had changed `_build_layout_index()`'s return signature to a 3-tuple (scaffolding for a never-finished "Wrapped Heading Continuation Repair" feature) without updating `detect_headings()`'s single call site, which still unpacked 2 values. This made `detect_headings()` raise unconditionally on every document — a silent total failure of this phase in the real API (caught and reported as `ProcessingStatus.FAILED` by `phase1_pipeline.py`, not a crash), not just a test-suite artifact. Fixed by updating the call site to accept and discard the unused third value. See `DECISIONS_LOG.md` Part 10.
* **`feature_007_wrapped_heading_continuation_repair` — implemented 2026-06-25** (the feature `bug_007` found scaffolded but unbuilt): a logical heading spanning multiple PDF lines (e.g. `"1.16  Subjectivity and objectivity in"` + `"educational research"`) was previously detected as two separate `Heading` objects instead of one. After classification, a bold anchor line now absorbs up to 4 following same-layout lines confirmed as continuations — same PyMuPDF block always confirms; cross-block requires `gap_ratio` in a corpus-calibrated window (`-0.20` to `+0.45`, derived from an exhaustive sweep of the whole benchmark corpus, 1 real positive example with a 0.54 margin to the nearest false candidate). Local, heading-only soft-hyphen repair on absorption (`_join_with_local_hyphen_repair()`), 4-line absorption cap, defensive guard against absorbing a line that matches its own heading pattern. Audit and full design: `samples/regressions/feature_007_wrapped_heading_continuation_repair/notes_md/wrapped_heading_continuation_repair_audit.md`. Verified document-by-document against all 10 benchmark PDFs (true before/after comparison, not prediction): `Nature of Enquiry` 48→35, `Aims of Education` 3→2, `sockett_profession` 21→15 (a same-block-driven beneficial side effect, confirmed harmless), 7 PDFs unchanged. See `DECISIONS_LOG.md` Part 12.
* Tests: `tests/test_headings.py` (layout-based detection, benchmark PDFs, `TestBug002FallbackTier`), `tests/test_docx.py` (`TestHeadingHierarchy`, `TestNavigationPaneCompatibility`). No new automated test added for `feature_007` in this pass — verified directly against real benchmark PDFs instead.

---

## Phase C — Image Filtering

**Verdict: VERIFIED COMPLETE**

Five independent filter criteria in `src/images/image_extractor.py` (`_filter_reason()`): background/full-page images (≥85% page area), extreme-aspect-ratio slivers (>8:1 with short side <50pt), tiny rasters (<16px), duplicates (byte-digest match), and non-referenced images (using `get_image_info(xrefs=True)` rather than `get_images(full=True)`).

* Tests: `tests/test_images.py`, including regression tests pinning exact counts against real benchmark PDFs (54→2, 11→4 raw-vs-kept).

---

## Phase F.1 — Image Position Persistence

**Verdict: VERIFIED COMPLETE**

`Image.bbox: Optional[BoundingBox]`, populated at extraction time, in the same PyMuPDF page-coordinate system as `TextBlock.bbox`. This is what makes proximity-based caption matching (F.2) possible without recomputing position data.

* Code: `src/models/image.py`, `src/images/image_extractor.py`.
* Tests: `tests/test_images.py` (`TestImageBboxPersistence`) — bbox populated even on failed extractions.

---

## Phase F.2 — Figure/Caption Detection

**Verdict: VERIFIED COMPLETE**

Deterministic regex + proximity matching in `image_extractor.py`'s `_find_caption_block()`: searches `Document.blocks` on the same page for a `Figure N` / `Fig. N` / `FIGURE N` pattern within 36pt vertical distance of the image. Each text block can be claimed by at most one image.

* Tests: `tests/test_images.py` (`TestFigureCaptionDetection`) — case-insensitivity, decimal numbering, proximity boundaries, exclusive claiming, non-matching text.

---

## Phase F.3 — Alt-Text Infrastructure

**Verdict: VERIFIED COMPLETE (as infrastructure — not generation; see `KNOWN_LIMITATIONS.md`)**

`Figure.alt_text` and `Figure.alt_text_status` (`AltTextStatus.PENDING_REVIEW` / `HUMAN_REVIEWED`) exist. Every retained image gets a deterministic placeholder (`"{caption}: description pending human review"` or `"Image from page {N}: description pending human review"`) and is unconditionally marked `PENDING_REVIEW`. `HUMAN_REVIEWED` is defined but never set anywhere — there is no mechanism yet to feed a human reviewer's edit back into the model.

* Code: `src/models/figure.py`, `src/images/image_extractor.py` (`_build_placeholder_alt_text()`).
* Tests: `tests/test_images.py` (`TestPlaceholderAltText`) — deterministic templates, every benchmark image gets a placeholder.
* **Documentation note:** This phase's completeness directly contradicts the literal text of `docs/PHASE1_SCOPE.md` and `docs/RAWRS_PROJECT_CONTEXT.md`, which list "Alt Text Generation" as unconditionally out of scope. Resolved in this reconciliation pass — see `DECISIONS_LOG.md` (C4) and the updated scope docs: AI-*generated* alt text remains out of scope; rule-based placeholder *infrastructure* is in scope and complete.

---

## Phase F.4 — Markdown / DOCX Alt-Text Wiring

**Verdict: VERIFIED COMPLETE**

* Markdown: `markdown_builder.py` embeds `image.figure.alt_text` into standard image syntax (`![{alt_text}]({path})`).
* DOCX: `docx_generator.py` sets the OOXML accessibility attributes directly — `picture._inline.docPr.set("descr", alt_text)` and `.set("title", alt_text)`.
* Tests: `tests/test_markdown.py`, `tests/test_docx.py` (`TestImageAltTextMetadata`).

---

## Phase F.5 — Dataset Collection

**Verdict: VERIFIED COMPLETE**

`phase1_pipeline.py`'s `_write_alt_text_dataset()` writes `outputs/alt_text_dataset/{stem}.json` per processed document: image metadata, bbox, figure/caption/alt-text/status, and nearby text blocks for context. Written for every document, including zero-image documents; failed extractions excluded.

* Tests: `tests/test_pipeline.py` (`TestAltTextDatasetCollection`).
* Note: the `outputs/alt_text_dataset/` directory does not exist in the repo at rest — it's an output, created on first pipeline run. No code exists yet for the "future planned" `ocr_dataset/`, `heading_dataset/`, `footnote_dataset/`, or `validation_dataset/` directories — confirmed correctly described as not-yet-built.

---

## Phase H — Structure Detection

**Verdict: VERIFIED COMPLETE (as originally scoped) — with a confirmed downstream information-loss consequence, see feature_005 below**

`BoundingBox` (x0/y0/x1/y1), `TextBlock` (page_number, text, bbox, order, font_size, is_bold, **source_block_index** — added for bug_001, see Paragraph Reconstruction below), and `Document.blocks: List[TextBlock]` all exist. `detect_structure()` runs at pipeline Stage 3 (right after text extraction), is purely additive (never reads or alters reading order, columns, tables, or existing fields), and is already consumed by Phase K (footnote detection reads `Document.blocks` for font-size-drop signals) and by `src/structure/paragraph_grouper.py` (bug_001).

* Code: `src/models/bounding_box.py`, `src/models/text_block.py`, `src/models/document.py` (`blocks` field), `src/structure/structure_detector.py`, wired in at `src/pipeline/phase1_pipeline.py`.
* Tests: `tests/test_structure_detector.py` — real and synthetic PDFs, blank pages, scanned pages, OCR-only pages, corrupt-PDF error handling.
* **Documentation gap (not a code gap):** this entire phase — its models, its pipeline stage, its purpose — is absent from `docs/ARCHITECTURE.md`'s Core Modules section, even though the module is named in that same doc's high-level workflow diagram. Fixed in `ARCHITECTURE_CURRENT.md`.
* **Confirmed downstream consequence (a design review, not a code defect in this phase):** `TextBlock`'s deliberate line-granularity (one scalar `font_size`, one scalar `is_bold` per line, computed via max-of-line size and >50%-char-majority bold vote) discards PDF span-level data — font name, per-character size/flags, baseline position — that PyMuPDF itself extracts and exposes. Confirmed directly (not inferred) via real span dumps: a true footnote-marker superscript carries PyMuPDF's `TEXT_FONT_SUPERSCRIPT` flag, a smaller size, and a raised baseline, none of which survive into `TextBlock`. This is the confirmed root cause of Phase K's footnote-detection gap (below) and was the subject of a completed design review, `feature_005_span_level_text_model` (recommendation: an additive `Span` model embedded in `TextBlock`; not implemented). See `KNOWN_LIMITATIONS.md`.
* **`feature_009_printed_page_number_preservation` (implemented 2026-06-25):** `detect_structure()`'s per-page scan now also populates `Page.printed_label: Optional[str]` — the page number actually printed on the page (e.g. "3", "xlv"), distinct from `page_number`'s physical position, read from a short isolated numeric-or-roman-numeral line in the top/bottom 12% margin at any horizontal position. Detected per-page, not per-document (a single global offset is provably wrong for at least one real benchmark PDF, which splices non-contiguous chapters); falls back to `None` (physical numbering downstream) whenever zero or more than one candidate is found on a page, rather than guessing. `heading_detector.py`/`markdown_builder.py`'s H6 page-marker generation now prefer this label when present. Full audit and benchmark verification: `samples/regressions/feature_009_printed_page_number_preservation/notes_md/printed_page_number_audit.md`. See `DECISIONS_LOG.md` Part 13.
* **Configurable Page Numbering Policy (implemented 2026-06-28):** H6 page-marker generation is now configurable via `src/config/page_numbering.PageNumberingPolicy`. Four modes: `AUTO` (emit only detected `Page.printed_label`; suppress pages where it is `None`), `MANUAL_RANGE` (emit markers only for physical pages in a `[range_start, range_end]` window), `MANUAL_NUMBER_OVERRIDE` (emit for every page, numbered sequentially from a user-specified `number_start`), `DISABLED` (no markers). The policy is threaded through `detect_headings()`, `build_markdown()`, and `run_pipeline()` as an optional parameter (`page_numbering_policy: Optional[PageNumberingPolicy] = None`); when `None`, the original behavior is preserved exactly (every page gets a marker, `printed_label or str(page_number)`). 41 regression tests in `tests/test_page_numbering_policy.py`. See `DECISIONS_LOG.md` Part 16 and `docs/PAGE_RULES.md` for the full mode descriptions. **Known gap:** `PAGE_001` validation does not receive the active policy and fires as a false positive on pages whose markers are intentionally suppressed by `AUTO` or `DISABLED` mode.

---

## Phase L — Paragraph Reconstruction (bug_001)

**Verdict: VERIFIED COMPLETE**

Two independent, compounding bugs, found via a dedicated regression audit (`samples/regressions/bug_001_brinkman_word_splitting/notes_md/root_cause_audit.md`) and fixed together by one mechanism (Option B of three designed candidates — see `notes_md/paragraph_reconstruction_design_review.md` in the same regression folder):

* **Bug 1 (extraction-level):** PyMuPDF's own line-clustering mis-segments a justified PDF line into multiple fragments when inter-word gaps are encoded as absolute positioning jumps rather than literal space-character glyphs — a PDF-producer-specific encoding quirk, upstream of RAWRS, inherited verbatim by every consumer that re-derives from PyMuPDF.
* **Bug 2 (rendering-level, pervasive):** `src/markdown/markdown_builder.py::_render_page_body()` had no paragraph-joining logic at all — every `page.cleaned_text` line became its own markdown paragraph block, in every document, not just the one sentence originally reported.

**Fix:** `TextBlock.source_block_index` (additive field, Phase H) plus a new module, `src/structure/paragraph_grouper.py::group_into_paragraphs()` — merges same-`source_block_index` lines into paragraphs (fixes Bug 2), gated by a same-baseline (bbox y0/y1 tolerance) + x-continuity/gap guard against multi-column false-merges (fixes Bug 1), with a vertical-gap fallback reusing the validator's already-tested 1.5×-median-line-height threshold. Wired into `markdown_builder.py`.

* Code: `src/structure/paragraph_grouper.py`, `src/models/paragraph.py` (the `Paragraph` model — deliberately transient, not stored on `Document`, consumed within one `markdown_builder.py` call), `src/models/text_block.py` (`source_block_index` field).
* Tests: `tests/test_paragraph_grouper.py`, plus updated cases in `tests/test_markdown.py`/`tests/test_docx.py`.
* Regression evidence: the Brinkman regression PDF's generated Markdown went from 2037 lines (one paragraph per raw PDF line, the Bug 2 symptom) to 545 lines (close to the expected 362; the remaining gap is table/footnote rendering, a separate, already-documented limitation, not a paragraph-joining defect).

**feature_010 update (2026-06-25):** the Bug 1 multi-column safety guard inside `_starts_new_paragraph()` (distinct from the same-baseline merge guard above) was found, via a dedicated audit, to be miscalibrated for at least one PDF producer (`iLovePDF` — Nature of Enquiry): it treated *any* bbox y-overlap as a column boundary, including the ~1-2.5pt overlap ordinary same-column line-wraps have in that producer's output, causing 2,324 false-positive paragraph splits (96.8% line-count inflation vs. expected). Fixed with a calibrated magnitude floor, `_OVERLAP_GUARD_MIN_PT = 4.0pt` — see `DECISIONS_LOG.md` Part 15 for full before/after numbers and regression verification against bug_001/bug_005/feature_007.

---

## Phase K — Footnotes & Endnotes

**Verdict: PARTIALLY IMPLEMENTED — downgraded from "VERIFIED COMPLETE" after a confirmed detection-coverage gap, plus the terminology nuance already on record below**

* **bug_005 — confirmed gap (not previously documented as a limitation):** detection only recognizes a footnote/endnote marker when it is a **literal Unicode superscript-digit glyph** (U+00B9/U+00B2/U+00B3/U+2070/U+2074–U+2079) glued onto a word. A marker encoded the more common real-world way — a plain digit at a smaller font size with PyMuPDF's own superscript flag bit set and a raised baseline — is silently not detected. Confirmed directly on a real regression PDF: 0 of 3 actual footnotes detected, end to end. Root-caused as span-level information loss in Phase H's `TextBlock` model (see above), not a defect in this module's own logic — `footnote_detector.py`'s logic is internally consistent against the only signal it's given. Affected features beyond footnotes/endnotes themselves: superscripts, subscripts, equations, scientific notation, chemistry notation (per-category detail in `DECISIONS_LOG.md` Part 8). **Status: Open. Blocking: `feature_005_span_level_text_model` implementation.** See `KNOWN_LIMITATIONS.md`.
* **Detection (as far as the above signal allows):** Unicode superscript-digit markers glued to the preceding word (`src/footnotes/footnote_detector.py`).
* **Endnote detection is genuinely distinct from footnote detection** — not just a comment. A dedicated "Notes"/"Endnotes" section-heading pattern switches a document into endnote scoping (document-wide numbering) instead of footnote scoping (per-page numbering, resets each page).
* **Marker ↔ body linking:** real, not just co-detection — `_link_and_collect()` only promotes a marker+body pair to a `Footnote` when both exist and match by number; orphaned markers or bodies are dropped, not guessed at.
* **Markdown syntax:** Pandoc-style page-qualified labels, `[^p{page}-{number}]` inline and as a definition, to avoid collisions from per-page-reset numbering. Endnotes collect into a dedicated `## Endnotes` section.
* **DOCX preservation — terminology nuance:** the prior description "DOCX bookmark/hyperlink preservation" is technically accurate but can mislead. RAWRS does **not** use Word's native `w:footnote`/`w:endnote` OOXML elements (python-docx has no API for these, as the original claim correctly noted). Instead, it builds a superscript run wrapped in a `w:hyperlink` pointing at a `w:bookmark` in the body text — a real, clickable, traversable internal reference, but the note body still renders as ordinary body text with a bookmark, **not** in Word's auto-numbered footnote/endnote pane. If a future requirement needs notes to appear in Word's native footnote pane, that is new work, not something this phase already provides.
* **Validation support:** `NOTE_001` (footnote detected) / `NOTE_002` (endnote detected), both `Severity.INFO`.
* Tests: `tests/test_footnote_detector.py` (worked example from the original brief, cross-page endnote linking, case-insensitive section detection, per-page vs. global numbering scoping, orphan-marker/orphan-body rejection), `tests/test_docx.py` (file opens cleanly with footnotes present).
* **Forward reference:** bug_005 (above) is the direct motivation for `feature_005_span_level_text_model`, a completed design review (no implementation) proposing an additive `Span` model on `TextBlock` as the fix. See `KNOWN_LIMITATIONS.md` for the recorded status.

---

## XML Sanitization Architecture (Defense in Depth)

**Verdict: VERIFIED COMPLETE**

A production PDF crashed `generate_docx()` with an XML-compatibility error from a character (e.g. U+0002, from a broken PDF font/ToUnicode mapping) that OOXML 1.0 disallows. Tracing every text path found three independent PyMuPDF read passes, only one of which had any cleanup at all (whitespace-only, never XML-legality) — a source-only fix would have left figure captions and footnote/endnote text vulnerable, and would have left all future AI-generated text (alt text, equations, tables) unprotected by construction, since generated text has no PDF-extraction call to attach a sanitizer to.

Three layers, each independently necessary (Architecture C, chosen over source-only and export-boundary-only — see `DECISIONS_LOG.md` Part 5 for the full comparison):

1. **Layer 1** (`src/utils/text_sanitization.py`) — sanitizes at every point text first enters the Document model (`src/ocr/extractor.py`, `src/ocr/docling_engine.py`, `src/ocr/surya_engine.py`, `src/structure/structure_detector.py`).
2. **Layer 2** (`src/validation/validator.py`, rule `DOC_004`, `Severity.WARNING` — by the time it can fire, Layer 1 has already removed the character and the document has already generated successfully, so "processing quality is compromised" is false by construction) — discloses every place Layer 1 had to act, via `Document.sanitization_events` (`src/models/sanitization.py`).
3. **Layer 3** (`src/docx/docx_generator.py`, `_safe_run_text()`) — last-resort guard at every OOXML-text call site; logs loudly if it ever actually changes something, since that signals a real upstream gap a future text-creation path forgot to wire into Layer 1.

* Code: `src/utils/text_sanitization.py`, `src/models/sanitization.py`, `src/validation/validator.py` (`DOC_004`), `src/docx/docx_generator.py` (`_safe_run_text()`).
* Tests: `tests/test_text_sanitization.py`, plus dedicated sanitization test classes added across `tests/test_ocr.py`, `test_docling_engine.py`, `test_surya_engine.py`, `test_structure_detector.py`, `test_images.py`, `test_footnote_detector.py`, `test_validation.py`, `test_docx.py`, `test_pipeline.py`.
* Live-API confirmed end-to-end: a synthetic `\x01`/`\x02` repro PDF was POSTed through the real running backend (`/api/documents`), and the downloaded DOCX had zero control characters, with `DOC_004` correctly naming the removed codepoints with page attribution in the validation response.

---

## Phase I.1 — Reading Order Validation

**Verdict: VERIFIED COMPLETE**

`PAGE_003` (`Severity.WARNING`) flags two anomaly types on `Document.blocks`: backward reading jumps (a block's top y-coordinate jumps backward by more than 1.5× the page's median line height) and overlapping blocks (bbox intersection ≥50% of the smaller block's area). Strictly detection-only — every function in `src/validation/validator.py` is read-only; nothing reorders, restitches, or otherwise modifies content. Reconstruction remains a separate, later, unscoped phase (see `DECISIONS_LOG.md` and `KNOWN_LIMITATIONS.md`).

* Code: `src/validation/validator.py` (`_check_reading_order_anomalies`, `_count_backward_jumps`, `_count_overlapping_pairs`).
* Tests: `tests/test_validation.py` — scrambled order flagged, overlapping blocks flagged, confirms the check never consumes/mutates `Page.cleaned_text`.

---

## Phase M — Front-Matter Extraction (bug_006 / feature_006_front_matter_extraction)

**Verdict: VERIFIED COMPLETE**

A document's title, author(s), and affiliation(s) previously had no detection treatment at all — not a heading, not metadata — and were silently flattened into ordinary, undifferentiated body text (confirmed on the Brinkman benchmark PDF). A new, additive, page-1-only, deterministic module finds a "masthead-zone boundary" (the first line matching `abstract`/`keywords`/`introduction`/`summary` within page 1's first 20 lines), then partitions the zone above it by relative font size: title = contiguous run ≥1.3× the document's dominant body font size; author = contiguous run immediately after, strictly between body and title size, capped at 5 lines; affiliation = the remainder. A short leading "kicker" line (e.g. Brinkman's "Article") is skipped first if present. Any step finding nothing fails closed — `FrontMatter` stays entirely empty, the correct outcome for a PDF with no title page (3 of the 4 benchmark PDFs).

* Code: `src/models/front_matter.py` (`FrontMatter` model, additive `Document.front_matter: Optional[FrontMatter]`), `src/frontmatter/front_matter_extractor.py` (`extract_front_matter()`). Wired into `src/pipeline/phase1_pipeline.py` Stage 3, immediately after footnote detection. Consumed by `src/markdown/markdown_builder.py` (renders a bold-title/italic-byline/plain-affiliation block right after page 1's H6 marker; suppresses those exact source lines from ordinary body rendering via the same exact-line-matching technique used for footnote bodies and figure captions) and `src/docx/docx_generator.py` (styled title/byline/affiliation paragraphs).
* Deliberately isolated from `src/headings/heading_detector.py` — no shared constants, no calls into it, no change to its classification tiers. A related one-line fix landed alongside it in the same module: `"keywords"` added to `heading_detector.py::_H2_KEYWORDS`, since a PDF's literal "Keywords" line was previously falling through undetected as a heading (same audit, same symptom class).
* Tests: `tests/test_front_matter_extractor.py` (18 tests — full-masthead-zone, no-kicker, fail-closed-on-missing-boundary/missing-title, author/affiliation split variants, plus `TestRealBrinkmanPdf` end-to-end against the real regression PDF).
* **Process note:** implemented and verified 2026-06-24, but left completely unrecorded (no ticket number, no save-state/docs update, no memory) until a routine status check on 2026-06-25 found it and retroactively assigned `bug_006`/`feature_006_front_matter_extraction`, mirroring the existing `bug_005`/`feature_005_span_level_text_model` pairing. See `DECISIONS_LOG.md` Part 9 and `PROJECT_SAVE_STATE.md` §6/§7.

---

## FEATURE_015 — Accessible Table Remediation Workspace

**Verdict: VERIFIED COMPLETE (2026-06-29); extended by FEATURE_015.1 (2026-06-29)**

PyMuPDF-based table detection for born-digital PDF pages, integrated into Stage 3, with full semantic DOCX rendering, accessibility validation, AI assistance, screen reader simulation, and a human-review workspace in the frontend.

* **Auto-detection:** `src/tables/table_extractor.py` calls `page.find_tables(strategy='lines')` on every `DIRECT_TEXT_EXTRACTION` page. Detects tables drawn with explicit PDF vector border lines. Borderless tables (academic journal style — Brinkman's 8 tables → 0 auto-detected) require manual creation.
* **Merged cell detection (FEATURE_015.1):** `_detect_cell_spans()` in `table_extractor.py` reads PyMuPDF's `None`-cell pattern from `fitz_table.cells` to populate `col_span` and `row_span` on anchor cells. Two-pass algorithm: col-span pass (consecutive Nones in same row) then row-span pass (consecutive Nones in same column not owned by a col-span). Span-consumed None cells are excluded from the confidence penalty.
* **Model:** `src/models/table.py` — `Table`, `TableRow`, `TableCell`, `TableStatus` (AUTO_DETECTED / MANUALLY_CREATED / REVIEWED). `TableCell.col_span` and `row_span` carry merge information. `Table.bbox` drives TextBlock suppression.
* **Pipeline integration:** Stage 3 of `src/pipeline/phase1_pipeline.py`, after footnote/front-matter extraction: `document.tables = extract_tables(document, pdf_path)`.
* **Markdown output:** `_render_pipe_table()` in `src/markdown/markdown_builder.py` — GitHub-flavoured pipe tables. TextBlocks whose bbox overlaps a table's bbox are suppressed.
* **DOCX semantic rendering:** `_add_semantic_table()` in `src/docx/docx_generator.py` — reads the `Table` model directly. Sets `w:tblHeader` on header rows (`_set_row_tbl_header()`), bolds header/row-header cells, calls `_apply_cell_merges()` for col_span/row_span > 1, renders caption as italic paragraph before the table, summary as small italic paragraph after (WCAG H73). Semantic routing via `<!-- table-id: {id} -->` HTML comment in Markdown.
* **Accessibility validation:** `_check_table_accessibility()` in `src/validation/validator.py`:
  * TABLE_001 (WARNING): no caption
  * TABLE_002 (WARNING): no WCAG H73 summary
  * TABLE_003 (WARNING): no header row
  * TABLE_004 (WARNING): empty header cell
  * TABLE_005 (INFO): low-confidence auto-detected table (<0.7)
  * TABLE_006 (WARNING, FEATURE_015.1): table has merged cells — structure preserved in DOCX but lost in Markdown pipe table
* **AI assistance:** `src/ai/table_analyzer.py` — on-demand AI analysis (POST `/tables/{id}/analyze`). Returns `TableAISuggestions` (table_type, suggested_caption, suggested_summary, header_rows_detected, header_cols_detected, warnings, confidence). Reviewer always approves before applying. `RAWRS_AI_STUB=1` for testing without model weights.
* **Screen reader simulation:** `buildAnnouncement()` in `TableDetailPanel.tsx` — builds NVDA/JAWS announcement from all column header texts (multi-level, joined " > ") + row header (first col when header_col_count > 0) + cell value. Updates when header structure changes.
* **API:** 5 endpoints — GET/POST/PATCH/DELETE `/documents/{id}/tables` + POST `/documents/{id}/tables/{id}/analyze`. PATCH updates caption, summary, header_row_indices, header_col_count, and individual cell text (`cells: List[{row_index, col_index, text}]`).
* **Frontend:** `TableCard`, `TableDetailPanel`, `TableGrid` components + Tables tab in `DocumentWorkspace.tsx`. Edit mode toggle makes all cells editable as text inputs; cell edits are included in the Save PATCH.
* **Tests:** 61 tests in `tests/test_table_accessibility.py` covering all phases. `tests/test_table_extractor.py` (13 tests). `tests/test_table_api.py` (12 tests).
* **strategy='text' evaluated and rejected:** On multi-column academic PDFs it treats the entire page as one giant table grid (Brinkman page 5 → one 40×8 table). Documented in `DECISIONS_LOG.md` Part 17.

---

## FEATURE_015.2 — Evidence-Fusion Table Detection

**Verdict: VERIFIED COMPLETE (2026-06-30)**

Replaces the single-strategy `page.find_tables(strategy='lines')` extractor with a 4-detector evidence-fusion architecture. Each detector emits `EvidenceSignal` objects collected into an `EvidenceBundle`; the bundle computes a weighted-mean confidence and fires `TABLE_007` for degenerate single-column spatial-analysis detections.

* **Detectors:** `src/tables/detectors/` — `VectorBorderDetector` (PyMuPDF `find_tables('lines')`), `HorizontalRuleDetector` (`page.get_drawings()` booktabs 3-line pattern), `SpanAlignmentDetector` (text-span column alignment), `ColumnAlignmentDetector` (descriptor/key-value grids).
* **EvidenceBundle:** weighted-mean confidence. `three_line_pattern` signal gets extra weight (0.9). TABLE_007 fires when `col_count ≤ 1` and `extraction_source == "spatial_analysis"`.
* **Caption framework:** `src/captions/caption_detector.py` — shared by all 4 detectors. Searches 5–50pt above the region's top edge. Scoring tiers: 1.0 (explicit Table/Figure label), 0.8 (all-caps ≤8 words), 0.6 (ends-with-period ≤20 words). `_MIN_CAPTION_SCORE = 0.6` gates out the 0.4 tier (single short lines = too permissive). Bare-number rejection (page numbers, figure counts) added.
* **Tests:** `tests/test_feature015_2.py` — 93 tests covering all 4 detectors, EvidenceBundle, caption detection, and validation rules.

---

## FEATURE_015.3 — Table Detection Hardening (Production Sign-Off)

**Verdict: VERIFIED COMPLETE (2026-06-30) — all 7 parts implemented; full suite 1239 passed, 0 failed**

Production-calibration pass addressing false positives, caption detector permissiveness, benchmark accuracy, and accessibility readiness dashboard.

* **Part A — HorizontalRuleDetector false positive elimination:** `MIN_DUAL_COL_FILL_FRAC = 0.20` gate in `_build_candidate()` — 2-column candidates must have ≥20% of rows with BOTH columns simultaneously filled. Eliminates decorative separator false positives (alternating column fill = 0% dual fill). FolkPedagogy 11 FPs → 0; Brinkman/NoE TPs preserved.
* **Part B — Benchmark corrections:** `expected_table_count` updated to 5 for Brinkman (confirmed by `expected_md` inspection: Table 1 p.347, Table 2 p.348-349, Table 3 p.350, Table 4 p.352, Table 5 p.356-357). Benchmark metrics: Binary P/R/F1 = 1.0/1.0/1.0; Count-level P=0.800, R=0.667, F1=0.727. Report: `docs/benchmark_tables_report.json`.
* **Part C — Brinkman deep verification:** 3 tables detected (pages 9 and 11 confirmed TP; 1 FP on page 1, confidence 0.691 → TABLE_005 fires). 3 FN: Tables 1, 2, 5 — Tables 2 and 5 span page breaks (cross-page tables are an architectural limitation). Caption suppression correct: TABLE_001 fires for all 3 detected tables (captions are inside the booktabs structure, above the first data rule, not above the top rule — `find_caption()` correctly returns None).
* **Part D — Caption detector calibration:** bare-number rejection (digits-only strings score 0.0), `_MIN_CAPTION_SCORE = 0.6` (rejects vague short standalone lines). Journal running headers no longer captured as captions.
* **Part E — False positive audit:** 0 FPs on all 6 no-table benchmark PDFs after calibration. 1 borderline detection on Brinkman page 1 (confidence 0.691) → TABLE_005 INFO → reviewer alerted.
* **Part F/H — Accessibility readiness dashboard (ChecklistPanel):** Tables group expanded from 1 binary item to 5 items: Table Detection, Tables Reviewed, Captions & Summaries, Structure & Headers, Detection Confidence. `SummaryBar` denominator fixed to exclude `na` and `not_impl` items. `ResultsDashboard` "Tables Detected" and "Page Labels" wired from live data (previously hardcoded "Not Available"). "AI Alt Text" item replaced with live status from `alt_text_status === "ai_generated"` tracking.
* **Part G — Caption framework:** `src/captions/caption_detector.py` is the canonical shared implementation, re-exported by `src/tables/detectors/caption.py`. All 4 table detectors use it. `src/images/image_extractor.py::_find_caption_block()` uses a separate `TextBlock`-based implementation (intentional: operates at a different abstraction layer, requires bidirectional search, needs "Figure N"-only matching). No refactor required; documented as a Phase 2 improvement opportunity.
* **Known limitations (documented, gated by validation rules):**
  * Cross-page tables not detected (Tables 2, 5 in Brinkman) — architectural; require manual creation.
  * "Row 0 is header" heuristic may mark embedded caption as header row for spatial detections — TABLE_003 does not fire (reviewer must verify in Tables workspace).
  * Log counts `"span-alignment"` for all non-vector detectors (includes HorizontalRuleDetector); benchmark script correctly differentiates by signal name.

---

## FEATURE_016 — Accessibility Remediation Platform

**Verdict: VERIFIED COMPLETE (2026-06-29) — all sub-features 016A–016G implemented**

FEATURE_016 makes RAWRS an enterprise accessibility remediation platform. Every reviewable object follows a unified lifecycle: Detected → AI Analysis → Human Review → Accessibility Validation → Screen Reader Simulation → DOCX Verification → Approved. New sub-features: Heading workspace (016A), Reading Order workspace (016B), DOCX list rendering (016C partial), Footnote workspace (016D), Image DOCX embedding verification (016E), Document properties/metadata workspace (016F), Formatting fidelity (016G).

### 016A — Heading Review Workspace

* **Model:** `HeadingReviewStatus` enum (DETECTED / APPROVED / LEVEL_CHANGED / REJECTED) + `Heading.review_status`, `Heading.reviewer_note` fields in `src/models/heading.py`.
* **API:** `GET /documents/{id}/headings` (content headings only; no page markers), `PATCH /documents/{id}/headings/{document_order}` (level 1–5 only, text edit, approve/reject).
* **Validation:** `HEADING_005` (WARNING) fires when more than one H1 is detected in a document.
* **Frontend:** `HeadingGrid` two-panel card+detail layout, `HeadingCard`, `HeadingDetailPanel`. Screen reader simulation preview: "Heading level N: text".
* New "Headings" tab in `DocumentWorkspace` (tab position 2).
* Tests: `tests/test_feature016_accessibility.py` — `TestHeadingReviewWorkspace` class.

### 016B — Reading Order Review Workspace

* **Model:** `ReadingOrderStatus` enum (UNREVIEWED / APPROVED / CORRECTED) on `Page`; `TextBlock.corrected_order: Optional[int]` — when set, used as sort key in `_group_blocks_by_page()`.
* **Correction wiring:** `_render_page_body_with_paragraphs()` re-derives text from blocks sorted by `corrected_order` whenever any block has one set — actual rendered output changes, not just grouping metadata.
* **API:** `GET /documents/{id}/reading-order` (pages with PAGE_003 issues or already reviewed; blocks sorted by effective order), `PATCH /documents/{id}/pages/{n}/reading-order` (action: "approve" → APPROVED; "reorder" with `block_sequence` → CORRECTED with corrected_order assignments).
* **Frontend:** `ReadingOrderPanel` — page list + sortable block list with up/down arrows + approve button. New "Reading Order" tab (badge shows unreviewed count).
* Tests: `TestReadingOrderStatus`, `TestGetReadingOrderApi`, `TestPatchReadingOrderApi`, `TestCorrectedOrderAffectsMarkdown` — 14 tests.
* **Note:** This is the first implemented reading-order *correction* mechanism (Phase I.1 provided detection only). Correction is always human-initiated; automatic reordering is not performed.

### 016C — DOCX List Rendering (partial — rendering only, no semantic list model)

* `_BULLET_LIST_PATTERN` / `_NUMBERED_LIST_PATTERN` in `src/docx/docx_generator.py`: detect lines with bullet markers (•▪▸▶◦○◉●→⁃✓✗✔✘-) and numbered prefixes (1., a., i.) at the paragraph level.
* `_add_list_paragraph()`: uses Word's `"List Bullet"` / `"List Number"` paragraph styles; marker stripped from text before rendering (no doubled `• •` artefacts); falls back to plain paragraph if style absent from template.
* Tests: `TestListBulletRendering`, `TestListNumberRendering`, `TestMixedListAndBodyContent` — 13 tests.
* **Deferred (016C full model):** List/ListItem models, `list_detector.py`, list review API, review workspace UI. Only the DOCX rendering of lines already carrying bullet/number markers is implemented.

### 016D — Footnote Review Workspace

* **Model:** `FootnoteReviewStatus` enum (DETECTED / APPROVED / EDITED / REJECTED) in `src/models/footnote.py`; `footnote_id` assigned as `f"fn-{idx}"` in `src/footnotes/footnote_detector.py`.
* **API:** `PATCH /documents/{id}/footnotes/{footnote_id}` (body edit → EDITED, approve, reject). `GET /documents/{id}/footnotes` extended with `footnote_id`, `review_status`, `reviewer_note`.
* **Frontend:** `FootnoteTable` rewritten as two-panel review component. Screen reader simulation: "Footnote N: body".
* Tests: `TestFootnoteReviewWorkspace` class.

### 016E — Image DOCX Embedding Verification

* `_docx_compatible_picture_source()` in `src/docx/docx_generator.py` converts CMYK JPEGs to RGB before calling `add_picture()`.
* `_add_image()` now returns `bool` (True = embedded, False = skipped/failed). `Image.embedded_in_docx: Optional[bool] = None` (None = pre-generation) in `src/models/image.py`.
* `generate_docx()` builds `images_by_path` dict and records embedding result on each `Image` object.
* `IMAGE_005` (WARNING): fires when `embedded_in_docx == False` AND not already covered by IMAGE_001/002.
* Tests: `TestDocxEmbeddingVerification` in `tests/test_validation.py` — 6 tests.
* **Closes confirmed gap:** this rule was recorded as missing in `KNOWN_LIMITATIONS.md` (a CMYK JPEG that successfully extracts can still fail to embed; the old report overstated delivered image count). IMAGE_005 now surfaces this accurately.

### 016F — Document Properties / Metadata Workspace

* `Metadata` model (`src/models/metadata.py`) gains: `language`, `title`, `author`, `subject` fields.
* **API:** `GET /documents/{id}/metadata`, `PATCH /documents/{id}/metadata` (empty string → `None`, clears field).
* **DOCX output:** `_apply_core_properties()` in `src/docx/docx_generator.py` writes `dc:language`, `dc:title`, `dc:creator`, `dc:subject` to DOCX core properties.
* **Validation:** `META_001` (INFO): no `dc:language` (WCAG 3.1.1). `META_002` (INFO): no `dc:title` (WCAG 2.4.2).
* **Frontend:** `MetadataPanel` with IETF BCP 47 note, WCAG citations. New "Metadata" tab in `DocumentWorkspace` (tab position 6).
* Tests: `TestMetadataReviewWorkspace` class.

### 016G — Formatting Fidelity (bold/italic inline)

* `_all_blocks_bold()` / `_all_blocks_italic()` in `src/markdown/markdown_builder.py`: inspect non-superscript spans' `font_flags & 16/2`; bold falls back to `TextBlock.is_bold`.
* `_apply_inline_format()`: wraps paragraph text in `**...**` / `*...*` / `***...***` when all contributing blocks share uniform formatting.
* `flush_run()` in `_render_page_body_with_paragraphs()` calls `_apply_inline_format()` before `_substitute_markers()`, using `Paragraph.source_orders` to look up contributing blocks.
* DOCX: `_INLINE_FORMAT_PATTERN` + `_parse_inline_format()` in `src/docx/docx_generator.py` splits `***...***`/`**...**`/`*...*` markers into `(text, is_bold, is_italic)` segments. `_add_plain_run()` gains `bold`/`italic` params; `_add_body_text_with_inline_format()` emits per-segment runs; `_add_body_paragraph()` routes through it.
* Tests: 18 new tests in `tests/test_feature016_accessibility.py`. 2 existing `tests/test_docx.py` tests updated (`test_asterisk_line_without_preceding_image_is_plain_text` → now expects italic; `test_every_body_paragraph_complies_with_body_text_rules` → `bold in (True, False)` now allowed).

### Test summary

* 91 tests in `tests/test_feature016_accessibility.py` (46 for 016A/016D/016F + 13 for 016C + 14 for 016B + 18 for 016G).
* 6 IMAGE_005 tests in `tests/test_validation.py::TestDocxEmbeddingVerification`.
* 2 pre-existing `tests/test_docx.py` tests updated (not added). Suite clean at 0 failures after all 016 sub-features.

---

## Validation Rules — Full Current Inventory

All 29 rule IDs that exist in code today, cross-checked against `docs/VALIDATION_RULES.md`:

| Rule ID | Severity | Checks |
|---|---|---|
| DOC_001 | WARNING | Document has pages but no extracted text, headings, or images |
| DOC_002 | WARNING/INFO | Metadata stale (page/image count mismatch) or missing processing date |
| DOC_003 | ERROR | Document has zero pages |
| DOC_004 | WARNING | XML-invalid character(s) found and removed from extracted text before export (XML Sanitization Architecture, Layer 2 — see above) |
| HEADING_001 | WARNING | Heading hierarchy jump (level increase >1) |
| HEADING_002 | WARNING | No H1 detected |
| HEADING_003 | WARNING | Empty/blank heading |
| HEADING_004 | WARNING | Duplicate (level, text) heading pair |
| HEADING_005 | WARNING | Multiple H1 headings detected (added FEATURE_016A) |
| PAGE_001 | ERROR | Page missing its H6 page marker |
| PAGE_002 | ERROR/WARNING | Duplicate page number, sequence gap, or out-of-order pages |
| PAGE_003 | WARNING | Reading-order anomaly (backward jump or overlap) — Phase I.1 |
| IMAGE_001 | ERROR | Image reports success but file is missing |
| IMAGE_002 | ERROR | Image extraction failed |
| IMAGE_003 | ERROR | Duplicate image_id |
| IMAGE_004 | INFO | Alt text pending human review |
| IMAGE_005 | WARNING | Image successfully extracted but failed to embed into DOCX (added FEATURE_016E) |
| OCR_001 | WARNING | Page OCR confidence is LOW (Surya fallback recovery) |
| OCR_002 | WARNING | OCR-recovered text exceeds the unusable-character ratio threshold |
| TABLE_001 | WARNING | Table has no caption |
| TABLE_002 | WARNING | Table has no WCAG H73 accessibility summary |
| TABLE_003 | WARNING | Table has no header row |
| TABLE_004 | WARNING | Empty header cell |
| TABLE_005 | INFO | Auto-detected table has low confidence (<0.7) |
| TABLE_006 | WARNING | Table has merged cells (structure lost in Markdown pipe table) |
| TABLE_007 | WARNING | Borderless-detected table has only one inferred column — column structure may need reviewer verification (added FEATURE_015.3) |
| NOTE_001 | INFO | Footnote detected |
| NOTE_002 | INFO | Endnote detected |
| META_001 | INFO | No dc:language set — WCAG 3.1.1 (added FEATURE_016F) |
| META_002 | INFO | No dc:title set — WCAG 2.4.2 (added FEATURE_016F) |

**Remaining gaps:** broken-word detection still has no rule ID. "Figure Validation" (missing captions, unlinked references, missing numbering) still has no rule ID. Both are called out in `VALIDATION_RULES.md` and `KNOWN_LIMITATIONS.md`. The IMAGE_005 gap (CMYK JPEG embedding failure not detectable from `IMAGE_001`/`IMAGE_002`) is now **closed** as of FEATURE_016E.

---

## Phase M-1 — Mathpix Import Layer

**Verdict: VERIFIED COMPLETE (2026-06-30)**

Full ingestion pipeline for Mathpix MMD files. After Phase M-1, `run_pipeline()` has two entry paths:

* **PDF-native path** (`mmd_path=None`, default): unchanged behavior — all 8 stages run exactly as before.
* **Mathpix path** (`mmd_path=<path>.mmd`): Stage 2 replaced by `MathpixImportProvider.import_document()`; footnote/front-matter/table detection and `detect_headings()` are skipped (Mathpix already extracted this). All other stages (structure detection, image extraction, Markdown/DOCX generation, validation) run unchanged.

### Architecture ownership (approved)

RAWRS is an **accessibility remediation platform** that imports Mathpix extraction, verifies it against the original PDF, enriches it, and produces accessibility-compliant output documents.

* **Mathpix MMD = extraction source** (import-only; raw MMD form is discarded after `import_document()` returns)
* **RAWRS Document Model = canonical representation** (single source of truth for all downstream stages)
* **Original PDF = evidence only** (used by Verification Engine in Phases M-2/M-3 for cross-checking)
* **CorrectionRecord audit trail** = every Mathpix value that RAWRS proposes to correct is recorded as `original_value → proposed_value → status`; Mathpix extraction is never silently overwritten

### New files

| File | Role |
|---|---|
| `src/models/correction.py` | `CorrectionRecord` + `CorrectionStatus` models |
| `src/importers/__init__.py` | Import layer package |
| `src/importers/base.py` | `ImportProvider` Protocol (provider-agnostic; Mathpix is provider #1) |
| `src/mathpix/mmd_parser.py` | State-machine MMD → P2Document (handles: `\title{}`, `\section*{}`, `\subsection*{}`, `\subsubsection*{}`, `\author{}`, `\begin{figure}`, `\begin{tabular}`, `\begin{table}`, `\begin{abstract}`, `| pipe |` tables, `- bullet`/`1. numbered` lists, `\footnotetext{N}{body}`, inline footnote refs via `math_transformer`) |
| `src/mathpix/ingestor.py` | `MathpixImportProvider` — P2Document → RAWRS `Document`; proportional page assignment (refined by Phase M-2 DOCX H6 markers) |
| `tests/test_mathpix_ingestor.py` | 44 tests, all pass |

### Model additions

| Model | Field | Notes |
|---|---|---|
| `Document` | `corrections: List[CorrectionRecord] = []` | Audit trail for all proposed corrections |
| `Heading` | `source: str = "rawrs"` | Values: `"mathpix"` / `"rawrs_recovery"` / `"rawrs"` |
| `Footnote` | `source: str = "rawrs"` | Same values |
| `ExtractionMethod` | `MATHPIX_IMPORT = "mathpix_import"` | Set by `MathpixImportProvider` on each page |

### Known gap (Phase M-2 will close)

Mathpix footnote anchors (inline `[N]` refs) are placeholders in Phase M-1: `anchor_text = marker`, `anchor_page_number = 1`. Phase M-2 will enrich these using DOCX H6 page markers to resolve the exact page. See `KNOWN_LIMITATIONS.md`.

* Code: `src/models/correction.py`, `src/importers/base.py`, `src/importers/__init__.py`, `src/mathpix/mmd_parser.py`, `src/mathpix/ingestor.py`. Pipeline: `src/pipeline/phase1_pipeline.py` (`run_pipeline(mmd_path=...)` parameter).
* Tests: `tests/test_mathpix_ingestor.py` — 44 tests: `TestParseMmdTitle`, `TestParseMmdHeadings`, `TestParseMmdParagraph`, `TestParseMmdLists`, `TestParseMmdFigure`, `TestParseMmdPipeTable`, `TestParseMmdFootnote`, `TestParseMmdAbstract`, `TestParseMmdEmptyAndEdgeCases`, `TestMathpixImportProvider`.

---

## Test Suite

**Last full-suite run on record: 486 passed, 1 skipped, 0 failed** (all markers, ~27 min). **Stale — not re-confirmed since.** A later reconciliation pass (covering XML Sanitization Architecture C, bug_001, bug_002) re-verified only the fast subset: **567 passed, 1 skipped, 5 deselected, 0 failed** (`pytest -m "not real_docling and not real_surya"`). The full suite, including the slow `real_docling`/`real_surya`-marked tests, was not re-run in that pass — do not cite `486` as current without re-running `pytest` with no marker filters first.

**Re-verified after pinning `surya-ocr==0.20.0`** (Decisions Log Part 4): fast subset — 481 passed, 1 skipped, 0 failed, 4m05s; `pytest -m real_surya` — 2 passed, 0 failed, 10m35s, with observable real `llama-server` subprocess activity at teardown. No regressions; the pin changes no runtime behavior on this host, only future-install reproducibility. (This `481` figure is itself superseded by the `567` figure above, from later test additions — both are fast-subset counts, not full-suite counts.)

**Current authoritative figure, 2026-06-25:** fast subset (`pytest -m "not real_docling and not real_surya"`) — **865 passed, 7 skipped, 5 deselected, 0 failed**, 27m20s. Every prior figure above (`486`/`567`/`481`) predates two findings from this date: `bug_007` (a half-finished edit had left `detect_headings()` raising unconditionally on every document — see `DECISIONS_LOG.md` Part 10) and the Benchmark Corpus Expansion (`samples/benchmark/pdfs/` silently grew from 4 to 10 PDFs on 2026-06-24 — see `DECISIONS_LOG.md` Part 11). Treat `865` as current only until the next real suite run; do not assume it stays accurate indefinitely without re-running `pytest`.

**Updated 2026-06-28 (Configurable Page Numbering Policy):** 41 new tests added in `tests/test_page_numbering_policy.py`. All existing tests pass unchanged.

**Updated 2026-06-28 (FEATURE_012 — AI alt text):** 24 new tests in `tests/test_alt_text_generator.py` (9) and `tests/test_image_review_api.py` (15). All existing tests pass unchanged.

**Updated 2026-06-29 (FEATURE_015 — Table remediation):** 25 new tests in `tests/test_table_extractor.py` (13) and `tests/test_table_api.py` (12). All existing tests pass unchanged.

**Updated 2026-06-29 (FEATURE_015.1 — Semantic Accessible Table Remediation):** 61 tests in `tests/test_table_accessibility.py` (34 pre-existing + 15 new: 6 span detection, 4 TABLE_006, 5 cell edit API). Fixed pre-existing `_make_job_with_table` breakage (`PipelineResult` and `Job` gained required fields since the fixture was written). TABLE_006 validation rule added. `_detect_cell_spans()` in table_extractor.py. Cell text editing via PATCH API + frontend edit mode. All existing tests pass unchanged.

**Current authoritative figure, 2026-06-29 (pre-015.1):** fast subset — **969 passed, 7 skipped, 5 deselected, 0 failed**.

**Updated 2026-06-29 (FEATURE_015.1):** 15 new tests in `test_table_accessibility.py` + 14 pre-existing fixture failures fixed (required fields added to `_make_job_with_table()`). Net delta: +29 passing → **~998 passed** (estimated; re-run `pytest` to confirm).

**Updated 2026-06-29 (FEATURE_016):** 91 new tests in `tests/test_feature016_accessibility.py` + 6 IMAGE_005 tests in `tests/test_validation.py`. Suite confirmed clean (0 failures) after all 016 sub-features. Net delta: +97 → **~1095 passed** (estimated; re-run `pytest` to confirm current count after Phase 2 skeleton added).

**Updated 2026-06-30 (FEATURE_015.3 — Table Detection Hardening & Accessibility Readiness Platform):** Added `HorizontalRuleDetector` + `ColumnAlignmentDetector` (Parts A), benchmark measurement script `scripts/benchmark_tables.py` (Part B), `src/captions/` package (Part D), `ObjectLifecycleStatus` on Heading + Footnote models (Part E), TABLE_007 validation rule (Part F). 10 new tests in `tests/test_table_extractor.py` for new detectors + detector registration + lifecycle. Full suite confirmed: **1239 passed, 0 failed, 7 skipped** (2026-06-30).

**Updated 2026-06-30 (Phase M-1 — Mathpix Import Layer):** Full Mathpix MMD ingestion pipeline: `ImportProvider` protocol, `MathpixImportProvider`, `mmd_parser.py` (state-machine MMD → P2Document), `CorrectionRecord` audit-trail model, `Document.corrections`, `Heading.source`/`Footnote.source`, `ExtractionMethod.MATHPIX_IMPORT`, `run_pipeline(mmd_path=...)` branch. 44 new tests in `tests/test_mathpix_ingestor.py`. Full suite: **1296 passed, 0 failed** (2026-06-30).

---

## Phase M-2 — Cross-Source Verification Engine, Evidence Fusion, and Platform Additions (FEATURE_017–020)

**Verdict: VERIFIED COMPLETE — implemented across two sessions (2026-07-01 commit `f6c8f73`, then this session); documented here for the first time.** This section closes a real documentation gap: `f6c8f73` ("Add full Next.js frontend, Mathpix cross-source verification engine, and generalized SemanticObject/SemanticVerifier foundation") shipped without a `PHASE_STATUS.md`/`DECISIONS_LOG.md` update, and this session's follow-on work sat uncommitted with the same gap — the same "implemented but unrecorded" pattern already seen once before (see Phase M "Process note" above, bug_006/feature_006). `docs/VALIDATION_RULES.md`, `docs/PAGE_RULES.md`, and `docs/KNOWN_LIMITATIONS.md` were kept current throughout both sessions; this file, `DECISIONS_LOG.md`, `TASKS.md`, and `CURRENT_STATE.md` were the ones that lagged.

### FEATURE_017 — Generic Cross-Source Verification Engine (shipped in `f6c8f73`)

The Phase M-1 promise ("Verification Engine = a conceptual layer, not a new module") was superseded by an actual generic engine once a second and third asset type (headings, lists) needed the same PDF-vs-Mathpix comparison logic figures already had. `src/verification/`:

* `src/models/semantic_object.py` — `SemanticObject` base model (id, bbox, `verification_status`, `confidence`, `lifecycle_status`) that `Heading`, `ListBlock`, `Table`, `Callout` all extend from, unifying the ad-hoc per-model fields FEATURE_015.3 (Part E) had started adding one model at a time.
* `src/verification/base.py` — `SemanticVerifier` abstract base: `asset_type`, `build_pdf_matcher()`, `to_canonical()`, `classify()`, `rule_table()`, `apply()`, `revert()`.
* `src/verification/engine.py` — `VerificationEngine` registry (`engine.register(...)`); each verifier module self-registers via a module-level `_register()` call on import.
* `src/verification/matching.py` — `MultiSignalMatcher`/`WeightedSignal`/`MatchResult`: generic weighted multi-signal identity matching (a candidate is "the same real-world object" across two sources), shared by every verifier's `build_pdf_matcher()`.
* `src/verification/merge.py` — `MergeAction` (KEEP/REPAIR/RECOVER/REMOVE) + `decide_from_evidence()`, the shared decision function every verifier's `classify()` calls once it has a confidence score.
* `src/verification/figures.py` (515 lines) — the first asset type, migrated from Phase M-1's figure-specific logic; `IMAGE_VERIFY_001`–`008`.
* `src/verification/headings.py`, `src/verification/lists.py` — second and third asset types, built directly on the new base classes from the start (`HEADING_VERIFY_001`–`004`, list equivalents).
* `src/api/`, `frontend/` — the Corrections API (`GET/PATCH /documents/{id}/corrections`) and a full Next.js frontend shipped in the same commit.

### FEATURE_019 — Evidence Fusion Engine (this session)

Every verifier's `classify()` originally decided KEEP/REPAIR/RECOVER from a single binary PDF-match signal. `src/verification/evidence.py` adds `EvidenceSignal`/`EvidenceBundle` (originally built and proven inside `src/tables/` — see FEATURE_015.3 — then promoted to `src/verification/` as the generic primitive; `src/tables/evidence.py` re-exports it unchanged so existing table-detector imports keep working). `decide_from_evidence()` now takes a fused `EvidenceBundle` — a weighted mean of every independent signal available — instead of one binary flag.

* **`HeadingVerifier` (`src/verification/headings.py`)** gains three new signals beyond the existing PDF match: `_typography_signal` (font size vs. document body baseline, reusing `heading_detector.py::build_heading_layout_context()`), `_whitespace_signal` (vertical isolation vs. the page's own median line gap), and `_running_header_signal` (exact-text recurrence across ≥2 pages — the same signature `heading_detector.py`'s native-path Tier-4 Recurrence Guard already used, ported here because that guard never ran for Mathpix-sourced headings). A weak running-header score now proposes REMOVE (`HEADING_VERIFY_005`) even when the PDF match itself looked confident.
* **`ListVerifier` (`src/verification/lists.py`)** — mechanically updated from the old `EvidenceItem` shape to `EvidenceSignal`/`EvidenceBundle`; no new signals added this pass.
* **`CalloutVerifier` (`src/verification/callouts.py`, new)** — the fourth registered asset type, and the first with **no PDF-side detector at all** (`build_pdf_matcher()` returns an empty matcher; every `Callout` goes through `classify()` as `unmatched_a`). Proves the framework generalizes to asset types with only import-side evidence: `_label_pattern_signal` (a numbered label like "Case study 11.2" scores higher than a bare keyword match like "Summary", which is ambiguous with an ordinary section title) and `_heading_intact_signal` (the anchoring `Heading` this callout references still exists). `CALLOUT_VERIFY_001` fires on weak evidence.
* **`src/models/callout.py` (new)** — `Callout` model: `callout_type` (open string, not an Enum — new box vocabularies across other textbook series are expected), `label`, `heading_id` (references the anchoring `Heading` by id rather than duplicating its body text). Classified by `src/mathpix/mmd_parser.py::classify_callout_type()` at import time.
* **`src/ocr/targeted.py` (new)** — region-scoped OCR (`ocr_region(pdf_path, page_number, bbox)`), reusing `surya_config.py::build_recognition_predictor()` with a PyMuPDF `clip` crop rather than a full-page render. Built as an evidence-of-last-resort primitive for verifiers with ambiguous typography/whitespace signals on scanned pages; not yet called from any verifier's `classify()` in this pass (infrastructure only).
* **`src/verification/benchmark_report.py` (new)** — aggregates every `SemanticObject`'s `verification_status` plus `Document.corrections`' reviewer-action status into a per-asset-type + whole-document summary (`mathpix_accuracy`, `recovery_rate`). Wired into `phase1_pipeline.py`'s existing JSON validation report, not a new endpoint.

### FEATURE_018 — Page Label Manager

`src/structure/page_label_resolver.py` (new) resolves each page's final, reviewer-facing `Page.page_label` from three precedence tiers: (1) a manual per-page override always wins, (2) the first reviewer-defined `Document.page_label_sections` entry covering that page (bulk range + style [arabic/roman upper/roman lower/none] + start number + prefix/suffix — offset and restart-numbering are just parameter values on this one shape), (3) fall back to the detected `Page.printed_label`. Called once by `structure_detector.py` at detection time (identical to pre-FEATURE_018 behavior when no sections exist yet) and again by `src/api/routes.py` whenever a reviewer edits sections. `GET/PATCH /api/documents/{id}/page-labels` + `PUT /api/documents/{id}/page-label-sections`; every change recorded as a `CorrectionRecord` (`object_type="page_label"`). Validation rules `PAGE_004`–`PAGE_008`. Full detail: `docs/PAGE_RULES.md`.

### FEATURE_020 — Cross-type source-order interleaving

`source_line: Optional[int]` added to `Heading` (and the equivalent on other Mathpix-sourced semantic objects) — the position in the source `.mmd` a given object came from. Mathpix-path only (`None` for RAWRS-native objects, where `document_order` already orders correctly within-type). Purpose: a shared, cross-type sort key so `markdown_builder.py` can interleave headings/paragraphs/callouts/lists in true source order instead of only within their own type.

### AI Subsystem Redesign — optional dependency split + resource preflight

`torch`/`transformers`/`qwen-vl-utils`/`psutil` moved out of `requirements.txt` into a new, optional `requirements-ai.txt` — the base install is fully functional without them (`src/ai/providers/qwen.py` reports itself unavailable via `GET /api/ai/status` with a clear reason, never crashes the backend). `_check_resources()` runs a synchronous RAM/VRAM preflight (14 GB VRAM on GPU / equivalent RAM on CPU float32) before `start_background_load()` spawns the actual model-load thread — unavailability from insufficient hardware is known immediately at backend startup, not discovered on the first real inference request as FEATURE_012 originally left it.

### Frontend — Workspace redesign

The single-scroll, tabbed `DocumentWorkspace` (FEATURE_016's tab-per-object-type layout) was replaced with a `WorkspaceShell` (`frontend/components/workspace/`): a persistent PDF/Markdown/DOCX center-pane switcher, a `SemanticNavTree` left rail, a `ContextInspectorRail` + `ObjectInspectorFrame` right rail driven by object selection (`frontend/lib/store/SelectionContext.tsx`, `DocumentDataContext.tsx`, `PdfViewportContext.tsx`), and a collapsible `BottomPanel`. New review panels: `CalloutPanel`, `ListPanel`, `PageLabelManagerPanel`, `CorrectionHistoryList`, `EvidenceBreakdown` (renders an `EvidenceBundle.explanation` for reviewers), plus a `PdfViewer` and light/dark `ThemeToggle`/`ThemeProvider` (`frontend/lib/theme/`). `Tabs.tsx`, `MarkdownViewer.tsx`, `DownloadBar.tsx`, `DownloadCards.tsx`, `FileDropzone.tsx` removed as superseded.

**Theming sweep — closed 2026-07-08 (was an open gap in the prior pass):** the 19 pre-existing panels (`ChecklistPanel`, `ResultsDashboard`, `HeadingGrid`/`HeadingCard`/`HeadingDetailPanel`, `ImageGrid`/`ImageCard`/`ImageDetailPanel`, `TableGrid`/`TableCard`/`TableDetailPanel`, `PageLabelManagerPanel`, `FootnoteTable`, `MetadataPanel`, `OcrPageTable`, `PipelineView`, `ReadinessPanel`, `BulkActions`, `DocxPreview`'s chrome) that hardcoded raw Tailwind `gray-*`/`blue-*`/`red-*`/`amber-*`/`indigo-*`/`violet-*` classes with no `dark:` variant were migrated onto the theme-token system (`surface-canvas`/`surface-panel`/`surface-elevated`, `border`/`border-strong`, `text-primary`/`text-secondary`, `accent`/`accent-contrast`, `success`/`warning`/`danger`, using Tailwind v4 opacity modifiers like `bg-danger/10` for tinted badges). Pure className migration, no layout/behavior change. `Badge.tsx` was left untouched — it already handled both themes correctly via explicit `dark:` variants, a different but equally valid pattern. `next build` re-verified clean.

**Two upload/workspace bugs found and fixed 2026-07-08, while manually driving the app end-to-end in a real browser** (not caught by the test suite, since both are dev-server/runtime-only failure modes with no automated coverage):

1. **Uploaded files were silently dropped, "no change" on upload.** Next.js 16 blocks cross-origin dev requests (including the webpack-hmr WebSocket) by default. The dev server was being opened via `127.0.0.1:3000` rather than the exact `localhost:3000` host it printed, which Next.js treats as a different, untrusted origin — this silently broke HMR and made the browser fall back to full-page reloads on every socket reconnect attempt (multiple times per second), wiping any file already selected in the upload form's `<input type="file">` before a user could click Run. Fixed by adding `allowedDevOrigins: ["127.0.0.1", "localhost"]` to `frontend/next.config.ts`.
2. **Every document's workspace page crashed after a successful upload.** `DocumentWorkspaceContent` (`frontend/app/documents/[id]/DocumentWorkspace.tsx`) called a `useMemo()` (building `pdfOverlays` for the PDF viewport) *after* two conditional early returns (`notFound`, `!job` while still loading) — a Rules of Hooks violation: fewer hooks run on the loading render than on the loaded render, which React detects and throws on. Fixed by moving the `useMemo` above both early returns; the selectors it calls only read always-present dictionary fields off `state`, never `state.job`, so this is safe on every render path.

Both verified live: uploaded a real `.md` + `.pdf` pair through the actual running app, confirmed the file registered in the UI, ran the pipeline, and confirmed the destination workspace renders (PDF/Markdown split view, 110 validation issues including the new `HEADING_VERIFY_*` cross-source findings) instead of crashing.

### Test suite

**Re-verified 2026-07-08:** fast subset (`pytest -m "not real_docling and not real_surya"`) — **1487 passed, 7 skipped, 5 deselected, 0 failed**, 27m47s. New test files this session: `tests/test_heading_verifier.py` (23), `tests/test_feature018_page_label_manager.py` (37), `tests/test_feature019_evidence_fusion.py` (11), `tests/test_callout_verifier.py` (14), `tests/test_benchmark_report.py` (8), `tests/test_targeted_ocr.py` (5), `tests/test_ai_registry.py` (8), plus 15 new cases in `tests/test_corrections_api.py`. `frontend/`'s `next build` (Turbopack) re-verified clean three times across this session (theming sweep, and both bugfix commits): compiles, typechecks, and generates all routes with no errors. Neither the theming sweep nor the two bug fixes changed backend code, so the pytest figure above still applies unchanged.

## Phase 1 IDE Redesign — Frontend UX Overhaul (2026-07-08/09)

Started from a 13-objective brief to turn RAWRS from a "verification dashboard" into an "Accessibility Remediation IDE." An audit against the actual frontend (not the brief's assumptions) found most objectives already built by Phase M-2/FEATURE_012/016 — AI alt-text workflow, Page Label Manager, Reading Order editor, PR-style Corrections panel, grouped Validation table, rich Table editor, provider-agnostic AI backend. Real gaps were narrower than the brief assumed. See `DECISIONS_LOG.md` Part 25 for the two architectural decisions this pass made (Live Projection Model; Validation Issue persistence scope) and the full audit findings.

**Shipped this session (frontend-only, no backend changes; `tsc --noEmit` and `next build` both clean after every step):**

* **Live sync fix (real bug, not a new feature).** `DocumentProvider.tsx`'s poller stopped entirely once a job reached `complete`/`failed`, so `job.document_version` froze in the frontend store forever after that point — any later edit (a correction accepted, a table saved, alt text approved) bumped `document.version` server-side but the frontend never learned about it. `DocxPreview` and the Markdown pane both silently went stale with no visual indication (only `BottomPanel`'s own `markdownStale`/`docxStale` badges, easy to miss, showed the truth). Fixed: the poller now watches `document_version` indefinitely after completion (`VERSION_POLL_INTERVAL_MS = 4000`, reusing the existing poll pattern — see the `ponytail:` comment on why this is plain polling, not a push channel). `DocxPreview` re-keys its conversion effect on `documentVersion`. `MarkdownEditor` remounts on version change (`key={`md-${document_version}`}`) and briefly flashes the changed lines via a hand-rolled positional line diff (`computeChangedLines` in `DocumentWorkspace.tsx`) — no diff library added.
* **`TableGrid.tsx`/`HeadingGrid.tsx` wired into `DocumentWorkspace.tsx`'s `specialViews`.** Both components were fully built (grid + detail panel + create/delete for tables) but never imported anywhere in the app — confirmed via grep before wiring them in, mirroring the existing `images` special-view pattern exactly. Near-zero-cost fix that delivers a "Tables Workspace" almost entirely for free.
* **`ImageGrid.tsx` filters + doc-wide bulk AI generation.** Filter bar (All/Missing Alt Text/Needs Review/Accepted/Rejected/Decorative/Low Resolution — `LOW_RES_THRESHOLD_PX = 150`, unmeasured, flagged for tuning). "Generate Missing" and "Generate Entire Document" buttons are a client-side loop over the existing per-image `POST generate-alt-text` endpoint (no new backend endpoint) — the two differ in which `AltTextStatus` values they exclude, and neither ever touches `approved`/`human_reviewed`/`decorative` images (never overwrite a reviewer's decision, per the brief's own explicit rule). Failed generations in a batch are tracked client-side (session-only, not persisted) and offered as "Retry Failed."
* **`ObjectInspectorFrame.tsx` converted to tabs** (Properties/Evidence+Validation/History/AI/Actions) instead of one long stacked-section panel. All existing prop names kept stable (`metadata`, `evidence`, `validation`, `correctionHistory`, `version`, `actions`) plus one new optional `ai` prop — so 4 of the 6 callers (Heading/Footnote/List/Callout detail panels) needed zero changes; only `ImageDetailPanel.tsx`/`TableDetailPanel.tsx` had their AI block extracted into the new prop.
* **Upload screen polish (`app/page.tsx`).** Remove buttons now reveal on hover only (`group-hover:opacity-100`); long filenames truncate with a `title` tooltip showing the full name/size/timestamp; Recent Documents rows get the same tooltip treatment using the existing `created_at` field.

**Environment note (not a code defect):** `next dev` (Turbopack) crashed on Windows this session with `0xc0000142` spawning a CSS worker process for `globals.css`, unrelated to any of the above changes (`next build` stayed clean throughout). Fixed by killing the stale dev-server process and deleting `frontend/.next` before restarting — worth trying first if `next dev` 500s on a fresh restart.

## Phase 1 IDE Redesign — remaining 4 tasks shipped (2026-07-10)

The 4 items deferred above were completed in a follow-up session, closing out the Phase 1 IDE Redesign backlog:

* **Resizable panel layout** — `WorkspaceShell.tsx` rebuilt on `react-resizable-panels@3.0.6` (pinned below the library's v4, which renamed `PanelGroup`/`PanelResizeHandle` to `Group`/`Separator` — the older API is the one every existing tutorial/shadcn integration assumes). Nav/PDF/Markdown/Context-Inspector are all independently draggable; split presets (PDF+Markdown, PDF+DOCX, Markdown+DOCX) share one `SPLIT_PAIRS` lookup instead of a hardcoded branch per pair. Body height changed from fixed `h-[640px]` to a viewport-filling `calc()`.
* **Focus Mode** — one toolbar toggle collapsing the nav+rail panels via the library's native `collapsible`/`collapsedSize`/imperative-ref API, not a hand-rolled show/hide. Deliberately skipped F11 (already the browser's own fullscreen key) and dblclick (no unambiguous target) — a single button covers the "declutter for focused work" goal.
* **Reading Order overlay** — numbered badges on `PdfViewer.tsx`, reusing the exact absolute-position/zoom-scale math the existing heading/table/image overlays already use. Scoped down from the brief: a true PDF+ReadingOrderPanel split view was ruled out because `WorkspaceShell`'s "special" mode fully replaces center+rail with the special view (no PDF pane) — building that hybrid layout was out of scope for "add an overlay," so the badges are always-visible on the main PDF view instead.
* **Validation Issue persistence** — `ValidationIssue` gained `issue_id`/`status`/`reviewed_at` (all additive, no existing constructor call site needed updating) and a `ValidationIssueStatus` enum with exactly the two states `ValidationIssueTable.tsx` already had as component-local `Set<string>` state (Ignore/Review later) — no invented third state. New `PATCH /documents/{job_id}/validation-issues/{issue_id}` mirrors `review_correction`'s action-request shape, status-only per the model's "read-only side-channel" docstring. 4 new tests in `test_corrections_api.py`; 120/120 passing across the corrections/validation/readiness/verification suite.

All 4 verified via `tsc --noEmit` + `next build` (clean) and live-checked against the running dev server with chrome-devtools (existing completed jobs, no new console errors beyond a pre-existing stale-source-PDF-path issue unrelated to these changes).

## Phase M-3 — Cross-Source Intelligence Engine extension (in progress)

The user's "Phase 2 — Cross-Source Intelligence Engine" brief (2026-07-10) asked for cross-source comparison, evidence fusion, recovery/repair/proposal/confidence engines, and a Golden Benchmark Corpus. A full backend architecture audit (3 parallel Explore agents + direct `docs/`/code reads) found this system **already exists** as Phase M-2 (FEATURE_017-020, above) — asset-agnostic `CrossSourceVerificationEngine`, `SemanticVerifier`, `EvidenceBundle`, `merge.py`'s KEEP/REPAIR/RECOVER/REMOVE, `CorrectionRecord`-based proposals, and `samples/benchmark/` as the corpus. The real gap was narrower: 2 asset types the framework doesn't cover yet (tables, footnotes) and a benchmark report that doesn't compute the requested metrics yet. Plan approved via Plan Mode 2026-07-10, continuing the live M-series numbering as **Phase M-3** (not the abandoned "Phase 2" blueprint above, which this name would otherwise collide with).

### M-3.1 — FootnoteVerifier (FOOTNOTE_VERIFY_001-003) — done, 2026-07-10

The 5th registered asset type. `src/mathpix/ingestor.py::_p2footnote_to_footnote()` has always written a hard-coded `anchor_page_number=1` placeholder on every Mathpix-sourced footnote, commented "enriched by Verification Engine" — a promise `KNOWN_LIMITATIONS.md` recorded as closed by Phase M-2, but the placeholder was still live in code (confirmed by reading `ingestor.py:386` directly, not trusting the doc). `FootnoteVerifier` (`src/verification/footnotes.py`) is that enrichment: matches each canonical Mathpix `Footnote` against an independently PDF-detected candidate and proposes the PDF-derived page as a REPAIR correction. Built on `merge.compute_merge_decisions()` (the simpler of the two Document Merge Layer patterns — a clean binary canonical-vs-PDF match, like `figures.py`, not `headings.py`'s multi-signal `EvidenceBundle` fusion, since footnote identity is one question, not several signals to fuse).

* `src/footnotes/footnote_detector.py` — split `detect_footnotes()` into a thin wrapper around new `_compute_footnotes()`, plus a new pure `detect_footnote_pdf_candidates(document) -> List[Footnote]` entry point (same split pattern `heading_detector.py` already used for `detect_headings_from_pdf()`). Zero detection-logic changes; reuses `document.blocks`, which `detect_structure()` already populates unconditionally on both the Mathpix and RAWRS-native paths.
* `src/verification/footnotes.py` (new) — `FootnoteVerifier`: matching signals `exact_body`/`body_similarity` (difflib ratio)/`number_and_type`/`positional_fallback`; findings `missing_from_package` (RECOVER — PDF found a note Mathpix's package lacks entirely), `unconfirmed` (Mathpix note with no PDF match — informational), `wrong_page` (matched pair, page disagrees — the actual bug fix, REPAIR). Self-registers via the existing `_register()`/`engine.register()` pattern; `src/verification/engine.py` untouched.
* `src/pipeline/phase1_pipeline.py` — Stage 3 gained an `else:` branch (Mathpix path) calling `detect_footnote_pdf_candidates()` + `engine.run_pdf_verification("footnote", ...)`, mirroring the existing figure/heading/list/callout call sites exactly.
* Real-corpus run (Brinkman regression PDF + its real Mathpix `.mmd` export) surfaced a **separate, pre-existing bug**: `src/mathpix/mmd_parser.py`'s `\footnotetext{N}{body}` regex is single-line-only and doesn't match that document's actual multi-line MMD output (0 footnotes parsed by Mathpix for that sample) — out of scope for M-3.1, flagged here for a future ticket. `FootnoteVerifier`'s RECOVER path is what actually surfaced those 3 footnotes as proposals despite the gap.
* Tests: `tests/test_footnote_verifier.py` (11 new). Full suite: **1500 passed, 7 skipped, 0 failed** (23m46s), up from 1487 — zero regressions.

### M-3.2 — TableVerifier — done, 2026-07-11

The 6th registered asset type. `src/mathpix/ingestor.py::_p2table_to_table()` builds Mathpix-sourced `Table` objects with no `bbox` (MMD has no PDF geometry) and a proportional `page_number` estimate — the same imprecision class the M-3.1 footnote placeholder had. `TableVerifier` (`src/verification/tables.py`) cross-checks each canonical Mathpix table against `src/tables/table_extractor.py::extract_tables()` — the existing, unmodified 4-detector evidence-fusion pipeline (`VectorBorderDetector`/`SpanAlignmentDetector`/`ColumnAlignmentDetector`/`HorizontalRuleDetector`) — already a pure function, so no refactor was needed there (unlike footnotes/headings, which needed a `_from_pdf` split).

* `src/tables/table_extractor.py` — one-line change: `extract_tables()`'s page filter now includes `MATHPIX_IMPORT` alongside `DIRECT_TEXT_EXTRACTION`, since the function re-opens `pdf_path` via `fitz` directly and never reads `Page.cleaned_text` — a page's extraction-method tag doesn't change what geometry is available to it, it only needs to exclude true OCR-only pages.
* `src/verification/tables.py` (new) — `TableVerifier`: matching signals `dimensions` (row/col equality)/`caption_similarity` (difflib ratio)/`page_proximity`/`positional_fallback`; built on `merge.compute_merge_decisions()` (the simpler binary canonical-vs-PDF pattern, like FootnoteVerifier/figures.py) since table identity is "same dimensions + caption + page," not several independent signals to fuse. `classify()` reports each independent structural disagreement (row/column/caption) as its own Finding, escalating to a single `structure_mismatch` when both row and column disagree simultaneously (`TABLE_VERIFY_001` through `_007`). Self-registers via the standard `_register()`/`engine.register()` pattern; `src/verification/engine.py` untouched.
* `src/pipeline/phase1_pipeline.py` — Stage 3's Mathpix-path `else:` branch (added for M-3.1) gained a second call: `extract_tables(document, pdf_path)` for PDF-side evidence + `engine.run_pdf_verification("table", ...)`, mirroring the footnote call site exactly. No new PDF scan or OCR re-run — reuses the same `fitz.open(pdf_path)` this stage already performs.
* Tests: `tests/test_table_verifier.py` (14 new) — perfect match, missing-from-Mathpix (RECOVER), missing-from-PDF, caption/row/column/structure mismatch, low-confidence match, ambiguous two-candidate resolution, apply + revert, and engine self-registration.
* Full suite: **1514 passed, 7 skipped, 0 failed** (up from 1500) — zero regressions. `scripts/benchmark_tables.py` (FEATURE_015.3's existing table-detection benchmark) re-run against the full corpus: binary precision/recall/F1 all 1.0000, count-level F1 0.7273 — identical to the pre-M-3.2 baseline, confirming the `MATHPIX_IMPORT`-inclusion change is inert against this corpus (all benchmark PDFs are `DIRECT_TEXT_EXTRACTION`) and introduces no detection regression.

### M-3.3 — Benchmark & Quality Metrics extension — done, 2026-07-11

Extended `src/verification/benchmark_report.py` (additive only — every M-3.1/M-3.2-era key keeps its existing meaning) plus one new module, `src/verification/docx_fidelity.py`.

* **Bug fix in `benchmark_report.py`, not TableVerifier**: `_RECOVER_FIELDS` was missing `"missing_from_mathpix"` (TableVerifier's own RECOVER kind name, added in M-3.2) — table recoveries were silently uncounted. Added.
* **Accessibility Score** — `compute_accessibility_score(issues)`: 100 minus a severity-weighted deduction (ERROR=10/WARNING=3/INFO=1) per *open* `ValidationIssue`, floored at 0. Reuses `document.validation_issues` (already populated by Stage 8 before the report is written) — no new validation engine.
* **Manual Corrections Remaining** — `AssetTypeBenchmark.remaining` = `corrections_proposed + corrections_pending_review`, per type and summed at `manual_corrections_remaining` top-level.
* **Repair Rate** — new `repair_proposed`/`repair_accepted`/`repair_rate` fields, generically distinguishing an actionable REPAIR correction from an informational-only one (`low_confidence`/`missing_from_pdf`/`unconfirmed`/etc.) via each verifier's own already-declared `RuleSpec.severity` (`!= "info"`) — no per-verifier kind list to hand-maintain. Deliberately did **not** wire the existing-but-unused `BenchmarkOutcome`/`classify_benchmark_outcome` (`src/verification/engine.py`) — doing that generically would require threading `MergeDecision` through every verifier's `classify()` signature, which is "revisiting" work explicitly out of scope this milestone.
* **Object Counts** — `object_count` per asset type (`len()` of the canonical population); also added `footnote` to `_canonical_populations()` so footnotes get this too (their model, like Table pre-M-3.2, has no `verification_status` field — a pre-existing gap in both models, left alone; adding one is a model migration, out of scope here).
* **Confidence Distribution** — `_confidence_distribution()`: a 4-bucket histogram (`0.0-0.5`/`0.5-0.7`/`0.7-0.85`/`0.85-1.0`) over `document.corrections`' `confidence` field.
* **Recovery Statistics / Verification Statistics** (Mathpix Accuracy, Recovery Rate, Object Counts) — already existed from FEATURE_019/M-3.1/M-3.2; "Cross-Source Accuracy" is the same number as `mathpix_accuracy` (no duplicate field added). "Proposal Acceptance Rate" was considered and dropped — `repair_rate`/`recovery_rate` already answer it per correction category; a third blended number would be redundant, not "(if available)" per the spec's own hedge.
* **DOCX Fidelity** (`src/verification/docx_fidelity.py`, new) — `compute_docx_fidelity(generated_path, expected_path)`: heading/paragraph/table/figure/page-break counts via python-docx (already a dependency), diffed, and reduced to one deterministic score: `1 - sum(abs(diff)) / max(1, sum(expected))`, clamped `[0, 1]`. No visual/rendering comparison, per the plan. Not wired into a benchmark script — it's a pure function; verified directly against all 10 `samples/benchmark/remediated_docx/*.docx` files (self-comparison → 1.0 each, confirming no parsing issues on the real corpus).
* **Human Minutes Saved** — NOT implemented, per instruction not to fabricate it. Documented in `benchmark_report.py`'s module docstring: needs real reviewer-timing telemetry (timestamp Accept/Reject/Edit vs. when a correction first appeared) aggregated per `rule_id` before any minutes-per-correction constant could be derived — none of that data exists yet.
* Tests: 11 new in `tests/test_benchmark_report.py`, 4 new in `tests/test_docx_fidelity.py` (15 total). Full suite: **1518 passed, 1 failed, 7 skipped** — the 1 failure (`test_docling_engine.py::TestRealDoclingIntegration::test_oleary_single_page_recovers_real_text`) is a pre-existing, unrelated environment issue (`RapidOCR`/`torch.PP-OCRv6.det.small` "unsupported configuration" in the real Docling OCR integration path) — reproduces in total isolation with zero involvement of any file this milestone touched; flagged, not fixed, per scope.

**Phase M-3 is now complete** (M-3.1 FootnoteVerifier, M-3.2 TableVerifier, M-3.3 Benchmark & Quality Metrics). A comprehensive phase review is pending before Phase M-4 begins.

## Phase M-4 — Reviewer Workspace & Queue Navigation

The corrections/proposals produced by every verifier built in Phase M-2/M-3 had no dedicated review surface — `CorrectionsPanel.tsx`'s bottom panel listed them flat, and `OutputWorkspace.tsx` had carried a "Review Queue" tab under `SOON_TABS` (never built) since the Phase 1 IDE redesign. M-4 fills that slot with a one-item-at-a-time triage workspace over the same `document.corrections` data, reusing existing pieces throughout rather than building a second proposal system.

### M-4.1 — ReviewerWorkspace shell

* `frontend/components/ReviewerWorkspace.tsx` (new) — status tabs (Pending/Accepted/Rejected/Ignored/All), asset-type/severity/rule/min-confidence/page filters, free-text search, and Document Order/Confidence/Page Number sort, all computed client-side over the already-fetched correction list (per-document volumes are in the low hundreds, not thousands — not a premature optimization to skip virtualizing). Renders the current item via `CorrectionHistoryList` (the same `CorrectionRow` the bottom panel already uses) — no second proposal-card implementation.
* `frontend/lib/correctionFilters.ts` (new) — `STATUS_TABS`/`statusTabMatches`/`isResolved` extracted out of `CorrectionsPanel.tsx` so both panels share the exact same status-grouping logic instead of a second copy.
* `frontend/components/OutputWorkspace.tsx` — `"review"` moved from `SoonId`/`SOON_TABS` to `TabId`/`ACTIVE_TABS`, wired to `<ReviewerWorkspace jobId={job.job_id} />`, and made the default active tab (`OutputWorkspace`'s primary purpose is now reviewing, not reading).

### M-4.2 — Reviewer Queue Navigation

* `src/api/schemas.py`/`src/api/routes.py::_correction_out()` — `CorrectionOut` gained `rule_id`/`severity`/`page_number`, all derived at read time rather than stored: `rule_id`/`severity` come from the owning verifier's own `RuleSpec` (looked up via `engine._verifiers[object_type].rule_table()[field]`), `page_number` from the affected canonical object (`CorrectionRecord` itself carries no page — a RECOVER correction with `object_id=None` gets `page_number=None`). `_OBJECT_ID_ATTR`/`_OBJECT_COLLECTION` cover the same "table/footnote predate the generic `.id`" lookup problem `benchmark_report.py`'s object-population tallying already solved independently; kept local to `routes.py` rather than importing that module's private helper across a package boundary.
* Selecting a queue item syncs the rest of the workspace via the *existing* `SelectionContext`/`PdfViewportContext` — the same `select()` + `jumpToObject()` pairing `SemanticNavTree`/`ContextInspectorRail` already call, not a new sync channel.
* Two infinite-render-loop bugs surfaced by live browser verification of this sync (not caught by unit tests, since both only manifest when a consumer re-selects/re-jumps the *same* object every render):
  * `SelectionContext.select()` now bails out to the same `prev` reference when the requested selection is already current, instead of always constructing a new object — without this, a queue synced to "whichever item is current" churns `selection`'s identity every render, which churns `select`'s own identity, which re-fires any effect depending on it, which calls `select` again, forever ("Maximum update depth exceeded").
  * `PdfViewportContext`'s `setZoom`/`jumpToObject` are now `useCallback`-wrapped (empty deps — each only calls a setState setter, which React itself guarantees is stable), so the context `value`'s function identities don't change just because the provider re-rendered for an unrelated reason.

### M-4.3 — Proposal Review Experience

Keyboard-first review, ignored while focus is inside a text input/textarea/select (search box, the Proposal Card's own edit fields) so shortcut letters don't fight normal typing: `n`/`→` next, `p`/`←` previous, `a` accept, `r` reject, `i` ignore, `u` undo, `e` re-open Inspector, `j` re-jump to PDF (relies on `jumpTarget`'s nonce always bumping, even for the same page — see M-4.2's `jumpToObject`), `/` focus search. All actions call the same generic Corrections API `CorrectionRow`'s own buttons call — one endpoint, two triggers, not a second business-logic path. On-screen legend documents the same list, not left silent.

### M-4.4 — Minimal correction telemetry

`src/models/correction.py` — `CorrectionTelemetryAction` (`displayed`/`accepted`/`rejected`/`edited`/`ignored`/`undone` — deliberately narrower than `CorrectionAction`/`CorrectionStatus`: `needs_review` is an escalation, not one of the 5 reviewer decisions this milestone measures) and `CorrectionTelemetryEvent`, appended to `CorrectionRecord.telemetry_events` (not a parallel telemetry model or table) by `review_correction()` in `routes.py`. The first action on any correction backdates a synthetic `displayed` event to `correction.created_at` (the deterministic proxy for "earliest point available to a reviewer," since real per-render UI instrumentation is out of scope this milestone); `latency_seconds` is `timestamp - created_at`, same deterministic basis. Collection only — `telemetry_events` is not exposed via `CorrectionOut`/the API response; nothing reads it yet, a future benchmark-report extension will (mirrors M-3.3's own "Human Minutes Saved" deferral for the same reason: no consumer to ground the number against yet).

Tests: 4 new in `tests/test_corrections_api.py` (`TestCorrectionTelemetry`, M-4.4) plus 1 for M-4.2's derived fields; frontend changes verified via live browser + `tsc --noEmit`/`next build`, per this repo's established pattern (no frontend test runner wired into this suite).

**Phase M-4 complete** (M-4.1 ReviewerWorkspace, M-4.2 Queue Navigation, M-4.3 Review Experience, M-4.4 Telemetry).

## Phase M-5 — Targeted OCR Evidence Integration

`src/ocr/targeted.py` (`ocr_region()`, FEATURE_019) existed since an earlier phase as a region-scoped OCR primitive but had no caller. M-5 wires it into `HeadingVerifier` as one more `EvidenceSignal` — evidence of last resort, only consulted when every other signal (PDF match, typography, whitespace, running-header) has already left the fused bundle ambiguous — and, in the process of validating it against the real benchmark corpus, surfaced and fixed two real bugs plus one more found while writing up this phase.

### M-5.1 — Targeted OCR as an EvidenceSignal

* `src/verification/headings.py::_targeted_ocr_signal()` — crops the heading's own line (via `HeadingLayoutContext.bbox_index`, padded `_OCR_CROP_Y_PADDING` vertically, full page width since `bbox_index` only tracks vertical extent) and OCRs it via `ocr_region()`; the `difflib` similarity between the OCR text and Mathpix's own heading text becomes one more weighted signal into `EvidenceBundle`'s existing weighted-mean confidence — it never changes how confidence itself is computed, only ever contributes one more input.
* Gated by `_OCR_AMBIGUOUS_CONFIDENCE_THRESHOLD = 0.5`, the same boundary `_RUNNING_HEADER_REPAIR_THRESHOLD`/`decide_from_evidence()` already treat as "ambiguous" — one shared notion of ambiguity reused, not a second threshold invented. Never invoked for an already-confident candidate (verified directly: `test_high_confidence_candidate_never_invokes_ocr` asserts `ocr_region` is never called).
* Every failure mode degrades to "no signal," never a crash: no `pdf_path`, no layout context, `TextResolver` (M-5.3) can't resolve the heading's text to any PDF line, `TargetedOCRError`, or — caught only once this code path actually ran against a real document (M-5.2) — a raw Surya `ValueError` escaping `ocr_region()` uncaught. All logged and swallowed; "evidence of last resort" must never take down verification for a single ambiguous heading.

### M-5.2 — Real-corpus validation benchmark

`docs/m52_ocr_evidence_benchmark.json` (throwaway benchmark script, run twice per document — OCR threshold forced to `-1.0` for "before", the real `0.5` for "after" — across all 10 benchmark-corpus PDF+MMD pairs) is what this milestone's own name is for: running M-5.1 against real documents instead of only synthetic PDFs. It disproved an assumption before the surrounding architecture expanded on top of it, and surfaced the two real bugs M-5.3 and M-5.4 exist to fix:

1. **Text resolution rarely matches at all.** `HeadingLayoutContext.layout_index`/`.bbox_index` are `{exact_line_text: value}` dicts; Mathpix's own text and PyMuPDF's independent per-line extraction agree on *content* far more often than they agree on the *exact string* (segmentation/whitespace/OCR-artifact differences), so an exact-key lookup missed constantly — not a synthetic guess, a real diagnostic run (`diagnose_mismatch.py`) confirmed the dominant failure mode was a running header PyMuPDF grouped with an adjacent page number into one combined line. This is what M-5.3's `TextResolver` exists to fix — and disproved the original assumption that extending `MultiSignalMatcher` (the object-identity matcher) was the right layer; text-to-key resolution turned out to be a narrower, lower-level question than object identity, answered by a new, smaller abstraction instead.
2. **A real Surya API mismatch.** The one document in the corpus where the OCR-ambiguous gate actually fired (`FolkPedagogy_Bruner`, 5 calls) hit `predictor([image], full_page=False)` raising `"layout_results required when full_page=False"` in the installed `surya-ocr` 0.20.0 — the old code comment's assumption about `full_page`'s meaning was backwards (see M-5.4).

### M-5.3 — Evidence Resolution Layer (generic TextResolver)

* `src/verification/text_resolution.py` (new) — `TextResolver`: a generic, tiered text-to-key resolver (exact → normalized [NFKC/casefold/whitespace-collapsed/punctuation-stripped] → containment [only when exactly one candidate matches — an ambiguous multi-match is a miss, not a guess] → `difflib` fuzzy, guarded by `_MIN_FUZZY_LENGTH=6` so short strings like a stray page-number "heading" can't produce a confident-looking wrong match). Deliberately not an extension of `MultiSignalMatcher` — that operates on paired object lists via weighted signals for an identity decision, a different abstraction level than resolving one string against one page's raw-text dict (see M-5.2's disproved assumption).
* `src/verification/headings.py` — `_typography_signal()`/`_whitespace_signal()`/`_targeted_ocr_signal()` all now resolve through a per-page `TextResolver` (`_layout_resolver()`/`_bbox_resolver()`, built lazily and reused across every heading on that page — normalization computed once per page, not once per heading) instead of the old exact-dict `.get()`.
* Tests: `tests/test_text_resolution.py` (new, tier-by-tier coverage of `TextResolver` in isolation).

### M-5.4 — Targeted OCR compatibility fix

* `src/ocr/targeted.py::ocr_region()` — `full_page=False` → `full_page=True`. The old comment's model was backwards: in installed `surya-ocr` 0.20.0, `full_page=True` means "treat this image as one region to recognize directly" (exactly this function's case — the image is already a known, isolated crop via PyMuPDF's own `clip`), and `full_page=False` means "this image contains multiple layout blocks needing per-block requests," which requires a `LayoutResult` this function never had — the exact cause of the error M-5.2 surfaced. `page_result_to_text()`'s parsing is unaffected; the result shape is identical either way.

### Found during this continuation session — targeted OCR rebuilt the whole model per call

While verifying M-5's work before writing it up here, `docs/m52_ocr_evidence_benchmark.json`'s own "after" column showed `FolkPedagogy_Bruner`'s elapsed time jump to **26,160s (~7.3 hours) for 5 OCR calls** post-M-5.4 — the crash was fixed, but the fix's own performance was never checked. Root cause: `src/ocr/surya_config.py::build_recognition_predictor()` — its own docstring already documented the contract ("construct one of these per document/run and reuse it across pages... that cost should only be paid once per process, not once per page") and `src/ocr/surya_engine.py` already follows it (builds one predictor, loops it across every page in a document). `src/ocr/targeted.py::ocr_region()` violates that contract: it calls `build_recognition_predictor()` fresh on every invocation, and `_targeted_ocr_signal()` calls `ocr_region()` once per ambiguous heading — so a document with several ambiguous headings rebuilt the entire Surya model from scratch once per heading. Fixed with `@lru_cache(maxsize=1)` on `build_recognition_predictor()` itself (`surya_config.py`) — the shared factory function every caller already goes through, so the fix applies process-wide without touching `targeted.py`, `surya_engine.py`, or either call site. Tests monkeypatch this function by replacing the reference at each call-site module (`src.ocr.targeted.build_recognition_predictor` / `src.ocr.surya_engine.build_recognition_predictor`), not the underlying function object, so the cache never affects them.

Also caught by this pass: `tests/test_targeted_ocr.py::TestOcrRegion::test_recovers_text_from_region` still asserted the pre-M-5.4 `full_page=False` call shape — nobody had updated it when M-5.4 changed the real call to `full_page=True`. Updated the assertion to match the (correct, already-shipped) `full_page=True` behavior.

**Re-run evidence (this session, uncontended — run after the full pytest suite finished, so no CPU contention with it):** the first OCR call — `FolkPedagogy_Bruner`, the exact document/region that took the model-rebuild path before — completed in **~64s**, down from the ~87min/call implied by the stale 26,160s/5-calls figure above. That confirms the caching fix. The full 10-document corpus re-run did not finish, though: it stalled after that first call — 1h23m elapsed with only 116s of CPU time on the process, i.e. blocked, not computing — and was killed rather than left to run indefinitely. This looks like a separate, pre-existing reliability gap in the underlying Surya inference call itself (the same class of failure M-5.1's `_targeted_ocr_signal()` already wraps in a broad `except Exception` for a raised error — see M-5.2's "Inference error: Request timed out" — but that guard only catches an exception the call actually raises, not a call that never returns at all). Flagged, not fixed here: `ocr_region()` has no timeout around the underlying `predictor(...)` call, so a hung inference request currently blocks `HeadingVerifier.classify()` indefinitely for that one heading rather than degrading to "no signal" like every other failure mode in `_targeted_ocr_signal()` does. A future fix would wrap that call with a bounded timeout (e.g. a thread/process-based deadline) so this joins the same graceful-degradation path as `TargetedOCRError`. `docs/m52_ocr_evidence_benchmark.json` still holds the pre-fix numbers (10/10 documents, all real) since the corpus re-run didn't complete; not overwritten with a partial result.

Tests: `tests/test_heading_verifier.py::TestTargetedOcrEvidence` (3 new: high-confidence never invokes OCR, low-confidence invokes it exactly once, OCR agreement raises confidence above the no-agreement baseline). Full suite after all of Phase M-4, Phase M-5, and this session's two fixes: **1558 passed, 7 skipped, 0 failed** (52m45s for the first run, which caught the one stale assertion above; clean on re-run).

**Phase M-5 complete** (M-5.1 EvidenceSignal, M-5.2 validation benchmark, M-5.3 TextResolver, M-5.4 compatibility fix, plus the predictor-caching fix and stale-test fix found closing out this phase). The OCR-call timeout gap noted above is a known follow-up, not a blocker — every other failure mode already degrades gracefully, and the caching bug (the one that made this path unusable in practice) is confirmed fixed.
