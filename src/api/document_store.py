"""Durable storage for the canonical Document (FE-0-001).

Why this exists
---------------
Job *records* have always survived a restart (src/api/jobs.py), but the
Document they describe did not: ``_result_to_dict()`` serialized nine
scalar/path fields and dropped ``document`` entirely. A recovered job
therefore came back as ``status=COMPLETE`` with ``document=None`` — the
UI reported a finished, clean document while holding no data, and
``_needs_export_regen()`` silently served stale exports because it
short-circuits on ``document is None``. This module closes that hole.

Design (approved FE-0-001 architecture + implementation review)
---------------------------------------------------------------
The whole Document tree is Pydantic (``Document`` -> ``SemanticObject``
-> ``BaseModel``), so serialization needs no bespoke mapping layer. One
JSON sidecar per job, mirroring the existing ``outputs/jobs/`` convention.

Four invariants come from the implementation review and are load-bearing.
Breaking any of them reintroduces a real defect that was found by review
rather than by test:

1. **This module never acquires ``jobs._lock``.** All seven mutation
   sites already run under that lock, and it is a plain, *non-reentrant*
   ``threading.Lock``. If ``save_document()`` re-acquired it the server
   would deadlock permanently on the first correction. This module does
   not import ``jobs`` at all, which makes the invariant structural
   rather than a matter of discipline (and avoids a circular import).

2. **Serialize inside the caller's lock; write outside it.**
   ``serialize_document()`` is pure CPU and must run while the caller
   still holds the lock, because ``model_dump_json()`` walks a mutable
   object graph — concurrent mutation yields a torn snapshot that still
   validates on reload, i.e. silent corruption. ``save_document()`` takes
   the *already-serialized string* precisely so the file I/O can happen
   after the lock is released. That split is why these are two functions.

3. **Atomic rename is not durability.** ``os.replace()`` is atomic on
   POSIX and Windows, but without ``flush()`` + ``os.fsync()`` first, a
   power loss can land the rename while the data pages have not been
   written — producing a file that looks valid and is empty or stale.
   The temp file is created in the *same directory* so the rename never
   crosses a volume boundary.

4. **The schema envelope ships from the first commit.** Retrofitting a
   version field onto files already on disk is not cleanly possible, so
   every sidecar carries ``schema_version`` from day one. A mismatch is
   refused cleanly rather than surfacing as an opaque ValidationError.

Failure policy: every load failure degrades to ``None`` — exactly the
pre-change behaviour — and logs loudly. A half-populated Document is
never returned; that would be worse than no document at all, because it
would look like real data.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger
from pydantic import ValidationError

from src.models.document import Document
from src.pipeline.phase1_pipeline import DEFAULT_OUTPUT_ROOT

# Bump whenever a change to Document (or anything it contains) makes
# previously written sidecars unreadable — a renamed/removed/retyped
# field. Additive optional fields do not require a bump: Pydantic fills
# them with defaults. On mismatch load_document() returns None, which
# degrades to the documented "no document for this recovered job" state.
SCHEMA_VERSION = 1

DOCUMENTS_DIR = DEFAULT_OUTPUT_ROOT / "documents"

TEMP_SUFFIX = ".tmp"

# os.replace() raises PermissionError on Windows when the destination is
# held open by another process. Antivirus and search indexers do this
# routinely on this platform, so a single attempt fails intermittently in
# production and — worse — flakily in CI.
_REPLACE_ATTEMPTS = 5
_REPLACE_BACKOFF_SECONDS = 0.05


def document_path(job_id: str) -> Path:
    """Absolute path of the sidecar for ``job_id``.

    Resolved absolutely because ``DEFAULT_OUTPUT_ROOT`` is a *relative*
    Path("outputs"): where it lands depends on the process working
    directory. That was cosmetic while these files were disposable
    artifacts; now that reviewer work lives here it is load-bearing, so
    the resolved location is made explicit rather than left implicit.
    """
    return (DOCUMENTS_DIR / f"{job_id}.json").resolve()


def _temp_path(job_id: str) -> Path:
    """Temp path for ``job_id``, deliberately in the same directory.

    Same directory means same volume, which ``os.replace()`` requires in
    order to be atomic. A system temp dir would silently degrade to a
    non-atomic copy.
    """
    final = document_path(job_id)
    return final.with_name(final.name + TEMP_SUFFIX)


def serialize_document(document: Document) -> str:
    """Serialize ``document`` into the versioned envelope, as a string.

    MUST be called while the caller still holds the lock guarding the
    document (invariant 2). Pure CPU, no I/O — measured at 1-101 ms
    across the 10-document benchmark corpus (worst case 3.36 MB).

    The envelope is composed around ``model_dump_json()`` rather than
    ``json.dumps({..., "document": document.model_dump(mode="json")})``
    because the latter serializes the tree twice — roughly doubling the
    worst case toward the 250 ms threshold that would have forced a
    different architecture. ``doc_json`` is valid JSON by construction
    and the other two fields are locally controlled, so the composition
    is safe; ``test_envelope_is_valid_json`` pins that.
    """
    doc_json = document.model_dump_json()
    saved_at = datetime.now(timezone.utc).isoformat()
    return (
        '{"schema_version": '
        + str(SCHEMA_VERSION)
        + ', "saved_at": '
        + json.dumps(saved_at)
        + ', "document": '
        + doc_json
        + "}"
    )


def _replace_with_retry(tmp: Path, final: Path) -> None:
    last_error: Optional[OSError] = None
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(tmp, final)
            return
        except PermissionError as exc:  # Windows: destination held open
            last_error = exc
            time.sleep(_REPLACE_BACKOFF_SECONDS * (attempt + 1))
    raise OSError(
        f"Could not replace {final} after {_REPLACE_ATTEMPTS} attempts: {last_error}"
    )


def save_document(job_id: str, payload: str) -> bool:
    """Atomically write a serialized document sidecar. Returns success.

    Takes the *already-serialized* payload from serialize_document() so
    the caller can release its lock before this runs (invariant 2).

    NEVER acquires jobs._lock (invariant 1).

    Durability sequence (invariant 3): write temp -> flush -> fsync ->
    atomic replace. A reader therefore observes either the previous
    version or the new one, never a partial file, even across power loss.

    Returns False rather than raising: a persistence failure must not
    fail the reviewer's HTTP request — the mutation itself already
    succeeded in memory. The error is logged at ERROR level.
    """
    final = document_path(job_id)
    tmp = _temp_path(job_id)
    try:
        final.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(tmp, final)
        return True
    except Exception as exc:
        logger.error("Failed to persist document for job {}: {}", job_id, exc)
        # Best-effort cleanup; a surviving temp file is swept at startup.
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return False


def load_document(job_id: str) -> Optional[Document]:
    """Load a persisted Document, or None if unavailable or unreadable.

    Returns None — never a partially populated Document — for every
    failure mode: missing file, unreadable file, malformed JSON, missing
    or mismatched schema_version, and failed model validation. None is
    the pre-change behaviour for a recovered job, so every failure
    degrades to a state the rest of the system already handles.
    """
    path = document_path(job_id)
    if not path.is_file():
        return None

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.error("Unreadable document sidecar for job {}: {}", job_id, exc)
        return None

    if not isinstance(raw, dict):
        logger.error("Document sidecar for job {} is not a JSON object", job_id)
        return None

    version = raw.get("schema_version")
    if version != SCHEMA_VERSION:
        logger.warning(
            "Document sidecar for job {} has schema_version {} (expected {}); ignoring it",
            job_id,
            version,
            SCHEMA_VERSION,
        )
        return None

    if "document" not in raw:
        logger.error("Document sidecar for job {} has no 'document' key", job_id)
        return None

    try:
        return Document.model_validate(raw["document"])
    except ValidationError as exc:
        logger.error("Document sidecar for job {} failed validation: {}", job_id, exc)
        return None


def delete_document(job_id: str) -> bool:
    """Remove a job's sidecar. True if a file was removed."""
    path = document_path(job_id)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.error("Could not delete document sidecar for job {}: {}", job_id, exc)
        return False


def sweep_orphan_temp_files() -> int:
    """Delete ``*.json.tmp`` left behind by a process killed mid-write.

    Called once at startup. Orphans are always safe to delete: a temp
    file only becomes authoritative via os.replace(), so any that
    survives represents a write that never completed.
    """
    if not DOCUMENTS_DIR.exists():
        return 0
    removed = 0
    for path in DOCUMENTS_DIR.glob(f"*.json{TEMP_SUFFIX}"):
        try:
            path.unlink()
            removed += 1
        except OSError as exc:
            logger.warning("Could not remove orphan temp file {}: {}", path.name, exc)
    if removed:
        logger.info("Removed {} orphan document temp file(s)", removed)
    return removed
