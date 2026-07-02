"""Tests for src/validation/validator.py."""

from datetime import datetime, timezone
from pathlib import Path
from typing import List

import pytest

from src.headings.heading_detector import detect_headings
from src.models.contracts import (
    AltTextStatus,
    BoundingBox,
    Document,
    ExtractionMethod,
    Figure,
    Footnote,
    Heading,
    HeadingLevel,
    Image,
    Metadata,
    NoteType,
    OCRConfidence,
    Page,
    SanitizationEvent,
    Severity,
    TextBlock,
)
from src.parser.pdf_parser import parse_pdf
from src.structure.structure_detector import detect_structure
from src.validation.validator import validate_document

SAMPLE_PDF_DIR = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"
SAMPLE_PDFS = sorted(SAMPLE_PDF_DIR.glob("*.pdf"))


def _build_document(
    pages_text: List[str],
    *,
    image_count: int = 0,
    language: str = "en-US",
    title: str = "Test Document",
) -> Document:
    """Build a Document with text pre-populated and headings detected,
    with Metadata counts kept consistent so a "valid" baseline document
    does not itself trip the metadata-consistency check.

    language and title default to valid values so that META_001/META_002
    (WCAG 3.1.1/2.4.2) do not fire on baseline "well-formed" fixtures.
    Pass language="" or title="" explicitly to test those rules.
    """
    pages = [Page(page_number=i + 1, cleaned_text=text) for i, text in enumerate(pages_text)]
    document = Document(
        source_pdf_path="dummy.pdf",
        metadata=Metadata(
            filename="dummy.pdf",
            page_count=len(pages),
            image_count=image_count,
            processing_date=datetime.now(timezone.utc),
            language=language if language else None,
            title=title if title else None,
        ),
        pages=pages,
    )
    return detect_headings(document)


class TestValidDocument:
    def test_well_formed_single_page_document_has_no_issues(self) -> None:
        document = _build_document(["Doc Title\nIntroduction\nbody text"])
        assert validate_document(document) == []

    def test_well_formed_multi_page_document_has_no_issues(self) -> None:
        document = _build_document(
            ["Doc Title\nIntroduction\nbody", "3.1 Overview\nbody", "3.1.1 Details\nbody"]
        )
        assert validate_document(document) == []


class TestInvalidHierarchy:
    def test_h1_then_h3_is_flagged_as_hierarchy_jump(self) -> None:
        document = _build_document(["Doc Title\n3.1 Overview\nbody"])
        issues = validate_document(document)

        jumps = [i for i in issues if i.rule_id == "HEADING_001"]
        assert len(jumps) == 1
        assert jumps[0].severity == Severity.WARNING
        assert jumps[0].page_number == 1

    def test_decreasing_level_is_not_flagged(self) -> None:
        # H1 -> H2 -> H3 -> H4 are all valid one-step increments, then
        # H4 -> H3 decreases. Going back up to a higher-level section is
        # normal document structure, not a hierarchy violation.
        document = _build_document(
            ["Doc Title\nIntroduction\n3.1 Overview\n3.1.1 Details\n4.2 Teaching Strategies\nbody"]
        )
        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "HEADING_001"] == []

    def test_missing_h1_is_flagged(self) -> None:
        # The H1 slot is consumed by the very first non-blank line
        # regardless of outcome. A line matching the more specific H3
        # numbering pattern (checked before the H1 slot) consumes the
        # slot without ever becoming H1, so no H1 appears anywhere.
        document = _build_document(["3.1 Overview\nbody text"])
        issues = validate_document(document)

        missing_h1 = [i for i in issues if i.rule_id == "HEADING_002"]
        assert len(missing_h1) == 1
        assert missing_h1[0].severity == Severity.WARNING
        assert missing_h1[0].page_number is None

    def test_duplicate_heading_is_flagged(self) -> None:
        document = _build_document(["Doc Title\nIntroduction\nbody", "Introduction\nmore"])
        issues = validate_document(document)

        duplicates = [i for i in issues if i.rule_id == "HEADING_004"]
        assert len(duplicates) == 1
        assert duplicates[0].severity == Severity.WARNING
        assert duplicates[0].page_number == 2

    def test_empty_heading_is_flagged_defensively(self) -> None:
        # Heading itself rejects blank text at construction; bypass
        # that here purely to exercise validator.py's own
        # defense-in-depth check for this otherwise-unreachable case.
        document = _build_document(["Doc Title"])
        blank_heading = Heading.model_construct(
            level=HeadingLevel.H2,
            text="   ",
            page_number=1,
            document_order=99,
            is_page_marker=False,
        )
        document.headings.append(blank_heading)

        issues = validate_document(document)
        empty = [i for i in issues if i.rule_id == "HEADING_003"]
        assert len(empty) == 1
        assert empty[0].severity == Severity.WARNING


class TestMissingPageMarkers:
    def test_missing_marker_is_flagged_as_error(self) -> None:
        document = _build_document(["Doc Title"])
        document.headings = [h for h in document.headings if not h.is_page_marker]

        issues = validate_document(document)
        missing = [i for i in issues if i.rule_id == "PAGE_001"]
        assert len(missing) == 1
        assert missing[0].severity == Severity.ERROR
        assert missing[0].page_number == 1

    def test_all_pages_with_markers_produce_no_page_001_issue(self) -> None:
        document = _build_document(["one", "two"])
        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "PAGE_001"] == []


class TestPageOrdering:
    def test_duplicate_page_number_is_error(self) -> None:
        document = _build_document(["one"])
        document.pages.append(Page(page_number=1, cleaned_text="dup"))

        issues = validate_document(document)
        duplicates = [i for i in issues if i.rule_id == "PAGE_002" and "more than once" in i.message]
        assert len(duplicates) == 1
        assert duplicates[0].severity == Severity.ERROR

    def test_gap_in_page_sequence_is_error(self) -> None:
        document = _build_document(["one"])
        document.pages.append(Page(page_number=3, cleaned_text="three"))

        issues = validate_document(document)
        gaps = [i for i in issues if i.rule_id == "PAGE_002" and "missing from the page sequence" in i.message]
        assert len(gaps) == 1
        assert gaps[0].severity == Severity.ERROR
        assert gaps[0].page_number == 2

    def test_out_of_order_but_complete_pages_is_warning(self) -> None:
        page_1 = Page(page_number=1, cleaned_text="first")
        page_2 = Page(page_number=2, cleaned_text="second")
        document = Document(
            source_pdf_path="dummy.pdf",
            metadata=Metadata(filename="dummy.pdf", page_count=2),
            pages=[page_2, page_1],
        )
        detect_headings(document)

        issues = validate_document(document)
        order_issues = [
            i for i in issues if i.rule_id == "PAGE_002" and "out of page-number order" in i.message
        ]
        assert len(order_issues) == 1
        assert order_issues[0].severity == Severity.WARNING


def _block(
    page_number: int,
    order: int,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    font_size: float = 12.0,
) -> TextBlock:
    return TextBlock(
        page_number=page_number,
        text=f"line {order}",
        bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
        order=order,
        font_size=font_size,
    )


def _document_with_blocks(blocks: List[TextBlock]) -> Document:
    """A minimal Document carrying only document.blocks (Phase H data) -
    Phase I.1's check operates entirely on this, independent of
    Page.cleaned_text/headings."""
    page_numbers = sorted({block.page_number for block in blocks})
    document = Document(
        source_pdf_path="dummy.pdf",
        metadata=Metadata(filename="dummy.pdf", page_count=len(page_numbers)),
        pages=[Page(page_number=number) for number in page_numbers],
    )
    document.blocks = blocks
    return document


def _page_003_issues(document: Document) -> List:
    return [issue for issue in validate_document(document) if issue.rule_id == "PAGE_003"]


class TestReadingOrderAnomalies:
    """Phase I.1: PAGE_003 - a conservative, geometry-only signal that a
    page's Document.blocks (Phase H) may not follow a single coherent
    top-to-bottom reading order. Operates entirely on existing block
    data; never reorders or modifies anything."""

    def test_normal_single_column_page_has_no_anomaly(self) -> None:
        blocks = [_block(1, i, 72, 72 + i * 20, 300, 72 + i * 20 + 14) for i in range(8)]
        document = _document_with_blocks(blocks)

        assert _page_003_issues(document) == []

    def test_minor_same_line_jitter_is_not_flagged(self) -> None:
        # Two spans of the same visual line ending up as separate blocks
        # with a tiny y0 difference (well under one line height) must
        # not be mistaken for a backward jump - exactly the kind of
        # false positive Phase I.1 must avoid.
        blocks = [
            _block(1, 0, 72, 72.0, 200, 86),
            _block(1, 1, 205, 72.3, 300, 86),  # 0.3pt jitter, same visual line
            _block(1, 2, 72, 92.0, 300, 106),
        ]
        document = _document_with_blocks(blocks)

        assert _page_003_issues(document) == []

    def test_intentionally_scrambled_order_is_flagged(self) -> None:
        # Block at order=2 sits well *above* the previous block in
        # sequence - a clear, large backward jump.
        blocks = [
            _block(1, 0, 72, 72, 300, 86),
            _block(1, 1, 72, 92, 300, 106),
            _block(1, 2, 72, 30, 300, 44),  # jumps back up the page
            _block(1, 3, 72, 132, 300, 146),
        ]
        document = _document_with_blocks(blocks)

        issues = _page_003_issues(document)
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].page_number == 1
        assert "backward vertical jump" in issues[0].message

    def test_overlapping_blocks_are_flagged(self) -> None:
        blocks = [
            _block(1, 0, 72, 72, 300, 100),
            _block(1, 1, 80, 80, 310, 110),  # heavily overlaps block 0
        ]
        document = _document_with_blocks(blocks)

        issues = _page_003_issues(document)
        assert len(issues) == 1
        assert "overlapping block pair" in issues[0].message

    def test_slightly_overlapping_blocks_are_not_flagged(self) -> None:
        # Adjacent lines whose bboxes touch/slightly overlap at the
        # edges (common with real font ascenders/descenders) must stay
        # under the 50%-of-smaller-block threshold.
        blocks = [
            _block(1, 0, 72, 72, 300, 90),
            _block(1, 1, 72, 88, 300, 106),  # 2pt overlap out of 18pt height
        ]
        document = _document_with_blocks(blocks)

        assert _page_003_issues(document) == []

    def test_obvious_column_style_anomaly_is_flagged(self) -> None:
        # Left column read fully top-to-bottom, then emission jumps back
        # to the top of the page to start the right column - the
        # classic column-interleaving failure signature.
        blocks = []
        order = 0
        for y in (72, 92, 112, 132):
            blocks.append(_block(1, order, 72, y, 250, y + 14))
            order += 1
        for y in (72, 92, 112, 132):
            blocks.append(_block(1, order, 320, y, 500, y + 14))
            order += 1
        document = _document_with_blocks(blocks)

        issues = _page_003_issues(document)
        assert len(issues) == 1
        assert "backward vertical jump" in issues[0].message

    def test_side_by_side_columns_without_a_jump_are_not_flagged(self) -> None:
        # Two columns whose blocks happen to be emitted in a
        # non-decreasing-y order (e.g. row-by-row) produce no backward
        # jump and don't overlap in bbox - Phase I.1's conservative
        # heuristic does not claim to catch every possible column
        # pattern, only the large, unambiguous ones (see module
        # docstring / Phase I audit's documented scope).
        blocks = [
            _block(1, 0, 72, 72, 250, 86),
            _block(1, 1, 320, 72, 500, 86),
            _block(1, 2, 72, 92, 250, 106),
            _block(1, 3, 320, 92, 500, 106),
        ]
        document = _document_with_blocks(blocks)

        assert _page_003_issues(document) == []

    def test_anomaly_is_isolated_to_its_own_page(self) -> None:
        good_page = [_block(1, i, 72, 72 + i * 20, 300, 72 + i * 20 + 14) for i in range(4)]
        bad_page = [
            _block(2, 0, 72, 72, 300, 86),
            _block(2, 1, 72, 30, 300, 44),
        ]
        document = _document_with_blocks(good_page + bad_page)

        issues = _page_003_issues(document)
        assert len(issues) == 1
        assert issues[0].page_number == 2

    def test_no_blocks_yields_no_anomaly(self) -> None:
        document = _document_with_blocks([])
        assert _page_003_issues(document) == []

    def test_single_block_on_a_page_yields_no_anomaly(self) -> None:
        document = _document_with_blocks([_block(1, 0, 72, 72, 300, 86)])
        assert _page_003_issues(document) == []

    def test_check_does_not_consume_page_cleaned_text(self) -> None:
        # Phase I.1 operates entirely on document.blocks - confirms the
        # check still works (or correctly finds nothing) even when
        # Page.cleaned_text is empty, since real callers run this after
        # Structure Detection but the two are otherwise independent.
        blocks = [
            _block(1, 0, 72, 72, 300, 86),
            _block(1, 1, 72, 30, 300, 44),
        ]
        document = _document_with_blocks(blocks)
        assert document.pages[0].cleaned_text == ""

        issues = _page_003_issues(document)
        assert len(issues) == 1


_EXPECTED_PAGE_003_COUNT = {
    # Confirmed during the original Phase I architecture audit: these 4
    # were the entire benchmark corpus at the time and are all clean,
    # single-column extraction order.
    "4. O Leary_Developing the research questions.pdf": 0,
    "4.Teaching as a professional discipline-Chapter 1.pdf": 0,
    "5.Teachingas a profession_Calderhead.pdf": 0,
    "6. Fullan&Hargreaves_teacherasaperson.pdf": 0,
    # The benchmark corpus grew to 10 PDFs on 2026-06-24 (see
    # DECISIONS_LOG.md "Benchmark Corpus Expansion"); these 6 additions
    # include several genuinely multi-column real documents. Counts
    # below are real, directly-confirmed PAGE_003 output, not
    # speculative - pinned as a regression guard the same way the
    # original 4 were, not loosened into "anomalies are fine
    # everywhere".
    "1. Nature of Enquiry.pdf": 28,
    "1.Aims of Education and the teacher_Dhankar_PhilPers (1).pdf": 4,
    "2. Social research strategies Bryman.pdf": 0,
    "2.FolkPedagogy_Bruner_PsychDimensions_New.pdf": 0,
    "3. sockett_profession.pdf": 9,
    "7.brinkman-learner-centred-education-reform-india-missing-beliefs.pdf": 18,
}


@pytest.mark.parametrize("sample_pdf_path", SAMPLE_PDFS, ids=[p.name for p in SAMPLE_PDFS])
class TestReadingOrderAnomaliesWithRealPdfs:
    def test_anomaly_count_matches_known_benchmark_corpus_ground_truth(
        self, sample_pdf_path: Path
    ) -> None:
        document = parse_pdf(sample_pdf_path)
        detect_structure(document)

        issues = _page_003_issues(document)
        assert len(issues) == _EXPECTED_PAGE_003_COUNT[sample_pdf_path.name]


class TestLowOcrConfidence:
    """OCR_001: flags pages whose Page.ocr_confidence is LOW (Surya
    fallback recovery) - the one confidence tier docs/OCR_RULES.md
    explicitly calls out for validation review."""

    def test_low_confidence_page_is_flagged_as_warning(self) -> None:
        document = _build_document(["Doc Title\nbody"])
        document.pages[0].ocr_confidence = OCRConfidence.LOW

        issues = validate_document(document)
        low_confidence = [i for i in issues if i.rule_id == "OCR_001"]
        assert len(low_confidence) == 1
        assert low_confidence[0].severity == Severity.WARNING
        assert low_confidence[0].page_number == 1

    def test_medium_confidence_page_is_not_flagged(self) -> None:
        # Docling's normal, successful outcome - not flagged, or every
        # OCR_REQUIRED page Docling succeeds on would warn.
        document = _build_document(["Doc Title\nbody"])
        document.pages[0].ocr_confidence = OCRConfidence.MEDIUM

        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "OCR_001"] == []

    def test_high_confidence_page_is_not_flagged(self) -> None:
        document = _build_document(["Doc Title\nbody"])
        document.pages[0].ocr_confidence = OCRConfidence.HIGH

        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "OCR_001"] == []

    def test_no_confidence_set_is_not_flagged(self) -> None:
        # Default state (e.g. direct-extraction pages, or a page never
        # routed) - ocr_confidence is None, not LOW, so no false flag.
        document = _build_document(["Doc Title\nbody"])
        assert document.pages[0].ocr_confidence is None

        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "OCR_001"] == []

    def test_multiple_low_confidence_pages_each_produce_their_own_issue(self) -> None:
        document = _build_document(["one", "two", "three"])
        document.pages[0].ocr_confidence = OCRConfidence.LOW
        document.pages[2].ocr_confidence = OCRConfidence.LOW

        issues = validate_document(document)
        low_confidence = [i for i in issues if i.rule_id == "OCR_001"]
        assert len(low_confidence) == 2
        assert {i.page_number for i in low_confidence} == {1, 3}


class TestOcrArtifacts:
    """OCR_002: flags pages where Docling/Surya ran and the recovered
    text is still dominated by control characters or the Unicode
    replacement character - reuses src/ocr/router.py's existing
    _unusable_char_ratio()/_MAX_UNUSABLE_CHAR_RATIO rather than a new
    threshold."""

    def test_docling_page_with_excessive_artifacts_is_flagged(self) -> None:
        garbled = chr(0xFFFD) * 40 + "ok"
        document = _build_document([garbled])
        document.pages[0].extraction_method = ExtractionMethod.DOCLING

        issues = validate_document(document)
        artifacts = [i for i in issues if i.rule_id == "OCR_002"]
        assert len(artifacts) == 1
        assert artifacts[0].severity == Severity.WARNING
        assert artifacts[0].page_number == 1

    def test_surya_page_with_excessive_artifacts_is_flagged(self) -> None:
        garbled = chr(0xFFFD) * 40 + "ok"
        document = _build_document([garbled])
        document.pages[0].extraction_method = ExtractionMethod.SURYA

        issues = validate_document(document)
        assert len([i for i in issues if i.rule_id == "OCR_002"]) == 1

    def test_docling_page_with_clean_text_is_not_flagged(self) -> None:
        document = _build_document(["Doc Title\nA perfectly ordinary recovered paragraph."])
        document.pages[0].extraction_method = ExtractionMethod.DOCLING

        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "OCR_002"] == []

    def test_docling_page_with_a_few_stray_control_chars_is_not_flagged(self) -> None:
        # 3 control chars mixed into ~80 chars of real text - well
        # under the 10% threshold, mirrors test_router.py's own
        # equivalent boundary case for the same underlying ratio.
        noisy = "\x01\x02\x03" + ("This is ordinary recovered prose text. " * 2)
        document = _build_document([noisy])
        document.pages[0].extraction_method = ExtractionMethod.DOCLING

        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "OCR_002"] == []

    def test_direct_text_page_is_never_evaluated_even_with_artifacts(self) -> None:
        # Scope is DOCLING/SURYA only - a DIRECT_TEXT page already
        # passed this exact gate at classification time and is not
        # re-evaluated here, regardless of its text content.
        garbled = chr(0xFFFD) * 40 + "ok"
        document = _build_document([garbled])
        document.pages[0].extraction_method = ExtractionMethod.DIRECT_TEXT_EXTRACTION

        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "OCR_002"] == []

    def test_surya_page_that_recovered_nothing_is_not_flagged(self) -> None:
        # OCR was attempted (extraction_method=SURYA) but recovered
        # empty text - ratio is 0.0 by construction, not a garbled-text
        # case; "recovered nothing" is a separate, already-observable
        # condition (DOC_001), not artifact noise.
        document = _build_document([""])
        document.pages[0].extraction_method = ExtractionMethod.SURYA

        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "OCR_002"] == []

    def test_ocr_pending_page_is_not_evaluated(self) -> None:
        garbled = chr(0xFFFD) * 40 + "ok"
        document = _build_document([garbled])
        document.pages[0].extraction_method = ExtractionMethod.OCR_PENDING

        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "OCR_002"] == []

    def test_multiple_garbled_ocr_pages_each_produce_their_own_issue(self) -> None:
        garbled = chr(0xFFFD) * 40 + "ok"
        document = _build_document([garbled, "clean text here", garbled])
        document.pages[0].extraction_method = ExtractionMethod.DOCLING
        document.pages[1].extraction_method = ExtractionMethod.DOCLING
        document.pages[2].extraction_method = ExtractionMethod.SURYA

        issues = validate_document(document)
        artifacts = [i for i in issues if i.rule_id == "OCR_002"]
        assert len(artifacts) == 2
        assert {i.page_number for i in artifacts} == {1, 3}


class TestMissingImages:
    def test_missing_image_file_is_error(self, tmp_path: Path) -> None:
        document = _build_document(["Doc Title"])
        document.images.append(
            Image(
                image_id="img-1",
                page_number=1,
                file_path=str(tmp_path / "missing.png"),
                extraction_failed=False,
            )
        )

        issues = validate_document(document)
        missing_file = [i for i in issues if i.rule_id == "IMAGE_001"]
        assert len(missing_file) == 1
        assert missing_file[0].severity == Severity.ERROR
        assert missing_file[0].page_number == 1

    def test_failed_extraction_is_error_and_not_double_reported_as_missing_file(
        self, tmp_path: Path
    ) -> None:
        document = _build_document(["Doc Title"])
        document.images.append(
            Image(
                image_id="img-1",
                page_number=1,
                file_path=str(tmp_path / "never_written.png"),
                extraction_failed=True,
            )
        )

        issues = validate_document(document)
        failed = [i for i in issues if i.rule_id == "IMAGE_002"]
        missing_file = [i for i in issues if i.rule_id == "IMAGE_001"]
        assert len(failed) == 1
        assert failed[0].severity == Severity.ERROR
        assert missing_file == []  # IMAGE_001 defers to IMAGE_002 for failed extractions

    def test_successful_extraction_with_real_file_has_no_image_issues(self, tmp_path: Path) -> None:
        real_file = tmp_path / "ok.png"
        real_file.write_bytes(b"not a real png but a real file")
        document = _build_document(["Doc Title"], image_count=1)
        document.images.append(
            Image(image_id="img-1", page_number=1, file_path=str(real_file), extraction_failed=False)
        )

        issues = validate_document(document)
        image_issues = [i for i in issues if i.rule_id.startswith("IMAGE_")]
        assert image_issues == []


class TestPendingAltTextReview:
    """Phase F.3: IMAGE_004 flags every image whose Figure.alt_text_status
    is still PENDING_REVIEW."""

    def test_pending_review_image_is_info(self, tmp_path: Path) -> None:
        real_file = tmp_path / "a.png"
        real_file.write_bytes(b"data")
        document = _build_document(["Doc Title"], image_count=1)
        document.images.append(
            Image(
                image_id="img-1",
                page_number=1,
                file_path=str(real_file),
                figure=Figure(
                    alt_text="Image from page 1: description pending human review",
                    alt_text_status=AltTextStatus.PENDING_REVIEW,
                ),
            )
        )

        issues = validate_document(document)
        pending = [i for i in issues if i.rule_id == "IMAGE_004"]
        assert len(pending) == 1
        assert pending[0].severity == Severity.INFO
        assert pending[0].page_number == 1

    def test_human_reviewed_image_is_not_flagged(self, tmp_path: Path) -> None:
        real_file = tmp_path / "a.png"
        real_file.write_bytes(b"data")
        document = _build_document(["Doc Title"], image_count=1)
        document.images.append(
            Image(
                image_id="img-1",
                page_number=1,
                file_path=str(real_file),
                figure=Figure(
                    alt_text="A human-confirmed description.",
                    alt_text_status=AltTextStatus.HUMAN_REVIEWED,
                ),
            )
        )

        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "IMAGE_004"] == []

    def test_image_with_no_figure_is_not_flagged(self, tmp_path: Path) -> None:
        # No Figure at all (e.g. extraction failed, or a pre-Phase-F.3
        # Image) - nothing to review, not a defect this check reports.
        real_file = tmp_path / "a.png"
        real_file.write_bytes(b"data")
        document = _build_document(["Doc Title"], image_count=1)
        document.images.append(Image(image_id="img-1", page_number=1, file_path=str(real_file)))

        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "IMAGE_004"] == []

    def test_multiple_pending_images_each_produce_their_own_issue(self, tmp_path: Path) -> None:
        real_file = tmp_path / "a.png"
        real_file.write_bytes(b"data")
        document = _build_document(["Doc Title"], image_count=2)
        for image_id, page_number in [("img-1", 1), ("img-2", 1)]:
            document.images.append(
                Image(
                    image_id=image_id,
                    page_number=page_number,
                    file_path=str(real_file),
                    figure=Figure(
                        alt_text="placeholder",
                        alt_text_status=AltTextStatus.PENDING_REVIEW,
                    ),
                )
            )

        issues = validate_document(document)
        pending = [i for i in issues if i.rule_id == "IMAGE_004"]
        assert len(pending) == 2


def _footnote(
    note_type: NoteType = NoteType.FOOTNOTE,
    number: int = 1,
    anchor_page_number: int = 1,
) -> Footnote:
    return Footnote(
        note_type=note_type,
        number=number,
        marker="¹",
        anchor_page_number=anchor_page_number,
        anchor_text="A claim with a marker¹.",
        body="A note body.",
        body_page_number=anchor_page_number,
        body_source_text="¹ A note body.",
    )


class TestFootnoteEndnoteDetectedChecks:
    """Phase K: NOTE_001/NOTE_002 match docs/VALIDATION_RULES.md's
    documented Info examples verbatim ("Footnote detected", "Endnote
    detected")."""

    def test_footnote_produces_note_001_info(self) -> None:
        document = _build_document(["Doc Title"])
        document.footnotes = [_footnote(note_type=NoteType.FOOTNOTE)]

        issues = validate_document(document)
        footnote_issues = [i for i in issues if i.rule_id == "NOTE_001"]
        assert len(footnote_issues) == 1
        assert footnote_issues[0].severity == Severity.INFO
        assert footnote_issues[0].page_number == 1
        assert [i for i in issues if i.rule_id == "NOTE_002"] == []

    def test_endnote_produces_note_002_info(self) -> None:
        document = _build_document(["Doc Title"])
        document.footnotes = [_footnote(note_type=NoteType.ENDNOTE)]

        issues = validate_document(document)
        endnote_issues = [i for i in issues if i.rule_id == "NOTE_002"]
        assert len(endnote_issues) == 1
        assert endnote_issues[0].severity == Severity.INFO
        assert [i for i in issues if i.rule_id == "NOTE_001"] == []

    def test_multiple_notes_each_produce_their_own_issue(self) -> None:
        document = _build_document(["Doc Title"])
        document.footnotes = [
            _footnote(note_type=NoteType.FOOTNOTE, number=1, anchor_page_number=1),
            _footnote(note_type=NoteType.FOOTNOTE, number=2, anchor_page_number=1),
            _footnote(note_type=NoteType.ENDNOTE, number=1, anchor_page_number=1),
        ]

        issues = validate_document(document)
        assert len([i for i in issues if i.rule_id == "NOTE_001"]) == 2
        assert len([i for i in issues if i.rule_id == "NOTE_002"]) == 1

    def test_no_footnotes_produces_no_note_issues(self) -> None:
        document = _build_document(["Doc Title"])
        issues = validate_document(document)
        assert [i for i in issues if i.rule_id.startswith("NOTE_")] == []


class TestDuplicateImageIds:
    def test_duplicate_image_id_is_error(self, tmp_path: Path) -> None:
        real_file = tmp_path / "a.png"
        real_file.write_bytes(b"data")
        document = _build_document(["Doc Title"], image_count=2)
        document.images.append(Image(image_id="dup-id", page_number=1, file_path=str(real_file)))
        document.images.append(Image(image_id="dup-id", page_number=1, file_path=str(real_file)))

        issues = validate_document(document)
        duplicates = [i for i in issues if i.rule_id == "IMAGE_003"]
        assert len(duplicates) == 1
        assert duplicates[0].severity == Severity.ERROR

    def test_unique_image_ids_produce_no_duplicate_issue(self, tmp_path: Path) -> None:
        real_file = tmp_path / "a.png"
        real_file.write_bytes(b"data")
        document = _build_document(["Doc Title"], image_count=2)
        document.images.append(Image(image_id="img-1", page_number=1, file_path=str(real_file)))
        document.images.append(Image(image_id="img-2", page_number=1, file_path=str(real_file)))

        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "IMAGE_003"] == []


class TestDocxEmbeddingVerification:
    """016E / IMAGE_005: post-generation embedding verification.

    embedded_in_docx=False on a healthy image (file exists, extraction
    succeeded) means the DOCX generator's _add_image() silently dropped it.
    IMAGE_005 surfaces these as WARNING. Images already covered by IMAGE_001
    (missing file) or IMAGE_002 (extraction failed) are not double-reported.
    Images with embedded_in_docx=None (pre-generation) are not flagged.
    """

    def test_embedding_failure_is_warning(self, tmp_path: Path) -> None:
        real_file = tmp_path / "ok.png"
        real_file.write_bytes(b"data")
        document = _build_document(["Doc Title"], image_count=1)
        document.images.append(
            Image(
                image_id="img-1",
                page_number=2,
                file_path=str(real_file),
                embedded_in_docx=False,
            )
        )

        issues = validate_document(document)
        failures = [i for i in issues if i.rule_id == "IMAGE_005"]
        assert len(failures) == 1
        assert failures[0].severity == Severity.WARNING
        assert failures[0].page_number == 2

    def test_successfully_embedded_image_is_not_flagged(self, tmp_path: Path) -> None:
        real_file = tmp_path / "ok.png"
        real_file.write_bytes(b"data")
        document = _build_document(["Doc Title"], image_count=1)
        document.images.append(
            Image(image_id="img-1", page_number=1, file_path=str(real_file), embedded_in_docx=True)
        )

        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "IMAGE_005"] == []

    def test_pre_generation_image_none_is_not_flagged(self, tmp_path: Path) -> None:
        real_file = tmp_path / "ok.png"
        real_file.write_bytes(b"data")
        document = _build_document(["Doc Title"], image_count=1)
        document.images.append(
            Image(image_id="img-1", page_number=1, file_path=str(real_file))
            # embedded_in_docx defaults to None
        )

        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "IMAGE_005"] == []

    def test_extraction_failed_image_not_double_reported_as_005(self, tmp_path: Path) -> None:
        document = _build_document(["Doc Title"], image_count=1)
        document.images.append(
            Image(
                image_id="img-1",
                page_number=1,
                file_path=str(tmp_path / "never_written.png"),
                extraction_failed=True,
                embedded_in_docx=False,
            )
        )

        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "IMAGE_005"] == []
        assert len([i for i in issues if i.rule_id == "IMAGE_002"]) == 1

    def test_missing_file_not_double_reported_as_005(self, tmp_path: Path) -> None:
        document = _build_document(["Doc Title"], image_count=1)
        document.images.append(
            Image(
                image_id="img-1",
                page_number=1,
                file_path=str(tmp_path / "gone.png"),
                extraction_failed=False,
                embedded_in_docx=False,
            )
        )

        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "IMAGE_005"] == []
        assert len([i for i in issues if i.rule_id == "IMAGE_001"]) == 1

    def test_multiple_embedding_failures_each_produce_issue(self, tmp_path: Path) -> None:
        real_a = tmp_path / "a.png"
        real_b = tmp_path / "b.png"
        real_a.write_bytes(b"data")
        real_b.write_bytes(b"data")
        document = _build_document(["Doc Title"], image_count=2)
        document.images.append(
            Image(image_id="img-1", page_number=1, file_path=str(real_a), embedded_in_docx=False)
        )
        document.images.append(
            Image(image_id="img-2", page_number=2, file_path=str(real_b), embedded_in_docx=False)
        )

        issues = validate_document(document)
        failures = [i for i in issues if i.rule_id == "IMAGE_005"]
        assert len(failures) == 2
        assert {f.page_number for f in failures} == {1, 2}


class TestEmptyDocuments:
    def test_zero_pages_is_error(self) -> None:
        document = Document(source_pdf_path="dummy.pdf", metadata=Metadata(filename="dummy.pdf"))

        issues = validate_document(document)
        zero_pages = [i for i in issues if i.rule_id == "DOC_003"]
        assert len(zero_pages) == 1
        assert zero_pages[0].severity == Severity.ERROR
        assert zero_pages[0].page_number is None

    def test_pages_with_no_content_is_flagged_as_empty_document(self) -> None:
        document = _build_document([""])

        issues = validate_document(document)
        empty_doc = [i for i in issues if i.rule_id == "DOC_001"]
        assert len(empty_doc) == 1
        assert empty_doc[0].severity == Severity.WARNING

    def test_page_with_text_is_not_flagged_as_empty_document(self) -> None:
        document = _build_document(["some real text content"])
        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "DOC_001"] == []


class TestMetadataConsistency:
    def test_page_count_mismatch_is_warning(self) -> None:
        document = _build_document(["one", "two"])
        document.metadata.page_count = 99

        issues = validate_document(document)
        mismatches = [i for i in issues if i.rule_id == "DOC_002" and "page_count" in i.message]
        assert len(mismatches) == 1
        assert mismatches[0].severity == Severity.WARNING

    def test_image_count_mismatch_is_warning(self) -> None:
        document = _build_document(["one"])
        document.metadata.image_count = 5  # document.images is still empty

        issues = validate_document(document)
        mismatches = [i for i in issues if i.rule_id == "DOC_002" and "image_count" in i.message]
        assert len(mismatches) == 1
        assert mismatches[0].severity == Severity.WARNING

    def test_missing_processing_date_is_info(self) -> None:
        document = _build_document(["one"])
        document.metadata.processing_date = None

        issues = validate_document(document)
        info_issues = [
            i for i in issues if i.rule_id == "DOC_002" and i.severity == Severity.INFO
        ]
        assert len(info_issues) == 1


class TestXmlInvalidCharacters:
    """DOC_004 (XML Sanitization Architecture, Layer 2): a read-only
    disclosure of document.sanitization_events - this rule detects
    nothing itself, since Layer 1 has already removed the offending
    character from every Page/TextBlock field by the time this runs.
    Severity is Warning, not Error - see docs/DECISIONS_LOG.md (the
    architecture review's severity re-derivation) and
    docs/VALIDATION_RULES.md: by the time DOC_004 can possibly fire,
    the document has already generated successfully, so "processing
    quality is compromised" (Error's own definition) is false every
    time this rule runs, by construction."""

    def test_sanitization_event_produces_warning_not_error(self) -> None:
        document = _build_document(["Doc Title\nbody"])
        document.sanitization_events = [
            SanitizationEvent(page_number=1, field="page_text", removed_codepoints=["U+0001"])
        ]

        issues = validate_document(document)
        doc_004 = [i for i in issues if i.rule_id == "DOC_004"]
        assert len(doc_004) == 1
        assert doc_004[0].severity == Severity.WARNING
        assert doc_004[0].page_number == 1

    def test_message_discloses_what_was_removed(self) -> None:
        document = _build_document(["Doc Title\nbody"])
        document.sanitization_events = [
            SanitizationEvent(
                page_number=2, field="text_block", removed_codepoints=["U+0001", "U+0002"]
            )
        ]

        issues = validate_document(document)
        message = next(i for i in issues if i.rule_id == "DOC_004").message
        assert "U+0001" in message
        assert "U+0002" in message
        assert "text_block" in message
        assert "page 2" in message

    def test_no_sanitization_events_produces_no_doc_004_issue(self) -> None:
        document = _build_document(["Doc Title\nbody"])
        assert document.sanitization_events == []

        issues = validate_document(document)
        assert [i for i in issues if i.rule_id == "DOC_004"] == []

    def test_multiple_events_each_produce_their_own_issue(self) -> None:
        document = _build_document(["one", "two"])
        document.sanitization_events = [
            SanitizationEvent(page_number=1, field="page_text", removed_codepoints=["U+0001"]),
            SanitizationEvent(page_number=2, field="text_block", removed_codepoints=["U+0002"]),
        ]

        issues = validate_document(document)
        doc_004 = [i for i in issues if i.rule_id == "DOC_004"]
        assert len(doc_004) == 2
        assert {i.page_number for i in doc_004} == {1, 2}


class TestValidationDoesNotMutateDocument:
    def test_document_is_unchanged_after_validation(self) -> None:
        document = _build_document(["Doc Title\nIntroduction\nbody"])
        pages_before = list(document.pages)
        headings_before = list(document.headings)
        images_before = list(document.images)

        validate_document(document)

        assert document.pages == pages_before
        assert document.headings == headings_before
        assert document.images == images_before
        assert document.validation_issues == []  # validator never assigns into the Document


class TestCrossSourceVerificationFindings:
    """_check_cross_source_verification (src/validation/validator.py) is a
    thin, generic bridge: it hands document.verification_findings to the
    engine and trusts whatever RuleSpec the owning AssetVerifier registered.
    These tests exercise that bridge directly with the real, registered
    FigureAssetVerifier (src/verification/figures.py) rather than
    re-deriving findings through a full pipeline run.
    """

    def test_no_findings_produces_no_issues(self) -> None:
        document = _build_document(["body text"])
        assert document.verification_findings == []
        assert validate_document(document) == []

    def test_figure_finding_becomes_image_verify_issue(self) -> None:
        from src.models.verification import Finding
        import src.verification.figures  # noqa: F401 - registers FigureAssetVerifier

        document = _build_document(["body text"])
        document.verification_findings.append(
            Finding(
                asset_type="figure",
                kind="orphan",
                object_id=None,
                confidence=None,
                evidence="uploaded_filename=fig1.png",
                message="Uploaded image 'fig1.png' was not referenced by any figure in the MMD.",
            )
        )

        issues = validate_document(document)

        matches = [i for i in issues if i.rule_id == "IMAGE_VERIFY_003"]
        assert len(matches) == 1
        assert matches[0].severity == Severity.WARNING
        assert "fig1.png" in matches[0].message

    def test_unknown_kind_is_silently_skipped(self) -> None:
        from src.models.verification import Finding
        import src.verification.figures  # noqa: F401

        document = _build_document(["body text"])
        document.verification_findings.append(
            Finding(asset_type="figure", kind="not_a_real_kind", message="should be ignored")
        )

        assert validate_document(document) == []


@pytest.mark.parametrize("sample_pdf_path", SAMPLE_PDFS, ids=[p.name for p in SAMPLE_PDFS])
class TestValidationWithRealPdfs:
    def test_runs_without_error_and_flags_known_pipeline_gaps(self, sample_pdf_path: Path) -> None:
        # OCR is not implemented yet, so every real sample currently
        # has no extracted text, content headings, or images.
        document = parse_pdf(sample_pdf_path)
        detect_headings(document)

        issues = validate_document(document)

        assert any(i.rule_id == "DOC_001" for i in issues)
        assert any(i.rule_id == "HEADING_002" for i in issues)
        assert [i for i in issues if i.rule_id == "PAGE_001"] == []
