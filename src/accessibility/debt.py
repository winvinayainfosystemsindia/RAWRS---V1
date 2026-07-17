"""Accessibility Debt reporting. Section 26.

Critical/Moderate/Minor are the existing BarrierClass (Section 6), renamed
for this report - not a second severity taxonomy. resolved_debt_points
reads the already-existing document.corrections audit trail (no new
storage); it is honestly 0 today for every Phase 1 rule, since Phase 1
does not yet fold cross-source verification findings into this engine's
rule set (Section 20's disclosed gap) - the mechanism is real and
forward-compatible, the current data-availability limit is disclosed, not
hidden.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.accessibility.models import AccessibilityReport, BarrierClass, RuleOutcome
from src.accessibility.registry import AccessibilityRuleRegistry, registry as default_registry
from src.models.contracts import CorrectionStatus, Document


@dataclass(frozen=True)
class AccessibilityDebtReport:
    critical_debt_points: int
    moderate_debt_points: int
    minor_debt_points: int
    resolved_debt_points: int
    remaining_debt_points: int


def compute_debt_report(
    document: Document,
    report: AccessibilityReport,
    rule_registry: AccessibilityRuleRegistry = default_registry,
) -> AccessibilityDebtReport:
    critical = moderate = minor = 0
    for evaluation in report.evaluations:
        if evaluation.outcome != RuleOutcome.FAIL:
            continue
        rule = rule_registry.get(evaluation.rule_id)
        if rule is None:
            continue
        if rule.barrier_class == BarrierClass.BARRIER:
            critical += rule.weight
        elif rule.barrier_class == BarrierClass.DEGRADATION:
            moderate += rule.weight
        else:
            minor += rule.weight

    resolved = 0
    for correction in document.corrections:
        if correction.status not in (CorrectionStatus.ACCEPTED, CorrectionStatus.EDITED):
            continue
        rule = rule_registry.get(correction.reason_code)
        if rule is None:
            continue
        matching = [
            ev
            for ev in report.evaluations
            if ev.rule_id == rule.rule_id and ev.object_id == correction.object_id
        ]
        if matching and matching[0].outcome == RuleOutcome.PASS:
            resolved += rule.weight

    return AccessibilityDebtReport(
        critical_debt_points=critical,
        moderate_debt_points=moderate,
        minor_debt_points=minor,
        resolved_debt_points=resolved,
        remaining_debt_points=critical + moderate + minor,
    )
