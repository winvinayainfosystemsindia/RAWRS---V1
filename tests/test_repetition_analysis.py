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
from src.structure.layout_signals import _normalized_signature, annotate_repetition
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


class TestNormalizedSignature:
    """L2.3-b — a running header carrying its page number is still one line.

    The literal signature treats the printed number as part of identity, so
    ``Understanding resistance to conservation / 185`` and ``… / 187`` are two
    lines that each occur once. The furniture is invisible precisely because it
    is furniture: it changes on every page in the one way that does not matter.
    """

    def test_same_furniture_different_numbers_share_a_signature(self):
        assert (
            _normalized_signature("understanding resistance to conservation / 185")
            == _normalized_signature("understanding resistance to conservation / 187")
            == "understanding resistance to conservation / #"
        )

    def test_bare_page_number_normalizes(self):
        """The purest furniture there is, so it is kept deliberately."""
        assert _normalized_signature("343") == "#"

    def test_line_without_digits_has_none(self):
        """Nothing to tolerate; the literal signature already says it."""
        assert _normalized_signature("/ george holmes") is None

    def test_punctuation_husks_are_rejected(self):
        """'1990).' and '1961).' share ').' and nothing else.

        Both formed a '#).' family on the benchmark corpus before this guard.
        """
        assert _normalized_signature("1990).") is None
        assert _normalized_signature("(1983)") is None

    def test_prose_keeps_words_that_differ(self):
        assert _normalized_signature("the year 1985 was pivotal") != _normalized_signature(
            "the year 1985 was quiet"
        )


class TestNormalizedEvidenceIsAdditive:
    def test_literal_stays_blind_while_normalized_sees_the_family(self):
        blocks = [_blk(f"Running head / {180 + p}", p, 40, 0) for p in range(1, 5)]
        annotate_repetition(blocks, page_count=4)
        assert all(b.repetition is None for b in blocks)
        evidence = blocks[0].repetition_normalized
        assert evidence.signature == "running head / #"
        assert evidence.recurrence_count == 4
        assert evidence.positional_stability == 1.0

    def test_an_existing_literal_family_is_undisturbed(self):
        blocks = [_blk("/ George Holmes", p, 124, 0) for p in (1, 3, 5, 7)]
        annotate_repetition(blocks, page_count=8)
        assert blocks[0].repetition.recurrence_count == 4
        assert blocks[0].repetition.alternation == "odd"
        assert blocks[0].repetition_normalized is None

    def test_alternation_survives_normalization(self):
        blocks = [_blk(f"Journal title / {p}", p, 40, 0) for p in (2, 4, 6, 8)]
        annotate_repetition(blocks, page_count=8)
        assert blocks[0].repetition_normalized.alternation == "even"

    def test_repeats_within_one_page_are_not_furniture(self):
        """Three distinct endnotes citing one source formed a family before
        this rule — '5.', '14.' and '20. Tomasello, Kruger and Ratner…' across
        two pages. Furniture appears once per page.
        """
        blocks = [
            _blk("5. Tomasello, Kruger and Ratner, cultural learning.", 1, 300, 0),
            _blk("14. Tomasello, Kruger and Ratner, cultural learning.", 1, 400, 1),
            _blk("20. Tomasello, Kruger and Ratner, cultural learning.", 2, 300, 2),
        ]
        annotate_repetition(blocks, page_count=2)
        assert all(b.repetition_normalized is None for b in blocks)

    def test_normalization_decides_nothing(self):
        """L2.3-b is evidence intake; the decision belongs to L2.3-c."""
        blocks = [_blk(f"Understanding resistance / {180 + p}", p, 124, 0) for p in range(1, 10)]
        annotate_repetition(blocks, page_count=9)
        assert all(b.repetition_normalized is not None for b in blocks)
        assert not any(b.suppressed for b in blocks)
        assert all(b.artifact is None for b in blocks)
