"""Tests for the table CRUD API endpoints.

These tests drive GET /tables, POST /tables, PATCH /tables/{id}, and
DELETE /tables/{id} through the FastAPI test client using a synthetic
in-memory Document so they run instantly without a real PDF.
"""

from pathlib import Path
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.jobs import _jobs, Job, JobStatus
from src.api.main import app
from src.models.contracts import Document, Metadata
from src.models.table import Table, TableCell, TableRow, TableStatus
from src.pipeline.phase1_pipeline import PipelineResult


@pytest.fixture(autouse=True)
def clear_jobs():
    """Isolate job store between tests."""
    _jobs.clear()
    yield
    _jobs.clear()


@pytest.fixture()
def client():
    return TestClient(app)


def _make_doc_with_table(table: Table) -> Document:
    doc = Document(
        source_pdf_path="test.pdf",
        metadata=Metadata(filename="test.pdf", page_count=1),
    )
    doc.tables = [table]
    return doc


def _make_table(table_id: str = "table-p1-0") -> Table:
    return Table(
        table_id=table_id,
        page_number=1,
        row_count=2,
        col_count=2,
        rows=[
            TableRow(
                cells=[
                    TableCell(text="Name", row_index=0, col_index=0, is_header=True),
                    TableCell(text="Value", row_index=0, col_index=1, is_header=True),
                ],
                is_header_row=True,
            ),
            TableRow(
                cells=[
                    TableCell(text="Alice", row_index=1, col_index=0),
                    TableCell(text="42", row_index=1, col_index=1),
                ],
                is_header_row=False,
            ),
        ],
        status=TableStatus.AUTO_DETECTED,
        extraction_source="pymupdf",
    )


def _inject_job(doc: Document) -> str:
    job_id = "test-job-tables"
    result = PipelineResult(
        source_pdf_path="test.pdf",
        success=True,
        status=doc.processing_status,
        duration_seconds=0.1,
        document=doc,
    )
    job = Job(
        job_id=job_id,
        filename="test.pdf",
        pdf_path=Path("test.pdf"),
        status=JobStatus.COMPLETE,
        created_at=datetime.now(timezone.utc),
        result=result,
    )
    _jobs[job_id] = job
    return job_id


# ---------------------------------------------------------------------------
# GET /documents/{id}/tables
# ---------------------------------------------------------------------------

def test_get_tables_returns_empty_list(client):
    doc = Document(
        source_pdf_path="test.pdf",
        metadata=Metadata(filename="test.pdf", page_count=1),
    )
    job_id = _inject_job(doc)
    resp = client.get(f"/api/documents/{job_id}/tables")
    assert resp.status_code == 200
    assert resp.json() == {"tables": []}


def test_get_tables_returns_table(client):
    table = _make_table()
    doc = _make_doc_with_table(table)
    job_id = _inject_job(doc)

    resp = client.get(f"/api/documents/{job_id}/tables")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tables"]) == 1
    t = data["tables"][0]
    assert t["table_id"] == "table-p1-0"
    assert t["page_number"] == 1
    assert t["row_count"] == 2
    assert t["col_count"] == 2
    assert t["status"] == "auto_detected"
    assert t["extraction_source"] == "pymupdf"
    assert t["caption"] is None
    assert t["summary"] is None
    assert len(t["rows"]) == 2
    assert t["rows"][0]["is_header_row"] is True
    assert t["rows"][0]["cells"][0]["text"] == "Name"
    assert t["rows"][0]["cells"][0]["is_header"] is True


def test_get_tables_unknown_job_returns_404(client):
    resp = client.get("/api/documents/no-such-job/tables")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /documents/{id}/tables/{table_id}
# ---------------------------------------------------------------------------

def test_patch_table_updates_caption_and_summary(client):
    table = _make_table()
    doc = _make_doc_with_table(table)
    job_id = _inject_job(doc)

    resp = client.patch(
        f"/api/documents/{job_id}/tables/table-p1-0",
        json={"caption": "Table 1. Results", "summary": "Shows results."},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["caption"] == "Table 1. Results"
    assert data["summary"] == "Shows results."
    assert data["status"] == "reviewed"


def test_patch_table_updates_header_rows(client):
    table = _make_table()
    doc = _make_doc_with_table(table)
    job_id = _inject_job(doc)

    # Mark row 1 (index 1) as header instead of row 0
    resp = client.patch(
        f"/api/documents/{job_id}/tables/table-p1-0",
        json={"header_row_indices": [1]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["rows"][0]["is_header_row"] is False
    assert data["rows"][1]["is_header_row"] is True


def test_patch_table_unknown_table_returns_404(client):
    doc = Document(
        source_pdf_path="test.pdf",
        metadata=Metadata(filename="test.pdf", page_count=1),
    )
    job_id = _inject_job(doc)
    resp = client.patch(f"/api/documents/{job_id}/tables/no-such-table", json={"caption": "X"})
    assert resp.status_code == 404


def test_patch_table_partial_update_leaves_other_fields(client):
    """Patching only caption should not reset summary (partial update)."""
    table = _make_table()
    table.summary = "Existing summary"
    doc = _make_doc_with_table(table)
    job_id = _inject_job(doc)

    resp = client.patch(
        f"/api/documents/{job_id}/tables/table-p1-0",
        json={"caption": "New caption"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["caption"] == "New caption"
    assert data["summary"] == "Existing summary"


# ---------------------------------------------------------------------------
# POST /documents/{id}/tables (manual creation)
# ---------------------------------------------------------------------------

def test_create_table_returns_new_table(client):
    doc = Document(
        source_pdf_path="test.pdf",
        metadata=Metadata(filename="test.pdf", page_count=1),
    )
    job_id = _inject_job(doc)

    resp = client.post(
        f"/api/documents/{job_id}/tables",
        json={"caption": "My table", "summary": "A summary"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "manually_created"
    assert data["extraction_source"] == "manual"
    assert data["caption"] == "My table"
    assert data["summary"] == "A summary"
    assert data["table_id"].startswith("table-manual-")


def test_create_table_appears_in_get_tables(client):
    doc = Document(
        source_pdf_path="test.pdf",
        metadata=Metadata(filename="test.pdf", page_count=1),
    )
    job_id = _inject_job(doc)

    client.post(f"/api/documents/{job_id}/tables", json={})
    resp = client.get(f"/api/documents/{job_id}/tables")
    assert resp.status_code == 200
    assert len(resp.json()["tables"]) == 1


# ---------------------------------------------------------------------------
# DELETE /documents/{id}/tables/{table_id}
# ---------------------------------------------------------------------------

def test_delete_table_removes_it(client):
    table = _make_table()
    doc = _make_doc_with_table(table)
    job_id = _inject_job(doc)

    resp = client.delete(f"/api/documents/{job_id}/tables/table-p1-0")
    assert resp.status_code == 204

    resp = client.get(f"/api/documents/{job_id}/tables")
    assert resp.json() == {"tables": []}


def test_delete_table_unknown_returns_404(client):
    doc = Document(
        source_pdf_path="test.pdf",
        metadata=Metadata(filename="test.pdf", page_count=1),
    )
    job_id = _inject_job(doc)
    resp = client.delete(f"/api/documents/{job_id}/tables/no-such-id")
    assert resp.status_code == 404
