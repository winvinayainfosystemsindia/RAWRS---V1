"""Horizontal-rule table detector for RAWRS.

Detects academic three-line tables that have horizontal vector rules
(top rule / header rule / bottom rule) but NO vertical borders.

This is the dominant table style in journals using the Booktabs LaTeX
package and in APA-formatted research papers.  VectorBorderDetector
misses these because find_tables(strategy='lines') requires a complete
grid of vertical + horizontal lines to delineate cells.
SpanAlignmentDetector may miss them when cell text is wider than its
MAX_SPAN_WIDTH_FRACTION threshold.

Algorithm
---------
1. Extract horizontal line segments from PyMuPDF path drawings.
2. Accept lines (and thin rectangles) whose x-extent ≥ MIN_RULE_WIDTH_FRACTION
   of page width and whose stroke width ≤ MAX_RULE_STROKE_PT.
3. Cluster lines by y-position (within RULE_CLUSTER_PT tolerance) to
   collapse multiple strokes that represent one logical rule.
4. Find groups of ≥ MIN_RULES distinct rule clusters with similar
   x-extent (same table, not two separate decorative rules).
5. Verify text exists between the outermost rules (non-empty table body).
6. Build a raw cell grid from text spans grouped by y-band (rows) and
   x-cluster (columns).
7. Apply the page-coverage false-positive guard.
8. Emit one CandidateRegion per qualifying group.

Evidence signals contributed
----------------------------
  horizontal_rules      — how many rules were found (strong positive)
  three_line_pattern    — classic top/mid/bottom triple rule (strongest)
  text_between_rules    — fraction of expected row slots with content
  column_count          — number of detected text columns
  row_count             — number of detected text rows
  rule_x_consistency    — how similar the rules are in x-extent
  bold_header_row       — first text band contains bold spans
  caption_found         — "Table N" label above the region
  page_coverage_penalty — region covers too much of page (false-positive guard)
"""

import re
from typing import Dict, List, Optional, Tuple

import fitz
from loguru import logger

from src.tables.detectors.base import CandidateRegion, TableDetector
from src.captions.caption_detector import find_caption
from src.tables.evidence import EvidenceBundle, EvidenceSignal


# --- Tuning constants --------------------------------------------------------

# Minimum x-extent of a line to qualify as a table rule (fraction of page width).
MIN_RULE_WIDTH_FRACTION = 0.25

# Maximum stroke width — very thick lines are decorative borders, not table rules.
MAX_RULE_STROKE_PT = 4.0

# y-distance tolerance for collapsing strokes into one logical rule.
RULE_CLUSTER_PT = 3.0

# x-extent tolerance: two rules belong to the same table if their widths differ
# by less than this fraction of the longer rule's width.
RULE_WIDTH_TOLERANCE = 0.25

# Minimum number of distinct horizontal rules to form a candidate.
MIN_RULES = 2

# Maximum number of rules per candidate (more suggests page decoration).
MAX_RULES = 6

# Text y-band grouping tolerance (same as SpanAlignmentDetector).
ROW_BAND_PT = 4.0

# Minimum gap between consecutive rules (rules that are too close together
# are probably the same double-stroke, not two separate rows).
MIN_RULE_GAP_PT = 8.0

# Maximum gap between consecutive rules belonging to the same table.
# Tables taller than this are probably page-spanning rule artifacts.
MAX_RULE_GAP_PT = 500.0

# Minimum fraction of detected row-slots that must have content.
MIN_CELL_FILL = 0.25

# For two-column candidates: minimum fraction of rows that must have BOTH
# columns filled. Body text false positives (text between decorative rules) have
# rows that alternate between column 1 only and column 2 only (0% dual-fill).
# Real tables have at least some rows where both columns are populated.
# Calibrated against FolkPedagogy_Bruner (iLovePDF, decorative section rules).
MIN_DUAL_COL_FILL_FRAC = 0.20

# Page height fraction above which a candidate is penalised.
LARGE_PAGE_FRACTION = 0.60

# Minimum x-gap to count as a distinct column within a row band.
COL_GAP_PT = 12.0

# Minimum number of columns to consider this a table (not a single-col block).
MIN_TABLE_COLS = 1   # allow single-column — validated by cell fill + rules


class HorizontalRuleDetector(TableDetector):
    """Detect academic three-line tables via horizontal vector rules (medium-high confidence)."""

    @property
    def name(self) -> str:
        return "horizontal_rule"

    def detect(self, fitz_page: fitz.Page, page_number: int) -> List[CandidateRegion]:
        try:
            return self._detect(fitz_page, page_number)
        except Exception as exc:
            logger.warning("HorizontalRuleDetector: error on page {}: {}", page_number, exc)
            return []

    def _detect(self, fitz_page: fitz.Page, page_number: int) -> List[CandidateRegion]:
        page_rect = fitz_page.rect
        page_width = page_rect.width
        page_height = page_rect.height
        min_rule_px = MIN_RULE_WIDTH_FRACTION * page_width

        # Step 1: extract horizontal rule segments
        rules = _extract_horizontal_rules(fitz_page, min_rule_px)
        if len(rules) < MIN_RULES:
            return []

        # Step 2: cluster rules by y-position
        clusters = _cluster_rules_by_y(rules)
        if len(clusters) < MIN_RULES:
            return []

        # Step 3: find groups of clusters that form a table
        try:
            page_dict = fitz_page.get_text("dict")
        except Exception as exc:
            logger.debug("HorizontalRuleDetector: get_text failed on page {}: {}", page_number, exc)
            return []

        groups = _find_rule_groups(clusters, page_width)

        results: List[CandidateRegion] = []
        for group in groups:
            candidate = _build_candidate(
                group, fitz_page, page_dict, page_number, page_width, page_height
            )
            if candidate is not None:
                results.append(candidate)

        return results


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _extract_horizontal_rules(fitz_page: fitz.Page, min_length: float) -> List[Dict]:
    """Return horizontal line segments from vector drawings."""
    rules = []
    try:
        drawings = fitz_page.get_drawings()
    except Exception:
        return []

    for path in drawings:
        stroke_width = path.get("width", 1.0) or 1.0
        if stroke_width > MAX_RULE_STROKE_PT:
            continue

        for item in path.get("items", []):
            kind = item[0]

            if kind == "l":
                # Straight line: item = ('l', p1, p2)
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) > RULE_CLUSTER_PT:
                    continue  # not horizontal
                length = abs(p2.x - p1.x)
                if length < min_length:
                    continue
                rules.append({
                    "y": (p1.y + p2.y) / 2,
                    "x0": min(p1.x, p2.x),
                    "x1": max(p1.x, p2.x),
                    "length": length,
                })

            elif kind == "re":
                # Rectangle: item = ('re', rect, ...)
                rect = item[1]
                if rect.height > MAX_RULE_STROKE_PT * 2:
                    continue  # too tall to be a horizontal rule
                if rect.width < min_length:
                    continue
                rules.append({
                    "y": (rect.y0 + rect.y1) / 2,
                    "x0": rect.x0,
                    "x1": rect.x1,
                    "length": rect.width,
                })

    return rules


def _cluster_rules_by_y(rules: List[Dict]) -> List[Dict]:
    """Collapse rules within RULE_CLUSTER_PT into one representative rule."""
    if not rules:
        return []

    sorted_rules = sorted(rules, key=lambda r: r["y"])
    clusters: List[Dict] = []
    current = list(sorted_rules[:1])

    for rule in sorted_rules[1:]:
        if abs(rule["y"] - current[-1]["y"]) <= RULE_CLUSTER_PT:
            current.append(rule)
        else:
            clusters.append(_merge_rule_cluster(current))
            current = [rule]
    clusters.append(_merge_rule_cluster(current))
    return clusters


def _merge_rule_cluster(rules: List[Dict]) -> Dict:
    """Merge a set of nearly-y-coincident rules into one representative."""
    y_mean = sum(r["y"] for r in rules) / len(rules)
    x0 = min(r["x0"] for r in rules)
    x1 = max(r["x1"] for r in rules)
    return {"y": y_mean, "x0": x0, "x1": x1, "length": x1 - x0}


def _find_rule_groups(clusters: List[Dict], page_width: float) -> List[List[Dict]]:
    """Find groups of clusters that likely belong to the same table.

    Two clusters belong to the same group when:
    - Their y-gap is between MIN_RULE_GAP_PT and MAX_RULE_GAP_PT
    - Their x-extents overlap with similarity > (1 - RULE_WIDTH_TOLERANCE)
    """
    if len(clusters) < MIN_RULES:
        return []

    sorted_clusters = sorted(clusters, key=lambda c: c["y"])
    groups: List[List[Dict]] = []
    i = 0

    while i < len(sorted_clusters):
        group = [sorted_clusters[i]]
        j = i + 1
        while j < len(sorted_clusters) and len(group) < MAX_RULES:
            gap = sorted_clusters[j]["y"] - group[-1]["y"]
            if gap < MIN_RULE_GAP_PT:
                j += 1
                continue
            if gap > MAX_RULE_GAP_PT:
                break
            if _x_extents_compatible(group[-1], sorted_clusters[j]):
                group.append(sorted_clusters[j])
            j += 1

        if len(group) >= MIN_RULES:
            groups.append(group)
            i = j  # skip the clusters we consumed
        else:
            i += 1

    return groups


def _x_extents_compatible(a: Dict, b: Dict) -> bool:
    """Return True if two rules have similar x-extents (same table)."""
    longer = max(a["length"], b["length"])
    if longer == 0:
        return False
    overlap_x0 = max(a["x0"], b["x0"])
    overlap_x1 = min(a["x1"], b["x1"])
    overlap = max(0.0, overlap_x1 - overlap_x0)
    return overlap / longer >= (1.0 - RULE_WIDTH_TOLERANCE)


def _build_candidate(
    group: List[Dict],
    fitz_page: fitz.Page,
    page_dict: dict,
    page_number: int,
    page_width: float,
    page_height: float,
) -> Optional[CandidateRegion]:
    """Convert one rule-group into a CandidateRegion with evidence."""
    y_top = group[0]["y"]
    y_bot = group[-1]["y"]
    x0 = min(r["x0"] for r in group)
    x1 = max(r["x1"] for r in group)
    bbox = (x0, y_top, x1, y_bot)

    # Extract text between rules
    raw_rows, col_count = _extract_cell_grid(page_dict, group, x0, x1)

    # Cell fill check
    total_cells = max(len(raw_rows) * max(col_count, 1), 1)
    filled_cells = sum(1 for row in raw_rows for cell in row if cell.strip())
    cell_fill = filled_cells / total_cells

    if cell_fill < MIN_CELL_FILL:
        return None  # table body appears empty — probably page decorations

    # Dual-column fill guard: body text between decorative rules (e.g. iLovePDF
    # footnote/section separators) produces rows that alternate between col-1-only
    # and col-2-only fill (0% simultaneous fill). Real 2-column tables have most
    # rows with both columns populated.
    if col_count == 2 and len(raw_rows) >= 2:
        both_filled = sum(
            1 for row in raw_rows
            if sum(1 for cell in row if cell.strip()) >= 2
        )
        if both_filled / len(raw_rows) < MIN_DUAL_COL_FILL_FRAC:
            return None

    bundle = _build_evidence(group, raw_rows, col_count, cell_fill, y_bot - y_top, page_height, page_dict, bbox, x0, x1)

    caption, caption_score = find_caption(page_dict, bbox, page_width)
    if caption_score > 0:
        bundle.add(EvidenceSignal(
            name="caption_found",
            score=caption_score,
            weight=0.5,
            note=f"Caption above region: {caption[:50]!r}" if caption else "caption signal",
        ))

    return CandidateRegion(
        page_number=page_number,
        bbox=bbox,
        evidence=bundle,
        raw_rows=raw_rows,
        caption=caption,
    )


def _extract_cell_grid(
    page_dict: dict,
    group: List[Dict],
    bbox_x0: float,
    bbox_x1: float,
) -> Tuple[List[List[str]], int]:
    """Extract text spans between horizontal rules as a cell grid."""
    # Build y-band boundaries from rule y-positions
    rule_ys = [r["y"] for r in group]

    # Collect spans in the table x-extent and between first/last rule
    table_spans = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue
                sx0, sy0, sx1, sy1 = span.get("bbox", (0, 0, 0, 0))
                mid_y = (sy0 + sy1) / 2
                mid_x = (sx0 + sx1) / 2
                # Must be within the horizontal extent of the rules
                if mid_x < bbox_x0 - 10 or mid_x > bbox_x1 + 10:
                    continue
                # Must be between first and last rule
                if mid_y < rule_ys[0] or mid_y > rule_ys[-1]:
                    continue
                # Must not be ON a rule (within RULE_CLUSTER_PT of any rule)
                if any(abs(mid_y - ry) < RULE_CLUSTER_PT for ry in rule_ys):
                    continue
                flags = span.get("flags", 0)
                font = span.get("font", "").lower()
                is_bold = bool(flags & (2 ** 4)) or "bold" in font
                table_spans.append({
                    "x0": sx0, "y0": sy0, "x1": sx1, "y1": sy1,
                    "text": text, "is_bold": is_bold,
                })

    if not table_spans:
        return [], 0

    # Group spans into row-bands
    sorted_spans = sorted(table_spans, key=lambda s: (round(s["y0"]), s["x0"]))
    bands: List[List[Dict]] = []
    current_band: List[Dict] = [sorted_spans[0]]
    current_y = sorted_spans[0]["y0"]

    for span in sorted_spans[1:]:
        if abs(span["y0"] - current_y) <= ROW_BAND_PT:
            current_band.append(span)
        else:
            bands.append(current_band)
            current_band = [span]
            current_y = span["y0"]
    bands.append(current_band)

    # Determine columns by clustering x0 positions across all spans
    all_x0 = [s["x0"] for s in table_spans]
    col_positions = _cluster_x0_values(all_x0, COL_GAP_PT)
    if not col_positions:
        return [], 0

    # Build cell grid
    raw_rows: List[List[str]] = []
    for band in bands:
        row = [""] * len(col_positions)
        for span in band:
            best_col = min(range(len(col_positions)), key=lambda c: abs(span["x0"] - col_positions[c]))
            sep = " " if row[best_col] else ""
            row[best_col] = row[best_col] + sep + span["text"]
        raw_rows.append(row)

    return raw_rows, len(col_positions)


def _cluster_x0_values(x0_vals: List[float], gap: float) -> List[float]:
    """Cluster x0 positions into column representatives."""
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


def _build_evidence(
    group: List[Dict],
    raw_rows: List[List[str]],
    col_count: int,
    cell_fill: float,
    height: float,
    page_height: float,
    page_dict: dict,
    bbox: tuple,
    bbox_x0: float,
    bbox_x1: float,
) -> EvidenceBundle:
    bundle = EvidenceBundle()
    n_rules = len(group)
    n_rows = len(raw_rows)

    # --- Horizontal rules presence ---
    rule_score = min(1.0, (n_rules - 1) / 3.0)  # 2→0.33, 3→0.67, 4+→1.0
    bundle.add(EvidenceSignal(
        name="horizontal_rules",
        score=rule_score,
        weight=1.0,
        note=f"{n_rules} horizontal rules spanning ≥{MIN_RULE_WIDTH_FRACTION:.0%} of page width",
    ))

    # --- Three-line pattern (top + header-divider + bottom) ---
    if n_rules == 3:
        gap_top_mid = group[1]["y"] - group[0]["y"]
        gap_mid_bot = group[2]["y"] - group[1]["y"]
        # Classic three-line: mid-rule closer to top rule than bottom (header spacing)
        if 8 < gap_top_mid < 50 and gap_mid_bot > gap_top_mid:
            bundle.add(EvidenceSignal(
                name="three_line_pattern",
                score=1.0,
                weight=0.9,
                note="Classic Booktabs three-line table pattern detected",
            ))

    # --- Rule x-extent consistency ---
    lengths = [r["length"] for r in group]
    max_len = max(lengths)
    min_len = min(lengths)
    consistency = min_len / max_len if max_len > 0 else 0.0
    bundle.add(EvidenceSignal(
        name="rule_x_consistency",
        score=consistency,
        weight=0.6,
        note=f"Rule x-extents vary by {(1-consistency):.0%}",
    ))

    # --- Text between rules ---
    fill_score = min(1.0, cell_fill / 0.5)
    bundle.add(EvidenceSignal(
        name="text_between_rules",
        score=fill_score,
        weight=0.8,
        note=f"{cell_fill:.0%} of cell slots contain text",
    ))

    # --- Column count ---
    col_score = min(1.0, max(0.0, (col_count - 1) / 4.0))
    bundle.add(EvidenceSignal(
        name="column_count",
        score=col_score,
        weight=0.4,
        note=f"{col_count} text column(s) detected between rules",
    ))

    # --- Row count ---
    row_score = min(1.0, (n_rows - 1) / 5.0) if n_rows > 1 else 0.1
    bundle.add(EvidenceSignal(
        name="row_count",
        score=row_score,
        weight=0.3,
        note=f"{n_rows} text row(s) detected",
    ))

    # --- Bold header row ---
    if raw_rows:
        first_band_y_approx = group[0]["y"]
        first_band_bold = _first_band_is_bold(page_dict, first_band_y_approx, bbox_x0, bbox_x1)
        if first_band_bold:
            bundle.add(EvidenceSignal(
                name="bold_header_row",
                score=1.0,
                weight=0.4,
                note="First text band between rules contains bold spans",
            ))

    # --- Page coverage penalty ---
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


def _first_band_is_bold(page_dict: dict, rule_y: float, x0: float, x1: float) -> bool:
    """Return True if there are bold spans just below the top/first rule."""
    search_top = rule_y
    search_bot = rule_y + 30.0
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                sx0, sy0, sx1, sy1 = span.get("bbox", (0, 0, 0, 0))
                mid_y = (sy0 + sy1) / 2
                mid_x = (sx0 + sx1) / 2
                if not (search_top < mid_y < search_bot):
                    continue
                if mid_x < x0 or mid_x > x1:
                    continue
                flags = span.get("flags", 0)
                font = span.get("font", "").lower()
                if bool(flags & (2 ** 4)) or "bold" in font:
                    return True
    return False
