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

from pydantic import Field

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
    ``source_orders`` is the page-scoped ``TextBlock.order`` value of
    every contributing line on the RAWRS-native path, in order - back-
    reference provenance only. Empty on the Mathpix path; see
    ``source_line`` for that path's own ordering key.
    ``document_order``/``source_line`` are optional (unlike Heading's
    required document_order) since the RAWRS-native construction path
    has no document-wide paragraph numbering to give them.
    """

    object_type: str = "paragraph"
    page_number: int = Field(..., ge=1)
    text: str = Field(..., min_length=1)
    bbox: Optional[BoundingBox] = None
    source_orders: List[int] = Field(default_factory=list)
    document_order: Optional[int] = None
    source_line: Optional[int] = None
