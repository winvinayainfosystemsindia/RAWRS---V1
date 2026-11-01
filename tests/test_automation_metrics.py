"""Automation-rate metrics (src/metrics/automation.py)."""

import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest

from src.metrics import automation as m
from src.models.correction import CorrectionRecord, CorrectionStatus
from src.models.equation import EquationStatus
from src.models.figure import AltTextStatus
from src.models.footnote import FootnoteReviewStatus
from src.models.heading import HeadingReviewStatus
from src.models.page import ReadingOrderStatus
from src.models.table import TableStatus
from src.models.validation_issue import ValidationIssueStatus


def _doc(**parts):
    base = dict(headings=[], images=[], tables=[], pages=[], footnotes=[], equations=[],
                corrections=[], validation_issues=[])
    return NS(**{**base, **parts})


def _human(object_type, object_id, code, original="", status=CorrectionStatus.EDITED):
    return CorrectionRecord(object_type=object_type, object_id=object_id, field="f", original_value=original,
                            proposed_value="", reason_code=code, provider="manual_reviewer", status=status)


def _heading(i, status=HeadingReviewStatus.DETECTED, marker=False):
    return NS(id=f"h{i}", review_status=status, is_page_marker=marker)


def _image(i, status, alt=""):
    return NS(image_id=f"i{i}", figure=NS(alt_text_status=status, alt_text=alt))


def _only(counts, category):
    return {b: n for b, n in counts[category].items() if n}


# --------------------------------------------------------------------------- buckets

def test_every_status_of_every_category_lands_in_exactly_one_bucket():
    doc = _doc(
        headings=[_heading(i, s) for i, s in enumerate(HeadingReviewStatus)],
        images=[_image(i, s) for i, s in enumerate(AltTextStatus)],
        tables=[NS(table_id=f"t{i}", status=s) for i, s in enumerate(TableStatus)],
        pages=[NS(page_number=i + 1, reading_order_status=s) for i, s in enumerate(ReadingOrderStatus)],
        footnotes=[NS(footnote_id=f"f{i}", review_status=s) for i, s in enumerate(FootnoteReviewStatus)],
        equations=[NS(id=f"e{i}", status=s) for i, s in enumerate(EquationStatus)],
        corrections=[CorrectionRecord(object_type="heading", field="f", original_value="", proposed_value="",
                                      status=s, provider="mathpix") for s in CorrectionStatus],
    )
    counts = m.item_buckets(doc)
    sizes = {"headings": len(HeadingReviewStatus), "images": len(AltTextStatus), "tables": len(TableStatus),
             "reading_order": len(ReadingOrderStatus), "footnotes": len(FootnoteReviewStatus),
             "equations": len(EquationStatus), "corrections": len(CorrectionStatus)}
    for category, size in sizes.items():
        assert sum(counts[category].values()) == size, category


def test_headings_page_markers_skipped_and_reviewer_actions_classified():
    doc = _doc(
        headings=[_heading(0), _heading(1, HeadingReviewStatus.APPROVED), _heading(2, HeadingReviewStatus.LEVEL_CHANGED),
                  _heading(3, HeadingReviewStatus.APPROVED), _heading(9, marker=True)],
        corrections=[_human("heading", "h3", "HEADING_TEXT_MANUAL_EDIT"),
                     _human("heading", "gone", "HEADING_REJECTED_BY_REVIEWER")],
    )
    assert _only(m.item_buckets(doc), "headings") == {
        "auto_decided": 1, "accepted_unchanged": 1, "edited": 2, "rejected": 1}


def test_reviewer_records_are_never_counted_as_corrections_and_undone_ones_are_ignored():
    doc = _doc(
        headings=[_heading(0)],
        corrections=[_human("heading", "h0", "HEADING_TEXT_MANUAL_EDIT", status=CorrectionStatus.REVERTED),
                     _human("heading", "h0", "HEADING_LEVEL_MANUAL_EDIT"),
                     CorrectionRecord(object_type="heading", field="f", original_value="", proposed_value="",
                                      status=CorrectionStatus.AUTO_APPLIED),
                     CorrectionRecord(object_type="heading", field="f", original_value="", proposed_value="")],
    )
    counts = m.item_buckets(doc)
    assert _only(counts, "headings") == {"edited": 1}
    assert _only(counts, "corrections") == {"auto_decided": 1, "pending_human": 1}


def test_image_alt_text_kept_vs_rewritten():
    original = json.dumps({"alt_text": "A map", "alt_text_status": "ai_generated"})
    doc = _doc(
        images=[_image(0, AltTextStatus.AI_GENERATED, "A map"), _image(1, AltTextStatus.PENDING_REVIEW),
                _image(2, AltTextStatus.APPROVED, "A map"), _image(3, AltTextStatus.APPROVED, "A city map"),
                _image(4, AltTextStatus.REJECTED, "A map")],
        corrections=[_human("figure", f"i{i}", "FIGURE_ALT_TEXT_REVIEWED", original) for i in (2, 3, 4)],
    )
    assert _only(m.item_buckets(doc), "images") == {
        "auto_decided": 1, "pending_human": 1, "accepted_unchanged": 1, "edited": 1, "rejected": 1}


def test_flagged_reading_order_counts_as_asking_a_human_and_deleted_tables_as_rejected():
    issue = NS(rule_id="PAGE_003", page_number=2, status=ValidationIssueStatus.OPEN)
    doc = _doc(
        pages=[NS(page_number=1, reading_order_status=ReadingOrderStatus.UNREVIEWED),
               NS(page_number=2, reading_order_status=ReadingOrderStatus.UNREVIEWED)],
        validation_issues=[issue],
        tables=[NS(table_id="t1", status=TableStatus.MANUALLY_CREATED)],
        corrections=[_human("table", "t9", "TABLE_DELETED_BY_REVIEWER"),
                     _human("table", "t1", "TABLE_CREATED_BY_REVIEWER")],
    )
    counts = m.item_buckets(doc)
    assert _only(counts, "reading_order") == {"auto_decided": 1, "pending_human": 1}
    assert _only(counts, "tables") == {"edited": 1, "rejected": 1}


# --------------------------------------------------------------------------- rounding and rates

def test_rounding_never_flatters_rawrs():
    assert m.floor_pct(0.99999) == 99.9
    assert m.floor_pct(0.5) == 50.0
    assert m.floor_pct(2 / 3) == 66.6
    assert m.ceil_seconds(1.01) == 1.1
    assert m.ceil_seconds(2.0) == 2.0


def test_rate_reports_median_pooled_and_labelled_wilson_bound():
    rate = m._rate([9, 1], [10, 10])
    assert rate["documents"] == 2 and rate["items"] == 20
    assert rate["pooled_pct"] == 50.0 and rate["median_document_pct"] == 50.0
    assert rate["wilson_low_pct"] < 50.0 and rate["wilson_note"] == m.WILSON_NOTE
    assert m._rate([0], [0])["status"] == m.NOT_MEASURED


# --------------------------------------------------------------------------- sidecar and aggregate

def _snapshot(**buckets):
    counts = {c: {b: 0 for b in m.BUCKETS} for c in m.CATEGORIES}
    counts["headings"].update(buckets)
    return counts


def _sidecar(root, stem, snapshot, **extra):
    path = m.sidecar_path(root, stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"schema": m.SCHEMA, "total_seconds": 10.0, "stage_seconds": {"parse_pdf": 1.0},
            "checks": {"pass": 3, "fail": 1, "warn": 1, "manual": 1, "not_applicable": 2},
            "snapshot": snapshot, "review_seconds_strict": 0, "review_seconds_loose": 0, **extra}
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("reviewed, expected", [(4, m.NOT_MEASURED), (5, "measured")])
def test_reviewer_metric_needs_min_reviewed_documents(tmp_path, reviewed, expected):
    assert m.MIN_REVIEWED_DOCS == 5
    for i in range(reviewed):
        _sidecar(tmp_path, f"r{i}", _snapshot(accepted_unchanged=3, edited=1))
    _sidecar(tmp_path, "unreviewed", _snapshot(auto_decided=4))
    report = m.aggregate(tmp_path)
    kept = report["measured"]["reviewer_kept_unchanged"]
    assert kept["status"] == expected
    assert kept["human_reviewed_documents"] == reviewed
    if expected == "measured":
        assert kept["pooled_pct"] == 75.0


def test_aggregate_keeps_estimate_apart_and_counts_checks_conservatively(tmp_path):
    _sidecar(tmp_path, "a", _snapshot(auto_decided=3, pending_human=1),
             estimate={"label": m.ESTIMATE_LABEL, "heading_f1": 0.8})
    (tmp_path / "reports" / f"broken{m.SIDECAR_SUFFIX}").write_text("{", encoding="utf-8")
    report = m.aggregate(tmp_path)
    assert report["documents"] == 1 and report["unreadable_sidecars"] == 1
    assert report["measured"]["decided_without_human"]["pooled_pct"] == 75.0
    checks = report["measured"]["checks"]
    assert checks["needs_human"] == 2 and checks["pass_rate"]["pooled_pct"] == 50.0
    assert "estimate" not in report["measured"]
    assert report["estimate"]["mean"] == {"heading_f1": 0.8}


def test_pipeline_metrics_write_is_atomic_keeps_review_time_and_never_raises(tmp_path):
    path = _sidecar(tmp_path, "job", _snapshot(), review_seconds_strict=40, review_seconds_loose=90)
    doc = _doc(pages=[NS(page_number=1, reading_order_status=ReadingOrderStatus.UNREVIEWED, page_type=None)],
               headings=[_heading(0)])
    assert m.write_pipeline_metrics(doc, path, {"parse_pdf": 0.5}, 1.5, {"pass": 1})
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["review_seconds_loose"] == 90 and data["snapshot"]["headings"]["auto_decided"] == 1
    assert not list(path.parent.glob("*.tmp"))
    assert m.write_pipeline_metrics(object(), path, {}, 0.0, None) is False


def test_review_time_is_capped_per_call_and_accumulates(tmp_path):
    path = _sidecar(tmp_path, "job", _snapshot())
    m.add_review_time(path, 30, 999)
    totals = m.add_review_time(path, -5, 10)
    assert totals == {"review_seconds_strict": 30, "review_seconds_loose": 310}
    assert m.add_review_time(tmp_path / "reports" / "none.metrics.json", 1, 1) is None


# --------------------------------------------------------------------------- API

@pytest.fixture
def api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from src.api.jobs import Job, JobStatus, _jobs, _lock
    from src.api.main import app

    monkeypatch.setattr("src.api.learning_routes.DEFAULT_OUTPUT_ROOT", tmp_path)
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = Job(job_id=job_id, filename="b.pdf", pdf_path=tmp_path / "b.pdf",
                            status=JobStatus.COMPLETE, created_at=datetime.now(timezone.utc))
    yield TestClient(app), job_id, tmp_path
    with _lock:
        _jobs.pop(job_id, None)


def test_review_time_endpoint(api):
    client, job_id, root = api
    assert client.post(f"/api/documents/{job_id}/review-time", json={"strict_seconds": 1, "loose_seconds": 1}).status_code == 404
    _sidecar(root, job_id, _snapshot(auto_decided=2))
    body = {"strict_seconds": 20, "loose_seconds": 400}
    assert client.post(f"/api/documents/{job_id}/review-time", json=body).json() == {
        "review_seconds_strict": 20, "review_seconds_loose": 300}
    assert client.post(f"/api/documents/{job_id}/review-time", json={"strict_seconds": -1, "loose_seconds": 0}).status_code == 422
    assert client.post("/api/documents/nope/review-time", json=body).status_code == 404
    metrics = client.get(f"/api/documents/{job_id}/metrics").json()
    assert metrics["review_seconds_loose"] == 300
    assert metrics["rates"]["decided_without_human"]["pooled_pct"] == 100.0
    assert metrics["rates"]["reviewer_kept_unchanged"]["status"] == m.NOT_MEASURED


# --------------------------------------------------------------------------- pipeline

def test_pipeline_records_every_stage_and_writes_the_sidecar(tmp_path):
    import fitz

    from src.pipeline.phase1_pipeline import run_pipeline

    pdf = tmp_path / "tiny.pdf"
    with fitz.open() as out:
        page = out.new_page()
        page.insert_text((72, 72), "Introduction", fontsize=18)
        page.insert_text((72, 110), "Body text for the automation metrics test.", fontsize=11)
        out.save(pdf)
    result = run_pipeline(pdf, output_root=tmp_path / "out", enable_ocr=False)
    assert result.success
    assert list(result.stage_seconds) == ["parse_pdf", "extract_text", "detect_structure", "extract_images",
                                          "detect_headings", "generate_markdown", "generate_docx", "run_validation"]
    data = json.loads(m.sidecar_path(tmp_path / "out", "tiny").read_text(encoding="utf-8"))
    assert data["total_seconds"] >= sum(result.stage_seconds.values()) * 0.99
    assert data["checks"] and set(data["snapshot"]) == set(m.CATEGORIES)
