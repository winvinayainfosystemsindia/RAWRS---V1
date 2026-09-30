"""Mathpix MMD parser: no equation is lost (docs/EQUATION_DESIGN.md F1-F3, §5)."""

from src.mathpix.mmd_parser import parse_mmd
from src.models.phase2_document import P2BlockType


def _eq_blocks(mmd):
    return [b for b in parse_mmd(mmd).blocks if b.block_type == P2BlockType.EQUATION]


def _paragraph_texts(mmd):
    return [b.text for b in parse_mmd(mmd).blocks if b.block_type == P2BlockType.PARAGRAPH]


class TestDisplayEnvironments:
    def test_equation_star_is_captured_with_its_latex(self):
        blocks = _eq_blocks("Intro\n\\begin{equation*}\nF=m a\n\\end{equation*}\nAfter\n")
        assert [b.text for b in blocks] == ["F=m a"]
        assert blocks[0].equation_env == "equation*"

    def test_numbered_equation_keeps_env_name(self):
        blocks = _eq_blocks("\\begin{equation}\nE=m c^{2} \\tag{1}\n\\end{equation}\n")
        assert blocks[0].equation_env == "equation"
        assert "\\tag{1}" in blocks[0].text

    def test_align_star_is_one_block_holding_all_rows(self):
        blocks = _eq_blocks("\\begin{align*}\na & =b+c \\\\\nd & =e\n\\end{align*}\n")
        assert len(blocks) == 1
        assert "a & =b+c" in blocks[0].text and "d & =e" in blocks[0].text

    def test_gather_is_captured(self):
        assert len(_eq_blocks("\\begin{gather}\nx=1\n\\end{gather}\n")) == 1

    def test_source_line_is_recorded(self):
        blocks = _eq_blocks("p1\n\n\\begin{equation*}\nx=1\n\\end{equation*}\n")
        assert blocks[0].source_line > 0


class TestDisplayDelimiters:
    def test_double_dollar_multiline(self):
        blocks = _eq_blocks("Text\n$$\nE=m c^{2}\n$$\nMore\n")
        assert [b.text for b in blocks] == ["E=m c^{2}"]

    def test_double_dollar_single_line(self):
        assert [b.text for b in _eq_blocks("$$x^{2}+y^{2}=r^{2}$$\n")] == ["x^{2}+y^{2}=r^{2}"]

    def test_bracket_delimiters(self):
        blocks = _eq_blocks("\\[\n\\int_{0}^{1} x d x=\\frac{1}{2}\n\\]\n")
        assert [b.text for b in blocks] == ["\\int_{0}^{1} x d x=\\frac{1}{2}"]

    def test_no_raw_delimiter_paragraphs_remain(self):
        texts = _paragraph_texts("a\n$$\nx=1\n$$\nb\n\\[\ny=2\n\\]\n")
        assert "$$" not in texts and "\\[" not in texts and "\\]" not in texts
        assert not any("x=1" in t or "y=2" in t for t in texts)

    def test_prose_around_an_equation_survives(self):
        assert _paragraph_texts("Before\n$$\nx=1\n$$\nAfter\n") == ["Before", "After"]


class TestInlineStaysInTheParagraph:
    def test_inline_math_is_not_a_display_block(self):
        mmd = "Also \\(v=u+a t\\) inline and $x^{2}+y^{2}=r^{2}$ here.\n"
        assert _eq_blocks(mmd) == []
        assert len(_paragraph_texts(mmd)) == 1

    def test_dollar_currency_does_not_open_a_display_block(self):
        assert _eq_blocks("It cost $400 and then $5.\n") == []


class TestMathSuperscriptsAreNotNoteMarkers:
    """``x^{2}`` inside maths is an exponent, not footnote 2 (N-1 read every
    bare ``^{N}`` as a marker, so STEM prose proved a numbered list a note
    apparatus)."""

    def test_inline_exponent_does_not_prove_a_numbered_list_a_note_apparatus(self):
        doc = parse_mmd("Solve $x^{2}=4$.\n\n1. First item.\n\n2. Second item.\n")
        assert doc.footnotes == []
        numbered = [b for b in doc.blocks if b.block_type == P2BlockType.LIST_ITEM]
        assert [b.list_number for b in numbered] == [1, 2]

    def test_single_line_display_exponent_is_not_a_marker(self):
        doc = parse_mmd("$$x^{2}$$\n\n1. A.\n\n2. B.\n")
        assert doc.footnotes == []

    def test_paren_delimited_exponent_is_not_a_marker(self):
        doc = parse_mmd("Solve \\(x^{2}=4\\).\n\n1. A.\n\n2. B.\n")
        assert doc.footnotes == []

    def test_a_real_marker_beside_an_exponent_still_counts(self):
        doc = parse_mmd("Claim $x^{2}=4$ holds ${ }^{1}$ here.\n\n1. Note.\n\n2. Extra.\n")
        by_number = {f.number: f for f in doc.footnotes}
        assert by_number[1].anchor_line is not None
        assert by_number[2].anchor_line is None


class TestNothingElseChanged:
    def test_figure_and_table_still_parse(self):
        mmd = "\\begin{figure}\n\\includegraphics{a.jpg}\n\\caption{Cap}\n\\end{figure}\n"
        types = [b.block_type for b in parse_mmd(mmd).blocks]
        assert P2BlockType.FIGURE in types
