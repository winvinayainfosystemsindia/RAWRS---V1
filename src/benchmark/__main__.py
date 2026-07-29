"""CLI for the Benchmark Differ (F0).

Usage:
    python -m src.benchmark <rawrs_docx_dir> [--benchmark <dir>] [--out report.json]

Compares every human-remediated benchmark DOCX against the matching
RAWRS-generated DOCX and prints the corpus-level remediation-gap metrics
(optionally writing the full machine-readable report to --out).

Read-only. Running RAWRS to produce <rawrs_docx_dir> is a separate step; this
tool only measures.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.benchmark.differ import run_corpus

_DEFAULT_BENCHMARK = Path("samples/benchmark/remediated_docx")


def main() -> None:
    ap = argparse.ArgumentParser(description="RAWRS benchmark remediation-gap differ (F0).")
    ap.add_argument("rawrs_docx_dir", help="Directory of RAWRS-generated .docx outputs.")
    ap.add_argument("--benchmark", default=str(_DEFAULT_BENCHMARK), help="Directory of human-remediated benchmark .docx.")
    ap.add_argument("--out", default=None, help="Write the full JSON report here.")
    args = ap.parse_args()

    report = run_corpus(args.benchmark, args.rawrs_docx_dir, out_path=args.out)
    print(json.dumps(report["corpus"], indent=2))
    if report.get("unmatched_benchmark_documents"):
        print("\nUnmatched benchmark documents (no RAWRS output found):")
        for name in report["unmatched_benchmark_documents"]:
            print(f"  - {name}")
    if args.out:
        print(f"\nFull report written to {args.out}")


if __name__ == "__main__":
    main()
