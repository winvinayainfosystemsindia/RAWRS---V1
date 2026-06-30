# Wrapped Heading Continuation Repair — Audit & Design Review

**Status: IMPLEMENTED & VERIFIED (2026-06-25).** Implemented in `src/headings/heading_detector.py` per §3's design, with the three final parameter choices: 4-line absorption cap, local (heading-only) soft-hyphen handling, sockett-specific side effects accepted as-is (confirmed not a benchmark regression — see §9). Full fast-subset test suite and document-by-document benchmark re-run both confirmed clean; see §9.

Ticket: `feature_007_wrapped_heading_continuation_repair`. This is the same feature `heading_detector.py`'s `detect_headings()` already names in a comment as not-yet-built (added during the `bug_007` fix, see `docs/DECISIONS_LOG.md` Part 10): `_build_layout_index()` already returns a third value, a `bbox_index: Dict[page][text] -> (y0, y1)`, scaffolded specifically for this feature's `_try_absorb_continuations()` — which does not exist yet.

---

## 1. Independent Verification of Benchmark Evidence

All evidence below was re-derived directly from the real PDFs via PyMuPDF, not assumed from the task brief.

### 1.1 Nature of Enquiry wrap (reported example)

`samples/benchmark/pdfs/1. Nature of Enquiry.pdf`, page 23:

```
block=4 line=0 bbox=(279.6,271.7,483.5,284.8) size=11.0 bold=True font=Helvetica-Bold text='1.16  Subjectivity and objectivity in'
block=4 line=1 bbox=(279.6,282.7,400.1,295.8) size=11.0 bold=True font=Helvetica-Bold text='educational research'
```

Confirmed: same block (4), consecutive line indices (0, 1), same size (11.0), same bold state, same font. `gap = y0(line1) - y1(line0) = 282.7 - 284.8 = -2.1`; `line_height = y1(line0) - y0(line0) = 13.1`; `gap_ratio = -2.1 / 13.1 = -0.160`. **Matches the reported `gap_ratio ≈ -0.160` exactly.**

Live current behavior, confirmed by running `detect_headings()` unmodified: this produces **H3** (`'1.16  Subjectivity and objectivity in'`, via the numbering-pattern tier) immediately followed by a separate **H2** (`'educational research'`, via the bold-layout tier) — exactly the reported `H3 + H2` defect.

### 1.2 Aims of Education title wrap (reported example)

`samples/benchmark/pdfs/1.Aims of Education and the teacher_Dhankar_PhilPers (1).pdf`, page 1:

```
block=1 line=0 bbox=(125.9,72.6,477.4,90.3)  size=16.0      bold=True font=TimesNewRomanPS-BoldMT text='AIMS OF EDUCATION: DO TEACHERS NEED'
block=2 line=0 bbox=(189.1,97.0,409.9,114.8) size=[14.0,16.0] bold=True font=TimesNewRomanPS-BoldMT text='TO BOTHER ABOUT THEM?'
```

Confirmed: **different** blocks (1 vs 2), **different x0** (125.9 vs 189.1), same max font size (16.0) on both, same bold state. `gap = 97.0 - 90.3 = 6.7`; `line_height = 90.3 - 72.6 = 17.7`; `gap_ratio = 6.7 / 17.7 = 0.378`. **Matches the reported `gap_ratio ≈ +0.377`** (the 0.001 difference is rounding of the displayed bbox coordinates).

Live current behavior, confirmed: produces **H1** (the title-slot tier) immediately followed by a separate **H2** (bold-layout tier) — the reported `H1 + H2` defect.

### 1.3 Full count of confirmed defects — independently reproduced, not just spot-checked

A corpus-wide scan for every same-block, bold-to-bold consecutive line pair (the exact signal class both reported examples share) found **exactly 9 distinct multi-line heading defects in Nature of Enquiry**, matching the task brief's count precisely:

| Heading | Lines | gap_ratio (each link) |
|---|---|---|
| 1.6 | 2 | -0.160 |
| 1.9 | 2 | -0.160 |
| 1.11 | **4** | -0.160, -0.160, -0.160 |
| 1.12 | **3** | -0.160, -0.160 |
| 1.13 | **3** | -0.160, -0.160 |
| 1.14 | 2 | -0.160 |
| 1.15 | 2 | -0.160 |
| 1.16 | 2 | -0.160 (reported example) |
| 1.17 | 2 | -0.160 |

Every link in every chain — including the 3- and 4-line cases — has **identical** size (11.0), bold state, font, and `gap_ratio` (-0.160). This directly confirms requirement #4 (multi-line support): a chain-following algorithm that re-applies the same pairwise gate to each successive line, rather than a fixed 2-line special case, naturally covers all observed wrap lengths with no additional logic.

Aims of Education has exactly **1** such defect (the title), matching the brief.

**Total: 10 confirmed defects, exactly as specified.**

### 1.4 Controls

**Body-text wraps** (plain, non-bold, justified paragraph lines): sampled extensively across both PDFs, e.g. page 9's numbered list (`'1  Its problem-seeking...'` → `'2  Its testing...'`): `gap_ratio` -0.117 to -0.131. **This is in the same numeric neighborhood as the real heading wraps above** (-0.160) — confirming `gap_ratio` alone is *not* a sufficient discriminator. These lines are correctly excluded today, and must remain excluded, by the fact that they are not bold (`is_bold=False`) — confirmed directly: this list sits inside a "BOX 1.1" caption block at body size/weight and produces **zero** headings under the current, unmodified detector.

**Distinct, unrelated headings:** no naturally-occurring case exists in this corpus of two genuinely different headings sitting on immediately-consecutive candidate lines with no body text between them — every real heading in the sampled corpus is followed by its own body paragraph. The "≈20–37" figure in the brief reflects this: any two truly distinct headings are always dozens of line-heights apart in extraction order, nowhere near the calibrated continuation window below. This is not a tight boundary case to design against; it is confirmation that the metric has wide separation between "same heading" and "anything else" once the lines genuinely differ in font/bold/size or position.

### 1.5 The "Chapter 3);" trap — confirmed real, not hypothetical

Found at `1. Nature of Enquiry.pdf`, page 22, as a literal, standalone candidate line:

```
line 113: 'power, a feature of critical theory, discussed in '
line 114: 'Chapter\xa03);'
line 115: 'the recognition that researchers are part of the world '
```

This is the tail end of a justified body sentence, wrapped so that `'Chapter\xa03);'` (note: `\xa0` is a non-breaking space, which Python's `\s` regex class matches) lands alone on its own candidate line. **Confirmed via direct PyMuPDF inspection: this line is plain body text — size 9.5, `is_bold=False`** — identical to the surrounding paragraph.

**Confirmed live, pre-existing defect, independent of this feature:** running the current, unmodified `detect_headings()` shows this line is *already* misclassified as **H2** today, via tier 3's `_H2_CHAPTER_PATTERN` (`^(unit|chapter)\s+\d+\b`), which matches on text pattern alone and has no bold/layout requirement. This is a real, separate, pre-existing bug (not part of this feature's scope to fix), but it is exactly why requirement #6 matters: this line's *own* layout signal is **not bold**, and the line before and after it are **also not bold, and also the same size as this line** (it's all one paragraph). If a continuation-merge rule were keyed only on "matching font size + matching bold state between two adjacent lines," `'Chapter\xa03);'` and its neighboring body lines would match each other trivially (all are 9.5pt, all non-bold, `gap_ratio` consistent with the body-wrap range of -0.12) — and the merge would silently absorb an unbounded run of ordinary paragraph text into a single bogus "heading," compounding the existing tier-3 false positive into something much worse.

**This is the central design constraint the rest of this review is built around:** a continuation-merge must never fire from a non-bold anchor line, regardless of what the *next* line looks like.

---

## 2. Root Cause

`detect_headings()` operates on one candidate line at a time (`for line in _iter_candidate_lines(text)`), classifying and emitting each line as an independent `Heading` with no memory of, or look-ahead to, neighboring lines. When a PDF's column width forces a single logical heading onto 2–4 physical lines, every wrapped line independently passes its own classification tier:

- The first line passes via a *text-pattern* tier (numbering, in Nature of Enquiry; the H1 title-slot, in Aims) — both of which only inspect the line's own text, never its neighbors.
- Every continuation line independently passes the *bold-layout* tier (tier 4: bold and larger than body), because the heading's bold/size styling is applied per-line by the PDF, not per-logical-heading.

There is no code path anywhere in `_classify_line()` or its caller that ever considers two lines jointly. The defect is a **structural absence of cross-line context**, not a faulty rule — every individual classification is, in isolation, behaving exactly as designed.

---

## 3. Implementation Plan (smallest safe design)

### 3.1 Reused signal: extend, don't replace, the existing scaffolding

`_build_layout_index()` already does one PyMuPDF dict-mode pass per document and already returns `bbox_index: Dict[page][text] -> (y0, y1)` (added, unused, during `bug_007`). The plan extends this **same loop, same pass** to also capture the line's enclosing block index — a value already in scope (`bi` from `enumerate(page_dict.get('blocks', []))`) but currently discarded:

```
bbox_index: Dict[page][text] -> (block_index, y0, y1)
```

No new PDF pass. No new field needed for `x0`: the Aims case (confirmed §1.2) has *different* `x0` between its two lines and is still a valid continuation, so `x0` must **not** be a matching condition — including it would have actively excluded the one cross-block defect this feature exists to fix. This was confirmed, not assumed: the brief's own evidence already shows "different x0 values" for the one case that must still match.

### 3.2 Where it plugs in

`detect_headings()`'s per-page loop currently does:
```python
for line in _iter_candidate_lines(text):
    level = _classify_line(line, ...)
    if level is None: continue
    headings.append(Heading(level=level, text=line, ...))
```

Plan: materialize `_iter_candidate_lines(text)` into a `list` once per page (pages are at most a few hundred lines; trivial cost), then iterate by index instead of a plain `for`. After a line is classified as a non-`None` heading **and its own `layout.is_bold` is `True`** (see §3.3, gate 1), attempt `_try_absorb_continuations()`, which looks at subsequent lines and returns how many were absorbed; the index advances past every absorbed line so they are never independently classified or emitted.

This means **every existing tier's classification of the anchor line is completely unchanged** — the new step only ever runs *after* the existing, unmodified five-tier chain has already produced a heading, and only ever consumes lines forward. Tiers 1–5 and `_classify_line()`'s own logic are not touched at all. This directly satisfies requirement #7.

### 3.3 The merge gate — every condition independently evidenced above

To absorb candidate line `N+1` into an already-classified heading at line `N`:

1. **Anchor eligibility:** line `N`'s own `LineLayout.is_bold` must be `True`. *(Confirmed by §1.5: this is what correctly excludes the "Chapter 3);" trap — that line's own layout is non-bold, so the merge attempt never even starts, regardless of what follows it. Confirmed by §1.1/1.2: both real defects' anchor lines are independently bold.)*
2. **Layout match:** line `N+1`'s `(font_size, is_bold)` from the existing `layout_index` must equal line `N`'s. *(Confirmed by §1.1/1.2: both defects show identical size/bold across every absorbed line; confirmed by §1.4: this is what excludes the body-text-wrap control, since body lines are never bold.)*
3. **Geometric continuity (either):**
   - **Same block index** (from the §3.1 extension) — the strong signal, requiring no ratio at all. *(Confirmed: all 9 Nature of Enquiry defects, including every link in the 3- and 4-line chains, are same-block.)* **OR**
   - **Cross-block fallback:** `gap_ratio` (computed against the *immediately preceding absorbed line's* bbox, not the original anchor, so multi-line chains accumulate correctly) falls within a calibrated window. Window: **-0.20 to +0.45** — a small margin around the confirmed real range (-0.160 to +0.377), still nowhere near the "20+" range that distinct, unrelated content produces. *(Confirmed by §1.2: the only cross-block defect in the entire calibration corpus is +0.377. §7's exhaustive corpus-wide sweep, run before any implementation, found exactly 7 other bold cross-block candidates corpus-wide and confirmed none of them are continuations — the nearest, +0.917, clears this window by a 0.54 margin. The window is corpus-confirmed, not merely proposed; the one remaining caveat is that positive calibration still rests on a single real example — see Risk Analysis §4.3/§7.)*
4. **Don't absorb a line that is itself clearly a new heading:** line `N+1` must not independently match `_H3_PATTERN`/`_H4_PATTERN`/`_H5_PATTERN`/`_H2_CHAPTER_PATTERN`/`_H2_KEYWORDS` (tiers 1–3). *(Defensive; no corpus case currently exercises this, but it is the direct code expression of requirement #7 — "preserve all existing tiers unless a continuation is confirmed" — for the one scenario this audit cannot rule out structurally: two genuine headings with no body text between them.)*
5. **Defensive cap:** stop after absorbing some small maximum number of continuation lines (proposed: 5, comfortably above the largest confirmed real case of 3 continuation lines for 1.11's 4-line heading) — pure insurance against a pathological document, matching this codebase's existing convention of capped absorption loops (e.g. `_MAX_AUTHOR_LINES`, `_MAX_MASTHEAD_LINES` in the front-matter extractor).

### 3.4 Joining the absorbed text

Found, not assumed: `src/structure/paragraph_grouper.py::_join_with_hyphen_repair()` already solves exactly this sub-problem (joining adjacent line fragments, hyphen-aware) for paragraph reconstruction. Reusing it is the right call for requirement #3 — **with one necessary, evidenced extension**: several real continuation lines end in a soft hyphen (U+00AD, `\xad`), not a literal `-` — e.g. heading 1.15's first line ends `'...post-\xad'`. Confirmed directly: this character survives untouched into `Page.cleaned_text` (Layer 1 sanitization correctly leaves it alone, since it is XML-legal). `_join_with_hyphen_repair()`'s existing check, `previous_text.endswith("-")`, does **not** match a trailing `\xad`, so reusing it unmodified would join as `"post-\xad structuralist"` (stray soft hyphen, plus a space, sitting inside the word) instead of `"post-structuralist"`.

Proposed: a one-line extension to strip a trailing `\xad` before the existing literal-hyphen check, inside whichever function does the joining for this feature (either by extending `_join_with_hyphen_repair()` itself — which would also incidentally improve `paragraph_grouper.py`'s own output, a welcome but out-of-scope side effect to flag for sign-off, not assume — or a small local wrapper in `heading_detector.py` that strips `\xad` before delegating). This needs an explicit decision before implementation; it is not free to assume either way.

### 3.5 Resulting heading

The merged `Heading.level` is the anchor line's own classified level (e.g. H3 for 1.16, H1 for the Aims title) — never the continuation lines' independent (and, pre-fix, incorrect) tier-4 level. `Heading.text` is the hyphen-aware join of all absorbed lines in order.

---

## 4. Risk Analysis

### 4.1 Confirmed safe: zero effect on 7 of the 10 benchmark PDFs

A corpus-wide scan for *any* bold-to-bold consecutive candidate-line pair (the only shape this feature could possibly act on) found such pairs in exactly **2** of the 10 current benchmark PDFs: Nature of Enquiry and `3. sockett_profession.pdf`. Calderhead, Fullan & Hargreaves, Brinkman, O'Leary, Teaching-as-a-Professional-Discipline, Bryman, and FolkPedagogy_Bruner have **none at all** — this feature is structurally incapable of changing their output, confirmed empirically, not assumed. Aims of Education is the brief's own second target.

Brinkman's tier-5 fallback headings (bug_002, non-bold-flagged distinct-font headings) were checked directly: all 19 are single, complete lines with no wrap. Gate 1 (anchor must be bold) does not even apply to whether tier 5 *fires* — it only gates the *new* absorption step — but since none of Brinkman's headings need absorption, this is moot for the current corpus; it would only become relevant if a future tier-5 heading happened to wrap, which is structurally possible (tier 5 permits multi-block continuation the same way Aims' tier-2 case does, since tier 5 already requires each piece be sole-line-in-its-own-block) but not currently exercised anywhere.

### 4.2 A related, but explicitly out-of-scope, finding: `sockett_profession.pdf`'s cover page

The corpus-wide scan also surfaced a decorative title-page sequence in `sockett_profession.pdf` ("The Moral" / "Core" / "of Professionalism" / "in Teaching") that is the *same defect class* — a logical title split across several short lines — but with much noisier geometry: `gap_ratio` values of -1.000, +0.273, and -1.000 across the chain (the -1.000 values come from degenerate/overlapping bboxes typical of a stylized, large-decorative-font cover page, not normal body-text wrapping).

This was **not** one of the 10 confirmed defects in the task brief, and the calibrated window (-0.20 to +0.45) only partially overlaps it: "Core" → "of Professionalism" (+0.273) would be absorbed; "The Moral" → "Core" and "of Professionalism" → "in Teaching" (-1.000 each) would not. The net effect on this page would be a partial improvement (4 fragments → 2 fragments) with **zero risk of a wrong merge**, since at least one gate already excludes every adjacent pair the brief doesn't confirm as a real wrap. Flagged here for visibility, not proposed as in-scope work — the brief's 10 defects remain the target; this is a reported side observation, not a silent scope expansion.

### 4.3 Least-evidenced part of the design: the cross-block fallback window

Gate 3's cross-block path (§3.3) is calibrated against a **single** real example (Aims' title, `gap_ratio = +0.377`). The same-block path (§3.3's primary signal) is calibrated against 9 independent real instances and is far better evidenced. If this feature is ever exercised against a PDF outside the current 10-PDF benchmark and produces an unexpected cross-block merge (or a missed one), the cross-block window is the first place to revisit — not the same-block path, and not the bold/size-match gates, which are well-evidenced across both targets and the controls.

### 4.4 Duplicate-line-text collision (pre-existing pattern, slightly elevated stakes here)

`_build_layout_index()`'s indices are keyed by exact line **text**, not by position — an existing, already-accepted limitation shared by the font/bold lookup this feature reuses unchanged. For font/bold lookup, a same-text collision is low-consequence (worst case: a line gets another occurrence's identical style, usually correct anyway). For continuation-merging specifically, a same-text collision could in principle attribute the wrong bbox to a line and produce a wrong merge decision. No instance of this exists anywhere in the current 10-PDF corpus (confirmed: every line text involved in every absorption candidate above is unique on its page). Not blocking; noted as the one place where the existing index's known limitation has marginally higher stakes than its current uses.

### 4.5 Pre-existing, unrelated bug surfaced by this audit (not in scope)

The "Chapter 3);" line (§1.5) is *already*, today, independently of this feature, misclassified as H2 by tier 3. This audit's design correctly avoids making it worse, but does not fix it — that is a separate, pre-existing defect (tier 3's `_H2_CHAPTER_PATTERN` has no bold/layout gate at all) outside this feature's scope. Flagged for awareness, not bundled into this implementation.

---

## 5. Expected Benchmark Impact

| PDF | Before | After (predicted) |
|---|---|---|
| `1. Nature of Enquiry.pdf` | 9 logical headings rendered as 9 H3/H4-tier headings + 12 spurious extra H2 fragments (3 headings need 2 extra lines absorbed each ×6, 2 lines absorbed ×2, 1 needs 3 lines absorbed ×1 — 1+1+3+2+2+1+1+1+1 = 13 continuation lines total across 9 headings) | Each of the 9 becomes one correctly-leveled heading (H3, matching the numbering tier); 13 spurious H2 fragments removed from `document.headings` |
| `1.Aims of Education and the teacher...pdf` | Title split into H1 + spurious H2 | Single H1, full title text, correctly joined |
| All other 8 benchmark PDFs | — | No change (confirmed §4.1: structurally no bold-adjacent pairs exist) |
| `3. sockett_profession.pdf` | Decorative cover title in 4 fragments | Partial improvement to 2 fragments (§4.2) — a side effect, not a target |

Downstream effects, not yet verified against generated Markdown/DOCX (would need implementation + regression run, per req "do not modify code yet"): fewer, more accurate entries in `Document.headings` should improve `HEADING_001` (hierarchy-jump) signal quality for these two PDFs, since the spurious H2 fragments currently sitting directly under an H3 are a textbook hierarchy-jump shape; full validation-report impact should be measured after implementation, not predicted here.

---

## 7. Cross-Block Calibration Sweep (2026-06-25, before implementing §3.3's cross-block fallback)

Per explicit instruction, no cross-block logic was implemented until this sweep was run. Searched **every** adjacent candidate-line pair (in document reading order, materialized per page exactly as §3.2 proposes processing them) across all 10 benchmark PDFs for: different block index, same font family, same font size, same bold state, and a generous gap-ratio window (-2.0 to +6.0, then re-checked with no upper bound at all to be certain nothing was missed just outside that window).

**Result: 8 total candidates corpus-wide — 1 confirmed continuation, 7 confirmed non-continuations. No additional calibration examples for "real cross-block wrap" exist anywhere in the current corpus.**

The non-bold population (922 pairs, almost entirely ordinary justified body-paragraph text split across blocks at column/page boundaries) was counted but not individually classified — it is irrelevant to this feature, since gate 1 (§3.3) already requires the anchor line to be bold, which structurally excludes all of it. Its size alone is further confirmation of why gate 1 is load-bearing: without it, this fallback path would have 922 opportunities to misfire for every 1 real case.

| Document | Page | Line 1 | Line 2 | Size | Bold | gap_ratio | Human classification |
|---|---|---|---|---|---|---|---|
| `1. Nature of Enquiry.pdf` | 1 | "Setting the field" | "CHAPTER 1" | 18.0 | Yes | **-2.317** | **Separate heading.** Two distinct title-page masthead elements (a subtitle at x0=53.5, y0=63.1, and a chapter label at x0=373.8, y0=34.9) — confirmed via direct geometry that "CHAPTER 1" actually sits *above* "Setting the field" on the page; PyMuPDF's block-emission order doesn't match visual top-to-bottom order here (a reading-order quirk, the same class of thing `PAGE_003` already exists to flag). Not a wrap by any reading. |
| `1.Aims of Education and the teacher...pdf` | 1 | "AIMS OF EDUCATION: DO TEACHERS NEED" | "TO BOTHER ABOUT THEM?" | 16.0 | Yes | **+0.377** | **Continuation.** The confirmed target case (§1.2). |
| `2.FolkPedagogy_Bruner_PsychDimensions_New.pdf` | 5 | "FOLK PEDAGOGY" | "47" | 12.0 | Yes | +1.083 | **Separate heading.** Confirmed via direct geometry: a running header ("FOLK PEDAGOGY", centered, y0=53.8) stacked directly above that page's page number ("47", y0=78.8) — two different semantic elements (running title + page number) in a decorative two-line masthead, not one heading wrapped across lines. |
| `2.FolkPedagogy_Bruner_PsychDimensions_New.pdf` | 7 | "FOLK PEDAGOGY" | "49" | 10.0 | Yes | +1.500 | **Separate heading.** Same running-header/page-number pattern as above (recurs each page). |
| `2.FolkPedagogy_Bruner_PsychDimensions_New.pdf` | 9 | "FOLK PEDAGOGY" | "51" | 10.0 | Yes | +1.500 | **Separate heading.** Same pattern. |
| `2.FolkPedagogy_Bruner_PsychDimensions_New.pdf` | 15 | "FOLK PEDAGOGY" | "57" | 10.0 | Yes | +1.500 | **Separate heading.** Same pattern. |
| `2.FolkPedagogy_Bruner_PsychDimensions_New.pdf` | 16 | "THE CULTURE OF EDUCATION" | "58" | 12.0 | Yes | +1.000 | **Separate heading.** Same running-header/page-number pattern, different running title (this document's running header changes partway through, consistent with a part/section change). |
| `2.FolkPedagogy_Bruner_PsychDimensions_New.pdf` | 20 | "THE CULTURE OF EDUCATION" | "62" | 12.0 | Yes | +0.917 | **Separate heading.** Same pattern. |

No "title/byline" or "unknown" classification was needed — every candidate resolved cleanly to one of the other two categories on direct inspection.

### Conclusion: the proposed §3.3 window holds, with comfortable margin on both sides

The single genuine continuation (+0.377) and the nearest false candidate (+0.917, "THE CULTURE OF EDUCATION"/"62") are separated by a margin (0.54) wider than the entire proposed window itself (-0.20 to +0.45, width 0.65). Every one of the 7 false candidates falls outside that window already — none require the window to be narrowed further than originally proposed. The window does not need adjustment based on this sweep.

**What this sweep changes vs. §4.3's original risk note:** the cross-block path is still calibrated against only **one** positive example — that has not changed, and remains the least-evidenced part of the design. What has changed is the negative evidence: this was previously an assumption ("no other PDF in the corpus has this shape"); it is now a confirmed, exhaustive, corpus-wide fact (8 candidates found and individually classified, not sampled). The risk in §4.3 should be read as "narrow positive calibration, now corpus-confirmed as narrow rather than assumed narrow" — the recommendation to revisit this window first if a future document misbehaves still stands.

A second, useful side finding: the "Setting the field"/"CHAPTER 1" pair on Nature of Enquiry's own title page is a real instance of `gap_ratio` going strongly negative (-2.317) for two *unrelated* bold elements — confirming the lower bound of the proposed window (-0.20) also has real, corpus-evidenced separation to lean on, not just the body-text-wrap controls from §1.4.

---

## 8. Open Decisions Needed Before Implementation

1. ~~Cross-block `gap_ratio` window bounds~~ — **resolved by §7's exhaustive sweep.** -0.20 to +0.45, corpus-confirmed against all 8 real bold cross-block candidates that exist anywhere in the benchmark corpus (not just the 1 positive example), with a 0.54 margin to the nearest false candidate. No further confirmation needed before implementation.
2. ~~Soft-hyphen join handling~~ — **resolved: local, heading-only helper.** User chose a local wrapper (`_join_with_local_hyphen_repair()`) over extending the shared `paragraph_grouper.py` helper, to avoid coupling this feature's behavior into the paragraph-grouping path.
3. ~~Defensive absorption cap~~ — **resolved: 4 lines** (not the originally-proposed 5). Sufficient for the corpus's longest confirmed chain (1.11, a 4-line wrap).
4. ~~Confirm `sockett_profession.pdf`'s side effect is acceptable~~ — **resolved: accepted as-is.** Actual effect was *larger* than §4.2 predicted (full merge of all decorative title/category fragments, not a partial 2-fragment merge — see §9.2 for why), because these fragments are same-block, and the same-block gate (§3.3 gate 3) bypasses the gap-ratio check entirely by design. Confirmed not a benchmark regression: neither `tests/test_pipeline.py` nor `tests/test_validation.py`'s sockett-specific assertions touch heading content/count (they assert validation-issue parity and `PAGE_003` anomaly counts only).

---

## 9. Implementation & Verification (2026-06-25)

### 9.1 Code changes

`src/headings/heading_detector.py`: added `_CROSS_BLOCK_GAP_RATIO_MIN/MAX` (-0.20/+0.45) and `_MAX_CONTINUATION_LINES` (4) module constants; extended `_build_layout_index()`'s `bbox_index` to carry `block_index` (`Tuple[int, float, float]` instead of `Tuple[float, float]`); restructured `detect_headings()`'s per-page loop to an index-based `while` loop so absorbed lines can be skipped; added `_absorb_continuations()`, `_matches_new_heading_pattern()`, `_is_confirmed_continuation()`, and `_join_with_local_hyphen_repair()`.

### 9.2 Document-by-document benchmark re-run

Re-ran heading detection on all 10 benchmark PDFs, comparing against a true "before" baseline (absorption disabled via monkeypatch, not a prediction):

| PDF | Before → After | Result |
|---|---|---|
| `1. Nature of Enquiry.pdf` | 48 → 35 headings | All 9 confirmed wraps merged correctly, including the 4-line (`1.11`) and 3-line (`1.12`, `1.13`) chains and the soft-hyphen repairs (`post-\xadpositivism` → `Post-\xadpositivism` heading text unaffected since hyphen is mid-word here; `1.15` correctly becomes `Postmodernist and post-structuralist perspectives` with no stray soft hyphen or space). `Chapter\xa03);` trap remains correctly un-absorbed as an isolated H2, exactly as designed — it did not begin absorbing the following body paragraph. |
| `1.Aims of Education and the teacher...pdf` | 3 → 2 headings | Title fully merged into one H1 (`AIMS OF EDUCATION: DO TEACHERS NEED TO BOTHER ABOUT THEM?`); `Rohit Dhankar` byline correctly remains un-absorbed (different font size, fails the layout-equality gate). |
| `2. Social research strategies Bryman.pdf` | 0 → 0 | No change. |
| `2.FolkPedagogy_Bruner_PsychDimensions_New.pdf` | 3 → 3 | No change — confirms the 6 "running header + page number" cross-block candidates from §7's sweep are correctly excluded by the calibration window (their ratios, +0.92 to +1.50, all fall outside +0.45). |
| `3. sockett_profession.pdf` | 21 → 15 | **Larger improvement than §4.2 predicted.** `"The Moral"/"Core"/"of Professionalism"/"in Teaching"` (4 fragments) merges fully into one heading, and `"PROFESSIONALISM"/"AND"/"PROFESSIONALIzATION"` (3 fragments) merges fully into one, not the partial 2-fragment merge originally predicted. Root cause: these decorative cover-page fragments are same-block (not cross-block, as §4.2 implicitly assumed when reasoning from gap_ratio) — gate 3's same-block path bypasses the ratio check entirely, so all same-block bold-adjacent lines merge unconditionally up to the 4-line cap. Confirmed harmless and not a benchmark regression (§8.4). |
| `4. O Leary_Developing the research questions.pdf` | 0 → 0 | No change. |
| `4.Teaching as a professional discipline-Chapter 1.pdf` | 10 → 10 | No change. |
| `5.Teachingas a profession_Calderhead.pdf` | 2 → 2 | No change. |
| `6. Fullan&Hargreaves_teacherasaperson.pdf` | 2 → 2 | No change. |
| `7.brinkman-learner-centred-education-reform-india-missing-beliefs.pdf` | 20 → 20 | No change — confirms bug_002's tier-5 fallback headings have no wraps in the current corpus, as predicted in §4.1. |

### 9.3 Fast-subset test suite

`pytest -m "not real_docling and not real_surya"` re-run after implementation: clean, no failures (see `docs/DECISIONS_LOG.md` for the exact pass count recorded at sign-off).
