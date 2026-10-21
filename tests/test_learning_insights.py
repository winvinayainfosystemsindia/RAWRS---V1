"""src/learning/store.py and src/learning/insights.py."""

import io
import os
import zipfile

import pytest

from src.api.document_store import serialize_document
from src.learning import store
from src.learning.insights import build_insights, iter_dataset
from src.models.contracts import Document, Metadata
from src.models.correction import CorrectionRecord, CorrectionStatus


def _sidecar(directory, job_id, records, filename="book.pdf"):
    directory.mkdir(parents=True, exist_ok=True)
    document = Document(source_pdf_path=filename, metadata=Metadata(filename=filename), corrections=records)
    path = directory / f"{job_id}.json"
    path.write_text(serialize_document(document), encoding="utf-8")
    return path


def _correction(status, provider="mathpix", reason_code="HEADING_LEVEL_MISMATCH", original="3", proposed="1"):
    return CorrectionRecord(object_type="heading", field="level_mismatch", original_value=original,
                            proposed_value=proposed, reason_code=reason_code, provider=provider, status=status)


def _review(edits, fixed=()):
    return {
        "job_id": "x", "filename": "book.pdf", "reviewed_at": "2026-10-21T00:00:00+00:00",
        "diff": {"summary": {"kept_share": 0.9, "edits": len(edits)}, "edits": edits},
        "checklist": {"fixed_by_remediator": [{"item_id": i, "requirement": "Headings are styled"} for i in fixed]},
    }


def _docx_bytes(names=("[Content_Types].xml", "word/document.xml"), payload=b"<x/>"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, payload)
    return buffer.getvalue()


# --- store ---------------------------------------------------------------------


def test_job_ids_cannot_escape_the_store(tmp_path):
    for bad in ("../etc", "a/b", "..", ""):
        with pytest.raises(ValueError):
            store.job_dir(tmp_path, bad)


def test_validate_docx_refuses_non_word_files():
    with pytest.raises(store.InvalidDocx):
        store.validate_docx(b"")
    with pytest.raises(store.InvalidDocx):
        store.validate_docx(b"%PDF-1.4 not a zip")
    with pytest.raises(store.InvalidDocx):
        store.validate_docx(_docx_bytes(names=("something.txt",)))
    store.validate_docx(_docx_bytes())


def test_validate_docx_refuses_a_zip_bomb(monkeypatch):
    monkeypatch.setattr(store, "MAX_UNCOMPRESSED_BYTES", 100)
    with pytest.raises(store.InvalidDocx, match="unreasonable"):
        store.validate_docx(_docx_bytes(payload=b"0" * 1000))


def test_review_round_trip_and_delete(tmp_path):
    store.save_review(tmp_path, "job1", _review([]))
    assert store.load_review(tmp_path, "job1")["schema_version"] == store.SCHEMA_VERSION
    assert [job for job, _ in store.iter_reviews(tmp_path)] == ["job1"]
    assert store.delete_review(tmp_path, "job1")
    assert store.load_review(tmp_path, "job1") is None


def test_snapshot_export_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("RAWRS_LEARNING_SNAPSHOT", "on")
    assert store.snapshot_export(tmp_path, "job1", tmp_path / "missing.docx") is False
    source = tmp_path / "out.docx"
    source.write_bytes(_docx_bytes())
    assert store.snapshot_export(tmp_path, "job1", source) is True
    assert store.exported_snapshot(tmp_path, "job1").read_bytes() == source.read_bytes()


# --- insights ------------------------------------------------------------------


def test_insights_combine_decisions_and_post_export_edits(tmp_path):
    documents = tmp_path / "documents"
    _sidecar(documents, "job1", [_correction(CorrectionStatus.ACCEPTED), _correction(CorrectionStatus.REJECTED),
                                 _correction(CorrectionStatus.EDITED, provider="manual_reviewer",
                                             reason_code="HEADING_LEVEL_MANUAL_EDIT", original="2", proposed="3")])
    edits = [
        {"category": "HEADING_LEVEL_CHANGED", "object_type": "heading", "before": "H2", "after": "H3"},
        {"category": "HEADING_LEVEL_CHANGED", "object_type": "heading", "before": "H2", "after": "H3"},
        {"category": "TEXT_EDITED", "object_type": "paragraph", "before": "teh cat", "after": "the cat",
         "word_changes": [{"op": "replace", "from": "teh", "to": "the"}]},
    ]
    store.save_review(tmp_path, "job1", _review(edits, fixed=("DR-H1",)))

    insights = build_insights(documents, tmp_path)

    rule = insights["decisions"]["rules"][0]
    assert (rule["reason_code"], rule["decided"]) == ("HEADING_LEVEL_MISMATCH", 2)
    assert insights["decisions"]["human_edits"][0]["count"] == 1
    after = insights["after_export"]
    assert after["categories"][0] == {"category": "HEADING_LEVEL_CHANGED", "object_type": "heading", "count": 2,
                                      "documents": 1, "phrase": "changed a heading's level"}
    assert after["word_substitutions"] == [{"from": "teh", "to": "the", "count": 1, "documents": 1}]
    assert after["checklist_fixed_by_remediators"][0]["item_id"] == "DR-H1"
    assert after["mean_kept_share"] == 0.9
    messages = [p["message"] for p in insights["priorities"]]
    assert messages[0].startswith("After export, remediators changed a heading's level 2 times")
    assert any("HEADING_LEVEL_MANUAL_EDIT" in m and "2 → 3" in m for m in messages)
    assert insights["reviewed_documents"][0]["job_id"] == "job1"


def test_index_notices_changed_and_deleted_sidecars(tmp_path):
    documents = tmp_path / "documents"
    path = _sidecar(documents, "job1", [_correction(CorrectionStatus.ACCEPTED)])
    assert build_insights(documents, tmp_path)["decisions"]["totals"]["proposals"] == 1

    _sidecar(documents, "job1", [_correction(CorrectionStatus.ACCEPTED)] * 3)
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1_000_000))
    assert build_insights(documents, tmp_path)["decisions"]["totals"]["proposals"] == 3

    path.unlink()
    assert build_insights(documents, tmp_path)["decisions"]["totals"]["proposals"] == 0


def test_unreadable_sidecar_is_skipped(tmp_path):
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "broken.json").write_text("{not json", encoding="utf-8")
    _sidecar(documents, "job1", [_correction(CorrectionStatus.ACCEPTED)])
    assert build_insights(documents, tmp_path)["decisions"]["totals"]["proposals"] == 1


def test_dataset_holds_labelled_examples_only(tmp_path):
    documents = tmp_path / "documents"
    _sidecar(documents, "job1", [_correction(CorrectionStatus.ACCEPTED), _correction(CorrectionStatus.PROPOSED),
                                 _correction(CorrectionStatus.EDITED, provider="manual_reviewer")])
    store.save_review(tmp_path, "job1", _review([{"category": "ALT_TEXT_WRITTEN", "object_type": "figure",
                                                  "before": "", "after": "A chart."}]))
    rows = list(iter_dataset(documents, tmp_path))
    assert [row["kind"] for row in rows] == ["proposal_decision", "reviewer_edit", "post_export_edit"]
    assert rows[0]["outcome"] == "accepted" and rows[1]["outcome"] is None
    assert rows[2]["after"] == "A chart."
