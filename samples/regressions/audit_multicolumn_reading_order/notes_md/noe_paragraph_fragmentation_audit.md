# RAWRS Audit — Nature of Enquiry Paragraph Fragmentation

**Status: AUDIT ONLY. No production code was changed.** Follow-up to
`multicolumn_reading_order_audit.md` §3c, which found Nature of Enquiry
renders ~2,731 Markdown content lines vs. ~399 in `expected_md` (6.8×
inflation) and attributed it to `paragraph_grouper.py`'s multi-column
overlap guard. This document is the full evidence trail.

## Method

Ran `parse_pdf → extract_text → detect_structure` on
`samples/benchmark/pdfs/1. Nature of Enquiry.pdf`, then for every page
called the production `_merge_same_baseline_fragments()` (Bug 1 fix) and
walked every resulting adjacent line pair through the exact branch logic of
`_starts_new_paragraph()` (re-evaluating each of its three conditions
individually, not just its boolean return, so the *specific* rule
responsible for each split could be attributed). For ground truth, built a
token-level index of `expected_md` (lower-cased alnum tokens) and tested
whether each pair's joined text (tried both with the line-wrap hyphen kept,
matching the production `_join_with_hyphen_repair()` behavior, and with it
removed, since `expected_md` reflows genuine line-wrap hyphens but the
literal join does not — see Appendix) appears as a contiguous run in that
index. 2,838 adjacent line pairs were evaluated this way. The same method
was run against the Brinkman regression PDF (`bug_001`/`bug_005`'s subject)
for the regression check in §5.

## 1. Where fragmentation begins

First false-positive split (alphabetically/positionally first in the
document), physical page 1:

```
PREV: "planning and conduct of research as though one were"
CUR:  "reading a recipe for baking a cake. Nor is the planning"
prev: x0=53.53 x1=267.85 y0=300.36 y1=312.84   (source_block_index=3)
cur:  x0=53.53 x1=267.85 y0=311.36 y1=323.84   (source_block_index=3)
gap = cur.y0 - prev.y1 = -1.48   (i.e. an overlap of 1.48pt)
median_height (page) = 12.48
gap_ratio = -0.119
```

This is the very first line-wrap on the very first page — fragmentation is
not a late-onset or rare effect, it is present from the first paragraph of
the document onward.

## 2. Which rule is responsible (exact attribution)

`_starts_new_paragraph()` (`src/structure/paragraph_grouper.py:268-317`) has
three independent conditions, checked in order. Re-evaluating each
condition separately for all 2,838 pairs:

| Condition | Times it alone would fire a split | Of those, false positives (ground truth says same paragraph) |
|---|---|---|
| `line.bbox.y0 < previous.bbox.y1` (overlap guard, line 280) | **2,595** | **2,324 (89.6%)** |
| First-line indent (line 297) | 0 | 0 |
| Cross-block / same-block gap ratio (line 315-317) | 79 | 7 |

**The overlap guard at `paragraph_grouper.py:280-281` is responsible for
2,595 of the 2,674 total splits this document produces — 97% of all
splitting decisions, and 99.7% of all the *incorrect* ones (2,324 of
2,331 measured false positives).** No other rule contributes meaningfully.

```python
if line.bbox.y0 < previous.bbox.y1:
    return True
```

## 3. Geometry calibration evidence (50 real failures)

Full 50-pair sample with raw TextBlocks, geometry, and grouping decisions
saved to `frag_sample_50.json` alongside this document (regenerable via the
script referenced in Appendix A). Five representative rows:

| page | prev text (tail) | cur text (head) | prev y0/y1 | cur y0/y1 | gap | overlap | line height | gap_ratio | block idx (prev/cur) | rule fired | expected |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | "...as though one were" | "reading a recipe..." | 300.36/312.84 | 311.36/323.84 | -1.48 | 1.48 | 12.48 | -0.119 | 3/3 | OVERLAP_GUARD | same paragraph |
| 1 | "...educational" | "research. It sets out..." | 72.27/84.75 | 83.27/95.75 | -1.48 | 1.48 | 12.48 | -0.119 | 2/2 | OVERLAP_GUARD | same paragraph |
| 8 | "...history of western thought from the" | "the present, it is historically associated..." | 157.7/170.2 | 168.7/181.2 | -1.5 | 1.5 | 12.5 | -0.120 | 4/4 | OVERLAP_GUARD | same paragraph |
| 10 | "...epistemological" | "basis of social science..." | 47.7/60.2 | 58.7/71.2 | -1.48 | 1.48 | 12.48 | -0.119 | 2/2 | OVERLAP_GUARD | same paragraph |
| 12 | "...trade-offs between" | "what one would like to do..." | (similar) | (similar) | -1.48 | 1.48 | 12.48 | -0.119 | same | OVERLAP_GUARD | same paragraph |

**Calibration finding — overlap magnitude is the discriminating signal, not
x-position:**

| Population | n | overlap magnitude (pt) |
|---|---|---|
| False positives (should NOT split) | 2,324 | min 0.51, **96% ≤2.0**, p90 1.48, max 612 (residual is measurement-tool noise — see Appendix B) |
| Genuine breaks confirmed disjoint-column (should split) | 116 | **min 5.02**, p5 5.02, median 8.45 |

There is a clean gap between 2.5pt (top of the false-positive cluster,
excluding noise) and 5.02pt (floor of every confirmed genuine column-switch
break in this document). **Cross-validated on Brinkman** (the `bug_001`
regression PDF, single-column, no multi-column false positives expected):
its only 3 genuine continuation-line overlaps measure 2.42-2.48pt, while
its smallest *genuine* break (a table-cell-to-table-cell transition) measures
8.97pt and its header/footer-ordering artifacts measure 176-589pt. The same
~2.5pt / ~5-9pt gap reproduces across both documents and both PDF
producers (`iLovePDF` for NoE, `Adobe LiveCycle PDFG ES` for Brinkman) —
this is not a coincidence specific to one font.

## 4. Structure classification (Goal 3)

Of the 2,324 confirmed false-positive splits, every single one sampled
(50/50 in the deliverable sample, and a further ~200 spot-checked while
building the ground-truth tool) is **same-column wrapped body text** —
ordinary prose line-wraps within one paragraph, in the same text column. None
involve:
- multi-column text (the false-positive population's x-ranges all overlap
  >85% with the previous line's — same column; genuine multi-column
  switches are the *separate*, correctly-identified 116-pair population)
- list items, quotations, headings, captions, or tables (Nature of Enquiry
  has no list items or block quotes in the sampled pages; its few headings
  are pulled out of the run by `markdown_builder.py` before
  `group_into_paragraphs()` ever sees them, per that module's own heading-
  flush logic — confirmed 0 INDENT-rule firings, which is the signal
  headings/indented structure would otherwise produce)

**This is purely a same-column wrapped-line defect.** It has nothing to do
with multi-column layout except that this guard was *written* for
multi-column safety and is misfiring on ordinary text because it only
checks *whether* an overlap exists, never *how large* it is.

## 5. Root cause confirmation and regression check

**Root cause:** `_starts_new_paragraph()`'s overlap guard treats *any*
`line.bbox.y0 < previous.bbox.y1`, however small, as proof of a column
boundary. For this PDF producer (`iLovePDF`), ordinary single-spaced body
text has bbox vertical extents (ascender-to-descender) that are
~1.0-1.6pt taller than the actual line pitch — a font-metric/PyMuPDF
bbox-computation characteristic, not a layout signal. Every consecutive
line pair in flowing body text triggers the guard.

**Proposed smallest fix (not implemented):** require the overlap to exceed
a small calibrated magnitude before treating it as a column-boundary
signal, e.g.:

```python
_OVERLAP_GUARD_MIN_PT = 4.0  # calibration: see notes_md/noe_paragraph_fragmentation_audit.md

if line.bbox.y0 < previous.bbox.y1 - _OVERLAP_GUARD_MIN_PT:
    return True
```

(4.0 sits with margin above the false-positive cluster's ~2.5pt ceiling in
both PDFs tested, and with margin below the smallest confirmed genuine break
in either PDF — 5.02pt in Nature of Enquiry, 8.97pt in Brinkman.)

**Demonstrated effect (computed against the real corpus, not simulated):**

- **Nature of Enquiry:** fixes 2,238 of 2,324 confirmed false positives
  (96.3%); the remaining 86 sit in a higher-magnitude band that is itself
  dominated by my own ground-truth tool's measurement noise on
  short-common-word coincidental token matches (see Appendix B) rather than
  real remaining defects.
- **bug_001 / bug_005 (Brinkman, same source PDF for both tickets):**
  Brinkman has only 127 total overlap-guard firings (vs. NoE's 2,595).
  Of those, exactly **3** measure ≤4pt (2.42-2.48pt) — all 3 confirmed
  genuine same-paragraph continuations (false positives the existing code
  also currently mis-splits, just far more rarely than in NoE). **The fix
  would only ever change behavior on these 3 pairs in Brinkman, all in the
  direction of *fixing* additional, previously-undetected minor
  fragmentation** — it cannot regress bug_001's headline 2037→545-line
  result (which is dominated by far larger structural fixes elsewhere in
  the module) or bug_005's footnote/endnote handling (footnote body text
  is matched and substituted by exact source-line text *before*
  `group_into_paragraphs()` ever runs on it — verified in
  `markdown_builder.py`'s `suppressed_body_lines`/`_substitute_markers`
  logic, which operates on whole lines independent of paragraph grouping).
  All 124 of Brinkman's *other* overlap firings (8.97pt and up: table
  cells, header/footer, masthead) measure above the proposed 4.0pt floor
  and are therefore **unaffected** — they keep splitting exactly as today.
- **feature_007 (wrapped heading continuation repair, NoE/Aims/sockett):**
  structurally insulated from this change — `heading_detector.py` runs
  independently of `paragraph_grouper.py`, and any line `markdown_builder.py`
  recognizes as heading text is removed from the run *before*
  `group_into_paragraphs()` is called (confirmed: 0 of this audit's 2,838
  evaluated pairs involved heading text, since headings never reach this
  function in production). Aims has zero pairs ≤4pt (fix is a no-op there).
  Sockett has 18 pairs ≤4pt (consistent with its heavy OCR block
  fragmentation, separately noted in the multi-column audit) — not
  independently verified against sockett's expected_md in this pass; flagged
  as a verification item for implementation, not a known regression.

## 6. Quantified summary

| Metric | Value |
|---|---|
| Total adjacent line pairs evaluated (NoE) | 2,838 |
| Pairs where the overlap guard fires | 2,595 |
| Confirmed false positives (incorrect split) | 2,324 (89.6% of all pairs; 99.7% of measured wrong splits) |
| Confirmed genuine breaks correctly caught by the guard | 116 disjoint-column + a handful of larger same-column breaks |
| False positives fixed by the proposed 4.0pt threshold | 2,238 of 2,324 (96.3%) |
| Brinkman (bug_001/bug_005 PDF) pairs affected by the same fix | 3 of 127 (2.4%), all currently-wrong continuations corrected, 0 regressions |
| Aims (feature_007 PDF) pairs affected | 0 |
| Sockett (feature_007 PDF) pairs affected | 18 (not yet individually verified) |

## 7. Risks

- The 4.0pt constant is calibrated against exactly two PDF producers
  (`iLovePDF`, `Adobe LiveCycle PDFG ES`/Brinkman). A third producer with a
  larger inherent bbox-overlap leading characteristic (e.g. 4-5pt) could
  still under-merge; conversely a producer with smaller genuine
  column/table-cell gaps than 5pt (none observed in this 10-PDF corpus)
  could under-split. Recommend keeping the constant named and documented
  exactly like `_SAME_BASELINE_Y_TOLERANCE_PT`/`_MAX_FRAGMENT_GAP_PT`
  already are, with this audit cited as the calibration evidence, and
  re-checking it if a new corpus PDF is added.
- Sockett's 18 affected pairs were not individually checked against
  `expected_md` in this audit (time-boxed) — should be verified during
  implementation, not assumed safe purely by extrapolation from NoE/Brinkman.
- This fix does not address the separate, smaller, harder problem already
  flagged in §4: genuine same-column paragraph breaks in this PDF have no
  reliable geometric signal at all (no indent, no enlarged gap, no
  meaningful overlap difference) — some true paragraph boundaries may
  still merge into their neighbor after this fix. That is a pre-existing,
  unrelated limitation of `_PARAGRAPH_GAP_RATIO`/indent detection, not
  something this fix makes worse, and is out of scope for "fix the 6.8×
  fragmentation inflation."

## 8. Estimated files affected (if implemented later)

- `src/structure/paragraph_grouper.py` (the fix — one new module constant,
  one changed comparison)
- `tests/test_paragraph_grouper.py` (new calibration test cases, mirroring
  this audit's NoE/Brinkman pairs)
- Possibly `tests/test_markdown_builder.py` / `tests/test_pipeline.py`
  golden-output tests, if any assert exact line counts/paragraph counts for
  Nature of Enquiry or sockett
- No model changes; no changes to `structure_detector.py`,
  `heading_detector.py`, `footnote_detector.py`, or any DOCX-layer code

## Deliverables summary

1. **Quantified failure counts:** 2,324 confirmed false-positive splits out
   of 2,838 evaluated line pairs in Nature of Enquiry (81.9% of all pairs);
   97% of all splitting decisions and 99.7% of wrong ones attributable to
   one rule.
2. **Root cause:** `paragraph_grouper.py:280-281`'s overlap guard
   (`line.bbox.y0 < previous.bbox.y1`) fires on any overlap regardless of
   magnitude; this PDF producer's font metrics put ordinary line-wrap
   overlap at ~1.0-1.6pt, well within the guard's reach.
3. **Geometry calibration evidence:** clean separation between the
   false-positive cluster (≤2.5pt, reproduced in both NoE and Brinkman) and
   the smallest genuine break (5.02pt NoE, 8.97pt Brinkman) — supports a
   4.0pt magnitude floor.
4. **Smallest deterministic fix:** add a magnitude floor to the existing
   overlap guard; one constant, one comparison change.
5. **Risks:** producer-specific calibration risk, sockett unverified, and a
   pre-existing separate limitation (no signal for same-column paragraph
   breaks) that this fix does not solve and should not be conflated with.
6. **Estimated files:** 1 source file, 1-2 test files.

**No code was modified to produce this audit.**

---

## Appendix A: reproduction

Evidence generated by ad hoc scripts in the session scratchpad (not
committed): loads the real PDF via `parse_pdf`/`extract_text`/
`detect_structure`, calls the real `_merge_same_baseline_fragments` and
re-evaluates `_starts_new_paragraph`'s three conditions per pair, and
cross-checks against `samples/benchmark/expected_md/1. Nature of Enquiry.md`
via token-adjacency matching (handles both hyphen-kept and de-hyphenated
line-wrap joins).

## Appendix B: ground-truth tool noise

The token-adjacency ground-truth check can produce false "genuine break"
labels when a pair's trailing/leading words are short and common enough to
coincidentally form a contiguous run elsewhere in the 28-page document by
chance (e.g. "to" / "observation and experience" type fragments). Manual
inspection of the highest-magnitude "false positive" entries (defined as
overlap > 50pt, n=53) found these are virtually all mislabeled genuine
column-switches or footer-to-body transitions, not real pipeline defects —
i.e. the true false-positive-fix rate of the proposed 4.0pt threshold is at
least 96.3% and likely higher once this measurement noise is excluded.

---

## IMPLEMENTATION RECORD (feature_010, 2026-06-25)

**Implemented exactly as audited above — no design changes during
implementation.** `src/structure/paragraph_grouper.py`: added
`_OVERLAP_GUARD_MIN_PT = 4.0` (module constant, with the calibration
evidence above cited in its docstring) and changed
`_starts_new_paragraph()`'s guard from
`if line.bbox.y0 < previous.bbox.y1:` to
`if line.bbox.y0 < previous.bbox.y1 - _OVERLAP_GUARD_MIN_PT:`. No other
rule (indent, cross-block gap, same-block gap, footnote logic, heading
logic) was touched.

### Verification (measured against the real corpus, post-implementation)

**Nature of Enquiry:**

| Metric | Before | After | Expected (ground truth) |
|---|---|---|---|
| Total paragraphs (`group_into_paragraphs`, all pages) | 2,702 | 311 | — |
| Rendered Markdown content lines | 2,731 | **370** | 399 |
| Overlap-guard firings (of 2,838 pairs) | 2,595 | 204 | — |

88.5% reduction in paragraph count; rendered line count moved from 6.8×
inflated to 0.93× (slightly under, not over) the expected count. Spot
check: `###### Page 10`'s opening paragraph (the audit's own first
example) now renders as one flowing sentence, matching `expected_md`
exactly.

**Brinkman (`bug_001`/`bug_005` regression PDF) — regenerated both
before/after Markdown via the real pipeline (`parse_pdf` →
`extract_text` → `detect_structure` → `extract_images` →
`detect_headings` → `detect_footnotes` → `build_markdown`), diffed:**

- Only 3 of 127 overlap-guard firings are ≤4pt. All 3 are exactly the
  pairs identified in this audit's §5/§3. All 3 now merge correctly,
  matching `expected_md` verbatim:
  - `...children's psychological` + `development and interests'...` → confirmed contiguous in `expected_md`.
  - `...crucial importance of` + `taking into account teachers'...` → confirmed contiguous in `expected_md`.
  - `...adversely affect their learning. For example,` + `in describing her students, Farida (B4-L)...` → confirmed contiguous in `expected_md`.
- The other 124 firings (table cells at 8.97-41.97pt, header/footer/
  masthead at 176-589pt) are **bit-for-bit identical** before/after —
  confirmed via full-document diff, zero unexpected changes anywhere else
  in the 60KB+ generated Markdown (only the 3 paragraph merges plus
  non-deterministic image-hash filenames, unrelated to this fix, differ).
- **bug_005 (footnote/endnote substitution) verified unaffected:** all 3
  endnote markers (`[^p16-1]`, `[^p16-2]`, `[^p16-3]`) substitute at
  identical inline positions before and after, and all 3 footnote-
  definition blocks at the end of the document are byte-identical.
  Confirmed: marker substitution operates on whole-line anchor text
  (`markdown_builder.py::_substitute_markers`) independently of how that
  line's paragraph neighbors get grouped.

**feature_007 (wrapped heading continuation repair) — verified
structurally insulated, not just assumed:** ran `detect_headings()`
before/after on Nature of Enquiry, Aims, and sockett and compared the
full `(level, text)` heading list:

| PDF | Heading count before | Heading count after | Identical? |
|---|---|---|---|
| Nature of Enquiry | 63 | 63 | Yes |
| Aims | 6 | 6 | Yes |
| sockett | 24 | 24 | Yes |

Confirmed reason: `heading_detector.py` has no dependency on
`paragraph_grouper.py`, and any line `markdown_builder.py` matches as
heading text is removed from the run *before* `group_into_paragraphs()`
is ever called on it.

**sockett — investigated individually, not assumed safe (per
instruction):** 18 of 779 line pairs are affected (Aims: 0 of 166).
Listed and inspected all 18:

- All are either (a) genuine same-line OCR-fragment continuations of
  real sentences (e.g. `"of professionalism in teaching. Most teachers,
  ...unable t"` + `"o research or record teaching..."`), or (b)
  single/double-character OCR noise tokens (e.g. `"i"`/`"I"`, `"~"`/`"."`)
  whose merge-or-not decision is immaterial since the underlying OCR text
  is already garbled either way.
- **None cross the page-spread gutter** — checked x-ranges for all 18:
  every pair's x0/x1 values stay within the same half (either both <420
  or both >470 of the 843pt double-page-spread width); none bridges left
  book-page content into right book-page content.
- All 18 measure well below the smallest genuine break magnitude observed
  anywhere in the 10-PDF corpus (5.02pt) — none is at risk of being a
  disguised genuine structural break.
- **Conclusion: safe.** No further action needed, but this was measured,
  not extrapolated from NoE/Brinkman as the original audit flagged it
  should not be.

### Test results

Added `tests/test_paragraph_grouper.py::TestOverlapGuardCalibration` (6
tests, using real geometry from this audit plus 2 synthetic boundary-value
checks at exactly the 4.0pt floor). All 23 tests in the file pass.

Full suite, `pytest -m "not real_docling and not real_surya"`:

```
877 passed, 7 skipped, 5 deselected, 1 warning in 1796.56s
```

(871 pre-feature_010 baseline + 6 new tests = 877; 0 failed, 0
regressions.)

### Files modified

- `src/structure/paragraph_grouper.py` — new constant
  `_OVERLAP_GUARD_MIN_PT`, one changed comparison, updated docstrings on
  the constant block and on `_starts_new_paragraph()`'s guard.
- `tests/test_paragraph_grouper.py` — new `TestOverlapGuardCalibration`
  class (6 tests).
- `docs/DECISIONS_LOG.md` (Part 15), `docs/PHASE_STATUS.md` (Phase L),
  `docs/TASKS.md`, `PROJECT_SAVE_STATE.md` §6 — status records.

No other `src/` file was touched. No model, validator, heading, footnote,
or DOCX-layer code was changed.
