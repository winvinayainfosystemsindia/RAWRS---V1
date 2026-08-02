"""Cross-source correction review gate — REVIEW_001.

A workflow-completion rule (not a WCAG success criterion): a document cannot
be Export Ready while any cross-source ``CorrectionRecord`` is still awaiting a
reviewer decision. This is the one business invariant the Accessibility
Intelligence Engine was missing — the engine's other rules verify accessibility
*properties* of the live document, but nothing gated on whether the reviewer
had actually resolved the proposed cross-source corrections.

Reads live ``document.corrections`` and contributes to ``blocking_failures``
through the ordinary ``scoring.compose_score`` pipeline (a
``required_for_export`` ``MANUAL_REVIEW_REQUIRED`` outcome), so no special-case
readiness logic is introduced anywhere.

Document-scoped: one evaluation aggregating across every correction (the
Corrections workspace lists the individual records), which keeps the score
impact to a single OBSERVATION-weight unit rather than flooding the point
ledger and blocking-failure list with one entry per proposed correction.
"""

from __future__ import annotations

from typing import List

from src.accessibility.models import (
    AccessibilityRule,
    BarrierClass,
    RuleAutomation,
    RuleEvaluation,
    RuleImpact,
    RuleOutcome,
)
from src.accessibility.registry import registry
from src.models.correction import NON_TERMINAL_STATUSES, CorrectionStatus
from src.models.document import Document


class CorrectionTerminalRule(AccessibilityRule):
    rule_id = "REVIEW_001"
    name = "Cross-source corrections resolved"
    category = "Review"
    # Internal workflow gate, not a WCAG/PDF-UA criterion (internal_only is
    # derived from these two being empty — see AccessibilityRule.internal_only).
    wcag_criteria = []
    pdf_ua_clause = None
    # OBSERVATION: an unresolved correction is a pending reviewer decision, not
    # itself an AT barrier, so it must not add to points_lost or depress the
    # accessibility score. required_for_export=True (kept from the base default)
    # is what makes the MANUAL_REVIEW_REQUIRED outcome gate export via the
    # existing compose_score() path — no special-casing needed.
    barrier_class = BarrierClass.OBSERVATION
    automation = RuleAutomation.MANUAL
    rationale = (
        "A cross-source correction the reviewer has not yet accepted, rejected, "
        "edited, or ignored leaves the document content in an undecided state; "
        "exporting before that decision ships content no human signed off on."
    )
    impact = RuleImpact(
        affected_users=[
            "All consumers of the exported document, who receive content whose "
            "accuracy the reviewer has not confirmed",
        ],
        user_consequence=(
            "The export may contain an un-reviewed provider value or an "
            "un-applied proposed correction — the reviewer's decision was skipped."
        ),
        severity_rationale=(
            "Not an accessibility barrier in itself (hence OBSERVATION), but a "
            "required workflow gate: export must wait for the human decision."
        ),
    )
    required_for_export = True

    # The only non-terminal statuses. Their union with the terminal set
    # {ACCEPTED, EDITED, REJECTED, IGNORED, AUTO_APPLIED} is the complete
    # CorrectionStatus enum — asserted in the tests, so any future status must
    # be classified explicitly rather than silently treated as terminal.
    # Defined once in src/models/correction.py: the verification engine needs
    # the identical partition to decide what belongs in the reviewer queue,
    # and two copies could drift into disagreeing about "resolved".
    _NON_TERMINAL = NON_TERMINAL_STATUSES

    def evaluate(self, document: Document) -> List[RuleEvaluation]:
        corrections = document.corrections
        if not corrections:
            # Nothing to gate — no evaluation, so this rule is excluded from the
            # score denominator entirely (Section 7's NOT_APPLICABLE-by-absence).
            return []

        unresolved = [c for c in corrections if c.status in self._NON_TERMINAL]
        if unresolved:
            return [
                RuleEvaluation(
                    rule_id=self.rule_id,
                    outcome=RuleOutcome.MANUAL_REVIEW_REQUIRED,
                    message=(
                        f"{len(unresolved)} of {len(corrections)} cross-source "
                        f"correction(s) awaiting a reviewer decision."
                    ),
                )
            ]
        return [
            RuleEvaluation(
                rule_id=self.rule_id,
                outcome=RuleOutcome.PASS,
                message=f"All {len(corrections)} cross-source correction(s) resolved.",
            )
        ]


registry.register(CorrectionTerminalRule())
