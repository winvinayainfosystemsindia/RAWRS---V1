"""Bounding box model for RAWRS layout/structure metadata.

See docs/ARCHITECTURE.md ("Structure Detection") for the pipeline stage
this model exists to support.
"""

from pydantic import BaseModel


class BoundingBox(BaseModel):
    """An axis-aligned bounding box in PDF page coordinates (points,
    origin top-left - PyMuPDF's native coordinate system, read directly
    from it with no transformation).

    A plain value object - no behavior beyond field types. Composed
    into TextBlock (see src/models/text_block.py) rather than standing
    alone as a top-level Document entity, the same composition pattern
    Figure already uses inside Image.
    """

    x0: float
    y0: float
    x1: float
    y1: float
