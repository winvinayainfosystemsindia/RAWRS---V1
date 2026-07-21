# Architecture Review — Adversarial Pass on Phase 3.5A

Challenges `ARCHITECTURE_INVENTORY_2026-07-19.md`. Optimized for semantic correctness, remediation, reviewer workflow, maintainability, benchmark learning, enterprise scale — **not** for minimum diff.

**Verdict: 4 of 6 proposals rejected, 1 amended, 1 upheld. Two foundational subsystems were missing from the inventory entirely.**

---

## The Error Underneath All Six Proposals

RAWRS's output targets are **PDF/UA and WCAG**. Both are defined over a **structure tree** with an **Artifact vs Real Content** partition. RAWRS models neither, and the inventory did not notice.

Every proposal in it — sequence unification, region enum, relationship graph — is a flat-model workaround for that single absence.

| Model | Shape | Containment | Artifact concept |
|---|---|---|---|
| Tagged PDF / PDF-UA | Tree (`StructTreeRoot`) | Native | ✅ `/Artifact /Pagination` |
| HTML DOM / ARIA | Tree | Native | ✅ `aria-hidden`, `role=presentation` |
| TEI, JATS, DocBook | Tree | Native | ✅ `<fw>` forme work |
| DoclingDocument | Body tree + groups | Native | ✅ furniture |
| ALTO / PAGE-XML | Physical zones | Regions | ✅ zone types |
| **RAWRS Phase 1** | 12 parallel flat lists | ✗ | ✗ |
| **RAWRS Phase 2** | 1 flat `blocks` list | ✗ | 🟡 `is_running_header` bool |
| **Inventory's C-1** | Flat sequence | ✗ | ✗ |

No serious document model is a flat sequence. I proposed one anyway.

### Evidence found this pass

`P2Block` (`phase2_document.py:86-96`) is a union-by-optional-fields: `heading`/`text`/`table`/`figure`/`footnote` all `Optional` on one class. `list_style` and `list_number` are flat scalars — **a nested list is unrepresentable**. `P2Heading.is_running_header` (:48) and `P2Document.running_headers_detected` (:114) already exist and were never propagated to Phase 1: running-header awareness was designed, then stranded.

---

# C-1 · Object Sequence Unification — **REJECTED**

| | |
|---|---|
| **Current proposal** | `Document.sequence() -> List[SemanticObject]` — one flat ordered list on both paths |
| **My proposal** | **A-1: Structure Tree.** Typed nodes with children. Containment native: `Section > *`, `List > Item > Body > List`, `Table > Row > Cell`, `Figure > Caption` |
| **Evidence** | A flat sequence cannot express list nesting, table cell→header scope, or figure/caption grouping — all three are **hard PDF/UA conformance requirements**, not nice-to-haves. `P2Block.list_number` proves the flat model already failed at nesting |
| **Trade-offs** | Tree is harder to iterate than a list and harder to diff. Mitigate with one `walk()` in-order traversal — every current list consumer becomes `walk()` filtered by type |
| **Migration cost** | **Higher than C-1.** Tree build + all consumers. But C-1 pays most of that cost and then still can't emit conformant DOCX, so C-1's cost is largely *wasted* |
| **Long-term impact** | Reading order = in-order traversal, free. Regions = section nodes, free. Half of C-4 = containment, free. DOCX/HTML/EPUB export becomes a tree walk. Structural rules become tree queries |

**Decisive point:** C-1 costs ~80% of A-1 and cannot produce a conformant tagged document. It is the expensive half of the right answer.

---

# C-2 · Document-Wide Pre-Pass — **AMENDED (diagnosis right, design wrong)**

| | |
|---|---|
| **Current proposal** | `analyze_document(pages) -> DocumentProfile` collecting repeated text, consumed by the heading detector |
| **My proposal** | **A-2: Artifact/Content partition as a first-class, persisted classification** — not a transient stats bag consumed by one caller |
| **Evidence** | PDF/UA's exact concept. Running headers, footers and page numbers are **Pagination Artifacts**: real ink, deliberately outside the content tree. The brief says "remove them from outline/navigation/DOCX/markdown" — *removal is the wrong verb*. Remediation demands auditability; a reviewer must see what was reclassified and override it. TEI calls the same thing forme work (`<fw>`); ABBYY and Docling both call it furniture removal — universal in document understanding, never a bolt-on |
| **Trade-offs** | Persisted classification is heavier than a throwaway profile and needs a reviewer override surface. That surface is the point |
| **Migration cost** | Similar to C-2. Additive field + one pipeline stage. **Low, and it does not require A-1** |
| **Long-term impact** | A `DocumentProfile` consumed by one caller accretes fields until it is a god-object. A persisted partition is queryable by validation, export, navigation and the reviewer UI on day one |

**Upheld:** global reasoning must precede classification, and single-pass detection is the root cause of D1. **Rejected:** "profile" framing, and filtering rather than classifying.

---

# C-3 · Region Model — **REJECTED (category error, inherited from the brief)**

| | |
|---|---|
| **Current proposal** | One `DocumentRegion` enum as a flat field on `SemanticObject` |
| **My proposal** | **A-3: two orthogonal axes.** (1) *Physical zone* — header/footer/body/margin/gutter, per-page, geometric. (2) *Logical division* — front matter/body/appendix/back matter, spans pages, **a tree section node** |
| **Evidence** | The brief's own list mixes them: "Front Matter" and "Appendix" are logical divisions spanning many pages; "Running Header" and "Margin Note" are physical page zones. They are independent — front matter pages have running headers too. The field split is exactly why ALTO/PAGE-XML (physical) and TEI/JATS (logical) are separate standards. One enum forces a false choice per object |
| **Trade-offs** | Two fields, not one. Marginally more to reason about; eliminates an unresolvable modelling conflict |
| **Migration cost** | Physical zone: cheap, additive, needs only A-2. Logical division: **needs A-1**, since it *is* a tree node |
| **Long-term impact** | With one enum, "is this appendix heading inside a running header zone?" is unaskable. Sidebars and margin notes — both in the brief — are physical zones containing logical content; a single enum cannot represent them at all |

---

# C-4 · Relationship Graph — **REJECTED (over-general)**

| | |
|---|---|
| **Current proposal** | `Relationship(source_id, target_id, kind)` — open-vocabulary edge list on `Document` |
| **My proposal** | **A-5: closed, typed, non-tree edges only.** Exactly: `note_ref→note_body`, `xref→target`, `cell→header`, `continuation`, `figure→described_by`. Nothing else |
| **Evidence** | Most of what the inventory called "relationships" is **containment**, which A-1 gives natively — figure→caption is a parent/child, not an edge. What remains is small and already has standard vocabulary: PDF/UA `/Ref`, table `Headers`/`IDs`, ARIA `aria-describedby`. An untyped triple store invents a private ontology for concepts that are already standardised, and rots — nobody can enumerate which `kind` values are legal |
| **Trade-offs** | Closed vocabulary needs a schema change to extend. That friction is a feature: each new edge type must justify itself against an existing standard |
| **Migration cost** | Much lower than C-4 — the tree absorbs most edges. Needs A-1 and A-4 |
| **Long-term impact** | Each edge type maps 1:1 onto a DOCX/PDF-UA/HTML construct, so export is mechanical. A generic graph would need a bespoke interpreter per target |

---

# C-5 · Semantic Editor — **REJECTED (misdiagnosed as a frontend problem)**

| | |
|---|---|
| **Current proposal** | New frontend subsystem, prereq C-1 + C-4, "high risk, largest frontend change" |
| **My proposal** | **A-4: stable content-addressed identity** — the actual blocker — after which the editor is a *view over A-1's tree*, not a subsystem |
| **Evidence** | **Verified this pass: every object ID is positional.** `f"fn-{idx}"` (`footnote_detector.py:266`), `f"table-p{page}-{index}"` (`table_extractor.py:316,537`), `f"p{page}-{number}"` (`markdown_builder.py:452`). Insert one footnote and every downstream ID shifts. Correction history detaches, reviewer decisions reattach to the wrong objects, and **benchmark learning is impossible** — you cannot accumulate expert labels against identifiers that move |
| **Trade-offs** | Content-hash + structural-path IDs are longer and less human-readable than `fn-3`. Irrelevant — they are machine keys |
| **Migration cost** | **Moderate and urgent.** Independent of A-1; can and should ship first. Every day of reviewer decisions recorded against positional IDs is a day of unusable training data |
| **Long-term impact** | This is the precondition for "learn from expert remediators." The inventory listed that as a Phase 3.7 question. It is actually a **Phase 3.5B data-integrity emergency** |

**This gap was absent from the inventory's Part 2. That is the inventory's most serious omission.**

---

# C-6 · Unified Rule Engine — **REJECTED (right diagnosis, wrong cure)**

| | |
|---|---|
| **Current proposal** | Collapse validator's 35 hardcoded rules into the accessibility registry |
| **My proposal** | **A-6: one rule *framework*, three rule *families*, versioned.** Extraction correctness (validator) · cross-source verification (`verification/`) · accessibility conformance (`accessibility/`) |
| **Evidence** | The three engines answer genuinely different questions: *did we read the document correctly?* · *do two sources agree?* · *is the output accessible?* They have different lifecycles and different audiences — an extraction bug is an engineering defect, an accessibility gap is a remediation task. Merging the rule *sets* destroys that distinction. axe-core keeps rule families separate for the same reason. What should unify is the `Finding`+`Evidence` vocabulary and the rule interface, which `verification/engine.py` and `accessibility/registry.py` already converge on |
| **Trade-offs** | Three registries, not one. Offset by a single shared base and one shared output type |
| **Migration cost** | Lower than C-6 — no rule-set merge, only interface conformance for `validator.py` |
| **Long-term impact** | **Rule versioning** — which the inventory never mentioned — is mandatory for learning. Without `rule_id@version` on every finding you cannot tell whether a precision change came from better documents or a changed rule |

---

# Missing From the Inventory Entirely

### A-7 · Evaluation Harness — **required for the stated goal**

| | |
|---|---|
| Purpose | Make "learn from expert remediators" mechanically possible |
| Needs | Ground-truth corpus (`samples/benchmark/` exists) · replay detection against it · per-rule precision/recall · regression gates on merge · every reviewer decision persisted as a labelled example |
| Why it's foundational | "Semantic maturity" is unmeasurable without it. The project has repeatedly shipped features believed complete and later found broken — an eval harness is the structural fix for that pattern, not more careful reports |
| Prereq | A-4 (stable identity), A-6 (rule versioning) |

### A-8 · Persistence & Concurrency — **enterprise blocker**

| | |
|---|---|
| Evidence | `_jobs: Dict[str, Job] = {}` (`api/jobs.py:93`) — **in-memory; a restart loses every job.** `Document.version` is documented as explicitly *not* a concurrency token (`document.py:113-120`) |
| Consequence | Two reviewers on one document silently clobber each other. No audit trail survives a process restart. Neither is acceptable for enterprise remediation, which is a regulated, multi-reviewer workflow |
| Why it matters now | Correction history is the training data for A-7. Storing it in a process-local dict means it does not durably exist |

---

# Revised Dependency Graph

```
A-4 Stable Identity ──┬──> A-7 Eval Harness <── A-6 Rule Framework
  (urgent, cheap)     │
                      └──> A-1 Structure Tree ──┬──> A-3b Logical Divisions
                                                ├──> A-5 Typed Edges ──> Semantic Editor
                                                └──> Reading Order (free)
A-2 Artifact Partition ──> A-3a Physical Zones ──> D1/D2 fixes
  (independent, cheap)
A-8 Persistence ── independent, blocking for enterprise
```

| Phase | Contents | Why here |
|---|---|---|
| **3.5B** | Green suite · **A-4 identity** · A-2 artifact partition · A-3a zones · D1/D2 | A-4 stops data corruption today; A-2 is cheap and needs no tree |
| **3.6** | **A-1 structure tree** · A-3b logical divisions | The keystone. Needs a green suite beneath it |
| **3.7** | A-5 edges · A-6 framework · A-8 persistence | All unblocked by A-1/A-4 |
| **3.8** | Semantic editor · navigator · **A-7 eval harness** | Editor is now a tree view, not a subsystem |
| **4** | Design system | Unchanged — last |

---

# Where My Original Proposal Was Right

Not everything survives being wrong. Upheld:

| Claim | Status |
|---|---|
| Dual rendering paths are the central defect | ✅ Confirmed and strengthened |
| Global reasoning must precede heading classification (C-2's core) | ✅ Upheld |
| D1, D2 root causes | ✅ Unchanged |
| Two rule engines have diverged | ✅ Diagnosis right, cure wrong |
| Phase 4 goes last | ✅ Unchanged |

---

# Honest Risks In *This* Proposal

Arguing against a document I wrote hours ago biases toward the more elaborate design. Where A-* could be wrong:

| Risk | Assessment |
|---|---|
| A-1 tree is over-engineering for a PDF→DOCX tool | **Weak objection.** DOCX accessibility *is* tree-shaped; the tree is the deliverable, not an abstraction over it |
| A-1 migration could stall mid-way like `SemanticObject` did | **Real.** That migration is 5-of-9 done and abandoned. Mitigation: A-1 lands behind a byte-diff gate on all 10 benchmark PDFs, or it does not land |
| Two-axis regions are harder to explain to reviewers | **Real but acceptable** — the UI can surface one axis at a time |
| Three rule families entrench duplication I claimed to fix | **Partly fair.** The bet is that shared `Finding`/`Evidence` + shared interface captures most of the value at a fraction of the merge risk |
| A-4 IDs may not be stably derivable for low-confidence OCR objects | **Real, unsolved.** Content hashing assumes stable content; re-OCR can change text. Needs a fallback identity policy |

---

# Final Answer

> **"If RAWRS were starting today, would you still choose the architecture proposed in the inventory?"**

**No.**

The inventory optimized for low risk and small diffs — precisely what this review was instructed not to optimize for — and it produced a plan that sequences cheap additive work ahead of the change everything else depends on. Its C-1 was a flat sequence in a domain where every credible model, and both compliance targets, are trees. Its C-3 folded two orthogonal axes into one enum. Its C-4 invented an ontology for relationships that PDF/UA and ARIA already standardise.

Worst: it never noticed that **object identity is positional**, so every reviewer decision recorded today is training data attached to an identifier that moves. It listed "learn from expert remediators" as a question for Phase 3.7 while the data required to answer it was being silently corrupted.

**Starting today I would build, in order:** stable identity (A-4) → artifact/content partition (A-2) → structure tree (A-1) → typed edges (A-5) → rule framework + eval harness (A-6/A-7), with persistence (A-8) landing before any multi-reviewer deployment.

That is a larger programme than the inventory's. It is also the one that makes the original Phase 3.5 brief — regions, semantic editing, document-wide reasoning, reference linking — expressible rather than approximable.
