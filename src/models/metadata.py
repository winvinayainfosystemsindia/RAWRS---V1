"""Metadata model for RAWRS document processing.

See docs/PHASE1_SCOPE.md (Metadata Capture) for the fields this model
exists to support.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Metadata(BaseModel):
    """Descriptive metadata captured about a processed document.

    A passive data container with explicit fields (approved architecture
    decision #6): values such as ``page_count`` and ``image_count`` are
    set directly by the pipeline stage that finalizes processing rather
    than computed from the Document tree, so the source of truth is
    traceable to a single, explicit assignment.
    """

    filename: str = Field(..., min_length=1)
    page_count: int = Field(default=0, ge=0)
    image_count: int = Field(default=0, ge=0)
    processing_date: Optional[datetime] = None
    processing_duration_seconds: Optional[float] = Field(default=None, ge=0)
    # Accessibility properties (FEATURE_016F) — set by reviewer and written to DOCX
    language: Optional[str] = None    # IETF BCP 47, e.g. "en-US"
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
