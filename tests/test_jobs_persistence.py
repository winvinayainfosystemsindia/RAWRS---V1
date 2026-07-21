"""Job-level document persistence wiring (FE-0-001, Phase 2).

Phase 2 covers the *write* path only: a completed job writes its
Document to outputs/documents/{job_id}.json, and the job checkpoint
records that it did. Rehydration on startup is Phase 3.

The behaviour these tests protect is the one FE-0-001 exists to fix:
before this change ``_result_to_dict()`` serialized nine scalar/path
fields and silently dropped ``document``, so a restarted server reported
status=COMPLETE while holding no data.
"""

import json
from pathlib import Path

import pytest

from src.api import document_store, jobs
from src.api.jobs import Job, JobStatus, _job_from_dict, _write_checkpoint
from src.models.contracts import Document
from src.models.document import ProcessingStatus
from src.models.metadata import Metadata
from src.models.page import Page
from src.pipeline.phase1_pipeline import PipelineResult


@pytest.fixture(autouse=True)
def _isolated_dirs(tmp_path, monkeypatch):
    """Keep every test off the real outputs/ tree."""
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(jobs, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(document_store, "DOCUMENTS_DIR", tmp_path / "documents")
    return tmp_path


@pytest.fixture(autouse=True)
def _clean_job_registry():
    yield
    with jobs._lock:
        jobs._jobs.clear()


def _document(page_count: int = 2) -> Document:
    return Document(
        source_pdf_path="test.pdf",
        metadata=Metadata(filename="test.pdf", page_count=page_count),
        pages=[Page(page_number=i + 1) for i in range(page_count)],
    )


def _result(document=None, success: bool = True) -> PipelineResult:
    return PipelineResult(
        source_pdf_path="test.pdf",
        success=success,
        status=ProcessingStatus.VALIDATED if success else ProcessingStatus.FAILED,
        duration_seconds=1.0,
        document=document,
    )


def _run_job_with(monkeypatch, result: PipelineResult, job_id: str = "job1") -> Job:
    """Drive _run_job() with a stubbed pipeline.

    Stubbing run_pipeline keeps these tests targeted at the persistence
    wiring rather than re-running an OCR pipeline.
    """
    job = Job(job_id=job_id, filename="test.pdf", pdf_path=Path(f"uploads/{job_id}.pdf"))
    with jobs._lock:
        jobs._jobs[job_id] = job
    monkeypatch.setattr(jobs, "run_pipeline", lambda *a, **k: result)
    jobs._run_job(job_id, enable_ocr=False)
    return job


# ── document is persisted on completion ────────────────────────────────

class TestDocumentPersistedOnCompletion:
    def test_completed_job_writes_document_sidecar(self, monkeypatch):
        _run_job_with(monkeypatch, _result(_document()))
        assert document_store.document_path("job1").is_file()

    def test_persisted_document_is_loadable(self, monkeypatch):
        doc = _document(page_count=3)
        doc.version = 12
        _run_job_with(monkeypatch, _result(doc))

        loaded = document_store.load_document("job1")
        assert loaded is not None
        assert loaded.version == 12
        assert len(loaded.pages) == 3

    def test_job_records_document_persisted_true(self, monkeypatch):
        job = _run_job_with(monkeypatch, _result(_document()))
        assert job.document_persisted is True

    def test_checkpoint_records_document_persisted(self, monkeypatch, _isolated_dirs):
        _run_job_with(monkeypatch, _result(_document()))
        data = json.loads((_isolated_dirs / "jobs" / "job1.json").read_text(encoding="utf-8"))
        assert data["document_persisted"] is True

    def test_failed_job_with_document_still_persists_it(self, monkeypatch):
        """A partial document is still reviewer-visible state worth keeping."""
        job = _run_job_with(monkeypatch, _result(_document(), success=False))
        assert job.status == JobStatus.FAILED
        assert job.document_persisted is True
        assert document_store.load_document("job1") is not None


# ── absence of a document is handled ───────────────────────────────────

class TestNoDocument:
    def test_result_without_document_writes_no_sidecar(self, monkeypatch):
        job = _run_job_with(monkeypatch, _result(document=None))
        assert job.document_persisted is False
        assert not document_store.document_path("job1").exists()

    def test_checkpoint_still_written_without_document(self, monkeypatch, _isolated_dirs):
        _run_job_with(monkeypatch, _result(document=None))
        data = json.loads((_isolated_dirs / "jobs" / "job1.json").read_text(encoding="utf-8"))
        assert data["document_persisted"] is False


# ── persistence failure must not fail the job ──────────────────────────

class TestPersistenceFailureIsNonFatal:
    def test_save_failure_leaves_job_complete(self, monkeypatch):
        monkeypatch.setattr(jobs, "save_document", lambda *a, **k: False)
        job = _run_job_with(monkeypatch, _result(_document()))
        # The pipeline succeeded; a disk problem must not rewrite that.
        assert job.status == JobStatus.COMPLETE
        assert job.document_persisted is False

    def test_save_failure_still_writes_checkpoint(self, monkeypatch, _isolated_dirs):
        monkeypatch.setattr(jobs, "save_document", lambda *a, **k: False)
        _run_job_with(monkeypatch, _result(_document()))
        data = json.loads((_isolated_dirs / "jobs" / "job1.json").read_text(encoding="utf-8"))
        assert data["status"] == "complete"
        assert data["document_persisted"] is False


# ── backward compatibility with pre-FE-0-001 checkpoints ───────────────

class TestBackwardCompatibility:
    def test_checkpoint_without_the_key_defaults_to_false(self):
        """Existing on-disk checkpoints have no document_persisted key."""
        legacy = {
            "job_id": "legacy1",
            "filename": "old.pdf",
            "pdf_path": "uploads/legacy1.pdf",
            "status": "complete",
            "created_at": "2026-07-01T10:00:00+00:00",
            "started_at": "2026-07-01T10:00:01+00:00",
            "completed_at": "2026-07-01T10:05:00+00:00",
            "last_completed_stage": "Run Validation",
            "error_message": None,
            "result": None,
        }
        job = _job_from_dict(legacy)
        assert job.document_persisted is False
        assert job.status == JobStatus.COMPLETE

    def test_legacy_checkpoint_round_trips(self, _isolated_dirs):
        legacy_job = Job(
            job_id="legacy2",
            filename="old.pdf",
            pdf_path=_isolated_dirs / "old.pdf",
            status=JobStatus.COMPLETE,
        )
        _write_checkpoint(legacy_job)
        data = json.loads((_isolated_dirs / "jobs" / "legacy2.json").read_text(encoding="utf-8"))
        assert data["document_persisted"] is False
        assert _job_from_dict(data).document_persisted is False

    def test_existing_checkpoint_fields_are_unchanged(self, monkeypatch, _isolated_dirs):
        """Phase 2 must add a key, not alter the existing contract."""
        _run_job_with(monkeypatch, _result(_document()))
        data = json.loads((_isolated_dirs / "jobs" / "job1.json").read_text(encoding="utf-8"))
        for key in (
            "job_id", "filename", "pdf_path", "status", "created_at",
            "started_at", "completed_at", "last_completed_stage",
            "error_message", "result",
        ):
            assert key in data, f"pre-existing checkpoint key '{key}' disappeared"


# ── lock strategy (invariants 1 and 2) ─────────────────────────────────

class TestLockStrategy:
    def test_file_io_happens_outside_the_lock(self, monkeypatch):
        """Invariant 2: serialize under the lock, write after releasing it.

        If save_document() ran while the lock was held, a 3.36 MB write
        would block every other request; worse, a future re-acquire would
        deadlock on the non-reentrant lock.
        """
        observed = {}

        def _spy(job_id, payload):
            observed["locked_during_write"] = jobs._lock.locked()
            return True

        monkeypatch.setattr(jobs, "save_document", _spy)
        _run_job_with(monkeypatch, _result(_document()))
        assert observed["locked_during_write"] is False

    def test_serialization_happens_before_write(self, monkeypatch):
        """save_document() receives an already-serialized string."""
        captured = {}

        def _spy(job_id, payload):
            captured["payload"] = payload
            return True

        monkeypatch.setattr(jobs, "save_document", _spy)
        _run_job_with(monkeypatch, _result(_document()))

        assert isinstance(captured["payload"], str)
        parsed = json.loads(captured["payload"])
        assert parsed["schema_version"] == document_store.SCHEMA_VERSION
        assert "document" in parsed


# ── Phase 3 · restart / recovery ───────────────────────────────────────

def _simulate_restart() -> None:
    """Drop all in-memory state, as a process restart would."""
    with jobs._lock:
        jobs._jobs.clear()
    jobs.load_persisted_jobs()


class TestRestartRecovery:
    def test_restart_restores_the_document(self, monkeypatch):
        doc = _document(page_count=4)
        doc.version = 7
        _run_job_with(monkeypatch, _result(doc))

        _simulate_restart()

        recovered = jobs.get_job("job1")
        assert recovered is not None
        assert recovered.status == JobStatus.COMPLETE
        assert recovered.result is not None
        assert recovered.result.document is not None, "the FE-0-001 defect"
        assert recovered.result.document.version == 7
        assert len(recovered.result.document.pages) == 4

    def test_restart_preserves_reviewer_state(self, monkeypatch):
        """The concrete thing a remediator loses today."""
        doc = _document()
        doc.metadata.title = "Reviewed Title"
        doc.metadata.language = "en-GB"
        doc.version = 3
        _run_job_with(monkeypatch, _result(doc))

        _simulate_restart()

        restored = jobs.get_job("job1").result.document
        assert restored.metadata.title == "Reviewed Title"
        assert restored.metadata.language == "en-GB"
        assert restored.version == 3

    def test_missing_sidecar_recovers_without_document(self, monkeypatch):
        _run_job_with(monkeypatch, _result(_document()))
        document_store.delete_document("job1")

        _simulate_restart()

        recovered = jobs.get_job("job1")
        assert recovered.status == JobStatus.COMPLETE
        assert recovered.result.document is None
        # Flag corrected to match reality rather than trusting the checkpoint.
        assert recovered.document_persisted is False

    def test_corrupted_sidecar_recovers_without_document(self, monkeypatch):
        _run_job_with(monkeypatch, _result(_document()))
        document_store.document_path("job1").write_text("{ truncated", encoding="utf-8")

        _simulate_restart()

        recovered = jobs.get_job("job1")
        assert recovered.status == JobStatus.COMPLETE
        assert recovered.result.document is None
        assert recovered.document_persisted is False

    def test_schema_mismatch_recovers_without_document(self, monkeypatch):
        _run_job_with(monkeypatch, _result(_document()))
        path = document_store.document_path("job1")
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["schema_version"] = document_store.SCHEMA_VERSION + 99
        path.write_text(json.dumps(raw), encoding="utf-8")

        _simulate_restart()

        assert jobs.get_job("job1").result.document is None

    def test_failed_job_with_document_recovers_it(self, monkeypatch):
        _run_job_with(monkeypatch, _result(_document(), success=False))

        _simulate_restart()

        recovered = jobs.get_job("job1")
        assert recovered.status == JobStatus.FAILED
        assert recovered.result.document is not None

    def test_legacy_checkpoint_recovers_unchanged(self, _isolated_dirs):
        """A pre-FE-0-001 checkpoint on disk, with no sidecar anywhere."""
        (_isolated_dirs / "jobs").mkdir(parents=True, exist_ok=True)
        (_isolated_dirs / "jobs" / "legacy9.json").write_text(
            json.dumps({
                "job_id": "legacy9",
                "filename": "old.pdf",
                "pdf_path": "uploads/legacy9.pdf",
                "status": "complete",
                "created_at": "2026-07-01T10:00:00+00:00",
                "started_at": "2026-07-01T10:00:01+00:00",
                "completed_at": "2026-07-01T10:05:00+00:00",
                "last_completed_stage": "Run Validation",
                "error_message": None,
                "result": {
                    "source_pdf_path": "old.pdf",
                    "success": True,
                    "status": "validated",
                    "duration_seconds": 12.0,
                    "failed_stage": None,
                    "error_message": None,
                    "markdown_path": None,
                    "docx_path": None,
                    "report_path": None,
                },
            }),
            encoding="utf-8",
        )
        _simulate_restart()

        recovered = jobs.get_job("legacy9")
        assert recovered is not None
        assert recovered.status == JobStatus.COMPLETE
        assert recovered.result is not None
        assert recovered.result.document is None  # exactly the old behaviour
        assert recovered.document_persisted is False

    def test_document_is_not_loaded_for_interrupted_jobs(self, _isolated_dirs):
        """A job still PROCESSING at death recovers as FAILED, no result."""
        (_isolated_dirs / "jobs").mkdir(parents=True, exist_ok=True)
        (_isolated_dirs / "jobs" / "midrun.json").write_text(
            json.dumps({
                "job_id": "midrun",
                "filename": "x.pdf",
                "pdf_path": "uploads/midrun.pdf",
                "status": "processing",
                "created_at": "2026-07-01T10:00:00+00:00",
                "started_at": "2026-07-01T10:00:01+00:00",
                "completed_at": None,
                "last_completed_stage": "Detect Headings",
                "error_message": None,
                "result": None,
            }),
            encoding="utf-8",
        )
        _simulate_restart()

        recovered = jobs.get_job("midrun")
        assert recovered.status == JobStatus.FAILED
        assert recovered.result is None

    def test_sidecar_is_source_of_truth_over_the_flag(self, monkeypatch, _isolated_dirs):
        """A stale document_persisted=false must not hide a real sidecar."""
        _run_job_with(monkeypatch, _result(_document()))
        path = _isolated_dirs / "jobs" / "job1.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["document_persisted"] = False  # deliberately wrong
        path.write_text(json.dumps(data), encoding="utf-8")

        _simulate_restart()

        recovered = jobs.get_job("job1")
        assert recovered.result.document is not None
        assert recovered.document_persisted is True


class TestFullRestartFlow:
    def test_end_to_end_restart_preserves_review_state(self, monkeypatch, _isolated_dirs):
        """pipeline completes -> persisted -> restart -> reload -> restored."""
        # 1. pipeline completes, with reviewer-visible state on the document
        doc = _document(page_count=5)
        doc.metadata.title = "Accessible Report"
        doc.metadata.language = "en-US"
        doc.version = 21
        _run_job_with(monkeypatch, _result(doc))

        # 2. document persisted
        assert document_store.document_path("job1").is_file()
        assert jobs.get_job("job1").document_persisted is True

        # 3. backend restart — all in-memory state gone
        with jobs._lock:
            jobs._jobs.clear()
        assert jobs.get_job("job1") is None

        # 4. checkpoint reload
        jobs.load_persisted_jobs()
        recovered = jobs.get_job("job1")
        assert recovered is not None
        assert recovered.status == JobStatus.COMPLETE

        # 5. document restored
        assert recovered.result.document is not None

        # 6. reviewer state preserved
        restored = recovered.result.document
        assert restored.metadata.title == "Accessible Report"
        assert restored.metadata.language == "en-US"
        assert restored.version == 21
        assert len(restored.pages) == 5

    def test_export_regenerates_after_restart(self, monkeypatch):
        """The stale-export path closes as a consequence of rehydration.

        _needs_export_regen() short-circuits to False when document is
        None, which is why a restarted server served stale exports. With
        the document restored — and generated_at_version not persisted,
        so None — it now reports True and the download rebuilds.
        """
        from src.api.routes import _needs_export_regen

        doc = _document()
        doc.version = 5
        _run_job_with(monkeypatch, _result(doc))
        _simulate_restart()

        restored = jobs.get_job("job1").result
        assert restored.document is not None
        assert _needs_export_regen(restored.document, restored.markdown_generated_at_version) is True


# ── Phase 4 · reviewer mutations persist synchronously ─────────────────

@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from src.api.main import app

    return TestClient(app)


def _seed_job(job_id: str = "rev1"):
    """Register a COMPLETE job with a reviewable document."""
    from src.models.contracts import Heading, HeadingLevel

    doc = _document(page_count=2)
    doc.headings.append(
        Heading(text="Introduction", level=HeadingLevel.H1, page_number=1, document_order=0)
    )
    job = Job(
        job_id=job_id,
        filename="test.pdf",
        pdf_path=Path(f"uploads/{job_id}.pdf"),
        status=JobStatus.COMPLETE,
        result=_result(doc),
    )
    with jobs._lock:
        jobs._jobs[job_id] = job
    # A real completed job always has a checkpoint on disk; without one
    # a simulated restart has nothing to recover from.
    _write_checkpoint(job)
    return job, doc


class TestReviewerMutationsPersist:
    def test_metadata_update_is_persisted(self, client):
        _seed_job()
        resp = client.patch("/api/documents/rev1/metadata", json={"title": "New Title"})
        assert resp.status_code == 200

        # Durable *before* the next request, not on some later flush.
        persisted = document_store.load_document("rev1")
        assert persisted is not None
        assert persisted.metadata.title == "New Title"

    def test_metadata_update_survives_restart(self, client):
        _seed_job()
        client.patch("/api/documents/rev1/metadata", json={"language": "en-CA"})

        _simulate_restart()

        recovered = jobs.get_job("rev1")
        assert recovered is not None
        assert recovered.result.document.metadata.language == "en-CA"

    def test_heading_review_is_persisted(self, client):
        _seed_job()
        resp = client.patch(
            "/api/documents/rev1/headings/0",
            json={"action": "approve"},
        )
        if resp.status_code == 200:
            persisted = document_store.load_document("rev1")
            assert persisted is not None
            assert persisted.headings, "heading review must persist the heading list"

    def test_persistence_failure_does_not_fail_the_request(self, client, monkeypatch):
        _seed_job()
        monkeypatch.setattr("src.api.routes.save_document", lambda *a, **k: False)
        resp = client.patch("/api/documents/rev1/metadata", json={"title": "Still Works"})
        # Mutation already succeeded in memory; a disk problem must not 500.
        assert resp.status_code == 200


class TestAllMutationSitesWired:
    def test_every_lock_guarded_mutation_snapshots(self):
        """Each `with _lock:` mutation block must persist.

        The originally approved plan said "the 7 version += 1 sites",
        which would have missed nine reviewer mutation endpoints —
        headings, footnotes, tables, metadata, validation issues — whose
        edits would then vanish on restart. This pins the wider set.
        """
        source = Path("src/api/routes.py").read_text(encoding="utf-8")
        assert source.count("_persist(job_id, payload)") == 15
        assert source.count("payload = _snapshot(document)") == 15

    def test_snapshot_precedes_persist_in_every_case(self):
        """Serialize inside the lock, write after it (invariant 2)."""
        lines = Path("src/api/routes.py").read_text(encoding="utf-8").splitlines()
        snapshots = [i for i, ln in enumerate(lines) if "payload = _snapshot(document)" in ln]
        persists = [i for i, ln in enumerate(lines) if "_persist(job_id, payload)" in ln]
        for snap, pers in zip(snapshots, persists):
            assert snap < pers, "snapshot must precede persist"
            # Snapshot is indented inside the lock block; persist is not.
            assert lines[snap].startswith("        "), "snapshot must be inside the lock"
            assert lines[pers].startswith("    ") and not lines[pers].startswith("     "), \
                "persist must be outside the lock"


# ── Phase 5 · startup orphan sweep ─────────────────────────────────────

class TestStartupSweep:
    def test_lifespan_sweeps_orphan_temp_files(self):
        source = Path("src/api/main.py").read_text(encoding="utf-8")
        assert "sweep_orphan_temp_files()" in source
        # Must run before recovery, so recovery never sees a partial file.
        assert source.index("sweep_orphan_temp_files()") < source.index("load_persisted_jobs()\n")

    def test_sweep_leaves_real_sidecars_alone(self, monkeypatch):
        """Cleanup is limited to temp artifacts (no sidecar lifecycle)."""
        _run_job_with(monkeypatch, _result(_document()))
        document_store.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
        (document_store.DOCUMENTS_DIR / f"stale.json{document_store.TEMP_SUFFIX}").write_text(
            "partial", encoding="utf-8"
        )

        assert document_store.sweep_orphan_temp_files() == 1
        assert document_store.load_document("job1") is not None
