"""P-1 C2 — a block's page is stated by the PDF, or it is not stated at all.

Every test here pins a safety property of src/mathpix/page_alignment.py:
what may become an anchor, what may never become one, what an unproven side
of a bracket means, and when a whole document must be refused. Synthetic
pages throughout — a real PDF would test PyMuPDF, not the rule.
"""

from dataclasses import dataclass
from typing import Optional

from src.mathpix.page_alignment import (
    MIN_ANCHOR_CHARS,
    AlignmentStatus,
    align_blocks_to_pages,
)


@dataclass
class _Block:
    """The two attributes the aligner reads off a P2Block."""

    source_line: Optional[int]
    text: str


ALPHA = "Alpha the quick brown fox jumps over the lazy dog"
BETA = "Beta the patient tortoise outpaces the sleeping hare"
GAMMA = "Gamma the careful heron waits beside the still river"
HEADER = "Folk Pedagogy and the Culture of Education"


def _page(*parts: str) -> str:
    return "\n".join(parts)


class TestWhatMayBecomeAnAnchor:
    def test_a_unique_long_block_states_its_page(self) -> None:
        alignment = align_blocks_to_pages(
            [_Block(0, ALPHA)], [_page("nothing here at all"), _page(ALPHA)]
        )

        assert alignment.status is AlignmentStatus.ALIGNED
        assert alignment.stated_page(0) == 2
        assert alignment.accepted == 1

    def test_text_on_two_pages_is_not_an_anchor(self) -> None:
        alignment = align_blocks_to_pages(
            [_Block(0, ALPHA)], [_page(ALPHA), _page(ALPHA)]
        )

        assert alignment.status is AlignmentStatus.NO_EVIDENCE
        assert alignment.rejected_ambiguous == 1
        assert alignment.stated_page(0) is None

    def test_a_running_header_is_not_an_anchor(self) -> None:
        """It repeats on every page, so it identifies none of them."""
        pages = [_page(HEADER, ALPHA), _page(HEADER, BETA), _page(HEADER, GAMMA)]

        alignment = align_blocks_to_pages([_Block(0, HEADER), _Block(1, BETA)], pages)

        assert alignment.rejected_ambiguous == 1
        assert alignment.stated_page(0) is None
        assert alignment.stated_page(1) == 2

    def test_text_shorter_than_the_threshold_is_not_an_anchor(self) -> None:
        short = "Chapter 4"
        assert len(short) < MIN_ANCHOR_CHARS
        alignment = align_blocks_to_pages(
            [_Block(0, short), _Block(1, BETA)], [_page(short), _page(BETA)]
        )

        assert alignment.rejected_short == 1
        assert alignment.stated_page(0) is None

    def test_text_absent_from_every_page_is_unmatched_not_anchored(self) -> None:
        alignment = align_blocks_to_pages(
            [_Block(0, ALPHA), _Block(1, GAMMA)], [_page(ALPHA), _page(BETA)]
        )

        assert alignment.unmatched == 1
        assert alignment.stated_page(1) is None

    def test_an_empty_page_never_matches(self) -> None:
        alignment = align_blocks_to_pages([_Block(0, ALPHA)], ["", _page(ALPHA), ""])

        assert alignment.stated_page(0) == 2

    def test_normalisation_ignores_case_punctuation_and_whitespace(self) -> None:
        block = _Block(0, "The Nature of Enquiry, revisited: a study of method")
        page = _page("the   nature of enquiry revisited a study of method")

        assert align_blocks_to_pages([block], ["", page]).stated_page(0) == 2

    def test_a_word_the_pdf_broke_across_lines_is_not_repaired(self) -> None:
        """No fuzzy repair: the block simply does not anchor."""
        block = _Block(0, "Understanding pedagogy requires patience and attention")
        page = _page("Understanding peda-", "gogy requires patience and attention")

        alignment = align_blocks_to_pages([block], [page])

        assert alignment.status is AlignmentStatus.NO_EVIDENCE
        assert alignment.unmatched == 1


class TestMonotonicity:
    def test_anchors_may_advance_across_pages(self) -> None:
        alignment = align_blocks_to_pages(
            [_Block(0, ALPHA), _Block(5, BETA), _Block(9, GAMMA)],
            [_page(ALPHA), _page(BETA), _page(GAMMA)],
        )

        assert alignment.accepted == 3
        assert alignment.anchor_pages == (1, 2, 3)

    def test_two_anchors_may_share_a_page(self) -> None:
        alignment = align_blocks_to_pages(
            [_Block(0, ALPHA), _Block(1, BETA)], [_page(ALPHA, BETA), _page(GAMMA)]
        )

        assert alignment.accepted == 2
        assert alignment.anchor_pages == (1, 1)

    def test_a_backwards_anchor_is_refused_not_reordered(self) -> None:
        """One stray hit must not drag the document backwards, and the
        anchors around it still stand."""
        pages = [_page(ALPHA)] + [
            _page(f"body number {index} " + BETA) for index in range(2, 24)
        ]
        blocks = [_Block(0, ALPHA)] + [
            _Block(index, f"body number {index} " + BETA) for index in range(2, 24)
        ]
        blocks.append(_Block(99, ALPHA))  # last block, but its text is on page 1

        alignment = align_blocks_to_pages(blocks, pages)

        assert alignment.rejected_backwards == 1
        assert alignment.status is AlignmentStatus.ALIGNED  # 1 of 23 is within 5%
        assert alignment.stated_page(99) is None
        assert list(alignment.anchor_pages) == sorted(alignment.anchor_pages)

    def test_too_many_conflicts_reject_the_whole_document(self) -> None:
        pages = [_page(ALPHA), _page(BETA), _page(GAMMA)]
        blocks = [
            _Block(0, ALPHA),
            _Block(1, GAMMA),
            _Block(2, BETA),  # backwards: page 2 after page 3
        ]

        alignment = align_blocks_to_pages(blocks, pages)

        assert alignment.status is AlignmentStatus.REJECTED
        assert alignment.brackets == {}
        assert alignment.bracket_for(0).is_open

    def test_a_document_with_no_anchors_has_no_evidence(self) -> None:
        alignment = align_blocks_to_pages([_Block(0, ALPHA)], ["", "", ""])

        assert alignment.status is AlignmentStatus.NO_EVIDENCE
        assert alignment.usable is False
        assert alignment.bracket_for(0).is_open


class TestBrackets:
    def _three_page_alignment(self):
        pages = [_page(ALPHA), _page(BETA), _page(GAMMA)]
        blocks = [
            _Block(0, "a short lead"),  # before the first anchor
            _Block(1, ALPHA),  # anchor, page 1
            _Block(2, "unmatched middle prose that appears nowhere in the pdf"),
            _Block(3, GAMMA),  # anchor, page 3
            _Block(4, "a short tail"),  # after the last anchor
        ]
        return align_blocks_to_pages(blocks, pages)

    def test_an_anchor_brackets_itself_exactly(self) -> None:
        alignment = self._three_page_alignment()

        assert alignment.bracket_for(1).stated == 1
        assert alignment.bracket_for(3).stated == 3

    def test_a_block_between_anchors_is_bounded_by_both(self) -> None:
        bracket = self._three_page_alignment().bracket_for(2)

        assert (bracket.lower, bracket.upper) == (1, 3)
        assert bracket.stated is None

    def test_a_block_before_the_first_anchor_invents_no_lower_bound(self) -> None:
        bracket = self._three_page_alignment().bracket_for(0)

        assert bracket.lower is None
        assert bracket.upper == 1

    def test_a_block_after_the_last_anchor_invents_no_upper_bound(self) -> None:
        bracket = self._three_page_alignment().bracket_for(4)

        assert bracket.lower == 3
        assert bracket.upper is None

    def test_an_unknown_line_is_unproven(self) -> None:
        alignment = self._three_page_alignment()

        assert alignment.bracket_for(404).is_open
        assert alignment.bracket_for(None).is_open


class TestInputIsUntouched:
    def test_pages_stay_within_the_physical_page_range(self) -> None:
        pages = [_page(ALPHA), _page(BETA), _page(GAMMA)]
        alignment = align_blocks_to_pages(
            [_Block(0, ALPHA), _Block(1, BETA), _Block(2, GAMMA)], pages
        )

        for bracket in alignment.brackets.values():
            for bound in (bracket.lower, bracket.upper):
                assert bound is None or 1 <= bound <= len(pages)

    def test_block_order_is_read_not_imposed(self) -> None:
        """Blocks handed over out of source_line order produce the same
        evidence, and the caller's list is left exactly as it was."""
        pages = [_page(ALPHA), _page(BETA), _page(GAMMA)]
        ordered = [_Block(0, ALPHA), _Block(1, BETA), _Block(2, GAMMA)]
        shuffled = [ordered[2], ordered[0], ordered[1]]
        identities = [id(block) for block in shuffled]

        from_ordered = align_blocks_to_pages(ordered, pages)
        from_shuffled = align_blocks_to_pages(shuffled, pages)

        assert from_ordered.brackets == from_shuffled.brackets
        assert [id(block) for block in shuffled] == identities
        assert [block.source_line for block in shuffled] == [2, 0, 1]

    def test_a_block_without_a_source_line_is_ignored(self) -> None:
        alignment = align_blocks_to_pages(
            [_Block(None, ALPHA), _Block(1, BETA)], [_page(ALPHA), _page(BETA)]
        )

        assert alignment.accepted == 1
        assert alignment.stated_page(1) == 2

    def test_the_same_input_gives_the_same_answer(self) -> None:
        pages = [_page(ALPHA), _page(BETA)]
        blocks = [_Block(0, ALPHA), _Block(1, BETA)]

        assert align_blocks_to_pages(blocks, pages) == align_blocks_to_pages(blocks, pages)

    def test_a_document_with_no_pages_has_no_evidence(self) -> None:
        alignment = align_blocks_to_pages([_Block(0, ALPHA)], [])

        assert alignment.status is AlignmentStatus.NO_EVIDENCE
        assert alignment.page_count == 0
