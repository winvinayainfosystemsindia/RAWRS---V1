"""Resolve the document's cross-object relationships, once.

Not a graph subsystem. This is the step that stamps the *edges* other
stages already imply but never wrote down, using the vocabulary the
projection architecture review settled on: typed, directional, id-based,
and added one edge at a time as something actually needs it. Traversal
stays an implementation concern (see src/structure/content_stream.py);
nothing here builds or stores an index, and nothing here is required in
order to read a Document.

Why a stage rather than a detector's own job
--------------------------------------------
An edge can only be resolved once both endpoints exist. Tables are
detected in Stage 3, images in Stage 4, headings in Stage 5 - so
"which body lines does this table already contain?" is not answerable
inside table extraction, which is exactly why the renderer ended up
answering it instead, at render time, once per output format.

``Heading.source_block_id`` is deliberately NOT resolved here: the
heading detector knows the answer while it reads the line, and
recovering it afterwards would mean matching text again - reintroducing
the very defect this change removes. An edge belongs wherever it is
known, not wherever it is convenient.

Behaviour
---------
Additive and idempotent. Every edge this writes was previously
recomputed by a consumer, from the same inputs, under the same rules -
so linking a document changes no output; it changes only where the
answer lives. A Document that never ran this step keeps whatever
fallback its consumers already had.
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.models.bounding_box import BoundingBox
from src.models.table import Table
from src.models.text_block import TextBlock


def link_document(document: Any) -> Any:
    """Resolve every cross-object relationship this document can support.

    Mutates and returns the same Document, matching the convention every
    other pipeline stage uses (``detect_structure``, ``detect_headings``).
    """
    blocks = getattr(document, "blocks", []) or []
    _link_table_blocks(getattr(document, "tables", []) or [], blocks)
    _link_image_anchors(getattr(document, "images", []) or [], blocks)
    return document


def _link_table_blocks(tables: List[Table], blocks: List[TextBlock]) -> None:
    """Record which body lines each table already contains.

    A PyMuPDF-detected table's bbox covers its area of the page, so every
    TextBlock overlapping it came from a cell and must not also render as
    prose - otherwise cell text appears twice, once as body lines and once
    inside the rendered table. That was true before this function existed;
    the geometry is unchanged, lifted verbatim from
    markdown_builder._table_suppressed_blocks. What changes is that the
    answer is now a relationship on the Table (``source_block_ids``)
    instead of a set of list indices valid only for the one page-blocks
    list that produced them, recomputed by every projection that needs it.

    Tables with no bbox (manually created, or Mathpix-supplied) contribute
    nothing, exactly as before.
    """
    if not tables or not blocks:
        return

    blocks_by_page: Dict[int, List[TextBlock]] = {}
    for block in blocks:
        blocks_by_page.setdefault(block.page_number, []).append(block)

    for table in tables:
        if table.bbox is None:
            continue
        table.source_block_ids = overlapping_block_ids(
            table, blocks_by_page.get(table.page_number, [])
        )


def overlapping_block_ids(table: Table, page_blocks: List[TextBlock]) -> List[str]:
    """The block ids a table's own bbox covers, computed from geometry.

    Public because a projection handed an *unlinked* Document (a direct
    ``build_markdown()`` call, a fixture) still needs the answer, and the
    one thing it must not do is keep a second copy of this rule. The
    linked path stores the result on the Table; the unlinked path asks the
    same function. One implementation either way.
    """
    if table.bbox is None:
        return []
    return [
        block.block_id
        for block in page_blocks
        if block.bbox is not None and _overlaps(block.bbox, table.bbox)
    ]


def _overlaps(first: BoundingBox, second: BoundingBox) -> bool:
    """Rectangles intersect when neither lies wholly outside the other on
    either axis. Touching edges do not count as overlap."""
    return (
        first.x0 < second.x1
        and first.x1 > second.x0
        and first.y0 < second.y1
        and first.y1 > second.y0
    )


def _link_image_anchors(images: List[Any], blocks: List[TextBlock]) -> None:
    """Give every image a place in reading order.

    Until this existed, ``Image`` was the only ordered object type with no
    ordering field, so every consumer put images after a page's body text -
    not because that was right, but because the model could not say anything
    else. ``_render_images()`` said so in its own comment; ``build_content_stream``
    inherited the same approximation.

    The anchor is the last line whose bottom edge sits at or above the image's
    top: the block the image follows. ``None`` is a real answer - the image
    precedes all body text on its page - not a missing one, so a consumer must
    place it first rather than last.

    ``document_order`` is assigned across the whole document in (page, anchor,
    vertical position) order, matching Heading.document_order's convention.
    Ties break on the image's own list position, which keeps the result stable
    for two images sharing a bbox.

    Images with no bbox (Mathpix-path, or an extraction that failed before
    geometry was known) get no anchor and no order, and consumers fall back to
    their previous placement.
    """
    if not images:
        return

    blocks_by_page: Dict[int, List[TextBlock]] = {}
    for block in blocks:
        blocks_by_page.setdefault(block.page_number, []).append(block)
    for page_blocks in blocks_by_page.values():
        page_blocks.sort(
            key=lambda b: b.corrected_order if b.corrected_order is not None else b.order
        )

    placed: List[tuple] = []
    for index, image in enumerate(images):
        image.source_block_id = None
        image.document_order = None
        if image.bbox is None:
            continue
        anchor, anchor_position = None, -1
        for position, block in enumerate(blocks_by_page.get(image.page_number, [])):
            if block.bbox is not None and block.bbox.y1 <= image.bbox.y0:
                anchor, anchor_position = block.block_id, position
        image.source_block_id = anchor
        placed.append((image.page_number, anchor_position, image.bbox.y0, index, image))

    placed.sort(key=lambda item: item[:4])
    for order, item in enumerate(placed):
        item[-1].document_order = order
