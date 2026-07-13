"""Tests for src/verification/footnotes.py::FootnoteVerifier (M-3.1) — the
fifth asset type registered with the cross-source verification engine, and
the mechanism that resolves src/mathpix/ingestor.py's
anchor_page_number=1 placeholder into a real, PDF-confirmed page.
"""

import json

from src.models.correction import CorrectionRecord, CorrectionStatus
from src.models.footnote import Footnote, NoteType
from src.verification.engine import engine
from src.verification.footnotes import FootnoteVerifier


def _canonical(number: int = 1, page: int = 1, body: str = "Smith argues the opposite.") -> Footnote:
    """A Mathpix-sourced footnote carrying the real
    _p2footnote_to_footnote() placeholder (anchor_page_number=1) unless
    overridden — matches production shape exactly."""
    return Footnote(
        note_type=NoteType.FOOTNOTE,
        number=number,
        marker=str(number),
        anchor_page_number=page,
        anchor_text=str(number),
        body=body,
        body_page_number=page,
        body_source_text=f"[{number}] {body}",
        footnote_id=f"mathpix-{number}",
        source="mathpix",
    )


def _pdf_candidate(number: int = 1, page: int = 1, body: str = "Smith argues the opposite.") -> Footnote:
    """An independently PDF-detected footnote (src/footnotes/footnote_detector.py
    shape) — the real page, unlike the Mathpix placeholder."""
    return Footnote(
        note_type=NoteType.FOOTNOTE,
        number=number,
        marker=str(number),
        anchor_page_number=page,
        anchor_text=f"...text{number}",
        body=body,
        body_page_number=page,
        body_source_text=f"{number}. {body}",
        footnote_id=f"fn-{number}",
        source="rawrs",
    )


class TestFootnoteVerifierClassify:
    def test_matching_page_confirms_silently(self):
        canonical = _canonical(number=1, page=5)
        pdf_note = _pdf_candidate(number=1, page=5)
        findings = engine.run_pdf_verification("footnote", [canonical], [pdf_note])
        assert findings == []

    def test_placeholder_page_1_repaired_to_real_pdf_page(self):
        """The actual bug this milestone exists to fix: Mathpix's
        anchor_page_number=1 placeholder disagrees with the PDF's real
        page (5) -> REPAIR, proposing the PDF page."""
        canonical = _canonical(number=1, page=1)  # the literal placeholder value
        pdf_note = _pdf_candidate(number=1, page=5)
        findings = engine.run_pdf_verification("footnote", [canonical], [pdf_note])

        assert len(findings) == 1
        finding = findings[0]
        assert finding.kind == "wrong_page"
        assert finding.object_id == "mathpix-1"
        proposed = json.loads(finding.proposed_value)
        assert proposed["anchor_page_number"] == 5
        original = json.loads(finding.original_value)
        assert original["anchor_page_number"] == 1

    def test_mathpix_only_footnote_is_unconfirmed_not_removed(self):
        canonical = _canonical(number=1, page=3)
        findings = engine.run_pdf_verification("footnote", [canonical], [])
        assert len(findings) == 1
        assert findings[0].kind == "unconfirmed"
        assert findings[0].object_id == "mathpix-1"

    def test_pdf_only_footnote_recovered_as_missing_from_package(self):
        pdf_note = _pdf_candidate(number=2, page=7, body="A completely different note Mathpix missed.")
        findings = engine.run_pdf_verification("footnote", [], [pdf_note])
        assert len(findings) == 1
        finding = findings[0]
        assert finding.kind == "missing_from_package"
        assert finding.object_id is None
        recovered = json.loads(finding.proposed_value)
        assert recovered["anchor_page_number"] == 7
        assert recovered["number"] == 2

    def test_body_similarity_matches_despite_ocr_noise(self):
        """A Mathpix/PDF body-text difference (OCR noise) should still
        match by similarity rather than falsely recovering a duplicate."""
        canonical = _canonical(number=3, page=2, body="The theory was first proposed by Kuhn in 1962.")
        pdf_note = _pdf_candidate(number=3, page=2, body="The theory was first propsed by Kuhn in 1962")
        findings = engine.run_pdf_verification("footnote", [canonical], [pdf_note])
        assert findings == []  # same page, matched by similarity -> confirmed silently


class TestFootnoteVerifierApply:
    def test_accepting_wrong_page_updates_anchor_fields(self):
        verifier = FootnoteVerifier()
        footnote = _canonical(number=1, page=1)
        document = _DocumentDouble(footnotes=[footnote])
        correction = CorrectionRecord(
            object_type="footnote",
            object_id="mathpix-1",
            field="wrong_page",
            original_value=json.dumps({"anchor_page_number": 1, "anchor_text": "1", "anchor_offset": None}),
            proposed_value=json.dumps({"anchor_page_number": 5, "anchor_text": "...text1", "anchor_offset": None}),
            status=CorrectionStatus.ACCEPTED,
        )
        verifier.apply(document, correction)
        assert footnote.anchor_page_number == 5
        assert footnote.anchor_text == "...text1"

    def test_reverting_wrong_page_restores_original_page(self):
        verifier = FootnoteVerifier()
        footnote = _canonical(number=1, page=1)
        document = _DocumentDouble(footnotes=[footnote])
        correction = CorrectionRecord(
            object_type="footnote",
            object_id="mathpix-1",
            field="wrong_page",
            original_value=json.dumps({"anchor_page_number": 1, "anchor_text": "1", "anchor_offset": None}),
            proposed_value=json.dumps({"anchor_page_number": 5, "anchor_text": "...text1", "anchor_offset": None}),
            status=CorrectionStatus.ACCEPTED,
        )
        verifier.apply(document, correction)
        assert footnote.anchor_page_number == 5

        verifier.revert(document, correction)
        assert footnote.anchor_page_number == 1
        assert footnote.anchor_text == "1"

    def test_accepting_missing_from_package_recovers_a_new_footnote(self):
        verifier = FootnoteVerifier()
        document = _DocumentDouble(footnotes=[])
        recovered_payload = json.dumps(
            {
                "note_type": "footnote",
                "number": 2,
                "marker": "2",
                "anchor_page_number": 7,
                "anchor_text": "...text2",
                "anchor_offset": None,
                "body": "A note Mathpix missed.",
                "body_page_number": 7,
                "body_source_text": "2. A note Mathpix missed.",
            }
        )
        correction = CorrectionRecord(
            object_type="footnote",
            object_id=None,
            field="missing_from_package",
            original_value="",
            proposed_value=recovered_payload,
            status=CorrectionStatus.ACCEPTED,
        )
        verifier.apply(document, correction)
        assert len(document.footnotes) == 1
        assert document.footnotes[0].anchor_page_number == 7
        assert document.footnotes[0].source == "rawrs_recovery"

    def test_unconfirmed_apply_is_a_no_op(self):
        verifier = FootnoteVerifier()
        footnote = _canonical(number=1, page=3)
        document = _DocumentDouble(footnotes=[footnote])
        correction = CorrectionRecord(
            object_type="footnote",
            object_id="mathpix-1",
            field="unconfirmed",
            original_value="",
            proposed_value="",
            status=CorrectionStatus.ACCEPTED,
        )
        verifier.apply(document, correction)
        assert footnote.anchor_page_number == 3  # untouched


class TestFootnoteRegisteredWithEngine:
    def test_footnote_is_a_registered_asset_type(self):
        # Importing src.verification.footnotes registers it at module load
        # time (see _register() at the bottom of that file) — the same
        # pattern every other asset type (heading/list/figure/callout) uses.
        assert "footnote" in engine._verifiers


class _DocumentDouble:
    """Minimal stand-in for Document — apply()/revert() only touch
    .footnotes, so a full pydantic Document isn't needed (same lightweight
    test-double pattern test_callout_verifier.py's TestCalloutVerifierApply
    uses via the real Document, simplified here since Footnote has no
    cross-object integrity check the way Callout.heading_id does)."""

    def __init__(self, footnotes):
        self.footnotes = footnotes
