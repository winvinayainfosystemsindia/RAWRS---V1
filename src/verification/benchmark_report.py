"""Benchmark aggregation report (FEATURE_019).

Tallies document.headings/lists/callouts/tables/images' cross-source
verification_status (SemanticObject's own field — set by every registered
SemanticVerifier's classify(), regardless of whether a Finding/
CorrectionRecord was produced; the majority "no finding, status=VERIFIED"
case IS the confirmation, not an absence of signal) alongside
document.corrections' reviewer-action status, into one per-asset-type +
whole-document summary: objects preserved (VERIFIED), repaired
(MISMATCH+corrected), recovered, Mathpix accuracy, and recovery rate.

Wired into src/pipeline/phase1_pipeline.py's existing JSON validation
report (_write_validation_report()) rather than a new report or endpoint
— see FEATURE_019's plan.

M-3.3 extends this with remediation-oriented metrics — repair_rate,
manual_corrections_remaining, confidence_distribution, object_count, and
(from document.validation_issues, already populated by Stage 8 before
this runs — see src/pipeline/phase1_pipeline.py) accessibility_score.
All additive: every M-3.1/M-3.2-era key keeps its existing meaning.

"Human Minutes Saved" (requested but NOT implemented — do not fabricate
it): would need a real per-correction-type time estimate, which RAWRS has
no data source for today. To build it for real: (1) telemetry of actual
reviewer wall-clock time per correction (timestamp Accept/Reject/Edit
against when the correction was first shown), aggregated per rule_id
over enough real review sessions to be a distribution, not a guess; (2)
a documented per-rule_id minutes-saved constant derived FROM that
telemetry, not invented; (3) then minutes_saved = sum(count[rule_id] *
minutes[rule_id]) over accepted+auto_applied corrections. None of that
data exists yet, so the metric stays absent rather than seeded with a
made-up constant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.models.validation_issue import Severity, ValidationIssue, ValidationIssueStatus
from src.models.verification import VerificationStatus

# Finding.kind values every current verifier uses for a RECOVER proposal
# (Mathpix missed a real object the PDF independently found). A RECOVER's
# canonical object doesn't exist — and so carries no verification_status
# to tally — until a reviewer accepts it, so recovery rate can only be
# computed from document.corrections, not the object populations below.
# "missing_from_mathpix" is TableVerifier's own name for the same concept
# (src/verification/tables.py) — kept as its own literal rather than
# renamed for consistency, since renaming it means touching TableVerifier,
# out of scope here (see M-3.2's closeout: don't revisit it without cause).
_RECOVER_FIELDS = {"missing_from_package", "recovered_from_pdf", "missing_from_mathpix"}

# Points deducted per open validation issue, by severity — reused, not
# reinvented, from the Severity vocabulary validation issues already
# carry. Deliberately simple linear deduction (Lighthouse-style), clamped
# to [0, 100]: no per-rule weighting, since no evidence yet justifies one
# rule being worse than another of the same severity.
_ACCESSIBILITY_SEVERITY_WEIGHT = {Severity.ERROR: 10, Severity.WARNING: 3, Severity.INFO: 1}

# Confidence histogram buckets for document.corrections' confidence field.
_CONFIDENCE_BUCKETS = [
    ("0.0-0.5", 0.0, 0.5),
    ("0.5-0.7", 0.5, 0.7),
    ("0.7-0.85", 0.7, 0.85),
    ("0.85-1.0", 0.85, 1.0001),  # upper bound inclusive of 1.0
]


def compute_accessibility_score(issues: List[ValidationIssue]) -> float:
    """100 minus a severity-weighted deduction per open validation issue,
    floored at 0. Ignores IGNORED/DEFERRED issues — a reviewer already
    triaged those as not worth counting against the document."""
    deduction = sum(
        _ACCESSIBILITY_SEVERITY_WEIGHT.get(issue.severity, 1)
        for issue in issues
        if issue.status == ValidationIssueStatus.OPEN
    )
    return float(max(0, 100 - deduction))


def _confidence_distribution(confidences: List[float]) -> Dict[str, int]:
    buckets = {label: 0 for label, _, _ in _CONFIDENCE_BUCKETS}
    for c in confidences:
        for label, lo, hi in _CONFIDENCE_BUCKETS:
            if lo <= c < hi:
                buckets[label] += 1
                break
    return buckets

_STATUS_FIELD = {
    VerificationStatus.VERIFIED: "verified",
    VerificationStatus.MISMATCH: "mismatch",
    VerificationStatus.MISSING_FROM_PDF: "missing_from_pdf",
    VerificationStatus.LOW_CONFIDENCE: "low_confidence",
    VerificationStatus.ORPHAN: "orphan",
    VerificationStatus.UNVERIFIED: "unverified",
}

_CORRECTION_STATUS_FIELD = {
    "proposed": "corrections_proposed",
    "accepted": "corrections_accepted",
    "rejected": "corrections_rejected",
    "edited": "corrections_edited",
    "ignored": "corrections_ignored",
    "pending_review": "corrections_pending_review",
    "reverted": "corrections_reverted",
}


@dataclass
class AssetTypeBenchmark:
    asset_type: str
    verified: int = 0
    mismatch: int = 0
    missing_from_pdf: int = 0
    low_confidence: int = 0
    orphan: int = 0
    unverified: int = 0
    corrections_proposed: int = 0
    corrections_accepted: int = 0
    corrections_rejected: int = 0
    corrections_edited: int = 0
    corrections_ignored: int = 0
    corrections_pending_review: int = 0
    corrections_reverted: int = 0
    recovered_proposed: int = 0
    recovered_accepted: int = 0
    repair_proposed: int = 0
    repair_accepted: int = 0
    object_count: int = 0

    @property
    def remaining(self) -> int:
        """Manual Corrections Remaining: proposals still awaiting a
        reviewer decision (not yet actioned either way)."""
        return self.corrections_proposed + self.corrections_pending_review

    @property
    def repair_rate(self) -> Optional[float]:
        """Fraction of proposed REPAIR corrections (mismatch found, fix
        proposed — excludes RECOVER and informational-only findings) a
        reviewer accepted. None when none were ever proposed."""
        return self.repair_accepted / self.repair_proposed if self.repair_proposed else None

    @property
    def checked_total(self) -> int:
        """Objects a cross-source verification pass actually looked at —
        excludes UNVERIFIED (the RAWRS-native path runs no cross-source
        check at all, so counting those would silently overstate accuracy)."""
        return self.verified + self.mismatch + self.missing_from_pdf + self.low_confidence + self.orphan

    @property
    def mathpix_accuracy(self) -> Optional[float]:
        """Fraction of checked objects Mathpix got right outright, no
        correction ever needed. None when nothing was ever checked."""
        return self.verified / self.checked_total if self.checked_total else None

    @property
    def recovery_rate(self) -> Optional[float]:
        """Fraction of proposed RECOVER corrections a reviewer accepted.
        None when none were ever proposed."""
        return self.recovered_accepted / self.recovered_proposed if self.recovered_proposed else None

    @property
    def total_corrections(self) -> int:
        return (
            self.corrections_proposed + self.corrections_accepted + self.corrections_rejected
            + self.corrections_edited + self.corrections_ignored + self.corrections_pending_review
            + self.corrections_reverted
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_type": self.asset_type,
            "verified": self.verified,
            "mismatch": self.mismatch,
            "missing_from_pdf": self.missing_from_pdf,
            "low_confidence": self.low_confidence,
            "orphan": self.orphan,
            "unverified": self.unverified,
            "mathpix_accuracy": self.mathpix_accuracy,
            "corrections_proposed": self.corrections_proposed,
            "corrections_accepted": self.corrections_accepted,
            "corrections_rejected": self.corrections_rejected,
            "corrections_edited": self.corrections_edited,
            "corrections_ignored": self.corrections_ignored,
            "corrections_pending_review": self.corrections_pending_review,
            "corrections_reverted": self.corrections_reverted,
            "recovered_proposed": self.recovered_proposed,
            "recovered_accepted": self.recovered_accepted,
            "recovery_rate": self.recovery_rate,
            "repair_proposed": self.repair_proposed,
            "repair_accepted": self.repair_accepted,
            "repair_rate": self.repair_rate,
            "manual_corrections_remaining": self.remaining,
            "object_count": self.object_count,
        }


def _canonical_populations(document: Any) -> Dict[str, List[Any]]:
    """The object collections to tally verification_status over — every
    SemanticObject-derived collection a registered verifier owns. Page
    markers (H6) are excluded from "heading" — HeadingVerifier never
    verifies them (see src/verification/headings.py's module docstring)."""
    return {
        "heading": [h for h in document.headings if not h.is_page_marker],
        "list": list(document.lists),
        "callout": list(document.callouts),
        "table": list(document.tables),
        "image": list(document.images),
        "footnote": list(document.footnotes),
    }


def aggregate(document: Any) -> Dict[str, Any]:
    """Build the per-asset-type + whole-document benchmark summary.

    Returns a plain, JSON-serializable dict — this feeds
    src/pipeline/phase1_pipeline.py::_write_validation_report()'s
    existing JSON report directly, not a new endpoint or schema.
    """
    from src.verification.engine import engine  # local import: avoids a cycle at module load

    populations = _canonical_populations(document)
    by_type: Dict[str, AssetTypeBenchmark] = {
        asset_type: AssetTypeBenchmark(asset_type=asset_type) for asset_type in populations
    }

    for asset_type, objects in populations.items():
        bench = by_type[asset_type]
        bench.object_count = len(objects)
        for obj in objects:
            status = getattr(obj, "verification_status", VerificationStatus.UNVERIFIED)
            field_name = _STATUS_FIELD.get(status, "unverified")
            setattr(bench, field_name, getattr(bench, field_name) + 1)

    for correction in document.corrections:
        bench = by_type.setdefault(
            correction.object_type, AssetTypeBenchmark(asset_type=correction.object_type)
        )
        status_field = _CORRECTION_STATUS_FIELD.get(correction.status.value)
        if status_field:
            setattr(bench, status_field, getattr(bench, status_field) + 1)

        if correction.field in _RECOVER_FIELDS:
            bench.recovered_proposed += 1
            if correction.status.value in ("accepted", "edited"):
                bench.recovered_accepted += 1
            continue

        # REPAIR vs. informational-only: every verifier already declares
        # this distinction via its own rule_table() severity ("info" =
        # no document mutation proposed, e.g. low_confidence/orphan/
        # unconfirmed) — reused here rather than re-curated per field name.
        verifier = engine._verifiers.get(correction.object_type)
        spec = verifier.rule_table().get(correction.field) if verifier else None
        if spec is not None and spec.severity != "info":
            bench.repair_proposed += 1
            if correction.status.value in ("accepted", "edited"):
                bench.repair_accepted += 1

    total_verified = sum(b.verified for b in by_type.values())
    total_checked = sum(b.checked_total for b in by_type.values())
    confidences = [c.confidence for c in document.corrections if c.confidence is not None]

    return {
        "per_asset_type": {
            k: v.to_dict() for k, v in by_type.items() if v.checked_total or v.total_corrections
        },
        "overall_mathpix_accuracy": (total_verified / total_checked) if total_checked else None,
        "total_corrections_proposed": len(document.corrections),
        "manual_corrections_remaining": sum(b.remaining for b in by_type.values()),
        "confidence_distribution": _confidence_distribution(confidences),
        "accessibility_score": compute_accessibility_score(document.validation_issues),
    }
