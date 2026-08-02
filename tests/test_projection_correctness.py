"""Projection correctness — see docs/ADR_PROJECTION_CORRECTNESS_2026-08-03.md.

Every invariant gets a test that makes it FIRE, not only one that makes it
pass. A gate nothing can trip is not a gate, and the defect this ADR exists to
prevent survived because the check that should have caught it (byte parity)
could only ever compare output to itself.
"""

from types import SimpleNamespace

from src.benchmark.projection import check_projection
from src.models.bounding_box import BoundingBox
from src.models.figure import Figure
from src.models.footnote import Footnote, NoteType
from src.models.front_matter import FrontMatter
from src.models.heading import Heading, HeadingLevel
from src.models.image import Image
from src.models.table import Table, TableCell, TableRow
from src.models.text_block import TextBlock


def _block(text: str, order: int, y: float = 100.0, page: int = 1) -> TextBlock:
    return TextBlock(
        page_number=page,
        text=text,
        bbox=BoundingBox(x0=50.0, y0=y, x1=250.0, y1=y + 10.0),
        order=order,
        source_block_index=0,
    )


def _heading(text: str, order: int = 0, **kw) -> Heading:
    return Heading(
        level=HeadingLevel.H2,
        text=text,
        page_number=1,
        document_order=order,
        is_page_marker=False,
        **kw,
    )


def _doc(**over):
    base = dict(
        blocks=[],
        tables=[],
        headings=[],
        footnotes=[],
        images=[],
        lists=[],
        pages=[],
        front_matter=None,
        source_pdf_path="fixture.pdf",
    )
    base.update(over)
    return SimpleNamespace(**base)


def _kinds(report):
    return report.by_kind()


# --------------------------------------------------------------------------- #
# the baseline: a faithful projection
# --------------------------------------------------------------------------- #

class TestFaithfulProjection:
    def test_matching_model_and_markdown_is_clean(self) -> None:
        doc = _doc(
            blocks=[_block("Section One", 0), _block("Some body prose here.", 1, 112.0)],
            headings=[_heading("Section One", source_block_id="p1:b0")],
        )
        report = check_projection(doc, "## Section One\n\nSome body prose here.\n")
        assert report.ok, report.violations


# --------------------------------------------------------------------------- #
# PI-1 lost objects — the defect that caused the ADR
# --------------------------------------------------------------------------- #

class TestLostObjects:
    def test_dropped_heading_is_a_violation(self) -> None:
        """The pre-P2 defect in miniature: the model holds a heading, the
        projection renders its text as prose, byte parity stays silent."""
        doc = _doc(
            blocks=[_block("Section One", 0), _block("Body prose.", 1, 112.0)],
            headings=[_heading("Section One", source_block_id="p1:b0")],
        )
        report = check_projection(doc, "**Section One**\n\nBody prose.\n")
        assert _kinds(report) == {"lost_object": 1}

    def test_dropped_table_is_a_violation(self) -> None:
        table = Table(
            table_id="t1",
            page_number=1,
            row_count=1,
            col_count=1,
            rows=[TableRow(cells=[TableCell(text="cell", row_index=0, col_index=0)])],
        )
        report = check_projection(_doc(tables=[table]), "some prose cell\n")
        assert "lost_object" in _kinds(report)

    def test_dropped_note_definition_is_a_violation(self) -> None:
        note = Footnote(
            note_type=NoteType.FOOTNOTE,
            number=1,
            marker="1",
            anchor_page_number=1,
            anchor_text="a line",
            body="The note body.",
            body_page_number=1,
            body_source_text="The note body.",
        )
        report = check_projection(_doc(footnotes=[note]), "The note body.\n")
        assert "lost_object" in _kinds(report)

    def test_dropped_page_marker_is_a_violation(self) -> None:
        marker = Heading(
            level=HeadingLevel.H6,
            text="7",
            page_number=1,
            document_order=0,
            is_page_marker=True,
        )
        report = check_projection(_doc(headings=[marker]), "7\n")
        assert "lost_object" in _kinds(report)


# --------------------------------------------------------------------------- #
# PI-2 invented objects
# --------------------------------------------------------------------------- #

class TestInventedObjects:
    def test_heading_with_no_model_object_is_a_violation(self) -> None:
        doc = _doc(blocks=[_block("Not a heading", 0)])
        report = check_projection(doc, "## Not a heading\n")
        assert _kinds(report) == {"invented_object": 1}

    def test_generated_endnotes_heading_is_a_finding_not_a_violation(self) -> None:
        """RAWRS writes "## Endnotes" itself. Authorized - and recorded as
        outstanding debt, because the model has nowhere to hold it (PI-6)."""
        note = Footnote(
            note_type=NoteType.ENDNOTE,
            number=1,
            marker="1",
            anchor_page_number=1,
            anchor_text="a line",
            body="Note body.",
            body_page_number=1,
            body_source_text="Note body.",
        )
        report = check_projection(_doc(footnotes=[note]), "## Endnotes\n\n[^p1-1]: Note body.\n")
        assert report.ok, report.violations
        assert [f.kind for f in report.findings] == ["renderer_generated_object"]


# --------------------------------------------------------------------------- #
# PI-3 content conservation
# --------------------------------------------------------------------------- #

class TestContentConservation:
    def test_missing_prose_is_content_loss(self) -> None:
        doc = _doc(blocks=[_block("kept line", 0), _block("vanished line", 1, 112.0)])
        report = check_projection(doc, "kept line\n")
        assert "content_loss" in _kinds(report)

    def test_text_with_no_model_source_is_content_invention(self) -> None:
        doc = _doc(blocks=[_block("real line", 0)])
        report = check_projection(doc, "real line\n\nfabricated sentence\n")
        assert "content_invention" in _kinds(report)

    def test_duplicated_prose_is_content_invention(self) -> None:
        """The caption / front-matter double-render class, fixed twice in
        markdown_builder's history and never before mechanically detectable."""
        doc = _doc(blocks=[_block("repeated line", 0)])
        report = check_projection(doc, "repeated line\n\nrepeated line\n")
        assert "content_invention" in _kinds(report)


# --------------------------------------------------------------------------- #
# PI-4 authorized absence — the difference between a decision and a deletion
# --------------------------------------------------------------------------- #

class TestAuthorizedAbsence:
    def test_suppressed_block_may_vanish(self) -> None:
        """A CorrectionRecord authorized it, and reverting brings it back."""
        blocks = [_block("kept line", 0), _block("running header", 1, 112.0)]
        blocks[1].suppressed = True
        report = check_projection(_doc(blocks=blocks), "kept line\n")
        assert report.ok, report.violations

    def test_table_absorbed_block_may_vanish_from_prose(self) -> None:
        blocks = [_block("prose", 0), _block("cell text", 1, 112.0)]
        table = Table(
            table_id="t1",
            page_number=1,
            row_count=1,
            col_count=1,
            rows=[TableRow(cells=[TableCell(text="cell text", row_index=0, col_index=0)])],
            source_block_ids=["p1:b1"],
        )
        md = "prose\n\n<!-- table-id: t1 -->\n\n| cell text |\n| --- |\n"
        report = check_projection(_doc(blocks=blocks, tables=[table]), md)
        assert report.ok, report.violations

    def test_unbacked_absorption_is_a_finding(self) -> None:
        """The table claims a line its cells do not carry - a bbox that
        over-captured. The projection obeyed the model, so this is a detector
        finding, not a projection violation."""
        blocks = [_block("prose", 0), _block("orphaned by the bbox", 1, 112.0)]
        table = Table(
            table_id="t1",
            page_number=1,
            row_count=1,
            col_count=1,
            rows=[TableRow(cells=[TableCell(text="cell text", row_index=0, col_index=0)])],
            source_block_ids=["p1:b1"],
        )
        md = "prose\n\n<!-- table-id: t1 -->\n\n| cell text |\n| --- |\n"
        report = check_projection(_doc(blocks=blocks, tables=[table]), md)
        assert report.ok, report.violations
        assert [f.kind for f in report.findings] == ["unbacked_authorization"]

    def test_front_matter_title_need_not_render_as_a_heading(self) -> None:
        fm = FrontMatter(title="The Title", title_source_texts=["The Title"])
        doc = _doc(
            blocks=[_block("The Title", 0), _block("body", 1, 112.0)],
            headings=[_heading("The Title", source_block_id="p1:b0")],
            front_matter=fm,
        )
        report = check_projection(doc, "**The Title**\n\nbody\n")
        assert report.ok, report.violations

    def test_absorbed_heading_line_stays_absorbed(self) -> None:
        """A heading whose block a table owns must NOT be emitted - absorbed
        beats heading (ADR §3). Its absence is authorized."""
        blocks = [_block("Table Title", 0), _block("body", 1, 400.0)]
        table = Table(
            table_id="t1",
            page_number=1,
            row_count=1,
            col_count=1,
            rows=[TableRow(cells=[TableCell(text="Table Title", row_index=0, col_index=0)])],
            source_block_ids=["p1:b0"],
        )
        doc = _doc(
            blocks=blocks,
            tables=[table],
            headings=[_heading("Table Title", source_block_id="p1:b0")],
        )
        md = "<!-- table-id: t1 -->\n\n| Table Title |\n| --- |\n\nbody\n"
        report = check_projection(doc, md)
        assert report.ok, report.violations


# --------------------------------------------------------------------------- #
# PI-5 single realization
# --------------------------------------------------------------------------- #

class TestSingleRealization:
    def test_heading_emitted_twice_is_a_violation(self) -> None:
        doc = _doc(
            blocks=[_block("Section One", 0)],
            headings=[_heading("Section One", source_block_id="p1:b0")],
        )
        report = check_projection(doc, "## Section One\n\n## Section One\n")
        assert "duplicate_realization" in _kinds(report)

    def test_image_emitted_twice_is_a_violation(self) -> None:
        img = Image(
            image_id="i1",
            page_number=1,
            file_path="out/a.png",
            figure=Figure(alt_text="a chart"),
        )
        md = "![a chart](out/a.png)\n\n![a chart](out/a.png)\n"
        report = check_projection(_doc(images=[img]), md)
        assert "duplicate_realization" in _kinds(report)


# --------------------------------------------------------------------------- #
# wrapped headings — the exact shape of the pre-P2 defect
# --------------------------------------------------------------------------- #

class TestWrappedHeadings:
    def test_wrapped_heading_rendered_once_is_clean(self) -> None:
        blocks = [_block("CHAPTER", 0), _block("1", 1, 112.0), _block("body", 2, 124.0)]
        doc = _doc(
            blocks=blocks,
            headings=[
                _heading("CHAPTER 1", source_block_id="p1:b0", continuation_block_ids=["p1:b1"])
            ],
        )
        report = check_projection(doc, "## CHAPTER 1\n\nbody\n")
        assert report.ok, report.violations

    def test_wrapped_heading_dropped_to_prose_is_caught(self) -> None:
        """Precisely what the pre-P2 renderer did to 14 headings: the joined
        text matched no line, so the heading vanished and its lines rendered as
        body. Byte parity passed; PI-1 does not."""
        blocks = [_block("CHAPTER", 0), _block("1", 1, 112.0), _block("body", 2, 124.0)]
        doc = _doc(
            blocks=blocks,
            headings=[
                _heading("CHAPTER 1", source_block_id="p1:b0", continuation_block_ids=["p1:b1"])
            ],
        )
        report = check_projection(doc, "***CHAPTER 1***\n\nbody\n")
        assert "lost_object" in _kinds(report)
