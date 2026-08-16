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


class TestAnchorTransport:
    """N-2 commit 1+2: the position N-1 proved reaches the Footnote model."""

    def test_the_offset_lands_on_the_marker_not_near_it(self):
        doc = parse_mmd(_mmd("Some prose ${ }^{1}$ and more ${ }^{2}$ here.", run=[1, 2]))
        for note in doc.footnotes:
            assert note.anchor_text is not None
            segment = note.anchor_text[note.anchor_offset :]
            assert segment.startswith(f"[{note.number}]"), segment[:20]

    def test_the_anchor_is_the_transformed_line_the_paragraph_will_hold(self):
        doc = parse_mmd(_mmd("Prose ${ }^{1}$ tail.", run=[1]))
        assert doc.footnotes[0].anchor_text == "Prose [1] tail."

    def test_a_body_with_no_marker_carries_no_anchor(self):
        doc = parse_mmd(_mmd("Only ${ }^{1}$ is cited.", run=[1, 2]))
        first, second = doc.footnotes
        assert first.anchor_text is not None and first.anchor_offset is not None
        assert second.anchor_text is None and second.anchor_offset is None

    def test_a_number_cited_twice_keeps_one_anchor(self):
        doc = parse_mmd(_mmd("A ${ }^{1}$ then again ${ }^{1}$.", run=[1]))
        assert len(doc.footnotes) == 1
        assert doc.footnotes[0].anchor_text.index("[1]") == doc.footnotes[0].anchor_offset

    def test_bruner_anchors_exactly_thirty_three_of_thirty_six(self):
        doc = _corpus("*Bruner*")
        anchored = [f for f in doc.footnotes if f.anchor_text is not None]
        assert len(doc.footnotes) == 36 and len(anchored) == 33
        assert [f.number for f in doc.footnotes if f.anchor_text is None] == [15, 26, 34]

    def test_a_marker_inside_a_list_item_is_anchored_to_the_item_text(self):
        """The anchor is recorded against the source line, but what gets
        rendered is the block that line became - and a numbered item drops
        its "1. " prefix on the way. The offset moves by exactly that
        prefix; nothing is searched for."""
        doc = parse_mmd(
            "Prose ${ }^{1}$ here.\n\n"
            "1. An item citing ${ }^{2}$ inline.\n\n"
            "1. Body one.\n\n2. Body two."
        )
        cited = next(f for f in doc.footnotes if f.number == 2)

        assert cited.anchor_text == "An item citing [2] inline."
        assert cited.anchor_text[cited.anchor_offset :].startswith("[2]")

    def test_an_anchor_whose_block_is_not_a_suffix_keeps_the_line(self):
        """Fail closed: only the exact suffix relationship is a licence to
        move the coordinate."""
        from src.mathpix.mmd_parser import _anchor_on_its_block
        from src.models.phase2_document import P2Block

        anchor = (7, "1. text with [2] inside", 16)
        merged = P2Block(
            block_type=P2BlockType.PARAGRAPH,
            text="text with [2] inside and a second line",
            source_line=7,
        )
        elsewhere = P2Block(
            block_type=P2BlockType.PARAGRAPH, text="inside", source_line=8
        )

        assert _anchor_on_its_block(anchor, merged) == anchor
        assert _anchor_on_its_block(anchor, elsewhere) == anchor
        assert _anchor_on_its_block(anchor, None) == anchor

    def test_bruner_binds_its_two_list_item_anchors(self):
        doc = _corpus("*Bruner*")
        for number in (18, 19):
            note = next(f for f in doc.footnotes if f.number == number)
            assert not note.anchor_text.startswith("1. "), note.anchor_text[:20]
            assert note.anchor_text[note.anchor_offset :].startswith(f"[{number}]")

    def test_the_renderer_spells_only_the_anchors_that_were_proven(self):
        """N-2 commit 3. The marker becomes ``[^label]`` where a marker was
        proven, and stays literal text where one never existed - including
        when the orphan's own number happens to sit in the prose."""
        from src.markdown.markdown_builder import _render_page_semantic
        from src.mathpix.ingestor import _p2footnote_to_footnote
        from src.models.paragraph import Paragraph

        doc = parse_mmd(_mmd("Cited [15] in 1915 and ${ }^{1}$ here.", run=[1, 15]))
        notes = [_p2footnote_to_footnote(f, page_count=1, total_blocks=1) for f in doc.footnotes]
        paragraph = Paragraph(
            page_number=1, text="Cited [15] in 1915 and [1] here.", source_line=0
        )

        [block] = _render_page_semantic([], [paragraph], [], [], [], notes)

        assert block == f"Cited [15] in 1915 and [^{notes[0].label}] here."

    def test_a_reference_printed_inside_a_list_item_is_spelled_there(self):
        """N-2 repair: the list branch spells references with the same
        helper the paragraph branch uses - two of Bruner's thirty-three
        proven markers are printed inside a list item."""
        from src.markdown.markdown_builder import _render_page_semantic
        from src.mathpix.ingestor import _p2footnote_to_footnote
        from src.models.list_block import ListBlock, ListItem, ListType

        doc = parse_mmd(
            "Prose ${ }^{1}$ here.\n\n"
            "1. An item citing ${ }^{2}$ inline.\n\n"
            "1. Body one.\n\n2. Body two."
        )
        notes = [
            _p2footnote_to_footnote(f, page_count=1, total_blocks=1)
            for f in doc.footnotes
        ]
        cited = next(n for n in notes if n.number == 2)
        lst = ListBlock(
            list_type=ListType.NUMBERED,
            items=[ListItem(text="An item citing [2] inline.")],
            page_number=1,
            document_order=0,
            source_line=2,
        )

        blocks = _render_page_semantic([], [], [lst], [], [], notes)

        assert blocks[-1] == f"1. An item citing [^{cited.label}] inline."

    def test_the_ingestor_maps_the_anchor_and_makes_it_an_endnote(self):
        from src.mathpix.ingestor import _p2footnote_to_footnote
        from src.models.footnote import NoteType

        doc = parse_mmd(_mmd("Prose ${ }^{1}$ tail.", run=[1, 2]))
        anchored = _p2footnote_to_footnote(doc.footnotes[0], page_count=4, total_blocks=8)
        orphan = _p2footnote_to_footnote(doc.footnotes[1], page_count=4, total_blocks=8)

        assert anchored.note_type is NoteType.ENDNOTE
        assert anchored.anchor_text == "Prose [1] tail."
        assert anchored.anchor_offset == doc.footnotes[0].anchor_offset
        assert anchored.footnote_id == "mathpix-1"

        # The orphan keeps the old placeholders: its anchor is genuinely
        # unknown, and nothing may go looking for it.
        assert orphan.note_type is NoteType.ENDNOTE
        assert orphan.anchor_text == orphan.marker and orphan.anchor_offset is None
