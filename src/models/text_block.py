"""TextBlock model for RAWRS Structure Detection (Phase H).

See docs/ARCHITECTURE.md ("Structure Detection") for the pipeline stage
that populates this model (src/structure/structure_detector.py), and
BENCHMARK_GAP_ANALYSIS.md §4.2 / BENCHMARK_RECONCILIATION_AND_PHASE1_PLAN.md
§3 for why this model exists now: bbox and font-layout data were
already being computed transiently inside
src/headings/heading_detector.py (and, separately, image bbox data
inside src/images/image_extractor.py) and discarded immediately after
use. TextBlock is the first place that signal is captured and kept, so
later phases (reading order reconstruction, multi-column detection,
footnote detection - none of which this model or its producing stage
implement) have a foundation to build on instead of recomputing it.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from src.models.bounding_box import BoundingBox
from src.models.span import Span


class TextBlock(BaseModel):
    """One line of text on a page, with its layout signal and position.

    Granularity is PyMuPDF's native text *line* (not its coarser
    "block" unit) - deliberately matching the granularity
    src/headings/heading_detector.py's own layout signal already
    operates at, and the granularity later phases need (column
    clustering, footnote font-size-drop detection both need per-line,
    not per-paragraph, position/size data).

    ``order`` is this block's position among the other blocks on its
    own page, in the order PyMuPDF emitted it while reading the page's
    text - the order text was found in, not a validated or corrected
    reading order. Correcting/reordering this sequence, or relating
    order across pages, is explicitly out of scope for Structure
    Detection (see src/structure/structure_detector.py); it is recorded
    here as the input a later phase (reading order reconstruction)
    will read, not interpreted.

    ``source_block_index`` is the index of the PyMuPDF
    ``page.get_text("dict")["blocks"]`` entry this line came from
    (page-scoped, like ``order``) - PyMuPDF's own coarser grouping,
    distinct from this model's own per-line granularity (see class
    docstring above). Optional/``None`` for any TextBlock built outside
    src/structure/structure_detector.py's real extraction path (e.g.
    existing test fixtures predating this field), so its absence must
    always be handled as "unknown," never assumed to be a real block
    boundary. Added for src/structure/paragraph_grouper.py's paragraph
    reconstruction (consumed by src/markdown/markdown_builder.py) -
    PyMuPDF's own block segmentation is a reasonable first approximation
    of "lines belonging to one paragraph," refined further there by a
    vertical-gap fallback for the cases where it isn't.

    ``spans`` (feature_005, see src/models/span.py) is this line's
    PyMuPDF spans, preserved individually instead of being collapsed
    into ``font_size``/``is_bold``'s line-level max/majority-vote
    summary - additive only, per the approved design review
    (docs/DECISIONS_LOG.md Part 8): every existing field above keeps its
    exact prior meaning, and ``spans`` defaults to an empty list for any
    TextBlock built outside src/structure/structure_detector.py's real
    extraction path (e.g. existing test fixtures predating this field),
    so its absence must always be handled as "no span data available,"
    never assumed to mean the line had no text. ``font_size``/``is_bold``
    are not derived from ``spans`` at construction time (no behavior
    change to either field); a consumer that needs span-level fidelity
    reads ``spans`` directly instead.
    """

    page_number: int = Field(..., ge=1)
    text: str = Field(..., min_length=1)
    bbox: BoundingBox
    order: int = Field(..., ge=0)
    font_size: Optional[float] = None
    is_bold: Optional[bool] = None
    source_block_index: Optional[int] = None
    spans: List[Span] = Field(default_factory=list)
    # 016B reading order correction. None = use `order` (PyMuPDF extraction
    # order). Set to an integer by the reading-order workspace when a human
    # manually reorders the page's blocks. markdown_builder.py sorts by
    # this field when set, falling back to `order` otherwise.
    corrected_order: Optional[int] = None
