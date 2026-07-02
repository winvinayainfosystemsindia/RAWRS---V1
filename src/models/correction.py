"""CorrectionRecord model — RAWRS verification audit trail.

Every change RAWRS makes to imported content is recorded here, preserving
the original provider value alongside the proposed correction and reviewer
decision.  The audit trail is non-destructive: the Document model carries
the live (accepted) value; CorrectionRecord carries the history.

The chain for every imported object is::

    provider_value → verification_result → proposed_correction →
    reviewer_decision → final_accessible_output

This is the canonical data structure for that chain.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from src.models.verification import EvidenceItem


class CorrectionStatus(str, Enum):
    """Lifecycle of a single correction proposal.

    The generic reviewer-action vocabulary (see the Corrections API,
    src/api/routes.py) maps one-to-one onto these statuses: Accept ->
    ACCEPTED, Reject -> REJECTED, Edit -> EDITED, Ignore -> IGNORED,
    Needs Review -> PENDING_REVIEW, Undo -> REVERTED. Every current and
    future verifier's reviewer step uses this same six-state lifecycle —
    no per-object-type status enum is ever needed again.

    PROPOSED:      RAWRS identified a potential correction; awaiting review.
    AUTO_APPLIED:  Applied without review (high-confidence, low-risk).
    ACCEPTED:      Reviewer confirmed RAWRS's correction is correct.
    REJECTED:      Reviewer kept the original provider value instead — "no,
                   this was wrong."
    EDITED:        Reviewer changed the proposed value before accepting it.
    IGNORED:       Reviewer dismissed this specific instance without
                   judging it right or wrong — "don't ask again," distinct
                   from REJECTED's "no."
    PENDING_REVIEW: Flagged for human attention; not yet decided ("Needs
                   Review").
    REVERTED:      A previously ACCEPTED/EDITED correction was undone —
                   the document mutation was rolled back.
    """

    PROPOSED = "proposed"
    AUTO_APPLIED = "auto_applied"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EDITED = "edited"
    IGNORED = "ignored"
    PENDING_REVIEW = "pending_review"
    REVERTED = "reverted"


class CorrectionRecord(BaseModel):
    """One proposed or applied correction to an imported document object.

    ``object_type`` names the semantic category of the affected object:
    "heading", "paragraph", "table", "image", "footnote", "front_matter",
    "reading_order", "metadata", "caption", "list".

    ``object_id`` is the identifier of the specific affected object when
    one exists (e.g. Table.table_id, Footnote.footnote_id).  None when
    the object has no stable id (e.g. a raw paragraph block).

    ``field`` names which attribute changed: "level", "text", "body",
    "caption", "order", "page_number", "is_bold", etc.

    ``original_value`` is what the import provider said.
    ``proposed_value`` is what RAWRS proposes instead.

    ``evidence`` is machine-readable verification context (e.g.
    "pdf_font_rank=3,mathpix_level=2") so a reviewer can inspect raw
    signals.

    ``reason`` is a human-readable explanation.

    ``reason_code`` is a stable key for the correction category:
    "HEADING_LEVEL_MISMATCH", "PARAGRAPH_MERGE_DETECTED",
    "FOOTNOTE_MISSING_FROM_PROVIDER", "TABLE_MISSING_FROM_PROVIDER",
    "OCR_TYPO_DETECTED", "READING_ORDER_ANOMALY", etc.

    ``provider`` names the import provider the original_value came from.
    Currently always "mathpix"; future values: "abbyy", "azure_doc_ai",
    "google_doc_ai", "docling", "rawrs_native".
    """

    correction_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    object_type: str
    object_id: Optional[str] = None
    field: str
    original_value: str
    proposed_value: str
    evidence: str = ""
    # Structured evidence breakdown, mirrored from Finding.evidence_items
    # (see engine.findings_to_corrections) — additive, existing readers of
    # the free-text `evidence` string above are unaffected.
    evidence_items: List[EvidenceItem] = Field(default_factory=list)
    confidence: Optional[float] = None
    reason: str = ""
    reason_code: str = ""
    provider: str = "mathpix"
    status: CorrectionStatus = CorrectionStatus.PROPOSED
    reviewed_at: Optional[datetime] = None
    reviewer_notes: Optional[str] = None
