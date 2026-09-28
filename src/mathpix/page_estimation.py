"""Shared MMD-line-to-physical-page estimation.

Used by both the Mathpix ingestor (headings/paragraphs/tables) and the
figure verification asset type (src/verification/figures.py) — factored
out so both have exactly one implementation rather than two copies
drifting apart.
"""

from __future__ import annotations

import math
import re
from bisect import bisect_right
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple, Union

from src.utils.mathpix_crop import crop_box


_FILENAME_PAGE_RE = re.compile(r"-(\d{1,3})_\d+_\d+_\d+_\d+$")
# Height over width of a US Letter / most book pages; only used to turn a
# crop's pixel offset into a fraction of the page.
_PAGE_ASPECT = 792 / 612


def page_from_filename(path: Union[str, Path], page_count: int) -> Optional[int]:
    """The physical page Mathpix's own image filename states, when it states one.

    Mathpix names each extracted image ``{uuid}-{PAGE}_{x}_{y}_{w}_{h}.jpg``,
    and that page token is the physical page the pixels came from (checked
    against PyMuPDF's per-page image list on the corpus: 14 of 17 encoded
    filenames name a page that really carries an image; the other three sit on
    a scan with no image objects to check against). A stem that does not match,
    or a page outside the document, yields None.
    """
    match = _FILENAME_PAGE_RE.search(Path(str(path)).stem)
    if not match:
        return None
    page = int(match.group(1))
    return page if 1 <= page <= page_count else None


def position_from_filename(path: Union[str, Path], page_count: int) -> Optional[float]:
    """Where on its page a Mathpix figure sits, as a page position: 3.2 is a
    fifth of the way down page 4. The render's width is estimated as the crop
    plus a matching margin on each side (text blocks are centred), and its
    height from the page's shape."""
    box = crop_box(path)
    if box is None or not 1 <= box.page <= page_count:
        return None
    page, width, top_y, top_x = box.page, box.width, box.top_y, box.top_x
    page_height_px = (width + 2 * top_x) * _PAGE_ASPECT
    fraction = min(max(top_y / page_height_px, 0.0), 0.95) if page_height_px else 0.5
    return page - 1 + fraction


def _block_text_length(block: Any) -> int:
    """How much text a block puts on its page - the measure of how far through
    the document it sits."""
    parts: List[str] = [getattr(block, "text", None) or ""]
    heading = getattr(block, "heading", None)
    if heading is not None:
        parts.append(heading.text or "")
    table = getattr(block, "table", None)
    if table is not None:
        parts.extend(cell.text or "" for row in table.rows for cell in row)
    figure = getattr(block, "figure", None)
    if figure is not None:
        parts.append(figure.caption or "")
    footnote = getattr(block, "footnote", None)
    if footnote is not None:
        parts.append(getattr(footnote, "body", "") or "")
    return sum(len(part) for part in parts) + 1


class TextPositionPages:
    """Which page an MMD block is on, for an import with no text layer to align
    against (a scanned PDF).

    The old estimate divided a block's MMD *line number* by the *block count*.
    MMD separates blocks with blank lines, so line numbers run about twice the
    block count and every block past the document's midpoint was clamped to
    the last page - measured on O'Leary: 141 characters on page 1, 10,005 on
    page 13, against 1,400-3,200 per page by OCR. Pages were effectively
    skipped and the last one swallowed half the chapter.

    This measures position by the text itself: a block's page is where its
    first character falls in the document's text, spread across the pages -
    which is how a printed page fills. Where Mathpix's image filenames say
    which page a figure is on, those are fixed points and the text between
    them is spread across the pages between them, so one long page cannot
    push everything after it out of place. On O'Leary the four figure pages
    (4, 6, 8, 9) match OCR's own figure captions exactly.
    """

    def __init__(self, blocks: Sequence[Any], page_count: int) -> None:
        self.page_count = max(page_count, 1)
        ordered = sorted(
            (b for b in blocks if getattr(b, "source_line", None) is not None),
            key=lambda b: b.source_line,
        )
        self._lines: List[int] = []
        self._offsets: List[int] = []
        offset = 0
        anchors: List[Tuple[int, float]] = []
        for block in ordered:
            self._lines.append(block.source_line)
            self._offsets.append(offset)
            figure = getattr(block, "figure", None)
            stated = (
                position_from_filename(figure.image_path, self.page_count)
                if figure and figure.image_path
                else None
            )
            if stated is not None:
                anchors.append((offset, stated))
            offset += _block_text_length(block)
        self._total = max(offset, 1)
        self._knots = self._monotone_knots(anchors)

    def _monotone_knots(self, anchors: List[Tuple[int, float]]) -> List[Tuple[int, float]]:
        """(text offset, page position) points from the document's start, through
        every figure anchor that keeps pages in order, to its end. An anchor that
        would send the page count backwards (a floated figure) is dropped."""
        knots: List[Tuple[int, float]] = [(0, 0.0)]
        for offset, position in sorted(anchors):
            if offset > knots[-1][0] and knots[-1][1] <= position < self.page_count:
                knots.append((offset, position))
        knots.append((self._total, float(self.page_count)))
        return knots

    def page(self, source_line: Optional[int]) -> int:
        if source_line is None or not self._lines:
            return self.page_count
        index = max(bisect_right(self._lines, source_line) - 1, 0)
        offset = self._offsets[index]
        for (x0, y0), (x1, y1) in zip(self._knots, self._knots[1:]):
            if offset <= x1:
                position = y0 + (y1 - y0) * ((offset - x0) / max(x1 - x0, 1))
                return max(1, min(math.floor(position) + 1, self.page_count))
        return self.page_count


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
