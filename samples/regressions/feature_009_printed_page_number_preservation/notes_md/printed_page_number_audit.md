# Printed Page Number Preservation — Audit & Design Review

**Status: AUDIT/DESIGN ONLY. No code changed.** Per explicit instruction ("Full audit first"), this is a benchmark audit and implementation design, gated for sign-off before any code is written.

Ticket: `feature_009_printed_page_number_preservation`.

User report: the generated H6 page markers (`###### Page 1`, `###### Page 2`, ...) show the PDF's physical page position, not the page number actually printed in the book. `docs/PAGE_RULES.md` ("Header and Footer Handling") explicitly requires: **"Page numbers themselves should be preserved."** This is a real, confirmed gap against a documented requirement, not just a cosmetic preference.

---

## 1. Root Cause

`src/models/page.py`'s `Page.page_number` is purely the 1-based physical position PyMuPDF enumerated the page at — it was never intended to represent the number printed on the page, and no field for that exists. Both places that generate the H6 marker use it directly and unconditionally:

- `src/headings/heading_detector.py:272` — `text=f"Page {page.page_number}"`
- `src/markdown/markdown_builder.py:381` — `text=f"Page {page_number}"`

No code anywhere extracts the literal printed page number. `heading_detector.py` has logic that *recognizes* a bare footer-digit line (e.g. `"3"`) specifically to **exclude** it from heading candidates (so it isn't misdetected as a heading) — but it discards the value rather than capturing it.

Checked first: PDF-level `/PageLabels` metadata (the spec-level mechanism for "printed numbering differs from physical position," e.g. roman numerals for a preface then arabic for the body). **None of the 10 benchmark PDFs have usable label data** — `fitz.Page.get_label()` returns either nothing or just the physical position back, for every PDF checked. This metadata path is not viable; any fix must read the number actually printed in the page's visible text.

---

## 2. Benchmark Evidence

Scanned every PDF's pages for short (≤6 char), purely-numeric-or-roman-numeral text lines positioned in the top or bottom 12% of the page (margin zones where running page numbers conventionally sit), recording physical page, value, vertical zone, and horizontal position.

| PDF | Sample findings | Printed vs. physical relationship |
|---|---|---|
| `1. Nature of Enquiry.pdf` | phys 1→"3", phys 2→"4", ... phys 28→"30" (BOTTOM, alternating RIGHT/LEFT) | **Constant offset of +2** — this excerpt starts mid-book; the book's real numbering continues unbroken. |
| `1.Aims of Education...pdf` | phys 1→"1", phys 2→"2", phys 3→"3", phys 4→"4" (BOTTOM) | Offset 0 — printed matches physical here, coincidentally. |
| `2. Social research strategies Bryman.pdf` | No candidates anywhere in the document (`text_len=0` on every sampled page) | **No usable signal at all** — scanned/no-text-layer PDF (confirmed previously in `feature_008`'s audit). |
| `2.FolkPedagogy_Bruner_PsychDimensions_New.pdf` | phys 2→"44", phys 3→"45", phys 4→"46", phys 5→"47" ... phys 14→"56", **phys 26→"198"** (TOP) | **Offset is NOT constant.** 56→198 across only 12 physical pages (12→142 jump) — this excerpt splices together non-contiguous chapters from the original book. A single global offset would be wrong for roughly half this document. |
| `3. sockett_profession.pdf` | phys 2→"2"(TOP); phys 3→"I"(BOTTOM, roman numeral); phys 4→"6" **and** "7" (TOP, two candidates on one page); phys 6→"10","11"(TOP) **and** "I","I" (BOTTOM, duplicated) | **Front matter in roman numerals, body in arabic** (the standard book convention) — but also genuinely ambiguous/duplicate candidates on single pages, the messiest document in the corpus (already flagged as OCR/structurally corrupted in `feature_007`/`feature_008`'s audits). |
| `4. O Leary_Developing the research questions.pdf` | No candidates anywhere (`text_len=0` throughout) | **No usable signal** — scanned/no-text-layer, same as Bryman. |
| `4.Teaching as a professional discipline-Chapter 1.pdf` | No numeric candidates found despite real text on most pages (e.g. phys 2 has 2734 chars) | **No usable signal found** for a different reason than Bryman/O'Leary — text exists, but nothing matching a page-number shape appears in the scanned margin zones on any sampled page. |
| `5.Teachingas a profession_Calderhead.pdf` | phys 1→"80"(BOTTOM CENTER, chapter-opening page), phys 2→"81"(TOP RIGHT), phys 3→"82"(TOP LEFT), phys 4→"83"(TOP RIGHT) | **Constant offset +79**, but **position changes within the same document**: bottom-center on the chapter's opening page, then alternating top-left/top-right (recto/verso) on continuing pages. |
| `6. Fullan&Hargreaves_teacherasaperson.pdf` | phys 1→"67"(BOTTOM CENTER), phys 2-6→"68".."72" (TOP, alternating LEFT/RIGHT) | **Constant offset +66**, identical chapter-opening-page convention as Calderhead. |
| `7.brinkman-...pdf` | phys 1→*(none)*, phys 2→"343"(TOP RIGHT), phys 3→"344"(TOP LEFT), phys 4→"345"(TOP RIGHT)... phys 18→"359" | **Constant offset +341** from page 2 onward; the title page (phys 1) prints no running number at all, a common journal convention. |

**Summary:** 5 of 10 PDFs have a reliable, extractable printed page number (Nature of Enquiry, Aims, Calderhead, Fullan&Hargreaves, Brinkman). 1 has it but with non-constant offset and ambiguity (sockett). 1 has it but a single global offset would be actively wrong partway through (FolkPedagogy_Bruner). 3 have no usable signal at all (Bryman, O'Leary, Teaching-as-Discipline).

---

## 3. Key Complications (why this is not a simple offset fix)

1. **Position is not fixed within a document.** Calderhead and Fullan&Hargreaves both place the number bottom-center on a chapter-opening page, then alternating top-left/top-right (recto/verso) on every page after. A design that only checks one fixed corner will miss real numbers.
2. **A single per-document offset is provably wrong for at least one real document.** FolkPedagogy_Bruner's printed numbers jump from 56 to 198 across just 12 physical pages — this PDF splices together non-adjacent chapters from the source book. Any "detect the offset once, apply it everywhere" design would silently mislabel roughly half of this document.
3. **Front matter can use roman numerals, body pages use arabic** (sockett) — the standard print convention. A correct design must recognize and preserve roman numerals as printed, not force everything through arabic-only parsing.
4. **Ambiguous/duplicate candidates exist on individual pages** (sockett: two numeric candidates on one page; a roman numeral duplicated twice on another) — this PDF is independently known to be OCR/structurally corrupted (flagged in both `feature_007` and `feature_008`'s audits). Any per-page extraction needs a way to decline (fall back to physical numbering) rather than guess when a page's evidence is ambiguous.
5. **No usable signal exists at all for 3 of 10 benchmark PDFs.** Two have no text layer whatsoever (architecturally identical to `feature_008`'s scanned-PDF limitation — no signal can be read until/unless OCR is involved, and OCR output carries no positional metadata for this either). One has real text but no detectable page-number shape on any sampled page — a case that must fall back to physical numbering rather than fail or guess.

---

## 4. Proposed Design (not yet implemented, for sign-off)

**Smallest viable approach, consistent with this project's established conventions** (`footnote_detector.py`'s/`front_matter_extractor.py`'s pattern of an additive, isolated detection step that falls back cleanly when its signal isn't confidently present):

1. New optional field, e.g. `Page.printed_label: Optional[str]` — additive, defaults to `None`, no existing `Page` construction site affected (mirrors `PageType`/`ExtractionMethod`'s existing optional-field precedent in the same model).
2. New, isolated extraction step (new module or function, not folded into `heading_detector.py`'s existing bare-numeral-exclusion logic, which serves a different purpose): for each page, look for a short, isolated numeric-or-roman-numeral text line in the top **or** bottom margin zone (not just one fixed corner), at **any** horizontal position (not just one side) — per the recto/verso evidence in §3.1.
3. **Per-page, not per-document.** No global offset is computed or assumed (per §3.2's Bruner evidence) — every page's label is read independently from that page's own text.
4. **A confidence/validation check, not a raw accept of anything numeral-shaped.** At minimum: reject a page with more than one candidate found (sockett's ambiguous cases) rather than guessing between them. A stronger version would also check the candidate against the immediately preceding confirmed page's label for a plausible (monotonically non-decreasing, or roman-then-arabic) sequence — not yet decided; see open decisions below.
5. **Fall back to the existing physical-number marker whenever no confident label is found** for a page — preserves exactly today's behavior for Bryman/O'Leary/Teaching-as-Discipline and any individual page elsewhere that simply doesn't have a confidently-detected number.
6. `heading_detector.py`/`markdown_builder.py`'s H6 marker generation changes from `f"Page {page.page_number}"` to prefer `page.printed_label` when present, falling back to `f"Page {page.page_number}"` otherwise — the smallest possible change to the two actual marker call sites.

No AI/ML, no new model redesign beyond one additive optional field, no change to `Document`/`Heading`.

---

## 5. Open Decisions Needed Before Implementation

1. **Roman numeral handling** — display exactly as printed (e.g. `Page i`, matching `docs/PAGE_RULES.md`'s "preserve" instruction literally), or convert to a normalized form? Recommend: preserve as printed, no conversion — simplest, and most literally satisfies the documented requirement.
2. **Validation strength** — is "reject if more than one candidate on a page" sufficient, or is a full monotonic-sequence cross-check against neighboring pages needed before trusting any single page's candidate? The former is simpler and already resolves sockett's specific ambiguity; the latter is more robust but a meaningfully larger piece of logic (effectively a small state machine carried across pages) and not yet validated against the corpus.
3. **Scope confirmation for the 3 architecturally-blocked PDFs** (Bryman, O'Leary, Teaching-as-Discipline) — confirm these are accepted as falling back to physical numbering indefinitely (no further fix possible without OCR providing positional digit data, an explicitly separate and larger effort), consistent with `feature_008`'s precedent for the same kind of limitation.
4. **Where the new field is populated** — as its own small pipeline stage (mirroring `front_matter_extractor.py`'s page-1-only, additive pattern but applied to every page), or folded into the existing `structure_detector.py` pass that already reads every page's `page.get_text("dict")` once. The latter avoids a second PDF re-open per page; needs a quick check of whether `structure_detector.py`'s existing block-extraction loop can cheaply also flag margin-zone candidates without complicating that module's current, narrow responsibility.

---

## 6. Implementation (2026-06-25)

**Status: IMPLEMENTED & VERIFIED.** Per "start implementation" with no further direction on the 3 still-open decisions, proceeded with this audit's own recommendations: roman numerals preserved as printed (item 1); the simpler "reject if ambiguous" validation (item 2, the smallest deterministic guard, consistent with this project's established preference); the 3 architecturally-blocked PDFs accepted as falling back to physical numbering (item 3); and folded directly into `structure_detector.py`'s existing per-page scan (item 4), confirmed cheap to add.

### 6.1 Changes

- `src/models/page.py` — added `Page.printed_label: Optional[str] = None`.
- `src/structure/structure_detector.py` — `_extract_page_blocks()` now also returns a detected `printed_label`, computed by new `_detect_printed_label()` from the same already-parsed `page_dict` (no second PDF read). A candidate is a short (≤6 char), purely numeric-or-roman-numeral, isolated line in the top or bottom 12% margin (`_MARGIN_ZONE_RATIO`), at any horizontal position. Exactly one candidate → used; zero or more than one → `None` (falls back to physical numbering). `detect_structure()` assigns this onto each `Page` directly.
- `src/headings/heading_detector.py` — the H6 marker now reads `page.printed_label or str(page.page_number)` instead of `page.page_number` unconditionally.
- `src/markdown/markdown_builder.py` — `_find_page_marker()`'s fallback-synthesis path (only reached if `heading_detector.py` failed to produce a marker at all) updated the same way; now takes the `Page` object instead of a bare `page_number` int so it can read `printed_label`.

### 6.2 Benchmark verification (real production code)

| PDF | Sample `printed_label` values | Matches audit evidence? |
|---|---|---|
| Nature of Enquiry | phys 1→'3', 2→'4', ... 28→'30' | Yes, exactly (+2 offset) |
| Aims of Education | phys 1→'1' ... 4→'4' | Yes, exactly |
| Bryman | all `None` | Yes (no text layer) |
| FolkPedagogy_Bruner | phys 1→`None`, 2→'44', ..., 14→'56', **26→'198'** | Yes, exactly — the non-constant-offset jump is preserved correctly because detection is per-page, not a computed global offset |
| sockett_profession | phys 1→`None`, 2→'2', **3→'I'**, 4→`None`, **5→'I'**, 6→`None` | Yes, exactly — roman numeral correctly read; ambiguous pages (page 4's two candidates, page 6's duplicate "I") correctly rejected rather than guessed |
| O'Leary | all `None` | Yes (no text layer) |
| Teaching-as-Discipline | all `None` | Yes (no detectable signal on any sampled page) |
| Calderhead | phys 1→'80' ... 4→'83' | Yes, exactly (+79 offset) |
| Fullan & Hargreaves | phys 1→'67' ... 6→'72' | Yes, exactly (+66 offset) |
| Brinkman | phys 1→`None`, 2→'343' ... 18→'359' | Yes, exactly (+341 offset; title page correctly has no number) |

End-to-end H6 marker text confirmed correct: Nature of Enquiry produces `'Page 3'` (physical page 1) instead of `'Page 1'`; sockett produces `'Page I'` for its roman-numeral pages and falls back to `'Page 4'`/`'Page 6'` (physical) for its ambiguous ones.

### 6.3 Test results

- Targeted (`tests/test_structure_detector.py`, `tests/test_headings.py`, `tests/test_markdown.py`, `tests/test_docx.py`): **227 passed, 2 skipped, 0 failed.**
- Full fast-subset suite (`pytest -m "not real_docling and not real_surya"`): see final entry appended after this run completes.

### 6.4 Known limitations (carried over from §5, now confirmed rather than anticipated)

- Bryman, O'Leary, and Teaching-as-Discipline fall back to physical page numbering with no further fix possible inside this design — no text-layer signal exists to read (same architectural boundary as `feature_008`'s scanned-PDF limitation).
- The "reject if ambiguous" guard is deliberately conservative: any page with two or more margin-zone numeric candidates falls back to physical numbering rather than attempting to pick the right one. A future, more robust version could cross-check against neighboring confirmed pages' sequence, but that wasn't needed to resolve any real corpus case found in this audit.
- A single isolated short word that happens to be entirely roman-numeral letters (e.g. the English word "I") could in principle be mistaken for a roman numeral if it lands alone in a margin zone - no real instance of this exists in the benchmark corpus, but it's a residual risk inherent to the pattern-only (not content-aware) detection design.

### 6.5 Test fallout found and fixed during verification

The full fast-subset suite surfaced 6 failures, all in `tests/test_pipeline.py::TestStructureDetectionDoesNotChangeExistingOutputs` (the same test class `bug_007`'s corpus-expansion fix previously had to extend — see `DECISIONS_LOG.md` Part 11). Two distinct, both legitimate (not regressions):

1. **H6 marker text comparison.** This test asserts `[h.model_dump() for h in ...]` equality between a real Structure Detection run and a stubbed no-op run. Since `printed_label` is only ever populated by Structure Detection actually running, the "with" run can show a real printed page number while "without" always falls back to physical numbering - a deliberate, by-design divergence the test's full-equality check had no exception for. Fixed by nulling the `text` field specifically for `is_page_marker=True` headings before comparing (every other field, and every content heading's text, is still compared exactly).
2. **`HEADING_004` (duplicate-heading detection).** `_check_duplicate_headings()` is explicitly scoped to include H6 page markers. Once `printed_label` can repeat across physical pages (sockett's pages 3 and 5 both print roman numeral "I" - confirmed real, not a detection error), "with" legitimately raises a `HEADING_004` warning that "without" can never produce, since physical `page_number` is always unique per page and "without" never has `printed_label` populated. Added `HEADING_004` to the test's existing `_EXCLUDED_RULE_IDS` set, with the same documented-exception reasoning already used for `PAGE_003`/`DOC_004`/`NOTE_001`/`NOTE_002`.

Both fixes are test-only; no source code under `src/` was changed for this finding. Full test class re-verified: 10 passed (all 10 benchmark PDFs).

### 6.6 Full fast-subset suite, final result

`pytest -m "not real_docling and not real_surya"`: **871 passed, 7 skipped, 5 deselected, 0 failed** (11m46s) — identical to the pre-feature_009 baseline (`feature_008`'s final count). Zero regressions anywhere else in the suite; the only fallout was the two documented, legitimate test-comparison gaps in §6.5, both fixed.
