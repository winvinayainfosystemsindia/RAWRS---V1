"""Score one downloaded PDF: veraPDF PDF/UA-1 plus RAWRS's input checks.

Input checks (PyMuPDF, already a RAWRS dependency): tagged or not, title,
language, readable text per page (scanned or not), images. Alt text and
table structure come from veraPDF's failed rules on tagged files; an
untagged file cannot carry alt text at all, so each of its images counts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF

from src.docx import pdf_export

# Plain-English problem per issue type, and its weight in the "worst" ranking.
ISSUES: Dict[str, tuple] = {
    "scanned": ("Scanned image with no text: a screen reader reads nothing.", 5),
    "untagged": ("Not tagged: a screen reader gets no headings, lists, tables or reading order.", 3),
    "images_no_alt": ("{n} image(s) without a text description.", 2),
    "table_headers": ("Tables without header cells marked.", 2),
    "missing_text": ("{n} of {pages} pages have no readable text.", 2),
    "no_language": ("No document language: a screen reader may use the wrong voice.", 1),
    "no_title": ("No document title: the file name is announced instead.", 1),
    "other_pdfua": ("Fails {n} other PDF/UA-1 rule(s).", 1),
}


def check_of(rule: dict) -> str:
    """Checklist check for one failed veraPDF rule (PDF/UA-1 clause numbers, ISO 14289-1)."""
    clause, text = rule["clause"], rule["description"].lower()
    if clause == "7.7" or "formula" in text:
        return "equations"
    if clause == "7.5" or (clause == "7.2" and any(w in text for w in ("table", " th ", " td ", " tr "))):
        return "table headers"
    if clause == "7.3" or ("alternate" in text and not clause.startswith("7.18")):  # 7.18.x: links
        return "alt text"
    if "lang" in text or "natural language" in text:
        return "language"
    if "title" in text:
        return "title"
    if clause in ("7.1", "7.2", "7.4", "7.9"):  # tagging, artifacts, structure, headings, notes
        return "reading order"
    return "other"


def _catalog_value(doc: fitz.Document, key: str) -> str:
    kind, value = doc.xref_get_key(doc.pdf_catalog(), key)
    return "" if kind == "null" else value


def input_checks(path: Path) -> Dict[str, Any]:
    with fitz.open(str(path)) as doc:
        mark_info = _catalog_value(doc, "MarkInfo")
        if mark_info.endswith(" 0 R"):
            mark_info = doc.xref_object(int(mark_info.split()[0]))
        tagged = bool(_catalog_value(doc, "StructTreeRoot")) and "/Marked true" in mark_info
        language = _catalog_value(doc, "Lang").strip("()")
        return {
            "pages": doc.page_count,
            "tagged": tagged,
            "title": (doc.metadata or {}).get("title", "").strip(),
            "language": language,
            "images": sum(len(page.get_images(full=False)) for page in doc),
        }


def problems(checks: Dict[str, Any], text: Optional[Dict[str, Any]], vera: Optional[Dict[str, Any]]) -> List[dict]:
    """Issue types found, each with its plain-English sentence."""
    found: Dict[str, dict] = {}
    pages = checks["pages"]
    empty = len(text["pages_without_text"]) if text else 0
    if text and pages and empty == pages:
        found["scanned"] = {}
    elif empty:
        found["missing_text"] = {"n": empty, "pages": pages}
    if not checks["tagged"]:
        found["untagged"] = {}
        if checks["images"]:
            found["images_no_alt"] = {"n": checks["images"]}
    if not checks["language"]:
        found["no_language"] = {}
    if not checks["title"]:
        found["no_title"] = {}
    rules = (vera or {}).get("failed_rules", [])
    alt = sum(r["failed_checks"] for r in rules if check_of(r) == "alt text")
    if alt and checks["tagged"]:
        found["images_no_alt"] = {"n": alt}
    if checks["tagged"] and any(check_of(r) == "table headers" for r in rules):
        found["table_headers"] = {}
    covered = {"alt text", "table headers", "language", "title"}
    other = [r for r in rules if check_of(r) not in covered] if checks["tagged"] else []
    if other:
        found["other_pdfua"] = {"n": len(other)}
    return [{"issue": key, "text": ISSUES[key][0].format(**values)} for key, values in found.items()]


def severity(result: Dict[str, Any]) -> int:
    return sum(ISSUES[p["issue"]][1] for p in result["problems"])


def score_pdf(url: str, path: Path) -> Dict[str, Any]:
    """Everything the report needs about one PDF; an unreadable file is reported, not raised."""
    try:
        checks = input_checks(path)
    except Exception as exc:  # a broken download is a finding, not a crash
        return {"url": url, "file": path.name, "error": f"could not open: {exc}", "problems": []}
    text = pdf_export.text_presence(path)
    vera = pdf_export.verapdf_verdict(path)
    return {
        "url": url, "file": path.name, **checks,
        "characters": (text or {}).get("characters"),
        "pdfua1_compliant": (vera or {}).get("compliant"),
        "failed_rules": [f"{r['clause']}-{r['test']}" for r in (vera or {}).get("failed_rules", [])],
        "problems": problems(checks, text, vera),
    }
