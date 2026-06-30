"""Image model for RAWRS image/figure extraction.

See docs/VALIDATION_RULES.md (Image Validation) for the checks this
model exists to support: extraction failures, missing image files,
duplicate extractions, and missing figure references.
"""

from typing import Optional

from pydantic import BaseModel, Field

from src.models.bounding_box import BoundingBox
from src.models.figure import Figure
from src.models.lifecycle import ObjectLifecycleStatus


class Image(BaseModel):
    """An image or figure extracted from a PDF page.

    ``figure`` is populated when the image has an associated figure
    label/caption (see approved architecture decision #4: Figure is
    composed within Image rather than a sibling top-level entity).

    ``bbox`` (added Phase F.1) is the image's position on its page, in
    the same PyMuPDF page-coordinate system as
    src/models/text_block.py's TextBlock.bbox - this is what makes
    proximity-based figure/caption detection (Phase F.2) possible:
    before this field existed, src/images/image_extractor.py computed
    this exact data internally (for its background-image filter) and
    discarded it, the same discard pattern Phase H's audit found and
    fixed for text. Optional and defaulted to None so existing Image
    construction sites (e.g. a synthetic Image built directly in a
    test) remain valid unchanged.
    """

    image_id: str = Field(..., min_length=1)
    page_number: int = Field(..., ge=1)
    file_path: str = Field(..., min_length=1)
    width: Optional[int] = Field(default=None, ge=0)
    height: Optional[int] = Field(default=None, ge=0)
    bbox: Optional[BoundingBox] = None
    figure: Optional[Figure] = None
    extraction_failed: bool = False
    embedded_in_docx: Optional[bool] = None
    # Universal lifecycle tracking (see src/models/lifecycle.py).
    lifecycle_status: ObjectLifecycleStatus = ObjectLifecycleStatus.DETECTED
