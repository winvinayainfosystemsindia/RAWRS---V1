"""Equations on the correction rail, the review queue and the API
(docs/EQUATION_DESIGN.md §2, §5).

A reviewer's change to an equation is an ordinary ``CorrectionRecord``: the
rail performs it, undo is the generic swap, and both projections change only
because they read the Semantic Document.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from src.api import routes
from src.api.main import app
from src.markdown.markdown_builder import build_markdown
from src.mathpix.ingestor import MathpixImportProvider
from src.models.contracts import Document
from src.models.correction import CorrectionRecord, CorrectionStatus
from src.models.equation import Equation, EquationStatus
from src.models.metadata import Metadata
from src.models.page import Page
from src.validation.validator import validate_document
from src.verification.engine import engine
from src.verification.equations import (
    ASSET_TYPE,
    DESCRIPTION_EDIT,
    LATEX_EDIT,
    NUMBER_EDIT,
    EquationVerifier,
)

client = TestClient(app)


def _doc(mmd: str, tmp_path: Path) -> Document:
    mmd_file = tmp_path / "t.mmd"
    mmd_file.write_text(mmd, encoding="utf-8")
    document = Document(
        source_pdf_path="t.pdf",
        metadata=Metadata(filename="t.pdf", page_count=1),
        pages=[Page(page_number=1)],
    )
    return MathpixImportProvider().import_document(document, mmd_path=mmd_file)


def _edit(document: Document, equation: Equation, field: str, new: str, old: Optional[str] = None):
    current = {
        LATEX_EDIT: equation.latex,
        NUMBER_EDIT: equation.number or "",
        DESCRIPTION_EDIT: equation.description or "",
    }[field]
    correction = CorrectionRecord(
        object_type=ASSET_TYPE,
        object_id=equation.id,
        field=field,
        original_value=current if old is None else old,
        proposed_value=new,
        reason="Reviewer edited the equation.",
        reason_code="EQUATION_EDITED_BY_REVIEWER",
        provider="manual_reviewer",
        status=CorrectionStatus.EDITED,
        transaction_id=f"txn-{len(document.corrections)}",
    )
    document.corrections.append(correction)
    engine.apply_correction(document, correction)
    return correction


class TestRegistration:
    def test_equation_is_a_registered_asset_type(self):
        assert isinstance(engine._verifiers[ASSET_TYPE], EquationVerifier)  # noqa: SLF001

    def test_each_editable_field_has_a_rule_id(self):
        table = EquationVerifier().rule_table()
        assert set(table) == {LATEX_EDIT, NUMBER_EDIT, DESCRIPTION_EDIT}
        assert len({spec.rule_id for spec in table.values()}) == 3

    def test_it_proposes_nothing_of_its_own(self, tmp_path):
        document = _doc("$$\nx^{2}\n$$\n", tmp_path)
        assert EquationVerifier().inspect(document) == []


class TestLatexEdit:
    def test_editing_a_flagged_equation_to_a_valid_one_converts_it(self, tmp_path):
        document = _doc("$$\n\\weirdmacro{x}+y^{2}\n$$\n", tmp_path)
        equation = document.equations[0]
        assert equation.status is EquationStatus.FLAGGED

        _edit(document, equation, LATEX_EDIT, "x^{2}+y^{2}")

        assert equation.latex == "x^{2}+y^{2}"
        assert equation.status is EquationStatus.CONVERTED
        assert equation.flag_reasons == []

    def test_editing_to_something_unsupported_flags_it(self, tmp_path):
        document = _doc("$$\nx^{2}\n$$\n", tmp_path)
        equation = document.equations[0]

        _edit(document, equation, LATEX_EDIT, "\\weirdmacro{x}")

        assert equation.status is EquationStatus.FLAGGED
        assert any("weirdmacro" in reason for reason in equation.flag_reasons)

    def test_revert_restores_latex_status_and_text(self, tmp_path):
        document = _doc("$$\n\\weirdmacro{x}+y^{2}\n$$\n", tmp_path)
        equation = document.equations[0]
        before = (equation.latex, equation.status, equation.text, list(equation.flag_reasons))
        correction = _edit(document, equation, LATEX_EDIT, "x^{2}+y^{2}")

        engine.revert_correction(document, correction)

        assert (equation.latex, equation.status, equation.text, equation.flag_reasons) == before

    def test_the_source_is_never_touched(self, tmp_path):
        document = _doc("$$\nx^{2}\n$$\n", tmp_path)
        equation = document.equations[0]
        source = equation.latex_source

        _edit(document, equation, LATEX_EDIT, "y^{3}")

        assert equation.latex_source == source

    def test_the_document_version_is_bumped(self, tmp_path):
        document = _doc("$$\nx^{2}\n$$\n", tmp_path)
        before = document.version
        _edit(document, document.equations[0], LATEX_EDIT, "y^{3}")
        assert document.version == before + 1

    def test_the_edit_reaches_the_markdown_projection(self, tmp_path):
        document = _doc("$$\nx^{2}\n$$\n", tmp_path)
        _edit(document, document.equations[0], LATEX_EDIT, "y^{3}")
        assert "$$y^{3}$$" in build_markdown(document)

    def test_a_number_missing_its_tag_stays_flagged_after_an_edit(self, tmp_path):
        document = _doc("\\begin{equation}\nx^{2}=4\n\\end{equation}\n", tmp_path)
        equation = document.equations[0]
        _edit(document, equation, LATEX_EDIT, "x^{2}=9")
        assert equation.status is EquationStatus.FLAGGED
        assert any("number" in reason for reason in equation.flag_reasons)


class TestNumberAndDescription:
    def test_number_edit_clears_the_unknown_number_flag(self, tmp_path):
        document = _doc("\\begin{equation}\nx^{2}=4\n\\end{equation}\n", tmp_path)
        equation = document.equations[0]
        _edit(document, equation, NUMBER_EDIT, "3.2")
        assert equation.number == "3.2"
        assert equation.status is EquationStatus.CONVERTED
        assert equation.flag_reasons == []

    def test_an_empty_number_means_no_number(self, tmp_path):
        document = _doc("\\begin{equation}\nx^{2}=4 \\tag{1}\n\\end{equation}\n", tmp_path)
        equation = document.equations[0]
        _edit(document, equation, NUMBER_EDIT, "")
        assert equation.number is None

    def test_description_edit_and_revert(self, tmp_path):
        document = _doc("$$\nx^{2}\n$$\n", tmp_path)
        equation = document.equations[0]
        correction = _edit(document, equation, DESCRIPTION_EDIT, "Squares x.")
        assert equation.description == "Squares x."
        engine.revert_correction(document, correction)
        assert not equation.description


class TestInlineEquationEdit:
    def test_paragraph_text_and_anchors_follow_a_longer_rendering(self, tmp_path):
        document = _doc("A $x^{2}$ and B $y^{3}$ end.\n", tmp_path)
        first, second = [e for e in document.equations if not e.display]
        _edit(document, first, LATEX_EDIT, "x^{2}+z^{2}+w^{2}")
        paragraph = document.paragraphs[0]
        for equation in (first, second):
            start = equation.anchor_offset
            assert paragraph.text[start:start + equation.anchor_length] == equation.text
        assert paragraph.text.startswith("A x² + z² + w² and B")

    def test_revert_restores_the_paragraph_exactly(self, tmp_path):
        document = _doc("A $x^{2}$ and B $y^{3}$ end.\n", tmp_path)
        before = document.paragraphs[0].text
        first = [e for e in document.equations if not e.display][0]
        correction = _edit(document, first, LATEX_EDIT, "x^{2}+z^{2}+w^{2}")
        engine.revert_correction(document, correction)
        assert document.paragraphs[0].text == before

    def test_a_note_anchor_after_the_equation_still_lands_on_its_marker(self, tmp_path):
        document = _doc("Claim $x^{2}$ holds ${ }^{1}$.\n\n1. The note body.\n", tmp_path)
        equation = [e for e in document.equations if not e.display][0]
        _edit(document, equation, LATEX_EDIT, "x^{2}+y^{2}+z^{2}")
        paragraph, note = document.paragraphs[0], document.footnotes[0]
        assert note.anchor_text == paragraph.text
        assert paragraph.text[note.anchor_offset:note.anchor_offset + len(note.marker)] == note.marker


class TestNoOps:
    def test_a_correction_naming_no_equation_is_a_clean_no_op(self, tmp_path):
        document = _doc("$$\nx^{2}\n$$\n", tmp_path)
        before = document.equations[0].latex
        correction = CorrectionRecord(
            object_type=ASSET_TYPE,
            object_id="equation-line-999-0",
            field=LATEX_EDIT,
            original_value="a",
            proposed_value="b",
            reason="x",
            reason_code="EQUATION_EDITED_BY_REVIEWER",
            provider="manual_reviewer",
            status=CorrectionStatus.EDITED,
            transaction_id="t",
        )
        document.corrections.append(correction)
        engine.apply_correction(document, correction)
        assert document.equations[0].latex == before


class TestReviewQueue:
    def test_a_flagged_equation_is_a_validation_issue_with_its_reasons(self, tmp_path):
        document = _doc("$$\n\\weirdmacro{x}+y^{2}\n$$\n", tmp_path)
        issues = [i for i in validate_document(document) if i.rule_id == "EQUATION_001"]
        assert len(issues) == 1
        assert "weirdmacro" in issues[0].message

    def test_converted_and_plain_equations_raise_nothing(self, tmp_path):
        document = _doc("$$\nx^{2}+y^{2}\n$$\n\\begin{equation*}\nF=m a\n\\end{equation*}\n", tmp_path)
        assert not [i for i in validate_document(document) if i.rule_id == "EQUATION_001"]


@pytest.fixture
def served(tmp_path, monkeypatch):
    document = _doc("\\begin{equation}\nx^{2}=4\n\\end{equation}\n$$\ny^{2}\n$$\n", tmp_path)
    monkeypatch.setattr(routes, "_require_document", lambda job_id: document)
    monkeypatch.setattr(routes, "_persist", lambda job_id, payload: None)
    return document


class TestApi:
    def test_list_returns_every_equation_with_its_status(self, served):
        body = client.get("/api/documents/job/equations").json()
        assert [e["equation_id"] for e in body["equations"]] == [e.id for e in served.equations]
        assert body["equations"][0]["status"] == "flagged"
        assert body["equations"][1]["status"] == "converted"

    def test_patch_latex_records_a_correction_and_returns_the_equation(self, served):
        target = served.equations[1]
        response = client.patch(
            f"/api/documents/job/equations/{target.id}", json={"latex": "z^{3}"}
        )
        assert response.status_code == 200
        assert response.json()["latex"] == "z^{3}"
        assert target.latex == "z^{3}"
        assert served.corrections[-1].object_type == "equation"

    def test_patch_number_and_description(self, served):
        target = served.equations[0]
        response = client.patch(
            f"/api/documents/job/equations/{target.id}",
            json={"number": "2.1", "description": "Squares equal four."},
        )
        assert response.status_code == 200
        assert target.number == "2.1" and target.description == "Squares equal four."
        assert len(served.corrections) == 2

    def test_blank_latex_is_refused(self, served):
        target = served.equations[1]
        response = client.patch(f"/api/documents/job/equations/{target.id}", json={"latex": "  "})
        assert response.status_code == 422

    def test_unknown_equation_is_404(self, served):
        response = client.patch("/api/documents/job/equations/nope", json={"latex": "x"})
        assert response.status_code == 404

    def test_an_empty_patch_changes_nothing(self, served):
        target = served.equations[1]
        response = client.patch(f"/api/documents/job/equations/{target.id}", json={})
        assert response.status_code == 422
        assert served.corrections == []
