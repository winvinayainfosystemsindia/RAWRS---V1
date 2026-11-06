"""Accessible PDF export (src/docx/pdf_export.py).

The unit tests run anywhere. The end-to-end test needs LibreOffice and
veraPDF (installed in the Codespace) and is skipped elsewhere.
"""
from pathlib import Path

import docx
import pytest
from docx.oxml.ns import qn

from src.docx import pdf_export
from src.docx.docx_generator import generate_docx
from src.metrics.automation import NOT_MEASURED, _independent_view
from src.models.contracts import Document, Metadata

_MARKDOWN = "\n\n".join([
    "###### 1",
    "## 1.1 Introduction",
    "The US and the UK said 5 kg. See www.example.com for more.",
    "<!-- pagebreak -->",
    "###### 2",
    "#### Deep heading",
    "More text.",
])


def _generated(tmp_path: Path) -> Path:
    document = Document(source_pdf_path="missing.pdf", metadata=Metadata(filename="missing.pdf"))
    return generate_docx(document, _MARKDOWN, output_path=tmp_path / "out.docx")


def _styles(path: Path):
    return [p.style.name for p in docx.Document(str(path)).paragraphs]


def test_pdf_copy_turns_page_markers_into_plain_paragraphs(tmp_path):
    source = _generated(tmp_path)
    assert _styles(source).count("Heading 6") == 2

    restyled = pdf_export.pdf_ready_docx(source, tmp_path / "pdf.docx")

    after = _styles(tmp_path / "pdf.docx")
    assert restyled == 2
    assert "Heading 6" not in after and after.count("Page Number") == 2
    other_headings = [s for s in _styles(source) if s.startswith("Heading") and s != "Heading 6"]
    assert [s for s in after if s.startswith("Heading")] == other_headings
    assert _styles(source).count("Heading 6") == 2  # the DOCX itself is untouched


def test_every_link_carries_a_screentip(tmp_path):
    body = docx.Document(str(_generated(tmp_path))).element.body
    links = list(body.iter(qn("w:hyperlink")))
    assert links and all(link.get(qn("w:tooltip")) == "http://www.example.com" for link in links)


def test_pdf_copy_adds_missing_screentips(tmp_path):
    source = _generated(tmp_path)
    document = docx.Document(str(source))
    for link in document.element.body.iter(qn("w:hyperlink")):
        del link.attrib[qn("w:tooltip")]
    document.save(str(source))

    pdf_export.pdf_ready_docx(source, tmp_path / "pdf.docx")

    links = list(docx.Document(str(tmp_path / "pdf.docx")).element.body.iter(qn("w:hyperlink")))
    assert links and all(link.get(qn("w:tooltip")) == "http://www.example.com" for link in links)


def _report(compliant, rules):
    return {"report": {"jobs": [{"validationResult": [{
        "profileName": "PDF/UA-1 validation profile", "compliant": compliant,
        "details": {"ruleSummaries": rules}}]}]}}


def test_parse_verapdf_keeps_failed_rules_only():
    rules = [
        {"clause": "7.4.2", "testNumber": 1, "failedChecks": 3, "description": "headings", "ruleStatus": "FAILED"},
        {"clause": "7.1", "testNumber": 2, "failedChecks": 0, "description": "ok", "ruleStatus": "PASSED"},
    ]
    verdict = pdf_export.parse_verapdf(_report(False, rules))
    assert verdict["compliant"] is False
    assert [(r["clause"], r["test"], r["failed_checks"]) for r in verdict["failed_rules"]] == [("7.4.2", 1, 3)]
    assert pdf_export.parse_verapdf(_report(True, []))["failed_rules"] == []


def test_summary_marks_missing_tools_as_unknown_not_passed():
    summary = pdf_export.summary_of({"verapdf": None, "text": None})
    assert summary["pdfua1_compliant"] is None and summary["characters"] is None
    full = pdf_export.summary_of({
        "verapdf": {"compliant": False, "failed_rules": [{"clause": "7.3", "test": 1}]},
        "text": {"pages": 2, "characters": 0, "pages_without_text": [1, 2]},
    })
    assert full["failed_rules"] == ["7.3-1"] and full["pages_without_text"] == 2


def test_independent_view_counts_only_validated_files():
    jobs = [
        {"independent": {"label": "x", "pdfua1_compliant": True, "characters": 10}},
        {"independent": {"label": "x", "pdfua1_compliant": False, "characters": 0}},
        {"independent": {"label": "x", "pdfua1_compliant": None, "characters": 5}},
        {"independent": None},
    ]
    view = _independent_view(jobs)
    assert (view["documents_exported"], view["documents_validated"], view["pdfua1_compliant"],
            view["documents_with_no_text"]) == (3, 2, 1, 1)
    assert _independent_view([])["status"] == NOT_MEASURED


def test_export_never_raises_and_switch_turns_it_off(tmp_path, monkeypatch):
    monkeypatch.setenv("RAWRS_SOFFICE", str(tmp_path / "no-such-soffice"))
    source = _generated(tmp_path)
    assert pdf_export.export_and_validate(source, tmp_path / "a.pdf", tmp_path / "a.json") is None
    monkeypatch.setenv("RAWRS_PDF_EXPORT", "off")
    assert pdf_export.enabled() is False


def test_stored_verdict_goes_stale_when_the_docx_changes(tmp_path):
    import json
    import os

    docx_path, report = tmp_path / "a.docx", tmp_path / "a.pdfua.json"
    assert pdf_export.stored_verdict(report, docx_path) is None
    docx_path.write_bytes(b"x")
    report.write_text(json.dumps({"verapdf": {"compliant": True, "failed_rules": []}, "text": None}))
    os.utime(docx_path, (1, 1))
    assert pdf_export.stored_verdict(report, docx_path)["stale"] is False
    os.utime(docx_path, (report.stat().st_mtime + 10,) * 2)
    verdict = pdf_export.stored_verdict(report, docx_path)
    assert verdict["stale"] is True and verdict["pdfua1_compliant"] is True


@pytest.mark.skipif(not (pdf_export.soffice_binary() and pdf_export.verapdf_binary()),
                    reason="needs LibreOffice and veraPDF (Codespace)")
def test_generated_docx_exports_to_compliant_pdf_with_text(tmp_path):
    summary = pdf_export.export_and_validate(_generated(tmp_path), tmp_path / "out.pdf", tmp_path / "out.json")
    assert summary is not None, "conversion failed"
    assert summary["pdfua1_compliant"] is True, summary["failed_rules"]
    assert summary["characters"] > 0 and summary["pages_without_text"] == 0
