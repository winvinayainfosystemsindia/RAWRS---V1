"""POST /documents/{id}/corrections/bulk-action — one judgement over one cause.

Fixture mirrors tests/test_corrections_api.py: a synthetic COMPLETE job whose
Document carries headings and PROPOSED HeadingVerifier corrections.
"""

import uuid
from datetime import datetime, timezone

import pytest


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from src.api.main import app
    return TestClient(app)


def _job(tmp_path, specs, basis="deterministic"):
    """specs: (field, reason_code, proposed_value) per heading. Returns (job_id, corrections, headings).

    ``basis`` defaults to deterministic: these tests exercise the bulk mechanics,
    which only deterministic corrections may use (Phase E).
    """
    import src.verification.headings  # noqa: F401 - registers HeadingVerifier
    from src.api.jobs import Job, JobStatus, _jobs, _lock
    from src.models.contracts import Document, Heading, HeadingLevel, Metadata, ProcessingStatus
    from src.models.correction import CorrectionRecord, CorrectionStatus, DecisionBasis
    from src.pipeline.phase1_pipeline import PipelineResult

    doc = Document(source_pdf_path="test.pdf", metadata=Metadata(filename="test.pdf"))
    for order, (field, reason_code, proposed) in enumerate(specs):
        heading = Heading(level=HeadingLevel.H3, text=f"Title {order}", page_number=1, document_order=order)
        doc.headings.append(heading)
        doc.corrections.append(
            CorrectionRecord(
                object_type="heading",
                object_id=heading.id,
                field=field,
                original_value="3",
                proposed_value=proposed,
                reason="test",
                reason_code=reason_code,
                status=CorrectionStatus.PROPOSED,
                confidence=0.99,
                decision_basis=DecisionBasis(basis),
            )
        )
    job_id = uuid.uuid4().hex
    result = PipelineResult(
        source_pdf_path="test.pdf", success=True, status=ProcessingStatus.VALIDATED,
        duration_seconds=0.1, document=doc,
    )
    with _lock:
        _jobs[job_id] = Job(
            job_id=job_id, filename="test.pdf", pdf_path=tmp_path / "test.pdf",
            status=JobStatus.COMPLETE, created_at=datetime.now(timezone.utc), result=result,
        )
    return job_id, doc.corrections, doc.headings


LEVEL = ("level_mismatch", "HEADING_LEVEL_MISMATCH")


@pytest.fixture
def jobs():
    from src.api.jobs import _jobs, _lock
    created = []
    yield created
    with _lock:
        for job_id in created:
            _jobs.pop(job_id, None)


def _bulk(client, job_id, ids, action):
    return client.post(
        f"/api/documents/{job_id}/corrections/bulk-action",
        json={"correction_ids": [c.correction_id for c in ids], "action": action},
    )


def test_accepts_one_cause_and_applies_every_target(client, tmp_path, jobs):
    job_id, corrections, headings = _job(tmp_path, [(*LEVEL, "1"), (*LEVEL, "2")])
    jobs.append(job_id)

    resp = _bulk(client, job_id, corrections, "accept")

    assert resp.status_code == 200
    assert [c["status"] for c in resp.json()["corrections"]] == ["accepted", "accepted"]
    assert [h.level for h in headings] == [1, 2]
    assert all(c.telemetry_events for c in corrections)


def test_refuses_corrections_of_different_causes(client, tmp_path, jobs):
    job_id, corrections, headings = _job(
        tmp_path, [(*LEVEL, "1"), ("text_correction", "HEADING_TEXT_OCR_ERROR", "Fixed")]
    )
    jobs.append(job_id)

    resp = _bulk(client, job_id, corrections, "accept")

    assert resp.status_code == 422
    assert headings[0].level == 3
    assert all(c.status.value == "proposed" for c in corrections)


def test_a_failure_mid_batch_rolls_back_and_changes_nothing(client, tmp_path, jobs):
    # "9" is not a HeadingLevel: the third apply raises after two succeeded.
    job_id, corrections, headings = _job(tmp_path, [(*LEVEL, "1"), (*LEVEL, "2"), (*LEVEL, "9")])
    jobs.append(job_id)

    resp = _bulk(client, job_id, corrections, "accept")

    assert resp.status_code == 409
    assert "nothing was changed" in resp.json()["detail"]
    assert [h.level for h in headings] == [3, 3, 3]
    assert all(c.status.value == "proposed" and c.reviewed_at is None for c in corrections)
    assert not any(c.telemetry_events for c in corrections)


def test_undo_reverses_the_whole_batch(client, tmp_path, jobs):
    job_id, corrections, headings = _job(tmp_path, [(*LEVEL, "1"), (*LEVEL, "2")])
    jobs.append(job_id)
    _bulk(client, job_id, corrections, "accept")

    resp = _bulk(client, job_id, corrections, "undo")

    assert resp.status_code == 200
    assert [c["status"] for c in resp.json()["corrections"]] == ["reverted", "reverted"]
    assert [h.level for h in headings] == [3, 3]


def test_refuses_already_decided_targets(client, tmp_path, jobs):
    job_id, corrections, _ = _job(tmp_path, [(*LEVEL, "1"), (*LEVEL, "2")])
    jobs.append(job_id)
    client.patch(f"/api/documents/{job_id}/corrections/{corrections[0].correction_id}", json={"action": "reject"})

    resp = _bulk(client, job_id, corrections, "accept")

    assert resp.status_code == 409
    assert corrections[1].status.value == "proposed"


@pytest.mark.parametrize("action", ["edit", "needs_review"])
def test_refuses_non_bulk_actions(client, tmp_path, jobs, action):
    job_id, corrections, _ = _job(tmp_path, [(*LEVEL, "1"), (*LEVEL, "2")])
    jobs.append(job_id)

    assert _bulk(client, job_id, corrections, action).status_code == 422


def test_unknown_correction_changes_nothing(client, tmp_path, jobs):
    job_id, corrections, headings = _job(tmp_path, [(*LEVEL, "1")])
    jobs.append(job_id)

    resp = client.post(
        f"/api/documents/{job_id}/corrections/bulk-action",
        json={"correction_ids": [corrections[0].correction_id, "nope"], "action": "accept"},
    )

    assert resp.status_code == 404
    assert headings[0].level == 3


def test_importing_the_api_registers_every_verifier():
    # A fresh interpreter: this test process has already imported verifiers,
    # which is exactly what hid the gap on a restarted server.
    import subprocess
    import sys

    code = (
        "import src.api.routes; from src.verification.engine import engine; "
        "print(','.join(sorted(engine._verifiers)))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    registered = set(out.stdout.strip().splitlines()[-1].split(","))

    assert {"figure", "heading", "list", "table", "footnote", "paragraph", "metadata", "reading_order"} <= registered


def test_correction_out_carries_reason_code(client, tmp_path, jobs):
    job_id, _, _ = _job(tmp_path, [(*LEVEL, "1")])
    jobs.append(job_id)

    data = client.get(f"/api/documents/{job_id}/corrections").json()

    assert data["corrections"][0]["reason_code"] == "HEADING_LEVEL_MISMATCH"


def test_refuses_judgement_corrections_however_confident(client, tmp_path, jobs):
    # Same cause, 0.99 confidence: still individual reviewer decisions.
    job_id, corrections, headings = _job(tmp_path, [(*LEVEL, "1"), (*LEVEL, "2")], basis="judgement")
    jobs.append(job_id)

    for action in ("accept", "reject", "ignore"):
        resp = _bulk(client, job_id, corrections, action)
        assert resp.status_code == 422
        assert "individual reviewer decision" in resp.json()["detail"]
    assert [h.level for h in headings] == [3, 3]
    assert all(c.status.value == "proposed" and not c.telemetry_events for c in corrections)


def test_one_judgement_target_blocks_the_whole_batch(client, tmp_path, jobs):
    from src.models.correction import DecisionBasis

    job_id, corrections, headings = _job(tmp_path, [(*LEVEL, "1"), (*LEVEL, "2")])
    jobs.append(job_id)
    corrections[1].decision_basis = DecisionBasis.JUDGEMENT

    assert _bulk(client, job_id, corrections, "accept").status_code == 422
    assert [h.level for h in headings] == [3, 3]
