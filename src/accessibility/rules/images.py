"""Image rules - Section 20 "Images" table, IMAGE_A11Y_001/002.

Object-scoped: one RuleEvaluation per Image (not per document) - matches
Section 21's per-instance worked-example shape. Images with no Figure at
all (extraction failed - already covered by IMAGE_002 in validator.py) or
whose embedded_in_docx has never been set (pre-generation) produce no
evaluation for the relevant rule, rather than a fabricated PASS/FAIL.
"""

from __future__ import annotations

from pathlib import Path
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
from src.models.contracts import AltTextStatus, Document
from src.verification.evidence import EvidenceBundle, EvidenceSignal

# Mirrors src/api/routes.py's _IMG_COMPLETE set exactly (same file, the
# existing "human has acted on this image's alt text" definition) -
# AI_GENERATED means an AI ran but a human hasn't confirmed it yet, so it
# must NOT count as reviewed here any more than PENDING_REVIEW does.
_HUMAN_REVIEWED_STATUSES = {
    AltTextStatus.APPROVED,
    AltTextStatus.DECORATIVE,
    AltTextStatus.COMPLEX,
    AltTextStatus.REJECTED,
    AltTextStatus.SKIPPED,
    AltTextStatus.HUMAN_REVIEWED,
}

_IMAGES_IMPACT = RuleImpact(
    affected_users=[
        "Screen reader users",
        "Users with images disabled or on low bandwidth relying on the text alternative",
    ],
    user_consequence=(
        "Hears \"image\" with nothing else - or worse, hears the literal "
        "placeholder sentence read aloud as if it were real content."
    ),
    severity_rationale=(
        "Alt text not yet confirmed by a human, or the image missing from the "
        "export entirely, means the *only* representation a blind user gets of "
        "that image is absent or unconfirmed - Barrier."
    ),
)


def _evaluation(rule_id: str, image_id: str, outcome: RuleOutcome, signal_name: str, note: str, message: str) -> RuleEvaluation:
    bundle = EvidenceBundle()
    bundle.add(
        EvidenceSignal(name=signal_name, score=1.0 if outcome == RuleOutcome.PASS else 0.0, weight=1.0, note=note)
    )
    return RuleEvaluation(rule_id=rule_id, outcome=outcome, message=message, object_id=image_id, evidence=bundle)


class AltTextConfirmedRule(AccessibilityRule):
    rule_id = "IMAGE_A11Y_001"
    name = "Alt text confirmed by a human"
    category = "Images"
    wcag_criteria = ["1.1.1 Non-text Content (A)"]
    pdf_ua_clause = "ISO 14289-1 §7.3"
    barrier_class = BarrierClass.BARRIER
    automation = RuleAutomation.MANUAL
    rationale = (
        "A placeholder alt text ('description pending human review') is still "
        "unconditionally attached to every retained image; until a human "
        "confirms or replaces it, a screen reader may read the placeholder "
        "sentence verbatim as if it were a real description."
    )
    impact = _IMAGES_IMPACT

    def evaluate(self, document: Document) -> List[RuleEvaluation]:
        evaluations: List[RuleEvaluation] = []
        for image in document.images:
            if image.figure is None or image.figure.alt_text_status is None:
                continue
            status = image.figure.alt_text_status
            if status in _HUMAN_REVIEWED_STATUSES:
                outcome, note, message = (RuleOutcome.PASS, f"Alt text status: {status.value}.", "")
            else:
                # PENDING_REVIEW (untouched placeholder) or AI_GENERATED (an
                # AI ran but no human has confirmed it) - both require review.
                outcome, note, message = (
                    RuleOutcome.MANUAL_REVIEW_REQUIRED,
                    f"Alt text status '{status.value}' has not been confirmed by a human.",
                    f"Image '{image.image_id}' alt text has not been confirmed by a human (status: {status.value}).",
                )
            evaluations.append(_evaluation(self.rule_id, image.image_id, outcome, "alt_text_status", note, message))
        return evaluations


class ImageEmbeddedRule(AccessibilityRule):
    rule_id = "IMAGE_A11Y_002"
    name = "Image embedded in export"
    category = "Images"
    wcag_criteria = ["1.1.1 Non-text Content (A)"]
    pdf_ua_clause = "ISO 14289-1 §7.3"
    barrier_class = BarrierClass.BARRIER
    automation = RuleAutomation.AUTOMATIC
    rationale = (
        "An image whose file exists and extracted successfully can still fail "
        "to embed in the generated DOCX; when that happens, the image - and "
        "its alt text - is entirely absent from the reviewer's exported document."
    )
    impact = _IMAGES_IMPACT

    def evaluate(self, document: Document) -> List[RuleEvaluation]:
        evaluations: List[RuleEvaluation] = []
        for image in document.images:
            if image.embedded_in_docx is None:
                continue  # not yet generated
            if image.extraction_failed or not Path(image.file_path).is_file():
                continue  # covered by IMAGE_001/002 in validator.py, not double-counted here
            outcome = RuleOutcome.PASS if image.embedded_in_docx else RuleOutcome.FAIL
            note = "Embedded in DOCX." if image.embedded_in_docx else "add_picture() failed during DOCX generation."
            message = "" if outcome == RuleOutcome.PASS else f"Image '{image.image_id}' was not embedded in the generated DOCX."
            evaluations.append(_evaluation(self.rule_id, image.image_id, outcome, "embedded_in_docx", note, message))
        return evaluations


registry.register(AltTextConfirmedRule())
registry.register(ImageEmbeddedRule())
