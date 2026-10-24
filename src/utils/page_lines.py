"""Finding the page line each layout item became.

Shared by the scanned-page passes (src/ocr/scan_structure.py,
src/images/image_extractor.py) and the markdown projection, which may not
import a decision package (invariant AI-2).
"""

import re
from typing import List, Optional, Sequence

# Docling's text export prefixes a list item with its marker ("- Will the
# question hold my interest?"); the layout item's own text has none.
_LIST_MARKER = re.compile(r"^(?:[-•*]|\d{1,3}[.)])\s+")


def page_text_lines(text: Optional[str]) -> List[str]:
    """A page text's non-blank lines, stripped - what Callout line numbers
    count and what headings are matched against."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def layout_line_indices(items: Sequence, lines: Sequence[str]) -> List[Optional[int]]:
    """Each layout item's position among ``lines``, matched in reading order:
    the first line at or after the previous match that equals the item's text,
    with or without a list marker. Matching in order keeps a short line that
    repeats on the page ("Yes", a heading) tied to its own occurrence. None
    for furniture, pictures, items without text, and text no later line has
    (a line the OCR re-read has since corrected)."""
    indices: List[Optional[int]] = []
    cursor = 0
    for item in items:
        text = item.text.strip()
        found = None
        if text and not item.furniture and item.label != "picture":
            for index in range(cursor, len(lines)):
                if lines[index] == text or _LIST_MARKER.sub("", lines[index]) == text:
                    found = index
                    break
        indices.append(found)
        if found is not None:
            cursor = found + 1
    return indices
