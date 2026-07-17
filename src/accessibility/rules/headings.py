"""Heading rules - Section 20 "Headings" table, HEADING_STRUCT_001-004.

Each wraps an existing src/validation/validator.py check (HEADING_001,
HEADING_002, HEADING_003, HEADING_005) as a thin re-classification: same
condition, read straight off document.headings, no new detection logic.
Document-scoped (one evaluation per document, not per heading) - matches
Section 21's worked example, which shows these four as single PASS/FAIL
rows.
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
from src.models.contracts import Document, HeadingLevel
from src.verification.evidence import EvidenceBundle, EvidenceSignal

_HEADINGS_IMPACT = RuleImpact(
    affected_users=[
        "Screen reader / voice-control users navigating by heading landmarks",
        "Keyboard-only users using landmark-jump shortcuts",
    ],
    user_consequence=(
        "Cannot jump directly to a section; a missing or empty landmark forces "
        "linear reading of the entire document to find content a sighted user "
        "locates in seconds."
    ),
    severity_rationale=(
        "A missing or empty H1 removes the landmark entirely (Barrier); a "
        "hierarchy jump or duplicate H1 leaves navigation working but less "
        "confident (Degradation)."
    ),
)


def _content_headings(document: Document) -> List:
    return sorted(
        (h for h in document.headings if not h.is_page_marker),
        key=lambda h: h.document_order,
    )


def _evaluation(rule_id: str, satisfied: bool, signal_name: str, note: str, fail_message: str) -> RuleEvaluation:
    bundle = EvidenceBundle()
    bundle.add(EvidenceSignal(name=signal_name, score=1.0 if satisfied else 0.0, weight=1.0, note=note))
    return RuleEvaluation(
        rule_id=rule_id,
        outcome=RuleOutcome.PASS if satisfied else RuleOutcome.FAIL,
        message="Passed." if satisfied else fail_message,
        evidence=bundle,
    )


class HeadingHierarchyJumpRule(AccessibilityRule):
    rule_id = "HEADING_STRUCT_001"
    name = "Heading hierarchy has no level jumps"
    category = "Headings"
    wcag_criteria = ["1.3.1 Info and Relationships (A)"]
    pdf_ua_clause = None
    barrier_class = BarrierClass.DEGRADATION
    automation = RuleAutomation.AUTOMATIC
    rationale = (
        "WCAG 1.3.1 requires structural relationships to be programmatically "
        "determinable; skipping a heading level breaks the hierarchy a screen "
        "reader announces."
    )
    impact = _HEADINGS_IMPACT
    required_for_export = False

    def evaluate(self, document: Document) -> List[RuleEvaluation]:
        if not document.pages:
            return []
        headings = _content_headings(document)
        for previous, current in zip(headings, headings[1:]):
            if current.level.value - previous.level.value > 1:
                return [
                    _evaluation(
                        self.rule_id,
                        False,
                        "heading_hierarchy_jump",
                        f"H{previous.level.value} directly followed by H{current.level.value}.",
                        (
                            f"Heading hierarchy jump: H{previous.level.value} "
                            f"('{previous.text}') is directly followed by "
                            f"H{current.level.value} ('{current.text}')."
                        ),
                    )
                ]
        return [_evaluation(self.rule_id, True, "heading_hierarchy_jump", "No level jumps found.", "")]


class MissingH1Rule(AccessibilityRule):
    rule_id = "HEADING_STRUCT_002"
    name = "Document has an H1"
    category = "Headings"
    wcag_criteria = ["1.3.1 Info and Relationships (A)", "2.4.6 Headings and Labels (AA)"]
    pdf_ua_clause = None
    barrier_class = BarrierClass.BARRIER
    automation = RuleAutomation.AUTOMATIC
    rationale = (
        "WCAG 2.4.6 requires headings to describe content; with no H1 a screen "
        "reader user has no primary document landmark to orient with at all."
    )
    impact = _HEADINGS_IMPACT

    def evaluate(self, document: Document) -> List[RuleEvaluation]:
        if not document.pages:
            return []
        has_h1 = any(h.level == HeadingLevel.H1 for h in document.headings)
        return [
            _evaluation(
                self.rule_id,
                has_h1,
                "h1_present",
                "H1 heading found." if has_h1 else "No H1 heading in document.headings.",
                "No H1 heading was detected in the document.",
            )
        ]


class EmptyHeadingRule(AccessibilityRule):
    rule_id = "HEADING_STRUCT_003"
    name = "No empty headings"
    category = "Headings"
    wcag_criteria = ["1.3.1 Info and Relationships (A)"]
    pdf_ua_clause = None
    barrier_class = BarrierClass.BARRIER
    automation = RuleAutomation.AUTOMATIC
    rationale = (
        "An empty heading announces a landmark with nothing to say - a screen "
        "reader user lands on it and gets no information at all."
    )
    impact = _HEADINGS_IMPACT

    def evaluate(self, document: Document) -> List[RuleEvaluation]:
        if not document.pages:
            return []
        empty = [h for h in document.headings if not h.text.strip()]
        return [
            _evaluation(
                self.rule_id,
                not empty,
                "heading_text_present",
                "No empty headings." if not empty else f"{len(empty)} empty heading(s).",
                "An empty heading was detected.",
            )
        ]


class MultipleH1Rule(AccessibilityRule):
    rule_id = "HEADING_STRUCT_004"
    name = "At most one H1"
    category = "Headings"
    wcag_criteria = ["1.3.1 Info and Relationships (A)"]
    pdf_ua_clause = None
    barrier_class = BarrierClass.DEGRADATION
    automation = RuleAutomation.AUTOMATIC
    rationale = (
        "Screen readers announce H1 as the primary document landmark; "
        "duplicates confuse navigation even though the content is still reachable."
    )
    impact = _HEADINGS_IMPACT
    required_for_export = False

    def evaluate(self, document: Document) -> List[RuleEvaluation]:
        if not document.pages:
            return []
        h1_count = sum(1 for h in document.headings if not h.is_page_marker and h.level == HeadingLevel.H1)
        return [
            _evaluation(
                self.rule_id,
                h1_count <= 1,
                "h1_count",
                f"{h1_count} H1 heading(s) found.",
                f"{h1_count} H1 headings detected; a well-structured document should have exactly one.",
            )
        ]


registry.register(HeadingHierarchyJumpRule())
registry.register(MissingH1Rule())
registry.register(EmptyHeadingRule())
registry.register(MultipleH1Rule())
