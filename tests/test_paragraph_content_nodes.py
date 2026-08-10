"""P3 step 1 — prose is a node in the traversal, not a run of source lines.

Before this, 95% of the stream's ``BODY_LINE`` nodes were source lines
the model had already grouped into Paragraphs (7,474 of 7,859 corpus
blocks): the traversal restated the page's text instead of naming the
document's semantics, and disagreed with the document about what its own
content was.

What these tests pin is that a ``PARAGRAPH`` node *references* rather than
*copies*: it holds ``Paragraph.id`` and a position derived from the block
the paragraph begins at, carries no text, and takes the place of the body
lines it absorbed. Identity is W-2a's, so two paragraphs reading
identically are still two nodes — the property a text-keyed traversal
cannot have.

The Mathpix path is the deliberate non-case: its paragraphs record a
``source_line`` and no ``source_block_ids``, a coordinate system this
traversal does not share, so it emits nothing rather than guessing.
"""

from pathlib import Path
from typing import Any, List, Optional

import pytest

from src.benchmark.projection import check_paragraph_stream
from src.models.bounding_box import BoundingBox
from src.models.content_stream import ContentKind
from src.models.contracts import (
    Document,
    Heading,
    HeadingLevel,
    Metadata,
    Page,
    Paragraph,
    TextBlock,
)
from src.structure.content_stream import build_content_stream

BENCHMARK_PDFS = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"


def _block(order: int, text: str = "", page: int = 1) -> TextBlock:
    return TextBlock(
        page_number=page,
        text=text or f"Line {order}",
        bbox=BoundingBox(x0=72, y0=40 + order * 20, x1=400, y1=56 + order * 20),
        order=order,
    )


def _document(
    blocks: List[TextBlock],
    paragraphs: List[Paragraph],
    headings: Optional[List[Heading]] = None,
    pages: int = 1,
) -> Document:
    return Document(
        source_pdf_path="x.pdf",
        metadata=Metadata(filename="x.pdf", page_count=pages),
        pages=[Page(page_number=n, cleaned_text="") for n in range(1, pages + 1)],
        blocks=blocks,
        paragraphs=paragraphs,
        headings=headings or [],
    )


@pytest.fixture
def document() -> Document:
    """Six lines: two paragraphs of two lines each, and two lines no
    paragraph claims — one of them a heading's anchor."""
    blocks = [_block(i) for i in range(6)]
    paragraphs = [
        Paragraph(
            page_number=1,
            text="First paragraph.",
            source_block_ids=[blocks[0].block_id, blocks[1].block_id],
        ),
        Paragraph(
            page_number=1,
            text="Second paragraph.",
            source_block_ids=[blocks[3].block_id, blocks[4].block_id],
        ),
    ]
    heading = Heading(
        text="Line 2",
        level=HeadingLevel.H2,
        page_number=1,
        document_order=0,
        source_block_id=blocks[2].block_id,
    )
    return _document(blocks, paragraphs, [heading])


def _kinds(document: Document):
    return build_content_stream(document).kind_counts()


def _nodes(document: Document, kind: ContentKind):
    return [n for n in build_content_stream(document).nodes if n.kind is kind]


class TestTheKindExists:
    def test_paragraph_is_a_content_kind(self) -> None:
        assert ContentKind.PARAGRAPH.value == "paragraph"

    def test_the_existing_kinds_keep_their_values(self) -> None:
        # Renaming or renumbering one would silently reinterpret every
        # persisted or asserted stream shape.
        assert [k.value for k in ContentKind] == [
            "page_marker",
            "heading",
            "paragraph",
            "body_line",
            "list",
            "table",
            "image",
            "note_definition",
            "front_matter",
        ]


class TestOneNodePerParagraph:
    def test_every_paragraph_appears_exactly_once(self, document: Document) -> None:
        nodes = _nodes(document, ContentKind.PARAGRAPH)
        assert [n.object_id for n in nodes] == [p.id for p in document.paragraphs]

    def test_the_node_identity_is_the_paragraph_id(self, document: Document) -> None:
        first = _nodes(document, ContentKind.PARAGRAPH)[0]
        assert first.object_id == document.paragraphs[0].id == "paragraph-p1:b0"

    def test_the_node_carries_no_paragraph_text(self, document: Document) -> None:
        # Rule 3 of the ContentStream contract: nodes reference, never copy.
        node = _nodes(document, ContentKind.PARAGRAPH)[0]
        assert "First paragraph." not in node.model_dump_json()
        assert set(node.model_dump()) == {"object_id", "kind", "page_number", "order"}

    def test_the_node_lands_on_its_own_page(self, document: Document) -> None:
        assert all(n.page_number == 1 for n in _nodes(document, ContentKind.PARAGRAPH))


class TestBodyLineExclusion:
    def test_paragraph_owned_blocks_are_no_longer_body_lines(self, document: Document) -> None:
        owned = {b for p in document.paragraphs for b in p.source_block_ids}
        body = {n.object_id for n in _nodes(document, ContentKind.BODY_LINE)}
        assert owned & body == set()

    def test_unclaimed_blocks_are_still_body_lines(self, document: Document) -> None:
        # p1:b2 is the heading's anchor and p1:b5 is claimed by nothing.
        # Neither is a paragraph's, so both remain — BODY_LINE now means
        # "a block no semantic object claimed".
        body = {n.object_id for n in _nodes(document, ContentKind.BODY_LINE)}
        assert body == {"p1:b2", "p1:b5"}

    def test_the_stream_holds_no_object_twice(self, document: Document) -> None:
        ids = [n.object_id for n in build_content_stream(document).nodes]
        assert len(ids) == len(set(ids))


class TestOrdering:
    def test_a_paragraph_sits_where_its_first_block_sat(self, document: Document) -> None:
        stream = build_content_stream(document)
        by_order = [
            (n.kind.value, n.object_id) for n in sorted(stream.nodes, key=lambda n: n.order)
        ]
        assert by_order == [
            ("paragraph", "paragraph-p1:b0"),  # blocks 0-1
            ("heading", str(document.headings[0].id)),  # block 2
            ("body_line", "p1:b2"),
            ("paragraph", "paragraph-p1:b3"),  # blocks 3-4
            ("body_line", "p1:b5"),
        ]

    def test_corrected_reading_order_moves_the_paragraph(self, document: Document) -> None:
        # W-1's rail is the only reading-order mechanism; a paragraph
        # follows the block it begins at, so a reviewer's correction moves
        # it with no paragraph-specific ordering code.
        for block in document.blocks:
            block.corrected_order = {0: 5, 1: 6, 3: 0, 4: 1}.get(block.order, block.order + 10)

        order = [n.object_id for n in _nodes(document, ContentKind.PARAGRAPH)]
        assert order == ["paragraph-p1:b3", "paragraph-p1:b0"]

    def test_paragraphs_order_across_pages_by_page(self) -> None:
        blocks = [_block(0, page=1), _block(0, page=2)]
        paragraphs = [
            Paragraph(page_number=2, text="Second page.", source_block_ids=[blocks[1].block_id]),
            Paragraph(page_number=1, text="First page.", source_block_ids=[blocks[0].block_id]),
        ]
        document = _document(blocks, paragraphs, pages=2)

        nodes = _nodes(document, ContentKind.PARAGRAPH)
        assert [(n.page_number, n.object_id) for n in nodes] == [
            (1, "paragraph-p1:b0"),
            (2, "paragraph-p2:b0"),
        ]


class TestIdentityIsNotContent:
    def test_two_paragraphs_reading_identically_are_two_nodes(self) -> None:
        blocks = [_block(0), _block(1)]
        paragraphs = [
            Paragraph(
                page_number=1, text="The same sentence.", source_block_ids=[blocks[0].block_id]
            ),
            Paragraph(
                page_number=1, text="The same sentence.", source_block_ids=[blocks[1].block_id]
            ),
        ]
        document = _document(blocks, paragraphs)

        nodes = _nodes(document, ContentKind.PARAGRAPH)
        assert len(nodes) == 2
        assert nodes[0].object_id != nodes[1].object_id
        assert nodes[0].order != nodes[1].order

    def test_editing_the_text_does_not_change_the_node(self, document: Document) -> None:
        """The W-2b consequence, pinned: identity is not content.

        A reviewer's prose edit must move nothing in the traversal — if it
        did, every edit would invalidate every downstream reference to the
        paragraph's position.
        """
        before = [n.model_dump() for n in build_content_stream(document).nodes]

        document.paragraphs[0].text = "Completely different prose now."

        assert [n.model_dump() for n in build_content_stream(document).nodes] == before


class TestUnplaceableParagraphsAreNotGuessed:
    def test_a_paragraph_with_no_source_blocks_emits_nothing(self) -> None:
        # The Mathpix shape: a source_line in a coordinate system the
        # traversal does not share.
        blocks = [_block(0)]
        imported = Paragraph(page_number=1, text="Imported prose.", source_line=17)
        document = _document(blocks, [imported])

        assert _nodes(document, ContentKind.PARAGRAPH) == []

    def test_mathpix_paragraphs_do_not_displace_body_lines(self) -> None:
        # The safety half: emitting nothing must also claim nothing, or an
        # imported document would silently lose its lines.
        blocks = [_block(0), _block(1)]
        document = _document(blocks, [Paragraph(page_number=1, text="Imported.", source_line=4)])

        assert {n.object_id for n in _nodes(document, ContentKind.BODY_LINE)} == {
            "p1:b0",
            "p1:b1",
        }

    def test_a_paragraph_naming_an_unknown_block_emits_nothing(self) -> None:
        document = _document(
            [_block(0)],
            [Paragraph(page_number=1, text="Orphan.", source_block_ids=["p9:b9"])],
        )

        assert _nodes(document, ContentKind.PARAGRAPH) == []
        assert {n.object_id for n in _nodes(document, ContentKind.BODY_LINE)} == {"p1:b0"}


class TestOtherKindsAreUnaffected:
    def test_removing_paragraphs_changes_only_paragraph_and_body_counts(
        self, document: Document
    ) -> None:
        with_paragraphs = _kinds(document)
        document.paragraphs = []
        without = _kinds(document)

        for kind in (
            "page_marker",
            "heading",
            "list",
            "table",
            "image",
            "note_definition",
            "front_matter",
        ):
            assert with_paragraphs.get(kind, 0) == without.get(kind, 0), kind
        assert without["body_line"] == 6  # every block, as before this change
        assert with_paragraphs["body_line"] == 2
        assert with_paragraphs["paragraph"] == 2

    def test_heading_placement_is_unchanged(self, document: Document) -> None:
        heading = _nodes(document, ContentKind.HEADING)[0]
        document.paragraphs = []
        assert _nodes(document, ContentKind.HEADING)[0].object_id == heading.object_id


class TestPI8:
    def test_a_clean_document_passes(self, document: Document) -> None:
        report = check_paragraph_stream(document, "fixture")
        assert report.ok
        assert report.counts == {
            "paragraphs": 2,
            "placeable": 2,
            "in_stream": 2,
            "owned_blocks": 4,
            "body_line_nodes": 2,
        }

    def test_an_unplaceable_import_paragraph_is_a_finding_not_a_violation(self) -> None:
        document = _document([_block(0)], [Paragraph(page_number=1, text="X", source_line=4)])
        report = check_paragraph_stream(document, "mathpix")

        assert report.ok
        assert [v.kind for v in report.findings] == ["no_recorded_position"]

    def test_a_paragraph_naming_a_missing_block_is_a_violation(self) -> None:
        document = _document(
            [_block(0)], [Paragraph(page_number=1, text="X", source_block_ids=["p9:b9"])]
        )
        report = check_paragraph_stream(document, "broken-edge")

        assert not report.ok
        assert [v.kind for v in report.violations] == ["lost_object"]

    def test_two_paragraphs_claiming_one_block_is_a_violation(self) -> None:
        blocks = [_block(0)]
        document = _document(
            blocks,
            [
                Paragraph(page_number=1, text="A", source_block_ids=[blocks[0].block_id]),
                Paragraph(
                    page_number=1,
                    id="paragraph-second",
                    text="B",
                    source_block_ids=[blocks[0].block_id],
                ),
            ],
        )
        report = check_paragraph_stream(document, "shared-block")

        assert not report.ok
        assert any(v.kind == "duplicate" for v in report.violations)

    def test_duplicate_paragraph_ids_are_a_violation(self) -> None:
        blocks = [_block(0), _block(1)]
        document = _document(
            blocks,
            [
                Paragraph(
                    page_number=1, id="same", text="A", source_block_ids=[blocks[0].block_id]
                ),
                Paragraph(
                    page_number=1, id="same", text="B", source_block_ids=[blocks[1].block_id]
                ),
            ],
        )
        report = check_paragraph_stream(document, "duplicate-ids")

        assert not report.ok
        assert any(v.kind == "duplicate" for v in report.violations)

    def test_a_body_line_duplicating_a_paragraph_block_would_be_caught(
        self, document: Document, monkeypatch
    ) -> None:
        """The invariant's whole point, proven by breaking it.

        Exclusivity is asserted against a stream that really does emit the
        duplicate, so the check cannot pass vacuously.
        """
        import src.benchmark.projection as projection
        from src.models.content_stream import ContentNode, ContentStream

        real = build_content_stream(document)
        owned = document.paragraphs[0].source_block_ids[0]
        broken = ContentStream(
            nodes=real.nodes
            + [
                ContentNode(
                    object_id=owned,
                    kind=ContentKind.BODY_LINE,
                    page_number=1,
                    order=len(real.nodes),
                )
            ]
        )
        monkeypatch.setattr(
            "src.structure.content_stream.build_content_stream", lambda _doc: broken
        )

        report = projection.check_paragraph_stream(document, "injected-duplicate")

        assert not report.ok
        assert any("also emitted as a body line" in v.detail for v in report.violations)


def _real_document(pattern: str) -> Any:
    """A corpus document built by the real detectors, through the stages
    that decide what prose is.

    Deliberately not ``run_pipeline``: images, DOCX and validation change
    nothing this invariant reads, and paying for them would make a fast
    check slow enough to skip.
    """
    from src.footnotes.footnote_detector import detect_footnotes
    from src.frontmatter.front_matter_extractor import extract_front_matter
    from src.headings.heading_detector import detect_headings
    from src.ocr.extractor import extract_text
    from src.parser.pdf_parser import parse_pdf
    from src.structure.paragraph_assembly import assemble_paragraphs
    from src.structure.structure_detector import detect_structure

    pdf = next(BENCHMARK_PDFS.glob(pattern), None)
    if pdf is None:
        pytest.skip(f"{pattern} is not in the benchmark corpus")

    document = detect_structure(extract_text(parse_pdf(pdf)))
    document = detect_headings(extract_front_matter(detect_footnotes(document)))
    document.paragraphs = assemble_paragraphs(document)
    return document


@pytest.mark.skipif(not BENCHMARK_PDFS.is_dir(), reason="benchmark corpus not present")
class TestAgainstTheRealCorpus:
    """PI-8 over documents the detectors built, not fixtures.

    Properties, not counts. A paragraph total moves with every detector
    calibration — measured at 992 across the ten corpus PDFs through these
    stages, 745 through the full pipeline, which is the same documents and
    a different question — so pinning one would make this fail for reasons
    that are not the invariant's.
    """

    @pytest.mark.parametrize("pattern", ["7.brinkman*.pdf", "3. sockett*.pdf"])
    def test_every_placeable_paragraph_is_in_the_stream_once(self, pattern: str) -> None:
        report = check_paragraph_stream(_real_document(pattern), name=pattern)

        assert report.violations == []
        assert report.counts["paragraphs"] > 0
        assert report.counts["in_stream"] == report.counts["placeable"]
        assert report.counts["placeable"] == report.counts["paragraphs"]

    def test_no_surviving_body_line_is_unclaimed(self) -> None:
        """BODY_LINE's new meaning, measured rather than asserted.

        Every line that survives as a body line is one some *other* object
        claimed — a heading's anchor, or content a table, note, caption or
        the front matter absorbed. A line claimed by nothing would mean
        the assembler dropped prose the stream then emitted raw, which is
        the failure this kind's narrowing could plausibly cause. Zero on
        the corpus, both through these stages and the full pipeline.
        """
        from src.structure.paragraph_assembly import (
            absorbed_block_ids,
            heading_anchor_block_ids,
        )

        document = _real_document("7.brinkman*.pdf")
        by_page: dict = {}
        for block in document.blocks:
            by_page.setdefault(block.page_number, []).append(block)

        claimed = {bid for t in (document.tables or []) for bid in (t.source_block_ids or [])}
        for page, page_blocks in by_page.items():
            claimed |= heading_anchor_block_ids(document, page, page_blocks)
            claimed |= absorbed_block_ids(document, page, page_blocks)

        body = {
            n.object_id
            for n in build_content_stream(document).nodes
            if n.kind is ContentKind.BODY_LINE
        }
        assert body - claimed == set()
