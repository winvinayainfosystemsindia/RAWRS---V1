"""Hand-edited Markdown: saved edits become the deliverables, the preview
renders a draft without saving, and discarding returns to the model."""

import io
from pathlib import Path

import pytest
from docx import Document as open_docx
from fastapi.testclient import TestClient

from src.api import document_store, jobs
from src.api.jobs import Job, JobStatus
from src.models.contracts import Document, Metadata, Page
from src.models.document import ProcessingStatus
from src.pipeline.phase1_pipeline import PipelineResult

GENERATED = "###### 1\n\n# Generated Title\n\nGenerated body text.\n"
EDITED = "###### 1\n\n# Edited Title\n\nThe reviewer rewrote this sentence.\n"


@pytest.fixture
def client(tmp_path, monkeypatch):
    import src.api.routes as routes
    from src.api.main import app

    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(jobs, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(document_store, "DOCUMENTS_DIR", tmp_path / "documents")
    monkeypatch.setattr(routes, "DEFAULT_OUTPUT_ROOT", tmp_path)

    markdown_path = tmp_path / "gen.md"
    markdown_path.write_text(GENERATED, encoding="utf-8")
    document = Document(
        source_pdf_path="missing.pdf",
        metadata=Metadata(filename="missing.pdf", page_count=1),
        pages=[Page(page_number=1)],
    )
    job = Job(
        job_id="edit1", filename="test.pdf", pdf_path=Path("uploads/edit1.pdf"),
        status=JobStatus.COMPLETE,
        result=PipelineResult(
            source_pdf_path="missing.pdf", success=True, status=ProcessingStatus.VALIDATED,
            duration_seconds=1.0, document=document, markdown_path=markdown_path,
            markdown_generated_at_version=document.version,
            docx_path=tmp_path / "gen.docx", docx_generated_at_version=-1,
        ),
    )
    with jobs._lock:
        jobs._jobs["edit1"] = job
    yield TestClient(app)
    with jobs._lock:
        jobs._jobs.clear()


def _docx_text(data: bytes) -> str:
    return "\n".join(p.text for p in open_docx(io.BytesIO(data)).paragraphs)


def test_generated_markdown_is_not_marked_edited(client) -> None:
    body = client.get("/api/documents/edit1/markdown").json()
    assert body["content"] == GENERATED and body["edited"] is False


def test_preview_renders_a_draft_without_saving_it(client) -> None:
    response = client.post("/api/documents/edit1/docx-preview", json={"content": EDITED})
    assert response.status_code == 200
    assert "The reviewer rewrote this sentence." in _docx_text(response.content)
    assert client.get("/api/documents/edit1/markdown").json()["edited"] is False


def test_saved_edits_become_both_deliverables(client) -> None:
    saved = client.put("/api/documents/edit1/markdown", json={"content": EDITED}).json()
    assert saved["edited"] is True and saved["edited_at_version"] is not None

    assert client.get("/api/documents/edit1/markdown").json()["content"] == EDITED
    assert client.get("/api/documents/edit1/download/markdown").text == EDITED
    docx_text = _docx_text(client.get("/api/documents/edit1/download/docx").content)
    assert "Edited Title" in docx_text and "Generated" not in docx_text


def test_discarding_returns_to_the_generated_output(client) -> None:
    client.put("/api/documents/edit1/markdown", json={"content": EDITED})
    restored = client.delete("/api/documents/edit1/markdown").json()
    assert restored["edited"] is False
    assert "Generated body text." in restored["content"]
    assert "Edited" not in _docx_text(client.get("/api/documents/edit1/download/docx").content)
