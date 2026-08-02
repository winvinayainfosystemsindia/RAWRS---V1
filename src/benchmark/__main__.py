"""CLI for the benchmark harness.

Two modes, answering the two questions of
docs/ADR_PROJECTION_CORRECTNESS_2026-08-03.md §6:

**Layer 1 — projection correctness** (hard gate, no ground truth needed)::

    python -m src.benchmark --projection <pdf_dir> [--out report.json]

Runs the pipeline over each PDF and verifies that the Markdown it produced
expresses the Semantic Document behind it: nothing lost, nothing invented,
nothing suppressed without a recorded fact. Exits non-zero on any violation.
Applies to any document, not only the benchmark corpus.

**Layer 2 — detector quality** (graded, needs the human corpus)::

    python -m src.benchmark <rawrs_docx_dir> [--benchmark <dir>] [--out report.json]

Compares every human-remediated benchmark DOCX against the matching
RAWRS-generated DOCX and prints the corpus-level remediation-gap metrics.

Read-only in both modes.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from src.benchmark.differ import run_corpus

_DEFAULT_BENCHMARK = Path("samples/benchmark/remediated_docx")


def _run_projection(pdf_dir: str, out: str | None) -> int:
    # Imported here, not at module scope: this mode drives the whole pipeline,
    # and the DOCX-differ mode must stay importable without it.
    from src.benchmark.projection import check_projection, summarize
    from src.pipeline.phase1_pipeline import run_pipeline

    pdfs = sorted(Path(pdf_dir).glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {pdf_dir}")
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        reports = []
        for pdf in pdfs:
            result = run_pipeline(pdf, output_root=Path(tmp), enable_ocr=False)
            markdown = (Path(tmp) / "markdown" / f"{pdf.stem}.md").read_text(encoding="utf-8")
            report = check_projection(result.document, markdown, name=pdf.name)
            reports.append(report)
            status = "OK  " if report.ok else "FAIL"
            print(f"{status} {pdf.name[:56]:<58} {report.by_kind() or ''}")

        summary = summarize(reports)

    print(f"\nprojection correctness: ok={summary['ok']}")
    if summary["violations_by_kind"]:
        print(f"  violations (blocking): {summary['violations_by_kind']}")
    if summary["findings_by_kind"]:
        print(f"  findings (Layer 2, non-blocking): {summary['findings_by_kind']}")
    if out:
        Path(out).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nFull report written to {out}")
    return 0 if summary["ok"] else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="RAWRS benchmark harness.")
    ap.add_argument(
        "rawrs_docx_dir",
        nargs="?",
        help="Directory of RAWRS-generated .docx outputs (detector-quality mode).",
    )
    ap.add_argument(
        "--projection",
        metavar="PDF_DIR",
        help="Run projection-correctness checks over every PDF in this directory.",
    )
    ap.add_argument(
        "--benchmark",
        default=str(_DEFAULT_BENCHMARK),
        help="Directory of human-remediated benchmark .docx.",
    )
    ap.add_argument("--out", default=None, help="Write the full JSON report here.")
    args = ap.parse_args()

    if args.projection:
        sys.exit(_run_projection(args.projection, args.out))

    if not args.rawrs_docx_dir:
        ap.error("give either a rawrs_docx_dir (detector quality) or --projection PDF_DIR")

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
