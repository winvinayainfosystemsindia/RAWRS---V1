"""P1: a derived reading-order traversal, and stable identity for every
renderable entity.

The contract is entirely about what does *not* change. P1 adds a way to
ask the document for its reading order; nothing consumes it yet, no output
moves, no benchmark moves. What it buys is that P2/P3 have somewhere to
put the ordering decisions that currently live inside two renderers.

The rules from ContentStream's docstring are pinned here because breaking
one silently would recreate, one layer up, the exact defect this
architecture removes:

  1. identity lives on nodes, not stream positions
  2. the stream is derived, never stored on Document
  3. nodes reference, never copy
  4. it is one traversal, not the document
"""

from pathlib import Path

import pytest

from src.models.bounding_box import BoundingBox
from src.models.content_stream import ContentKind, ContentStream
from src.models.contracts import (
    Document,
    Heading,
    HeadingLevel,
    Metadata,
    Page,
    TextBlock,
)
from src.structure.content_stream import build_content_stream

BENCHMARK_PDFS = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"


def _block(text: str, order: int, page: int = 1, suppressed: bool = False) -> TextBlock:
    block = TextBlock(
        page_number=page,
        text=text,
        bbox=BoundingBox(x0=0, y0=order * 10, x1=100, y1=order * 10 + 8),
        order=order,
    )
    block.suppressed = suppressed
    return block


def _document(blocks=None, headings=None, pages=1) -> Document:
    return Document(
        source_pdf_path="x.pdf",
        metadata=Metadata(filename="x.pdf", page_count=pages),
        pages=[Page(page_number=n, raw_text="", cleaned_text="") for n in range(1, pages + 1)],
        blocks=list(blocks or []),
        headings=list(headings or []),
    )


class TestStableIdentity:
    def test_every_text_block_has_one(self) -> None:
        assert _block("hello", 0, page=3).block_id == "p3:b0"

    def test_it_distinguishes_identical_text_across_pages(self) -> None:
        # The running-header signature is identical text on many pages, so
        # a text-derived id would collapse exactly what must stay distinct.
        assert _block("Brinkmann", 0, page=3).block_id != _block("Brinkmann", 0, page=4).block_id

    def test_the_suppression_rail_and_the_stream_agree_on_it(self) -> None:
        # One definition, not two modules agreeing by coincidence.
        from src.verification.artifacts import block_id

        block = _block("Brinkmann", 2, page=7)
        assert block_id(block) == block.block_id

    def test_nodes_carry_object_identity_not_positions(self) -> None:
        # Rule 1: an id must survive re-traversal; "third node on page 2"
        # would not.
        document = _document(blocks=[_block("body", 0)])
        node = build_content_stream(document).nodes[0]
        assert node.object_id == "p1:b0"


class TestTheStreamIsDerived:
    def test_it_is_not_stored_on_the_document(self) -> None:
        # Rule 2. Persisting it would make reading order a second source of
        # truth, free to drift from the objects — the Markdown defect,
        # recreated one layer up.
        document = _document(blocks=[_block("body", 0)])
        assert not hasattr(document, "content_stream")
        assert "content_stream" not in document.model_dump()

    def test_building_it_mutates_nothing(self) -> None:
        document = _document(blocks=[_block("body", 0)], headings=[])
        before = document.model_dump_json()
        build_content_stream(document)
        assert document.model_dump_json() == before

    def test_it_is_recomputed_from_current_state(self) -> None:
        document = _document(blocks=[_block("body", 0)])
        assert len(build_content_stream(document).nodes) == 1
        document.blocks.append(_block("more", 1))
        assert len(build_content_stream(document).nodes) == 2

    def test_nodes_hold_no_content(self) -> None:
        # Rule 3: a node references; copied text would drift.
        document = _document(blocks=[_block("some prose", 0)])
        node = build_content_stream(document).nodes[0]
        assert "some prose" not in node.model_dump_json()


class TestTraversalOrder:
    def test_headings_are_placed_at_the_block_they_came_from(self) -> None:
        document = _document(
            blocks=[_block("intro line", 0), _block("A Heading", 1), _block("after", 2)],
            headings=[
                Heading(level=HeadingLevel(2), text="A Heading", page_number=1, document_order=0)
            ],
        )
        kinds = [n.kind for n in build_content_stream(document).nodes]
        assert kinds == [
            ContentKind.BODY_LINE,
            ContentKind.HEADING,
            ContentKind.BODY_LINE,
            ContentKind.BODY_LINE,
        ]

    def test_page_marker_leads_its_page(self) -> None:
        marker = Heading(
            level=HeadingLevel(6), text="1", page_number=1, document_order=0, is_page_marker=True
        )
        document = _document(blocks=[_block("body", 0)], headings=[marker])
        assert build_content_stream(document).nodes[0].kind is ContentKind.PAGE_MARKER

    def test_suppressed_blocks_are_absent(self) -> None:
        # A suppression is an applied decision, so the line is genuinely not
        # content until the correction is reverted.
        document = _document(blocks=[_block("Brinkmann", 0, suppressed=True), _block("real", 1)])
        nodes = build_content_stream(document).nodes
        assert [n.object_id for n in nodes] == ["p1:b1"]

    def test_pages_are_walked_in_order(self) -> None:
        document = _document(
            blocks=[_block("p2", 0, page=2), _block("p1", 0, page=1)], pages=2
        )
        assert [n.page_number for n in build_content_stream(document).nodes] == [1, 2]

    def test_order_is_dense_and_ascending(self) -> None:
        document = _document(blocks=[_block(f"l{i}", i) for i in range(5)])
        assert [n.order for n in build_content_stream(document).nodes] == [0, 1, 2, 3, 4]

    def test_empty_document_yields_an_empty_stream(self) -> None:
        assert build_content_stream(_document()).nodes == []


class TestAgainstTheRealCorpus:
    @pytest.mark.skipif(not BENCHMARK_PDFS.is_dir(), reason="benchmark corpus not present")
    def test_a_real_document_produces_a_coherent_traversal(self) -> None:
        from src.headings.heading_detector import detect_headings
        from src.ocr.extractor import extract_text
        from src.parser.pdf_parser import parse_pdf
        from src.structure.structure_detector import detect_structure

        pdf = next(BENCHMARK_PDFS.glob("7.brinkman*.pdf"), None)
        if pdf is None:
            pytest.skip("Brinkman benchmark PDF not present")

        document = detect_headings(detect_structure(extract_text(parse_pdf(pdf))))
        stream = build_content_stream(document)

        assert stream.nodes, "no traversal produced for a real document"
        # Ids are unique: two nodes pointing at one object would make an
        # anchor ambiguous when P3 maps an edit back to an object.
        ids = [n.object_id for n in stream.nodes]
        assert len(ids) == len(set(ids))
        # Every content heading is represented exactly once.
        content_headings = [h for h in document.headings if not h.is_page_marker]
        assert stream.kind_counts().get("heading", 0) == len(content_headings)
        # And the traversal is globally ordered.
        assert [n.order for n in stream.nodes] == sorted(n.order for n in stream.nodes)
