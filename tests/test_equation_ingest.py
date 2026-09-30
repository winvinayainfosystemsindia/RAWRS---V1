"""Equation model + Mathpix ingest (docs/EQUATION_DESIGN.md §2, §3, §5)."""

from __future__ import annotations

from pathlib import Path

from src.mathpix.ingestor import MathpixImportProvider
from src.models.contracts import Document
from src.models.equation import Equation, EquationStatus
from src.models.metadata import Metadata
from src.models.page import Page


def _import(mmd: str, tmp_path: Path, pages: int = 1) -> Document:
    mmd_file = tmp_path / "t.mmd"
    mmd_file.write_text(mmd, encoding="utf-8")
    doc = Document(
        source_pdf_path="t.pdf",
        metadata=Metadata(filename="t.pdf", page_count=pages),
        pages=[Page(page_number=i + 1) for i in range(pages)],
    )
    return MathpixImportProvider().import_document(doc, mmd_path=mmd_file)


def _display(doc):
    return [e for e in doc.equations if e.display]


def _inline(doc):
    return [e for e in doc.equations if not e.display]


class TestModel:
    def test_latex_defaults_to_the_source(self):
        eq = Equation(latex_source=r"x^{2}", page_number=1, document_order=0)
        assert eq.latex == r"x^{2}"
        assert eq.object_type == "equation"
        assert eq.status is EquationStatus.CONVERTED

    def test_id_is_backfilled_from_the_source_line(self):
        eq = Equation(latex_source="x", page_number=1, document_order=3, source_line=12, row=2)
        assert eq.id == "equation-line-12-2"

    def test_document_carries_no_equations_by_default(self):
        doc = Document(source_pdf_path="a.pdf", metadata=Metadata(filename="a.pdf", page_count=1))
        assert doc.equations == []


class TestDisplayEquations:
    def test_simple_display_equation_is_plain_text_outside_the_box(self, tmp_path):
        doc = _import("Intro\n\\begin{equation*}\nF=m a\n\\end{equation*}\n", tmp_path)
        (eq,) = _display(doc)
        assert eq.status is EquationStatus.PLAIN
        assert eq.text == "F = ma"
        assert eq.latex_source == "F=m a"

    def test_real_equation_is_converted_with_its_tag_as_the_number(self, tmp_path):
        doc = _import("\\begin{equation}\nE=m c^{2} \\tag{6.1}\n\\end{equation}\n", tmp_path)
        (eq,) = _display(doc)
        assert eq.status is EquationStatus.CONVERTED
        assert eq.number == "6.1"
        assert eq.latex == "E=m c^{2}"

    def test_numbered_environment_without_tag_is_flagged_not_guessed(self, tmp_path):
        doc = _import("\\begin{equation}\nx^{2}=4\n\\end{equation}\n", tmp_path)
        (eq,) = _display(doc)
        assert eq.status is EquationStatus.FLAGGED
        assert eq.number is None
        assert any("number" in reason for reason in eq.flag_reasons)

    def test_align_rows_become_separate_equations_with_ordered_ids(self, tmp_path):
        doc = _import("\\begin{align*}\nx^{2} & =1 \\\\\ny^{2} & =2\n\\end{align*}\n", tmp_path)
        eqs = _display(doc)
        assert [e.latex for e in eqs] == ["x^{2} =1", "y^{2} =2"]
        assert len({e.id for e in eqs}) == 2
        assert eqs[0].id.endswith("-0") and eqs[1].id.endswith("-1")

    def test_unknown_macro_is_flagged(self, tmp_path):
        doc = _import("$$\n\\weirdmacro{x}+y^{2}\n$$\n", tmp_path)
        (eq,) = _display(doc)
        assert eq.status is EquationStatus.FLAGGED
        assert any("weirdmacro" in reason for reason in eq.flag_reasons)

    def test_text_in_the_middle_is_flagged(self, tmp_path):
        doc = _import("$$\na^{2} \\text{ if } b^{2}\n$$\n", tmp_path)
        (eq,) = _display(doc)
        assert eq.status is EquationStatus.FLAGGED

    def test_edge_text_leaves_the_box(self, tmp_path):
        doc = _import("$$\n\\text{where } a^{2}=b^{2} \\text{ for all}\n$$\n", tmp_path)
        (eq,) = _display(doc)
        assert eq.latex == "a^{2}=b^{2}"
        assert eq.before_text == "where"
        assert eq.after_text == "for all"

    def test_spacing_macros_are_removed_but_the_source_is_kept(self, tmp_path):
        doc = _import("$$\nx^{2}\\,+\\,y^{2}\n$$\n", tmp_path)
        (eq,) = _display(doc)
        assert eq.latex == "x^{2}+y^{2}"
        assert eq.latex_source == "x^{2}\\,+\\,y^{2}"

    def test_non_maths_in_a_display_block_is_plain(self, tmp_path):
        doc = _import("$$\n(1970,1972)\n$$\n", tmp_path)
        (eq,) = _display(doc)
        assert eq.status is EquationStatus.PLAIN

    def test_page_and_source_line_are_recorded(self, tmp_path):
        doc = _import("p\n\n$$\nx^{2}\n$$\n", tmp_path)
        (eq,) = _display(doc)
        assert eq.page_number == 1
        assert eq.source_line is not None and eq.source_line > 0


class TestChemistry:
    def test_ce_is_translated_and_the_source_kept(self, tmp_path):
        doc = _import("$$\n\\ce{2H2 + O2 -> 2H2O}\n$$\n", tmp_path)
        (eq,) = _display(doc)
        assert eq.status is EquationStatus.CONVERTED
        assert eq.latex_source == "\\ce{2H2 + O2 -> 2H2O}"
        assert "\\rightarrow" in eq.latex and "\\ce" not in eq.latex

    def test_a_lone_species_label_is_plain_text_not_a_box(self, tmp_path):
        doc = _import("$$\n\\ce{A}\n$$\n", tmp_path)
        (eq,) = _display(doc)
        assert eq.status is EquationStatus.PLAIN
        assert eq.text == "A"

    def test_a_real_formula_stays_an_equation(self, tmp_path):
        doc = _import("$$\n\\ce{H2O}\n$$\n", tmp_path)
        (eq,) = _display(doc)
        assert eq.status is EquationStatus.CONVERTED

    def test_ce_outside_the_subset_is_flagged(self, tmp_path):
        doc = _import("$$\n\\ce{Na+}\n$$\n", tmp_path)
        (eq,) = _display(doc)
        assert eq.status is EquationStatus.FLAGGED
        assert any("mhchem" in reason for reason in eq.flag_reasons)


class TestInlineEquations:
    def test_inline_maths_becomes_an_anchored_equation(self, tmp_path):
        doc = _import("Energy is $x^{2}+y^{2}=r^{2}$ here.\n", tmp_path)
        (eq,) = _inline(doc)
        (paragraph,) = doc.paragraphs
        assert eq.paragraph_id == paragraph.id
        assert paragraph.text[eq.anchor_offset:eq.anchor_offset + eq.anchor_length] == eq.text
        assert "$" not in paragraph.text
        assert eq.status is EquationStatus.CONVERTED

    def test_paren_delimiters_are_inline_maths_too(self, tmp_path):
        doc = _import("Also \\(v=u+a t\\) inline.\n", tmp_path)
        (eq,) = _inline(doc)
        assert eq.status is EquationStatus.PLAIN
        assert doc.paragraphs[0].text == f"Also {eq.text} inline."

    def test_currency_is_never_maths(self, tmp_path):
        doc = _import("It cost $400 and then $5 more.\n", tmp_path)
        assert doc.equations == []
        assert doc.paragraphs[0].text == "It cost $400 and then $5 more."

    def test_two_spans_keep_their_own_anchors(self, tmp_path):
        doc = _import("A $x^{2}$ and B $y^{3}$ end.\n", tmp_path)
        first, second = _inline(doc)
        text = doc.paragraphs[0].text
        assert text[first.anchor_offset:first.anchor_offset + first.anchor_length] == first.text
        assert text[second.anchor_offset:second.anchor_offset + second.anchor_length] == second.text
        assert first.anchor_offset < second.anchor_offset

    def test_note_anchor_survives_an_earlier_equation(self, tmp_path):
        mmd = "Claim $x^{2}+y^{2}$ holds${ }^{1}$.\n\n1. The note body.\n"
        doc = _import(mmd, tmp_path)
        (paragraph,) = doc.paragraphs
        (note,) = doc.footnotes
        assert note.anchor_offset is not None
        assert paragraph.text[note.anchor_offset:note.anchor_offset + len(note.marker)] == note.marker
        assert note.anchor_text == paragraph.text
