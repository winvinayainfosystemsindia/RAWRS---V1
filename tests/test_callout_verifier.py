"""Tests for src/models/callout.py, src/mathpix/mmd_parser.py's
classify_callout_type(), and src/verification/callouts.py::CalloutVerifier
(FEATURE_019) — the fourth registered asset type, proving the Evidence
Fusion Engine generalizes beyond Heading/List/Table.
"""

from src.mathpix.mmd_parser import classify_callout_type
from src.models.contracts import Callout, Document, Heading, HeadingLevel, Metadata
from src.models.correction import CorrectionRecord, CorrectionStatus
from src.models.verification import VerificationStatus
from src.verification.callouts import CalloutVerifier
from src.verification.engine import engine


class TestClassifyCalloutType:
    def test_numbered_case_study(self):
        assert classify_callout_type("Case study 11.2") == "case_study"

    def test_case_study_with_name(self):
        assert classify_callout_type("Case study 10.1 Kate") == "case_study"

    def test_thinking_point(self):
        assert classify_callout_type("Thinking point 10.1") == "thinking_point"

    def test_key_ideas(self):
        assert classify_callout_type("Key ideas explored in this chapter are:") == "key_ideas"

    def test_summary(self):
        assert classify_callout_type("Summary") == "summary"

    def test_activity(self):
        assert classify_callout_type("Activity 3.1") == "activity"

    def test_ordinary_heading_is_not_a_callout(self):
        assert classify_callout_type("Exploring professional identity") is None

    def test_case_insensitive(self):
        assert classify_callout_type("CASE STUDY 5.1") == "case_study"


def _doc_with_callout(label: str, callout_type: str, heading_intact: bool = True) -> Document:
    doc = Document(source_pdf_path="x.pdf", metadata=Metadata(filename="x.pdf"))
    heading = Heading(level=HeadingLevel.H2, text=label, page_number=1, document_order=0)
    doc.headings = [heading] if heading_intact else []
    doc.callouts = [
        Callout(
            callout_type=callout_type,
            label=label,
            heading_id=heading.id,
            page_number=1,
            document_order=0,
        )
    ]
    return doc


class TestCalloutVerifierClassify:
    def test_numbered_label_with_intact_heading_is_verified_silently(self):
        doc = _doc_with_callout("Case study 11.2", "case_study")
        findings = engine.run_pdf_verification("callout", doc.callouts, [], document=doc)
        assert findings == []
        assert doc.callouts[0].verification_status == VerificationStatus.VERIFIED

    def test_unnumbered_label_alone_is_not_enough_to_flag(self):
        """A bare 'Summary' is ambiguous but not automatically wrong —
        only when combined with a second weak/negative signal (e.g. an
        orphaned heading reference) does confidence drop enough to flag."""
        doc = _doc_with_callout("Summary", "summary", heading_intact=True)
        findings = engine.run_pdf_verification("callout", doc.callouts, [], document=doc)
        assert findings == []

    def test_unnumbered_label_plus_orphaned_heading_flags_weak(self):
        doc = _doc_with_callout("Summary", "summary", heading_intact=False)
        findings = engine.run_pdf_verification("callout", doc.callouts, [], document=doc)
        assert len(findings) == 1
        assert findings[0].kind == "weak_callout_label"
        assert findings[0].confidence < 0.5

    def test_no_document_in_context_skips_heading_integrity_signal_gracefully(self):
        doc = _doc_with_callout("Case study 1.1", "case_study")
        # No document= kwarg -> heading_intact signal unavailable, must not raise.
        findings = engine.run_pdf_verification("callout", doc.callouts, [])
        assert findings == []


class TestCalloutVerifierApply:
    def test_accepting_weak_label_removes_the_callout_not_the_heading(self):
        verifier = CalloutVerifier()
        doc = _doc_with_callout("Summary", "summary", heading_intact=True)
        callout_id = doc.callouts[0].id
        correction = CorrectionRecord(
            object_type="callout",
            object_id=callout_id,
            field="weak_callout_label",
            original_value="summary",
            proposed_value="",
            status=CorrectionStatus.ACCEPTED,
        )
        verifier.apply(doc, correction)
        assert doc.callouts == []
        assert len(doc.headings) == 1  # the anchoring heading is untouched


class TestCalloutRegisteredWithEngine:
    def test_callout_is_a_registered_asset_type(self):
        # Importing src.verification.callouts registers it at module load
        # time (see _register() at the bottom of that file) — the same
        # pattern every other asset type (heading/list/figure) uses.
        assert "callout" in engine._verifiers
