"""P4a — the two rules both projections share, tested where they now live.

Emphasis and note placement were decided inside the Markdown projection and
recovered by the DOCX one from the syntax Markdown had just written. These
tests pin the semantic answers themselves — booleans and positions — with
no ``**`` and no ``[^label]`` anywhere in the assertions. That is the point:
if a test here needed Markdown syntax to express its expectation, the rule
would not have moved.

The Markdown-side syntax is pinned separately, in
``TestMarkdownStillSpellsItTheSameWay``.
"""

from typing import List, Optional

from src.models.bounding_box import BoundingBox
from src.models.contracts import Footnote, NoteType, Span, TextBlock
from src.models.inline_format import (
    BOLD_FLAG,
    ITALIC_FLAG,
    SUPERSCRIPT_FLAG,
    TextRun,
    all_blocks_bold,
    all_blocks_italic,
    format_runs,
)
from src.models.note_references import resolve_note_references

PLAIN = 0


def _span(text: str, flags: int) -> Span:
    return Span(
        text=text,
        font_flags=flags,
        font_size=12.0,
        font_name="Times",
        baseline_y=50.0,
        bbox=BoundingBox(x0=0, y0=40, x1=100, y1=52),
    )


def _block(
    text: str, spans: Optional[List[Span]] = None, is_bold=None, order: int = 0
) -> TextBlock:
    return TextBlock(
        page_number=1,
        text=text,
        bbox=BoundingBox(x0=0, y0=order * 10, x1=100, y1=order * 10 + 8),
        order=order,
        is_bold=is_bold,
        spans=spans or [],
    )


def _note(
    marker: str = "1",
    anchor_text: str = "A line with a marker1",
    anchor_offset: Optional[int] = 20,
    number: int = 1,
    note_type: NoteType = NoteType.FOOTNOTE,
    body: str = "The note body.",
) -> Footnote:
    return Footnote(
        note_type=note_type,
        number=number,
        marker=marker,
        anchor_page_number=1,
        anchor_text=anchor_text,
        anchor_offset=anchor_offset,
        body=body,
        body_page_number=1,
        body_source_text=f"{marker} {body}",
    )


class TestEmphasisIsReadFromTheDocument:
    def test_plain_text_is_one_unemphasised_run(self) -> None:
        block = _block("Ordinary prose.", [_span("Ordinary prose.", PLAIN)])
        assert format_runs("Ordinary prose.", [block]) == [TextRun("Ordinary prose.")]

    def test_bold(self) -> None:
        block = _block("Bold prose.", [_span("Bold prose.", BOLD_FLAG)])
        assert format_runs("Bold prose.", [block]) == [TextRun("Bold prose.", bold=True)]

    def test_italic(self) -> None:
        block = _block("Italic prose.", [_span("Italic prose.", ITALIC_FLAG)])
        assert format_runs("Italic prose.", [block]) == [TextRun("Italic prose.", italic=True)]

    def test_bold_and_italic_together(self) -> None:
        block = _block("Both.", [_span("Both.", BOLD_FLAG | ITALIC_FLAG)])
        assert format_runs("Both.", [block]) == [TextRun("Both.", bold=True, italic=True)]

    def test_the_run_carries_the_paragraph_text_not_the_span_text(self) -> None:
        """``Paragraph.text`` is transformed — hyphens repaired, fragments
        merged — so the run must carry what the caller passed, not what the
        spans happen to hold."""
        block = _block("frag", [_span("frag", BOLD_FLAG)])

        assert format_runs("Repaired paragraph text.", [block])[0].text == (
            "Repaired paragraph text."
        )


class TestUniformityIsRequired:
    def test_one_plain_span_defeats_bold(self) -> None:
        block = _block("Mixed.", [_span("Bold ", BOLD_FLAG), _span("plain.", PLAIN)])
        assert format_runs("Mixed.", [block]) == [TextRun("Mixed.")]

    def test_one_plain_block_defeats_bold(self) -> None:
        blocks = [
            _block("Bold line.", [_span("Bold line.", BOLD_FLAG)]),
            _block("Plain line.", [_span("Plain line.", PLAIN)], order=1),
        ]
        assert format_runs("Bold line. Plain line.", blocks)[0].bold is False

    def test_adjacent_spans_agreeing_stay_bold(self) -> None:
        block = _block("Two spans.", [_span("Two ", BOLD_FLAG), _span("spans.", BOLD_FLAG)])
        assert format_runs("Two spans.", [block])[0].bold is True

    def test_span_order_does_not_change_the_answer(self) -> None:
        # Uniformity is a property of the set, so a reordered span list must
        # give the same answer — the rule never reads span text or position.
        spans = [_span("a", BOLD_FLAG), _span("b", BOLD_FLAG), _span("c", BOLD_FLAG)]

        assert all_blocks_bold([_block("abc", spans)]) is True
        assert all_blocks_bold([_block("abc", list(reversed(spans)))]) is True


class TestSuperscriptsAreDecorationNotFormatting:
    def test_a_superscript_marker_does_not_defeat_bold(self) -> None:
        block = _block(
            "Bold with marker1",
            [_span("Bold with marker", BOLD_FLAG), _span("1", SUPERSCRIPT_FLAG)],
        )
        assert format_runs("Bold with marker1", [block])[0].bold is True

    def test_a_block_of_only_superscripts_is_not_decisive(self) -> None:
        blocks = [
            _block("Bold.", [_span("Bold.", BOLD_FLAG)]),
            _block("1", [_span("1", SUPERSCRIPT_FLAG)], order=1),
        ]
        assert format_runs("Bold. 1", blocks)[0].bold is True


class TestMissingEvidence:
    def test_no_blocks_yields_one_plain_run(self) -> None:
        assert format_runs("Unattributed.", []) == [TextRun("Unattributed.")]

    def test_a_block_without_spans_falls_back_to_is_bold(self) -> None:
        assert all_blocks_bold([_block("Line.", None, is_bold=True)]) is True
        assert all_blocks_bold([_block("Line.", None, is_bold=False)]) is False
        assert all_blocks_bold([_block("Line.", None, is_bold=None)]) is False

    def test_italic_has_no_line_level_fallback(self) -> None:
        """Deliberate asymmetry, predating P4a: TextBlock has no is_italic,
        and asserting italic from nothing would italicise ordinary prose."""
        assert all_blocks_italic([_block("Line.", None, is_bold=True)]) is False

    def test_empty_block_list_is_false_for_both(self) -> None:
        assert all_blocks_bold([]) is False
        assert all_blocks_italic([]) is False

    def test_special_characters_are_carried_through_untouched(self) -> None:
        # The rule decides emphasis; escaping is each format's own problem,
        # so nothing here may transform the text.
        text = "Asterisks * and ** and <xml> & \\backslash"

        assert format_runs(text, [_block(text, [_span(text, PLAIN)])])[0].text == text


class TestNoteReferencePlacement:
    def test_a_single_reference_is_located_by_recorded_offset(self) -> None:
        note = _note()
        [reference] = resolve_note_references("A line with a marker1", [note])

        assert (reference.start, reference.length) == (20, 1)
        assert reference.note is note

    def test_the_reference_carries_identity_not_syntax(self) -> None:
        note = _note()
        [reference] = resolve_note_references("A line with a marker1", [note])

        assert reference.label == note.label
        assert reference.number == 1
        assert reference.note_type is NoteType.FOOTNOTE

    def test_an_endnote_is_reported_as_an_endnote(self) -> None:
        note = _note(note_type=NoteType.ENDNOTE)
        [reference] = resolve_note_references("A line with a marker1", [note])

        assert reference.note_type is NoteType.ENDNOTE

    def test_multiple_references_come_back_in_ascending_position(self) -> None:
        first = _note(marker="1", anchor_text="Alpha1 and beta2", anchor_offset=5, number=1)
        second = _note(marker="2", anchor_text="Alpha1 and beta2", anchor_offset=15, number=2)

        references = resolve_note_references("Alpha1 and beta2", [second, first])

        assert [r.start for r in references] == [5, 15]
        assert [r.number for r in references] == [1, 2]

    def test_references_from_different_lines_of_one_paragraph(self) -> None:
        # Paragraph assembly joins lines; each note keeps its own anchor
        # line, which is how a joined paragraph stays resolvable.
        first = _note(marker="1", anchor_text="First line1", anchor_offset=10, number=1)
        second = _note(marker="2", anchor_text="second line2", anchor_offset=11, number=2)

        references = resolve_note_references("First line1 second line2", [first, second])

        assert [r.start for r in references] == [10, 23]

    def test_an_anchor_at_the_very_beginning(self) -> None:
        note = _note(marker="1", anchor_text="1 opens the line", anchor_offset=0)
        [reference] = resolve_note_references("1 opens the line", [note])

        assert reference.start == 0

    def test_an_anchor_at_the_very_end(self) -> None:
        note = _note(marker="9", anchor_text="ends with nine9", anchor_offset=14)
        [reference] = resolve_note_references("ends with nine9", [note])

        assert reference.start == 14

    def test_a_note_whose_line_is_absent_is_not_placed(self) -> None:
        # One call may be handed a whole page's notes while rendering a
        # single paragraph; a note from elsewhere must never touch it.
        note = _note(anchor_text="A line from another paragraph1")

        assert resolve_note_references("Unrelated prose entirely.", [note]) == []

    def test_offsets_survive_a_prefix_on_the_text(self) -> None:
        """The offset is relative to the anchor line, which is why an
        already-emphasised paragraph still resolves — the line is located
        first, and the offset applied from there."""
        note = _note()
        [reference] = resolve_note_references("**A line with a marker1**", [note])

        assert reference.start == 22  # 2 for the wrapper, 20 within the line


class TestUnresolvableReferences:
    def test_an_offset_pointing_at_the_wrong_character_falls_back_to_search(self) -> None:
        note = _note(marker="1", anchor_text="A line with a marker1", anchor_offset=3)
        [reference] = resolve_note_references("A line with a marker1", [note])

        assert reference.start == 20  # found by bounded search, not by the offset

    def test_a_missing_offset_falls_back_to_search(self) -> None:
        note = _note(marker="1", anchor_text="A line with a marker1", anchor_offset=None)
        [reference] = resolve_note_references("A line with a marker1", [note])

        assert reference.start == 20

    def test_the_search_never_leaves_the_anchor_line(self) -> None:
        """bug_005: a plain-digit marker collides with years and counts
        elsewhere in the same paragraph, so the fallback is bounded."""
        note = _note(marker="7", anchor_text="second line7", anchor_offset=None)

        [reference] = resolve_note_references("in 1977 a year sat here second line7", [note])

        assert reference.start == 35  # the marker in its own line, not the "7" in "1977"

    def test_a_marker_that_cannot_be_found_yields_no_reference(self) -> None:
        note = _note(marker="4", anchor_text="a line with no such marker", anchor_offset=None)

        assert resolve_note_references("a line with no such marker", [note]) == []

    def test_two_notes_sharing_a_line_do_not_claim_the_same_marker(self) -> None:
        exact = _note(marker="1", anchor_text="one1 and one1 again", anchor_offset=3, number=1)
        searched = _note(
            marker="1", anchor_text="one1 and one1 again", anchor_offset=None, number=2
        )

        references = resolve_note_references("one1 and one1 again", [exact, searched])

        assert sorted(r.start for r in references) == [3, 12]

    def test_no_notes_yields_no_references(self) -> None:
        assert resolve_note_references("Prose with no notes at all.", []) == []


class TestMarkdownStillSpellsItTheSameWay:
    """The projection's half: same semantic answer, same Markdown syntax."""

    def test_emphasis_syntax(self) -> None:
        from src.markdown.markdown_builder import _apply_inline_format

        bold = _block("t", [_span("t", BOLD_FLAG)])
        italic = _block("t", [_span("t", ITALIC_FLAG)])
        both = _block("t", [_span("t", BOLD_FLAG | ITALIC_FLAG)])
        plain = _block("t", [_span("t", PLAIN)])

        assert _apply_inline_format("t", [bold]) == "**t**"
        assert _apply_inline_format("t", [italic]) == "*t*"
        assert _apply_inline_format("t", [both]) == "***t***"
        assert _apply_inline_format("t", [plain]) == "t"
        assert _apply_inline_format("t", []) == "t"

    def test_note_reference_syntax(self) -> None:
        from src.markdown.markdown_builder import _substitute_markers

        note = _note()

        assert _substitute_markers("A line with a marker1", [note]) == (
            f"A line with a marker[^{note.label}]"
        )

    def test_two_references_are_substituted_right_to_left(self) -> None:
        """Applying left to right would invalidate the second offset, since
        ``[^label]`` is longer than the marker it replaces."""
        from src.markdown.markdown_builder import _substitute_markers

        first = _note(marker="1", anchor_text="Alpha1 and beta2", anchor_offset=5, number=1)
        second = _note(marker="2", anchor_text="Alpha1 and beta2", anchor_offset=15, number=2)

        result = _substitute_markers("Alpha1 and beta2", [first, second])

        assert result == f"Alpha[^{first.label}] and beta[^{second.label}]"

    def test_an_unresolvable_note_leaves_the_text_alone(self) -> None:
        from src.markdown.markdown_builder import _substitute_markers

        note = _note(anchor_text="a line from somewhere else1")

        assert _substitute_markers("Untouched prose.", [note]) == "Untouched prose."
