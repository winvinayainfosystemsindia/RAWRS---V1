# RAWRS Audit — Multi-Column Layout Support / Reading-Order Anomalies

**Status: AUDIT ONLY. No production code was changed.** This document is the
full evidence trail behind the audit requested 2026-06-25. All findings below
are measured directly against the real benchmark corpus
(`samples/benchmark/pdfs/`, `samples/benchmark/expected_md/`,
`samples/benchmark/remediated_docx/`) and the real `src/` pipeline, not
inferred or assumed.

## 0. Method

For every benchmark PDF: ran `parse_pdf` → `extract_text` → `detect_structure`
→ `extract_images` → `detect_headings` → `build_markdown`, then ran the
production `_check_reading_order_anomalies()` (rule `PAGE_003`,
`src/validation/validator.py`) against the resulting `Document`. Where
`PAGE_003` flagged a page, dumped the page's raw PyMuPDF block geometry
(`order`, `x0/x1/y0/y1`, `text`) directly via `page.get_text("dict")` and
compared it line-by-line against the rendered Markdown and against
`samples/benchmark/expected_md/*.md` (human-remediated ground truth).

## 1. Goal 1–2: Do multi-column documents exist in the corpus, and which?

`PAGE_003` flags **100% of pages** on 4 of the 10 benchmark PDFs and **0
pages** on the other 6:

| PDF | Pages | PAGE_003 flagged | Genuinely multi-column? |
|---|---|---|---|
| 1. Nature of Enquiry | 28 | 28/28 | **Yes** — true 2-column academic layout |
| 1. Aims of Education (Dhankar) | 4 | 4/4 | No — single column |
| 3. sockett_profession | 9 | 9/9 | **Yes, but not in the usual sense** — each PDF page is a scanned double-page spread (2 physical book pages side by side) |
| 7. Brinkman | 18 | 18/18 | No — single column |
| 2. Bryman | 9 | 0/9 | No |
| 2. FolkPedagogy_Bruner | — | 0 | No |
| 4. O'Leary | — | 0 | No |
| 4. Teaching-as-a-Professional-Discipline | — | 0 | No |
| 5. Calderhead | — | 0 | No |
| 6. Fullan & Hargreaves | — | 0 | No |

**Critical finding: `PAGE_003`'s 100%-of-pages signal does not mean
"multi-column."** Of the 4 flagged PDFs, only 2 (Nature of Enquiry, sockett)
have an actual side-by-side text layout. The other 2 (Aims, Brinkman) are
ordinary single-column documents where the *same* geometric heuristic
(backward y-jump) is triggered by something else entirely (§3). This
distinction was only resolved by reading raw per-page geometry — it is
invisible from the validation issue text alone.

## 2. Goal 3 + Required Evidence: Is reading order actually wrong?

### 2a. Nature of Enquiry (genuine 2-column) — reading order is CORRECT

Raw block dump, physical page 8 (`page_w=524`):

```
order=0  x0=32.2  x1=245.1  y0=24.0   "the context of educational research"   (running header)
order=1  x0=32.2  x1=43.3   y0=648.6  "10"                                    (footer page number)
order=2  x0=44.2  x1=246.5  y0=47.7   "Because of its significance..."        (LEFT column start)
...
order=55 x0=32.3  x1=246.5  y0=619.8  "...ethnographers and"                  (LEFT column end)
order=56 x0=258.3 x1=472.6  y0=47.7   "discourse analysts rely..."            (RIGHT column start)
...
order=110 x0=258.3 x1=472.6 y0=565.7  "...philosopher John"                   (RIGHT column end)
```

The block order is: header → footer → **entire left column top-to-bottom** →
**entire right column top-to-bottom**. Confirmed against the rendered
Markdown (`"Although positivism..."`, left-column order=9, appears at
markdown line 1373; `"Though the term positivism..."`, right-column order=58,
appears at line 1465 — strictly after). **This is correct reading order.**
PyMuPDF's native block emission already groups left-column-then-right-column
for this PDF producer; nothing downstream reorders or needs to reorder it.

`PAGE_003` flags this page anyway, because its `_count_backward_jumps()`
heuristic measures a single linear y-position sequence and cannot distinguish
"legitimate column switch" (right column's first line sits far above the
left column's last line, on a page that has columns) from "things are out of
order." The column switch alone (order 55→56, Δy0 = 619.8→47.7) registers as
one large backward jump every single page — this is a **structural property
of any correctly-rendered 2-column page**, not evidence of a defect.

### 2b. sockett_profession (scanned double-page spreads) — reading order is CORRECT

`page_w=843`, almost exactly 2× a normal page width. Raw geometry confirms
each PDF page is two physical book pages scanned side by side: blocks
order=0–100 sit at x0 134–410 (left book page, running head + body, OCR'd,
heavily fragmented into small per-phrase blocks — a separate OCR
segmentation artifact, not a column-order bug), then order=101–219 jump to
x0 492–762 (right book page, its own running head + body). Block order is
left-book-page-in-full, then right-book-page-in-full — i.e. correct
sequential reading order for a spread. `PAGE_003` fires for the same
column-switch reason as Nature of Enquiry, compounded by OCR fragmentation
producing many additional small blocks per line (56 "small" backward jumps
measured below 150pt, vs. only 12 "big" ones — see §4 quantification).

### 2c. Aims of Education — NOT multi-column; false-positive cause identified

Raw geometry, physical page 2 (`page_w=595`): single column, x0=72 to
x1≈526.5 throughout (89% of page width — not split). The *only* backward
jump on every page is order=0 (the footer page-number block, e.g. `"2"` at
y0=792, bottom margin) immediately followed by order=1 (body text top,
y0=72.3). PyMuPDF emits the footer block **first** in its content stream
despite it sitting visually at the **bottom** of the page. `PAGE_003` is
correctly detecting a real ordering anomaly here — it is just not a
column problem, it's a producer page-number/body ordering quirk (§3).

### 2d. Brinkman — NOT multi-column; two distinct, already-tentatively-known causes

Body text on a representative page (page 6) spans x0≈48.2–439.4 — i.e. a
single full-width column, not split. `PAGE_003` fires for two reasons,
confirmed by direct geometry and by diffing rendered Markdown against
`samples/benchmark/expected_md/7.brinkman....md`:

1. **Running-header/page-number ordering quirk** (same mechanism as Aims):
   the page header (`"Brinkmann"`) and footer page number are emitted by
   PyMuPDF partway through, or at the end of, the page's block stream, not
   at the position their bbox says they occupy.
2. **Table/caption ordering** (Required Evidence §C: "captions/tables/images
   break ordering"): on Table-1-bearing pages, Table 1's cell text is
   emitted in block order, then the running header/footer pair, then Figure
   1's image and caption — see §3 for the directly observed Markdown
   evidence.

## 3. Goal 4: Root-cause attribution by pipeline stage — DIRECT EVIDENCE

Ran the full pipeline end-to-end and inspected the actual generated
Markdown (not a hypothetical) for all 4 flagged PDFs.

### 3a. Confirmed: `Document.blocks` includes running headers/footers verbatim, with no filtering anywhere downstream

Grepped `src/structure/structure_detector.py`, `src/structure/paragraph_grouper.py`,
`src/markdown/markdown_builder.py` for any header/footer/margin-text
exclusion logic. **None exists.** `_detect_printed_label()` (feature_009)
*reads* margin-zone text to populate `Page.printed_label`, but never removes
the source block from `text_blocks` — the same line is kept in the body
stream and rendered as an ordinary paragraph. `markdown_builder.py:227` sorts
each page's blocks purely by `block.order` (PyMuPDF's native emission order)
with no x/y correction of any kind.

**Direct evidence, Nature of Enquiry, actual generated Markdown (`Page 10`):**

```
###### Page 10

t h e  c o n t e x t  o f  e d u c a t i o n a l  r e s e a r c h

10

Because of its significance for the epistemological
...
```

**Ground truth (`expected_md/1. Nature of Enquiry.md`)** contains neither the
letter-spaced running head nor the bare `"10"` anywhere — the body text
begins directly with "This large chapter explores...". **This is the first
point of divergence (Required Evidence §B)**: an extra, misplaced paragraph
injected between the auto-generated `###### Page N` marker and real body
content, on every single page.

Same pattern confirmed in **Aims** (`"###### Page 2"` → `"2"` → body) and
**Brinkman** (`"Brinkmann"` appears as its own paragraph mid-page on 9 of 18
pages — verified via grep on the actual rendered Markdown).

**Pipeline stage responsible: Structure Detection (`structure_detector.py`)**
is the point where this information is available (margin-zone position is
already computed for `printed_label`) but not acted on — the block is never
flagged or excluded for downstream consumers. This is a **Case 2
(reconstruction problem)** by the audit's own taxonomy: the geometric
information needed already exists (margin-zone test, used for
`printed_label`), it is simply never used to suppress the block from the
body-content stream.

### 3b. Confirmed: Brinkman's table/caption ordering defect, direct Markdown evidence

Actual generated Markdown, page 6 of the Brinkman PDF:

```
1 Mid-LCE belief score
6
11
3 High-LCE belief score
0
4
16

Brinkmann          <- running header, mid-content
347                 <- footer page number, mid-content

![Figure 1. ...](...)
*Figure 1. State-wise differences in LCE pedagogy and belief scores.*
```

`expected_md` for the same content has **no `Brinkmann`/`347` between the
table and the figure** — clean transition straight from the last table cell
to the figure. Root cause: same Structure-Detection-stage gap as §3a (header/
footer block ordering), compounded on this page by the pre-existing,
already-documented limitation that **table cell text is rendered as a flat
sequence of one-line paragraphs with no table structure** (`docs/TASKS.md`:
"table remediation" is explicitly listed as not yet started). The table
itself is not reading-order-corrupted — its cells are in correct visual
order — it just has no markdown table structure, and the header/footer
artifact happens to land in the table→figure transition.

**Pipeline stage responsible: same as 3a (Structure Detection), plus the
pre-existing, separately-scoped table-rendering gap (Markdown Builder).**

### 3c. New finding (incidental to this audit): Nature of Enquiry has near-total paragraph fragmentation, root-caused to `paragraph_grouper.py`'s multi-column safety guard

While comparing actual vs. expected Markdown for Nature of Enquiry, found
the actual output renders **every line as its own one-line paragraph**
(e.g. "Because of its significance for the epistemological" / "basis of
social science and its consequences for educa-" / ... as 6 separate
blank-line-separated paragraphs, never joined). Measured: **2,731 non-blank
content lines in the actual Markdown vs. 399 in `expected_md`** — a ~6.8×
inflation, corpus-wide for this one document.

Root cause, confirmed by direct unit-level test
(`group_into_paragraphs()` called directly on page-8's blocks): every
consecutive line pair in this PDF has a small (~1.5pt) vertical bbox
*overlap* — e.g. line N's `y1=60.2`, line N+1's `y0=58.7` — a normal
ascender/descender leading characteristic of this particular PDF producer
(`producer: iLovePDF`), not a column artifact. `paragraph_grouper.py:280-281`:

```python
if line.bbox.y0 < previous.bbox.y1:
    return True
```

This guard exists specifically to prevent two genuinely different
*columns* whose lines coincide in y from being merged into one paragraph
(see the module's own docstring: "two independent multi-column safety
guards exist... Neither guard is exercised by any PDF in the current
benchmark/regression corpus"). That statement is now **falsified** — Nature
of Enquiry exercises this guard on effectively every line, but as a false
positive: the overlap here is ordinary same-column line leading, not a
column boundary, and the guard has no way to tell the two apart since it
only looks at y-overlap, never x-overlap/x-distance.

**Pipeline stage responsible: Paragraph Grouper.** This is a distinct,
previously-undiscovered defect, found only because this audit required
diffing actual vs. expected Markdown for a genuinely multi-column document
— not a typical code path this project's existing regression corpus
exercises (Brinkman, the corpus's other paragraph-reconstruction proof
case, does not have this y-overlap characteristic).

## 4. Goal 5: Numeric quantification (not qualitative)

| PDF | Pages | PAGE_003-flagged pages | Backward jumps >150pt (column/spread switches) | Backward jumps ≤150pt (header/footer/OCR-fragment artifacts) | Leaked header/footer paragraphs in actual MD |
|---|---|---|---|---|---|
| Nature of Enquiry | 28 | 28 (100%) | 57 | 26 | 14 (running-head lines) + 1 per page (footer digit) |
| Aims | 4 | 4 (100%) | 4 | 0 | 4 (1 per page, footer digit) |
| sockett | 9 | 9 (100%) | 12 | 56 | not separately isolated (OCR noise dominates) |
| Brinkman | 18 | 18 (100%) | 21 | 38 | 9 (`"Brinkmann"` lines) |

Nature-of-Enquiry-specific: **2,731 actual content lines vs. 399 expected
(6.8× inflation)**, attributable to §3c's paragraph-fragmentation defect, not
to reading order at all.

## 5. Required Evidence §C: classification of every anomaly found

| PDF | Column-interleaved? | Columns swapped? | Caption/table/image breaks order? | Otherwise corrupted? |
|---|---|---|---|---|
| Nature of Enquiry | No (order is correct) | No | No | **Yes** — header/footer block mid-stream (§3a) |
| sockett | No (order is correct) | No | No | **Yes** — header/footer + OCR fragmentation (§3a-analog) |
| Aims | N/A (not multi-column) | N/A | No | **Yes** — footer-before-body ordering quirk (§2c) |
| Brinkman | N/A (not multi-column) | N/A | **Yes** — table/figure transition (§3b) | **Yes** — header/footer mid-stream (§3a) |

**No PDF in the benchmark corpus exhibits column-interleaving or
column-swapping.** Every measured anomaly across all 4 flagged PDFs reduces
to one of: (1) a running-header/footer block emitted out of visual-position
order by the PDF producer, (2) a table→figure transition crossing the same
header/footer artifact, or (3) (sockett only) heavy OCR block fragmentation
compounding the header/footer artifact's small-jump count.

## 6. Architecture Analysis (Case 1–4 classification)

**Primary finding — header/footer body-leak (§3a, affects 3 of 4 PDFs,
responsible for the large majority of `PAGE_003` firings): Case 2
(reconstruction problem).** `_detect_printed_label()` already computes the
exact geometric test needed (margin-zone position, top/bottom 12% of page
height) to identify these blocks — it just doesn't act on the result beyond
populating `Page.printed_label`. The information exists; it is simply never
used to keep the block out of the body-content stream that
`paragraph_grouper.py`/`markdown_builder.py` render.

**Secondary finding — Brinkman table/caption ordering (§3b): Case 1
(validation problem only) for the header/footer component (same fix as
above resolves it); the table's own flat-cell-text rendering is a
**pre-existing, already-tracked, out-of-scope limitation** (table
remediation, `docs/TASKS.md`), not new to this audit.

**Tertiary finding — Nature of Enquiry paragraph fragmentation (§3c): Case
1 (validation/heuristic-calibration problem).** The `TextBlock`/`Document`
model already carries everything needed (`bbox`, `source_block_index`); the
defect is a single over-broad guard condition in `paragraph_grouper.py`
(`y0 < previous.y1` with no x-axis check) misfiring on ordinary same-column
leading for one PDF producer.

**No PDF in the corpus presents a Case 3 (model problem) or Case 4
(extraction problem).** PyMuPDF already emits left-column-then-right-column
/ left-page-then-right-page order correctly for both genuinely multi-column
documents in the corpus; `TextBlock` already carries `bbox`/`order`/
`source_block_index`, which is sufficient for everything found here. **There
is no evidence in this corpus that RAWRS needs new column-detection or
column-reordering logic at all** — the corpus's only two truly multi-column
documents already render in correct reading order without any column-aware
code existing.

## 7. Severity assessment

- **Header/footer body-leak (§3a):** Medium-high user-visible impact —
  produces a stray, semantically-meaningless one-line paragraph (a
  letter-spaced running head, or a bare page-number digit duplicating the
  document's own `###### Page N` marker) on every affected page, in 3 of 10
  benchmark PDFs (30% of corpus). Accessibility-relevant: a screen-reader
  user hits a meaningless "10" or "the context of educational research"
  paragraph between every page's heading marker and its real content.
- **Brinkman table/figure transition (§3b):** Low-medium — same root cause
  as above, narrower blast radius (table-bearing pages only), and overlaps
  with an already-tracked, separately-scoped limitation (no table
  structure at all).
- **Nature of Enquiry paragraph fragmentation (§3c):** High for this one
  document — 6.8× line-count inflation makes the rendered chapter
  substantially harder to read than the source, though it is a localized,
  single-PDF-producer defect, not corpus-wide.
- **Genuine multi-column reading order:** **No defect found.** Severity:
  none — do not build column-detection/reordering logic to fix a problem
  that does not exist in the corpus.

## 8. Smallest viable deterministic fix (NOT IMPLEMENTED — audit only)

1. **For §3a (header/footer leak, highest-leverage fix):** in
   `structure_detector.py`, reuse `_detect_printed_label()`'s existing
   margin-zone test to additionally mark the *source block(s)* that
   produced the chosen `printed_label` candidate (and, by the same
   margin-zone geometric test, any other short, isolated line in the
   margin zone that repeats verbatim across multiple pages — the
   running-head signature) as non-body, and exclude marked blocks from the
   sequence `paragraph_grouper.py`/`markdown_builder.py` render as body
   paragraphs. This requires no new pipeline stage, no model redesign, and
   reuses an existing, already-calibrated geometric test.
2. **For §3c (paragraph fragmentation):** add an x-axis check to
   `paragraph_grouper.py`'s `y0 < previous.bbox.y1` guard at line ~280 —
   only treat a y-overlap as a column-boundary signal when the two lines'
   x-ranges also do not overlap (a same-column line-wrap with leading
   overlap always has overlapping or near-identical x0; two different
   columns never do). This is the smallest change that fixes the false
   positive without weakening the guard's original, still-valid purpose.
3. Both fixes are independent and can ship separately.

## 9. Risks

- Risk to (1): a repeating margin-zone line is presumed to be a running
  head/footer; a document with a genuinely repeating short *body* line in
  the margin zone (none found in this 10-PDF corpus) could be
  incorrectly suppressed. Mitigation: require the line to repeat across
  ≥2 pages before suppressing (consistent with how `printed_label`
  ambiguity is already handled conservatively per feature_009).
- Risk to (2): loosening the y-overlap guard with an x-check could, in
  principle, allow two columns with overlapping x-ranges (e.g. a
  full-width element bridging both columns) to be incorrectly joined.
  No such case exists in the current corpus (verified: NoE's two
  columns have x-ranges 32–246 and 258–472, a clean 12pt gutter with no
  overlap), but the fix should keep a gutter-width sanity check as a
  second guard, not rely on x-overlap alone.
- Neither fix touches `Document.blocks` itself (per the existing
  paragraph_grouper design constraint — `footnote_detector.py` and other
  consumers keep reading the unmodified block stream).

## 10. Estimated files affected (if implemented later)

- `src/structure/structure_detector.py` (fix 1 — block exclusion/marking)
- `src/structure/paragraph_grouper.py` (fix 2 — guard refinement)
- `src/markdown/markdown_builder.py` (fix 1 — consume the exclusion marker)
- `tests/test_structure_detector.py`, `tests/test_paragraph_grouper.py`,
  `tests/test_markdown_builder.py` (new/updated tests)
- Likely `tests/test_pipeline.py::TestStructureDetectionDoesNotChangeExistingOutputs`
  per the established pattern from feature_009/bug_007 (any change that
  makes Structure Detection observably affect downstream content needs
  this test's exclusion-list/equality-assertion extended)
- No model changes (`text_block.py`, `document.py`, `page.py` unaffected)

## Deliverables summary

1. **Benchmark findings:** 4/10 PDFs flagged by PAGE_003 at 100% of pages;
   only 2 are genuinely multi-column, and both already render in correct
   reading order today.
2. **Root cause:** running-header/footer blocks rendered into body content
   verbatim (Structure Detection gap, Case 2) — not a multi-column problem.
   One additional, unrelated paragraph-fragmentation defect found in
   `paragraph_grouper.py`'s multi-column safety guard (Case 1).
3. **Severity:** medium-high for the header/footer leak (3/10 PDFs, every
   page), high but localized for the NoE fragmentation defect, none for
   "true" multi-column reading order (no defect exists).
4. **Architectural impact:** none of the 4 Case classifications require a
   new pipeline stage, new model fields, or new PDF-extraction logic — all
   needed geometric information already exists in `TextBlock`/`Page`.
5. **Smallest viable fix:** reuse `_detect_printed_label()`'s margin-zone
   test to exclude header/footer blocks from body rendering; add an x-axis
   check to `paragraph_grouper.py`'s column-overlap guard.
6. **Risks:** both enumerated in §9, both mitigable with conservative,
   corpus-consistent guards.
7. **Estimated files:** 3 source files, 3-4 test files (§10).

**No code was modified to produce this audit.**
