"""In-memory job tracking for the RAWRS API.

run_pipeline() (src/pipeline/phase1_pipeline.py) is a long-running,
blocking call - real OCR pages have taken anywhere from ~1-3 minutes
(Docling) to several minutes (Surya fallback) per page in this
project's own benchmark runs. An HTTP request can't block for that
long, so every upload is handed to a background thread immediately and
tracked here by job id; the frontend polls GET /api/documents/{id} for
status instead of waiting on the upload request itself.

No database (docs/ARCHITECTURE.md "no databases" constraint) - this is
a plain in-memory dict guarded by a lock. Job state does not survive a
process restart. That is an accepted limitation for a first internal
tool, not an oversight - see docs/KNOWN_LIMITATIONS.md's framing of the
platform layer as deliberately minimal in Phase 1.
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from src.pipeline.phase1_pipeline import DEFAULT_OUTPUT_ROOT, PipelineResult, run_pipeline

UPLOAD_DIR = DEFAULT_OUTPUT_ROOT / "uploads"


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


_jobs: Dict[str, Job] = {}
_lock = threading.Lock()


def create_job(filename: str, pdf_bytes: bytes) -> Job:
    """Save the uploaded PDF to disk and register a new QUEUED job.

    Saving under a job-id-prefixed filename (rather than the original
    name) avoids collisions between two uploads of a same-named file
    and keeps each job's source PDF unambiguous on disk.
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex
    pdf_path = UPLOAD_DIR / f"{job_id}.pdf"
    pdf_path.write_bytes(pdf_bytes)

    job = Job(job_id=job_id, filename=filename, pdf_path=pdf_path)
    with _lock:
        _jobs[job_id] = job
    logger.info("Job {} created for upload '{}'", job_id, filename)
    return job


def start_job(job_id: str, *, enable_ocr: bool = True) -> None:
    """Run the pipeline for this job on a background thread.

    Fire-and-forget: the calling request returns immediately with the
    QUEUED job; this thread updates the same Job object in place as it
    progresses, which the polling endpoint reads directly.
    """
    thread = threading.Thread(target=_run_job, args=(job_id, enable_ocr), daemon=True)
    thread.start()


def _run_job(job_id: str, enable_ocr: bool) -> None:
    job = get_job(job_id)
    if job is None:
        logger.error("Job {} disappeared before it could start", job_id)
        return

    with _lock:
        job.status = JobStatus.PROCESSING
        job.started_at = datetime.now(timezone.utc)

    logger.info("Job {} processing started for '{}'", job_id, job.filename)

    try:
        result = run_pipeline(job.pdf_path, enable_ocr=enable_ocr)
    except Exception as exc:  # run_pipeline itself never raises, but guard regardless
        logger.error("Job {} crashed outside run_pipeline's own error handling: {}", job_id, exc)
        with _lock:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            job.completed_at = datetime.now(timezone.utc)
        return

    with _lock:
        job.result = result
        job.status = JobStatus.COMPLETE if result.success else JobStatus.FAILED
        job.error_message = result.error_message
        job.completed_at = datetime.now(timezone.utc)

    logger.info(
        "Job {} finished with status={} in {:.2f}s",
        job_id,
        job.status.value,
        result.duration_seconds,
    )


def get_job(job_id: str) -> Optional[Job]:
    with _lock:
        return _jobs.get(job_id)


def list_jobs() -> List[Job]:
    """Most recently created first - what the upload page's "recent
    documents" list shows."""
    with _lock:
        return sorted(_jobs.values(), key=lambda job: job.created_at, reverse=True)
