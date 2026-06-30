"""Tests for src/ocr/docling_engine.py (Phase D.1: Docling integration).

Most tests here mock the Docling converter boundary
(src.ocr.docling_engine.build_converter) so they run fast and
deterministically, without needing model downloads or the ~1-3
minutes/page Docling's full-page OCR pipeline actually takes (measured
against this project's own benchmark - see
BENCHMARK_RECONCILIATION_AND_PHASE1_PLAN.md Phase D.1).

A small number of tests are marked REAL and intentionally scoped to a
single page each, to keep the added suite runtime bounded while still
proving the real library integration actually works end-to-end against
real benchmark content (not just our own mocks of it).
"""

from pathlib import Path
from typing import Optional

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
from conftest import a_scanned_pdf
from src.ocr.docling_engine import DoclingOCRError, OCRTimingMetrics, run_docling_ocr
from src.parser.pdf_parser import parse_pdf

SAMPLE_PDF_DIR = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"
SCANNED_PDF = a_scanned_pdf()  # manifest-declared (samples/benchmark/manifest.json)


class _FakeDoclingDocument:
    def __init__(self, text: str):
        self._text = text

    def export_to_text(self) -> str:
        return self._text


class _FakeConversionResult:
    def __init__(self, text: str):
        self.document = _FakeDoclingDocument(text)


class _FakeConverter:
    """Stands in for a real docling.DocumentConverter.

    text_by_page: page_number -> text to "recover" for that page.
    Pages not in the dict raise, simulating a conversion failure.
    """

    def __init__(self, text_by_page: dict, raise_for_pages: Optional[set] = None):
        self.text_by_page = text_by_page
        self.raise_for_pages = raise_for_pages or set()
        self.convert_calls = []

    def convert(self, pdf_path, page_range):
        page_number = page_range[0]
        self.convert_calls.append(page_number)
        if page_number in self.raise_for_pages:
            raise RuntimeError(f"simulated Docling failure on page {page_number}")
        return _FakeConversionResult(self.text_by_page.get(page_number, ""))


def _document_with_pages(pages: list, source_pdf_path: str = "dummy.pdf") -> Document:
    return Document(
        source_pdf_path=source_pdf_path,
        metadata=Metadata(filename="dummy.pdf"),
        pages=pages,
    )


def _pending_page(page_number: int) -> Page:
    return Page(
        page_number=page_number,
        page_type=PageType.OCR_REQUIRED,
        extraction_method=ExtractionMethod.OCR_PENDING,
        routing_decision=RoutingDecision.ROUTE_TO_OCR_PLACEHOLDER,
    )


def _direct_text_page(page_number: int, text: str = "Some real direct-extracted text.") -> Page:
    return Page(
        page_number=page_number,
        cleaned_text=text,
        raw_text=text,
        ocr_confidence=OCRConfidence.HIGH,
        page_type=PageType.DIRECT_TEXT,
        extraction_method=ExtractionMethod.DIRECT_TEXT_EXTRACTION,
        routing_decision=RoutingDecision.ROUTE_TO_DIRECT_EXTRACTION,
    )


class TestNoOCRNeeded:
    def test_no_pending_pages_skips_docling_entirely(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        build_called = {"n": 0}

        def _fail_if_called():
            build_called["n"] += 1
            raise AssertionError("build_converter should never be called")

        monkeypatch.setattr("src.ocr.docling_engine.build_converter", _fail_if_called)

        pdf_path = tmp_path / "dummy.pdf"
        pdf_path.write_bytes(b"irrelevant")
        document = _document_with_pages([_direct_text_page(1)], source_pdf_path=str(pdf_path))

        result = run_docling_ocr(document)

        assert result is document
        assert build_called["n"] == 0

    def test_direct_text_pages_are_never_touched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_converter = _FakeConverter(text_by_page={})
        monkeypatch.setattr("src.ocr.docling_engine.build_converter", lambda: fake_converter)

        pdf_path = tmp_path / "dummy.pdf"
        pdf_path.write_bytes(b"irrelevant")
        original_text = "Original direct-extracted text, must survive untouched."
        page = _direct_text_page(1, text=original_text)
        document = _document_with_pages([page], source_pdf_path=str(pdf_path))

        run_docling_ocr(document)

        assert document.pages[0].cleaned_text == original_text
        assert document.pages[0].extraction_method == ExtractionMethod.DIRECT_TEXT_EXTRACTION
        assert document.pages[0].ocr_confidence == OCRConfidence.HIGH
        assert fake_converter.convert_calls == []


class TestMockedSuccess:
    def test_recovered_text_populates_page(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_converter = _FakeConverter(text_by_page={1: "Recovered prose from page one."})
        monkeypatch.setattr("src.ocr.docling_engine.build_converter", lambda: fake_converter)

        pdf_path = tmp_path / "dummy.pdf"
        pdf_path.write_bytes(b"irrelevant")
        document = _document_with_pages([_pending_page(1)], source_pdf_path=str(pdf_path))

        run_docling_ocr(document)
        page = document.pages[0]

        assert "Recovered prose from page one." in page.raw_text
        assert "Recovered prose from page one." in page.cleaned_text
        assert page.ocr_confidence == OCRConfidence.MEDIUM
        assert page.extraction_method == ExtractionMethod.DOCLING
        assert page.routing_decision == RoutingDecision.ROUTE_TO_DOCLING
        # page_type is a historical classification fact, unchanged by OCR's outcome
        assert page.page_type == PageType.OCR_REQUIRED

    def test_only_pending_pages_are_sent_to_docling(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_converter = _FakeConverter(text_by_page={2: "Page two recovered text."})
        monkeypatch.setattr("src.ocr.docling_engine.build_converter", lambda: fake_converter)

        pdf_path = tmp_path / "dummy.pdf"
        pdf_path.write_bytes(b"irrelevant")
        document = _document_with_pages(
            [_direct_text_page(1), _pending_page(2), _direct_text_page(3)],
            source_pdf_path=str(pdf_path),
        )

        run_docling_ocr(document)

        assert fake_converter.convert_calls == [2]
        assert document.pages[1].cleaned_text == "Page two recovered text."
        assert document.pages[0].extraction_method == ExtractionMethod.DIRECT_TEXT_EXTRACTION
        assert document.pages[2].extraction_method == ExtractionMethod.DIRECT_TEXT_EXTRACTION

    def test_multiple_pending_pages_all_processed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_converter = _FakeConverter(text_by_page={1: "one", 2: "two", 3: "three"})
        monkeypatch.setattr("src.ocr.docling_engine.build_converter", lambda: fake_converter)

        pdf_path = tmp_path / "dummy.pdf"
        pdf_path.write_bytes(b"irrelevant")
        document = _document_with_pages(
            [_pending_page(1), _pending_page(2), _pending_page(3)], source_pdf_path=str(pdf_path)
        )

        run_docling_ocr(document)

        assert fake_converter.convert_calls == [1, 2, 3]
        assert [p.cleaned_text for p in document.pages] == ["one", "two", "three"]


class TestXmlSanitization:
    """XML Sanitization Architecture, Layer 1: Docling-recovered text is
    not guaranteed clean any more than direct-extraction text is - both
    pass through the same normalize_whitespace() call site, which this
    phase extended to also strip XML-illegal characters."""

    def test_control_character_is_removed_from_recovered_text(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_converter = _FakeConverter(text_by_page={1: "before\x01after"})
        monkeypatch.setattr("src.ocr.docling_engine.build_converter", lambda: fake_converter)

        pdf_path = tmp_path / "dummy.pdf"
        pdf_path.write_bytes(b"irrelevant")
        document = _document_with_pages([_pending_page(1)], source_pdf_path=str(pdf_path))

        run_docling_ocr(document)

        assert "\x01" not in document.pages[0].cleaned_text
        assert "beforeafter" in document.pages[0].cleaned_text
        assert "\x01" in document.pages[0].raw_text  # raw_text stays verbatim

    def test_sanitization_event_is_recorded_on_document(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_converter = _FakeConverter(text_by_page={1: "before\x01after"})
        monkeypatch.setattr("src.ocr.docling_engine.build_converter", lambda: fake_converter)

        pdf_path = tmp_path / "dummy.pdf"
        pdf_path.write_bytes(b"irrelevant")
        document = _document_with_pages([_pending_page(1)], source_pdf_path=str(pdf_path))

        run_docling_ocr(document)

        assert len(document.sanitization_events) == 1
        event = document.sanitization_events[0]
        assert event.page_number == 1
        assert event.field == "page_text"
        assert event.removed_codepoints == ["U+0001"]

    def test_clean_recovered_text_records_no_event(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_converter = _FakeConverter(text_by_page={1: "Perfectly clean recovered text."})
        monkeypatch.setattr("src.ocr.docling_engine.build_converter", lambda: fake_converter)

        pdf_path = tmp_path / "dummy.pdf"
        pdf_path.write_bytes(b"irrelevant")
        document = _document_with_pages([_pending_page(1)], source_pdf_path=str(pdf_path))

        run_docling_ocr(document)
        assert document.sanitization_events == []


class TestMockedEmptyAndFailure:
    def test_empty_recovered_text_leaves_confidence_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_converter = _FakeConverter(text_by_page={1: ""})
        monkeypatch.setattr("src.ocr.docling_engine.build_converter", lambda: fake_converter)

        pdf_path = tmp_path / "dummy.pdf"
        pdf_path.write_bytes(b"irrelevant")
        document = _document_with_pages([_pending_page(1)], source_pdf_path=str(pdf_path))

        run_docling_ocr(document)
        page = document.pages[0]

        assert page.cleaned_text == ""
        assert page.ocr_confidence is None
        # still recorded as attempted, distinguishing it from "never tried"
        assert page.extraction_method == ExtractionMethod.DOCLING
        assert page.routing_decision == RoutingDecision.ROUTE_TO_DOCLING

    def test_conversion_failure_on_one_page_does_not_abort_others(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_converter = _FakeConverter(
            text_by_page={2: "page two succeeded"}, raise_for_pages={1}
        )
        monkeypatch.setattr("src.ocr.docling_engine.build_converter", lambda: fake_converter)

        pdf_path = tmp_path / "dummy.pdf"
        pdf_path.write_bytes(b"irrelevant")
        document = _document_with_pages(
            [_pending_page(1), _pending_page(2)], source_pdf_path=str(pdf_path)
        )

        run_docling_ocr(document)  # must not raise

        assert document.pages[0].cleaned_text == ""
        assert document.pages[0].ocr_confidence is None
        assert document.pages[0].extraction_method == ExtractionMethod.DOCLING
        assert document.pages[1].cleaned_text == "page two succeeded"
        assert document.pages[1].ocr_confidence == OCRConfidence.MEDIUM

    def test_converter_initialization_failure_raises_docling_ocr_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom():
            raise RuntimeError("simulated model load failure")

        monkeypatch.setattr("src.ocr.docling_engine.build_converter", _boom)

        pdf_path = tmp_path / "dummy.pdf"
        pdf_path.write_bytes(b"irrelevant")
        document = _document_with_pages([_pending_page(1)], source_pdf_path=str(pdf_path))

        with pytest.raises(DoclingOCRError):
            run_docling_ocr(document)


class TestErrorHandling:
    def test_missing_source_pdf_raises_file_not_found(self, tmp_path: Path) -> None:
        document = _document_with_pages(
            [_pending_page(1)], source_pdf_path=str(tmp_path / "missing.pdf")
        )
        with pytest.raises(FileNotFoundError):
            run_docling_ocr(document)

    def test_missing_pdf_with_no_pending_pages_does_not_raise(self, tmp_path: Path) -> None:
        # The file-existence check only matters once there's actually
        # something to process - a fully-direct-text document should
        # never even look at the (possibly already-deleted) source file.
        document = _document_with_pages(
            [_direct_text_page(1)], source_pdf_path=str(tmp_path / "missing.pdf")
        )
        run_docling_ocr(document)  # must not raise


class TestTimingMetrics:
    def test_metrics_record_per_page_duration(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_converter = _FakeConverter(text_by_page={1: "one", 2: "two"})
        monkeypatch.setattr("src.ocr.docling_engine.build_converter", lambda: fake_converter)

        pdf_path = tmp_path / "dummy.pdf"
        pdf_path.write_bytes(b"irrelevant")
        document = _document_with_pages(
            [_pending_page(1), _pending_page(2)], source_pdf_path=str(pdf_path)
        )

        metrics = OCRTimingMetrics()
        run_docling_ocr(document, metrics=metrics)

        assert metrics.page_count == 2
        assert set(metrics.per_page_seconds.keys()) == {1, 2}
        assert all(seconds >= 0 for seconds in metrics.per_page_seconds.values())
        assert metrics.total_seconds == pytest.approx(
            sum(metrics.per_page_seconds.values())
        )
        assert metrics.average_seconds == pytest.approx(metrics.total_seconds / 2)

    def test_metrics_empty_when_no_pages_processed(self) -> None:
        metrics = OCRTimingMetrics()
        assert metrics.page_count == 0
        assert metrics.total_seconds == 0.0
        assert metrics.average_seconds == 0.0

    def test_failed_page_still_records_timing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_converter = _FakeConverter(text_by_page={}, raise_for_pages={1})
        monkeypatch.setattr("src.ocr.docling_engine.build_converter", lambda: fake_converter)

        pdf_path = tmp_path / "dummy.pdf"
        pdf_path.write_bytes(b"irrelevant")
        document = _document_with_pages([_pending_page(1)], source_pdf_path=str(pdf_path))

        metrics = OCRTimingMetrics()
        run_docling_ocr(document, metrics=metrics)

        assert metrics.page_count == 1
        assert 1 in metrics.per_page_seconds


@pytest.mark.real_docling
class TestRealDoclingIntegration:
    """Real, unmocked Docling calls against actual benchmark content.

    Intentionally scoped to a single page per test: Docling's full-page
    OCR pipeline takes roughly 1-3 minutes per page in this environment
    (measured during Phase D.1 design), so this proves the real
    integration genuinely works without exploding routine suite runtime.
    """

    def test_oleary_single_page_recovers_real_text(self, tmp_path: Path) -> None:
        # Extract just page 2 of O'Leary into its own 1-page PDF, so the
        # real Docling call only ever processes one page.
        single_page_pdf = tmp_path / "oleary_page2.pdf"
        with fitz.open(SCANNED_PDF) as src:
            single_doc = fitz.open()
            single_doc.insert_pdf(src, from_page=1, to_page=1)  # 0-indexed: page 2
            single_doc.save(str(single_page_pdf))
            single_doc.close()

        document = parse_pdf(single_page_pdf)
        document.pages[0].page_type = PageType.OCR_REQUIRED
        document.pages[0].extraction_method = ExtractionMethod.OCR_PENDING
        document.pages[0].routing_decision = RoutingDecision.ROUTE_TO_OCR_PLACEHOLDER

        metrics = OCRTimingMetrics()
        run_docling_ocr(document, metrics=metrics)

        page = document.pages[0]
        assert len(page.cleaned_text.strip()) > 0
        assert page.ocr_confidence == OCRConfidence.MEDIUM
        assert page.extraction_method == ExtractionMethod.DOCLING
        assert metrics.page_count == 1
        assert metrics.per_page_seconds[1] > 0
