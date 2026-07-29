"""Shared PDF per-line layout-signal extraction for RAWRS.

Computes (text, font size, is-bold, char count) for one line of
PyMuPDF's ``page.get_text("dict")`` output. Originally lived only in
src/headings/heading_detector.py (Phase B), where it still drives
heading classification unchanged; extracted here in Phase H so
src/structure/structure_detector.py can reuse the exact same signal
for every line on a page, rather than duplicating this logic per
docs/CLAUDE_INSTRUCTIONS.md's "Do not create duplicate data
structures" rule (read broadly to include duplicate extraction logic,
not just duplicate models).
"""

import statistics
from collections import defaultdict
from typing import List, Optional, Tuple

from src.models.text_block import PhysicalZone, RepetitionEvidence, TextBlock

LineLayout = Tuple[float, bool]  # (font size, is_bold)

_BOLD_FONT_FLAG = 16  # PyMuPDF span flags bit 4
# A line's bold status is "true" when a majority of its characters (not
# just any single span) come from a bold-flagged or bold-named font -
# this avoids misclassifying a body sentence that merely contains one
# bold word (inline emphasis) as bold.
_BOLD_MAJORITY_THRESHOLD = 0.5


def line_layout(line_dict: dict) -> Optional[Tuple[str, float, bool, int]]:
    """Aggregate a PyMuPDF dict-mode line's spans into (text, size, is_bold, char_count).

    size is the largest span size on the line; is_bold is true when a
    majority of the line's characters come from a bold span. Returns
    None for a line with no non-blank text.
    """
    spans = line_dict.get("spans", [])
    text = "".join(span["text"] for span in spans).strip()
    if not text:
        return None

    total_chars = sum(len(span["text"]) for span in spans)
    if total_chars == 0:
        return None

    bold_chars = sum(len(span["text"]) for span in spans if span_is_bold(span))
    is_bold = (bold_chars / total_chars) > _BOLD_MAJORITY_THRESHOLD
    size = round(max(span["size"] for span in spans), 1)

    return text, size, is_bold, total_chars


def span_is_bold(span: dict) -> bool:
    font_name = span.get("font", "")
    return "bold" in font_name.lower() or bool(span.get("flags", 0) & _BOLD_FONT_FLAG)


_HEADER_FOOTER_BAND_RATIO = 0.12  # top/bottom fraction of page height treated as header/footer


def assign_physical_zone(y0: float, y1: float, page_height: float) -> PhysicalZone:
    """Classify a line into a vertical physical zone by its bbox centre.

    HEADER when the line's vertical centre falls in the top
    ``_HEADER_FOOTER_BAND_RATIO`` of the page, FOOTER when in the bottom band,
    BODY otherwise. Purely geometric - a calibration knob, not an
    interpretation. Returns BODY on a degenerate (non-positive) page height
    rather than raising.
    """
    if page_height <= 0:
        return PhysicalZone.BODY
    centre = (y0 + y1) / 2
    if centre < page_height * _HEADER_FOOTER_BAND_RATIO:
        return PhysicalZone.HEADER
    if centre > page_height * (1 - _HEADER_FOOTER_BAND_RATIO):
        return PhysicalZone.FOOTER
    return PhysicalZone.BODY


_REPETITION_MIN_PAGES = 2  # a signature must span this many distinct pages to count
_STABILITY_SCALE = 20.0  # pt; positional_stability = scale / (scale + y-centre stdev)


def _repetition_signature(text: str) -> str:
    return " ".join(text.lower().split()).strip()


def annotate_repetition(blocks: List[TextBlock], page_count: int) -> None:
    """Document-wide pass: attach RepetitionEvidence to every block whose
    normalized text recurs across >= _REPETITION_MIN_PAGES distinct pages.

    Mutates ``blocks`` in place and is purely additive - blocks below the
    threshold keep ``repetition = None``. Evidence only: no classification, no
    suppression, no consumer. The reusable, model-attached successor to the
    per-interpreter recurrence heuristics scattered elsewhere (e.g.
    heading_detector's Tier-4 guard), which later stages will converge onto.
    """
    groups: dict = defaultdict(list)
    for block in blocks:
        signature = _repetition_signature(block.text)
        if signature:
            groups[signature].append(block)

    for signature, group in groups.items():
        pages = sorted({block.page_number for block in group})
        if len(pages) < _REPETITION_MIN_PAGES:
            continue
        centres = [(block.bbox.y0 + block.bbox.y1) / 2 for block in group]
        stdev = statistics.pstdev(centres) if len(centres) > 1 else 0.0
        if all(page % 2 == 1 for page in pages):
            alternation = "odd"
        elif all(page % 2 == 0 for page in pages):
            alternation = "even"
        else:
            alternation = None
        evidence = RepetitionEvidence(
            signature=signature,
            recurrence_count=len(group),
            page_numbers=pages,
            recurrence_ratio=round(len(pages) / page_count, 4) if page_count else 0.0,
            positional_stability=round(_STABILITY_SCALE / (_STABILITY_SCALE + stdev), 4),
            alternation=alternation,
        )
        for block in group:
            block.repetition = evidence
