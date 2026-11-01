"""Run the benchmark corpus through the real pipeline and aggregate automation metrics.

    python scripts/run_corpus_metrics.py [--pdfs DIR] [--gold DIR] [--out DIR]

Production settings: OCR on, OCR cache off (cold timings). Each document's
similarity to its human-remediated DOCX is stored as the separate, labelled
estimate (src/benchmark/differ.py); it never feeds the measured numbers.
The human-remediated DOCX files are copyrighted and gitignored (the PDFs are
tracked for CI): never commit them or the outputs (outputs/ is gitignored).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("RAWRS_OCR_CACHE", "off")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EXPECTED_DOCUMENTS = 10
ESTIMATE_KEYS = ("heading_precision", "heading_recall", "heading_f1", "footnote_placement_accuracy",
                 "figure_count_fidelity", "table_count_fidelity", "front_page_similarity")


def _require(directory: Path, pattern: str) -> list[Path]:
    files = sorted(directory.glob(pattern))
    if len(files) != EXPECTED_DOCUMENTS:
        sys.exit(f"Expected {EXPECTED_DOCUMENTS} {pattern} files in {directory}, found {len(files)}. "
                 "Copy the gitignored corpus first (gh codespace cp -r -e).")
    return files


def _flatten(metrics: dict) -> dict:
    flat = {f"heading_{k}": v for k, v in metrics["heading"].items()}
    flat.update({k: v for k, v in metrics.items() if not isinstance(v, dict)})
    return {k: flat[k] for k in ESTIMATE_KEYS if k in flat}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdfs", default="samples/benchmark/pdfs")
    parser.add_argument("--gold", default="samples/benchmark/remediated_docx")
    parser.add_argument("--out", default="outputs/corpus_metrics")
    args = parser.parse_args()
    pdfs, gold_dir, out = _require(Path(args.pdfs), "*.pdf"), Path(args.gold), Path(args.out)
    _require(gold_dir, "*.docx")

    from src.benchmark.differ import _best_match, metrics, profile_from_docx
    from src.metrics.__main__ import main as print_aggregate
    from src.metrics.automation import set_estimate, sidecar_path
    from src.pipeline.phase1_pipeline import run_pipeline

    for pdf in pdfs:
        result = run_pipeline(pdf, output_root=out, enable_ocr=True)
        print(f"{'OK  ' if result.success else 'FAIL'} {result.duration_seconds:8.1f} s  {pdf.name}", flush=True)

    rawrs = sorted((out / "docx").glob("*.docx"))
    for gold in sorted(gold_dir.glob("*.docx")):
        match = _best_match(gold.name, rawrs)
        if match is None:
            print(f"no RAWRS DOCX matches {gold.name}: no estimate for it")
            continue
        estimate = _flatten(metrics(profile_from_docx(gold), profile_from_docx(match)))
        set_estimate(sidecar_path(out, match.stem), {"gold": gold.name, **estimate})
    return print_aggregate([str(out)])


if __name__ == "__main__":
    sys.exit(main())
