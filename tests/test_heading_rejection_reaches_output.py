"""A reviewer's rejection reaches the document, not just a status field.

The workspace chain is: decision -> semantic document -> Markdown -> DOCX
-> validation -> history. Before this it broke at the first link:
HeadingReviewStatus.REJECTED had *zero* consumers — markdown_builder,
docx_generator, the validator and the accessibility rules all ignored it —
so a reviewer could mark a line "not a heading" and it would keep
rendering as one forever.

Rejection now records a CorrectionRecord and applies it through
HeadingVerifier, the same removal path likely_running_header and
positional_only_h1 already use. These tests follow the decision all the
way to rendered Markdown, and back again via undo.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.markdown.markdown_builder import build_markdown
from src.api.jobs import Job, JobStatus, _jobs
from src.models.bounding_box import BoundingBox
from src.models.contracts import Document, Heading, HeadingLevel, Metadata, Page, TextBlock
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


def _document() -> Document:
    """One page whose first line RAWRS wrongly called a heading."""
    text = "Article\nreal body prose follows here\n"
    return Document(
        source_pdf_path="x.pdf",
        metadata=Metadata(filename="x.pdf", page_count=1),
        pages=[Page(page_number=1, raw_text=text, cleaned_text=text)],
        headings=[
            Heading(level=HeadingLevel(1), text="Article", page_number=1, document_order=0)
        ],
        blocks=[
            TextBlock(
                page_number=1,
                text="Article",
                bbox=BoundingBox(x0=0, y0=0, x1=50, y1=10),
                order=0,
            ),
            TextBlock(
                page_number=1,
                text="real body prose follows here",
                bbox=BoundingBox(x0=0, y0=20, x1=50, y1=30),
                order=1,
            ),
        ],
    )


def _inject(document: Document, job_id: str = "test-job-reject") -> str:
    _jobs[job_id] = Job(
        job_id=job_id,
        filename="x.pdf",
        pdf_path=Path("x.pdf"),
        status=JobStatus.COMPLETE,
        created_at=datetime.now(timezone.utc),
        result=PipelineResult(
            source_pdf_path="x.pdf",
            success=True,
            status=document.processing_status,
            duration_seconds=0.1,
            document=document,
        ),
    )
    return job_id


def _doc(job_id: str) -> Document:
    return _jobs[job_id].result.document


class TestRejectionReachesTheDocument:
    def test_rejected_heading_is_removed_from_the_semantic_document(self, client) -> None:
        job_id = _inject(_document())
        response = client.patch(
            f"/api/documents/{job_id}/headings/0", json={"action": "reject"}
        )
        assert response.status_code == 200
        assert response.json()["review_status"] == "rejected"
        assert [h.text for h in _doc(job_id).headings if not h.is_page_marker] == []

    def test_rejection_is_recorded_as_a_correction(self, client) -> None:
        job_id = _inject(_document())
        client.patch(f"/api/documents/{job_id}/headings/0", json={"action": "reject"})

        corrections = [c for c in _doc(job_id).corrections if c.field == "reviewer_rejected"]
        assert len(corrections) == 1
        assert corrections[0].reason_code == "HEADING_REJECTED_BY_REVIEWER"
        assert corrections[0].provider == "manual_reviewer"
        # Terminal — the reviewer has decided, so it must not gate export.
        assert corrections[0].status is CorrectionStatus.EDITED

    def test_rejection_reaches_rendered_markdown(self, client) -> None:
        # The link that was missing entirely: the decision changing output.
        job_id = _inject(_document())
        before = build_markdown(_doc(job_id))
        assert "# Article" in before

        client.patch(f"/api/documents/{job_id}/headings/0", json={"action": "reject"})

        after = build_markdown(_doc(job_id))
        assert "# Article" not in after
        # Demoted, not deleted — it is body text, which is what "not a
        # heading" means.
        assert "Article" in after
        assert "real body prose follows here" in after

    def test_undo_restores_the_heading_and_the_markdown(self, client) -> None:
        job_id = _inject(_document())
        client.patch(f"/api/documents/{job_id}/headings/0", json={"action": "reject"})
        correction = [c for c in _doc(job_id).corrections if c.field == "reviewer_rejected"][0]

        response = client.patch(
            f"/api/documents/{job_id}/corrections/{correction.correction_id}",
            json={"action": "undo"},
        )
        assert response.status_code == 200
        assert "Article" in {h.text for h in _doc(job_id).headings}
        assert "# Article" in build_markdown(_doc(job_id))


class TestApproveIsStillAnAnnotation:
    def test_approve_changes_no_structure(self, client) -> None:
        # Approve asserts the detection was right, so it must leave both
        # the document and the output alone.
        job_id = _inject(_document())
        client.patch(f"/api/documents/{job_id}/headings/0", json={"action": "approve"})
        assert [h.text for h in _doc(job_id).headings] == ["Article"]
        assert [c for c in _doc(job_id).corrections if c.field == "reviewer_rejected"] == []
