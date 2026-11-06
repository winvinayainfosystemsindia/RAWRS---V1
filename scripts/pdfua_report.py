"""Task 3 table: veraPDF PDF/UA-1 verdicts of the exported PDFs, by checklist check.

    python scripts/pdfua_report.py [outputs/corpus_pdfua]

Reads the ``reports/*.pdfua.json`` files that the pipeline writes
(src/docx/pdf_export.py) and prints one Markdown row per document. Each failed
veraPDF rule is put under the remediation-checklist check it belongs to; a
rule that fits none is listed under "other" so that nothing is hidden.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

CHECKS = ("table headers", "alt text", "reading order", "language", "title", "equations", "other")


def check_of(rule: dict) -> str:
    """Checklist check for one failed veraPDF rule (PDF/UA-1 clause numbers, ISO 14289-1)."""
    clause, text = rule["clause"], rule["description"].lower()
    if clause == "7.7" or "formula" in text:
        return "equations"
    if clause == "7.5" or (clause == "7.2" and any(w in text for w in ("table", " th ", " td ", " tr "))):
        return "table headers"
    if clause == "7.3" or ("alternate" in text and clause != "7.18"):
        return "alt text"
    if "lang" in text or "natural language" in text:
        return "language"
    if "title" in text:
        return "title"
    if clause in ("7.1", "7.2", "7.4", "7.9"):  # tagging, artifacts, structure, headings, notes
        return "reading order"
    return "other"


def row(report_path: Path) -> tuple[str, dict, dict]:
    data = json.loads(report_path.read_text(encoding="utf-8"))
    vera, text = data.get("verapdf") or {}, data.get("text") or {}
    by_check: dict[str, list[str]] = {}
    for rule in vera.get("failed_rules", []):
        by_check.setdefault(check_of(rule), []).append(
            f"{rule['clause']}-{rule['test']} x{rule['failed_checks']}: {rule['description']}")
    return report_path.name.removesuffix(".pdfua.json"), {"compliant": vera.get("compliant"), **text}, by_check


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "outputs/corpus_pdfua")
    reports = sorted((root / "reports").glob("*.pdfua.json"))
    if not reports:
        sys.exit(f"no *.pdfua.json under {root / 'reports'}")
    print("| Document | PDF/UA-1 | chars | pages w/o text | " + " | ".join(CHECKS) + " |")
    print("|---" * (len(CHECKS) + 4) + "|")
    reasons = []
    for path in reports:
        name, verdict, by_check = row(path)
        cells = ["fail" if by_check.get(c) else "pass" for c in CHECKS]
        status = {True: "PASS", False: "FAIL", None: "not validated"}[verdict.get("compliant")]
        print(f"| {name[:40]} | {status} | {verdict.get('characters')} | "
              f"{len(verdict.get('pages_without_text', []))} | " + " | ".join(cells) + " |")
        reasons += [f"- {name[:40]} / {c}: {r}" for c in CHECKS for r in by_check.get(c, [])]
    print("\nFailure reasons (veraPDF rule, failed checks, description):")
    print("\n".join(reasons) or "- none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
