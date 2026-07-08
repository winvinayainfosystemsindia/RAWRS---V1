"""Tests for the generic Corrections API (GET/PATCH
/documents/{id}/corrections) and the Accessibility Readiness endpoint
(GET /documents/{id}/readiness).

Mirrors tests/test_image_review_api.py's synthetic-job fixture pattern.
Uses HeadingVerifier (already registered) as the concrete asset type
under test — the endpoints themselves are asset-agnostic.
"""

import uuid
from datetime import datetime, timezone

import pytest


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from src.api.main import app
    return TestClient(app)


@pytest.fixture
def synthetic_job(tmp_path):
    """A COMPLETE job with one heading and one PROPOSED level_mismatch
    correction. Yields (job_id, correction_id, heading)."""
    import src.verification.headings  # noqa: F401 - registers HeadingVerifier
    from src.models.contracts import Document, Heading, HeadingLevel, Metadata, ProcessingStatus
    from src.models.correction import CorrectionRecord, CorrectionStatus
    from src.models.validation_issue import Severity, ValidationIssue
    from src.pipeline.phase1_pipeline import PipelineResult
    from src.api.jobs import Job, JobStatus, _jobs, _lock

    heading = Heading(level=HeadingLevel.H3, text="Some Title", page_number=1, document_order=0)
    doc = Document(source_pdf_path="test.pdf", metadata=Metadata(filename="test.pdf"))
    doc.headings = [heading]
    doc.validation_issues = [
        ValidationIssue(severity=Severity.WARNING, rule_id="HEADING_VERIFY_003", message="Heading level disagrees.")
    ]
    correction = CorrectionRecord(
        object_type="heading",
        object_id=heading.id,
        field="level_mismatch",
        original_value="3",
        proposed_value="1",
        reason="Heading level disagrees with PDF typography.",
        reason_code="HEADING_LEVEL_MISMATCH",
        status=CorrectionStatus.PROPOSED,
    )
    doc.corrections = [correction]

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

    yield job_id, correction.correction_id, heading

    with _lock:
        _jobs.pop(job_id, None)


class TestGetCorrections:
    def test_lists_corrections(self, client, synthetic_job):
        job_id, correction_id, _heading = synthetic_job
        resp = client.get(f"/api/documents/{job_id}/corrections")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["corrections"]) == 1
        assert data["corrections"][0]["correction_id"] == correction_id
        assert data["corrections"][0]["object_type"] == "heading"
        assert data["corrections"][0]["current_value"] == "3"
        assert data["corrections"][0]["suggested_value"] == "1"
        assert data["corrections"][0]["status"] == "proposed"

    def test_filters_by_object_type(self, client, synthetic_job):
        job_id, _correction_id, _heading = synthetic_job
        resp = client.get(f"/api/documents/{job_id}/corrections?object_type=figure")
        assert resp.status_code == 200
        assert resp.json()["corrections"] == []

    def test_unknown_job_returns_404(self, client):
        resp = client.get("/api/documents/doesnotexist/corrections")
        assert resp.status_code == 404


class TestReviewCorrection:
    def test_accept_applies_and_sets_status(self, client, synthetic_job):
        job_id, correction_id, heading = synthetic_job
        resp = client.patch(
            f"/api/documents/{job_id}/corrections/{correction_id}", json={"action": "accept"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert heading.level == 1  # HeadingLevel.H1's int value

    def test_reject_does_not_mutate(self, client, synthetic_job):
        job_id, correction_id, heading = synthetic_job
        resp = client.patch(
            f"/api/documents/{job_id}/corrections/{correction_id}", json={"action": "reject"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"
        assert heading.level == 3

    def test_edit_replaces_proposed_value_before_applying(self, client, synthetic_job):
        job_id, correction_id, heading = synthetic_job
        resp = client.patch(
            f"/api/documents/{job_id}/corrections/{correction_id}",
            json={"action": "edit", "proposed_value": "2"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "edited"
        assert data["suggested_value"] == "2"
        assert heading.level == 2

    def test_ignore_does_not_mutate(self, client, synthetic_job):
        job_id, correction_id, heading = synthetic_job
        resp = client.patch(
            f"/api/documents/{job_id}/corrections/{correction_id}", json={"action": "ignore"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"
        assert heading.level == 3


class TestDocumentVersionBump:
    """FEATURE_020 — document.version is the generic signal
    _needs_export_regen() now compares against, replacing per-field
    checks. It must bump exactly when engine.apply_correction()/
    revert_correction() actually mutate the document, not on every
    review action."""

    def test_accept_bumps_version(self, client, synthetic_job):
        from src.api.jobs import _jobs
        job_id, correction_id, _ = synthetic_job
        assert _jobs[job_id].result.document.version == 0
        client.patch(f"/api/documents/{job_id}/corrections/{correction_id}", json={"action": "accept"})
        assert _jobs[job_id].result.document.version == 1

    def test_reject_does_not_bump_version(self, client, synthetic_job):
        from src.api.jobs import _jobs
        job_id, correction_id, _ = synthetic_job
        client.patch(f"/api/documents/{job_id}/corrections/{correction_id}", json={"action": "reject"})
        assert _jobs[job_id].result.document.version == 0

    def test_revert_after_accept_bumps_again(self, client, synthetic_job):
        from src.api.jobs import _jobs
        job_id, correction_id, _ = synthetic_job
        client.patch(f"/api/documents/{job_id}/corrections/{correction_id}", json={"action": "accept"})
        resp = client.patch(f"/api/documents/{job_id}/corrections/{correction_id}", json={"action": "undo"})
        assert resp.status_code == 200
        assert _jobs[job_id].result.document.version == 2

    def test_needs_review_sets_pending_status(self, client, synthetic_job):
        job_id, correction_id, _heading = synthetic_job
        resp = client.patch(
            f"/api/documents/{job_id}/corrections/{correction_id}", json={"action": "needs_review"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending_review"

    def test_undo_after_accept_restores_original(self, client, synthetic_job):
        job_id, correction_id, heading = synthetic_job
        client.patch(f"/api/documents/{job_id}/corrections/{correction_id}", json={"action": "accept"})
        assert heading.level == 1
        resp = client.patch(
            f"/api/documents/{job_id}/corrections/{correction_id}", json={"action": "undo"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "reverted"
        assert heading.level == 3

    def test_unknown_correction_returns_404(self, client, synthetic_job):
        job_id, _correction_id, _heading = synthetic_job
        resp = client.patch(
            f"/api/documents/{job_id}/corrections/nonexistent", json={"action": "accept"}
        )
        assert resp.status_code == 404


class TestReadinessEndpoint:
    def test_reports_category_from_validation_issues(self, client, synthetic_job):
        job_id, _correction_id, _heading = synthetic_job
        resp = client.get(f"/api/documents/{job_id}/readiness")
        assert resp.status_code == 200
        data = resp.json()
        categories = {c["category"]: c for c in data["categories"]}
        assert "HEADING" in categories
        assert categories["HEADING"]["ready"] is False
        assert data["ready"] is False

    def test_unknown_job_returns_404(self, client):
        resp = client.get("/api/documents/doesnotexist/readiness")
        assert resp.status_code == 404
