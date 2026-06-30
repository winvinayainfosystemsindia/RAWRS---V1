"""Tests for the image review API endpoints (FEATURE_012).

Uses FastAPI's TestClient with a synthetic in-memory job containing one image.
All AI calls run in RAWRS_AI_STUB mode so no model is loaded.
"""

import pytest


@pytest.fixture(autouse=True)
def stub_ai(monkeypatch):
    monkeypatch.setenv("RAWRS_AI_STUB", "1")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from src.api.main import app
    return TestClient(app)


@pytest.fixture
def synthetic_job(tmp_path):
    """Register a synthetic COMPLETE job with one reviewable image. Yields (job_id, image_id)."""
    from src.models.figure import AltTextStatus, Figure
    from src.models.image import Image
    from src.models.bounding_box import BoundingBox
    from src.models.document import Document
    from src.models.metadata import Metadata
    from src.models.contracts import ProcessingStatus
    from src.pipeline.phase1_pipeline import PipelineResult
    from src.api.jobs import Job, JobStatus, _jobs, _lock
    import uuid
    from datetime import datetime, timezone

    img_file = tmp_path / "test_img.png"
    img_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    figure = Figure(
        label="Figure 1",
        number=1,
        caption="Test caption.",
        alt_text="description pending human review",
        alt_text_status=AltTextStatus.PENDING_REVIEW,
    )
    image = Image(
        image_id="img001",
        page_number=1,
        file_path=str(img_file),
        width=200,
        height=150,
        bbox=BoundingBox(x0=100.0, y0=100.0, x1=300.0, y1=250.0),
        figure=figure,
    )
    doc = Document(source_pdf_path="test.pdf", metadata=Metadata(filename="test.pdf"))
    doc.images = [image]

    result = PipelineResult(
        source_pdf_path="test.pdf",
        success=True,
        status=ProcessingStatus.VALIDATED,
        duration_seconds=0.1,
        document=doc,
    )
    job_id = uuid.uuid4().hex
    job = Job(
        job_id=job_id,
        filename="test.pdf",
        pdf_path=tmp_path / "test.pdf",
        status=JobStatus.COMPLETE,
        created_at=datetime.now(timezone.utc),
        result=result,
    )
    with _lock:
        _jobs[job_id] = job

    yield job_id, "img001"

    with _lock:
        _jobs.pop(job_id, None)


# ---------------------------------------------------------------------------
# generate-alt-text endpoint
# ---------------------------------------------------------------------------

class TestGenerateAltText:
    def test_generate_sets_ai_generated_status(self, client, synthetic_job):
        job_id, image_id = synthetic_job
        resp = client.post(f"/api/documents/{job_id}/images/{image_id}/generate-alt-text")
        assert resp.status_code == 200
        data = resp.json()
        assert data["figure"]["alt_text_status"] == "ai_generated"
        assert data["figure"]["ai_description"]
        assert data["figure"]["ai_confidence"] is not None
        assert isinstance(data["figure"]["ai_warnings"], list)

    def test_generate_unknown_image_returns_404(self, client, synthetic_job):
        job_id, _ = synthetic_job
        resp = client.post(f"/api/documents/{job_id}/images/nonexistent/generate-alt-text")
        assert resp.status_code == 404

    def test_generate_unknown_job_returns_404(self, client):
        resp = client.post("/api/documents/doesnotexist/images/img001/generate-alt-text")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH review endpoint
# ---------------------------------------------------------------------------

class TestReviewImage:
    def test_approve_with_custom_text(self, client, synthetic_job):
        job_id, image_id = synthetic_job
        resp = client.patch(
            f"/api/documents/{job_id}/images/{image_id}",
            json={"action": "approve", "alt_text": "A bar chart of results."},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["figure"]["alt_text_status"] == "approved"
        assert data["figure"]["alt_text"] == "A bar chart of results."

    def test_reject(self, client, synthetic_job):
        job_id, image_id = synthetic_job
        resp = client.patch(
            f"/api/documents/{job_id}/images/{image_id}",
            json={"action": "reject"},
        )
        assert resp.status_code == 200
        assert resp.json()["figure"]["alt_text_status"] == "rejected"

    def test_mark_decorative(self, client, synthetic_job):
        job_id, image_id = synthetic_job
        resp = client.patch(
            f"/api/documents/{job_id}/images/{image_id}",
            json={"action": "mark_decorative"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["figure"]["alt_text_status"] == "decorative"
        assert data["figure"]["alt_text"] == ""

    def test_mark_complex(self, client, synthetic_job):
        job_id, image_id = synthetic_job
        resp = client.patch(
            f"/api/documents/{job_id}/images/{image_id}",
            json={"action": "mark_complex"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["figure"]["alt_text_status"] == "complex"
        assert "[Complex image" in data["figure"]["alt_text"]

    def test_skip(self, client, synthetic_job):
        job_id, image_id = synthetic_job
        resp = client.patch(
            f"/api/documents/{job_id}/images/{image_id}",
            json={"action": "skip"},
        )
        assert resp.status_code == 200
        assert resp.json()["figure"]["alt_text_status"] == "skipped"

    def test_approve_empty_text_is_422(self, client, synthetic_job):
        job_id, image_id = synthetic_job
        resp = client.patch(
            f"/api/documents/{job_id}/images/{image_id}",
            json={"action": "approve", "alt_text": ""},
        )
        assert resp.status_code == 422

    def test_edit_saves_draft(self, client, synthetic_job):
        job_id, image_id = synthetic_job
        resp = client.patch(
            f"/api/documents/{job_id}/images/{image_id}",
            json={"action": "edit", "alt_text": "My draft text."},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["figure"]["alt_text"] == "My draft text."
        assert data["figure"]["alt_text_status"] == "ai_generated"

    def test_unknown_image_returns_404(self, client, synthetic_job):
        job_id, _ = synthetic_job
        resp = client.patch(
            f"/api/documents/{job_id}/images/ghost",
            json={"action": "skip"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Bulk action endpoint
# ---------------------------------------------------------------------------

class TestBulkAction:
    def test_bulk_approve(self, client, synthetic_job):
        job_id, image_id = synthetic_job
        resp = client.post(
            f"/api/documents/{job_id}/images/bulk-action",
            json={"image_ids": [image_id], "action": "approve"},
        )
        assert resp.status_code == 200
        images = resp.json()["images"]
        img = next(i for i in images if i["image_id"] == image_id)
        assert img["figure"]["alt_text_status"] == "approved"

    def test_bulk_skip_unknown_ids_are_ignored(self, client, synthetic_job):
        job_id, image_id = synthetic_job
        resp = client.post(
            f"/api/documents/{job_id}/images/bulk-action",
            json={"image_ids": ["nonexistent", image_id], "action": "skip"},
        )
        assert resp.status_code == 200
        images = resp.json()["images"]
        img = next(i for i in images if i["image_id"] == image_id)
        assert img["figure"]["alt_text_status"] == "skipped"

    def test_bulk_all_unknown_ids_returns_200(self, client, synthetic_job):
        job_id, _ = synthetic_job
        resp = client.post(
            f"/api/documents/{job_id}/images/bulk-action",
            json={"image_ids": ["ghost1", "ghost2"], "action": "mark_decorative"},
        )
        assert resp.status_code == 200

    def test_bulk_mark_decorative(self, client, synthetic_job):
        job_id, image_id = synthetic_job
        resp = client.post(
            f"/api/documents/{job_id}/images/bulk-action",
            json={"image_ids": [image_id], "action": "mark_decorative"},
        )
        assert resp.status_code == 200
        images = resp.json()["images"]
        img = next(i for i in images if i["image_id"] == image_id)
        assert img["figure"]["alt_text_status"] == "decorative"
        assert img["figure"]["alt_text"] == ""
