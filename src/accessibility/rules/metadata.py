"""Metadata/Language rules - Section 20 table, LANG_001/META_A11Y_001.

Wrap existing src/validation/validator.py checks (META_001, META_002).
Document-scoped, single evaluation each.
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
from src.models.contracts import Document
from src.verification.evidence import EvidenceBundle, EvidenceSignal


def _evaluation(rule_id: str, satisfied: bool, signal_name: str, note: str, fail_message: str) -> RuleEvaluation:
    bundle = EvidenceBundle()
    bundle.add(EvidenceSignal(name=signal_name, score=1.0 if satisfied else 0.0, weight=1.0, note=note))
    return RuleEvaluation(
        rule_id=rule_id,
        outcome=RuleOutcome.PASS if satisfied else RuleOutcome.FAIL,
        message="" if satisfied else fail_message,
        evidence=bundle,
    )


class DocumentLanguageDeclaredRule(AccessibilityRule):
    rule_id = "LANG_001"
    name = "Document language declared"
    category = "Language"
    wcag_criteria = ["3.1.1 Language of Page (A)"]
    pdf_ua_clause = "ISO 14289-1 §7.2"
    barrier_class = BarrierClass.BARRIER
    automation = RuleAutomation.AUTOMATIC
    rationale = (
        "WCAG 3.1.1 requires the language to be programmatically determinable "
        "so screen readers use the correct voice - with no language set, every "
        "word in the document is potentially mispronounced."
    )
    impact = RuleImpact(
        affected_users=["All screen reader / text-to-speech users"],
        user_consequence=(
            "The TTS engine uses the wrong pronunciation ruleset for the whole "
            "document (e.g. English text read with French phonetics)."
        ),
        severity_rationale="With no declared language, this is a total-document failure, not a partial one.",
    )

    def evaluate(self, document: Document) -> List[RuleEvaluation]:
        has_language = bool(document.metadata.language)
        return [
            _evaluation(
                self.rule_id,
                has_language,
                "language_declared",
                document.metadata.language or "not set",
                "No document language set.",
            )
        ]


class DocumentTitleSetRule(AccessibilityRule):
    rule_id = "META_A11Y_001"
    name = "Document title set"
    category = "Metadata"
    wcag_criteria = ["2.4.2 Page Titled (A)"]
    pdf_ua_clause = "ISO 14289-1 §7.2"
    barrier_class = BarrierClass.DEGRADATION
    automation = RuleAutomation.AUTOMATIC
    rationale = (
        "WCAG 2.4.2 requires documents to have a descriptive title so screen "
        "readers can identify the document when it's opened."
    )
    impact = RuleImpact(
        affected_users=["Screen reader users opening the document"],
        user_consequence="Hears a generic/blank title instead of the document's actual subject when it opens.",
        severity_rationale="The document's content remains reachable; only initial orientation is degraded.",
    )
    required_for_export = False

    def evaluate(self, document: Document) -> List[RuleEvaluation]:
        has_title = bool(document.metadata.title)
        return [
            _evaluation(
                self.rule_id,
                has_title,
                "title_set",
                document.metadata.title or "not set",
                "No document title set.",
            )
        ]


registry.register(DocumentLanguageDeclaredRule())
registry.register(DocumentTitleSetRule())
