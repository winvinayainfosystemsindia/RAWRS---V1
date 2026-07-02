"""Tests for src/lists/list_detector.py::detect_lists_from_pdf()."""

from pathlib import Path
from typing import List, Tuple

import fitz
import pytest

from src.lists.list_detector import detect_lists_from_pdf
from src.models.list_block import ListType


def _build_pdf(tmp_path: Path, lines: List[Tuple[str, float]], name: str = "lists.pdf") -> Path:
    """One-page PDF with each line at increasing y, optionally indented
    (the float is the x-coordinate) so nesting-level detection is testable."""
    pdf_path = tmp_path / name
    doc = fitz.open()
    page = doc.new_page()
    y = 72.0
    for text, x in lines:
        page.insert_text((x, y), text, fontname="helv", fontsize=11)
        y += 20
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


class TestDetectListsFromPdf:
    def test_missing_pdf_returns_empty(self, tmp_path: Path) -> None:
        assert detect_lists_from_pdf(tmp_path / "nope.pdf") == []

    def test_no_list_markers_yields_no_lists(self, tmp_path: Path) -> None:
        pdf_path = _build_pdf(tmp_path, [("Just an ordinary paragraph.", 72.0)])
        assert detect_lists_from_pdf(pdf_path) == []

    def test_bullet_run_detected_as_one_list(self, tmp_path: Path) -> None:
        pdf_path = _build_pdf(
            tmp_path,
            [
                ("- First item", 72.0),
                ("- Second item", 72.0),
                ("- Third item", 72.0),
            ],
        )
        lists = detect_lists_from_pdf(pdf_path)
        assert len(lists) == 1
        assert lists[0].list_type == ListType.BULLET
        assert [item.text for item in lists[0].items] == ["First item", "Second item", "Third item"]

    def test_numbered_run_detected(self, tmp_path: Path) -> None:
        pdf_path = _build_pdf(
            tmp_path,
            [
                ("1. Alpha", 72.0),
                ("2. Beta", 72.0),
            ],
        )
        lists = detect_lists_from_pdf(pdf_path)
        assert len(lists) == 1
        assert lists[0].list_type == ListType.NUMBERED
        assert [item.text for item in lists[0].items] == ["Alpha", "Beta"]

    def test_paragraph_between_two_bullet_runs_splits_them(self, tmp_path: Path) -> None:
        pdf_path = _build_pdf(
            tmp_path,
            [
                ("- First list item one", 72.0),
                ("- First list item two", 72.0),
                ("An intervening paragraph.", 72.0),
                ("- Second list item one", 72.0),
            ],
        )
        lists = detect_lists_from_pdf(pdf_path)
        assert len(lists) == 2
        assert len(lists[0].items) == 2
        assert len(lists[1].items) == 1

    def test_indented_line_gets_higher_nesting_level(self, tmp_path: Path) -> None:
        pdf_path = _build_pdf(
            tmp_path,
            [
                ("- Top level item", 72.0),
                ("- Nested item", 100.0),
            ],
        )
        lists = detect_lists_from_pdf(pdf_path)
        assert len(lists) == 1
        assert lists[0].items[0].level == 0
        assert lists[0].items[1].level >= 1
