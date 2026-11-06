"""The free audit report for a non-technical official.

The content is written once as blocks and rendered twice: HTML for the web,
and DOCX, which becomes the PDF through the Task 3 route (LibreOffice, then
veraPDF). LibreOffice's own HTML import does not tag <h1> as H1, so a PDF
made straight from the HTML fails PDF/UA-1 rule 7.4.2 (measured 2026-11-06).
"""
from __future__ import annotations

import html
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.audit.score import ISSUES, severity
from src.docx import pdf_export

WORST_SHOWN = 20
_TEXT_WIDTH_INCHES = 6.5  # Letter page, 1-inch margins (python-docx default)
# Measured in Task 1 (docs/AUTOMATION_RATE_2026-11-01.md): RAWRS on the 10
# benchmark documents. Hand-remediation time and RAWRS review time were NOT
# measured (0 reviewed documents), so the report gives no hours figure.
MEASURED = {"auto_share_pooled": 81.5, "items": 546, "documents": 10, "median_seconds_per_document": 17.2}
ISSUE_LABELS = {
    "scanned": "Scanned, no readable text", "untagged": "Not tagged", "images_no_alt": "Images without a description",
    "table_headers": "Tables without headers", "missing_text": "Some pages without text",
    "no_language": "No language set", "no_title": "No title", "other_pdfua": "Other PDF/UA-1 failures",
}
_STYLE = """body{font-family:Georgia,serif;max-width:52rem;margin:2rem auto;padding:0 1rem;color:#1b1b1b;line-height:1.5}
h1{font-size:1.9rem;margin-bottom:.2rem}h2{margin-top:2.2rem;border-bottom:2px solid #1b1b1b}
table{border-collapse:collapse;width:100%;font-size:.95rem}th,td{border:1px solid #888;padding:.35rem .5rem;text-align:left;vertical-align:top}
th{background:#eee}.strong{font-size:1.3rem;font-weight:bold}td{word-break:break-all}"""

Block = Tuple[Any, ...]  # ("h1"|"h2"|"p"|"strong", text) or ("table", caption, headers, rows)


def summarise(results: List[Dict[str, Any]], found: int) -> Dict[str, Any]:
    checked = [r for r in results if "error" not in r]
    failing = [r for r in checked if r["problems"] or r.get("pdfua1_compliant") is False]
    counts = Counter(p["issue"] for r in checked for p in r["problems"])
    return {
        "pdfs_found": found, "pdfs_checked": len(checked), "unreadable": len(results) - len(checked),
        "failing": len(failing), "failing_share": round(100 * len(failing) / len(checked), 1) if checked else None,
        "pages": sum(r["pages"] for r in checked),
        "by_issue": {k: counts[k] for k in ISSUES if counts[k]},
        "worst": [r for r in sorted(failing, key=lambda r: (severity(r), r["pages"]), reverse=True)][:WORST_SHOWN],
    }


def blocks(site: str, date: str, summary: Dict[str, Any], crawl: Dict[str, Any]) -> List[Block]:
    n, m = summary["pdfs_checked"], MEASURED
    issues = [[ISSUE_LABELS[k], str(v), f"{round(100 * v / n)}%"] for k, v in summary["by_issue"].items()]
    worst = [[str(i), r["url"], str(r["pages"]), "\n".join(p["text"] for p in r["problems"]) or "Fails PDF/UA-1 only"]
             for i, r in enumerate(summary["worst"], start=1)]
    headline = (f"{summary['failing']} of {n} PDFs ({summary['failing_share']}%) have at least one accessibility problem."
                if n else "No PDF files could be checked.")
    return [
        ("h1", f"PDF accessibility check: {site}"),
        ("p", f"Checked on {date}. {n} PDF files were checked, out of {summary['pdfs_found']} found "
              f"(found through the site's {crawl['source']}; {summary['unreadable']} could not be opened)."),
        ("strong", headline),
        ("h2", "Problems found"),
        ("table", f"How many of the {n} PDFs have each problem", ["Problem", "PDFs", "Share"],
         issues or [["None found", "0", "0%"]]),
        ("h2", f"The PDFs that need the most work (up to {WORST_SHOWN})"),
        ("table", "Worst first", ["#", "Address", "Pages", "Problems"], worst or [["-", "None", "-", "-"]]),
        ("h2", "Effort"),
        ("p", f"On 10 test documents, RAWRS made {m['auto_share_pooled']}% of the remediation decisions without a "
              f"person (n = {m['items']} decisions in {m['documents']} documents), taking a median "
              f"{m['median_seconds_per_document']} seconds of computer time per document. This is an estimate from "
              f"those test documents, not from this site's files."),
        ("p", "We have not yet measured how long a person takes to fix these files by hand, or to review RAWRS's "
              "work, so this report gives no hours figure."),
        ("h2", "About this check"),
        ("p", "This is an automated check, not a certification. It uses veraPDF (an independent PDF/UA-1 validator) "
              "and RAWRS's own checks for tags, title, language, readable text and images. A passing file can "
              "still be hard to use; only a person with a screen reader can confirm that."),
        ("p", f"Files were fetched politely: robots.txt was obeyed, requests were spaced out, and "
              f"{crawl.get('requests', 0)} requests were made in total."),
    ]


def render_html(site: str, date: str, summary: Dict[str, Any], crawl: Dict[str, Any]) -> str:
    e = html.escape
    parts = []
    for block in blocks(site, date, summary, crawl):
        kind = block[0]
        if kind == "table":
            _, caption, headers, rows = block
            head = "".join(f'<th scope="col">{e(h)}</th>' for h in headers)
            body = "".join("<tr>" + "".join(f"<td>{e(c).replace(chr(10), '<br>')}</td>" for c in row) + "</tr>"
                           for row in rows)
            parts.append(f"<table><caption>{e(caption)}</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
        elif kind == "strong":
            parts.append(f'<p class="strong">{e(block[1])}</p>')
        else:
            parts.append(f"<{kind}>{e(block[1])}</{kind}>")
    return (f'<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8"><title>PDF accessibility check: {e(site)}'
            f"</title><style>{_STYLE}</style></head><body>\n" + "\n".join(parts) + "\n</body></html>\n")


def render_docx(site: str, date: str, summary: Dict[str, Any], crawl: Dict[str, Any], path: Path) -> Path:
    import docx
    from docx.shared import Inches

    from src.docx.docx_generator import _apply_default_style, _set_row_tbl_header

    document = docx.Document()
    _apply_default_style(document, "en-US")
    document.core_properties.title = f"PDF accessibility check: {site}"
    document.core_properties.language = "en-US"
    for block in blocks(site, date, summary, crawl):
        kind = block[0]
        if kind in ("h1", "h2"):
            document.add_heading(block[1], level=int(kind[1]))
        elif kind == "strong":
            document.add_paragraph().add_run(block[1]).bold = True
        elif kind == "p":
            document.add_paragraph(block[1])
        else:
            _, caption, headers, rows = block
            document.add_paragraph(caption, style="Caption")
            table = document.add_table(rows=1, cols=len(headers))
            table.style = "Table Grid"
            table.autofit = False
            # Width follows content: "#" and "Pages" stay narrow, text columns share the rest.
            weights = [min(max(12, *(len(c) for c in [h, *(r[i] for r in rows)])), 60) for i, h in enumerate(headers)]
            widths = [Inches(_TEXT_WIDTH_INCHES * w / sum(weights)) for w in weights]
            for cell, text in zip(table.rows[0].cells, headers):
                cell.text = text
            _set_row_tbl_header(table.rows[0])
            for row in rows:
                for cell, text in zip(table.add_row().cells, row):
                    cell.text = text  # python-docx turns "\n" into a line break
            for column, width in zip(table.columns, widths):
                column.width = width  # the grid, which LibreOffice reads
            for row in table.rows:
                for cell, width in zip(row.cells, widths):
                    cell.width = width  # the cells, which Word reads
    document.save(str(path))
    return path


def render_pdf(site: str, date: str, summary: Dict[str, Any], crawl: Dict[str, Any], pdf_path: Path) -> Optional[Path]:
    """Tagged PDF of the report; None when LibreOffice is not installed."""
    if pdf_export.soffice_binary() is None:
        return None
    with tempfile.TemporaryDirectory(prefix="rawrs-report-") as scratch:
        source = render_docx(site, date, summary, crawl, Path(scratch) / "report.docx")
        return pdf_export.docx_to_pdf(source, pdf_path)
