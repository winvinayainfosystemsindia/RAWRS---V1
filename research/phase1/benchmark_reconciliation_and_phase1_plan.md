# Benchmark Reconciliation & Phase 1 Plan

**Note on inputs:** `CLAUDE.md` does not exist anywhere in this repo. `docs/CLAUDE_INSTRUCTIONS.md` is the equivalent file and has governed this engagement throughout — used here in its place. All 9 other required docs were re-read and are current as of this writing. No code was written or modified; this is a planning document only.

---

## 1. Benchmark vs Documentation Conflicts

| # | Conflict | Sources | Recommended Resolution |
|---|---|---|---|
| C1 | Page marker **format**: docs show `###### Page 1` (word "Page" + sequential PDF index); benchmark uses bare printed page number (`###### 80`). | `HEADING_RULES.md`, `PAGE_RULES.md` vs `expected_md` (Calderhead, Fullan&Hargreaves) | Amend both docs: marker text = source's own printed page number when detectable (header/footer text), else fall back to sequential PDF index. No model change — `Heading.text` is already free-form. |
| C2 | Page markers **entirely absent** in 2/4 benchmark files vs. docs' unconditional "every page" rule. | `PAGE_RULES.md` vs `expected_md` (O'Leary, Teaching-Ch.1) | Keep the documented unconditional rule — it's the safer, more accessible default. Treat the 2 missing-marker files as benchmark defects, not a spec change. |
| C3 | O'Leary's expected DOCX has **zero page breaks** despite 13 pages and its own MD having 12 break markers. | `PAGE_RULES.md` vs `expected_docx` (O'Leary) | Benchmark defect. Keep current `docx_generator.py` behavior (`page_count - 1` breaks), already validated against 3/4 files. |
| C4 | **Alt Text**: docs exclude Alt Text Generation from Phase 1; benchmark DOCX images carry rich, AI-quality descriptive alt text. | `PHASE1_SCOPE.md`, `RAWRS_PROJECT_CONTEXT.md` vs `expected_docx` (O'Leary, Teaching-Ch.1) | Do **not** add AI-generated alt text (violates "No AI"/frozen architecture). Add a cheap, rule-based **placeholder** alt-text string instead (closes "empty `descr`" gap without AI). Full descriptive alt text stays an explicit out-of-scope item pending a separate scope decision. |
| C5 | **Heading detection signal**: docs' only examples are numbered/keyword patterns; real benchmark headings are plain Title-Case phrases with no numbering. | `HEADING_RULES.md` vs `expected_md` (O'Leary, Teaching-Ch.1) | H1–H6 hierarchy/formatting semantics in the doc stay valid — only the *detection heuristic* changes (layout signal, not text pattern). Add a short "Detection Heuristics" addendum to `HEADING_RULES.md` documenting the new mechanism. |
| C6 | **"REFERENCES"** is a heading in one benchmark doc, plain text in another — same keyword, different ground truth. | *(internal benchmark inconsistency)* vs `HEADING_RULES.md` (silent on this case) | Pick one consistent rule for RAWRS: fixed small keyword list (References/Bibliography/Appendix/Acknowledgements) → always H2. Document the decision; accept it will only match 1 of the 2 conflicting files. |
| C7 | **Image over-extraction**: no doc defines a filtering/precision rule; benchmark shows 54→1 and 11→4 raw-vs-kept ratios. | `ARCHITECTURE.md`, `PHASE1_SCOPE.md` (Image Extraction responsibilities) vs `expected_docx` (Teaching-Ch.1, O'Leary) | Add an explicit filtering rule (discard images covering most of the page area) as a short addition to `OCR_RULES.md` or a new "Image Filtering" subsection. No model change. |
| C8 | **"Markdown as source of truth"**: the benchmark's own expected MD and expected DOCX for the *same* document structurally disagree with each other (title-block merging, zero image refs in MD vs. real images in DOCX). | `ARCHITECTURE.md` vs `expected_md` + `expected_docx` pairs | Keep `ARCHITECTURE.md`'s principle for RAWRS's *own* pipeline (DOCX generation must keep deriving strictly from RAWRS's own generated markdown — that's what makes it auditable). Treat the benchmark's internal MD/DOCX mismatch as evidence the benchmark pair wasn't produced this way, not a reason to weaken the principle. |
| C9 | **OCR_RULES.md** implies all PDFs go through Docling/Surya; benchmark shows 3/4 PDFs need zero OCR (clean native text layer). | `OCR_RULES.md`, `TECH_STACK.md` (PyMuPDF responsibilities) vs benchmark inventory | Add a "Direct Text Extraction" step ahead of OCR engines (detailed in §4). Update `TECH_STACK.md`'s PyMuPDF responsibility list to include text extraction for born-digital PDFs. |

---

## 2. Source of Truth Hierarchy

When sources conflict, precedence is, highest to lowest:

1. **Architecture/process constraints** (`docs/CLAUDE_INSTRUCTIONS.md`, `ARCHITECTURE.md`, `TECH_STACK.md`'s exclusion list) — absolute. Never overridden by a benchmark file. *Why:* these are stakeholder-imposed and frozen; a perfect benchmark match achieved by violating them (e.g., adding AI for alt text) is a worse outcome than an imperfect match that respects them.
2. **Behavioral rule docs** (`HEADING_RULES.md`, `PAGE_RULES.md`, `OCR_RULES.md`, `VALIDATION_RULES.md`, `PHASE1_SCOPE.md`) — the team's deliberated, written intent. Amendable when benchmark evidence proves a documented example wrong (C1, C5, C7, C9 above), but the fix is to **amend the doc**, not silently chase the benchmark in code. *Why:* a doc change is visible and reviewable; quietly coding to match a 4-sample benchmark risks baking in an authoring mistake as if it were policy — and §5 of the gap analysis proved the benchmark itself contains exactly such mistakes.
3. **Benchmark corpus** (PDFs + expected MD/DOCX) — empirical ground truth, but only where internally consistent across samples (3/4 or 4/4 agreement). Where it disagrees with itself (C2, C3, C6), it is not authoritative on that point until its owner resolves the inconsistency. *Why:* it's the best available proxy for real production acceptance, but it's 4 samples, not a spec.
4. **Existing code decisions** (e.g., `docx_generator.py`'s no-trailing-page-break rule) — lowest formal precedence, but don't casually override something that already independently matches the benchmark's majority pattern.

---

## 3. Phase 1 Re-Scope Recommendations

All recommendations stay inside existing modules — no new `src/` packages, no new frameworks/services/databases, no change to the canonical pipeline stage list.

- **OCR (`src/ocr/`):** implement as a hybrid — direct extraction first, OCR engines only when needed (§4). This is the first real implementation of this currently-empty module, not a redesign.
- **Image Extraction (`src/images/`):** add a filtering sub-step (§5) inside the existing module.
- **Heading Detection (`src/headings/`):** change the *signal* used (layout/font, not text-pattern-only); keep the same module, same `Heading` output contract (§6).
- **Figure Detection:** currently has no module of its own — implement as a small addition inside `src/images/image_extractor.py` (it already owns `Image.figure`), not a new package.
- **Alt-text placeholders:** generated at DOCX-generation time inside `src/docx/docx_generator.py`; no new model field, no AI.
- **Reading order / cross-page paragraph stitching** (gap analysis §4.2, Gap A): **explicitly deferred**. This requires rethinking how `Page`-level text and `Document`-level markers interact — an architecture-sensitive change needing its own sign-off, not bundled into this re-scope. Document as a known Phase 1 limitation.
- **Pipeline stage order:** `phase1_pipeline.py` currently runs Image Extraction before Heading Detection, and Validation after DOCX Generation — both deviate from the canonical order in `ARCHITECTURE.md`. Recommend realigning to the documented order (Validation before DOCX) as part of this roadmap (Phase G below), since nothing technical blocks it now.
- **Validation:** extend with Figure-level checks once Figure Detection exists — small, already in scope per `VALIDATION_RULES.md`.

---

## 4. OCR Strategy — Hybrid Extraction

**Decision function (per page, not per document):**
```
has_extractable_text(page) =
    page.get_text() stripped length > threshold (~20 chars)
    AND char density is plausible for the page size
```
- **True →** direct extraction: PyMuPDF `get_text()` straight into `Page.raw_text`/`cleaned_text`. Zero cost, deterministic, no new dependency (PyMuPDF already used). `Page.ocr_confidence = HIGH` (no recognition uncertainty).
- **False →** OCR path: **Docling (primary)** per `OCR_RULES.md`/`TECH_STACK.md` (already named, just not yet installed/wired — this fulfills an already-approved stack entry, not a new framework). **Surya (fallback)** if Docling fails or returns low confidence. `Page.ocr_confidence` set from the engine's reported score, bucketed HIGH/MEDIUM/LOW per `OCR_RULES.md`.
- **Mixed-document support:** the decision runs independently per page, so one PDF can have some pages direct-extracted and others OCR'd (e.g., a digital document with one scanned insert) — this is exactly what the existing page-level `ocr_confidence` field was designed for.
- Reading-order reconstruction, hyphenation cleanup, and header/footer removal (already documented OCR responsibilities) apply uniformly to text from **either** path — a direct-extraction page can still have a running header to strip, as the Calderhead PDF proves.

**Benchmark validation target:** 3/4 PDFs should resolve entirely via the direct path; only O'Leary should ever invoke Docling/Surya.

---

## 5. Image Strategy

| Step | Mechanism | Notes |
|---|---|---|
| Extraction | Unchanged — `page.get_images()` + `extract_image()` | Already correct |
| **Filtering** | Discard images whose bbox area ≥ ~85–90% of the page area (full-page scan/background, not a figure); dedupe repeated `xref` | Uses `get_images(full=True)`/bbox data PyMuPDF already returns — no new dependency. Target: bring 54→~1 and 11→~4 ratios in line with benchmark |
| **Caption handling** | Look for a `^(figure\|fig\.?)\s*\d+` text line near the image's bbox (above/below within a small pixel window); populate `Image.figure.label/number/caption` | Small addition inside `image_extractor.py`; no model change (`Figure` model already has these fields) |
| Caption placement | Render image + caption in the **same** DOCX paragraph (matches benchmark convention) instead of two separate paragraphs | Small `docx_generator.py` tweak |
| **Alt-text placeholders** | Deterministic template, e.g. `"{figure.label}: description pending human review"` or `"Image from page {page_number}"` if no figure detected | Set on the DOCX `docPr`/`descr` attribute at generation time; not stored on the model |
| Accessibility | The "pending human review" phrasing is itself the safeguard — tells both screen-reader users and human reviewers the description is provisional, consistent with "Human Review" as a core project principle | No AI, no new abstraction |

---

## 6. Heading Detection Strategy

Benchmark evidence: real headings are short, Title-Case, **unnumbered** phrases ("Teaching as an Art", "Boundaries", "Defining the Investigation"). The current numbering/keyword-only rules catch effectively none of them.

**New signal (primary):** font size + bold flag + line isolation, from PyMuPDF's `page.get_text("dict")` span data (already available, no new dependency).
- A line is a heading candidate if: it's an isolated line (not embedded in a longer paragraph block), its font size is larger than the page's dominant body-text size **or** it's bold while body text isn't, and it's short (e.g. <12 words).
- **Level assignment:** rank the distinct heading font sizes found *within that document* (largest unique size → H1, next → H2, ...) rather than fixed pt thresholds — the benchmark's own DOCX styles already prove absolute sizes vary document-to-document (gap analysis §4.9).

**Existing signal (kept, now secondary/override):** `Unit N`/`Chapter N`/`X.Y` numbering patterns — still fire when present (e.g., "Chapter 9", "3.1 Overview"), just no longer the *only* path to a heading.

**Existing H1-slot positional rule:** kept as a fallback tie-breaker only when font-size differentiation is inconclusive (e.g., a short, uniformly-styled document).

**Fixed exception list:** References/Bibliography/Appendix/Acknowledgements → always H2, independent of font signal (resolves C6), since these sections don't always get distinct formatting.

Same module, same `Heading` model and output contract — no architecture change.

---

## 7. Updated Phase 1 Roadmap

| Phase | Goal | Files Affected | Dependencies | Risks | Success Criteria |
|---|---|---|---|---|---|
| **A — Direct Text Extraction** | Populate `Page.raw_text`/`cleaned_text` for born-digital PDFs via PyMuPDF | `src/ocr/extractor.py` (new), `src/pipeline/phase1_pipeline.py` (wire in) | None — PyMuPDF already a dependency | Misclassifying a low-text-density real page as scanned | 3/4 benchmark PDFs produce non-empty `cleaned_text` on every page |
| **B — Image Filtering** | Cut over-extraction (54→~1, 11→~4) | `src/images/image_extractor.py` | None | Threshold too aggressive, drops a real small figure | Extracted image counts land within benchmark-observed bounds for the 2 image-bearing PDFs |
| **C — Layout-Based Heading Detection** | Detect real, unnumbered headings | `src/headings/heading_detector.py` | Phase A (needs real text + PyMuPDF span data) | False positives on bold/large body text (pull-quotes, emphasis) | Heading counts/levels approximate benchmark's H1/H2/H3 counts for O'Leary and Teaching-Ch.1 |
| **D — True OCR Engine (Docling/Surya)** | Handle fully-scanned PDFs | `src/ocr/extractor.py` | Phase A (shares the module; direct-extraction check gates this path) | New runtime dependency footprint/install size; engine latency | O'Leary produces non-empty `cleaned_text`; confidence levels populate per page |
| **E — Page Marker Format** | Bare printed-page-number markers | `src/headings/heading_detector.py`, `docs/HEADING_RULES.md`, `docs/PAGE_RULES.md` (amend) | Phase A/D (needs page text to find the printed number) | Printed number not detectable on some pages (footer cropped/missing) — needs a documented fallback to sequential index | Calderhead/Fullan&Hargreaves markers match expected bare-number format |
| **F — Figure Detection + Captions + Alt-Text Placeholders** | Close caption/accessibility gaps | `src/images/image_extractor.py`, `src/docx/docx_generator.py` | Phase B (filter first) | Caption-proximity heuristic misattributes a caption to the wrong image | O'Leary's 4 retained images get correct labels/captions; every retained image across all docs has non-empty placeholder alt text |
| **G — Validation Extensions + Pipeline Realignment** | Figure-level validation checks; reorder pipeline to canonical (Validation before DOCX) | `src/validation/validator.py`, `src/pipeline/phase1_pipeline.py` | Phase F | Reordering could surface validation issues that previously went unnoticed post-DOCX — expected, not a regression | Pipeline order matches `ARCHITECTURE.md`; new Figure checks (missing caption/numbering) fire correctly on O'Leary |

Each phase should re-run the full benchmark (all 4 PDFs) before moving to the next — no phase is "done" until it doesn't regress the others.

---

## 8. Test Strategy

| Category | What to test | Notes |
|---|---|---|
| **Benchmark tests** (`tests/test_benchmark.py`, new) | Run full pipeline against all 4 production PDFs; assert *directional* correctness (heading counts roughly match expected, image counts within filtered bounds, markers present) rather than byte-exact match | Skip exact-match assertions for the 3 known ground-truth inconsistencies (O'Leary page breaks/markers, REFERENCES treatment) — document why in the test |
| **OCR tests** | `has_extractable_text()` correctly classifies all 4 PDFs (3 direct, 1 OCR); confidence bucketing; a synthetic mixed PDF (1 scanned + 1 digital page) routes each page independently | Extends `tests/test_parser.py` patterns |
| **Image tests** | Filtering threshold (full-page image discarded, small content image kept) using the benchmark's own measured ratios as bounds; xref dedup | Extends `tests/test_images.py` |
| **Accessibility tests** | Every retained image has non-empty alt-text placeholder; heading styles still map to Word's built-in Heading 1–6 (Nav Pane); figure captions co-located with their image | New assertions in `tests/test_docx.py` |
| **DOCX tests** | Page-marker bare-number format; caption-same-paragraph structure; regression check that "no trailing page break" behavior is unchanged | Extends `tests/test_docx.py` |

No implementation code was written for this plan, per instructions.
