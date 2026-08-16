"""N-1 — a superscript becomes a note only when the source proves the body.

Mathpix marks a note reference in the prose (``${ }^{12}$``) and prints the note
bodies as an ordinary numbered run. That run is indistinguishable *by shape*
from a list: one benchmark document contains a four-item conceptual list, a
thirty-six-item note apparatus and an eleven-item citation list, all identical
line shapes. Classifying on typography would make all three notes, or none.

Two facts in the source decide it instead — the run begins after the last
marker, and its numbers cover every marker number. These tests pin the rule on
synthetic documents first (so it is not tuned to one corpus file), then pin the
measured corpus evidence the rule was derived from.
"""

from pathlib import Path
from typing import List, Optional

import pytest

from src.mathpix.mmd_parser import parse_mmd
from src.models.phase2_document import P2BlockType, P2Document, P2ListStyle

_SAMPLES = Path("samples/mathpix")


def _numbered(doc: P2Document) -> List[int]:
    return [
        block.list_number
        for block in doc.blocks
        if block.block_type is P2BlockType.LIST_ITEM
        and block.list_style is P2ListStyle.NUMBERED
    ]


def _corpus(pattern: str) -> P2Document:
    matches = sorted(_SAMPLES.rglob(f"{pattern}.mmd*"))
    if not matches:
        pytest.skip(f"corpus sample {pattern!r} not present")
    return parse_mmd(matches[0].read_text(encoding="utf8"))


def _mmd(
    prose: str, run: Optional[List[int]] = None, second: Optional[List[int]] = None
) -> str:
    parts = [prose]
    for numbers in (run, second):
        if numbers:
            parts.append("\n\n".join(f"{n}. Body number {n}." for n in numbers))
    return "\n\n".join(parts)


class TestTheRule:
    def test_a_run_after_the_markers_that_covers_them_is_the_apparatus(self):
        doc = parse_mmd(_mmd("Claim one ${ }^{1}$ and claim two ${ }^{2}$.", run=[1, 2, 3]))
        assert [f.number for f in doc.footnotes] == [1, 2, 3]
        assert _numbered(doc) == []

    def test_a_numbered_list_with_no_markers_anywhere_stays_a_list(self):
        """No typography-only classification: shape alone proves nothing."""
        doc = parse_mmd(_mmd("Ordinary prose with no superscripts.", run=[1, 2, 3]))
        assert doc.footnotes == []
        assert _numbered(doc) == [1, 2, 3]

    def test_a_run_that_does_not_cover_every_marker_is_not_the_apparatus(self):
        """The citation-list case: numbered, positioned after the prose, but not
        what the markers point into."""
        doc = parse_mmd(_mmd("A ${ }^{1}$ B ${ }^{2}$ C ${ }^{9}$.", run=[1, 2, 3]))
        assert doc.footnotes == []
        assert _numbered(doc) == [1, 2, 3]

    def test_a_run_inside_the_marker_span_is_not_the_apparatus(self):
        """The conceptual-list case: a numbered list interleaved with the prose
        that cites the notes."""
        source = (
            "Claim one ${ }^{1}$.\n\n"
            "1. A conceptual point.\n\n2. Another conceptual point.\n\n"
            "Later prose ${ }^{2}$.\n\n"
            "1. Body number 1.\n\n2. Body number 2."
        )
        doc = parse_mmd(source)
        assert [f.number for f in doc.footnotes] == [1, 2]
        assert _numbered(doc) == [1, 2]

    def test_the_first_qualifying_run_wins(self):
        doc = parse_mmd(_mmd("A ${ }^{1}$ B ${ }^{2}$.", run=[1, 2], second=[1, 2, 3]))
        assert [f.number for f in doc.footnotes] == [1, 2]
        assert _numbered(doc) == [1, 2, 3]

    def test_an_unmatched_marker_creates_nothing_and_keeps_its_prose(self):
        doc = parse_mmd("Prose citing ${ }^{7}$ with no bodies at all.")
        assert doc.footnotes == []
        texts = [b.text for b in doc.blocks if b.block_type is P2BlockType.PARAGRAPH]
        assert any("[7]" in (t or "") for t in texts), texts

    def test_repeated_markers_resolve_to_one_body(self):
        doc = parse_mmd(_mmd("A ${ }^{1}$ again ${ }^{1}$ and ${ }^{2}$.", run=[1, 2]))
        assert [f.number for f in doc.footnotes] == [1, 2]

    def test_bodies_keep_the_order_of_the_run(self):
        doc = parse_mmd(_mmd("A ${ }^{1}$ B ${ }^{3}$.", run=[1, 2, 3, 4]))
        assert [f.number for f in doc.footnotes] == [1, 2, 3, 4]
        assert doc.footnotes[0].body.endswith("number 1.")
        assert doc.footnotes[-1].body.endswith("number 4.")

    def test_a_body_the_markers_skip_is_still_part_of_the_apparatus(self):
        """The asymmetry: a body may lack a reference; a reference may never
        lack a body."""
        doc = parse_mmd(_mmd("A ${ }^{1}$ C ${ }^{3}$.", run=[1, 2, 3]))
        assert [f.number for f in doc.footnotes] == [1, 2, 3]

    def test_other_superscript_forms_are_recognised(self):
        for marker in ("^{1}", "\\textsuperscript{1}"):
            doc = parse_mmd(_mmd(f"A claim {marker} here.", run=[1]))
            assert [f.number for f in doc.footnotes] == [1], marker


class TestCorpusEvidence:
    def test_bruner_proves_a_thirty_six_body_apparatus(self):
        doc = _corpus("*Bruner*")
        assert [f.number for f in doc.footnotes] == list(range(1, 37))

    def test_bruner_keeps_its_conceptual_list_and_citation_list(self):
        """51 numbered lines in, 36 proven as the apparatus, 15 remain: the
        four-item conceptual list and the eleven-item citation list."""
        doc = _corpus("*Bruner*")
        assert _numbered(doc) == [1, 2, 3, 4] + list(range(1, 12))

    def test_bruner_bodies_without_markers_are_kept(self):
        """15, 26 and 34 are printed and numbered but their superscripts are
        absent from the package. They are bodies; no reference is invented."""
        doc = _corpus("*Bruner*")
        assert {15, 26, 34} <= {f.number for f in doc.footnotes}

    def test_aims_creates_no_notes(self):
        """21 markers, and the package contains no numbered bodies at all."""
        doc = _corpus("*Aims*")
        assert doc.footnotes == []

    def test_nature_of_enquiry_creates_no_notes(self):
        doc = _corpus("*Nature*")
        assert doc.footnotes == []

    def test_brinkman_proves_three(self):
        doc = _corpus("*brinkman*")
        assert [f.number for f in doc.footnotes] == [1, 2, 3]

    def test_documents_with_no_markers_are_untouched(self):
        for pattern, numbered in (("*Bryman*", 8), ("*sockett*", 3), ("*Leary*", 9)):
            doc = _corpus(pattern)
            assert doc.footnotes == [], pattern
            assert len(_numbered(doc)) == numbered, pattern
