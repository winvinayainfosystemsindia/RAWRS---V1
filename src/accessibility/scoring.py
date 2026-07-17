"""Scoring arithmetic for the Accessibility Intelligence Engine.

Sections 7 (category scoring), 8 (overall score), 9 (export readiness),
18 (priority), 25 (predicted score - reuses compose_score() unchanged on a
hypothetically mutated evaluation list, per Section 25's own design
decision: no second scoring formula).
"""

from __future__ import annotations

import dataclasses
from typing import Iterable, List, Set

from src.accessibility.models import (
    AccessibilityReport,
    AccessibilityRule,
    CategoryScore,
    ConfidenceTier,
    RuleEvaluation,
    RuleOutcome,
    ScorePrediction,
)
from src.accessibility.registry import AccessibilityRuleRegistry


def _evaluation_label(evaluation: RuleEvaluation) -> str:
    if evaluation.object_id:
        return f"{evaluation.rule_id}:{evaluation.object_id}"
    return evaluation.rule_id


def compose_score(
    evaluations: Iterable[RuleEvaluation], registry: AccessibilityRuleRegistry
) -> AccessibilityReport:
    """Sections 7/8/9. The single place the score is computed - both
    evaluate_document() (a real run) and predict_score() (a hypothetical
    "what if") call this same function, so there is never a second scoring
    formula to keep in sync (Section 25's own stated rationale).
    """
    categories: dict[str, CategoryScore] = {}
    point_ledger: List[tuple[str, int]] = []
    manual_review_count = 0
    blocking_failures: List[str] = []

    for evaluation in evaluations:
        rule = registry.get(evaluation.rule_id)
        if rule is None:
            continue  # a rule was deprecated/removed between report and now

        category = categories.setdefault(rule.category, CategoryScore(category=rule.category))

        if evaluation.outcome == RuleOutcome.NOT_APPLICABLE:
            continue  # excluded from the denominator entirely (Section 7)

        category.max_points += rule.weight

        if evaluation.outcome == RuleOutcome.FAIL:
            category.points_lost += rule.weight
            point_ledger.append((_evaluation_label(evaluation), rule.weight))
            if rule.barrier_class.value == "barrier" and rule.required_for_export:
                blocking_failures.append(_evaluation_label(evaluation))
        elif evaluation.outcome == RuleOutcome.MANUAL_REVIEW_REQUIRED:
            category.manual_review_count += 1
            manual_review_count += 1
            if rule.required_for_export:
                blocking_failures.append(_evaluation_label(evaluation))
        # PASS: no points lost, no ledger entry - the absence *is* the pass.

    return AccessibilityReport(
        evaluations=list(evaluations),
        categories=sorted(categories.values(), key=lambda c: c.category),
        point_ledger=point_ledger,
        manual_review_count=manual_review_count,
        blocking_failures=blocking_failures,
    )


def predict_score(
    report: AccessibilityReport,
    resolved_rule_ids: Set[str],
    registry: AccessibilityRuleRegistry,
) -> ScorePrediction:
    """Section 25 - deterministic "what if". resolved_rule_ids are treated
    as PASS regardless of their current outcome (FAIL or
    MANUAL_REVIEW_REQUIRED); matching is against the evaluation label
    (Section 21's "TABLE_A11Y_001:table1" shape) so a caller can preview
    resolving one specific object instance, not just a whole rule_id.
    """
    hypothetical = [
        dataclasses.replace(ev, outcome=RuleOutcome.PASS)
        if _evaluation_label(ev) in resolved_rule_ids and ev.outcome != RuleOutcome.PASS
        else ev
        for ev in report.evaluations
    ]
    predicted = compose_score(hypothetical, registry)
    return ScorePrediction(
        current_score=report.overall_score,
        predicted_score=predicted.overall_score,
        points_recovered=report.points_lost - predicted.points_lost,
        resolved_rule_ids=sorted(resolved_rule_ids),
    )


def priority_key(evaluation: RuleEvaluation, rule: AccessibilityRule, affected_object_count: int) -> tuple:
    """Section 18 - a lexicographic sort key, not a blended score. Sort a
    list of failed/manual-review evaluations ascending by this key to get
    BARRIER before DEGRADATION before OBSERVATION, HIGH-confidence before
    LOW within the same class, most-affected-objects first, rule_id as a
    stable tiebreaker.
    """
    barrier_rank = {"barrier": 0, "degradation": 1, "observation": 2}[rule.barrier_class.value]
    confidence_rank = {ConfidenceTier.HIGH: 0, ConfidenceTier.MEDIUM: 1, ConfidenceTier.LOW: 2}[
        evaluation.confidence_tier
    ]
    return (barrier_rank, confidence_rank, -affected_object_count, evaluation.rule_id)
