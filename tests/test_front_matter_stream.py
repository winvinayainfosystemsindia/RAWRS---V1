"""L5'a — front matter enters the canonical traversal.

Front matter was the last detected content the ContentStream could not
carry, and the reason was structural rather than incidental: a
``ContentNode`` holds *the id of the object it points at*, and a title or
byline had no id to point at — ``FrontMatter`` stored bare strings in
three lists. It was also the only object of its class not deriving from
``SemanticObject``. So the Markdown projection decided the rendering
itself, which its own ``PROJECTION_CONTRACT`` declared as a limitation.

These tests pin the three halves of the fix: the model records identity
and position, the traversal places by that recorded position, and the
projections read what the traversal placed.
"""

from pathlib import Path
from typing import List

import pytest

from src.benchmark.projection import check_front_matter_stream
from src.frontmatter.front_matter_extractor import extract_front_matter
from src.markdown.markdown_builder import build_markdown
from src.models.bounding_box import BoundingBox
from src.models.content_stream import ContentKind
from src.models.contracts import Document, Metadata, Page, TextBlock
from src.models.front_matter import FrontMatter, FrontMatterItem, FrontMatterRole
from src.ocr.extractor import extract_text
from src.parser.pdf_parser import parse_pdf
from src.structure.content_stream import build_content_stream
from src.structure.structure_detector import detect_structure

SAMPLE_PDF_DIR = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"


def _block(text: str, order: int, page: int = 1) -> TextBlock:
    return TextBlock(
        page_number=page,
        text=text,
        bbox=BoundingBox(x0=72, y0=40 + order * 20, x1=400, y1=56 + order * 20),
        order=order,
    )


def _item(role: FrontMatterRole, text: str, block: TextBlock, order: int) -> FrontMatterItem:
    return FrontMatterItem(
        role=role,
        text=text,
        source_block_id=block.block_id,
        document_order=order,
        page_number=block.page_number,
    )


def _document(blocks: List[TextBlock], items: List[FrontMatterItem]) -> Document:
    return Document(
        source_pdf_path="fm.pdf",
        metadata=Metadata(filename="fm.pdf", page_count=1),
        pages=[Page(page_number=1, cleaned_text="\n".join(b.text for b in blocks))],
        blocks=blocks,
        front_matter=FrontMatter(items=items),
    )


def _front_matter_nodes(document: Document):
    return [n for n in build_content_stream(document).nodes if n.kind is ContentKind.FRONT_MATTER]


class TestItemIdentity:
    def test_an_item_backfills_a_stable_id(self) -> None:
        block = _block("A Title", 0)
        item = _item(FrontMatterRole.TITLE, "A Title", block, 0)
        assert item.id == "frontmatter-0"
        assert item.object_type == "front_matter_item"

    def test_an_item_carries_the_semantic_object_contract(self) -> None:
        # The reason for the base class: L5'b needs correction_ids, and
        # provenance is what tells a reviewer where the item came from.
        item = _item(FrontMatterRole.AUTHOR, "Jane Doe", _block("Jane Doe", 0), 0)
        assert item.correction_ids == []
        assert item.provenance is not None

    def test_role_travels_on_the_item(self) -> None:
        # AI-2 forbids a projection importing src.frontmatter, so a role
        # recovered by calling role_for_text() at render time is not
        # available to one. It has to be on the object.
        item = _item(FrontMatterRole.AFFILIATION, "A University", _block("A University", 0), 0)
        assert item.role is FrontMatterRole.AFFILIATION


class TestPlacementByRecordedPosition:
    def test_items_are_placed_at_the_blocks_they_record(self) -> None:
        blocks = [_block("Body above", 0), _block("A Title", 1), _block("Jane Doe", 2)]
        document = _document(
            blocks,
            [
                _item(FrontMatterRole.TITLE, "A Title", blocks[1], 0),
                _item(FrontMatterRole.AUTHOR, "Jane Doe", blocks[2], 1),
            ],
        )
        stream = build_content_stream(document)
        kinds = [(n.kind.value, n.object_id) for n in stream.nodes]

        assert kinds == [
            ("body_line", blocks[0].block_id),
            ("front_matter", "frontmatter-0"),
            ("front_matter", "frontmatter-1"),
        ]

    def test_two_items_with_identical_text_are_not_confused(self) -> None:
        # The test that proves text-keyed placement is gone. Both lines read
        # "Smith" — an author byline and a repeated name elsewhere in the
        # masthead. A text key cannot tell them apart and would claim both
        # for whichever item resolved first; a recorded source_block_id
        # places each at its own line.
        blocks = [_block("Smith", 0), _block("Middle line", 1), _block("Smith", 2)]
        document = _document(
            blocks,
            [
                _item(FrontMatterRole.AUTHOR, "Smith", blocks[0], 0),
                _item(FrontMatterRole.AFFILIATION, "Smith", blocks[2], 1),
            ],
        )
        nodes = _front_matter_nodes(document)

        assert [n.object_id for n in nodes] == ["frontmatter-0", "frontmatter-1"]
        # Distinct positions, in recorded block order — and the middle body
        # line still sits between them.
        assert [n.order for n in nodes] == [0, 2]
        body = [n for n in build_content_stream(document).nodes if n.kind is ContentKind.BODY_LINE]
        assert [n.object_id for n in body] == [blocks[1].block_id]

    def test_an_item_with_no_recorded_block_is_not_placed(self) -> None:
        # The Mathpix path records no position in the PDF. Inventing one is
        # the thing this milestone exists to stop; the item simply does not
        # enter the traversal, and PI-7 reports it as a finding.
        block = _block("Body", 0)
        item = FrontMatterItem(
            role=FrontMatterRole.TITLE,
            text="Imported Title",
            source_block_id=None,
            document_order=0,
        )
        document = _document([block], [item])

        assert _front_matter_nodes(document) == []
        report = check_front_matter_stream(document)
        assert report.violations == []
        assert [f.kind for f in report.findings] == ["no_recorded_position"]

    def test_a_front_matter_block_is_never_also_a_body_line(self) -> None:
        blocks = [_block("A Title", 0), _block("Ordinary prose", 1)]
        document = _document(blocks, [_item(FrontMatterRole.TITLE, "A Title", blocks[0], 0)])

        body = [n for n in build_content_stream(document).nodes if n.kind is ContentKind.BODY_LINE]
        assert [n.object_id for n in body] == [blocks[1].block_id]

    def test_each_item_appears_exactly_once(self) -> None:
        blocks = [_block(f"Line {i}", i) for i in range(3)]
        document = _document(
            blocks, [_item(FrontMatterRole.TITLE, b.text, b, i) for i, b in enumerate(blocks)]
        )
        ids = [n.object_id for n in _front_matter_nodes(document)]
        assert ids == sorted(set(ids), key=ids.index)
        assert len(ids) == 3


class TestProjectionsConsumeTheStream:
    def test_markdown_renders_front_matter_from_the_stream(self) -> None:
        blocks = [_block("A Title", 0), _block("Jane Doe", 1), _block("A University", 2)]
        document = _document(
            blocks,
            [
                _item(FrontMatterRole.TITLE, "A Title", blocks[0], 0),
                _item(FrontMatterRole.AUTHOR, "Jane Doe", blocks[1], 1),
                _item(FrontMatterRole.AFFILIATION, "A University", blocks[2], 2),
            ],
        )
        markdown = build_markdown(document)

        assert "**A Title**" in markdown
        assert "*Jane Doe*" in markdown
        assert "A University" in markdown

    def test_a_multi_line_title_renders_as_one_block(self) -> None:
        blocks = [_block("A TITLE SPLIT", 0), _block("ACROSS TWO LINES", 1)]
        document = _document(
            blocks,
            [
                _item(FrontMatterRole.TITLE, "A TITLE SPLIT", blocks[0], 0),
                _item(FrontMatterRole.TITLE, "ACROSS TWO LINES", blocks[1], 1),
            ],
        )
        assert "**A TITLE SPLIT ACROSS TWO LINES**" in build_markdown(document)


class TestProjectionInvariant:
    """PI-7, over documents built by the real extractor."""

    @pytest.mark.parametrize(
        "filename,expected_items",
        [
            ("1.Aims of Education and the teacher_Dhankar_PhilPers (1).pdf", 3),
            ("2.FolkPedagogy_Bruner_PsychDimensions_New.pdf", 2),
            ("5.Teachingas a profession_Calderhead.pdf", 2),
            ("6. Fullan&Hargreaves_teacherasaperson.pdf", 2),
            ("7.brinkman-learner-centred-education-reform-india-missing-beliefs.pdf", 5),
        ],
    )
    def test_corpus_front_matter_is_placed_exactly_once(
        self, filename: str, expected_items: int
    ) -> None:
        document = extract_front_matter(
            detect_structure(extract_text(parse_pdf(SAMPLE_PDF_DIR / filename)))
        )
        report = check_front_matter_stream(document, name=filename)

        assert report.violations == []
        assert report.counts["front_matter_items"] == expected_items
        assert report.counts["placeable"] == expected_items
        assert report.counts["in_stream"] == expected_items

    def test_pi7_catches_an_item_the_stream_never_placed(self) -> None:
        # Without a failing case the invariant could pass by being unable
        # to fail: this item names a block that is not in the document.
        block = _block("A Title", 0)
        orphan = FrontMatterItem(
            role=FrontMatterRole.TITLE,
            text="A Title",
            source_block_id="p9:b99",
            document_order=0,
        )
        report = check_front_matter_stream(_document([block], [orphan]))

        assert [v.kind for v in report.violations] == ["lost_object"]

    def test_pi7_catches_duplicate_identity(self) -> None:
        blocks = [_block("A", 0), _block("B", 1)]
        items = [
            _item(FrontMatterRole.TITLE, "A", blocks[0], 0),
            _item(FrontMatterRole.AUTHOR, "B", blocks[1], 0),  # same order -> same id
        ]
        report = check_front_matter_stream(_document(blocks, items))

        assert any(v.kind == "duplicate" for v in report.violations)

    def test_a_document_with_no_front_matter_is_silent(self) -> None:
        document = _document([_block("Body", 0)], [])
        report = check_front_matter_stream(document)
        assert report.violations == []
        assert report.counts["front_matter_items"] == 0
