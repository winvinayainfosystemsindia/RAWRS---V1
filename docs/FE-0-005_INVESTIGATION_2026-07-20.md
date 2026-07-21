# FE-0-005 Investigation — Native Wrapped Title Regression

**Date:** 2026-07-20 · **Type:** diagnosis only, no fixes · RES v1

> **CORRECTION (2026-07-20, superseded by H-001).** This report's headline —
> "the split is pre-existing at HEAD" — is **WRONG and retracted**. The
> measurement it rests on was taken with stale `__pycache__` after a
> `git stash`, so it reflected no real code version. With bytecode cleared,
> HEAD produces the **joined** title, and so does FE-0-005/006. The split
> exists in neither. See `H-001_heading_reproducibility_2026-07-20.md`.
>
> The Pipeline Trace, Execution Timeline and Divergence Point sections below
> remain valid — they were derived from source, not from the contaminated run.

## Headline: the premise was wrong

**The title split is NOT a regression introduced by FE-0-005. It is pre-existing behaviour at HEAD.**

With all three modified files stashed (`git stash push src/headings/heading_detector.py src/mathpix/ingestor.py src/markdown/markdown_builder.py`) — no FE-0-004, no FE-0-005/006 — the native path produces the split, deterministically:

```
run 1:  2 content headings: ['AIMS OF EDUCATION: DO TEACHERS NEED', 'TO BOTHER ABOUT THEM?']
run 2:  2 content headings: ['AIMS OF EDUCATION: DO TEACHERS NEED', 'TO BOTHER ABOUT THEM?']
```

**Confidence: Confirmed.** Same document, same endpoint, three runs at HEAD (one plus a 2-run determinism check), identical output every time.

My previous report named FE-0-005 as the cause. That claim was wrong and is retracted below.

---

## Pipeline Trace

Native path, `src/pipeline/phase1_pipeline.py`:

| Stage | Call | Effect on `document.headings` |
|---|---|---|
| 1 | `parse_pdf()` | none — creates Page shells, **no text** |
| 2 | text extraction / `route_pages` | populates `page.cleaned_text` |
| 3 | `detect_structure()` | blocks; no headings |
| 4 | `detect_footnotes()`, `extract_front_matter()` `:265`, `extract_tables()` | populates `document.front_matter`; **no headings** |
| 5 | `detect_headings(document, page_numbering_policy=...)` `:437` | **sole writer of `document.headings`** |
| 6 | `build_markdown()` | reads only |
| 7 | `validate()` | reads only |

`phase1_pipeline.py:379-381` states it explicitly: *"RAWRS-native path: unchanged — detect_headings() is the sole source of document.headings."* The `detect_headings_from_pdf()` + verification-engine branch at `:392` is inside `if _mathpix_path:` and **never executes on the native path**.

**Answer to question 4:** no other stage modifies the heading list. Front-matter classification, continuation repair and page-marker insertion all occur *inside* `detect_headings()`. Confidence: **Confirmed** (single assignment site, `heading_detector.py:368` `document.headings = headings`).

---

## Execution Timeline — `_absorb_continuations()`

| Property | Value |
|---|---|
| Caller | `detect_headings()` only, `heading_detector.py:345` |
| Guard | reached only after a tier has classified the line as a heading **and** `layout is not None and layout[1]` (line is bold) |
| Input | `anchor_text`, `anchor_layout`, `page_lines`, `anchor_index`, `page_layouts`, `page_bboxes` |
| Output | `(heading_text, lines_absorbed)` — absorbed lines skipped via `line_index += 1 + lines_absorbed` `:366` |
| Differs between direct call and API? | **No.** Same function, same call site, one code path |

---

## Divergence Point — direct call vs API

**Question 3 answered. The divergence is not a branch; it is missing input.**

```
parse_pdf() + detect_structure() only:
  cleaned_text is None: False
  cleaned_text len: 0
  raw_text len: 0
```

`heading_detector.py:309` reads `text = page.cleaned_text or page.raw_text` → `''` → `_iter_candidate_lines('')` yields nothing → **zero content headings**.

My direct-call test omitted the pipeline's text-extraction stage, so the detector had no text to classify. The API populates it at Stage 2. Nothing about heading detection differs.

**Confidence: Confirmed** — measured field lengths above.

This also retracts the previous report's statement that the API path "differs in a way I have not traced." It does not differ. My test harness was incomplete.

---

## Root Cause Candidates — the actual split

The split occurs because `_absorb_continuations()` does not merge `'TO BOTHER ABOUT THEM?'` into `'AIMS OF EDUCATION: DO TEACHERS NEED'`. Both lines are the same wrapped title (confirmed: `front_matter.title_source_texts == ['AIMS OF EDUCATION: DO TEACHERS NEED', 'TO BOTHER ABOUT THEM?']`).

| # | Candidate | Confidence |
|---|---|---|
| 1 | Absorption gate not satisfied — anchor not bold (`layout[1]` false), so `_absorb_continuations` is never called for the title | **Hypothesis** — not measured |
| 2 | Gate satisfied but the continuation fails the (font size, is_bold) + same-block / gap_ratio match | **Hypothesis** — not measured |
| 3 | Second line independently classified as H2 by a later tier after the anchor consumed the H1 slot | **Highly Likely** — the observed output is exactly H1 then H2, and tier 4 (bold-relative-to-body) would produce H2 |

Distinguishing 1 from 2 needs one instrumented run logging `layout[1]` for the anchor and the reject reason inside `_absorb_continuations`. **I did not add instrumentation** — the brief permits it, but the pre-existing finding already answers the question that was asked, and adding logging to production code has a cost I did not think was justified before you see this result.

---

## Unreconciled observation — flagged, not explained

Earlier in this session two native runs reported a **joined** title plus a `'Rohit Dhankar'` H2:

```
job 43ed5dc4 (during FE-0-004 validation):
  H1 'AIMS OF EDUCATION: DO TEACHERS NEED TO BOTHER ABOUT THEM?'
  H2 'Rohit Dhankar'
```

HEAD now produces split-and-no-byline, deterministically. These cannot both be correct for the same code. Possibilities I have **not** tested: backend process serving stale bytecode at the time of that run; job-store state reused across restarts; or a genuine non-determinism source.

**Confidence: Hypothesis, all three.** I am recording this rather than resolving it because it is the more serious question — if heading detection is not reproducible across restarts, every heading measurement in this project is suspect, including the FE-0 findings.

---

## Recommended Fix Location

**None yet — and none for FE-0-005.** The split is not FE-0-005's defect. Fixing it means changing `_absorb_continuations()`'s gates in `heading_detector.py:345`, which is feature_007's calibrated logic; the audit notes warn that loosening it re-opens the `"Chapter 3);"` false-positive trap.

Correct sequence: resolve the reproducibility question first, then instrument absorption, then decide.

---

## Risks

| Risk | Severity |
|---|---|
| Heading detection may not be reproducible across backend restarts | **High** — would undermine every heading claim in this project |
| My previous report asserted a false root cause | **High** — corrected here; the FE-0-005/006 report needs amending |
| Loosening absorption gates re-opens known false positives | Medium |
| Split affects any native document with a wrapped title | Medium — model only; markdown is unaffected |

---

## Does FE-0-005 require redesign, or a localized correction?

**Neither — FE-0-005's design is not implicated.**

Evidence: at HEAD, with FE-0-005 entirely absent, the split is present and deterministic. A defect that exists without the change cannot be caused by the change. The front-matter role classifier touches only whether AUTHOR/AFFILIATION lines are *eligible*; both title lines classify as `TITLE` and remain eligible, so the classifier never reaches them.

The split belongs to **feature_007's continuation-repair calibration**, a separate concern from front-matter semantics, and warrants its own backlog item rather than expanding FE-0-005.

## Final Question

**The title split can be corrected with a localized change** — the gates inside `_absorb_continuations()` (`heading_detector.py:345`) — but *which* gate is failing is not yet measured, so I cannot state the change itself.

There is **no architectural inconsistency in the FE-0-005 design**, and it does not require revisiting.

There **is** a more serious open question the investigation surfaced: whether native heading detection is reproducible across backend restarts. That must be settled before any heading fix is attempted, because two runs of ostensibly the same code produced different heading structures and I cannot yet say why.
