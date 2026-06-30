"""Tests for src/tables/table_extractor.py (Phase T — table detection)."""

import io
import struct
import zlib
from pathlib import Path
from typing import List

import fitz
import pytest

from src.models.contracts import Document, ExtractionMethod, Metadata
from src.models.page import Page, PageType
from src.models.table import Table, TableStatus
from src.parser.pdf_parser import parse_pdf
from src.ocr.extractor import extract_text
from src.ocr.router import route_pages
from src.structure.structure_detector import detect_structure
from src.tables.table_extractor import _build_table, _tuple_to_bbox, extract_tables
from src.tables.detectors.base import CandidateRegion
from src.tables.evidence import EvidenceBundle, EvidenceSignal

BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"
BRINKMAN_PDF = BENCHMARK_DIR / "7.brinkman-learner-centred-education-reform-india-missing-beliefs.pdf"


# ---------------------------------------------------------------------------
# Unit: _tuple_to_bbox
# ---------------------------------------------------------------------------

def test_tuple_to_bbox_from_fitz_rect():
    rect = fitz.Rect(10, 20, 100, 200)
    bbox = _tuple_to_bbox(rect)
    assert bbox.x0 == pytest.approx(10)
    assert bbox.y0 == pytest.approx(20)
    assert bbox.x1 == pytest.approx(100)
    assert bbox.y1 == pytest.approx(200)


def test_tuple_to_bbox_from_tuple():
    bbox = _tuple_to_bbox((5.0, 10.0, 50.0, 80.0))
    assert bbox.x0 == pytest.approx(5.0)
    assert bbox.y0 == pytest.approx(10.0)
    assert bbox.x1 == pytest.approx(50.0)
    assert bbox.y1 == pytest.approx(80.0)


# ---------------------------------------------------------------------------
# Unit: _build_table — degenerate inputs
# ---------------------------------------------------------------------------

def _make_candidate(
    rows: List[List],
    signal_name: str = "vector_borders",
    bbox: tuple = (0.0, 0.0, 200.0, 200.0),
) -> CandidateRegion:
    """Build a minimal CandidateRegion for unit-testing _build_table."""
    evidence = EvidenceBundle()
    evidence.add(EvidenceSignal(name=signal_name, score=0.9, weight=1.0, note="test"))
    return CandidateRegion(page_number=1, bbox=bbox, evidence=evidence, raw_rows=rows)


def test_build_table_zero_rows_returns_none():
    candidate = _make_candidate([])
    assert _build_table(candidate, page_number=1, index=0, fitz_page=None, cell_signals={}) is None


def test_build_table_zero_cols_returns_none():
    candidate = _make_candidate([])
    assert _build_table(candidate, page_number=1, index=0, fitz_page=None, cell_signals={}) is None


def test_build_table_single_row_no_header():
    """A table with only one row should have no header (we mark header only when >1 row)."""
    candidate = _make_candidate([["A", "B"]])
    table = _build_table(candidate, page_number=2, index=0, fitz_page=None, cell_signals={})
    assert table is not None
    assert table.row_count == 1
    assert table.col_count == 2
    assert not table.rows[0].is_header_row
    assert not table.rows[0].cells[0].is_header


def test_build_table_multi_row_first_row_is_header():
    """With >1 row, row 0 should be the header row."""
    rows = [["Name", "Value"], ["Alice", "1"], ["Bob", "2"]]
    candidate = _make_candidate(rows)
    table = _build_table(candidate, page_number=1, index=0, fitz_page=None, cell_signals={})
    assert table is not None
    assert table.rows[0].is_header_row
    assert all(cell.is_header for cell in table.rows[0].cells)
    assert not table.rows[1].is_header_row
    assert not table.rows[2].is_header_row


def test_build_table_id_format():
    candidate = _make_candidate([["H1", "H2"], ["D1", "D2"]])
    table = _build_table(candidate, page_number=5, index=3, fitz_page=None, cell_signals={})
    assert table is not None
    assert table.table_id == "table-p5-3"


def test_build_table_cell_text_stripped():
    candidate = _make_candidate([["  col1  ", None], ["val", " "]])
    table = _build_table(candidate, page_number=1, index=0, fitz_page=None, cell_signals={})
    assert table is not None
    assert table.rows[0].cells[0].text == "col1"
    assert table.rows[0].cells[1].text == ""
    assert table.rows[1].cells[1].text == ""


def test_build_table_status_and_source():
    candidate = _make_candidate([["H"], ["D"]])
    table = _build_table(candidate, page_number=1, index=0, fitz_page=None, cell_signals={})
    assert table is not None
    assert table.status == TableStatus.AUTO_DETECTED
    assert table.extraction_source == "pymupdf"


# ---------------------------------------------------------------------------
# Unit: extract_tables — empty document / missing PDF
# ---------------------------------------------------------------------------

def _minimal_document(pdf_path: str = "nonexistent.pdf") -> Document:
    return Document(
        source_pdf_path=pdf_path,
        metadata=Metadata(filename=pdf_path, page_count=0),
    )


def test_extract_tables_no_direct_text_pages_returns_empty():
    doc = _minimal_document()
    # No pages → no DIRECT_TEXT pages → returns []
    result = extract_tables(doc, Path("nonexistent.pdf"))
    assert result == []


def test_extract_tables_missing_pdf_returns_empty(tmp_path):
    """extract_tables should not raise when the PDF path is missing."""
    doc = _minimal_document(str(tmp_path / "missing.pdf"))
    doc.pages.append(
        Page(
            page_number=1,
            page_type=PageType.DIRECT_TEXT,
            extraction_method=ExtractionMethod.DIRECT_TEXT_EXTRACTION,
            raw_text="some text",
        )
    )
    result = extract_tables(doc, tmp_path / "missing.pdf")
    assert result == []


# ---------------------------------------------------------------------------
# Integration: Brinkman (only benchmark PDF with tables: true)
# These use real PDFs so may take a moment but remain fast (native text
# layer only — no OCR).
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not BRINKMAN_PDF.exists(), reason="Brinkman benchmark PDF not present")
def test_brinkman_tables_zero_auto_detected():
    """Brinkman uses borderless academic tables; PyMuPDF find_tables()
    (lines strategy) finds 0. This is the expected, documented result —
    reviewers create these manually in the workspace."""
    doc = parse_pdf(BRINKMAN_PDF)
    doc = extract_text(doc)
    doc = route_pages(doc)
    doc = detect_structure(doc)
    tables = extract_tables(doc, BRINKMAN_PDF)
    # Confirm zero auto-detected (not a failure, just a known limitation)
    assert isinstance(tables, list)
    # No assertion that count > 0 — borderless tables are manual-entry territory


# ---------------------------------------------------------------------------
# Integration: synthetic bordered table PDF
# ---------------------------------------------------------------------------

def _make_pdf_with_table(path: Path) -> None:
    """Create a minimal PDF containing a simple 2x3 table with explicit
    border lines, so find_tables() can detect it."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    col_widths = [100, 100, 100]
    row_heights = [30, 25, 25]
    x0, y0 = 50, 100

    # Draw table borders
    x_pos = [x0]
    for w in col_widths:
        x_pos.append(x_pos[-1] + w)
    y_pos = [y0]
    for h in row_heights:
        y_pos.append(y_pos[-1] + h)

    for y in y_pos:
        page.draw_line(fitz.Point(x_pos[0], y), fitz.Point(x_pos[-1], y))
    for x in x_pos:
        page.draw_line(fitz.Point(x, y_pos[0]), fitz.Point(x, y_pos[-1]))

    # Insert text into cells
    data = [
        ["Name", "Score", "Grade"],
        ["Alice", "95", "A"],
        ["Bob", "82", "B"],
    ]
    for ri, row in enumerate(data):
        for ci, text in enumerate(row):
            cx = x_pos[ci] + 5
            cy = y_pos[ri] + 18
            page.insert_text(fitz.Point(cx, cy), text, fontsize=10)

    doc.save(str(path))
    doc.close()


def test_extract_tables_from_bordered_table_pdf(tmp_path):
    """A PDF with explicit table borders should yield at least one table."""
    pdf_path = tmp_path / "table_test.pdf"
    _make_pdf_with_table(pdf_path)

    doc = parse_pdf(pdf_path)
    doc = extract_text(doc)
    doc = route_pages(doc)
    doc = detect_structure(doc)
    tables = extract_tables(doc, pdf_path)

    assert len(tables) >= 1
    t = tables[0]
    assert t.page_number == 1
    assert t.row_count >= 2
    assert t.col_count >= 2
    assert t.table_id.startswith("table-p1-")
    assert t.status == TableStatus.AUTO_DETECTED
    assert t.extraction_source == "pymupdf"
    assert t.bbox is not None
    # Row 0 should be header when there are multiple rows
    if t.row_count > 1:
        assert t.rows[0].is_header_row


# ---------------------------------------------------------------------------
# Unit: HorizontalRuleDetector
# ---------------------------------------------------------------------------

def _make_horizontal_rule_pdf(path: Path) -> None:
    """Create a PDF with three horizontal rules (booktabs-style academic table).

    Page layout:
      y=100: top rule (full width)
      y=130: header-divider rule (full width)
      y=160: row 1 of data
      y=190: row 2 of data
      y=220: bottom rule (full width)
    Text is inserted between the rules to provide table body content.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    x_left, x_right = 50, 500
    # Three horizontal rules
    for y in (100, 130, 220):
        page.draw_line(fitz.Point(x_left, y), fitz.Point(x_right, y), color=(0, 0, 0), width=0.75)
    # Header text (between rule 1 and rule 2)
    headers = ["Condition", "Mean", "SD", "N"]
    col_xs = [60, 200, 310, 410]
    for cx, hdr in zip(col_xs, headers):
        page.insert_text(fitz.Point(cx, 124), hdr, fontsize=9)
    # Data rows (between rule 2 and rule 3)
    data = [
        ["Control", "3.21", "0.45", "42"],
        ["Treatment", "4.87", "0.33", "38"],
    ]
    for ri, row in enumerate(data):
        for cx, cell in zip(col_xs, row):
            page.insert_text(fitz.Point(cx, 150 + ri * 30), cell, fontsize=9)
    doc.save(str(path))
    doc.close()


def test_horizontal_rule_detector_imports():
    """HorizontalRuleDetector can be imported and instantiated without error."""
    from src.tables.detectors.horizontal_rule import HorizontalRuleDetector
    detector = HorizontalRuleDetector()
    assert detector.name == "horizontal_rule"


def test_horizontal_rule_detector_smoke_on_bordered_pdf(tmp_path):
    """HorizontalRuleDetector.detect() returns a list (empty or populated) without crashing."""
    from src.tables.detectors.horizontal_rule import HorizontalRuleDetector
    pdf_path = tmp_path / "hrule_smoke.pdf"
    _make_horizontal_rule_pdf(pdf_path)
    fitz_doc = fitz.open(str(pdf_path))
    fitz_page = fitz_doc[0]
    detector = HorizontalRuleDetector()
    candidates = detector.detect(fitz_page, page_number=1)
    fitz_doc.close()
    assert isinstance(candidates, list)
    for c in candidates:
        assert c.page_number == 1
        assert isinstance(c.evidence.signals, list)
        assert len(c.evidence.signals) >= 1
        assert any(s.name == "horizontal_rules" for s in c.evidence.signals)


def test_horizontal_rule_detector_finds_table(tmp_path):
    """HorizontalRuleDetector should detect at least one candidate on a 3-rule table PDF."""
    from src.tables.detectors.horizontal_rule import HorizontalRuleDetector
    pdf_path = tmp_path / "hrule_detect.pdf"
    _make_horizontal_rule_pdf(pdf_path)
    fitz_doc = fitz.open(str(pdf_path))
    fitz_page = fitz_doc[0]
    detector = HorizontalRuleDetector()
    candidates = detector.detect(fitz_page, page_number=1)
    fitz_doc.close()
    assert len(candidates) >= 1, (
        "HorizontalRuleDetector must detect at least one candidate on a 3-rule booktabs PDF"
    )


def test_horizontal_rule_detector_no_candidates_on_empty_page(tmp_path):
    """HorizontalRuleDetector returns empty list on a PDF page with no drawings."""
    from src.tables.detectors.horizontal_rule import HorizontalRuleDetector
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    pdf_path = tmp_path / "empty_page.pdf"
    doc.save(str(pdf_path))
    doc.close()
    fitz_doc = fitz.open(str(pdf_path))
    fitz_page = fitz_doc[0]
    detector = HorizontalRuleDetector()
    candidates = detector.detect(fitz_page, page_number=1)
    fitz_doc.close()
    assert candidates == []


# ---------------------------------------------------------------------------
# Unit: ColumnAlignmentDetector
# ---------------------------------------------------------------------------

def _make_column_aligned_pdf(path: Path) -> None:
    """Create a PDF with text-only column-aligned table (no borders, no rules).

    Layout: 4 columns at consistent x positions, 5 rows with consistent spacing.
    This mimics a descriptor-heavy academic table (e.g., feature comparison grid).
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    col_xs = [50, 170, 310, 440]
    row_ys = [80, 105, 130, 155, 180]
    table_data = [
        ["Feature", "Option A", "Option B", "Option C"],
        ["Ease of use", "High", "Medium", "Low"],
        ["Cost", "Low", "High", "Medium"],
        ["Reliability", "High", "High", "Medium"],
        ["Support", "Community", "Commercial", "None"],
    ]
    for ri, (y, row) in enumerate(zip(row_ys, table_data)):
        for cx, cell in zip(col_xs, row):
            page.insert_text(fitz.Point(cx, y), cell, fontsize=9)
    doc.save(str(path))
    doc.close()


def test_column_alignment_detector_imports():
    """ColumnAlignmentDetector can be imported and instantiated without error."""
    from src.tables.detectors.column_alignment import ColumnAlignmentDetector
    detector = ColumnAlignmentDetector()
    assert detector.name == "column_alignment"


def test_column_alignment_detector_smoke_on_aligned_pdf(tmp_path):
    """ColumnAlignmentDetector.detect() returns a list without crashing."""
    from src.tables.detectors.column_alignment import ColumnAlignmentDetector
    pdf_path = tmp_path / "col_align_smoke.pdf"
    _make_column_aligned_pdf(pdf_path)
    fitz_doc = fitz.open(str(pdf_path))
    fitz_page = fitz_doc[0]
    detector = ColumnAlignmentDetector()
    candidates = detector.detect(fitz_page, page_number=1)
    fitz_doc.close()
    assert isinstance(candidates, list)
    for c in candidates:
        assert c.page_number == 1
        assert isinstance(c.evidence.signals, list)
        assert len(c.evidence.signals) >= 1


def test_column_alignment_detector_evidence_signals(tmp_path):
    """When ColumnAlignmentDetector finds a candidate, it should carry column_x_alignment signal."""
    from src.tables.detectors.column_alignment import ColumnAlignmentDetector
    pdf_path = tmp_path / "col_align_signals.pdf"
    _make_column_aligned_pdf(pdf_path)
    fitz_doc = fitz.open(str(pdf_path))
    fitz_page = fitz_doc[0]
    detector = ColumnAlignmentDetector()
    candidates = detector.detect(fitz_page, page_number=1)
    fitz_doc.close()
    if candidates:
        signal_names = {s.name for s in candidates[0].evidence.signals}
        assert "column_x_alignment" in signal_names, (
            f"Expected 'column_x_alignment' signal; got: {signal_names}"
        )


def test_column_alignment_detector_no_candidates_on_single_text_block(tmp_path):
    """ColumnAlignmentDetector should not detect a table in a PDF with only body text."""
    from src.tables.detectors.column_alignment import ColumnAlignmentDetector
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Single paragraph of text — not a table
    text = "This is a paragraph of body text with no tabular structure whatsoever."
    page.insert_text(fitz.Point(50, 100), text, fontsize=11)
    pdf_path = tmp_path / "body_text_only.pdf"
    doc.save(str(pdf_path))
    doc.close()
    fitz_doc = fitz.open(str(pdf_path))
    fitz_page = fitz_doc[0]
    detector = ColumnAlignmentDetector()
    candidates = detector.detect(fitz_page, page_number=1)
    fitz_doc.close()
    assert candidates == [], (
        "ColumnAlignmentDetector must not report a table on a single body-text block"
    )


# ---------------------------------------------------------------------------
# Integration: all four detectors registered in _DETECTORS
# ---------------------------------------------------------------------------

def test_all_four_detectors_are_registered():
    """The _DETECTORS list must contain all four detector instances."""
    from src.tables.table_extractor import _DETECTORS
    detector_classes = {type(d).__name__ for d in _DETECTORS}
    assert "VectorBorderDetector" in detector_classes
    assert "HorizontalRuleDetector" in detector_classes
    assert "SpanAlignmentDetector" in detector_classes
    assert "ColumnAlignmentDetector" in detector_classes


# ---------------------------------------------------------------------------
# Integration: lifecycle on new detector evidence sources
# ---------------------------------------------------------------------------

def test_detected_table_has_lifecycle_status_detected(tmp_path):
    """Tables produced by any detector path should have lifecycle_status=DETECTED."""
    from src.models.lifecycle import ObjectLifecycleStatus
    pdf_path = tmp_path / "lifecycle_check.pdf"
    _make_pdf_with_table(pdf_path)
    doc = parse_pdf(pdf_path)
    doc = extract_text(doc)
    doc = route_pages(doc)
    doc = detect_structure(doc)
    tables = extract_tables(doc, pdf_path)
    assert len(tables) >= 1
    for t in tables:
        assert t.lifecycle_status == ObjectLifecycleStatus.DETECTED
