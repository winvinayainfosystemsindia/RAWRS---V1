"""Phase E — producer-owned decision basis, independent of confidence and
auto_apply, plus the single-correction lifecycle guard."""

import uuid
from datetime import datetime, timezone

import pytest

from src.models.correction import CorrectionRecord, CorrectionStatus, DecisionBasis
from src.models.verification import Finding


def test_default_is_judgement_for_findings_and_records():
    assert Finding(asset_type="heading", kind="level_mismatch").decision_basis is DecisionBasis.JUDGEMENT
    record = CorrectionRecord(object_type="heading", field="level_mismatch", original_value="3", proposed_value="2")
    assert record.decision_basis is DecisionBasis.JUDGEMENT


def test_serialises_and_round_trips_independently_of_confidence():
    record = CorrectionRecord(
        object_type="heading", field="f", original_value="a", proposed_value="b",
        decision_basis=DecisionBasis.DETERMINISTIC, confidence=0.2,
    )
    data = record.model_dump(mode="json")
    assert data["decision_basis"] == "deterministic"
    back = CorrectionRecord.model_validate(data)
    assert (back.decision_basis, back.confidence) == (DecisionBasis.DETERMINISTIC, 0.2)


def test_persisted_record_without_the_field_loads_as_judgement():
    legacy = {"object_type": "figure", "field": "page_mismatch", "original_value": "26",
              "proposed_value": "25", "confidence": 0.99, "status": "proposed"}
    assert CorrectionRecord.model_validate(legacy).decision_basis is DecisionBasis.JUDGEMENT


def test_engine_propagates_the_producer_value():
    import src.verification.headings  # noqa: F401 - registers HeadingVerifier
    from src.models.contracts import Document, Metadata
    from src.verification.engine import engine

    doc = Document(source_pdf_path="t.pdf", metadata=Metadata(filename="t.pdf"))
    kind = next(iter(engine._verifiers["heading"].rule_table()))
    engine.findings_to_corrections(doc, [
        Finding(asset_type="heading", kind=kind, confidence=0.3, decision_basis=DecisionBasis.DETERMINISTIC),
        Finding(asset_type="heading", kind=kind, confidence=0.99),
    ])
    assert [(c.decision_basis, c.confidence) for c in doc.corrections] == [
        (DecisionBasis.DETERMINISTIC, 0.3), (DecisionBasis.JUDGEMENT, 0.99),
    ]


def test_auto_applied_artifacts_stay_judgement():
    # Decision 1: auto_apply is a policy-backed heuristic, not a deterministic basis.
    from src.models.text_block import ArtifactClass
    from src.verification.artifacts import SuppressionPolicy, propose_suppressions
    from tests.test_artifact_suppression import _block

    auto = propose_suppressions([_block("12", artifact_class=ArtifactClass.PAGE_NUMBER, confidence=0.9)])[
        SuppressionPolicy.AUTO
    ]
    assert auto and auto[0].auto_apply is True
    assert auto[0].decision_basis is DecisionBasis.JUDGEMENT


# --- API ---------------------------------------------------------------------


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from src.api.main import app
    return TestClient(app)


@pytest.fixture
def mixed_job(tmp_path):
    """One document, one cause, three proposals: high-confidence deterministic,
    high-confidence judgement, low-confidence judgement."""
    import src.verification.headings  # noqa: F401
    from src.api.jobs import Job, JobStatus, _jobs, _lock
    from src.models.contracts import Document, Heading, HeadingLevel, Metadata, ProcessingStatus
    from src.pipeline.phase1_pipeline import PipelineResult

    doc = Document(source_pdf_path="test.pdf", metadata=Metadata(filename="test.pdf"))
    specs = [(0.99, DecisionBasis.DETERMINISTIC), (0.99, DecisionBasis.JUDGEMENT), (0.2, DecisionBasis.JUDGEMENT)]
    for order, (confidence, basis) in enumerate(specs):
        heading = Heading(level=HeadingLevel.H3, text=f"T{order}", page_number=1, document_order=order)
        doc.headings.append(heading)
        doc.corrections.append(CorrectionRecord(
            object_type="heading", object_id=heading.id, field="level_mismatch", original_value="3",
            proposed_value="2", reason="t", reason_code="HEADING_LEVEL_MISMATCH",
            status=CorrectionStatus.PROPOSED, confidence=confidence, decision_basis=basis,
        ))
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = Job(
            job_id=job_id, filename="test.pdf", pdf_path=tmp_path / "test.pdf", status=JobStatus.COMPLETE,
            created_at=datetime.now(timezone.utc),
            result=PipelineResult(source_pdf_path="test.pdf", success=True, status=ProcessingStatus.VALIDATED,
                                  duration_seconds=0.1, document=doc),
        )
    yield job_id, doc
    with _lock:
        _jobs.pop(job_id, None)


def _patch(client, job_id, correction, action, **extra):
    return client.patch(
        f"/api/documents/{job_id}/corrections/{correction.correction_id}", json={"action": action, **extra}
    )


def _bulk(client, job_id, corrections, action):
    return client.post(
        f"/api/documents/{job_id}/corrections/bulk-action",
        json={"correction_ids": [c.correction_id for c in corrections], "action": action},
    )


def test_api_exposes_basis_and_confidence_separately(client, mixed_job):
    job_id, _ = mixed_job
    out = client.get(f"/api/documents/{job_id}/corrections").json()["corrections"]
    assert [(c["decision_basis"], c["confidence"]) for c in out] == [
        ("deterministic", 0.99), ("judgement", 0.99), ("judgement", 0.2),
    ]


def test_mixed_document_distinguishes_all_three(client, mixed_job):
    job_id, doc = mixed_job
    det, high_judgement, low_judgement = doc.corrections

    # Same cause, both 0.99 — still not one bulk decision.
    assert _bulk(client, job_id, [det, high_judgement], "accept").status_code == 422
    assert all(c.status is CorrectionStatus.PROPOSED for c in doc.corrections)
    # The deterministic correction alone may use the bulk path.
    assert _bulk(client, job_id, [det], "accept").status_code == 200
    # Judgement corrections, high or low confidence, are decided one at a time.
    assert _patch(client, job_id, high_judgement, "accept").status_code == 200
    assert _patch(client, job_id, low_judgement, "reject").status_code == 200
    assert [c.status for c in doc.corrections] == [
        CorrectionStatus.ACCEPTED, CorrectionStatus.ACCEPTED, CorrectionStatus.REJECTED,
    ]
    assert [h.level for h in doc.headings] == [2, 2, 3]


@pytest.mark.parametrize(
    "first, second",
    [
        ("accept", "accept"),   # would apply twice
        ("accept", "reject"),   # re-deciding a decided correction
        ("reject", "undo"),     # undoing something never applied
        ("ignore", "edit"),
    ],
)
def test_invalid_single_transitions_are_refused_and_change_nothing(client, mixed_job, first, second):
    job_id, doc = mixed_job
    target, heading = doc.corrections[1], doc.headings[1]
    assert _patch(client, job_id, target, first).status_code == 200
    before = (target.status, heading.level, len(target.telemetry_events), target.reviewed_at)

    resp = _patch(client, job_id, target, second, proposed_value="1")

    assert resp.status_code == 409
    assert (target.status, heading.level, len(target.telemetry_events), target.reviewed_at) == before


def test_undo_of_a_proposal_is_refused_and_the_lifecycle_still_works(client, mixed_job):
    job_id, doc = mixed_job
    target, heading = doc.corrections[1], doc.headings[1]
    assert _patch(client, job_id, target, "undo").status_code == 409
    assert heading.level == 3

    assert _patch(client, job_id, target, "accept").status_code == 200
    assert heading.level == 2
    assert _patch(client, job_id, target, "undo").status_code == 200
    assert (target.status, heading.level) == (CorrectionStatus.REVERTED, 3)
    # REVERTED is non-terminal: the question is open again.
    assert _patch(client, job_id, target, "accept").status_code == 200
    assert heading.level == 2


def test_bulk_undo_is_never_gated_by_basis(client, mixed_job):
    job_id, doc = mixed_job
    high_judgement = doc.corrections[1]
    assert _patch(client, job_id, high_judgement, "accept").status_code == 200
    # An applied judgement correction can still be reversed via the bulk path.
    assert _bulk(client, job_id, [high_judgement], "undo").status_code == 200
    assert doc.headings[1].level == 3
