"""LaTeX -> native Word equation (OMML) through pandoc, with post-processing
for Eq 3 and a round-trip check (docs/EQUATION_DESIGN.md §2, §5)."""

import pytest
from lxml import etree

from src.equations import omml

pytestmark = pytest.mark.skipif(omml.pandoc_path() is None, reason="pandoc not installed")

_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def _count(result, tag):
    return len(etree.fromstring(result.omml.encode("utf8")).findall(f".//{{{_M}}}{tag}"))


def _one(latex):
    (result,) = omml.convert_batch([latex])
    return result


class TestConvert:
    def test_superscripts_become_native_word_structure(self):
        result = _one("x^{2}+y^{2}=r^{2}")
        assert result.omml is not None and result.verified
        assert _count(result, "sSup") == 3

    def test_fraction_and_root(self):
        result = _one(r"\frac{-b \pm \sqrt{b^{2}-4ac}}{2a}")
        assert result.verified
        assert _count(result, "f") == 1 and _count(result, "rad") == 1

    def test_subscripts_and_greek(self):
        result = _one(r"\alpha_{1}+\beta_{2}")
        assert result.verified
        assert _count(result, "sSub") == 2

    def test_matrix_keeps_both_rows(self):
        result = _one(r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}")
        assert result.verified
        assert _count(result, "mr") == 2

    def test_batch_keeps_order_and_length(self):
        results = omml.convert_batch(["a^{2}", r"\frac{1}{2}", "b_{1}"])
        assert len(results) == 3
        assert _count(results[0], "sSup") == 1
        assert _count(results[1], "f") == 1
        assert _count(results[2], "sSub") == 1

    def test_empty_batch(self):
        assert omml.convert_batch([]) == []

    def test_chemistry_translated_to_latex_converts(self):
        result = _one(r"2\mathrm{H_{2}} + \mathrm{O_{2}} \rightarrow 2\mathrm{H_{2}O}")
        assert result.omml is not None
        assert result.verified


class TestFunctions:
    def test_named_functions_use_the_equation_tool(self):
        result = _one(r"\sin x + \cos y")
        assert _count(result, "func") == 2
        assert result.verified

    def test_inverse_function_keeps_its_exponent_inside_the_function_name(self):
        result = _one(r"\sin^{-1} x")
        assert _count(result, "func") == 1
        assert _count(result, "sSup") == 1
        assert result.verified

    def test_function_with_a_bracketed_argument(self):
        result = _one(r"\tan(x+y)")
        assert _count(result, "func") == 1
        assert result.verified

    def test_a_function_with_nothing_after_it_is_left_alone_not_broken(self):
        result = _one(r"x + \sin")
        assert result.omml is not None
        assert _count(result, "func") == 0


class TestFailures:
    def test_unknown_macro_yields_no_equation_and_a_reason(self):
        result = _one(r"\unknownmacro{x}+y")
        assert result.omml is None
        assert result.reason

    def test_one_failure_does_not_spoil_its_neighbours(self):
        first, broken, last = omml.convert_batch(["a^{2}", r"\unknownmacro{x}", "b^{2}"])
        assert first.omml is not None and last.omml is not None
        assert broken.omml is None

    def test_round_trip_rejects_a_different_equation(self):
        (good,) = omml.convert_batch(["a+b"])
        assert omml.round_trip(["a-b"], [good.omml]) == [False]
        assert omml.round_trip(["a+b"], [good.omml]) == [True]

    def test_without_pandoc_every_equation_is_unconverted_with_a_reason(self, monkeypatch):
        monkeypatch.setattr(omml, "pandoc_path", lambda: None)
        (result,) = omml.convert_batch(["a^{2}"])
        assert result.omml is None
        assert "pandoc" in result.reason
