"""Figure model for RAWRS image/figure metadata.

See docs/VALIDATION_RULES.md (Figure Validation) for the checks this
model exists to support: missing captions, unlinked figure references,
and missing figure numbering. ``alt_text``/``alt_text_status`` (added
Phase F.3) extend this to accessibility metadata - see the Phase H.5
Alt Text Architecture Audit for why alt text lives here rather than on
Image directly or as a new top-level model: it is exactly as
figure-shaped as ``caption``/``label``/``number`` already are (a
one-to-one description of a figure's accessibility role, not a
property of the raw extracted image bytes), and a non-content image
(already filtered out before a Figure is ever built - see
src/images/image_extractor.py) never needs one.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class AltTextStatus(str, Enum):
    """Review state of Figure.alt_text.

    PENDING_REVIEW is set unconditionally on every retained image's Figure
    by src/images/image_extractor.py (Phase F.3) — alt_text is always a
    deterministic placeholder at that point. The remaining values are set
    by the human review workflow (FEATURE_012 / src/api/routes.py):
    AI_GENERATED once on-demand AI generation has run (but human hasn't
    acted yet), APPROVED/REJECTED/DECORATIVE/COMPLEX/SKIPPED after human
    action. HUMAN_REVIEWED is the legacy terminal state kept for backward
    compatibility — no code currently sets it, but removing it would break
    any stored data or tests that reference it.
    """

    PENDING_REVIEW = "pending_review"
    HUMAN_REVIEWED = "human_reviewed"   # legacy — kept for backward compat
    AI_GENERATED = "ai_generated"       # AI ran; human hasn't acted yet
    APPROVED = "approved"               # human approved (possibly edited)
    REJECTED = "rejected"               # human rejected; available to regenerate
    DECORATIVE = "decorative"           # human confirmed no alt text needed
    COMPLEX = "complex"                 # human flagged: needs long description
    SKIPPED = "skipped"                 # human explicitly deferred


class Figure(BaseModel):
    """Caption and labeling metadata for a figure.

    A Figure is always composed within an Image (see Image.figure) rather
    than standing alone as a top-level document entity, per approved
    architecture decision #4.

    AI fields (ai_description, ai_purpose, ai_visible_text, ai_confidence,
    ai_warnings) are populated only when the reviewer explicitly triggers
    on-demand AI generation via POST /images/{id}/generate-alt-text —
    never automatically during pipeline execution. All default to
    None/empty so every existing Figure construction site remains valid.
    """

    label: Optional[str] = None
    number: Optional[int] = None
    caption: Optional[str] = None
    is_referenced: bool = False
    alt_text: Optional[str] = None
    alt_text_status: Optional[AltTextStatus] = None
    # Caption-duplication fix: the exact source TextBlock.text the
    # caption was matched from (src/images/image_extractor.py's
    # _link_figures()), kept verbatim so src/markdown/markdown_builder.py
    # can suppress that same line during ordinary body rendering -
    # without it, the caption (a real same-page line of body text) is
    # rendered once in place AND a second time, italicized, attached to
    # the image - the same exact-line-matching technique
    # Footnote.body_source_text already uses for the analogous footnote
    # leak fix. None when no caption was matched (the figure has no
    # caption at all), or for a Figure built before this field existed.
    caption_source_text: Optional[str] = None

    # AI structured response — all None/empty until generate-alt-text called
    ai_description: Optional[str] = None
    ai_purpose: Optional[str] = None
    ai_visible_text: Optional[str] = None
    ai_confidence: Optional[float] = None   # 0.0–1.0; None = not yet generated
    ai_warnings: List[str] = Field(default_factory=list)
