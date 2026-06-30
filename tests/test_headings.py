"""Tests for src/headings/heading_detector.py."""

from collections import Counter
from pathlib import Path
from typing import List, Tuple

import fitz
import pytest

from conftest import benchmark_pdfs_with
from src.headings.heading_detector import detect_headings
from src.models.contracts import Document, Heading, HeadingLevel, Metadata, Page
from src.ocr.extractor import extract_text
from src.parser.pdf_parser import parse_pdf

SAMPLE_PDF_DIR = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"
SAMPLE_PDFS = sorted(SAMPLE_PDF_DIR.glob("*.pdf"))

# Manifest-declared (samples/benchmark/manifest.json) born-digital PDFs -
# heading layout signal is only testable against these. Scanned PDFs
# stay out of scope here (no OCR implemented). Previously filtered by
# `"O Leary" not in p.name`, which silently included any newly-added
# scanned PDF whose filename didn't happen to contain "O Leary" (see
# the Benchmark Infrastructure Audit).
DIGITAL_SAMPLE_PDFS = benchmark_pdfs_with("born_digital")


def _build_real_document(tmp_path: Path, lines: List[Tuple[str, str, float]]) -> Document:
    """Build a real one-page PDF with controlled per-line font/size, then
    run it through the real parser + text-extraction stage, so
    detect_headings can read genuine layout signal from the file.

    lines: list of (text, fontname, fontsize). fontname should be a
    PyMuPDF builtin alias, e.g. "helv" (Helvetica) or "hebo"
    (Helvetica-Bold).
    """
    pdf_path = tmp_path / "layout.pdf"
    doc = fitz.open()
    page = doc.new_page()
    y = 72.0
    for text, fontname, fontsize in lines:
        page.insert_text((72, y), text, fontname=fontname, fontsize=fontsize)
        y += fontsize + 10
    doc.save(str(pdf_path))
    doc.close()

    document = parse_pdf(pdf_path)
    return extract_text(document)


def _build_multi_page_real_document(
    tmp_path: Path, pages: List[List[Tuple[float, float, str, str, float]]]
) -> Document:
    """Build a real multi-page PDF with explicit per-insertion (x, y) placement.

    Unlike _build_real_document (which always advances y by line and so
    always produces one PyMuPDF block per line), this gives tests direct
    control over PyMuPDF's own block-clustering: two insertions sharing a
    y-coordinate land in one block as two separate lines - exactly how
    the real Brinkman PDF's "Brinkmann" + page-number running header is
    encoded (see notes_md/heading_isolation_signal_review.md) - which is
    what bug_002's sole-line-block regression tests below need to
    reproduce deterministically rather than relying on incidental
    PyMuPDF layout behavior at different y-coordinates.

    pages: one list of (x, y, text, fontname, fontsize) per page.
    """
    pdf_path = tmp_path / "multipage.pdf"
    doc = fitz.open()
    for page_insertions in pages:
        page = doc.new_page()
        for x, y, text, fontname, fontsize in page_insertions:
            page.insert_text((x, y), text, fontname=fontname, fontsize=fontsize)
    doc.save(str(pdf_path))
    doc.close()

    document = parse_pdf(pdf_path)
    return extract_text(document)


def _build_document(pages_text: List[str]) -> Document:
    """Build a Document with one Page per text block, text pre-populated.

    Mirrors the contract this module relies on: Page.cleaned_text is
    already populated by the (not-yet-implemented) OCR stage.
    """
    pages = [
        Page(page_number=i + 1, cleaned_text=text) for i, text in enumerate(pages_text)
    ]
    return Document(
        source_pdf_path="dummy.pdf",
        metadata=Metadata(filename="dummy.pdf"),
        pages=pages,
    )


def _content_headings(document: Document) -> List[Heading]:
    return [h for h in document.headings if not h.is_page_marker]


class TestH1Detection:
    def test_first_line_of_document_is_h1(self) -> None:
        document = _build_document(["The Silenced Dialogue\nSome body text here."])
        detect_headings(document)

        content = _content_headings(document)
        assert len(content) == 1
        assert content[0].level == HeadingLevel.H1
        assert content[0].text == "The Silenced Dialogue"

    def test_only_one_h1_ever_assigned(self) -> None:
        document = _build_document(
            ["Document Title\nIntroduction\nsome text", "Another Title-Looking Line\nmore text"]
        )
        detect_headings(document)

        h1_headings = [h for h in document.headings if h.level == HeadingLevel.H1]
        assert len(h1_headings) == 1
        assert h1_headings[0].text == "Document Title"

    def test_no_h1_when_document_has_no_text(self) -> None:
        document = _build_document(["", ""])
        detect_headings(document)
        assert [h for h in document.headings if h.level == HeadingLevel.H1] == []


class TestH2Detection:
    @pytest.mark.parametrize("line", ["Unit 1", "Chapter 3", "chapter 12", "Introduction"])
    def test_h2_keyword_and_chapter_patterns(self, line: str) -> None:
        # placeholder first line consumes the H1 slot so it does not
        # interfere with the H2 line under test
        document = _build_document([f"Doc Title\n{line}\nbody text"])
        detect_headings(document)

        content = _content_headings(document)
        assert any(h.level == HeadingLevel.H2 and h.text == line for h in content)


class TestH3Detection:
    @pytest.mark.parametrize("line", ["3.1 Overview", "4.2 Teaching Strategies"])
    def test_h3_section_numbering(self, line: str) -> None:
        document = _build_document([f"Doc Title\n{line}\nbody text"])
        detect_headings(document)

        content = _content_headings(document)
        assert any(h.level == HeadingLevel.H3 and h.text == line for h in content)


class TestH4AndH5Detection:
    def test_h4_subsection_numbering(self) -> None:
        document = _build_document(["Doc Title\n3.1.1 Learning Objectives\nbody text"])
        detect_headings(document)

        content = _content_headings(document)
        assert any(
            h.level == HeadingLevel.H4 and h.text == "3.1.1 Learning Objectives" for h in content
        )

    def test_h5_lower_level_subsection_numbering(self) -> None:
        document = _build_document(["Doc Title\n3.1.1.1 Edge Case Detail\nbody text"])
        detect_headings(document)

        content = _content_headings(document)
        assert any(
            h.level == HeadingLevel.H5 and h.text == "3.1.1.1 Edge Case Detail" for h in content
        )


class TestPageMarkerGeneration:
    def test_every_page_gets_exactly_one_h6_marker(self) -> None:
        document = _build_document(["Page one text", "Page two text", "Page three text"])
        detect_headings(document)

        markers = [h for h in document.headings if h.is_page_marker]
        assert len(markers) == 3
        assert [m.page_number for m in markers] == [1, 2, 3]
        assert [m.text for m in markers] == ["1", "2", "3"]
        assert all(m.level == HeadingLevel.H6 for m in markers)

    def test_page_markers_generated_even_with_no_text(self) -> None:
        document = _build_document(["", "", ""])
        detect_headings(document)

        markers = [h for h in document.headings if h.is_page_marker]
        assert len(markers) == 3


class TestDocumentOrdering:
    def test_document_order_is_strictly_increasing(self) -> None:
        document = _build_document(
            ["Doc Title\nIntroduction\nbody", "3.1 Overview\nbody", "3.1.1 Details\nbody"]
        )
        detect_headings(document)

        orders = [h.document_order for h in document.headings]
        assert orders == sorted(orders)
        assert len(orders) == len(set(orders))
        assert orders[0] == 0

    def test_page_marker_precedes_content_headings_on_same_page(self) -> None:
        document = _build_document(["Doc Title\nIntroduction\nbody text"])
        detect_headings(document)

        page_1_headings = [h for h in document.headings if h.page_number == 1]
        assert page_1_headings[0].is_page_marker is True
        assert page_1_headings[0].level == HeadingLevel.H6
        # content headings on the same page follow the marker, in line order
        assert [h.text for h in page_1_headings[1:]] == ["Doc Title", "Introduction"]

    def test_headings_preserve_cross_page_reading_order(self) -> None:
        document = _build_document(["Doc Title\nIntroduction\nbody", "3.1 Overview\nbody"])
        detect_headings(document)

        ordered_texts = [h.text for h in document.headings]
        assert ordered_texts == ["1", "Doc Title", "Introduction", "2", "3.1 Overview"]


class TestInvalidHierarchyIsDetectedNotCorrected:
    """Hierarchy *validation* belongs to the Validation module, not here.

    This module must faithfully record whatever heading levels appear,
    even when the resulting sequence is hierarchically invalid - it must
    not raise, drop, or silently re-level a heading to "fix" the jump.
    """

    def test_h1_directly_followed_by_h3_is_recorded_as_is(self) -> None:
        document = _build_document(["Doc Title\n3.1 Overview\nbody text"])
        detect_headings(document)

        content = _content_headings(document)
        levels = [h.level for h in content]
        assert levels == [HeadingLevel.H1, HeadingLevel.H3]

    def test_h2_directly_followed_by_h4_is_recorded_as_is(self) -> None:
        document = _build_document(["Doc Title\nIntroduction\n3.1.1 Details\nbody"])
        detect_headings(document)

        content = _content_headings(document)
        levels = [h.level for h in content]
        assert levels == [HeadingLevel.H1, HeadingLevel.H2, HeadingLevel.H4]

    def test_repeated_h2_at_same_level_is_recorded_without_complaint(self) -> None:
        document = _build_document(["Doc Title\nIntroduction\nbody\nConclusion\nbody"])
        detect_headings(document)

        content = _content_headings(document)
        levels = [h.level for h in content]
        assert levels == [HeadingLevel.H1, HeadingLevel.H2, HeadingLevel.H2]


class TestBodyTextIsNotMisclassified:
    def test_long_line_is_not_treated_as_heading(self) -> None:
        long_line = "3.1 " + ("word " * 40)  # numbering prefix but far too long to be a heading
        document = _build_document([f"Doc Title\n{long_line}"])
        detect_headings(document)

        content = _content_headings(document)
        assert all(h.text != long_line.strip() for h in content)

    def test_ordinary_paragraph_text_is_ignored(self) -> None:
        document = _build_document(
            ["Doc Title\nThis is just a normal sentence of body text, not a heading."]
        )
        detect_headings(document)

        content = _content_headings(document)
        assert len(content) == 1
        assert content[0].level == HeadingLevel.H1


class TestDetectHeadingsReturnValue:
    def test_returns_same_document_instance(self) -> None:
        document = _build_document(["Doc Title\nIntroduction"])
        result = detect_headings(document)
        assert result is document


@pytest.mark.parametrize("sample_pdf_path", SAMPLE_PDFS, ids=[p.name for p in SAMPLE_PDFS])
class TestHeadingDetectionWithRealPdfs:
    def test_only_page_markers_when_no_ocr_has_run_yet(self, sample_pdf_path: Path) -> None:
        # The real pipeline's OCR stage is not implemented yet, so the
        # parser leaves Page text empty. detect_headings must degrade
        # gracefully: still emit one H6 marker per page, and zero content
        # headings, rather than erroring on empty text.
        document = parse_pdf(sample_pdf_path)
        detect_headings(document)

        markers = [h for h in document.headings if h.is_page_marker]
        content = _content_headings(document)

        assert len(markers) == len(document.pages)
        assert content == []


class TestLayoutBasedHeadingDetection:
    """Phase B: bold-relative-to-body layout signal, derived from real
    benchmark PDFs (see BENCHMARK_RECONCILIATION_AND_PHASE1_PLAN.md
    Phase B). These require a real PDF file, since the signal is read
    directly from PyMuPDF span data - unlike the text-pattern tests
    above, a fake source_pdf_path provides no layout signal at all.
    """

    def test_bold_line_with_no_numbering_becomes_h2(self, tmp_path: Path) -> None:
        document = _build_real_document(
            tmp_path,
            [
                ("Some ordinary body text.", "helv", 10),
                ("Teaching as an Art", "hebo", 10),
                ("More ordinary body text follows here.", "helv", 10),
            ],
        )
        detect_headings(document)

        content = _content_headings(document)
        matches = [h for h in content if h.text == "Teaching as an Art"]
        assert len(matches) == 1
        assert matches[0].level == HeadingLevel.H2

    def test_large_non_bold_subtitle_is_not_detected_as_heading(self, tmp_path: Path) -> None:
        # Real counter-example found in the benchmark: a non-bold
        # subtitle line can be the LARGEST text on the page (18pt vs a
        # 10pt body) and still must not become a heading. Pure
        # size-based promotion would get this backwards.
        document = _build_real_document(
            tmp_path,
            [
                ("Chapter 9", "helv", 14),
                ("Teaching as a professional activity", "helv", 18),
                ("James Calderhead", "helv", 14),
                ("Body text begins here and continues for a while.", "helv", 10),
            ],
        )
        detect_headings(document)

        content = _content_headings(document)
        subtitle_matches = [h for h in content if "professional activity" in h.text]
        assert subtitle_matches == []

    def test_minority_bold_span_does_not_flag_line_as_bold(self) -> None:
        # A single bold word within an otherwise-regular sentence must
        # not promote the whole line to a heading - only a line that is
        # *mostly* bold should qualify. PyMuPDF's insert_text() does not
        # merge separate calls into one shared line/span structure even
        # at matching coordinates, so this is exercised directly against
        # the span-aggregation helper instead of a rendered PDF.
        # Moved to src.structure.layout_signals in Phase H (Structure
        # Detection) so it can be shared with that module's per-line
        # extraction instead of duplicated; heading_detector.py still
        # imports and uses it unchanged.
        from src.structure.layout_signals import line_layout

        line_dict = {
            "spans": [
                {"text": "This is mostly regular text with ", "font": "Helvetica", "flags": 0, "size": 10.0},
                {"text": "one bold word", "font": "Helvetica-Bold", "flags": 16, "size": 10.0},
            ]
        }
        text, size, is_bold, char_count = line_layout(line_dict)
        assert is_bold is False

    def test_majority_bold_span_flags_line_as_bold(self) -> None:
        from src.structure.layout_signals import line_layout

        line_dict = {
            "spans": [
                {"text": "Mostly Bold Heading Text", "font": "Helvetica-Bold", "flags": 16, "size": 10.0},
                {"text": " x", "font": "Helvetica", "flags": 0, "size": 10.0},
            ]
        }
        text, size, is_bold, char_count = line_layout(line_dict)
        assert is_bold is True

    def test_running_header_smaller_than_body_is_not_misdetected(self, tmp_path: Path) -> None:
        document = _build_real_document(
            tmp_path,
            [
                ("Doc Title", "helv", 10),  # consumes the H1 slot
                ("Repeated Running Header", "helv", 8),  # smaller than body, not bold
                ("This is the real body paragraph text for the page.", "helv", 10),
            ],
        )
        detect_headings(document)

        content = _content_headings(document)
        assert all("Running Header" not in h.text for h in content)


class TestH1PositionalPriorityOverKeyword:
    """Phase B: the H1 slot is now checked before the Chapter/Unit
    keyword rule, so a short excerpt whose very first line is "Chapter
    9" gets H1 (it IS that excerpt's title), matching the benchmark.
    """

    def test_chapter_n_as_first_line_becomes_h1(self) -> None:
        document = _build_document(["Chapter 9\nbody text"])
        detect_headings(document)

        content = _content_headings(document)
        assert content[0].text == "Chapter 9"
        assert content[0].level == HeadingLevel.H1

    def test_chapter_n_after_a_preceding_title_still_becomes_h2(self) -> None:
        # Regression guard: when a document already has its own title
        # as the first line, a later "Chapter N" must still fall
        # through to H2, not steal the (already-consumed) H1 slot.
        document = _build_document(["Book Title\nChapter 1\nbody text"])
        detect_headings(document)

        content = _content_headings(document)
        assert content[0].text == "Book Title"
        assert content[0].level == HeadingLevel.H1
        assert content[1].text == "Chapter 1"
        assert content[1].level == HeadingLevel.H2


@pytest.mark.parametrize(
    "sample_pdf_path", DIGITAL_SAMPLE_PDFS, ids=[p.name for p in DIGITAL_SAMPLE_PDFS]
)
class TestHeadingRecoveryOnRealBenchmarkPdfs:
    def test_content_headings_are_now_detected(self, sample_pdf_path: Path) -> None:
        # Before Phase B, every born-digital benchmark PDF produced
        # zero content headings even with real text present. This is
        # the direct "heading recovery improves" proof.
        document = parse_pdf(sample_pdf_path)
        extract_text(document)
        detect_headings(document)

        content = _content_headings(document)
        assert len(content) > 0

    def test_no_h1_is_missing_anymore(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(sample_pdf_path)
        extract_text(document)
        detect_headings(document)

        content = _content_headings(document)
        assert any(h.level == HeadingLevel.H1 for h in content)


class TestHeadingRecoveryOnSpecificBenchmarkDocuments:
    def test_calderhead_chapter_becomes_h1_not_h2(self) -> None:
        path = SAMPLE_PDF_DIR / "5.Teachingas a profession_Calderhead.pdf"
        document = parse_pdf(path)
        extract_text(document)
        detect_headings(document)

        content = _content_headings(document)
        chapter = [h for h in content if h.text == "Chapter 9"]
        assert len(chapter) == 1
        assert chapter[0].level == HeadingLevel.H1
        # the byline/subtitle must not be misdetected as headings
        assert all("professional activity" not in h.text for h in content)
        assert all("James Calderhead" != h.text for h in content)

    def test_fullan_hargreaves_matches_expected_structure_exactly(self) -> None:
        path = SAMPLE_PDF_DIR / "6. Fullan&Hargreaves_teacherasaperson.pdf"
        document = parse_pdf(path)
        extract_text(document)
        detect_headings(document)

        content = _content_headings(document)
        assert [(h.level, h.text) for h in content] == [
            (HeadingLevel.H1, "Chapter 7"),
            (HeadingLevel.H2, "REFERENCES"),
        ]

    def test_teaching_as_professional_discipline_recovers_section_headings(self) -> None:
        path = SAMPLE_PDF_DIR / "4.Teaching as a professional discipline-Chapter 1.pdf"
        document = parse_pdf(path)
        extract_text(document)
        detect_headings(document)

        content = _content_headings(document)
        texts = {h.text for h in content}
        # These are plain Title-Case headings with zero numbering - the
        # exact pattern the pre-Phase-B rule set could never detect.
        for expected in [
            "Teaching as a Common-sense Activity",
            "Teaching as an Art",
            "Teaching as a Craft",
            "Conclusion",
        ]:
            assert expected in texts


class TestBug002FallbackTier:
    """bug_002: the distinct-recurring-font + sole-line-block fallback
    tier, last in the classification chain (tier 5). See
    notes_md/heading_isolation_signal_review.md for the audit and
    src/headings/heading_detector.py's module docstring point 5 for the
    full condition list, including the size-floor condition added after
    verification (not part of the original six-condition audit) and the
    sole-line-only recurrence-counting fix - both found via real
    regressions during this implementation, not hypothesized.
    """

    def test_fallback_tier_requires_sole_line_block(self) -> None:
        # Direct unit coverage of the gate itself: identical font, size,
        # and recurrence count - the only difference is is_sole_line.
        from src.headings.heading_detector import _FallbackSignal, _is_fallback_heading

        signature_counts = Counter({("CustomFont", 14.0): 2})
        sole = _FallbackSignal(font_name="CustomFont", size=14.0, is_sole_line=True)
        shared = _FallbackSignal(font_name="CustomFont", size=14.0, is_sole_line=False)
        common_kwargs = dict(
            is_h1_slot=False,
            body_font_name="BodyFont",
            signature_counts=signature_counts,
            body_profile=(10.0, False),
        )

        assert (
            _is_fallback_heading("Recurring Heading", fallback_signal=sole, **common_kwargs)
            is True
        )
        assert (
            _is_fallback_heading("Recurring Heading", fallback_signal=shared, **common_kwargs)
            is False
        )

    def test_fallback_tier_requires_size_at_least_body_size(self) -> None:
        # The seventh condition, added after verification found that
        # table/figure captions and table-footnote lines (smaller than
        # body, in a distinct recurring font, sole-line) satisfy all six
        # originally-audited gates just as real section headings do.
        from src.headings.heading_detector import _FallbackSignal, _is_fallback_heading

        signature_counts = Counter({("CaptionFont", 8.0): 5})
        caption_sized = _FallbackSignal(font_name="CaptionFont", size=8.0, is_sole_line=True)

        assert (
            _is_fallback_heading(
                "Table 1. Summary of results",
                is_h1_slot=False,
                fallback_signal=caption_sized,
                body_font_name="BodyFont",
                signature_counts=signature_counts,
                body_profile=(10.0, False),
            )
            is False
        )

    def test_recurring_distinct_font_sole_line_becomes_heading_end_to_end(
        self, tmp_path: Path
    ) -> None:
        # Positive control: proves the tier actually fires through the
        # real detect_headings() entry point, not just at the unit level.
        document = _build_multi_page_real_document(
            tmp_path,
            [
                [
                    (72, 72, "Section Heading One", "tiro", 14),
                    (72, 100, "Ordinary body text for page one continues here.", "helv", 10),
                ],
                [
                    (72, 72, "Section Heading Two", "tiro", 14),
                    (72, 100, "Ordinary body text for page two continues here.", "helv", 10),
                ],
            ],
        )
        detect_headings(document)

        texts = {h.text for h in _content_headings(document)}
        assert "Section Heading One" in texts
        assert "Section Heading Two" in texts

    def test_running_header_sharing_block_with_page_number_is_not_misdetected(
        self, tmp_path: Path
    ) -> None:
        # Two insertions at the same y-coordinate land in one PyMuPDF
        # block as two separate lines - exactly how the real Brinkman
        # PDF's "Brinkmann" + page-number running header is encoded.
        # Recurs across both pages, in a font distinct from body, and is
        # alphabetic - every other gate is satisfied; only sole-line-block
        # is false, and that alone must be enough to exclude it.
        document = _build_multi_page_real_document(
            tmp_path,
            [
                [
                    (72, 72, "Doc Title", "helv", 10),  # consumes the H1 slot
                    (72, 700, "RunningAuthorName", "tiro", 8),
                    (300, 700, "5", "helv", 8),
                    (72, 100, "Ordinary body text for page one continues here.", "helv", 10),
                ],
                [
                    (72, 700, "RunningAuthorName", "tiro", 8),
                    (300, 700, "6", "helv", 8),
                    (72, 72, "Ordinary body text for page two continues here.", "helv", 10),
                ],
            ],
        )
        detect_headings(document)

        content = _content_headings(document)
        assert all("RunningAuthorName" != h.text for h in content)

    def test_chapter_label_sharing_masthead_block_still_becomes_h1(
        self, tmp_path: Path
    ) -> None:
        # The exact shape of the real regression this implementation
        # fixed: "Chapter 9"/"Chapter 7" share a multi-line masthead
        # block with the chapter title (not sole-line), but must still
        # become H1 via the higher-priority positional-slot rule,
        # checked before the fallback tier is ever reached.
        document = _build_multi_page_real_document(
            tmp_path,
            [
                [
                    (72, 72, "Chapter 9", "helv", 14),
                    (300, 72, "Subtitle On Same Line", "helv", 14),
                    (72, 100, "Body text begins here and continues for a while.", "helv", 10),
                ],
            ],
        )
        detect_headings(document)

        content = _content_headings(document)
        assert content[0].text == "Chapter 9"
        assert content[0].level == HeadingLevel.H1

    def test_real_chapter_labels_are_not_sole_line_but_still_detected(self) -> None:
        # Confirms the regression-guard reasoning above against the real
        # benchmark PDFs, not just the synthetic reproduction: both
        # "Chapter 9" and "Chapter 7" are documented (root_cause_audit /
        # heading_isolation_signal_review) as NOT sole-line blocks - they
        # share a 3-line masthead block with the chapter title - yet
        # both remain detected as H1, proving sole-line-block is enforced
        # only inside the new tier and never reaches these lines at all.
        from src.headings.heading_detector import _build_fallback_tier_index

        for filename, expected_chapter in [
            ("5.Teachingas a profession_Calderhead.pdf", "Chapter 9"),
            ("6. Fullan&Hargreaves_teacherasaperson.pdf", "Chapter 7"),
        ]:
            path = SAMPLE_PDF_DIR / filename
            document = parse_pdf(path)
            extract_text(document)

            fallback_index, _, _ = _build_fallback_tier_index(str(path))
            signal = fallback_index.get(1, {}).get(expected_chapter)
            assert signal is not None, f"{expected_chapter} not found in fallback index at all"
            assert signal.is_sole_line is False, (
                f"{expected_chapter} is now sole-line in its PyMuPDF block - "
                "the masthead layout this regression guard assumes has changed; "
                "re-verify the H1-slot rule still protects it independently"
            )

            detect_headings(document)
            content = _content_headings(document)
            chapter_headings = [h for h in content if h.text == expected_chapter]
            assert len(chapter_headings) == 1
            assert chapter_headings[0].level == HeadingLevel.H1
