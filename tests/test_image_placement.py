"""P-IMG: the model owns where an image sits, not the renderer.

Image was the only ordered object type with no ordering field, so every
consumer put images after a page's body text — not because that was right,
but because the model could not say anything else. ``_render_images()``
admitted as much in its own comment and ``build_content_stream`` inherited
the same approximation.

These lock the *edge*, not one renderer's output: the anchor rule, the two
consumers reading it, and the fallback for images the model genuinely
cannot place. The fallback matters as much as the fix — an image with no
bbox (the Mathpix path) or a Document that never ran Stage 5c must keep its
previous placement, or this becomes a regression dressed as an improvement.
"""

from types import SimpleNamespace
from typing import Optional

from src.markdown.markdown_builder import build_markdown
from src.models.content_stream import ContentKind
from src.models.contracts import (
    BoundingBox,
    Document,
    Figure,
    Heading,
    HeadingLevel,
    Image,
    Metadata,
    Page,
    TextBlock,
)
from src.structure.content_stream import build_content_stream
from src.structure.relationships import link_document


def _block(text: str, order: int, y: float, page: int = 1) -> TextBlock:
    return TextBlock(
        page_number=page,
        text=text,
        bbox=BoundingBox(x0=50.0, y0=y, x1=250.0, y1=y + 10.0),
        order=order,
        source_block_index=0,
    )


def _image(
    image_id: str, page: int = 1, y: float = 200.0, caption: Optional[str] = None
) -> Image:
    return Image(
        image_id=image_id,
        page_number=page,
        file_path=f"outputs/images/{image_id}.png",
        width=100,
        height=100,
        bbox=BoundingBox(x0=50.0, y0=y, x1=250.0, y1=y + 80.0),
        figure=Figure(caption=caption, alt_text="alt") if caption else None,
    )


def _bare_doc(**overrides):
    """A duck-typed document — link_document reads three attributes."""
    base = dict(blocks=[], tables=[], images=[])
    base.update(overrides)
    return SimpleNamespace(**base)


def _document(blocks, images, pages: int = 1) -> Document:
    """A real Document whose page text is its blocks, in order.

    markdown_builder walks a page's text lines in lockstep with its blocks,
    so a fixture that lets them disagree tests the drift fallback rather
    than the placement rule.
    """
    page_text = {n: [] for n in range(1, pages + 1)}
    for block in sorted(blocks, key=lambda b: (b.page_number, b.order)):
        page_text[block.page_number].append(block.text)
    return Document(
        source_pdf_path="x.pdf",
        metadata=Metadata(filename="x.pdf", page_count=pages),
        pages=[
            Page(
                page_number=n,
                raw_text="\n".join(page_text[n]),
                cleaned_text="\n".join(page_text[n]),
            )
            for n in range(1, pages + 1)
        ],
        blocks=list(blocks),
        images=list(images),
    )


class TestTheAnchorEdge:
    def test_the_anchor_is_the_last_line_above_the_image(self) -> None:
        blocks = [_block("above", 0, y=100.0), _block("below", 1, y=300.0)]
        image = _image("i1", y=200.0)
        link_document(_bare_doc(blocks=blocks, images=[image]))
        assert image.source_block_id == "p1:b0"

    def test_an_image_above_all_body_text_anchors_to_nothing(self) -> None:
        # None is a real answer — "before everything" — not a missing one, so
        # it must still carry an order.
        image = _image("i1", y=50.0)
        link_document(_bare_doc(blocks=[_block("body", 0, y=100.0)], images=[image]))
        assert image.source_block_id is None
        assert image.document_order == 0

    def test_a_touching_edge_still_counts_as_above(self) -> None:
        # A line whose bottom is exactly the image's top is the line the
        # image follows; excluding it would push the image up a paragraph.
        image = _image("i1", y=110.0)
        link_document(_bare_doc(blocks=[_block("above", 0, y=100.0)], images=[image]))
        assert image.source_block_id == "p1:b0"

    def test_an_image_with_no_bbox_gets_no_position(self) -> None:
        # The Mathpix path: no PDF-side geometry to anchor against. Both
        # fields stay None so consumers fall back rather than guess.
        image = Image(image_id="i1", page_number=1, file_path="x.png")
        link_document(_bare_doc(blocks=[_block("body", 0, y=100.0)], images=[image]))
        assert image.source_block_id is None
        assert image.document_order is None

    def test_only_same_page_blocks_are_considered(self) -> None:
        image = _image("i1", page=2, y=500.0)
        link_document(_bare_doc(blocks=[_block("page one", 0, y=100.0)], images=[image]))
        assert image.source_block_id is None

    def test_document_order_runs_across_pages(self) -> None:
        blocks = [_block("p1 line", 0, y=100.0), _block("p2 line", 0, y=100.0, page=2)]
        second = _image("i2", page=2, y=200.0)
        first = _image("i1", page=1, y=200.0)
        link_document(_bare_doc(blocks=blocks, images=[second, first]))
        # List order is not document order: page 1's image precedes page 2's.
        assert (first.document_order, second.document_order) == (0, 1)

    def test_two_images_after_one_line_keep_their_vertical_order(self) -> None:
        lower = _image("lower", y=400.0)
        upper = _image("upper", y=200.0)
        link_document(_bare_doc(blocks=[_block("above", 0, y=100.0)], images=[lower, upper]))
        assert (upper.document_order, lower.document_order) == (0, 1)

    def test_relinking_is_idempotent(self) -> None:
        # Stage 5c may run more than once on a stored document; a second
        # pass must not renumber anything.
        image = _image("i1", y=200.0)
        doc = _bare_doc(blocks=[_block("above", 0, y=100.0)], images=[image])
        link_document(doc)
        before = (image.source_block_id, image.document_order)
        link_document(doc)
        assert (image.source_block_id, image.document_order) == before

    def test_a_stale_anchor_is_recomputed_not_kept(self) -> None:
        # The edge is derived. Re-linking after the geometry changed must
        # produce the new answer, not preserve the old one.
        image = _image("i1", y=200.0)
        image.source_block_id = "p1:b99"
        link_document(_bare_doc(blocks=[_block("above", 0, y=100.0)], images=[image]))
        assert image.source_block_id == "p1:b0"


class TestMarkdownPlacement:
    def test_an_image_renders_at_its_anchor_not_at_the_page_end(self) -> None:
        blocks = [_block("first line", 0, y=100.0), _block("second line", 1, y=400.0)]
        image = _image("i1", y=200.0)
        document = link_document(_document(blocks, [image]))
        markdown = build_markdown(document)

        assert markdown.index("first line") < markdown.index("![") < markdown.index("second line")

    def test_an_anchorless_image_renders_before_the_body(self) -> None:
        blocks = [_block("first line", 0, y=100.0)]
        image = _image("i1", y=20.0)
        markdown = build_markdown(link_document(_document(blocks, [image])))

        assert markdown.index("![") < markdown.index("first line")

    def test_an_unlinked_document_keeps_the_page_end_slot(self) -> None:
        # No Stage 5c: the model has said nothing, so the projection must
        # not invent a position. This is the pre-P-IMG behaviour, unchanged.
        blocks = [_block("first line", 0, y=100.0), _block("second line", 1, y=400.0)]
        markdown = build_markdown(_document(blocks, [_image("i1", y=200.0)]))

        assert markdown.index("second line") < markdown.index("![")

    def test_every_image_is_realized_exactly_once(self) -> None:
        # PI-1/PI-5: an object is materialized or diagnosed, never both and
        # never neither. Placement must not become a way to lose one.
        blocks = [_block("first line", 0, y=100.0), _block("second line", 1, y=400.0)]
        images = [_image("i1", y=200.0), _image("i2", y=500.0), _image("i3", y=20.0)]
        markdown = build_markdown(link_document(_document(blocks, images)))

        for image in images:
            assert markdown.count(image.file_path) == 1

    def test_an_image_anchored_to_a_heading_still_lands(self) -> None:
        # The heading branch used to `continue` before images were consulted.
        blocks = [_block("A Heading", 0, y=100.0), _block("body line", 1, y=400.0)]
        document = _document(blocks, [_image("i1", y=200.0)])
        document.headings.append(
            Heading(
                level=HeadingLevel.H2,
                text="A Heading",
                page_number=1,
                document_order=0,
                source_block_id="p1:b0",
            )
        )
        markdown = build_markdown(link_document(document))

        assert markdown.index("## A Heading") < markdown.index("![") < markdown.index("body line")

    def test_a_failed_extraction_still_renders_nothing(self) -> None:
        blocks = [_block("first line", 0, y=100.0)]
        image = _image("i1", y=200.0)
        image.extraction_failed = True
        markdown = build_markdown(link_document(_document(blocks, [image])))

        assert "![" not in markdown

    def test_a_caption_follows_its_image_to_the_new_position(self) -> None:
        blocks = [_block("first line", 0, y=100.0), _block("second line", 1, y=400.0)]
        image = _image("i1", y=200.0, caption="Figure 1. A caption.")
        markdown = build_markdown(link_document(_document(blocks, [image])))

        assert markdown.index("![") < markdown.index("*Figure 1. A caption.*")
        assert markdown.index("*Figure 1. A caption.*") < markdown.index("second line")


class TestContentStreamPlacement:
    def test_the_image_node_sits_at_its_anchor(self) -> None:
        blocks = [_block("first line", 0, y=100.0), _block("second line", 1, y=400.0)]
        document = link_document(_document(blocks, [_image("i1", y=200.0)]))
        kinds = [n.kind for n in build_content_stream(document).nodes]

        assert kinds == [ContentKind.BODY_LINE, ContentKind.IMAGE, ContentKind.BODY_LINE]

    def test_an_anchorless_image_node_leads_the_page_body(self) -> None:
        document = link_document(_document([_block("body", 0, y=100.0)], [_image("i1", y=20.0)]))
        kinds = [n.kind for n in build_content_stream(document).nodes]

        assert kinds == [ContentKind.IMAGE, ContentKind.BODY_LINE]

    def test_an_unlinked_document_keeps_images_after_the_body(self) -> None:
        blocks = [_block("first line", 0, y=100.0), _block("second line", 1, y=400.0)]
        document = _document(blocks, [_image("i1", y=200.0)])
        kinds = [n.kind for n in build_content_stream(document).nodes]

        assert kinds == [ContentKind.BODY_LINE, ContentKind.BODY_LINE, ContentKind.IMAGE]

    def test_the_node_references_the_image_by_id(self) -> None:
        document = link_document(_document([_block("body", 0, y=100.0)], [_image("i1", y=200.0)]))
        node = next(n for n in build_content_stream(document).nodes if n.kind is ContentKind.IMAGE)

        assert node.object_id == "i1"
