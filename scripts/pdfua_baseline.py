"""PDF/UA-1 baseline: veraPDF on each corpus PDF, before and after OpenDataLoader auto-tagging.

    python scripts/pdfua_baseline.py --pdfs samples/benchmark/pdfs --verapdf /path/to/verapdf --out result.json

Research for the startup plan and Task 3: how far does a free Apache-2.0 auto-tagger
(opendataloader-pdf, local mode, no AI backend) get the corpus toward PDF/UA-1?
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


def verapdf_failures(verapdf: str, pdf: Path) -> dict:
    """Failed PDF/UA-1 rules: {"compliant": bool, "rules": {"clause-test": [failed_checks, description]}}."""
    xml = subprocess.run([verapdf, "--flavour", "ua1", "--format", "mrr", str(pdf)],
                         capture_output=True, text=True, timeout=900).stdout
    root = ET.fromstring(xml[xml.index("<"):])
    report = root.find(".//validationReport")
    if report is None:
        return {"compliant": False, "error": (root.findtext(".//exceptionMessage") or "no report")[:200], "rules": {}}
    rules = {}
    for rule in report.iter("rule"):
        if rule.get("status") == "failed":
            key = f"{rule.get('clause')}-{rule.get('testNumber')}"
            rules[key] = [int(rule.get("failedChecks", 0)), (rule.findtext("description") or "").strip()[:160]]
    return {"compliant": report.get("isCompliant") == "true", "rules": rules}


def fix_metadata(src: Path, dst: Path, lang: str = "en") -> None:
    """The mechanical PDF/UA-1 fixes: language, title, XMP with pdfuaid, DisplayDocTitle, Tabs=S.

    ponytail: corpus is English, so lang is fixed; a product run would use the detected language.
    """
    import pikepdf

    with pikepdf.open(src) as pdf:
        title = str(pdf.docinfo.get("/Title", "")) or src.stem
        pdf.Root.Lang = pikepdf.String(lang)
        pdf.Root.ViewerPreferences = pikepdf.Dictionary(DisplayDocTitle=True)
        pdf.docinfo["/Title"] = title
        with pdf.open_metadata() as meta:
            meta["dc:title"] = title
            meta["pdfuaid:part"] = "1"
        for page in pdf.pages:
            if "/Annots" in page.obj:
                page.obj.Tabs = pikepdf.Name.S
        pdf.save(dst)


def _text_chars(pdf: Path) -> int:
    import pypdfium2

    doc = pypdfium2.PdfDocument(str(pdf))
    try:
        return sum(len(doc[i].get_textpage().get_text_range().strip()) for i in range(len(doc)))
    finally:
        doc.close()


def main() -> int:
    import opendataloader_pdf

    p = argparse.ArgumentParser()
    p.add_argument("--pdfs", required=True)
    p.add_argument("--verapdf", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--work", default="/tmp/odl_out")
    a = p.parse_args()
    rows = {}
    for pdf in sorted(Path(a.pdfs).glob("*.pdf")):
        work = Path(a.work) / pdf.stem
        work.mkdir(parents=True, exist_ok=True)
        start = time.perf_counter()
        err = ""
        try:
            opendataloader_pdf.convert(input_path=[str(pdf)], output_dir=str(work), format="tagged-pdf")
            tagged = next(iter(sorted(work.glob("*.pdf"))), None)
        except Exception as exc:  # report and keep going
            tagged, err = None, f"{type(exc).__name__}: {exc}"[:200]
        seconds = time.perf_counter() - start
        fixed = work / "fixed.pdf"
        if tagged:
            fix_metadata(tagged, fixed)
        rows[pdf.name] = {"before": verapdf_failures(a.verapdf, pdf), "tag_seconds": seconds,
                          "after": verapdf_failures(a.verapdf, tagged) if tagged else {"error": err or "no output"},
                          "after_fix": verapdf_failures(a.verapdf, fixed) if tagged else {"error": "no output"}}
        # A scan with no text layer can pass veraPDF and still be unreadable to a screen reader.
        rows[pdf.name]["text_chars"] = _text_chars(fixed) if tagged else 0
        b, t, f = (rows[pdf.name][k] for k in ("before", "after", "after_fix"))
        print(pdf.name[:40], "before", len(b.get("rules", {})), "after", len(t.get("rules", {})),
              "after_fix", len(f.get("rules", {})), "compliant", f.get("compliant"), f"{seconds:.0f}s", flush=True)
        Path(a.out).write_text(json.dumps(rows, indent=1), encoding="utf-8")
    for stage in ("after", "after_fix"):
        left = Counter(k for r in rows.values() for k in r[stage].get("rules", {}))
        print(f"failed rules, {stage}:", left.most_common(12))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
