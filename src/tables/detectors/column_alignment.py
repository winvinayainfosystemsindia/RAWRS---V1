"""Column alignment table detector for RAWRS.

Detects tables where cells contain moderate-width text — wider than
SpanAlignmentDetector's narrow-span threshold but still structured in
a regular grid.  Targets descriptor-heavy academic tables like:

    Factor           Low    High
    Teaching         Poor   Good
    Research         Low    High

Unlike SpanAlignmentDetector (which filters spans to < 45% page width
and focuses on numeric content), this detector:

  - Accepts spans up to COL_MAX_SPAN_WIDTH_FRACTION (60%) of page width
  - Uses ROW_SPACING_CONSISTENCY as a primary signal instead of
    numeric content — regular vertical spacing is the hallmark of a
    table even when cells contain prose
  - Requires MIN_TABLE_COLS ≥ 2 and MIN_TABLE_ROWS ≥ 2 (lower than
    SpanAlignmentDetector's 3-row minimum to catch two-row tables
    that appear above or below a three-line rule pattern)

Evidence signals contributed
----------------------------
  column_x_alignment        — consistency of x0 column positions (primary)
  row_spacing_consistency   — regularity of vertical row gaps
  column_count              — number of detected columns
  row_count                 — number of detected rows
  cell_fill                 — fraction of expected cells with content
  bold_header_row           — first row contains bold spans
  caption_found             — label/caption above the region
  page_coverage_penalty     — region covers too much of page
"""

import re
from typing import Dict, List, Optional, Tuple

import fitz
from loguru import logger

from src.tables.detectors.base import CandidateRegion, TableDetector
from src.captions.caption_detector import find_caption
from src.tables.evidence import EvidenceBundle, EvidenceSignal


# --- Tuning constants --------------------------------------------------------

# Accept spans up to this fraction of page width (wider than SpanAlignment's 0.45).
COL_MAX_SPAN_WIDTH_FRACTION = 0.60

# y0 tolerance for grouping spans into the same row band.
ROW_BAND_PT = 4.0

# Minimum gap between two x0 clusters to be distinct columns.
COL_GAP_PT = 14.0

# x0 position tolerance when matching column positions across rows.
COL_TOLERANCE_PT = 14.0

# Minimum columns to form a candidate.
MIN_TABLE_COLS = 2

# Minimum rows to form a candidate.
MIN_TABLE_ROWS = 2

# Maximum vertical gap between consecutive rows to belong to the same table.
MAX_ROW_GAP_PT = 28.0

# Minimum fraction of expected cells with content.
MIN_CELL_FILL = 0.30

# Page fraction above which a coverage penalty applies.
LARGE_PAGE_FRACTION = 0.60

# Pattern for numerics — used to distinguish from SpanAlignmentDetector.
_NUMERIC_RE = re.compile(r"^[-+]?\d[\d,.\s%]*$")


class ColumnAlignmentDetector(TableDetector):
    """Detect text-heavy grid tables via x-column + row-spacing regularity."""

    @property
    def name(self) -> str:
        return "column_alignment"

    def detect(self, fitz_page: fitz.Page, page_number: int) -> List[CandidateRegion]:
        try:
            return self._detect(fitz_page, page_number)
        except Exception as exc:
            logger.warning("ColumnAlignmentDetector: error on page {}: {}", page_number, exc)
            return []

    def _detect(self, fitz_page: fitz.Page, page_number: int) -> List[CandidateRegion]:
        page_rect = fitz_page.rect
        page_width = page_rect.width
        page_height = page_rect.height

        try:
            page_dict = fitz_page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        except Exception as exc:
            logger.debug("ColumnAlignmentDetector: get_text failed on page {}: {}", page_number, exc)
            return []

        # Collect spans up to the wider width threshold
        spans = _collect_spans(page_dict, page_width)
        if not spans:
            return []

        # Group into horizontal row-bands
        bands = _group_into_bands(spans)

        # Find multi-column bands
        multi_col_bands = []
        for band in bands:
            clusters = _cluster_x0([s["x0"] for s in band], COL_GAP_PT)
            if len(clusters) >= MIN_TABLE_COLS:
                multi_col_bands.append((band, clusters))

        if len(multi_col_bands) < MIN_TABLE_ROWS:
            return []

        # Find runs of consistent multi-column bands
        runs = _find_consistent_runs(multi_col_bands)

        results: List[CandidateRegion] = []
        for run_bands, col_positions in runs:
            all_spans_in_run = [s for band, _ in run_bands for s in band]

            bbox = (
                min(s["x0"] for s in all_spans_in_run),
                min(s["y0"] for s in all_spans_in_run),
                max(s["x1"] for s in all_spans_in_run),
                max(s["y1"] for s in all_spans_in_run),
            )
            height = bbox[3] - bbox[1]

            raw_rows = _build_cell_grid(run_bands, col_positions)

            total_cells = len(run_bands) * len(col_positions)
            filled_cells = sum(1 for row in raw_rows for cell in row if cell.strip())
            cell_fill = filled_cells / total_cells if total_cells > 0 else 0.0

            if cell_fill < MIN_CELL_FILL:
                continue

            # Row spacing consistency signal
            row_gaps = _compute_row_gaps(run_bands)
            spacing_consistency = _spacing_consistency(row_gaps)

            bundle = _build_evidence(
                run_bands=run_bands,
                col_positions=col_positions,
                raw_rows=raw_rows,
                cell_fill=cell_fill,
                spacing_consistency=spacing_consistency,
                height=height,
                page_height=page_height,
            )

            caption_page_dict = fitz_page.get_text("dict") if True else {}
            caption, caption_score = find_caption(caption_page_dict, bbox, page_width)
            if caption_score > 0:
                bundle.add(EvidenceSignal(
                    name="caption_found",
                    score=caption_score,
                    weight=0.5,
                    note=f"Caption: {caption[:50]!r}" if caption else "caption signal",
                ))

            results.append(CandidateRegion(
                page_number=page_number,
                bbox=bbox,
                evidence=bundle,
                raw_rows=raw_rows,
                caption=caption,
            ))

        return results


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _collect_spans(page_dict: dict, page_width: float) -> List[Dict]:
    max_width = COL_MAX_SPAN_WIDTH_FRACTION * page_width
    spans = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue
                bbox = span.get("bbox", (0, 0, 0, 0))
                x0, y0, x1, y1 = bbox
                if (x1 - x0) > max_width:
                    continue
                flags = span.get("flags", 0)
                font = span.get("font", "").lower()
                is_bold = bool(flags & (2 ** 4)) or "bold" in font
                spans.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": text, "flags": flags, "is_bold": is_bold})
    return spans


def _group_into_bands(spans: List[Dict]) -> List[List[Dict]]:
    if not spans:
        return []
    sorted_spans = sorted(spans, key=lambda s: (round(s["y0"]), s["x0"]))
    bands: List[List[Dict]] = []
    current: List[Dict] = [sorted_spans[0]]
    current_y = sorted_spans[0]["y0"]
    for span in sorted_spans[1:]:
        if abs(span["y0"] - current_y) <= ROW_BAND_PT:
            current.append(span)
        else:
            bands.append(current)
            current = [span]
            current_y = span["y0"]
    bands.append(current)
    return bands


def _cluster_x0(x0_vals: List[float], gap: float) -> List[float]:
    if not x0_vals:
        return []
    xs = sorted(x0_vals)
    clusters: List[List[float]] = [[xs[0]]]
    for x in xs[1:]:
        if x - clusters[-1][-1] >= gap:
            clusters.append([x])
        else:
            clusters[-1].append(x)
    return [sum(c) / len(c) for c in clusters]


def _count_shared_cols(cols_a: List[float], cols_b: List[float], tol: float) -> int:
    return sum(1 for a in cols_a if any(abs(a - b) <= tol for b in cols_b))


def _find_consistent_runs(
    multi_col_bands: List[Tuple[List[Dict], List[float]]],
) -> List[Tuple[List[Tuple[List[Dict], List[float]]], List[float]]]:
    """Find runs of ≥ MIN_TABLE_ROWS consecutive bands with consistent columns."""
    runs = []
    i = 0
    while i < len(multi_col_bands):
        run = [multi_col_bands[i]]
        j = i + 1
        while j < len(multi_col_bands):
            prev_band, prev_cols = run[-1]
            curr_band, curr_cols = multi_col_bands[j]

            prev_y_max = max(s["y0"] for s in prev_band)
            curr_y_min = min(s["y0"] for s in curr_band)
            if curr_y_min - prev_y_max > MAX_ROW_GAP_PT:
                break

            shared = _count_shared_cols(prev_cols, curr_cols, COL_TOLERANCE_PT)
            if shared >= MIN_TABLE_COLS:
                run.append(multi_col_bands[j])
                j += 1
            else:
                break

        if len(run) >= MIN_TABLE_ROWS:
            all_cols = [col for _, cols in run for col in cols]
            consensus = _cluster_x0(all_cols, COL_GAP_PT)
            if len(consensus) >= MIN_TABLE_COLS:
                runs.append((run, consensus))

        i = j if j > i else i + 1

    return runs


def _build_cell_grid(
    run_bands: List[Tuple[List[Dict], List[float]]],
    col_positions: List[float],
) -> List[List[str]]:
    rows = []
    for band, _ in run_bands:
        row = [""] * len(col_positions)
        for span in band:
            best_col = min(range(len(col_positions)), key=lambda c: abs(span["x0"] - col_positions[c]))
            sep = " " if row[best_col] else ""
            row[best_col] = row[best_col] + sep + span["text"]
        rows.append(row)
    return rows


def _compute_row_gaps(run_bands: List[Tuple[List[Dict], List[float]]]) -> List[float]:
    """Compute vertical gaps between consecutive row bands."""
    gaps = []
    for i in range(1, len(run_bands)):
        prev_band, _ = run_bands[i - 1]
        curr_band, _ = run_bands[i]
        prev_y = max(s["y1"] for s in prev_band)
        curr_y = min(s["y0"] for s in curr_band)
        gaps.append(max(0.0, curr_y - prev_y))
    return gaps


def _spacing_consistency(gaps: List[float]) -> float:
    """Return 0.0–1.0 for how consistent row gaps are (1.0 = perfectly uniform)."""
    if len(gaps) < 2:
        return 0.5  # not enough data to judge
    mean_gap = sum(gaps) / len(gaps)
    if mean_gap == 0:
        return 0.5
    variance = sum((g - mean_gap) ** 2 for g in gaps) / len(gaps)
    cv = (variance ** 0.5) / mean_gap  # coefficient of variation
    return max(0.0, min(1.0, 1.0 - cv))


def _build_evidence(
    run_bands: List[Tuple[List[Dict], List[float]]],
    col_positions: List[float],
    raw_rows: List[List[str]],
    cell_fill: float,
    spacing_consistency: float,
    height: float,
    page_height: float,
) -> EvidenceBundle:
    bundle = EvidenceBundle()
    n_rows = len(run_bands)
    n_cols = len(col_positions)

    # Column x-alignment consistency
    alignment_scores = []
    for band, band_cols in run_bands:
        shared = _count_shared_cols(band_cols, col_positions, COL_TOLERANCE_PT)
        alignment_scores.append(shared / n_cols if n_cols else 0.0)
    alignment_score = sum(alignment_scores) / len(alignment_scores) if alignment_scores else 0.0

    bundle.add(EvidenceSignal(
        name="column_x_alignment",
        score=alignment_score,
        weight=0.7,
        note=f"{n_cols} columns with {alignment_score:.0%} cross-row x-alignment",
    ))

    # Row spacing consistency (primary differentiator from body text)
    bundle.add(EvidenceSignal(
        name="row_spacing_consistency",
        score=spacing_consistency,
        weight=0.6,
        note=f"Row vertical spacing consistency: {spacing_consistency:.0%}",
    ))

    # Column count
    col_score = min(1.0, (n_cols - 1) / 4.0)
    bundle.add(EvidenceSignal(
        name="column_count",
        score=col_score,
        weight=0.4,
        note=f"{n_cols} distinct aligned columns",
    ))

    # Row count
    row_score = min(1.0, (n_rows - 1) / 6.0)
    bundle.add(EvidenceSignal(
        name="row_count",
        score=row_score,
        weight=0.3,
        note=f"{n_rows} rows detected",
    ))

    # Cell fill
    bundle.add(EvidenceSignal(
        name="cell_fill",
        score=min(1.0, cell_fill / 0.6),
        weight=0.4,
        note=f"{cell_fill:.0%} of expected cells contain text",
    ))

    # Bold first row
    if run_bands:
        first_band_spans, _ = run_bands[0]
        has_bold = any(s.get("is_bold", False) for s in first_band_spans)
        if has_bold:
            bundle.add(EvidenceSignal(
                name="bold_header_row",
                score=1.0,
                weight=0.3,
                note="First row contains bold spans — probable header row",
            ))

    # Page coverage penalty
    coverage = height / page_height if page_height > 0 else 0.0
    if coverage > LARGE_PAGE_FRACTION:
        penalty = max(0.0, 1.0 - (coverage - LARGE_PAGE_FRACTION) / (1.0 - LARGE_PAGE_FRACTION))
        bundle.add(EvidenceSignal(
            name="page_coverage_penalty",
            score=penalty,
            weight=0.8,
            note=f"Candidate covers {coverage:.0%} of page — possible false positive",
        ))

    return bundle
