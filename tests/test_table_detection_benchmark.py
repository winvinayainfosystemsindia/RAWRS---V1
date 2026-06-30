"""Benchmark evaluation for RAWRS table detection (Point 9 of architectural approval).

Runs extract_tables() across all born-digital benchmark PDFs and measures:
  - False positive rate for PDFs declared tables:false in the manifest
  - Recall for PDFs declared tables:true
  - Detection source distribution (VectorBorderDetector vs SpanAlignmentDetector)
  - Confidence score distribution

Only born-digital (DIRECT_TEXT_EXTRACTION) PDFs are tested — OCR pages cannot
run table detection (no vector graphics or reliable span positions).

The manifest `tables` flag is a caption-text heuristic, not a structure-detection
result; for that reason, we do NOT assert strict recall for tables:true PDFs.
Instead, we verify that the detector does not flood reviewers with false positives
on PDFs that contain no tables.
"""

from pathlib import Path
from typing import List

import pytest

from tests.conftest import (
    BENCHMARK_MANIFEST,
    BENCHMARK_DIR,
    benchmark_pdfs_with,
    benchmark_pdfs_without,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_pipeline_for_tables(pdf_path: Path):
    """Run the full pre-table-detection pipeline on one PDF and return tables."""
    from src.parser.pdf_parser import parse_pdf
    from src.ocr.extractor import extract_text
    from src.ocr.router import route_pages
    from src.structure.structure_detector import detect_structure
    from src.tables.table_extractor import extract_tables

    doc = parse_pdf(pdf_path)
    doc = extract_text(doc)
    doc = route_pages(doc)
    doc = detect_structure(doc)
    return extract_tables(doc, pdf_path)


def _born_digital_no_tables() -> List[Path]:
    """Born-digital PDFs that the manifest declares have no tables."""
    no_table_names = {
        name for name, entry in BENCHMARK_MANIFEST.items()
        if not entry.get("tables") and entry.get("born_digital")
    }
    return sorted(
        BENCHMARK_DIR / name for name in no_table_names
        if (BENCHMARK_DIR / name).exists()
    )


def _born_digital_with_tables() -> List[Path]:
    """Born-digital PDFs that the manifest declares have tables."""
    table_names = {
        name for name, entry in BENCHMARK_MANIFEST.items()
        if entry.get("tables") and entry.get("born_digital")
    }
    return sorted(
        BENCHMARK_DIR / name for name in table_names
        if (BENCHMARK_DIR / name).exists()
    )


# ---------------------------------------------------------------------------
# Precision: no false positives on no-table PDFs
# ---------------------------------------------------------------------------

_NO_TABLE_PDFS = _born_digital_no_tables()


@pytest.mark.parametrize("pdf_path", _NO_TABLE_PDFS, ids=lambda p: p.name)
@pytest.mark.skipif(not _NO_TABLE_PDFS, reason="No born-digital no-table benchmark PDFs present")
def test_no_tables_detected_on_no_table_pdf(pdf_path):
    """Detector must not report any tables on PDFs the manifest declares table-free.

    A false positive here means the reviewer is burdened with reviewing a
    spurious table in a document that has none. This is a hard precision
    requirement — confidence threshold or evidence bundle tuning must ensure
    zero false positives on the known-clean corpus.
    """
    tables = _run_pipeline_for_tables(pdf_path)
    assert tables == [], (
        f"{pdf_path.name}: SpanAlignmentDetector/VectorBorderDetector reported "
        f"{len(tables)} table(s) on a manifest-declared no-table PDF. "
        f"Detections: {[{'page': t.page_number, 'source': t.extraction_source, 'confidence': round(t.confidence, 3)} for t in tables]}"
    )


# ---------------------------------------------------------------------------
# Recall: tables are detected on known-table PDFs (informational, not hard gate)
# ---------------------------------------------------------------------------

_TABLE_PDFS = _born_digital_with_tables()


@pytest.mark.parametrize("pdf_path", _TABLE_PDFS, ids=lambda p: p.name)
@pytest.mark.skipif(not _TABLE_PDFS, reason="No born-digital with-table benchmark PDFs present")
def test_table_detection_output_is_valid_list_on_table_pdf(pdf_path):
    """Detector returns a well-formed list on PDFs the manifest declares have tables.

    This is a smoke test only — we assert structural validity, not strict recall.
    The manifest `tables` flag is a text-presence heuristic; not all tables may
    be geometrically detectable (e.g., Brinkman's borderless aligned tables).
    Recall measurement is tracked via printed output below.
    """
    tables = _run_pipeline_for_tables(pdf_path)

    assert isinstance(tables, list), "extract_tables() must return a list"
    for t in tables:
        assert t.page_number >= 1, "page_number must be >= 1"
        assert t.row_count >= 1, "row_count must be >= 1"
        assert t.col_count >= 1, "col_count must be >= 1"
        assert t.extraction_source in {"pymupdf", "spatial_analysis", "pymupdf+spatial"}, (
            f"unexpected extraction_source: {t.extraction_source}"
        )
        assert 0.0 <= t.confidence <= 1.0, f"confidence {t.confidence} out of range"

    # Informational recall reporting
    expected = BENCHMARK_MANIFEST.get(pdf_path.name, {}).get("expected_table_count")
    print(
        f"\n  [{pdf_path.name}] detected={len(tables)}"
        + (f" expected={expected}" if expected is not None else "")
        + (f" recall={min(len(tables), expected)/expected:.2f}" if expected else "")
    )
    if tables:
        signal_counts: dict = {}
        for t in tables:
            for s in t.evidence_signals:
                name = s.get("name", "") if isinstance(s, dict) else s.name
                signal_counts[name] = signal_counts.get(name, 0) + 1
        print(f"    signal breakdown: {signal_counts}")


# ---------------------------------------------------------------------------
# Detection source audit: verify both detectors are contributing
# ---------------------------------------------------------------------------

def test_vector_border_detector_fires_on_bordered_pdf(tmp_path):
    """VectorBorderDetector must fire and produce extraction_source='pymupdf'."""
    import fitz
    from src.parser.pdf_parser import parse_pdf
    from src.ocr.extractor import extract_text
    from src.ocr.router import route_pages
    from src.structure.structure_detector import detect_structure
    from src.tables.table_extractor import extract_tables

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    col_w, row_h, x0, y0 = 100, 30, 50, 100
    xs = [x0 + i * col_w for i in range(4)]
    ys = [y0 + i * row_h for i in range(4)]
    for y in ys:
        page.draw_line(fitz.Point(xs[0], y), fitz.Point(xs[-1], y))
    for x in xs:
        page.draw_line(fitz.Point(x, ys[0]), fitz.Point(x, ys[-1]))
    data = [["Name", "Score", "Grade"], ["Alice", "95", "A"], ["Bob", "82", "B"]]
    for ri, row in enumerate(data):
        for ci, text in enumerate(row):
            page.insert_text(fitz.Point(xs[ci] + 4, ys[ri] + 20), text, fontsize=10)
    pdf_path = tmp_path / "bordered_audit.pdf"
    doc.save(str(pdf_path))
    doc.close()

    rawrs_doc = parse_pdf(pdf_path)
    rawrs_doc = extract_text(rawrs_doc)
    rawrs_doc = route_pages(rawrs_doc)
    rawrs_doc = detect_structure(rawrs_doc)
    tables = extract_tables(rawrs_doc, pdf_path)

    assert len(tables) >= 1, "Bordered PDF must produce at least one detected table"
    sources = {t.extraction_source for t in tables}
    assert "pymupdf" in sources or "pymupdf+spatial" in sources, (
        f"Expected VectorBorderDetector to fire on a bordered PDF; got sources={sources}"
    )


def _make_bordered_pdf_for_audit(path: Path) -> None:
    """Create a 3-row × 3-col bordered PDF with enough text to route as DIRECT_TEXT."""
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    col_w, row_h, x0, y0 = 100, 30, 50, 100
    xs = [x0 + i * col_w for i in range(4)]
    ys = [y0 + i * row_h for i in range(4)]
    for y in ys:
        page.draw_line(fitz.Point(xs[0], y), fitz.Point(xs[-1], y))
    for x in xs:
        page.draw_line(fitz.Point(x, ys[0]), fitz.Point(x, ys[-1]))
    data = [["Name", "Score", "Grade"], ["Alice", "95", "A"], ["Bob", "82", "B"]]
    for ri, row in enumerate(data):
        for ci, text in enumerate(row):
            page.insert_text(fitz.Point(xs[ci] + 4, ys[ri] + 20), text, fontsize=10)
    doc.save(str(path))
    doc.close()


def test_evidence_signals_present_on_detected_table(tmp_path):
    """Every detected table must carry at least one evidence signal with non-zero confidence."""
    from src.parser.pdf_parser import parse_pdf
    from src.ocr.extractor import extract_text
    from src.ocr.router import route_pages
    from src.structure.structure_detector import detect_structure
    from src.tables.table_extractor import extract_tables

    pdf_path = tmp_path / "evidence_check.pdf"
    _make_bordered_pdf_for_audit(pdf_path)

    rawrs_doc = parse_pdf(pdf_path)
    rawrs_doc = extract_text(rawrs_doc)
    rawrs_doc = route_pages(rawrs_doc)
    rawrs_doc = detect_structure(rawrs_doc)
    tables = extract_tables(rawrs_doc, pdf_path)

    assert len(tables) >= 1, "Bordered PDF must produce at least one detected table"
    for t in tables:
        assert isinstance(t.evidence_signals, list), "evidence_signals must be a list"
        assert len(t.evidence_signals) >= 1, "every detected table must have at least one signal"
        assert t.confidence > 0.0, "confidence must be > 0 when evidence signals are present"
        for sig in t.evidence_signals:
            assert "name" in sig and "score" in sig and "weight" in sig
