"""Span model for RAWRS Structure Detection (Phase H / feature_005).

See docs/DECISIONS_LOG.md Part 8 for the design review this implements
(Option A: an additive Span model embedded in TextBlock, not a parallel
Document.spans list or a separate pipeline stage), and bug_005
(docs/KNOWN_LIMITATIONS.md, docs/PHASE_STATUS.md "Phase K") for the
confirmed footnote-detection gap this exists to close.

TextBlock (one PDF line) deliberately collapses every PyMuPDF span on
that line into a single (font_size, is_bold) scalar pair - by design,
for the column-clustering/paragraph-reconstruction needs that
granularity serves. That collapse discards exactly the signal a
footnote-marker superscript carries: a smaller size, a distinct font,
PyMuPDF's own superscript flag bit, and a raised baseline, all confined
to the one or two characters of the marker itself rather than the whole
line. Span exists to preserve that signal without changing what
TextBlock means or how any existing consumer reads it - see
TextBlock.spans's own docstring for the additive contract.
"""

from pydantic import BaseModel

from src.models.bounding_box import BoundingBox


class Span(BaseModel):
    """One PyMuPDF text span - a maximal run of characters on a line
    sharing one font/size/flags/baseline, exactly as PyMuPDF segments it.

    Deliberately a faithful record of what PyMuPDF reported, not an
    interpretation of it: ``font_flags`` is the raw bitmask (PyMuPDF's
    own encoding - SUPERSCRIPT=1, ITALIC=2, SERIFED=4, MONOSPACED=8,
    BOLD=16, confirmed exhaustively against the installed PyMuPDF
    version during the feature_005 design review), not pre-decoded into
    named booleans. Callers that need "is this superscript" test
    ``span.font_flags & 1`` themselves rather than have that
    interpretation baked into the stored model - the same reasoning
    already applied to TextBlock.is_bold's own majority-vote threshold,
    which lives in src/structure/layout_signals.py, not in a model.

    ``baseline_y`` is the span's own measured PyMuPDF origin
    y-coordinate (``span["origin"][1]``), not a derived offset from the
    line's baseline - keeping this a faithful record rather than an
    interpretation means a future consumer needing a different
    threshold/comparison than today's footnote_detector.py doesn't need
    a model change to get it.

    PyMuPDF has no dedicated subscript flag bit - a future subscript
    consumer would need to infer it from ``baseline_y``/``font_size``
    relative to the line's other spans, the same way ``font_flags``
    must be decoded by the caller rather than the model.
    """

    text: str
    font_name: str
    font_size: float
    font_flags: int
    baseline_y: float
    bbox: BoundingBox
