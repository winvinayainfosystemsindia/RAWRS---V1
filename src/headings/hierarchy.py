"""Make a document's headings an outline a reader can navigate.

Sources that know a page's typography (a born-digital PDF) give RAWRS
headings at real levels. Two sources do not: Mathpix's Markdown-flavoured MMD
writes every heading as ``##``, and Docling's OCR labels every section header
level 1. Measured on O'Leary's chapter, both produced 34 headings all at one
level, including four that are not headings at all:

* ``3`` - the chapter number, printed on its own line above the title;
* ``'I know the general area ... but I'm not quite sure...'`` - the epigraph;
* ``-Albert Szent-Gvorgi`` - a quotation's attribution;
* ``✓ Is the question right for you?`` / ``- Is the question right ...`` -
  real headings, but carrying the list glyph they were printed with.

``repair_headings`` fixes those in place, for every input route:

1. a heading that is really a quotation or an attribution becomes a paragraph
   (its text is kept, never dropped);
2. a leading list glyph is stripped from a heading's text;
3. a heading that is only a chapter number is merged into the title that
   follows it (``3 - Developing Your Research Question``);
4. when every heading shares one level, a hierarchy is inferred: the first
   heading is the title (H1), headings set in capitals are sections (H2), and
   the rest are sub-sections (H3) - the convention of the textbooks in the
   corpus, and what the remediation checklist's heading table describes.
"""

import re
from typing import List

from loguru import logger

from src.models.contracts import Document, Heading, HeadingLevel, Paragraph

# A heading this long that ends like a sentence is prose that was set large.
_MAX_HEADING_WORDS_FOR_A_SENTENCE = 8
_QUOTE_OPENERS = "'\"‘“"
_ATTRIBUTION = re.compile(r"^[-–—]\s*[A-Z][\w.'’-]+(?:\s+[A-Z][\w.'’-]+){0,4}\s*$")
_LEADING_GLYPH = re.compile(r"^[✓✔•▪●○–—*-]\s+")
_CHAPTER_NUMBER = re.compile(r"^(?:chapter\s+|unit\s+)?(\d{1,3}|[IVXLC]{1,6})\.?$", re.IGNORECASE)
_MIN_HEADINGS_TO_INFER = 4


def _is_not_a_heading(text: str) -> bool:
    text = text.strip()
    if _ATTRIBUTION.match(text):
        return True
    words = text.split()
    if text[:1] in _QUOTE_OPENERS and len(words) >= 4:
        return True
    return len(words) > _MAX_HEADING_WORDS_FOR_A_SENTENCE and text.endswith((".", "!", "?"))


def _is_capitals(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    return len(letters) >= 3 and sum(ch.isupper() for ch in letters) / len(letters) > 0.85


def repair_headings(document: Document) -> dict:
    """Apply the four repairs; returns counts for the pipeline log."""
    counts = {"demoted": 0, "glyphs": 0, "promoted": 0, "numbers_merged": 0, "levels_inferred": 0}
    kept: List[Heading] = []
    glyph_levels: dict = {}
    for heading in document.headings:
        if heading.is_page_marker:
            kept.append(heading)
            continue
        if _is_not_a_heading(heading.text):
            _keep_as_paragraph(document, heading)
            counts["demoted"] += 1
            continue
        stripped = _LEADING_GLYPH.sub("", heading.text).strip()
        if stripped and stripped != heading.text:
            glyph_levels.setdefault(heading.text.strip()[0], heading.level)
            heading.text = stripped
            counts["glyphs"] += 1
        kept.append(heading)
    counts["promoted"] = _promote_glyph_siblings(document, kept, glyph_levels)

    merged: List[Heading] = []
    for index, heading in enumerate(kept):
        following = next((h for h in kept[index + 1:] if not h.is_page_marker), None)
        if (
            not heading.is_page_marker
            and _CHAPTER_NUMBER.match(heading.text.strip())
            and following is not None
            and following.page_number == heading.page_number
        ):
            following.text = f"{_CHAPTER_NUMBER.match(heading.text.strip()).group(1)} - {following.text}"
            counts["numbers_merged"] += 1
            continue
        merged.append(heading)
    document.headings = sorted(
        merged,
        key=lambda h: (h.page_number, not h.is_page_marker, getattr(h, "source_line", None) or 0),
    )
    for order, heading in enumerate(document.headings):
        heading.document_order = order

    content = [h for h in document.headings if not h.is_page_marker]
    if len(content) >= _MIN_HEADINGS_TO_INFER and len({h.level for h in content}) == 1:
        for position, heading in enumerate(content):
            heading.level = (
                HeadingLevel.H1 if position == 0 else HeadingLevel.H2 if _is_capitals(heading.text) else HeadingLevel.H3
            )
        counts["levels_inferred"] = len(content)
    if any(counts.values()):
        logger.info("Heading repair: {}", counts)
    return counts


def _keep_as_paragraph(document: Document, heading: Heading) -> None:
    """A demoted heading's text stays in the document. On a Mathpix import the
    projection renders paragraphs by source line, so the text becomes a
    Paragraph at the heading's place; on a native page the line is already in
    the page text and simply renders as prose once no heading claims it."""
    source_line = getattr(heading, "source_line", None)
    if source_line is None:
        return
    document.paragraphs.append(
        Paragraph(page_number=heading.page_number, text=heading.text, source_line=source_line)
    )
    document.paragraphs.sort(key=lambda p: (p.page_number, p.source_line if p.source_line is not None else 0))


# A glyph-led paragraph longer than this is a list item or prose, not a
# heading printed with the same mark as its siblings.
_MAX_PROMOTED_HEADING_WORDS = 14


def _promote_glyph_siblings(document: Document, headings: List[Heading], glyph_levels: dict) -> int:
    """Paragraphs printed like headings the source did recognise.

    O'Leary prints its four "good question" tests as "✓ Is the question ...?";
    Mathpix made two of them headings and left two as paragraphs. When a
    document already has headings led by a glyph, a short paragraph led by the
    same glyph is a heading at the same level. Only on imports whose
    paragraphs carry a source line (a native page's lines are its text, and
    stay where they are).
    """
    promoted = 0
    remaining = []
    for paragraph in getattr(document, "paragraphs", []) or []:
        text = (paragraph.text or "").strip()
        glyph = text[:1]
        if (
            glyph in glyph_levels
            and glyph not in "-*–—"  # too common in ordinary text
            and _LEADING_GLYPH.match(text)
            and paragraph.source_line is not None
            and len(text.split()) <= _MAX_PROMOTED_HEADING_WORDS
        ):
            headings.append(
                Heading(
                    level=glyph_levels[glyph],
                    text=_LEADING_GLYPH.sub("", text).strip(),
                    page_number=paragraph.page_number,
                    document_order=len(headings),
                    source="rawrs_recovery",
                    source_line=paragraph.source_line,
                    # Its own name: the default "heading-{document_order}"
                    # would collide with an existing heading's (a page marker's,
                    # measured) and the projection would render it in its place.
                    id=f"heading-recovered-line-{paragraph.source_line}",
                )
            )
            promoted += 1
        else:
            remaining.append(paragraph)
    if promoted:
        document.paragraphs = remaining
    return promoted
