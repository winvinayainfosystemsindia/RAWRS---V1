"""Document metadata: the tenth registered asset type (W-1 Group B).

Like ``"reading_order"``, ``"metadata"`` has always been named in
``CorrectionRecord``'s docstring as an expected ``object_type`` and never
had a verifier, so ``PATCH /metadata`` wrote straight into the Semantic
Document. The four fields it edits are not cosmetic: ``language`` and
``title`` are read by the accessibility metadata rules (META_001/META_002)
and all four are written into the DOCX core properties
(``dc:language``/``dc:title``/``dc:creator``/``dc:subject``) by
``docx_generator._apply_core_properties``. Editing them is a
projection-visible reviewer decision that had no audit row and no undo.

**One document-level owner, not one verifier per field.** The reviewer's
decision is "this document's accessibility metadata is now this", and a
single request may change several fields at once. So the correction
carries the whole editable set before and after, ``object_id`` is None
(the document is the object), and one request is one transaction.

**Only the editable four travel.** ``filename``, ``page_count`` and
``image_count`` are set by the pipeline stage that finalises processing —
derived from ingestion, not decided by anyone — as are
``processing_date``/``processing_duration_seconds``. Putting them in a
correction would claim a human decided something they did not, so they
stay off the rail and out of the payload.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.models.correction import CorrectionRecord
from src.verification.base import SemanticVerifier
from src.verification.matching import MatchResult, MultiSignalMatcher

ASSET_TYPE = "metadata"
DOCUMENT_METADATA = "document_metadata"

#: The reviewer-editable accessibility fields, and the whole of what a
#: metadata correction represents. Each one reaches a projection: see the
#: module docstring for where.
EDITABLE_FIELDS = ("language", "title", "author", "subject")


def encode_metadata(metadata: Any) -> str:
    """The editable metadata state, as a correction payload.

    Complete rather than differential, for the same reason reading order
    is: undo must restore ``None`` — a field the reviewer cleared — as
    faithfully as it restores a previous string.
    """
    if metadata is None:
        return json.dumps({field: None for field in EDITABLE_FIELDS})
    return json.dumps({field: getattr(metadata, field, None) for field in EDITABLE_FIELDS})


class MetadataVerifier(SemanticVerifier):
    """Single-source: document metadata is the document's own, so there is
    nothing to reconcile it against."""

    asset_type = ASSET_TYPE

    def build_pdf_matcher(self) -> MultiSignalMatcher:
        """No second source — the documented single-source default."""
        return MultiSignalMatcher([])

    def to_canonical(self, match_result: MatchResult, **context: Any) -> List[Any]:
        """Metadata is a field set on an object that already exists."""
        return []

    def classify(self, match_result: MatchResult, **context: Any) -> List[Any]:
        """Not a producer. Missing language and title are already reported
        by META_001/META_002; this verifier carries the reviewer's answer
        rather than restating the question."""
        return []

    def rule_table(self) -> Dict[str, Any]:
        from src.models.verification import RuleSpec

        return {
            DOCUMENT_METADATA: RuleSpec(
                rule_id="METADATA_001",
                reason_code="DOCUMENT_METADATA_EDITED_BY_REVIEWER",
                severity="info",
            )
        }

    def apply(self, document: Any, correction: CorrectionRecord) -> None:
        """Set the editable metadata to the state this correction carries.

        Symmetric and idempotent: the payload is the complete editable
        set, so ``SemanticVerifier.revert()``'s generic swap restores the
        previous values — including the ones that were ``None`` — and
        applying twice writes the same thing.
        """
        if correction.field != DOCUMENT_METADATA or not correction.proposed_value:
            return
        metadata = getattr(document, "metadata", None)
        if metadata is None:
            return

        state: Dict[str, Optional[str]] = json.loads(correction.proposed_value)
        for field in EDITABLE_FIELDS:
            if field in state:
                setattr(metadata, field, state[field])


def _register() -> None:
    from src.verification.engine import engine

    engine.register(MetadataVerifier())


_register()
