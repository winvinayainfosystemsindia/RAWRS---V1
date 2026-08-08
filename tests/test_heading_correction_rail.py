"""Reviewer heading edits go through the correction rail (L-2).

Before this, ``PATCH /documents/{job}/headings/{order}`` mutated
``Heading.level``/``.text`` in place and recorded only a per-object
``HeadingReviewStatus``. The result was that the most consequential
decisions in the system — the human's own — produced no audit row, no
evidence link and no undo, while every Mathpix-derived correction got all
three. ``CorrectionStatus``'s own docstring says the six-state lifecycle
is the one every reviewer step uses and "no per-object-type status enum
is ever needed again".

What is pinned here:

1. A level/text edit appends a CorrectionRecord and the *rail* performs
   the mutation (not the handler).
2. Undo works, via the generic engine.revert_correction — no
   heading-specific undo code was written for this.
3. The existing API contract is unchanged: review_status is still
   maintained as a derived mirror, and no-op edits create no rows.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.api.jobs import Job, JobStatus, _jobs
from src.models.contracts import Document, Heading, HeadingLevel, Metadata
from src.models.correction import CorrectionStatus
from src.pipeline.phase1_pipeline import PipelineResult


@pytest.fixture(autouse=True)
def _clean_jobs():
    before = set(_jobs)
    yield
    for job_id in set(_jobs) - before:
        _jobs.pop(job_id, None)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from src.api.main import app

    return TestClient(app)


def _inject(heading: Heading, job_id: str = "test-job-rail") -> str:
    document = Document(
        source_pdf_path="test.pdf",
        metadata=Metadata(filename="test.pdf", page_count=1),
    )
    document.headings = [heading]
    _jobs[job_id] = Job(
        job_id=job_id,
        filename="test.pdf",
        pdf_path=Path("test.pdf"),
        status=JobStatus.COMPLETE,
        created_at=datetime.now(timezone.utc),
        result=PipelineResult(
            source_pdf_path="test.pdf",
            success=True,
            status=document.processing_status,
            duration_seconds=0.1,
            document=document,
        ),
    )
    return job_id


def _heading(level: int = 3, text: str = "Overview") -> Heading:
    return Heading(level=HeadingLevel(level), text=text, page_number=1, document_order=0)


def _document(job_id: str) -> Document:
    return _jobs[job_id].result.document


def _heading_corrections(document: Document):
    """Corrections this handler created. The fixture document has no
    others, but being explicit keeps the assertions honest if it grows."""
    return [c for c in document.corrections if c.object_type == "heading"]


class TestLevelEdit:
    def test_level_change_creates_an_audit_row(self, client) -> None:
        job_id = _inject(_heading(level=3))
        response = client.patch(f"/api/documents/{job_id}/headings/0", json={"level": 2})
        assert response.status_code == 200
        assert response.json()["level"] == 2

        corrections = _heading_corrections(_document(job_id))
        assert len(corrections) == 1
        correction = corrections[0]
        assert correction.field == "level_mismatch"
        assert correction.object_id == "heading-0"
        assert correction.original_value == "3"
        assert correction.proposed_value == "2"
        assert correction.provider == "manual_reviewer"
        assert correction.reason_code == "HEADING_LEVEL_MANUAL_EDIT"
        assert correction.reviewed_at is not None

    def test_the_rail_performs_the_mutation(self, client) -> None:
        # The handler no longer assigns heading.level itself; if the rail
        # were bypassed or the verifier unregistered, the level would not
        # change even though a correction row appeared.
        job_id = _inject(_heading(level=1))
        client.patch(f"/api/documents/{job_id}/headings/0", json={"level": 4})
        assert _document(job_id).headings[0].level is HeadingLevel.H4

    def test_status_is_terminal_so_export_is_not_blocked(self, client) -> None:
        job_id = _inject(_heading(level=3))
        client.patch(f"/api/documents/{job_id}/headings/0", json={"level": 2})
        assert _heading_corrections(_document(job_id))[0].status is CorrectionStatus.EDITED

    def test_review_status_mirror_is_preserved(self, client) -> None:
        # Existing API consumers still read review_status; the correction
        # is the audit trail, not a replacement for the response contract.
        job_id = _inject(_heading(level=3))
        response = client.patch(f"/api/documents/{job_id}/headings/0", json={"level": 2})
        assert response.json()["review_status"] == "level_changed"

    def test_no_op_edit_creates_no_row(self, client) -> None:
        job_id = _inject(_heading(level=3))
        client.patch(f"/api/documents/{job_id}/headings/0", json={"level": 3})
        assert _heading_corrections(_document(job_id)) == []

    def test_invalid_level_still_rejected_before_any_row(self, client) -> None:
        job_id = _inject(_heading(level=3))
        response = client.patch(f"/api/documents/{job_id}/headings/0", json={"level": 6})
        assert response.status_code == 422
        assert _heading_corrections(_document(job_id)) == []


class TestTextEdit:
    def test_text_change_creates_an_audit_row_and_mutates(self, client) -> None:
        job_id = _inject(_heading(text="Overveiw"))
        response = client.patch(
            f"/api/documents/{job_id}/headings/0", json={"text": "Overview"}
        )
        assert response.status_code == 200

        correction = _heading_corrections(_document(job_id))[0]
        assert correction.field == "text_correction"
        assert correction.original_value == "Overveiw"
        assert correction.proposed_value == "Overview"
        assert correction.reason_code == "HEADING_TEXT_MANUAL_EDIT"
        assert _document(job_id).headings[0].text == "Overview"

    def test_blank_text_still_rejected_before_any_row(self, client) -> None:
        job_id = _inject(_heading(text="Overview"))
        response = client.patch(f"/api/documents/{job_id}/headings/0", json={"text": "   "})
        assert response.status_code == 422
        assert _heading_corrections(_document(job_id)) == []


class TestUndo:
    """The whole point of routing through the rail: undo for free."""

    def test_undo_restores_the_previous_level(self, client) -> None:
        job_id = _inject(_heading(level=3))
        client.patch(f"/api/documents/{job_id}/headings/0", json={"level": 2})
        correction = _heading_corrections(_document(job_id))[0]
        assert _document(job_id).headings[0].level is HeadingLevel.H2

        response = client.patch(
            f"/api/documents/{job_id}/corrections/{correction.correction_id}",
            json={"action": "undo"},
        )
        assert response.status_code == 200
        assert _document(job_id).headings[0].level is HeadingLevel.H3

    def test_undo_restores_the_previous_text(self, client) -> None:
        job_id = _inject(_heading(text="Overveiw"))
        client.patch(f"/api/documents/{job_id}/headings/0", json={"text": "Overview"})
        correction = _heading_corrections(_document(job_id))[0]

        client.patch(
            f"/api/documents/{job_id}/corrections/{correction.correction_id}",
            json={"action": "undo"},
        )
        assert _document(job_id).headings[0].text == "Overveiw"


class TestEvidenceTravelsWithTheDecision:
    def test_correction_carries_the_headings_detection_evidence(self, client) -> None:
        # L3.1 put the detection signals on Heading.evidence_items; a
        # correction against that heading copies them, so a reviewer sees
        # what RAWRS believed when it made the original call.
        from src.verification.evidence import EvidenceSignal

        heading = _heading(level=3)
        heading.confidence = 0.35
        heading.evidence_items = [
            EvidenceSignal(name="title_position", score=0.35, weight=1.0, note="position only")
        ]
        job_id = _inject(heading)
        client.patch(f"/api/documents/{job_id}/headings/0", json={"level": 2})

        correction = _heading_corrections(_document(job_id))[0]
        assert correction.confidence == 0.35
        assert [s.name for s in correction.evidence_items] == ["title_position"]
