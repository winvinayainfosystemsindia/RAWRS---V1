"""Cross-source verification engine — asset-agnostic registry and dispatch.

This module contains no knowledge of figures, images, headings, or any other
domain object. It only knows how to: (1) hold a registry of AssetVerifiers
keyed by asset_type, (2) dispatch match/classify calls to whichever verifier
owns a given asset_type, and (3) translate the resulting generic Findings
into the two surfaces the rest of RAWRS already understands —
CorrectionRecord (stateful audit trail) and ValidationIssue (transient,
recomputed every validate_document() run).

Adding a new asset type (headings, footnotes, tables, ...) means writing one
AssetVerifier and calling `engine.register(...)` — nothing in this file
changes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from src.models.correction import CorrectionRecord, CorrectionStatus
from src.models.validation_issue import Severity, ValidationIssue
from src.models.verification import BenchmarkOutcome, Finding, RepairSuggestion
from src.verification.base import SemanticVerifier
from src.verification.matching import MatchResult
from src.verification.merge import MergeAction, MergeDecision


class UnknownAssetTypeError(Exception):
    """Raised when a caller asks the engine to dispatch to an asset_type
    that no AssetVerifier has registered for."""


class CrossSourceVerificationEngine:
    def __init__(self) -> None:
        self._verifiers: Dict[str, SemanticVerifier] = {}

    def register(self, verifier: SemanticVerifier) -> None:
        self._verifiers[verifier.asset_type] = verifier
        logger.debug("Verification engine: registered asset type '{}'", verifier.asset_type)

    def _require(self, asset_type: str) -> SemanticVerifier:
        verifier = self._verifiers.get(asset_type)
        if verifier is None:
            raise UnknownAssetTypeError(
                f"No AssetVerifier registered for asset_type '{asset_type}'. "
                f"Registered: {sorted(self._verifiers)}"
            )
        return verifier

    def run_import(
        self, asset_type: str, a_items: List[Any], b_items: List[Any], **context: Any
    ) -> Tuple[List[Any], List[Finding]]:
        """Match provider-source items against package assets at import
        time, returning (canonical_objects, findings)."""
        verifier = self._require(asset_type)
        matcher = verifier.build_import_matcher()
        result: MatchResult = matcher.match(a_items, b_items)
        context.setdefault("phase", "import")
        canonical = verifier.to_canonical(result, **context)
        findings = verifier.classify(result, **context)
        return canonical, findings

    def run_pdf_verification(
        self, asset_type: str, canonical_items: List[Any], pdf_items: List[Any], **context: Any
    ) -> List[Finding]:
        """Match canonical (already-imported) objects against independently
        PDF-extracted candidates. The engine itself never mutates
        canonical_items; an asset verifier's classify() may annotate its
        own domain-specific provenance/verification fields on its own
        canonical objects as part of producing findings (e.g. FigureAssetVerifier
        setting Image.verification_status) — that is the one place PDF
        verification is allowed to touch canonical state, and it never
        touches content fields like file_path or figure.caption."""
        verifier = self._require(asset_type)
        matcher = verifier.build_pdf_matcher()
        result: MatchResult = matcher.match(canonical_items, pdf_items)
        context.setdefault("phase", "pdf_verification")
        return verifier.classify(result, **context)

    def apply_correction(self, document: Any, correction: CorrectionRecord) -> None:
        """Generic dispatch for "a reviewer accepted this correction."

        Looks up the verifier that owns ``correction.object_type`` and
        calls its ``apply()`` — the one place that verifier's actual
        repair logic lives. This is what makes accepting a correction a
        real, working mutation for any registered asset type, not
        audit-trail bookkeeping for some and a bespoke endpoint for
        others. Callers are responsible for updating ``correction.status``
        themselves after this returns (this method only mutates the
        Document side of the correction).

        FEATURE_020: bumps document.version by one — the single choke
        point every correction-driven mutation passes through, so every
        registered asset type's exports become invalidatable for free
        (see src/api/routes.py's export-download handlers). Guarded by
        hasattr() so lightweight test doubles without a version field
        (common across this codebase's verifier tests) keep working
        unchanged.
        """
        verifier = self._require(correction.object_type)
        verifier.apply(document, correction)
        if hasattr(document, "version"):
            document.version += 1

    def revert_correction(self, document: Any, correction: CorrectionRecord) -> None:
        """Generic dispatch for "a reviewer undid this correction."

        Looks up the verifier that owns ``correction.object_type`` and
        calls its ``revert()`` (concrete-by-default on SemanticVerifier —
        see src/verification/base.py). Callers are responsible for setting
        ``correction.status = CorrectionStatus.REVERTED`` themselves.

        FEATURE_020: bumps document.version — see apply_correction()
        above; a revert is just as much a content change as an apply.
        """
        verifier = self._require(correction.object_type)
        verifier.revert(document, correction)
        if hasattr(document, "version"):
            document.version += 1

    def findings_to_corrections(self, document: Any, findings: List[Finding]) -> None:
        """Append one CorrectionRecord per finding to document.corrections.

        This is the first real writer of that field (it has existed since
        Phase M-1 but stayed empty — no verification pass ran until now).
        """
        for finding in findings:
            verifier = self._verifiers.get(finding.asset_type)
            if verifier is None:
                continue
            spec = verifier.rule_table().get(finding.kind)
            if spec is None:
                continue
            document.corrections.append(
                CorrectionRecord(
                    object_type=finding.asset_type,
                    object_id=finding.object_id,
                    field=finding.kind,
                    original_value=finding.original_value or "",
                    proposed_value=finding.proposed_value or "",
                    evidence=finding.evidence,
                    evidence_items=finding.evidence_items,
                    confidence=finding.confidence,
                    reason=finding.message,
                    reason_code=spec.reason_code,
                    provider="mathpix",
                    status=CorrectionStatus.PROPOSED,
                )
            )

    def findings_to_validation_issues(
        self, document: Any, findings: List[Finding]
    ) -> List[ValidationIssue]:
        """Translate findings into ValidationIssues for the existing
        Validation tab. Generic — never special-cases an asset_type."""
        issues: List[ValidationIssue] = []
        for finding in findings:
            verifier = self._verifiers.get(finding.asset_type)
            if verifier is None:
                continue
            spec = verifier.rule_table().get(finding.kind)
            if spec is None:
                continue
            try:
                severity = Severity(spec.severity)
            except ValueError:
                severity = Severity.WARNING
            issues.append(
                ValidationIssue(
                    severity=severity,
                    rule_id=spec.rule_id,
                    message=finding.message,
                    page_number=None,
                    suggested_action=None,
                )
            )
        return issues

    def findings_to_repair_suggestions(self, findings: List[Finding]) -> List[RepairSuggestion]:
        """Translate findings into the richer, reviewer-facing
        RepairSuggestion view — Problem/Current/Suggested/Reason/
        Confidence/Evidence breakdown — instead of a raw Finding. Generic:
        every field comes straight off Finding; no asset_type branching."""
        suggestions: List[RepairSuggestion] = []
        for finding in findings:
            verifier = self._verifiers.get(finding.asset_type)
            if verifier is None:
                continue
            spec = verifier.rule_table().get(finding.kind)
            if spec is None:
                continue
            suggestions.append(
                RepairSuggestion(
                    object_type=finding.asset_type,
                    object_id=finding.object_id,
                    problem=finding.message,
                    current_value=finding.original_value or "",
                    suggested_value=finding.proposed_value or "",
                    reason=finding.message,
                    confidence=finding.confidence,
                    evidence=finding.evidence_items,
                )
            )
        return suggestions


def classify_benchmark_outcome(decision: MergeDecision, finding: Optional[Finding] = None) -> BenchmarkOutcome:
    """Derive a BenchmarkOutcome mechanically from a MergeDecision (and,
    when available, the finding it produced) — no per-verifier code
    needed, so every registered asset type gets benchmark self-reporting
    for free the moment it builds classify() on merge_decisions().
    """
    if decision.action == MergeAction.RECOVER:
        return BenchmarkOutcome.RECOVERED
    if decision.action == MergeAction.REPAIR:
        return BenchmarkOutcome.CORRECTED
    # KEEP: either genuinely confirmed, or an unconfirmed Mathpix value
    # (no PDF evidence matched it at all) — the latter is a candidate the
    # verifier itself may separately flag as low-confidence/missing.
    if decision.pdf_evidence is None:
        if finding is not None and finding.confidence is not None and finding.confidence < 0.5:
            return BenchmarkOutcome.MANUAL_INTERVENTION_REQUIRED
        return BenchmarkOutcome.MISSED if finding is not None else BenchmarkOutcome.CONFIRMED
    return BenchmarkOutcome.CONFIRMED


# Module-level singleton — asset modules (e.g. src/verification/figures.py)
# import this and call engine.register(...) at import time.
engine = CrossSourceVerificationEngine()
