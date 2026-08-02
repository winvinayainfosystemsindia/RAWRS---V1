"""Heading model for RAWRS document structure.

See docs/HEADING_RULES.md for the canonical hierarchy and validation rules.
"""

from enum import Enum, IntEnum
from typing import List, Optional

from pydantic import Field, field_validator, model_validator

from src.models.semantic_object import SemanticObject
from src.verification.evidence import EvidenceSignal


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
    # L3.1 — the heading signals that argued for this detection, from
    # src/headings/heading_signals.py::evaluate_heading(). Same field name,
    # type, and purpose as CorrectionRecord.evidence_items: the shared
    # EvidenceSignal primitive (FEATURE_019), not a heading-specific
    # vocabulary. ``confidence`` (inherited from SemanticObject) is this
    # bundle's weighted mean. Additive: empty for headings produced outside
    # the native detector (Mathpix import, page markers, fixtures), so an
    # empty list always means "no evidence recorded", never "no support".
    #
    # Read THIS, not ``confidence``, when you need detection strength:
    # ``confidence`` is shared with the cross-source verifier, which
    # overwrites it with match confidence ("is this the same heading the
    # PDF found?") at src/verification/headings.py's merge step - a
    # different question with the same field name (a pre-existing
    # SemanticObject ambiguity, not one this field introduces). Signals
    # here are individually named and carry ``source_module``, so their
    # provenance is never ambiguous.
    evidence_items: List[EvidenceSignal] = Field(default_factory=list)
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
    # P2 — the ``TextBlock.block_id`` of the line this heading was detected
    # from. The first genuinely new *relationship* in the model: typed,
    # directional, id-based (see docs/RAWRS_PROJECTION_ARCHITECTURE.md).
    #
    # Before this existed, every consumer that needed "where does this
    # heading sit in the body flow?" recovered it by matching heading text
    # against page text — src/markdown/markdown_builder.py's two body
    # renderers and src/structure/content_stream.py, three independent
    # reconstructions of a fact the detector knew and discarded. Text
    # matching is exactly wrong for this: identical text recurring across
    # pages is the running-header signature, and a wrapped heading's joined
    # text (feature_007) matches no single line at all.
    #
    # None means "no block correspondence recorded", never "no block":
    # Mathpix-path headings (which carry ``source_line`` instead), page
    # markers (synthesized per page, not detected from a line),
    # detect_headings_from_pdf() candidates (no Document, so no blocks), and
    # fixtures predating this field. Every consumer must keep its existing
    # fallback for that case.
    source_block_id: Optional[str] = None
    # P2 — the blocks feature_007 (Wrapped Heading Continuation Repair)
    # absorbed into ``text`` after the anchor. A heading printed across two
    # PDF lines is one heading whose text spans several blocks, so the
    # continuation lines are this heading's, not the body's, and a
    # projection must not render them again as prose.
    #
    # Before this existed nothing recorded them, and the omission was
    # masked by the very text matching P2 removes: the joined text matched
    # no single line, so the renderer silently dropped the whole heading
    # and emitted every one of its lines as body instead. Two defects that
    # happened to cancel - visible in the benchmark the moment placement
    # became id-based.
    continuation_block_ids: List[str] = Field(default_factory=list)

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
