"""python -m src.metrics [outputs_dir] [--json]: aggregate automation metrics.

Measured figures and the estimate are printed in separate sections and are
never combined. See src/metrics/automation.py for the definitions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.metrics.automation import aggregate


def _rate_line(name: str, rate: dict) -> str:
    if rate.get("status") != "measured":
        return f"  {name}: {rate.get('status')} (documents={rate.get('documents', 0)}, items={rate.get('items', 0)})"
    return (f"  {name}: median {rate['median_document_pct']}% per document, pooled {rate['pooled_pct']}% "
            f"(documents={rate['documents']}, items={rate['items']}; Wilson low {rate['wilson_low_pct']}%, "
            f"{rate['wilson_note']})")


def _print(report: dict) -> None:
    m = report["measured"]
    print(f"Documents with metrics: {report['documents']} (unreadable sidecars: {report['unreadable_sidecars']})")
    print("MEASURED")
    print(_rate_line("(a) decided without asking a human", m["decided_without_human"]))
    kept = m["reviewer_kept_unchanged"]
    print(_rate_line("(b) reviewer kept unchanged", kept)
          + f" [human-reviewed documents: {kept['human_reviewed_documents']}, minimum {kept['min_reviewed_documents']}]")
    c = m["checks"]
    print(f"  checks: pass {c['pass']}, fail {c['fail']}, needs human {c['needs_human']}, n/a {c['not_applicable']}")
    print(_rate_line("  check pass rate", c["pass_rate"]) + f"  [{c['note']}]")
    t = m["timing"]
    print(f"  timing: median {t['median_total_seconds']} s, max {t['max_total_seconds']} s per document; "
          f"median per stage {t['median_stage_seconds']}")
    print(f"  review time: {m['review_time']}")
    i = m["independent"]
    print(f"  {i['label']}: {i['pdfua1_compliant']}/{i['documents_validated']} pass PDF/UA-1, "
          f"{i['documents_with_no_text']} with no text (exported: {i['documents_exported']})")
    print("  items at pipeline end, by category:")
    for category, buckets in m["snapshot_by_category"].items():
        print(f"    {category:<14} {buckets}")
    print("ESTIMATE (not a measurement of reviewer behaviour)")
    e = report["estimate"]
    print(f"  {e['label']}: documents={e['documents']} {e['mean']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.metrics", description=__doc__)
    parser.add_argument("outputs", nargs="?", default="outputs")
    parser.add_argument("--json", action="store_true", help="print the full JSON report")
    args = parser.parse_args(argv)
    if not Path(args.outputs).is_dir():
        print(f"No such directory: {args.outputs}", file=sys.stderr)
        return 2
    report = aggregate(Path(args.outputs))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
