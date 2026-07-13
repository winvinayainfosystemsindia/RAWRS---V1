"""Table extraction for RAWRS using evidence-fusion detection.

Orchestrates multiple TableDetector plugins, merges overlapping candidates,
aggregates their evidence bundles, and converts final candidates to Table
model objects with explainable confidence scores.

Registered detectors (in priority order):
  1. VectorBorderDetector  — tables with explicit PDF border lines (highest confidence)
  2. SpanAlignmentDetector — borderless tables via text column alignment (medium confidence)

Evidence-fusion design: each detector returns CandidateRegion objects with
independent evidence signals. When two detectors propose overlapping regions
(IoU > MERGE_IOU_THRESHOLD), their evidence bundles are merged into a single
candidate and the confidence is re-computed from all combined signals.

Candidate-to-Table conversion reuses the header detection, cell span
detection, and confidence scoring logic from Phase T (FEATURE_015.1),
now operating on merged evidence rather than raw PyMuPDF output.

Detection scope: only DIRECT_TEXT_EXTRACTION pages — OCR pages lack
both vector line graphics and reliable span position data.

strategy='text' was evaluated and rejected: on multi-column academic
layouts it treats the entire page as a single large table grid.
See the SpanAlignmentDetector for the alternative that replaced it.

PyMuPDF 1.23.0+ is required for page.find_tables(). This project
uses 1.27.2.3.
"""

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import fitz
from loguru import logger

from src.models.bounding_box import BoundingBox
from src.models.contracts import Document, ExtractionMethod
from src.models.lifecycle import ObjectLifecycleStatus
from src.models.table import Table, TableCell, TableRow, TableStatus
from src.tables.detectors.base import CandidateRegion, TableDetector
from src.tables.detectors.vector_border import VectorBorderDetector
from src.tables.detectors.span_alignment import SpanAlignmentDetector
from src.tables.detectors.horizontal_rule import HorizontalRuleDetector
from src.tables.detectors.column_alignment import ColumnAlignmentDetector
from src.tables.evidence import EvidenceBundle, EvidenceSignal


# IoU threshold for merging overlapping candidates from different detectors.
MERGE_IOU_THRESHOLD = 0.25

# Registered detectors — add new plugins here.
# Priority order within each page: VectorBorder first (highest fidelity),
# then HorizontalRule (academic 3-line tables), SpanAlignment (short-cell
# borderless tables), ColumnAlignment (wider-cell borderless tables).
_DETECTORS: List[TableDetector] = [
    VectorBorderDetector(),
    HorizontalRuleDetector(),
    SpanAlignmentDetector(),
    ColumnAlignmentDetector(),
]


def extract_tables(document: Document, pdf_path: Path) -> List[Table]:
    """Detect tables on each born-digital page using evidence-fusion detection.

    Args:
        document: A Document with completed Stage 2 (text extraction and
            routing) so page.extraction_method is populated.
        pdf_path: Path to the source PDF.

    Returns:
        List of Table objects in (page_number, detection_order) order.
        Empty list if no tables detected or PDF cannot be opened.
    """
    # MATHPIX_IMPORT pages are included alongside DIRECT_TEXT_EXTRACTION:
    # this function never reads Page.cleaned_text (it re-opens pdf_path via
    # fitz directly, same "independent PDF re-read" pattern
    # heading_detector.py/footnote_detector.py use for cross-source
    # verification), so a page's extraction_method tag doesn't change what
    # geometry is available here — it only gates out true OCR-only pages
    # (DOCLING/SURYA/OCR_PENDING), which lack reliable vector-line/span
    # position data for table detection either way.
    scannable_methods = {ExtractionMethod.DIRECT_TEXT_EXTRACTION, ExtractionMethod.MATHPIX_IMPORT}
    direct_text_pages = [p for p in document.pages if p.extraction_method in scannable_methods]
    if not direct_text_pages:
        logger.info(
            "Table extraction: no DIRECT_TEXT_EXTRACTION pages in '{}'; skipping",
            document.source_pdf_path,
        )
        return []

    try:
        fitz_doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning(
            "Table extraction: could not open '{}': {}; no tables extracted",
            pdf_path,
            exc,
        )
        return []

    tables: List[Table] = []
    try:
        direct_page_numbers = {p.page_number for p in direct_text_pages}
        for page_number in sorted(direct_page_numbers):
            fitz_page = fitz_doc[page_number - 1]
            page_tables = _extract_page_tables(fitz_page, page_number)
            tables.extend(page_tables)
    finally:
        fitz_doc.close()

    logger.info(
        "Table extraction complete for '{}': {} table(s) across {} page(s) "
        "({} vector-border, {} horizontal-rule, {} span-alignment, {} column-alignment, {} merged)",
        document.source_pdf_path,
        len(tables),
        len({t.page_number for t in tables}),
        sum(1 for t in tables if t.extraction_source == "pymupdf"),
        sum(1 for t in tables if "horizontal_rules" in [s.get("name", "") for s in t.evidence_signals]),
        sum(1 for t in tables if t.extraction_source == "spatial_analysis"),
        sum(1 for t in tables if any(s.get("name") == "column_x_alignment" for s in t.evidence_signals)),
        sum(1 for t in tables if "+" in t.extraction_source),
    )
    return tables


def _extract_page_tables(fitz_page: fitz.Page, page_number: int) -> List[Table]:
    """Run all detectors on one page, merge candidates, build Table objects."""
    all_candidates: List[CandidateRegion] = []

    for detector in _DETECTORS:
        try:
            candidates = detector.detect(fitz_page, page_number)
            all_candidates.extend(candidates)
        except Exception as exc:
            logger.warning(
                "Detector '{}' failed on page {}: {}", detector.name, page_number, exc
            )

    if not all_candidates:
        return []

    merged = _merge_overlapping_candidates(all_candidates)

    # Build per-cell font signals for header detection
    cell_signals = _build_cell_font_signals(fitz_page)

    results: List[Table] = []
    for index, candidate in enumerate(merged):
        table = _build_table(candidate, page_number, index, fitz_page, cell_signals)
        if table is not None:
            results.append(table)
    return results


def _merge_overlapping_candidates(candidates: List[CandidateRegion]) -> List[CandidateRegion]:
    """Merge candidates whose bboxes overlap above MERGE_IOU_THRESHOLD.

    When two candidates (e.g. from VectorBorderDetector and SpanAlignmentDetector)
    overlap the same region, their evidence bundles are combined into a single
    candidate with a richer, more explainable confidence score.

    Non-overlapping candidates are kept as separate Table detections.
    """
    if len(candidates) <= 1:
        return candidates

    used = [False] * len(candidates)
    merged: List[CandidateRegion] = []

    for i, a in enumerate(candidates):
        if used[i]:
            continue
        group = [a]
        for j, b in enumerate(candidates[i + 1:], start=i + 1):
            if used[j]:
                continue
            if _iou(a.bbox, b.bbox) >= MERGE_IOU_THRESHOLD:
                group.append(b)
                used[j] = True

        if len(group) == 1:
            merged.append(a)
        else:
            merged.append(_combine_candidates(group))

        used[i] = True

    return merged


def _iou(bbox_a: tuple, bbox_b: tuple) -> float:
    """Intersection over Union for two (x0,y0,x1,y1) bboxes."""
    ax0, ay0, ax1, ay1 = bbox_a
    bx0, by0, bx1, by1 = bbox_b

    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)

    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    if inter == 0:
        return 0.0

    area_a = (ax1 - ax0) * (ay1 - ay0)
    area_b = (bx1 - bx0) * (by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _combine_candidates(group: List[CandidateRegion]) -> CandidateRegion:
    """Merge a group of overlapping candidates into one with combined evidence."""
    # Use the largest bbox to cover all detections
    x0 = min(c.bbox[0] for c in group)
    y0 = min(c.bbox[1] for c in group)
    x1 = max(c.bbox[2] for c in group)
    y1 = max(c.bbox[3] for c in group)
    merged_bbox = (x0, y0, x1, y1)

    combined = EvidenceBundle()
    for candidate in group:
        for signal in candidate.evidence.signals:
            combined.add(signal)

    # Prefer raw_rows from VectorBorderDetector (highest fidelity)
    raw_rows = next((c.raw_rows for c in group if c.raw_rows and "pymupdf" not in (c.extraction_source if hasattr(c, "extraction_source") else "")), None)
    # Fallback: use first candidate's raw_rows
    if raw_rows is None:
        raw_rows = next((c.raw_rows for c in group if c.raw_rows), None)

    caption = next((c.caption for c in group if c.caption), None)

    return CandidateRegion(
        page_number=group[0].page_number,
        bbox=merged_bbox,
        evidence=combined,
        raw_rows=raw_rows,
        caption=caption,
    )


def _build_table(
    candidate: CandidateRegion,
    page_number: int,
    index: int,
    fitz_page: fitz.Page,
    cell_signals: Dict[Tuple[float, float], bool],
) -> Optional[Table]:
    """Convert a merged CandidateRegion to a Table model object."""
    # Determine extraction source from evidence signal names
    signal_names = {s.name for s in candidate.evidence.signals}
    has_vector = "vector_borders" in signal_names
    has_spatial = "span_column_alignment" in signal_names
    if has_vector and has_spatial:
        extraction_source = "pymupdf+spatial"
    elif has_vector:
        extraction_source = "pymupdf"
    else:
        extraction_source = "spatial_analysis"

    # Get raw rows — from candidate or re-extract for spatial detections
    raw_rows = candidate.raw_rows
    if raw_rows is None or not raw_rows:
        return None

    row_count = len(raw_rows)
    col_count = max((len(row) for row in raw_rows), default=0)
    if row_count == 0 or col_count == 0:
        return None

    # A single-column result from a spatial/alignment detector is degenerate —
    # real tables require at least 2 columns to be distinguishable from body text.
    # VectorBorderDetector (explicit PDF grid lines) is exempt from this gate.
    if col_count <= 1 and extraction_source == "spatial_analysis":
        return None

    # Pad rows to uniform width
    raw_rows = [row + [""] * (col_count - len(row)) for row in raw_rows]

    # --- Header row detection via font signals ---
    bbox_obj = _tuple_to_bbox(candidate.bbox)

    # Compute per-row cell bboxes for font signal lookup
    # For spatial detections we don't have per-cell bboxes, so use a simpler heuristic
    header_row_set = _detect_header_rows(raw_rows, candidate, cell_signals, fitz_page)

    # --- Row header column detection ---
    header_col_count = _detect_header_col(raw_rows, header_row_set, candidate, cell_signals)

    # --- Build TableRow / TableCell objects ---
    header_row_list = sorted(header_row_set)
    rows: List[TableRow] = []
    for row_idx, raw_row in enumerate(raw_rows):
        is_header_row = row_idx in header_row_set
        header_level = header_row_list.index(row_idx) + 1 if is_header_row else 0

        cells: List[TableCell] = []
        for col_idx, cell_text in enumerate(raw_row):
            is_header = is_header_row or col_idx < header_col_count
            is_row_header = (col_idx < header_col_count) and not is_header_row
            cells.append(TableCell(
                text=(cell_text or "").strip(),
                row_index=row_idx,
                col_index=col_idx,
                is_header=is_header,
                is_row_header=is_row_header,
                header_level=header_level if is_header_row else 0,
            ))
        rows.append(TableRow(cells=cells, is_header_row=is_header_row))

    confidence = candidate.evidence.confidence

    return Table(
        table_id=f"table-p{page_number}-{index}",
        page_number=page_number,
        row_count=row_count,
        col_count=col_count,
        rows=rows,
        caption=candidate.caption,
        status=TableStatus.AUTO_DETECTED,
        extraction_source=extraction_source,
        bbox=bbox_obj,
        header_col_count=header_col_count,
        confidence=confidence,
        evidence_signals=candidate.evidence.to_dict_list(),
        lifecycle_status=ObjectLifecycleStatus.DETECTED,
    )


def _detect_header_rows(
    raw_rows: List[List[str]],
    candidate: CandidateRegion,
    cell_signals: Dict[Tuple[float, float], bool],
    fitz_page: fitz.Page,
) -> Set[int]:
    """Detect which row indices are header rows.

    For vector-border tables: uses per-cell bold font signals.
    For spatial tables: falls back to "row 0 is the header" heuristic
    (the most reliable signal when we don't have cell bboxes).
    """
    row_count = len(raw_rows)
    if row_count == 0:
        return set()

    signal_names = {s.name for s in candidate.evidence.signals}
    header_set = set()

    if "vector_borders" in signal_names and cell_signals:
        # Use font signals for bordered tables
        header_set.add(0)  # baseline: row 0 is always a header candidate
        # Additional bold-based header detection for up to 2 header rows
        for row_idx in range(min(row_count, 3)):
            bold_fraction = _row_bold_fraction_from_page(fitz_page, candidate.bbox, row_idx, row_count)
            if bold_fraction > 0.5 and row_idx not in header_set:
                if not header_set or (row_idx - max(header_set)) == 1:
                    header_set.add(row_idx)
                else:
                    break
            elif row_idx > 0 and row_idx not in header_set:
                break
    else:
        # Spatial detection: row 0 is the header by default
        if row_count > 1:
            header_set.add(0)

    return header_set


def _row_bold_fraction_from_page(
    fitz_page: fitz.Page,
    table_bbox: tuple,
    row_idx: int,
    row_count: int,
) -> float:
    """Estimate bold fraction for a table row using a vertical band lookup."""
    if row_count == 0:
        return 0.0
    _, ty0, _, ty1 = table_bbox
    row_height = (ty1 - ty0) / row_count
    row_y0 = ty0 + row_idx * row_height
    row_y1 = row_y0 + row_height

    try:
        page_dict = fitz_page.get_text("rawdict")
        bold_count = 0
        total_count = 0
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_bbox = line.get("bbox", (0, 0, 0, 0))
                line_mid_y = (line_bbox[1] + line_bbox[3]) / 2
                if not (row_y0 <= line_mid_y <= row_y1):
                    continue
                for span in line.get("spans", []):
                    total_count += 1
                    flags = span.get("flags", 0)
                    font = span.get("font", "").lower()
                    if flags & (2 ** 4) or "bold" in font:
                        bold_count += 1
        return bold_count / total_count if total_count > 0 else 0.0
    except Exception:
        return 0.0


def _detect_header_col(
    raw_rows: List[List[str]],
    header_row_set: Set[int],
    candidate: CandidateRegion,
    cell_signals: Dict[Tuple[float, float], bool],
) -> int:
    """Detect whether column 0 is a row-header column (returns 0 or 1)."""
    data_rows = [raw_rows[i] for i in range(len(raw_rows)) if i not in header_row_set]
    if len(data_rows) < 2 or not raw_rows or not raw_rows[0]:
        return 0

    col_count = len(raw_rows[0])
    if col_count < 2:
        return 0

    # Heuristic: col 0 is a row header if its content is non-numeric
    # while other columns have numeric content
    col0_non_numeric = sum(
        1 for row in data_rows
        if row and row[0].strip() and not _is_numeric(row[0])
    )
    other_numeric = sum(
        1 for row in data_rows for ci in range(1, col_count)
        if len(row) > ci and row[ci].strip() and _is_numeric(row[ci])
    )

    col0_frac = col0_non_numeric / len(data_rows) if data_rows else 0.0
    other_denom = len(data_rows) * (col_count - 1)
    other_frac = other_numeric / other_denom if other_denom > 0 else 0.0

    if col0_frac > 0.6 and other_frac > 0.4:
        return 1
    return 0


def _is_numeric(text: str) -> bool:
    import re
    return bool(re.match(r"^[-+]?\d[\d,.\s%]*$", text.strip()))


def _tuple_to_bbox(t: tuple) -> BoundingBox:
    return BoundingBox(x0=t[0], y0=t[1], x1=t[2], y1=t[3])


def _convert_table(
    fitz_table,
    page_number: int,
    index: int,
    cell_signals: Optional[Dict[Tuple[float, float], bool]] = None,
) -> Optional[Table]:
    """Convert a raw PyMuPDF table object to a Table model with span detection.

    PyMuPDF encodes merged cells as None in the flat .cells list (row-major order).
    A None at position (row, col) means that cell is consumed by a prior anchor cell.
    This function detects col_span from horizontal Nones (same row, prior column) and
    row_span from vertical Nones (same column, prior row).
    """
    if cell_signals is None:
        cell_signals = {}

    row_count = fitz_table.row_count
    col_count = fitz_table.col_count
    if row_count == 0 or col_count == 0:
        return None

    raw_rows = fitz_table.extract()
    if not raw_rows:
        return None

    raw_rows = [row + [""] * (col_count - len(row)) for row in raw_rows]

    # Span detection: scan the flat cells list for None entries.
    flat_cells = getattr(fitz_table, "cells", None)
    spans: Dict[Tuple[int, int], Tuple[int, int]] = {}  # anchor (row, col) → (col_span, row_span)
    consumed: Set[Tuple[int, int]] = set()

    if flat_cells is not None and len(flat_cells) == row_count * col_count:
        for row_idx in range(row_count):
            for col_idx in range(col_count):
                if flat_cells[row_idx * col_count + col_idx] is not None:
                    continue
                # Look left in the same row for a non-None, non-consumed anchor (col-span).
                anchor: Optional[Tuple[int, int]] = None
                for c in range(col_idx - 1, -1, -1):
                    if flat_cells[row_idx * col_count + c] is not None and (row_idx, c) not in consumed:
                        anchor = (row_idx, c)
                        break
                if anchor:
                    old_cs, old_rs = spans.get(anchor, (1, 1))
                    spans[anchor] = (old_cs + 1, old_rs)
                    consumed.add((row_idx, col_idx))
                    continue
                # Look up in the same column for a non-None, non-consumed anchor (row-span).
                for r in range(row_idx - 1, -1, -1):
                    if flat_cells[r * col_count + col_idx] is not None and (r, col_idx) not in consumed:
                        anchor = (r, col_idx)
                        break
                if anchor:
                    old_cs, old_rs = spans.get(anchor, (1, 1))
                    spans[anchor] = (old_cs, old_rs + 1)
                    consumed.add((row_idx, col_idx))

    header_row_set: Set[int] = {0} if row_count > 1 else set()
    header_row_list = sorted(header_row_set)
    rows: List[TableRow] = []
    for row_idx, raw_row in enumerate(raw_rows):
        is_header_row = row_idx in header_row_set
        header_level = header_row_list.index(row_idx) + 1 if is_header_row else 0
        cells: List[TableCell] = []
        for col_idx, cell_text in enumerate(raw_row):
            cell_col_span, cell_row_span = spans.get((row_idx, col_idx), (1, 1))
            text = "" if (row_idx, col_idx) in consumed else (cell_text or "").strip()
            cells.append(TableCell(
                text=text,
                row_index=row_idx,
                col_index=col_idx,
                is_header=is_header_row,
                is_row_header=False,
                header_level=header_level if is_header_row else 0,
                col_span=cell_col_span,
                row_span=cell_row_span,
            ))
        rows.append(TableRow(cells=cells, is_header_row=is_header_row))

    raw_bbox = getattr(fitz_table, "bbox", None)
    bbox_obj = _tuple_to_bbox(raw_bbox) if raw_bbox else BoundingBox(x0=0, y0=0, x1=0, y1=0)

    return Table(
        table_id=f"table-p{page_number}-{index}",
        page_number=page_number,
        row_count=row_count,
        col_count=col_count,
        rows=rows,
        caption=None,
        status=TableStatus.AUTO_DETECTED,
        extraction_source="pymupdf",
        bbox=bbox_obj,
        header_col_count=0,
        confidence=0.8,
        lifecycle_status=ObjectLifecycleStatus.DETECTED,
    )


def _build_cell_font_signals(fitz_page: fitz.Page) -> Dict[Tuple[float, float], bool]:
    """Build a mapping from (x0, y0) bbox corner → is_bold for text spans."""
    signals: Dict[Tuple[float, float], bool] = {}
    try:
        page_dict = fitz_page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    flags = span.get("flags", 0)
                    font_name = span.get("font", "").lower()
                    is_bold = bool(flags & 2 ** 4) or "bold" in font_name
                    bbox = span.get("bbox", (0, 0, 0, 0))
                    key = (round(bbox[0], 1), round(bbox[1], 1))
                    signals[key] = signals.get(key, False) or is_bold
    except Exception as exc:
        logger.debug("Font signal extraction failed on page: {}", exc)
    return signals
