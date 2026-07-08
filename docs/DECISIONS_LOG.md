# RAWRS Decisions Log

## Purpose

This log records *why* RAWRS's architecture and rules are what they are, not what they are (that's `ARCHITECTURE_CURRENT.md` / `PHASE_STATUS.md`) or what's still missing (`KNOWN_LIMITATIONS.md`).

Two kinds of decisions are recorded here:

* **Numbered architecture decisions** — referenced directly in code docstrings as "approved architecture decision #N", but never previously written down anywhere. Reconstructed here from the comments that cite them.
* **Benchmark reconciliation decisions** — conflicts found between the original `docs/` rule files and real benchmark PDFs, and how each was resolved. Originally recorded in `BENCHMARK_RECONCILIATION_AND_PHASE1_PLAN.md` (root); restated here as the permanent record.

Treat this file as append-only. When a future decision reverses one recorded here, add a new entry that supersedes it — don't edit history out.

---

## Part 1 — Numbered Architecture Decisions

Code across `src/models/` cites decisions "#3" through "#6" by number. No prior document defined them; this section is the first time they've been written down. **Decisions #1 and #2 are referenced implicitly by this numbering (it starts at #3) but no surviving code comment states what they were** — they likely predate the convention of citing decisions by number in docstrings. If you find out what they were, add them here rather than renumbering anything.

### Decision #3 — OCR confidence is tracked per page, not per region

**Decision:** `Page.ocr_confidence` is a single value per page (HIGH / MEDIUM / LOW). Finer-grained per-region (per-line, per-block) confidence is deferred.

**Why:** Simplicity — Phase 1 has no consumer that needs sub-page confidence resolution, and adding it would mean threading confidence through every block-level structure speculatively.

**Where:** `src/models/page.py` (`OCRConfidence` enum docstring).

**Status:** Still in effect. Not revisited by Phase H, even though `Document.blocks` (added later) would technically allow per-block confidence — that remains future-phase scope, not picked up incidentally.

---

### Decision #4 — Figure is composed within Image, not a sibling top-level entity

**Decision:** `Image.figure: Optional[Figure]`, not `Document.figures: List[Figure]`.

**Why:** A Figure (caption/label/number/alt-text) has no independent existence apart from the image it describes — it is always a property of exactly one Image, never shared or referenced from elsewhere. Modeling it as a sibling top-level list would require synthetic foreign-key-style linking for no benefit.

**Where:** `src/models/image.py`, `src/models/figure.py`.

**Status:** Still in effect. Phase F.1–F.5 (Image accessibility infrastructure) built entirely on top of this — `Image.bbox`, `Figure.alt_text`, `Figure.alt_text_status` all hang off this same composition.

---

### Decision #5 — ValidationIssue references a page by number, not by holding a Page object

**Decision:** `ValidationIssue.page_number: Optional[int]`, not `ValidationIssue.page: Optional[Page]`.

**Why:** Keeps validation a strictly read-only side-channel that never holds a live reference back into the content tree it's validating — a `ValidationIssue` can be serialized, logged, or handed to a reviewer without dragging the entire `Page` (and transitively the `Document`) along with it.

**Where:** `src/models/validation_issue.py`.

**Status:** Still in effect across all 16 current rule IDs (see `PHASE_STATUS.md`).

---

### Decision #6 — Metadata is a passive container with explicitly-assigned fields, not a computed view

**Decision:** `Metadata.page_count` / `Metadata.image_count` etc. are set directly by the pipeline stage that finalizes processing, rather than being `@property` methods computed from `Document.pages` / `Document.images` at access time.

**Why:** Traceability — a bug in a computed property silently produces a wrong number every time it's read; an explicit assignment's correctness can be checked once, at the one call site that sets it, and `DOC_002` validation (metadata staleness) exists specifically to catch the case where the explicit value and the live tree disagree.

**Where:** `src/models/metadata.py`.

**Status:** Still in effect. `DOC_002` (see `PHASE_STATUS.md` / `VALIDATION_RULES.md`) is the direct consequence of this decision: it exists *because* the value isn't computed and therefore can go stale.

---

## Part 2 — Benchmark Reconciliation Decisions

In an earlier session, the team ran RAWRS against a new 4-PDF benchmark set (3 born-digital, 1 scanned) and found nine direct conflicts between the original `docs/` rule files and what the benchmark's expected output actually required. Each was resolved deliberately — full reasoning lives in `BENCHMARK_RECONCILIATION_AND_PHASE1_PLAN.md` (root); this is the durable summary.

**Source-of-truth precedence used to resolve these conflicts** (highest to lowest):

1. Architecture/process constraints (`CLAUDE_INSTRUCTIONS.md`, `ARCHITECTURE.md`, exclusion lists) — never overridden by a benchmark file.
2. Behavioral rule docs (`HEADING_RULES.md`, `PAGE_RULES.md`, `OCR_RULES.md`, `VALIDATION_RULES.md`, `PHASE1_SCOPE.md`) — amendable when benchmark evidence proves a documented example wrong, but the fix is to amend the doc, not silently chase the benchmark in code.
3. Benchmark corpus — empirical ground truth, but only where internally consistent across samples.
4. Existing code decisions — lowest precedence.

This same hierarchy still governs how `docs/` should be amended going forward; see `DOCUMENTATION_MAP.md`.

| # | Conflict | Decision | Implemented? |
|---|---|---|---|
| C1 | Docs specify page markers as `###### Page 1` (word "Page" + sequential index); one benchmark style uses the bare printed page number (`###### 80`). | Amend docs to prefer the source's own printed page number when detectable, else fall back to sequential index. | **Implemented** (feature_011 Part 2, 2026-06-28). `heading_detector.py` and `markdown_builder.py` now emit the bare `page_label` (printed label or physical page number as string, no "Page " prefix). DOCX generator no longer applies explicit run-property overrides to H6 paragraphs — they inherit the Heading 6 style defaults, matching benchmark convention. `HEADING_RULES.md`/`PAGE_RULES.md`/`PHASE1_SCOPE.md` updated to reflect `###### N` format. |
| C2 | Page markers were absent entirely in some benchmark samples vs. docs' unconditional "every page" rule. | Keep the unconditional rule; treat marker-less benchmark samples as benchmark defects. | **Implemented as decided.** Every page still gets a marker. |
| C3 | One benchmark sample's expected DOCX had zero page breaks despite 12+ page-break markers in its own expected Markdown. | Benchmark defect — keep existing `docx_generator.py` behavior (`page_count - 1` breaks, no trailing break). | **Implemented as decided.** |
| C4 | Docs exclude Alt Text Generation from Phase 1; benchmark DOCX images carried rich, AI-quality descriptive alt text. | Do **not** add AI-generated alt text. Add a cheap, deterministic, rule-based **placeholder** alt-text string instead. Full descriptive alt text stays an explicit, separately-decided out-of-scope item. | **Implemented.** This is exactly Phase F.3 (`Figure.alt_text` / `AltTextStatus.PENDING_REVIEW`, see `PHASE_STATUS.md`). `PHASE1_SCOPE.md`/`RAWRS_PROJECT_CONTEXT.md` were not updated to reflect this at the time — fixed as part of this reconciliation pass. |
| C5 | Docs' heading-detection examples are all numbered/keyword patterns; real benchmark headings are unnumbered Title-Case phrases. | Keep H1–H6 hierarchy/formatting semantics; change the *detection heuristic* to font-size-rank + bold + line-isolation (layout signal), with numbering/keyword patterns kept as a secondary/override signal. | **Implemented** in `heading_detector.py` (layout signals from `src/structure/layout_signals.py`). `HEADING_RULES.md`'s "Detection Heuristics" addendum recommended at the time was never actually added — fixed as part of this reconciliation pass. |
| C6 | "REFERENCES" was a heading in one benchmark sample, plain text in another — same keyword, different ground truth. | Fixed rule for RAWRS: a fixed keyword list (References/Bibliography/Appendix/Acknowledgements) always promotes to H2, independent of layout signal. | **Implemented** in `heading_detector.py`. Documented for the first time in this reconciliation pass (`HEADING_RULES.md`). |
| C7 | No filtering rule existed for over-extracted images (54 raw refs kept where the benchmark wanted ~1). | Add an explicit filtering rule: discard background/full-page images (≥~85% page area), slivers, tiny images, and duplicates. | **Implemented** — this is Phase C (Image Filtering). See `PHASE_STATUS.md` for the five concrete thresholds. |
| C8 | The benchmark's own expected Markdown and expected DOCX for the same source document structurally disagreed with each other. | Keep RAWRS's own principle that DOCX generation derives strictly from RAWRS's own generated Markdown — treat the benchmark's internal MD/DOCX mismatch as evidence of how *that* benchmark pair was produced, not a reason to weaken the principle for RAWRS's own pipeline. | **Implemented as decided** (no code change required — this affirmed an existing principle). |
| C9 | `OCR_RULES.md` implied every PDF goes through Docling/Surya; the benchmark showed 3 of 4 PDFs needed zero OCR. | Add a Direct Text Extraction step ahead of the OCR engines, gated by per-page classification. | **Implemented** — this is Phase A (Direct Text Extraction) + Phase D.0 (OCR Routing). |

### Other decisions made during the same reconciliation

* **OCR engine order is Direct Text → Docling → Surya, never "everything → OCR."** Direct extraction is tried first and is the cheapest, zero-uncertainty path; Docling is the primary OCR engine; Surya is a fallback used only on pages Docling left empty, not a parallel/competing engine.
* **Pipeline stage reordering (Heading Detection before Image Extraction; Validation before DOCX Generation) was recommended but deliberately deferred**, not implemented. The two deviations from `ARCHITECTURE.md`'s canonical order are still present today — see `ARCHITECTURE_CURRENT.md`. This is a known, tracked gap, not an oversight.
* **Reading order / cross-page paragraph stitching was explicitly deferred** as an architecture-sensitive change requiring its own sign-off (it would touch the frozen `Page`/`Document` model). Phase I.1 later implemented reading-order *validation* (flagging only) without revisiting this deferral — reconstruction is still not on the table. See `KNOWN_LIMITATIONS.md`.

---

## Part 3 — Strategic Agreements (from project handover, June 2026)

These are durable working agreements that should constrain future phases, not implementation details:

1. **Deterministic first, AI later.** Every rule-based capability is built before any AI-assisted one; AI enhances, it doesn't replace.
2. **Human review is never removed**, even for future AI-generated outputs (alt text, OCR corrections, QA suggestions) — RAWRS is assistance software, not autonomous remediation software.
3. **Dataset collection starts immediately**, not gated on AI phases existing yet. Phase F.5 (`outputs/alt_text_dataset/`) is the first concrete instance of this.
4. **Phase 1 stays near-zero-cost.** No paid APIs in the production pipeline; only local/open libraries (PyMuPDF, Docling, Surya).
5. **Every phase preserves previous behavior.** No phase should break existing tests or replace a stable module without strong justification — enforced today by running the full test suite (486 tests as of this audit) before any phase is considered done.

---

## Part 4 — Surya Backend Architecture Correction

### Background

Two conflicting statements existed in project history: (A) that Surya required llama.cpp/llama-server setup and a `LLAMA_CPP_BINARY` environment variable during Phase D.2 implementation, and (B) a later audit's conclusion that no llama.cpp reference exists in RAWRS's codebase and that Surya uses "standard `RecognitionPredictor` inference," not llama.cpp.

### What a dedicated backend audit found

Tracing `run_surya_ocr()` past RAWRS's own code and into the installed `surya-ocr` package (version 0.20.0, "Surya2" — a vision-language-model rewrite, not classical Surya) showed: `SuryaInferenceManager` auto-selects an inference backend per host — `vllm` if an NVIDIA GPU is present, `llamacpp` otherwise. This project's deployment is CPU-only, so it resolves to `llamacpp`, which spawns the real upstream `llama-server` binary and serves the `surya-2.gguf` model through it over a local OpenAI-compatible HTTP API. This was confirmed with live, non-circumstantial evidence on the deployment host: a `LLAMA_CPP_BINARY` environment variable pointing at a real, present `llama-server.exe`; a cached `surya-2.gguf` (1.27 GB) + `surya-2-mmproj.gguf` (205 MB) model pair pulled from Hugging Face Hub; and a `llama-server` runtime log showing genuine per-token generation timing for a completed OCR request.

### Decision

Statement A was correct. Statement B's narrow factual observation (no llama.cpp string appears in RAWRS's own `src/`) was correct, but the conclusion it drew from that observation (Surya doesn't use llama.cpp) was wrong, and was incorrectly written into `OCR_RULES.md`, `TECH_STACK.md`, `PHASE_STATUS.md`, and this file as a "correction" during an earlier documentation reconciliation pass. That incorrect correction has now been reversed in all four documents.

### Why the error happened

`requirements.txt` declared `surya-ocr` with no version pin. The installed 0.20.0 is architecturally unrecognizable from classical Surya — it replaced direct torch model inference with a pluggable VLM backend (`vllm`/`llamacpp`) that, on a CPU host, requires and shells out to a full external llama.cpp installation. An audit that stops at "is there a `llama-cpp-python` entry in `requirements.txt`?" or "does RAWRS's own code import anything llama-named?" will answer "no" to both and conclude no llama.cpp dependency exists — missing that the dependency lives one layer down, inside the third-party package's own runtime backend selection, not in RAWRS's code or RAWRS's direct dependency list.

### Resolution

`requirements.txt` now pins `surya-ocr==0.20.0` (the version this entire audit trail, including the test suite's `real_surya`-marked tests, was actually validated against). This doesn't change runtime behavior — 0.20.0 was already installed — but it stops a future `pip install -r requirements.txt` on a clean machine from silently landing on a different Surya major version with a different backend architecture (or none at all) without anyone noticing until something breaks in a way that looks unrelated to a dependency change.

### Status

Resolved and verified. After pinning `surya-ocr==0.20.0` in `requirements.txt`, the full test suite was re-run in two parts: the fast subset (`pytest -m "not real_docling and not real_surya"`) returned 481 passed, 1 skipped, 0 failed in 4m05s; the real, unmocked Surya suite (`pytest -m real_surya`) returned 2 passed, 0 failed in 10m35s, including a visible llama.cpp subprocess spawn/teardown (a benign Windows process-termination warning on exit referenced the spawned `llamacpp` PID) — independent confirmation, at verification time, that the documented backend path is what actually ran. No regressions; results are identical to the pre-pin baseline, as expected since 0.20.0 was already installed and the pin changes no runtime behavior, only future-install reproducibility.

Treat any future Surya-related documentation as needing to describe the `vllm`/`llamacpp` backend split explicitly, not "Surya is a local OCR model" as a black box — that abstraction is exactly what produced the original error.

---

## Part 5 — XML Sanitization Architecture (Defense in Depth)

### Background

A production PDF crashed `generate_docx` with `ValueError: All strings must be XML compatible: Unicode or ASCII, no NULL bytes or control characters` — an error raised inside `lxml`'s compiled core (`apihelpers.pxi`, confirmed by direct reproduction, not assumption) the instant an OOXML text node or attribute is set to a string containing a character XML 1.0 disallows.

### What the investigation found

Tracing every text path into the system (direct extraction, Docling, Surya, headings, figure captions, alt text, footnotes, endnotes, validation messages, metadata) found **three independent PyMuPDF read passes**, not one: `src/ocr/extractor.py` (`page.get_text()`), `src/structure/structure_detector.py` via `src/structure/layout_signals.py` (`page.get_text("dict")`), and `src/headings/heading_detector.py`'s own separate layout-index read (also `page.get_text("dict")`, used only for font-size/bold lookup, not text content). Only the first of these passed through any cleanup at all (`normalize_whitespace()` — whitespace only, never character-class legality), and even that cleanup never addressed XML legality.

An initial recommendation to "fix `normalize_whitespace()`, everything downstream is protected" was tested against the actual code and **disproved**: figure captions (`src/images/image_extractor.py`) and footnote/endnote text (`src/footnotes/footnote_detector.py`) both read `TextBlock.text` from the second, independent pass and would have stayed vulnerable regardless of any fix to the first. Future AI-generated content (alt text, equations, tables, callouts) would be unprotected by construction, since generated text has no PDF-extraction call to attach a sanitizer to at all.

### Decision: Architecture C (Defense in Depth), not source-only or export-boundary-only

Evaluated three candidates:

- **Source-only** (Architecture A): incomplete today (misses captions/footnotes) and incapable of covering future AI-generated text by construction.
- **Export-boundary-only** (Architecture B): would prevent every DOCX crash, but leaves Markdown — this project's own stated "source of truth for downstream processing" (`docs/ARCHITECTURE.md`) — silently diverging from the DOCX it's supposed to describe, and converts a loud crash into a quiet, untracked content alteration.
- **Defense in depth** (Architecture C): adopted. Three layers, each independently necessary:
  1. **Layer 1** (`src/utils/text_sanitization.py`) — sanitizes at every point text first enters the Document model (`src/ocr/extractor.py`, `src/ocr/docling_engine.py`, `src/ocr/surya_engine.py`, `src/structure/structure_detector.py`), keeping Markdown, the in-memory model, and any future API/frontend consumer clean, not just the DOCX.
  2. **Layer 2** (`src/validation/validator.py`, rule `DOC_004`) — discloses every place Layer 1 had to act, via a new `Document.sanitization_events` audit trail (`src/models/sanitization.py`) Layer 1 emits at the moment it acts, since by design there is nothing left to re-detect in already-clean Document fields afterward.
  3. **Layer 3** (`src/docx/docx_generator.py`, `_safe_run_text()`) — a last-resort guard at every call site that sets OOXML text/attributes, so a future text-creation path added without being wired into Layer 1 still cannot crash DOCX generation. Logs loudly (`logger.error`) if it ever actually changes something, since that should never happen in normal operation and signals a real upstream gap.

A consistency gap was also found and fixed in `src/headings/heading_detector.py`: its own independent layout-index read builds a dict keyed by line text, looked up against `page.cleaned_text`'s now-sanitized lines — left unfixed, a heading containing an illegal character would have silently lost its bold/font-size layout signal (a different, quieter regression Layer 1 alone would have introduced). Sanitized identically there too, without re-recording a duplicate audit event for the same underlying character.

### Severity re-derivation: DOC_004 is WARNING, not ERROR

An earlier draft of this work (before Layer 1 existed) recommended `DOC_004` as **Error**, reasoning that an XML-illegal character is unconditionally fatal to DOCX generation if left unhandled. That recommendation was explicitly revisited once Architecture C actually existed, and reversed:

Per `docs/VALIDATION_RULES.md`'s own definitions — Error means "processing quality is compromised" (examples: missing page, corrupted extraction, failed markdown generation); Warning means "potential issue, human review recommended." By the time `DOC_004` can possibly fire, Layer 1 has *already* removed the character and the document has *already* generated successfully — "processing quality is compromised" is false every single time this rule runs, by construction, because the rule only exists to report on an already-handled event. The premise behind the original Error recommendation (it "will unconditionally break things") no longer holds once the thing that would have broken it can no longer reach that point. What remains true matches Warning exactly: confirm the removed character's surrounding text still reads as intended — a recommended check, not a confirmed defect or a processing failure.

This is recorded here specifically because it is a case where a prior recommendation's premise changed (sanitization started existing) and the conclusion needed to change with it, not be carried forward by habit. See `docs/VALIDATION_RULES.md`'s "DOC_004 severity" section for the same reasoning restated alongside the rule itself.

### Status

Resolved and implemented. All three layers built and tested (`tests/test_text_sanitization.py`, plus dedicated `TestXmlSanitization`/`TestXmlSanitizationSafetyGuard`/`TestXmlSanitizationEndToEnd` classes added to `tests/test_ocr.py`, `test_docling_engine.py`, `test_surya_engine.py`, `test_structure_detector.py`, `test_images.py`, `test_footnote_detector.py`, `test_validation.py`, `test_docx.py`, and `test_pipeline.py` — six independent path-specific reproductions plus a full end-to-end pipeline test, per the architecture review's own test strategy). Full suite re-run after implementation; see test output recorded alongside this change for pass/fail counts.

---

## Part 6 — Paragraph Reconstruction (bug_001)

### Background

A regression PDF (`samples/regressions/bug_001_brinkman_word_splitting/`) produced generated Markdown with one paragraph per raw PDF line throughout the entire document (2037 lines vs. an expected 362), with one sentence rendered as a dramatic vertical stack of single words. A dedicated root-cause audit (`notes_md/root_cause_audit.md` in that regression folder) found **two independent, compounding bugs**, not one: PyMuPDF's own line-clustering mis-segmenting a justified line when inter-word gaps are encoded as absolute positioning rather than literal space glyphs (upstream of RAWRS), and `markdown_builder.py::_render_page_body()` having no paragraph-joining logic at all (the pervasive cause).

### Decision: Option B (geometry-grounded grouping on `TextBlock.source_block_index` + bbox), not lexical joining or a new pipeline stage

Three candidates were designed (`notes_md/paragraph_reconstruction_design_review.md`, same regression folder):

- **Option A (lexical line-joining):** smallest diff, but "coincidental, not structural" — would glue lines together based on sentence-final punctuation heuristics with no positional grounding, a known false-positive risk on any line that legitimately ends mid-sentence at a wrap point.
- **Option B (adopted):** an additive `TextBlock.source_block_index` field plus a new `src/structure/paragraph_grouper.py::group_into_paragraphs()`, merging same-block lines (fixing the pervasive bug) gated by a same-baseline + x-continuity/gap guard against multi-column false-merges (fixing the justified-line mis-segmentation), with a vertical-gap fallback reusing the validator's already-tested 1.5×-median-line-height threshold.
- **Option C (dedicated `LayoutZone` pipeline stage):** rejected as larger than warranted — the same "do not redesign architecture" concern that later also weighed against Option C in the `feature_005` review (Part 8) below.

### Status

Resolved and implemented. `src/structure/paragraph_grouper.py`, `src/models/paragraph.py` (the `Paragraph` model — deliberately transient, not stored on `Document`). Brinkman regression's generated Markdown went from 2037 to 545 lines (expected: 362; the remaining gap is table/footnote rendering, a separate, already-documented limitation). Tests: `tests/test_paragraph_grouper.py`, plus updated cases in `tests/test_markdown.py`/`tests/test_docx.py`. See `PHASE_STATUS.md` ("Phase L").

---

## Part 7 — Heading Detection Fallback Tier (bug_002)

### Background

The same Brinkman regression PDF used 12 real section headings rendered in a distinct embedded font subset (`AdvP7D0F`) with no `"bold"` substring and no PyMuPDF bold flag bit set — defeating the existing bold-relative-to-body-text gate (`layout_signals.py::span_is_bold()`). A design review evaluated font-family differentiation, relative font-size analysis, font-frequency analysis, statistical heading scoring, and a hybrid approach; a follow-up review then specifically evaluated adding a "heading isolation" (sole-line-PyMuPDF-block) signal to reduce false positives among recurring non-body-font elements (running headers, journal metadata).

### Decision: a fifth, last-resort fallback tier, gated by 6 conditions — 2 of them found as real regressions during implementation, not designed upfront

Font≠document-body-font AND (font, size) recurs ≥2× **among sole-line-block contributions only** AND the line is itself a sole-line block AND size≥body-size AND not-the-H1-slot-line AND has an alphabetic character.

Two of these six conditions were not part of the original audited design and were added only after implementation surfaced real, demonstrated false positives:

- **Sole-line-only recurrence counting:** without this, "Chapter 9"/"Chapter 7" (non-sole, 3-line masthead blocks shared with the chapter title) inflated recurrence for the unrelated, separately-blocked, sole-line bylines beneath them ("James Calderhead" / "Michael Fullan and Andy Hargreaves," coincidentally sharing the same 14pt-Helvetica signature) past the threshold — caught by the benchmark test suite, not anticipated.
- **Size≥body-size:** table/figure captions and table-footnote lines (8–9pt, distinct recurring font, sole-line) satisfied every one of the original six gates exactly like the 12 real headings (which are 12pt against a 10pt body) — found during verification against the real Brinkman PDF, disclosed as a deviation from the literal originally-audited spec before implementing it, rather than silently expanding scope.

The sole-line-block restriction is enforced **only inside this fifth tier**, never as a global heading requirement — "Chapter 9"/"Chapter 7" are real headings that are *not* sole-line blocks, but are resolved by the higher-priority H1-positional-slot rule before the fallback tier is ever reached, confirmed empirically against the real Calderhead/Fullan & Hargreaves PDFs, not just argued structurally.

### Status

Resolved and implemented in `src/headings/heading_detector.py` (`_is_fallback_heading()`, `_build_fallback_tier_index()` — an independent PDF pass that does not touch the shared `line_layout()`/`LineLayout` signal `structure_detector.py` also depends on). Brinkman heading count: 5→19 content headings (12 targeted + "Funding"/"Notes" bonus, same font signature). Calderhead/Fullan & Hargreaves/Teaching-as-a-Professional-Discipline/O'Leary: zero change, regression-verified. Full fast-subset suite: 567 passed, 0 failed. Tests: `tests/test_headings.py::TestBug002FallbackTier` (6 new tests). See `PHASE_STATUS.md` ("Phase B").

**Known, explicitly out-of-scope finding from the same audit (bug_003, not addressed by this decision):** the H1-positional-slot rule itself assumes the document's first non-blank line is always the title; on the Brinkman PDF that line is a journal kicker label ("Article"), which wins the H1 slot instead. Not fixed here — see `KNOWN_LIMITATIONS.md`.

---

## Part 8 — Span-Level Text Model Design Review (`feature_005_span_level_text_model`)

### Background

**bug_005 — Footnote/Endnote Detection.** Auditing why footnote detection failed on the Brinkman PDF (0 of 3 real footnotes detected) found that PyMuPDF correctly extracts the distinguishing signal for a footnote marker (smaller font size, `TEXT_FONT_SUPERSCRIPT` flag bit, raised baseline — confirmed via direct span dump) but `structure_detector.py` discards it the moment it collapses every PDF span into `TextBlock`'s single line-level `font_size`/`is_bold` scalar pair. Classified as span-level information loss, root-caused as an architectural limitation of `TextBlock`'s deliberate line-granularity (a Phase H design choice, not an oversight) — not a defect in `footnote_detector.py`'s own logic.

Filed as **bug_005** (symptom/bug ticket — Status: Open, Blocking: this feature's implementation) distinct from `feature_005_span_level_text_model` (the architecture-level fix this Part documents the design of). Affected features confirmed or evaluated, per category: footnotes, endnotes, superscripts, subscripts, equations, scientific notation, chemistry notation — see "What the design review found" and the per-category impact table referenced below for which of these the same root cause demonstrably reaches versus only plausibly reaches.

### What the design review found

A complete consumer inventory of `Document.blocks`/`TextBlock` (5 real production consumers: `footnote_detector.py`, `image_extractor.py`, `paragraph_grouper.py`, `validator.py`'s `PAGE_003`, `phase1_pipeline.py`'s dataset context) found that `heading_detector.py` is **not** a consumer at all — it already independently re-derives layout signal from PyMuPDF twice (including a font-name workaround built specifically for bug_002, Part 7 above, because `TextBlock` has no font-name field) — direct prior evidence that the pain this review addresses is real and recurring, not hypothetical. Separately, `TextBlock.is_bold` was found to have zero production consumers anywhere (only its own test reads it), and `TextBlock.font_size` has exactly one (`footnote_detector.py`'s size-drop heuristic) — both lowering the migration risk of any change to those fields.

### Decision: Option A (embed `spans: List[Span]` directly in `TextBlock`), not a parallel `Document.spans` list or a new pipeline stage

Three architectures were evaluated:

- **Option A (recommended):** additive `spans: List[Span]` field on `TextBlock`. Smallest real diff given Structure Detection's stage already charters "per-line layout signal" as its job; zero blast radius on existing consumers (every field they read today is untouched); avoids the "new pipeline stage" framing closest to violating "do not redesign architecture" — the same concern that weighed against bug_001's own Option C (Part 6 above).
- **Option B (parallel `Document.spans` list):** not unprecedented in this codebase (`Paragraph` uses exactly this shape) but a worse fit here specifically, since no consumer needs to query spans independently of their parent line, unlike paragraphs.
- **Option C (separate pipeline stage):** rejected — highest migration complexity, and the architecture closest to the project's standing "do not introduce unnecessary abstractions" rule.

A minimal `Span` model was designed preserving text, font name, font size, raw font flags (kept undecoded rather than pre-interpreted into named booleans, for forward compatibility), baseline position, and bbox.

### Status

**Design review complete. Not implemented — no code written, by explicit instruction.** A 4-step migration path was proposed (additive model → populate during the existing per-span loop → `footnote_detector.py` gains a second, superscript-flag-based marker-detection path → re-evaluate replacing `heading_detector.py`'s bug_002 workaround), each step gated on the full test suite passing unchanged before the next begins. Multi-column reconstruction and table reconstruction were explicitly determined to be able to proceed independently of this decision, on either timeline, regardless of which option is eventually chosen or whether `Span` is ever implemented at all — neither feature's consumer needs combine span-content data with cross-block column/table geometry. One real, unaddressed gap surfaced and left open: `Span` as designed only ever populates from `DIRECT_TEXT` pages — whether Docling/Surya OCR output exposes an equivalent signal is a separate, unscoped investigation. See `KNOWN_LIMITATIONS.md` and `PHASE_STATUS.md` (Phase K forward-reference).

---

## Part 9 — Front-Matter Semantic Extraction (`bug_006` / `feature_006_front_matter_extraction`)

### Background

A "Scholarly Article Semantics Audit" on the Brinkman benchmark PDF (2026-06-24) found that the document's title, author byline, and institutional affiliation had no detection treatment anywhere in the pipeline — not a heading (the font-size-rank/keyword signal in `heading_detector.py` doesn't model title-page semantics), not metadata, nothing. All three rendered as one undifferentiated run-on body paragraph in both generated Markdown and DOCX: "Learner-centred education reforms in India... Suzana Brinkmann Institute of Education, London, UK" with no structural distinction at all.

### Decision: a new, additive, isolated module — not an extension of `heading_detector.py`

`src/frontmatter/front_matter_extractor.py` + an additive `Document.front_matter: Optional[FrontMatter]` field (`src/models/front_matter.py`). Deliberately kept separate from `heading_detector.py` — no shared constants, no calls into it, no change to any of its classification tiers — consistent with this project's standing rule against coupling unrelated detection concerns (the same convention `footnote_detector.py`'s independently-defined `_NOTES_SECTION_PATTERN` already follows relative to `markdown_builder.py`'s near-identical pattern). It reads only `Document.blocks`, already persisted by Structure Detection (Phase H) — no new PyMuPDF re-open, no new dependency.

Algorithm (page 1 only, deterministic, rule-based, no AI — consistent with Part 3's "deterministic first, AI later" agreement): find a "masthead-zone boundary" within page 1's first 20 lines (first line matching `abstract`/`keywords`/`introduction`/`summary`); skip one optional short kicker line below the title threshold (e.g. Brinkman's "Article"); title = the contiguous run of lines ≥1.3× the document's dominant body font size; author = the contiguous run immediately after, strictly between body and title size, capped at 5 lines; affiliation = everything remaining in the already-bounded zone. Calibrated directly against Brinkman's real measured geometry (body=10.0pt, title=17.9pt, author=12.0pt, affiliation=9.0pt — wide margins between every tier). Any step finding nothing fails closed: `FrontMatter` stays entirely empty, the correct, expected outcome for a PDF with no title page (3 of the 4 benchmark PDFs have none).

A related one-line fix landed in the same change, found during the same audit: `"keywords"` was added to `heading_detector.py::_H2_KEYWORDS`, since a PDF's literal "Keywords" line was previously falling through undetected as a heading entirely (same symptom class — content silently absorbed into body text — different mechanism).

### Status

**Implemented and verified 2026-06-24.** Wired into `phase1_pipeline.py` Stage 3 (immediately after footnote detection); consumed by `markdown_builder.py` (renders title/byline/affiliation as a distinct block after page 1's H6 marker, suppresses the same source lines from body rendering) and `docx_generator.py` (styled title/byline/affiliation paragraphs). 18 tests in `tests/test_front_matter_extractor.py`, including `TestRealBrinkmanPdf` against the real regression PDF.

**Process gap, found and corrected 2026-06-25:** despite being fully implemented and tested, this work was never assigned a ticket number and never recorded in `PROJECT_SAVE_STATE.md`, `TASKS.md`, `PHASE_STATUS.md`, or memory — a deviation from this project's own established convention (every other fix in `PROJECT_SAVE_STATE.md` §6 has a ticket). A routine status/recall check on 2026-06-25 found the gap and retroactively assigned `bug_006` (the symptom ticket) / `feature_006_front_matter_extraction` (the architecture-level fix), mirroring the existing `bug_005`/`feature_005_span_level_text_model` pairing exactly. No code was changed during this recording pass — see `PROJECT_SAVE_STATE.md` §6/§7 and `PHASE_STATUS.md` "Phase M" for the full technical record.

---

## Part 10 — Heading Detection Unpack Regression (`bug_007`)

### Background

While verifying test counts during the `bug_006` recording pass (2026-06-25), the fast test subset returned **250 failed, 620 passed** — sharply contradicting every prior figure on record ("588 passing, 0 failed"). Tracing one failure (`tests/test_validation.py::TestXmlInvalidCharacters::test_message_discloses_what_was_removed`) found the cause immediately: `ValueError: too many values to unpack (expected 2)` at `src/headings/heading_detector.py:211`.

### Root cause

`_build_layout_index()` (`heading_detector.py:441-512`) had been changed to return a **3-tuple** (`index, body_profile, bbox_index`), with a docstring explicitly naming the reason: scaffolding for an in-progress, **never-implemented** "Wrapped Heading Continuation Repair" feature, whose intended consumer, `_try_absorb_continuations()`, does not exist anywhere in the codebase (confirmed by grep — zero matches outside that one docstring comment). The function's single call site, `detect_headings()` line 211, was never updated to match and still unpacked exactly 2 values — an unconditional, 100%-reproducible crash on every call, regardless of input (the function returns a 3-tuple on both its real-PDF path and its PDF-not-found fallback path, so no input could avoid the crash).

Because `detect_headings()` is Stage 5/8 of `phase1_pipeline.py`, and that stage's `try/except` catches the exception and marks the document `ProcessingStatus.FAILED` rather than crashing the process, this was not a loud server crash — it was a **silent, total failure of heading detection on every document processed through the real API**, not just a test artifact. No one had re-run the test suite since this half-finished edit landed, violating this project's own Part 3 agreement ("every phase preserves previous behavior... enforced by running the full test suite before any phase is considered done").

### Decision: restore the working 2-value contract at the call site, do not implement the unfinished feature

`detect_headings()` now unpacks all 3 returned values, discarding the unused third (`_unused_bbox_index`) with an inline comment explaining why it's unused and pointing back to this entry. **Not** chosen: implementing `_try_absorb_continuations()` to actually consume the third value — that would mean inventing a new feature's behavior under an "emergency bug fix" banner, which this project's standing rule against unauthorized architecture/scope changes (`CLAUDE_INSTRUCTIONS.md`, Part 13) does not permit without its own checklist-impact analysis and sign-off. If "Wrapped Heading Continuation Repair" is wanted, it should be picked up as its own scoped feature, starting from the already-present (and still entirely valid) `bbox_index` plumbing.

### Status

**Fixed 2026-06-25.** One-line change at `heading_detector.py:211`. No regression test was added — `tests/test_headings.py::TestDetectHeadingsReturnValue::test_returns_same_document_instance` already calls `detect_headings()` unconditionally and would have caught this immediately had the suite been re-run after the breaking edit; the gap was process (not re-running tests before considering work done), not test coverage. Full fast-subset suite re-verified after the fix — see `PROJECT_SAVE_STATE.md` §6 (`bug_007`) for the before/after counts.

---

## Part 11 — Benchmark Corpus Expansion

### Background

While verifying test counts during the `bug_006`/`bug_007` recording pass (2026-06-25), fixing `bug_007` dropped the fast-subset failure count from 250 to 16, but didn't reach zero. Tracing the remaining 16 found a single, distinct root cause, unrelated to `bug_007`: `samples/benchmark/pdfs/` had been silently expanded from the documented 4 PDFs to 10 on 2026-06-24 (6 new files, all dated that day) — `1. Nature of Enquiry.pdf`, `1.Aims of Education and the teacher_Dhankar_PhilPers (1).pdf`, `2. Social research strategies Bryman.pdf`, `2.FolkPedagogy_Bruner_PsychDimensions_New.pdf`, `3. sockett_profession.pdf`, and a duplicate copy of the `bug_005` regression PDF (`7.brinkman-...pdf`, which already lives in `samples/regressions/bug_005_footnote_endnote_information_loss/`). This directly contradicted the standing convention (memory `project_benchmark_corpus_convention`) that this folder is ground-truth-only and must stay intact, and was never recorded anywhere.

Three independent tests/test classes had been calibrated against the original 4-PDF set's specific, confirmed-clean properties and broke once the corpus grew:
1. `tests/test_validation.py::TestReadingOrderAnomaliesWithRealPdfs` asserted zero `PAGE_003` (reading-order anomaly) issues across "all real benchmark PDFs" — true for the original 4 (all single-column), false for 4 of the 6 additions (genuinely multi-column real documents).
2. `tests/test_pipeline.py::TestStructureDetectionDoesNotChangeExistingOutputs` compared a pipeline run with Structure Detection enabled against one with it forced to a no-op, asserting identical validation issues — which surfaced a latent, pre-existing test-design gap: `PAGE_003` is a real, deliberate consumer of `document.blocks` (Structure Detection's own output), so disabling Structure Detection always suppresses `PAGE_003` issues specifically, regardless of corpus. The original 4-PDF set never exposed this because all 4 have zero `PAGE_003` issues either way; multi-column PDFs entering the corpus finally exposed it.
3. `tests/test_footnote_detector.py::TestBenchmarkDocuments` asserted zero real footnotes/endnotes across the whole corpus — true originally, false for Brinkman (which has 3 real, confirmed endnotes — the exact subject of `bug_005`) and for two more additions (`1. Nature of Enquiry.pdf`, `1.Aims of Education...`) which contain real, sequentially-numbered markers that the span signal correctly flags but that never link to a `Footnote` (a separate, already-documented limitation, not a new gap).
4. `tests/test_images.py` used `sorted(glob("*.pdf"))[0]` as shorthand for "a PDF known to have multiple images" — previously resolved to the corpus's one scanned/image-heavy PDF by sort-order coincidence; the new alphabetically-earlier filenames (`1.`, `2.`, `3.`) silently redirected it to a 0-image PDF instead.

Direct re-verification confirmed **none of these are pipeline regressions** — the pipeline's actual output for every affected PDF is internally correct; only the tests' calibration against an outdated, narrower ground truth was wrong.

### Decision: keep the expanded corpus, update the tests to match it

Presented as a 3-way choice (revert the corpus / keep it and fix the tests / record only, decide later). **Chosen: keep the larger corpus** (more real-world PDF coverage is a genuine improvement) **and update the affected tests** rather than reverting the new PDFs or leaving the regression unaddressed:

1. `test_validation.py`: replaced the blanket `issues == []` assertion with a per-PDF expected-count dict (`_EXPECTED_PAGE_003_COUNT`), pinning the real, directly-confirmed current count for every one of the 10 PDFs — preserving the test's actual purpose (regression guard against future `PAGE_003` behavior changes) rather than loosening it into "anomalies are fine everywhere."
2. `test_pipeline.py`: excluded `PAGE_003` specifically from the with/without comparison, with an explanatory comment recording why (`PAGE_003` is a deliberate consumer of the exact signal the "without" run forces empty) — the comparison still holds for every other rule ID.
3. `test_footnote_detector.py`: split the corpus into "confirmed zero footnotes" (the original guard, still enforced) versus two explicitly-named exclusion sets — PDFs with real, body-linked footnotes (Brinkman) and PDFs with real, unlinked marker candidates (`Nature of Enquiry`, `Aims of Education`) — skipped with an explanatory reason rather than silently passing.
4. `test_images.py`: replaced `SAMPLE_PDFS[0]` with an explicitly-named constant (`_PDF_WITH_MULTIPLE_IMAGES`, pointing at `4. O Leary_...pdf` by filename) so future corpus growth can't silently redirect it again.

### Status

**Fixed 2026-06-25, in 3 iterations.** No source code under `src/` was changed for this finding — test-only fixes, consistent with the verified fact that the pipeline's real behavior was already correct. The first pass (excluding only `PAGE_003` from the with/without comparison) left 2 PDFs still failing; tracing those found `DOC_004` has the identical dependency on Structure Detection actually running (it's one of several Layer-1 sanitization producers); a third pass found `NOTE_001`/`NOTE_002` have the same dependency via `footnote_detector.py`'s own explicit empty-blocks no-op. Each addition to the exclusion set was made only after being confirmed against a real, reproduced failing test - not guessed or batched preemptively. Final verified result: full fast-subset suite, **865 passed, 7 skipped, 5 deselected, 0 failed**. See `PROJECT_SAVE_STATE.md` §6 for the full per-PDF count table.

---

## Part 12 — Wrapped Heading Continuation Repair (`feature_007_wrapped_heading_continuation_repair`)

### Background

The benchmark heading-fidelity audit identified 10 confirmed wrapped-heading defects: a logical heading spanning multiple PDF lines (e.g. `"1.16  Subjectivity and objectivity in"` + `"educational research"`) was being detected as two separate `Heading` objects (H3 + H2) instead of one correctly-leveled heading. 9 instances in `1. Nature of Enquiry.pdf`, 1 in `1.Aims of Education...pdf` (the document title itself). This is the same not-yet-built feature `bug_007` (Part 10) found already named in a stale code comment and an orphaned 3-tuple return from `_build_layout_index()`.

### Audit-first process

Per explicit instruction, no code was written until a full audit was complete: independent re-derivation of every benchmark gap_ratio cited in the task brief (not trusted at face value), a corpus-wide scan confirming 7 of 10 PDFs have zero bold-adjacent line pairs at all (zero regression risk for those), and discovery that the `"Chapter 3);"` line (page 22, Nature of Enquiry) is a real, pre-existing false-positive trap — already mis-classified as H2 by an unrelated tier, and not bold, making "anchor must be bold" the load-bearing safety gate. Before implementing the riskier cross-block fallback specifically, a second, exhaustive (not sampled) corpus-wide sweep for every same-font/same-size/same-bold/different-block/small-gap line pair was run, finding exactly 8 candidates corpus-wide, 1 real continuation (Aims) and 7 false candidates (running-header + page-number pairs in `FolkPedagogy`), with a 0.54 margin between them — confirming the proposed `-0.20` to `+0.45` window with real evidence, not assumption. Full design document: `samples/regressions/feature_007_wrapped_heading_continuation_repair/notes_md/wrapped_heading_continuation_repair_audit.md`.

### Decision: implement as designed, with 3 final parameter choices

1. **Absorption cap = 4 lines** (not the originally-proposed 5) — sufficient for the corpus's longest confirmed chain.
2. **Local, heading-only soft-hyphen handling** (`_join_with_local_hyphen_repair()`) rather than extending the shared `paragraph_grouper.py` helper — keeps this feature's behavior decoupled from paragraph-grouping, consistent with this project's established "small, independently-defined per-module helpers over cross-module coupling" convention.
3. **Sockett-specific corruption side effects accepted, not suppressed** — `3. sockett_profession.pdf`'s decorative cover-page title fragments merge further than the audit predicted (full merge, not partial), because those fragments are same-block and the same-block gate bypasses the gap_ratio check entirely by design. Confirmed not a benchmark regression (no pinned test asserts heading content/count for this PDF).

### Implementation

`src/headings/heading_detector.py`: extended `_build_layout_index()`'s `bbox_index` to carry block index; restructured `detect_headings()`'s per-page loop to an index-based `while` loop so absorbed lines can be skipped; added `_absorb_continuations()`, `_matches_new_heading_pattern()`, `_is_confirmed_continuation()`, `_join_with_local_hyphen_repair()`.

### Status

**Implemented and verified 2026-06-25.** Document-by-document benchmark re-run (true before/after comparison via monkeypatch, not prediction): `1. Nature of Enquiry.pdf` 48→35 headings (all 9 wraps merged correctly, including 4-line and 3-line chains, soft-hyphen repair clean, `"Chapter 3);"` trap still correctly un-absorbed); `1.Aims of Education...pdf` 3→2 (title fully merged, byline correctly excluded); `3. sockett_profession.pdf` 21→15 (beneficial side effect, larger than predicted, confirmed harmless); all other 7 benchmark PDFs unchanged (0 delta), confirming the calibration window correctly excludes the 6 running-header/page-number false candidates. Full fast-subset suite re-verified: **865 passed, 7 skipped, 5 deselected, 0 failed** — identical to the pre-implementation baseline, zero regressions.

---

## Part 13 — Front-Matter Generalization (`feature_008_front_matter_generalization`)

### Background

`feature_006`'s front-matter extraction worked for Brinkman only — Aims of Education, FolkPedagogy_Bruner, Calderhead, and Fullan&Hargreaves all have real title+author on page 1 but extracted nothing, because `front_matter_extractor.py` required a literal Abstract/Keywords/Introduction/Summary line to bound the masthead zone (journal-article shape only) and used one global 1.3x-body-size threshold to separate title from author, which only works when the document's author line happens to sit below that threshold.

### Decision: generalize boundary/tier detection, add two mandatory affiliation guards

Audited in 3 passes (design, then a focused affiliation-validation pass, then a deterministic-signal investigation) before any code changed — full record in `samples/regressions/feature_008_front_matter_generalization/notes_md/front_matter_generalization_audit.md`. Implemented 2026-06-25: boundary detection falls back to a font-size transition when no keyword section exists; kicker-skip compares against the next line's size instead of the global threshold; title/author runs stop at the first font-size change. The generalization itself introduced 2 real false-positive affiliations (Aims' 55.5pt epigraph, Bruner's "HARVARD UNIVERSITY PRESS" publisher imprint), fixed with two corpus-calibrated guards: reject any affiliation candidate at/above the title's own font size; reject the whole remainder if its first line's vertical gap from the author exceeds a calibrated `gap_ratio` threshold (2.0, vs. real corpus values 0.169 genuine / 8.404 false-positive).

### Status

**Implemented and verified 2026-06-25.** Mid-implementation, also caught and fixed an unscoped regression (`sockett_profession.pdf`'s lone OCR glyph passing the title gate) using a guard already designed earlier in the same audit — stopped and reported before silently adding it, per explicit instruction. Aims/Bruner/Calderhead/Fullan&Hargreaves all now correctly extract title+author with no false-positive affiliation; Brinkman unchanged byte-for-byte. Full fast-subset suite: **871 passed, 7 skipped, 5 deselected, 0 failed**.

---

## Part 14 — Printed Page Number Preservation (`feature_009_printed_page_number_preservation`)

### Background

The H6 page marker (`###### Page N`) always showed the PDF's physical page position, not the number actually printed in the book — e.g. Nature of Enquiry's physical page 1 (a mid-book excerpt) showed "Page 1" instead of the book's real "Page 3". This directly violates `docs/PAGE_RULES.md`'s explicit "Page numbers themselves should be preserved" requirement. No PDF in the benchmark corpus has usable `/PageLabels` metadata (the PDF-spec mechanism for this), so any fix has to read the number actually printed in each page's margin text.

### Decision: per-page margin scan, fold into the existing Structure Detection pass

Audited first (full record: `samples/regressions/feature_009_printed_page_number_preservation/notes_md/printed_page_number_audit.md`) — benchmark evidence showed printed-number detection cannot be a simple per-document offset (`FolkPedagogy_Bruner.pdf` splices non-contiguous chapters, so its printed numbers jump 56→198 across 12 physical pages), position varies within a single document (Calderhead/Fullan&Hargreaves both place the number bottom-center on a chapter-opening page, then alternating top-left/top-right afterward), and some pages are genuinely ambiguous (`sockett_profession.pdf` has duplicate/conflicting candidates on individual pages).

Implemented 2026-06-25 per the audit's own recommendations on the 3 items left open for sign-off: new additive `Page.printed_label: Optional[str]`, populated by `structure_detector.py`'s existing per-page scan (no second PDF read) — a candidate is a short, isolated, purely numeric-or-roman-numeral line in the top or bottom 12% margin at any horizontal position; detected **per page, not per document**; falls back to physical numbering whenever zero or more than one candidate is found (the smallest deterministic guard, resolving sockett's ambiguity without guessing); roman numerals preserved exactly as printed (no conversion). `heading_detector.py`/`markdown_builder.py`'s H6 marker generation now prefer this label when present.

### Status

**Implemented and verified 2026-06-25.** Verified against all 10 benchmark PDFs, byte-for-byte matching the audit's evidence, including the hardest cases (Bruner's non-constant offset preserved correctly per-page; sockett's roman numerals extracted and its ambiguous pages correctly rejected). Surfaced 2 legitimate (not regression) gaps in `tests/test_pipeline.py::TestStructureDetectionDoesNotChangeExistingOutputs` — the same test class `bug_007`'s corpus-expansion fix (Part 11) previously had to extend: its exact heading-equality assertion had no exception for H6 marker text now legitimately differing based on whether `printed_label` was populated (fixed by excluding page-marker text from that one comparison); `HEADING_004` (duplicate-heading detection, explicitly scoped to include page markers) can now legitimately fire only in the "with" run, since two different physical pages can share `printed_label` text in a way physical `page_number` never could — added to the test's existing rule-exclusion set alongside `PAGE_003`/`DOC_004`/`NOTE_001`/`NOTE_002`. Both fixes are test-only. Full fast-subset suite: **871 passed, 7 skipped, 5 deselected, 0 failed** — identical to the pre-feature_009 baseline.

---

## Part 15 — Paragraph Overlap Guard Calibration Repair (`feature_010_overlap_guard_calibration`)

### Background

A multi-column reading-order audit (`samples/regressions/audit_multicolumn_reading_order/notes_md/multicolumn_reading_order_audit.md`) found that the corpus's only genuinely multi-column documents already render in correct reading order, but Nature of Enquiry's rendered Markdown was inflated 6.8× (2,731 lines vs. 399 expected) — root-caused, in a dedicated follow-up audit (`.../notes_md/noe_paragraph_fragmentation_audit.md`), to `src/structure/paragraph_grouper.py::_starts_new_paragraph()`'s multi-column safety guard: `if line.bbox.y0 < previous.bbox.y1: return True` treated *any* bbox overlap, however small, as proof of a column boundary. For Nature of Enquiry's PDF producer (`iLovePDF`), ordinary single-spaced body text has a ~1.0-1.6pt bbox ascender/descender overlap on virtually every line transition — a font-metric artifact, not a layout signal — so the guard fired on 2,595 of 2,838 evaluated line pairs, 2,324 of them (89.6%) confirmed false positives against `expected_md`.

### Decision: magnitude floor on the existing guard, not a new signal

Audited first, then implemented exactly as audited (no scope changes): a calibrated minimum-overlap-magnitude constant, `_OVERLAP_GUARD_MIN_PT = 4.0`, added to `src/structure/paragraph_grouper.py`. The guard now reads `if line.bbox.y0 < previous.bbox.y1 - _OVERLAP_GUARD_MIN_PT: return True`. Calibration evidence (both PDFs measured directly, not estimated): false-positive overlaps cluster at ≤2.5pt in both Nature of Enquiry (iLovePDF) and the Brinkman regression PDF (Adobe LiveCycle PDFG ES); the smallest confirmed genuine break measures 5.02pt (Nature of Enquiry column switch) and 8.97pt (Brinkman table-cell-to-table-cell transition). 4.0pt sits with margin on both sides. No other paragraph-boundary rule (indent, cross-block gap, same-block gap, footnote/heading logic) was touched, per the audit's explicit scope.

### Status

**Implemented and verified 2026-06-25.**

* Nature of Enquiry: total paragraphs from `group_into_paragraphs` across all pages dropped from 2,702 to 311 (88.5% reduction); rendered Markdown content-line count dropped from 2,731 to 370 against an expected_md count of 399 (was 6.8× inflated, now 0.93× — under, not over). Spot-checked the audit's own worst example (`###### Page 10`'s opening paragraph) — now one flowing paragraph, matching `expected_md`.
* Brinkman (`bug_001`/`bug_005`'s regression PDF): only 3 of 127 overlap-guard firings are ≤4pt; all 3 confirmed false positives, now correctly merged, matching `expected_md` exactly (`development and interests'`, `crucial importance of taking into account`, `their learning. For example, in describing`). The other 124 firings (table cells at 8.97pt+, header/footer/masthead artifacts at 176-589pt) are bit-for-bit unaffected. Footnote/endnote marker substitution (`bug_005`) verified unaffected — all 3 endnote markers (`[^p16-1..3]`) substitute at identical positions before and after, since marker substitution operates on whole-line anchor text independent of paragraph grouping.
* feature_007 (wrapped heading continuation repair): heading detection runs in a separate module (`heading_detector.py`) upstream of paragraph grouping, and heading lines are removed from `markdown_builder.py`'s run before `group_into_paragraphs()` ever sees them. Verified directly: detected heading lists for Nature of Enquiry (63), Aims (6), and sockett (24) are byte-for-byte identical before/after the fix.
* sockett: 18 of 779 line pairs are affected (vs. 0 for Aims). Individually inspected (not assumed safe) — all 18 are either genuine same-line OCR-fragment continuations or single-character OCR noise tokens; none cross the page-spread gutter (verified by x-range), and all measure well below the smallest genuine break observed anywhere in the corpus (5.02pt).
* Added `tests/test_paragraph_grouper.py::TestOverlapGuardCalibration` (6 new tests): real-geometry false-positive fixtures from both Nature of Enquiry and Brinkman, a real-geometry genuine-column-switch fixture, a real-geometry genuine-table-cell-break fixture, and two synthetic boundary-value tests at the 4.0pt floor.
* Full fast-subset suite: see `PROJECT_SAVE_STATE.md` for the final pass count recorded at implementation time — identical to the pre-feature_010 baseline (871 passed, 7 skipped, 5 deselected, 0 failed) plus the 6 new tests, 0 failed.

---

---

## Part 16 — Configurable Page Numbering Policy

### Background

The existing H6 page-marker behavior had two problems. First, the output was `###### Page N` — the word "Page" appeared in the marker text, which violates the remediation standard and the benchmark expected output. Second, the behavior was a single fixed policy: every page always received a marker, using `Page.printed_label` if detected or `str(page_number)` as a synthetic fallback. Real remediation workflows require at least four distinct behaviors:

1. **Auto** — emit only genuinely detected printed page numbers; do not synthesize a number where none was printed.
2. **Manual Range** — restrict markers to a specific inclusive page window (e.g. body content only, excluding front matter).
3. **Manual Number Override** — override the numbering sequence entirely (common for scanned book extracts that begin mid-volume, e.g. pages 1–20 of a book whose physical pages are numbered 301–320).
4. **Disabled** — emit no markers at all.

### Decision: `PageNumberingPolicy` dataclass; `Optional` param with `None` default for backward compat

A new module, `src/config/page_numbering.py`, defines `PageNumberingMode` (enum) and `PageNumberingPolicy` (dataclass). A single method, `resolve_marker_text(page_number, printed_label) → Optional[str]`, is the sole decision point per page: it returns the text to use for the marker, or `None` to suppress the marker entirely.

The parameter is `Optional[PageNumberingPolicy] = None` on all three call sites: `detect_headings()`, `build_markdown()`, and `run_pipeline()`. When `None`, the original code path is followed exactly (every page gets a marker, `printed_label or str(page_number)`). This preserves all 877 pre-existing tests without modification — no existing caller was changed.

Alternatives considered:
- **Global config object / settings singleton** — rejected because RAWRS has no existing settings object and adding one for one feature would be premature. An optional parameter matches the existing `enable_ocr` pattern already in `run_pipeline()`.
- **Policy applied only at markdown rendering** — rejected because `document.headings` is a public model field. If `detect_headings()` unconditionally creates markers and the renderer silently drops some, the model and the output diverge. Both stages must agree.
- **`_find_page_marker()` as the only enforcement point** — rejected for the same reason. The fallback synthesis path in `build_markdown` would re-create suppressed markers if it weren't also policy-aware. Both `detect_headings` and `build_markdown` must receive the same policy.

`_find_page_marker()` was changed from `→ Heading` to `→ Optional[Heading]`. `_render_page()` skips the `_render_heading()` call when the return is `None` but still renders body content and the `<!-- pagebreak -->` marker — suppressing the H6 must never suppress page content.

### Known gap introduced

`PAGE_001` (`validator.py`) fires when a page has no H6 marker. It does not receive the active policy, so it fires as a false positive on pages whose markers were intentionally suppressed by `AUTO` or `DISABLED` mode. This is documented in `PAGE_RULES.md` and `KNOWN_LIMITATIONS.md`. Fix deferred — requires threading the policy into `validate_document()` and teaching `_check_page_markers()` to distinguish intentional absence from accidental omission.

### Status

**Implemented and verified 2026-06-28.** 41 new regression tests in `tests/test_page_numbering_policy.py` (all 4 modes, mixed documents, markdown rendering, legacy backward-compat path). All 877 pre-existing tests pass unchanged. Module signatures confirmed:

```
detect_headings(document, page_numbering_policy=None)
build_markdown(document, page_numbering_policy=None)
run_pipeline(pdf_path, output_root, enable_ocr, page_numbering_policy=None)
```

---

## Part 17 — Accessible Table Remediation Workspace (FEATURE_015)

### Background

RAWRS had no table representation, detection, rendering, or review workflow. The Phase 2 Engineering Blueprint listed table remediation as a P0 gap. The central question was detection strategy: PyMuPDF offers `find_tables()` with several strategies, but the benchmark corpus requires handling both bordered tables (detectable by vector line analysis) and borderless academic-journal tables (no automated strategy is reliable).

### Decision: `find_tables(strategy='lines')` + manual creation workspace

**`strategy='lines'`** (PyMuPDF default) was chosen as the only automated path. It reliably detects tables drawn with explicit PDF vector border lines — the common case in textbooks and government reports. It correctly returns 0 results on borderless academic-journal tables (confirmed: Brinkman's 8 tables → 0 auto-detected). This is the correct outcome, not a failure — those tables become manual-entry work.

**`strategy='text'`** was evaluated and rejected. On Brinkman page 5, it returns a single 40×8 table covering the entire page — it treats all spatially-aligned text columns as one giant grid, producing an unusable result for multi-column academic layouts.

**Docling `TableItem`** (Docling 2.104.0 has ML-based table detection) was considered and deferred. Docling is only called for `OCR_REQUIRED` pages in the current pipeline. Adding a second Docling call for table detection on `DIRECT_TEXT_EXTRACTION` pages is separable scope. Architecturally clean to add later against the existing `Table` model without changing the current API.

**Manual creation endpoint** (`POST /documents/{id}/tables`) bridges the borderless-table gap: reviewers define the table structure (caption, summary, header rows, cell content) via the Tables workspace. `TableStatus.MANUALLY_CREATED` distinguishes these from auto-detected tables in the UI.

Only `DIRECT_TEXT_EXTRACTION` pages are processed by `find_tables()`. OCR pages lack the vector line graphics the strategy depends on — attempting detection on them produces noise.

### Table suppression in Markdown rendering

When a table's bbox is known (auto-detected), `_table_suppressed_blocks()` in `markdown_builder.py` marks TextBlocks whose bbox overlaps the table's page-area bbox. These are skipped in `_render_page_body_with_paragraphs()`, preventing cell text from appearing twice (once as raw body lines and once as the pipe-table rendering). Suppression applies only to the paragraph path (born-digital pages); the line-by-line OCR path is unaffected since OCR pages never have PyMuPDF-detected tables.

### Accessibility design

Two fields per table follow established standards:
- `caption`: visible label. Renders as *italic* line above the pipe table in Markdown.
- `summary`: WCAG H73 prose description for complex tables — not a visible element; stored as `<!-- table-summary: ... -->` HTML comment in Markdown. DOCX generator currently ignores it (future work).

### Status

**Implemented and verified 2026-06-29.** 25 new regression tests (13 in `tests/test_table_extractor.py`, 12 in `tests/test_table_api.py`). Full fast-subset suite: **969 passed, 7 skipped, 5 deselected, 0 failed** — zero regressions.

---

## Part 18 — FEATURE_015.1: Semantic Accessible Table Remediation (Remaining 35%)

**Date: 2026-06-29**

### Merged cell span detection from PyMuPDF None-cell pattern

PyMuPDF's `find_tables()` returns `None` in `fitz_table.cells` for every cell position consumed by a merge. The anchor cell (top-left of the merged region) retains its full merged bbox. Prior to FEATURE_015.1, `_convert_table()` treated all Nones as empty text and left `col_span = row_span = 1`.

**Approach chosen:** `_detect_cell_spans()` — two-pass scan of the already-built `cell_bboxes` grid:
1. **Col-span pass** (row-major, left-to-right): consecutive Nones after a non-None anchor → col_span for that anchor.
2. **Row-span pass** (per anchor, scan downward): consecutive Nones in the same column not claimed by a col-span in their own row → row_span.

Span-consumed Nones are excluded from the confidence penalty. Anchor cell `col_span`/`row_span` flows into DOCX via existing `_apply_cell_merges()` — no change needed in DOCX generation.

**Alternative considered:** Geometric bbox comparison. Rejected: extra complexity without benefit given the None-pattern approach is reliable and already tested.

### Cell text editing via PATCH API

`TableReviewRequest` extended with `cells: Optional[List[CellUpdateRequest]]` where each entry is `{row_index, col_index, text}`. The PATCH handler builds a lookup dict and applies updates. Out-of-range coordinates are silently ignored.

**Alternative considered:** Separate `PUT /cells` sub-resource. Rejected: unnecessary complexity; consistent with existing header_row_indices partial-update pattern.

### Frontend cell editing (TableDetailPanel.tsx)

"Edit cells" toggle button switches all cells to `<input>` fields. Edits tracked in `Map<string, string>` keyed by `"rowIdx-colIdx"`. On Save, map serialised to `cells: CellUpdate[]` payload. Map cleared after successful save.

**Alternative considered:** Double-click per-cell. Rejected: conflicts with click-to-show-announcement UX.

### TABLE_006 — Markdown fidelity warning for merged cells

TABLE_006 (WARNING) fires when any cell has `col_span > 1` or `row_span > 1`. Alerts reviewers that the Markdown pipe table export cannot represent the merge (empty cells in consumed positions), while the DOCX export is correct.

**Why WARNING not ERROR:** DOCX export is correct; only Markdown is lossy. Markdown consumers are secondary to DOCX accessibility for RAWRS's use case.

### Test fixture breakage repair

`_make_job_with_table()` predated `PipelineResult` gaining `source_pdf_path`, `success`, `status` (required fields) and `Job` gaining `pdf_path` (required). This silently broke 14 tests masked by the fast-subset deselection. Fixed by passing the missing fields.

### Status

**Implemented and verified 2026-06-29.** 15 new tests in `tests/test_table_accessibility.py` (6 span detection, 4 TABLE_006, 5 cell edit API). 14 pre-existing fixture failures fixed. All 61 tests in that file pass.

---

---

## Part 19 — FEATURE_016: Accessibility Remediation Platform

**Date: 2026-06-29**

### Unified lifecycle model

Every reviewable object in RAWRS now follows: Detected → AI Analysis → Human Review → Accessibility Validation → Screen Reader Simulation → DOCX Verification → Approved. This lifecycle (implemented as `ObjectLifecycleStatus` in `src/models/lifecycle.py`) was adopted rather than per-object ad-hoc review state machines, because the accessibility workflows for headings, reading order, footnotes, images, tables, and metadata are structurally identical: all involve the same human decision pattern (inspect → approve/correct/reject), the same API shape (GET listing + PATCH single item), and the same frontend pattern (card + detail panel).

### Reading order correction (016B)

**Decision: correction applies directly to rendered output, not just to the model.**

The initial design only set `corrected_order` on `TextBlock` but left `_render_page_body_with_paragraphs()` reading `cleaned_text` (the original pre-correction text). This was intentional as a "metadata-only" phase. However, after implementation it was clear that if `corrected_order` is set and the reviewer approves, the generated Markdown and DOCX must reflect that correction — otherwise the feature is cosmetic only. `_render_page_body_with_paragraphs()` was extended to re-derive text from blocks sorted by `corrected_order` whenever any block on the page has one set, with `TestCorrectedOrderAffectsMarkdown` confirming the rendered output actually changes.

**Alternative considered:** storing the corrected full-page text string on `Page`. Rejected — it would decouple the review state from the source blocks, making future re-corrections harder and breaking the "always re-derivable from source" principle.

### Formatting fidelity (016G) — detection vs. re-emission

**Decision: detect formatting from existing `TextBlock.is_bold` + `font_flags`, not by re-parsing spans.**

`TextBlock` discards span-level data (font_flags per span) at construction time — only line-level `is_bold` and `font_flags` (the majority vote across spans) survive. For uniformly bold/italic paragraphs (the common case: chapter titles, headings rendered as body text, etc.) this is sufficient. For mixed inline formatting within a single paragraph (e.g., `"This is **bold** and this is *italic* in the same line"`) the block-level signals cannot distinguish — a paragraph where only some spans are bold will have `is_bold = False` (majority is not bold) and the inline formatting is silently lost.

This is an accepted limitation. The `feature_005_span_level_text_model` (a reviewed design, not yet implemented) is the architectural prerequisite for accurate inline formatting detection. 016G gives correct results for the common case (uniformly formatted paragraphs) and silent no-op for the uncommon case (mixed inline) — better than breaking, and better than nothing.

### IMAGE_005 replaces the confirmed KNOWN_LIMITATIONS gap

The `KNOWN_LIMITATIONS.md` file previously recorded: "Image extraction success does not guarantee DOCX embedding success — `IMAGE_004` (alt-text-pending) fires for an image even when it fails to embed." FEATURE_016E directly closes this gap: `Image.embedded_in_docx` tracks the DOCX embed result, `IMAGE_005` fires when it is `False`, and `_docx_compatible_picture_source()` converts CMYK JPEGs to RGB before embedding. The KNOWN_LIMITATIONS entry for this specific gap has been removed (see `KNOWN_LIMITATIONS.md` update).

### Status

**Implemented and verified 2026-06-29.** All 7 sub-features (016A–016G) complete. 91 tests in `tests/test_feature016_accessibility.py`, 6 IMAGE_005 tests in `tests/test_validation.py`. Suite confirmed clean at 0 failures. 016C full semantic list model (List/ListItem models, `list_detector.py`, list review API) is explicitly deferred — only DOCX rendering of lines already marked with bullet/number characters is implemented.

---

## Part 20 — Phase 2 Architecture Decisions (pre-implementation)

**Date: 2026-06-29**

### Context

RAWRS Phase 2 takes Mathpix MMD exports (`.mmd` files from Mathpix's OCR pipeline) as an alternative input path, producing the same Markdown + DOCX + validation outputs as Phase 1. The Phase 2 Engineering Blueprint (desktop file `RAWRS_Phase2_Engineering_Blueprint.md`, 2026-06-27) identified 5 pre-implementation decisions required before coding begins. All 5 are resolved here.

### Decision 1: DOCX supplement is required with degraded-mode fallback

The Mathpix DOCX companion (e.g. `1. Nature of Enquiry.docx` alongside the `.mmd`) carries H1/H2/H3 heading levels and H6 page markers derived from Mathpix's own layout analysis. The MMD itself has only `\section*{}` (flat, no levels) — without the DOCX supplement, all sections render at H2 with no depth. **Decision: treat the DOCX supplement as required input; when absent, emit all `\section*{}` as H2 and log a `HEADING_SUPPLEMENT_MISS` validation warning.** The degraded output is still usable (a reviewer can level headings manually via the Heading workspace), but the warning makes the deficit explicit.

### Decision 2: Phase 2 validation rules defined upfront

New rules required by Phase 2 (added to `docs/VALIDATION_RULES.md` when implemented):
- `MATH_001` (INFO): inline math span kept verbatim (unknown pattern; could not convert to readable form)
- `HEADING_SUPPLEMENT_MISS` (WARNING): DOCX supplement absent; all headings defaulted to H2
- `P2_META_001` (INFO): no `dc:language` (same as META_001, re-used if metadata is set from front matter)

### Decision 3: Input convention — Mathpix export directory as unit

A Mathpix export is a directory containing one `.mmd` (or `.mmd.mmd`) file, one `.docx` (or equivalent double-extension), and an optional `images/` subdirectory. The Phase 2 pipeline accepts a **directory path**, not individual file paths. The parser resolves the `.mmd` and `.docx` by the double-extension convention (strip one extension at a time to find the canonical base name). This mirrors how the samples are structured in `samples/mathpix/*/`.

### Decision 4: Phase2Document lives in src/models/, not in src/mathpix/

`src/models/phase2_document.py` — consistent with all other models. The Phase 2 pipeline imports from `src.models.phase2_document`, not from within `src.mathpix`. The `src/mathpix/` directory is for ingestion and transformation modules only; models follow the existing project convention of living in `src/models/`.

### Decision 5: F-018b (running header detection) ships with safe mode only

The ≥3-occurrence heuristic for running header detection (`\section*{same text}` appearing 3+ times) has benchmark evidence from only 1 of 10 documents (Bruner's "The Culture of Education"). In safe mode, detected running headers are **logged and flagged** (`is_running_header = True` on the `P2Heading`) but **not deleted from the output**. A reviewer must explicitly confirm deletion via a future workspace action. Auto-deletion is not implemented until the heuristic is validated on a larger corpus.

### Phase 2 implementation status (as of 2026-06-29)

**Skeleton started, pipeline not yet complete.** Files written:
- `src/models/phase2_document.py` — Phase2Document model (P2Document, P2Block, P2Heading, P2Table, P2Figure, P2Footnote, P2FrontMatter, P2BlockType)
- `src/mathpix/__init__.py` — package init
- `src/mathpix/latex_env_parser.py` — F-014 tokenizer (MMD → flat token list)
- `src/mathpix/math_transformer.py` — F-017 inline math transformer (footnote refs, statistical math)

Remaining work (F-011 pipeline skeleton, F-012 DOCX supplement reader, F-013 front matter normalizer, F-015a table transformer, F-016 figure transformer, F-018a heading normalizer, F-018b running header detector, F-019 heading hierarchy, F-020 DOCX metadata, renderers, validation, tests) is in queue for the next implementation session.

---

## Part 21 — FEATURE_015.3: Table Detection Hardening & Accessibility Readiness Platform

**Date: 2026-06-30**

### Background

Two detection gaps remained after FEATURE_015/015.1: (1) academic booktabs-style tables (three horizontal rules, no vertical lines) were invisible to VectorBorderDetector because `find_tables(strategy='lines')` requires a closed grid; (2) descriptor-heavy borderless tables (feature/comparison grids with text-only cells at consistent column positions) were missed or mis-detected because SpanAlignmentDetector's `MIN_TABLE_COLS=2` combined with its 45%-width span threshold produced too many false negatives for wide-cell tables.

### Decision: two new evidence-contributing detectors, not a strategy flag

**HorizontalRuleDetector** — reads `fitz_page.get_drawings()` for horizontal lines/thin-rectangles, clusters by y-coordinate, finds groups with compatible x-extent, checks for text between rules, builds a cell grid from the text content between rule pairs. Signal: `horizontal_rules` (weight 1.0), `three_line_pattern` (weight 0.9). No new dependency — PyMuPDF `get_drawings()` is already in scope.

**ColumnAlignmentDetector** — same span-clustering approach as SpanAlignmentDetector but with two tuned differences: `COL_MAX_SPAN_WIDTH_FRACTION=0.60` (vs 0.45) for wider cells, and `row_spacing_consistency` signal (coefficient-of-variation of row gaps, weight 0.6) replacing `numeric_content` as the primary differentiator — descriptor tables contain text, not numbers.

**Why new detectors, not a modified strategy flag:** Each detector contributes named `EvidenceSignal` objects traceable to the reviewer. A single combined detector would produce opaque scores. The evidence-fusion architecture already handles merging — adding a detector is safe and surgical.

**Why `COL_MAX_SPAN_WIDTH_FRACTION=0.60` in ColumnAlignmentDetector:** SpanAlignmentDetector's 0.45 limit correctly rejects body-text paragraphs whose lines happen to start at the same x. At 0.60 we accept feature-comparison-grid cells (which are genuinely wider) while still excluding full-width body text (which would always hit 1.0).

### Caption framework extraction (Part D)

Caption detection logic was already implemented as `src/tables/detectors/caption.py` — a generic utility designed from the start for all visual object types, not just tables. FEATURE_015.3 makes this explicit: `src/captions/caption_detector.py` is the canonical location; `src/tables/detectors/caption.py` becomes a thin re-export. No behavior change — existing imports in `vector_border.py` and `span_alignment.py` continue to work.

### ObjectLifecycleStatus on Heading and Footnote (Part E)

`Table` and `Image` already carried `ObjectLifecycleStatus`. Heading and Footnote were added for consistency — all four reviewable object types now share the same 6-state lifecycle. Field is additive (default `DETECTED`), backward-compatible with all existing tests.

### TABLE_007 validation rule (Part F)

Fires WARNING when a borderless-detector candidate (horizontal_rule or column_x_alignment signal present, vector_borders signal absent) has `col_count <= 1`. When a borderless detector fires but only finds one column, the table structure is likely underspecified — the reviewer should confirm whether column structure was correctly inferred. This is a reviewer guidance signal, not an error gate.

### Benchmark measurement script (Part B)

`scripts/benchmark_tables.py` runs the full pipeline across all manifest PDFs, computes binary (any-tables / no-tables) precision/recall/F1 and count-level precision/recall/F1 (for PDFs with `expected_table_count` in the manifest), and writes a machine-readable JSON report to `docs/benchmark_tables_report.json`. Does not modify any model or API — standalone measurement tool only.

### Status

**Implemented 2026-06-30.** All 7 parts complete:
- A: `HorizontalRuleDetector` (`src/tables/detectors/horizontal_rule.py`) + `ColumnAlignmentDetector` (`src/tables/detectors/column_alignment.py`); both registered in `_DETECTORS`
- B: `scripts/benchmark_tables.py` (precision/recall/F1/TP/FP/FN per PDF + JSON report)
- C: `ExportReadinessOut` + `GET /documents/{id}/export-readiness` pre-existed; `ChecklistPanel` tables group wired from live data via `ResultsDashboard` → `ChecklistPanel` prop threading
- D: `src/captions/caption_detector.py` + `src/captions/__init__.py`; `src/tables/detectors/caption.py` → thin re-export
- E: `lifecycle_status` added to `Heading` (`src/models/heading.py`) and `Footnote` (`src/models/footnote.py`)
- F: TABLE_007 in `src/validation/validator.py` + `docs/VALIDATION_RULES.md` + `docs/PHASE_STATUS.md`
- G: benchmark suite will run as Part G after implementation (run `python scripts/benchmark_tables.py`)

10 new tests in `tests/test_table_extractor.py`: 4 for HorizontalRuleDetector, 4 for ColumnAlignmentDetector, 1 for 4-detector registration, 1 for lifecycle on detected tables. Full suite re-run pending.

### Production Sign-Off Addendum (2026-06-30)

**Final verification exposed 4 defects fixed before sign-off:**

**1. HorizontalRuleDetector false positives (FolkPedagogy_Bruner — 11 FPs):**
Root cause: decorative iLovePDF section-separator rules produced text between the rules in an alternating column fill pattern (body paragraphs occupy left column OR right column, never simultaneously). The grid passed all existing gates (≥25% overall cell fill) because they alternated. Fix: `MIN_DUAL_COL_FILL_FRAC = 0.20` constant in `horizontal_rule.py` — for 2-column candidates, require ≥20% of rows to have BOTH columns simultaneously filled. Alternating fill = 0% dual fill → rejected. Brinkman TPs (where rows ARE fully populated) preserved. Implemented in `_build_candidate()` after the existing `cell_fill < MIN_CELL_FILL` check.

**2. Caption detector permissiveness (page numbers, journal headers accepted as captions):**
Two bugs found:
- `"350" == "350".upper()` is `True` — digits are their own "uppercase," so bare page numbers scored 0.8 in the all-caps tier. Fix: added early rejection gate `if not any(c.isalpha() for c in text): return 0.0` in `_score_candidate()`.
- After number rejection, journal running headers ("Policy Futures in Education 13(3)") scored 0.4 ("any short standalone line") and appeared in the 50pt search window. Real table captions (e.g. "Table 3. Teachers' beliefs...") are INSIDE the booktabs structure, not above the top rule. Fix: `_MIN_CAPTION_SCORE = 0.6` — the score-0.4 tier is permanently disabled. All detected Brinkman tables now correctly get `caption=None` → TABLE_001 fires → reviewer prompted.

**3. Brinkman expected_table_count correction (1 → 5):**
Benchmark manifest had `expected_table_count: 1` (set by a text-search heuristic on first run). Direct inspection of `expected_md` revealed 5 tables. Updated to 5. Count-level metrics: P=0.800, R=0.667, F1=0.727 (4/5 tables found, 1 FP on page 1). Binary metrics remain 1.0/1.0/1.0.

**4. Log typo — "horizontal_rule" vs "horizontal_rules":**
`table_extractor.py` log counted detections by checking `"horizontal_rule"` (singular) but the signal name is `"horizontal_rules"` (plural), causing all HorizontalRuleDetector detections to show as "0 horizontal-rule" even when tables were detected. Fixed to `"horizontal_rules"`. No functional impact — logging only.

**5. ChecklistPanel dashboard (Part F/H of production sign-off):**
- Tables group expanded from 1 binary item to 5: Table Detection, Tables Reviewed, Captions & Summaries, Structure & Headers, Detection Confidence. Each maps to a TABLE_00X rule bucket.
- `SummaryBar` denominator changed to exclude `na` and `not_impl` items — a document with no images was previously penalized in the completion percentage for unchecked image items.
- `ResultsDashboard` "Tables Detected" wired from `tables.length` (was hardcoded "Not Available"). "Page Labels" wired from `pages.filter(printed_label !== null).length`. "Front Matter Normalized" and "Printed Page Labels Preserved" wired from live data.
- "AI Alt Text" item changed from hardcoded `not_impl` to dynamic status tracking `alt_text_status === "ai_generated"` (FEATURE_012 was already implemented; the stale `not_impl` was incorrect).

**6. Caption test update:**
`test_short_line_score_04` in `test_feature015_2.py` expected `find_caption()` to return score 0.4 for "Mean scores". After `_MIN_CAPTION_SCORE = 0.6`, `find_caption()` correctly returns `(None, 0.0)`. Test updated: renamed to `test_short_line_rejected_below_min_score` (verifies find_caption returns None) + new `test_score_candidate_short_line_is_04` (directly verifies `_score_candidate("Mean scores") == 0.4` — the scoring function is unchanged, only the gate moved).

**Final suite: 1239 passed, 0 failed, 7 skipped (verified 2026-06-30).**

---

## Part 22 — Phase M-1: Mathpix Import Layer & Ownership Model

**Date: 2026-06-30**

### Background

RAWRS's Phase 1 pipeline extracts all information directly from the PDF (text, OCR, headings, footnotes, tables, front matter). This worked well for born-digital PDFs but had known gaps for scanned documents, complex math, and multi-column layouts. Mathpix provides a higher-quality extraction source (MMD format) for academic PDFs. The question was: how should RAWRS relate to Mathpix?

### Decision: RAWRS as accessibility remediation platform, not Mathpix editor

**RAWRS is NOT becoming a Mathpix editor.** RAWRS is an accessibility remediation platform that **imports** Mathpix extraction, **verifies** it against the original PDF, **enriches** it (alt text, accessibility review, validation), and produces a new accessibility-compliant document.

Nine ownership principles (all approved 2026-06-30):

1. **Mathpix MMD = import-only.** Ingested immediately into the RAWRS Document Model; the raw MMD form is discarded after `import_document()` returns. RAWRS never re-reads the MMD.
2. **RAWRS Document Model = canonical representation.** After import, the Document Model is the single source of truth. All downstream stages (Markdown, DOCX, validation, review workspaces) read only from it.
3. **Original PDF = evidence only.** Never edited. Used by the Verification Engine (Phases M-2/M-3) to cross-check Mathpix extraction against PDF geometry, font signals, and content.
4. **Never overwrite Mathpix silently.** Every Mathpix value that RAWRS proposes to change is recorded as a `CorrectionRecord` (original_value → proposed_value → status) and surfaced to the human reviewer. Mathpix extraction is never silently discarded.
5. **Verification Engine = a conceptual layer, not a new module.** The existing heading_detector, footnote_detector, and table_extractor modules run in "verify-only" mode in Phases M-2/M-3 — they add `CorrectionRecord`s for mismatches and create `source="rawrs_recovery"` objects for things Mathpix missed, but they never delete Mathpix objects.
6. **Document Model is canonical.** No parallel "Mathpix Document" sits alongside the RAWRS Document.
7. **RAWRS owns:** Verification, Recovery, Accessibility, Validation, Export. Mathpix owns: initial text/structure extraction.
8. **CorrectionRecord audit trail.** `src/models/correction.py` — `CorrectionStatus` enum (PROPOSED / AUTO_APPLIED / ACCEPTED / REJECTED / PENDING_REVIEW). `Document.corrections: List[CorrectionRecord]`. All proposed corrections flow through this model.
9. **ImportProvider Protocol.** `src/importers/base.py` — `@runtime_checkable` Protocol defining the provider interface. `MathpixImportProvider` is provider #1. Future providers (ABBYY, Azure Doc AI, Google Doc AI, Docling) implement the same interface.

### Why this architecture, not a "Mathpix side pipeline"

The alternative — a separate Phase 2 pipeline that took Mathpix output directly and produced a separate Document Model — would duplicate all accessibility logic (validation, review workspaces, DOCX generation). The chosen architecture reuses everything: after `import_document()` returns a populated RAWRS Document, all existing stages see no difference. This means FEATURE_012 (alt text), FEATURE_015 (tables), FEATURE_016 (review workspaces) work on Mathpix-imported documents with zero code changes.

### Why CorrectionRecord, not direct edit of Mathpix data

Mathpix extraction represents a human-paid, calibrated OCR result. Silently overwriting it when RAWRS disagrees destroys the basis for human review. With CorrectionRecord, a human reviewer can see: "Mathpix said H2, RAWRS thinks H3, here's the PDF evidence" — and accept or reject RAWRS's correction explicitly. This is the only way to build a trustworthy accessibility remediation workflow.

### Implementation: Phase M-1

See `PHASE_STATUS.md` Phase M-1 section for the full module inventory, model additions, and test count (44 tests, 1296 total). Backward compatibility: `mmd_path=None` (default) preserves all existing behavior exactly; all 1239 pre-M-1 tests pass unchanged.

### Pending: Phases M-2 through M-5

- **M-2:** `detect_headings()` verify-only mode — creates CROSS_001 CorrectionRecords for heading level mismatches; adds `source="rawrs_recovery"` for headings Mathpix missed.
- **M-3:** `detect_footnotes()` + `extract_tables()` recovery mode — creates CROSS_002/003 CorrectionRecords.
- **M-4:** `POST /api/documents/upload` accepts optional `mathpix_mmd` file field in multipart form.
- **M-5:** FEATURE_014 cross-source comparison panel — shows CorrectionRecord audit trail in the review workspace.

---

## Part 23 — Cross-Source Verification Engine, Evidence Fusion, and the FEATURE_017–020 Documentation Gap

**Date: 2026-07-08 (recording work actually done 2026-07-01 through 2026-07-07)**

### Background

Commit `f6c8f73` ("Add full Next.js frontend, Mathpix cross-source verification engine, and generalized SemanticObject/SemanticVerifier foundation") landed without any `PHASE_STATUS.md`/`DECISIONS_LOG.md` update. A follow-on session then built four more features (`FEATURE_018` Page Label Manager, `FEATURE_019` Evidence Fusion Engine, `FEATURE_020` source-order interleaving, an AI subsystem dependency-split redesign) on top of it and left them uncommitted, with the same gap. This is the same "implemented but unrecorded" failure mode already logged once in Part 9 (bug_006/feature_006). `docs/VALIDATION_RULES.md`, `docs/PAGE_RULES.md`, and `docs/KNOWN_LIMITATIONS.md` were kept current by whoever did the implementation work; this file and `PHASE_STATUS.md` were not. Resolved by a reconciliation pass: full fast-subset suite re-run (**1487 passed, 7 skipped, 5 deselected, 0 failed**), `next build` re-verified clean, then this entry plus the new `PHASE_STATUS.md` "Phase M-2" section written directly from the code and from the docs that were already accurate.

### Decision: generalize the verification engine instead of hand-writing a fourth PDF-comparison module

Phase M-1 (Part 22) described "Verification Engine" as a conceptual layer living inside existing detector modules, not a new one. That held for one asset type (figures). Once headings needed the same PDF-vs-Mathpix comparison, the alternative to a shared `src/verification/` package was three more copies of match/classify/apply logic, each with its own drift risk. `SemanticObject` (base model), `SemanticVerifier` (base class), `MultiSignalMatcher` (identity matching), and `decide_from_evidence()` (the KEEP/REPAIR/RECOVER/REMOVE decision) are the shared pieces every asset type's verifier now built on.

### Decision: promote table detection's evidence-fusion primitive to a shared engine layer

`EvidenceSignal`/`EvidenceBundle` (weighted-mean confidence, explainable per-signal breakdown) was built and proven inside `src/tables/` across four independent table detectors (FEATURE_015.2, Part 20 of this log). Rather than reinventing a similar structure for headings' multi-signal typography/whitespace/running-header evidence, the primitive was moved to `src/verification/evidence.py` and `src/tables/evidence.py` became a thin re-export — no behavior change for existing table-detector callers, and every verifier (`HeadingVerifier`, `ListVerifier`, `CalloutVerifier`) now fuses confidence the same way.

### Decision: `CalloutVerifier` gets an empty PDF matcher, not a skipped verifier

`Callout` (a boxed textbook aside — Case Study, Thinking Point, Key Ideas, Summary, Activity) has no independent PDF-side geometric detector yet (recognizing a bordered/shaded region from PDF drawing commands is a separate, larger future detector). Rather than special-casing "asset types with no second source" outside the framework, `CalloutVerifier.build_pdf_matcher()` returns an empty `MultiSignalMatcher([])` — the same documented default `SemanticVerifier` already uses for that case — so every `Callout` flows through `classify()` as `unmatched_a` and gets evaluated on label-pattern specificity and anchoring-heading integrity alone. This was treated as the proof case that the framework generalizes beyond "always have two sources to compare."

### Decision: page label precedence is override > sections > detection, not a single mutable field

`FEATURE_018`'s `Page.page_label` needed to support three real reviewer workflows at once — a one-off override, a bulk numbering scheme applied to a page range (front matter in roman numerals, body in arabic, restarting after an insert), and the original per-page detection — without any of them silently clobbering the others. `src/structure/page_label_resolver.py::resolve_page_labels()` encodes a strict precedence order (override always wins; else the first matching `PageLabelSection`; else the detected `printed_label`) computed fresh from `Document.page_label_sections` every time, rather than three separate mutable label fields that could drift out of sync with each other.

### Decision: split AI dependencies into `requirements-ai.txt`, add a startup resource preflight

FEATURE_012's original Qwen2.5-VL interface only discovered "not enough RAM/VRAM to load the model" on the first real inference request. Two problems: `torch`/`transformers` are large, GPU-toolchain-adjacent dependencies that shouldn't be mandatory for a platform whose core pipeline is deterministic and AI-optional, and hardware unsuitability should be knowable at backend startup, not mid-request. `requirements-ai.txt` makes the AI dependencies opt-in; `src/ai/providers/qwen.py::_check_resources()` runs synchronously at startup (fast — no model load) and `GET /api/ai/status` reports unavailability with a specific reason before any reviewer ever clicks "Generate AI Alt Text."

### Status

All five pieces (FEATURE_017 engine, FEATURE_018 page labels, FEATURE_019 evidence fusion, FEATURE_020 interleaving, AI subsystem redesign) plus the accompanying frontend `WorkspaceShell` redesign are implemented and test-covered as of this entry. See `PHASE_STATUS.md`'s "Phase M-2" section for the full file inventory. **Known gap carried forward, not fixed in this pass:** the new shell's theme-token system has not been back-ported to several pre-existing frontend panels (raw Tailwind `gray-*`/`blue-*`/`red-*` still hardcoded in `ChecklistPanel`, `ResultsDashboard`, `HeadingGrid`, `ImageGrid`, `TableGrid`, `PageLabelManagerPanel`, and others) — flagged for a follow-up theming sweep, not attempted here since it is a separate, unscoped, ~20-file change.

---

## How to add a new entry

Append a new `###` section under the relevant Part, dated, with: the decision, the reasoning ("why"), where it's implemented (file/module), and its current status. Do not delete or rewrite existing entries even if later superseded — add a new entry that references and supersedes the old one.
