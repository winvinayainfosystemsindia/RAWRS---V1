# RAWRS Engineering Execution Standard (RES v1)

**Status:** governing · **From:** 2026-07-19 · Applies to every Master Implementation Backlog item.

Reference this document; do not restate it in task reports.

---

## 1. Implementation Principles

| # | Principle | Why it exists here |
|---|---|---|
| P1 | **Measure, don't reason.** | Three claims this project made from reasoning were wrong by measurement: ">5 min" suite was 42m58s; "structure tree mandatory" collapsed on checking output targets; a "<10 min" test tier measured ~23 min. |
| P2 | **Run the thing.** | Six planning documents code-traced the frontend and missed all 13 FE-0 defects, 4 of them P0. Code tracing cannot verify runtime behaviour. |
| P3 | **Re-test ambiguous results before recording them.** | FE-0 nearly filed a false CRITICAL ("Accept produces Reject") from two errored clicks. A clean retest disproved it. |
| P4 | **One backlog item per commit.** | No drive-by fixes. Discovered issues get recorded, not silently fixed — unless they block the current item. |
| P5 | **Root cause, not symptom.** | Fix where all callers route through. FE-0-004's fix is in Mathpix ingest, not in the validator that reports it. |
| P6 | **Reversible by default.** | Every task states a rollback that works without migration or manual repair. |
| P7 | **Absent evidence is stated, never assumed.** | "Not verified" is an acceptable report line. A confident claim without evidence is not. |

---

## 2. Engineering Lifecycle

| Stage | Entry criteria | Exit criteria |
|---|---|---|
| **Backlog** | Item exists in MIB with ID, category, priority, effort, dependency | — |
| **Ready** | Deps closed; acceptance criteria written and testable; baseline captured if measurable | Named engineer can start without asking a question |
| **In Progress** | Branch created; item is the *only* thing in scope | Code written; self-review done |
| **Implementation Complete** | Acceptance criteria addressed in code | Diff limited to the item; no unrelated changes |
| **Validation** | Suite runnable; baseline known | Acceptance criteria **demonstrated with evidence** (§4) |
| **Code Review** | Validation evidence attached | Review checklist (§7) answered; CRITICAL/HIGH resolved |
| **Accepted** | Review passed | Report published; MIB status updated |
| **Closed** | Merged | Docs updated; discovered issues filed as new MIB items |

**Blocked** is a valid state from any stage. It records: what blocks, which item unblocks it, and whether a workaround exists.

---

## 3. Reporting Template

Every implementation task produces one report at `docs/<ITEM-ID>_<slug>_<date>.md`:

```markdown
# <ITEM-ID> — <Title>

**Date:** · **Scope:** · **Status:**

## Objective
## Scope  (in scope / explicitly out of scope)
## Files Modified          (table: file | change)
## Design Decisions        (decision | alternatives | why)
## Implementation Summary
## Acceptance Criteria     (table: criterion | met? | evidence ref)
## Validation Performed    (§5)
## Evidence                (§4 — command + verbatim output)
## Known Limitations
## Rollback Strategy       (exact commands)
## Remaining Risks         (table: risk | severity | mitigation)
## Next Dependent Task
```

Sections with nothing to report say **"None"** — they are never deleted.

---

## 4. Evidence Standard

Every claim carries evidence of one of these kinds:

test results · benchmark numbers · screenshots · API responses · logs · before/after output · `file:line` code references · performance measurements

**Rules**
1. Evidence is **verbatim**. Paste the command and its output; never paraphrase a result.
2. A claim without evidence is written as *"Not verified — <reason>."*
3. Truncated or interrupted runs are **not** results. Extrapolating from them caused the 43-minute error.
4. Background/parallel command exit codes are verified explicitly — a piped `tail` masks a failing `pytest`.

**Root cause confidence** — every defect states all four:

| Field | Requirement |
|---|---|
| Observed behaviour | What actually happened, with evidence |
| Expected behaviour | What should happen, and per which spec/standard |
| Root cause | The mechanism, at `file:line` where possible |
| **Confidence** | **Confirmed** (evidence proves the mechanism) · **Highly Likely** (strong indirect evidence, mechanism unverified) · **Hypothesis** (plausible, untested) |

Never label a Hypothesis as Confirmed. Promote it only by testing the mechanism.

*Worked example — FE-0-004 reached **Confirmed** by reading rapidocr's `default_models.yaml` and showing PP-OCRv6 exists under `onnxruntime` but not `torch`. Before that read it was **Highly Likely**.*

---

## 5. Validation Standard

**A task is not complete because code was written. It is complete when its acceptance criteria are demonstrated.**

| Type | When required | Minimum |
|---|---|---|
| Functional | Always | Each acceptance criterion exercised and shown |
| Regression | Always | Full suite vs. known baseline; deviations explained |
| Performance | Perf-affecting change | Before/after measurement, same machine |
| Accessibility | Reviewer-facing or output-affecting change | WCAG 2.2 / PDF-UA check on the affected surface |
| **Live** | **Any change to reviewer-facing behaviour** | **Click-through against a running app — code tracing is not validation (P2)** |

**Baseline (2026-07-20):** `1645 passed, 0 failed, 7 skipped` in `37m46s`. **Any failure is now a regression** — there is no longer a tolerated red test. `test_oleary_single_page_recovers_real_text` was fixed by P0-1 dependency pinning and now passes.

*Superseded baseline (2026-07-19): `1617 passed, 1 failed, 7 skipped` in `42m58s`.*

**Measurement protocol (mandatory, added per H-001).** Before any before/after measurement: clear `src/**/__pycache__` and restart the backend. Two consecutive wrong root causes in this project trace to skipping this. `git stash` does not invalidate bytecode, and the resulting module mix corresponds to no commit — the failure mode is silent and produces confident, plausible, wrong results.

**Benchmark standard** — if a change could affect performance, OCR, classification, validation, rendering or review workflow, take before/after measurements. Prefer measurement over reasoning (P1).

---

## 6. Completion Checklist & Definition of Done

**Definition of Done** — all nine true:

1. Acceptance criteria demonstrated with evidence
2. Full suite run; result matches baseline or every deviation is explained
3. Diff contains only this backlog item
4. Report published using the §3 template
5. MIB status updated; no duplicate entries
6. Discovered issues filed as new MIB items (not silently fixed)
7. Rollback stated and plausible
8. Decision log updated if an architectural choice was made
9. Live verification done if the change is reviewer-facing

**Not Done if:** code written but unvalidated · "should work" · suite not run · report predicts results not yet observed · unrelated fixes in the diff.

---

## 7. Code Review Checklist

| Question | Fail condition |
|---|---|
| Satisfies acceptance criteria? | Any criterion unmet or unevidenced |
| Introduces technical debt? | New debt undeclared in Known Limitations |
| Reduces reviewer effort? | Adds steps to the remediation workflow |
| Preserves accessibility? | Regresses WCAG 2.2 / PDF-UA, or degrades the a11y tree |
| Preserves architecture? | Contradicts an ADR without a superseding decision |
| Increases maintainability? | File >800 ln, function >50 ln, nesting >4 |
| Could it be simpler? | A stdlib/existing helper does the same job |

Severity: **CRITICAL** blocks merge · **HIGH** should block · **MEDIUM** fix if cheap · **LOW** optional.

---

## 8. Repository Conventions

| Area | Convention |
|---|---|
| Branch | `<item-id>-<slug>`, e.g. `p0-1-dependency-pinning` |
| Commit | `<type>: <description>` — feat, fix, refactor, docs, test, chore, perf, ci |
| Commit body | What changed and **why**; reference the item ID |
| Reports | `docs/<ITEM-ID>_<slug>_<date>.md` |
| Governing docs | `docs/` — ADR, MIB, RES. Never duplicated |
| Deps | Pinned in `requirements*.txt`; full graph in `requirements.lock`; regenerate on any intentional change |
| Env | Backend `:8001` (per `frontend/.env.local`), frontend `:3000` |
| Test markers | `real_docling`, `real_surya` for network/inference tests |
| Code | Files <800 ln · functions <50 ln · nesting ≤4 · no hardcoded secrets · errors handled explicitly |

**Documentation rule:** update the existing document. Never create a second document covering the same ground.

---

## 9. When to Deviate

Deviation is allowed when the standard costs more than it protects — a one-line typo fix does not need a benchmark. **State the deviation and why in the report.** Silent deviation is not permitted.

The standard is a floor for correctness, not a ceremony to perform.
