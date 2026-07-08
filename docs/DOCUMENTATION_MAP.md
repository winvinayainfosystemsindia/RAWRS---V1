# RAWRS Documentation Map

## Purpose

A single index of every document that governs or describes RAWRS, what each one is *for*, and which one wins when two of them disagree. Produced as the closing deliverable of a documentation reconciliation audit (June 2026) that found several `docs/` files had drifted from the actual codebase — see each file's own changes for specifics, and `DECISIONS_LOG.md` for the reasoning behind what changed.

---

## Precedence order — read top to bottom when two documents conflict

1. **The code itself, plus the test suite.** Always wins. If a doc disagrees with what `src/` does and `pytest` confirms, the doc is wrong, not the code (unless the code is the thing under deliberate review).
2. **`CURRENT_STATE.md`, `PHASE_STATUS.md`, `ARCHITECTURE_CURRENT.md`** — the "what's actually true right now" layer. These three were written by reconciling every other document directly against source and tests, and should be kept current as the fastest-changing layer. **This is the new source of truth for "is X built."**
3. **`KNOWN_LIMITATIONS.md`** — the "what's deliberately not built, and what's a confirmed gap" layer. Consult this before assuming a missing capability is a bug.
4. **`DECISIONS_LOG.md`** — the "why is it this way" layer. Consult this before re-opening a decision that was already made and recorded (e.g., "should Surya output be HIGH confidence?" — no, see Decision history).
5. **Behavioral rule docs** (`HEADING_RULES.md`, `PAGE_RULES.md`, `OCR_RULES.md`, `VALIDATION_RULES.md`) — the team's deliberated intent for how each subsystem should behave. Amended in place when found to contradict reality (this audit did this for `HEADING_RULES.md` and `VALIDATION_RULES.md`); not silently overridden.
6. **Scope/constraint docs** (`PHASE1_SCOPE.md`, `RAWRS_PROJECT_CONTEXT.md`, `TECH_STACK.md`, `CLAUDE_INSTRUCTIONS.md`) — what's in/out of scope and which technologies are approved. High authority on *scope decisions* (these are stakeholder-level agreements, not casually overridden by a benchmark or a convenient implementation shortcut), but their *status claims* ("X is not supported") must match `PHASE_STATUS.md` — fixed where they didn't, in this audit.
7. **`ARCHITECTURE.md`** — the canonical/target architecture. Authoritative on *intent*; `ARCHITECTURE_CURRENT.md` is authoritative on *fact* where the two differ.
8. **Root-level planning/audit documents** (`BENCHMARK_GAP_ANALYSIS.md`, `BENCHMARK_RECONCILIATION_AND_PHASE1_PLAN.md`) — historical record of a specific past audit. Not maintained going forward; their durable conclusions have been folded into `DECISIONS_LOG.md` and `KNOWN_LIMITATIONS.md`. Keep them for the reasoning trail, but don't treat them as current.
9. **`TASKS.md`** — lowest precedence. A coarse module checklist only; defers to `PHASE_STATUS.md` for anything beyond "does this file exist."

---

## Full Index

### Current state (start here)

| Document | What it's for |
|---|---|
| `CURRENT_STATE.md` | One-page answer to "what does RAWRS actually do right now." Test counts, dependency reality, what doesn't exist yet (frontend/API). |
| `PHASE_STATUS.md` | Per-phase (A, B, C, D.0–D.2, H, F.1–F.5, K, I.1) verdict — VERIFIED COMPLETE / PARTIALLY IMPLEMENTED / etc. — with file:line citations and test references. The detailed companion to `CURRENT_STATE.md`. |
| `ARCHITECTURE_CURRENT.md` | Actual pipeline stage order, full current module/model inventory, the two tracked deviations from `ARCHITECTURE.md`. |

### Why things are the way they are

| Document | What it's for |
|---|---|
| `DECISIONS_LOG.md` | Reconstructed numbered architecture decisions (#3–#6, cited in code but never previously written down) plus the nine benchmark-reconciliation conflict resolutions (C1–C9) and standing strategic agreements. |
| `KNOWN_LIMITATIONS.md` | Everything intentionally not built, plus gaps found during this audit that weren't previously flagged as limitations, plus benchmark ground-truth inconsistencies that are not RAWRS defects. |

### Intended design and scope (amended where they contradicted reality)

| Document | What it's for | Amended this audit? |
|---|---|---|
| `ARCHITECTURE.md` | Canonical/target architecture and module responsibilities. | Yes — added Structure/Footnotes modules, flagged pipeline-order deviation, updated OCR/Image/DOCX responsibilities. |
| `PHASE1_SCOPE.md` | Phase 1 input/output/pipeline/capability scope. | Yes — fixed Reading Order Reconstruction → Validation, added Structure/Footnote/Alt-Text-Infrastructure capabilities, fixed Alt Text exclusion wording. |
| `RAWRS_PROJECT_CONTEXT.md` | Project identity, principles, tech stack, current scope summary. | Yes — same scope fixes as above, flagged frontend/backend as not-yet-built. |
| `HEADING_RULES.md` | Heading hierarchy semantics and formatting. | Yes — added the Detection Heuristics section that benchmark reconciliation recommended but never actually added; clarified detection-vs-output-formatting distinction. |
| `PAGE_RULES.md` | Page marker/break/footnote/endnote preservation rules. | No — verified accurate against code as written (page markers are literally `"Page {N}"`, matching this doc). |
| `VALIDATION_RULES.md` | Validation categories, severities, design principles. | Yes — added the real current rule-ID table; flagged OCR/Figure validation categories as having no implemented rule ID yet. |
| `OCR_RULES.md` | OCR engine order, page classification, confidence model. | Yes (light touch) — added `force_full_page_ocr` note and corrected the Surya-backend description preemptively. |
| `TECH_STACK.md` | Target technology choices. | Yes — added an implementation-status note distinguishing built (Docling/PyMuPDF/python-docx) from aspirational (frontend, FastAPI, Black/Ruff/MyPy). |
| `CLAUDE_INSTRUCTIONS.md` | Required reading list and process rules for anyone (human or AI) contributing code. | Yes — expanded required-reading list to include the five new docs; fixed the same scope/pipeline-order issues as above. |
| `TASKS.md` | Coarse module checklist. | Yes — checked off everything that now exists; added the modules missing from the original list; pointed to `PHASE_STATUS.md` as the detailed tracker. |

### Phase 2 design record

| Document | What it's for |
|---|---|
| `research/phase2/audit_1_format_selection.md` | Phase 2 format selection audit — why Mathpix MMD was chosen as the input format |
| `research/phase2/audit_2_cross_format_reconciliation.md` | Cross-format reconciliation — MMD vs. Mathpix DOCX vs. expected MD |
| `research/phase2/audit_3_signal_reliability.md` | Signal reliability tiers for each MMD structural element |
| `research/phase2/audit_4_benchmark_validity.md` | Benchmark validity audit for the 10 Mathpix sample documents |
| `research/phase2/specification_canonical_semantic_model.md` | Canonical semantic model spec — 19 object types, 3 section roles, 12 constraints |

The Phase 2 Engineering Blueprint (`RAWRS_Phase2_Engineering_Blueprint.md`) and Phase 2 Remediation Gap Audit (`RAWRS_Phase2_Remediation_Gap_Audit.md`) are stored on the Desktop (local only, not in the repository).

### Historical record (not maintained going forward)

| Document | What it's for |
|---|---|
| `research/phase1/benchmark_gap_analysis.md` | A point-in-time audit comparing RAWRS output against a 4-PDF benchmark set. Durable conclusions folded into `DECISIONS_LOG.md`/`KNOWN_LIMITATIONS.md`. Kept for its reasoning detail; don't treat its "current state" framing as current. |
| `research/phase1/benchmark_reconciliation_and_phase1_plan.md` | The plan that resolved the nine conflicts (C1–C9) found in the gap analysis, including the source-of-truth precedence rule this very map extends. Same status as above. |

---

## What changed in this reconciliation pass, at a glance

* **5 new documents created:** `CURRENT_STATE.md`, `PHASE_STATUS.md`, `ARCHITECTURE_CURRENT.md`, `KNOWN_LIMITATIONS.md`, `DECISIONS_LOG.md`.
* **8 existing documents amended in place:** `PHASE1_SCOPE.md`, `RAWRS_PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, `HEADING_RULES.md`, `VALIDATION_RULES.md`, `OCR_RULES.md`, `TECH_STACK.md`, `CLAUDE_INSTRUCTIONS.md`, plus `TASKS.md`.
* **1 document left unchanged:** `PAGE_RULES.md` (verified already accurate).
* **No production code was changed.** This was a documentation-only pass, per instruction.

---

## Updates since this map was produced (not a full re-audit — see each doc's own change history)

This map predates Phase M-1 (Mathpix Import Layer), Phase M-2 (cross-source verification engine, evidence fusion, Page Label Manager, `WorkspaceShell` frontend redesign), and FEATURE_012/015/016 entirely. Rather than rewrite this map's now-dated "5 new / 8 amended" framing, later work has been folded into the existing precedence structure as it happened:

* `CURRENT_STATE.md`, `PHASE_STATUS.md`, `ARCHITECTURE_CURRENT.md` — kept current through Phase M-2 and the 2026-07-08 theming sweep + bug fixes (see each file's own dated entries).
* `DECISIONS_LOG.md` — Parts 20–24 cover Phase 2 skeleton, FEATURE_015.3, Phase M-1, Phase M-2, and the theming/bugfix closure.
* `VALIDATION_RULES.md`/`PAGE_RULES.md`/`KNOWN_LIMITATIONS.md` — updated in place alongside the Phase M-2 implementation (`HEADING_VERIFY_*`, `PAGE_004`–`008`, `CALLOUT_VERIFY_001` rule IDs added; validation rule count is now 41, not the 29 current when this map was written).
* Two of the root-level paths this map originally listed (`BENCHMARK_GAP_ANALYSIS.md`, `BENCHMARK_RECONCILIATION_AND_PHASE1_PLAN.md`) had already moved to `research/phase1/` by the time of this correction; the Historical Record table above now points at their real location.
