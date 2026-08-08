"""Tests for src/frontmatter/front_matter_extractor.py.

Front-Matter Semantic Extraction: extracts title/author(s)/
affiliation(s) from page 1's already-persisted Document.blocks (Phase
H) - see the module docstring for the exact algorithm and its
calibration against the real Brinkman regression PDF.
"""

from pathlib import Path

import pytest
from typing import List, Optional

from src.frontmatter.front_matter_extractor import extract_front_matter
from src.models.contracts import BoundingBox, Document, Metadata, TextBlock
from src.ocr.extractor import extract_text
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


L5B1_SAMPLE_PDF_DIR = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"


def _corpus_front_matter(filename: str):
    document = extract_front_matter(
        detect_structure(extract_text(parse_pdf(L5B1_SAMPLE_PDF_DIR / filename)))
    )
    return document.front_matter


class TestTitleDiscoveryIsTypographicNotOrdinal:
    """L5'b-1: the title is found by the page's own typography.

    The masthead zone is an *ordinal* prefix, and two corpus documents
    print their title outside it - Nature of Enquiry at block order 93 of
    96 (while physically at the top of the page), sockett_profession at
    order 61 behind ~60 blocks of scan noise. Both were undetectable
    while discovery meant "look at the first few blocks".
    """

    def test_title_is_found_behind_many_earlier_blocks(self) -> None:
        blocks = _body_filler(0, count=40, font_size=10.0)
        blocks.append(_block("A Real Chapter Title", 24.0, 40))
        front_matter = extract_front_matter(_document(blocks)).front_matter

        assert front_matter.title == "A Real Chapter Title"
        assert [i.role.value for i in front_matter.items] == ["title"]

    def test_scan_noise_before_the_title_is_skipped(self) -> None:
        # sockett_profession's page 1, in miniature: oversized OCR debris
        # ahead of the real title. The earlier runs are larger, so a
        # "biggest wins" rule would take them; they are not words, so this
        # rule does not.
        blocks = [
            _block("e", 29.0, 0),
            _block("-", 62.8, 1),
            _block("~Uu1;L L/~<73J", 18.5, 2),
            _block(". $L", 22.6, 3),
            _block("NuN 14k", 20.0, 4),
            _block("The Moral Core of Professionalism", 13.0, 5),
        ]
        blocks.extend(_body_filler(6, count=8, font_size=8.0))
        front_matter = extract_front_matter(_document(blocks)).front_matter

        assert front_matter.title == "The Moral Core of Professionalism"

    def test_a_pull_quote_larger_than_the_title_does_not_win(self) -> None:
        # Aims of Education prints a 55.5pt epigraph below its 16.0pt
        # title. First in reading order, never largest.
        blocks = [
            _block("THE REAL TITLE OF THE PAPER", 16.0, 0),
            _block("Rohit Dhankar", 14.0, 1),
            _block("There is nothing more practical than theory", 55.5, 2),
        ]
        blocks.extend(_body_filler(3, count=8, font_size=12.0))
        front_matter = extract_front_matter(_document(blocks)).front_matter

        assert front_matter.title == "THE REAL TITLE OF THE PAPER"

    def test_a_chapter_kicker_is_not_a_title(self) -> None:
        # "Chapter 9" is one word and a number, and at 14.0pt against a
        # 10.0pt body it clears the size threshold - the word test is what
        # declines it, so the title run starts at the line below.
        blocks = [
            _block("Chapter 9", 14.0, 0),
            _block("Teaching as a professional activity", 18.0, 1),
            _block("James Calderhead", 14.0, 2),
        ]
        blocks.extend(_body_filler(3, count=8, font_size=10.0))
        front_matter = extract_front_matter(_document(blocks)).front_matter

        assert front_matter.title == "Teaching as a professional activity"
        assert front_matter.authors == ["James Calderhead"]

    def test_ordinary_body_text_never_becomes_front_matter(self) -> None:
        # Nothing on the page clears the size threshold.
        blocks = _body_filler(0, count=20, font_size=10.0)
        front_matter = extract_front_matter(_document(blocks)).front_matter

        assert front_matter.title is None
        assert front_matter.items == []


class TestAuthorScopeIsUnchanged:
    """A large text run is not a complete front-matter block.

    Widening title discovery must not widen what the byline tier claims:
    outside the masthead, "bigger than body, smaller than title" catches
    subtitles and chapter kickers, and the model has no role for either.
    """

    def test_a_title_found_outside_the_masthead_yields_no_author(self) -> None:
        # Nature of Enquiry's shape: title 24.0pt, then a subtitle and a
        # chapter kicker at 18.0pt - both inside the byline band.
        blocks = _body_filler(0, count=30, font_size=9.5)
        blocks.append(_block("The nature of enquiry", 24.0, 30))
        blocks.append(_block("Setting the field", 18.0, 31))
        blocks.append(_block("CHAPTER 1", 18.0, 32))
        front_matter = extract_front_matter(_document(blocks)).front_matter

        assert front_matter.title == "The nature of enquiry"
        assert front_matter.authors == []
        assert front_matter.affiliations == []
        assert [i.role.value for i in front_matter.items] == ["title"]

    def test_a_title_found_inside_the_masthead_still_yields_its_author(self) -> None:
        blocks = [
            _block("A Paper Title", 16.0, 0),
            _block("Jane Doe", 13.0, 1),
        ]
        blocks.extend(_body_filler(2, count=8, font_size=10.0))
        front_matter = extract_front_matter(_document(blocks)).front_matter

        assert front_matter.title == "A Paper Title"
        assert front_matter.authors == ["Jane Doe"]


class TestCorpusRecall:
    """Measured on the benchmark corpus. Title recall improves; author and
    affiliation recall are unchanged, and no existing item moves."""

    def test_nature_recovers_its_title_and_asserts_no_author(self) -> None:
        front_matter = _corpus_front_matter("1. Nature of Enquiry.pdf")

        assert front_matter.title == "The nature of enquiry"
        assert front_matter.authors == []
        assert [(i.role.value, i.source_block_id) for i in front_matter.items] == [
            ("title", "p1:b93")
        ]

    def test_sockett_recovers_its_title_from_behind_scan_noise(self) -> None:
        front_matter = _corpus_front_matter("3. sockett_profession.pdf")

        assert front_matter.title == "The Moral Core of Professionalism in Teaching"
        assert front_matter.authors == []
        assert [i.source_block_id for i in front_matter.items] == [
            "p1:b61",
            "p1:b62",
            "p1:b63",
            "p1:b64",
        ]

    @pytest.mark.parametrize(
        "filename,title,authors,affiliations,block_ids",
        [
            (
                "1.Aims of Education and the teacher_Dhankar_PhilPers (1).pdf",
                "AIMS OF EDUCATION: DO TEACHERS NEED TO BOTHER ABOUT THEM?",
                ["Rohit Dhankar"],
                [],
                ["p1:b1", "p1:b2", "p1:b3"],
            ),
            (
                "2.FolkPedagogy_Bruner_PsychDimensions_New.pdf",
                "THE CULTURE OF EDUCATION",
                ["Jerome Bruner"],
                [],
                ["p1:b0", "p1:b1"],
            ),
            (
                "5.Teachingas a profession_Calderhead.pdf",
                "Teaching as a professional activity",
                ["James Calderhead"],
                [],
                ["p1:b1", "p1:b2"],
            ),
            (
                "6. Fullan&Hargreaves_teacherasaperson.pdf",
                "The teacher as a person",
                ["Michael Fullan", "Andy Hargreaves"],
                [],
                ["p1:b1", "p1:b2"],
            ),
        ],
    )
    def test_existing_documents_are_unchanged(
        self, filename, title, authors, affiliations, block_ids
    ) -> None:
        front_matter = _corpus_front_matter(filename)

        assert front_matter.title == title
        assert front_matter.authors == authors
        assert front_matter.affiliations == affiliations
        assert [i.source_block_id for i in front_matter.items] == block_ids

    @pytest.mark.parametrize(
        "filename",
        [
            "2. Social research strategies Bryman.pdf",
            "4. O Leary_Developing the research questions.pdf",
            "4.Teaching as a professional discipline-Chapter 1.pdf",
        ],
    )
    def test_a_page_with_no_extractable_text_invents_nothing(self, filename: str) -> None:
        # No page-1 text layer at all. The gold DOCX has a title block for
        # each of these; it came from a human reading a page image, and is
        # not evidence RAWRS can act on.
        front_matter = _corpus_front_matter(filename)

        assert front_matter.title is None
        assert front_matter.items == []
