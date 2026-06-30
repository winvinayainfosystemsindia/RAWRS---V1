"""Paragraph reconstruction for RAWRS (Option B - see
samples/regressions/bug_001_brinkman_word_splitting/notes_md/
paragraph_reconstruction_design_review.md and root_cause_audit.md for
the full design/evidence this implements).

Fixes two independent, previously-confirmed bugs with one
geometry-grounded mechanism built on data src/structure/structure_detector.py
(Phase H) already extracts and already persists on TextBlock - no new
PDF reads, no new external dependency:

* Bug 1 (extraction-level): PyMuPDF's own line-clustering occasionally
  mis-segments one visually-continuous, fully-justified line into
  several separate TextBlocks sharing the same baseline (identical
  bbox y0/y1) with no PyMuPDF-emitted space between them.
  ``_merge_same_baseline_fragments`` re-joins these before anything
  else runs.
* Bug 2 (rendering-level): src/markdown/markdown_builder.py previously
  rendered every TextBlock/line as its own markdown paragraph, with no
  logic anywhere to merge PDF line-wraps back into continuous prose.
  ``group_into_paragraphs`` (the public entry point) joins consecutive
  same-paragraph lines using a first-line-indent signal and PyMuPDF's
  own block boundaries (TextBlock.source_block_index) as corroborating
  signals, falling back to a vertical-gap heuristic for the (expected)
  cases where one PyMuPDF block contains more than one real paragraph.
  A later paragraph-fidelity audit found and fixed two further defects
  in this same mechanism, calibrated directly against the benchmark
  corpus and the Brinkman regression PDF: trusting a block-index change
  *unconditionally*
  misclassified every line-wrap as a paragraph break for PDF producers
  that segment one PyMuPDF block per visual line (over-fragmentation);
  and indent-only paragraph starts (no enlarged gap, no block-index
  change) were missed entirely (under-fragmentation) - confirmed in
  three independent PDF producers, including two previously-undetected
  cases within Brinkman itself. See ``_starts_new_paragraph``'s
  docstring and the module-level constants below for the calibration
  evidence.

Deliberately NOT done here, per the approved Option B scope: no
mutation of Document.blocks (src/footnotes/footnote_detector.py and any
other existing consumer keep reading exactly what they always have),
no new pipeline stage, no multi-column/table/equation handling - this
is paragraph reconstruction only. Two independent multi-column safety
guards exist: the same-baseline merge step requires x-continuity and a
bounded gap (so it never fuses two columns into one line), and the
paragraph-join step separately refuses to join any two lines whose
y-ranges overlap or coincide once that merge step is done (so two
columns whose lines happen to share a y-coordinate without being
fragments of the same line still can't be joined into one paragraph).
Neither guard is exercised by any PDF in the current benchmark/
regression corpus (none is genuinely multi-column at the points this
module runs), so both are reasoned-about, unit-tested protections, not
field-validated ones.
"""

from typing import List, Optional, Sequence

from src.models.contracts import BoundingBox, Paragraph, TextBlock

# Two lines are "the same baseline" (Bug 1's fragmentation signature)
# when their bbox y0/y1 differ by no more than this many PDF points -
# generous enough to absorb ordinary floating-point/rendering jitter
# between spans PyMuPDF itself considers co-linear, far tighter than
# any real distinct line's height.
_SAME_BASELINE_Y_TOLERANCE_PT = 1.0

# Maximum horizontal gap between two same-baseline fragments to still
# treat them as one visually-continuous line. The single confirmed Bug
# 1 case measures a ~9pt gap (justified-text word-spacing with no
# PyMuPDF-emitted space glyph between fragments - see
# root_cause_audit.md's Evidence section); this stays well above that
# with headroom for other fonts/sizes, while remaining well under
# typical multi-column gutter widths (commonly 30-50pt+ in academic
# two-column layouts), so it does not, by itself, bridge two columns.
_MAX_FRAGMENT_GAP_PT = 25.0

# A vertical gap between consecutive lines exceeding this multiple of
# the run's own median line height signals a real paragraph break, not
# just ordinary line-wrap spacing - the same self-calibrating ratio
# src/validation/validator.py's PAGE_003 reading-order check already
# uses (_READING_ORDER_JUMP_RATIO), reused here for consistency rather
# than inventing a second threshold convention. Applies when two lines
# share the same PyMuPDF block (or block-index data is unavailable for
# either) - see _CROSS_BLOCK_GAP_RATIO below for the separate, lower
# threshold used when block index actually differs.
_PARAGRAPH_GAP_RATIO = 1.5

# Paragraph_011 fidelity audit (see docs/regressions/.../paragraph
# fidelity investigation): a *different* PyMuPDF block index was
# previously trusted as an unconditional, gap-independent paragraph
# break. Confirmed false for PDF producers that emit one block per
# visual line (e.g. "Teaching as a Professional Discipline" - 619/619
# measured mismatches were exactly this: a block-index change on every
# line, with an ordinary ~0.51x-median-height line-wrap gap, not a
# paragraph gap). A real cross-block paragraph break was directly
# measured at ratio >=0.80 in both the Brinkman regression PDF and in
# this same benchmark PDF's own real paragraph breaks (ratio ~1.09-1.10
# both places); the false (line-wrap) case clusters tightly at ~0.50-
# 0.51 across 173 measured transitions. This threshold sits with
# comfortable margin above every measured false case and below every
# measured true case - calibrated against real geometry, not a guess.
# Deliberately lower than _PARAGRAPH_GAP_RATIO: a block-index change is
# still real corroborating evidence, just not sufficient evidence alone
# for every PDF producer's block-segmentation convention.
_CROSS_BLOCK_GAP_RATIO = 0.7

# A line whose left edge (bbox.x0) sits more than this many PDF points
# to the right of the run's own baseline left margin is a first-line-
# indent paragraph marker, not a continuation line - confirmed via
# direct geometry in three independent PDF producers (Brinkman: 60.2
# vs. 48.2 baseline; Calderhead and Fullan & Hargreaves: 66.0 vs. 54.0
# baseline - all a ~12pt indent), each missed today because the
# existing signals (block index, vertical gap) are both unchanged at
# exactly these missed breaks (same block, ~2pt ordinary line gap).
# Set well below the smallest observed real indent (12pt) and well
# above observed x0 jitter (<0.1pt across hundreds of measured lines).
_FIRST_LINE_INDENT_PT = 4.0

# A run's left-margin baseline (see _baseline_x0 below) is only trusted
# when its most-common rounded x0 is shared by at least this fraction of
# the run's lines. Verification against the Brinkman regression PDF
# found a centered journal-info sidebar where every line has a
# different x0 (centered lines of varying length never share a left
# margin) - its most-repeated value covered only a small minority of
# lines. Real body-text margins measured across the benchmark corpus
# cover roughly 80-90% of a run's lines (indented first lines being the
# minority exception). Set below that real range, comfortably above the
# sidebar's minority share, so centered/no-margin runs correctly yield
# None instead of a spurious baseline.
_BASELINE_X0_MIN_SUPPORT = 0.6

# Minimum overlap magnitude (previous.bbox.y1 - line.bbox.y0) before the
# multi-column safety guard in _starts_new_paragraph treats an overlap as
# proof of a column boundary, rather than as ordinary same-column line-wrap
# noise. Calibrated against real geometry (see
# samples/regressions/audit_multicolumn_reading_order/notes_md/
# noe_paragraph_fragmentation_audit.md): Nature of Enquiry's PDF producer
# (iLovePDF) gives ordinary single-spaced body lines a bbox
# ascender/descender extent ~1.0-1.6pt taller than the actual line pitch,
# producing a tiny overlap on every line transition (false-positive cluster
# measured at <=2.5pt across 2,324 confirmed continuation pairs) that the
# unconditional guard previously treated as a column switch. The smallest
# confirmed genuine break in that same document (a true column-to-column
# transition) measures 5.02pt; cross-validated against the Brinkman
# regression PDF (bug_001/bug_005, a different producer - Adobe LiveCycle
# PDFG ES), whose smallest genuine break (a table-cell-to-table-cell
# transition) measures 8.97pt and whose own 3 false-positive continuation
# pairs measure 2.42-2.48pt. Set with margin above both measured
# false-positive ceilings and with margin below both measured genuine-break
# floors.
_OVERLAP_GUARD_MIN_PT = 4.0


class _MergedLine:
    """One same-baseline-merged line: Bug 1's fix output, Bug 2's input."""

    __slots__ = ("page_number", "text", "bbox", "source_block_index", "source_orders")

    def __init__(
        self,
        page_number: int,
        text: str,
        bbox: BoundingBox,
        source_block_index: Optional[int],
        source_orders: List[int],
    ) -> None:
        self.page_number = page_number
        self.text = text
        self.bbox = bbox
        self.source_block_index = source_block_index
        self.source_orders = source_orders


def group_into_paragraphs(blocks: Sequence[TextBlock]) -> List[Paragraph]:
    """Reconstruct paragraphs from a run of TextBlocks, in order.

    Args:
        blocks: TextBlocks to group, assumed already in the order they
            should render in (e.g. a contiguous, order-sorted run of
            one page's plain-body lines). Not required to be a whole
            page - src/markdown/markdown_builder.py calls this once per
            uninterrupted run of body lines between headings/footnote
            events, which is exactly the granularity this function
            expects.

    Returns:
        Paragraphs in the same relative order as the input, each
        merging same-baseline fragments (Bug 1) and joining
        line-wrapped lines within one paragraph (Bug 2). Empty input
        yields an empty list. Never reorders anything - paragraph
        boundaries are inserted into the existing sequence, never
        computed by re-sorting it.
    """
    if not blocks:
        return []

    merged_lines = _merge_same_baseline_fragments(blocks)
    return _join_into_paragraphs(merged_lines)


def _merge_same_baseline_fragments(blocks: Sequence[TextBlock]) -> List[_MergedLine]:
    """Bug 1 fix: re-join PyMuPDF line-segmentation fragments that share
    a baseline (see module docstring for the mechanism this addresses).
    """
    merged: List[_MergedLine] = []
    current: Optional[_MergedLine] = None

    for block in blocks:
        if current is not None and _is_same_baseline_continuation(current, block):
            current.text = _join_with_hyphen_repair(current.text, block.text)
            current.bbox = _union_bbox(current.bbox, block.bbox)
            current.source_orders.append(block.order)
            continue

        if current is not None:
            merged.append(current)
        current = _MergedLine(
            page_number=block.page_number,
            text=block.text,
            bbox=block.bbox,
            source_block_index=block.source_block_index,
            source_orders=[block.order],
        )

    if current is not None:
        merged.append(current)

    return merged


def _is_same_baseline_continuation(current: _MergedLine, candidate: TextBlock) -> bool:
    """True when ``candidate`` is the next fragment of ``current``'s
    line: same baseline (bbox y0/y1 within tolerance) and immediately
    to its right (non-overlapping, gap within the bounded maximum) -
    both conditions required, so a same-y but far-away or
    overlapping/leftward block (e.g. a genuinely different column) is
    never merged.
    """
    same_top = abs(candidate.bbox.y0 - current.bbox.y0) <= _SAME_BASELINE_Y_TOLERANCE_PT
    same_bottom = abs(candidate.bbox.y1 - current.bbox.y1) <= _SAME_BASELINE_Y_TOLERANCE_PT
    if not (same_top and same_bottom):
        return False

    gap = candidate.bbox.x0 - current.bbox.x1
    return 0.0 <= gap <= _MAX_FRAGMENT_GAP_PT


def _join_into_paragraphs(lines: List[_MergedLine]) -> List[Paragraph]:
    """Bug 2 fix: join consecutive lines belonging to the same paragraph.

    Three signals, in priority order: (1) a first-line indent relative
    to the run's own baseline left margin always starts a new paragraph,
    independent of block index or gap - the signal a paragraph-fidelity
    audit found missing for PDF producers that mark paragraph starts by
    indentation alone, with no enlarged gap and no block-index change
    (Calderhead, Fullan & Hargreaves, and two previously-undetected
    cases within this same Brinkman PDF); (2) PyMuPDF's own block
    boundary (TextBlock.source_block_index changing) is corroborating,
    not conclusive, evidence of a break - it is weighed against the
    vertical gap using a lower threshold (_CROSS_BLOCK_GAP_RATIO) than a
    same-block gap needs, since some PDF producers segment one block per
    visual line and a same-audit finding showed trusting a block change
    alone misclassifies every ordinary line-wrap as a paragraph break for
    those producers; (3) even within the same PyMuPDF block, a vertical
    gap larger than _PARAGRAPH_GAP_RATIO times the run's own median line
    height still starts a new paragraph, for the documented case where
    PyMuPDF's block segmentation lumps more than one real paragraph
    together. A line with source_block_index=None (no PyMuPDF block
    signal available) is treated as same-block for threshold purposes.
    """
    if not lines:
        return []

    median_height = _median_line_height(lines)
    baseline_x0 = _baseline_x0(lines)
    paragraphs: List[Paragraph] = []
    current_group: List[_MergedLine] = [lines[0]]

    for previous, line in zip(lines, lines[1:]):
        if _starts_new_paragraph(previous, line, median_height, baseline_x0):
            paragraphs.append(_build_paragraph(current_group))
            current_group = [line]
        else:
            current_group.append(line)

    paragraphs.append(_build_paragraph(current_group))
    return paragraphs


def _starts_new_paragraph(
    previous: _MergedLine, line: _MergedLine, median_height: float, baseline_x0: Optional[float]
) -> bool:
    # _merge_same_baseline_fragments already fused every genuine
    # same-baseline continuation into one _MergedLine - two _MergedLine
    # instances reaching this point are, by construction, no longer
    # candidates for that. If this line's top edge sits far enough above
    # the previous line's bottom edge, that is not normal top-to-bottom
    # flow - e.g. two genuinely different columns whose lines happen to
    # coincide in y. Always break rather than risk a cross-column merge,
    # regardless of source_block_index, indent, or gap size. The overlap
    # must exceed _OVERLAP_GUARD_MIN_PT (not just be positive) before this
    # fires - see that constant's docstring for the calibration evidence
    # showing ordinary same-column line-wrap leading produces a small,
    # nonzero overlap of its own for some PDF producers, well below every
    # measured genuine column/structural break.
    if line.bbox.y0 < previous.bbox.y1 - _OVERLAP_GUARD_MIN_PT:
        return True

    # First-line indent: fires only on the *transition* from a
    # baseline-margin line into an indented one - not on absolute
    # distance from the baseline alone. Two real false-positive cases
    # found during verification needed this distinction: a centered
    # journal-info sidebar (every line's x0 differs from every other
    # line's, since centered lines of different lengths have different
    # left edges - none of that is indentation) and a block-quote where
    # *every* line, including continuation lines, sits at the indented
    # x0 (only the transition into the quote is a real paragraph-like
    # break; the quote's own continuation lines are not new paragraphs
    # relative to each other). Requiring the previous line to already
    # be at the baseline correctly excludes both: the sidebar has no
    # reliable baseline at all (see _baseline_x0), and the quote's
    # continuation lines never have a baseline-margin predecessor.
    if (
        baseline_x0 is not None
        and abs(previous.bbox.x0 - baseline_x0) <= _FIRST_LINE_INDENT_PT
        and (line.bbox.x0 - baseline_x0) > _FIRST_LINE_INDENT_PT
    ):
        return True

    different_block = (
        previous.source_block_index is not None
        and line.source_block_index is not None
        and previous.source_block_index != line.source_block_index
    )

    if median_height <= 0:
        # No gap signal available at all - block index, if known to
        # differ, is the only remaining evidence.
        return different_block

    gap = line.bbox.y0 - previous.bbox.y1
    gap_ratio = _CROSS_BLOCK_GAP_RATIO if different_block else _PARAGRAPH_GAP_RATIO
    return gap > median_height * gap_ratio


def _baseline_x0(lines: List[_MergedLine]) -> Optional[float]:
    """The run's left-margin baseline, if one reliably exists.

    The minimum bbox.x0 across the run is *not* used directly - a
    false-positive found during verification showed why: a centered
    journal-info sidebar has a different x0 on every line (centered
    lines of different lengths have different left edges), so its
    minimum is just whichever line happened to be longest, not a real
    margin. Instead, this rounds every line's x0 to the nearest whole
    point (absorbing sub-point rendering jitter - confirmed stable to
    within 0.1pt in every real margin measured) and returns the most
    common value, but only when it is shared by a clear majority of the
    run's lines - the same real margin measurements that motivated this
    function showed the true body margin accounts for roughly 80-90% of
    a run's lines (the rest being indented paragraph starts), while the
    centered sidebar's most-repeated rounded value accounted for a small
    minority. Returns None - "no reliable baseline" - when no value
    reaches that majority, which correctly disables the indent signal
    for that run rather than risk measuring noise as indentation.
    """
    if not lines:
        return None

    counts: dict = {}
    for line in lines:
        key = round(line.bbox.x0)
        counts[key] = counts.get(key, 0) + 1

    mode_x0, mode_count = max(counts.items(), key=lambda item: item[1])
    if mode_count / len(lines) < _BASELINE_X0_MIN_SUPPORT:
        return None
    return float(mode_x0)


def _median_line_height(lines: List[_MergedLine]) -> float:
    heights = [line.bbox.y1 - line.bbox.y0 for line in lines if line.bbox.y1 > line.bbox.y0]
    if not heights:
        return 0.0
    ordered = sorted(heights)
    count = len(ordered)
    midpoint = count // 2
    if count % 2 == 0:
        return (ordered[midpoint - 1] + ordered[midpoint]) / 2
    return ordered[midpoint]


def _build_paragraph(group: List[_MergedLine]) -> Paragraph:
    text = group[0].text
    bbox = group[0].bbox
    source_orders: List[int] = list(group[0].source_orders)
    for line in group[1:]:
        text = _join_with_hyphen_repair(text, line.text)
        bbox = _union_bbox(bbox, line.bbox)
        source_orders.extend(line.source_orders)

    return Paragraph(
        page_number=group[0].page_number,
        text=text,
        bbox=bbox,
        source_orders=source_orders,
    )


def _join_with_hyphen_repair(previous_text: str, next_text: str) -> str:
    """Join two adjacent text spans (same-baseline fragments, or two
    line-wrapped lines within one paragraph - the same operation at two
    granularities).

    A trailing hyphen is treated as a line-wrap break for a hyphenated
    word and joined directly with no space (e.g. "Western-" +
    "originating" -> "Western-originating", matching this corpus's own
    expected_md). Otherwise joined with a single space - PyMuPDF
    strips the literal space glyph when it segments text into separate
    lines/fragments, so it must be reintroduced here, never assumed
    present in either span's own text.

    Known simplification: this cannot distinguish a genuine line-wrap
    hyphen from a literal trailing hyphen/dash that was not meant to
    fuse with the next span - no case in the current benchmark/
    regression corpus exercises that distinction.
    """
    if previous_text.endswith("-"):
        return previous_text + next_text
    return f"{previous_text} {next_text}"


def _union_bbox(first: BoundingBox, second: BoundingBox) -> BoundingBox:
    return BoundingBox(
        x0=min(first.x0, second.x0),
        y0=min(first.y0, second.y0),
        x1=max(first.x1, second.x1),
        y1=max(first.y1, second.y1),
    )
