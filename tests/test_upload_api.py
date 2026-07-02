"""Tests for POST /api/documents (src/api/routes.py, src/api/jobs.py) —
the Mathpix package upload endpoint: PDF + optional MMD + optional image
files, all saved unmodified to disk so the pipeline's Mathpix import path
(src/mathpix/ingestor.py -> src/verification/figures.py) can register
every uploaded image as a figure.

start_job() is monkeypatched to a no-op in every test here so the actual
pipeline never runs in a background thread — these tests only cover the
upload/save/job-record contract, not end-to-end processing (covered by
tests/test_mathpix_figure_pipeline.py and tests/test_pipeline.py).
"""

from __future__ import annotations

import io

import pytest


@pytest.fixture(autouse=True)
def no_op_start_job(monkeypatch):
    monkeypatch.setattr("src.api.routes.start_job", lambda job_id, enable_ocr=True: None)


@pytest.fixture(autouse=True)
def cleanup_created_jobs():
    """Every test here creates a real Job in the shared in-memory store via
    the upload endpoint; remove it afterward so state doesn't leak across
    the test session (mirrors test_image_review_api.py's synthetic_job
    fixture teardown)."""
    from src.api.jobs import _jobs, _lock

    before = set(_jobs)
    yield
    with _lock:
        for job_id in set(_jobs) - before:
            _jobs.pop(job_id, None)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from src.api.main import app
    return TestClient(app)


def _minimal_pdf_bytes() -> bytes:
    import fitz

    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def _png_bytes() -> bytes:
    from PIL import Image as PILImage

    buf = io.BytesIO()
    PILImage.new("RGB", (10, 10), color="red").save(buf, format="PNG")
    return buf.getvalue()


class TestUploadWithoutImages:
    def test_pdf_only_upload_leaves_image_dir_unset(self, client) -> None:
        from src.api.jobs import get_job

        response = client.post(
            "/api/documents",
            files={"file": ("test.pdf", _minimal_pdf_bytes(), "application/pdf")},
        )
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        job = get_job(job_id)
        assert job is not None
        assert job.image_dir is None
        assert job.mmd_path is None


class TestUploadWithImages:
    def test_uploaded_images_saved_unmodified_under_job_image_dir(self, client) -> None:
        from src.api.jobs import get_job

        img_bytes = _png_bytes()
        response = client.post(
            "/api/documents",
            files=[
                ("file", ("test.pdf", _minimal_pdf_bytes(), "application/pdf")),
                ("mmd_file", ("test.mmd", b"\\section*{Intro}", "text/plain")),
                ("image_files", ("chart.png", img_bytes, "image/png")),
                ("image_files", ("figure2.jpg", img_bytes, "image/jpeg")),
            ],
        )
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        job = get_job(job_id)
        assert job.mmd_path is not None
        assert job.mmd_path.read_bytes() == b"\\section*{Intro}"
        assert job.image_dir is not None
        assert job.image_dir.is_dir()

        saved_names = {p.name for p in job.image_dir.iterdir()}
        assert saved_names == {"chart.png", "figure2.jpg"}
        assert (job.image_dir / "chart.png").read_bytes() == img_bytes

    def test_non_image_file_in_image_files_is_rejected(self, client) -> None:
        response = client.post(
            "/api/documents",
            files=[
                ("file", ("test.pdf", _minimal_pdf_bytes(), "application/pdf")),
                ("image_files", ("notes.txt", b"hello", "text/plain")),
            ],
        )
        assert response.status_code == 400

    def test_non_pdf_primary_file_is_rejected(self, client) -> None:
        response = client.post(
            "/api/documents",
            files={"file": ("test.txt", b"not a pdf", "text/plain")},
        )
        assert response.status_code == 400
