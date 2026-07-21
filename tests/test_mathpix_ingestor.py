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
        # FE-0-004: doc.headings holds content headings AND one H6 page
        # marker per page, matching the native PDF path. Assert the two
        # groups separately rather than the combined length.
        # FE-0-005: \title{Doc} is additionally promoted to an H1, so
        # content is [title H1, "Part One", "Sub A"].
        content = [h for h in doc.headings if not h.is_page_marker]
        markers = [h for h in doc.headings if h.is_page_marker]
        assert len(content) == 3
        assert len(markers) == 2  # one per page
        assert content[0].text == "Doc"          # title -> H1
        assert content[1].text == "Part One"
        assert content[2].text == "Sub A"

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
        # FE-0-004: content headings keep orders 0..4; the 2 page markers
        # continue the sequence (5, 6) rather than restarting or colliding.
        content_orders = [h.document_order for h in doc.headings if not h.is_page_marker]
        assert content_orders == list(range(5))
        all_orders = [h.document_order for h in doc.headings]
        assert all_orders == list(range(7))  # 5 content + 2 page markers
        assert len(set(all_orders)) == len(all_orders)  # no duplicate orders

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


class TestFeature020ParagraphPromotionAndSourceLine:
    """document.paragraphs (promoted from transient/RAWRS-native-only)
    and source_line (the shared cross-type ordering key) — both feed
    markdown_builder.py's _render_page_semantic()."""

    def test_paragraphs_populated_alongside_cleaned_text(self, tmp_path):
        mmd = "First paragraph.\n\nSecond paragraph."
        doc = _run_import(mmd, page_count=1, tmp_path=tmp_path)
        assert len(doc.paragraphs) == 2
        assert doc.paragraphs[0].text == "First paragraph."
        assert doc.paragraphs[1].text == "Second paragraph."
        # page.cleaned_text still populated in parallel, not replaced.
        assert "First paragraph." in doc.pages[0].cleaned_text

    def test_paragraph_source_line_increases_in_order(self, tmp_path):
        mmd = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        doc = _run_import(mmd, page_count=1, tmp_path=tmp_path)
        lines = [p.source_line for p in doc.paragraphs]
        assert lines == sorted(lines)
        assert len(set(lines)) == 3

    def test_heading_list_callout_table_carry_source_line(self, tmp_path):
        mmd = (
            "\\section*{Summary}\n\n"
            "- item one\n- item two\n\n"
            "Body paragraph.\n\n"
            "| A | B |\n|---|---|\n| 1 | 2 |"
        )
        doc = _run_import(mmd, page_count=1, tmp_path=tmp_path)
        assert doc.headings[0].source_line is not None
        assert doc.lists[0].source_line is not None
        assert doc.callouts[0].source_line is not None
        assert doc.tables[0].source_line is not None
        # A true document-order sequence: heading first, then everything else.
        assert doc.headings[0].source_line < doc.lists[0].source_line

    def test_rawrs_native_paragraph_construction_unaffected(self):
        """paragraph_grouper.py's construction (no document_order/
        source_line, no provenance kwarg) must keep working unchanged —
        the promotion to SemanticObject is additive."""
        from src.models.bounding_box import BoundingBox
        from src.models.paragraph import Paragraph

        p = Paragraph(
            page_number=1,
            text="Some text.",
            bbox=BoundingBox(x0=0, y0=0, x1=10, y1=10),
            source_orders=[0, 1],
        )
        assert p.document_order is None
        assert p.source_line is None

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

    def test_bullet_list_becomes_list_block_not_flattened_paragraph(self, tmp_path):
        mmd = "- First item\n- Second item\n- Third item"
        doc = _run_import(mmd, page_count=1, tmp_path=tmp_path)
        assert len(doc.lists) == 1
        assert doc.lists[0].list_type.value == "bullet"
        assert [i.text for i in doc.lists[0].items] == ["First item", "Second item", "Third item"]
        # The exact defect this fixes: list item text must not also leak
        # into page.cleaned_text as flattened paragraph lines.
        combined_page_text = "\n".join(p.cleaned_text or "" for p in doc.pages)
        assert "First item" not in combined_page_text

    def test_numbered_list_becomes_list_block(self, tmp_path):
        mmd = "1. Alpha\n2. Beta"
        doc = _run_import(mmd, page_count=1, tmp_path=tmp_path)
        assert len(doc.lists) == 1
        assert doc.lists[0].list_type.value == "numbered"

    def test_list_provenance_is_mathpix(self, tmp_path):
        mmd = "- Only item"
        doc = _run_import(mmd, page_count=1, tmp_path=tmp_path)
        assert doc.lists[0].provenance.value == "mathpix"

    def test_paragraph_between_two_lists_produces_two_list_blocks(self, tmp_path):
        mmd = "- List one item\n\nAn intervening paragraph.\n\n- List two item"
        doc = _run_import(mmd, page_count=1, tmp_path=tmp_path)
        assert len(doc.lists) == 2

    def test_double_extension_file(self, tmp_path):
        mmd = "\\title{Double Extension}\n\n\\section*{Introduction}"
        mmd_file = tmp_path / "test.mmd.mmd"
        mmd_file.write_text(mmd, encoding="utf-8")
        doc = _make_document(1)
        doc = MathpixImportProvider().import_document(doc, mmd_path=mmd_file)
        assert doc.front_matter.title == "Double Extension"
        # FE-0-004: content headings counted separately from page markers.
        # FE-0-005: the title is additionally promoted to H1, so content
        # is [title H1, "Introduction"].
        content = [h for h in doc.headings if not h.is_page_marker]
        assert len(content) == 2
        assert content[0].text == "Double Extension"   # title -> H1
        assert content[1].text == "Introduction"

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


# ════════════════════════════════════════════════════════════════════════
# FE-0-004 — page-marker parity between ingestion pipelines
#
# The defect: Mathpix ingestion produced no page-marker Heading objects,
# while the markdown renderer silently synthesized replacements at render
# time. Output looked correct; the canonical model was incomplete, so
# PAGE_001 reported every page as missing its marker and those phantom
# errors drove the readiness score.
#
# These tests fail if either pipeline stops producing markers, or if the
# two stop agreeing.
# ════════════════════════════════════════════════════════════════════════

class TestFE0004PageMarkerParity:
    def test_mathpix_import_creates_one_marker_per_page(self, tmp_path):
        doc = _run_import(r"\section*{Only Heading}", page_count=4, tmp_path=tmp_path)
        markers = [h for h in doc.headings if h.is_page_marker]
        assert len(markers) == 4
        assert sorted(m.page_number for m in markers) == [1, 2, 3, 4]

    def test_markers_are_h6(self, tmp_path):
        from src.models.contracts import HeadingLevel
        doc = _run_import(r"\section*{H}", page_count=3, tmp_path=tmp_path)
        for m in (h for h in doc.headings if h.is_page_marker):
            assert m.level == HeadingLevel.H6

    def test_every_page_has_exactly_one_marker(self, tmp_path):
        """The invariant PAGE_001 enforces, asserted directly."""
        doc = _run_import(
            "\\section*{A}\n\n\\section*{B}", page_count=5, tmp_path=tmp_path
        )
        for page in doc.pages:
            found = [
                h for h in doc.headings
                if h.is_page_marker and h.page_number == page.page_number
            ]
            assert len(found) == 1, f"page {page.page_number} has {len(found)} markers"

    def test_page_001_reports_no_error_for_mathpix_document(self, tmp_path):
        """End-to-end: the validator rule that produced the false errors."""
        from src.validation.validator import _check_missing_page_markers
        doc = _run_import(r"\section*{Heading}", page_count=4, tmp_path=tmp_path)
        assert _check_missing_page_markers(doc) == []

    def test_marker_text_prefers_page_label_then_printed_label(self, tmp_path):
        """Label precedence must match the native path (FEATURE_018/feature_009)."""
        doc = _make_document(3)
        doc.pages[0].page_label = "iv"          # reviewed label wins
        doc.pages[1].printed_label = "12"       # detected label when no review
        # page 3 has neither -> physical page number
        mmd_file = tmp_path / "t.mmd"
        mmd_file.write_text(r"\section*{X}", encoding="utf-8")
        doc = MathpixImportProvider().import_document(doc, mmd_path=mmd_file)
        by_page = {
            h.page_number: h.text for h in doc.headings if h.is_page_marker
        }
        assert by_page[1] == "iv"
        assert by_page[2] == "12"
        assert by_page[3] == "3"

    def test_both_pipelines_use_the_same_marker_builder(self):
        """Guards against a second, divergent implementation appearing.

        Both ingestion paths must resolve build_page_marker to the same
        function object; if either grows its own copy this fails.
        """
        from src.headings import heading_detector
        from src.mathpix import ingestor
        from src.headings.page_markers import build_page_marker
        assert heading_detector.build_page_marker is build_page_marker
        assert ingestor.build_page_marker is build_page_marker
