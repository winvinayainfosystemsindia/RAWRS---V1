"""Generic visual-object caption finder for RAWRS.

Locates caption text for a detected region (table, figure, equation, or
any other visual object) by scanning the PDF page's text spans in a
vertical band immediately above the object's bounding box.

This is intentionally a standalone utility, not a TableDetector, because
the same logic applies to tables, figures, and future object types. It
returns a (caption_text, evidence_score) pair so callers can add the
evidence signal to whichever EvidenceBundle they maintain.

Caption detection heuristics (in order of confidence):
  1. "Table N" / "Figure N" / "Box N" pattern  →  score 1.0
  2. Short all-caps line (e.g. "SURVEY RESULTS")  →  score 0.8
  3. Short standalone line that ends with "."  →  score 0.6
  4. Any short standalone line  →  score 0.4

"Short" means the line spans < 80% of the page width and has ≤ 25 words.
The search window is 5–50pt above the candidate region's top edge.
If multiple candidate lines are found, the one closest to the region wins.
If no candidate is found, returns (None, 0.0).
"""

import re
from typing import Optional, Tuple


# Patterns that strongly suggest a label line rather than body text.
_LABEL_PATTERN = re.compile(
    r"^(Table|Figure|Fig\.|Box|Chart|Diagram|Exhibit|Appendix|Scheme)\s*\d*[.:]?\s*",
    re.IGNORECASE,
)

# Minimum score for a candidate to be accepted as a caption.
# Score 0.4 ("any short standalone line") is too permissive: it matches
# journal running headers, page numbers, and kicker labels that appear within
# the search window but are not actual captions. Require at least 0.6
# (ends-with-period line or all-caps label or explicit Table/Figure label).
_MIN_CAPTION_SCORE = 0.6


def find_caption(
    page_dict: dict,
    region_bbox: tuple,
    page_width: float,
    search_above_pt: float = 50.0,
    min_above_pt: float = 2.0,
) -> Tuple[Optional[str], float]:
    """Find a caption line above a detected region.

    Args:
        page_dict:       PyMuPDF get_text("dict") result for the page.
        region_bbox:     (x0, y0, x1, y1) of the detected region.
        page_width:      Page width in points (for "short" check).
        search_above_pt: How far above the region to search.
        min_above_pt:    Minimum gap (to skip lines that are inside
                         the region due to coordinate rounding).

    Returns:
        (caption_text, confidence_score) where:
            caption_text is None if nothing found.
            confidence_score is 0.0 if nothing found, else 0.4–1.0.
    """
    _, region_top, _, _ = region_bbox
    search_top = region_top - search_above_pt
    search_bottom = region_top - min_above_pt

    candidates: list = []

    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            line_bbox = line.get("bbox", (0, 0, 0, 0))
            lx0, ly0, lx1, ly1 = line_bbox
            line_mid_y = (ly0 + ly1) / 2

            if not (search_top <= line_mid_y <= search_bottom):
                continue

            text = " ".join(
                span.get("text", "").strip()
                for span in line.get("spans", [])
            ).strip()
            if not text:
                continue

            line_width = lx1 - lx0
            word_count = len(text.split())

            if line_width > 0.8 * page_width or word_count > 25:
                continue

            score = _score_candidate(text)
            if score >= _MIN_CAPTION_SCORE:
                candidates.append((line_mid_y, text, score))

    if not candidates:
        return None, 0.0

    candidates.sort(key=lambda c: -c[0])
    _, caption_text, score = candidates[0]
    return caption_text, score


def _score_candidate(text: str) -> float:
    """Score a candidate caption line 0.0 (not a caption) to 1.0 (strong)."""
    if not text:
        return 0.0

    # Bare numbers (page numbers, figure numbers alone) are never captions.
    # digits-only: "350", "26", "2015" etc. — reject early.
    if not any(c.isalpha() for c in text):
        return 0.0

    if _LABEL_PATTERN.match(text):
        return 1.0

    if text == text.upper() and len(text.split()) <= 8:
        return 0.8

    if text.endswith(".") and len(text.split()) <= 20:
        return 0.6

    if len(text.split()) <= 15:
        return 0.4

    return 0.0
