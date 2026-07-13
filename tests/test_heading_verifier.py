"""Tests for src/verification/headings.py::HeadingVerifier and
src/headings/heading_detector.py::detect_headings_from_pdf()."""

import json
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


# ===========================================================================
# FEATURE_019: multi-signal EvidenceBundle
# ===========================================================================


class TestRunningHeaderRecurrenceSignal:
    def test_unique_text_is_not_flagged(self) -> None:
        verifier = HeadingVerifier()
        canonical = _heading("Introduction", page=1)
        result = verifier.build_pdf_matcher().match([canonical], [])
        findings = verifier.classify(result)
        assert findings[0].kind == "unconfirmed"
        # Fused confidence now reports a real number (running-header signal
        # always runs, even with zero PDF candidates) instead of None.
        assert findings[0].confidence is not None

    def test_text_recurring_across_pages_proposes_removal(self) -> None:
        """A heading whose exact text repeats across several pages (the
        running-header/footer signature) gets a likely_running_header
        REMOVE proposal — closes the forensic-audit DEF-10 gap: this guard
        previously only ran inside heading_detector.py's PDF-native
        classification loop, never for Mathpix-sourced headings."""
        verifier = HeadingVerifier()
        recurring = [_heading("PROFESSIONAL IDENTITY", page=p, order=p) for p in range(1, 5)]
        result = verifier.build_pdf_matcher().match(recurring, [])
        findings = verifier.classify(result)
        kinds = {f.kind for f in findings}
        assert kinds == {"likely_running_header"}
        assert len(findings) == 4
        for f in findings:
            assert f.confidence is not None and f.confidence < 0.5

    def test_accepting_removal_deletes_the_heading(self) -> None:
        verifier = HeadingVerifier()
        heading = _heading("Running Header", page=1)
        correction = CorrectionRecord(
            object_type="heading",
            object_id=heading.id,
            field="likely_running_header",
            original_value="Running Header",
            proposed_value="",
        )

        class _Doc:
            headings = [heading]

        document = _Doc()
        verifier.apply(document, correction)
        assert document.headings == []

    def test_proposed_value_carries_full_restore_payload(self) -> None:
        """classify() must encode enough to reconstruct the Heading after
        apply() deletes it — not just leave proposed_value empty."""
        verifier = HeadingVerifier()
        recurring = [_heading("PROFESSIONAL IDENTITY", level=HeadingLevel.H3, page=p, order=p) for p in range(1, 5)]
        result = verifier.build_pdf_matcher().match(recurring, [])
        finding = verifier.classify(result)[0]
        assert finding.proposed_value
        payload = json.loads(finding.proposed_value)
        assert payload == {"level": 3, "text": "PROFESSIONAL IDENTITY", "page_number": 1}

    def test_revert_restores_the_exact_removed_heading(self) -> None:
        """FEATURE_020 Part 1 — the revert() override, not the base
        class's swap-and-replay default (which would have nothing left
        to swap, since apply() already deleted the object)."""
        verifier = HeadingVerifier()
        recurring = [_heading("PROFESSIONAL IDENTITY", level=HeadingLevel.H2, page=p, order=p) for p in range(1, 5)]
        result = verifier.build_pdf_matcher().match(recurring, [])
        finding = verifier.classify(result)[0]

        class _Doc:
            headings = list(recurring)

        document = _Doc()
        correction = CorrectionRecord(
            object_type="heading",
            object_id=finding.object_id,
            field=finding.kind,
            original_value=finding.original_value,
            proposed_value=finding.proposed_value,
        )

        verifier.apply(document, correction)
        assert len(document.headings) == 3

        verifier.revert(document, correction)
        assert len(document.headings) == 4
        restored = next(h for h in document.headings if h.source == "rawrs_recovery")
        assert restored.text == "PROFESSIONAL IDENTITY"
        assert restored.level == HeadingLevel.H2
        assert restored.page_number == 1

    def test_engine_revert_correction_uses_the_override_not_the_default(self) -> None:
        engine = CrossSourceVerificationEngine()
        engine.register(HeadingVerifier())
        heading = _heading("Running Header", page=1, order=0)

        class _Doc:
            headings = [heading]

        document = _Doc()
        verifier = HeadingVerifier()
        result = verifier.build_pdf_matcher().match([heading], [])
        # Force a low running-header score directly via classify() would
        # need 2+ pages; simplest reliable trigger here is to build the
        # correction the same shape classify() would for a flagged heading.
        correction = CorrectionRecord(
            object_type="heading",
            object_id=heading.id,
            field="likely_running_header",
            original_value=heading.text,
            proposed_value=json.dumps({"level": int(heading.level), "text": heading.text, "page_number": heading.page_number}),
            status=CorrectionStatus.ACCEPTED,
        )
        engine.apply_correction(document, correction)
        assert document.headings == []
        engine.revert_correction(document, correction)
        assert len(document.headings) == 1
        assert document.headings[0].source == "rawrs_recovery"


class TestMultiSignalEvidenceWithRealPdf:
    """Typography/whitespace signals need a real PDF text layer — built
    via the same _build_pdf() helper TestDetectHeadingsFromPdf already
    uses, so classify() is exercised with pdf_path in context exactly as
    src/pipeline/phase1_pipeline.py's Mathpix branch calls it."""

    def test_matched_pair_gets_typography_and_whitespace_signals(self, tmp_path: Path) -> None:
        pdf_path = _build_pdf(
            tmp_path,
            [
                ("A Bold Section Heading", "hebo", 18),
                ("Body text follows here, at normal size.", "helv", 10),
                ("More ordinary body text on this page.", "helv", 10),
            ],
        )
        verifier = HeadingVerifier()
        canonical = _heading("A Bold Section Heading", level=HeadingLevel.H2, page=1)
        pdf_heading = _heading("A Bold Section Heading", level=HeadingLevel.H2, page=1)
        result = verifier.build_pdf_matcher().match([canonical], [pdf_heading])
        findings = verifier.classify(result, pdf_path=pdf_path)
        # Agreement + strong typography/whitespace evidence -> VERIFIED, no findings.
        assert findings == []
        assert canonical.verification_status == VerificationStatus.VERIFIED
        assert canonical.confidence is not None and canonical.confidence > 0.5

    def test_no_pdf_path_falls_back_to_pdf_match_and_recurrence_only(self) -> None:
        """When no pdf_path is supplied (e.g. a caller that hasn't been
        updated), classify() must not raise — typography/whitespace are
        simply skipped, matching the pre-FEATURE_019 behavior's signal
        coverage for that case."""
        verifier = HeadingVerifier()
        canonical = _heading("Introduction", level=HeadingLevel.H2)
        pdf_heading = _heading("Introduction", level=HeadingLevel.H2)
        result = verifier.build_pdf_matcher().match([canonical], [pdf_heading])
        findings = verifier.classify(result)  # no pdf_path kwarg
        assert findings == []
        assert canonical.verification_status == VerificationStatus.VERIFIED


class TestTargetedOcrEvidence:
    """M-5.1 — targeted OCR as one more EvidenceSignal, evidence of last
    resort. The low-confidence PDF below deliberately has weak typography
    (heading rendered at the same size as body text) and a weak PDF match
    (dissimilar text, far-apart pages -> positional_fallback), so the
    fused bundle lands below _OCR_AMBIGUOUS_CONFIDENCE_THRESHOLD on its
    own — exercising the real gate, not a mocked confidence value."""

    def _low_confidence_scenario(self, tmp_path: Path):
        pdf_path = _build_pdf(
            tmp_path,
            [
                ("Xyzzy Foo Bar", "helv", 10),
                ("Some other filler body text on this page.", "helv", 10),
            ],
        )
        verifier = HeadingVerifier()
        canonical = _heading("Xyzzy Foo Bar", page=1)
        pdf_heading = _heading("Something Totally Unrelated Text", page=5)
        result = verifier.build_pdf_matcher().match([canonical], [pdf_heading])
        return verifier, canonical, result, pdf_path

    def test_high_confidence_candidate_never_invokes_ocr(self, tmp_path: Path, monkeypatch) -> None:
        def _fail_if_called(*_args, **_kwargs):
            raise AssertionError("ocr_region must not be called for an already-confident candidate")

        monkeypatch.setattr("src.verification.headings.ocr_region", _fail_if_called)

        pdf_path = _build_pdf(
            tmp_path,
            [
                ("A Bold Section Heading", "hebo", 18),
                ("Body text follows here, at normal size.", "helv", 10),
                ("More ordinary body text on this page.", "helv", 10),
            ],
        )
        verifier = HeadingVerifier()
        canonical = _heading("A Bold Section Heading", page=1)
        pdf_heading = _heading("A Bold Section Heading", page=1)
        result = verifier.build_pdf_matcher().match([canonical], [pdf_heading])
        verifier.classify(result, pdf_path=pdf_path)  # would raise if ocr_region were called
        assert canonical.confidence is not None and canonical.confidence > 0.5

    def test_low_confidence_candidate_invokes_ocr(self, tmp_path: Path, monkeypatch) -> None:
        calls = []
        monkeypatch.setattr(
            "src.verification.headings.ocr_region",
            lambda *args, **kwargs: (calls.append(args) or "Xyzzy Foo Bar"),
        )
        verifier, canonical, result, pdf_path = self._low_confidence_scenario(tmp_path)
        verifier.classify(result, pdf_path=pdf_path)
        assert len(calls) == 1

    def test_ocr_agreement_raises_confidence_above_baseline(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.verification.headings.ocr_region",
            lambda *args, **kwargs: "Xyzzy Foo Bar",  # exact match
        )
        verifier, canonical, result, pdf_path = self._low_confidence_scenario(tmp_path)
        verifier.classify(result, pdf_path=pdf_path)
        with_ocr = canonical.confidence

        monkeypatch.setattr("src.verification.headings.ocr_region", lambda *a, **k: "")
        verifier2, canonical2, result2, _ = self._low_confidence_scenario(tmp_path)
        verifier2.classify(result2, pdf_path=pdf_path)
        without_agreement = canonical2.confidence

        assert with_ocr is not None and without_agreement is not None
        assert with_ocr > without_agreement

    def test_ocr_disagreement_lowers_confidence(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.verification.headings.ocr_region",
            lambda *args, **kwargs: "Completely Different Recognized Text",
        )
        verifier, canonical, result, pdf_path = self._low_confidence_scenario(tmp_path)
        verifier.classify(result, pdf_path=pdf_path)
        assert canonical.confidence is not None and canonical.confidence < 0.5

    def test_ocr_failure_handled_gracefully(self, tmp_path: Path, monkeypatch) -> None:
        from src.ocr.targeted import TargetedOCRError

        def _raise(*_args, **_kwargs):
            raise TargetedOCRError("simulated OCR failure")

        monkeypatch.setattr("src.verification.headings.ocr_region", _raise)
        verifier, canonical, result, pdf_path = self._low_confidence_scenario(tmp_path)
        findings = verifier.classify(result, pdf_path=pdf_path)  # must not raise
        assert canonical.confidence is not None

    def test_existing_behavior_unchanged_when_ocr_signal_unavailable(self, tmp_path: Path) -> None:
        """No monkeypatch at all — real ocr_region import stays wired,
        but classify() never reaches it unless the bundle is already
        ambiguous, so a normal high-confidence match behaves exactly as
        it did before M-5.1."""
        pdf_path = _build_pdf(
            tmp_path,
            [
                ("A Bold Section Heading", "hebo", 18),
                ("Body text follows here, at normal size.", "helv", 10),
                ("More ordinary body text on this page.", "helv", 10),
            ],
        )
        verifier = HeadingVerifier()
        canonical = _heading("A Bold Section Heading", page=1)
        pdf_heading = _heading("A Bold Section Heading", page=1)
        result = verifier.build_pdf_matcher().match([canonical], [pdf_heading])
        findings = verifier.classify(result, pdf_path=pdf_path)
        assert findings == []
        assert canonical.verification_status == VerificationStatus.VERIFIED
