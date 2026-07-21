# H-001 — Heading Reproducibility Investigation

> **RESOLVED 2026-07-20.** Both outstanding items named in §Final Questions are closed:
> the full suite ran green (**1645 / 0 failed / 7 skipped / 37m46s**, vs 1617/1/7/42m58s
> baseline), and the five regression cases are written and passing
> (`tests/test_front_matter_roles.py`, 21 tests). §4's "highest-priority next task" is done.
> This report's recommendation — clear `__pycache__` before any before/after measurement —
> is now mandatory in `RAWRS_ENGINEERING_STANDARD.md`.

**Date:** 2026-07-20 · **Type:** investigation, no production change · RES v1

---

## Investigation Summary

**Native heading generation IS reproducible.** Every configuration produced byte-identical heading lists across repeated runs and across a backend restart.

**The "split title" never existed in any committed or working-tree state.** It was an artifact of **stale Python bytecode**: the earlier "HEAD baseline" test stashed the source files but did not clear `src/**/__pycache__`, so the backend imported `.pyc` from a mixed state that corresponded to no actual code version.

This corrects **two** of my previous conclusions, in opposite directions:

| Report | Claim | Verdict |
|---|---|---|
| FE-0-005/006 implementation | "FE-0-005 introduced the title split" | **WRONG** |
| FE-0-005 investigation | "The split is pre-existing at HEAD" | **ALSO WRONG** |

Both rested on measurements taken against contaminated bytecode. The split belongs to neither version.

---

## Environment Matrix

| Property | Value |
|---|---|
| Commit | `a30fa7a` (branch `master`) |
| Python | 3.11.14 |
| Dependencies | `requirements.lock`, 124 packages (P0-1) |
| Job storage | disk-backed; survives restart |
| Bytecode cache | `src/**/__pycache__` — **survives restart, not invalidated by `git stash`** |
| Backend | `uvicorn`, no `--reload` |
| Input | `1.Aims of Education and the teacher_Dhankar_PhilPers (1).pdf`, `enable_ocr=false` |

Controls applied before each configuration: all `uvicorn` processes terminated (listener count verified 0), all `src/**/__pycache__` removed (count verified 0), backend PID recorded.

---

## Reproducibility Results

### Config A — working tree with FE-0-005/006, clean bytecode, backend pid 6556

| Run | Headings |
|---|---|
| 1 | 1 — `['AIMS OF EDUCATION: DO TEACHERS NEED TO BOTHER ABOUT THEM?']` |
| 2 | identical |
| 3 | identical |

### Config B — same tree, **backend restarted**, pid 21984

| Run | Headings |
|---|---|
| 4 | 1 — `['AIMS OF EDUCATION: DO TEACHERS NEED TO BOTHER ABOUT THEM?']` |
| 5 | identical |

### Config C — **true HEAD** (files stashed), clean bytecode, pid 8060

| Run | Headings |
|---|---|
| 6 | 2 — `['AIMS OF EDUCATION: DO TEACHERS NEED TO BOTHER ABOUT THEM?', 'Rohit Dhankar']` |
| 7 | identical |

**Within every configuration: 100% identical. Across restart: identical.**

---

## Divergence Analysis

The two code versions differ exactly as designed, and no more:

| | Title | Byline |
|---|---|---|
| HEAD (Config C) | joined ✅ | present as H2 ❌ |
| FE-0-005/006 (Config A/B) | joined ✅ | **excluded** ✅ |

The title is joined in **both**. `_absorb_continuations()` works correctly in both. The only difference is byline exclusion — precisely FE-0-006's intended effect, and nothing else.

**Config C reproduces the original FE-0-004-era observation exactly** (`joined title + 'Rohit Dhankar'`). That historical measurement was correct all along.

The anomalous split appeared only in runs where source files had changed but `__pycache__` had not been cleared.

---

## Root Cause Candidates

| Candidate | Verdict | Evidence |
|---|---|---|
| **Stale Python bytecode** | **Confirmed** | Split reproduced only with un-cleared `__pycache__` after `git stash`; never reproduced in 7 runs with cleared cache across 3 configs |
| Genuine nondeterminism | **Ruled out** | 7/7 identical within configuration |
| Stale backend process | **Ruled out** | PIDs recorded per config (6556 / 21984 / 8060); listener count verified 0 before each start |
| Persisted job state | **Ruled out** | Each run created a new job; results identical across restarts |
| Different commit / input / config | **Ruled out** | Same commit `a30fa7a`, same PDF, same `enable_ocr=false` |
| OCR / model cache | **Ruled out** | `enable_ocr=false`; no OCR executed |

### Why `git stash` + stale bytecode produces a state matching no version

`git stash` rewrites source `.py` files but leaves `.pyc` files whose invalidation is per-module. Modules whose source changed get recompiled; modules that did not, do not. The importer therefore assembled a mix of HEAD and FE-0-005 modules. That combination — FE-0-006's byline exclusion active while continuation repair ran against mismatched helper state — is not a state any commit can produce.

**Confidence: Confirmed** for the mechanism class (stale bytecode); **Highly Likely** for the precise module-level mix, which I did not enumerate per-module.

---

## Confidence Levels

| Conclusion | Confidence |
|---|---|
| Native heading generation is reproducible | **Confirmed** — 7/7 across 3 configs |
| Reproducible across backend restart | **Confirmed** — Config A vs B |
| The split was a stale-bytecode artifact | **Confirmed** |
| FE-0-005/006 behaves as designed | **Confirmed** — title joined, byline excluded |
| Exact per-module bytecode mix | **Highly Likely** — not enumerated |

---

## Remaining Unknowns

1. **Which specific modules were stale.** Not enumerated; would need `.pyc` mtime forensics on a state now destroyed.
2. **How many earlier session measurements were contaminated.** `__pycache__` was cleared only in this investigation. Any measurement taken after an edit without a cache clear carries the same risk — including parts of FE-0-004's validation, though its markdown byte-identity check and 426-test pass are independent corroboration.
3. **Whether `git stash`-based A/B testing is safe here at all.** On this evidence, not without a cache clear between every switch.

---

## Recommendation

Adopt as standing practice, and add to RES §5: **clear `src/**/__pycache__` and restart the backend before any before/after measurement.** Two consecutive wrong root causes in this project trace to skipping it. Cost is seconds; the error mode is silent and produces confident, plausible, wrong results.

The FE-0-005 investigation report needs the same retraction header it applied to its predecessor.

---

## Final Questions

### 1. Is native heading generation reproducible?

**YES.** Seven runs across three configurations and one backend restart produced byte-identical heading lists within every configuration. Zero variance observed.

### 2. Can future heading investigations rely on deterministic behaviour?

**Yes — provided bytecode is cleared between code changes.** The determinism is real; the observation apparatus was the defect. With a cache clear and process restart, results are trustworthy and repeatable.

### 3. What must be corrected before FE-0-005/006 continues?

Nothing in the code. **FE-0-005/006 works correctly** — Config A/B show the title joined and the byline excluded, exactly as designed. What must be corrected is the *record*: the "native title split regression" does not exist and both prior reports overstate it.

The genuine outstanding items are unchanged from the original report, and neither is a defect: **the full regression suite has never completed** for FE-0-004 or FE-0-005/006, and **the five required regression tests are unwritten**.

### 4. Highest-priority next engineering task

**Run the full regression suite** against the current tree (FE-0-004 + FE-0-005/006 together), with cleared bytecode, comparing to the `1617 passed / 1 failed / 7 skipped` baseline.

It is the last gate on two otherwise-complete changes, it has been started and abandoned twice, and RES §6 makes it a Not-Done condition. Writing the FE-0-005/006 regression tests follows immediately after — and can now be written against behaviour confirmed correct rather than against a phantom defect.
