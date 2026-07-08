"""Tests for src/verification/benchmark_report.py (FEATURE_019)."""

from src.models.contracts import (
    Callout,
    CorrectionRecord,
    CorrectionStatus,
    Document,
    Heading,
    HeadingLevel,
    Metadata,
    VerificationStatus,
)
from src.verification.benchmark_report import aggregate


def _doc() -> Document:
    return Document(source_pdf_path="x.pdf", metadata=Metadata(filename="x.pdf"))


class TestAggregateVerificationStatus:
    def test_empty_document_reports_nothing_checked(self):
        report = aggregate(_doc())
        assert report["per_asset_type"] == {}
        assert report["overall_mathpix_accuracy"] is None

    def test_unverified_objects_excluded_from_accuracy(self):
        """The RAWRS-native path runs no cross-source verification at
        all — every heading stays UNVERIFIED (the default). This must
        report as 'nothing checked', not falsely 0% or 100% accuracy."""
        doc = _doc()
        doc.headings = [Heading(level=HeadingLevel.H2, text="A", page_number=1, document_order=0)]
        report = aggregate(doc)
        assert report["per_asset_type"] == {}
        assert report["overall_mathpix_accuracy"] is None

    def test_verified_and_mismatch_compute_accuracy(self):
        doc = _doc()
        h1 = Heading(level=HeadingLevel.H2, text="A", page_number=1, document_order=0)
        h1.verification_status = VerificationStatus.VERIFIED
        h2 = Heading(level=HeadingLevel.H2, text="B", page_number=2, document_order=1)
        h2.verification_status = VerificationStatus.MISMATCH
        h3 = Heading(level=HeadingLevel.H2, text="C", page_number=3, document_order=2)
        h3.verification_status = VerificationStatus.VERIFIED
        doc.headings = [h1, h2, h3]

        report = aggregate(doc)
        heading = report["per_asset_type"]["heading"]
        assert heading["verified"] == 2
        assert heading["mismatch"] == 1
        assert heading["mathpix_accuracy"] == 2 / 3
        assert report["overall_mathpix_accuracy"] == 2 / 3

    def test_page_markers_excluded_from_heading_population(self):
        doc = _doc()
        marker = Heading(
            level=HeadingLevel.H6, text="3", page_number=3, document_order=0, is_page_marker=True
        )
        marker.verification_status = VerificationStatus.VERIFIED
        doc.headings = [marker]
        report = aggregate(doc)
        assert report["per_asset_type"] == {}

    def test_multiple_asset_types_tallied_independently(self):
        doc = _doc()
        h = Heading(level=HeadingLevel.H2, text="A", page_number=1, document_order=0)
        h.verification_status = VerificationStatus.VERIFIED
        doc.headings = [h]
        c = Callout(callout_type="summary", label="Summary", page_number=1, document_order=0)
        c.verification_status = VerificationStatus.LOW_CONFIDENCE
        doc.callouts = [c]

        report = aggregate(doc)
        assert report["per_asset_type"]["heading"]["verified"] == 1
        assert report["per_asset_type"]["callout"]["low_confidence"] == 1
        assert report["per_asset_type"]["callout"]["mathpix_accuracy"] == 0.0


class TestAggregateCorrections:
    def test_correction_status_tallied_per_asset_type(self):
        doc = _doc()
        doc.corrections = [
            CorrectionRecord(
                object_type="heading", field="level_mismatch", original_value="2",
                proposed_value="1", status=CorrectionStatus.ACCEPTED,
            ),
            CorrectionRecord(
                object_type="heading", field="level_mismatch", original_value="2",
                proposed_value="1", status=CorrectionStatus.REJECTED,
            ),
            CorrectionRecord(
                object_type="callout", field="weak_callout_label", original_value="summary",
                proposed_value="", status=CorrectionStatus.PROPOSED,
            ),
        ]
        report = aggregate(doc)
        assert report["per_asset_type"]["heading"]["corrections_accepted"] == 1
        assert report["per_asset_type"]["heading"]["corrections_rejected"] == 1
        assert report["per_asset_type"]["callout"]["corrections_proposed"] == 1
        assert report["total_corrections_proposed"] == 3

    def test_recovery_rate_from_accepted_vs_proposed_recover_corrections(self):
        doc = _doc()
        doc.corrections = [
            CorrectionRecord(
                object_type="heading", field="missing_from_package", original_value="",
                proposed_value="x", status=CorrectionStatus.ACCEPTED,
            ),
            CorrectionRecord(
                object_type="heading", field="missing_from_package", original_value="",
                proposed_value="y", status=CorrectionStatus.PROPOSED,
            ),
        ]
        report = aggregate(doc)
        heading = report["per_asset_type"]["heading"]
        assert heading["recovered_proposed"] == 2
        assert heading["recovered_accepted"] == 1
        assert heading["recovery_rate"] == 0.5

    def test_no_recover_corrections_reports_none_not_zero(self):
        doc = _doc()
        doc.corrections = [
            CorrectionRecord(
                object_type="heading", field="level_mismatch", original_value="2",
                proposed_value="1", status=CorrectionStatus.ACCEPTED,
            ),
        ]
        report = aggregate(doc)
        assert report["per_asset_type"]["heading"]["recovery_rate"] is None
