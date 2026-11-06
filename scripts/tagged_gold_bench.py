"""Score RAWRS against PDFs that people already made accessible.

For each PDF in --pdfs: keep it only if it is worth it (passes veraPDF
PDF/UA-1, has real headings, no filler alt text), read its tags as the gold
answer, strip the tags, run RAWRS on the bare file, and compare.

    python scripts/tagged_gold_bench.py --pdfs <dir> --out outputs/tagged_gold
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdfs", required=True)
    parser.add_argument("--out", default="outputs/tagged_gold")
    parser.add_argument("--vet-only", action="store_true", help="vet the files, do not run RAWRS")
    args = parser.parse_args()

    from src.benchmark import tagged_gold
    from src.docx import pdf_export
    from src.pipeline.phase1_pipeline import run_pipeline

    out = Path(args.out)
    (out / "stripped").mkdir(parents=True, exist_ok=True)
    report = {}
    for pdf in sorted(Path(args.pdfs).glob("*.pdf")):
        vera = pdf_export.verapdf_verdict(pdf)
        gold = tagged_gold.read_gold(pdf)
        reasons = tagged_gold.worth_it(gold, (vera or {}).get("compliant"))
        entry = {"kept": not reasons, "rejected_because": reasons, "gold_headings": len(gold["headings"]),
                 "gold_figures": len(gold["figures"]), "gold_tables": gold["tables"]}
        print(f"{pdf.name}: {'KEEP' if not reasons else 'reject: ' + '; '.join(reasons)}", flush=True)
        if not reasons and not args.vet_only:
            bare = out / "stripped" / pdf.name
            tagged_gold.strip_tags(pdf, bare)
            result = run_pipeline(bare, output_root=out / "rawrs", enable_ocr=True)
            document = result.document
            headings = tagged_gold.docx_headings(result.docx_path) if result.docx_path else []
            # Placeholders stay PENDING_REVIEW; only text a model wrote counts.
            alts = [i.figure.alt_text for i in (document.images if document else [])
                    if i.figure and i.figure.alt_text and i.figure.alt_text_status == "ai_generated"]
            entry.update(success=result.success, seconds=round(result.duration_seconds, 1),
                         gold=gold, **tagged_gold.score(gold, headings, alts))
            print(f"  {json.dumps({k: entry[k] for k in ('headings', 'alt_text')})}", flush=True)
        report[pdf.name] = entry
        (out / "results.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
