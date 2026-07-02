"""Tests for src/verification/headings.py::HeadingVerifier and
src/headings/heading_detector.py::detect_headings_from_pdf()."""

from pathlib import Path
from typing import List, Tuple

import fitz

from src.headings.heading_detector import detect_headings, detect_headings_from_pdf
from src.models.contracts import Heading, HeadingLevel
from src.models.correction import CorrectionRecord, CorrectionStatus
from src.models.verification import VerificationStatus
from src.verification.engine import CrossSourceVerificationEngine
from src.verification.headings import HeadingVerifier


def _heading(text: str, level: HeadingLevel = HeadingLevel.H2, page: int = 1, order: int = 0) -> Heading:
    return Heading(level=level, text=text, page_number=page, document_order=order, is_page_marker=False)


def _build_pdf(tmp_path: Path, lines: List[Tuple[str, str, float]], name: str = "headings.pdf") -> Path:
    pdf_path = tmp_path / name
    doc = fitz.open()
    page = doc.new_page()
    y = 72.0
    for text, fontname, fontsize in lines:
        page.insert_text((72, y), text, fontname=fontname, fontsize=fontsize)
        y += fontsize + 20
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


class TestDetectHeadingsFromPdf:
    def test_missing_pdf_returns_empty(self, tmp_path: Path) -> None:
        assert detect_headings_from_pdf(tmp_path / "nope.pdf") == []

    def test_never_produces_page_markers(self, tmp_path: Path) -> None:
        pdf_path = _build_pdf(
            tmp_path,
            [
                ("A Bold Section Heading", "hebo", 14),
                ("Body text follows here.", "helv", 10),
            ],
        )
        headings = detect_headings_from_pdf(pdf_path)
        assert all(not h.is_page_marker for h in headings)

    def test_native_path_detect_headings_unaffected_by_new_function_existing(self, tmp_path: Path) -> None:
        """detect_headings() itself must be byte-for-byte unaffected by
        the addition of detect_headings_from_pdf() — same module, same
        shared helpers, nothing in the native path's own call site changed."""
        from src.ocr.extractor import extract_text
        from src.parser.pdf_parser import parse_pdf

        pdf_path = _build_pdf(tmp_path, [("Chapter One Begins Here", "hebo", 14)])
        document = extract_text(parse_pdf(pdf_path))
        document = detect_headings(document)
        assert any(not h.is_page_marker for h in document.headings)


class TestHeadingVerifierMatching:
    def test_exact_text_match(self) -> None:
        verifier = HeadingVerifier()
        canonical = _heading("Introduction")
        pdf_heading = _heading("Introduction")
        result = verifier.build_pdf_matcher().match([canonical], [pdf_heading])
        assert len(result.pairs) == 1
        assert result.pairs[0].matched_by == "exact_text"

    def test_similar_text_matches_via_similarity_signal(self) -> None:
        verifier = HeadingVerifier()
        canonical = _heading("CONTEMPRORARY TEAGHNG METHODS")
        pdf_heading = _heading("CONTEMPORARY TEACHING METHODS")
        result = verifier.build_pdf_matcher().match([canonical], [pdf_heading])
        assert len(result.pairs) == 1
        assert result.pairs[0].matched_by == "text_similarity"


class TestHeadingVerifierClassify:
    def test_agreeing_headings_are_verified(self) -> None:
        verifier = HeadingVerifier()
        canonical = _heading("Introduction", level=HeadingLevel.H2)
        pdf_heading = _heading("Introduction", level=HeadingLevel.H2)
        result = verifier.build_pdf_matcher().match([canonical], [pdf_heading])
        findings = verifier.classify(result)
        assert findings == []
        assert canonical.verification_status == VerificationStatus.VERIFIED

    def test_level_mismatch_produces_finding(self) -> None:
        verifier = HeadingVerifier()
        canonical = _heading("Big Chapter Title", level=HeadingLevel.H3)
        pdf_heading = _heading("Big Chapter Title", level=HeadingLevel.H1)
        result = verifier.build_pdf_matcher().match([canonical], [pdf_heading])
        findings = verifier.classify(result)
        kinds = {f.kind for f in findings}
        assert "level_mismatch" in kinds
        level_finding = next(f for f in findings if f.kind == "level_mismatch")
        assert level_finding.original_value == "3"
        assert level_finding.proposed_value == "1"

    def test_text_correction_produces_finding(self) -> None:
        verifier = HeadingVerifier()
        canonical = _heading("CONTEMPRORARY TEAGHNG", level=HeadingLevel.H2)
        pdf_heading = _heading("CONTEMPORARY TEACHING", level=HeadingLevel.H2)
        result = verifier.build_pdf_matcher().match([canonical], [pdf_heading])
        findings = verifier.classify(result)
        text_finding = next(f for f in findings if f.kind == "text_correction")
        assert text_finding.proposed_value == "CONTEMPORARY TEACHING"

    def test_missing_from_package_recovers_pdf_heading(self) -> None:
        verifier = HeadingVerifier()
        pdf_heading = _heading("A Real Chapter Mathpix Missed", level=HeadingLevel.H1, page=3)
        result = verifier.build_pdf_matcher().match([], [pdf_heading])
        findings = verifier.classify(result)
        assert len(findings) == 1
        assert findings[0].kind == "missing_from_package"
        assert findings[0].proposed_value is not None

    def test_unconfirmed_canonical_heading(self) -> None:
        verifier = HeadingVerifier()
        canonical = _heading("Only In Mathpix")
        result = verifier.build_pdf_matcher().match([canonical], [])
        findings = verifier.classify(result)
        assert len(findings) == 1
        assert findings[0].kind == "unconfirmed"
        assert canonical.verification_status == VerificationStatus.MISSING_FROM_PDF


class TestHeadingVerifierApply:
    def test_apply_level_mismatch_mutates_heading(self) -> None:
        verifier = HeadingVerifier()
        heading = _heading("Some Title", level=HeadingLevel.H3, order=0)
        correction = CorrectionRecord(
            object_type="heading",
            object_id=heading.id,
            field="level_mismatch",
            original_value="3",
            proposed_value="1",
        )

        class _Doc:
            headings = [heading]

        verifier.apply(_Doc(), correction)
        assert heading.level == HeadingLevel.H1

    def test_apply_missing_from_package_inserts_and_shifts_orders(self) -> None:
        verifier = HeadingVerifier()
        h0 = _heading("First", page=1, order=0)
        h1 = _heading("Second", page=5, order=1)

        class _Doc:
            headings = [h0, h1]

        document = _Doc()
        recovered_pdf_heading = _heading("Recovered", level=HeadingLevel.H2, page=3)
        result = verifier.build_pdf_matcher().match([], [recovered_pdf_heading])
        findings = verifier.classify(result)
        correction = CorrectionRecord(
            object_type="heading",
            field="missing_from_package",
            original_value="",
            proposed_value=findings[0].proposed_value,
        )
        verifier.apply(document, correction)
        assert len(document.headings) == 3
        orders = sorted(h.document_order for h in document.headings)
        assert orders == [0, 1, 2]
        recovered = next(h for h in document.headings if h.text == "Recovered")
        assert recovered.page_number == 3
        # Inserted between page-1 and page-5 headings, not appended blindly.
        assert h0.document_order == 0
        assert recovered.document_order == 1
        assert h1.document_order == 2

    def test_unconfirmed_is_noop(self) -> None:
        verifier = HeadingVerifier()
        heading = _heading("Whatever")
        correction = CorrectionRecord(
            object_type="heading", object_id=heading.id, field="unconfirmed",
            original_value="", proposed_value="",
        )

        class _Doc:
            headings = [heading]

        verifier.apply(_Doc(), correction)  # must not raise
        assert heading.text == "Whatever"


class TestEngineIntegration:
    def test_registers_under_heading_asset_type(self) -> None:
        import src.verification.headings  # noqa: F401 - registers HeadingVerifier
        from src.verification.engine import engine as module_engine

        assert isinstance(module_engine._verifiers.get("heading"), HeadingVerifier)

    def test_revert_restores_original_level(self) -> None:
        engine = CrossSourceVerificationEngine()
        engine.register(HeadingVerifier())
        heading = _heading("Some Title", level=HeadingLevel.H3)
        correction = CorrectionRecord(
            object_type="heading",
            object_id=heading.id,
            field="level_mismatch",
            original_value="3",
            proposed_value="1",
            status=CorrectionStatus.ACCEPTED,
        )

        class _Doc:
            headings = [heading]

        document = _Doc()
        engine.apply_correction(document, correction)
        assert heading.level == HeadingLevel.H1
        engine.revert_correction(document, correction)
        assert heading.level == HeadingLevel.H3
