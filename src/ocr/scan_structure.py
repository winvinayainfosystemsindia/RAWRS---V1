"""Structure a scanned page's text cannot carry, read back from its layout.

Docling flattens a scanned page to text plus a list of headings at one level.
Measured against the human-remediated DOCX of the two scanned benchmark
chapters (Bryman ch. 2, O'Leary ch. 3), that loses four things the checklist
asks for; ``apply_scan_structure`` recovers each from ``Page.ocr_layout``
(src/ocr/docling_engine.py) and the page image:

1. **Printed page numbers.** Docling reads them - as furniture it keeps out of
   the text - so every H6 was the PDF position (1..26) instead of the book's
   page (19..43). The numbers found in running headers/footers must agree on
   one offset from the PDF position; a page whose number is missing or misread
   (O'Leary's "39" read as "63") takes the offset, and a misread is flagged.
2. **The chapter number.** Printed large above the title, it is either its own
   text item ("3") or, set in a pale colour, a picture Docling never read
   ("2"). RapidOCR (already Docling's OCR engine) reads that picture. The
   number joins the title line as ``N - Title`` (the checklist's convention).
3. **Boxes.** A shaded or tinted panel (Bryman's "Research in focus", O'Leary's
   "Box 3.1", pull quotes) becomes a ``Callout`` covering exactly the lines
   inside it. Only its first line can be a heading - its title; a section
   header Docling saw further inside is box text.
4. **Heading levels.** Every section header arrives at one level. Their printed
   size does tell main sections from sub-sections: the ascender-to-baseline
   height of the heading's ink, which unlike the full line height does not
   depend on which letters a heading happens to contain. Sorted, the first gap
   of 1.2x or more with at least two headings on either side splits the tiers
   (Bryman: 13.3-15.8 pt above, 9.7-10.1 below, a 1.32x gap; nothing inside a
   tier differs by more than 1.03x). A lone largest heading on the first page
   is the title (H1), the upper tier H2, the lower H3. With no such gap
   (O'Leary, where capitals - not size - mark the sections) the levels are
   left for src/headings/hierarchy.py to infer, exactly as before.

Only pages Docling read are touched; a born-digital page has no layout and
keeps every byte of its output.
"""

import re
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional, Sequence, Set, Tuple

from loguru import logger

from src.headings.hierarchy import _CHAPTER_NUMBER
from src.mathpix.mmd_parser import classify_callout_type
from src.models.contracts import Callout, Document, ExtractionMethod, OCRLayoutItem, Page
from src.structure.page_label_resolver import resolve_page_labels
from src.utils.page_lines import layout_line_indices, page_text_lines

_HEADER_LABELS = ("title", "section_header")
_FOLIO_LABELS = ("page_header", "page_footer")

# --- printed page numbers ---------------------------------------------------
# A folio is a running header/footer that is a number, or starts or ends with
# one ("21 Social research strategies").
_FOLIO_NUMBER = re.compile(r"^(\d{1,4})(?:\s.*)?$|^.*\s(\d{1,4})$")
_PRINTED = 1.0
_INFERRED = 0.5

# --- chapter number -----------------------------------------------------------
# A chapter number set as a picture is a glyph or two, never a figure.
_MAX_NUMBER_PICTURE_PT = 150.0

# --- boxes ----------------------------------------------------------------------
_BOX_DPI = 72  # one pixel per point
# Text strokes are a pixel or two wide at 72 dpi; the max of a 5x5 window
# erases them and leaves the paper or panel behind.
_STROKE_WINDOW = 5
_TINT_CORE = 8  # grey levels below the paper: certainly a panel
_TINT_EDGE = 1  # below the paper at all: the faded side of a gradient panel
_MIN_TINTED_ROW_PT = 60
_MIN_BOX_HEIGHT_PT = 20
_MIN_BOX_WIDTH_PT = 72
_MIN_HORIZONTAL_OVERLAP = 0.5  # of an item's width
_MAX_PICTURE_SHARE = 0.5  # a panel mostly covered by a picture is the figure's

# --- heading levels -------------------------------------------------------------
_MEASURE_DPI = 200
_INK = 140  # grey level below which a pixel is ink
_CORE_SHARE = 0.25  # a row inside the x-height band has this much of the peak ink
_TIER_GAP = 1.2
_MIN_TIER_SIZE = 2


def apply_scan_structure(document: Document) -> Dict[str, int]:
    """Apply the four recoveries to every Docling page; returns counts for the
    pipeline log. Changes nothing when no page carries a Docling layout."""
    pages = [
        page
        for page in document.pages
        if page.extraction_method == ExtractionMethod.DOCLING and page.ocr_layout
    ]
    counts = {"page_labels": 0, "chapter_numbers": 0, "boxes": 0, "headings_tiered": 0}
    if not pages:
        return counts
    counts["page_labels"] = _apply_printed_labels(pages)
    if counts["page_labels"]:
        resolve_page_labels(document)
    pdf = _open_pdf(document.source_pdf_path)
    try:
        counts["chapter_numbers"] = sum(_merge_chapter_number(page, pdf) for page in pages)
        if pdf is not None:
            for page in pages:
                boxes = _detect_boxes(page, pdf[page.page_number - 1], len(document.callouts))
                document.callouts.extend(boxes)
                counts["boxes"] += len(boxes)
            counts["headings_tiered"] = _tier_heading_levels(pages, pdf)
    finally:
        if pdf is not None:
            pdf.close()
    logger.info("Scanned-page structure: {}", counts)
    return counts


def _open_pdf(path: str):
    try:
        import fitz

        return fitz.open(str(Path(path)))
    except Exception as exc:  # the page images are evidence; the text stands without them
        logger.warning("Scanned-page structure cannot open '{}': {}", path, exc)
        return None


def page_lines(page: Page) -> List[str]:
    """The page text's non-blank lines, stripped - what Callout line numbers
    count and what headings are matched against."""
    return page_text_lines(page.cleaned_text)


# ------------------------------------------------------------------ page labels


def _folio_numbers(page: Page) -> List[int]:
    numbers = []
    for item in page.ocr_layout:
        if item.label not in _FOLIO_LABELS:
            continue
        match = _FOLIO_NUMBER.match(item.text.strip())
        if match:
            numbers.append(int(match.group(1) or match.group(2)))
    return numbers


def _apply_printed_labels(pages: List[Page]) -> int:
    """Set printed_label on every page from the one offset its folios agree on.
    Returns the number of pages labelled."""
    folios = {page.page_number: _folio_numbers(page) for page in pages}
    support: Dict[int, int] = {}
    for page_number, numbers in folios.items():
        for offset in {n - page_number for n in numbers}:
            support[offset] = support.get(offset, 0) + 1
    if not support:
        return 0
    offset, votes = max(support.items(), key=lambda kv: (kv[1], -abs(kv[0])))
    pages_with_folios = sum(1 for numbers in folios.values() if numbers)
    if votes < 2 or votes * 2 <= pages_with_folios:
        logger.info("Printed page numbers disagree ({} of {} pages); keeping PDF positions", votes, pages_with_folios)
        return 0
    labelled = 0
    for page in pages:
        expected = page.page_number + offset
        if page.printed_label is not None or expected < 1:
            continue
        numbers = folios[page.page_number]
        page.printed_label = str(expected)
        page.label_confidence = _PRINTED if expected in numbers else _INFERRED
        # A number printed on the page that the sequence contradicts is a
        # misreading or a real anomaly; either way a reviewer looks.
        page.label_conflict = bool(numbers) and expected not in numbers
        labelled += 1
    return labelled


# --------------------------------------------------------------- chapter number


def _merge_chapter_number(page: Page, pdf) -> int:
    """Join a chapter number printed alone above the page's first heading to
    that heading's line. Returns 1 when merged."""
    body = [item for item in page.ocr_layout if not item.furniture]
    if len(body) < 2 or body[1].label not in _HEADER_LABELS:
        return 0
    number_item, title_item = body[0], body[1]
    # Set above the title or beside it, a drop numeral taller than the title
    # (O'Leary's "3" spans 75-165 pt beside a title at 106 pt); never below.
    if number_item.bbox[1] > title_item.bbox[1] + 2:
        return 0
    title = title_item.text.strip()
    found = dict(zip(map(id, body[:2]), layout_line_indices(body[:2], page_lines(page))))
    title_line = found[id(title_item)]
    if title not in page.ocr_heading_levels or title_line is None:
        return 0
    changes: Dict[int, Optional[str]] = {}
    if number_item.label == "picture":
        width = number_item.bbox[2] - number_item.bbox[0]
        height = number_item.bbox[3] - number_item.bbox[1]
        if number_item.children or max(width, height) > _MAX_NUMBER_PICTURE_PT or pdf is None:
            return 0
        reading = _read_picture_text(pdf[page.page_number - 1], number_item.bbox)
    else:
        reading = number_item.text.strip()
        if found[id(number_item)] is None:
            return 0
        changes[found[id(number_item)]] = None
    match = _CHAPTER_NUMBER.match(reading or "")
    if not match:
        return 0
    merged = f"{match.group(1)} - {title}"
    changes[title_line] = merged
    _rewrite_lines(page, changes)
    page.ocr_heading_levels[merged] = page.ocr_heading_levels.pop(title)
    # The layout item now stands for the merged line, so the size and box
    # passes below still find it.
    title_item.text = merged
    logger.info("Page {}: chapter number joined to its title: {!r}", page.page_number, merged)
    return 1


def _rewrite_lines(page: Page, changes: Dict[int, Optional[str]]) -> None:
    """Replace page lines by position among the non-blank lines; a change to
    None drops the line."""
    out: List[str] = []
    ordinal = 0
    for raw in page.cleaned_text.splitlines():
        if not raw.strip():
            out.append(raw)
            continue
        index, ordinal = ordinal, ordinal + 1
        if index in changes:
            if changes[index] is not None:
                out.append(changes[index])
            continue
        out.append(raw)
    page.cleaned_text = "\n".join(out)


_rapid_engine = None


def _read_picture_text(pdf_page, bbox: Sequence[float]) -> Optional[str]:
    """RapidOCR's reading of a small picture, or None when it cannot read it."""
    global _rapid_engine
    try:
        import fitz
        import numpy as np
        from PIL import Image, ImageOps
        from rapidocr import RapidOCR

        if _rapid_engine is None:
            _rapid_engine = RapidOCR()
        pix = pdf_page.get_pixmap(clip=fitz.Rect(*bbox), dpi=_MEASURE_DPI)
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        # RapidOCR's detector misses a glyph that touches the crop's edge.
        result = _rapid_engine(np.array(ImageOps.expand(image, border=40, fill="white")))
        texts = [t.strip() for t in (getattr(result, "txts", None) or ()) if t and t.strip()]
        return " ".join(texts) or None
    except Exception as exc:  # a picture read is a bonus on top of the text
        logger.warning("Could not read picture text on page {}: {}", pdf_page.number + 1, exc)
        return None


# ------------------------------------------------------------------------ boxes


def _grey_page(pdf_page, dpi: int):
    import fitz
    import numpy as np

    pix = pdf_page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def _erase_strokes(grey):
    import numpy as np

    pad = _STROKE_WINDOW // 2
    padded = np.pad(grey, pad, constant_values=255)
    out = grey.copy()
    for dy in range(_STROKE_WINDOW):
        for dx in range(_STROKE_WINDOW):
            np.maximum(out, padded[dy:dy + grey.shape[0], dx:dx + grey.shape[1]], out=out)
    return out


def find_panels(grey) -> List[Tuple[float, float, float, float]]:
    """Shaded panels on a 72-dpi greyscale page, as (x0, y0, x1, y1) points.

    Rows where a stretch of the stroke-free page is clearly darker than the
    paper make a band; the band's columns darker than the paper at all - a
    gradient panel fades almost to white on one side - give its width."""
    import numpy as np

    paper = _erase_strokes(grey)
    level = float(np.percentile(paper, 90))
    core = paper < level - _TINT_CORE
    rows = core.sum(axis=1)
    # Erasing strokes also eats this far into the panel from every edge.
    pad = _STROKE_WINDOW // 2
    height, width = grey.shape
    panels = []
    start = None
    for y, count in enumerate(list(rows) + [0]):
        if count >= _MIN_TINTED_ROW_PT and start is None:
            start = y
        elif count < _MIN_TINTED_ROW_PT and start is not None:
            if y - start >= _MIN_BOX_HEIGHT_PT:
                columns = _panel_columns(paper[start:y], core[start:y], level)
                if columns is not None and columns[1] - columns[0] >= _MIN_BOX_WIDTH_PT:
                    panels.append((
                        float(max(columns[0] - pad, 0)), float(max(start - pad, 0)),
                        float(min(columns[1] + pad, width)), float(min(y + pad, height)),
                    ))
            start = None
    return panels


def _panel_columns(paper_band, core_band, level: float) -> Optional[Tuple[int, int]]:
    import numpy as np

    core_columns = np.nonzero(core_band.mean(axis=0) > 0.5)[0]
    if not len(core_columns):
        return None
    tinted = np.median(paper_band, axis=0) < level - _TINT_EDGE
    left, right = int(core_columns.min()), int(core_columns.max())
    while left > 0 and tinted[left - 1]:
        left -= 1
    while right < len(tinted) - 1 and tinted[right + 1]:
        right += 1
    return left, right + 1


def _overlap(a: Sequence[float], b: Sequence[float]) -> float:
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    return max(width, 0.0) * max(height, 0.0)


def _inside(item: OCRLayoutItem, panel: Sequence[float]) -> bool:
    x0, y0, x1, y1 = item.bbox
    centre_y = (y0 + y1) / 2
    shared = min(x1, panel[2]) - max(x0, panel[0])
    return panel[1] - 2 <= centre_y <= panel[3] + 2 and shared >= _MIN_HORIZONTAL_OVERLAP * max(x1 - x0, 1.0)


def _detect_boxes(page: Page, pdf_page, order_start: int) -> List[Callout]:
    """The page's boxes as Callouts; a non-title heading inside one stops
    being a heading."""
    try:
        panels = find_panels(_grey_page(pdf_page, _BOX_DPI))
    except Exception as exc:  # boxes are a bonus on top of the text
        logger.warning("Could not look for boxes on page {}: {}", page.page_number, exc)
        return []
    lines = page_lines(page)
    found = dict(zip(map(id, page.ocr_layout), layout_line_indices(page.ocr_layout, lines)))
    pictures = [item.bbox for item in page.ocr_layout if item.label == "picture"]
    callouts: List[Callout] = []
    taken: Set[int] = set()
    for panel in panels:
        area = (panel[2] - panel[0]) * (panel[3] - panel[1])
        if any(_overlap(panel, picture) > _MAX_PICTURE_SHARE * area for picture in pictures):
            continue
        members = [
            item for item in page.ocr_layout
            if not item.furniture and item.label != "picture" and item.text and _inside(item, panel)
        ]
        callout = _box_callout(page, members, found, lines, taken, order_start + len(callouts))
        if callout is not None:
            taken.update(range(callout.first_line, callout.last_line + 1))
            callouts.append(callout)
    return callouts


def _box_callout(
    page: Page,
    members: List[OCRLayoutItem],
    found: Dict[int, Optional[int]],
    lines: List[str],
    taken: Set[int],
    order: int,
) -> Optional[Callout]:
    if not members:
        return None
    indices = set()
    for item in members:
        if found[id(item)] is None:
            logger.info("Page {}: box line not in the page text, box skipped: {!r}", page.page_number, item.text[:60])
            return None
        indices.add(found[id(item)])
    first, last = min(indices), max(indices)
    if indices != set(range(first, last + 1)):
        logger.info("Page {}: box lines not contiguous in the page text, box skipped", page.page_number)
        return None
    if indices & taken:
        logger.info("Page {}: box shares lines with another box, box skipped", page.page_number)
        return None
    title = lines[first] if lines[first] in page.ocr_heading_levels else None
    # Heading levels are keyed by text: a line that is also a heading outside
    # the box stays one.
    outside = set(lines[:first] + lines[last + 1:])
    for line in lines[first + 1:last + 1]:
        if line not in outside:
            page.ocr_heading_levels.pop(line, None)
    return Callout(
        callout_type=(classify_callout_type(title) if title else None) or "box",
        label=title or lines[first][:80],
        document_order=order,
        page_number=page.page_number,
        first_line=first,
        last_line=last,
    )


# --------------------------------------------------------------- heading levels


def ascender_height(grey, scale: float) -> Optional[float]:
    """Median ascender-to-baseline height, in points, of the text lines in a
    greyscale crop rendered at ``scale`` pixels per point."""
    import numpy as np

    rows = (grey < _INK).sum(axis=1)
    heights = []
    start = None
    for y, count in enumerate(list(rows) + [0]):
        if count > 0 and start is None:
            start = y
        elif count == 0 and start is not None:
            band = rows[start:y]
            if y - start >= 4 and band.max() >= 3:
                core = np.nonzero(band >= _CORE_SHARE * band.max())[0]
                heights.append((core[-1] + 1) / scale)
            start = None
    return median(heights) if heights else None


def _measure_heading(pdf_page, bbox: Sequence[float]) -> Optional[float]:
    import fitz
    import numpy as np

    x0, y0, x1, y1 = bbox
    pix = pdf_page.get_pixmap(clip=fitz.Rect(x0 - 1, y0 - 1, x1 + 1, y1 + 1), dpi=_MEASURE_DPI, colorspace=fitz.csGRAY)
    grey = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    return ascender_height(grey, _MEASURE_DPI / 72.0)


def split_tiers(sizes: List[float]) -> Optional[int]:
    """Index into ``sizes`` (sorted largest first) of the first heading below
    the first clear size gap, or None when the sizes form one tier."""
    for index in range(_MIN_TIER_SIZE, len(sizes) - _MIN_TIER_SIZE + 1):
        if sizes[index] > 0 and sizes[index - 1] / sizes[index] >= _TIER_GAP:
            return index
    return None


def _tier_heading_levels(pages: List[Page], pdf) -> int:
    """Re-level every scanned heading by its printed size. Returns how many
    headings were re-levelled (0 when the sizes show no tiers)."""
    measured: List[Tuple[float, Page, str]] = []
    for page in pages:
        pdf_page = pdf[page.page_number - 1]
        for item in page.ocr_layout:
            text = item.text.strip()
            if item.label not in _HEADER_LABELS or text not in page.ocr_heading_levels:
                continue
            try:
                size = _measure_heading(pdf_page, item.bbox)
            except Exception as exc:  # an unmeasured heading keeps its level
                logger.warning("Could not measure heading {!r}: {}", text[:40], exc)
                size = None
            if size:
                measured.append((size, page, text))
    measured.sort(key=lambda m: -m[0])
    sizes = [m[0] for m in measured]
    split = split_tiers(sizes)
    if split is None:
        return 0
    has_title = sizes[0] / sizes[1] >= _TIER_GAP and measured[0][1] is pages[0]
    for position, (_, page, text) in enumerate(measured):
        if position == 0 and has_title:
            level = 1
        else:
            level = 2 if position < split else 3
        page.ocr_heading_levels[text] = level
    logger.info(
        "Scanned headings tiered by size: split at {:.1f}/{:.1f} pt ({} above, {} below{})",
        sizes[split - 1], sizes[split], split, len(sizes) - split, ", title found" if has_title else "",
    )
    return len(measured)
