"""Tests for the Mathpix MMD parser and MathpixImportProvider.

Covers: mmd_parser.parse_mmd() unit tests (inline fixtures) and
MathpixImportProvider.import_document() integration tests (tmp_path).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.mathpix.ingestor import MathpixImportProvider
from src.mathpix.mmd_parser import parse_mmd
from src.models.contracts import Document
from src.models.metadata import Metadata
from src.models.page import ExtractionMethod, OCRConfidence, Page
from src.models.phase2_document import P2BlockType, P2ListStyle


# ── helpers ────────────────────────────────────────────────────────────

def _make_document(page_count: int = 3) -> Document:
    """Minimal Document shell (as returned by parse_pdf)."""
    return Document(
        source_pdf_path="test.pdf",
        metadata=Metadata(filename="test.pdf", page_count=page_count),
        pages=[Page(page_number=i + 1) for i in range(page_count)],
    )


def _run_import(mmd_text: str, page_count: int, tmp_path: Path) -> Document:
    """Write mmd_text to a tmp file and run MathpixImportProvider on it."""
    mmd_file = tmp_path / "test.mmd"
    mmd_file.write_text(mmd_text, encoding="utf-8")
    doc = _make_document(page_count)
    return MathpixImportProvider().import_document(doc, mmd_path=mmd_file)


# ════════════════════════════════════════════════════════════════════════
# parse_mmd — unit tests
# ════════════════════════════════════════════════════════════════════════

class TestParseMmdTitle:
    def test_single_line_title(self):
        p2 = parse_mmd(r"\title{The Nature of Enquiry}")
        assert p2.front_matter.title == "The Nature of Enquiry"

    def test_multiline_title(self):
        mmd = "\\title{\nThe Nature of Enquiry\n}"
        p2 = parse_mmd(mmd)
        assert p2.front_matter.title == "The Nature of Enquiry"

    def test_title_with_internal_spaces(self):
        mmd = "\\title{\n  Introduction to Educational Research  \n}"
        p2 = parse_mmd(mmd)
        assert p2.front_matter.title == "Introduction to Educational Research"

    def test_no_title_leaves_front_matter_empty(self):
        p2 = parse_mmd("Some paragraph text only.")
        assert p2.front_matter.title is None


class TestParseMmdHeadings:
    def test_section_becomes_h2(self):
        p2 = parse_mmd(r"\section*{Introduction}")
        headings = [b for b in p2.blocks if b.block_type == P2BlockType.HEADING]
        assert len(headings) == 1
        assert headings[0].heading.level == 2
        assert headings[0].heading.text == "Introduction"

    def test_subsection_becomes_h3(self):
        p2 = parse_mmd(r"\subsection*{1.1 Background}")
        headings = [b for b in p2.blocks if b.block_type == P2BlockType.HEADING]
        assert headings[0].heading.level == 3
        assert headings[0].heading.text == "1.1 Background"

    def test_subsubsection_becomes_h4(self):
        p2 = parse_mmd(r"\subsubsection*{Detail}")
        headings = [b for b in p2.blocks if b.block_type == P2BlockType.HEADING]
        assert headings[0].heading.level == 4

    def test_heading_without_star_still_parsed(self):
        p2 = parse_mmd(r"\section{Results}")
        headings = [b for b in p2.blocks if b.block_type == P2BlockType.HEADING]
        assert len(headings) == 1
        assert headings[0].heading.text == "Results"

    def test_multiple_headings_preserve_order(self):
        mmd = "\\section*{A}\n\n\\subsection*{B}\n\n\\subsection*{C}"
        p2 = parse_mmd(mmd)
        headings = [b for b in p2.blocks if b.block_type == P2BlockType.HEADING]
        assert [h.heading.text for h in headings] == ["A", "B", "C"]
        assert [h.heading.level for h in headings] == [2, 3, 3]


class TestParseMmdParagraph:
    def test_plain_text_is_paragraph(self):
        p2 = parse_mmd("This is a plain paragraph.")
        paras = [b for b in p2.blocks if b.block_type == P2BlockType.PARAGRAPH]
        assert len(paras) == 1
        assert paras[0].text == "This is a plain paragraph."

    def test_footnote_ref_in_paragraph_becomes_bracket(self):
        mmd = r"See Smith (1990). ${ }^{1}$"
        p2 = parse_mmd(mmd)
        para = [b for b in p2.blocks if b.block_type == P2BlockType.PARAGRAPH][0]
        assert "[1]" in para.text
        assert "$" not in para.text


class TestParseMmdLists:
    def test_bullet_list_item(self):
        p2 = parse_mmd("- first item")
        items = [b for b in p2.blocks if b.block_type == P2BlockType.LIST_ITEM]
        assert len(items) == 1
        assert items[0].list_style == P2ListStyle.BULLET
        assert items[0].text == "first item"

    def test_numbered_list_item(self):
        p2 = parse_mmd("1. first numbered item")
        items = [b for b in p2.blocks if b.block_type == P2BlockType.LIST_ITEM]
        assert items[0].list_style == P2ListStyle.NUMBERED
        assert items[0].list_number == 1
        assert items[0].text == "first numbered item"

    def test_multiple_bullet_items(self):
        mmd = "- alpha\n- beta\n- gamma"
        p2 = parse_mmd(mmd)
        items = [b for b in p2.blocks if b.block_type == P2BlockType.LIST_ITEM]
        assert [i.text for i in items] == ["alpha", "beta", "gamma"]


class TestParseMmdFigure:
    def test_figure_env_captures_caption(self):
        mmd = textwrap.dedent("""\
            \\begin{figure}
            \\captionsetup{labelformat=empty}
            \\caption{A scheme for social science}
            \\includegraphics[alt={},max width=\\textwidth]{./images/fig1.jpg}
            \\end{figure}
        """)
        p2 = parse_mmd(mmd)
        figures = [b for b in p2.blocks if b.block_type == P2BlockType.FIGURE]
        assert len(figures) == 1
        assert figures[0].figure.caption == "A scheme for social science"

    def test_figure_env_captures_image_path(self):
        mmd = textwrap.dedent("""\
            \\begin{figure}
            \\includegraphics{./images/test.jpg}
            \\end{figure}
        """)
        p2 = parse_mmd(mmd)
        figures = [b for b in p2.blocks if b.block_type == P2BlockType.FIGURE]
        assert figures[0].figure.image_path == "./images/test.jpg"

    def test_figure_with_no_caption(self):
        mmd = "\\begin{figure}\n\\includegraphics{./img.jpg}\n\\end{figure}"
        p2 = parse_mmd(mmd)
        figures = [b for b in p2.blocks if b.block_type == P2BlockType.FIGURE]
        assert figures[0].figure.caption is None


class TestParseMmdPipeTable:
    def test_pipe_table_parsed(self):
        mmd = "| Col A | Col B |\n|-------|-------|\n| r1c1  | r1c2  |"
        p2 = parse_mmd(mmd)
        tables = [b for b in p2.blocks if b.block_type == P2BlockType.TABLE]
        assert len(tables) == 1
        t = tables[0].table
        assert t.has_header_row is True
        assert len(t.rows) == 2  # header + data
        assert t.rows[0][0].text == "Col A"
        assert t.rows[1][1].text == "r1c2"

    def test_pipe_table_no_separator_no_header(self):
        mmd = "| A | B |\n| C | D |"
        p2 = parse_mmd(mmd)
        tables = [b for b in p2.blocks if b.block_type == P2BlockType.TABLE]
        assert tables[0].table.has_header_row is False

    def test_pipe_table_three_columns(self):
        mmd = "| X | Y | Z |\n|---|---|---|\n| 1 | 2 | 3 |"
        p2 = parse_mmd(mmd)
        t = [b for b in p2.blocks if b.block_type == P2BlockType.TABLE][0].table
        assert len(t.rows[0]) == 3


class TestParseMmdFootnote:
    def test_footnotetext_captured(self):
        mmd = r"\footnotetext{1}{This is the footnote body.}"
        p2 = parse_mmd(mmd)
        assert len(p2.footnotes) == 1
        assert p2.footnotes[0].number == 1
        assert p2.footnotes[0].body == "This is the footnote body."

    def test_multiple_footnotes(self):
        mmd = (
            "\\footnotetext{1}{First note.}\n"
            "\\footnotetext{2}{Second note.}"
        )
        p2 = parse_mmd(mmd)
        assert len(p2.footnotes) == 2
        assert p2.footnotes[0].number == 1
        assert p2.footnotes[1].number == 2


class TestParseMmdAbstract:
    def test_abstract_block_type(self):
        mmd = "\\begin{abstract}\nThis paper explores X.\n\\end{abstract}"
        p2 = parse_mmd(mmd)
        abstracts = [b for b in p2.blocks if b.block_type == P2BlockType.ABSTRACT]
        assert len(abstracts) == 1
        assert "This paper explores X." in abstracts[0].text


class TestParseMmdEmptyAndEdgeCases:
    def test_empty_content_returns_empty_doc(self):
        p2 = parse_mmd("")
        assert p2.blocks == []
        assert p2.footnotes == []

    def test_blank_lines_ignored(self):
        p2 = parse_mmd("\n\n\n")
        assert p2.blocks == []

    def test_mixed_content_order_preserved(self):
        mmd = (
            "\\title{My Title}\n\n"
            "\\section*{Intro}\n\n"
            "A paragraph.\n\n"
            "- list item"
        )
        p2 = parse_mmd(mmd)
        assert p2.front_matter.title == "My Title"
        types = [b.block_type for b in p2.blocks]
        assert P2BlockType.HEADING in types
        assert P2BlockType.PARAGRAPH in types
        assert P2BlockType.LIST_ITEM in types


# ════════════════════════════════════════════════════════════════════════
# MathpixImportProvider — integration tests
# ════════════════════════════════════════════════════════════════════════

class TestMathpixImportProvider:
    def test_headings_populated(self, tmp_path):
        mmd = "\\title{Doc}\n\n\\section*{Part One}\n\n\\subsection*{Sub A}"
        doc = _run_import(mmd, page_count=2, tmp_path=tmp_path)
        assert len(doc.headings) == 2
        assert doc.headings[0].text == "Part One"
        assert doc.headings[1].text == "Sub A"

    def test_heading_levels(self, tmp_path):
        mmd = "\\section*{H2 Heading}\n\n\\subsection*{H3 Heading}"
        doc = _run_import(mmd, page_count=1, tmp_path=tmp_path)
        from src.models.contracts import HeadingLevel
        assert doc.headings[0].level == HeadingLevel.H2
        assert doc.headings[1].level == HeadingLevel.H3

    def test_heading_source_is_mathpix(self, tmp_path):
        mmd = "\\section*{Test Heading}"
        doc = _run_import(mmd, page_count=1, tmp_path=tmp_path)
        assert doc.headings[0].source == "mathpix"

    def test_heading_document_order(self, tmp_path):
        mmd = "\n\n".join(
            f"\\section*{{Section {i}}}" for i in range(5)
        )
        doc = _run_import(mmd, page_count=2, tmp_path=tmp_path)
        orders = [h.document_order for h in doc.headings]
        assert orders == list(range(5))

    def test_front_matter_title(self, tmp_path):
        mmd = "\\title{My Document Title}\n\n\\section*{Chapter 1}"
        doc = _run_import(mmd, page_count=1, tmp_path=tmp_path)
        assert doc.front_matter is not None
        assert doc.front_matter.title == "My Document Title"

    def test_page_text_assigned(self, tmp_path):
        mmd = "A paragraph on the page."
        doc = _run_import(mmd, page_count=1, tmp_path=tmp_path)
        assert any(p.cleaned_text for p in doc.pages)

    def test_extraction_method_set(self, tmp_path):
        mmd = "Paragraph text."
        doc = _run_import(mmd, page_count=2, tmp_path=tmp_path)
        for page in doc.pages:
            assert page.extraction_method == ExtractionMethod.MATHPIX_IMPORT

    def test_ocr_confidence_high(self, tmp_path):
        mmd = "Paragraph text."
        doc = _run_import(mmd, page_count=1, tmp_path=tmp_path)
        assert doc.pages[0].ocr_confidence == OCRConfidence.HIGH

    def test_footnotes_populated(self, tmp_path):
        mmd = (
            "Text with footnote. ${ }^{1}$\n\n"
            "\\footnotetext{1}{The footnote body.}"
        )
        doc = _run_import(mmd, page_count=1, tmp_path=tmp_path)
        assert len(doc.footnotes) == 1
        assert doc.footnotes[0].number == 1
        assert doc.footnotes[0].body == "The footnote body."

    def test_footnote_source_is_mathpix(self, tmp_path):
        mmd = "\\footnotetext{1}{Body text.}"
        doc = _run_import(mmd, page_count=1, tmp_path=tmp_path)
        assert doc.footnotes[0].source == "mathpix"

    def test_tables_populated(self, tmp_path):
        mmd = "| Col A | Col B |\n|-------|-------|\n| r1c1  | r1c2  |"
        doc = _run_import(mmd, page_count=1, tmp_path=tmp_path)
        assert len(doc.tables) == 1
        assert doc.tables[0].extraction_source == "mathpix"

    def test_table_has_correct_dimensions(self, tmp_path):
        mmd = "| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |\n| 4 | 5 | 6 |"
        doc = _run_import(mmd, page_count=1, tmp_path=tmp_path)
        t = doc.tables[0]
        assert t.row_count == 3  # header + 2 data rows
        assert t.col_count == 3

    def test_double_extension_file(self, tmp_path):
        mmd = "\\title{Double Extension}\n\n\\section*{Introduction}"
        mmd_file = tmp_path / "test.mmd.mmd"
        mmd_file.write_text(mmd, encoding="utf-8")
        doc = _make_document(1)
        doc = MathpixImportProvider().import_document(doc, mmd_path=mmd_file)
        assert doc.front_matter.title == "Double Extension"
        assert len(doc.headings) == 1

    def test_no_front_matter_when_missing(self, tmp_path):
        mmd = "\\section*{Just a Heading}"
        doc = _run_import(mmd, page_count=1, tmp_path=tmp_path)
        # front_matter should remain None (no title found)
        assert doc.front_matter is None

    def test_existing_pages_preserved(self, tmp_path):
        mmd = "A paragraph."
        doc = _run_import(mmd, page_count=4, tmp_path=tmp_path)
        assert len(doc.pages) == 4
        page_numbers = [p.page_number for p in doc.pages]
        assert page_numbers == [1, 2, 3, 4]

    def test_heading_page_number_within_bounds(self, tmp_path):
        mmd = "\\section*{A}\n\n\\section*{B}\n\n\\section*{C}"
        doc = _run_import(mmd, page_count=3, tmp_path=tmp_path)
        for h in doc.headings:
            assert 1 <= h.page_number <= 3

    def test_document_corrections_starts_empty(self, tmp_path):
        mmd = "\\title{T}\n\n\\section*{S}"
        doc = _run_import(mmd, page_count=1, tmp_path=tmp_path)
        # Phase M-1 import: no corrections generated yet (that is Phase M-2)
        assert doc.corrections == []

    def test_importprovider_protocol_satisfied(self):
        from src.importers.base import ImportProvider
        provider = MathpixImportProvider()
        assert isinstance(provider, ImportProvider)
        assert provider.name == "mathpix"
