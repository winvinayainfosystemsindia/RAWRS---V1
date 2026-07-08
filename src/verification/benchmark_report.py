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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.models.verification import VerificationStatus

# Finding.kind values every current verifier uses for a RECOVER proposal
# (Mathpix missed a real object the PDF independently found). A RECOVER's
# canonical object doesn't exist — and so carries no verification_status
# to tally — until a reviewer accepts it, so recovery rate can only be
# computed from document.corrections, not the object populations below.
_RECOVER_FIELDS = {"missing_from_package", "recovered_from_pdf"}

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
    }


def aggregate(document: Any) -> Dict[str, Any]:
    """Build the per-asset-type + whole-document benchmark summary.

    Returns a plain, JSON-serializable dict — this feeds
    src/pipeline/phase1_pipeline.py::_write_validation_report()'s
    existing JSON report directly, not a new endpoint or schema.
    """
    populations = _canonical_populations(document)
    by_type: Dict[str, AssetTypeBenchmark] = {
        asset_type: AssetTypeBenchmark(asset_type=asset_type) for asset_type in populations
    }

    for asset_type, objects in populations.items():
        bench = by_type[asset_type]
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

    total_verified = sum(b.verified for b in by_type.values())
    total_checked = sum(b.checked_total for b in by_type.values())

    return {
        "per_asset_type": {
            k: v.to_dict() for k, v in by_type.items() if v.checked_total or v.total_corrections
        },
        "overall_mathpix_accuracy": (total_verified / total_checked) if total_checked else None,
        "total_corrections_proposed": len(document.corrections),
    }
