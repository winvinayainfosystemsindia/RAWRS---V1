"""src/ocr/cache.py and its use by the Docling and Surya engines.

The contract under test: a cache hit leaves every Page field exactly as a
fresh conversion would, a hit never builds the engine, and anything that could
change the engine's answer (PDF bytes, page, engine source) misses.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.models.contracts import Document, ExtractionMethod, Metadata, Page, PageType, RoutingDecision
from src.ocr import cache as ocr_cache
from src.ocr.docling_engine import run_docling_ocr
from src.ocr.surya_engine import run_surya_ocr

PAGE_FIELDS = ("raw_text", "cleaned_text", "ocr_heading_levels", "ocr_confidence",
               "extraction_method", "routing_decision")


@pytest.fixture
def cache_on(tmp_path, monkeypatch):
    monkeypatch.setenv("RAWRS_OCR_CACHE", "on")
    monkeypatch.setenv("RAWRS_OCR_CACHE_DIR", str(tmp_path / "cache"))
    return tmp_path / "cache"


def _item(label, text, level=None):
    return SimpleNamespace(label=SimpleNamespace(value=label), text=text, level=level)


class _DoclingDoc:
    def __init__(self, text, items):
        self._text, self._items = text, items

    def export_to_text(self):
        return self._text

    def iterate_items(self):
        return iter([(item, 0) for item in self._items])


class _Converter:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def convert(self, pdf_path, page_range):
        number = page_range[0]
        self.calls.append(number)
        if number not in self.pages:
            raise RuntimeError("simulated failure")
        return SimpleNamespace(document=self.pages[number])


PAGES = {
    1: _DoclingDoc("A Title\n\nINTRO\nBody  text\x02 here.",
                   [_item("title", "A Title"), _item("section_header", "INTRO", 1), _item("text", "Body")]),
    2: _DoclingDoc("", []),
}


def _pdf(tmp_path, data=b"%PDF-1.4 fake bytes"):
    path = tmp_path / "doc.pdf"
    path.write_bytes(data)
    return path


def _document(pdf, numbers, method=ExtractionMethod.OCR_PENDING):
    pages = [Page(page_number=n, page_type=PageType.OCR_REQUIRED, extraction_method=method,
                  routing_decision=RoutingDecision.ROUTE_TO_OCR_PLACEHOLDER) for n in numbers]
    return Document(source_pdf_path=str(pdf), metadata=Metadata(filename="doc.pdf"), pages=pages)


def _snapshot(document):
    return [{f: getattr(p, f) for f in PAGE_FIELDS} for p in document.pages], document.sanitization_events


def _run_docling(monkeypatch, pdf, numbers, pages=PAGES):
    converter = _Converter(pages)
    built = []
    monkeypatch.setattr("src.ocr.docling_engine.build_converter", lambda: built.append(1) or converter)
    document = run_docling_ocr(_document(pdf, numbers))
    return document, converter, built


def test_hit_is_field_identical_to_a_fresh_conversion_and_builds_no_engine(cache_on, tmp_path, monkeypatch):
    pdf = _pdf(tmp_path)
    fresh, converter, built = _run_docling(monkeypatch, pdf, [1, 2])
    assert converter.calls == [1, 2] and built == [1]

    cached, converter2, built2 = _run_docling(monkeypatch, pdf, [1, 2])

    assert converter2.calls == [] and built2 == []  # Docling never loaded
    assert _snapshot(cached) == _snapshot(fresh)
    assert cached.pages[0].ocr_heading_levels == {"A Title": 1, "INTRO": 2}
    assert cached.sanitization_events  # the \x02 removal is recomputed, not lost


def test_disabled_cache_never_reads_or_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("RAWRS_OCR_CACHE", "off")
    monkeypatch.setenv("RAWRS_OCR_CACHE_DIR", str(tmp_path / "cache"))
    pdf = _pdf(tmp_path)
    _run_docling(monkeypatch, pdf, [1])
    _, converter, _ = _run_docling(monkeypatch, pdf, [1])
    assert converter.calls == [1]
    assert not (tmp_path / "cache").exists()


def test_failed_pages_are_not_cached(cache_on, tmp_path, monkeypatch):
    pdf = _pdf(tmp_path)
    _run_docling(monkeypatch, pdf, [3])  # page 3 raises in the fake
    _, converter, _ = _run_docling(monkeypatch, pdf, [3])
    assert converter.calls == [3]


def test_changed_pdf_bytes_miss(cache_on, tmp_path, monkeypatch):
    pdf = _pdf(tmp_path)
    _run_docling(monkeypatch, pdf, [1])
    pdf.write_bytes(b"%PDF-1.4 different bytes")
    _, converter, _ = _run_docling(monkeypatch, pdf, [1])
    assert converter.calls == [1]


def test_partial_hit_converts_only_the_missing_page(cache_on, tmp_path, monkeypatch):
    pdf = _pdf(tmp_path)
    _run_docling(monkeypatch, pdf, [1])
    _, converter, built = _run_docling(monkeypatch, pdf, [1, 2])
    assert converter.calls == [2] and built == [1]


def test_engine_fingerprint_depends_on_engine_source(monkeypatch, tmp_path):
    before = ocr_cache.engine_fingerprint("docling")
    fake_dir = tmp_path / "ocr"
    fake_dir.mkdir()
    for name in ("docling_config.py", "docling_engine.py"):
        (fake_dir / name).write_text("changed source", encoding="utf-8")
    monkeypatch.setattr(ocr_cache, "_OCR_DIR", fake_dir)
    ocr_cache.engine_fingerprint.cache_clear()
    try:
        assert ocr_cache.engine_fingerprint("docling") != before
    finally:
        ocr_cache.engine_fingerprint.cache_clear()


def test_corrupt_entry_is_a_miss_not_a_crash(cache_on, tmp_path, monkeypatch):
    pdf = _pdf(tmp_path)
    _run_docling(monkeypatch, pdf, [1])
    for entry in Path(cache_on).rglob("*.json"):
        entry.write_text("{not json", encoding="utf-8")
    _, converter, _ = _run_docling(monkeypatch, pdf, [1])
    assert converter.calls == [1]


def test_surya_hit_is_field_identical_and_builds_no_predictor(cache_on, tmp_path, monkeypatch):
    pdf = _pdf(tmp_path)
    calls = []

    def predictor(images, full_page):
        calls.append(1)
        return [SimpleNamespace()]

    monkeypatch.setattr("src.ocr.surya_engine.render_page_to_image", lambda path, n: object())
    monkeypatch.setattr("src.ocr.surya_engine.page_result_to_text", lambda result: "Recovered  line")
    built = []
    monkeypatch.setattr("src.ocr.surya_engine.build_recognition_predictor",
                        lambda: built.append(1) or predictor)

    fresh = run_surya_ocr(_document(pdf, [1], method=ExtractionMethod.DOCLING))
    again = run_surya_ocr(_document(pdf, [1], method=ExtractionMethod.DOCLING))

    assert calls == [1] and built == [1]
    assert _snapshot(again) == _snapshot(fresh)
    assert again.pages[0].cleaned_text.startswith("Recovered")
