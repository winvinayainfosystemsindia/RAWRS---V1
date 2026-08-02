"""Decide, once, which lines are prose and how they group into paragraphs.

P2. Paragraph grouping was a render-time decision: markdown_builder walked
a page's text, accumulated runs of "lines that were not something else",
and called ``group_into_paragraphs`` on each run - discarding the result
immediately. The DOCX projection then recovered those paragraphs by
parsing the Markdown that walk produced. One semantic decision, made
inside a format, and reconstructed by the next format down.

This module owns that decision now. ``assemble_paragraphs`` returns the
document's paragraphs; the pipeline stores them on ``Document.paragraphs``
(Stage 5c) and every projection reads them.

What "prose" means
------------------
A line is prose unless some other object already carries its content. The
exclusions below are the renderer's own former cascade, moved here
unchanged - not a new rule among them:

  * a table already contains it        (``Table.source_block_ids``)
  * a suppression decision removed it  (``TextBlock.suppressed``, L2.2)
  * a heading was detected from it     (``Heading.source_block_id``)
  * a wrapped heading absorbed it      (``Heading.continuation_block_ids``)
  * a note body, a figure caption, or the front matter absorbed it
  * RAWRS generates its own "## Endnotes" heading in place of it

The first four are answered by reading a relationship. The last two are
still resolved by matching the exact source line each detector recorded
(``Footnote.body_source_text``, ``Figure.caption_source_text``,
``FrontMatter.*_source_texts``) - because text is what those detectors
record. Deliberately not fixed here: the honest fix is for each detector
to record the block id it read, which is three detectors' worth of change.
What P2 buys is that the matching happens *once*, in the model, instead of
once per projection per render. See ``_absorbed_block_ids``.

Why not a ``TextBlock.claimed_by`` field
----------------------------------------
It was the obvious candidate, and it turns out not to be needed. The
claim's only consumer is this segmentation, and the segmentation's result
- which blocks ended up inside which Paragraph - already records the
answer in the model, by id. Adding a reverse edge as well would store the
same fact twice and give it a second place to drift, which is the defect
this whole layer exists to remove. If something later needs to ask "what
claimed this line?" rather than "is this line prose?", that is when the
edge earns its place.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Set

from src.models.paragraph import Paragraph
from src.models.text_block import TextBlock
from src.structure.paragraph_grouper import group_into_paragraphs
from src.structure.relationships import overlapping_block_ids

# The literal section-heading line src/footnotes/footnote_detector.py uses to
# find the start of an endnotes section. Defined here rather than in a
# projection because it answers a question about the *document* ("is this
# line the endnotes heading RAWRS replaces?"), and every projection needs
# the same answer. src/markdown/markdown_builder.py imports it.
NOTES_SECTION_HEADING_PATTERN = re.compile(r"^(notes|endnotes)$", re.IGNORECASE)


def assemble_paragraphs(document: Any) -> List[Paragraph]:
    """Every paragraph on every page, in page then reading order.

    Pure: reads the document, returns new Paragraphs, mutates nothing. The
    caller decides whether to store them (Stage 5c does).

    Pages with no TextBlocks contribute nothing - an OCR-recovered page has
    no geometry to ground paragraph reconstruction in, which is exactly why
    src/markdown/markdown_builder.py keeps a separate line-by-line path for
    them. That path is unchanged and still does its own thing.
    """
    blocks_by_page = _blocks_by_page(getattr(document, "blocks", []) or [])
    paragraphs: List[Paragraph] = []
    for page_number in sorted(blocks_by_page):
        paragraphs.extend(_assemble_page(document, page_number, blocks_by_page[page_number]))
    return paragraphs


def _assemble_page(
    document: Any, page_number: int, page_blocks: List[TextBlock]
) -> List[Paragraph]:
    """This page's paragraphs: maximal runs of prose lines, each grouped.

    Runs matter, not just membership. ``group_into_paragraphs`` calibrates
    its indent and line-height thresholds against the run it is given (see
    its ``_baseline_x0``), so a run interrupted by a heading must be grouped
    separately from what follows it - the same granularity the renderer fed
    it before this module existed.
    """
    excluded = _non_prose_block_ids(document, page_number, page_blocks)
    paragraphs: List[Paragraph] = []
    run: List[TextBlock] = []
    for block in page_blocks:
        if block.block_id in excluded:
            paragraphs.extend(group_into_paragraphs(run))
            run = []
            continue
        run.append(block)
    paragraphs.extend(group_into_paragraphs(run))
    return paragraphs


def _non_prose_block_ids(document: Any, page_number: int, page_blocks: List[TextBlock]) -> Set[str]:
    """Every block on this page whose content some other object owns."""
    return absorbed_block_ids(document, page_number, page_blocks) | heading_anchor_block_ids(
        document, page_number, page_blocks
    )


def absorbed_block_ids(document: Any, page_number: int, page_blocks: List[TextBlock]) -> Set[str]:
    """Blocks whose content is already carried somewhere a projection emits
    it, so the line itself renders nowhere.

    Deliberately excludes heading anchors, which a projection *does* emit
    (as headings). That split is what lets a projection preserve the
    precedence it has always had: a line absorbed by a table, a note body,
    a caption, the front matter, or the endnotes section is suppressed even
    when heading detection also claimed it. Collapsing the two sets would
    silently promote those lines to headings - measured on the benchmark as
    a duplicate "## Notes" alongside RAWRS's own generated "## Endnotes",
    and a table's title line emitted above the table that contains it.
    """
    absorbed: Set[str] = {block.block_id for block in page_blocks if block.suppressed}

    for table in getattr(document, "tables", []) or []:
        if table.page_number != page_number:
            continue
        # The recorded containment edge, or the geometry it was resolved
        # from when this document never ran Stage 5c. Same function either
        # way - see relationships.overlapping_block_ids.
        absorbed.update(table.source_block_ids or overlapping_block_ids(table, page_blocks))

    for heading in _content_headings(document, page_number):
        # A wrapped heading's continuation lines are inside its text
        # already (feature_007), so they are absorbed, not anchors.
        absorbed.update(heading.continuation_block_ids)

    absorbed.update(_source_text_block_ids(document, page_number, page_blocks))

    if _has_endnotes(document):
        absorbed.update(
            block.block_id
            for block in page_blocks
            if NOTES_SECTION_HEADING_PATTERN.match(block.text.strip())
        )
    return absorbed


def heading_anchor_block_ids(
    document: Any, page_number: int, page_blocks: List[TextBlock]
) -> Set[str]:
    """Blocks a content heading was detected from.

    The text fallback mirrors src/markdown/markdown_builder.py's own, and
    for the same reason: a heading with no recorded block (Mathpix-path,
    reviewer-created, fixture) can still only be placed by its text, and
    both sides must place it the same way - or a projection will emit a
    heading over a line this module already handed to a paragraph.
    """
    anchors: Set[str] = set()
    unresolved: List[Any] = []
    for heading in _content_headings(document, page_number):
        if heading.source_block_id is not None:
            anchors.add(heading.source_block_id)
        else:
            unresolved.append(heading)

    for heading in unresolved:
        for block in page_blocks:
            if block.block_id not in anchors and block.text == heading.text:
                anchors.add(block.block_id)
                break
    return anchors


def headings_by_anchor(document: Any, page_number: int) -> Dict[str, Any]:
    """Block id -> the content heading detected from it.

    A projection emits a heading when it reaches that block. This replaces
    the sequential "next pending heading" queue every renderer used while
    placement was text-based: a queue stalls permanently the first time a
    heading's line is suppressed for some other reason, silently swallowing
    every later heading on the page. Two such cascades were measured on the
    benchmark corpus the moment placement became id-based.
    """
    return {
        heading.source_block_id: heading
        for heading in _content_headings(document, page_number)
        if heading.source_block_id is not None
    }


def _content_headings(document: Any, page_number: int) -> List[Any]:
    return [
        heading
        for heading in getattr(document, "headings", []) or []
        if heading.page_number == page_number and not heading.is_page_marker
    ]


def _source_text_block_ids(
    document: Any, page_number: int, page_blocks: List[TextBlock]
) -> Set[str]:
    """Blocks a note body, a figure caption, or the front matter absorbed.

    Resolved by exact source-line equality, page-scoped, claiming *every*
    matching block rather than the first - which is what the renderer's
    ``line in suppressed_body_lines`` set did, and the reason a page with
    two identical lines suppresses both. Preserved deliberately: changing
    it here would change output, and this module's job in P2 is to move the
    decision, not to re-decide it.
    """
    texts = _absorbed_source_texts(document, page_number)
    if not texts:
        return set()
    return {block.block_id for block in page_blocks if block.text in texts}


def _absorbed_source_texts(document: Any, page_number: int) -> Set[str]:
    texts: Set[str] = set()

    for note in getattr(document, "footnotes", []) or []:
        if note.body_page_number != page_number:
            continue
        texts.add(note.body_source_text)
        texts.update(note.body_continuation_source_texts)

    for image in getattr(document, "images", []) or []:
        if image.page_number != page_number or image.figure is None:
            continue
        if image.figure.caption_source_text:
            texts.add(image.figure.caption_source_text)

    # Front matter is a property of the document's first page, and
    # src/markdown/markdown_builder.py renders it there only.
    front_matter = getattr(document, "front_matter", None)
    if front_matter is not None and page_number == 1:
        texts.update(front_matter.title_source_texts)
        texts.update(front_matter.author_source_texts)
        texts.update(front_matter.affiliation_source_texts)

    return texts


def _has_endnotes(document: Any) -> bool:
    return any(
        str(getattr(note, "note_type", "")).upper().endswith("ENDNOTE")
        for note in getattr(document, "footnotes", []) or []
    )


def _blocks_by_page(blocks: Iterable[TextBlock]) -> Dict[int, List[TextBlock]]:
    """Blocks grouped by page, in the order a projection walks them.

    Sorted by ``corrected_order`` when a reviewer has set one, falling back
    to extraction ``order`` - the identical key
    src/markdown/markdown_builder.py's ``_group_blocks_by_page`` uses, so
    the run boundaries this module computes are the ones the renderer will
    encounter.
    """
    grouped: Dict[int, List[TextBlock]] = {}
    for block in blocks:
        grouped.setdefault(block.page_number, []).append(block)
    for page_blocks in grouped.values():
        page_blocks.sort(
            key=lambda block: block.corrected_order
            if block.corrected_order is not None
            else block.order
        )
    return grouped


def paragraph_starts(paragraphs: Iterable[Paragraph]) -> Dict[str, Paragraph]:
    """First block id -> the paragraph it begins.

    A projection emits a paragraph when it reaches that block, which is what
    lets it interleave paragraphs with headings without knowing how either
    was decided.
    """
    starts: Dict[str, Paragraph] = {}
    for paragraph in paragraphs:
        if paragraph.source_block_ids:
            starts.setdefault(paragraph.source_block_ids[0], paragraph)
    return starts


def paragraph_members(paragraphs: Iterable[Paragraph]) -> Set[str]:
    """Every block id any paragraph contains - "this line is already
    accounted for", so a projection skips it rather than emitting it
    twice."""
    return {bid for paragraph in paragraphs for bid in paragraph.source_block_ids}
