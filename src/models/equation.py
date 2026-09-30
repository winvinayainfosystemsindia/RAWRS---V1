"""Equation model — one mathematical or chemical expression (docs/EQUATION_DESIGN.md §2).

A display equation sits between paragraphs; an inline one is anchored into a
``Paragraph`` the way a note marker is (``Footnote.anchor_offset``): the
paragraph's text holds a readable Unicode rendering of the span and
``anchor_offset``/``anchor_length`` say where. The LaTeX lives here, never in
``Paragraph.text`` — Markdown and DOCX are projections that spell it.

``latex_source`` is what the source said and never changes; ``latex`` is what
is converted and what a reviewer edits, so a revert can always restore the
source. ``status`` is the confident-vs-flag boundary: CONVERTED will become a
native Word equation, FLAGGED goes to a human, PLAIN is a simple expression
(or not maths at all) that belongs outside an equation box (Eq 7).
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import Field, model_validator

from src.models.semantic_object import ProvenanceSource, SemanticObject


class EquationStatus(str, Enum):
    CONVERTED = "converted"
    FLAGGED = "flagged"
    PLAIN = "plain"


class Equation(SemanticObject):
    object_type: str = "equation"
    page_number: int = Field(..., ge=1)
    document_order: int = Field(..., ge=0)
    display: bool = True
    latex_source: str = Field(..., min_length=1)
    latex: str = ""
    number: Optional[str] = None
    label: Optional[str] = None
    # The source environment numbers its equations (equation, align, gather).
    # Kept so a number a reviewer clears is flagged as missing again.
    numbered_environment: bool = False
    status: EquationStatus = EquationStatus.CONVERTED
    flag_reasons: List[str] = Field(default_factory=list)
    # Reviewer-written description for a complex or flagged equation. Never
    # generated: the checklist asks for a description, not a guess.
    description: Optional[str] = None
    # Readable Unicode rendering (inline: what Paragraph.text holds at the
    # anchor; PLAIN: the text that replaces the equation box).
    text: str = ""
    # Text that joined the equation in the box and was moved out (Eq 5).
    before_text: str = ""
    after_text: str = ""
    source_line: Optional[int] = None
    # Position among the rows of one source block, or among the inline spans
    # of one paragraph — part of the id so rows of an align never collide.
    row: int = 0
    paragraph_id: Optional[str] = None
    anchor_offset: Optional[int] = None
    anchor_length: Optional[int] = None
    provenance: ProvenanceSource = ProvenanceSource.MATHPIX

    @model_validator(mode="after")
    def _backfill(self) -> "Equation":
        if not self.latex:
            self.latex = self.latex_source
        if self.id is None:
            self.id = (
                f"equation-line-{self.source_line}-{self.row}"
                if self.source_line is not None
                else f"equation-{self.document_order}"
            )
        return self
