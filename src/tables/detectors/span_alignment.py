"""Span alignment table detector for RAWRS.

Detects borderless academic tables using text span column alignment.
This addresses the primary gap in FEATURE_015.1: tables drawn without
PDF vector borders (common in academic survey/data tables like the
Brinkmann benchmark) are invisible to the VectorBorderDetector.

Algorithm:
  1. Extract all text spans from PyMuPDF rawdict.
  2. Filter to "narrow" spans (width < MAX_SPAN_WIDTH_FRACTION of page
     width): prose body text is typically full-width; table cells are short.
  3. Group spans into horizontal bands by y0 (±ROW_BAND_PT tolerance).
  4. Mark bands as "multi-column": ≥2 distinct x0 clusters separated by
     ≥COL_GAP_PT — the signature of tabular alignment.
  5. Find runs of ≥MIN_TABLE_ROWS consecutive multi-column bands where
     the same ≥MIN_TABLE_COLS column positions recur (±COL_TOLERANCE_PT).
  6. Apply false-positive guards: maximum height, minimum cell fill.
  7. Build an EvidenceBundle from multiple independent signals.

Evidence signals contributed:
  - span_column_alignment: how consistently spans align to fixed columns
  - column_count:          number of detected columns (more = more table-like)
  - row_count:             number of detected rows
  - cell_fill:             fraction of expected cells with content
  - numeric_content:       fraction of cells with numeric-looking content
  - bold_header:           whether the first band has any bold spans
  - caption_found:         whether a caption line was found above the region
  - page_coverage_penalty: penalises candidates that cover >LARGE_FRACTION of page

Detection scope: born-digital pages only. The caller (table_extractor.py)
filters out OCR pages before calling any detector.

strategy='text' was evaluated and rejected (see table_extractor.py
module docstring). This detector implements an independent column-alignment
signal that avoids the whole-page false-positive problem.
"""

import re
from typing import Dict, List, Optional, Tuple

import fitz
from loguru import logger

from src.tables.detectors.base import CandidateRegion, TableDetector
from src.tables.detectors.caption import find_caption
from src.tables.evidence import EvidenceBundle, EvidenceSignal


# --- Tuning constants (all in PDF points unless noted) ----------------------

# Spans wider than this fraction of the page are body-text lines, not cells.
MAX_SPAN_WIDTH_FRACTION = 0.45

# y0 tolerance for grouping spans into the same row band.
ROW_BAND_PT = 4.0

# Minimum horizontal gap between two x0 clusters to count as distinct columns.
COL_GAP_PT = 15.0

# x0 position tolerance when matching column positions across rows.
COL_TOLERANCE_PT = 12.0

# Minimum number of columns for a valid table.
MIN_TABLE_COLS = 2

# Minimum number of rows for a valid table.
MIN_TABLE_ROWS = 3

# Maximum gap between consecutive table rows (larger gap = row break).
MAX_ROW_GAP_PT = 22.0

# Candidates taller than this fraction of the page height are penalised
# (the whole-page false-positive signature of strategy='text').
LARGE_PAGE_FRACTION = 0.60

# The distance from the leftmost to rightmost column position must be at least
# this fraction of page width. Indent-based body-text false positives (numbered
# lists, hanging indents) have columns 15–30pt apart; real 2-column tables span
# at least 15% of the page (~89pt on A4). Calibrated against FolkPedagogy_Bruner
# (iLovePDF) false positives vs. Nature of Enquiry and Brinkman true positives.
MIN_COL_SPREAD_FRACTION = 0.15

# Maximum coefficient-of-variation of row-to-row vertical gaps within a run.
# Low CV = rows evenly spaced like a real table; high CV = flowing paragraph
# text where line spacing varies (long sections vs. short labels, section breaks
# within the gap limit). Calibrated against FolkPedagogy_Bruner false positives
# (formatted 2-column prose with variable inter-line spacing).
MAX_ROW_SPACING_CV = 0.40

# Minimum fraction of expected cells that must contain text to pass.
MIN_CELL_FILL = 0.35

# Pattern for numbers / percentages that suggest data-table content.
_NUMERIC_RE = re.compile(r"^[-+]?\d[\d,.\s%]*$")


class SpanAlignmentDetector(TableDetector):
    """Detect borderless tables via text span column alignment (medium confidence)."""

    @property
    def name(self) -> str:
        return "span_alignment"

    def detect(self, fitz_page: fitz.Page, page_number: int) -> List[CandidateRegion]:
        try:
            return self._detect(fitz_page, page_number)
        except Exception as exc:
            logger.warning("SpanAlignmentDetector: error on page {}: {}", page_number, exc)
            return []

    def _detect(self, fitz_page: fitz.Page, page_number: int) -> List[CandidateRegion]:
        page_rect = fitz_page.rect
        page_width = page_rect.width
        page_height = page_rect.height

        try:
            page_dict = fitz_page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        except Exception as exc:
            logger.debug("SpanAlignmentDetector: get_text failed on page {}: {}", page_number, exc)
            return []

        # --- Step 1: Collect narrow spans ---
        spans = _collect_narrow_spans(page_dict, page_width)
        if not spans:
            return []

        # --- Step 2: Group spans into horizontal row-bands ---
        bands = _group_into_bands(spans)

        # --- Step 3: Mark multi-column bands ---
        multi_col_bands = []
        for band in bands:
            clusters = _cluster_x0(band, COL_GAP_PT)
            if len(clusters) >= MIN_TABLE_COLS:
                multi_col_bands.append((band, clusters))

        if len(multi_col_bands) < MIN_TABLE_ROWS:
            return []

        # --- Step 4: Find runs of consistent multi-column bands ---
        runs = _find_consistent_runs(multi_col_bands)

        # --- Step 5: Convert runs to candidates ---
        results: List[CandidateRegion] = []
        for run_bands, col_positions in runs:
            # Column positions must span at least MIN_COL_SPREAD_FRACTION of page
            # width. Indent-based body text (numbered lists, hanging indents) creates
            # 2-column patterns with columns only 15–30pt apart — filtered here.
            col_spread = max(col_positions) - min(col_positions)
            if col_spread < MIN_COL_SPREAD_FRACTION * page_width:
                continue

            # Row spacing must be consistent (low CV). Flowing paragraph text
            # formatted into two visible columns (e.g., concept-on-left / text-on-right)
            # has variable inter-row gaps; real tables have evenly spaced rows.
            spacing_cv = _row_gap_cv(run_bands)
            if spacing_cv > MAX_ROW_SPACING_CV:
                continue

            all_spans_in_run = [s for band, _ in run_bands for s in band]

            bbox = (
                min(s["x0"] for s in all_spans_in_run),
                min(s["y0"] for s in all_spans_in_run),
                max(s["x1"] for s in all_spans_in_run),
                max(s["y1"] for s in all_spans_in_run),
            )
            height = bbox[3] - bbox[1]

            # Build cell grid
            raw_rows = _build_cell_grid(run_bands, col_positions)

            # Compute cell fill
            total_cells = len(run_bands) * len(col_positions)
            filled_cells = sum(1 for row in raw_rows for cell in row if cell.strip())
            cell_fill = filled_cells / total_cells if total_cells > 0 else 0.0

            if cell_fill < MIN_CELL_FILL:
                continue  # too sparse — likely prose with occasional aligned text

            # Build evidence
            bundle = _build_evidence(
                run_bands=run_bands,
                col_positions=col_positions,
                raw_rows=raw_rows,
                cell_fill=cell_fill,
                height=height,
                page_height=page_height,
            )

            # Caption detection
            caption, caption_score = find_caption(page_dict, bbox, page_width)
            if caption_score > 0:
                bundle.add(EvidenceSignal(
                    name="caption_found",
                    score=caption_score,
                    weight=0.5,
                    note=f"Caption above region: {caption[:50]!r}" if caption else "caption signal",
                ))

            results.append(CandidateRegion(
                page_number=page_number,
                bbox=bbox,
                evidence=bundle,
                raw_rows=raw_rows,
                caption=caption,
            ))

        return results


# --- Private helpers ---------------------------------------------------------


def _collect_narrow_spans(page_dict: dict, page_width: float) -> List[dict]:
    """Extract spans narrower than MAX_SPAN_WIDTH_FRACTION of the page."""
    max_width = MAX_SPAN_WIDTH_FRACTION * page_width
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
                spans.append({
                    "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                    "text": text,
                    "flags": span.get("flags", 0),
                })
    return spans


def _group_into_bands(spans: List[dict]) -> List[List[dict]]:
    """Group spans into horizontal bands by y0 proximity."""
    if not spans:
        return []
    spans_sorted = sorted(spans, key=lambda s: (round(s["y0"]), s["x0"]))
    bands: List[List[dict]] = []
    current: List[dict] = [spans_sorted[0]]
    current_y = spans_sorted[0]["y0"]
    for span in spans_sorted[1:]:
        if abs(span["y0"] - current_y) <= ROW_BAND_PT:
            current.append(span)
        else:
            bands.append(current)
            current = [span]
            current_y = span["y0"]
    bands.append(current)
    return bands


def _cluster_x0(band: List[dict], gap: float) -> List[float]:
    """Cluster x0 positions in a band into groups separated by ≥ gap points.

    Returns a sorted list of representative x0 values (one per cluster),
    where each representative is the mean of x0 positions in that cluster.
    """
    x0_vals = sorted(s["x0"] for s in band)
    if not x0_vals:
        return []

    clusters: List[List[float]] = [[x0_vals[0]]]
    for x in x0_vals[1:]:
        if x - clusters[-1][-1] >= gap:
            clusters.append([x])
        else:
            clusters[-1].append(x)

    return [sum(c) / len(c) for c in clusters]


def _find_consistent_runs(
    multi_col_bands: List[Tuple[List[dict], List[float]]],
) -> List[Tuple[List[Tuple[List[dict], List[float]]], List[float]]]:
    """Find runs of ≥MIN_TABLE_ROWS consecutive bands with consistent columns.

    Returns a list of (run_bands, consensus_col_positions) tuples, where
    run_bands is a list of (band_spans, col_positions) pairs and
    consensus_col_positions is the averaged column x0 positions across the run.
    """
    if not multi_col_bands:
        return []

    runs: List[Tuple[List, List[float]]] = []
    i = 0
    while i < len(multi_col_bands):
        run = [multi_col_bands[i]]
        j = i + 1
        while j < len(multi_col_bands):
            prev_band, prev_cols = run[-1]
            curr_band, curr_cols = multi_col_bands[j]

            # Check vertical proximity
            prev_y_max = max(s["y0"] for s in prev_band)
            curr_y_min = min(s["y0"] for s in curr_band)
            if curr_y_min - prev_y_max > MAX_ROW_GAP_PT:
                break

            # Check column consistency: ≥MIN_TABLE_COLS shared column positions
            shared = _count_shared_cols(prev_cols, curr_cols, COL_TOLERANCE_PT)
            if shared >= MIN_TABLE_COLS:
                run.append(multi_col_bands[j])
                j += 1
            else:
                break

        if len(run) >= MIN_TABLE_ROWS:
            # Compute consensus column positions across the run
            all_cols = [col for _, cols in run for col in cols]
            consensus = _cluster_x0(
                [{"x0": c} for c in all_cols],  # type: ignore[arg-type]
                COL_GAP_PT,
            )
            if len(consensus) >= MIN_TABLE_COLS:
                runs.append((run, consensus))

        i = j if j > i else i + 1

    return runs


def _row_gap_cv(run_bands: List[Tuple[List[dict], List[float]]]) -> float:
    """Coefficient-of-variation of vertical gaps between consecutive bands in a run.

    Low CV (< 0.4) means evenly spaced rows — consistent with a real table.
    High CV means variable spacing — consistent with flowing prose or mixed content.
    Returns infinity when fewer than 2 gaps can be computed (3+ bands required).
    """
    if len(run_bands) < 3:
        return float("inf")
    band_mid_ys = [
        (min(s["y0"] for s in band) + max(s["y1"] for s in band)) / 2.0
        for band, _ in run_bands
    ]
    gaps = [band_mid_ys[i + 1] - band_mid_ys[i] for i in range(len(band_mid_ys) - 1)]
    if not gaps:
        return float("inf")
    mean = sum(gaps) / len(gaps)
    if mean <= 0:
        return float("inf")
    variance = sum((g - mean) ** 2 for g in gaps) / len(gaps)
    return (variance ** 0.5) / mean


def _count_shared_cols(cols_a: List[float], cols_b: List[float], tol: float) -> int:
    """Count how many column positions in cols_a have a match in cols_b."""
    return sum(
        1 for a in cols_a
        if any(abs(a - b) <= tol for b in cols_b)
    )


def _build_cell_grid(
    run_bands: List[Tuple[List[dict], List[float]]],
    col_positions: List[float],
) -> List[List[str]]:
    """Build a rows×cols text grid from aligned span bands."""
    rows = []
    for band, _ in run_bands:
        row = [""] * len(col_positions)
        for span in band:
            # Assign span to closest column position
            best_col = min(range(len(col_positions)), key=lambda c: abs(span["x0"] - col_positions[c]))
            sep = " " if row[best_col] else ""
            row[best_col] = row[best_col] + sep + span["text"]
        rows.append(row)
    return rows


def _build_evidence(
    run_bands: List[Tuple[List[dict], List[float]]],
    col_positions: List[float],
    raw_rows: List[List[str]],
    cell_fill: float,
    height: float,
    page_height: float,
) -> EvidenceBundle:
    """Build an EvidenceBundle for a span-alignment candidate."""
    bundle = EvidenceBundle()
    n_rows = len(run_bands)
    n_cols = len(col_positions)

    # --- Column alignment consistency ---
    # Measure how consistently each band's spans align to the consensus positions.
    alignment_scores = []
    for band, band_cols in run_bands:
        shared = _count_shared_cols(band_cols, col_positions, COL_TOLERANCE_PT)
        alignment_scores.append(shared / n_cols if n_cols else 0.0)
    alignment_score = sum(alignment_scores) / len(alignment_scores) if alignment_scores else 0.0

    bundle.add(EvidenceSignal(
        name="span_column_alignment",
        score=alignment_score,
        weight=0.7,
        note=f"{n_cols} columns with {alignment_score:.0%} cross-row consistency",
    ))

    # --- Column count ---
    col_score = min(1.0, (n_cols - 1) / 4.0)  # 2 cols=0.25, 5 cols=1.0
    bundle.add(EvidenceSignal(
        name="column_count",
        score=col_score,
        weight=0.4,
        note=f"{n_cols} distinct aligned columns detected",
    ))

    # --- Row count ---
    row_score = min(1.0, (n_rows - 2) / 8.0)  # 3 rows=0.125, 10 rows=1.0
    bundle.add(EvidenceSignal(
        name="row_count",
        score=row_score,
        weight=0.3,
        note=f"{n_rows} table rows detected",
    ))

    # --- Cell fill ---
    bundle.add(EvidenceSignal(
        name="cell_fill",
        score=min(1.0, cell_fill / 0.7),
        weight=0.4,
        note=f"{cell_fill:.0%} of expected cells contain text",
    ))

    # --- Numeric content ---
    all_cells = [cell for row in raw_rows for cell in row if cell.strip()]
    numeric_count = sum(1 for c in all_cells if _NUMERIC_RE.match(c.strip()))
    numeric_frac = numeric_count / len(all_cells) if all_cells else 0.0
    if numeric_frac > 0:
        bundle.add(EvidenceSignal(
            name="numeric_content",
            score=min(1.0, numeric_frac * 2),
            weight=0.4,
            note=f"{numeric_frac:.0%} of cells contain numeric/percentage values",
        ))

    # --- Bold first row (header signal) ---
    if run_bands:
        first_band_spans, _ = run_bands[0]
        has_bold = any(s["flags"] & (2 ** 4) for s in first_band_spans)
        if has_bold:
            bundle.add(EvidenceSignal(
                name="bold_header_row",
                score=1.0,
                weight=0.3,
                note="First row contains bold spans — probable header row",
            ))

    # --- Page coverage penalty ---
    coverage = height / page_height if page_height > 0 else 0.0
    if coverage > LARGE_PAGE_FRACTION:
        penalty_score = max(0.0, 1.0 - (coverage - LARGE_PAGE_FRACTION) / (1.0 - LARGE_PAGE_FRACTION))
        bundle.add(EvidenceSignal(
            name="page_coverage_penalty",
            score=penalty_score,
            weight=0.8,
            note=f"Candidate covers {coverage:.0%} of page height — possible false positive",
        ))

    return bundle
