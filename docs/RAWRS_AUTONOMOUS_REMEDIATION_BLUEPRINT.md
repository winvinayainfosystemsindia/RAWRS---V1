# RAWRS — Autonomous Remediation Phase: Engineering Blueprint

**Phase objective:** *Automatically produce outputs that match or exceed the quality of benchmark human-remediated documents, while minimizing manual work for professional remediators.*

**Status:** partially implemented. F0, L1, L2 and L3's first two steps have shipped;
L4–L8 remain design only. This document is still the engineering specification for the
phase — the roadmap in §4 is the plan of record, annotated below with what exists.

| Item | State | Commit |
|---|---|---|
| F0 Benchmark Differ | **shipped** | `ce3ac8a` |
| F1 Span-level text model | **shipped earlier** (`feature_005`) | — |
| L1 Physical-zone assignment | **shipped** | `21f822e` |
| L1.2 Document-wide repetition analysis | **shipped** | `5180b78` |
| L2 Artifact classification | **shipped** | `9999418` |
| L2.1 Running-title classification | **shipped** | `c9fa131` |
| L2.2 Reversible artifact suppression | **shipped** | `bac3764` |
| L3 Artifact-aware heading candidacy | **shipped** | `1eeaae3` |
| L3.1 Heading detection produces evidence | **shipped** | `d2ba03b` |
| L3.2 Retire positional-H1 on measured grounds | **shipped** — position ranks, never decides; 89 → 86 corpus headings, all 3 removed were wrong | *this commit* |
| L4 Footnote/endnote distinction | design only | — |
| L5 Front-page reconstruction | design only | — |
| L6 Structure-preserving output | design only | — |
| L7 Auto-remediation composer | design only | — |
| L8 Canonical editing | design only | — |

**Interleaved work not in this roadmap.** Between L3.1 and L4 the correction rail was made
a universal pipeline primitive (ADR-016) and the projection architecture's P1/P2 landed
(ADR-018, ADR-019). Both were prerequisites this blueprint assumed rather than scheduled:
§2.4's composer is "90% wiring into machinery that already exists", and that machinery only
became path-agnostic and single-entry in `9348bb4`/`435bc1b`. See `ADR_2026-08-03.md`.

**Gate change.** §4's "measured against the corpus before/after" still holds for detector
quality, but any commit that touches a projection is additionally gated on projection
correctness (ADR-020): `python -m src.benchmark --projection <pdf_dir>`. Byte parity is
retired — see ADR-020 for why it was actively harmful here.

---

## 0. Framing

RAWRS today is a *conservative extractor with a review layer*: it reconstructs structure, verifies it against a second source, scores accessibility, and lets a human accept proposals. It deliberately does **not** make aggressive editorial decisions.

This phase changes the product's centre of gravity. RAWRS must now behave like an **experienced remediator**: it performs the editorial transformations a human expert would, expresses each as a reversible, evidence-backed proposal, and reduces the human to a verifier. The benchmark human-remediated documents (`samples/benchmark/remediated_docx/`, one per source PDF) stop being an evaluation set and become the **specification** — the concrete definition of "correct output."

The single most important architectural decision of this phase: **we already have the right substrate for autonomous, reversible, evidence-backed remediation — the cross-source correction rail (`Finding → CorrectionRecord → apply/revert`, with `EvidenceBundle` + confidence).** Autonomous remediation is not a new engine; it is a large set of new *proposers* feeding the machinery that already exists. Almost everything below extends current subsystems rather than replacing them.

---

## 1. Architectural Vision

### 1.1 The thesis: classify → interpret → remediate → verify

RAWRS's pipeline currently interleaves *interpretation* (heading detection, footnote detection) with weak, per-object heuristics that repeatedly re-derive the same layout facts (is this a running header? is this the title?). The result is fragile: the heading detector, for example, carries roughly six heuristic tiers whose entire job is to *decline* to promote a running masthead to a heading — one candidate at a time.

The new architecture makes layout understanding a **first-class, document-wide pre-pass** that runs *before* any semantic interpreter:

```
INGEST ─► LAYOUT INTELLIGENCE ─► SEMANTIC INTERPRETATION ─► REMEDIATION ─► VERIFY/SCORE ─► REVIEW ─► EXPORT
          (classify)             (interpret content only)   (auto-fix)     (existing)      (existing) (structure-preserving)
```

- **Layout Intelligence** classifies *every* block, document-wide, as **content** or **artifact** (running header, running footer, publisher line, journal name, page number, watermark, scan band), using repetition, position, physical zone, and typography. Artifacts are removed from the candidate pool for *all* downstream interpreters. The heading detector never sees the masthead again.
- **Semantic interpretation** (headings, footnotes/endnotes, front matter, tables, figures, lists) then runs on **content-only** blocks with richer signals, and produces cleaner results because the noise is already gone.
- **Remediation** composes the editorial transformations a human would apply — suppress the running header, reconstruct the title page, relocate footnotes to page bottoms, repair the heading hierarchy — each as a reversible `CorrectionRecord` carrying **reason, confidence, affected elements, and an undo**.
- **Verify/score/review/export** are the existing layers, extended to preserve page structure on the way out.

### 1.2 The benchmark becomes the specification

A new **Benchmark Differ** parses each human-remediated DOCX into the canonical `Document` model and diffs it against RAWRS's own output for the same source. This yields, per document, a structured *remediation-gap report*: which headings the human kept/dropped, what the human did to the title block, where footnotes landed, which running elements were removed. This harness is built **first**, because:

1. It converts "human quality" from a vibe into a measurable target (structural precision/recall per element type).
2. It is the substrate for **pattern mining**: recurring human transformations (e.g. "first occurrence of a repeated bold masthead is deleted," "title block is re-ordered to title → authors → affiliations → abstract") are discovered by aggregating diffs across the corpus, then generalized into algorithms — *not* hardcoded per document.

### 1.3 Two invariants that govern the whole phase

- **Nothing is ever destroyed automatically.** Every automatic transformation is a suppression or a reordering expressed as a reversible correction. "Delete the running header" means "mark it `artifact`, exclude it from output, and keep it one click from restoration."
- **The human is always the final authority.** Auto-applied corrections are still corrections: visible, explained, confidence-scored, and revertible. High-confidence transformations may auto-apply; lower-confidence ones stay proposed. The remediator verifies rather than rebuilds.

---

## 2. Subsystems That Must Change

Ordered by architectural layer. "New" = net-new module; "Extend" = build on an existing one.

### 2.1 Foundation

- **Span-level text model — Extend the document model (currently the hard blocker).** `TextBlock` is line-granularity today: a single `font_size`, a single `is_bold`, a `bbox`, and text — no font name, colour, per-character size/flags, or baseline. This impoverishment is the root cause of both fragile heading detection (the detector already has to reverse-engineer bold from font-subset names like Brinkman's `AdvP7D0F`) and unreliable footnote detection (superscript markers need baseline + size). Introduce an **additive** `Span` layer (font name, size, flags, baseline offset, colour) inside `TextBlock`, populated from data PyMuPDF already extracts and currently discards. Every downstream classifier gains real typographic evidence. This is the enabling prerequisite for §2.2–§2.5.

- **Benchmark Differ + gap report — New.** Parse `remediated_docx` into the canonical model; align to RAWRS output; emit a per-document, per-element structured diff and corpus-level aggregates. Becomes the phase's regression spec and pattern-mining input.

### 2.2 Layout Intelligence (the new pre-pass)

- **Document-wide repetition analysis — New.** Detect text that recurs across pages at a stable physical position: repeated headers/footers, **alternating** (odd/even) headers, publisher/journal lines, page-number patterns, watermarks. Produces per-block repetition evidence (recurrence count, position stability, alternation phase).
- **Physical zone assignment — New (model field + detector).** Tag each block with a zone: header / footer / body / margin / gutter, from page geometry. (Present in the backlog as a missing feature; foundational here.)
- **Artifact classification — New, but emits via the correction rail.** Combine repetition + zone + typography into a per-block classification `{content | running_header | running_footer | publisher_line | page_number | watermark | scan_band}` with confidence and evidence. The existing **scanned-page reconstruction band filter** is the first, already-shipped member of this family and should be folded under this classifier's umbrella rather than left as a standalone special case.

### 2.3 Semantic interpretation (operate on content-only blocks)

- **Heading detector — Redesign (replace the tier pile; keep the module).** Remove the two assumptions the phase brief calls out: "large text ⇒ heading" and "first productive line ⇒ H1." The redesigned detector consumes **content-only** blocks (artifacts already removed) and ranks candidates on principled, span-level signals: typography (font identity/size/weight *relative to the document's body font*), whitespace isolation, numbering patterns, document position, hierarchy consistency, and neighbouring-block context. Repetition-awareness moves *out* of the detector (Layout Intelligence owns it), so "a running header can never become a heading" becomes a structural guarantee, not a per-tier decline.
- **Footnote vs endnote detection — Extend `footnotes/`.** The model already distinguishes `NoteType.FOOTNOTE`/`ENDNOTE` with an `anchor_page_number`; the detector does not reliably classify them. New strategy: footnotes are page-anchored blocks in the footer zone, below a separator rule, with a marker that matches an in-body superscript reference on the same page; endnotes are a terminal, sequentially-numbered list section. Detect both, associate footnotes to their originating sentence and page, and record whether a separator rule was present. Some documents contain both — classification is per-note, not per-document.
- **Front-matter reconstruction — Extend `frontmatter/` from extraction into reconstruction.** Extraction (title/authors/affiliations) exists. Add detection of the fuller title-block element set — emails, publisher, journal metadata, copyright, DOI, abstract — via zone + typography + pattern signals, and emit them in a **canonical remediated layout learned from the benchmark**, generalized across the corpus (never hardcoded to Brinkman).

### 2.4 Remediation orchestration

- **Auto-remediation composer — New, built entirely on the correction rail.** A stage that turns Layout-Intelligence and semantic findings into concrete, reversible `CorrectionRecord`s: *suppress running header*, *reconstruct title page*, *repair heading level*, *relocate footnote to page bottom*, *classify + hide artifact*, *preserve page break*. Each carries `reason`, `confidence`, `evidence_items`, `affected object ids`, and an `apply/revert`. A confidence policy decides auto-apply vs propose. This is the "AI remediator" — and it is 90% wiring into machinery that already exists (`engine.findings_to_corrections`, `apply_correction`, `revert_correction`, `EvidenceBundle`, `CorrectionStatus`).

### 2.5 Structure-preserving output + editing

- **Structure-preserving generation — Extend `markdown/` and `docx/`.** Outputs must carry the *logical page structure*: page breaks, printed page numbers (the page-numbering policy + `printed_label` already exist), running headers/footers emitted as **suppressed-but-restorable** artifacts, footnotes rendered at page bottom below a rule (endnotes at document end), front matter in reconstructed order. The output should *feel like the original*, not merely contain its text.
- **Canonical editing architecture — New (frontend + a round-trip contract).** See §7 (Additional) for the full design; summarized in §2 as: the `Document` model is the single editing target; Markdown/DOCX are projections; a block-anchored round-trip contract keeps them from ever diverging.

### 2.6 Unchanged / lightly touched

Cross-source verification engine, accessibility engine + scoring + `export_ready`, OCR routing, persistence, and the validation queue are **not** redesigned. They gain new *inputs* (more corrections, more findings, cleaner structure) but keep their contracts.

---

## 3. Dependency Graph (Implementation Order)

```
                         ┌─────────────────────────────┐
                         │ F0  Benchmark Differ (spec)  │  ← measurement first; unblocks everything
                         └──────────────┬──────────────┘
                                        │
                         ┌──────────────▼──────────────┐
                         │ F1  Span-level text model    │  ← typographic signal foundation
                         └──────────────┬──────────────┘
                 ┌──────────────────────┼───────────────────────┐
                 ▼                      ▼                        ▼
      ┌───────────────────┐  ┌────────────────────┐   ┌────────────────────┐
      │ L1 Repetition +   │  │  (F1 also feeds     │   │  (F0 gates every   │
      │    physical zones │  │   heading + notes)  │   │   layer's accept)  │
      └─────────┬─────────┘  └────────────────────┘   └────────────────────┘
                ▼
      ┌───────────────────────────┐
      │ L2 Artifact classification│  (absorbs scanned-band filter)
      │     + reversible suppress │
      └─────────┬─────────────────┘
                ▼
      ┌───────────────────────────┐      ┌───────────────────────────┐
      │ L3 Heading detector       │      │ L4 Footnote/endnote        │
      │    redesign (content-only)│      │    distinction + anchoring │
      └─────────┬─────────────────┘      └─────────┬─────────────────┘
                └───────────────┬───────────────────┘
                                ▼
                   ┌───────────────────────────┐
                   │ L5 Front-page reconstruction│  (generalized from benchmark)
                   └─────────────┬───────────────┘
                                 ▼
                   ┌───────────────────────────┐
                   │ L6 Structure-preserving    │
                   │    Markdown + DOCX output  │
                   └─────────────┬──────────────┘
                                 ▼
                   ┌───────────────────────────┐
                   │ L7 Auto-remediation        │  (composes L1–L6 as reversible corrections)
                   │    composer + confidence   │
                   └─────────────┬──────────────┘
                                 ▼
                   ┌───────────────────────────┐
                   │ L8 Canonical editing       │  (model-bound editor + anchored round-trip)
                   └───────────────────────────┘
```

**Critical path:** F0 → F1 → L1 → L2 → L3 (heading redesign is the headline user-visible win and depends on artifacts already being classified out). L4/L5 parallel L3 once L1/L2 land. L6 depends on L1–L5 having produced the structural facts to preserve. L7 is the "make it autonomous" layer and depends on L1–L6 existing as proposers. L8 is orthogonal and can begin after F1 but is best sequenced last to edit a model that is already high-quality.

**Why this order minimizes rework:** measurement (F0) before change; the shared typographic foundation (F1) before every classifier; artifact removal (L1/L2) before interpretation (L3/L4) so interpreters are written once against clean input rather than being patched to dodge noise; output preservation (L6) after the structure exists to preserve; autonomy (L7) last among the engine changes so it orchestrates finished, individually-tested proposers.

---

## 4. Commit Roadmap (One-Commit Discipline)

Each commit compiles, keeps the app working, is independently revertible, and is gated on the Benchmark Differ where behaviour changes. Foundational commits are additive (no behaviour change); interpreter commits are measured against the corpus before/after.

**F0 — Benchmark Differ**
1. Parse `remediated_docx` → canonical `Document` (DOCX importer, read-only).
2. Structural align + per-element gap report + corpus aggregate; CLI/report artifact. *(No product behaviour change.)*

**F1 — Span-level text model**
3. Add additive `Span` layer to `TextBlock`; populate from parser; leave all consumers reading the existing line-level fields (behaviour identical).
4. (Optional, measured) Switch heading/footnote signal reads to span data where it strictly improves a benchmarked metric.

**L1 — Layout Intelligence pre-pass**
5. Physical-zone model field + assignment (additive; nothing consumes it yet).
6. Document-wide repetition analysis (produces evidence; no suppression yet).
7. Alternating (odd/even) header detection on top of the repetition pass.

**L2 — Artifact classification + reversible suppression**
8. Artifact classifier (content/header/footer/publisher/page-number/watermark) with evidence + confidence; fold the scanned-band filter under it.
9. Emit artifact suppressions as reversible corrections; exclude suppressed blocks from downstream candidate pools. *(Gated: heading/validation deltas measured on corpus.)*

**L3 — Heading detector redesign**
10. Re-implement on content-only input with span/hierarchy signals; retire the positional-first-line and large-text assumptions. *(Gated: heading precision/recall vs benchmark must not regress; running-header-as-heading rate → 0.)*

**L4 — Footnote/endnote distinction**
11. Per-note footnote-vs-endnote classification + page/sentence anchoring + separator capture. *(Gated: note placement vs benchmark.)*

**L5 — Front-page reconstruction**
12. Title-block element detection (email/publisher/journal/copyright/DOI/abstract).
13. Generalized reconstruction ordering mined from the corpus (not hardcoded). *(Gated: front-matter structural match vs benchmark, all applicable docs.)*

**L6 — Structure-preserving output**
14. Emit page breaks + printed page numbers in Markdown/DOCX.
15. Emit running headers/footers as restorable artifacts; footnotes at page bottom w/ rule, endnotes at end. *(Gated: DOCX structure vs remediated_docx.)*

**L7 — Auto-remediation composer**
16. Composer that turns L1–L6 findings into reversible corrections with reason/confidence/affected/undo.
17. Confidence policy for auto-apply vs propose; surface every auto decision in review. *(Gated: end-to-end corpus quality; zero irreversible actions.)*

**L8 — Canonical editing**
18. Model-bound structured editor (headings/paragraphs/tables/images/metadata/footnotes/page-labels) over existing PATCH surfaces.
19. Block-anchored Markdown round-trip contract (edit → re-map to model; unmappable edits become review items). DOCX stays output-only.

Roughly nineteen commits; F0–F1 and every "additive" step are behaviour-neutral, so risk concentrates in the gated interpreter commits (9, 10, 11, 13, 15, 16), each individually revertible.

---

## 5. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| **Autonomy erodes trust if a confident auto-fix is wrong.** | High — a compliance tool that silently mis-edits is worse than a manual one. | Everything routes through the reversible correction rail; confidence-gated auto-apply; every decision explained and one click from undo; the benchmark differ measures false-positive edits per corpus run before any confidence threshold is raised. |
| **Span-level model touches the frozen `TextBlock`/`Page` contract.** | High — broad blast radius. | Strictly additive layer; existing line-level fields untouched; consumers migrate one at a time, each migration gated on a benchmark metric improvement. |
| **Heading redesign regresses documents the current tiers happen to get right.** | Medium-High | F0 differ makes heading precision/recall a hard gate; the redesign ships only if it dominates the old tiers across the corpus; keep the old detector behind a flag until parity is proven. |
| **Pattern-mining overfits to 10 documents.** | Medium | Prefer signals with a mechanistic justification (repetition, zone, typography) over corpus-shaped constants; hold out documents during mining; treat mined constants as calibration knobs, not laws; expand corpus where a pattern is thin. |
| **Round-trip Markdown editing diverges from the model.** | Medium | Never treat free-text Markdown as authoritative; block-anchored contract; unmappable edits surface as explicit review items rather than silently rewriting the model; DOCX is output-only (never re-imported). |
| **Front-page reconstruction reorders content a human wouldn't.** | Medium | Reconstruction is a *proposed* correction with visible before/after; benchmark-gated; conservative default (detect-and-tag) with reordering behind higher confidence. |
| **Scope: this is a multi-quarter phase.** | Medium | The one-commit discipline + additive foundations keep the product shippable at every step; each layer delivers standalone value (artifact classification alone fixes the running-header bug). |
| **The Mathpix import path and native path may need parity.** | Medium | Layout Intelligence operates on the canonical model, so it benefits both paths; but repetition/zone signals are richer on the native (geometry) path — measure both, and treat the native path as the primary target for structure preservation. |

---

## 6. Extend, Don't Replace

The current architecture is well-suited to this phase in five decisive ways; the phase should build on them, not around them.

1. **The correction rail is the autonomy engine.** `CorrectionRecord` already carries original value, proposed value, evidence, confidence, reviewer decision, and reversible `apply/revert`. The phase's non-negotiable requirement — every auto decision has reason/confidence/affected-elements/reversibility — is *already the shape of a correction*. Do not build a parallel "auto-edit" system; emit corrections.
2. **The verification engine's evidence model is the classifier substrate.** `EvidenceBundle`/`EvidenceSignal` (weighted, named, fusable) is exactly what repetition/zone/typography classification needs to be transparent and calibratable. Reuse it for artifact and heading confidence.
3. **The accessibility engine + `export_ready` is the acceptance gate for autonomy.** Autonomous remediation should *move the score and the readiness gate*; the just-completed convergence means there is one canonical place to measure whether an auto-fix helped. Keep it as the arbiter.
4. **The canonical `Document` model is the right editing target.** Markdown-as-source-of-truth already means DOCX is generated, not authored. Editing extends this: the model is authored, both outputs are generated — so they cannot diverge by construction.
5. **The benchmark corpus + manifest is already the spec substrate.** `remediated_docx` exists for all ten documents. The phase formalizes it as the specification rather than inventing a new evaluation mechanism.

Replace only where the design is fundamentally wrong for the goal: the **heading detector's heuristic-tier stack** (replace with classify-then-interpret) and the **implicit assumption that layout facts are re-derived per interpreter** (replace with a shared Layout Intelligence pre-pass).

---

## 7. Additional Improvements (Necessary, Beyond the Brief)

1. **Span-level text model is a hard prerequisite, not an option.** The brief asks for typography-driven heading detection and reliable footnote detection; both are impossible to do well on the current line-granularity `TextBlock` (no font name, no colour, no baseline). Elevate the span model to a Foundation deliverable (F1) rather than leaving it implicit.

2. **A confidence-and-provenance model for every automatic decision.** Standardize the metadata the brief requires (reason, confidence, affected elements, reversibility) as a single provenance record attached to each correction, and surface it uniformly in the review UI ("RAWRS removed this running header — recurred on 22 pages, 0.97 confidence — Restore"). This turns autonomy into something a remediator can audit at a glance.

3. **A "trust dial."** Let the remediator set the auto-apply confidence threshold per document or per transformation type (aggressive vs conservative). The same corrections are produced either way; the dial only decides how many auto-apply vs wait for review. This makes autonomy adoptable incrementally.

4. **The Benchmark Differ should ship a living scorecard.** Beyond gating commits, publish a per-document, per-element "distance to human quality" dashboard so the phase's progress toward the objective is continuously visible — the objective is literally "match the benchmark," so measured distance-to-benchmark is the phase's primary KPI.

5. **Canonical editing round-trip contract (the explicit answer to Goal 6).** Edit the **model**, always. Object edits (headings, tables, images, metadata, footnotes, page labels) map directly through the existing PATCH surfaces. Markdown is a **projection**: every generated block carries a stable anchor id; a structured re-import parser maps an edited block back to its model node; an edit that breaks the anchor contract (e.g. a structural change the parser can't localize) becomes a **review item**, never a silent model rewrite. DOCX is **output-only** — never re-imported — because it is a lossy projection. Because both outputs are generated from one authored model, Markdown and DOCX cannot diverge; the only synchronization that exists is model → outputs, which is deterministic.

6. **Idempotency and re-run safety for autonomous transforms.** Re-running the pipeline (or re-processing after an edit) must not double-apply or fight the reviewer's decisions. Corrections already carry status; the composer must respect terminal reviewer states (accepted/rejected/ignored) and never re-propose what a human has resolved.

7. **Artifact classification should be one taxonomy, not many special cases.** The scanned-page reconstruction band filter, running-header suppression, page-number stripping, and watermark handling are the *same operation* — "this block is a repeated/positional artifact, not content." Unify them under one classifier with one evidence model and one reversible-suppression path, so future artifact types (rotated stamps, gutter marks) are a new classifier signal rather than a new subsystem.

8. **Explicit "originality" preservation contract in outputs.** The brief wants outputs to *feel like the original*. Make that a testable contract in the Benchmark Differ: page-break fidelity, page-number fidelity, front-matter order fidelity, and note-placement fidelity are measured element types, not prose aspirations.

---

## 8. Success Criteria

The phase is complete when, across the benchmark corpus, RAWRS's automatically-produced output — before any human touches it — reaches or exceeds the human-remediated DOCX on the measured element types (headings, running-element removal, front-matter structure, footnote/endnote placement, page-structure fidelity), **and** every automatic transformation that got it there is visible, explained, confidence-scored, and reversible in the review workspace. At that point the remediator's job has become verification, not reconstruction — which is the objective.

---

## 9. Architectural Extensions

The following three additions **extend** the blueprint without changing its core. The pipeline shape (classify → interpret → remediate → verify), the correction rail as the autonomy engine, the shared evidence/confidence model, and the benchmark-as-specification principle are all unchanged. Each addition slots into an existing seam: one *structures* the remediation stage (Transformation Library), one adds a *scoping layer* between classification and interpretation (Semantic Regions), and one supplies optional *priors* into both (Remediation Profiles). Nothing here introduces a second decision path or a bypass around the reversible correction rail.

### 9.1 Transformation Library

**Problem it solves.** Left unstructured, the auto-remediation composer (L7) becomes exactly what this phase set out to avoid: a growing pile of per-case heuristics. The Transformation Library is the discipline that keeps remediation *generalized* — one named, benchmark-validated transformation per recurring human pattern, instead of scattered special cases.

**What it is.** A registry of `Transformation`s, mirroring the two registries the codebase already uses (the verification engine's asset-verifier registry and the accessibility rule registry) — so this is a familiar pattern, not a new paradigm. Each `Transformation` is a self-contained, reversible remediation unit with a fixed contract:

| Contract element | Responsibility |
|---|---|
| `applies_to` | the semantic region(s) and/or artifact classes the transformation is scoped to (see §9.2) |
| `detect(document, region)` | gather evidence and decide applicability; returns candidate targets with an `EvidenceBundle` |
| `propose(...)` | emit **reversible `CorrectionRecord`s** (reason, confidence, affected object ids, apply/revert) — it never mutates the document directly |
| `confidence(...)` | the transparent, evidence-weighted score used by the auto-apply-vs-propose policy |
| `benchmark_spec` | the element type(s) in the Benchmark Differ this transformation is measured against |

The initial library is the set already named in the phase brief, each now a first-class, independently-testable unit:

- **RunningHeaderSuppression** / **RunningFooterSuppression** / **PageNumberStripping** / **WatermarkSuppression** — artifact suppressions (L2), reversible.
- **FrontPageReconstruction** — title-block detection + canonical reordering (L5).
- **HeadingNormalization** — hierarchy repair, level correction, spurious-heading demotion (L3).
- **FootnotePlacement** — relocate to page bottom with a rule; endnote-to-document-end (L4/L6).
- **ArtifactSuppression** — the generic parent under which the scanned-page-reconstruction band filter and all repeated/positional artifacts unify (§7.7).

**Why it generalizes instead of accumulating heuristics.** A transformation is defined by *evidence and parameters*, not by document-specific constants. New recurring patterns discovered by the Benchmark Differ become either (a) a new parameterization of an existing transformation, or (b) a new transformation with its own benchmark spec — never an `if document == X` branch. Adding a transformation is adding one registered unit with one measured target, exactly as adding an accessibility rule is today.

**Relationship to L7.** The Auto-Remediation Composer stops being a bag of logic and becomes the **runner** over the library: it orders transformations (artifact suppression before interpretation before reconstruction), invokes each `detect`/`propose`, routes the resulting corrections through the existing rail, and applies the confidence/trust-dial policy. The library is the *catalog of what to fix*; the rail is *how it is applied and undone*; the composer is *the schedule*.

### 9.2 Document Semantic Regions

**Problem it solves.** Interpreters today treat the document as a uniform stream of blocks, so a bold line in a bibliography can be mistaken for a heading, a numbered list at the end can be confused between endnotes and a reference list, and title reconstruction has no natural boundary. Coarse **semantic regions** give every interpreter the structural context a human uses implicitly.

**What it is.** An additive, document-level partition of the content blocks (after artifacts are removed, §2.2) into an ordered sequence of regions, each with a type, a block range, a confidence, and evidence:

`Front Matter · Body · References · Bibliography · Appendix · Index · Glossary` (plus, pragmatically, *Table of Contents* and *Abstract* as front-matter sub-regions).

Regions are detected from signals RAWRS already has or gains this phase: terminal/positional priors (front matter leads, references/appendix/index trail), section-heading keywords, content-pattern signals (citation density, alphabetical ordering, entry regularity), and benchmark behaviour. A region is stored as a model field, and every region boundary is itself a **reviewable, reversible** decision — the reviewer can move a boundary or re-type a region exactly like any other correction.

**How regions influence downstream interpretation.** Regions become a *precondition* on the interpreters and transformations rather than changing their internals:

- **Heading detection.** Region type conditions candidate scoring and hierarchy: a "References"/"Bibliography"/"Index" region contributes exactly one terminal section heading and treats its remaining lines as entries, not heading candidates (killing the "bold citation becomes a heading" failure); appendix regions may legitimately restart numbering; body-region hierarchy is validated for monotonic nesting. This is the principled successor to the heuristic tiers — region context replaces per-line declining.
- **Title reconstruction.** FrontPageReconstruction is *scoped to the Front Matter region only*, so it can never reorder body content, and abstract/keyword detection is bounded to where those elements actually live.
- **Footnote / endnote handling.** Footnotes are Body-region, page-anchored; the terminal numbered list is disambiguated by *which region it sits in* — an endnotes region yields endnotes, a References/Bibliography region yields citations, not notes. This resolves the single hardest ambiguity in L4 structurally.
- **Metadata extraction.** DOI, journal, publisher, copyright, and keyword detection are scoped to Front Matter (and References for cited-source metadata), sharply reducing false positives elsewhere.

Regions are the **`applies_to` mechanism** for the Transformation Library (§9.1): a transformation declares the regions it may act in, and the composer never runs it outside them.

### 9.3 Remediation Profiles

**Problem it solves.** Documents from the same publisher, journal, or family share strong conventions — a fixed title-page layout, a known masthead, a page-numbering style, a house heading style. Rediscovering these per document from scratch wastes evidence and lowers confidence. Profiles let RAWRS *remember* a family's conventions and apply them as **priors**, not rules.

**What it is.** An optional, learned bundle of expectations for a document family:

- expected front-matter layout and element ordering (title → authors → affiliations → email → abstract, etc.);
- publisher/journal metadata placement;
- running-header/footer conventions (which recurring lines are mastheads, alternation phase);
- page-numbering conventions;
- common heading styles (the family's body-relative typographic signature for each level).

A profile is **data, never code** — a set of parameters and expected layouts consumed by the *same* evidence-based transformations and region detectors. A document is matched to a profile by fingerprint (recurring publisher line, journal name, DOI prefix, font signature, page geometry); on a match, the profile *raises or lowers the confidence* of the relevant transformations and *supplies expected layouts* to reconstruction — it can bias a decision but never force one.

**Transparent, reviewable, overridable — by construction.**

- **Transparent.** Every profile-influenced decision names the profile in its provenance record ("matched *Publisher X* profile at 0.88; expects title-block order T→A→Aff→Abstract"), so the reviewer sees exactly what the prior contributed.
- **Reviewable.** Profiles are inspectable objects; a reviewer can see, per document, which profile matched and what it changed.
- **Overridable.** The reviewer can detach a profile from a document, or override any single decision — and because every profile-influenced action is still a reversible correction gated by confidence, a *wrong* profile cannot force a bad edit: it only shifts priors, and the correction rail still requires the outcome to survive review (or be one click from undo).

**How profiles are learned (benchmark-first, never hardcoded).** When the Benchmark Differ finds that several documents share a family and a recurring transformation, that pattern is generalized into a profile — the same mining discipline the phase uses everywhere, one level up. Reviewers can also *promote* a confirmed reconstruction into a profile ("save this publisher's title-page layout"), turning human corrections into reusable, transparent priors. Profiles thus close the loop: human remediation decisions become learned priors that reduce future human effort.

### 9.4 Integration Into the Existing Blueprint (no core change)

These additions attach to seams that already exist:

```
INGEST ─► LAYOUT INTELLIGENCE ─► [SEMANTIC REGIONS] ─► SEMANTIC INTERPRETATION ─► REMEDIATION ─► VERIFY/SCORE ─► REVIEW ─► EXPORT
          (classify)             (§9.2 new scoping     (interpret, now             (§9.1 Transformation
                                   layer, additive)     region-conditioned)         Library runs here)
                                        ▲                                                  ▲
                                        └──────────────  §9.3 Remediation Profiles  ───────┘
                                             (optional priors into regions + transformations,
                                              via the existing evidence/confidence model)
```

- **Semantic Regions** are a new *additive stage and model field* between Layout Intelligence (§2.2) and Semantic Interpretation (§2.3) — call it **L2.5** in the dependency graph. Interpreters gain a region precondition; their contracts are unchanged.
- **The Transformation Library** is the *formalization of the L7 composer*, not a replacement: L7 becomes "run the registered transformations." The reversible correction rail, evidence model, and confidence policy it uses are all pre-existing.
- **Remediation Profiles** are a *cross-cutting optional priors layer* (**L9**) that parameterizes regions and transformations through the same `EvidenceBundle`/confidence channel every classifier already uses. With no profile matched, the system behaves exactly as §1–§8 describe; a profile only tunes confidences and supplies expected layouts.

**Roadmap deltas (still one commit at a time, still benchmark-gated):**

- **L2.5 — Semantic Regions:** (a) additive `semantic_regions` model field + detector (no consumer yet); (b) make heading detection region-conditioned; (c) scope footnote/endnote and metadata/front-matter to regions. Slots between roadmap steps 9 and 10; each is benchmark-gated on the interpreter it conditions.
- **L7 — Transformation Library:** split step 16 into (16a) define the `Transformation` contract + registry and migrate the artifact suppressors into it; (16b+) add each transformation as its own registered, benchmark-gated unit. No new step count in principle — it re-shapes L7 rather than adding a parallel system.
- **L9 — Remediation Profiles (optional, last):** (a) profile object + fingerprint matcher (priors off by default); (b) wire profile priors into region/transformation confidence with full provenance; (c) reviewer "save/detach/override profile" surface. Sequenced after the library and regions exist, because a profile is only meaningful as priors *over* them.

**Invariants preserved.** Everything above still routes through the reversible correction rail; still carries reason/confidence/affected-elements/reversibility; is still measured against `remediated_docx` via the Benchmark Differ; and still leaves the human as the final authority. The three additions make the same architecture **more general** (transformations over heuristics), **more context-aware** (regions over uniform streams), and **more efficient over time** (profiles that learn a family's conventions) — without altering the core flow, the model's frozen contracts beyond additive fields, or the acceptance gate.

---

## 10. Document Intent (Optional Apex Prior)

**Verdict up front: include it.** Document Intent provides durable, compounding value and is the natural apex of the prior hierarchy this blueprint already establishes (regions in §9.2, profiles in §9.3). A human remediator settles "what kind of document is this?" in the first few seconds and lets that judgement colour every subsequent decision; RAWRS should do the same. Intent is what makes regions, front-page templates, heading models, and transformation selection *predictable* instead of rediscovered from scratch per document — and it makes onboarding a new document type a matter of adding data (an intent and its expectations), not code. It is optional and degrades to a no-op, so it costs nothing when it cannot decide. §10.4 gives the updated diagram.

**What it is.** A single, coarse, document-level classification produced *before* semantic interpretation — a distribution over intents with a confidence, not a hard label:

`Journal Article · Research Paper · Book · Book Chapter · Government Report · White Paper · Thesis · Manual · Magazine Article` (with **Generic/Unknown** as the safe default).

Intent sits one level above semantic regions: it predicts *which regions and layouts to expect*, then the region detector, interpreters, and transformations use that expectation as a prior. Because it is coarse and early, it is cheap; because it is a prior (never a switch), it is safe.

### 10.1 Inferring Intent from Repository Evidence

Intent is an **evidence-weighted classifier** over signals RAWRS already produces (or gains in this phase), fused through the existing `EvidenceBundle` model — the same transparent, calibratable mechanism used for artifact and heading confidence. No keyword table decides intent on its own; every signal contributes weighted evidence:

| Signal source (already in the repo / this phase) | Discriminating evidence |
|---|---|
| **Document length / page count** (`Page` count) | Books/Theses are long; Journal/Magazine articles short-to-medium; chapters medium |
| **Layout Intelligence** (§2.2 — columns, running headers, zones) | Multi-column → Journal/Magazine; recurring journal-name masthead → Journal Article; chapter-title running headers → Book Chapter |
| **Front-matter signals** (`frontmatter/`, metadata) | DOI + abstract + affiliations → Journal/Research Paper; ISBN + publisher → Book; degree/institution/committee → Thesis; agency + report number → Government Report; "Executive Summary" → White Paper/Report |
| **Terminal-region signals** (§9.2) | References/Bibliography → academic; Index + Glossary + Appendix → Book/Manual; numbered "Chapter N" → Book |
| **Typographic profile** (span model, §2.1) | House heading depth and numbering style; manuals show deep numbered hierarchies (1.2.3) |
| **PDF metadata / producer** | Weak prior only (title, producer string) |
| **Benchmark manifest** (`samples/benchmark/manifest.json`, `notes/`) | Ground-truth document types for training/validating the classifier on the corpus |

The classifier outputs an intent distribution; when the top intent's confidence is below threshold, intent is **Generic/Unknown** and contributes no priors — the system behaves exactly as §1–§9 describe. Intent may also be **revised** after region detection (e.g. discovering an Index upgrades confidence in *Book*): a cheap coarse pass early, optionally confirmed once regions are known. Like every other automatic decision, the inferred intent is a **reviewable, reversible** record — the remediator can correct it, which simply re-applies the priors.

### 10.2 How Intent Influences Downstream Stages

Intent conditions the same detectors and transformations already specified; it only shifts their priors and selects their expected templates.

- **Semantic region detection (§9.2).** Intent supplies the *expected region set and order*. Journal Article → {Front Matter(title/authors/affiliations/abstract/keywords), Body, References}, and explicitly *does not* expect Index/Glossary. Book → {ToC, Body(chapters), Appendix, Glossary, Index}. Thesis → {title page, committee, abstract, ToC, Body, References/Bibliography, Appendix}. These expectations raise/lower region-type priors, improving segmentation confidence and resolving terminal-list ambiguity (References vs Bibliography vs Index) that region signals alone find hard.
- **Heading interpretation (§2.3 / L3).** Intent sets the expected hierarchy model: Book/Thesis → chapter-rooted, deeply nested, numbered, numbering resettable per chapter; Journal Article → shallow, often-unnumbered section headings (Introduction/Methods/Results/Discussion); Manual → deep numbered hierarchies. This gives the redesigned detector a principled expectation for depth and numbering instead of inferring it per document.
- **Front-page reconstruction (§9.1 FrontPageReconstruction / L5).** Intent selects the *title-block template family*: Journal → title/authors/affiliations/email/abstract/journal/DOI; Book → title/subtitle/author/publisher/copyright/ISBN; Thesis → title/author/degree/institution/committee/date; Government Report → title/agency/report-number/date. This is intent's highest-leverage use — it picks *which* generalized front-matter layout to reconstruct toward.
- **Metadata extraction.** Intent predicts *which fields exist and where*: look for DOI/journal/volume in a Journal Article, ISBN/publisher in a Book, agency/report-number in a Government Report — and *don't* hunt for a DOI in a Manual. This raises precision by scoping the search.
- **Footnote / endnote behaviour (§2.3 / L4).** Intent biases the footnote-vs-endnote prior toward the family's convention (e.g. books commonly use per-chapter or end-of-document endnotes; journal articles favour footnotes or a terminal notes section), which the per-note evidence then confirms or overrides.
- **Transformation selection (§9.1).** Intent gates and prioritizes the Transformation Library: it selects the correct parameterization of running-header suppression (journal masthead vs chapter-title header), applies the intent-appropriate front-page template, and *skips inapplicable transformations entirely* (no Index handling for a journal article). Intent thus becomes a second axis, alongside semantic regions, on a transformation's `applies_to`.

### 10.3 Integration Without Document-Specific Hardcoding

Intent introduces no `if document == X` logic and no per-document branches. Three properties guarantee this:

1. **Intent is a learned classifier, not a lookup.** It is evidence-weighted over generic signals and validated against the benchmark manifest's ground-truth types — the same benchmark-as-specification discipline used everywhere in this phase. New document types are added by supplying training evidence and an expectations table, never code.
2. **Intent → expectations is data, not code.** The mapping from an intent to its expected regions, front-matter template, heading model, and note convention is a declarative table (parameters and expected layouts), reviewed like any other data. It biases the *same* evidence-based detectors and transformations; it cannot force an outcome.
3. **Intent is a prior gated by the existing machinery.** Every intent-influenced action is still a reversible, confidence-scored `CorrectionRecord`; a wrong intent can only shift priors, and the correction rail + confidence policy + human review still decide the outcome. With intent = Generic/Unknown, priors are empty and behaviour is identical to the pre-intent blueprint.

**Relationship to Profiles (§9.3) and Regions (§9.2).** These form a clean three-tier prior hierarchy, coarse to fine, all expressed through one evidence/confidence channel:

- **Document Intent** — the *coarse type* ("Journal Article"): predicts expected regions, templates, heading model, note convention.
- **Remediation Profile** — the *fine family* ("Publisher X's journal"): refines intent's generic priors into family-specific ones (exact masthead, exact title-block order, house heading styles). Intent also **narrows the profile search space** (only match journal profiles to journal-intent documents).
- **Semantic Regions** — the *within-document structure*: the concrete partition intent predicted and interpreters consume.

Intent supplies defaults when no profile matches; a profile, when matched, overrides intent's generic priors with family-specific ones. Neither overrides human review.

### 10.4 Updated Architecture Diagram

Document Intent enters as an optional apex prior between Layout Intelligence and Semantic Regions. This diagram extends (does not replace) §9.4; the core flow of §1 is unchanged.

```
INGEST ─► LAYOUT INTELLIGENCE ─► [DOCUMENT INTENT] ─► [SEMANTIC REGIONS] ─► SEMANTIC INTERPRETATION ─► REMEDIATION ─► VERIFY/SCORE ─► REVIEW ─► EXPORT
          (classify, §2.2)        (§10 optional         (§9.2 scoping        (region + intent               (§9.1 Transformation
                                   apex prior)           layer)               conditioned)                   Library runs here)
                                       │                                                                            ▲
        priors flow downward ─────────►│──────► regions · headings · front-page · metadata · notes · transform selection
                                       │
                     ┌─────────────────┴───────────────────────────────────────────────┐
                     │ PRIOR HIERARCHY (all via the shared EvidenceBundle/confidence)     │
                     │   Document Intent (coarse type)                                    │
                     │        └► narrows ► Remediation Profile (§9.3, fine family)         │
                     │                          └► both supply priors to Semantic Regions │
                     └───────────────────────────────────────────────────────────────────┘
```

**Dependency-graph placement:** a new node **L2.25 — Document Intent**, between Layout Intelligence and **L2.5 — Semantic Regions**. **Roadmap delta (one commit at a time, benchmark-gated):** (a) intent classifier with `EvidenceBundle` output, defaulting to Generic/Unknown and consumed by nothing (behaviour-neutral, additive model field); (b) declarative intent→expectations table + wire intent priors into region detection; (c) extend intent priors into heading model, front-page template selection, metadata scoping, note convention, and transformation `applies_to`, each gated on its element type in the Benchmark Differ; (d) let a matched Remediation Profile refine intent's priors. Intent accuracy itself becomes a measured metric against the benchmark manifest's ground-truth types.

**Invariants preserved.** Additive model field only; optional and no-op when undecided; every intent-influenced decision reversible, confidence-scored, and human-overridable; validated benchmark-first; no document-specific code. Document Intent makes the architecture **anticipatory** — it knows what kind of document it is remediating before it starts — without changing the core flow, the frozen model contracts beyond additive fields, or the acceptance gate.
