"""Equation LaTeX helpers (docs/EQUATION_DESIGN.md §2): row splitting,
numbers, spacing, allowlist, simple/non-maths classification, linear text."""

import pytest

from src.equations import latex as L


class TestSplitDisplay:
    def test_single_equation_is_one_row(self):
        rows = L.split_display("F=m a", "equation*")
        assert [r.latex for r in rows] == ["F=m a"]
        assert rows[0].number is None

    def test_align_rows_become_one_equation_each(self):
        rows = L.split_display(r"a & =b+c \\ d & =e", "align*")
        assert [r.latex for r in rows] == ["a =b+c", "d =e"]

    def test_gather_rows_split(self):
        rows = L.split_display(r"x=1 \\ y=2 \\ z=3", "gather*")
        assert [r.latex for r in rows] == ["x=1", "y=2", "z=3"]

    def test_row_separator_inside_a_matrix_is_not_a_row_break(self):
        rows = L.split_display(r"A=\begin{pmatrix} a & b \\ c & d \end{pmatrix}", "equation*")
        assert len(rows) == 1
        assert r"\begin{pmatrix}" in rows[0].latex

    def test_aligned_wrapper_is_unwrapped_into_rows(self):
        body = r"\begin{aligned} x &= 1 \\ y &= 2 \end{aligned}"
        rows = L.split_display(body, "equation*")
        assert [r.latex for r in rows] == ["x = 1", "y = 2"]

    def test_tag_becomes_the_number_and_leaves_the_equation(self):
        rows = L.split_display(r"E=m c^{2} \tag{6.1}", "equation")
        assert rows[0].number == "6.1"
        assert "tag" not in rows[0].latex

    def test_label_is_extracted(self):
        rows = L.split_display(r"E=m c^{2} \label{eq:e}", "equation*")
        assert rows[0].label == "eq:e"
        assert "label" not in rows[0].latex

    def test_nonumber_is_dropped(self):
        rows = L.split_display(r"a=b \nonumber", "equation")
        assert rows[0].latex == "a=b"

    def test_numbered_environment_without_tag_is_marked_unnumbered_known(self):
        rows = L.split_display("a=b", "equation")
        assert rows[0].number is None
        assert rows[0].numbered_without_tag is True

    def test_starred_environment_is_not_numbered(self):
        rows = L.split_display("a=b", "equation*")
        assert rows[0].numbered_without_tag is False

    def test_multi_column_align_row_is_reported(self):
        rows = L.split_display(r"a &= b & c &= d", "align*")
        assert rows[0].multi_column is True


class TestSpacing:
    def test_spacing_macros_are_removed(self):
        assert L.strip_spacing(r"a\,b\;c\!d\quad e") == "abcd e"

    def test_one_space_survives_before_a_unit(self):
        assert L.strip_spacing(r"6.02\,\mathrm{mol}") == r"6.02\ \mathrm{mol}"

    def test_space_before_text_unit_survives(self):
        assert L.strip_spacing(r"5\,\text{kg}") == r"5\ \text{kg}"


class TestAllowlist:
    def test_allowed_commands_pass(self):
        assert L.unsupported_commands(r"\frac{a}{b}+\sqrt{x}\leq\alpha") == set()

    def test_unknown_command_is_reported(self):
        assert L.unsupported_commands(r"\frac{a}{b}+\weirdmacro{x}") == {r"\weirdmacro"}

    def test_color_and_overset_are_never_allowed(self):
        assert L.unsupported_commands(r"\color{red}x") == {r"\color"}
        assert L.unsupported_commands(r"\overset{a}{b}") == {r"\overset"}

    def test_functions_and_environments_are_allowed(self):
        assert L.unsupported_commands(r"\sin x+\begin{pmatrix}a&b\end{pmatrix}") == set()

    def test_array_with_alignment_spec_is_unsupported(self):
        assert r"\begin{array}" in L.unsupported_commands(r"\begin{array}{cc} a & b \end{array}")

    def test_text_in_the_middle_is_detected(self):
        assert L.has_inner_text(r"a \text{ if } b")
        assert not L.has_inner_text(r"\text{rate} = k")
        assert not L.has_inner_text(r"k = 2 \text{ s}")


class TestEdgeText:
    def test_leading_and_trailing_text_move_out_of_the_box(self):
        eq, before, after = L.peel_edge_text(r"\text{where } a=b \text{ for all}")
        assert eq == "a=b"
        assert before == "where"
        assert after == "for all"

    def test_middle_text_is_left_alone_for_the_caller_to_flag(self):
        eq, before, after = L.peel_edge_text(r"a \text{ if } b")
        assert (eq, before, after) == (r"a \text{ if } b", "", "")

    def test_no_edge_text_changes_nothing(self):
        eq, before, after = L.peel_edge_text("a=b")
        assert (eq, before, after) == ("a=b", "", "")


class TestSimpleAndNonMaths:
    @pytest.mark.parametrize("src", ["F=m a", "x+y=3", "2 \\times 3", "n=20", "47 \\%"])
    def test_simple_equations(self, src):
        assert L.is_simple(src)

    @pytest.mark.parametrize(
        "src",
        [r"\frac{a}{b}", r"x^{2}", r"\sqrt{x}", r"a_{1}", r"\begin{pmatrix}a\end{pmatrix}", r"\sum x", r"\sin x",
         r"\mathrm{H_{2}O}", r"2\mathrm{H_{2}} + \mathrm{O_{2}}"],
    )
    def test_not_simple(self, src):
        assert not L.is_simple(src)

    @pytest.mark.parametrize("src", [r"\mathrm{A}", r"\mathrm{mol}", r"x=\mathrm{A}", r"\text{rate}=k"])
    def test_a_style_wrapper_around_plain_characters_is_still_simple(self, src):
        assert L.is_simple(src)

    @pytest.mark.parametrize("src", ["(1970,1972)", "1991", "$400", r"\$400", "(1959, 1979)", "25-30"])
    def test_non_maths_spans(self, src):
        assert L.is_non_maths(src)

    def test_real_maths_is_not_non_maths(self):
        assert not L.is_non_maths("x=1")


class TestLinearText:
    def test_superscript_digits_become_unicode(self):
        assert L.to_text(r"E=m c^{2}") == "E = mc²"

    def test_operators_are_spaced_and_unicode(self):
        assert L.to_text(r"p \leq 0.001") == "p ≤ 0.001"

    def test_fraction_and_root_are_readable(self):
        assert L.to_text(r"\frac{a}{b}") in ("(a)/(b)", "a/b")
        assert "√" in L.to_text(r"\sqrt{x}")

    def test_greek_letters(self):
        assert L.to_text(r"\alpha + \beta") == "α + β"

    def test_subscripts(self):
        assert L.to_text(r"H_{2}O") == "H₂O"


class TestNormalisation:
    def test_normalise_ignores_spacing_and_left_right(self):
        assert L.normalise(r"\left( a + b \right)") == L.normalise("(a+b)")

    def test_normalise_ignores_redundant_braces(self):
        assert L.normalise(r"x^{2}") == L.normalise(r"x^2")

    def test_normalise_treats_dfrac_as_frac(self):
        assert L.normalise(r"\dfrac{a}{b}") == L.normalise(r"\frac{a}{b}")

    def test_normalise_unwraps_mathrm(self):
        assert L.normalise(r"\mathrm{H_2SO_4}") == L.normalise("H_{2}SO_{4}")

    def test_normalise_row_break_forms_are_equal(self):
        source = r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}"
        round_tripped = "\\begin{pmatrix}\na & b\\ c & d\n\\end{pmatrix}"
        assert L.normalise(source) == L.normalise(round_tripped)

    def test_control_space_outside_a_matrix_is_only_spacing(self):
        assert L.normalise(r"6.02\ \mathrm{mol}") == L.normalise(r"6.02\, mol")

    def test_different_content_is_different(self):
        assert L.normalise("a+b") != L.normalise("a-b")

    def test_hat_and_widehat_are_the_same_accent(self):
        assert L.normalise(r"\hat{W}^{A}") == L.normalise(r"{\widehat{W}}^{A}")

    def test_an_accent_without_braces_equals_the_braced_one(self):
        assert L.normalise(r"\hat\lambda") == L.normalise(r"\widehat{\lambda}")

    def test_an_empty_script_is_no_script(self):
        assert L.normalise(r"\int_X f") == L.normalise(r"\int_{X}^{} f")

    def test_bracket_commands_equal_brackets(self):
        assert L.normalise(r"[a,b]") == L.normalise(r"\lbrack a,b\rbrack")

    def test_mathrm_around_an_accent_unwraps(self):
        assert L.normalise(r"\mathrm{\hat{J}}Z") == L.normalise(r"\hat{J}Z")

    def test_prime_before_a_subscript_equals_prime_after_it(self):
        assert L.normalise(r"U'_{eff}(x)") == L.normalise(r"U_{eff}'(x)")

    def test_a_real_accent_difference_is_still_a_difference(self):
        assert L.normalise(r"\hat{W}") != L.normalise(r"\bar{W}")
