"""P2: the model owns prose segmentation, paragraph grouping and the
containment edges a projection used to reconstruct at render time.

These lock the *decisions*, not the rendering. Markdown-level behaviour is
covered by tests/test_markdown.py and the whole-corpus parity check in
tests/test_pipeline.py.
"""

from types import SimpleNamespace

from src.models.bounding_box import BoundingBox
from src.models.figure import Figure
from src.models.footnote import Footnote, NoteType
from src.models.front_matter import FrontMatter
from src.models.heading import Heading, HeadingLevel
from src.models.image import Image
from src.models.table import Table, TableCell, TableRow
from src.models.text_block import TextBlock
from src.structure.paragraph_assembly import (
    absorbed_block_ids,
    assemble_paragraphs,
    heading_anchor_block_ids,
    headings_by_anchor,
    paragraph_members,
    paragraph_starts,
)
from src.structure.relationships import link_document, overlapping_block_ids


def _block(text: str, order: int, y: float = 100.0, page: int = 1, x0: float = 50.0) -> TextBlock:
    """One body line, 10pt tall at a stable left margin - close enough
    together that paragraph_grouper joins consecutive ones by default, so a
    split in these tests always means a real exclusion, never a gap."""
    return TextBlock(
        page_number=page,
        text=text,
        bbox=BoundingBox(x0=x0, y0=y, x1=x0 + 200.0, y1=y + 10.0),
        order=order,
        source_block_index=0,
    )


def _lines(count: int, page: int = 1, start_y: float = 100.0):
    return [_block(f"line {i}", i, start_y + i * 12.0, page) for i in range(count)]


def _doc(**overrides):
    base = dict(blocks=[], tables=[], headings=[], footnotes=[], images=[], front_matter=None)
    base.update(overrides)
    return SimpleNamespace(**base)


def _heading(text: str, page: int = 1, order: int = 0, **kwargs) -> Heading:
    return Heading(
        level=HeadingLevel.H2,
        text=text,
        page_number=page,
        document_order=order,
        is_page_marker=False,
        **kwargs,
    )


def _table(page: int, bbox, table_id: str = "t1") -> Table:
    return Table(
        table_id=table_id,
        page_number=page,
        row_count=1,
        col_count=1,
        rows=[TableRow(cells=[TableCell(text="cell", row_index=0, col_index=0)])],
        bbox=bbox,
    )


def _note(body_text: str, page: int = 1, note_type: NoteType = NoteType.FOOTNOTE) -> Footnote:
    return Footnote(
        note_type=note_type,
        number=1,
        marker="1",
        anchor_page_number=page,
        anchor_text="some anchor line",
        body=body_text,
        body_page_number=page,
        body_source_text=body_text,
    )


class TestTableContainmentEdge:
    def test_link_document_records_overlapping_blocks(self) -> None:
        blocks = [_block("in table", 0, y=100.0), _block("body prose", 1, y=400.0)]
        table = _table(1, BoundingBox(x0=40.0, y0=90.0, x1=300.0, y1=130.0))
        link_document(_doc(blocks=blocks, tables=[table]))
        assert table.source_block_ids == ["p1:b0"]

    def test_table_without_bbox_records_nothing(self) -> None:
        table = _table(1, None)
        link_document(_doc(blocks=_lines(2), tables=[table]))
        assert table.source_block_ids == []

    def test_only_same_page_blocks_are_considered(self) -> None:
        blocks = [_block("page two line", 0, y=100.0, page=2)]
        table = _table(1, BoundingBox(x0=40.0, y0=90.0, x1=300.0, y1=130.0))
        link_document(_doc(blocks=blocks, tables=[table]))
        assert table.source_block_ids == []

    def test_touching_edges_do_not_overlap(self) -> None:
        """A block whose bottom is exactly the table's top shares an edge and
        no area - counting it would suppress the line immediately above a
        table, which is ordinary prose."""
        block = _block("just above", 0, y=80.0)  # y1 == 90.0
        table = _table(1, BoundingBox(x0=40.0, y0=90.0, x1=300.0, y1=130.0))
        assert overlapping_block_ids(table, [block]) == []


class TestProseSegmentation:
    def test_consecutive_lines_become_one_paragraph(self) -> None:
        paragraphs = assemble_paragraphs(_doc(blocks=_lines(3)))
        assert len(paragraphs) == 1
        assert paragraphs[0].source_block_ids == ["p1:b0", "p1:b1", "p1:b2"]

    def test_heading_anchor_splits_the_run(self) -> None:
        blocks = _lines(3)
        heading = _heading("A Heading", source_block_id="p1:b1")
        paragraphs = assemble_paragraphs(_doc(blocks=blocks, headings=[heading]))
        assert [p.source_block_ids for p in paragraphs] == [["p1:b0"], ["p1:b2"]]

    def test_suppressed_artifact_is_not_prose(self) -> None:
        blocks = _lines(3)
        blocks[1].suppressed = True
        paragraphs = assemble_paragraphs(_doc(blocks=blocks))
        assert paragraph_members(paragraphs) == {"p1:b0", "p1:b2"}

    def test_wrapped_heading_continuation_is_not_prose(self) -> None:
        blocks = _lines(3)
        heading = _heading(
            "line 0 line 1", source_block_id="p1:b0", continuation_block_ids=["p1:b1"]
        )
        paragraphs = assemble_paragraphs(_doc(blocks=blocks, headings=[heading]))
        assert paragraph_members(paragraphs) == {"p1:b2"}

    def test_note_body_line_is_not_prose(self) -> None:
        blocks = _lines(3)
        doc = _doc(blocks=blocks, footnotes=[_note("line 1")])
        assert paragraph_members(assemble_paragraphs(doc)) == {"p1:b0", "p1:b2"}

    def test_figure_caption_line_is_not_prose(self) -> None:
        blocks = _lines(3)
        image = Image(
            image_id="img1",
            page_number=1,
            file_path="x.png",
            figure=Figure(caption_source_text="line 1"),
        )
        doc = _doc(blocks=blocks, images=[image])
        assert paragraph_members(assemble_paragraphs(doc)) == {"p1:b0", "p1:b2"}

    def test_front_matter_lines_are_not_prose_on_page_one_only(self) -> None:
        page1 = _lines(2, page=1)
        page2 = _lines(2, page=2)
        front_matter = FrontMatter(title="line 0", title_source_texts=["line 0"])
        doc = _doc(blocks=page1 + page2, front_matter=front_matter)
        members = paragraph_members(assemble_paragraphs(doc))
        assert "p1:b0" not in members  # absorbed into the front-matter block
        assert "p2:b0" in members  # same text, different page - still prose

    def test_notes_section_heading_is_not_prose_when_endnotes_exist(self) -> None:
        blocks = [_block("Notes", 0), _block("body prose", 1, y=112.0)]
        doc = _doc(blocks=blocks, footnotes=[_note("a note", note_type=NoteType.ENDNOTE)])
        assert paragraph_members(assemble_paragraphs(doc)) == {"p1:b1"}

    def test_notes_line_stays_prose_without_endnotes(self) -> None:
        blocks = [_block("Notes", 0), _block("body prose", 1, y=112.0)]
        assert "p1:b0" in paragraph_members(assemble_paragraphs(_doc(blocks=blocks)))

    def test_pages_are_segmented_independently(self) -> None:
        doc = _doc(blocks=_lines(2, page=1) + _lines(2, page=2))
        paragraphs = assemble_paragraphs(doc)
        assert [p.page_number for p in paragraphs] == [1, 2]


class TestPrecedenceSplit:
    """absorbed_block_ids must exclude heading anchors, so a projection can
    keep "absorbed beats heading" - collapsing the two sets promotes a
    suppressed line to a rendered heading."""

    def test_heading_anchor_is_not_absorbed(self) -> None:
        blocks = _lines(2)
        heading = _heading("line 0", source_block_id="p1:b0")
        doc = _doc(blocks=blocks, headings=[heading])
        assert "p1:b0" not in absorbed_block_ids(doc, 1, blocks)
        assert "p1:b0" in heading_anchor_block_ids(doc, 1, blocks)

    def test_heading_over_an_absorbed_line_stays_absorbed(self) -> None:
        blocks = [_block("Notes", 0), _block("body prose", 1, y=112.0)]
        heading = _heading("Notes", source_block_id="p1:b0")
        doc = _doc(
            blocks=blocks,
            headings=[heading],
            footnotes=[_note("a note", note_type=NoteType.ENDNOTE)],
        )
        assert "p1:b0" in absorbed_block_ids(doc, 1, blocks)


class TestHeadingAnchorLookup:
    def test_headings_are_keyed_by_their_block(self) -> None:
        heading = _heading("A Heading", source_block_id="p1:b1")
        assert headings_by_anchor(_doc(headings=[heading]), 1) == {"p1:b1": heading}

    def test_page_markers_are_excluded(self) -> None:
        marker = Heading(
            level=HeadingLevel.H6,
            text="1",
            page_number=1,
            document_order=0,
            is_page_marker=True,
            source_block_id="p1:b0",
        )
        assert headings_by_anchor(_doc(headings=[marker]), 1) == {}

    def test_unanchored_heading_falls_back_to_text(self) -> None:
        blocks = _lines(3)
        doc = _doc(blocks=blocks, headings=[_heading("line 1")])
        assert heading_anchor_block_ids(doc, 1, blocks) == {"p1:b1"}

    def test_recorded_anchors_win_over_text_matches(self) -> None:
        """Two headings with identical text: the one that recorded a block
        keeps it, and the text fallback takes the other occurrence rather
        than stealing an already-claimed line."""
        blocks = [_block("Summary", 0), _block("body", 1, y=112.0), _block("Summary", 2, y=124.0)]
        anchored = _heading("Summary", order=0, source_block_id="p1:b2")
        floating = _heading("Summary", order=1)
        doc = _doc(blocks=blocks, headings=[anchored, floating])
        assert heading_anchor_block_ids(doc, 1, blocks) == {"p1:b0", "p1:b2"}


class TestParagraphIndexes:
    def test_starts_map_first_block_to_its_paragraph(self) -> None:
        paragraphs = assemble_paragraphs(_doc(blocks=_lines(3)))
        assert list(paragraph_starts(paragraphs)) == ["p1:b0"]

    def test_empty_document_assembles_nothing(self) -> None:
        assert assemble_paragraphs(_doc()) == []


class TestNoteLabel:
    def test_label_is_page_qualified(self) -> None:
        assert _note("body", page=7).label == "p7-1"

    def test_label_is_not_the_identity(self) -> None:
        """footnote_id answers "which note is this"; label answers "what does
        it call itself". They must not be conflated - a reviewer renumbering
        a note changes one and not the other."""
        note = _note("body")
        note.footnote_id = "fn-3"
        assert note.label != note.footnote_id
