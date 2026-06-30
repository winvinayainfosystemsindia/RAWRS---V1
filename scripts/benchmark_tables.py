"""Table detection benchmark — FEATURE_015.3 Part B.

Measures precision, recall, F1, TP/FP/FN per PDF across the benchmark corpus
and writes a machine-readable JSON report.

Usage:
    python scripts/benchmark_tables.py [--out PATH]

    --out  Path to write JSON report (default: docs/benchmark_tables_report.json)

Only born-digital PDFs are measured — OCR pages cannot run table detection
(no reliable vector graphics or span positions).

Ground truth is the manifest `tables` flag (binary: has tables / no tables).
When `expected_table_count` is present in the manifest entry, count-level
precision/recall is also computed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = REPO_ROOT / "samples" / "benchmark" / "pdfs"
MANIFEST_PATH = REPO_ROOT / "samples" / "benchmark" / "manifest.json"
DEFAULT_REPORT = REPO_ROOT / "docs" / "benchmark_tables_report.json"

sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------

def _run_pipeline(pdf_path: Path) -> List[Any]:
    """Run the full pre-table-detection pipeline on one PDF; return Table list."""
    from src.parser.pdf_parser import parse_pdf
    from src.ocr.extractor import extract_text
    from src.ocr.router import route_pages
    from src.structure.structure_detector import detect_structure
    from src.tables.table_extractor import extract_tables

    doc = parse_pdf(pdf_path)
    doc = extract_text(doc)
    doc = route_pages(doc)
    doc = detect_structure(doc)
    return extract_tables(doc, pdf_path)


# ---------------------------------------------------------------------------
# Detector contribution helpers
# ---------------------------------------------------------------------------

def _detector_contributions(tables: List[Any]) -> Dict[str, int]:
    """Count how many tables each detector contributed evidence signals for."""
    counts: Dict[str, int] = {
        "vector_border": 0,
        "horizontal_rule": 0,
        "span_alignment": 0,
        "column_alignment": 0,
    }
    for t in tables:
        signal_names = {s.get("name", "") if isinstance(s, dict) else s.name
                        for s in t.evidence_signals}
        if "vector_borders" in signal_names:
            counts["vector_border"] += 1
        if "horizontal_rules" in signal_names:
            counts["horizontal_rule"] += 1
        if "span_column_alignment" in signal_names:
            counts["span_alignment"] += 1
        if "column_x_alignment" in signal_names:
            counts["column_alignment"] += 1
    return counts


def _avg_confidence(tables: List[Any]) -> Optional[float]:
    if not tables:
        return None
    return round(sum(t.confidence for t in tables) / len(tables), 4)


# ---------------------------------------------------------------------------
# Per-PDF measurement
# ---------------------------------------------------------------------------

def _measure_pdf(name: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    pdf_path = BENCHMARK_DIR / name
    has_tables_ground_truth: bool = bool(entry.get("tables", False))
    expected_count: Optional[int] = entry.get("expected_table_count")
    is_born_digital: bool = bool(entry.get("born_digital", False))

    result: Dict[str, Any] = {
        "name": name,
        "born_digital": is_born_digital,
        "ground_truth_has_tables": has_tables_ground_truth,
        "expected_table_count": expected_count,
        "skipped": False,
        "skip_reason": None,
        "detected_count": None,
        "avg_confidence": None,
        "detector_contributions": None,
        "binary_tp": None,
        "binary_fp": None,
        "binary_fn": None,
        "count_tp": None,
        "count_fp": None,
        "count_fn": None,
        "error": None,
        "elapsed_s": None,
    }

    if not is_born_digital:
        result["skipped"] = True
        result["skip_reason"] = "ocr_required — table detection not run on OCR pages"
        return result

    if not pdf_path.exists():
        result["skipped"] = True
        result["skip_reason"] = f"PDF not found on disk: {pdf_path}"
        return result

    t0 = time.monotonic()
    try:
        tables = _run_pipeline(pdf_path)
    except Exception as exc:
        result["error"] = str(exc)
        result["elapsed_s"] = round(time.monotonic() - t0, 2)
        return result

    elapsed = round(time.monotonic() - t0, 2)
    detected = len(tables)

    # Binary classification metrics (ground truth: does the PDF have tables?)
    detected_any = detected > 0
    binary_tp = int(has_tables_ground_truth and detected_any)
    binary_fp = int((not has_tables_ground_truth) and detected_any)
    binary_fn = int(has_tables_ground_truth and (not detected_any))

    # Count-level metrics (only when expected_table_count is set)
    count_tp = count_fp = count_fn = None
    if expected_count is not None:
        # TP = min(detected, expected), FN = max(0, expected - detected), FP = max(0, detected - expected)
        count_tp = min(detected, expected_count)
        count_fn = max(0, expected_count - detected)
        count_fp = max(0, detected - expected_count)

    result.update({
        "detected_count": detected,
        "avg_confidence": _avg_confidence(tables),
        "detector_contributions": _detector_contributions(tables),
        "binary_tp": binary_tp,
        "binary_fp": binary_fp,
        "binary_fn": binary_fn,
        "count_tp": count_tp,
        "count_fp": count_fp,
        "count_fn": count_fn,
        "elapsed_s": elapsed,
    })
    return result


# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------

def _aggregate(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    measured = [r for r in results if not r["skipped"] and r["error"] is None]

    # Binary
    tp = sum(r["binary_tp"] for r in measured if r["binary_tp"] is not None)
    fp = sum(r["binary_fp"] for r in measured if r["binary_fp"] is not None)
    fn = sum(r["binary_fn"] for r in measured if r["binary_fn"] is not None)

    precision = tp / (tp + fp) if (tp + fp) > 0 else None
    recall = tp / (tp + fn) if (tp + fn) > 0 else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision is not None and recall is not None and (precision + recall) > 0
          else None)

    # Count-level (only PDFs with expected_table_count)
    count_measured = [r for r in measured if r["count_tp"] is not None]
    count_tp = sum(r["count_tp"] for r in count_measured)
    count_fp = sum(r["count_fp"] for r in count_measured)
    count_fn = sum(r["count_fn"] for r in count_measured)
    count_precision = count_tp / (count_tp + count_fp) if (count_tp + count_fp) > 0 else None
    count_recall = count_tp / (count_tp + count_fn) if (count_tp + count_fn) > 0 else None
    count_f1 = (2 * count_precision * count_recall / (count_precision + count_recall)
                if count_precision is not None and count_recall is not None
                and (count_precision + count_recall) > 0
                else None)

    # Detector breakdown
    def _sum_contrib(key: str) -> int:
        return sum(r["detector_contributions"][key] for r in measured
                   if r["detector_contributions"] is not None)

    return {
        "total_pdfs": len(results),
        "measured_pdfs": len(measured),
        "skipped_pdfs": sum(1 for r in results if r["skipped"]),
        "errored_pdfs": sum(1 for r in results if r["error"] is not None),
        "binary_precision": round(precision, 4) if precision is not None else None,
        "binary_recall": round(recall, 4) if recall is not None else None,
        "binary_f1": round(f1, 4) if f1 is not None else None,
        "binary_tp": tp,
        "binary_fp": fp,
        "binary_fn": fn,
        "count_precision": round(count_precision, 4) if count_precision is not None else None,
        "count_recall": round(count_recall, 4) if count_recall is not None else None,
        "count_f1": round(count_f1, 4) if count_f1 is not None else None,
        "count_tp": count_tp,
        "count_fp": count_fp,
        "count_fn": count_fn,
        "detector_totals": {
            "vector_border": _sum_contrib("vector_border"),
            "horizontal_rule": _sum_contrib("horizontal_rule"),
            "span_alignment": _sum_contrib("span_alignment"),
            "column_alignment": _sum_contrib("column_alignment"),
        },
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _print_summary(aggregate: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 60)
    print("TABLE DETECTION BENCHMARK REPORT")
    print("=" * 60)
    print(f"  PDFs measured:  {aggregate['measured_pdfs']} / {aggregate['total_pdfs']}")
    print(f"  Skipped:        {aggregate['skipped_pdfs']} (OCR-only)")
    print(f"  Errors:         {aggregate['errored_pdfs']}")
    print()
    print("  Binary (any-tables) metrics:")
    p = aggregate["binary_precision"]
    r = aggregate["binary_recall"]
    f = aggregate["binary_f1"]
    print(f"    Precision: {p:.4f}" if p is not None else "    Precision: N/A")
    print(f"    Recall:    {r:.4f}" if r is not None else "    Recall:    N/A")
    print(f"    F1:        {f:.4f}" if f is not None else "    F1:        N/A")
    print(f"    TP={aggregate['binary_tp']}  FP={aggregate['binary_fp']}  FN={aggregate['binary_fn']}")
    print()
    print("  Count-level metrics (PDFs with expected_table_count):")
    cp = aggregate["count_precision"]
    cr = aggregate["count_recall"]
    cf = aggregate["count_f1"]
    print(f"    Precision: {cp:.4f}" if cp is not None else "    Precision: N/A")
    print(f"    Recall:    {cr:.4f}" if cr is not None else "    Recall:    N/A")
    print(f"    F1:        {cf:.4f}" if cf is not None else "    F1:        N/A")
    print(f"    TP={aggregate['count_tp']}  FP={aggregate['count_fp']}  FN={aggregate['count_fn']}")
    print()
    print("  Detector contributions (tables carrying each signal):")
    dt = aggregate["detector_totals"]
    print(f"    VectorBorderDetector:    {dt['vector_border']}")
    print(f"    HorizontalRuleDetector:  {dt['horizontal_rule']}")
    print(f"    SpanAlignmentDetector:   {dt['span_alignment']}")
    print(f"    ColumnAlignmentDetector: {dt['column_alignment']}")
    print()
    print("  Per-PDF breakdown:")
    for r in results:
        if r["skipped"]:
            status = "SKIP"
        elif r["error"]:
            status = "ERR "
        else:
            tp_mark = "TP" if r["binary_tp"] else ""
            fp_mark = "FP" if r["binary_fp"] else ""
            fn_mark = "FN" if r["binary_fn"] else ""
            classification = "/".join(x for x in [tp_mark, fp_mark, fn_mark] if x) or "TN"
            status = f"{classification:<4}"
        detected = r["detected_count"]
        count_str = f"detected={detected}" if detected is not None else ""
        conf_str = f"avg_conf={r['avg_confidence']}" if r["avg_confidence"] is not None else ""
        parts = [x for x in [count_str, conf_str] if x]
        detail = "  ".join(parts) if parts else (r["skip_reason"] or r["error"] or "")
        print(f"    [{status}] {r['name'][:50]:<50}  {detail}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Run table detection benchmark")
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT,
                        help=f"Path to write JSON report (default: {DEFAULT_REPORT})")
    args = parser.parse_args()

    with open(MANIFEST_PATH, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)["pdfs"]

    results: List[Dict[str, Any]] = []
    for name, entry in sorted(manifest.items()):
        print(f"  Processing: {name[:60]}", end="", flush=True)
        result = _measure_pdf(name, entry)
        elapsed = result.get("elapsed_s")
        if result["skipped"]:
            print(f"  SKIP ({result['skip_reason']})")
        elif result["error"]:
            print(f"  ERROR: {result['error']}")
        else:
            print(f"  {result['detected_count']} table(s)  [{elapsed}s]")
        results.append(result)

    aggregate = _aggregate(results)

    report = {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "aggregate": aggregate,
        "per_pdf": results,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    _print_summary(aggregate, results)
    print(f"\n  Report written to: {args.out}")


if __name__ == "__main__":
    main()
