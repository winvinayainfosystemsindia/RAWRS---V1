"""Tests for src/parser/pdf_parser.py."""

from datetime import datetime
from pathlib import Path

import fitz
import pytest

import src.parser.pdf_parser as pdf_parser_module
from src.models.contracts import Document, ProcessingStatus
from src.parser.pdf_parser import PDFParserError, page_text_layer, parse_pdf

SAMPLE_PDF_DIR = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"

SAMPLE_PDFS = sorted(SAMPLE_PDF_DIR.glob("*.pdf"))


@pytest.fixture(params=SAMPLE_PDFS, ids=[p.name for p in SAMPLE_PDFS])
def sample_pdf_path(request: pytest.FixtureRequest) -> Path:
    return request.param


def _expected_page_count(pdf_path: Path) -> int:
    with fitz.open(pdf_path) as doc:
        return doc.page_count


class TestParsePdfSuccess:
    def test_returns_document_instance(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(sample_pdf_path)
        assert isinstance(document, Document)

    def test_source_pdf_path_is_recorded(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(sample_pdf_path)
        assert document.source_pdf_path == str(sample_pdf_path)

    def test_processing_status_is_parsed(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(sample_pdf_path)
        assert document.processing_status == ProcessingStatus.PARSED

    def test_page_count_matches_pdf(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(sample_pdf_path)
        expected = _expected_page_count(sample_pdf_path)
        assert document.metadata.page_count == expected
        assert len(document.pages) == expected

    def test_pages_are_sequential_starting_at_one(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(sample_pdf_path)
        page_numbers = [page.page_number for page in document.pages]
        assert page_numbers == list(range(1, len(document.pages) + 1))

    def test_pages_have_no_text_content_yet(self, sample_pdf_path: Path) -> None:
        # OCR/text extraction is out of scope for the parser; pages should
        # start empty for the OCR stage to populate.
        document = parse_pdf(sample_pdf_path)
        for page in document.pages:
            assert page.raw_text == ""
            assert page.cleaned_text == ""
            assert page.ocr_confidence is None

    def test_metadata_filename_matches_source_file(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(sample_pdf_path)
        assert document.metadata.filename == sample_pdf_path.name

    def test_metadata_processing_date_is_set(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(sample_pdf_path)
        assert isinstance(document.metadata.processing_date, datetime)

    def test_metadata_processing_duration_is_non_negative(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(sample_pdf_path)
        assert document.metadata.processing_duration_seconds is not None
        assert document.metadata.processing_duration_seconds >= 0

    def test_metadata_image_count_defaults_to_zero(self, sample_pdf_path: Path) -> None:
        # Image extraction is a later pipeline stage, out of scope here.
        document = parse_pdf(sample_pdf_path)
        assert document.metadata.image_count == 0

    def test_no_headings_images_or_validation_issues_yet(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(sample_pdf_path)
        assert document.headings == []
        assert document.images == []
        assert document.validation_issues == []

    def test_accepts_string_path(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(str(sample_pdf_path))
        assert document.metadata.filename == sample_pdf_path.name


class TestParsePdfErrors:
    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        missing_path = tmp_path / "does_not_exist.pdf"
        with pytest.raises(FileNotFoundError):
            parse_pdf(missing_path)

    def test_directory_path_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            parse_pdf(tmp_path)

    def test_non_pdf_file_raises_pdf_parser_error(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "not_a_pdf.pdf"
        bad_file.write_text("this is not a valid pdf file")
        with pytest.raises(PDFParserError):
            parse_pdf(bad_file)

    def test_empty_pdf_raises_pdf_parser_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # PyMuPDF refuses to even save a zero-page PDF, so a page-less PDF
        # is not constructible as a real fixture file. Instead, simulate
        # one by patching fitz.open to return a zero-page document.
        class _ZeroPageDocument:
            page_count = 0
            metadata = {}

            def __enter__(self) -> "_ZeroPageDocument":
                return self

            def __exit__(self, *args: object) -> bool:
                return False

        pdf_path = tmp_path / "zero_page.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 placeholder")

        monkeypatch.setattr(
            pdf_parser_module.fitz, "open", lambda *_a, **_kw: _ZeroPageDocument()
        )

        with pytest.raises(PDFParserError):
            parse_pdf(pdf_path)


def _write_text_pdf(path: Path, page_texts: list) -> Path:
    """A born-digital PDF: one page per string, that string drawn on it."""
    with fitz.open() as doc:
        for text in page_texts:
            page = doc.new_page()
            if text:
                page.insert_text((72, 72), text)
        doc.save(str(path))
    return path


def _write_scanned_pdf(path: Path, page_texts: list) -> Path:
    """The same pages rasterised: pixels only, no text layer — a scan."""
    source = _write_text_pdf(path.with_name("_source_" + path.name), page_texts)
    with fitz.open(str(source)) as origin, fitz.open() as scan:
        for page in origin:
            pixmap = page.get_pixmap()
            target = scan.new_page(width=page.rect.width, height=page.rect.height)
            target.insert_image(target.rect, pixmap=pixmap)
        scan.save(str(path))
    source.unlink()
    return path


class TestPageTextLayer:
    """P-1 evidence reader: the PDF's own text, per physical page.

    Every case here pins a property the alignment milestone will rely on —
    one entry per page, in page order, silence where a page can prove
    nothing, and no side effect of any kind.
    """

    def test_one_entry_per_page_in_page_order(self, tmp_path: Path) -> None:
        pdf = _write_text_pdf(tmp_path / "three.pdf", ["Alpha one", "Beta two", "Gamma three"])

        texts = page_text_layer(pdf)

        assert len(texts) == 3
        assert "Alpha" in texts[0] and "Beta" in texts[1] and "Gamma" in texts[2]

    def test_a_page_with_no_text_layer_yields_an_empty_string(self, tmp_path: Path) -> None:
        pdf = _write_text_pdf(tmp_path / "gap.pdf", ["Alpha one", "", "Gamma three"])

        texts = page_text_layer(pdf)

        assert texts[1].strip() == ""
        assert "Alpha" in texts[0] and "Gamma" in texts[2]

    def test_a_scanned_pdf_yields_only_empty_strings(self, tmp_path: Path) -> None:
        pdf = _write_scanned_pdf(tmp_path / "scan.pdf", ["Alpha one", "Beta two"])

        texts = page_text_layer(pdf)

        assert len(texts) == 2
        assert all(text.strip() == "" for text in texts)

    def test_entry_count_matches_the_pdf_page_count(self, sample_pdf_path: Path) -> None:
        assert len(page_text_layer(sample_pdf_path)) == _expected_page_count(sample_pdf_path)

    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        # Same contract as parse_pdf: one module, one behaviour.
        with pytest.raises(FileNotFoundError):
            page_text_layer(tmp_path / "does_not_exist.pdf")

    def test_unreadable_file_raises_pdf_parser_error(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "not_a_pdf.pdf"
        bad_file.write_text("this is not a valid pdf file")

        with pytest.raises(PDFParserError):
            page_text_layer(bad_file)

    def test_reading_leaves_no_trace(self, tmp_path: Path) -> None:
        """No cache, no companion file, no mutation of a parsed Document,
        and no dependence on having been called before."""
        pdf = _write_text_pdf(tmp_path / "trace.pdf", ["Alpha one", "Beta two"])
        before = sorted(p.name for p in tmp_path.iterdir())
        document = parse_pdf(pdf)

        first = page_text_layer(pdf)
        second = page_text_layer(pdf)

        assert first == second
        assert sorted(p.name for p in tmp_path.iterdir()) == before
        assert [page.raw_text for page in document.pages] == ["", ""]
        assert [page.cleaned_text for page in document.pages] == ["", ""]
