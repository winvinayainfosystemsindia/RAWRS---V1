"""Accessible PDF from RAWRS's DOCX, checked by someone other than RAWRS.

LibreOffice's own tagged PDF/UA-1 export builds the tags from the DOCX
styles; no PDF tags are written here. veraPDF (an independent validator)
then checks the file against PDF/UA-1, and pypdfium2 counts the real text on
each page, because a file can pass PDF/UA with nothing a screen reader can
read (docs/STARTUP_PLAN.md section 4).

One DOCX convention is changed in the PDF copy only. Heading 6 is RAWRS's
printed-page marker (remediation checklist). In a tagged PDF it would be an
H6 heading before the first H1, which PDF/UA-1 forbids (veraPDF rule
7.4.2). The PDF copy therefore restyles it as a plain "Page Number"
paragraph; the DOCX keeps Heading 6. Link descriptions (rules 7.18.1 and
7.18.5) come from the ScreenTip that docx_generator puts on every link.

Needs ``soffice`` (LibreOffice 25.2 measured; 7.4 fails rules 7.9, 7.18.3
and 7.3) and, for the check, ``verapdf``. Both are found on PATH or through
RAWRS_SOFFICE / RAWRS_VERAPDF. RAWRS_PDF_EXPORT=off turns the pipeline step off.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

PAGE_MARKER_STYLE = "Heading 6"
PDF_PAGE_MARKER_STYLE = "Page Number"
VALIDATION_LABEL = "independent check: veraPDF PDF/UA-1, plus real text on every page"
# ponytail: a page under this many characters counts as "no text". A printed
# page number alone ("12") is not readable content; an OCR failure leaves
# exactly that (O'Leary, 2026-11-06: 17 characters on 13 pages, PDF/UA PASS).
# Ceiling: a real near-empty page (chapter opener) is flagged too; compare
# with the source PDF's page text if that proves noisy.
MIN_PAGE_CHARACTERS = 20
CONVERT_TIMEOUT_SECONDS = 300
VALIDATE_TIMEOUT_SECONDS = 900
_EXPORT_FILTER = "pdf:writer_pdf_Export:" + json.dumps(
    {name: {"type": "boolean", "value": "true"} for name in ("UseTaggedPDF", "PDFUACompliance", "ExportBookmarks")}
)


class PdfExportUnavailable(RuntimeError):
    """LibreOffice is not installed here."""


def soffice_binary() -> Optional[str]:
    return os.environ.get("RAWRS_SOFFICE") or shutil.which("soffice") or shutil.which("libreoffice")


def verapdf_binary() -> Optional[str]:
    return os.environ.get("RAWRS_VERAPDF") or shutil.which("verapdf")


def enabled() -> bool:
    """The pipeline exports a PDF when LibreOffice is present and not switched off."""
    return os.environ.get("RAWRS_PDF_EXPORT", "auto").lower() != "off" and soffice_binary() is not None


def pdf_ready_docx(source: Path, target: Path) -> int:
    """Write a copy of ``source`` whose page markers are plain paragraphs.
    Returns how many markers were restyled."""
    import docx
    from docx.enum.style import WD_STYLE_TYPE
    from docx.oxml.ns import qn
    from docx.text.paragraph import Paragraph

    document = docx.Document(str(source))
    styles = document.styles
    try:
        marker_style = styles[PDF_PAGE_MARKER_STYLE]
    except KeyError:
        marker_style = styles.add_style(PDF_PAGE_MARKER_STYLE, WD_STYLE_TYPE.PARAGRAPH)
        marker_style.base_style = styles["Normal"]
    restyled = 0
    for element in document.element.body.iter(qn("w:p")):
        paragraph = Paragraph(element, document._body)
        if paragraph.style is not None and paragraph.style.name == PAGE_MARKER_STYLE:
            paragraph.style = marker_style
            restyled += 1
    # Older DOCX (and ones finished in Word) may lack the link ScreenTip
    # that becomes the PDF link description; use the link's own address.
    rels = document.part.rels
    for link in document.element.body.iter(qn("w:hyperlink")):
        rel_id = link.get(qn("r:id"))
        if not link.get(qn("w:tooltip")) and rel_id in rels and rels[rel_id].is_external:
            link.set(qn("w:tooltip"), rels[rel_id].target_ref)
    document.save(str(target))
    return restyled


def docx_to_pdf(docx_path: Path, pdf_path: Path) -> Path:
    """Convert with LibreOffice into ``pdf_path`` (replaced atomically)."""
    binary = soffice_binary()
    if binary is None:
        raise PdfExportUnavailable("LibreOffice (soffice) is not installed")
    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rawrs-pdf-") as scratch:
        work = Path(scratch)
        source = work / "document.docx"
        pdf_ready_docx(Path(docx_path), source)
        # A private profile per call: two conversions sharing a profile block each other.
        command = [
            binary, f"-env:UserInstallation={(work / 'profile').as_uri()}", "--headless",
            "--convert-to", _EXPORT_FILTER, "--outdir", str(work), str(source),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=CONVERT_TIMEOUT_SECONDS)
        produced = work / "document.pdf"
        if not produced.is_file():
            raise RuntimeError(
                f"LibreOffice made no PDF (exit {completed.returncode}): {completed.stderr.strip()[-300:]}"
            )
        partial = pdf_path.with_name(pdf_path.name + ".tmp")
        shutil.copyfile(produced, partial)
        os.replace(partial, pdf_path)
    return pdf_path


def parse_verapdf(report: Dict[str, Any]) -> Dict[str, Any]:
    """The one-file verdict from veraPDF's ``--format json`` report."""
    result = report["report"]["jobs"][0]["validationResult"]
    result = result[0] if isinstance(result, list) else result
    failed = [
        {"clause": rule["clause"], "test": rule["testNumber"], "failed_checks": rule["failedChecks"],
         "description": rule["description"]}
        for rule in result["details"]["ruleSummaries"]
        if rule.get("ruleStatus", "FAILED") == "FAILED"
    ]
    return {"profile": result.get("profileName"), "compliant": bool(result["compliant"]), "failed_rules": failed}


def _verapdf(pdf_path: Path) -> Optional[Dict[str, Any]]:
    binary = verapdf_binary()
    if binary is None:
        return None
    completed = subprocess.run(
        [binary, "--flavour", "ua1", "--format", "json", str(pdf_path)],
        capture_output=True, text=True, timeout=VALIDATE_TIMEOUT_SECONDS,
    )
    try:
        return parse_verapdf(json.loads(completed.stdout))
    except (ValueError, KeyError, IndexError) as exc:
        return {"error": f"unreadable veraPDF output (exit {completed.returncode}): {exc}"}


def text_presence(pdf_path: Path) -> Optional[Dict[str, Any]]:
    """Characters a screen reader could read, per page (pypdfium2 arrives with docling)."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return None
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        counts = []
        for page in pdf:
            textpage = page.get_textpage()
            counts.append(len(textpage.get_text_bounded().strip()))
            textpage.close()
            page.close()
    finally:
        pdf.close()
    return {
        "pages": len(counts),
        "characters": sum(counts),
        "pages_without_text": [
            number for number, count in enumerate(counts, start=1) if count < MIN_PAGE_CHARACTERS
        ],
    }


def validate_pdf(pdf_path: Path) -> Dict[str, Any]:
    return {"label": VALIDATION_LABEL, "verapdf": _verapdf(Path(pdf_path)), "text": text_presence(Path(pdf_path))}


def summary_of(validation: Dict[str, Any]) -> Dict[str, Any]:
    """The few numbers the metrics sidecar keeps; None where a tool was missing."""
    vera = validation.get("verapdf") or {}
    text = validation.get("text") or {}
    return {
        "label": VALIDATION_LABEL,
        "pdfua1_compliant": vera.get("compliant"),
        "failed_rules": [f"{r['clause']}-{r['test']}" for r in vera.get("failed_rules", [])],
        "characters": text.get("characters"),
        "pages": text.get("pages"),
        "pages_without_text": len(text["pages_without_text"]) if "pages_without_text" in text else None,
    }


def report_path(output_root: Path, stem: str) -> Path:
    return Path(output_root) / "reports" / f"{stem}.pdfua.json"


def stored_verdict(report: Path, docx_path: Path) -> Optional[Dict[str, Any]]:
    """The pipeline's verdict for the checklist view; ``stale`` once the
    DOCX was changed after the PDF was checked. None when never exported."""
    if not report.is_file():
        return None
    try:
        summary = summary_of(json.loads(report.read_text(encoding="utf-8")))
    except (ValueError, KeyError, TypeError) as exc:
        logger.error("Unreadable PDF/UA report '{}': {}", report, exc)
        return None
    return {**summary, "stale": Path(docx_path).stat().st_mtime > report.stat().st_mtime}


def export_and_validate(docx_path: Path, pdf_path: Path, report_path: Path) -> Optional[Dict[str, Any]]:
    """Pipeline step: PDF beside the DOCX, full verdict in ``report_path``.
    Never raises; returns the summary, or None when no PDF could be made."""
    try:
        docx_to_pdf(docx_path, pdf_path)
        validation = validate_pdf(pdf_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(validation, indent=2), encoding="utf-8")
        summary = summary_of(validation)
        logger.info("PDF export: {} - PDF/UA-1 {} {}", pdf_path.name, summary["pdfua1_compliant"],
                    summary["failed_rules"] or "")
        return summary
    except Exception as exc:
        logger.error("PDF export failed for '{}': {}", docx_path, exc)
        return None
