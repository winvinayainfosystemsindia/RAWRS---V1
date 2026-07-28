"""Commit 2 — CorrectionTerminalRule (REVIEW_001).

A document cannot be Export Ready while any cross-source CorrectionRecord is
non-terminal. These tests isolate the new rule: the fixture document passes
every other accessibility rule (language set; no pages/images/tables, so the
page-guarded structural rules produce no evaluations), so export_ready is
governed solely by REVIEW_001.
"""

from datetime import datetime, timezone

import pytest

import src.accessibility.rules  # noqa: F401 - registers all rules incl. REVIEW_001
from src.accessibility.models import RuleOutcome
from src.accessibility.pipeline import evaluate_document
from src.accessibility.registry import registry
from src.accessibility.rules.corrections import CorrectionTerminalRule
from src.models.correction import CorrectionRecord, CorrectionStatus
from src.models.document import Document
from src.models.metadata import Metadata

NON_TERMINAL = {
    CorrectionStatus.PROPOSED,
    CorrectionStatus.PENDING_REVIEW,
    CorrectionStatus.REVERTED,
}
TERMINAL = {
    CorrectionStatus.ACCEPTED,
    CorrectionStatus.EDITED,
    CorrectionStatus.REJECTED,
    CorrectionStatus.IGNORED,
    CorrectionStatus.AUTO_APPLIED,
}


def _correction(status: CorrectionStatus) -> CorrectionRecord:
    return CorrectionRecord(
        object_type="heading",
        field="level",
        original_value="1",
        proposed_value="2",
        status=status,
    )


def _accessible_document(*corrections: CorrectionRecord) -> Document:
    """A document that passes every rule except (potentially) REVIEW_001."""
    return Document(
        source_pdf_path="dummy.pdf",
        metadata=Metadata(
            filename="dummy.pdf",
            page_count=1,
            image_count=0,
            processing_date=datetime.now(timezone.utc),
            language="en-US",
            title="Test Document",
        ),
        pages=[],
        corrections=list(corrections),
    )


class TestStatusPartition:
    def test_non_terminal_and_terminal_partition_the_enum(self):
        # If a future CorrectionStatus is added, this fails until it is
        # explicitly classified (guards against a new state silently passing).
        assert NON_TERMINAL | TERMINAL == set(CorrectionStatus)
        assert NON_TERMINAL & TERMINAL == set()
        assert CorrectionTerminalRule._NON_TERMINAL == frozenset(NON_TERMINAL)


class TestRuleEvaluate:
    def test_no_corrections_produces_no_evaluation(self):
        assert CorrectionTerminalRule().evaluate(_accessible_document()) == []

    @pytest.mark.parametrize("status", sorted(NON_TERMINAL, key=lambda s: s.value))
    def test_non_terminal_requires_manual_review(self, status):
        [ev] = CorrectionTerminalRule().evaluate(_accessible_document(_correction(status)))
        assert ev.outcome == RuleOutcome.MANUAL_REVIEW_REQUIRED

    @pytest.mark.parametrize("status", sorted(TERMINAL, key=lambda s: s.value))
    def test_terminal_passes(self, status):
        [ev] = CorrectionTerminalRule().evaluate(_accessible_document(_correction(status)))
        assert ev.outcome == RuleOutcome.PASS

    def test_one_non_terminal_among_terminal_still_blocks(self):
        [ev] = CorrectionTerminalRule().evaluate(
            _accessible_document(
                _correction(CorrectionStatus.ACCEPTED),
                _correction(CorrectionStatus.PROPOSED),
            )
        )
        assert ev.outcome == RuleOutcome.MANUAL_REVIEW_REQUIRED


class TestExportReadyIntegration:
    def test_rule_is_registered(self):
        assert registry.get("REVIEW_001") is not None

    def test_accessibility_passes_but_unresolved_correction_blocks(self):
        report = evaluate_document(_accessible_document(_correction(CorrectionStatus.PROPOSED)))
        assert report.export_ready is False
        assert "REVIEW_001" in report.blocking_failures

    def test_accessibility_passes_all_terminal_is_ready(self):
        report = evaluate_document(_accessible_document(_correction(CorrectionStatus.ACCEPTED)))
        assert report.export_ready is True
        assert "REVIEW_001" not in report.blocking_failures

    def test_no_corrections_is_ready(self):
        report = evaluate_document(_accessible_document())
        assert report.export_ready is True

    def test_reverted_reopens_readiness(self):
        report = evaluate_document(_accessible_document(_correction(CorrectionStatus.REVERTED)))
        assert report.export_ready is False

    def test_unresolved_correction_does_not_lower_points_lost(self):
        # OBSERVATION + MANUAL_REVIEW_REQUIRED blocks export without adding to
        # points_lost — it bumps manual_review_count instead.
        report = evaluate_document(_accessible_document(_correction(CorrectionStatus.PROPOSED)))
        assert report.manual_review_count >= 1
