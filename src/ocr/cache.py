"""Page-level OCR result cache.

Docling takes 1-3 minutes per scanned page and Surya several; neither result
depends on anything RAWRS decides. Re-uploading a PDF, re-running a corpus
after a RAWRS fix, or a benchmark probe therefore re-pays minutes per page for
an answer that cannot have changed. This module remembers that answer.

What is cached is the engine's *raw* output for one page - the text it
exported (and, for Docling, its title/section-header items) - never anything
RAWRS derived from it. Whitespace normalisation, XML sanitisation and heading
levels are recomputed from the cached raw output on every run, so a change to
RAWRS's own code can never be masked by a stale entry.

A hit is valid only for the same

* PDF bytes (sha256 of the file - a renamed copy still hits, an edited one misses),
* page number,
* engine package versions (docling + its OCR backend, or surya + torch),
* source of the modules that turn a page into raw output (engine + config).

Any of those changing simply misses. Failed conversions are never cached - a
crash may be transient, and the next run should retry.

Knobs: ``RAWRS_OCR_CACHE=off`` disables it; ``RAWRS_OCR_CACHE_DIR`` moves it
(default ``outputs/cache/ocr``). Deleting the directory is always safe.

ponytail: model *weights* live in the Hugging Face cache and are not part of
the key; they only change when a package upgrade asks for new ones, which the
version component already catches. Clear the directory after hand-swapping
weights.
"""

from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Optional, Union

from loguru import logger

CACHE_SCHEMA = 1

_DEFAULT_DIR = Path("outputs") / "cache" / "ocr"
_OCR_DIR = Path(__file__).resolve().parent
_OFF_VALUES = frozenset({"0", "off", "false", "no"})

# Everything that shapes an engine's raw page output.
_ENGINE_PACKAGES = {
    "docling": ("docling", "docling-core", "docling-ibm-models", "rapidocr", "onnxruntime"),
    "surya": ("surya-ocr", "torch"),
}
_ENGINE_SOURCES = {
    "docling": ("docling_config.py", "docling_engine.py"),
    "surya": ("surya_config.py", "surya_engine.py"),
}

PathLike = Union[str, Path]


def enabled() -> bool:
    return os.environ.get("RAWRS_OCR_CACHE", "on").strip().lower() not in _OFF_VALUES


def cache_dir() -> Path:
    return Path(os.environ.get("RAWRS_OCR_CACHE_DIR") or _DEFAULT_DIR)


@lru_cache(maxsize=64)
def _file_sha256(path: str, size: int, mtime_ns: int) -> str:
    # size + mtime are part of the lru key so an edited file is re-hashed.
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pdf_fingerprint(pdf_path: PathLike) -> str:
    path = Path(pdf_path).resolve()
    stat = path.stat()
    return _file_sha256(str(path), stat.st_size, stat.st_mtime_ns)


def _version(package: str) -> str:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return "absent"


@lru_cache(maxsize=None)
def engine_fingerprint(engine: str) -> str:
    digest = hashlib.sha256(f"schema={CACHE_SCHEMA};engine={engine}".encode())
    for package in _ENGINE_PACKAGES[engine]:
        digest.update(f";{package}={_version(package)}".encode())
    for name in _ENGINE_SOURCES[engine]:
        digest.update((_OCR_DIR / name).read_bytes())
    return digest.hexdigest()[:16]


def _entry_path(engine: str, pdf_path: PathLike, page_number: int) -> Path:
    pdf_sha = pdf_fingerprint(pdf_path)
    name = f"{pdf_sha}-{engine_fingerprint(engine)}-p{page_number}.json"
    return cache_dir() / engine / pdf_sha[:2] / name


def lookup(engine: str, pdf_path: PathLike, page_number: int) -> Optional[dict]:
    """The cached raw output for this page, or None (miss, disabled, unreadable)."""
    if not enabled():
        return None
    try:
        path = _entry_path(engine, pdf_path, page_number)
        if not path.is_file():
            return None
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("OCR cache read failed for page {}: {}", page_number, exc)
        return None
    if not isinstance(entry, dict) or not isinstance(entry.get("text"), str):
        return None
    return entry


def store(engine: str, pdf_path: PathLike, page_number: int, entry: dict) -> None:
    """Remember one page's raw output. Never raises: a cache that cannot be
    written costs the next run time, not this run its result."""
    if not enabled():
        return
    tmp: Optional[Path] = None
    try:
        path = _entry_path(engine, pdf_path, page_number)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)  # atomic: a reader sees the old entry or the new one
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("OCR cache write failed for page {}: {}", page_number, exc)
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
