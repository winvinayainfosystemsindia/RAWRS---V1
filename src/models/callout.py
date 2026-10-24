"""Callout model — a boxed aside (Case Study, Thinking Point, Key Ideas,
Summary, Activity, ...), not an ordinary heading.

Closes the gap the forensic audit (RAWRS_forensic_audit.md, DEF-04) named
directly: RAWRS's semantic vocabulary stopped at Heading/Paragraph/
ListBlock/Table/Figure/Footnote, so a textbook's boxed aside could only
ever become a heading immediately followed by ordinary body content — no
grouping, no role, no way for a screen reader to be told "this is a
self-contained aside, exit to resume the main narrative," and no way for
DOCX generation to draw a border or shade a background.

References its anchoring ``Heading`` by id rather than embedding a copy
of the box's body content — the same "don't create duplicate data
structures" rule Heading itself already follows for page content (see
Heading's own docstring): the body text already lives in Page.cleaned_text
(Mathpix path) or Document.blocks (RAWRS-native path); duplicating it here
would risk the exact double-render bug class
src/mathpix/ingestor.py::_assign_page_text() was written to avoid for
headings and list items. A box found on a scanned page
(src/ocr/scan_structure.py) also carries its real extent (page and line
range); those boxes are rendered - fenced in the markdown, a one-cell table
in the DOCX. A heading-anchored callout from a Mathpix import has no extent
yet, so its rendering is still the separate piece of work it was.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field, model_validator

from src.models.semantic_object import SemanticObject


class Callout(SemanticObject):
    """One detected boxed aside, anchored to the Heading that carries its
    label (e.g. "Case study 11.2", "Thinking point 10.1").

    ``callout_type`` is a stable, open string (not an Enum) — new box
    vocabularies are a near-certainty across other textbook series/
    publishers, and an open string lets src/mathpix/mmd_parser.py's
    label-pattern classifier grow without a schema migration. Known
    values today: "case_study", "thinking_point", "key_ideas",
    "summary", "activity".

    ``label`` is the literal heading text that triggered classification
    (e.g. "Case study 11.2") — kept distinct from the anchoring Heading's
    own ``text`` field so a reviewer edit to one doesn't silently drift
    from the other; they start identical and are expected to.
    """

    object_type: str = "callout"
    callout_type: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    heading_id: Optional[str] = None
    document_order: int = Field(..., ge=0)
    # FEATURE_020 — see Heading.source_line's docstring (src/models/heading.py).
    source_line: Optional[int] = None
    # A box found on a scanned page (src/ocr/scan_structure.py) has a real
    # extent, not "up to the next heading": the page it sits on and the
    # first/last line it covers, counted over the page text's non-blank lines
    # from 0. Counted rather than quoted so a re-read that corrects a line's
    # words (src/verification/ocr_text.py) cannot detach it from its box.
    page_number: Optional[int] = Field(default=None, ge=1)
    first_line: Optional[int] = Field(default=None, ge=0)
    last_line: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _backfill_semantic_object_id(self) -> "Callout":
        if self.id is None:
            self.id = f"callout-{self.document_order}"
        return self
