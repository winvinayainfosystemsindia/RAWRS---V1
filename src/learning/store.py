"""Where post-export learning lives on disk.

One directory per job, beside the other outputs (same convention as
``outputs/edits`` - RAWRS keeps its state in files, docs/ARCHITECTURE.md):

    outputs/learning/<job_id>/exported.docx   the DOCX the remediator downloaded last
    outputs/learning/<job_id>/final.docx      the DOCX they uploaded back
    outputs/learning/<job_id>/review.json     the diff + checklist comparison

``exported.docx`` is snapshotted at download time, not regenerated at upload
time: a reviewer who kept working in RAWRS after downloading would otherwise
have RAWRS's own later changes counted as the remediator's.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Iterator, Optional, Tuple

from loguru import logger

SCHEMA_VERSION = 1
MAX_DOCX_BYTES = 50_000_000
# A DOCX is a zip; refuse one that would inflate past this (a zip bomb).
MAX_UNCOMPRESSED_BYTES = 500_000_000
_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

EXPORTED = "exported.docx"
FINAL = "final.docx"
REVIEW = "review.json"


class InvalidDocx(ValueError):
    """The upload is not a Word document RAWRS can read."""


def learning_dir(output_root: Path) -> Path:
    return output_root / "learning"


def job_dir(output_root: Path, job_id: str) -> Path:
    if not _JOB_ID.match(job_id):  # never let an id become a path outside the store
        raise ValueError(f"Invalid job id: {job_id!r}")
    return learning_dir(output_root) / job_id


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def snapshot_export(output_root: Path, job_id: str, docx_path: Optional[Path]) -> bool:
    """Keep a copy of the DOCX being downloaded. Never raises: a failed
    snapshot must not fail the download (the upload then falls back to the
    current export). ``RAWRS_LEARNING_SNAPSHOT=off`` turns it off."""
    if os.environ.get("RAWRS_LEARNING_SNAPSHOT", "on").strip().lower() in {"0", "off", "false", "no"}:
        return False
    if docx_path is None or not Path(docx_path).is_file():
        return False
    try:
        target = job_dir(output_root, job_id) / EXPORTED
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        shutil.copyfile(docx_path, tmp)
        os.replace(tmp, target)
        return True
    except (OSError, ValueError) as exc:
        logger.warning("Could not snapshot the exported DOCX for job {}: {}", job_id, exc)
        return False


def exported_snapshot(output_root: Path, job_id: str) -> Optional[Path]:
    path = job_dir(output_root, job_id) / EXPORTED
    return path if path.is_file() else None


def validate_docx(data: bytes) -> None:
    """Refuse anything that is not a plausible, safe-to-open DOCX."""
    if not data:
        raise InvalidDocx("The file is empty.")
    if len(data) > MAX_DOCX_BYTES:
        raise InvalidDocx(f"The file is larger than {MAX_DOCX_BYTES // 1_000_000} MB.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            inflated = sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile as exc:
        raise InvalidDocx("This is not a Word (.docx) document.") from exc
    if "word/document.xml" not in names or "[Content_Types].xml" not in names:
        raise InvalidDocx("This is not a Word (.docx) document.")
    if inflated > MAX_UNCOMPRESSED_BYTES:
        raise InvalidDocx("The document expands to an unreasonable size and was refused.")


def save_final(output_root: Path, job_id: str, data: bytes) -> Path:
    validate_docx(data)
    path = job_dir(output_root, job_id) / FINAL
    _atomic_write_bytes(path, data)
    return path


def save_review(output_root: Path, job_id: str, review: dict) -> dict:
    record = {"schema_version": SCHEMA_VERSION, **review}
    payload = json.dumps(record, ensure_ascii=False, indent=1).encode("utf-8")
    _atomic_write_bytes(job_dir(output_root, job_id) / REVIEW, payload)
    return record


def load_review(output_root: Path, job_id: str) -> Optional[dict]:
    path = job_dir(output_root, job_id) / REVIEW
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("Unreadable learning review for job {}: {}", job_id, exc)
        return None
    return record if record.get("schema_version") == SCHEMA_VERSION else None


def delete_review(output_root: Path, job_id: str) -> bool:
    """Forget the uploaded final DOCX and its review; the export snapshot stays."""
    removed = False
    for name in (FINAL, REVIEW):
        path = job_dir(output_root, job_id) / name
        if path.is_file():
            path.unlink()
            removed = True
    return removed


def iter_reviews(output_root: Path) -> Iterator[Tuple[str, dict]]:
    root = learning_dir(output_root)
    if not root.is_dir():
        return
    for directory in sorted(root.iterdir()):
        if directory.is_dir() and _JOB_ID.match(directory.name):
            review = load_review(output_root, directory.name)
            if review is not None:
                yield directory.name, review
