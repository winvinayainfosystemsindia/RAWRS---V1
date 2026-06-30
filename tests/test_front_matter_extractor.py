"""Tests for src/frontmatter/front_matter_extractor.py.

Front-Matter Semantic Extraction: extracts title/author(s)/
affiliation(s) from page 1's already-persisted Document.blocks (Phase
H) - see the module docstring for the exact algorithm and its
calibration against the real Brinkman regression PDF.
"""

from pathlib import Path
from typing import List, Optional

from src.frontmatter.front_matter_extractor import extract_front_matter
from src.models.contracts import BoundingBox, Document, Metadata, TextBlock
from src.parser.pdf_parser import parse_pdf
from src.structure.structure_detector import detect_structure


def _block(text: str, font_size: Optional[float], order: int, page_number: int = 1) -> TextBlock:
    return TextBlock(
        page_number=page_number,
        text=text,
        bbox=BoundingBox(x0=42.5, y0=float(order * 12), x1=400.0, y1=float(order * 12 + 10)),
        order=order,
        font_size=font_size,
    )


def _document(blocks: List[TextBlock]) -> Document:
    document = Document(
        source_pdf_path="synthetic.pdf",
        metadata=Metadata(filename="synthetic.pdf"),
    )
    document.blocks = blocks
    return document


# A realistic-length run of body-sized filler lines, so the document's
# dominant-body-font-size majority vote (character-count-weighted) isn't
# skewed by a sparse fixture - the same rationale
# tests/test_footnote_detector.py's own _FILLER_LINES documents: a
# 1-2-line synthetic page would let the title's own (longer) text
# outweigh a sparse "body" in character count and corrupt the vote.
def _body_filler(start_order: int, count: int = 6, font_size: float = 10.0) -> List[TextBlock]:
    return [
        _block(
            f"This is filler body text on line {i} of the synthetic fixture, long enough to "
            "dominate the character-count vote.",
            font_size,
            start_order + i,
        )
        for i in range(count)
    ]


# Brinkman's real, measured page-1 geometry (TextBlock.font_size, rounded
# to 1dp exactly as src/structure/layout_signals.py::line_layout() rounds
# it) - body_font_size=10.0, title=17.9, author=12.0, affiliation=9.0.
_BRINKMAN_LIKE_ZONE = [
    _block("Article", 10.0, 0),
    _block("Learner-centred education", 17.9, 1),
    _block("reforms in India: The missing", 17.9, 2),
    _block("piece of teachers' beliefs", 17.9, 3),
    _block("Suzana Brinkmann", 12.0, 4),
    _block("Institute of Education, London, UK", 9.0, 5),
    _block("Abstract", 10.0, 6),
] + _body_filler(start_order=7)


class TestFullMastheadZone:
    def test_title_extracted_correctly(self) -> None:
        document = _document(_BRINKMAN_LIKE_ZONE)
        extract_front_matter(document)
        assert document.front_matter.title == (
            "Learner-centred education reforms in India: The missing piece of teachers' beliefs"
        )

    def test_author_extracted_correctly(self) -> None:
        document = _document(_BRINKMAN_LIKE_ZONE)
        extract_front_matter(document)
        assert document.front_matter.authors == ["Suzana Brinkmann"]

    def test_affiliation_extracted_correctly(self) -> None:
        document = _document(_BRINKMAN_LIKE_ZONE)
        extract_front_matter(document)
        assert document.front_matter.affiliations == ["Institute of Education, London, UK"]

    def test_source_texts_populated_for_suppression(self) -> None:
        document = _document(_BRINKMAN_LIKE_ZONE)
        extract_front_matter(document)
        fm = document.front_matter
        assert fm.title_source_texts == [
            "Learner-centred education",
            "reforms in India: The missing",
            "piece of teachers' beliefs",
        ]
        assert fm.author_source_texts == ["Suzana Brinkmann"]
        assert fm.affiliation_source_texts == ["Institute of Education, London, UK"]

    def test_kicker_line_excluded_from_title(self) -> None:
        document = _document(_BRINKMAN_LIKE_ZONE)
        extract_front_matter(document)
        assert "Article" not in document.front_matter.title


class TestNoKicker:
    def test_title_starting_at_first_line_still_extracted(self) -> None:
        blocks = [
            _block("A Title With No Kicker Line", 17.9, 0),
            _block("Jane Doe", 12.0, 1),
            _block("Example University", 9.0, 2),
            _block("Abstract", 10.0, 3),
        ] + _body_filler(start_order=4)
        document = _document(blocks)
        extract_front_matter(document)
        assert document.front_matter.title == "A Title With No Kicker Line"
        assert document.front_matter.authors == ["Jane Doe"]


class TestFailClosed:
    def test_no_blocks_yields_empty_front_matter(self) -> None:
        document = _document([])
        extract_front_matter(document)
        fm = document.front_matter
        assert fm.title is None
        assert fm.authors == []
        assert fm.affiliations == []

    def test_no_font_size_data_yields_empty_front_matter(self) -> None:
        blocks = [
            _block("Some Title", None, 0),
            _block("Abstract", None, 1),
        ]
        document = _document(blocks)
        extract_front_matter(document)
        assert document.front_matter.title is None

    def test_no_title_sized_line_yields_empty_front_matter(self) -> None:
        # Every line is body-sized - no confident title tier exists.
        blocks = [
            _block("Just Another Heading-Like Line", 10.0, 0),
            _block("Abstract", 10.0, 1),
        ] + _body_filler(start_order=2)
        document = _document(blocks)
        extract_front_matter(document)
        assert document.front_matter.title is None

    def test_blocks_on_other_pages_are_ignored(self) -> None:
        blocks = [
            _block("A Title", 17.9, 0, page_number=2),
            _block("Jane Doe", 12.0, 1, page_number=2),
            _block("Abstract", 10.0, 2, page_number=2),
        ] + [
            block.model_copy(update={"page_number": 2})
            for block in _body_filler(start_order=3)
        ]
        document = _document(blocks)
        extract_front_matter(document)
        assert document.front_matter.title is None


class TestFeature008BoundaryGeneralization:
    """feature_008: book/chapter-excerpt front matter (title -> author ->
    straight into body, no Abstract/Keywords/Introduction/Summary section
    at all) is now extracted via the font-size-transition boundary
    fallback, not left empty. Real benchmark cases: Aims of Education,
    FolkPedagogy_Bruner, Calderhead, Fullan&Hargreaves - see
    samples/regressions/feature_008_front_matter_generalization/notes_md/
    front_matter_generalization_audit.md.
    """

    def test_title_with_no_keyword_boundary_extracted_via_body_size_fallback(self) -> None:
        # No "abstract"/"keywords"/"introduction"/"summary" line anywhere
        # in the window - previously this failed closed unconditionally;
        # feature_008 now finds the boundary at the first body-sized
        # line instead (mirroring Calderhead/Fullan&Hargreaves' real
        # shape: title then straight into body prose).
        blocks = [_block("A Title With No Bounded Zone", 17.9, 0)]
        blocks.extend(_body_filler(start_order=1, count=30))
        document = _document(blocks)
        extract_front_matter(document)
        assert document.front_matter.title == "A Title With No Bounded Zone"

    def test_title_and_author_above_threshold_kept_as_separate_tiers(self) -> None:
        # Both title and author exceed the global 1.3x threshold (real
        # case: Bruner, title 29.0pt / author 24.0pt / threshold 16.9pt)
        # - feature_008's run-based separation must still split them
        # into distinct tiers instead of merging the author into the
        # title.
        blocks = [
            _block("A Big Title", 29.0, 0),
            _block("An Author Name", 24.0, 1),
        ]
        blocks.extend(_body_filler(start_order=2))
        document = _document(blocks)
        extract_front_matter(document)
        fm = document.front_matter
        assert fm.title == "A Big Title"
        assert fm.authors == ["An Author Name"]

    def test_kicker_above_global_threshold_still_skipped(self) -> None:
        # The kicker itself exceeds the global 1.3x threshold (real
        # case: Calderhead/Fullan&Hargreaves' "Chapter N" label,
        # 14.0pt vs. a 13.0pt threshold) - feature_008's kicker-skip
        # compares against the next line's size, not the threshold, so
        # it must still be recognized and excluded from the title.
        blocks = [
            _block("Chapter 9", 14.0, 0),
            _block("A Real Title", 18.0, 1),
            _block("An Author Name", 14.0, 2),
        ]
        blocks.extend(_body_filler(start_order=3))
        document = _document(blocks)
        extract_front_matter(document)
        fm = document.front_matter
        assert fm.title == "A Real Title"
        assert fm.authors == ["An Author Name"]

    def test_single_glyph_title_rejected(self) -> None:
        # Real case: sockett_profession.pdf - a lone OCR-garbled glyph
        # passes the title-size gate the same way a real title would,
        # now that the boundary fallback no longer requires a keyword
        # to have screened it out first. Every real title in the
        # benchmark corpus is multiple words; a single token/glyph is
        # rejected instead.
        blocks = [_block("e", 29.0, 0)]
        blocks.extend(_body_filler(start_order=1, count=30, font_size=8.0))
        document = _document(blocks)
        extract_front_matter(document)
        assert document.front_matter.title is None


class TestFeature008AffiliationGuards:
    """feature_008's two mandatory affiliation guards, each calibrated
    against a real benchmark false positive - see
    front_matter_generalization_audit.md SS7-8.
    """

    def test_affiliation_at_or_above_title_size_rejected(self) -> None:
        # Real case: Aims of Education's 55.5pt epigraph against a
        # 16.0pt title - guard #1.
        blocks = [
            _block("A Title", 16.0, 0),
            _block("An Author", 14.0, 1),
            _block("AN OVERSIZED EPIGRAPH LINE", 55.5, 2),
        ]
        blocks.extend(_body_filler(start_order=3, font_size=12.0))
        document = _document(blocks)
        extract_front_matter(document)
        assert document.front_matter.affiliations == []

    def test_affiliation_far_below_author_rejected(self) -> None:
        # Real case: Bruner's "HARVARD UNIVERSITY PRESS" publisher
        # imprint, sitting gap_ratio=8.404 below its author line (vs.
        # Brinkman's genuine affiliation at gap_ratio=0.169) - guard #2.
        # Filler is set below the candidate's own size (9.0) so the
        # candidate survives the boundary fallback and is actually
        # evaluated by guard #2, rather than being excluded by the
        # boundary itself before reaching it. Author line here uses
        # _block's fixed 10pt bbox height; placing the candidate's
        # `order` far ahead (50 vs. 1) reproduces a Bruner-scale
        # vertical gap (gap_ratio=57.8), far past _MAX_AFFILIATION_GAP_RATIO.
        blocks = [
            _block("A Title", 17.9, 0),
            _block("An Author", 12.0, 1),
            _block("A FAR-AWAY PUBLISHER-STYLE LINE", 9.0, 50),
        ]
        blocks.extend(_body_filler(start_order=51, font_size=8.0))
        document = _document(blocks)
        extract_front_matter(document)
        assert document.front_matter.affiliations == []

    def test_genuine_affiliation_immediately_after_author_kept(self) -> None:
        # Real case: Brinkman's affiliation, immediately following the
        # author line with only a small gap - both guards must let this
        # through unchanged.
        blocks = [
            _block("A Title", 17.9, 0),
            _block("An Author", 12.0, 1),
            _block("A Real Affiliation", 9.0, 2),
            _block("Abstract", 10.0, 3),
        ]
        blocks.extend(_body_filler(start_order=4))
        document = _document(blocks)
        extract_front_matter(document)
        assert document.front_matter.affiliations == ["A Real Affiliation"]


class TestAuthorAndAffiliationVariants:
    def test_title_without_distinct_author_or_affiliation_tier(self) -> None:
        # The line right after the title is already body-sized (no
        # distinct byline tier) and is itself the zone boundary keyword
        # - title extracted, author/affiliation both empty.
        blocks = [
            _block("A Standalone Title", 17.9, 0),
            _block("Abstract", 10.0, 1),
        ] + _body_filler(start_order=2)
        document = _document(blocks)
        extract_front_matter(document)
        fm = document.front_matter
        assert fm.title == "A Standalone Title"
        assert fm.authors == []
        assert fm.affiliations == []

    def test_multiple_authors_split_on_comma_and_ampersand(self) -> None:
        blocks = [
            _block("A Title", 17.9, 0),
            _block("Jane Doe, John Smith & Alex Lee", 12.0, 1),
            _block("Example University", 9.0, 2),
            _block("Abstract", 10.0, 3),
        ] + _body_filler(start_order=4)
        document = _document(blocks)
        extract_front_matter(document)
        assert document.front_matter.authors == ["Jane Doe", "John Smith", "Alex Lee"]

    def test_author_run_capped_at_max_lines(self) -> None:
        blocks = [_block("A Title", 17.9, 0)]
        for i in range(8):
            blocks.append(_block(f"Byline filler {i}", 12.0, i + 1))
        blocks.append(_block("Abstract", 10.0, 9))
        blocks.extend(_body_filler(start_order=10))
        document = _document(blocks)
        extract_front_matter(document)
        assert len(document.front_matter.author_source_texts) <= 5

    def test_keywords_alone_can_be_the_zone_boundary(self) -> None:
        # No "Abstract" section at all - "Keywords" alone bounds the zone.
        blocks = [
            _block("A Title", 17.9, 0),
            _block("Jane Doe", 12.0, 1),
            _block("Example University", 9.0, 2),
            _block("Keywords", 10.0, 3),
        ] + _body_filler(start_order=4)
        document = _document(blocks)
        extract_front_matter(document)
        assert document.front_matter.title == "A Title"
        assert document.front_matter.affiliations == ["Example University"]


BRINKMAN_PDF = (
    Path(__file__).resolve().parents[1]
    / "samples"
    / "regressions"
    / "bug_001_brinkman_word_splitting"
    / "source_pdf"
    / "7.brinkman-learner-centred-education-reform-india-missing-beliefs.pdf"
)


class TestRealBrinkmanPdf:
    """End-to-end regression coverage against the real benchmark PDF
    this module's thresholds were calibrated against."""

    def _detect(self) -> Document:
        document = parse_pdf(BRINKMAN_PDF)
        detect_structure(document)
        extract_front_matter(document)
        return document

    def test_title_extracted(self) -> None:
        document = self._detect()
        assert document.front_matter.title == (
            "Learner-centred education reforms in India: The missing piece of teachers’ beliefs"
        )

    def test_author_extracted(self) -> None:
        document = self._detect()
        assert document.front_matter.authors == ["Suzana Brinkmann"]

    def test_affiliation_extracted(self) -> None:
        document = self._detect()
        assert document.front_matter.affiliations == ["Institute of Education, London, UK"]
