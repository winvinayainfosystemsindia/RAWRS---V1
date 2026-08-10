"""P3b — the Markdown projection renders the traversal's paragraphs.

Before this, prose placement was rediscovered at render time: the page's
text lines were walked in lockstep with its TextBlocks, one block consumed
per non-blank line, and each block asked whether some paragraph happened to
start at it. The ContentStream already knew the answer — P3a put it there —
and the renderer computed it again from lines.

What these tests pin is that the stream is now the traversal: a PARAGRAPH
node names a Paragraph, the projection resolves it *by id*, and renders
``Paragraph.text``. The distinction matters most where text cannot
disambiguate — two paragraphs reading identically, a reviewer's edit, a
corrected reading order — because those are the cases a text-keyed renderer
gets wrong while looking correct.

The adjacency cases (heading, image, table, note, page boundary) are here
because the walk that was replaced interleaved all of them in one loop, so
each is a chance for the new walk to drop or reorder something.
"""

from pathlib import Path
from typing import List, Optional

import pytest

from src.benchmark.projection import check_paragraph_projection
from src.markdown.markdown_builder import build_markdown
from src.models.bounding_box import BoundingBox
from src.models.contracts import (
    Document,
    Footnote,
    Heading,
    HeadingLevel,
    Metadata,
    NoteType,
    Page,
    Paragraph,
    Table,
    TableCell,
    TableRow,
    TextBlock,
)

BENCHMARK_PDFS = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"


def _block(order: int, text: str, page: int = 1) -> TextBlock:
    return TextBlock(
        page_number=page,
        text=text,
        bbox=BoundingBox(x0=72, y0=40 + order * 20, x1=400, y1=56 + order * 20),
        order=order,
    )


def _document(
    blocks: List[TextBlock],
    paragraphs: List[Paragraph],
    headings: Optional[List[Heading]] = None,
    pages: int = 1,
    **kwargs,
) -> Document:
    return Document(
        source_pdf_path="x.pdf",
        metadata=Metadata(filename="x.pdf", page_count=pages),
        pages=[
            Page(
                page_number=n,
                cleaned_text="\n".join(b.text for b in blocks if b.page_number == n),
            )
            for n in range(1, pages + 1)
        ],
        blocks=blocks,
        paragraphs=paragraphs,
        headings=headings or [],
        **kwargs,
    )


def _prose(markdown: str) -> List[str]:
    """Body blocks only — no marker, no pagebreak, no heading, no note."""
    return [
        line.strip()
        for line in markdown.splitlines()
        if line.strip()
        and not line.startswith("#")
        and not line.startswith("<!--")
        and not line.startswith("[^")
    ]


@pytest.fixture
def document() -> Document:
    blocks = [_block(0, "First line."), _block(1, "second line."), _block(2, "A closing one.")]
    paragraphs = [
        Paragraph(
            page_number=1,
            text="First line. second line.",
            source_block_ids=[blocks[0].block_id, blocks[1].block_id],
        ),
        Paragraph(page_number=1, text="A closing one.", source_block_ids=[blocks[2].block_id]),
    ]
    return _document(blocks, paragraphs)


class TestResolutionByIdentity:
    def test_each_stream_paragraph_renders_once(self, document: Document) -> None:
        assert _prose(build_markdown(document)) == [
            "First line. second line.",
            "A closing one.",
        ]

    def test_the_rendered_text_is_the_semantic_objects(self, document: Document) -> None:
        """The paragraph's text, not its blocks' text rejoined.

        ``Paragraph.text`` is a transformed string — hyphen repair and
        same-baseline merging happened during grouping — so a renderer that
        rebuilt prose from TextBlocks would produce something subtly
        different from what the model says the paragraph says.
        """
        document.paragraphs[0].text = "Repaired hyphenation and merged fragments."
        markdown = build_markdown(document)

        assert "Repaired hyphenation and merged fragments." in _prose(markdown)
        assert "First line. second line." not in markdown

    def test_a_paragraph_whose_blocks_are_gone_still_renders(self, document: Document) -> None:
        # Identity is the handle, not the blocks: a paragraph is placed by
        # its first block and rendered from its own text, so losing the
        # inline-formatting lookup cannot lose the prose.
        document.paragraphs[1].source_block_ids = [document.blocks[2].block_id, "p1:b99"]

        assert "A closing one." in _prose(build_markdown(document))

    def test_an_edit_to_paragraph_text_reaches_markdown(self, document: Document) -> None:
        # W-2b's reviewer edit writes Paragraph.text; nothing else has to
        # know, which is the whole reason prose is edited on the model.
        document.paragraphs[0].text = "The reviewer rewrote this sentence."

        assert "The reviewer rewrote this sentence." in _prose(build_markdown(document))


class TestIdentityIsNotText:
    def test_two_paragraphs_with_identical_text_both_render(self) -> None:
        blocks = [_block(0, "Same words here."), _block(1, "Same words here.")]
        paragraphs = [
            Paragraph(
                page_number=1, text="Same words here.", source_block_ids=[blocks[0].block_id]
            ),
            Paragraph(
                page_number=1, text="Same words here.", source_block_ids=[blocks[1].block_id]
            ),
        ]

        assert _prose(build_markdown(_document(blocks, paragraphs))) == [
            "Same words here.",
            "Same words here.",
        ]

    def test_editing_one_of_two_identical_paragraphs_changes_only_that_one(self) -> None:
        """The property a text-keyed renderer cannot have.

        Rediscovering paragraphs by text would match the first occurrence
        twice, or the wrong one; identity keeps them independent.
        """
        blocks = [_block(0, "Same words here."), _block(1, "Same words here.")]
        paragraphs = [
            Paragraph(
                page_number=1, text="Same words here.", source_block_ids=[blocks[0].block_id]
            ),
            Paragraph(
                page_number=1, text="Same words here.", source_block_ids=[blocks[1].block_id]
            ),
        ]
        document = _document(blocks, paragraphs)
        document.paragraphs[1].text = "Only the second changed."

        assert _prose(build_markdown(document)) == [
            "Same words here.",
            "Only the second changed.",
        ]

    def test_corrected_reading_order_reorders_the_prose(self, document: Document) -> None:
        # The reviewer's reading-order correction is the only ordering
        # mechanism; the paragraph follows the block it begins at, and the
        # projection follows the stream.
        for block in document.blocks:
            block.corrected_order = {0: 5, 1: 6, 2: 0}.get(block.order, block.order)

        assert _prose(build_markdown(document)) == [
            "A closing one.",
            "First line. second line.",
        ]


class TestAdjacency:
    """Each neighbour the replaced loop used to interleave by hand."""

    def test_paragraph_adjacent_to_a_heading(self) -> None:
        blocks = [_block(0, "A Heading"), _block(1, "Body prose follows.")]
        heading = Heading(
            text="A Heading",
            level=HeadingLevel.H2,
            page_number=1,
            document_order=0,
            source_block_id=blocks[0].block_id,
        )
        paragraphs = [
            Paragraph(
                page_number=1,
                text="Body prose follows.",
                source_block_ids=[blocks[1].block_id],
            )
        ]
        markdown = build_markdown(_document(blocks, paragraphs, [heading]))

        assert markdown.index("## A Heading") < markdown.index("Body prose follows.")

    def test_two_adjacent_paragraphs_keep_their_order(self) -> None:
        blocks = [_block(0, "Alpha."), _block(1, "Beta."), _block(2, "Gamma.")]
        paragraphs = [
            Paragraph(page_number=1, text=text, source_block_ids=[block.block_id])
            for text, block in zip(("Alpha.", "Beta.", "Gamma."), blocks)
        ]

        assert _prose(build_markdown(_document(blocks, paragraphs))) == [
            "Alpha.",
            "Beta.",
            "Gamma.",
        ]

    def test_paragraph_adjacent_to_a_table(self) -> None:
        # A table's own lines are absorbed, so they are not prose; the
        # paragraph beside it must still render, and exactly once.
        blocks = [_block(0, "Intro prose."), _block(1, "Cell A | Cell B")]
        table = Table(
            page_number=1,
            table_id="table-p1-0",
            row_count=1,
            col_count=2,
            rows=[
                TableRow(
                    cells=[
                        TableCell(text="Cell A", row_index=0, col_index=0),
                        TableCell(text="Cell B", row_index=0, col_index=1),
                    ]
                )
            ],
            source_block_ids=[blocks[1].block_id],
        )
        paragraphs = [
            Paragraph(page_number=1, text="Intro prose.", source_block_ids=[blocks[0].block_id])
        ]
        markdown = build_markdown(_document(blocks, paragraphs, tables=[table]))

        assert markdown.count("Intro prose.") == 1

    def test_paragraph_adjacent_to_a_note_anchor(self) -> None:
        blocks = [_block(0, "Prose with a marker.1")]
        note = Footnote(
            number=1,
            marker="1",
            anchor_page_number=1,
            body_page_number=1,
            anchor_text="Prose with a marker.1",
            body="The note body.",
            body_source_text="1 The note body.",
            note_type=NoteType.FOOTNOTE,
        )
        paragraphs = [
            Paragraph(
                page_number=1,
                text="Prose with a marker.1",
                source_block_ids=[blocks[0].block_id],
            )
        ]
        markdown = build_markdown(_document(blocks, paragraphs, footnotes=[note]))

        assert f"[^{note.label}]: The note body." in markdown
        assert "Prose with a marker." in markdown

    def test_paragraph_at_the_start_and_end_of_a_page(self) -> None:
        blocks = [_block(0, "Opens page one."), _block(0, "Opens page two.", page=2)]
        paragraphs = [
            Paragraph(
                page_number=1, text="Opens page one.", source_block_ids=[blocks[0].block_id]
            ),
            Paragraph(
                page_number=2, text="Opens page two.", source_block_ids=[blocks[1].block_id]
            ),
        ]
        markdown = build_markdown(_document(blocks, paragraphs, pages=2))

        assert (
            markdown.index("Opens page one.")
            < markdown.index("<!-- pagebreak -->")
            < markdown.index("Opens page two.")
        )

    def test_a_page_boundary_does_not_merge_paragraphs(self) -> None:
        blocks = [_block(0, "Page one prose."), _block(0, "Page two prose.", page=2)]
        paragraphs = [
            Paragraph(
                page_number=1, text="Page one prose.", source_block_ids=[blocks[0].block_id]
            ),
            Paragraph(
                page_number=2, text="Page two prose.", source_block_ids=[blocks[1].block_id]
            ),
        ]

        assert _prose(build_markdown(_document(blocks, paragraphs, pages=2))) == [
            "Page one prose.",
            "Page two prose.",
        ]


class TestUnplaceableParagraphsAreSafe:
    def test_a_block_no_paragraph_claims_renders_nothing(self) -> None:
        """A BODY_LINE node emits nothing, exactly as before P3b.

        The document must already carry paragraphs for this to be
        reachable: ``build_markdown`` assembles them for a Document that
        never ran Stage 5c, and the assembler would claim the loose block.
        """
        blocks = [_block(0, "Claimed prose."), _block(1, "A line nothing claims.")]
        paragraphs = [
            Paragraph(page_number=1, text="Claimed prose.", source_block_ids=[blocks[0].block_id])
        ]

        assert _prose(build_markdown(_document(blocks, paragraphs))) == ["Claimed prose."]

    def test_a_paragraph_cannot_be_empty_in_the_first_place(self) -> None:
        # The stray-empty-block case the projection would have to guard is
        # unreachable: the model rejects it, so the guard would be dead code.
        with pytest.raises(ValueError):
            Paragraph(page_number=1, text="", source_block_ids=["p1:b0"])

    def test_a_paragraph_naming_a_missing_block_is_not_invented(self) -> None:
        # The stream cannot place a paragraph whose first block is not in
        # the document, so it emits no node for it — and this path must not
        # render it either, which would be the projection guessing a
        # position the model never recorded.
        blocks = [_block(0, "Placed prose.")]
        paragraphs = [
            Paragraph(page_number=1, text="Placed prose.", source_block_ids=[blocks[0].block_id]),
            Paragraph(page_number=1, text="Orphan prose.", source_block_ids=["p9:b99"]),
        ]
        markdown = build_markdown(_document(blocks, paragraphs))

        assert "Placed prose." in markdown
        assert "Orphan prose." not in markdown


class TestPI9:
    def test_a_clean_document_passes(self, document: Document) -> None:
        report = check_paragraph_projection(document, build_markdown(document), "fixture")

        assert report.ok
        assert report.counts["stream_paragraphs"] == 2
        assert report.counts["expected_rendered"] == 2

    def test_a_dropped_paragraph_is_a_violation(self, document: Document) -> None:
        markdown = build_markdown(document).replace("A closing one.", "")
        report = check_paragraph_projection(document, markdown, "dropped")

        assert not report.ok
        assert [v.kind for v in report.violations] == ["content_loss"]

    def test_paragraphs_rendered_out_of_stream_order_are_a_violation(
        self, document: Document
    ) -> None:
        """Order is the property that catches a text-keyed regression."""
        markdown = "\n\n".join(
            ["###### Page 1", "A closing one.", "First line. second line.", "<!-- pagebreak -->"]
        )
        report = check_paragraph_projection(document, markdown, "reordered")

        assert not report.ok
        assert any(v.kind == "duplicate" for v in report.violations)


@pytest.mark.skipif(not BENCHMARK_PDFS.is_dir(), reason="benchmark corpus not present")
class TestAgainstTheRealCorpus:
    @pytest.mark.parametrize("pattern", ["7.brinkman*.pdf", "5.Teachingas*.pdf"])
    def test_every_stream_paragraph_is_rendered_in_order(self, pattern: str) -> None:
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

        report = check_paragraph_projection(document, build_markdown(document), name=pdf.name)

        assert report.violations == []
        assert report.counts["stream_paragraphs"] > 0
