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
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

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
    # FEATURE_020 — see Heading.source_line's docstring (src/models/heading.py).
    source_line: Optional[int] = None

    @model_validator(mode="after")
    def _backfill_semantic_object_id(self) -> "ListBlock":
        """Give the list the stable identity its siblings already have.

        P4c-4′. ``ListBlock`` was the last populated object type with no
        ``id``, and the consequences were silent: ``build_content_stream``
        drops any node whose ``object_id`` is falsy, so ``ContentKind.LIST``
        had never once been emitted — 48 lists across the benchmark corpus,
        0 nodes — and ``markdown_builder._render_lists`` wrote the literal
        anchor ``<!-- list-id: None -->`` 48 times.

        **Derived from source, not from position**, for the reason
        ``Paragraph._backfill_semantic_object_id`` states at length: the
        sibling convention ``{type}-{document_order}`` is a list counter
        (``order += 1`` per flushed run), so inserting or dropping an
        earlier list would rename every list after it, and a correction
        recorded against the old name would then apply to someone else's
        list.

        ``source_line`` is the basis, and it is unique per list by
        construction: ``_group_list_items_to_lists`` (src/mathpix/ingestor.py)
        records the line of the run's *first* item, and two runs cannot begin
        on the same line.

        A ``ListBlock`` with no ``source_line`` keeps ``id=None`` rather than
        being given an unstable one — the same honest answer Paragraph gives.
        That is every list from ``detect_lists_from_pdf``
        (src/lists/list_detector.py), which builds from PDF geometry and has
        no source-document coordinate to name; those objects are candidates
        for ``ListVerifier`` and are not placed in ``Document.lists``, so
        they are not addressable and do not become nodes.
        """
        if self.id is None and self.source_line is not None:
            self.id = f"list-line-{self.source_line}"
        return self
