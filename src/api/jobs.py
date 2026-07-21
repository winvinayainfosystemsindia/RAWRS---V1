"""Job tracking for the RAWRS API — in-memory store with disk persistence.

run_pipeline() (src/pipeline/phase1_pipeline.py) is a long-running,
blocking call - real OCR pages have taken anywhere from ~1-3 minutes
(Docling) to several minutes (Surya fallback) per page in this
project's own benchmark runs. An HTTP request can't block for that
long, so every upload is handed to a background thread immediately and
tracked here by job id; the frontend polls GET /api/documents/{id} for
status instead of waiting on the upload request itself.

Persistence model
-----------------
Terminal jobs (complete or failed) are written to
  outputs/jobs/{job_id}.json
as soon as they reach that state, so they survive a process restart.
In-progress jobs also write a lightweight checkpoint after each pipeline
stage so that, if the server dies mid-run, recovery can report the last
stage that *completed* rather than just "unknown".

On startup, call load_persisted_jobs() to reload these records into the
in-memory store. Jobs that were still PROCESSING when the server died
are recovered as FAILED with an explanatory error_message.

The canonical Document is persisted alongside the job record, as its own
sidecar under outputs/documents/{job_id}.json (see
src/api/document_store.py). Before FE-0-001 it was not: a recovered job
came back as status=COMPLETE with document=None, so the UI reported a
finished, clean document while holding no data at all.

``document_persisted`` records whether that sidecar was written, so a
recovered job can tell "no document was ever saved" apart from "a
document exists and should be loaded". Checkpoints written before
FE-0-001 have no such key and default to False, which reproduces the old
behaviour exactly: sub-resource endpoints return empty collections, while
the job summary, markdown, DOCX and validation report downloads keep
working because those are on-disk artifacts.
"""

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger

from src.api.document_store import load_document, save_document, serialize_document
from src.pipeline.phase1_pipeline import DEFAULT_OUTPUT_ROOT, PipelineResult, run_pipeline

UPLOAD_DIR = DEFAULT_OUTPUT_ROOT / "uploads"
JOBS_DIR = DEFAULT_OUTPUT_ROOT / "jobs"


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class Job:
    """One uploaded-document's processing lifecycle.

    ``result`` is only populated once status is COMPLETE or FAILED -
    it is exactly the PipelineResult run_pipeline() itself returned, so
    every field the API exposes (markdown_path, validation_issues,
    etc.) is real pipeline output, never re-derived or guessed at here.

    After a server restart, result may be a stub PipelineResult with
    document=None (path fields only). result.document being None is a
    valid state for recovered jobs.

    mmd_path is set when the upload included a Mathpix MMD file.  When
    present it is passed directly to run_pipeline() so the Mathpix
    import path is taken and the MMD drives document construction.

    image_dir is set when the upload included one or more Mathpix package
    image files, saved unmodified under this directory (original filenames
    preserved — figure matching depends on them). Not persisted in the
    checkpoint JSON, consistent with mmd_path already not being persisted:
    recovered jobs don't re-run the pipeline.
    """

    job_id: str
    filename: str
    pdf_path: Path
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[PipelineResult] = None
    error_message: Optional[str] = None
    last_completed_stage: Optional[str] = None
    mmd_path: Optional[Path] = None
    image_dir: Optional[Path] = None
    # FE-0-001 — True once this job's Document has been written to
    # outputs/documents/{job_id}.json. Distinguishes "no document was
    # ever saved" (pre-FE-0-001 checkpoint, or a job that failed before
    # producing one) from "a document exists and should be loaded".
    document_persisted: bool = False


_jobs: Dict[str, Job] = {}
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_job(
    filename: str,
    pdf_bytes: bytes,
    mmd_bytes: Optional[bytes] = None,
    image_files: Optional[List[Tuple[str, bytes]]] = None,
) -> Job:
    """Save the uploaded PDF (and optional MMD + package images) to disk
    and register a new QUEUED job.

    Every file is saved under a job-id-prefixed name/directory so each
    job's source artifacts are unambiguous on disk and collision-free.
    Uploaded images are written byte-for-byte, unmodified, with their
    original filenames preserved — the figure-matching engine
    (src/verification/figures.py) matches on filename, and these files
    are never written to again after this point.

    When mmd_bytes is supplied the job's mmd_path is set; run_pipeline()
    will take the Mathpix import path and treat the MMD as the primary
    document source. When image_files is non-empty, image_dir is set so
    every uploaded image is registered as a figure (matched or not) during
    that same import.
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex
    pdf_path = UPLOAD_DIR / f"{job_id}.pdf"
    pdf_path.write_bytes(pdf_bytes)

    mmd_path: Optional[Path] = None
    if mmd_bytes:
        mmd_path = UPLOAD_DIR / f"{job_id}.mmd"
        mmd_path.write_bytes(mmd_bytes)

    image_dir: Optional[Path] = None
    if image_files:
        image_dir = UPLOAD_DIR / f"{job_id}_images"
        image_dir.mkdir(parents=True, exist_ok=True)
        for original_name, data in image_files:
            (image_dir / Path(original_name).name).write_bytes(data)

    job = Job(
        job_id=job_id,
        filename=filename,
        pdf_path=pdf_path,
        mmd_path=mmd_path,
        image_dir=image_dir,
    )
    with _lock:
        _jobs[job_id] = job
    logger.info(
        "Job {} created for upload '{}' [source: {}, {} package image(s)]",
        job_id,
        filename,
        "mathpix+pdf" if mmd_path else "pdf-only",
        len(image_files) if image_files else 0,
    )
    return job


def start_job(job_id: str, *, enable_ocr: bool = True) -> None:
    """Run the pipeline for this job on a background thread.

    Fire-and-forget: the calling request returns immediately with the
    QUEUED job; this thread updates the same Job object in place as it
    progresses, which the polling endpoint reads directly.
    """
    thread = threading.Thread(target=_run_job, args=(job_id, enable_ocr), daemon=True)
    thread.start()


def get_job(job_id: str) -> Optional[Job]:
    with _lock:
        return _jobs.get(job_id)


def list_jobs() -> List[Job]:
    """Most recently created first - what the upload page's "recent
    documents" list shows."""
    with _lock:
        return sorted(_jobs.values(), key=lambda job: job.created_at, reverse=True)


def record_stage_complete(job_id: str, stage: str) -> None:
    """Update last_completed_stage and flush a checkpoint to disk.

    Called by the pipeline's on_stage_complete callback after every
    successful stage so that, if the server dies, recovery can report
    the furthest stage that actually finished.
    """
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.last_completed_stage = stage
    _write_checkpoint(job)


def load_persisted_jobs() -> None:
    """Reload terminal job records from disk into the in-memory store.

    Called once at server startup. Jobs that were PROCESSING when the
    server last died are recovered as FAILED. Already-in-memory jobs
    (e.g. from a hot-reload) are left untouched.
    """
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    loaded = 0
    recovered_as_failed = 0

    for path in sorted(JOBS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            job = _job_from_dict(data)
            with _lock:
                if job.job_id in _jobs:
                    continue
                _jobs[job.job_id] = job
                loaded += 1
                if job.status == JobStatus.FAILED and data.get("status") in (
                    JobStatus.QUEUED.value, JobStatus.PROCESSING.value
                ):
                    recovered_as_failed += 1
        except Exception as exc:
            logger.warning("Skipping unreadable job checkpoint {}: {}", path.name, exc)

    if loaded:
        logger.info(
            "Loaded {} persisted job(s) from disk ({} recovered as failed)",
            loaded,
            recovered_as_failed,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _run_job(job_id: str, enable_ocr: bool) -> None:
    job = get_job(job_id)
    if job is None:
        logger.error("Job {} disappeared before it could start", job_id)
        return

    with _lock:
        job.status = JobStatus.PROCESSING
        job.started_at = datetime.now(timezone.utc)

    # Write an initial checkpoint so that a restart while the pipeline is
    # running can see this job was in-flight (status=processing).
    _write_checkpoint(job)

    logger.info("Job {} processing started for '{}'", job_id, job.filename)

    def _on_stage_complete(stage: str) -> None:
        record_stage_complete(job_id, stage)

    try:
        result = run_pipeline(
            job.pdf_path,
            enable_ocr=enable_ocr,
            mmd_path=job.mmd_path,
            image_dir=job.image_dir,
            on_stage_complete=_on_stage_complete,
        )
    except Exception as exc:  # run_pipeline itself never raises, but guard regardless
        logger.error("Job {} crashed outside run_pipeline's own error handling: {}", job_id, exc)
        with _lock:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            job.completed_at = datetime.now(timezone.utc)
        _write_checkpoint(job)
        return

    with _lock:
        job.result = result
        job.status = JobStatus.COMPLETE if result.success else JobStatus.FAILED
        job.error_message = result.error_message
        job.completed_at = datetime.now(timezone.utc)
        # FE-0-001 invariant 2: serialize while the lock is still held.
        # model_dump_json() walks a mutable object graph, so serializing
        # after release could interleave with a reviewer mutation and
        # produce a torn snapshot that still validates on reload.
        document_payload = (
            serialize_document(result.document) if result.document is not None else None
        )

    # FE-0-001 invariant 2 (cont.): file I/O happens after the lock is
    # released, matching _write_checkpoint's existing convention that
    # disk writes must not block the lock.
    if document_payload is not None:
        job.document_persisted = save_document(job.job_id, document_payload)

    _write_checkpoint(job)

    logger.info(
        "Job {} finished with status={} in {:.2f}s",
        job_id,
        job.status.value,
        result.duration_seconds,
    )


def _write_checkpoint(job: Job) -> None:
    """Atomically write (or overwrite) the job's JSON sidecar on disk.

    Writing outside the lock is intentional: file I/O should not block
    the lock. Per-job writes are always from the single background thread
    that owns that job, so there is no concurrent writer for a given file.
    """
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    data: dict = {
        "job_id": job.job_id,
        "filename": job.filename,
        "pdf_path": str(job.pdf_path),
        "status": job.status.value,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "last_completed_stage": job.last_completed_stage,
        "error_message": job.error_message,
        "document_persisted": job.document_persisted,
        "result": _result_to_dict(job.result) if job.result else None,
    }
    path = JOBS_DIR / f"{job.job_id}.json"
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.error("Failed to write job checkpoint for {}: {}", job.job_id, exc)


def _result_to_dict(result: PipelineResult) -> dict:
    return {
        "source_pdf_path": result.source_pdf_path,
        "success": result.success,
        "status": result.status.value,
        "duration_seconds": result.duration_seconds,
        "failed_stage": result.failed_stage,
        "error_message": result.error_message,
        "markdown_path": str(result.markdown_path) if result.markdown_path else None,
        "docx_path": str(result.docx_path) if result.docx_path else None,
        "report_path": str(result.report_path) if result.report_path else None,
    }


def _result_from_dict(data: dict) -> PipelineResult:
    from src.models.document import ProcessingStatus
    return PipelineResult(
        source_pdf_path=data["source_pdf_path"],
        success=data["success"],
        status=ProcessingStatus(data["status"]),
        duration_seconds=data["duration_seconds"],
        failed_stage=data.get("failed_stage"),
        error_message=data.get("error_message"),
        markdown_path=Path(data["markdown_path"]) if data.get("markdown_path") else None,
        docx_path=Path(data["docx_path"]) if data.get("docx_path") else None,
        report_path=Path(data["report_path"]) if data.get("report_path") else None,
    )


def _job_from_dict(data: dict) -> Job:
    def _dt(s: Optional[str]) -> Optional[datetime]:
        return datetime.fromisoformat(s) if s else None

    status = JobStatus(data["status"])
    last_stage = data.get("last_completed_stage")

    # Jobs that were still in-flight when the server died cannot be resumed.
    # Convert them to FAILED so the frontend gets an actionable terminal state.
    recovering = status in (JobStatus.QUEUED, JobStatus.PROCESSING)
    if recovering:
        stage_info = f"; last completed stage: {last_stage}" if last_stage else ""
        error_message = f"Server restarted during processing{stage_info}."
        completed_at = datetime.now(timezone.utc)
        final_status = JobStatus.FAILED
    else:
        error_message = data.get("error_message")
        completed_at = _dt(data.get("completed_at"))
        final_status = status

    job = Job(
        job_id=data["job_id"],
        filename=data["filename"],
        pdf_path=Path(data["pdf_path"]),
        status=final_status,
        created_at=_dt(data.get("created_at")) or datetime.now(timezone.utc),
        started_at=_dt(data.get("started_at")),
        completed_at=completed_at,
        last_completed_stage=last_stage,
        error_message=error_message,
        # Absent in checkpoints written before FE-0-001 — defaulting to
        # False reproduces the old "no document after restart" behaviour
        # for them exactly.
        document_persisted=bool(data.get("document_persisted", False)),
    )

    if not recovering and data.get("result"):
        try:
            job.result = _result_from_dict(data["result"])
        except Exception as exc:
            logger.warning("Could not reconstruct PipelineResult for job {}: {}", job.job_id, exc)

    # FE-0-001 — rehydrate the canonical Document.
    #
    # The sidecar on disk is the source of truth, not job.document_persisted:
    # that flag is written once at completion and can be stale in either
    # direction (a sidecar deleted out of band; a save that succeeded while
    # the checkpoint write did not). So the load is attempted whenever there
    # is a result to attach it to, and the flag is then corrected to match
    # what was actually found.
    #
    # load_document() returns None for every failure mode — missing,
    # unreadable, corrupt, schema mismatch, failed validation — so None here
    # is not exceptional. It reproduces the documented pre-FE-0-001 state
    # (recovered job, document=None) that the rest of the system already
    # handles, rather than failing the whole recovery.
    if job.result is not None:
        document = load_document(job.job_id)
        if document is None and job.document_persisted:
            logger.warning(
                "Job {} checkpoint claims a persisted document but none could be "
                "loaded; recovering without it",
                job.job_id,
            )
        job.result.document = document
        job.document_persisted = document is not None

    return job
