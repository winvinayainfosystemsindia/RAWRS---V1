# Engineering Readiness Report — Phase 0

Governing architecture: `ADR_2026-07-19.md`. No architecture changed here. One ADR *success criterion* is refined on implementation evidence (§3, DOCX comparison) — the decision itself stands.

---

## 1. Dependency Stability

### Root cause of D5

| Fact | Evidence |
|---|---|
| `docling` is **unpinned** | `requirements.txt:5` — bare `docling`, no specifier |
| `rapidocr` is **undeclared** | Not in any requirements file; arrives transitively via docling |
| `surya-ocr` **is** pinned | `requirements.txt:6` — `surya-ocr==0.20.0` |
| `torch`/`transformers` unpinned | `requirements-ai.txt:12-13` |

An unpinned `docling` resolved to 2.87.0, which pulled `rapidocr` 3.9.0, in which the model identifier `PP-OCRv6.det.small` is unsupported on the torch backend. **The project pinned the OCR engine it declared and left the one it didn't declare free to drift.**

### Installed matrix (verified)

| Package | Installed | Currently pinned | Action |
|---|---|---|---|
| docling | 2.87.0 | ✗ | **Pin `==2.87.0`** |
| docling-core | 2.85.0 | ✗ (transitive) | Lockfile |
| docling-ibm-models | 3.13.3 | ✗ (transitive) | Lockfile |
| docling-parse | 5.11.0 | ✗ (transitive) | Lockfile |
| **rapidocr** | **3.9.0** | ✗ **undeclared** | **Declare + pin — D5's direct cause** |
| surya-ocr | 0.20.0 | ✅ | Keep |
| torch | 2.12.1 | ✗ | Pin `==2.12.1` |
| torchvision | 0.27.1 | ✗ | Pin |
| transformers | 4.57.6 | ✗ | Pin |

### Upgrade policy

**Anything that loads a model weight is pinned exactly.** Model identifiers are part of a library's public API in practice but are versioned as if private — `PP-OCRv6.det.small` disappearing in a minor bump is the proof. Floating ranges are acceptable only for pure-python utility libraries.

Generate `requirements.lock` via `pip-compile`; CI installs from the lock, not the loose files.

### D5 remedy — two options

| Option | Effort | Recommendation |
|---|---|---|
| Pin rapidocr to the last version supporting `PP-OCRv6.det.small` | Low | Short-term unblock |
| Configure the model identifier explicitly against rapidocr 3.9.0's supported set | Low-Med | **Preferred** — moves forward rather than backward, and makes the identifier an explicit, reviewable config value instead of an inherited default |

**Risk:** LOW either way. RAWRS production code never executes in this test.

---

## 2. Test Tier Strategy

**Tiering is not greenfield.** `pytest.ini` already declares `real_docling` and `real_surya`, with documented skip invocations. Only **4 tests** carry them. The convention exists; the coverage does not.

### Measured — and it breaks the obvious tier design

`pytest -m "not real_docling and not real_surya"` was run to see whether the existing markers already yield a usable tier.

**Result: killed by a 900s timeout at ~66% complete. Extrapolated full runtime ≈ 23 minutes.**

| | Runtime |
|---|---|
| Full suite | 42m58s (measured) |
| Excluding both `real_*` markers | **≈23 min (measured to 66%, extrapolated)** |
| Attributable to the 4 inference tests | ≈20 min |
| **Remaining, diffuse across the suite** | **≈23 min** |

**Consequence: the Medium tier as originally specified below (`-m "not real_docling and not real_surya"`, target <10 min) is unachievable.** Roughly half the suite's cost is *not* in the four marked inference tests; it is spread across the other 50 files, and nothing currently identifies where.

**This invalidates designing markers from source inspection.** The tier boundaries below were derived by grepping for inference imports rather than from timing data — the same error, in miniature, as estimating the suite at ">5 min" from a truncated run. Profiling must precede marking (P0-0).

### Proposed tiers

| Tier | Target | Includes | Excludes | Invocation | Trigger |
|---|---|---|---|---|---|
| **Fast** | **<2 min** | Pure unit + model logic | `real_*`, `benchmark_pdf`, `slow` | `-m "not slow and not benchmark_pdf and not real_docling and not real_surya"` | Every save / pre-commit / every PR push |
| **Medium** | <10 min | Fast + fixture-driven pipeline + golden-diff | Real inference | `-m "not real_docling and not real_surya"` | PR merge gate |
| **Full** | ~43 min | Everything | — | *(no marker filter)* | Nightly + pre-release |

### New markers required

| Marker | Purpose |
|---|---|
| `slow` | Any test >1s that isn't inference |
| **`benchmark_pdf`** | **Requires the untracked corpus** |
| `golden` | Fixture→render→compare |

### Why `benchmark_pdf` is the important one

It resolves **two** Phase 3.5F blockers with one mechanism. Tests needing `samples/benchmark/pdfs/` (untracked, copyrighted) are excluded from Fast and Medium — so **a fresh clone with no PDFs runs green**, and the reproducibility blocker closes without distributing any copyrighted file.

No test is deleted or rewritten. Markers only.

---

## 3. Benchmark Infrastructure

### Current state

| Asset | State |
|---|---|
| `samples/benchmark/pdfs/` | 10 PDFs, **untracked** (gitignored, copyrighted) |
| `samples/benchmark/expected_md/` | 10 files, **tracked** |
| `remediated_docx/` | Untracked |
| `manifest.json`, `notes/` | Tracked |
| Golden-diff runner | **None** — `test_pipeline.py` uses PDFs ad hoc |

### Golden dataset strategy

Commit **serialized `Document` JSON fixtures** captured immediately pre-render. Precedent is already set: `expected_md/` tracks extracted text from the same PDFs, so derived-text artifacts are within the established copyright posture; the PDFs themselves stay out.

Gate path becomes `fixture → renderer → compare vs expected_md`, requiring no PDF.

### DOCX comparison — refines ADR-001's criterion

ADR-001 states *"byte-identical `.md` and `.docx`."* **For DOCX this is not achievable.** A `.docx` is a ZIP archive containing per-entry timestamps and a `docProps/core.xml` carrying creation/modification times; two runs of identical content produce different bytes.

**Refined criterion — normalized comparison:** unzip, discard `docProps/*`, canonicalize whitespace in `word/document.xml`, compare the resulting XML. Markdown stays a true byte-diff.

*This refines a success metric on implementation evidence, per the ADR's own amendment clause. The decision — that ADR-001 is gated on output equivalence — is unchanged.*

### Regression detection

| Signal | Gate |
|---|---|
| Markdown byte-diff | Any diff fails |
| DOCX normalized XML diff | Any diff fails |
| Heading count per document | Δ=0 |
| Detected object counts by type | Δ=0 unless the ADR under test intends the change |

---

## 4. Migration Safety Checklist

| ADR | Benchmark gate | Regression gate | Rollback point | Feature flag | Extra safety needed |
|---|---|---|---|---|---|
| 012 Persistence | — | Log survives restart | In-memory retained | `RAWRS_PERSIST` | No |
| 002 Identity | Re-anchor ≥95% | 0 silent mis-anchors | Legacy ID alias | `RAWRS_UUID_IDS` | **Yes — orphan-surfacing UI must exist before cutover** |
| 010 Decision log | — | 1 event per action | Drop table | — | No |
| 003 Artifacts | Heading Δ=0 on 10/10 | D1/D2 pass | Detector ignores input | `RAWRS_ARTIFACTS` | No |
| 004 Zones | Zoning 10/10 | — | Field ignored | — | No |
| 008 Rules | — | Rule IDs unchanged | Per-rule revert | — | No |
| 001 Tree | md byte-diff + DOCX XML diff, at **each of 3 steps** | Object counts Δ=0 | Lists authoritative | `RAWRS_TREE` | **Yes — golden runner must pre-exist** |
| 014 Dual path | Same as 001 | — | Native renderer retained | `RAWRS_OBJECT_RENDER` | **Yes — per-page-type cutover** |

**Two ADRs need safety work before they can start:** ADR-002 (orphan surfacing) and ADR-001/014 (golden runner). Both are Phase 0 deliverables below.

---

## 5. Repository Readiness

| Item | State | Blocks implementation? |
|---|---|---|
| Suite green | 1 failed / 1617 passed — dependency only | No, after pin |
| Suite runtime | 42m58s | **Yes — until tiered** |
| Fresh-clone reproducibility | Broken | **Yes — until `benchmark_pdf` marker** |
| Golden-diff runner | Absent | **Yes for ADR-001/014** |
| Fixtures | Absent | **Yes** |
| Frontend tests | 7 files, all a11y; no logic tests | No — blocks 3.8 only |
| Coverage reporting | Not configured | No |
| `routes.py` 1914 / `validator.py` 1290 ln | Over 800 limit | No — ADR-008 reduces |
| `SemanticObject` 5-of-9 stalled | Debt | No — a warning for ADR-001 |

---

## 6. Developer Workflow

| Improvement | Rationale |
|---|---|
| `pytest-xdist` (`-n auto`) | Medium tier is I/O and CPU bound across independent files; near-linear speedup |
| `addopts = -m "not slow and not benchmark_pdf and not real_docling and not real_surya"` in `pytest.ini` | **Makes the fast tier the default.** Bare `pytest` becomes the safe, quick command — the safest workflow becomes the easiest, which is the stated goal |
| `make test` / `test-medium` / `test-full` | Names the tiers so nobody memorizes marker expressions |
| Pre-commit hook → fast tier | Catches regressions before push |
| `--cov=src --cov-report=term-missing` on medium | Coverage without paying inference cost |
| `pip-compile` → `requirements.lock` | Ends transitive drift (§1) |
| CI: fast on push, medium on PR, full nightly | Matches tier design |

**The `addopts` default-inversion is the highest-leverage single line in this report.** Today the default `pytest` invocation costs 43 minutes, so it is run rarely — which is the mechanism by which a byte-diff gate silently stops being a gate.

---

## 7. Phase 0 Implementation Plan

Four independent workstreams. P0-1 and P0-2 are parallel; P0-3 depends on P0-2; P0-4 is independent.

---

# Phase 0 Checklist

### P0-0 · Profile the suite *(new — added on measurement evidence)*
**Objective** Locate the ~23 min that is *not* inference, before any marker is written.
**Effort** 1-2h (one instrumented full run) · **Dependencies** P0-1 (profile a green suite)
**Success** Ranked cost table for all 1625 tests; the top-N accounting for ≥80% of runtime identified by name
**Verify** `pytest --durations=100 -p no:randomly` captured to a committed report
**Why it exists** Tier boundaries in §2 were inferred from source inspection and the measurement above disproved them. Marking without profiling would repeat that error at greater cost.

### P0-1 · Pin the dependency graph
**Objective** Eliminate transitive drift; fix D5.
**Effort** 2-4h · **Dependencies** none
**Success** `docling`, `rapidocr`, `torch`, `torchvision`, `transformers` pinned; `requirements.lock` committed; D5 passes
**Verify** `pytest tests/test_docling_engine.py -m real_docling` green; fresh venv install from lock reproduces exact versions

### P0-2 · Introduce tier markers
**Objective** Fast tier <2 min; fresh clone green.
**Effort** **1-3d (revised up from 4-8h)** · **Dependencies** P0-0
**Estimate basis** Measurement showed the cost is diffuse, not concentrated in 4 inference tests; marking is a survey of ~50 files against profiling data, not a 4-line edit. Medium's target is restated as "<10 min *after* P0-0 identifies what to mark" — it is not reachable with the existing two markers.
**Success** `slow`, `benchmark_pdf`, `golden` declared in `pytest.ini` and applied; fast tier <2 min; medium <10 min; **zero tests deleted or rewritten**
**Verify** Time all three tiers; confirm fast tier passes with `samples/benchmark/pdfs/` renamed away

### P0-3 · Build `Document` fixtures + golden runner
**Objective** Make ADR-001's gate runnable without PDFs.
**Effort** 1-2d · **Dependencies** P0-2
**Success** 10 fixtures committed; runner compares md byte-exact and DOCX normalized-XML; passes on unmodified `main`
**Verify** Run on a clone with no PDFs present; deliberately corrupt one fixture and confirm the runner fails

### P0-4 · Default-invert pytest + tooling
**Objective** Safest workflow becomes easiest.
**Effort** 2-4h · **Dependencies** P0-2
**Success** bare `pytest` runs fast tier; `make test|test-medium|test-full`; `pytest-xdist` on medium; pre-commit hook
**Verify** Time bare `pytest` — must be <2 min

### P0-5 · ADR-002 orphan-surfacing spike
**Objective** Satisfy the §4 pre-condition for identity cutover.
**Effort** 4-8h · **Dependencies** none
**Success** A re-anchor below threshold produces a visible orphan record, never a silent reattach
**Verify** Synthetic edit forcing a low-confidence match; confirm surfaced

### P0-6 · Document the concurrency gate
**Objective** ADR-013 stated, not implied.
**Effort** 1h · **Dependencies** none
**Success** `KNOWN_LIMITATIONS.md` states: no multi-reviewer deployment until optimistic concurrency exists
**Verify** Present in file

---

# Final Answer

> **After Phase 0 is complete, is RAWRS ready to begin implementing ADR-002?**

**YES.**

Phase 0 clears every engineering blocker standing between the ratified architecture and ADR-002: the suite becomes green (P0-1), fast (P0-2, P0-4), reproducible on a fresh clone (P0-2), and ADR-002's one safety pre-condition is satisfied (P0-5). ADR-002 needs neither fixtures nor the golden runner — P0-3 gates ADR-001, not identity — so ADR-002 can begin as soon as P0-1, P0-2 and P0-5 land.

### First commit

```
chore: pin OCR dependency graph

Pin docling==2.87.0, declare rapidocr==3.9.0 explicitly, pin
torch/torchvision/transformers; add requirements.lock.

docling was unpinned (requirements.txt:5) while surya-ocr was pinned,
so an undeclared transitive rapidocr drifted to 3.9.0, where model id
PP-OCRv6.det.small is unsupported on the torch backend — the sole
cause of the failing real_docling integration test.
```

**Why this commit first:** smallest possible diff, zero production-code risk, turns the suite green, and is a prerequisite for trusting every measurement Phase 0 makes afterwards. A tiering exercise measured against a suite with a known-red test cannot distinguish "my marker was wrong" from "that test was already failing."
