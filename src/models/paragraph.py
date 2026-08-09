"""Paragraph model for RAWRS paragraph reconstruction.

See src/structure/paragraph_grouper.py for the function that produces
these from TextBlock (Phase H) data (RAWRS-native path), and
notes/paragraph_reconstruction_design_review.md (Option B, in
samples/regressions/bug_001_brinkman_word_splitting/notes_md/) for the
design this implements.

FEATURE_020: promoted from a transient, RAWRS-native-only, render-time
value onto SemanticObject and Document.paragraphs — the Mathpix path
(src/mathpix/ingestor.py::_assign_page_text()) now also emits real
Paragraph objects, alongside its existing page.cleaned_text
concatenation (kept for other readers, not replaced), giving
src/markdown/markdown_builder.py::_render_page_semantic() a real object
to sort by source_line next to headings/lists/tables/images/callouts.
The RAWRS-native path's own construction (paragraph_grouper.py) is
unchanged and still doesn't set document_order/source_line — its
renderer never needed cross-type sorting and still doesn't.
"""

from typing import List, Optional

from pydantic import Field, model_validator

from src.models.bounding_box import BoundingBox
from src.models.semantic_object import SemanticObject


class Paragraph(SemanticObject):
    """One reconstructed paragraph: one or more TextBlock lines (RAWRS-
    native) or Mathpix PARAGRAPH/ABSTRACT blocks joined into continuous
    prose.

    ``text`` is the fully joined paragraph text (line-wrap hyphens
    repaired, same-baseline PyMuPDF line-segmentation fragments merged
    with a single space - see src/structure/paragraph_grouper.py).
    ``bbox`` is the union of every contributing TextBlock's bbox on the
    RAWRS-native path; unset on the Mathpix path (no PDF geometry to
    union there).
    ``source_block_ids`` is the ``TextBlock.block_id`` of every
    contributing line on the RAWRS-native path, in order - the
    containment relationship "this paragraph is made of those lines".
    Empty on the Mathpix path (no TextBlocks contributed); see
    ``source_line`` for that path's own ordering key.

    P2 replaced the earlier ``source_orders: List[int]``, which held the
    page-scoped ``TextBlock.order`` and was therefore only meaningful to
    a caller that already knew which page it was looking at - the
    positional-key idiom the projection architecture review identified
    as one of five different ways this repository spelled the same kind
    of edge. Same relationship, expressed the way every other edge now
    is: by the target's own document-unique identity.

    ``document_order``/``source_line`` are optional (unlike Heading's
    required document_order) since the RAWRS-native construction path
    has no document-wide paragraph numbering to give them.
    """

    object_type: str = "paragraph"
    page_number: int = Field(..., ge=1)
    text: str = Field(..., min_length=1)
    bbox: Optional[BoundingBox] = None
    source_block_ids: List[str] = Field(default_factory=list)
    document_order: Optional[int] = None
    source_line: Optional[int] = None

    @model_validator(mode="after")
    def _backfill_semantic_object_id(self) -> "Paragraph":
        """Give the paragraph the stable identity its siblings already have.

        W-2a. Paragraph was the one detected object of its class with no
        ``id``: every other SemanticObject backfills one, and without it a
        paragraph cannot be the ``object_id`` of a CorrectionRecord, which
        is what a reviewer prose edit will need. Measured before this:
        950 paragraphs across the corpus, 0 addressable.

        **Derived from source, not from position.** The sibling
        convention is ``{type}-{document_order}``, and that is the one
        thing this cannot copy: ``document_order`` is a list counter
        (``paragraph_order += 1`` on the Mathpix path, unset entirely on
        the native one), so inserting or dropping an earlier paragraph
        would silently rename every paragraph after it — and a correction
        recorded against the old name would then apply to someone else's
        prose.

        Two bases, one per construction path, each already recorded and
        each unique within its document:

        * native (src/structure/paragraph_grouper.py) — the first
          contributing ``TextBlock.block_id``. Paragraph grouping
          partitions a page's lines, so a block contributes to exactly one
          paragraph and its id therefore names exactly one paragraph.
        * Mathpix (src/mathpix/ingestor.py) — ``source_line``, the block's
          own line position in the source .mmd. That is a coordinate in
          the source document, not an index into a list, so it does not
          move when a neighbouring paragraph does.

        Deterministic in both cases: re-running assembly over the same
        blocks reproduces the same id, and a round trip through
        persistence keeps whatever was stored. A Paragraph carrying
        neither basis — a hand-built fixture, never a pipeline product —
        keeps ``id=None`` rather than being given an unstable one, which
        is the honest answer and is why this is not a ``or
        document_order`` fallback chain.
        """
        if self.id is None:
            if self.source_block_ids:
                self.id = f"paragraph-{self.source_block_ids[0]}"
            elif self.source_line is not None:
                self.id = f"paragraph-line-{self.source_line}"
        return self
