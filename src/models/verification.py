"""Generic cross-source verification vocabulary.

Shared by every asset type that plugs into the verification engine
(src/verification/engine.py) — figures today, headings/footnotes/tables
later. Nothing here is specific to any one asset type.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from src.verification.evidence import EvidenceSignal


class VerificationStatus(str, Enum):
    """Per-object verification state, set by a PDF-verification pass.

    UNVERIFIED is the default for every object until a verification pass
    actually runs against it (e.g. the RAWRS-native path never runs one,
    so every Image stays UNVERIFIED forever — that's an accurate
    description, not a gap).
    """

    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    MISMATCH = "mismatch"
    ORPHAN = "orphan"
    MISSING_FROM_PDF = "missing_from_pdf"
    LOW_CONFIDENCE = "low_confidence"


class ImportSource(str, Enum):
    """Where a canonical object's content actually came from."""

    MATHPIX = "mathpix"
    PDF = "pdf"
    MANUAL = "manual"


class Finding(BaseModel):
    """One raw, asset-agnostic verification observation.

    Produced by an AssetVerifier's classify() step; translated by the
    engine into a CorrectionRecord (stateful, reviewer-facing audit trail)
    and/or a ValidationIssue (transient, recomputed each validation run).

    ``kind`` is a stable per-asset-type string (e.g. "missing_from_package",
    "caption_mismatch") that the owning AssetVerifier's rule_table() maps to
    a RuleSpec. This module does not enumerate kinds — they belong to
    whichever asset type produced the finding.

    ``original_value``/``proposed_value`` are machine-readable (the owning
    verifier's own encoding — e.g. a bare level number, or a small JSON
    blob for a multi-field recovery) so that same verifier's ``apply()``
    can parse them back out of the resulting ``CorrectionRecord`` once a
    reviewer accepts it. Both default to ``None`` for findings that
    propose no document mutation at all (``apply()`` no-ops for those).
    ``evidence``/``message`` remain the human-readable explanation shown
    to a reviewer — distinct from the values ``apply()`` actually acts on.
    """

    asset_type: str
    kind: str
    object_id: Optional[str] = None
    confidence: Optional[float] = None
    evidence: str = ""
    message: str = ""
    original_value: Optional[str] = None
    proposed_value: Optional[str] = None
    # Structured, weighted evidence breakdown (additive — every existing
    # Finding construction site, e.g. figures.py, keeps working with just
    # the free-text `evidence` string above; verifiers populate this list
    # with EvidenceSignal(name, score, weight, note) so a reviewer sees
    # "font size / spacing / bold" as discrete, weighted signals rather
    # than one opaque sentence — the same primitive
    # src/verification/evidence.py's EvidenceBundle aggregates for
    # cross-signal confidence fusion (FEATURE_019).
    evidence_items: List[EvidenceSignal] = Field(default_factory=list)


class RuleSpec(BaseModel):
    """Maps one Finding.kind to the identifiers the rest of RAWRS understands."""

    rule_id: str
    reason_code: str
    severity: str = "warning"


class BenchmarkOutcome(str, Enum):
    """How one Finding's underlying MergeDecision (src/verification/merge.py)
    should be tallied for benchmark measurement. Derived mechanically from
    MergeAction + confidence (see engine.classify_benchmark_outcome) — no
    per-verifier code needed, so every registered asset type gets benchmark
    self-reporting for free.
    """

    CONFIRMED = "confirmed"
    RECOVERED = "recovered"
    CORRECTED = "corrected"
    MISSED = "missed"
    FALSE_POSITIVE = "false_positive"
    MANUAL_INTERVENTION_REQUIRED = "manual_intervention_required"


class RepairSuggestion(BaseModel):
    """The reviewer-facing, structured view of a still-PROPOSED
    CorrectionRecord — "Problem / Current / Suggested / Reason / Confidence
    / Evidence breakdown", not a raw Finding. Built by
    ``engine.findings_to_repair_suggestions()``; CorrectionRecord remains
    the durable audit-trail row underneath, this is a presentation
    translation, not a second source of truth.
    """

    object_type: str
    object_id: Optional[str] = None
    problem: str
    current_value: str
    suggested_value: str
    reason: str
    confidence: Optional[float] = None
    evidence: List[EvidenceSignal] = Field(default_factory=list)
    benchmark_outcome: Optional[BenchmarkOutcome] = None
