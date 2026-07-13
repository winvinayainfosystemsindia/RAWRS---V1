"""Tests for src/ocr/targeted.py (FEATURE_019: region-targeted OCR).

Mocks the Surya predictor boundary (src.ocr.targeted.build_recognition_predictor)
the same way tests/test_surya_engine.py does, so these run fast and
deterministically. PDF rasterization (PyMuPDF's own clip-based crop) is
exercised for real against a tiny in-memory PDF.
"""

from pathlib import Path
from typing import List

import fitz
import pytest

from src.models.contracts import BoundingBox
from src.ocr.targeted import TargetedOCRError, ocr_region


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
