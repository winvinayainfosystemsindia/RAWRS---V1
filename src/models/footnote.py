"""Footnote/Endnote model for RAWRS (Phase K).

See docs/PAGE_RULES.md ("Footnotes"/"Endnotes") for the Phase 1
responsibilities this model exists to support: detect, preserve the
reference, and record the location - never automatically remediate the
note's content. Page.footnote_references/endnote_references
(src/models/page.py) predate this model and were never populated by any
code - a bare List[str] cannot hold a marker-to-body relationship, only
a reference string. Footnote is the richer model that actually carries
that relationship; Page's lists are now populated as a per-page
projection of this canonical data (see src/footnotes/footnote_detector.py),
not a second, competing source of truth.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from src.models.lifecycle import ObjectLifecycleStatus


class FootnoteReviewStatus(str, Enum):
    """Human review lifecycle for a detected footnote/endnote.

    DETECTED: auto-detected, awaiting review.
    APPROVED: reviewer confirmed the note body and anchor are correct.
    EDITED: reviewer corrected the note body text.
    REJECTED: reviewer marked this as a false positive.
    """

    DETECTED = "detected"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


class NoteType(str, Enum):
    """Whether a detected note is a footnote (body on the same page as
    its marker, the print convention) or an endnote (body collected in
    a dedicated Notes/Endnotes section, detached from its marker's
    page) - see src/footnotes/footnote_detector.py for the detection
    rule each is based on.
    """

    FOOTNOTE = "footnote"
    ENDNOTE = "endnote"


class Footnote(BaseModel):
    """A footnote or endnote whose marker-to-body relationship was
    confidently detected: an inline marker in body text, linked by
    number to a matching note body.

    ``number`` is the note's printed number, parsed from its marker -
    not a globally unique identifier (footnote numbering conventionally
    resets per page, so the same number can legitimately belong to
    different Footnote instances on different pages). ``marker`` is the
    literal marker substring as found inline (e.g. a Unicode superscript
    "¹"), kept verbatim for exact in-place substitution at render
    time. ``anchor_text`` is the exact source line the marker was found
    within, and ``body_source_text`` is the exact source line the note
    body was found within (marker prefix and all) - both use the same
    exact-line-matching technique src/markdown/markdown_builder.py
    already uses for headings, letting a renderer both substitute
    markdown footnote syntax at the marker's position and suppress the
    body's original raw line (replaced by a proper footnote definition)
    without re-deriving position from bbox.

    ``anchor_offset`` (feature_005/bug_005) is the marker's exact
    character offset within ``anchor_text``, when known. Added because
    a plain-digit marker (bug_005's span-based detection signal) is a
    common substring that can occur elsewhere in the same line by pure
    coincidence (a year, a page reference, an unrelated count) - unlike
    the literal Unicode superscript glyph this model originally assumed
    was rare enough to find-and-replace blindly. ``None`` for any
    Footnote built without this offset known (e.g. existing test
    fixtures predating this field); callers must treat its absence as
    "fall back to substring replacement," never assume the marker is at
    position 0.

    ``body_continuation_source_texts`` (continuation-line absorption
    fix): a real note body is often wrapped across more than one
    physical PDF line - ``body`` and ``body_source_text`` alone only
    ever captured the first such line, silently truncating every
    multi-line note and leaking its remaining lines into ordinary body
    text (confirmed against the Brinkman regression PDF, where this cut
    every endnote off mid-sentence). This list holds the exact source
    line of every additional line src/footnotes/footnote_detector.py
    confidently absorbed into this same note's body, in document order,
    so a renderer can suppress all of them - not just the first line -
    the same exact-line-matching technique ``body_source_text`` already
    uses. Empty for a single-line note (the common case) or for any
    Footnote built without this field known (e.g. existing test
    fixtures predating it).
    """

    note_type: NoteType
    number: int = Field(..., ge=0)
    marker: str = Field(..., min_length=1)
    anchor_page_number: int = Field(..., ge=1)
    anchor_text: str = Field(..., min_length=1)
    anchor_offset: Optional[int] = Field(default=None, ge=0)
    body: str = Field(..., min_length=1)
    body_page_number: int = Field(..., ge=1)
    body_source_text: str = Field(..., min_length=1)
    body_continuation_source_texts: List[str] = Field(default_factory=list)
    footnote_id: Optional[str] = None  # assigned by footnote_detector; "p{page}-{number}"
    review_status: FootnoteReviewStatus = FootnoteReviewStatus.DETECTED
    reviewer_note: Optional[str] = None
    # Universal lifecycle tracking (see src/models/lifecycle.py).
    lifecycle_status: ObjectLifecycleStatus = ObjectLifecycleStatus.DETECTED
    # Import provenance: "rawrs" (span-based detector), "mathpix" (imported),
    # "rawrs_recovery" (RAWRS found it; provider missed it).
    source: str = "rawrs"
