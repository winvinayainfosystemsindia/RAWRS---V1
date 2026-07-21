"""FE-0-003 Phase 1 — the Markdown preview reflects reviewer decisions.

Before this change ``GET /documents/{id}/markdown`` served the static
pipeline-time file unconditionally, while both download handlers already
regenerated from live Document state. An accepted correction therefore
reached the exported .md/.docx but never the pane the reviewer was looking
at, which made the whole review loop look dead when only the preview was.

These tests pin the preview to the same regen-on-demand contract the
downloads use. Phase 1 only: no caching, no version-marker advance, no
persistence — those belong to Phase 2's shared helper.
"""

from pathlib import Path

import pytest

from src.api import document_store, jobs
from src.api.jobs import Job, JobStatus
from src.models.contracts import CorrectionRecord, CorrectionStatus, Heading, HeadingLevel
from src.models.document import Document, ProcessingStatus
from src.models.metadata import Metadata
from src.models.page import Page
from src.pipeline.phase1_pipeline import PipelineResult

# Registers HeadingVerifier on the engine — engine.apply_correction() needs
# the owning verifier for object_type="heading" to be present.
import src.verification.headings  # noqa: F401


PIPELINE_TIME_MARKDOWN = "# Pipeline Time Heading\n\nBody text from the original run.\n"
ORIGINAL_HEADING = "Pipeline Time Heading"
REVIEWED_HEADING = "Reviewer Corrected Heading"


@pytest.fixture(autouse=True)
def _isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(jobs, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(document_store, "DOCUMENTS_DIR", tmp_path / "documents")
    return tmp_path


@pytest.fixture(autouse=True)
def _clean_job_registry():
    yield
    with jobs._lock:
        jobs._jobs.clear()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from src.api.main import app

    return TestClient(app)


def _seed(tmp_path, job_id: str = "prev1", generated_at_version: int = 0):
    """A COMPLETE job whose on-disk Markdown matches pipeline time.

    The static file deliberately differs from what build_markdown() would
    produce for the live document, so a test can tell which of the two the
    endpoint actually served.
    """
    md_path = tmp_path / f"{job_id}.md"
    md_path.write_text(PIPELINE_TIME_MARKDOWN, encoding="utf-8")

    # source="mathpix" puts build_markdown on its semantic-projection path
    # (_render_page_semantic), which renders document.headings directly. The
    # alternative path reinserts headings by matching page.cleaned_text, which
    # a synthetic fixture has none of. Mathpix is also the product's real
    # primary input, so this is the representative case, not a test-only dodge.
    heading = Heading(
        text=ORIGINAL_HEADING,
        level=HeadingLevel.H1,
        page_number=1,
        document_order=0,
        source="mathpix",
        source_line=1,
    )
    doc = Document(
        source_pdf_path="test.pdf",
        metadata=Metadata(filename="test.pdf", page_count=1),
        pages=[Page(page_number=1)],
    )
    doc.headings.append(heading)
    doc.corrections.append(
        CorrectionRecord(
            object_type="heading",
            object_id=heading.id,
            field="text_correction",
            original_value=ORIGINAL_HEADING,
            proposed_value=REVIEWED_HEADING,
            reason="Heading text differs from the PDF.",
            provider="mathpix",
            status=CorrectionStatus.PROPOSED,
        )
    )

    job = Job(
        job_id=job_id,
        filename="test.pdf",
        pdf_path=Path(f"uploads/{job_id}.pdf"),
        status=JobStatus.COMPLETE,
        result=PipelineResult(
            source_pdf_path="test.pdf",
            success=True,
            status=ProcessingStatus.VALIDATED,
            duration_seconds=1.0,
            document=doc,
            markdown_path=md_path,
            markdown_generated_at_version=generated_at_version,
        ),
    )
    with jobs._lock:
        jobs._jobs[job_id] = job
    return job, doc


class TestPreviewReflectsReviewerDecisions:
    def test_accepting_a_correction_updates_the_preview(self, client, tmp_path):
        """The FE-0-003 defect, stated as a test.

        Repro from FE0_VERIFICATION_REPORT_2026-07-19: accept a heading
        text_correction, then read the preview. It used to come back
        pipeline-time.
        """
        _, doc = _seed(tmp_path)
        correction_id = doc.corrections[0].correction_id

        before = client.get("/api/documents/prev1/markdown")
        assert before.status_code == 200
        assert ORIGINAL_HEADING in before.json()["content"]

        accepted = client.patch(
            f"/api/documents/prev1/corrections/{correction_id}",
            json={"action": "accept"},
        )
        assert accepted.status_code == 200

        after = client.get("/api/documents/prev1/markdown")
        assert after.status_code == 200
        content = after.json()["content"]
        assert REVIEWED_HEADING in content, "preview must show the accepted correction"
        assert ORIGINAL_HEADING not in content, "preview must not still show pipeline-time text"

    def test_preview_reflects_the_reviewed_document_not_the_static_file(
        self, client, tmp_path
    ):
        """Divergence alone drives regeneration — no correction needed.

        Any reviewer mutation bumps document.version; the preview must
        follow the Document, not the file written at pipeline time.
        """
        _, doc = _seed(tmp_path)
        doc.headings[0].text = "Directly Edited Heading"
        doc.version += 1

        resp = client.get("/api/documents/prev1/markdown")
        assert resp.status_code == 200
        content = resp.json()["content"]
        assert "Directly Edited Heading" in content
        assert "Body text from the original run." not in content, (
            "served the static file despite a diverged document"
        )

    def test_preview_matches_the_download(self, client, tmp_path):
        """Preview and deliverable must not disagree.

        The two disagreeing is precisely what made FE-0-003 look like
        'corrections never reach the output' when they always reached the
        download.
        """
        _, doc = _seed(tmp_path)
        correction_id = doc.corrections[0].correction_id
        client.patch(
            f"/api/documents/prev1/corrections/{correction_id}", json={"action": "accept"}
        )

        preview = client.get("/api/documents/prev1/markdown").json()["content"]
        download = client.get("/api/documents/prev1/download/markdown")
        assert download.status_code == 200

        # Normalize line endings: the download is served from a file written
        # on this platform, the preview is an in-memory string. Comparing them
        # raw reports a whole-file diff that is purely CRLF-vs-LF noise.
        def _norm(text: str) -> str:
            return text.replace("\r\n", "\n").strip()

        assert _norm(preview) == _norm(download.text)


class TestNoRegressionForUnchangedDocuments:
    def test_unchanged_document_serves_the_static_file_verbatim(self, client, tmp_path):
        """version == generated_at_version: no rebuild, byte-for-byte."""
        _seed(tmp_path, generated_at_version=0)  # document.version defaults to 0

        resp = client.get("/api/documents/prev1/markdown")
        assert resp.status_code == 200
        assert resp.json()["content"] == PIPELINE_TIME_MARKDOWN

    def test_unchanged_document_does_not_invoke_the_builder(
        self, client, tmp_path, monkeypatch
    ):
        """Pins the cheap path: the poller hits this endpoint every 4s, so
        an unchanged document must not pay for a rebuild each tick."""
        _seed(tmp_path, generated_at_version=0)

        def _explode(*_a, **_k):
            raise AssertionError("build_markdown must not run for an unchanged document")

        monkeypatch.setattr("src.markdown.markdown_builder.build_markdown", _explode)

        resp = client.get("/api/documents/prev1/markdown")
        assert resp.status_code == 200
        assert resp.json()["content"] == PIPELINE_TIME_MARKDOWN

    def test_missing_markdown_still_404s(self, client, tmp_path):
        """Error behaviour preserved: no static file is still a 404, even
        though a live document could technically be rendered."""
        job, doc = _seed(tmp_path)
        job.result.markdown_path.unlink()
        doc.version += 1

        resp = client.get("/api/documents/prev1/markdown")
        assert resp.status_code == 404

    def test_regeneration_failure_falls_back_instead_of_500ing(
        self, client, tmp_path, monkeypatch
    ):
        """A read must never 500. Mirrors download_docx's failure path."""
        _, doc = _seed(tmp_path)
        doc.version += 1

        def _boom(*_a, **_k):
            raise RuntimeError("builder exploded")

        monkeypatch.setattr("src.markdown.markdown_builder.build_markdown", _boom)

        resp = client.get("/api/documents/prev1/markdown")
        assert resp.status_code == 200
        assert resp.json()["content"] == PIPELINE_TIME_MARKDOWN


def _norm(text: str) -> str:
    """Line endings differ between an in-memory string and a file written
    on this platform. Comparing them raw reports a whole-file diff that is
    pure CRLF-vs-LF noise — this has produced two near-miss false findings
    in this workstream already."""
    return text.replace("\r\n", "\n").strip()


class TestRegenerateAndCache:
    """FE-0-003 Phase 2 — regeneration happens at most once per version."""

    def test_marker_advances_after_regeneration(self, client, tmp_path):
        """The staleness label's whole basis. Before Phase 2 the marker
        never moved, so exports read '(stale)' forever — including right
        after serving freshly regenerated content."""
        job, doc = _seed(tmp_path)
        doc.version += 1

        assert job.result.markdown_generated_at_version == 0
        client.get("/api/documents/prev1/markdown")
        assert job.result.markdown_generated_at_version == doc.version

    def test_marker_advances_for_docx(self, client, tmp_path):
        job, doc = _seed(tmp_path)
        job.result.docx_path = tmp_path / "prev1.docx"
        job.result.docx_path.write_bytes(b"pipeline-time docx")
        job.result.docx_generated_at_version = 0
        doc.version += 1

        resp = client.get("/api/documents/prev1/download/docx")
        assert resp.status_code == 200
        assert job.result.docx_generated_at_version == doc.version
        assert job.result.docx_path.read_bytes() != b"pipeline-time docx"

    def test_second_read_does_not_rebuild(self, client, tmp_path, monkeypatch):
        """The cache contract. Without it the 4s poller rebuilds forever."""
        _, doc = _seed(tmp_path)
        doc.version += 1

        first = client.get("/api/documents/prev1/markdown")
        assert first.status_code == 200
        assert REVIEWED_HEADING not in first.json()["content"]  # sanity: heading unchanged

        def _explode(*_a, **_k):
            raise AssertionError("second read must be served from cache")

        monkeypatch.setattr("src.markdown.markdown_builder.build_markdown", _explode)

        second = client.get("/api/documents/prev1/markdown")
        assert second.status_code == 200
        assert _norm(second.json()["content"]) == _norm(first.json()["content"])

    def test_repeated_polling_rebuilds_once(self, client, tmp_path, monkeypatch):
        """Simulates the workspace poller: many reads, one version."""
        import src.markdown.markdown_builder as builder

        _, doc = _seed(tmp_path)
        doc.version += 1

        calls = {"n": 0}
        real = builder.build_markdown

        def _counting(*a, **k):
            calls["n"] += 1
            return real(*a, **k)

        monkeypatch.setattr(builder, "build_markdown", _counting)

        for _ in range(5):
            assert client.get("/api/documents/prev1/markdown").status_code == 200

        assert calls["n"] == 1, f"rebuilt {calls['n']} times across 5 polls"

    def test_download_reuses_the_artifact_the_preview_built(
        self, client, tmp_path, monkeypatch
    ):
        """Preview and download share one cache, so a download after a
        preview costs nothing and cannot disagree with it."""
        _, doc = _seed(tmp_path)
        doc.version += 1

        preview = client.get("/api/documents/prev1/markdown").json()["content"]

        def _explode(*_a, **_k):
            raise AssertionError("download must reuse the preview's artifact")

        monkeypatch.setattr("src.markdown.markdown_builder.build_markdown", _explode)

        download = client.get("/api/documents/prev1/download/markdown")
        assert download.status_code == 200
        assert _norm(download.text) == _norm(preview)

    def test_regeneration_writes_through_to_the_canonical_file(self, client, tmp_path):
        """The approved decision: the Document is canonical and the
        pipeline-time file is its cache, overwritten in place."""
        job, doc = _seed(tmp_path)
        doc.headings[0].text = "Written Through"
        doc.version += 1

        client.get("/api/documents/prev1/markdown")

        on_disk = job.result.markdown_path.read_text(encoding="utf-8")
        assert "Written Through" in on_disk
        assert "Body text from the original run." not in on_disk

    def test_failed_regeneration_leaves_marker_and_file_untouched(
        self, client, tmp_path, monkeypatch
    ):
        """A failed rebuild must not claim success — otherwise the marker
        advances and the stale artifact is served as current forever."""
        job, doc = _seed(tmp_path)
        doc.version += 1

        def _boom(*_a, **_k):
            raise RuntimeError("builder exploded")

        monkeypatch.setattr("src.markdown.markdown_builder.build_markdown", _boom)

        resp = client.get("/api/documents/prev1/markdown")
        assert resp.status_code == 200
        assert resp.json()["content"] == PIPELINE_TIME_MARKDOWN
        assert job.result.markdown_generated_at_version == 0, "marker must not advance"
        assert job.result.markdown_path.read_text(encoding="utf-8") == PIPELINE_TIME_MARKDOWN

    def test_failed_regeneration_leaves_no_temp_file(self, client, tmp_path, monkeypatch):
        """D3: the old tempfile-per-download path leaked one file per call."""
        _, doc = _seed(tmp_path)
        doc.version += 1

        monkeypatch.setattr(
            "src.markdown.markdown_builder.build_markdown",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        client.get("/api/documents/prev1/markdown")

        assert list(tmp_path.glob("*.tmp")) == []

    def test_repeated_downloads_leak_no_temp_files(self, client, tmp_path):
        _, doc = _seed(tmp_path)
        doc.version += 1

        for _ in range(3):
            assert client.get("/api/documents/prev1/download/markdown").status_code == 200

        assert list(tmp_path.glob("*.tmp")) == []
