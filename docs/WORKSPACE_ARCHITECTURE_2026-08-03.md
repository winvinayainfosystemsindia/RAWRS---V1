# The Interactive Workspace — Architecture

**Date:** 2026-08-03 · **Status:** Approved, then reduced by architectural review the same day.
**Baseline:** the Architecture Freeze (ADR-016 … ADR-020) is assumed correct and is not revisited.
**This file is the single description of the workspace architecture.** §7 records what the reduction removed and
why, so superseded concepts are archived here rather than in a competing document.
**Companion:** `INTERACTION_ARCHITECTURE_2026-08-03.md` — the reviewer's session as a state machine.

---

## 0. Position

> **The workspace consumes the ContentStream and returns decisions.**

It renders `D` and returns *decisions about objects it was handed by identity* — never content to be re-read. That
is the whole of what keeps ADR-019 intact at the human boundary: there is no `parse()`, so a surface can never
become a second home for a semantic fact.

**It is not a Projection and declares no `ProjectionContract`.** PI-1 is checked **once, on the stream** (§5), so
any surface rendering the whole stream is realization-complete by construction. Checking each surface separately
would be N checks for one property.

---

## 1. The loop

```
                ┌─────────────────────────────────────────────┐
                ▼                                             │
   Evidence → [ Semantic Document D ] → producers → Findings  │
                ▲                                        │    │
                └────────── Decisions ◄──────────────────┘    │
                                 │                            │
                                 └── D′ ─────────────────────┘
```

| | |
|---|---|
| **Done** | `export_ready` — `len(blocking_failures) == 0`. Not "the queue is empty": non-blocking findings may remain forever, and that is correct. |
| **Metric** | Reviewer effort = decisions required to reach it. Phase 2's objective, made measurable. |
| **Termination** | Every decision moves ≥1 finding terminal, and `IGNORED` ("don't ask again", distinct from `REJECTED`) suppresses re-proposal. Without `IGNORED` the loop could cycle. |
| **Producer contract** | A producer must be **idempotent and stable under its own applied decisions**: accepting the correction a finding proposed must stop that finding being produced. A contract test, not a hope. |

---

## 2. The five irreducible abstractions

Everything else in the workspace is an existing abstraction, a derived property, metadata, configuration, a rule,
or presentation. Four of the five already exist.

| # | Abstraction | Role | Status |
|---|---|---|---|
| 1 | `Finding` | A derived observation by a named producer, with evidence and an optional proposal | exists |
| 2 | `CorrectionRecord` | A stored decision — the only thing that changes `D` | exists |
| 3 | `ContentStream` | The one reading-order traversal; the workspace's read surface | exists |
| 4 | `Document.version` | Monotonic per committed transaction | exists |
| 5 | **`transaction_id`** | Groups the corrections of **one judgement**, so undo has a unit. Nothing else groups them reliably. | **one new field** |

**The entire workspace architecture is one field, four rules, and a smaller API.**

---

## 3. The four principles

Numbered W-1…W-4. Eight earlier principles were the Freeze restated and were merged back into it (§7.2) — a
workspace needing twelve new principles is forking the Freeze, not inheriting it.

| # | Principle | Why it is not already implied | Violated today? |
|---|---|---|---|
| **W-1** | **A finding is derived; a decision is stored.** | The Freeze governs a pipeline, where nothing is re-derived mid-run. `Document.verification_findings` is stored while validation and accessibility recompute — two lifecycles for one idea. | **Yes** |
| **W-2** | **History is append-only. Undo is a new decision, not an erasure.** | The rail has `revert()` but nothing states that history survives it. | Partly — `EDITED` mutates in place |
| **W-3** | **The unit of history is the transaction — one judgement, one undo.** | 34 running-header suppressions are one judgement; per-correction undo makes them 34. | **Yes — no `transaction_id`** |
| **W-4** | **Validation never blocks an edit; it blocks an export.** | `export_ready` implements it; nothing yet forbids a future surface from blocking on a diagnostic. | No |

**Corollary of W-1 (finding identity):** a decision references a finding by `(rule_id, object_id, field)`, never by
list position — that is what survives re-derivation, and what makes `IGNORED` mean anything.

---

## 4. What the workspace reads and writes

Three shapes, replacing eleven per-object-type mutation endpoints (§7.1).

| | |
|---|---|
| `GET /documents/{id}/stream` | The traversal plus the objects it references |
| `GET /documents/{id}/findings` | The unified work model — derived, recomputed per version |
| `POST /documents/{id}/decisions` | One transaction; one or more intents |

Object-type knowledge then lives in exactly one place — the verifier registry — which is where ADR-016 put it.

**Boundaries:** producers `inspect(D, ctx) → [Finding]`; the Projection Engine `render(D, options) → content`;
validation is a pure `D → Diagnostics`; benchmarks are read-only and never imported by production (**AI-3**);
history *is* the decision log, not a subsystem.

---

## 5. Where correctness is checked

| Property | Check | Once, on |
|---|---|---|
| Object realization (PI-1) | Every renderable object in `D` is referenced by the stream | **`ContentStream`** |
| No invention (PI-2) | Every node resolves to a model object by identity | **`ContentStream`** |
| Content conservation / authorized absence / single realization (PI-3/4/5) | Per rendered projection | Markdown, DOCX |
| Export readiness | `blocking_failures == []` | `AccessibilityReport` |

Surfaces inherit PI-1/PI-2 by rendering the stream. **A surface rendering a subset must say so** — that is a
filter, and a filter is presentation, not a projection contract.

---

## 6. State

| Tier | Contents |
|---|---|
| **Authoritative** | source PDF/MMD; extracted evidence (`pages`, `blocks`, image assets); the semantic objects; **the decision log** |
| **Derived** (cache keyed on `version`, never edited) | `ContentStream`; Markdown; DOCX; validation; `AccessibilityReport`/`export_ready`; findings; the queue; every KPI |
| **Session-local** (never persisted) | selection; viewport; layout; filters; drafts not yet committed |

---

## 7. Superseded — the reduction record

The 2026-08-03 review ran the YAGNI ladder over every noun in the first draft. Recorded here so the removals are
archived, not forgotten.

### 7.1 Deleted (14)

| Concept | Caught by |
|---|---|
| Workspace as a `Projection`; its own `ProjectionContract` (old WP-11) | PI-1 on the stream (§5) makes it redundant |
| `ValidationIssue` as a stored type | Finding-shaped; should be a function returning Findings |
| `RepairSuggestion` | A Finding's proposal, rendered |
| `RuleEvaluation` | PASS is the absence of a finding; the score's denominator is `applicable_rules(D) − finding.rule_ids` |
| A "priority" concept | `scoring.priority_key` already exists |
| Assignee / ownership | One actor. No config for a value that never changes |
| `sequence` field | `created_at` already orders monotonically |
| "Evidence revision" version axis | That is the existing job id |
| Export snapshot as an object | `exports: [{version, format, at}]` on the job record — metadata |
| The export gate as a new thing | `export_ready` exists |
| Collaboration substrate (comments, approval, conflict type) | A conflict is a Finding; the rest is YAGNI until two humans |
| Reverse index for `references` | No consumer |
| "AI integration" as a concept | `inspect()` exists; AI is a producer like any other |
| A "Document Services" module | Vocabulary over existing functions. The LSP mapping is naming, not a layer |

**Deferred, not deleted:** `actor` — derivable today (`AUTO_APPLIED`→auto, `reason_code`→ai, else human) and
trivially backfillable on a single-user corpus. It becomes real when there are two humans.

### 7.2 Merged into the Freeze (8 principles)

| Merged into | From |
|---|---|
| **PI-6** | edit the model not the artifact; no surface computes its own value |
| **ADR-016** | one write path; a producer proposes, a human disposes |
| **ADR-017** | every automated action names its evidence |
| **ADR-018** | identity never position (rule 1); session state is not truth (rule 2) |

### 7.3 Reclassified

| To | From |
|---|---|
| Derived property | fixed point; finding identity; work item; grouping by cause; priority ordering |
| Existing abstraction | edge corrections (`CorrectionRecord.field`); conflict (a Finding); AI (a producer) |
| Metadata | export history on the job record |
| Configuration | render options (`page_numbering_policy` is the precedent) |
| Rule | LIFO undo; producer stability |
| Presentation | surface classes; the three verbs; system alarm; previews-are-terminal |
| Caching | the three state tiers |

### 7.4 Correction to a prior document

`RAWRS_PROJECTION_ARCHITECTURE.md` §4 calls projection `anchors` *"the whole editing story."* That was written
assuming a reviewer edits inside a **rendered** surface. Editing happens on the semantic surface, built from
`ContentNode`s that **already carry `object_id`** — so anchors buy exactly one thing: clicking inside a read-only
Markdown/DOCX preview to reach the object behind it. **Demoted from foundational to optional.**

---

## 8. Open gaps, ordered

| Gap | Consequence of deferring | Status |
|---|---|---|
| `transaction_id` | No undo unit; a 34-target judgement costs 34 undos | **being implemented** |
| Findings re-derived per version (W-1) | The workspace shows stale work; the loop cannot converge | stored today |
| Reduced API (§4) | Two write paths into one model — ADR-016 violated one layer up | 11 endpoints today |
| Editable relationship edges | A wrong anchor has no recourse. Not a new concept: `CorrectionRecord.field = "source_block_id"` with an unimplemented `apply()` | unimplemented |
| PI-1 on the stream (§5) | Surfaces cannot inherit realization-completeness | unbuilt |
| Projection anchors | Preview→object navigation only | optional (§7.4) |

---

## 9. What would falsify this

| Claim | Falsifier |
|---|---|
| Five abstractions suffice | A workspace requirement expressible in none of them |
| PI-1 on the stream covers every surface | A surface that legitimately renders something not in the stream |
| `transaction_id` is the only new field | Undo needing an ordering `created_at` cannot supply |
| The reviewer never edits prose | Real reviewers reaching for a text buffer |

**The one thing that would falsify the whole design:** a reviewer's most common action turning out to be something
the Semantic Document cannot express. The answer is then to extend the model — never to let a surface hold the
fact. That rule is what the Architecture Freeze bought.
