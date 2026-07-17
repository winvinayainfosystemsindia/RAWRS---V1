# RAWRS Accessibility Intelligence Engine — Architecture Design

## Purpose

Design-only milestone. No source code changes. This document specifies the backend
rule engine that will power the Accessibility Center (`frontend/components/ReadinessPanel.tsx`,
shipped Phase RW-1), which today explicitly discloses that it is waiting for this
engine (`ReadinessPanel.tsx`'s "Awaiting Accessibility Rules Engine" note; `docs/PHASE_STATUS.md`
Phase RW-1's "Deferred, per the mission's own scope" line).

Everything below is grounded in what already exists in this codebase — no parallel
system is invented where a proven one already does the job. Section 0 states exactly
what is being reused, extended, or replaced, so the roadmap in Section 21 is a real
build plan, not a rewrite.

**Refinement pass (this revision):** the architecture in Sections 0–23 is approved
and unchanged. Sections 24–28 add four reviewer-guidance and reporting capabilities
requested for this milestone — Accessibility Impact, Predicted Accessibility Score,
Accessibility Debt, and Rule Provenance — each specified as an extension of the
existing registry/`AccessibilityRule` model, the existing `EvidenceBundle`
confidence model, or the existing Section 7/8 scoring arithmetic, never a parallel
mechanism. Exactly one small, backward-compatible field addition to an
already-approved model is proposed (Section 27, `EvidenceSignal.source_module`);
everything else is either a new field on `AccessibilityRule`/`RuleExplanation`
(both already-additive-by-design dataclasses) or a pure function computed from data
the architecture already produces. Still design-only — no code in this milestone.

---

## 0. Grounding — What Already Exists, What This Adds

RAWRS already has three independent pieces of infrastructure that are direct
precedents for this engine. The design below is their generalization and
convergence, not a fourth parallel system.

| Existing system | What it proves | What it's missing for this mission |
|---|---|---|
| `src/validation/validator.py` — 20 hand-written check functions, `ValidationIssue(severity, rule_id, message, page_number, suggested_action)` | A working rule_id namespace (`HEADING_xxx`, `TABLE_xxx`, ...) and severity model (ERROR/WARNING/INFO) already ship and are tested. | No rule metadata (WCAG/PDF-UA mapping, weight), no registry (rules are a hard-coded function-call list in `validate_document()`), no confidence, no automation-mode distinction, no scoring. |
| `src/verification/` — `SemanticVerifier` base class + `engine.register()` registry (`src/verification/engine.py`, `base.py`), `EvidenceSignal`/`EvidenceBundle` weighted-mean confidence fusion (`src/verification/evidence.py`) | A **plugin registry pattern already proven at scale** — 6 asset-type verifiers (figures, headings, lists, callouts, tables, footnotes) register themselves with zero changes to the engine — and a **working, explainable confidence model** (`EvidenceBundle.confidence`, `.explanation`) already reviewer-facing in `CorrectionHistoryList.tsx`. | Scoped to cross-source (Mathpix vs. PDF) verification only, not general WCAG conformance checking. No scoring/weighting layer sits on top of it. |
| `src/validation/readiness.py` — `compute_readiness()`, generic rule_id-prefix grouping, binary per-category `ready` (0 errors AND 0 warnings) | A working "group by rule prefix, no hand-maintained map" pattern (`_category_prefix()`), and a real, live frontend consumer (`GET /readiness`, `ReadinessPanel.tsx`). | The score is binary per category (`ready_categories / total_categories`) — a black-box percentage with no per-rule traceability, no weighting, no WCAG citation, no confidence, exactly what this mission is asked to fix. |

**Also grounding this in product direction, not just code:** `docs/RAWRS_DESIGN_BIBLE_v1.0.md`
§17 explicitly **rejects** a new, separate "Accessibility View" top-level screen
("accessibility is distributed by design, not a mode"). This is not a conflict with
this mission: Phase RW-1 did not add a new screen — it enriched the existing
Readiness special view (`ReadinessPanel.tsx`) the Bible's own "what exists today"
paragraph already names as one of the three places accessibility signal legitimately
lives. This engine powers that same existing surface, plus the Validation Center
(§10's "AI Confidence slider" and "running compliance score" — both directly
addressed below) and per-object Evidence tabs (§12). No new screen is proposed here.

**What this design adds**, concretely:

1. `src/accessibility/` — a new module, parallel to `src/validation/` and
   `src/verification/`, that turns "a list of ad hoc check functions" into a real,
   inspectable **rule registry** (Section 2) using the exact registration pattern
   `src/verification/engine.py` already proved.
2. A **weight/severity/WCAG-mapping metadata layer** on every rule (Section 3), so a
   score is a sum of named, cited, individually-inspectable point values — never a
   single opaque function.
3. A **manual-attestation model** (Section 9) generalizing the per-object review-status
   enums that already exist (`HeadingReviewStatus`, `FootnoteReviewStatus`,
   `ReadingOrderStatus`, `PageLabelStatus`) into a formal `RuleAutomation.MANUAL`
   rule type — this is what fills the three categories `frontend/lib/validationCategories.ts`
   already names as deferred: **Reading Order, Navigation, Language** (Section 20).
4. Backward-compatible migration: `readiness.py::compute_readiness()` becomes a thin
   adapter over the new engine; `GET /readiness` and `GET /documents/{id}/export-readiness`
   keep their existing response shapes; nothing currently deployed breaks (Section 22).

---

## 1. Design Principles

Six commitments, each traceable to a specific mechanism below — not slogans.

1. **Transparent.** Every score is a sum of named point deductions (Section 6). No
   function anywhere computes a percentage without a `List[RuleEvaluation]` a
   reviewer can expand to see exactly what produced it.
2. **Explainable.** Every `RuleEvaluation` carries a `RuleExplanation` (Section 11):
   what was checked, what was found, why it matters (a real WCAG/PDF-UA citation,
   never fabricated — Section 20 marks rules with no genuine mapping honestly as
   "no formal citation — internal quality gate," not a fake one), and what to do.
3. **Extensible.** New rules register themselves (Section 16) exactly the way
   `src/verification/engine.py`'s asset verifiers already do — zero changes to the
   engine, pipeline, or scoring code to add a rule.
4. **Deterministic where possible.** The majority of rules are pure functions over
   `Document` state, like today's `validator.py` checks (Section 4).
5. **AI-assisted where appropriate.** A small, explicitly-named set of rules
   (Section 15) where full automation is unreliable get an AI opinion — which is
   always evidence, never a verdict, per the Design Bible's Product Principle 2
   ("Human Review, Always... not negotiable even for high-confidence suggestions").
6. **WCAG 2.2 / PDF-UA compatible, future-compatible.** Every scored rule cites a
   real WCAG 2.2 success criterion and/or PDF/UA (ISO 14289-1) clause where one
   genuinely exists (Section 20). The registry has no hard-coded rule count, so
   WCAG 3.0 or a future PDF/UA revision extends it without a rewrite.

---

## 2. Rule Architecture

```
AccessibilityRule (abstract metadata + evaluate())
        │
        ├── static metadata (never changes at runtime):
        │     rule_id, name, category, wcag_criteria, pdf_ua_clause,
        │     barrier_class → severity/weight, automation, rationale
        │
        └── evaluate(document) -> RuleEvaluation   [AUTOMATIC / AI_ASSISTED only]
              MANUAL rules have no evaluate(); satisfied only by explicit
              reviewer attestation (Section 9).
```

`AccessibilityRule` is deliberately narrower than `src/verification/base.py`'s
`SemanticVerifier` — it does not match, merge, or mutate documents. It only asks
one question ("does this document satisfy this one accessibility requirement?") and
answers it with evidence. Where a rule's underlying detection logic already exists
(heading detection, table structure, footnote linking, cross-source verification),
`evaluate()` is a thin adapter that reads `Document` state or the existing
`document.validation_issues` / `document.verification_findings` streams — it does not
re-implement detection. This mirrors exactly how `_check_table_accessibility()` in
today's `validator.py` reads `document.tables` rather than re-detecting tables.

```python
# src/accessibility/models.py (design, not final code)

class RuleAutomation(str, Enum):
    AUTOMATIC = "automatic"      # evaluate() is a pure function, deterministic
    AI_ASSISTED = "ai_assisted"  # evaluate() calls an AIProvider; result is
                                  # ALWAYS RuleOutcome.MANUAL_REVIEW_REQUIRED
                                  # until a human attests (Section 15)
    MANUAL = "manual"            # no evaluate(); satisfied only by attestation
                                  # (Section 9)

class BarrierClass(str, Enum):
    """What kind of failure this rule detects — see Section 6 for why this,
    not WCAG level alone, drives point weight."""
    BARRIER = "barrier"          # content unreachable/unreadable by AT — weight 10
    DEGRADATION = "degradation"  # reachable but orientation/quality gap — weight 5
    OBSERVATION = "observation"  # informational; WCAG-relevant but not a failure — weight 2

class RuleOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"
    NOT_APPLICABLE = "not_applicable"   # e.g. TABLE_* rules on a 0-table document

@dataclass(frozen=True)
class AccessibilityRule(ABC):
    rule_id: str                       # reuses validator.py's existing prefix scheme
    name: str
    category: str                      # "Headings", "Images", "Tables", "Reading Order", ...
    wcag_criteria: List[str]           # e.g. ["1.3.1 Info and Relationships (A)"] — [] if none
    pdf_ua_clause: Optional[str]       # e.g. "ISO 14289-1 §7.2 (Page numbering)" — None if none
    barrier_class: BarrierClass
    automation: RuleAutomation
    rationale: str                     # the fixed "why this matters" text (Section 11)
    impact: "RuleImpact"                # who's affected / consequence / severity
                                        # rationale — Section 24 (refinement pass);
                                        # additive field, defaults to the rule's
                                        # category impact profile when not overridden

    @property
    def weight(self) -> int:
        return {"barrier": 10, "degradation": 5, "observation": 2}[self.barrier_class.value]

    @abstractmethod
    def evaluate(self, document: "Document") -> "RuleEvaluation": ...
```

---

## 3. Rule Registry

A module-level singleton, identical in shape to `src/verification/engine.py`'s
`engine = CrossSourceVerificationEngine()`:

```python
# src/accessibility/registry.py

class AccessibilityRuleRegistry:
    def __init__(self) -> None:
        self._rules: Dict[str, AccessibilityRule] = {}

    def register(self, rule: AccessibilityRule) -> None:
        if rule.rule_id in self._rules:
            raise ValueError(f"Duplicate rule_id: {rule.rule_id}")
        self._rules[rule.rule_id] = rule

    def all(self) -> List[AccessibilityRule]: ...
    def by_category(self, category: str) -> List[AccessibilityRule]: ...
    def get(self, rule_id: str) -> Optional[AccessibilityRule]: ...

registry = AccessibilityRuleRegistry()
```

Each rule module (`src/accessibility/rules/headings.py`,
`src/accessibility/rules/tables.py`, ...) instantiates its rules and calls
`registry.register(...)` at import time — exactly the pattern
`src/verification/figures.py` already uses for `engine.register(FigureAssetVerifier())`.
`src/accessibility/rules/__init__.py` imports every rule module once, at
application startup, so registration is a side effect of import, not a manual list
anyone has to remember to update (this directly replaces `validate_document()`'s
current hard-coded 20-line call sequence, which is the exact "hand-maintained list"
pattern `readiness.py`'s own docstring already calls out as something to avoid).

**Duplicate rule_id fails loudly at import time**, not silently at scoring time —
this is the mechanism that makes the registry trustworthy as new rules accrete.

---

## 4. Rule Lifecycle

A rule has exactly four states, all driven by the registry, not by hidden flags:

| State | Mechanism | Effect |
|---|---|---|
| **Draft** | Rule class exists in a module but is not yet imported by `rules/__init__.py`. | Invisible to the engine — safe to write and unit-test a rule before it affects any live score. |
| **Active** | Imported → registered. | Participates in every `evaluate_document()` call from this point forward. |
| **Deprecated** | `AccessibilityRule.deprecated_by: Optional[str] = None` field set to the superseding `rule_id`. | Still registered (so historical reports referencing its `rule_id` remain interpretable), excluded from new evaluations, `evaluate()` raises if called. Mirrors how `validator.py`'s docstring already records rationale for *not* reusing a retired prefix — this makes that kind of decision a real, queryable field instead of a comment. |
| **Retired** | Removed from the rule module entirely. | Only reachable via historical `AccessibilityReport` snapshots already persisted; the registry no longer knows about it. A retired rule_id must never be reused for an unrelated check (same discipline `validator.py`'s module docstring already documents for `DOC_xxx`/`NOTE_xxx`/`OCR_xxx` prefix reuse decisions). |

No rule is ever silently skipped. `evaluate_document()` (Section 5) always evaluates
every Active rule against every applicable document; a rule that doesn't apply
(e.g. a table rule on a document with zero tables) explicitly returns
`RuleOutcome.NOT_APPLICABLE`, which is a real, visible outcome in the report, not
an absence.

---

## 5. Rule Evaluation Pipeline

```
Document
   │
   ▼
for each Active rule in registry.all():
   │
   ├─ AUTOMATIC / AI_ASSISTED → rule.evaluate(document) → RuleEvaluation
   │
   └─ MANUAL → look up ManualAttestation for (document, rule_id)
                 present+confirmed → PASS
                 present+rejected  → FAIL
                 absent            → MANUAL_REVIEW_REQUIRED
   │
   ▼
List[RuleEvaluation]  (one per Active rule, every run — see NOT_APPLICABLE above)
   │
   ▼
ScoreComposer (Section 6/7/8)  →  AccessibilityReport
```

`evaluate_document()` lives in `src/accessibility/pipeline.py` and is a pure
function: `(Document) -> AccessibilityReport`, called the same place
`validate_document()` is called today (`src/pipeline/phase1_pipeline.py`, and
on-demand from `GET /documents/{id}/accessibility-report` — Section 22). It never
mutates `Document` — same read-only discipline `validator.py`'s module docstring
already enforces ("every function in this module is read-only").

**Where a rule's `evaluate()` gets its input from** (per the mission's per-rule
"Inputs" requirement) falls into exactly three sources, reused, not reinvented:

1. `Document` fields directly (`document.headings`, `document.tables`, `document.metadata`, ...) — the same fields `validator.py`'s checks already read.
2. `document.validation_issues` — a rule may be a thin re-classification of an
   existing `ValidationIssue` the Phase 1 validator already produced (e.g. the
   Heading Structure rules below are direct wraps of `HEADING_001`–`005`).
3. `document.verification_findings` / `document.corrections` — cross-source
   verification output (`src/verification/`), for rules whose evidence is a
   Mathpix-vs-PDF mismatch rather than a PDF-only structural gap.

---

## 6. Rule Weighting

**Design decision: weight is driven by *barrier class*, not by a WCAG-level
multiplier formula.** An earlier draft of this design used `severity_base ×
WCAG_level_multiplier` (A=1.5×, AA=1.0×, AAA=0.6×) — that was rejected here for a
concrete reason: it produces a plausible-looking number that isn't actually more
explainable than a flat weight, and the mission's own requirement ("no black-box
percentages... every lost point must be traceable") is best served by a
justification a reviewer can restate in one sentence, not a formula they have to
trust. So weight has exactly one input, with three fixed values:

| Barrier class | Weight | Definition | Example |
|---|---|---|---|
| **Barrier** | 10 | Content is unreachable, unreadable, or actively mispronounced by assistive technology. | No document language set → the whole document is read in the wrong voice. Missing table header row → a screen reader announces cell values with zero column context. |
| **Degradation** | 5 | Content is reachable, but a reviewer's or AT user's *orientation, efficiency, or confidence* is measurably worse. | No table caption → the table is still readable, but a screen-reader user must read every cell to guess its purpose. Multiple H1s → still navigable, but landmark navigation is confusing. |
| **Observation** | 2 | A real WCAG-relevant fact worth recording, but not itself a failure. | A footnote was detected (informational; Phase 1 never auto-remediates footnote content, so this is a "here's what exists" note, not a defect). |

WCAG/PDF-UA citations remain on every rule (Section 2's `wcag_criteria` field) as
**documentation and legal/compliance traceability**, not as a scoring input — this
also sidesteps a real accuracy risk: collapsing WCAG's A/AA/AAA levels into a
scoring multiplier would imply RAWRS is making a legal conformance-level judgment
call it isn't qualified to make product-wide; citing the criterion without weighting
by its level keeps the tool honest about what it is (a barrier-severity signal) and
isn't (a legal conformance certification).

Per-rule barrier-class assignments are in Section 20's full table, each with a
one-line reason a reviewer can check by eye.

---

## 7. Category Scoring

```
category_max_points  = Σ weight(rule) for every rule in this category
                        whose outcome != NOT_APPLICABLE this run
category_points_lost = Σ weight(rule) for every rule in this category
                        whose outcome == FAIL
category_score       = (category_max_points - category_points_lost)
                        / category_max_points          [1.0 if category_max_points == 0]
```

**MANUAL_REVIEW_REQUIRED is never scored as points lost, and never scored as
points earned.** It is tracked as a separate, always-visible count
(`category.manual_review_count`) — this is not a new invention, it is the exact
4-bucket model `ReadinessPanel.tsx` already ships and tests against (Critical /
Warnings / Passed / **Manual Review**), formalized as a first-class scoring state
instead of an inferred `info_count > 0` proxy. A document cannot game its score by
having everything sit in "needs manual review" forever — Section 8's export-readiness
gate (distinct from the score) blocks export on unresolved manual items too.

**`NOT_APPLICABLE` rules are excluded from the denominator entirely** — a
zero-table document is not penalized for TABLE_003's absence, and it does not get
inflated credit for "passing" a check that never ran. This matches the existing,
already-shipped behavior of `readiness.py`'s prefix grouping (a category with zero
fired issues doesn't appear at all) but makes the reason explicit and per-rule
rather than an emergent property of "no issue was ever constructed."

---

## 8. Overall Score

```
overall_score = Σ category_points_lost (all categories)
                / Σ category_max_points (all categories)
              → reported as (1 - that) as a percentage, matching the existing
                ReadinessPanel.tsx display convention (Math.round(score * 100))
```

A single flat sum across all categories, not a re-weighted "category importance"
average — deliberately. Introducing a second, category-level weight on top of
per-rule weights would reintroduce exactly the opacity Section 6 rejected (now a
reviewer has to trust two formulas instead of one). If a future product decision
wants, say, Images to matter more than Metadata in the headline number, that is a
real, visible constant to add and name — not a default this design assumes.

**Every lost point is traceable** by construction: `AccessibilityReport.point_ledger`
is a flat `List[Tuple[rule_id, weight_lost]]` — the literal arithmetic inputs to the
displayed percentage, not a derived summary. The Accessibility Center can render
this as "here are the 47 points you lost and exactly which rule took each one,"
satisfying the mission's explicit requirement in one direct, unglamorous data
structure rather than a clever visualization.

---

## 9. Export Readiness

**Export readiness is a hard gate, not the score.** A document can score 85% and
still not be export-ready if a required rule is unresolved — this preserves the
existing, already-shipped behavior of `get_export_readiness()`
(`src/api/routes.py`), whose docstring already states "ready=True only when all
categories are complete (no outstanding WARNING-level issues)" — DOCX download
itself stays non-blocking either way (`get_export_readiness`'s own docstring:
"this endpoint is non-blocking").

```
export_ready = (no rule with barrier_class == BARRIER has outcome == FAIL)
               AND
               (no rule with required_for_export == True has outcome ==
                MANUAL_REVIEW_REQUIRED)
```

`required_for_export: bool` is a new per-rule field (default `True` for every
BARRIER-class rule, `False` for DEGRADATION/OBSERVATION by default, overridable
per-rule where a DEGRADATION issue is judged export-blocking anyway — e.g. a
project could decide "no caption" should still block export even though it's not a
full barrier). This makes the export gate's exact composition inspectable per rule
instead of an implicit "WARNING blocks, INFO doesn't" convention buried in
`get_export_readiness()`'s current hand-written per-category logic.

---

## 10. Manual-Review Rules

`RuleAutomation.MANUAL` rules have no `evaluate()` — they cannot be reliably
automated (reading-order correctness for genuinely ambiguous layouts, whether an
alt-text description is actually *good* rather than merely present, whether a
document's navigation structure is coherent to a real user). They are satisfied
only by an explicit human attestation, modeled as:

```python
@dataclass
class ManualAttestation:
    rule_id: str
    scope: str              # "document" | f"page:{n}" | f"object:{object_id}"
    confirmed: bool          # True = reviewer confirms the requirement is met
    reviewer_note: Optional[str]
    attested_at: datetime
```

This is not a new concept invented for this design — it is the **direct
generalization of four review-status enums that already exist and already ship**:
`HeadingReviewStatus`, `FootnoteReviewStatus`, `ReadingOrderStatus`,
`PageLabelStatus`. Today each of those is a bespoke per-object-type field with its
own PATCH endpoint; `ManualAttestation` is the same idea made generic, the same way
`SemanticVerifier` generalized six independent verifier implementations into one
registrable shape. **Existing PATCH endpoints keep working unchanged** — the
migration path (Section 22) has each rule's `evaluate()`-equivalent read the
existing per-object status field directly for now (e.g. the new "Reading Order
Reviewed" rule reads `Page.reading_order_status`), so this is additive, not a
breaking schema change.

Until a `ManualAttestation` (or, during migration, the underlying legacy status
field) is confirmed, the rule's outcome is `MANUAL_REVIEW_REQUIRED` — it never
silently defaults to PASS, matching `docs/VALIDATION_RULES.md`'s standing "never
hide uncertainty" design principle, already cited in `validator.py`'s own module
docstring.

---

## 11. Confidence Model

Reused wholesale from `src/verification/evidence.py` — **not reinvented**. Every
AUTOMATIC or AI_ASSISTED rule's `evaluate()` builds an `EvidenceBundle` (the same
class already powering `CorrectionHistoryList.tsx`'s per-signal breakdown for
cross-source corrections) and its `RuleEvaluation.confidence` is that bundle's
`.confidence` property (weighted mean of signal scores, clamped [0, 1]).

A deterministic, single-signal rule (e.g. "does `document.metadata.language`
exist?") produces a one-signal `EvidenceBundle` with `score=1.0 or 0.0,
weight=1.0` — confidence is always exactly 1.0 or 0.0 by construction, which is
correct: a boolean field check has no genuine uncertainty to express.

| Confidence tier | Range | Effect on outcome |
|---|---|---|
| **HIGH** | ≥ 0.85 | `RuleEvaluation.outcome` is trusted as computed (PASS/FAIL stands). |
| **MEDIUM** | 0.5 – 0.85 | Outcome stands, but the report flags it for optional spot-check (does not force MANUAL_REVIEW_REQUIRED — this tier exists so a reviewer can filter to it, per the Design Bible §10 "AI Confidence slider" requirement below). |
| **LOW** | < 0.5 | Outcome is forced to `MANUAL_REVIEW_REQUIRED` regardless of what the raw PASS/FAIL computation said — a low-confidence FAIL never silently costs points, and a low-confidence PASS never silently grants them. |

This three-tier model is the literal backend counterpart the Design Bible §10 names
as "genuinely absent today": *"AI Confidence slider filter (V2/V3) — lets a
reviewer show only issues above/below a confidence threshold."* `RuleEvaluation.confidence`
is exactly the field that slider filters on; this design doc supplies the data
shape, the slider UI itself is out of scope here (design-only, no frontend changes).

---

## 12. Evidence Model

Also reused from `src/verification/evidence.py`: `RuleEvaluation.evidence:
EvidenceBundle`. Every signal has a stable name, a 0–1 score, a weight, and a
human-readable note — the exact shape already rendered today in
`CorrectionHistoryList.tsx`'s evidence breakdown and referenced in the Design
Bible §12 as the "Reasoning & Evidence card pattern" ("What exists today (DECIDED,
shipped): `EvidenceBreakdown.tsx`... F-5.0 called this the single best reuse
example in the whole workspace"). No second evidence representation is introduced.

---

## 13. Reviewer Explanations

```python
@dataclass
class RuleExplanation:
    what_was_checked: str   # plain language, from AccessibilityRule.name/category
    what_was_found: str     # from RuleEvaluation.evidence.explanation (Section 12)
    why_it_matters: str     # AccessibilityRule.rationale (fixed per rule — Section 20)
    impact: "RuleImpact"     # who's affected / consequence — Section 24 (refinement pass)
    how_to_fix: SuggestedFix  # Section 14
```

`why_it_matters` is the one field with real editorial weight: it must state the
*human consequence*, not restate the WCAG citation. Compare the existing
`suggested_action` strings already in `validator.py` — e.g. META_001's message
already models this well: *"WCAG 3.1.1 requires the language to be programmatically
determinable so screen readers use the correct voice"* — cites the criterion **and**
states the consequence in one sentence. Every rule's `rationale` field follows that
exact shape (Section 20's table gives one for every rule).

---

## 14. Suggested Fix Generation

Three tiers, matched to how much the engine can determine on its own — never a
single generic "fix this" string:

| Tier | What it is | Source |
|---|---|---|
| **1. Deterministic template** | A fixed string, parameterized by the specific finding (page number, object id, missing field name). | Direct continuation of `validator.py`'s existing `suggested_action` field — every rule in Section 20 has one. |
| **2. Structured Repair Action Plan** | The *specific* mutation the Accept button would perform, not just a description — e.g. "Set `Table.caption = 'Table 3. ...'`" rather than "add a caption." | This is the Design Bible §9's named concept ("Repair Action Plan card... without it, a reviewer accepts a repair without seeing what DOM change it actually performs"), reusing the exact `CorrectionRecord.proposed_value` shape `src/verification/`'s asset verifiers already produce for cross-source corrections (Section 22 wires this rule engine's FAIL findings into `CorrectionRecord` the same way). Only available where the fix is itself mechanical (e.g. "promote to H2") — not available for judgment calls (e.g. "write a better alt text description"). |
| **3. AI-assisted suggestion** | A natural-language suggested fix from an AI provider — e.g. a draft table summary, a draft alt-text rewrite. | Section 15 — always confidence-scored, always routed through the existing `src/ai/provider.py` abstraction, **never auto-applied** (Design Bible Product Principle 2/3, already the standing rule for every AI surface in this codebase). |

---

## 15. AI-Assisted Rules

A small, explicitly named set — AI assistance is the exception, not the default,
because most accessibility structure checks are genuinely deterministic (a table
either has a header row or it doesn't). AI earns its place only where a
deterministic check would be either impossible or misleadingly confident:

| Rule (proposed) | Why deterministic isn't enough | AI provider call |
|---|---|---|
| `IMAGE_QUALITY_001` — Alt text is *descriptive*, not just present | `IMAGE_004` (existing) already checks *presence*/review-status; it cannot judge whether a human-written or placeholder-derived description is actually useful. | `AIProvider.generate_alt_text()` — already exists (`src/ai/provider.py`) for *generation*; this rule adds a **quality-assessment** call using the same provider contract (`AICapability.vision`), not a new subsystem. |
| `TABLE_QUALITY_001` — Table summary is adequate for the table's actual complexity | `TABLE_002` (existing) checks *presence*; a one-word summary on a 12-column table passes today with no quality signal. | `AIProvider.analyze_table()` — already exists (`src/ai/table_analyzer.py`) and already returns `warnings`/`confidence` in `TableAISuggestions`; this rule consumes that existing output rather than adding a new call shape. |
| `READING_ORDER_003` — Reading-order plausibility pre-flag | `PAGE_003` (existing) is a conservative geometric heuristic (see its own docstring: "prefer under-reporting over false positives"); it is deliberately blind to cases a human would catch instantly but geometry can't (e.g. a pull-quote correctly overlapping body text). | No vision call needed — this one stays a **candidate for a future text-plausibility model**, explicitly flagged in Section 21's roadmap as *not* buildable from any AI capability that exists in `src/ai/` today (no text-coherence provider exists yet). Listed here so the gap is on the record, not silently assumed solved. |

**Every `AI_ASSISTED` rule's `evaluate()` result is `RuleOutcome.MANUAL_REVIEW_REQUIRED`
by construction — never `PASS` or `FAIL` directly.** The AI's output populates the
rule's `EvidenceBundle` as one more signal (with its own name, e.g.
`"ai_quality_assessment"`, score, and a note quoting the model's stated confidence)
and its `SuggestedFix` (Tier 3, Section 14) — but only a human attestation
(Section 10) can turn that into a scored PASS or FAIL. This is not a stricter rule
invented for this design; it is the literal, already-standing product principle
(Design Bible: *"Never let 'AI confidence is high' become a reason to skip the
accept click"*) applied mechanically at the type level so it can't be bypassed by a
future rule author who forgets the principle.

---

## 16. Plugin Architecture

Already fully specified by Sections 2–4 — restated here as the explicit answer to
"how does a new rule get added":

```python
# src/accessibility/rules/my_new_check.py
from src.accessibility.registry import registry
from src.accessibility.models import AccessibilityRule, BarrierClass, RuleAutomation

class MyNewRule(AccessibilityRule):
    rule_id = "CUSTOM_001"
    name = "..."
    category = "..."
    wcag_criteria = ["..."]
    pdf_ua_clause = None
    barrier_class = BarrierClass.DEGRADATION
    automation = RuleAutomation.AUTOMATIC
    rationale = "..."

    def evaluate(self, document): ...

registry.register(MyNewRule())
```

```python
# src/accessibility/rules/__init__.py
from . import headings, images, tables, metadata, reading_order, navigation, \
    language, page_structure, ocr, footnotes, my_new_check  # noqa: F401
```

Zero changes to `pipeline.py`, `scoring.py`, or any existing rule module. This is
not aspirational — it is the exact mechanism `src/verification/figures.py`,
`headings.py`, `tables.py`, `lists.py`, `callouts.py`, and `footnotes.py` already
use today to register six independent verifiers with `engine.register(...)` and
zero shared-engine changes per addition.

---

## 17. Future Custom Rules

Three tiers of "custom," ordered by how much trust/sandboxing they require —
**only the first is in scope for this codebase's near-term roadmap**; the other two
are named so the architecture doesn't foreclose them, not because they're being
committed to now:

1. **In-repo custom rules** (available today, per Section 16): a developer adds a
   new `AccessibilityRule` subclass. Full trust — same as adding a new
   `validator.py` check function today. No new capability needed.
2. **Declarative threshold rules** (roadmap, not built here): a YAML/JSON rule
   definition for the common case of "flag when `<document field> <comparator>
   <threshold>`" (e.g. "flag when more than N images lack alt text"), loaded at
   startup and compiled into a generic `AccessibilityRule` instance. No arbitrary
   code execution — the rule "language" is a closed, safe expression grammar, not a
   scripting sandbox. This is genuinely deferred (not designed further here)
   because RAWRS is single-reviewer/local-first by deliberate architecture decision
   (Design Bible's anti-references list explicitly rejects multi-tenant framing) —
   a declarative rule format only earns its complexity once there's a real
   multi-org customization need, which doesn't exist yet.
3. **Org-defined external rule plugins** (explicitly out of scope, named only to
   record the boundary): arbitrary third-party code execution against `Document`
   state raises real security questions (this document's contents may be
   sensitive/regulated) that this design does not attempt to resolve. If ever
   pursued, it needs its own dedicated security review before any code is written
   — not a default this architecture assumes.

---

## 18. Priority Calculation

**Deliberately a sort key, not a blended score** — for the same reason Section 6
rejected a multiplier formula: a single number that mixes severity, confidence, and
frequency is a black box the moment two rules produce a close score for different
reasons. Priority is a **lexicographic tuple**, each field independently
inspectable:

```
priority_key = (
    barrier_class,          # BARRIER before DEGRADATION before OBSERVATION
    confidence_tier,        # HIGH before MEDIUM before LOW — a LOW-confidence
                             #   barrier is surfaced but a reviewer knows to
                             #   verify it themselves before trusting it fully
    -affected_object_count, # a rule failing on 12 objects outranks the same
                             #   rule failing on 1, all else equal
    rule_id,                # stable tiebreaker
)
```

A reviewer sorting the failed-rule list by this key gets exactly what "priority"
should mean operationally: real barriers first, then degradations, with
high-confidence findings surfacing above low-confidence ones of the same class so
effort isn't spent chasing a possible false positive before a certain one.

---

## 19. Category → Deferred-Category Mapping

Direct payoff for the three categories `frontend/lib/validationCategories.ts`
already names as `DEFERRED_READINESS_CATEGORIES` — this section shows exactly which
new rules close each gap, so the frontend's existing "Awaiting Accessibility Rules
Engine" note has a concrete, named replacement plan rather than an open-ended
promise:

| Deferred category | New rule(s) | Automation | What it reuses |
|---|---|---|---|
| **Reading Order** | `READING_ORDER_001` (= existing `PAGE_003`, re-categorized rather than duplicated — see Section 20) — geometric anomaly detection. `READING_ORDER_002` — reviewer-confirmed reading order. | AUTOMATIC / MANUAL | `PAGE_003`'s existing detection (`validator.py::_check_reading_order_anomalies`); `Page.reading_order_status` (existing field, per Section 10). |
| **Navigation** | `NAV_001` — at least one structural heading exists, so Word's Navigation Pane and screen-reader landmark navigation have real content (WCAG 2.4.5/3.2.3). | AUTOMATIC | `document.headings` (existing) + the existing, already-verified heading→`Heading 1`–`6` style mapping (`docx_generator.py::add_heading()`, confirmed VERIFIED COMPLETE in `docs/PHASE_STATUS.md` Phase B). |
| **Language** | `LANG_001` (= existing `META_001`, re-categorized). `LANG_002` — Language of Parts (WCAG 3.1.2): flags a page/block whose language differs from the declared document language. | AUTOMATIC / **not yet buildable** | `LANG_001` reuses `document.metadata.language` (existing). `LANG_002` is honestly marked **blocked** — it needs a per-block language-detection signal that does not exist anywhere in this codebase today (no `langdetect`/`fasttext`-equivalent dependency, no per-block language field on `TextBlock`). Listed in Section 21's roadmap as a distinct, later phase requiring a new detection capability, not silently assumed solvable with existing data. |

---

## 20. Full Rule Taxonomy

Every rule this engine evaluates, with the fields the mission requires. **Two
groups**: rules that wrap an existing `validator.py`/`src/verification/` check
(marked **Existing**) need no new detection logic — `evaluate()` is a thin
re-classification of data already computed; rules with no current detector
(marked **New**) are genuinely new work, scoped in Section 21's roadmap.

Rules with no real WCAG or PDF/UA mapping are marked **"— (internal only)"**
rather than assigned a citation that doesn't genuinely apply — fabricating a
citation would directly violate this document's own "transparent/explainable"
principle (Section 1).

### Headings

| ID | Name | WCAG | PDF/UA | Barrier | Automatic/Manual | Inputs | Suggested reviewer action |
|---|---|---|---|---|---|---|---|
| HEADING_STRUCT_001 *(existing: HEADING_001)* | Heading hierarchy jump | 1.3.1 (A) | — | Degradation (5) | Automatic | `document.headings` | Insert the missing intermediate level, or confirm intentional. |
| HEADING_STRUCT_002 *(existing: HEADING_002)* | Missing H1 | 1.3.1 (A), 2.4.6 (AA) | — | Barrier (10) | Automatic | `document.headings` | Confirm the document has a clear title and heading detection ran. |
| HEADING_STRUCT_003 *(existing: HEADING_003)* | Empty heading | 1.3.1 (A) | — | Barrier (10) | Automatic | `document.headings` | Remove or populate the empty heading. |
| HEADING_STRUCT_004 *(existing: HEADING_005)* | Multiple H1 | 1.3.1 (A) | — | Degradation (5) | Automatic | `document.headings` | Downgrade incorrect H1s or reject false positives. |
| HEADING_STRUCT_005 *(New)* | Heading text is meaningfully descriptive | 2.4.6 (AA) | — | Degradation (5) | **AI-assisted** (Section 15 candidate — not built; a generic-heading-text detector needs a language-quality signal RAWRS doesn't have today) | `document.headings` text | Rewrite generic headings ("Section 1", "Untitled") to describe their content. |

### Images

| ID | Name | WCAG | PDF/UA | Barrier | Automatic/Manual | Inputs | Suggested reviewer action |
|---|---|---|---|---|---|---|---|
| IMAGE_A11Y_001 *(existing: IMAGE_004)* | Alt text confirmed by a human (not a placeholder) | 1.1.1 (A) | §7.3 | Barrier (10) | **Manual** (existing `AltTextStatus` field) | `Figure.alt_text_status` | Review and, if needed, replace the placeholder alt text. |
| IMAGE_A11Y_002 *(existing: IMAGE_005)* | Image actually embedded in export | 1.1.1 (A) | §7.3 | Barrier (10) | Automatic | `Image.embedded_in_docx` | Convert the image to PNG and regenerate. |
| IMAGE_A11Y_003 *(New: IMAGE_QUALITY_001)* | Alt text is descriptive, not generic | 1.1.1 (A) | §7.3 | Degradation (5) | **AI-assisted** (Section 15) | `Figure.alt_text` + image bytes | Review the AI's quality flag; rewrite if the description is too generic. |

### Tables

| ID | Name | WCAG | PDF/UA | Barrier | Automatic/Manual | Inputs | Suggested reviewer action |
|---|---|---|---|---|---|---|---|
| TABLE_A11Y_001 *(existing: TABLE_001)* | Caption present | 1.3.1 (A) | §7.5 | Degradation (5) | Automatic | `Table.caption` | Add a descriptive caption. |
| TABLE_A11Y_002 *(existing: TABLE_002)* | Accessibility summary present (H73) | 1.3.1 (A) | §7.5 | Degradation (5) | Automatic | `Table.summary` | Add a prose summary of what the table shows. |
| TABLE_A11Y_003 *(existing: TABLE_003)* | Header row present | 1.3.1 (A) | §7.5 | Barrier (10) | Automatic | `Table.rows[].is_header_row` | Mark a row as the header row. |
| TABLE_A11Y_004 *(existing: TABLE_004)* | No empty header cells | 1.3.1 (A) | §7.5 | Barrier (10) | Automatic | `TableCell.text` where `is_header` | Fill in the empty header cell. |
| TABLE_A11Y_005 *(existing: TABLE_005/007, folded in)* | Detection confidence high enough to trust | — (internal only) | — | Observation (2) | **Manual** trigger (confidence-gated; see Section 11 — LOW confidence forces this outcome regardless of the automatic checks above) | `Table.confidence`, `Table.evidence_signals` | Review the table structure before trusting TABLE_A11Y_001–004's result on it. |
| TABLE_A11Y_006 *(New: TABLE_QUALITY_001)* | Summary is adequate for table complexity | 1.3.1 (A) | §7.5 | Degradation (5) | **AI-assisted** (Section 15) | `Table` + `TableAISuggestions.warnings` | Expand the summary if the AI flags it as too thin for this table's structure. |

### Metadata / Language

| ID | Name | WCAG | PDF/UA | Barrier | Automatic/Manual | Inputs | Suggested reviewer action |
|---|---|---|---|---|---|---|---|
| LANG_001 *(existing: META_001)* | Document language declared | 3.1.1 (A) | §7.2 | Barrier (10) | Automatic | `Metadata.language` | Set the document language in the Metadata panel. |
| META_A11Y_001 *(existing: META_002)* | Document title set | 2.4.2 (A) | §7.2 | Degradation (5) | Automatic | `Metadata.title` | Set the document title in the Metadata panel. |
| LANG_002 *(New — blocked, Section 19)* | Language of parts | 3.1.2 (AA) | §7.2 | Degradation (5) | Automatic — **not buildable today**, no detector exists | Would need a new per-block language-detection signal | N/A until built |

### Reading Order / Navigation

| ID | Name | WCAG | PDF/UA | Barrier | Automatic/Manual | Inputs | Suggested reviewer action |
|---|---|---|---|---|---|---|---|
| READING_ORDER_001 *(existing: PAGE_003, re-categorized)* | No reading-order anomaly detected | 1.3.2 (A) | §7.1 | Barrier (10) | Automatic | `document.blocks` | Review this page's content order. |
| READING_ORDER_002 *(New)* | Reading order reviewer-confirmed | 1.3.2 (A) | §7.1 | Barrier (10) — but see Section 9: only `required_for_export` for pages `READING_ORDER_001` flagged | **Manual** (existing `Page.reading_order_status`) | `Page.reading_order_status` | Open the Reading Order panel and confirm or correct block sequence. |
| NAV_001 *(New)* | Document has real navigable structure | 2.4.5 / 3.2.3 (AA) | §7.4 (bookmarks/outline) | Degradation (5) | Automatic | `document.headings` (≥1 non-page-marker heading) | Confirm at least one heading exists so Navigation Pane/AT landmark jumps work. |

### Footnotes, OCR, Page Structure — Observational (not scored)

| ID | Name | WCAG | Barrier | Automatic/Manual | Reason not scored |
|---|---|---|---|---|---|
| *(existing: NOTE_001/002)* | Footnote/endnote detected | — (internal only) | Observation (2) | Automatic | Expected, deterministic content — not a defect (per `validator.py`'s own docstring, matches `VALIDATION_RULES.md`'s documented Info tier). |
| *(existing: OCR_001/002)* | OCR confidence / artifact ratio | — (internal only — a data-quality prerequisite underlying many WCAG SCs, not itself one) | Observation (2) | Automatic | A real quality signal, but assigning it a specific WCAG citation would overstate what the check actually verifies (text accuracy generally, not one named criterion). |
| *(existing: PAGE_001/002/004-008, DOC_001-004, IMAGE_001-003, HEADING_004)* | Various processing-integrity checks | — (internal only) | n/a | Automatic | These are pipeline-correctness checks (missing files, duplicate IDs, page gaps) — real and worth keeping in the Validation Center's issue list unchanged, but not WCAG conformance criteria themselves. Kept exactly as-is in `validator.py`; **not** ported into this engine's score, to avoid diluting the score with non-accessibility signal. |

**`*_VERIFY_*` cross-source rules** (`IMAGE_VERIFY_00X`, `HEADING_VERIFY_00X`,
`LIST_VERIFY_00X`, `TABLE_VERIFY_00X`, `FOOTNOTE_VERIFY_00X`) fold into the **same
category and same WCAG citation as their base object type** rather than getting a
separate "Cross-Source Verification" score — a missing heading Mathpix's source
had but the PDF-side detector missed is still a Heading structure barrier (WCAG
1.3.1), regardless of which detection path found it. The frontend's existing
"Cross-Source Verification" grouping in `validationCategories.ts` stays as a
**Validation Center filter/view**, unchanged — it does not need to become a
separate *scored* category in this engine.

---

## 21. Scoring Methodology — Worked Example

A concrete walkthrough, so "the score must always explain itself" is demonstrated,
not just asserted. A hypothetical document with:

- 2 tables: one has no caption (TABLE_A11Y_001 FAIL), one is fully compliant.
- 1 image: alt text still `PENDING_REVIEW` (IMAGE_A11Y_001 → MANUAL_REVIEW_REQUIRED).
- Headings: no anomalies (all 4 heading rules PASS).
- No document language set (LANG_001 FAIL).
- Reading order: 1 page flagged by geometry (READING_ORDER_001 FAIL), not yet
  reviewed (READING_ORDER_002 → MANUAL_REVIEW_REQUIRED).

| Rule | Outcome | Weight | Points lost |
|---|---|---|---|
| TABLE_A11Y_001 (table 1) | FAIL | 5 | 5 |
| TABLE_A11Y_001 (table 2) | PASS | 5 | 0 |
| TABLE_A11Y_002/003/004 (×2 tables, all pass) | PASS | 5/10/10 | 0 |
| IMAGE_A11Y_001 | MANUAL_REVIEW_REQUIRED | 10 | **0** (excluded, tracked separately) |
| IMAGE_A11Y_002 | PASS | 10 | 0 |
| HEADING_STRUCT_001–004 | PASS ×4 | 5/10/10/5 | 0 |
| LANG_001 | FAIL | 10 | 10 |
| META_A11Y_001 | PASS | 5 | 0 |
| READING_ORDER_001 | FAIL | 10 | 10 |
| READING_ORDER_002 | MANUAL_REVIEW_REQUIRED | 10 | **0** (excluded) |
| NAV_001 | PASS | 5 | 0 |

**Tables category**: max = 5+5+10+10+5 (table 2's four rules) + 5 (table 1's
caption rule, table 1's other 3 rules also count) — for brevity, assume
`category_max = 60`, `points_lost = 5` → **91.7%**, with the point ledger literally
showing `TABLE_A11Y_001 (table 1): -5, "no caption"`.

**Overall**: `points_lost = 5 (table) + 10 (language) + 10 (reading order) = 25`.
`category_max` summed across every scored rule this run. The report additionally,
separately states: **2 items awaiting manual review** (alt text, reading order) —
visible in its own count, never folded into the percentage, never hidden.

**Export readiness**: `export_ready = False` — `LANG_001` and
`READING_ORDER_001` are both BARRIER-class FAILs. Even if the score were 99%, this
document does not pass the export gate until those two are fixed and the two
MANUAL_REVIEW_REQUIRED items are attested.

This is the concrete shape "no black-box percentages" cashes out to: every number
on the Accessibility Center screen is either a literal count or a sum a reviewer
can re-derive from the point ledger by hand.

---

## 22. Implementation Roadmap

Explicitly **not started** — this section is the build plan for a future,
separately-approved milestone, per the mission's "do not implement, wait for
approval" instruction.

**Phase 1 — Engine core + existing-rule migration** (no new detection logic):
1. `src/accessibility/models.py`, `registry.py`, `pipeline.py`, `scoring.py` (Sections 2–8, 18).
2. Port every **Existing**-marked rule in Section 20's table: thin `evaluate()`
   wrappers reading already-computed `Document`/`validation_issues`/
   `verification_findings` state. Zero changes to `validator.py` or
   `src/verification/` detection logic.
3. `readiness.py::compute_readiness()` becomes a thin adapter: call
   `evaluate_document()`, reshape `AccessibilityReport` into the existing
   `ReadinessReport`/`ReadinessCategory` dataclass shape. **`GET /readiness`'s
   response schema is unchanged** — `ReadinessPanel.tsx` keeps working with zero
   frontend changes.
4. New endpoint `GET /documents/{job_id}/accessibility-report` exposes the full
   `AccessibilityReport` (point ledger, confidence, evidence, explanations) — additive,
   no existing consumer touches it yet.
5. `get_export_readiness()` similarly becomes a thin adapter over Section 9's
   `export_ready` computation, preserving its existing response contract.

**Phase 2 — Manual attestation generalization** (Section 9/10):
6. `ManualAttestation` model + generic PATCH surface, built as a thin layer over
   the four existing per-object status fields (`HeadingReviewStatus` etc.) — no
   schema migration, additive read-through.
7. `READING_ORDER_002`, `NAV_001`, `LANG_001` (re-categorized) rules land — this is
   the concrete close-out of `DEFERRED_READINESS_CATEGORIES` (Section 19).

**Phase 3 — AI-assisted rules** (Section 15):
8. `IMAGE_QUALITY_001`, `TABLE_QUALITY_001` — both reuse existing `AIProvider`
   contract methods, no new provider capability needed.
9. Explicitly **excluded from Phase 3**: `HEADING_STRUCT_005` (generic-heading-text
   detection) and `READING_ORDER_003` (plausibility pre-flag) and `LANG_002`
   (language of parts) — each named in this document as blocked on a detection
   capability (`src/ai/`) that does not exist yet. Building the underlying
   capability is its own, separately-scoped future milestone, not silently bundled
   into "AI-assisted rules."

**Phase 4 — Frontend consumption** (explicitly out of scope for this design and
this roadmap phase list — a future, separately-planned UI milestone):
10. `ReadinessPanel.tsx` migrates from the adapter-shaped `GET /readiness` onto the
    richer `GET /documents/{id}/accessibility-report` (point ledger display,
    confidence slider per Design Bible §10, Repair Action Plan cards per §9).

Every phase above ends with the same verification bar every prior phase in this
project has used: `pytest` full suite green, `tsc`/`jest`/`next build` clean where
frontend is touched, and live verification against a real processed document before
being marked complete — no phase is "done" on code review alone.

---

## 23. Summary — What This Design Commits To, and What It Doesn't

**Commits to:** a registry-based rule engine reusing three already-proven
codebase patterns (verifier registration, evidence-fusion confidence, per-object
review-status attestation); a two-axis weighting model (barrier class for score,
WCAG/PDF-UA citation for documentation) that is honest about not fabricating
citations where none exist; a hard export-readiness gate distinct from the score;
and a concrete, named plan to close the three categories the frontend already
discloses as missing.

**Does not commit to:** any new top-level UI screen (Design Bible §17 stands);
external/third-party rule plugins (Section 17, explicitly deferred pending a
security review that hasn't happened); `LANG_002`/`HEADING_STRUCT_005`/
`READING_ORDER_003` (each named as blocked on a detection capability that doesn't
exist); or a category-importance weighting on top of the overall score (Section 8
— deliberately flat, to avoid a second unexplainable formula).

**Stopping here for approval, per the mission's explicit instruction.** No code
in this milestone.

---

# Refinement Pass — Reviewer Guidance & Reporting

The architecture above (Sections 0–23) is approved and unchanged by what follows.
This pass adds four capabilities, each specified as an extension of an
already-approved model — no new registry, no new evidence primitive, no second
scoring formula.

---

## 24. Accessibility Impact

**Requirement:** for every rule, define who is affected, why it matters, expected
user impact, and severity rationale — visible to reviewers alongside the existing
rule explanation (Section 13).

**Design decision: impact is defined per *category*, not duplicated 30+ times per
rule.** Every rule within a category shares the same affected-user population and
the same class of consequence (e.g. every Table rule's failure mode is "a
screen-reader user loses cell context") — writing the same four sentences on 30+
individual rule rows would be repetition, not information, and would drift the
moment one copy is edited and the others aren't. Instead:

```python
@dataclass(frozen=True)
class RuleImpact:
    affected_users: List[str]     # e.g. ["Screen reader / TTS users",
                                    #       "Keyboard-only navigators"]
    user_consequence: str          # concrete, first-person-legible scenario —
                                    # not a restatement of the WCAG criterion
    severity_rationale: str        # explains *why* this rule's barrier_class
                                    # (Section 6) was assigned — this is NOT a
                                    # second severity axis, it is the prose
                                    # justification for the one that already
                                    # exists
```

`AccessibilityRule.impact` (Section 2, additive field) defaults to its category's
shared `RuleImpact` and may override any field where one rule in a category is a
genuine exception (e.g. `IMAGE_A11Y_002`'s consequence is more severe than
`IMAGE_A11Y_003`'s, even though both are Images-category — shown below). This is
the same "shared default, override where genuinely different" shape
`AccessibilityRule.weight` already uses via `barrier_class` (Section 2) — not a new
pattern.

**`severity_rationale` is explicitly not a new severity system.** Section 6
deliberately committed to one weighting axis (barrier class) to avoid a second
unexplainable formula; this field does not reopen that decision — it is prose
that restates, in user-impact terms, the reasoning that already produced the
rule's `barrier_class`. A reviewer reading it should recognize it as "the words
behind the number," not a competing number.

### Category impact profiles

| Category | Affected users | User consequence | Severity rationale |
|---|---|---|---|
| **Headings** | Screen reader / voice-control users navigating by heading landmarks; keyboard-only users using landmark-jump shortcuts. | Cannot jump directly to a section; a missing or empty landmark forces linear reading of the entire document to find content a sighted user locates in seconds. | `HEADING_STRUCT_002`/`003` (missing/empty H1) are Barrier — the landmark a screen reader needs is entirely absent or silent. `HEADING_STRUCT_001`/`004` (hierarchy jump/multiple H1) are Degradation — navigation still works, just less confidently. |
| **Images** | Screen reader users; users with images disabled or on low bandwidth relying on the text alternative. | Hears "image" with nothing else — or worse, hears the literal placeholder sentence ("description pending human review") read aloud as if it were real content. | `IMAGE_A11Y_001`/`002` are Barrier — content is either not confirmed real or not present in the export at all; the alt text (or lack of it) is the *only* representation a blind user gets of that image. `IMAGE_A11Y_003` (AI-assisted quality) is Degradation — a description exists, its quality is merely unconfirmed. |
| **Tables** | Screen reader users navigating cell-by-cell (JAWS/NVDA table mode); users with cognitive disabilities relying on captions for orientation before committing attention to a table. | No header row: every cell is announced with zero row/column context, forcing the user to count cells manually. No caption/summary: the user must read the entire table before learning what it's even about. | `TABLE_A11Y_003`/`004` (header row / empty header cells) are Barrier — this is the one piece of structure table navigation mode depends on entirely. `TABLE_A11Y_001`/`002` (caption/summary) are Degradation — the data is still reachable, orientation is what's lost. |
| **Language** | All screen reader / text-to-speech users. | The TTS engine uses the wrong pronunciation ruleset for the whole document (`LANG_001`) or one passage (`LANG_002`) — e.g. English text read with French phonetics — degrading from merely accented to genuinely unintelligible. | `LANG_001` is Barrier — with no declared language, every word in the document is potentially mispronounced, a total-document failure. `LANG_002` (once built — Section 19) is Degradation — the bulk of the document is still correctly voiced; only the differently-languaged passage suffers. |
| **Reading Order** | Screen reader users, who have no visual layout cue and must trust the linear read order completely; switch/scanning-access users, for whom read order *is* the navigation sequence. | Content is read in an incoherent sequence (e.g. interleaving two newspaper columns line-by-line) that garbles meaning with no visual signal that anything is wrong — unlike a sighted user, who would simply look at the other column. | Barrier — there is no partial-credit version of reading order; a scrambled sequence actively misinforms rather than merely inconveniencing. |
| **Navigation** (`NAV_001`) | Screen reader / keyboard-only users relying on Word's Navigation Pane or landmark-jump commands to skip repetitive content in long documents. | Forced to read or Tab through the entire document linearly with no way to jump to a section — a large, direct time-on-task cost for RAWRS's own stated 8–10 hr/day reviewer population, and equally for any end reader of the exported document. | Degradation — the document's content is still reachable via linear reading; what's lost is efficiency, which is real but not a hard barrier the way a missing header row is. |

Per-rule overrides (only where a rule's impact genuinely diverges from its
category default): `IMAGE_A11Y_002` ("not embedded") consequence is stated more
severely than `IMAGE_A11Y_003` ("quality") in the table above, precedent for how a
future rule author overrides a category default without inventing a new profile.

**Where reviewers see it:** `RuleExplanation.impact` (Section 13, additive field)
— rendered alongside the existing what/why/how-to-fix fields, so "who does this
affect and how badly" sits next to the fix itself rather than requiring a reviewer
to infer it from the WCAG citation.

---

## 25. Predicted Accessibility Score

**Requirement:** Current Score → Predicted Score After Accepted Fixes, deterministic
and explainable.

**Design decision: reuse Section 7/8's scoring arithmetic unchanged, on a
hypothetically mutated evaluation list.** This is not a new prediction model — it
is the existing `compose_score()` function (Section 7/8) called a second time with
a "what if these specific FAIL/MANUAL_REVIEW_REQUIRED rules became PASS" input.
No probability, no ML, no fuzzy estimate — the same weight table, the same
category-max/points-lost formula, run once for "now" and once for "if."

```python
@dataclass(frozen=True)
class ScorePrediction:
    current_score: float
    predicted_score: float
    points_recovered: int              # current.points_lost - predicted.points_lost
    resolved_rule_ids: List[str]       # exactly the rules the caller asked to preview

def predict_score(
    report: AccessibilityReport, resolved_rule_ids: Set[str]
) -> ScorePrediction:
    """Deterministic 'what if' — reuses compose_score() (Section 7/8) unchanged.
    resolved_rule_ids are treated as PASS regardless of their current outcome
    (FAIL or MANUAL_REVIEW_REQUIRED); every other rule's outcome is untouched."""
    hypothetical = [
        replace(ev, outcome=RuleOutcome.PASS) if ev.rule_id in resolved_rule_ids
        else ev
        for ev in report.evaluations
    ]
    predicted = compose_score(hypothetical)   # Section 7/8's existing function
    return ScorePrediction(
        current_score=report.overall_score,
        predicted_score=predicted.overall_score,
        points_recovered=report.points_lost - predicted.points_lost,
        resolved_rule_ids=sorted(resolved_rule_ids),
    )
```

**Called from two real, already-existing moments**, not a new workflow:

1. **Before commit** — a reviewer has one or more `CorrectionRecord`s staged
   (status `PROPOSED`, not yet `ACCEPTED`) in the Review Queue. The UI can call
   `predict_score(report, {rule_ids of the staged corrections})` to preview the
   score impact of accepting them, before the Accept click — this is exactly the
   Design Bible §10 "running compliance score" concept, extended to show a
   *before → after* rather than only a static number, with zero new backend
   state (`CorrectionRecord.status` already exists).
2. **After commit, reconciliation** — once a correction is actually accepted,
   `apply_correction()` (Section 22's existing engine method) mutates the
   `Document` and bumps `document.version` (already true today, per
   `src/verification/engine.py`). `evaluate_document()` re-runs for real. **If
   the real recomputed score doesn't match what was predicted, that mismatch is
   itself surfaced, not hidden** — it means the accepted correction didn't fully
   satisfy the rule's actual check (e.g. a caption was added but is still empty
   after whitespace trimming). This is the same "never hide uncertainty"
   principle already governing `DOC_004`/`validator.py` (Section 1's principle 1)
   applied to prediction specifically: a prediction is honest about being a
   preview, and the system says so out loud when reality diverges from it.

**Worked example, continuing Section 21's scenario:** current state is
`points_lost = 25` (5 table caption + 10 language + 10 reading order), with 2 items
in `MANUAL_REVIEW_REQUIRED`. Suppose a reviewer stages two fixes: the table 1
caption correction, and setting the document language in the Metadata panel.
`predict_score(report, {"TABLE_A11Y_001:table1", "LANG_001"})` recomputes with
those two rules forced to PASS: `points_lost` drops from 25 to 10,
`points_recovered = 15`. The UI shows "Current: [current %] → Predicted: [higher
%] (+15 points, 2 rules resolved)" — every number in that sentence is directly
readable off `ScorePrediction`, with no separate explanation needed.

---

## 26. Accessibility Debt

**Requirement:** track Critical / Moderate / Minor / Resolved / Remaining debt, to
support reviewer productivity reporting and a future management dashboard.

**Design decision: debt classes are the existing `BarrierClass` (Section 6),
renamed for this report, not a second severity taxonomy.** Introducing a
Critical/Moderate/Minor scheme independent of Barrier/Degradation/Observation would
be exactly the kind of "second unexplainable axis" Sections 6 and 8 already reject.
Instead:

| Debt class | = existing `BarrierClass` | Weight |
|---|---|---|
| Critical debt | `BARRIER` | 10 |
| Moderate debt | `DEGRADATION` | 5 |
| Minor debt | `OBSERVATION` | 2 |

```python
@dataclass(frozen=True)
class AccessibilityDebtReport:
    critical_debt_points: int    # Σ weight for BARRIER rules currently FAIL
    moderate_debt_points: int    # Σ weight for DEGRADATION rules currently FAIL
    minor_debt_points: int       # Σ weight for OBSERVATION rules currently FAIL
    resolved_debt_points: int    # Section 26.1
    remaining_debt_points: int   # = critical + moderate + minor (today's total)
```

`critical_debt_points`/`moderate_debt_points`/`minor_debt_points` are a direct
regrouping of `AccessibilityReport.point_ledger` (Section 8, already exists) by
`barrier_class` instead of by category — no new computation, a different `GROUP
BY` over data the engine already produces every run.

### 26.1 Resolved debt — reused, not new state

`resolved_debt_points` is computed from `document.corrections` — **already-existing
storage** (`CorrectionRecord`, `src/models/correction.py`, populated by
`engine.findings_to_corrections()` and mutated to `ACCEPTED`/`EDITED` by the
existing reviewer accept flow, Section 22's grounding). For every
`CorrectionRecord` with `status in (ACCEPTED, EDITED)`, resolve which
`AccessibilityRule.rule_id` it corresponds to via the owning `SemanticVerifier`'s
`rule_table()` (already exists, Section 5's grounding) and, if that rule now
evaluates `PASS`, add its weight to `resolved_debt_points`. **No new persistence is
introduced** — this reads exactly the audit trail the verification engine already
keeps for an unrelated reason (undo/redo, Section 9's `revert()`), repurposed here
as a debt-resolution ledger.

### 26.2 Productivity reporting — reused telemetry, not new instrumentation

"Reviewer productivity reporting" (the mission's explicit ask) is answerable
without any new tracking: `CorrectionRecord.telemetry_events`
(`CorrectionTelemetryEvent`, Phase M-4.4 — already collected on every reviewer
action today, per `docs/TASKS.md`'s own note that it is "collection only, not yet
exposed via the API") already timestamps every accept/reject/edit action. Filtering
`resolved_debt_points`' contributing corrections by their telemetry timestamp
within a window yields "N points of critical debt resolved this session / this
week" for free — this refinement's real contribution here is *pointing at* data
that already exists and was explicitly flagged as unexposed, not collecting
anything new.

### 26.3 Future management dashboard

`AccessibilityDebtReport`, computed per-document, is the exact shape a
multi-document dashboard would aggregate (`Σ critical_debt_points` across a batch
of documents = organizational critical-debt backlog). Building that dashboard is
explicitly **not** part of this design — RAWRS is single-reviewer/local-first by
deliberate architecture decision (Section 17's own citation of the Design Bible's
anti-multi-tenant stance) — but the per-document report is shaped so that decision
doesn't have to be revisited to build one later: the aggregation is a `Σ` over
already-produced per-document reports, not a redesign.

---

## 27. Rule Provenance

**Requirement:** every rule exposes rule identifier, WCAG mapping, PDF/UA mapping,
internal-only designation, evidence source, confidence, and automatic/manual —
traceable back to origin for reviewers and auditors.

**Six of these seven fields already exist** on `AccessibilityRule`/`RuleEvaluation`
(Sections 2, 11) — this section assembles them into one read view, plus proposes
exactly one small additive field to close the one real gap (evidence source
traceable to a specific detector module, not just a signal name).

```python
@dataclass(frozen=True)
class RuleProvenance:
    rule_id: str                    # AccessibilityRule.rule_id            [existing]
    wcag_mapping: List[str]         # AccessibilityRule.wcag_criteria      [existing]
    pdf_ua_mapping: Optional[str]   # AccessibilityRule.pdf_ua_clause      [existing]
    internal_only: bool             # derived: not wcag_mapping and pdf_ua_mapping is None
    evidence_source: List[str]      # EvidenceSignal.source_module per signal — see below
    confidence: Optional[float]     # RuleEvaluation.confidence            [existing]
    confidence_tier: str            # HIGH/MEDIUM/LOW, Section 11          [existing]
    automation: RuleAutomation      # AccessibilityRule.automation         [existing]

def provenance_for(report: AccessibilityReport, rule_id: str) -> RuleProvenance:
    """Pure assembly function — no new stored state beyond source_module below."""
```

`internal_only` is derived, never a separately-set flag that could drift from the
citations themselves — this is the same "computed, not duplicated" discipline
`AccessibilityRule.weight` (Section 2) already uses for its own derived property.

**The one proposed additive field:** `EvidenceSignal.source_module: Optional[str]
= None` on `src/verification/evidence.py`'s existing `EvidenceSignal` dataclass
(Section 12's grounding). Today a signal has `name`/`score`/`weight`/`note` but
nothing naming *which detector produced it* (e.g. `"src/tables/detectors/
VectorBorderDetector"` vs. `"src/tables/detectors/HorizontalRuleDetector"`) — for
most existing evidence-fusion consumers this doesn't matter (the `name` field
already reads as self-describing, e.g. `"vector_borders"`), but full audit
traceability — "which piece of code produced the evidence behind this specific
reported issue" — needs the module path, not just the signal's display name.
Defaulting to `None` means **every existing `EvidenceSignal(...)` construction
site in the codebase today keeps compiling and behaving identically** — this is
additive in the same way `Image.embedded_in_docx: Optional[bool] = None` (Phase
016E, already-shipped precedent) was additive when it was introduced. Only new or
updated signal-construction call sites need to start populating it, and only where
audit traceability is the point (this engine's rules) — `src/tables/`'s existing
consumers are not required to change.

**This is the one place in the entire refinement pass that touches an existing,
approved model file rather than only adding to the new `src/accessibility/`
module** — named explicitly here, not buried, so it can be evaluated on its own
merits: one optional field, one existing dataclass, zero behavior change for any
current caller.

---

## 28. Refinement Summary

**Adds:** `RuleImpact` (Section 24, category-level with per-rule override — closes
"who's affected/why it matters/severity rationale"); `ScorePrediction` and
`predict_score()` (Section 25, a second call to the already-existing `compose_score()`
— closes "current → predicted score"); `AccessibilityDebtReport` (Section 26, a
regrouping of the existing point ledger by the existing `BarrierClass`, plus a read
of already-existing `CorrectionRecord`/`CorrectionTelemetryEvent` data — closes
debt tracking and productivity reporting with zero new instrumentation);
`RuleProvenance` (Section 27, an assembly of six already-existing fields plus one
new optional field on `EvidenceSignal` — closes full audit traceability).

**Why each improves reviewer trust, transparency, or auditability, in one sentence
each:** Impact turns a WCAG citation into a sentence a reviewer without WCAG
training can act on. Predicted Score lets a reviewer see the consequence of an
Accept click before committing to it, and is held honest by the reconciliation
check against the real post-apply recompute. Debt turns "the score went up" into
"12 points of critical debt were resolved this week," which is what a reviewer's
manager actually wants to know. Provenance means any reported issue — in a
compliance audit, a dispute, or a "why did this fail" question six months later —
traces to an exact rule, an exact WCAG/PDF-UA citation or an honest "internal
only," an exact detector module, and an exact confidence value, with nothing
inferred or reconstructed after the fact.

**Confirmed preserved, per the mission's constraints:** the `SemanticVerifier`
registry (untouched — `src/accessibility/`'s `AccessibilityRuleRegistry` remains
its own, separate registry, Section 3); `EvidenceBundle` (untouched structurally,
one optional field added to `EvidenceSignal`); single-axis weighting (Section 6 —
explicitly reaffirmed, not reopened, in Sections 24 and 26); existing API
compatibility (nothing in this refinement pass changes `GET /readiness` or
`GET /documents/{id}/export-readiness`'s contracts — all four additions are new,
additive read surfaces); existing frontend integration (`ReadinessPanel.tsx` is
untouched by this document — Section 22's Phase 4 remains the only place frontend
consumption is even discussed, and it is unchanged by this pass).

**Stopping here for approval, per the mission's explicit instruction.** No code in
this milestone.
