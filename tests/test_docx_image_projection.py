"""P4c-3 — the DOCX projection materializes images and captions from the traversal.

DOCX used to learn that an image existed from a ``![alt](path)`` markdown line,
take the alt text off that line, and then use the *file path* as the image's
name for three model lookups: alignment, decorative state, and where to record
``embedded_in_docx``. A caption had no name at all — it was whatever italic line
followed an image.

Now an ``IMAGE`` node names the ``Image`` and the caption is read off
``Image.figure.caption``, which is a field of the image rather than a
neighbouring line. The corpus proves the common cases (122 images, 118 of them
on scanned pages with no prose at all) and proves none of these: decorative
images, failed extractions, a caption on a blockless page, two images sharing a
caption string, two images sharing a file path, and alt text containing the
characters that break the markdown pattern. Those are fixture claims below.
"""

import zipfile
from pathlib import Path
from typing import List, Optional, Tuple
from xml.etree import ElementTree as etree

import fitz

from src.benchmark.projection import check_image_projection
from src.docx.docx_generator import generate_docx
from src.markdown.markdown_builder import build_markdown
from src.models.bounding_box import BoundingBox
from src.models.contracts import Document, Metadata, Page, Paragraph, TextBlock
from src.models.figure import AltTextStatus, Figure
from src.models.image import Image

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def _png(path: Path, color=(255, 0, 0)) -> str:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 30))
    pix.set_rect(pix.irect, color)
    pix.save(str(path))
    return str(path)


def _image(
    image_id: str,
    path: str,
    page: int = 1,
    alt: Optional[str] = "alt",
    caption: Optional[str] = None,
    order: Optional[int] = 0,
    anchor: Optional[str] = None,
    status: Optional[AltTextStatus] = None,
    failed: bool = False,
    caption_source: Optional[str] = None,
) -> Image:
    return Image(
        image_id=image_id,
        page_number=page,
        file_path=path,
        document_order=order,
        source_block_id=anchor,
        extraction_failed=failed,
        bbox=BoundingBox(x0=100, y0=20, x1=300, y1=120),
        figure=Figure(
            alt_text=alt,
            alt_text_status=status,
            caption=caption,
            caption_source_text=caption_source,
        ),
    )


def _document(
    images: List[Image],
    prose_pages: Tuple[int, ...] = (1,),
    page_count: int = 1,
) -> Document:
    """A Document whose ``prose_pages`` carry a paragraph and whose other pages
    carry none — the blockless shape that holds 118 of the corpus' 122 images."""
    blocks, paragraphs = [], []
    for order, page in enumerate(prose_pages):
        block = TextBlock(
            page_number=page,
            text=f"Body text on page {page}.",
            bbox=BoundingBox(x0=72, y0=200 + order * 20, x1=400, y1=216 + order * 20),
            order=order,
        )
        blocks.append(block)
        paragraphs.append(
            Paragraph(
                page_number=page,
                text=block.text,
                source_block_ids=[block.block_id],
            )
        )
    return Document(
        source_pdf_path="images.pdf",
        metadata=Metadata(filename="images.pdf", page_count=page_count),
        pages=[
            Page(
                page_number=p,
                width_pt=612.0,
                height_pt=792.0,
                cleaned_text="\n".join(b.text for b in blocks if b.page_number == p),
            )
            for p in range(1, page_count + 1)
        ],
        blocks=blocks,
        paragraphs=paragraphs,
        images=images,
    )


def _render(document: Document, tmp_path: Path, markdown: Optional[str] = None) -> Path:
    out = tmp_path / "images.docx"
    generate_docx(
        document, markdown if markdown is not None else build_markdown(document), out
    )
    return out


def _body(path: Path) -> List[dict]:
    """Ordered body paragraphs: drawings with their docPr, text with its style."""
    with zipfile.ZipFile(str(path)) as zf:
        root = etree.fromstring(zf.read("word/document.xml"))
    body = root.find(_W + "body")
    items = []
    for paragraph in [] if body is None else body.findall(_W + "p"):
        text = "".join(t.text or "" for t in paragraph.iter(_W + "t")).strip()
        if list(paragraph.iter(_A + "graphic")):
            properties = next(iter(paragraph.iter(_WP + "docPr")), None)
            justification = paragraph.find(f"{_W}pPr/{_W}jc")
            items.append(
                {
                    "kind": "image",
                    "descr": None if properties is None else properties.get("descr"),
                    "title": None if properties is None else properties.get("title"),
                    "align": None if justification is None else justification.get(_W + "val"),
                }
            )
        elif text:
            italic = any(
                run.find(f"{_W}rPr/{_W}i") is not None for run in paragraph.findall(_W + "r")
            )
            justification = paragraph.find(f"{_W}pPr/{_W}jc")
            items.append(
                {
                    "kind": "text",
                    "text": text,
                    "italic": italic,
                    "center": justification is not None
                    and justification.get(_W + "val") == "center",
                }
            )
    return items


def _media(path: Path) -> List[str]:
    with zipfile.ZipFile(str(path)) as zf:
        return sorted(n for n in zf.namelist() if n.startswith("word/media/"))


class TestIdentity:
    def test_the_node_names_the_image_not_the_path(self, tmp_path):
        """Two images written to one path used to share alignment, decorative
        state and the embed flag, because the path was the only name DOCX had.
        They are two objects and render as two."""
        shared = _png(tmp_path / "shared.png")
        document = _document(
            [
                _image("img-a", shared, order=0, alt="First chart", caption="Figure 1."),
                _image(
                    "img-b",
                    shared,
                    order=1,
                    alt="Second chart",
                    status=AltTextStatus.DECORATIVE,
                ),
            ]
        )
        body = _body(_render(document, tmp_path))
        images = [item for item in body if item["kind"] == "image"]
        assert len(images) == 2
        assert images[0]["descr"] == "First chart"
        # Decorative wins over alt text: descr and title are set empty so a
        # screen reader skips the image entirely.
        assert images[1]["descr"] == ""
        assert images[1]["title"] == ""
        assert [i.embedded_in_docx for i in document.images] == [True, True]

    def test_alt_text_that_markdown_cannot_carry_survives(self, tmp_path):
        """``_IMAGE_PATTERN`` is ``!\\[([^\\]]*)\\]\\(([^)]+)\\)``, so an alt
        text containing ``]`` or ``)`` was unparseable and a newline made the
        line unmatchable. The model holds the string; nothing re-parses it."""
        alt = "Chart [fig] showing y (in %)\nsecond line"
        document = _document([_image("img-a", _png(tmp_path / "a.png"), alt=alt)])
        images = [i for i in _body(_render(document, tmp_path)) if i["kind"] == "image"]
        assert len(images) == 1
        # _safe_run_text may normalize control characters; the bracket and
        # paren content is what the markdown line could not have carried.
        assert "[fig]" in images[0]["descr"] and "(in %)" in images[0]["descr"]

    def test_a_failed_extraction_has_a_node_and_renders_nothing(self, tmp_path):
        """The image has an ``IMAGE`` node but no file. ``_render_images`` has
        always skipped it; a node walk that did not would try to embed nothing
        and stamp ``embedded_in_docx=False`` on it."""
        good = _image("img-a", _png(tmp_path / "a.png"), order=0)
        failed = _image("img-b", str(tmp_path / "gone.png"), order=1, failed=True)
        document = _document([good, failed])
        images = [i for i in _body(_render(document, tmp_path)) if i["kind"] == "image"]
        assert len(images) == 1
        assert good.embedded_in_docx is True
        assert failed.embedded_in_docx is None


class TestCaptions:
    def test_a_caption_follows_its_own_image(self, tmp_path):
        document = _document(
            [
                _image(
                    "img-a", _png(tmp_path / "a.png"), order=0, caption="Figure 1. Alpha."
                ),
                _image(
                    "img-b", _png(tmp_path / "b.png"), order=1, caption="Figure 2. Beta."
                ),
            ]
        )
        body = _body(_render(document, tmp_path))
        pairs = [
            (body[i]["descr"], body[i + 1])
            for i in range(len(body) - 1)
            if body[i]["kind"] == "image"
        ]
        assert len(pairs) == 2
        for _, caption in pairs:
            assert caption["kind"] == "text" and caption["italic"] and caption["center"]
        assert [caption["text"] for _, caption in pairs] == [
            "Figure 1. Alpha.",
            "Figure 2. Beta.",
        ]

    def test_two_images_may_share_a_caption_string(self, tmp_path):
        """The caption is a field of its image, so an identical string on two
        images is two captions. Recovered by adjacency it was ambiguous."""
        document = _document(
            [
                _image("img-a", _png(tmp_path / "a.png"), order=0, caption="Figure 1."),
                _image("img-b", _png(tmp_path / "b.png"), order=1, caption="Figure 1."),
            ]
        )
        body = _body(_render(document, tmp_path))
        captions = [
            i for i in body if i["kind"] == "text" and i["italic"] and i["center"]
        ]
        assert [c["text"] for c in captions] == ["Figure 1.", "Figure 1."]

    def test_a_caption_renders_on_a_page_with_no_prose(self, tmp_path):
        """24 of the corpus' image-bearing pages are blockless and 0 of them
        carry a caption, so this case is fixture-only. The caption must not
        depend on the page being a stream page."""
        document = _document(
            [
                _image(
                    "img-a", _png(tmp_path / "a.png"), page=2, caption="Figure 1. Scan."
                )
            ],
            prose_pages=(1,),
            page_count=2,
        )
        body = _body(_render(document, tmp_path))
        index = next(i for i, item in enumerate(body) if item["kind"] == "image")
        assert body[index + 1]["text"] == "Figure 1. Scan."
        assert body[index + 1]["italic"] and body[index + 1]["center"]

    def test_a_bold_line_after_an_image_is_not_eaten_as_a_caption(self, tmp_path):
        """``_CAPTION_PATTERN`` is ``^\\*(.+)\\*$``, which matches ``**Bold**``
        too — the corpus has 20 single-line italic/bold blocks against 2 real
        captions. An image with no caption leaves the following line alone."""
        document = _document([_image("img-a", _png(tmp_path / "a.png"), caption=None)])
        markdown = build_markdown(document).replace(
            "Body text on page 1.", "**A bold heading-ish line**"
        )
        body = _body(_render(document, tmp_path, markdown))
        assert not [
            i for i in body if i["kind"] == "text" and i["italic"] and i["center"]
        ]


class TestPlacement:
    def test_an_image_before_the_prose_stays_before_it(self, tmp_path):
        """``source_block_id is None`` with a real ``document_order`` means the
        image precedes every body line on its page."""
        document = _document([_image("img-a", _png(tmp_path / "a.png"), anchor=None)])
        body = _body(_render(document, tmp_path))
        kinds = [i["kind"] for i in body]
        assert kinds.index("image") < len(kinds) - 1
        assert body[-1]["kind"] == "text" and body[-1]["text"] == "Body text on page 1."

    def test_an_anchored_image_follows_the_line_it_is_anchored_to(self, tmp_path):
        document = _document([_image("img-a", _png(tmp_path / "a.png"))])
        document.images[0].source_block_id = document.blocks[0].block_id
        body = _body(_render(document, tmp_path))
        kinds = [i["kind"] for i in body]
        assert kinds.index("image") > kinds.index("text")

    def test_a_blockless_page_still_renders_its_images(self, tmp_path):
        """``is_stream_page()`` is False on all 24 blockless corpus pages, and
        118 of 122 images are on one. Emission keys on the image's own node."""
        document = _document(
            [
                _image("img-a", _png(tmp_path / "a.png"), page=2, order=0),
                # A different colour, so python-docx cannot fold the two into
                # one media part on identical bytes and hide a lost embed.
                _image(
                    "img-b", _png(tmp_path / "b.png", color=(0, 0, 255)), page=2, order=1
                ),
            ],
            prose_pages=(1,),
            page_count=2,
        )
        path = _render(document, tmp_path)
        assert len([i for i in _body(path) if i["kind"] == "image"]) == 2
        assert len(_media(path)) == 2

    def test_images_render_in_traversal_order_not_model_order(self, tmp_path):
        """``document.images`` is the extractor's order; ``document_order`` is
        reading order, and on the corpus the two disagree on 17 of 22
        image-bearing scanned pages."""
        document = _document(
            [
                _image("img-a", _png(tmp_path / "a.png"), page=2, order=1, alt="second"),
                _image("img-b", _png(tmp_path / "b.png"), page=2, order=0, alt="first"),
            ],
            prose_pages=(1,),
            page_count=2,
        )
        body = _body(_render(document, tmp_path))
        assert [i["descr"] for i in body if i["kind"] == "image"] == ["first", "second"]


class TestMarkdownFallback:
    def test_a_document_with_no_traversal_still_renders_its_image_line(self, tmp_path):
        """Hand-written markdown handed straight to generate_docx: no pages, no
        nodes, so the line is the only record of the image there is."""
        png = _png(tmp_path / "a.png")
        document = Document(
            source_pdf_path="hand.pdf",
            metadata=Metadata(filename="hand.pdf", page_count=1),
        )
        body = _body(
            _render(document, tmp_path, f"![Hand written]({png})\n\n*A caption*")
        )
        images = [i for i in body if i["kind"] == "image"]
        assert len(images) == 1 and images[0]["descr"] == "Hand written"
        assert [i["text"] for i in body if i["kind"] == "text"] == ["A caption"]

    def test_a_markdown_image_the_model_does_not_hold_is_kept(self, tmp_path):
        """A traversal that placed this document's images does not license
        dropping a line naming an image it never saw."""
        placed = _png(tmp_path / "a.png")
        stray = _png(tmp_path / "stray.png", color=(0, 0, 255))
        document = _document([_image("img-a", placed, alt="placed")])
        markdown = build_markdown(document) + f"\n\n![Stray]({stray})"
        images = [
            i for i in _body(_render(document, tmp_path, markdown)) if i["kind"] == "image"
        ]
        assert [i["descr"] for i in images] == ["placed", "Stray"]


class TestPI13:
    def test_a_clean_document_has_no_violations(self, tmp_path):
        document = _document(
            [
                _image("img-a", _png(tmp_path / "a.png"), order=0, caption="Figure 1."),
                _image("img-b", _png(tmp_path / "b.png"), order=1, alt="Bee"),
            ]
        )
        report = check_image_projection(
            document, _render(document, tmp_path), name="clean"
        )
        assert report.violations == []
        assert report.counts["images"] == 2
        assert report.counts["rendered_images"] == 2
        assert report.counts["captions"] == report.counts["rendered_captions"] == 1

    def test_a_mispaired_alt_text_is_caught(self, tmp_path):
        """The check that set membership cannot make: 122 corpus images share
        24 placeholder alt texts, so "every descr is a model alt text" holds
        even when every image carries its neighbour's."""
        document = _document(
            [
                _image("img-a", _png(tmp_path / "a.png"), order=0, alt="Alpha"),
                _image("img-b", _png(tmp_path / "b.png"), order=1, alt="Beta"),
            ]
        )
        path = _render(document, tmp_path)
        document.images[0].figure.alt_text = "Beta"
        document.images[1].figure.alt_text = "Alpha"
        report = check_image_projection(document, path, name="swapped")
        assert [v.kind for v in report.violations] == ["content_loss", "content_loss"]

    def test_a_caption_that_also_renders_as_prose_is_caught(self, tmp_path):
        document = _document(
            [
                _image(
                    "img-a",
                    _png(tmp_path / "a.png"),
                    caption="Figure 1. Alpha.",
                    caption_source="Body text on page 1.",
                )
            ]
        )
        report = check_image_projection(
            document, _render(document, tmp_path), name="leak"
        )
        assert [v.kind for v in report.violations] == ["duplicate"]
        assert report.counts["leaked_caption_lines"] == 1

    def test_a_document_with_no_images_is_vacuously_clean(self, tmp_path):
        document = _document([])
        report = check_image_projection(
            document, _render(document, tmp_path), name="none"
        )
        assert report.violations == [] and report.counts["images"] == 0
