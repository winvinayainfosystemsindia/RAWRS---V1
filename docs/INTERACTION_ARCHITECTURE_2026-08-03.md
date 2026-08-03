# User Interaction Architecture — the reviewer's hour

**Date:** 2026-08-03 · **Status:** Proposed, reduced by architectural review the same day.
**Baseline:** `WORKSPACE_ARCHITECTURE_2026-08-03.md` (approved, reduced) and the Architecture Freeze (ADR-016 … ADR-020).
**Reduction applied:** the `TRIAGE` phase and its `ESCALATE` exit are gone — structural implausibility is **one rule
in the existing accessibility registry**, not a new session state. See §3.6 and §9.1.
**Scope:** interaction model as a state machine. No wireframes, no screens, no components.
**Method:** measured, not imagined. Every number below comes from running the pipeline over the corpus.

---

## 1. What an hour actually contains

Four native-text corpus documents, 57 pages, full native pipeline + accessibility evaluation:

| Document | Pages | Headings | Images | Tables | Corrections | …auto | …proposed | Blocking | Manual | Validation |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Bruner — FolkPedagogy | 26 | **1** | 0 | 0 | 46 | 46 | 0 | 2 | 1 | 4 |
| sockett — profession | 9 | 14 | 0 | 0 | 8 | 7 | 1 | 3 | 1 | 20 |
| Calderhead — profession | 4 | 2 | 0 | 0 | 7 | 6 | 1 | 2 | 1 | 3 |
| **Brinkman — learner-centred** | 18 | 20 | 4 | 3 | **35** | **34** | **1** | **10** | 6 | 47 |
| **Total** | 57 | 37 | 4 | 3 | **96** | **91** | **5** | **17** | 9 | 74 |

```
correction statuses        {auto_applied: 91, proposed: 5}        → 94.8% autonomous
findings reaching a human   3 × text_block:suppress_artifact
                            2 × heading:positional_only_h1        → 5, total, across 57 pages
accessibility outcomes     {pass: 27, fail: 19, manual_review: 9}
blocking failures          REVIEW_001 4 · LANG_001 4 · IMAGE_A11Y_001 4 · TABLE_A11Y_004 3 · READING_ORDER_001 2
validation severities      {warning: 54, info: 19, error: 1}
```

**Brinkman's ten blocking failures, derived** (images and tables exist only in this document; `LANG_001` and
`REVIEW_001` are one per document):

| Rule | Count | What the reviewer actually does | Verb |
|---|--:|---|---|
| `IMAGE_A11Y_001` | 4 | Write alt text for 4 figures | **write** |
| `TABLE_A11Y_004` | 3 | Confirm header row / scope on 3 tables | **fix** |
| `LANG_001` | 1 | Set the document language | **fix** (~5 seconds) |
| `READING_ORDER_001` | 1 | Confirm one page's order | **fix** |
| `REVIEW_001` | 1 | Dispose of the 1 proposed correction | **decide** |

### 1.1 Six consequences that determine the whole design

| # | Measurement | Consequence |
|---|---|---|
| 1 | **91 of 96 changes are autonomous** | The reviewer is not a decider working a queue of 96. They are an **auditor of a batch of 91**, plus a decider on ~10. A queue-first product optimises the 5% and ignores the 95%. |
| 2 | **5 findings reach a human across 57 pages** | The correction queue is not the workload. The **accessibility gate** is — 17 blocking failures vs 5 proposals, a 3.4:1 ratio. |
| 3 | **`LANG_001` blocks every single document** | One field, trivially detectable, blocking 100% of exports. It should never have been a blank. |
| 4 | **4 of 17 blocking failures are `REVIEW_001`** | 24% of the export gate is "you haven't finished yet" — a workflow state masquerading as a document defect. |
| 5 | **Bruner: 26 pages, 1 heading, 46 silent corrections, 2 blocking failures** | A near-total structure-detection failure that produces an *almost clean* queue. A queue-driven reviewer would approve it. **The queue cannot see its own blind spot.** |
| 6 | **4 alt texts ≈ 16–20 min unaided** | Authorship is the largest single cost on the only document that has images. Everything else is minutes. **Alt text is the hour.** |

---

## 2. Five reframes

| # | Reframe | Because |
|---|---|---|
| **R1** | **The reviewer is an auditor, not an inspector.** | 91 silent changes cannot be individually checked and must not be individually queued. The interaction is *stratified sampling with cheap escape*, not enumeration. |
| **R2** | **The first interaction is a plausibility check, not a work item.** | Bruner. Before "what should I decide", the reviewer's real question is "did this understand my document?" If no, every downstream decision is worthless. |
| **R3** | **The model unifies findings; the interaction must not.** | Three verbs — **decide** (a proposal), **fix** (a diagnostic with no proposal), **write** (authorship) — have different costs, contexts and rhythms. One homogeneous queue makes the cheapest and the most expensive work look identical. |
| **R4** | **High-confidence proposals should not be in the queue at all.** | If the machine is 0.95 sure and still asking, the autonomy policy is miscalibrated. This converts a queue-*ordering* question into a **policy-calibration** question — measurable, not aesthetic. |
| **R5** | **For generated content, optimise the cost of *verification*, not generation.** | An AI alt text that is fluent and wrong is worse than none, because it will be accepted. Drafting is already cheap; *checking* is the bottleneck and the trust risk. |

---

## 3. The state machine

Five layers. Only Layer 1 and the decisions in Layer 3 are durable; the rest is session-local (WP-12).

### 3.1 Layer 1 — Document

```
   ABSENT ──upload──► INGESTING ──┬──► READY
                                  └──► FAILED ──retry──► INGESTING
```

**There is no review state, no "submit", no "approved" flag.** Readiness is a *predicate over D*, recomputed per
version (WP-4). What a reviewer sees are derived overlays, not stored states:

| Overlay | Predicate |
|---|---|
| `NEEDS_STRUCTURE` | structural plausibility check fails (§3.6 — **new**) |
| `NEEDS_WORK` | `len(blocking_failures) > 0` |
| `EXPORTABLE` | `blocking_failures == []` **and** projection correctness `ok` |
| `EXPORTED` | an export entry exists in the log at the current `version` |
| `STALE_EXPORT` | `exported_at_version < version` |

### 3.2 Layer 2 — Session phase (emergent, never selected)

The reviewer never picks a mode. Phases **fall out of the ordering function** (§4) applied to what remains:

```
  ORIENT ──► AUDIT ──► RESOLVE ⇄ AUTHOR ──► VERIFY ──► EXPORT
     ▲         │          │        │           │
     └─────────┴──────────┴────────┴───────────┘
                (any object, any time, via selection)
```

| Phase | Entered when | Left when | Dominant verb |
|---|---|---|---|
| **ORIENT** | Document opened | Reviewer has seen shape, what RAWRS did, and any structural-implausibility finding (§3.6) | look |
| **AUDIT** | Orientation done | Sample of the autonomous batch checked | sample |
| **RESOLVE** | Audit satisfied | No blocking *decide*/*fix* items remain | decide / fix |
| **AUTHOR** | Blocking items requiring content remain | Content written | write |
| **VERIFY** | `blocking_failures == []` | Preview accepted | confirm |
| **EXPORT** | Verify passed | Snapshot recorded | commit |

`RESOLVE ⇄ AUTHOR` is deliberately bidirectional: authorship is context-heavy, so the reviewer batches it, and
returning to it must not cost re-orientation.

### 3.3 Layer 3 — Work item

```
  UNOBSERVED ──(producer emits, no decision)
      │
      ├─► AUTO_APPLIED ────────────────────────────► terminal (auditable, revertible)
      │        └──audit reject──► REVERTED ──► (re-enters the queue)
      │
      └─► PROPOSED ──┬─► ACCEPTED ─┐
                     ├─► EDITED ───┤
                     ├─► REJECTED ─┼──► terminal
                     ├─► IGNORED ──┘   (IGNORED also suppresses re-proposal)
                     └─► PENDING_REVIEW ──► (non-terminal: explicitly deferred)
```

`UNOBSERVED` is the only new state and it is **derived**, not stored: a finding with no decision. `PROPOSED` vs
`PENDING_REVIEW` is the distinction between *not yet seen* and *seen and deferred* — and "defer" must be a
first-class action, because it is what preserves momentum.

### 3.4 Layer 4 — Transaction

```
  DRAFT ──commit──► VALIDATING ──┬──► COMMITTED (version++, log append)
  (session-local)                └──► REFUSED (precondition failed)

  COMMITTED ──undo──► REVERTED (a NEW log entry, never an erasure)
```

| Precondition | Refuses when |
|---|---|
| `parent_version` current | Another actor committed since (future multi-user) |
| Value equality (out-of-order undo only) | The object's current value ≠ the correction's `proposed_value` |
| Non-empty targets | The finding vanished before commit (the document changed underneath) |

A refusal is **never a dialog**; it becomes a conflict finding in the queue.

### 3.5 Layer 5 — Selection

`selection: object_id | null`. Every surface is a pure function of `(D, selection)`. There are exactly **two doors
into a decision**, and both terminate in the same transaction:

| Door | Path | Needed because |
|---|---|---|
| **Finding-first** | queue item → its targets → decision | Without it the reviewer has no guidance |
| **Object-first** | select any object → its findings, evidence, and available actions (even with zero findings) → decision | Without it the reviewer cannot act on anything a producer missed — which, per Bruner, is exactly where the real defects are |

A purely queue-driven tool is a form. A purely document-driven tool is an editor. RAWRS needs both doors into one room.

### 3.6 Structural implausibility — a rule, not a state

The fixed-point model assumes the run is sound. Bruner proves it is not always: 26 pages, **1 heading**, 46 silent
corrections, and a near-clean gate on a document RAWRS did not understand. A queue-driven reviewer would approve it.

**The first draft answered this with a new `TRIAGE` phase and an `ESCALATE` exit. That was over-built.** The
accessibility registry already exists, rules self-register at import, the report already surfaces them, and
`priority_key` already orders them. The whole answer is **one rule**:

| Signal | Bruner | Expectation |
|---|--:|---|
| Headings per page | **0.04** (1 / 26) | ≈ 1 per 1–3 pages for an academic paper |

It fires as an OBSERVATION, appears during ORIENT alongside everything else, and needs no new session state, no new
transition, and no new subsystem. A reviewer who sees it can still abandon the run — that is a choice, not a state.

---

## 4. The ordering function — which generates the phases

Phases are not designed; they are the output of sorting what remains. One function, applied continuously:

| Rank | Term | Rationale |
|--:|---|---|
| 1 | **Invalidating first** — findings whose resolution changes other findings (reading order, region boundaries, page labels, structural triage) | Deciding a heading level before fixing reading order wastes the decision |
| 2 | **Blocks export?** | The gate is the goal |
| 3 | **Barrier class** — BARRIER › DEGRADATION › OBSERVATION | Reuse `scoring.priority_key`'s first term verbatim |
| 4 | **Batch size, descending** | Maximises *blocking failures cleared per decision* — the metric the whole design optimises |
| 5 | **Confidence — direction depends on the verb** (§4.1) | |
| 6 | **Authorship last within a tier** | Context-heavy; batch it so the reviewer enters writing mode once |

### 4.1 Confidence points in opposite directions for the two verbs

This corrects an error in the approved Workspace Architecture §3.3, found by reading `scoring.priority_key`:

| Verb | Ordering | Why |
|---|---|---|
| **Diagnostic** (a defect assertion, no proposal) | **HIGH confidence first** — as `priority_key` already does | High confidence = *certainly* a real defect. Fix the definite things first. |
| **Proposal** (a suggested change) | **LOW confidence first** | High confidence = the machine should have applied it. Asking wastes the reviewer on easy calls. |

§3.3 stated "low-confidence first" for both. That is wrong for diagnostics, and the existing code is right.

**The sharper conclusion (R4):** if the proposal queue is full of high-confidence items, the fix is not a better sort
— it is a better autonomy policy. **The queue's confidence distribution is a live diagnostic of that policy.**

---

## 5. The hour, as a transition trace

Brinkman: 18 pages · 20 headings · 4 images · 3 tables · 35 corrections (34 auto) · 10 blocking · 47 validation issues.

| ⏱ | Phase | Transition | Reviewer action | System response | Δ blocking |
|---|---|---|---|---|--:|
| 0:00 | ORIENT | `READY`; surfaces resolve | Opens document | Shape: 18 pp, 20 headings, 4 figures, 3 tables. "RAWRS made **34 changes** without asking. **10 things block export.**" | 10 |
| 0:02 | ORIENT→AUDIT | no structural finding raised (1.1 headings/page) | — | 34 changes in **3 groups by cause**, each with a confidence range and its 3 weakest members | 10 |
| 0:03 | AUDIT | sample | Checks 9 of 34 (the 3 weakest per group); each links to its PDF region | All correct → trust established at a cost of 9 checks, not 34 | 10 |
| 0:07 | AUDIT→RESOLVE | batch accepted — auditing an auto-apply is a **no-op unless rejected** | — | Queue ordered by §4 | 10 |
| 0:07 | RESOLVE | rank 1 | `LANG_001` — sets language | **One field. One transaction.** `version++`, revalidate | **9** |
| 0:08 | RESOLVE | rank 1 (invalidating) | `READING_ORDER_001` — confirms page order | Transaction; downstream findings re-derived | **8** |
| 0:10 | RESOLVE | rank 2 | The 1 `PROPOSED` correction (`positional_only_h1`): sees the evidence — *positional signal alone at 0.35, vs 0.85+ corroborated elsewhere* — and rejects it | Transaction. `REVIEW_001` clears | **7** |
| 0:11 | RESOLVE | rank 3 | 3 × `TABLE_A11Y_004`: confirms header row + scope | 3 items, one per table — **not** batchable; each is unique content | **4** |
| 0:17 | RESOLVE→AUTHOR | only *write* items remain | — | Enters the authorship batch: 4 figures, one context | 4 |
| 0:17 | AUTHOR | AI draft | Requests drafts for all 4 | Qwen2.5-VL proposes 4 alt texts as `PROPOSED` corrections — **proposals, never applied** | 4 |
| 0:18 | AUTHOR | verify-not-generate (R5) | Each: image shown large, beside its caption, its page context, and the draft. Accepts 2, edits 1, rewrites 1 | 4 transactions (or 1 grouped) | **0** |
| 0:26 | AUTHOR→VERIFY | `blocking_failures == []` | — | **Gate opens.** Projection correctness `ok=True` checked silently | 0 |
| 0:26 | VERIFY | preview appears **for the first time** | Reads the DOCX projection | Read-only. Any defect found here is fixed *in the model*, never in the preview | 0 |
| 0:31 | VERIFY→EXPORT | accepts | Exports | Snapshot pinned at `(document_id, version, format)`; **the export is appended to the decision log** | 0 |
| 0:32 | EXPORTED | — | — | 47 non-blocking validation issues remain, and that is correct | 0 |

**≈32 minutes.** The hour is not the constraint. **Authorship is:** 9 of 32 active minutes on 4 images — and
16–20 minutes unaided, which is where the rest of the hour would have gone.

### 5.1 What the trace shows

| Observation | Design consequence |
|---|---|
| The queue is worked in **6 decisions**, not 35 | Batching by cause and autonomy did the work before the reviewer arrived |
| **The preview appears once, at 0:26** | Previews are a terminal-phase surface (§6.1) |
| **The audit costs 9 checks for 34 changes** | Stratified sampling, not enumeration |
| `LANG_001` — the highest-value 5 seconds in the product | And it should not have been asked at all (§9.3) |
| **Nothing blocked the reviewer at any point** | Only export gates. Every other signal is advisory (WP-7) |

---

## 6. Every surface, and when it is allowed to exist

| Surface | Phase | Mutability | Rule |
|---|---|---|---|
| **Run summary** | ORIENT, TRIAGE | — | The only surface that answers "did this understand my document?" |
| **Semantic** (ContentStream) | all | via decisions only | The work surface. Always present. |
| **Source** (PDF + overlays) | all | immutable | Evidence. One action away from any claim, always. |
| **Queue** | AUDIT → AUTHOR | — | Ordered by §4. Three visually distinct verbs (R3), one data model |
| **Evidence / provenance** | on selection | — | Why RAWRS believes this. Never more than one action away |
| **Decision log** | all | append-only | The audit surface for the 91 silent changes — *not* the queue |
| **Gate** | all | — | One number: blocking failures remaining. The honest progress metric |
| **Projection preview** | **VERIFY only** | read-only | §6.1 |
| **System health** | ambient, non-modal | — | PI violations, producer failures, empty-registry alarm |

### 6.1 Why the preview is terminal-phase only

An always-visible Markdown pane beside the work surface is an **invitation to edit the projection** — precisely
WP-1's forbidden action. Affordances teach behaviour; a surface that exists during resolution will be used during
resolution. Restricting previews to VERIFY is not a UI preference, it is how the architecture defends itself.

**Corollary:** a defect noticed in the preview must round-trip to the model. The preview's only interactive
affordance is *"take me to the object that produced this"* — which is what projection `anchors`
(`object_id ↔ SourceRange`, unbuilt) would provide. **Optional, not foundational:** the semantic surface is
navigable and text search is the zero-cost fallback, so anchors buy convenience here, not correctness. Editing never
needs them — the semantic surface is built from `ContentNode`s that already carry `object_id`
(`WORKSPACE_ARCHITECTURE_2026-08-03.md` §7.4).

---

## 7. Trust mechanics

Trust is the scarce resource, not clicks. 91 silent changes must be trustable without checking 91.

| Mechanism | Implementation | Status |
|---|---|---|
| **Stratified sampling** | Group by cause; show count, confidence range, and the *k* weakest members. Checking the weakest is evidence about the rest. | New (presentation only) |
| **Cheap, total escape** | "Undo all 47" as cheap as "accept". **Bulk undo is a trust feature, not a convenience** — sampling is only safe when reversal is free. | Needs `transaction_id` |
| **Provenance in one action** | Any claim → its evidence → its PDF region. `evidence_items` + `bbox` already exist. | Model complete, unexposed |
| **Calibration feedback** | If the reviewer rejects 4 of 5 items at 0.9, the system's 0.9 is a lie. `CorrectionTelemetryEvent` already records every accept/reject/edit with latency — **collected, no consumer.** Connecting it closes the loop. | Data exists |
| **Fail closed, loudly** | Zero rules evaluated ⇒ error, never a pass. A compliance tool failing *open* is the worst failure mode. | Trap already recorded |
| **No silent change** | Every mutation in the log, including auto-applied ones. | Exists |

**Trust destroyers to design out:** a percentage that reaches 100% while problems remain (use *count of blocking
failures*, never a score); confirmation dialogs (they signal irreversibility, which is false here); being asked about
things the machine should have decided; and *not* being asked about things it should not have.

---

## 8. Decision-reduction mechanics, in measured order of leverage

| Lever | Measured effect | Cost |
|---|---|---|
| **1. Autonomy policy** | Already removes 91 of 96 decisions (94.8%) | Exists — but see §9.4 |
| **2. AI drafting for authorship** | 4 alt texts: ~16–20 min → ~8 min. The largest remaining cost | `POST /generate-alt-text` exists |
| **3. Batch by cause** | 34 suppressions → 3 audit groups | Needs `transaction_id` |
| **4. Auto-detect `LANG_001`** | Removes 1 blocking failure from **every document ever processed** | Trivial; §9.3 |
| **5. Invalidation-first ordering** | Prevents decisions a later decision discards | Ordering only |
| **6. Defer as a first-class action** | Preserves momentum; `PENDING_REVIEW` already exists | Exists |

**The metric this serves:** *blocking failures cleared per reviewer action.* Brinkman: 10 cleared in 6 decisions +
4 authorships = **1.0 per action**. That is the number to drive up, and it is computable today.

---

## 9. Recommended changes before implementation

Nine, each grounded in a measurement or in existing code.

| # | Change | Evidence | Severity |
|--:|---|---|---|
| **9.1** | **One accessibility rule: implausible heading density.** *(Reduced — the first draft proposed a `TRIAGE` state with an `ESCALATE` exit; the registry makes that unnecessary — §3.6.)* | Bruner: 26 pages, 1 heading, 46 silent corrections, an *almost clean* gate. The queue cannot see its own blind spot. | **Highest** — a correctness hole, but one rule fills it |
| **9.2** | **Separate the two gate conditions.** `REVIEW_001` ("you haven't finished") must not sit in the same list as `IMAGE_A11Y_001` ("this document is inaccessible") | 4 of 17 blocking failures are `REVIEW_001` — 24% of the gate is circular | High |
| **9.3** | **`LANG_001` should be a high-confidence proposal, not a blank** | Blocks 4 of 4 documents; language is trivially detectable | High — a free win on every document |
| **9.4** | **Autonomy must be (class **AND** confidence), not class alone** | `artifacts._POLICY` maps `PAGE_NUMBER`/`RUNNING_HEADER`/`RUNNING_FOOTER` → AUTO **regardless of confidence**. A 0.51-confidence suppression is applied silently. | High — a direct trust hazard |
| **9.5** | **Correct §3.3's priority rule:** HIGH-confidence-first for diagnostics, LOW-first for proposals | `scoring.priority_key` already sorts HIGH first, and is right | Medium — my error; the code was correct |
| **9.6** | **Three verbs in the queue** (decide / fix / write), one data model | R3. `IMAGE_A11Y_001` and `positional_only_h1` are the same shape in the model and nothing alike in the hand | Medium |
| **9.7** | **Previews are VERIFY-phase only** | §6.1 — an always-present preview invites WP-1 violations | Medium |
| **9.8** | **Export must be an entry in the decision log** | Downloads silently regenerate today; there is no record that an export happened. For a compliance tool, *"what did we certify, at what version"* is the primary audit question and is currently unanswerable. | High |
| **9.9** | **Do not build an approval workflow yet** | With one actor, export *is* approval — and, with 9.8, it is recorded. A separate approval step is ceremony without meaning until there are two actors. | — (a decision not to build) |

**Unchanged and load-bearing:** the fixed point as the definition of done; the two doors into a decision; the rail as
the only write path; findings derived / decisions stored; identity never position; validation advisory, export gating.

---

## 10. What would falsify this design

| Claim | Falsifier | How to test before building |
|---|---|---|
| Sampling 9 of 34 establishes justified trust | Reviewers reject a sampled batch's unsampled members at a material rate | Instrument bulk-undo-after-accept; it should be near zero |
| Authorship dominates the hour | A corpus where images are rare and heading defects dense | This measurement has **4 images in 57 pages** — a wider corpus may invert it. Re-measure before committing to authorship-first design |
| High-confidence proposals indicate miscalibration | A finding kind that is genuinely high-confidence yet needs human judgement (editorial, not technical) | Per-kind calibration from `CorrectionTelemetryEvent` |
| The reviewer never needs to edit prose | Real reviewers reaching for a text buffer | Then extend the **model** with the missing object — never let a surface hold the fact |
| Structural triage catches bad runs | A bad run with plausible aggregate statistics | Validate triage thresholds against the OCR-heavy documents excluded here |

**Measurement caveat, stated plainly:** these numbers cover the **four native-text documents**. The OCR-heavy
documents (`Nature of Enquiry`, `O Leary`) exceeded a 10-minute-per-run budget — Docling runs ≈2.5 min/page — and
were excluded. Scanned documents have no `TextBlock` data, take the line-by-line rendering path, and will have a
*different* work profile. This model should be re-measured against them before implementation; §10's second row is
the specific risk.
