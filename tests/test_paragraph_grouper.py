"""Tests for src/structure/paragraph_grouper.py (paragraph reconstruction,
Option B - see samples/regressions/bug_001_brinkman_word_splitting/notes_md/
for the audit and design review this implements).
"""

from typing import List, Optional

from src.models.contracts import BoundingBox, TextBlock
from src.structure.paragraph_grouper import group_into_paragraphs


def _block(
    text: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    order: int,
    source_block_index: Optional[int] = 0,
    page_number: int = 1,
) -> TextBlock:
    return TextBlock(
        page_number=page_number,
        text=text,
        bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
        order=order,
        source_block_index=source_block_index,
    )


class TestEmptyInput:
    def test_empty_list_returns_empty_list(self) -> None:
        assert group_into_paragraphs([]) == []


class TestBug1SameBaselineMerge:
    """Real Brinkman bbox values (see root_cause_audit.md's Evidence
    table) - 8 same-baseline fragments with no PyMuPDF-emitted space
    between them, which must be merged back into one continuous run of
    text before paragraph joining ever runs."""

    def test_same_baseline_fragments_merge_with_inserted_spaces(self) -> None:
        # "and" (x 237.0-255.0) is required to bridge the interviews/
        # open-ended gap within _MAX_FRAGMENT_GAP_PT - omitting it would
        # make this fixture geometrically inconsistent with real PDF
        # word-spacing (interviews,->open-ended directly is a 32.3pt
        # gap, which is a real column-gutter-sized gap, not word
        # spacing - the merge correctly refuses to bridge it alone).
        blocks = [
            _block("questionnaires,", 42.52, 361.78, 103.18, 371.74, 0),
            _block("semi-structured", 112.14, 361.78, 176.24, 371.74, 1),
            _block("interviews,", 185.21, 361.78, 228.99, 371.74, 2),
            _block("and", 237.0, 361.78, 255.0, 371.74, 3),
            _block("open-ended", 261.29, 361.78, 309.42, 371.74, 4),
            _block("life-narratives,", 318.44, 361.78, 375.24, 371.74, 5),
            _block("while", 384.20, 361.78, 405.45, 371.74, 6),
            _block("their", 414.48, 361.78, 433.65, 371.74, 7),
        ]
        paragraphs = group_into_paragraphs(blocks)

        assert len(paragraphs) == 1
        assert paragraphs[0].text == (
            "questionnaires, semi-structured interviews, and open-ended life-narratives, while their"
        )

    def test_full_brinkman_sentence_reconstructs_correctly(self) -> None:
        blocks = [
            _block(
                "beliefs of 60 elementary teachers in three Indian states are explored through written",
                42.5, 349.8, 433.6, 359.8, 0,
            ),
            _block("questionnaires,", 42.52, 361.78, 103.18, 371.74, 1),
            _block("semi-structured", 112.14, 361.78, 176.24, 371.74, 2),
            _block("interviews,", 185.21, 361.78, 228.99, 371.74, 3),
            _block("and", 237.0, 361.78, 255.0, 371.74, 4),
            _block("open-ended", 261.29, 361.78, 309.42, 371.74, 5),
            _block("life-narratives,", 318.44, 361.78, 375.24, 371.74, 6),
            _block("while", 384.20, 361.78, 405.45, 371.74, 7),
            _block("their", 414.48, 361.78, 433.65, 371.74, 8),
            _block(
                "pedagogy is analysed through classroom observations. Findings suggest several prevalent",
                42.5, 373.7, 433.7, 383.7, 9,
            ),
        ]
        paragraphs = group_into_paragraphs(blocks)

        assert len(paragraphs) == 1
        assert paragraphs[0].text == (
            "beliefs of 60 elementary teachers in three Indian states are explored through written "
            "questionnaires, semi-structured interviews, and open-ended life-narratives, while their "
            "pedagogy is analysed through classroom observations. Findings suggest several prevalent"
        )

    def test_fragments_with_real_pymupdf_emitted_space_are_not_double_spaced(self) -> None:
        # A normal line (its words already include real space spans, so
        # each "fragment" here is the whole line, not a word) must not
        # be affected by the merge step at all when line gaps are large
        # (different baselines).
        blocks = [
            _block("First line of a paragraph", 42.5, 100.0, 200.0, 110.0, 0),
            _block("second line of the same paragraph", 42.5, 112.0, 220.0, 122.0, 1),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert len(paragraphs) == 1
        assert paragraphs[0].text == "First line of a paragraph second line of the same paragraph"


class TestSameBaselineGuards:
    def test_overlapping_same_y_fragments_are_not_merged(self) -> None:
        # Two-column false-merge guard: same y-range but x ranges
        # overlap (not a left-to-right continuation) - must not merge.
        blocks = [
            _block("Left column text", 42.0, 200.0, 150.0, 210.0, 0),
            _block("Overlapping fragment", 100.0, 200.0, 250.0, 210.0, 1),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert len(paragraphs) == 2

    def test_same_y_fragments_with_gap_too_large_are_not_merged(self) -> None:
        # Two-column false-merge guard: same y-range, large horizontal
        # gap (column gutter, not word-spacing) - must not merge.
        blocks = [
            _block("Column one text", 42.0, 200.0, 150.0, 210.0, 0),
            _block("Column two text", 300.0, 200.0, 420.0, 210.0, 1),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert len(paragraphs) == 2
        assert [p.text for p in paragraphs] == ["Column one text", "Column two text"]

    def test_different_y0_but_same_y1_is_not_merged(self) -> None:
        blocks = [
            _block("First fragment", 42.0, 200.0, 100.0, 212.0, 0),
            _block("Second fragment", 105.0, 205.0, 160.0, 212.0, 1),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert len(paragraphs) == 2


class TestHyphenRepair:
    def test_trailing_hyphen_joins_without_space(self) -> None:
        blocks = [
            _block("promoting Western-", 42.5, 100.0, 200.0, 110.0, 0),
            _block("originating approaches", 42.5, 112.0, 220.0, 122.0, 1),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert paragraphs[0].text == "promoting Western-originating approaches"

    def test_non_hyphenated_lines_join_with_space(self) -> None:
        blocks = [
            _block("ordinary line one", 42.5, 100.0, 200.0, 110.0, 0),
            _block("ordinary line two", 42.5, 112.0, 220.0, 122.0, 1),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert paragraphs[0].text == "ordinary line one ordinary line two"


class TestBug2ParagraphJoining:
    def test_lines_in_same_pymupdf_block_join_into_one_paragraph(self) -> None:
        blocks = [
            _block("Line one of paragraph", 42.5, 100.0, 200.0, 110.0, 0, source_block_index=0),
            _block("line two of paragraph", 42.5, 112.0, 220.0, 122.0, 1, source_block_index=0),
            _block("line three of paragraph", 42.5, 124.0, 210.0, 134.0, 2, source_block_index=0),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert len(paragraphs) == 1
        assert paragraphs[0].text == "Line one of paragraph line two of paragraph line three of paragraph"

    def test_different_source_block_index_starts_new_paragraph(self) -> None:
        blocks = [
            _block("First paragraph line", 42.5, 100.0, 200.0, 110.0, 0, source_block_index=0),
            _block("Second paragraph line", 42.5, 130.0, 220.0, 140.0, 1, source_block_index=1),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert len(paragraphs) == 2
        assert paragraphs[0].text == "First paragraph line"
        assert paragraphs[1].text == "Second paragraph line"

    def test_large_vertical_gap_within_same_block_still_splits(self) -> None:
        # Safety-net fallback: PyMuPDF sometimes lumps two real
        # paragraphs into one block - a gap far larger than the run's
        # own median line height must still force a paragraph break.
        blocks = [
            _block("First paragraph line one", 42.5, 100.0, 200.0, 110.0, 0, source_block_index=0),
            _block("first paragraph line two", 42.5, 112.0, 220.0, 122.0, 1, source_block_index=0),
            # large gap here (a blank-line-equivalent space), same block index
            _block("Second paragraph entirely", 42.5, 160.0, 220.0, 170.0, 2, source_block_index=0),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert len(paragraphs) == 2
        assert paragraphs[1].text == "Second paragraph entirely"

    def test_unknown_source_block_index_falls_back_to_gap_heuristic(self) -> None:
        blocks = [
            _block("Line one", 42.5, 100.0, 200.0, 110.0, 0, source_block_index=None),
            _block("line two close by", 42.5, 112.0, 220.0, 122.0, 1, source_block_index=None),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert len(paragraphs) == 1
        assert paragraphs[0].text == "Line one line two close by"

    def test_single_block_produces_single_paragraph(self) -> None:
        blocks = [_block("Only line", 42.5, 100.0, 200.0, 110.0, 0)]
        paragraphs = group_into_paragraphs(blocks)
        assert len(paragraphs) == 1
        assert paragraphs[0].text == "Only line"


class TestProvenanceAndOrdering:
    def test_paragraph_records_contributing_source_orders(self) -> None:
        blocks = [
            _block("Line one", 42.5, 100.0, 200.0, 110.0, 5, source_block_index=0),
            _block("line two", 42.5, 112.0, 220.0, 122.0, 6, source_block_index=0),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert paragraphs[0].source_orders == [5, 6]

    def test_paragraph_bbox_is_union_of_contributing_lines(self) -> None:
        # x0 deliberately differs slightly (42.5 vs 44.0) to exercise
        # real min()/max() union arithmetic, but stays well under
        # _FIRST_LINE_INDENT_PT (4.0) - this fixture is testing bbox
        # math, not paragraph-boundary indent detection, and a larger
        # gap here would now correctly be classified as a new paragraph
        # by the indent signal added for the under-fragmentation fix.
        blocks = [
            _block("Line one", 42.5, 100.0, 200.0, 110.0, 0, source_block_index=0),
            _block("line two", 44.0, 112.0, 220.0, 122.0, 1, source_block_index=0),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert len(paragraphs) == 1
        bbox = paragraphs[0].bbox
        assert bbox.x0 == 42.5
        assert bbox.y0 == 100.0
        assert bbox.x1 == 220.0
        assert bbox.y1 == 122.0

    def test_output_order_matches_input_order(self) -> None:
        blocks = [
            _block("Alpha paragraph", 42.5, 100.0, 200.0, 110.0, 0, source_block_index=0),
            _block("Beta paragraph", 42.5, 140.0, 200.0, 150.0, 1, source_block_index=1),
            _block("Gamma paragraph", 42.5, 180.0, 200.0, 190.0, 2, source_block_index=2),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert [p.text for p in paragraphs] == ["Alpha paragraph", "Beta paragraph", "Gamma paragraph"]


class TestOverlapGuardCalibration:
    """feature_010 - see samples/regressions/audit_multicolumn_reading_order/
    notes_md/noe_paragraph_fragmentation_audit.md for the full audit this
    implements. The multi-column safety guard in _starts_new_paragraph
    (paragraph_grouper.py) previously treated *any* line.bbox.y0 <
    previous.bbox.y1 as proof of a column boundary - correct for a real
    column switch, but wrong for ordinary same-column line-wraps whose
    bbox vertical extents overlap by a font-metric artifact of a few
    points. These fixtures use real geometry measured directly from the
    benchmark corpus (Nature of Enquiry physical page 1/10, Brinkman page
    6) - not invented numbers."""

    def test_real_noe_overlap_does_not_split_ordinary_line_wrap(self) -> None:
        # Real bbox values, Nature of Enquiry physical page 1 (see audit
        # Appendix A) - two consecutive body lines overlap by 1.48pt,
        # purely a font-metric artifact of this PDF's producer (iLovePDF).
        # This was previously split into 2 paragraphs; must now be 1.
        blocks = [
            _block(
                "planning and conduct of research as though one were",
                53.53, 300.36, 267.85, 312.84, 0, source_block_index=3,
            ),
            _block(
                "reading a recipe for baking a cake. Nor is the planning",
                53.53, 311.36, 267.85, 323.84, 1, source_block_index=3,
            ),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert len(paragraphs) == 1
        assert paragraphs[0].text == (
            "planning and conduct of research as though one were reading a "
            "recipe for baking a cake. Nor is the planning"
        )

    def test_real_brinkman_overlap_does_not_split_ordinary_line_wrap(self) -> None:
        # Geometry from the Brinkman regression PDF (bug_001/bug_005) page
        # 2 - a small (~1pt) overlap, the same false-positive class as
        # NoE's measured-2.42pt cases but on a different PDF producer
        # (Adobe LiveCycle PDFG ES), confirming the calibration is not
        # specific to one font.
        blocks = [
            _block(
                "active participation . . . [and] plans learning in keeping with children's psychological",
                72.0, 200.0, 500.0, 212.0, 0, source_block_index=0,
            ),
            _block(
                "development and interests' (NCF, 2005: 13).",
                72.0, 211.0, 300.0, 223.0, 1, source_block_index=0,
            ),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert len(paragraphs) == 1

    def test_genuine_column_switch_overlap_still_splits(self) -> None:
        # Real bbox magnitude class, Nature of Enquiry physical page 8 -
        # left column's last line (y1=632.2) followed by right column's
        # first line (y0=47.7): a 584.5pt overlap. The guard must still
        # treat this as a paragraph/column boundary - the fix narrows the
        # guard's trigger, it must not disable it.
        blocks = [
            _block(
                "empiricism. Indeed he notes that ethnographers and",
                32.3, 619.8, 246.5, 632.2, 0, source_block_index=4,
            ),
            _block(
                "discourse analysts rely on careful observational data",
                258.3, 47.7, 472.6, 60.2, 1, source_block_index=5,
            ),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert len(paragraphs) == 2

    def test_table_cell_overlap_above_threshold_still_splits(self) -> None:
        # Real bbox magnitude class, Brinkman page 6 (Table 1 cell-to-cell
        # transition): an 8.97pt overlap between two stacked table cells
        # in the same x-range. Above the calibrated floor - must still
        # split, even though it is same-column (the guard's threshold is
        # magnitude-based, not x-position-based - see the audit for why a
        # pure x-disjoint check would have wrongly let this merge).
        blocks = [
            _block("Low-LCE belief score", 53.5, 405.0, 150.0, 414.0, 0, source_block_index=0),
            _block("14", 53.5, 405.03, 70.0, 423.0, 1, source_block_index=1),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert len(paragraphs) == 2

    def test_overlap_just_below_floor_does_not_split(self) -> None:
        # Synthetic boundary-value check: overlap of exactly
        # _OVERLAP_GUARD_MIN_PT - epsilon must not trigger the guard.
        blocks = [
            _block("First line of one paragraph", 42.5, 100.0, 200.0, 112.0, 0, source_block_index=0),
            _block("continues here without a break", 42.5, 108.1, 220.0, 120.1, 1, source_block_index=0),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert len(paragraphs) == 1

    def test_overlap_just_above_floor_does_split(self) -> None:
        # Synthetic boundary-value check: overlap of exactly
        # _OVERLAP_GUARD_MIN_PT + epsilon must still trigger the guard.
        blocks = [
            _block("First paragraph entirely", 42.5, 100.0, 200.0, 112.0, 0, source_block_index=0),
            _block("Unrelated next paragraph", 42.5, 107.9, 220.0, 119.9, 1, source_block_index=0),
        ]
        paragraphs = group_into_paragraphs(blocks)
        assert len(paragraphs) == 2
