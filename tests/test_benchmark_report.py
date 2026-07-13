"""Tests for src/verification/benchmark_report.py (FEATURE_019, M-3.3)."""

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
from src.models.validation_issue import Severity, ValidationIssue, ValidationIssueStatus
from src.verification.benchmark_report import aggregate, compute_accessibility_score
import src.verification.headings  # noqa: F401 - registers HeadingVerifier (rule_table() lookup)


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


class TestAggregateRepairAndRemaining:
    def test_table_recovery_is_tallied_via_missing_from_mathpix(self):
        """Regression test for the M-3.3 bug fix: TableVerifier's RECOVER
        kind is 'missing_from_mathpix' (not 'missing_from_package'/
        'recovered_from_pdf' like every other verifier) — must still
        count as a recovery, not silently fall through uncounted."""
        doc = _doc()
        doc.corrections = [
            CorrectionRecord(
                object_type="table", field="missing_from_mathpix", original_value="",
                proposed_value="x", status=CorrectionStatus.ACCEPTED,
            ),
        ]
        report = aggregate(doc)
        table = report["per_asset_type"]["table"]
        assert table["recovered_proposed"] == 1
        assert table["recovered_accepted"] == 1
        assert table["recovery_rate"] == 1.0

    def test_repair_kind_correction_counted_separately_from_recover(self):
        doc = _doc()
        doc.corrections = [
            CorrectionRecord(
                object_type="heading", field="level_mismatch", original_value="2",
                proposed_value="1", status=CorrectionStatus.ACCEPTED,
            ),
        ]
        report = aggregate(doc)
        heading = report["per_asset_type"]["heading"]
        assert heading["repair_proposed"] == 1
        assert heading["repair_accepted"] == 1
        assert heading["repair_rate"] == 1.0
        assert heading["recovered_proposed"] == 0

    def test_info_severity_finding_is_not_counted_as_a_repair(self):
        """HEADING_VERIFY_001 (missing_from_pdf... actually 'unconfirmed_by_pdf')
        is severity=info — informational only, not an actionable repair."""
        doc = _doc()
        doc.corrections = [
            CorrectionRecord(
                object_type="table", field="low_confidence", original_value="",
                proposed_value="", status=CorrectionStatus.ACCEPTED,
            ),
        ]
        report = aggregate(doc)
        table = report["per_asset_type"]["table"]
        assert table["repair_proposed"] == 0
        assert table["repair_accepted"] == 0

    def test_manual_corrections_remaining_counts_proposed_and_pending(self):
        doc = _doc()
        doc.corrections = [
            CorrectionRecord(
                object_type="heading", field="level_mismatch", original_value="2",
                proposed_value="1", status=CorrectionStatus.PROPOSED,
            ),
            CorrectionRecord(
                object_type="heading", field="text_correction", original_value="a",
                proposed_value="b", status=CorrectionStatus.PENDING_REVIEW,
            ),
            CorrectionRecord(
                object_type="heading", field="level_mismatch", original_value="2",
                proposed_value="1", status=CorrectionStatus.ACCEPTED,
            ),
        ]
        report = aggregate(doc)
        assert report["manual_corrections_remaining"] == 2
        assert report["per_asset_type"]["heading"]["manual_corrections_remaining"] == 2

    def test_confidence_distribution_buckets_correction_confidences(self):
        doc = _doc()
        doc.corrections = [
            CorrectionRecord(
                object_type="heading", field="level_mismatch", original_value="2",
                proposed_value="1", status=CorrectionStatus.PROPOSED, confidence=0.92,
            ),
            CorrectionRecord(
                object_type="heading", field="level_mismatch", original_value="2",
                proposed_value="1", status=CorrectionStatus.PROPOSED, confidence=0.3,
            ),
        ]
        report = aggregate(doc)
        assert report["confidence_distribution"]["0.85-1.0"] == 1
        assert report["confidence_distribution"]["0.0-0.5"] == 1

    def test_object_count_reflects_canonical_population_size(self):
        """object_count is reported alongside checked/corrected stats —
        per the pre-existing per_asset_type filter (see
        test_unverified_objects_excluded_from_accuracy above), a type
        with objects but zero verification activity still reports
        nothing at all, so this uses a checked heading."""
        doc = _doc()
        h1 = Heading(level=HeadingLevel.H2, text="A", page_number=1, document_order=0)
        h1.verification_status = VerificationStatus.VERIFIED
        h2 = Heading(level=HeadingLevel.H2, text="B", page_number=2, document_order=1)
        h2.verification_status = VerificationStatus.VERIFIED
        doc.headings = [h1, h2]
        report = aggregate(doc)
        assert report["per_asset_type"]["heading"]["object_count"] == 2


class TestComputeAccessibilityScore:
    def test_no_issues_scores_100(self):
        assert compute_accessibility_score([]) == 100.0

    def test_errors_weighted_more_than_warnings_and_info(self):
        error_score = compute_accessibility_score(
            [ValidationIssue(severity=Severity.ERROR, rule_id="R1", message="m")]
        )
        warning_score = compute_accessibility_score(
            [ValidationIssue(severity=Severity.WARNING, rule_id="R1", message="m")]
        )
        info_score = compute_accessibility_score(
            [ValidationIssue(severity=Severity.INFO, rule_id="R1", message="m")]
        )
        assert error_score < warning_score < info_score < 100.0

    def test_score_never_goes_below_zero(self):
        issues = [ValidationIssue(severity=Severity.ERROR, rule_id="R1", message="m") for _ in range(50)]
        assert compute_accessibility_score(issues) == 0.0

    def test_ignored_and_deferred_issues_do_not_count_against_score(self):
        issues = [
            ValidationIssue(
                severity=Severity.ERROR, rule_id="R1", message="m",
                status=ValidationIssueStatus.IGNORED,
            ),
        ]
        assert compute_accessibility_score(issues) == 100.0

    def test_aggregate_includes_accessibility_score_from_document_validation_issues(self):
        doc = _doc()
        doc.validation_issues = [ValidationIssue(severity=Severity.WARNING, rule_id="R1", message="m")]
        report = aggregate(doc)
        assert report["accessibility_score"] == 97.0
