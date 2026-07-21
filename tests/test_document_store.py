"""Unit tests for src/api/document_store.py (FE-0-001, Phase 1).

Maps to the approved acceptance criteria:

  A1  round-trip fidelity
  A2  durability / atomicity
  A3  corruption rejection
  A4  missing file
  A9  schema envelope
  A10 orphan temp sweep

plus the two invariants the implementation review added, which exist
specifically because the *original* plan violated them:

  invariant 1  document_store never acquires jobs._lock (deadlock)
  invariant 2  serialize/write are separable (torn-snapshot corruption)
"""

import json
import os
from pathlib import Path

import pytest

from src.api import document_store
from src.api.document_store import (
    SCHEMA_VERSION,
    TEMP_SUFFIX,
    delete_document,
    document_path,
    load_document,
    save_document,
    serialize_document,
    sweep_orphan_temp_files,
)
from src.mathpix.ingestor import MathpixImportProvider
from src.models.contracts import Document
from src.models.metadata import Metadata
from src.models.page import Page

JOB_ID = "abc123"


@pytest.fixture(autouse=True)
def _isolated_documents_dir(tmp_path, monkeypatch):
    """Redirect the store at a per-test directory.

    Autouse so no test can accidentally write into the real
    outputs/documents/ tree.
    """
    monkeypatch.setattr(document_store, "DOCUMENTS_DIR", tmp_path / "documents")
    return tmp_path / "documents"


def _make_document(page_count: int = 2) -> Document:
    return Document(
        source_pdf_path="test.pdf",
        metadata=Metadata(filename="test.pdf", page_count=page_count),
        pages=[Page(page_number=i + 1) for i in range(page_count)],
    )


def _rich_document(tmp_path) -> Document:
    """A document with real nested content, via the Mathpix import path.

    Round-tripping an empty Document would prove almost nothing — the
    risk is in the nested object graph (headings, front matter, spans),
    so the fidelity tests use a document that actually has one.
    """
    mmd = tmp_path / "t.mmd"
    mmd.write_text(
        r"\title{The Nature of Enquiry}"
        + "\n\n"
        + r"\section*{Introduction}"
        + "\n\nSome body text.\n\n"
        + r"\section*{Method}"
        + "\n\nMore body text.\n",
        encoding="utf-8",
    )
    return MathpixImportProvider().import_document(_make_document(), mmd_path=mmd)


def _save(document, job_id: str = JOB_ID) -> bool:
    """Mirror the production call shape: serialize, then write."""
    return save_document(job_id, serialize_document(document))


# ── A1 · round-trip fidelity ───────────────────────────────────────────

class TestRoundTripFidelity:
    def test_minimal_document_round_trips(self):
        original = _make_document()
        assert _save(original) is True
        assert load_document(JOB_ID) == original

    def test_rich_document_round_trips(self, tmp_path):
        original = _rich_document(tmp_path)
        assert original.headings, "fixture must have headings or it proves nothing"
        assert _save(original) is True
        assert load_document(JOB_ID) == original

    def test_version_survives(self):
        doc = _make_document()
        doc.version = 47
        _save(doc)
        assert load_document(JOB_ID).version == 47

    def test_reviewer_state_survives(self, tmp_path):
        """The fields FE-0-001 exists to protect."""
        doc = _rich_document(tmp_path)
        doc.metadata.title = "Reviewed Title"
        doc.metadata.language = "en-GB"
        _save(doc)

        loaded = load_document(JOB_ID)
        assert loaded.metadata.title == "Reviewed Title"
        assert loaded.metadata.language == "en-GB"
        assert len(loaded.headings) == len(doc.headings)
        assert [h.text for h in loaded.headings] == [h.text for h in doc.headings]

    def test_overwrite_replaces_previous_version(self):
        doc = _make_document()
        _save(doc)
        doc.version = 99
        _save(doc)
        assert load_document(JOB_ID).version == 99


# ── A2 · durability / atomicity ────────────────────────────────────────

class TestAtomicity:
    def test_no_temp_file_remains_after_success(self, _isolated_documents_dir):
        _save(_make_document())
        assert list(_isolated_documents_dir.glob(f"*{TEMP_SUFFIX}")) == []

    def test_temp_file_is_same_directory_as_final(self):
        # Same directory => same volume => os.replace() is atomic.
        assert document_store._temp_path(JOB_ID).parent == document_path(JOB_ID).parent

    def test_fsync_is_called_before_replace(self, monkeypatch):
        """Invariant 3: atomic rename is not durability without fsync."""
        calls = []
        real_fsync, real_replace = os.fsync, os.replace
        monkeypatch.setattr(os, "fsync", lambda fd: (calls.append("fsync"), real_fsync(fd))[1])
        monkeypatch.setattr(os, "replace", lambda a, b: (calls.append("replace"), real_replace(a, b))[1])

        _save(_make_document())
        assert calls == ["fsync", "replace"], f"expected fsync before replace, got {calls}"

    def test_failed_write_preserves_previous_version(self, monkeypatch):
        doc = _make_document()
        doc.version = 1
        _save(doc)

        def _boom(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", _boom)
        doc.version = 2
        assert _save(doc) is False
        # Prior version intact — never partial, never lost.
        assert load_document(JOB_ID).version == 1

    def test_failed_write_cleans_up_temp_file(self, monkeypatch, _isolated_documents_dir):
        monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("nope")))
        assert _save(_make_document()) is False
        assert list(_isolated_documents_dir.glob(f"*{TEMP_SUFFIX}")) == []

    def test_save_returns_false_rather_than_raising(self, monkeypatch):
        """A persistence failure must not fail the reviewer's request."""
        monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("nope")))
        assert _save(_make_document()) is False


# ── A3 · corruption rejection ──────────────────────────────────────────

class TestCorruptionRejection:
    @pytest.mark.parametrize(
        "content",
        [
            "",                                  # empty
            "{ not json",                        # malformed
            "[]",                                # valid JSON, wrong shape
            '{"schema_version": 1}',             # envelope without document
            '{"document": {}}',                  # document without version
            '{"schema_version": 1, "document": {"nonsense": true}}',  # fails validation
        ],
        ids=["empty", "malformed", "wrong-shape", "no-document", "no-version", "invalid-model"],
    )
    def test_corrupt_sidecar_yields_none(self, content, _isolated_documents_dir):
        _isolated_documents_dir.mkdir(parents=True, exist_ok=True)
        document_path(JOB_ID).write_text(content, encoding="utf-8")
        assert load_document(JOB_ID) is None

    def test_truncated_sidecar_yields_none(self):
        _save(_make_document())
        path = document_path(JOB_ID)
        payload = path.read_text(encoding="utf-8")
        path.write_text(payload[: len(payload) // 2], encoding="utf-8")
        assert load_document(JOB_ID) is None

    def test_never_returns_partial_document(self, _isolated_documents_dir):
        """A half-populated Document would look like real data — worse than None."""
        _isolated_documents_dir.mkdir(parents=True, exist_ok=True)
        document_path(JOB_ID).write_text(
            json.dumps({"schema_version": SCHEMA_VERSION, "document": {"pages": []}}),
            encoding="utf-8",
        )
        assert load_document(JOB_ID) is None


# ── A4 · missing file ──────────────────────────────────────────────────

class TestMissingFile:
    def test_missing_sidecar_yields_none(self):
        assert load_document("never-saved") is None

    def test_missing_directory_yields_none(self):
        assert load_document(JOB_ID) is None

    def test_delete_removes_sidecar(self):
        _save(_make_document())
        assert delete_document(JOB_ID) is True
        assert load_document(JOB_ID) is None

    def test_delete_missing_is_not_an_error(self):
        assert delete_document("never-saved") is False


# ── A9 · schema envelope ───────────────────────────────────────────────

class TestSchemaEnvelope:
    def test_envelope_is_valid_json(self, tmp_path):
        """Pins the hand-composed envelope in serialize_document()."""
        raw = json.loads(serialize_document(_rich_document(tmp_path)))
        assert raw["schema_version"] == SCHEMA_VERSION
        assert isinstance(raw["saved_at"], str)
        assert isinstance(raw["document"], dict)

    def test_saved_at_is_iso8601_utc(self):
        from datetime import datetime

        raw = json.loads(serialize_document(_make_document()))
        parsed = datetime.fromisoformat(raw["saved_at"])
        assert parsed.tzinfo is not None

    def test_future_schema_version_is_refused_cleanly(self, _isolated_documents_dir):
        _isolated_documents_dir.mkdir(parents=True, exist_ok=True)
        raw = json.loads(serialize_document(_make_document()))
        raw["schema_version"] = SCHEMA_VERSION + 1
        document_path(JOB_ID).write_text(json.dumps(raw), encoding="utf-8")
        # Refused, not an opaque ValidationError traceback.
        assert load_document(JOB_ID) is None

    def test_written_file_carries_schema_version(self):
        _save(_make_document())
        raw = json.loads(document_path(JOB_ID).read_text(encoding="utf-8"))
        assert raw["schema_version"] == SCHEMA_VERSION


# ── A10 · orphan temp sweep ────────────────────────────────────────────

class TestOrphanSweep:
    def test_sweep_removes_orphan_temp_files(self, _isolated_documents_dir):
        _isolated_documents_dir.mkdir(parents=True, exist_ok=True)
        (_isolated_documents_dir / f"a.json{TEMP_SUFFIX}").write_text("partial", encoding="utf-8")
        (_isolated_documents_dir / f"b.json{TEMP_SUFFIX}").write_text("partial", encoding="utf-8")

        assert sweep_orphan_temp_files() == 2
        assert list(_isolated_documents_dir.glob(f"*{TEMP_SUFFIX}")) == []

    def test_sweep_preserves_real_sidecars(self, _isolated_documents_dir):
        _save(_make_document())
        (_isolated_documents_dir / f"orphan.json{TEMP_SUFFIX}").write_text("x", encoding="utf-8")

        assert sweep_orphan_temp_files() == 1
        assert load_document(JOB_ID) is not None

    def test_sweep_on_missing_directory_is_noop(self):
        assert sweep_orphan_temp_files() == 0


# ── invariants from the implementation review ──────────────────────────

class TestReviewInvariants:
    def test_module_never_imports_jobs(self):
        """Invariant 1 — structural guarantee against deadlock.

        jobs._lock is a plain non-reentrant threading.Lock, and all seven
        mutation sites already hold it. If this module could acquire it,
        the first correction would deadlock the server permanently. Not
        importing jobs at all makes that impossible rather than merely
        discouraged.
        """
        source = Path(document_store.__file__).read_text(encoding="utf-8")
        assert "from src.api.jobs" not in source
        assert "import jobs" not in source

    def test_serialize_and_save_are_separable(self, tmp_path):
        """Invariant 2 — serialize under the lock, write outside it.

        The two steps must be independently callable, or a caller cannot
        release the lock between them and every write risks a torn
        snapshot.
        """
        payload = serialize_document(_rich_document(tmp_path))
        assert isinstance(payload, str)
        assert save_document(JOB_ID, payload) is True
        assert load_document(JOB_ID) is not None

    def test_save_accepts_payload_not_document(self):
        """save_document() takes a string, never a live Document."""
        import inspect

        params = list(inspect.signature(save_document).parameters)
        assert params == ["job_id", "payload"]
