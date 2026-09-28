"""Repairs found in a real scanned-chapter output (O'Leary, Mathpix route):
pages collapsing onto the last page, Markdown-style MMD headings and images
ignored, figure captions dropped, a flat and noisy heading outline, figures
stretched to full width, filename titles and printer names as metadata, and
sentences left open at page ends on line-rendered pages."""

from types import SimpleNamespace

from src.docx.docx_generator import (
    _complete_sentences_across_page_breaks,
    _looks_like_a_filename,
    _named_in_document,
    _printed_size,
)
from src.headings.hierarchy import repair_headings
from src.mathpix.mmd_parser import parse_mmd
from src.mathpix.page_estimation import TextPositionPages, position_from_filename
from src.models.contracts import Document, Heading, HeadingLevel, Metadata, Page
from src.models.phase2_document import P2BlockType
from src.utils.mathpix_crop import crop_box

URL = "https://cdn.mathpix.com/cropped/abc-04.jpg?height=718&width=1337&top_left_y=277&top_left_x=311"


def _document(**fields) -> Document:
    return Document(source_pdf_path="x.pdf", metadata=Metadata(filename="x.pdf"), **fields)


# --- page placement ---------------------------------------------------------------


def _block(line: int, text: str, image: str = None):
    figure = SimpleNamespace(image_path=image, caption=None) if image else None
    return SimpleNamespace(source_line=line, text=text, heading=None, table=None, figure=figure, footnote=None)


def test_blocks_spread_over_every_page_not_crowded_onto_the_last() -> None:
    # Blank lines between blocks: line numbers run to twice the block count,
    # which is what used to clamp half the document onto the last page.
    blocks = [_block(line * 2, "x" * 100) for line in range(40)]
    pages = TextPositionPages(blocks, page_count=10)
    placed = [pages.page(b.source_line) for b in blocks]
    assert sorted(set(placed)) == list(range(1, 11))
    assert max(placed.count(p) for p in set(placed)) <= 5


def test_figure_crops_anchor_their_page() -> None:
    blocks = [_block(i, "x" * 100) for i in range(30)] + [_block(30, "", image=URL)] + [
        _block(31 + i, "x" * 100) for i in range(30)
    ]
    pages = TextPositionPages(blocks, page_count=13)
    assert pages.page(30) == 4


def test_crop_box_reads_filenames_and_mmd_urls_alike() -> None:
    assert crop_box("abc-04_718_1337_277_311.jpg") == crop_box(URL)
    assert 3.0 < position_from_filename(URL, 13) < 3.3  # near the top of page 4


# --- the MMD parser -----------------------------------------------------------------


def test_markdown_headings_images_and_captions_are_understood() -> None:
    doc = parse_mmd(f"## THE IMPORTANCE OF GOOD QUESTIONS\n\n![]({URL})\n\nFIGURE 3.1 CONCEPT MAP\n\nBOX 2.1 kept as text\n")
    kinds = [b.block_type for b in doc.blocks]
    assert kinds == [P2BlockType.HEADING, P2BlockType.FIGURE, P2BlockType.PARAGRAPH]
    assert doc.blocks[1].figure.caption == "FIGURE 3.1 CONCEPT MAP"  # attached, not dropped
    assert doc.blocks[2].text == "BOX 2.1 kept as text"  # never lost


# --- heading repair -------------------------------------------------------------------


def _heading(text: str, order: int, page: int = 1) -> Heading:
    return Heading(level=HeadingLevel.H2, text=text, page_number=page, document_order=order, source_line=order)


def test_heading_repair_builds_an_outline() -> None:
    document = _document(
        pages=[Page(page_number=1)],
        headings=[
            _heading("3", 0),
            _heading("Developing Your Research Question", 1),
            _heading("'I know the general area ... but I'm not quite sure.'", 2),
            _heading("THE IMPORTANCE OF GOOD QUESTIONS", 3),
            _heading("Defining the investigation", 4),
            _heading("-Albert Szent-Gvorgi", 5),
            _heading("✓ Is the question right for you?", 6),
        ],
    )
    counts = repair_headings(document)
    outline = [(h.level.value, h.text) for h in document.headings]
    assert outline == [
        (1, "3 - Developing Your Research Question"),
        (2, "THE IMPORTANCE OF GOOD QUESTIONS"),
        (3, "Defining the investigation"),
        (3, "Is the question right for you?"),
    ]
    assert counts["demoted"] == 2
    assert {p.text for p in document.paragraphs} >= {"-Albert Szent-Gvorgi"}  # kept as text


# --- DOCX projection ---------------------------------------------------------------------


def test_page_end_sentence_completes_past_a_figure_and_its_caption() -> None:
    lines = [
        "navigating the sea, following a path, or",
        "![fig](x.png)",
        "*FIGURE 3.1 CONCEPT MAP*",
        "<!-- pagebreak -->",
        "###### 5",
        "*FIGURE 3.2 ANOTHER*",
        "embarking on a journey? Each metaphor differs.",
    ]
    out = _complete_sentences_across_page_breaks(lines)
    assert out[0] == "navigating the sea, following a path, or embarking on a journey?"
    assert out[-1] == "Each metaphor differs."


def test_figures_keep_their_printed_size() -> None:
    mathpix = SimpleNamespace(page_number=4, file_path="abc-04_718_1337_277_311.jpg", bbox=None)
    width, height = _printed_size(mathpix, {4: 612.0})
    assert abs(width / 914400 - 1337 / (1337 + 622) * 8.5) < 0.01  # same share of the page
    assert abs(height / width - 718 / 1337) < 0.001  # same shape
    native = SimpleNamespace(page_number=1, file_path="p1.png", bbox=SimpleNamespace(x0=100, y0=0, x1=244, y1=72))
    assert _printed_size(native, {}) == (144 * 12700, 72 * 12700)


def test_metadata_ignores_filenames_and_strangers() -> None:
    assert _looks_like_a_filename("Zina O Leary_The_essential_guide_to_doing_research.pdf")
    assert not _looks_like_a_filename("Developing Your Research Question")
    document = _document(pages=[Page(page_number=1, cleaned_text="By Zina O'Leary. Chapter 3.")])
    assert not _named_in_document("Sharad Sure", document)
    assert _named_in_document("Zina O'Leary", document)
