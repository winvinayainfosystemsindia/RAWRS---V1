"""Shared MMD-line-to-physical-page estimation.

Used by both the Mathpix ingestor (headings/paragraphs/tables) and the
figure verification asset type (src/verification/figures.py) — factored
out so both have exactly one implementation rather than two copies
drifting apart.
"""

from __future__ import annotations

import math


def estimate_page(source_line: int, total_lines: int, page_count: int) -> int:
    """Estimate which physical page a block belongs to.

    Uses proportional position in the MMD line sequence as a proxy for
    position in the physical document. This is an approximation; a later
    phase may refine using DOCX H6 page markers when available.
    """
    if total_lines <= 0 or page_count <= 1:
        return 1
    frac = source_line / total_lines
    page = math.ceil(frac * page_count)
    return max(1, min(page, page_count))
