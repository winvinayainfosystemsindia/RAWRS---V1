"""Tests for src/ocr/targeted.py (FEATURE_019: region-targeted OCR).

Mocks the Surya predictor boundary (src.ocr.targeted.build_recognition_predictor)
the same way tests/test_surya_engine.py does, so these run fast and
deterministically. PDF rasterization (PyMuPDF's own clip-based crop) is
exercised for real against a tiny in-memory PDF.
"""

import time
from pathlib import Path
from typing import List

import fitz
import pytest

from src.models.contracts import BoundingBox
from src.ocr.targeted import TargetedOCRError, TargetedOCRTimeoutError, ocr_region


class _FakeBlock:
    def __init__(self, html: str, reading_order: int = 0, skipped: bool = False):
        self.html = html
        self.reading_order = reading_order
        self.skipped = skipped


class _FakePageResult:
    def __init__(self, blocks: List[_FakeBlock]):
        self.blocks = blocks


class _FakePredictor:
    def __init__(self, output: _FakePageResult):
        self._output = output
        self.calls: List[dict] = []

    def __call__(self, images, full_page: bool = True):
        self.calls.append({"n_images": len(images), "full_page": full_page})
        return [self._output]


def _build_pdf(tmp_path: Path) -> Path:
    pdf_path = tmp_path / "region.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "147", fontsize=10)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


class TestOcrRegion:
    def test_missing_pdf_raises(self, tmp_path: Path):
        with pytest.raises(TargetedOCRError):
            ocr_region(tmp_path / "nope.pdf", 1, BoundingBox(x0=0, y0=0, x1=50, y1=50))

    def test_out_of_range_page_raises(self, tmp_path: Path, monkeypatch):
        pdf_path = _build_pdf(tmp_path)
        with pytest.raises(TargetedOCRError):
            ocr_region(pdf_path, 99, BoundingBox(x0=0, y0=0, x1=50, y1=50))

    def test_recovers_text_from_region(self, tmp_path: Path, monkeypatch):
        pdf_path = _build_pdf(tmp_path)
        fake_predictor = _FakePredictor(_FakePageResult([_FakeBlock(html="<p>147</p>")]))
        monkeypatch.setattr("src.ocr.targeted.build_recognition_predictor", lambda: fake_predictor)

        result = ocr_region(pdf_path, 1, BoundingBox(x0=60, y0=60, x1=120, y1=90))

        assert result == "147"
        # M-5.4: full_page=True is the correct call shape for a pre-cropped
        # region (see src/ocr/targeted.py::ocr_region's own comment) — this
        # assertion previously encoded the pre-M-5.4 (incorrect) behavior.
        assert fake_predictor.calls == [{"n_images": 1, "full_page": True}]

    def test_empty_region_returns_empty_string_not_raise(self, tmp_path: Path, monkeypatch):
        pdf_path = _build_pdf(tmp_path)
        fake_predictor = _FakePredictor(_FakePageResult(blocks=[]))
        monkeypatch.setattr("src.ocr.targeted.build_recognition_predictor", lambda: fake_predictor)

        result = ocr_region(pdf_path, 1, BoundingBox(x0=500, y0=500, x1=550, y1=550))

        assert result == ""

    def test_reuses_surya_engines_shared_parser_not_a_duplicate(self):
        """page_result_to_text is imported, not reimplemented — the same
        function src/ocr/surya_engine.py's whole-page path uses."""
        from src.ocr.surya_engine import page_result_to_text as engine_fn
        from src.ocr.targeted import page_result_to_text as targeted_fn

        assert engine_fn is targeted_fn


class _HangingPredictor:
    """Simulates the real M-5.4.1 failure: a Surya call that never
    returns within any reasonable caller-side wait. Sleeps a bounded,
    short duration (not literally forever) so an abandoned test thread
    finishes on its own well within a test session, rather than
    accumulating indefinitely-blocked threads."""

    def __init__(self, hang_seconds: float):
        self._hang_seconds = hang_seconds
        self.calls = 0

    def __call__(self, images, full_page: bool = True):
        self.calls += 1
        time.sleep(self._hang_seconds)
        return [_FakePageResult([_FakeBlock(html="<p>too late</p>")])]


class _RaisingPredictor:
    def __call__(self, images, full_page: bool = True):
        raise ValueError("Surya blew up")


class TestOcrRegionTimeout:
    """M-5.4.1 — ocr_region() must never block its caller indefinitely.
    A benchmark re-run observed the real Surya call hang on an
    already-warm, cached predictor; these tests exercise the timeout
    wrapper directly (src.ocr.targeted._run_with_timeout via ocr_region),
    not a mock of ocr_region itself.
    """

    def test_hanging_call_raises_timeout_not_blocking_forever(self, tmp_path: Path, monkeypatch):
        pdf_path = _build_pdf(tmp_path)
        monkeypatch.setattr(
            "src.ocr.targeted.build_recognition_predictor",
            lambda: _HangingPredictor(hang_seconds=2.0),
        )

        start = time.monotonic()
        with pytest.raises(TargetedOCRTimeoutError):
            ocr_region(pdf_path, 1, BoundingBox(x0=60, y0=60, x1=120, y1=90), timeout_seconds=0.1)
        elapsed = time.monotonic() - start

        assert elapsed < 1.0, "ocr_region waited far longer than its own timeout"

    def test_timeout_error_is_a_targeted_ocr_error(self):
        """A TargetedOCRTimeoutError must be catchable by every existing
        `except TargetedOCRError` call site (e.g. HeadingVerifier's
        evidence-of-last-resort handling) without any change there."""
        assert issubclass(TargetedOCRTimeoutError, TargetedOCRError)

    def test_repeated_hangs_do_not_compound_across_calls(self, tmp_path: Path, monkeypatch):
        """The critical regression this design guards against: a naive
        shared single-worker timeout implementation would wedge every
        later call behind the first hung thread forever, since a Python
        thread cannot be forcibly cancelled. Two independent hangs must
        each cost only their own timeout, never accumulate."""
        pdf_path = _build_pdf(tmp_path)
        monkeypatch.setattr(
            "src.ocr.targeted.build_recognition_predictor",
            lambda: _HangingPredictor(hang_seconds=1.0),
        )
        bbox = BoundingBox(x0=60, y0=60, x1=120, y1=90)

        start = time.monotonic()
        with pytest.raises(TargetedOCRTimeoutError):
            ocr_region(pdf_path, 1, bbox, timeout_seconds=0.1)
        with pytest.raises(TargetedOCRTimeoutError):
            ocr_region(pdf_path, 1, bbox, timeout_seconds=0.1)
        elapsed = time.monotonic() - start

        # A wedged shared worker would make the second call wait out the
        # first hang too (>=1.0s); two independent, bounded timeouts stay
        # far below that.
        assert elapsed < 0.5

    def test_real_exception_still_propagates_not_swallowed_as_timeout(self, tmp_path: Path, monkeypatch):
        """A genuine failure inside the Surya call (e.g. the real
        ValueError M-5.2's benchmark surfaced) must still propagate as
        itself, not get converted into a timeout — HeadingVerifier's
        broader `except Exception` handling (a different log level,
        "unexpected" not "known-and-handled") depends on seeing the real
        exception type."""
        pdf_path = _build_pdf(tmp_path)
        monkeypatch.setattr("src.ocr.targeted.build_recognition_predictor", lambda: _RaisingPredictor())

        with pytest.raises(ValueError, match="Surya blew up"):
            ocr_region(pdf_path, 1, BoundingBox(x0=60, y0=60, x1=120, y1=90))

    def test_default_timeout_is_configurable_via_parameter(self, tmp_path: Path, monkeypatch):
        """A fast, well-behaved predictor completes normally regardless
        of the configured timeout — the wrapper must not slow down or
        otherwise affect the success path."""
        pdf_path = _build_pdf(tmp_path)
        fake_predictor = _FakePredictor(_FakePageResult([_FakeBlock(html="<p>147</p>")]))
        monkeypatch.setattr("src.ocr.targeted.build_recognition_predictor", lambda: fake_predictor)

        result = ocr_region(
            pdf_path, 1, BoundingBox(x0=60, y0=60, x1=120, y1=90), timeout_seconds=5.0
        )

        assert result == "147"
