# Implementation Readiness Review — Phase 3.5F

Governing design: `ADR_2026-07-19.md`. No architecture is revisited here. This review asks one question: **can engineering start on Monday?**

**Answer: No.** One blocker, discovered this pass, invalidates the gate that the ADR's highest-risk decision depends on. It is small and concrete.

---

## Blocking Discovery

**The test suite is not reproducible on a fresh clone, and ADR-001's gate cannot run in CI.**

| Fact | Evidence |
|---|---|
| Benchmark PDFs are gitignored | `.gitignore`: `samples/benchmark/pdfs/` — "copyrighted source documents (obtain separately)" |
| The suite reads them directly | `tests/test_pipeline.py:32` → `SAMPLE_PDF_DIR = .../samples/benchmark/pdfs` |
| They exist only on this machine | 10 PDFs present locally, **0 tracked in git** |
| Expected outputs *are* tracked | `samples/benchmark/expected_md/` — 10 files, in version control |

ADR-001's success criterion and rollback gate is *"byte-identical `.md` and `.docx` on all 10 benchmark PDFs."* That gate is currently unrunnable by anyone but this workstation. The ADR's own condition — *"ADR-001 lands behind its byte-diff gate or not at all"* — is therefore unsatisfiable as written.

**Fix (small, and the copyright posture already permits it):** commit **serialized `Document` JSON fixtures** captured immediately before rendering. `expected_md/` already tracks extracted text from the same PDFs, so derived-text artifacts are evidently acceptable; the PDFs themselves stay out. The byte-diff gate then runs from fixture → renderer → `expected_md`, with no PDF required. This also makes ADR-014's dual-path retirement verifiable in CI.

## Second Blocker — suite runtime *(verified after first draft)*

Full run: **1 failed, 1617 passed, 7 skipped — in 42m58s.** An earlier estimate of ">5 min" was wrong by an order of magnitude.

A 43-minute suite is disqualifying for ADR-001, whose entire safety model is *"run the byte-diff gate at each of three migration steps."* A gate that costs 43 minutes per invocation will be run rarely, batched, or skipped — which is how the `SemanticObject` migration reached 5-of-9 and stalled.

**Cause:** the suite executes real OCR inference. `test_docling_engine.py::TestRealDoclingIntegration` loads torch and runs RapidOCR against genuine PDFs.

**Fix:** tier the suite — `pytest -m "not slow"` for the fast gate (target <2 min), real-inference tests marked `slow` and run on demand or nightly. Additive; no test is deleted.

## D5 — identified

`tests/test_docling_engine.py::TestRealDoclingIntegration::test_oleary_single_page_recovers_real_text`

```
Docling OCR failed after 0.74s: Unsupported configuration: torch.PP-OCRv6.det.small
```

**Environment/dependency drift, not a code defect** — RapidOCR's torch backend does not accept the `PP-OCRv6.det.small` model identifier this test's configuration requests, consistent with an upstream version bump renaming or dropping that model. The RAWRS code under test never executes.

**Consequence:** downgraded from a code blocker to a dependency-pinning task. It does not block ADR work, but it must be pinned or the test re-pointed before the suite can be a merge gate — a suite with one permanently-red test trains engineers to ignore red.

---

# ADR Readiness Matrix

| ADR | Implementable | Hidden deps | Incremental | New infra | Risk | Ready |
|---|---|---|---|---|---|---|
| 001 Shallow tree | Yes | **Gate unrunnable (above)** | Yes — tree beside lists | Fixtures | **CRITICAL** | ⛔ blocked |
| 002 Identity | Yes | ID store; needs ADR-012 first | Yes — UUID + legacy alias | SQLite | MEDIUM | 🟡 after 012 |
| 003 Artifacts | Yes | None | Yes — optional input to detector | None | LOW | ✅ |
| 004 Physical zones | Yes | None | Yes — additive field | None | LOW | ✅ |
| 005 Logical divisions | Yes | ADR-001 | Yes | None | MEDIUM | 🔒 after 001 |
| 006 Relationships | Yes | ADR-001, 002 | Yes | None | LOW | 🔒 |
| 007 Reading order | Yes | ADR-001 | Yes | None | LOW | 🔒 |
| 008 Rule framework | Yes | None | Yes — per-rule port | None | MEDIUM | ✅ |
| 009 Findings vocab | Yes | ADR-008 | Yes | None | LOW | 🔒 |
| 010 Decision log | Yes | **ADR-012 must precede** | Yes — write-only | SQLite | LOW | 🟡 after 012 |
| 011 Eval harness | Yes | ADR-002, 008; **fixtures** | Yes | Runner | MEDIUM | 🔒 |
| 012 Persistence | Yes | None | Yes | SQLite | LOW | ✅ |
| 013 Concurrency | N/A — doc-only gate | None | — | None | LOW | ✅ |
| 014 Retire dual path | Yes | ADR-001 + gate | Yes — fallback retained | None | **HIGH** | 🔒 |

**Ordering correction:** the ADR lists ADR-002 before ADR-012 in Phase 3.5B. Wrong — identity needs somewhere durable to store the ID map, and the decision log needs the same store. **ADR-012 must ship first.** This is the only sequencing error found; it is a swap, not a redesign.

---

# Migration Readiness

| ADR | Current → Transition → Final | Failure mode | Recovery |
|---|---|---|---|
| 001 | 12 lists → tree built beside lists → lists become `walk()` views | Tree diverges from lists silently | Lists remain authoritative until gate passes; revert = stop calling `walk()` |
| 002 | Positional IDs → UUID minted, legacy kept as alias → UUID authoritative | Matcher mis-anchors corrections | Sub-threshold match becomes surfaced orphan, never silent reattach |
| 003 | No classification → optional input, detector may ignore → detector consumes | Over-classifies a real heading as artifact | Reviewer override; per-document disable |
| 008 | 2 engines → ported rules coexist with unported → 1 registry | A ported rule changes behaviour | Per-rule revert; IDs unchanged so frontend unaffected |
| 010 | Nothing → write-only log, read by nothing → consumed by 011 | None — cannot break product | Drop table |
| 012 | In-memory dict → SQLite beside dict → SQLite authoritative | Store corruption | In-memory path retained |
| 014 | Dual paths → object projection w/ line-by-line fallback → single path | Output regression | Fallback retained until byte-diff green on all 10 |

**Rollback realism:** all rollbacks are genuine except ADR-001's, which is only real *if* the gate can run. That is the blocker.

---

# Test Readiness

| Area | Exists | Must add |
|---|---|---|
| Backend | 50 test files | Fixture-based golden-diff runner |
| Frontend | **7 files, all a11y** (`frontend/__tests__/a11y/`) | Logic/unit tests — none exist today |
| Golden-file | Ad hoc in `test_pipeline.py`, PDF-dependent | Reusable fixture→render→compare harness |
| D1/D2 regression | None | Running-header first-occurrence; page-number across all 5 tiers |
| ADR-002 | None | Re-anchor ≥95% after edit; 0 silent mis-anchors |
| ADR-001 | None | Nested-list depth → DOCX `ilvl`; linearization totality |
| Integration | Partial | Fresh-clone smoke test (would currently fail) |

**Mandatory gates:** fixture byte-diff (ADR-001, 014) · D1/D2 regression (ADR-003) · re-anchor rate (ADR-002).

**Frontend gap is material for Phase 3.8** — a11y coverage without logic coverage means the reviewer workflow has no regression net.

---

# Benchmark Readiness

| ADR | Success metric | Failure metric | Dataset |
|---|---|---|---|
| 001 | Byte-identical md+docx, 10/10 | Any diff | Fixtures (to build) |
| 002 | ≥95% re-anchor after edit | Any silent mis-anchor | Fixtures + synthetic edits |
| 003 | D1/D2 pass; heading count Δ=0 | Real heading suppressed | 10 PDFs |
| 004 | Running headers zoned 10/10 | Body text zoned as header | 10 PDFs |
| 008 | 48 rules, IDs stable | Any ID change | Existing suites |
| 010 | 1 durable event per action | Any lost event | Synthetic session |
| 014 | Byte-diff green | Any diff | Fixtures |

**Corpus is adequate in size (10 PDFs) and has tracked expected outputs. It is inadequate in *distribution*: it cannot be used by CI or a second engineer.** That is the same blocker, restated.

---

# Repository Readiness

| Item | State | Blocks? |
|---|---|---|
| Benchmark reproducibility | **Broken** — PDFs untracked, suite depends on them | **YES** |
| Test suite green | **1 failed, 1617 passed, 7 skipped** — D5 identified, see below | 🟡 environment, not code |
| Test suite speed | **42m58s** — verified, not ">5 min" | **YES** — see below |
| Eval harness | Absent (ADR-011) | No — scheduled 3.8 |
| Existing abstractions | `SemanticObject` 5-of-9 migrated, stalled | No — but a warning for ADR-001 |
| Frontend logic tests | Absent | No — blocks 3.8 only |
| `routes.py` 1914 ln, `validator.py` 1290 ln | Over 800-line limit | No — ADR-008 reduces validator |

---

# Risk Assessment

| ADR | Risk | Why | Mitigation | Split? |
|---|---|---|---|---|
| 001 | **CRITICAL** | Widest blast radius; gate currently unrunnable; a prior migration (`SemanticObject`) already stalled at 5-of-9 | Fix fixtures first. Land tree beside lists, never replacing until green | **Yes — 3 steps: (a) tree built + unused, (b) `walk()` consumers migrated, (c) lists retired** |
| 014 | **HIGH** | Retiring the only working native renderer | Fallback retained; gate-blocked | Yes — per-page-type cutover |
| 002 | MEDIUM | Matcher quality unproven | Orphan-on-low-confidence; never silent | No |
| 008 | MEDIUM | 35 rules ported, wide surface | Per-rule, IDs frozen | Yes — by family |
| 011 | MEDIUM | Depends on fixtures | Sequenced after | No |
| Others | LOW | Additive, reversible | — | No |

---

# Revised Dependency Graph

```
[BLOCKER] Fixture reproducibility ──┬──> ADR-001 gate becomes runnable
                                    └──> ADR-011 eval harness
[BLOCKER] D5 identified + green ────┘

ADR-012 Persistence ──> ADR-002 Identity ──> ADR-010 Decision Log ──> ADR-011
   (FIRST — corrected)                              ↑
                                            ADR-008 ──> ADR-009
ADR-003 Artifacts ──> ADR-004 Zones ──> D1/D2   (parallel, independent)

ADR-001 (3 steps) ──┬──> ADR-005 ──> ADR-006 ──> ADR-007
                    └──> ADR-014
```

**Changes from the ADR:** ADR-012 moved before ADR-002 · fixture work added as a Phase 0 · ADR-001 split into three steps.
**Genuinely parallel:** {003, 004} · {008, 009} · {012→002→010}. Three streams, no contention.

---

# Final Engineering Roadmap

### Phase 0 — Unblock *(days, not weeks)*
**Objectives** Make the suite reproducible and green.
**Deliverables** `Document` JSON fixtures committed · fixture-based golden-diff runner · **suite tiered (`slow` marker) to a <2 min fast gate** · D5 dependency pinned or test re-pointed · fresh-clone smoke test.
**Gates** Fast suite green in <2 min from a clean checkout with no PDFs present.
**Rollback** N/A — additive.
**Completion** A second engineer clones and runs the suite green.

### Phase 3.5B — Foundations
**Objectives** Stop active data loss; fix heading pollution.
**Deliverables** ADR-012 → ADR-002 → ADR-010 · ADR-003 · ADR-004 · D1/D2 fixes.
**Dependencies** Phase 0.
**Gates** Re-anchor ≥95%, 0 silent mis-anchors · D1/D2 regressions · heading count Δ=0 on 10/10.
**Rollback** Legacy ID alias; in-memory path; detector ignores classification.
**Completion** Corrections survive reprocessing; running headers no longer become headings.

### Phase 3.6 — Canonical Model
**Objectives** ADR-001 in three steps, then ADR-014.
**Gates** Byte-diff 10/10 at each step · nested-list `ilvl` correct · linearization totality.
**Rollback** Lists authoritative until step (c); native renderer retained.
**Completion** One document model, one rendering path.

### Phase 3.7 — Semantics & Rules
**Deliverables** ADR-005, 006, 007, 008, 009.
**Gates** Rule IDs unchanged; frontend untouched.

### Phase 3.8 — Reviewer Surface
**Deliverables** ADR-011 eval harness · semantic editor view · navigator · **frontend logic tests**.
**Gates** Rule changes report precision delta pre-merge.

### Phase 4 — Design System
**Entry condition** ADR-001 + 014 complete; object presentation stable.

---

# Immediate Next Task

**Commit `Document` JSON fixtures for the 10 benchmark PDFs and repoint `tests/test_pipeline.py` at them.**

Smallest unblocking change. Makes the suite reproducible, makes ADR-001's gate runnable in CI, and is a prerequisite for ADR-011. Everything else in the roadmap is currently gated behind it.

Run concurrently: identify and fix D5.

---

# Final Answer

> **"If you were the lead engineer responsible for shipping RAWRS to production, would you begin implementation today?"**

**No.**

**Minimum remaining blocker:** the benchmark corpus is not in version control, so the test suite is not reproducible on a fresh clone and ADR-001's byte-diff gate — the ADR's own stated condition for its highest-risk decision — cannot run anywhere but this workstation. Beginning ADR-001 without it means attempting the widest-blast-radius refactor in the project with no reproducible safety net, on a codebase that already contains one migration abandoned at 5-of-9.

**Second blocker, verified after first draft:** the suite takes **42m58s**. ADR-001's safety model is a byte-diff gate run at each of three migration steps; at 43 minutes per run it will be batched or skipped, which is precisely how the `SemanticObject` migration stalled at 5-of-9. The suite must be tiered before it can gate anything.

D5 is resolved as a question: `test_oleary_single_page_recovers_real_text`, failing on RapidOCR dependency drift, not RAWRS code. A pinning task, not a code blocker.

All three are days of work, not weeks. Neither requires an architectural change — the ADR stands as governing design, with one sequencing correction (ADR-012 before ADR-002) and one split (ADR-001 into three steps).

**Once Phase 0 is green: start with ADR-012 → ADR-002.** Identity is the only item on the list where waiting has an ongoing cost — every reviewer decision recorded today is keyed to an identifier that moves.
