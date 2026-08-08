"""Build one reading-order traversal from the semantic document.

Pure and derived: ``build_content_stream(document)`` reads the document's
objects and returns a fresh ``ContentStream``. Nothing is stored, nothing is
mutated, and no production code consumes it yet — P1 is additive by
contract, so rendering behaviour is unchanged.

What this replaces, once P3/P4 land: both projections currently rebuild
reading order for themselves. ``markdown_builder`` walks a page's text lines
in lockstep with ``document.blocks``, matching headings by text equality and
suppressing others through four text-keyed sets; ``docx_generator`` then
re-derives structure a second time by parsing the markdown that walk
produced. That is one semantic decision — what order the content is in —
made twice inside two output formats. It belongs to the document.

**Fidelity status.** This traversal is derived from what the model can
state today: page markers, headings, body lines, lists, tables, images and
note definitions, ordered per page. P2 closed the two gaps that made it an
ordering rather than a rendering instruction — paragraph grouping now lives
in ``src/structure/paragraph_assembly.py`` and note labelling on
``Footnote.label`` — so what remains for P3 is to emit ``PARAGRAPH`` nodes
instead of ``BODY_LINE`` ones and have the projections read them.

P3 is gated on rendering from this stream producing byte-identical
markdown, which is what will prove the ordering correct rather than merely
plausible.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.models.content_stream import ContentKind, ContentNode, ContentStream


def _page_numbers(document: Any) -> List[int]:
    pages = [page.page_number for page in getattr(document, "pages", []) or []]
    if pages:
        return sorted(pages)
    # A fixture Document with objects but no Page rows still has a real
    # traversal; fall back to whatever pages the objects themselves name.
    seen = {block.page_number for block in getattr(document, "blocks", []) or []}
    seen |= {h.page_number for h in getattr(document, "headings", []) or []}
    return sorted(seen)


def _heading_anchor_orders(document: Any, page_number: int) -> Dict[str, int]:
    """Place each content heading at the block it was detected from.

    P2 made this a lookup. ``Heading.source_block_id`` is the recorded
    relationship, written by the detector at the moment it read the line, so
    the anchor is simply that block's position — no matching, no
    first-unconsumed-wins tie-breaking, and no way for two headings sharing
    text to be placed at each other's lines.

    The text-equality fallback below is what this function used to do
    entirely, kept for headings with no recorded block: Mathpix-path
    headings (ordered by ``source_line`` instead), reviewer-created ones,
    and fixtures. A heading that neither route resolves gets no anchor and
    is ordered after the page's body — see ``build_content_stream``.
    """
    blocks = [b for b in (getattr(document, "blocks", []) or []) if b.page_number == page_number]
    by_block_id = {b.block_id: b.order for b in blocks}
    consumed: set = set()
    anchors: Dict[str, int] = {}
    unresolved: List[Any] = []

    for heading in getattr(document, "headings", []) or []:
        if heading.page_number != page_number or heading.is_page_marker:
            continue
        order = by_block_id.get(heading.source_block_id) if heading.source_block_id else None
        if order is None:
            unresolved.append(heading)
            continue
        anchors[str(heading.id)] = order
        consumed.add(order)

    # Recorded anchors are claimed first, so a fallback text match can never
    # steal the block another heading positively identified as its own.
    for heading in unresolved:
        for block in blocks:
            if block.order in consumed or block.text != heading.text:
                continue
            anchors[str(heading.id)] = block.order
            consumed.add(block.order)
            break
    return anchors


def _front_matter_items(document: Any) -> List[Any]:
    """The document's front-matter items, in recorded order (L5'a).

    Empty for a FrontMatter that predates ``items`` or that a provider
    built without them - see ``_placed_front_matter`` for what that costs.
    """
    front_matter = getattr(document, "front_matter", None)
    items = list(getattr(front_matter, "items", []) or []) if front_matter else []
    return sorted(items, key=lambda item: item.document_order)


def _placed_front_matter(document: Any, page_number: int) -> List[tuple]:
    """(block order, item) for every front-matter item this page can place.

    Placement is by ``FrontMatterItem.source_block_id`` and nothing else.
    No text is matched, no first-unconsumed tie-break is applied, and page
    position is not consulted - the whole point of L5'a is that the item
    already records where it came from, the same way ``Heading`` and
    ``Image`` do.

    An item whose ``source_block_id`` is absent or names no block on this
    page is not placed. That is not a silent drop: it is the honest answer
    for front matter a provider supplied with no position in the PDF at
    all (src/mathpix/ingestor.py), and the Markdown projection's declared
    limitation covers what happens to it instead.
    """
    blocks = {
        block.block_id: block
        for block in (getattr(document, "blocks", []) or [])
        if block.page_number == page_number
    }
    placed = []
    for item in _front_matter_items(document):
        block = blocks.get(item.source_block_id) if item.source_block_id else None
        if block is None:
            continue
        order = block.corrected_order if block.corrected_order is not None else block.order
        placed.append((order, item))
    return placed


def _is_endnote(note: Any) -> bool:
    note_type = getattr(note, "note_type", None)
    return note_type is not None and str(note_type).upper().endswith("ENDNOTE")


def build_content_stream(document: Any) -> ContentStream:
    """Derive the document's reading-order traversal.

    Per page: the page marker, then headings and images interleaved with
    body lines by the block each was detected from or follows, then lists
    and tables, then the note definitions anchored to that page. Endnotes
    follow the last page, matching the convention that they are detached
    from any one page.

    Suppressed blocks are omitted: a suppression is an applied decision
    (``TextBlock.suppressed``, set only through the correction rail), so the
    line is genuinely not part of the document's content until the decision
    is reverted.
    """
    stream = ContentStream()
    order = 0

    def emit(object_id: Optional[str], kind: ContentKind, page_number: int) -> None:
        nonlocal order
        if not object_id:
            return
        stream.nodes.append(
            ContentNode(
                object_id=str(object_id), kind=kind, page_number=page_number, order=order
            )
        )
        order += 1

    headings = getattr(document, "headings", []) or []
    blocks = getattr(document, "blocks", []) or []
    footnotes = getattr(document, "footnotes", []) or []
    page_numbers = _page_numbers(document)

    for page_number in page_numbers:
        marker = next(
            (h for h in headings if h.page_number == page_number and h.is_page_marker), None
        )
        if marker is not None:
            emit(marker.id, ContentKind.PAGE_MARKER, page_number)

        anchors = _heading_anchor_orders(document, page_number)
        entries: List[tuple] = []  # (sort position, tie-break, kind, object id)

        # L5'a: front matter sits at the block it was read from, and that
        # block is not also a body line — the same line cannot be both, and
        # emitting both is exactly the duplication a traversal exists to
        # prevent. Tie-break 0 keeps it ahead of anything sharing its
        # position, matching how an anchored heading precedes its own line.
        front_matter = _placed_front_matter(document, page_number)
        front_matter_blocks = {
            item.source_block_id for _, item in front_matter if item.source_block_id
        }
        for position, item in front_matter:
            entries.append((position, 0, ContentKind.FRONT_MATTER, str(item.id)))

        for block in blocks:
            if block.page_number != page_number or block.suppressed:
                continue
            if block.block_id in front_matter_blocks:
                continue
            position = block.corrected_order if block.corrected_order is not None else block.order
            entries.append((position, 1, ContentKind.BODY_LINE, block.block_id))
        for heading in headings:
            if heading.page_number != page_number or heading.is_page_marker:
                continue
            anchor = anchors.get(str(heading.id))
            # Unanchored headings sort after every body line on the page
            # rather than being dropped; tie-break 0 puts an anchored
            # heading ahead of the body line it was detected from.
            position = anchor if anchor is not None else len(blocks) + heading.document_order
            entries.append((position, 0, ContentKind.HEADING, str(heading.id)))

        # Images sit at the block they follow (P-IMG). An unlinked Document —
        # Mathpix, a fixture, anything that never ran Stage 5c — has no anchor
        # to read, so those images keep the historical after-the-body slot.
        page_end_images: List[str] = []
        block_orders = {
            b.block_id: (b.corrected_order if b.corrected_order is not None else b.order)
            for b in blocks
            if b.page_number == page_number
        }
        for image in sorted(
            (i for i in (getattr(document, "images", []) or []) if i.page_number == page_number),
            key=lambda i: i.document_order if i.document_order is not None else 10**9,
        ):
            image_id = str(getattr(image, "image_id", None) or image.id)
            if image.document_order is None:
                page_end_images.append(image_id)
            elif image.source_block_id is None:
                # A real position, not a missing one: the image precedes every
                # body line on its page.
                entries.append((-1, 2, ContentKind.IMAGE, image_id))
            elif image.source_block_id in block_orders:
                # Tie-break 2: after the body line it follows, never before it.
                entries.append(
                    (block_orders[image.source_block_id], 2, ContentKind.IMAGE, image_id)
                )
            else:
                page_end_images.append(image_id)  # anchor block suppressed or gone

        for _, _, kind, object_id in sorted(entries, key=lambda e: (e[0], e[1])):
            emit(object_id, kind, page_number)

        for lst in getattr(document, "lists", []) or []:
            if lst.page_number == page_number:
                emit(lst.id, ContentKind.LIST, page_number)
        for table in getattr(document, "tables", []) or []:
            if table.page_number == page_number:
                emit(getattr(table, "table_id", None), ContentKind.TABLE, page_number)
        for image_id in page_end_images:
            emit(image_id, ContentKind.IMAGE, page_number)

        for note in footnotes:
            if _is_endnote(note):
                continue
            if getattr(note, "anchor_page_number", None) == page_number:
                emit(getattr(note, "footnote_id", None), ContentKind.NOTE_DEFINITION, page_number)

    # Endnotes: the same objects as footnotes, placed at the document end
    # instead of a page bottom. One graph, two linearizations — the case
    # that makes clear this stream is a traversal and not the document.
    last_page = page_numbers[-1] if page_numbers else 1
    for note in footnotes:
        if _is_endnote(note):
            emit(getattr(note, "footnote_id", None), ContentKind.NOTE_DEFINITION, last_page)

    return stream
