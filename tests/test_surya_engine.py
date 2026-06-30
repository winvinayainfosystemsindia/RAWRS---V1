"""Tests for src/ocr/surya_engine.py (Phase D.2: Surya OCR fallback).

Most tests here mock the Surya predictor boundary
(src.ocr.surya_engine.build_recognition_predictor) so they run fast and
deterministically, without needing model downloads or real inference.
PDF rasterization (src.ocr.surya_engine.render_page_to_image, backed by
PyMuPDF) is exercised for real against tiny in-memory PDFs created with
fitz - unlike Docling, this is cheap and does not need mocking to keep
the suite fast.

A small number of tests are marked real_surya and intentionally scoped
to a single page each, to keep the added suite runtime bounded while
still proving the real library integration actually works end-to-end
against real benchmark content (not just our own mocks of it).
"""

from pathlib import Path
from typing import List, Union

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
from src.ocr.docling_engine import OCRTimingMetrics
from src.ocr.surya_engine import SuryaOCRError, run_surya_ocr
from src.parser.pdf_parser import parse_pdf

SAMPLE_PDF_DIR = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"
SCANNED_PDF = a_scanned_pdf()  # manifest-declared (samples/benchmark/manifest.json)


class _FakeBlock:
    def __init__(self, html: str, reading_order: int = 0, skipped: bool = False):
        self.html = html
        self.reading_order = reading_order
        self.skipped = skipped


class _FakePageResult:
    def __init__(self, blocks: List[_FakeBlock]):
        self.blocks = blocks


def _text_result(text: str) -> _FakePageResult:
    return _FakePageResult(blocks=[_FakeBlock(html=f"<p>{text}</p>")])


def _empty_result() -> _FakePageResult:
    return _FakePageResult(blocks=[])


class _FakePredictor:
    """Stands in for a real surya.recognition.RecognitionPredictor.

    outputs: a list consumed in call order (one entry per
    run_surya_ocr -> _run_single_page call). Each entry is either a
    _FakePageResult to return, or an Exception instance to raise,
    simulating a conversion failure for that call.
    """

    def __init__(self, outputs: List[Union[_FakePageResult, Exception]]):
        self._outputs = list(outputs)
        self.call_count = 0

    def __call__(self, images, full_page: bool = True):
        self.call_count += 1
        outcome = self._outputs.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return [outcome]


def _minimal_pdf(path: Path, num_pages: int = 1) -> Path:
    """A tiny, real, valid PDF - render_page_to_image actually opens this."""
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page()
    doc.save(str(path))
    doc.close()
    return path


def _document_with_pages(pages: list, source_pdf_path: str = "dummy.pdf") -> Document:
    return Document(
        source_pdf_path=source_pdf_path,
        metadata=Metadata(filename="dummy.pdf"),
        pages=pages,
    )


def _docling_empty_page(page_number: int) -> Page:
    """A page Docling already attempted and left empty - Surya's trigger state."""
    return Page(
        page_number=page_number,
        page_type=PageType.OCR_REQUIRED,
        extraction_method=ExtractionMethod.DOCLING,
        routing_decision=RoutingDecision.ROUTE_TO_DOCLING,
    )


def _docling_success_page(page_number: int, text: str = "Docling recovered this text.") -> Page:
    return Page(
        page_number=page_number,
        cleaned_text=text,
        raw_text=text,
        ocr_confidence=OCRConfidence.MEDIUM,
        page_type=PageType.OCR_REQUIRED,
        extraction_method=ExtractionMethod.DOCLING,
        routing_decision=RoutingDecision.ROUTE_TO_DOCLING,
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


def _pending_page(page_number: int) -> Page:
    """Never reached Docling at all - must never be sent to Surya either."""
    return Page(
        page_number=page_number,
        page_type=PageType.OCR_REQUIRED,
        extraction_method=ExtractionMethod.OCR_PENDING,
        routing_decision=RoutingDecision.ROUTE_TO_OCR_PLACEHOLDER,
    )


class TestNoFallbackNeeded:
    def test_no_candidate_pages_skips_surya_entirely(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        build_called = {"n": 0}

        def _fail_if_called():
            build_called["n"] += 1
            raise AssertionError("build_recognition_predictor should never be called")

        monkeypatch.setattr("src.ocr.surya_engine.build_recognition_predictor", _fail_if_called)

        pdf_path = _minimal_pdf(tmp_path / "dummy.pdf")
        document = _document_with_pages(
            [_direct_text_page(1), _docling_success_page(2)], source_pdf_path=str(pdf_path)
        )

        result = run_surya_ocr(document)

        assert result is document
        assert build_called["n"] == 0

    def test_direct_text_pages_are_never_touched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_predictor = _FakePredictor(outputs=[])
        monkeypatch.setattr(
            "src.ocr.surya_engine.build_recognition_predictor", lambda: fake_predictor
        )

        pdf_path = _minimal_pdf(tmp_path / "dummy.pdf")
        original_text = "Original direct-extracted text, must survive untouched."
        page = _direct_text_page(1, text=original_text)
        document = _document_with_pages([page], source_pdf_path=str(pdf_path))

        run_surya_ocr(document)

        assert document.pages[0].cleaned_text == original_text
        assert document.pages[0].extraction_method == ExtractionMethod.DIRECT_TEXT_EXTRACTION
        assert fake_predictor.call_count == 0

    def test_docling_success_pages_are_never_touched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_predictor = _FakePredictor(outputs=[])
        monkeypatch.setattr(
            "src.ocr.surya_engine.build_recognition_predictor", lambda: fake_predictor
        )

        pdf_path = _minimal_pdf(tmp_path / "dummy.pdf")
        original_text = "Docling already recovered this - must survive untouched."
        page = _docling_success_page(1, text=original_text)
        document = _document_with_pages([page], source_pdf_path=str(pdf_path))

        run_surya_ocr(document)

        assert document.pages[0].cleaned_text == original_text
        assert document.pages[0].ocr_confidence == OCRConfidence.MEDIUM
        assert fake_predictor.call_count == 0

    def test_still_pending_pages_are_never_touched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A page that never even reached Docling (e.g. enable_ocr=False
        # left it OCR_PENDING) must not be picked up by the fallback -
        # Surya only retries pages Docling itself already attempted.
        fake_predictor = _FakePredictor(outputs=[])
        monkeypatch.setattr(
            "src.ocr.surya_engine.build_recognition_predictor", lambda: fake_predictor
        )

        pdf_path = _minimal_pdf(tmp_path / "dummy.pdf")
        document = _document_with_pages([_pending_page(1)], source_pdf_path=str(pdf_path))

        run_surya_ocr(document)

        assert document.pages[0].extraction_method == ExtractionMethod.OCR_PENDING
        assert fake_predictor.call_count == 0


class TestMockedSuccess:
    def test_recovered_text_populates_page_with_low_confidence(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_predictor = _FakePredictor(outputs=[_text_result("Recovered prose via Surya.")])
        monkeypatch.setattr(
            "src.ocr.surya_engine.build_recognition_predictor", lambda: fake_predictor
        )

        pdf_path = _minimal_pdf(tmp_path / "dummy.pdf")
        document = _document_with_pages([_docling_empty_page(1)], source_pdf_path=str(pdf_path))

        run_surya_ocr(document)
        page = document.pages[0]

        assert "Recovered prose via Surya." in page.raw_text
        assert "Recovered prose via Surya." in page.cleaned_text
        assert page.ocr_confidence == OCRConfidence.LOW
        assert page.extraction_method == ExtractionMethod.SURYA
        assert page.routing_decision == RoutingDecision.ROUTE_TO_SURYA
        # page_type is a historical classification fact, unchanged by the fallback's outcome
        assert page.page_type == PageType.OCR_REQUIRED

    def test_only_docling_empty_pages_are_sent_to_surya(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_predictor = _FakePredictor(outputs=[_text_result("Page two recovered text.")])
        monkeypatch.setattr(
            "src.ocr.surya_engine.build_recognition_predictor", lambda: fake_predictor
        )

        pdf_path = _minimal_pdf(tmp_path / "dummy.pdf", num_pages=3)
        document = _document_with_pages(
            [_direct_text_page(1), _docling_empty_page(2), _docling_success_page(3)],
            source_pdf_path=str(pdf_path),
        )

        run_surya_ocr(document)

        assert fake_predictor.call_count == 1
        assert document.pages[1].cleaned_text == "Page two recovered text."
        assert document.pages[0].extraction_method == ExtractionMethod.DIRECT_TEXT_EXTRACTION
        assert document.pages[2].extraction_method == ExtractionMethod.DOCLING

    def test_multiple_candidate_pages_all_processed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_predictor = _FakePredictor(
            outputs=[_text_result("one"), _text_result("two"), _text_result("three")]
        )
        monkeypatch.setattr(
            "src.ocr.surya_engine.build_recognition_predictor", lambda: fake_predictor
        )

        pdf_path = _minimal_pdf(tmp_path / "dummy.pdf", num_pages=3)
        document = _document_with_pages(
            [_docling_empty_page(1), _docling_empty_page(2), _docling_empty_page(3)],
            source_pdf_path=str(pdf_path),
        )

        run_surya_ocr(document)

        assert fake_predictor.call_count == 3
        assert [p.cleaned_text for p in document.pages] == ["one", "two", "three"]

    def test_blocks_joined_in_reading_order_and_skipped_blocks_omitted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _FakePageResult(
            blocks=[
                _FakeBlock(html="<p>second paragraph</p>", reading_order=1),
                _FakeBlock(html="", reading_order=2, skipped=True),  # e.g. a figure
                _FakeBlock(html="<p>first paragraph</p>", reading_order=0),
            ]
        )
        fake_predictor = _FakePredictor(outputs=[result])
        monkeypatch.setattr(
            "src.ocr.surya_engine.build_recognition_predictor", lambda: fake_predictor
        )

        pdf_path = _minimal_pdf(tmp_path / "dummy.pdf")
        document = _document_with_pages([_docling_empty_page(1)], source_pdf_path=str(pdf_path))

        run_surya_ocr(document)

        assert document.pages[0].cleaned_text == "first paragraph\n\nsecond paragraph"


class TestXmlSanitization:
    """XML Sanitization Architecture, Layer 1: Surya-recovered text
    passes through the same normalize_whitespace() call site as
    Docling's (see test_docling_engine.py's identical test class) -
    this phase extended it to also strip XML-illegal characters."""

    def test_control_character_is_removed_from_recovered_text(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_predictor = _FakePredictor(outputs=[_text_result("before\x01after")])
        monkeypatch.setattr(
            "src.ocr.surya_engine.build_recognition_predictor", lambda: fake_predictor
        )

        pdf_path = _minimal_pdf(tmp_path / "dummy.pdf")
        document = _document_with_pages([_docling_empty_page(1)], source_pdf_path=str(pdf_path))

        run_surya_ocr(document)

        assert "\x01" not in document.pages[0].cleaned_text
        assert "beforeafter" in document.pages[0].cleaned_text
        assert "\x01" in document.pages[0].raw_text  # raw_text stays verbatim

    def test_sanitization_event_is_recorded_on_document(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_predictor = _FakePredictor(outputs=[_text_result("before\x01after")])
        monkeypatch.setattr(
            "src.ocr.surya_engine.build_recognition_predictor", lambda: fake_predictor
        )

        pdf_path = _minimal_pdf(tmp_path / "dummy.pdf")
        document = _document_with_pages([_docling_empty_page(1)], source_pdf_path=str(pdf_path))

        run_surya_ocr(document)

        assert len(document.sanitization_events) == 1
        event = document.sanitization_events[0]
        assert event.page_number == 1
        assert event.field == "page_text"
        assert event.removed_codepoints == ["U+0001"]

    def test_clean_recovered_text_records_no_event(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_predictor = _FakePredictor(outputs=[_text_result("Perfectly clean recovered text.")])
        monkeypatch.setattr(
            "src.ocr.surya_engine.build_recognition_predictor", lambda: fake_predictor
        )

        pdf_path = _minimal_pdf(tmp_path / "dummy.pdf")
        document = _document_with_pages([_docling_empty_page(1)], source_pdf_path=str(pdf_path))

        run_surya_ocr(document)
        assert document.sanitization_events == []


class TestMockedEmptyAndFailure:
    def test_empty_recovered_text_leaves_confidence_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_predictor = _FakePredictor(outputs=[_empty_result()])
        monkeypatch.setattr(
            "src.ocr.surya_engine.build_recognition_predictor", lambda: fake_predictor
        )

        pdf_path = _minimal_pdf(tmp_path / "dummy.pdf")
        document = _document_with_pages([_docling_empty_page(1)], source_pdf_path=str(pdf_path))

        run_surya_ocr(document)
        page = document.pages[0]

        assert page.cleaned_text == ""
        assert page.ocr_confidence is None
        # still recorded as attempted, distinguishing it from "never tried"
        assert page.extraction_method == ExtractionMethod.SURYA
        assert page.routing_decision == RoutingDecision.ROUTE_TO_SURYA

    def test_conversion_failure_on_one_page_does_not_abort_others(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_predictor = _FakePredictor(
            outputs=[RuntimeError("simulated Surya failure on page 1"), _text_result("page two succeeded")]
        )
        monkeypatch.setattr(
            "src.ocr.surya_engine.build_recognition_predictor", lambda: fake_predictor
        )

        pdf_path = _minimal_pdf(tmp_path / "dummy.pdf", num_pages=2)
        document = _document_with_pages(
            [_docling_empty_page(1), _docling_empty_page(2)], source_pdf_path=str(pdf_path)
        )

        run_surya_ocr(document)  # must not raise

        assert document.pages[0].cleaned_text == ""
        assert document.pages[0].ocr_confidence is None
        assert document.pages[0].extraction_method == ExtractionMethod.SURYA
        assert document.pages[1].cleaned_text == "page two succeeded"
        assert document.pages[1].ocr_confidence == OCRConfidence.LOW

    def test_predictor_initialization_failure_raises_surya_ocr_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom():
            raise RuntimeError("simulated model load failure")

        monkeypatch.setattr("src.ocr.surya_engine.build_recognition_predictor", _boom)

        pdf_path = _minimal_pdf(tmp_path / "dummy.pdf")
        document = _document_with_pages([_docling_empty_page(1)], source_pdf_path=str(pdf_path))

        with pytest.raises(SuryaOCRError):
            run_surya_ocr(document)

    def test_rasterization_failure_is_caught_like_any_other_page_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A corrupt/unreadable source PDF should produce the same
        # "attempted but empty" outcome as a Surya prediction failure,
        # not an uncaught exception that aborts the whole document.
        fake_predictor = _FakePredictor(outputs=[_text_result("unreachable")])
        monkeypatch.setattr(
            "src.ocr.surya_engine.build_recognition_predictor", lambda: fake_predictor
        )

        pdf_path = tmp_path / "corrupt.pdf"
        pdf_path.write_bytes(b"not a real pdf")
        document = _document_with_pages([_docling_empty_page(1)], source_pdf_path=str(pdf_path))

        run_surya_ocr(document)  # must not raise

        page = document.pages[0]
        assert page.cleaned_text == ""
        assert page.extraction_method == ExtractionMethod.SURYA
        assert fake_predictor.call_count == 0  # never even reached the predictor


class TestErrorHandling:
    def test_missing_source_pdf_raises_file_not_found(self, tmp_path: Path) -> None:
        document = _document_with_pages(
            [_docling_empty_page(1)], source_pdf_path=str(tmp_path / "missing.pdf")
        )
        with pytest.raises(FileNotFoundError):
            run_surya_ocr(document)

    def test_missing_pdf_with_no_candidate_pages_does_not_raise(self, tmp_path: Path) -> None:
        # The file-existence check only matters once there's actually
        # something to process - a document with nothing for Surya to
        # retry should never even look at the (possibly already-deleted)
        # source file.
        document = _document_with_pages(
            [_direct_text_page(1)], source_pdf_path=str(tmp_path / "missing.pdf")
        )
        run_surya_ocr(document)  # must not raise


class TestTimingMetrics:
    def test_metrics_record_per_page_duration(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_predictor = _FakePredictor(outputs=[_text_result("one"), _text_result("two")])
        monkeypatch.setattr(
            "src.ocr.surya_engine.build_recognition_predictor", lambda: fake_predictor
        )

        pdf_path = _minimal_pdf(tmp_path / "dummy.pdf", num_pages=2)
        document = _document_with_pages(
            [_docling_empty_page(1), _docling_empty_page(2)], source_pdf_path=str(pdf_path)
        )

        metrics = OCRTimingMetrics()
        run_surya_ocr(document, metrics=metrics)

        assert metrics.page_count == 2
        assert set(metrics.per_page_seconds.keys()) == {1, 2}
        assert all(seconds >= 0 for seconds in metrics.per_page_seconds.values())
        assert metrics.total_seconds == pytest.approx(sum(metrics.per_page_seconds.values()))
        assert metrics.average_seconds == pytest.approx(metrics.total_seconds / 2)

    def test_metrics_empty_when_no_pages_processed(self) -> None:
        metrics = OCRTimingMetrics()
        assert metrics.page_count == 0
        assert metrics.total_seconds == 0.0
        assert metrics.average_seconds == 0.0

    def test_failed_page_still_records_timing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_predictor = _FakePredictor(outputs=[RuntimeError("simulated failure")])
        monkeypatch.setattr(
            "src.ocr.surya_engine.build_recognition_predictor", lambda: fake_predictor
        )

        pdf_path = _minimal_pdf(tmp_path / "dummy.pdf")
        document = _document_with_pages([_docling_empty_page(1)], source_pdf_path=str(pdf_path))

        metrics = OCRTimingMetrics()
        run_surya_ocr(document, metrics=metrics)

        assert metrics.page_count == 1
        assert 1 in metrics.per_page_seconds

    def test_separate_metrics_instances_do_not_collide_with_docling(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Regression guard: Docling and Surya must each get their own
        # OCRTimingMetrics instance when both run for the same page
        # number, or one engine's timing silently overwrites the other's.
        fake_predictor = _FakePredictor(outputs=[_text_result("recovered")])
        monkeypatch.setattr(
            "src.ocr.surya_engine.build_recognition_predictor", lambda: fake_predictor
        )

        pdf_path = _minimal_pdf(tmp_path / "dummy.pdf")
        document = _document_with_pages([_docling_empty_page(1)], source_pdf_path=str(pdf_path))

        docling_metrics = OCRTimingMetrics()
        docling_metrics.record(1, 99.0)  # simulates Docling's earlier measurement for page 1
        surya_metrics = OCRTimingMetrics()

        run_surya_ocr(document, metrics=surya_metrics)

        assert docling_metrics.per_page_seconds[1] == 99.0
        assert 1 in surya_metrics.per_page_seconds
        assert surya_metrics.per_page_seconds[1] != 99.0


@pytest.mark.real_surya
class TestRealSuryaIntegration:
    """Real, unmocked Surya calls against actual benchmark content.

    Intentionally scoped to a single page, to keep the added suite
    runtime bounded while still proving the real integration genuinely
    works without exploding routine suite runtime. Forces the page into
    the Docling-empty trigger state manually (rather than depending on
    Docling itself actually failing on a particular benchmark page),
    since this module's contract is "retry whatever is in that state",
    independent of how a page got there.
    """

    def test_oleary_page_recovers_real_text_via_fallback(self, tmp_path: Path) -> None:
        single_page_pdf = tmp_path / "oleary_page2.pdf"
        with fitz.open(SCANNED_PDF) as src:
            single_doc = fitz.open()
            single_doc.insert_pdf(src, from_page=1, to_page=1)  # 0-indexed: page 2
            single_doc.save(str(single_page_pdf))
            single_doc.close()

        document = parse_pdf(single_page_pdf)
        document.pages[0].page_type = PageType.OCR_REQUIRED
        document.pages[0].extraction_method = ExtractionMethod.DOCLING
        document.pages[0].routing_decision = RoutingDecision.ROUTE_TO_DOCLING

        metrics = OCRTimingMetrics()
        run_surya_ocr(document, metrics=metrics)

        page = document.pages[0]
        assert len(page.cleaned_text.strip()) > 0
        assert page.ocr_confidence == OCRConfidence.LOW
        assert page.extraction_method == ExtractionMethod.SURYA
        assert metrics.page_count == 1
        assert metrics.per_page_seconds[1] > 0
