"""Rule Provenance. Section 27.

Six of the seven required fields already exist on AccessibilityRule/
RuleEvaluation - this module only assembles them into one read view, plus
reads the one new additive field (EvidenceSignal.source_module,
src/verification/evidence.py) proposed and approved in Section 27.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from src.accessibility.models import AccessibilityReport, ConfidenceTier, RuleAutomation
from src.accessibility.registry import AccessibilityRuleRegistry, registry as default_registry


@dataclass(frozen=True)
class RuleProvenance:
    rule_id: str
    wcag_mapping: List[str]
    pdf_ua_mapping: Optional[str]
    internal_only: bool
    evidence_source: List[str]
    confidence: Optional[float]
    confidence_tier: ConfidenceTier
    automation: RuleAutomation


def provenance_for(
    report: AccessibilityReport,
    rule_id: str,
    object_id: Optional[str] = None,
    rule_registry: AccessibilityRuleRegistry = default_registry,
) -> Optional[RuleProvenance]:
    """None if no matching rule/evaluation exists in this report."""
    rule = rule_registry.get(rule_id)
    if rule is None:
        return None
    evaluation = next(
        (ev for ev in report.evaluations if ev.rule_id == rule_id and ev.object_id == object_id),
        None,
    )
    if evaluation is None:
        return None
    return RuleProvenance(
        rule_id=rule.rule_id,
        wcag_mapping=rule.wcag_criteria,
        pdf_ua_mapping=rule.pdf_ua_clause,
        internal_only=rule.internal_only,
        evidence_source=[
            signal.source_module or signal.name for signal in evaluation.evidence.signals
        ],
        confidence=evaluation.confidence,
        confidence_tier=evaluation.confidence_tier,
        automation=rule.automation,
    )
