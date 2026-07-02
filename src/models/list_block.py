"""ListBlock model — a genuine semantic list, not a paragraph.

Fixes the exact defect named in the brief: on the Mathpix import path,
consecutive ``P2BlockType.LIST_ITEM`` blocks were grouped into
``_PARA_TYPES`` (src/mathpix/ingestor.py) and rendered as flat paragraph
text, discarding list structure entirely. ``ListBlock`` is the canonical
model that structure survives into — the first new object type built
directly on ``SemanticObject`` (src/models/semantic_object.py) rather than
migrated onto it after the fact, and the first new asset type registered
with the cross-source verification engine alongside Heading (see
src/verification/lists.py::ListVerifier).
"""

from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field

from src.models.semantic_object import SemanticObject


class ListType(str, Enum):
    BULLET = "bullet"
    NUMBERED = "numbered"


class ListItem(BaseModel):
    text: str = Field(..., min_length=1)
    level: int = Field(default=0, ge=0)


class ListBlock(SemanticObject):
    """A single detected list, either imported from Mathpix's own list
    markup or recovered from PDF geometry (bullet-glyph/indent clustering
    — see src/lists/list_detector.py::detect_lists_from_pdf) when Mathpix
    flattened it to plain paragraphs.

    ``document_order`` mirrors Heading's field of the same name — the
    position among all lists in document-wide order, since two lists on
    the same page must still render in a stable, deterministic sequence.
    """

    object_type: str = "list"
    list_type: ListType
    items: List[ListItem] = Field(default_factory=list)
    page_number: int = Field(..., ge=1)
    document_order: int = Field(..., ge=0)
