"""L1.2 — document-wide repetition analysis (additive evidence).

Unit-tests annotate_repetition over synthetic TextBlocks and confirms
structure_detector wires it into the real extraction path. Additive: no
consumer reads TextBlock.repetition yet, so this only asserts the evidence is
computed and attached correctly.
"""

import fitz

from src.models.bounding_box import BoundingBox
from src.models.contracts import TextBlock
from src.parser.pdf_parser import parse_pdf
from src.structure.layout_signals import annotate_repetition
from src.structure.structure_detector import detect_structure


def _blk(text: str, page: int, y: float, order: int) -> TextBlock:
    return TextBlock(page_number=page, text=text, bbox=BoundingBox(x0=72, y0=y, x1=300, y1=y + 10), order=order)


class TestAnnotateRepetition:
    def test_running_header_across_pages(self):
        blocks = [
            _blk("Journal of X", 1, 40, 0),
            _blk("Journal of X", 2, 41, 0),
            _blk("Journal of X", 3, 39, 0),
            _blk("Body text", 1, 400, 1),
        ]
        annotate_repetition(blocks, page_count=3)
        r = blocks[0].repetition
        assert r is not None
        assert r.recurrence_count == 3
        assert r.page_numbers == [1, 2, 3]
        assert r.recurrence_ratio == 1.0
        assert r.positional_stability > 0.9   # tight y-band
        assert r.alternation is None          # spans consecutive pages
        assert blocks[3].repetition is None   # body line, single page

    def test_odd_alternation(self):
        blocks = [_blk("Left Masthead", 1, 40, 0), _blk("Left Masthead", 3, 40, 0)]
        annotate_repetition(blocks, page_count=4)
        assert blocks[0].repetition.alternation == "odd"

    def test_even_alternation(self):
        blocks = [_blk("Right Masthead", 2, 40, 0), _blk("Right Masthead", 4, 40, 0)]
        annotate_repetition(blocks, page_count=4)
        assert blocks[0].repetition.alternation == "even"

    def test_twice_on_one_page_is_not_repetition(self):
        blocks = [_blk("dup", 1, 100, 0), _blk("dup", 1, 500, 1)]
        annotate_repetition(blocks, page_count=1)
        assert all(b.repetition is None for b in blocks)  # only 1 distinct page

    def test_unique_line_has_no_evidence(self):
        blocks = [_blk("only once", 1, 100, 0), _blk("other", 2, 100, 1)]
        annotate_repetition(blocks, page_count=2)
        assert all(b.repetition is None for b in blocks)

    def test_unstable_position_lowers_stability(self):
        # same text but wildly different y on each page -> low stability
        blocks = [_blk("wanders", 1, 50, 0), _blk("wanders", 2, 700, 0)]
        annotate_repetition(blocks, page_count=2)
        assert blocks[0].repetition.positional_stability < 0.1


class TestStructureDetectorWiring:
    def test_repetition_annotated_on_real_pdf(self, tmp_path):
        doc = fitz.open()
        for _ in range(3):
            page = doc.new_page(width=612, height=792)
            page.insert_text((72, 40), "Running Header Line")
            page.insert_text((72, 400), f"Unique body {_}")
        path = tmp_path / "rep.pdf"
        doc.save(str(path))

        document = detect_structure(parse_pdf(str(path)))

        header_blocks = [b for b in document.blocks if b.text.strip() == "Running Header Line"]
        assert len(header_blocks) == 3
        assert all(b.repetition is not None for b in header_blocks)
        assert header_blocks[0].repetition.page_numbers == [1, 2, 3]
        # A unique body line is not flagged as repeated.
        body = next(b for b in document.blocks if b.text.strip().startswith("Unique body"))
        assert body.repetition is None
