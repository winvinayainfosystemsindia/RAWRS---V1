"""src/learning/docx_diff.py - what a remediator changed after export.

Every test builds a small "exported" DOCX, applies one remediator-style change
to a copy, and checks the change is reported as exactly that category - and
that nothing else is reported.
"""

import base64

from docx import Document
from docx.oxml import OxmlElement
from lxml import etree

from src.learning.docx_diff import PAIRING_BUDGET, Unit, diff_docx, diff_units, read_units
from src.validation.checklist_audit import PLACEHOLDER_ALT_MARK, _A16_DECORATIVE

# A 1x1 transparent PNG.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def _base(tmp_path, *, alt=f"Image ({PLACEHOLDER_ALT_MARK})", header=True):
    png = tmp_path / "pixel.png"
    png.write_bytes(PNG)
    doc = Document()
    doc.core_properties.title = "Exported title"
    doc.add_heading("Chapter One", level=1)
    doc.add_paragraph("The first paragraph explains the study and its context in detail.")
    doc.add_heading("Methods", level=2)
    doc.add_paragraph("A short line that should have been a heading")
    shape = doc.add_paragraph().add_run().add_picture(str(png))
    shape._inline.docPr.set("descr", alt)
    doc.add_paragraph("Figure 1. A caption.", style="Caption")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Name", "Value"
    table.cell(1, 0).text, table.cell(1, 1).text = "a", "1"
    if header:
        table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    doc.add_paragraph("The closing paragraph summarises the findings for readers.")
    return doc


def _save(doc, path):
    doc.save(str(path))
    return path


def _diff(tmp_path, change):
    exported = _save(_base(tmp_path), tmp_path / "exported.docx")
    final_doc = _base(tmp_path)
    change(final_doc)
    final = _save(final_doc, tmp_path / "final.docx")
    return diff_docx(exported, final)


def _categories(result):
    return [edit["category"] for edit in result["edits"]]


def _paragraph(doc, startswith):
    return next(p for p in doc.paragraphs if p.text.startswith(startswith))


def test_identical_documents_have_no_edits(tmp_path):
    result = _diff(tmp_path, lambda doc: None)
    assert result["edits"] == []
    assert result["summary"]["kept_share"] == 1.0
    assert result["summary"]["units_exported"] == 8  # 2 headings, 3 paragraphs, caption, image, table


def test_heading_level_change(tmp_path):
    result = _diff(tmp_path, lambda doc: setattr(_paragraph(doc, "Methods"), "style", doc.styles["Heading 3"]))
    assert _categories(result) == ["HEADING_LEVEL_CHANGED"]
    edit = result["edits"][0]
    assert (edit["before"], edit["after"], edit["object_type"]) == ("H2", "H3", "heading")


def test_body_line_promoted_to_heading(tmp_path):
    result = _diff(tmp_path, lambda doc: setattr(_paragraph(doc, "A short line"), "style", doc.styles["Heading 2"]))
    assert _categories(result) == ["PROMOTED_TO_HEADING"]
    assert result["edits"][0]["after"] == "H2"


def test_heading_demoted_to_body(tmp_path):
    result = _diff(tmp_path, lambda doc: setattr(_paragraph(doc, "Methods"), "style", doc.styles["Normal"]))
    assert _categories(result) == ["DEMOTED_FROM_HEADING"]


def test_case_change_aligns_and_is_a_text_edit(tmp_path):
    def change(doc):
        _paragraph(doc, "Chapter One").runs[0].text = "CHAPTER ONE"

    result = _diff(tmp_path, change)
    assert _categories(result) == ["TEXT_EDITED"]
    assert result["edits"][0]["word_changes"] == [{"op": "replace", "from": "Chapter One", "to": "CHAPTER ONE"}]


def test_reworded_paragraph_is_paired_not_removed_and_added(tmp_path):
    def change(doc):
        _paragraph(doc, "The first").runs[0].text = "The first paragraph explains the research and its context in detail."

    result = _diff(tmp_path, change)
    assert _categories(result) == ["TEXT_EDITED"]
    edit = result["edits"][0]
    assert edit["word_changes"] == [{"op": "replace", "from": "study", "to": "research"}]
    assert 0.6 < edit["similarity"] < 1


def test_added_and_removed_content(tmp_path):
    def change(doc):
        closing = _paragraph(doc, "The closing")
        closing._p.getparent().remove(closing._p)
        doc.add_paragraph("A note the remediator added at the end of the document.")

    result = _diff(tmp_path, change)
    assert sorted(_categories(result)) == ["CONTENT_ADDED", "CONTENT_REMOVED"]


def test_alt_text_written_over_placeholder(tmp_path):
    def change(doc):
        doc.inline_shapes[0]._inline.docPr.set("descr", "Bar chart of enrolment by year.")

    result = _diff(tmp_path, change)
    assert _categories(result) == ["ALT_TEXT_WRITTEN"]
    assert result["edits"][0]["object_type"] == "figure"
    assert result["edits"][0]["after"] == "Bar chart of enrolment by year."


def test_alt_text_rewritten(tmp_path):
    exported = _save(_base(tmp_path, alt="A chart."), tmp_path / "exported.docx")
    final_doc = _base(tmp_path, alt="A chart.")
    final_doc.inline_shapes[0]._inline.docPr.set("descr", "Bar chart of enrolment, 2010-2020.")
    result = diff_docx(exported, _save(final_doc, tmp_path / "final.docx"))
    assert _categories(result) == ["ALT_TEXT_REWRITTEN"]


def test_marked_decorative(tmp_path):
    def change(doc):
        doc_pr = doc.inline_shapes[0]._inline.docPr
        ext = etree.SubElement(etree.SubElement(doc_pr, f"{_A}extLst"), f"{_A}ext")
        etree.SubElement(ext, _A16_DECORATIVE).set("val", "1")

    result = _diff(tmp_path, change)
    assert _categories(result) == ["MARKED_DECORATIVE"]


def test_table_header_row_added(tmp_path):
    exported = _save(_base(tmp_path, header=False), tmp_path / "exported.docx")
    final = _save(_base(tmp_path, header=True), tmp_path / "final.docx")
    result = diff_docx(exported, final)
    assert _categories(result) == ["TABLE_HEADER_CHANGED"]
    assert result["edits"][0]["after"] == "1 header rows"


def test_table_cells_and_shape(tmp_path):
    def change(doc):
        table = doc.tables[0]
        table.cell(1, 1).text = "2"
        table.add_row()

    result = _diff(tmp_path, change)
    assert sorted(_categories(result)) == ["TABLE_CONTENT_EDITED", "TABLE_STRUCTURE_CHANGED"]


def test_metadata_title_changed(tmp_path):
    result = _diff(tmp_path, lambda doc: setattr(doc.core_properties, "title", "Remediated title"))
    assert _categories(result) == ["METADATA_CHANGED"]
    assert result["edits"][0]["field"] == "title"


def test_oversized_replaced_run_falls_back_to_remove_plus_add():
    size = int(PAIRING_BUDGET ** 0.5) + 2
    before = [Unit(kind="paragraph", text=f"old paragraph number {i}") for i in range(size)]
    after = [Unit(kind="paragraph", text=f"new paragraph number {i}") for i in range(size)]
    edits, kept = diff_units(before, after)
    assert kept == 0
    assert {e["category"] for e in edits} == {"CONTENT_ADDED", "CONTENT_REMOVED"}


def test_read_units_kinds(tmp_path):
    units = read_units(_base(tmp_path))
    assert [u.kind for u in units] == [
        "heading", "paragraph", "heading", "paragraph", "image", "caption", "table", "paragraph"
    ]
    assert units[6].header_rows == 1 and units[6].shape == (2, 2)
