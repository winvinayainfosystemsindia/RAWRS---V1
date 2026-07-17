"""Rule Evaluation Pipeline. Section 5.

evaluate_document() is a pure function: (Document) -> AccessibilityReport.
Never mutates document - same read-only discipline as
src/validation/validator.py::validate_document().

Phase 1 simplification, disclosed: Section 5's pseudocode branches
AUTOMATIC/AI_ASSISTED (call evaluate()) vs MANUAL (look up a
ManualAttestation). Section 10's migration note says a MANUAL rule's
evaluate()-equivalent reads its existing legacy status field directly until
the generic ManualAttestation store exists (Section 22 Phase 2). Rather than
special-case MANUAL at the pipeline level for a store that doesn't exist
yet, every rule - AUTOMATIC or MANUAL alike - implements evaluate() today;
Phase 2 only changes what a MANUAL rule's evaluate() body reads from
(legacy field -> ManualAttestation), not this loop.
"""

from __future__ import annotations

from src.accessibility.models import AccessibilityReport, RuleEvaluation
from src.accessibility.registry import AccessibilityRuleRegistry, registry as default_registry
from src.accessibility.scoring import compose_score
from src.models.document import Document


def evaluate_document(
    document: Document, rule_registry: AccessibilityRuleRegistry = default_registry
) -> AccessibilityReport:
    evaluations: list[RuleEvaluation] = []
    for rule in rule_registry.all():
        evaluations.extend(rule.evaluate(document))
    return compose_score(evaluations, rule_registry)
