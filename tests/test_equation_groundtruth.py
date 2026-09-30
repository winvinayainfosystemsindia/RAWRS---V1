r"""Real equations with LaTeX ground truth (docs/EQUATION_DESIGN.md §5).

Three openly licensed arXiv papers (CC BY 4.0, see
``data/cache/equation_samples/SOURCES.txt``): physics, chemistry, maths. The
``.tex`` each paper was typeset from is the ground truth, so every check here
compares RAWRS's Word equation with LaTeX a human wrote, independent of the
round trip the converter itself uses. Git-ignored and skipped when the samples
are not on disk.

Display equations are taken as unnumbered: arXiv sources auto-number, while a
Mathpix export carries ``\tag`` for a printed number, and the number is a
separate rule (Eq 4) with its own tests.
"""

from __future__ import annotations

import gzip
import io
import re
import tarfile
from collections import Counter
from pathlib import Path
from typing import List, Tuple

import pytest
from lxml import etree

from src.equations import latex as tex
from src.equations import omml
from src.equations.build import _matching_brace, prepare
from src.equations.mhchem import Unsupported, translate

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "cache" / "equation_samples"
PHYSICS, CHEMISTRY, MATHS = "2208.04306", "2609.33784", "2609.36306"
_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"

pytestmark = [
    pytest.mark.skipif(not SAMPLES.is_dir(), reason="equation samples not downloaded"),
    pytest.mark.skipif(omml.pandoc_path() is None, reason="pandoc not installed"),
]

_ENV = re.compile(r"\\begin\{(equation|align|gather)\*?\}(.*?)\\end\{\1\*?\}", re.S)
_BRACKET = re.compile(r"\\\[(.*?)\\\]", re.S)
_DOLLARS = re.compile(r"\$\$(.*?)\$\$", re.S)


def _tex_source(paper: str) -> str:
    raw = (SAMPLES / f"{paper}.src").read_bytes()
    try:
        archive = tarfile.open(fileobj=io.BytesIO(raw))
        members = [m for m in archive.getmembers() if m.name.endswith(".tex")]
        return "\n".join(archive.extractfile(m).read().decode("utf8", "ignore") for m in members)
    except tarfile.TarError:
        return gzip.decompress(raw).decode("utf8", "ignore")


def _display_rows(paper: str) -> List[str]:
    source = _tex_source(paper)
    blocks: List[Tuple[str, str]] = [(m.group(1) + "*", m.group(2)) for m in _ENV.finditer(source)]
    blocks += [("equation*", m.group(1)) for m in _BRACKET.finditer(source)]
    blocks += [("equation*", m.group(1)) for m in _DOLLARS.finditer(source)]
    return [row.latex for env, body in blocks for row in tex.split_display(body, env)]


def _confident(paper: str) -> List[str]:
    """Rows RAWRS would convert (CONVERTED, not PLAIN/FLAGGED), de-duplicated."""
    seen, rows = set(), []
    for latex in _display_rows(paper):
        prepared = prepare(latex)
        if prepared.status.value == "converted" and prepared.latex not in seen:
            seen.add(prepared.latex)
            rows.append(prepared.latex)
    return rows


def _alnum(text: str) -> Counter:
    return Counter(c for c in text if c.isalnum())


def _omml_text(xml: str) -> str:
    root = etree.fromstring(xml.encode("utf8"))
    return "".join(t.text or "" for t in root.iter(f"{{{_M}}}t"))


@pytest.fixture(scope="module")
def converted():
    """(latex, Conversion) for every confident row of the physics and maths papers."""
    rows = _confident(PHYSICS) + _confident(MATHS)
    return list(zip(rows, omml.convert_batch(rows)))


class TestParsing:
    @pytest.mark.parametrize("paper,minimum", [(PHYSICS, 100), (MATHS, 10)])
    def test_every_display_equation_yields_rows(self, paper, minimum):
        assert len(_display_rows(paper)) >= minimum

    def test_the_real_papers_contain_equations_rawrs_is_confident_about(self):
        assert len(_confident(PHYSICS)) >= 10
        assert len(_confident(MATHS)) >= 1


class TestFidelity:
    def test_most_confident_equations_survive_conversion_and_round_trip(self, converted):
        verified = [item for item in converted if item[1].verified]
        print(f"\nconfident rows: {len(converted)}, verified: {len(verified)}")
        assert len(verified) >= 0.95 * len(converted)

    def test_a_verified_equation_keeps_every_letter_and_digit_of_its_source(self, converted):
        for latex, result in converted:
            if not result.verified:
                continue
            source = _alnum(re.sub(r"\\[A-Za-z]+", "", latex))
            rendered = _alnum(_omml_text(result.omml))
            missing = {c: n for c, n in source.items() if rendered[c] < n}
            assert not missing, f"{latex!r} lost {missing}"

    def test_the_round_trip_rejects_a_changed_equation(self, converted):
        checked = 0
        for latex, result in converted:
            if not result.verified:
                continue
            assert omml.round_trip([latex + " + z"], [result.omml]) == [False], latex
            checked += 1
            if checked >= 25:
                break
        assert checked > 0

    def test_named_functions_in_real_equations_use_the_equation_tool(self, converted):
        seen = 0
        for latex, result in converted:
            if not result.verified or not re.search(r"\\(?:sin|cos|tan|log|ln|exp)\b", latex):
                continue
            root = etree.fromstring(result.omml.encode("utf8"))
            typed = [
                r for r in root.iter(f"{{{_M}}}r")
                if "".join(r.itertext()).strip() in tex.FUNCTIONS
                and not any(a.tag == f"{{{_M}}}fName" for a in r.iterancestors())
            ]
            assert not typed, latex
            seen += 1
        print(f"\nequations with named functions checked: {seen}")


class TestChemistry:
    @staticmethod
    def _bodies() -> List[str]:
        source = _tex_source(CHEMISTRY)
        bodies, position = [], 0
        while True:
            start = source.find("\\ce{", position)
            if start == -1:
                return sorted(set(bodies))
            end = _matching_brace(source, start + 3)
            if end == -1:
                return sorted(set(bodies))
            bodies.append(source[start + 4:end])
            position = end + 1

    def test_the_paper_really_uses_mhchem(self):
        assert len(self._bodies()) >= 50

    def test_every_translatable_ce_converts_and_verifies(self):
        translated = []
        for body in self._bodies():
            try:
                translated.append(translate(body))
            except Unsupported:
                continue
        print(f"\n\\ce bodies translatable: {len(translated)} of {len(self._bodies())}")
        assert len(translated) >= 0.6 * len(self._bodies())
        results = omml.convert_batch(translated)
        assert all(r.verified for r in results), [
            (t, r.reason) for t, r in zip(translated, results) if not r.verified
        ][:3]

    def test_an_ce_outside_the_subset_is_flagged_never_guessed(self):
        flagged = 0
        for body in self._bodies():
            try:
                translate(body)
            except Unsupported:
                prepared = prepare(f"\\ce{{{body}}}")
                assert prepared.status.value == "flagged", body
                assert any(r.startswith("mhchem") for r in prepared.reasons)
                flagged += 1
        assert flagged > 0
