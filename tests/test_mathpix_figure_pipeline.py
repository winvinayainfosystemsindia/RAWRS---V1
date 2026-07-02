"""Integration tests for figure registration on the Mathpix path.

Covers: MathpixImportProvider.import_document(..., image_dir=...) end to
end (matched, unmatched figure block, orphan upload, no image_dir at all),
plus one full run_pipeline() run proving the uploaded MMD/image package is
never mutated and that document.images ends up authoritative
(import_source=MATHPIX) rather than PDF-derived.
"""

from __future__ import annotations

import hashlib
import textwrap
from pathlib import Path

import pytest

from src.mathpix.ingestor import MathpixImportProvider
from src.models.document import Document
from src.models.metadata import Metadata
from src.models.page import Page
from src.models.verification import ImportSource, VerificationStatus
from src.pipeline.phase1_pipeline import run_pipeline

SAMPLE_PDF_DIR = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"
A_DIGITAL_SAMPLE_PDF = SAMPLE_PDF_DIR / "5.Teachingas a profession_Calderhead.pdf"


def _make_document(page_count: int = 3) -> Document:
    return Document(
        source_pdf_path="test.pdf",
        metadata=Metadata(filename="test.pdf", page_count=page_count),
        pages=[Page(page_number=i + 1) for i in range(page_count)],
    )


def _png(path: Path, size=(40, 20)) -> Path:
    from PIL import Image as PILImage

    PILImage.new("RGB", size, color="blue").save(path)
    return path


class TestFigureRegistrationDuringImport:
    def test_matched_figure_appears_in_document_images(self, tmp_path: Path) -> None:
        mmd = tmp_path / "test.mmd"
        mmd.write_text(
            textwrap.dedent(
                r"""
                \section*{Results}
                \begin{figure}
                \includegraphics{images/chart.png}
                \caption{Figure 1. Quarterly results}
                \end{figure}
                """
            ),
            encoding="utf-8",
        )
        image_dir = tmp_path / "images"
        image_dir.mkdir()
        _png(image_dir / "chart.png")

        doc = MathpixImportProvider().import_document(
            _make_document(3), mmd_path=mmd, image_dir=image_dir
        )

        assert len(doc.images) == 1
        image = doc.images[0]
        assert image.import_source == ImportSource.MATHPIX
        assert image.uploaded_filename == "chart.png"
        assert image.figure.caption == "Figure 1. Quarterly results"

    def test_uploaded_image_with_no_matching_figure_block_is_still_registered(self, tmp_path: Path) -> None:
        mmd = tmp_path / "test.mmd"
        mmd.write_text(r"\section*{Results}" + "\nSome text with no figure block.\n", encoding="utf-8")
        image_dir = tmp_path / "images"
        image_dir.mkdir()
        _png(image_dir / "unreferenced.png")

        doc = MathpixImportProvider().import_document(
            _make_document(3), mmd_path=mmd, image_dir=image_dir
        )

        assert len(doc.images) == 1
        assert doc.images[0].verification_status == VerificationStatus.ORPHAN
        orphan_findings = [f for f in doc.verification_findings if f.kind == "orphan"]
        assert len(orphan_findings) == 1

    def test_figure_block_with_no_matching_upload_produces_finding_but_no_fake_image(self, tmp_path: Path) -> None:
        mmd = tmp_path / "test.mmd"
        mmd.write_text(
            textwrap.dedent(
                r"""
                \begin{figure}
                \includegraphics{images/missing.png}
                \caption{Figure 1. Missing}
                \end{figure}
                """
            ),
            encoding="utf-8",
        )
        image_dir = tmp_path / "images"
        image_dir.mkdir()  # empty — nothing uploaded

        doc = MathpixImportProvider().import_document(
            _make_document(1), mmd_path=mmd, image_dir=image_dir
        )

        assert doc.images == []
        missing_findings = [f for f in doc.verification_findings if f.kind == "missing_from_package"]
        assert len(missing_findings) == 1

    def test_no_image_dir_registers_no_figures_backward_compatible(self, tmp_path: Path) -> None:
        mmd = tmp_path / "test.mmd"
        mmd.write_text(
            textwrap.dedent(
                r"""
                \begin{figure}
                \includegraphics{images/chart.png}
                \caption{Figure 1}
                \end{figure}
                """
            ),
            encoding="utf-8",
        )

        doc = MathpixImportProvider().import_document(_make_document(1), mmd_path=mmd)

        assert doc.images == []
        assert doc.verification_findings == []


class TestFullPipelineImmutabilityAndAuthority:
    def test_uploaded_mmd_and_images_are_byte_for_byte_unchanged_after_run(self, tmp_path: Path) -> None:
        mmd_path = tmp_path / "package.mmd"
        mmd_path.write_text(
            textwrap.dedent(
                r"""
                \title{Test Document}
                \section*{Results}
                \begin{figure}
                \includegraphics{images/chart.png}
                \caption{Figure 1. Quarterly results}
                \end{figure}
                Body text follows the figure.
                """
            ),
            encoding="utf-8",
        )
        image_dir = tmp_path / "uploaded_images"
        image_dir.mkdir()
        image_path = _png(image_dir / "chart.png")

        mmd_hash_before = hashlib.sha256(mmd_path.read_bytes()).hexdigest()
        image_hash_before = hashlib.sha256(image_path.read_bytes()).hexdigest()

        run_pipeline(
            A_DIGITAL_SAMPLE_PDF,
            output_root=tmp_path / "out",
            enable_ocr=False,
            mmd_path=mmd_path,
            image_dir=image_dir,
        )

        assert hashlib.sha256(mmd_path.read_bytes()).hexdigest() == mmd_hash_before
        assert hashlib.sha256(image_path.read_bytes()).hexdigest() == image_hash_before

    def test_mathpix_package_images_are_authoritative_over_pdf_extraction(self, tmp_path: Path) -> None:
        mmd_path = tmp_path / "package.mmd"
        mmd_path.write_text(
            textwrap.dedent(
                r"""
                \title{Test Document}
                \begin{figure}
                \includegraphics{images/chart.png}
                \caption{Figure 1. Quarterly results}
                \end{figure}
                """
            ),
            encoding="utf-8",
        )
        image_dir = tmp_path / "uploaded_images"
        image_dir.mkdir()
        _png(image_dir / "chart.png")

        result = run_pipeline(
            A_DIGITAL_SAMPLE_PDF,
            output_root=tmp_path / "out",
            enable_ocr=False,
            mmd_path=mmd_path,
            image_dir=image_dir,
        )

        assert result.success
        document = result.document
        assert len(document.images) == 1
        assert document.images[0].import_source == ImportSource.MATHPIX
        assert document.images[0].uploaded_filename == "chart.png"
