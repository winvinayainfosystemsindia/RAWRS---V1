"""Core data model for the Accessibility Intelligence Engine.

See docs/ACCESSIBILITY_INTELLIGENCE_ENGINE_DESIGN.md Sections 2, 7, 8, 11, 13,
24, 25 for the full design. This module defines only the shapes; scoring
arithmetic lives in scoring.py, the rule registry in registry.py.

AccessibilityRule follows the exact pattern src/verification/base.py's
SemanticVerifier already established in this codebase: an ABC with
class-level metadata attributes (not a dataclass __init__), so a concrete
rule is written the same way FigureAssetVerifier/HeadingAssetVerifier
already are - see rules/*.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from src.models.document import Document
from src.verification.evidence import EvidenceBundle


class RuleAutomation(str, Enum):
    """How a rule's outcome is determined. See design doc Section 2."""

    AUTOMATIC = "automatic"      # evaluate() is a pure, deterministic function
    AI_ASSISTED = "ai_assisted"  # evaluate() calls an AIProvider; outcome is
                                  # ALWAYS MANUAL_REVIEW_REQUIRED (Section 15) -
                                  # not built in Phase 1, no rule uses this yet
    MANUAL = "manual"            # evaluate() reads an existing reviewer-set
                                  # status field directly (Section 10's
                                  # migration note - not yet backed by a
                                  # generic ManualAttestation store)


class BarrierClass(str, Enum):
    """What kind of failure a rule detects. Drives both scoring weight
    (Section 6) and, renamed, the debt-report classes (Section 26). Exactly
    one axis - see Section 6 for why a second WCAG-level multiplier was
    rejected."""

    BARRIER = "barrier"          # content unreachable/unreadable by AT
    DEGRADATION = "degradation"  # reachable, orientation/quality gap
    OBSERVATION = "observation"  # informational, not itself a failure


# Section 6's fixed weight table - the only place these numbers live.
_BARRIER_WEIGHTS = {
    BarrierClass.BARRIER: 10,
    BarrierClass.DEGRADATION: 5,
    BarrierClass.OBSERVATION: 2,
}


class RuleOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"
    NOT_APPLICABLE = "not_applicable"


class ConfidenceTier(str, Enum):
    """Section 11's three confidence bands."""

    HIGH = "high"      # >= 0.85
    MEDIUM = "medium"  # 0.5 - 0.85
    LOW = "low"        # < 0.5


def confidence_tier(confidence: float) -> ConfidenceTier:
    if confidence >= 0.85:
        return ConfidenceTier.HIGH
    if confidence >= 0.5:
        return ConfidenceTier.MEDIUM
    return ConfidenceTier.LOW


@dataclass(frozen=True)
class RuleImpact:
    """Section 24 (refinement pass). Defined once per rule *category* and
    shared by every rule in it; a rule overrides any field where it
    genuinely diverges from its category's default (see rules/*.py)."""

    affected_users: List[str]
    user_consequence: str
    severity_rationale: str


@dataclass
class RuleEvaluation:
    """One rule's result against one document, or one object within it.

    object_id is None for a document-scoped rule (e.g. LANG_001 - a
    document either has a declared language or it doesn't); set for an
    object-scoped rule with one evaluation per applicable instance (e.g.
    one TABLE_A11Y_001 evaluation per table - see Section 21's worked
    example, which shows exactly this shape: "TABLE_A11Y_001 (table 1)",
    "TABLE_A11Y_001 (table 2)" as separate rows, not one aggregated row).

    An object-scoped rule with zero applicable objects (e.g. TABLE_A11Y_001
    on a zero-table document) simply produces zero RuleEvaluations - this is
    the NOT_APPLICABLE semantics in practice (Section 7's denominator
    exclusion falls out naturally from "nothing to sum"). RuleOutcome.
    NOT_APPLICABLE remains available for a rule that needs to say so
    explicitly at the document level.
    """

    rule_id: str
    outcome: RuleOutcome
    message: str
    object_id: Optional[str] = None
    page_number: Optional[int] = None
    evidence: EvidenceBundle = field(default_factory=EvidenceBundle)

    @property
    def confidence(self) -> float:
        return self.evidence.confidence

    @property
    def confidence_tier(self) -> ConfidenceTier:
        return confidence_tier(self.confidence)


@dataclass
class RuleExplanation:
    """Section 13. what/why/how a reviewer sees alongside a finding.

    how_to_fix is a Tier 1 deterministic template string (Section 14) -
    the richer structured Repair Action Plan (Tier 2) and AI-assisted
    suggestion (Tier 3) are Phase 2/3 additions per the roadmap, not built
    here.
    """

    what_was_checked: str
    what_was_found: str
    why_it_matters: str
    impact: RuleImpact
    how_to_fix: str


class AccessibilityRule(ABC):
    """Base class for one accessibility requirement. See
    src/verification/base.py's SemanticVerifier for the precedent this
    mirrors: class-level metadata, one behavioral method, registered via
    registry.register(SomeRule()) at import time (Section 3/16).
    """

    rule_id: str
    name: str
    category: str
    wcag_criteria: List[str]
    pdf_ua_clause: Optional[str]
    barrier_class: BarrierClass
    automation: RuleAutomation
    rationale: str
    impact: RuleImpact
    required_for_export: bool = True  # Section 9; BARRIER-class default

    @property
    def weight(self) -> int:
        return _BARRIER_WEIGHTS[self.barrier_class]

    @property
    def internal_only(self) -> bool:
        """Section 27 - derived, never a separately-set flag that could
        drift from the citations themselves."""
        return not self.wcag_criteria and self.pdf_ua_clause is None

    @abstractmethod
    def evaluate(self, document: Document) -> List[RuleEvaluation]:
        """Pure function of document state - never mutates it (same
        read-only discipline as src/validation/validator.py)."""
        ...


@dataclass
class CategoryScore:
    """Section 7."""

    category: str
    max_points: int = 0
    points_lost: int = 0
    manual_review_count: int = 0

    @property
    def score(self) -> float:
        if self.max_points == 0:
            return 1.0
        return (self.max_points - self.points_lost) / self.max_points


@dataclass
class AccessibilityReport:
    """Section 8. Every number here is directly re-derivable from
    point_ledger by hand - that is the "no black-box percentages"
    requirement, satisfied structurally rather than by a promise."""

    evaluations: List[RuleEvaluation]
    categories: List[CategoryScore]
    point_ledger: List[Tuple[str, int]]  # (evaluation label, points lost)
    manual_review_count: int
    blocking_failures: List[str]  # rule_id[:object_id] of unresolved,
                                    # required_for_export BARRIER FAILs

    @property
    def points_lost(self) -> int:
        return sum(points for _, points in self.point_ledger)

    @property
    def max_points(self) -> int:
        return sum(c.max_points for c in self.categories)

    @property
    def overall_score(self) -> float:
        if self.max_points == 0:
            return 1.0
        return (self.max_points - self.points_lost) / self.max_points

    @property
    def export_ready(self) -> bool:
        """Section 9 - a hard gate, distinct from overall_score."""
        return len(self.blocking_failures) == 0


@dataclass(frozen=True)
class ScorePrediction:
    """Section 25."""

    current_score: float
    predicted_score: float
    points_recovered: int
    resolved_rule_ids: List[str]
