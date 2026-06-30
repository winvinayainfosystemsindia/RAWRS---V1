"""Paragraph model for RAWRS paragraph reconstruction.

See src/structure/paragraph_grouper.py for the function that produces
these from TextBlock (Phase H) data, and
notes/paragraph_reconstruction_design_review.md (Option B, in
samples/regressions/bug_001_brinkman_word_splitting/notes_md/) for the
design this implements.

Deliberately transient: unlike TextBlock, Paragraph is not stored on
Document. It is built fresh inside src/markdown/markdown_builder.py for
one run of consecutive plain-body TextBlocks at a time and consumed
immediately - there is no document-wide "all paragraphs" list, since
nothing outside markdown rendering needs one yet.
"""

from typing import List

from pydantic import BaseModel, Field

from src.models.bounding_box import BoundingBox


class Paragraph(BaseModel):
    """One reconstructed paragraph: one or more TextBlock lines joined
    into continuous prose.

    ``text`` is the fully joined paragraph text (line-wrap hyphens
    repaired, same-baseline PyMuPDF line-segmentation fragments merged
    with a single space - see src/structure/paragraph_grouper.py).
    ``bbox`` is the union of every contributing TextBlock's bbox, kept
    for provenance/future consumers (e.g. alt-text "nearby paragraph"
    context) even though nothing currently reads it.
    ``source_orders`` is the page-scoped ``TextBlock.order`` value of
    every contributing line, in order - back-reference provenance only,
    mirroring how TextBlock itself never discards where its data came
    from.
    """

    page_number: int = Field(..., ge=1)
    text: str = Field(..., min_length=1)
    bbox: BoundingBox
    source_orders: List[int] = Field(default_factory=list)
