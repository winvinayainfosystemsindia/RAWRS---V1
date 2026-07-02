"""Tests for src/validation/readiness.py::compute_readiness().

Generic by construction: no rule_id is hand-listed here except as test
fixtures — the function itself only ever reads rule_id prefixes, so a
new verifier's rule IDs participate automatically as long as they follow
the existing PREFIX_NNN convention.
"""

from src.models.document import Document
from src.models.metadata import Metadata
from src.models.validation_issue import Severity, ValidationIssue
from src.validation.readiness import compute_readiness


def _document_with_issues(*issues: ValidationIssue) -> Document:
    doc = Document(source_pdf_path="test.pdf", metadata=Metadata(filename="test.pdf"))
    doc.validation_issues = list(issues)
    return doc


class TestComputeReadiness:
    def test_no_issues_is_fully_ready(self) -> None:
        report = compute_readiness(_document_with_issues())
        assert report.ready is True
        assert report.overall_score == 1.0
        assert report.categories == []

    def test_groups_by_rule_id_prefix(self) -> None:
        doc = _document_with_issues(
            ValidationIssue(severity=Severity.WARNING, rule_id="HEADING_VERIFY_003", message="a"),
            ValidationIssue(severity=Severity.WARNING, rule_id="HEADING_001", message="b"),
            ValidationIssue(severity=Severity.INFO, rule_id="LIST_VERIFY_001", message="c"),
        )
        report = compute_readiness(doc)
        categories = {c.category: c for c in report.categories}
        assert set(categories) == {"HEADING", "LIST"}
        assert categories["HEADING"].warning_count == 2
        assert categories["LIST"].info_count == 1

    def test_category_with_only_info_is_ready(self) -> None:
        doc = _document_with_issues(
            ValidationIssue(severity=Severity.INFO, rule_id="NOTE_001", message="footnote detected"),
        )
        report = compute_readiness(doc)
        assert report.categories[0].ready is True
        assert report.ready is True

    def test_category_with_warning_is_not_ready(self) -> None:
        doc = _document_with_issues(
            ValidationIssue(severity=Severity.WARNING, rule_id="LIST_VERIFY_002", message="recovered"),
        )
        report = compute_readiness(doc)
        assert report.categories[0].ready is False
        assert report.ready is False
        assert report.overall_score == 0.0

    def test_error_also_marks_category_not_ready(self) -> None:
        doc = _document_with_issues(
            ValidationIssue(severity=Severity.ERROR, rule_id="DOC_003", message="zero pages"),
        )
        report = compute_readiness(doc)
        assert report.categories[0].ready is False

    def test_overall_score_is_fraction_of_ready_categories(self) -> None:
        doc = _document_with_issues(
            ValidationIssue(severity=Severity.WARNING, rule_id="LIST_VERIFY_002", message="x"),
            ValidationIssue(severity=Severity.INFO, rule_id="NOTE_001", message="y"),
        )
        report = compute_readiness(doc)
        assert report.overall_score == 0.5  # 1 of 2 categories ready

    def test_known_prefix_gets_human_label(self) -> None:
        doc = _document_with_issues(
            ValidationIssue(severity=Severity.WARNING, rule_id="TABLE_001", message="no caption"),
        )
        report = compute_readiness(doc)
        assert report.categories[0].label == "Tables"

    def test_unknown_prefix_falls_back_to_titlecased_prefix(self) -> None:
        doc = _document_with_issues(
            ValidationIssue(severity=Severity.WARNING, rule_id="EQUATION_VERIFY_001", message="x"),
        )
        report = compute_readiness(doc)
        assert report.categories[0].label == "Equation"
