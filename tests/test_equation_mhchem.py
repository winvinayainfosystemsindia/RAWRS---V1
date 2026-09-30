"""mhchem `\\ce{...}` subset translator (docs/EQUATION_DESIGN.md §3)."""

import pytest

from src.equations.mhchem import Unsupported, translate


class TestTranslate:
    def test_formula_with_counts(self):
        assert translate("H2O") == r"\mathrm{H_{2}O}"

    def test_sulfuric_acid(self):
        assert translate("H2SO4") == r"\mathrm{H_{2}SO_{4}}"

    def test_reaction_with_coefficients_and_arrow(self):
        assert translate("2H2 + O2 -> 2H2O") == (
            r"2\mathrm{H_{2}} + \mathrm{O_{2}} \rightarrow 2\mathrm{H_{2}O}"
        )

    def test_equilibrium_arrow(self):
        assert r"\rightleftharpoons" in translate("N2 + 3H2 <=> 2NH3")

    def test_explicit_caret_charge(self):
        assert translate("Fe^3+") == r"\mathrm{Fe^{3+}}"
        assert translate("SO4^2-") == r"\mathrm{SO_{4}^{2-}}"
        assert translate("Fe^{3+}") == r"\mathrm{Fe^{3+}}"

    def test_state_symbols(self):
        assert translate("NaCl(aq)") == r"\mathrm{NaCl(aq)}"
        assert translate("H2O(l)") == r"\mathrm{H_{2}O(l)}"

    def test_parenthesised_group_with_count(self):
        assert translate("Ca(OH)2") == r"\mathrm{Ca(OH)_{2}}"

    @pytest.mark.parametrize(
        "src",
        ["Na+", "OH-", "CH3-CH2-OH", "$K$", r"\color{red}{H2O}", "H2O ->[heat] CO2", "{}^{14}C", "1/2 O2"],
    )
    def test_outside_the_subset_is_unsupported_never_guessed(self, src):
        with pytest.raises(Unsupported):
            translate(src)

    def test_empty_is_unsupported(self):
        with pytest.raises(Unsupported):
            translate("   ")
