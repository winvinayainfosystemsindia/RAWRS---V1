"""Heading model for RAWRS document structure.

See docs/HEADING_RULES.md for the canonical hierarchy and validation rules.
"""

from enum import Enum, IntEnum
from typing import Optional

from pydantic import Field, field_validator, model_validator

from src.models.semantic_object import SemanticObject


class HeadingLevel(IntEnum):
    """Heading hierarchy levels, H1 through H6.

    H6 is reserved for PDF page markers rather than content headings
    (see docs/HEADING_RULES.md and docs/PAGE_RULES.md).
    """

    H1 = 1
    H2 = 2
    H3 = 3
    H4 = 4
    H5 = 5
    H6 = 6


class HeadingReviewStatus(str, Enum):
    """Human review lifecycle for a detected heading.

    DETECTED: auto-detected, awaiting review.
    APPROVED: reviewer confirmed level and text are correct.
    LEVEL_CHANGED: reviewer corrected the heading level.
    REJECTED: reviewer marked this as a false positive (not a real heading).
    """

    DETECTED = "detected"
    APPROVED = "approved"
    LEVEL_CHANGED = "level_changed"
    REJECTED = "rejected"


class Heading(SemanticObject):
    """A single heading detected in the document.

    Represents both content headings (H1-H5) and PDF page markers
    (H6, ``is_page_marker=True``). Page markers are modeled as headings
    rather than a separate type so they participate naturally in DOCX
    navigation structure and heading-hierarchy validation.

    ``document_order`` is the position of this heading across the whole
    document (not the page), since heading-sequence validation (e.g.
    detecting an H1 -> H3 jump) must consider document-wide order, not
    per-page order.

    ``review_status`` tracks the human review lifecycle (FEATURE_016A).
    ``reviewer_note`` holds an optional reviewer annotation.

    Migrated onto ``SemanticObject`` (id/bbox/provenance/confidence/
    verification_status/lifecycle_status) for HeadingVerifier
    (src/verification/headings.py). ``source``/``review_status`` stay as
    their own real fields rather than being folded into ``provenance`` —
    same reasoning as ``Image.import_source`` (see src/models/image.py):
    collapsing them now would risk existing readers of these exact
    values. ``id`` backfills from ``document_order`` since headings have
    no independent identity field of their own.
    """

    object_type: str = "heading"
    level: HeadingLevel
    text: str = Field(..., min_length=1)
    page_number: int = Field(..., ge=1)
    document_order: int = Field(..., ge=0)
    is_page_marker: bool = False
    review_status: HeadingReviewStatus = HeadingReviewStatus.DETECTED
    reviewer_note: Optional[str] = None
    # Import provenance: "rawrs" (rule-based classifier), "mathpix" (imported),
    # "rawrs_recovery" (RAWRS found it; provider missed it), "pdf_native"
    # (a PDF-side verification candidate — see detect_headings_from_pdf()).
    source: str = "rawrs"
    # FEATURE_020 — P2Block.source_line (src/mathpix/mmd_parser.py), the
    # position in the source .mmd this heading came from. Mathpix-path
    # only; None for RAWRS-native headings (document_order already
    # orders those correctly within their own type). The shared,
    # cross-type sort key src/markdown/markdown_builder.py's
    # _render_page_semantic() uses to interleave headings/paragraphs/
    # lists/tables/images/callouts in true document order on one page —
    # document_order alone can't do this, since it only orders within
    # one object type.
    source_line: Optional[int] = None

    @model_validator(mode="after")
    def _backfill_semantic_object_id(self) -> "Heading":
        if self.id is None:
            self.id = f"heading-{self.document_order}"
        return self

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        """Reject whitespace-only heading text.

        Empty headings are an explicit validation concern in
        docs/HEADING_RULES.md, so this is rejected at the model level.
        """
        if not value.strip():
            raise ValueError("Heading text must not be blank")
        return value

    @model_validator(mode="after")
    def page_marker_must_be_h6(self) -> "Heading":
        """Enforce that H6 and is_page_marker imply each other.

        docs/HEADING_RULES.md reserves H6 exclusively for PDF page
        markers, so level == H6 and is_page_marker must always agree.
        """
        if self.level == HeadingLevel.H6 and not self.is_page_marker:
            raise ValueError("H6 headings must have is_page_marker=True")
        if self.is_page_marker and self.level != HeadingLevel.H6:
            raise ValueError("Page markers must use level=H6")
        return self
