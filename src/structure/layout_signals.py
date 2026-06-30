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

from typing import Optional, Tuple

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
