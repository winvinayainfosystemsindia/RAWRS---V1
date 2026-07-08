"""Page label resolver (FEATURE_018).

Turns each page's detected Page.printed_label plus any reviewer-defined
Document.page_label_sections into the final Page.page_label that
Markdown/DOCX generation actually render. This is the one place that
final-label precedence is decided:

    1. A manual per-page override (page_label_status == OVERRIDDEN) always
       wins and is left untouched.
    2. Otherwise, the first PageLabelSection covering this page number
       wins (start_page <= page_number <= end_page); its style/start_number/
       prefix/suffix compute the label, and status becomes APPROVED.
    3. Otherwise, fall back to the page's detected printed_label (or None),
       and status stays DETECTED.

Called once by src/structure/structure_detector.py right after it detects
every page's printed_label (initial auto-population - page_label_sections
is empty at that point, so every page falls through to step 3, identical
to pre-FEATURE_018 behavior), and again by src/api/routes.py whenever a
reviewer edits document.page_label_sections.
"""

from __future__ import annotations

from typing import List, Optional

from src.models.document import Document
from src.models.page import Page, PageLabelSection, PageLabelStatus, PageLabelStyle

_ROMAN_VALUES = [
    (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
    (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
    (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
]


def _to_roman(n: int) -> str:
    """Convert a positive integer to lowercase roman numeral text."""
    if n <= 0:
        return str(n)  # roman numerals have no zero/negative representation
    result = []
    remaining = n
    for value, symbol in _ROMAN_VALUES:
        count, remaining = divmod(remaining, value)
        result.append(symbol * count)
    return "".join(result)


def format_number(n: int, style: PageLabelStyle) -> Optional[str]:
    """Render one page's numeric position under a PageLabelSection's style.

    Returns None for PageLabelStyle.NONE (no label on this page at all -
    e.g. a blank/cover page intentionally left unnumbered).
    """
    if style == PageLabelStyle.NONE:
        return None
    if style == PageLabelStyle.ROMAN_LOWER:
        return _to_roman(n)
    if style == PageLabelStyle.ROMAN_UPPER:
        return _to_roman(n).upper()
    return str(n)  # ARABIC


def _find_section(sections: List[PageLabelSection], page_number: int) -> Optional[PageLabelSection]:
    for section in sections:
        if section.start_page <= page_number <= section.end_page:
            return section
    return None


def _resolve_page(page: Page, sections: List[PageLabelSection]) -> Optional[str]:
    if page.page_label_status == PageLabelStatus.OVERRIDDEN:
        return page.page_label  # manual value always wins, left untouched

    section = _find_section(sections, page.page_number)
    if section is not None:
        number_text = format_number(
            section.start_number + (page.page_number - section.start_page), section.style
        )
        page.page_label_status = PageLabelStatus.APPROVED
        if number_text is None:
            return None
        return f"{section.prefix}{number_text}{section.suffix}"

    page.page_label_status = PageLabelStatus.DETECTED
    return page.printed_label


def resolve_page_labels(document: Document) -> List[int]:
    """Recompute page_label for every page. Returns the page_numbers whose
    final label actually changed, so callers can build correction-history
    entries only for pages a reviewer action genuinely affected."""
    changed: List[int] = []
    for page in document.pages:
        previous = page.page_label
        page.page_label = _resolve_page(page, document.page_label_sections)
        if page.page_label != previous:
            changed.append(page.page_number)
    return changed
