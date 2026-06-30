"""Tests for src/ocr/extractor.py (Phase A: direct text extraction only)."""

from pathlib import Path

import fitz
import pytest

from conftest import a_scanned_pdf, benchmark_pdfs_with
from src.models.contracts import Document, Metadata, OCRConfidence, Page
from src.ocr.extractor import TextExtractionError, extract_text
from src.parser.pdf_parser import parse_pdf

SAMPLE_PDF_DIR = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"
SAMPLE_PDFS = sorted(SAMPLE_PDF_DIR.glob("*.pdf"))

# Manifest-declared (samples/benchmark/manifest.json) rather than
# hardcoded by filename or filtered by `!= SCANNED_PDF` identity - the
# latter silently missed additional scanned PDFs added to the corpus
# later (see the Benchmark Infrastructure Audit).
SCANNED_PDF = a_scanned_pdf()
DIGITAL_PDFS = benchmark_pdfs_with("born_digital")


def _make_text_pdf(path: Path, lines: list) -> None:
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line)
        y += 20
    doc.save(str(path))
    doc.close()


def _make_blank_pdf(path: Path) -> None:
    doc = fitz.open()
    doc.new_page()  # no text, no images - genuinely empty page
    doc.save(str(path))
    doc.close()


class TestTextExtraction:
    def test_populates_raw_and_cleaned_text(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "text.pdf"
        _make_text_pdf(pdf_path, ["Hello world", "Second line"])
        document = parse_pdf(pdf_path)

        result = extract_text(document)

        page = result.pages[0]
        assert "Hello world" in page.raw_text
        assert "Second line" in page.raw_text
        assert "Hello world" in page.cleaned_text
        assert page.ocr_confidence == OCRConfidence.HIGH

    def test_returns_same_document_instance(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "text.pdf"
        _make_text_pdf(pdf_path, ["content"])
        document = parse_pdf(pdf_path)

        result = extract_text(document)
        assert result is document

    def test_cleaned_text_normalizes_excessive_blank_lines(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "text.pdf"
        _make_text_pdf(pdf_path, ["First"] + [""] * 5 + ["Second"])
        document = parse_pdf(pdf_path)

        result = extract_text(document)
        page = result.pages[0]
        assert "\n\n\n" not in page.cleaned_text
        assert "First" in page.raw_text and "Second" in page.raw_text

    def test_page_ordering_is_preserved(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "multi.pdf"
        doc = fitz.open()
        for i in range(1, 6):
            page = doc.new_page()
            page.insert_text((72, 72), f"Page number {i}")
        doc.save(str(pdf_path))
        doc.close()

        document = parse_pdf(pdf_path)
        result = extract_text(document)

        page_numbers = [p.page_number for p in result.pages]
        assert page_numbers == [1, 2, 3, 4, 5]
        for i, page in enumerate(result.pages, start=1):
            assert f"Page number {i}" in page.cleaned_text


class TestEmptyPages:
    def test_page_with_no_text_is_left_untouched(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "blank.pdf"
        _make_blank_pdf(pdf_path)
        document = parse_pdf(pdf_path)

        result = extract_text(document)
        page = result.pages[0]
        assert page.raw_text == ""
        assert page.cleaned_text == ""
        assert page.ocr_confidence is None  # pending OCR, not "low confidence"

    def test_does_not_raise_for_fully_blank_document(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "blank.pdf"
        _make_blank_pdf(pdf_path)
        document = parse_pdf(pdf_path)

        extract_text(document)  # must not raise


class TestMixedContentPdfs:
    def test_only_pages_with_text_are_populated(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "mixed.pdf"
        doc = fitz.open()
        page1 = doc.new_page()
        page1.insert_text((72, 72), "Real extractable text on page one")
        doc.new_page()  # page two: genuinely blank, no text layer
        doc.save(str(pdf_path))
        doc.close()

        document = parse_pdf(pdf_path)
        result = extract_text(document)

        assert "Real extractable text" in result.pages[0].cleaned_text
        assert result.pages[0].ocr_confidence == OCRConfidence.HIGH

        assert result.pages[1].cleaned_text == ""
        assert result.pages[1].ocr_confidence is None

    def test_page_count_unaffected_by_mixed_content(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "mixed.pdf"
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "text page")
        doc.new_page()
        doc.new_page().insert_text((72, 72), "another text page")
        doc.save(str(pdf_path))
        doc.close()

        document = parse_pdf(pdf_path)
        result = extract_text(document)
        assert len(result.pages) == 3


class TestErrorHandling:
    def test_missing_source_pdf_raises_file_not_found(self, tmp_path: Path) -> None:
        document = Document(
            source_pdf_path=str(tmp_path / "missing.pdf"),
            metadata=Metadata(filename="missing.pdf"),
            pages=[Page(page_number=1)],
        )
        with pytest.raises(FileNotFoundError):
            extract_text(document)

    def test_corrupt_source_pdf_raises_text_extraction_error(self, tmp_path: Path) -> None:
        bad_pdf_path = tmp_path / "corrupt.pdf"
        bad_pdf_path.write_text("not a real pdf")
        document = Document(
            source_pdf_path=str(bad_pdf_path),
            metadata=Metadata(filename="corrupt.pdf"),
            pages=[Page(page_number=1)],
        )
        with pytest.raises(TextExtractionError):
            extract_text(document)


@pytest.mark.parametrize("sample_pdf_path", SAMPLE_PDFS, ids=[p.name for p in SAMPLE_PDFS])
class TestBenchmarkPdfs:
    def test_extraction_runs_without_error(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(sample_pdf_path)
        extract_text(document)  # must not raise for any benchmark PDF

    def test_page_count_and_order_preserved(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(sample_pdf_path)
        original_page_numbers = [p.page_number for p in document.pages]

        result = extract_text(document)
        assert [p.page_number for p in result.pages] == original_page_numbers


class TestBenchmarkBornDigitalPdfs:
    @pytest.mark.parametrize("sample_pdf_path", DIGITAL_PDFS, ids=[p.name for p in DIGITAL_PDFS])
    def test_born_digital_pdfs_get_real_text(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(sample_pdf_path)
        result = extract_text(document)

        pages_with_text = [p for p in result.pages if p.cleaned_text.strip()]
        assert len(pages_with_text) > 0
        assert all(p.ocr_confidence == OCRConfidence.HIGH for p in pages_with_text)


class TestBenchmarkScannedPdf:
    def test_scanned_pdf_stays_empty_pending_ocr(self) -> None:
        document = parse_pdf(SCANNED_PDF)
        result = extract_text(document)

        assert all(p.cleaned_text == "" for p in result.pages)
        assert all(p.ocr_confidence is None for p in result.pages)


class TestXmlSanitization:
    """XML Sanitization Architecture, Layer 1: reproduces the production
    failure mode directly - a real PDF whose text layer contains a
    control character (a broken font ToUnicode mapping can legitimately
    decode a glyph to one), confirmed to survive PyMuPDF's own
    insert_text -> save -> get_text round-trip (see the architecture
    review for the empirical verification this is grounded in)."""

    def test_control_character_is_removed_from_cleaned_text(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "dirty.pdf"
        _make_text_pdf(pdf_path, ["before\x01after"])
        document = parse_pdf(pdf_path)

        result = extract_text(document)
        page = result.pages[0]

        assert "\x01" not in page.cleaned_text
        assert "beforeafter" in page.cleaned_text

    def test_raw_text_stays_truly_verbatim(self, tmp_path: Path) -> None:
        # raw_text is a forensic record, deliberately NOT sanitized -
        # only cleaned_text (what every downstream stage reads) is.
        pdf_path = tmp_path / "dirty.pdf"
        _make_text_pdf(pdf_path, ["before\x01after"])
        document = parse_pdf(pdf_path)

        result = extract_text(document)
        assert "\x01" in result.pages[0].raw_text

    def test_sanitization_event_is_recorded(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "dirty.pdf"
        _make_text_pdf(pdf_path, ["before\x01after"])
        document = parse_pdf(pdf_path)

        result = extract_text(document)

        assert len(result.sanitization_events) == 1
        event = result.sanitization_events[0]
        assert event.page_number == 1
        assert event.field == "page_text"
        assert event.removed_codepoints == ["U+0001"]

    def test_clean_pdf_records_no_sanitization_events(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "clean.pdf"
        _make_text_pdf(pdf_path, ["Perfectly ordinary text."])
        document = parse_pdf(pdf_path)

        result = extract_text(document)
        assert result.sanitization_events == []
