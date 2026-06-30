"""Tests for src/ocr/router.py (Phase D.0: OCR routing layer)."""

from pathlib import Path

import fitz
import pytest

from src.models.contracts import (
    Document,
    ExtractionMethod,
    Metadata,
    OCRConfidence,
    Page,
    PageType,
    RoutingDecision,
)
from conftest import a_scanned_pdf, benchmark_pdfs_with
from src.ocr.extractor import extract_text
from src.ocr.router import classify_page, route_pages
from src.parser.pdf_parser import parse_pdf

SAMPLE_PDF_DIR = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"

# Manifest-declared (samples/benchmark/manifest.json) rather than
# hardcoded by filename or filtered by `!= SCANNED_PDF` identity - the
# latter silently missed additional scanned PDFs added to the corpus
# later (see the Benchmark Infrastructure Audit).
SCANNED_PDF = a_scanned_pdf()
DIGITAL_PDFS = benchmark_pdfs_with("born_digital")

_LONG_ENOUGH_TEXT = "This is a perfectly ordinary sentence of body text with plenty of characters."


def _route(pages_text):
    """Build a Document with the given per-page cleaned_text and route it."""
    pages = [Page(page_number=i + 1, cleaned_text=text) for i, text in enumerate(pages_text)]
    document = Document(
        source_pdf_path="dummy.pdf",
        metadata=Metadata(filename="dummy.pdf"),
        pages=pages,
    )
    return route_pages(document)


class TestClassifyPageUnit:
    """Direct, white-box tests of the classification rule itself."""

    def test_ordinary_text_is_direct_text(self) -> None:
        page = Page(page_number=1, cleaned_text=_LONG_ENOUGH_TEXT)
        assert classify_page(page) == PageType.DIRECT_TEXT

    def test_empty_text_is_ocr_required(self) -> None:
        page = Page(page_number=1, cleaned_text="")
        assert classify_page(page) == PageType.OCR_REQUIRED

    def test_whitespace_only_text_is_ocr_required(self) -> None:
        page = Page(page_number=1, cleaned_text="   \n\n   \t  ")
        assert classify_page(page) == PageType.OCR_REQUIRED

    def test_text_shorter_than_minimum_length_is_ocr_required(self) -> None:
        page = Page(page_number=1, cleaned_text="Page 3")  # 6 chars, well under the floor
        assert classify_page(page) == PageType.OCR_REQUIRED

    def test_garbled_replacement_character_text_is_ocr_required(self) -> None:
        # Simulates a broken font ToUnicode mapping: mostly-unusable
        # characters even though the string is technically non-empty.
        garbled = chr(0xFFFD) * 40 + "ok"
        page = Page(page_number=1, cleaned_text=garbled)
        assert classify_page(page) == PageType.OCR_REQUIRED

    def test_legitimate_typography_is_not_misclassified(self) -> None:
        # Em dashes, curly quotes, and accented characters are all
        # "printable" - this must not be confused with corrupted text.
        text = (
            "The teacher’s role—as both Calderhead and Delpit note—"
            "is to engage with café culture and naïve assumptions critically."
        )
        page = Page(page_number=1, cleaned_text=text)
        assert classify_page(page) == PageType.DIRECT_TEXT

    def test_falls_back_to_raw_text_when_cleaned_text_is_empty(self) -> None:
        page = Page(page_number=1, raw_text=_LONG_ENOUGH_TEXT, cleaned_text="")
        assert classify_page(page) == PageType.DIRECT_TEXT


class TestRoutePages:
    def test_direct_text_page_gets_correct_metadata(self) -> None:
        document = _route([_LONG_ENOUGH_TEXT])
        page = document.pages[0]

        assert page.page_type == PageType.DIRECT_TEXT
        assert page.extraction_method == ExtractionMethod.DIRECT_TEXT_EXTRACTION
        assert page.routing_decision == RoutingDecision.ROUTE_TO_DIRECT_EXTRACTION

    def test_ocr_required_page_gets_correct_metadata(self) -> None:
        document = _route([""])
        page = document.pages[0]

        assert page.page_type == PageType.OCR_REQUIRED
        assert page.extraction_method == ExtractionMethod.OCR_PENDING
        assert page.routing_decision == RoutingDecision.ROUTE_TO_OCR_PLACEHOLDER

    def test_ocr_confidence_cleared_when_downgraded_to_ocr_required(self) -> None:
        # Simulate a page that Phase A marked HIGH confidence (it found
        # *some* text) but whose text is actually unusable garbage -
        # the router must not leave a stale HIGH confidence in place.
        page = Page(
            page_number=1,
            cleaned_text=chr(0xFFFD) * 40,
            ocr_confidence=OCRConfidence.HIGH,
        )
        document = Document(
            source_pdf_path="dummy.pdf", metadata=Metadata(filename="dummy.pdf"), pages=[page]
        )
        route_pages(document)

        assert document.pages[0].page_type == PageType.OCR_REQUIRED
        assert document.pages[0].ocr_confidence is None

    def test_ocr_confidence_untouched_for_direct_text_page(self) -> None:
        page = Page(
            page_number=1, cleaned_text=_LONG_ENOUGH_TEXT, ocr_confidence=OCRConfidence.HIGH
        )
        document = Document(
            source_pdf_path="dummy.pdf", metadata=Metadata(filename="dummy.pdf"), pages=[page]
        )
        route_pages(document)

        assert document.pages[0].ocr_confidence == OCRConfidence.HIGH

    def test_returns_same_document_instance(self) -> None:
        document = _route([_LONG_ENOUGH_TEXT])
        result = route_pages(document)
        assert result is document

    def test_page_ordering_and_count_preserved(self) -> None:
        document = _route([_LONG_ENOUGH_TEXT, "", _LONG_ENOUGH_TEXT])
        assert [p.page_number for p in document.pages] == [1, 2, 3]
        assert [p.page_type for p in document.pages] == [
            PageType.DIRECT_TEXT,
            PageType.OCR_REQUIRED,
            PageType.DIRECT_TEXT,
        ]


class TestMixedDocumentScenarios:
    def test_document_with_one_text_page_and_one_blank_page(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "mixed.pdf"
        doc = fitz.open()
        page1 = doc.new_page()
        page1.insert_text((72, 72), _LONG_ENOUGH_TEXT)
        doc.new_page()  # page two: genuinely blank, no text layer
        doc.save(str(pdf_path))
        doc.close()

        document = parse_pdf(pdf_path)
        extract_text(document)
        route_pages(document)

        assert document.pages[0].page_type == PageType.DIRECT_TEXT
        assert document.pages[1].page_type == PageType.OCR_REQUIRED

    def test_mixed_document_routing_is_independent_per_page(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "mixed3.pdf"
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), _LONG_ENOUGH_TEXT)
        doc.new_page()  # blank
        doc.new_page().insert_text((72, 72), _LONG_ENOUGH_TEXT)
        doc.save(str(pdf_path))
        doc.close()

        document = parse_pdf(pdf_path)
        extract_text(document)
        route_pages(document)

        page_types = [p.page_type for p in document.pages]
        assert page_types == [PageType.DIRECT_TEXT, PageType.OCR_REQUIRED, PageType.DIRECT_TEXT]


class TestEmptyPages:
    def test_fully_empty_document_routes_every_page_to_ocr_required(self) -> None:
        document = _route(["", "", ""])
        assert all(p.page_type == PageType.OCR_REQUIRED for p in document.pages)

    def test_zero_page_document_does_not_raise(self) -> None:
        document = Document(source_pdf_path="dummy.pdf", metadata=Metadata(filename="dummy.pdf"))
        route_pages(document)  # must not raise
        assert document.pages == []


class TestCorruptedPages:
    """"Corrupted" here means the page's extracted text is garbled
    (broken font encoding), not that the PDF file itself is unreadable -
    file-level corruption is already handled by src/ocr/extractor.py.
    """

    def test_mostly_garbled_page_is_ocr_required(self) -> None:
        document = _route([chr(0xFFFD) * 100])
        assert document.pages[0].page_type == PageType.OCR_REQUIRED

    def test_page_with_some_control_characters_mixed_into_real_text(self) -> None:
        noisy = "\x01\x02\x03" + _LONG_ENOUGH_TEXT  # a few stray control chars, mostly clean
        document = _route([noisy])
        # 3 control chars out of ~80 characters is well under the 10%
        # threshold - this should NOT be treated as corrupted.
        assert document.pages[0].page_type == PageType.DIRECT_TEXT

    def test_majority_control_characters_is_ocr_required(self) -> None:
        noisy = ("\x01\x02\x03\x04\x05" * 10) + "ok"
        document = _route([noisy])
        assert document.pages[0].page_type == PageType.OCR_REQUIRED


@pytest.mark.parametrize("sample_pdf_path", DIGITAL_PDFS, ids=[p.name for p in DIGITAL_PDFS])
class TestBornDigitalBenchmarkPdfs:
    def test_most_pages_are_direct_text(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(sample_pdf_path)
        extract_text(document)
        route_pages(document)

        direct_text_count = sum(1 for p in document.pages if p.page_type == PageType.DIRECT_TEXT)
        assert direct_text_count > 0

    def test_every_page_gets_classified(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(sample_pdf_path)
        extract_text(document)
        route_pages(document)

        assert all(p.page_type is not None for p in document.pages)
        assert all(p.extraction_method is not None for p in document.pages)
        assert all(p.routing_decision is not None for p in document.pages)


class TestScannedBenchmarkPdf:
    def test_oleary_every_page_is_ocr_required(self) -> None:
        document = parse_pdf(SCANNED_PDF)
        extract_text(document)
        route_pages(document)

        assert all(p.page_type == PageType.OCR_REQUIRED for p in document.pages)
        assert all(p.extraction_method == ExtractionMethod.OCR_PENDING for p in document.pages)
        assert all(
            p.routing_decision == RoutingDecision.ROUTE_TO_OCR_PLACEHOLDER
            for p in document.pages
        )
        assert all(p.ocr_confidence is None for p in document.pages)

    def test_oleary_page_count_unaffected_by_routing(self) -> None:
        document = parse_pdf(SCANNED_PDF)
        extract_text(document)
        original_count = len(document.pages)
        route_pages(document)
        assert len(document.pages) == original_count


class TestSpecificBenchmarkDocumentExpectations:
    def test_teaching_as_professional_discipline_has_two_ocr_required_pages(self) -> None:
        # Pages 1 and 27 have no extractable text (a cover-image page
        # and a trailing page) - confirmed via direct inspection in the
        # Phase D.0 design analysis.
        path = SAMPLE_PDF_DIR / "4.Teaching as a professional discipline-Chapter 1.pdf"
        document = parse_pdf(path)
        extract_text(document)
        route_pages(document)

        ocr_required_pages = [p.page_number for p in document.pages if p.page_type == PageType.OCR_REQUIRED]
        assert ocr_required_pages == [1, 27]

    def test_calderhead_and_fullan_are_fully_direct_text(self) -> None:
        for filename in [
            "5.Teachingas a profession_Calderhead.pdf",
            "6. Fullan&Hargreaves_teacherasaperson.pdf",
        ]:
            document = parse_pdf(SAMPLE_PDF_DIR / filename)
            extract_text(document)
            route_pages(document)
            assert all(p.page_type == PageType.DIRECT_TEXT for p in document.pages)
