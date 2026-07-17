"""Reading Order rule - Section 20 table, READING_ORDER_001 (wraps
existing PAGE_003, re-categorized per Section 19).

Reuses src/validation/validator.py's existing, private
_count_backward_jumps/_count_overlapping_pairs helpers rather than
duplicating the geometric heuristic - the same cross-module private-import
pattern validator.py itself already uses for src.ocr.router's
_unusable_char_ratio. Zero changes to validator.py's detection logic.

Document-scoped, single evaluation (aggregates across every page) - matches
Section 21's worked example.
"""

from __future__ import annotations

from typing import Dict, List

from src.accessibility.models import (
    AccessibilityRule,
    BarrierClass,
    RuleAutomation,
    RuleEvaluation,
    RuleImpact,
    RuleOutcome,
)
from src.accessibility.registry import registry
from src.models.contracts import Document, TextBlock
from src.validation.validator import _count_backward_jumps, _count_overlapping_pairs
from src.verification.evidence import EvidenceBundle, EvidenceSignal


class ReadingOrderAnomalyRule(AccessibilityRule):
    rule_id = "READING_ORDER_001"
    name = "No reading-order anomaly detected"
    category = "Reading Order"
    wcag_criteria = ["1.3.2 Meaningful Sequence (A)"]
    pdf_ua_clause = "ISO 14289-1 §7.1"
    barrier_class = BarrierClass.BARRIER
    automation = RuleAutomation.AUTOMATIC
    rationale = (
        "WCAG 1.3.2 requires content to be presented in a meaningful sequence; "
        "a scrambled reading order actively misinforms a screen reader user, "
        "who has no visual layout cue that anything is wrong."
    )
    impact = RuleImpact(
        affected_users=[
            "Screen reader users, who must trust the linear read order completely",
            "Switch/scanning-access users, for whom read order is the navigation sequence",
        ],
        user_consequence=(
            "Content is read in an incoherent sequence (e.g. interleaving two "
            "columns line-by-line) that garbles meaning with no visual signal "
            "that anything is wrong."
        ),
        severity_rationale="There is no partial-credit version of reading order; a scrambled sequence misinforms rather than merely inconveniencing.",
    )

    def evaluate(self, document: Document) -> List[RuleEvaluation]:
        if not document.pages:
            return []

        blocks_by_page: Dict[int, List[TextBlock]] = {}
        for block in document.blocks:
            blocks_by_page.setdefault(block.page_number, []).append(block)

        anomalous_pages: List[int] = []
        for page_number, blocks in blocks_by_page.items():
            ordered = sorted(blocks, key=lambda b: b.order)
            if len(ordered) < 2:
                continue
            if _count_backward_jumps(ordered) or _count_overlapping_pairs(ordered):
                anomalous_pages.append(page_number)

        bundle = EvidenceBundle()
        satisfied = not anomalous_pages
        bundle.add(
            EvidenceSignal(
                name="reading_order_anomaly",
                score=1.0 if satisfied else 0.0,
                weight=1.0,
                note="No anomalies." if satisfied else f"Anomaly on page(s): {sorted(anomalous_pages)}.",
            )
        )
        return [
            RuleEvaluation(
                rule_id=self.rule_id,
                outcome=RuleOutcome.PASS if satisfied else RuleOutcome.FAIL,
                message="" if satisfied else f"Reading order anomaly detected on page(s) {sorted(anomalous_pages)}.",
                evidence=bundle,
            )
        ]


registry.register(ReadingOrderAnomalyRule())
