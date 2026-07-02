"""SemanticObject — the universal base every remediable document object shares.

Reading Heading/Footnote/Table/Image side by side found the same handful of
concepts reinvented four times with different names, types, and
completeness: an identity field, a page number, a bbox, a provenance marker,
a confidence score, a verification status, and a review lifecycle. This
module is the one real base class that collapses that duplication for every
future object type (List, Table, Footnote, Callout, Equation, ...), and for
the object types migrated onto it now (Image, Heading, List).

Every field here has a default so no existing construction call site needs
to change — subclasses add fields freely; nothing here is required.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from src.models.bounding_box import BoundingBox
from src.models.lifecycle import ObjectLifecycleStatus
from src.models.verification import VerificationStatus


class ProvenanceSource(str, Enum):
    """Where a semantic object's content actually came from.

    Supersedes the narrower, image-only ``ImportSource`` (PDF/MATHPIX/MANUAL)
    — every value there maps onto one of these. Not named ``source`` to avoid
    colliding with ``Heading.source``/``Footnote.source``, which are
    pre-existing free-string fields with a different (narrower) vocabulary;
    those stay as-is until their models are migrated onto SemanticObject too
    (see docs/DECISIONS_LOG.md roadmap entry for this refactor).
    """

    MATHPIX = "mathpix"
    PDF_NATIVE = "pdf_native"
    PDF_RECOVERED = "pdf_recovered"
    AI_GENERATED = "ai_generated"
    MANUAL_REVIEWER = "manual_reviewer"
    RAWRS_REPAIR = "rawrs_repair"


class SemanticObject(BaseModel):
    """Universal base for every object RAWRS detects, verifies, and reviews.

    ``id`` is intentionally optional at this level — each subclass backfills
    it from whatever identity field it already has (``table_id``,
    ``image_id``, ``footnote_id``, or a synthesized value) via a
    ``model_validator(mode="after")``, so no existing construction site
    needs to pass a new required argument.

    ``correction_ids`` links into ``Document.corrections`` (the durable
    audit trail) — this is the object's own view of its correction history,
    not a duplicate of CorrectionRecord's data.
    """

    id: Optional[str] = None
    object_type: str = ""
    page_number: Optional[int] = None
    bbox: Optional[BoundingBox] = None
    provenance: ProvenanceSource = ProvenanceSource.PDF_NATIVE
    confidence: Optional[float] = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    lifecycle_status: ObjectLifecycleStatus = ObjectLifecycleStatus.DETECTED
    correction_ids: List[str] = Field(default_factory=list)
