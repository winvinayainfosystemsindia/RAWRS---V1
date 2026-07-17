"""Tests for the engine core: registry, scoring (Sections 7/8/9/18/25),
pipeline (Section 5), debt (Section 26), provenance (Section 27).

evaluate_document tests exercise the real, registered Phase 1 rules against
a Section-21-style Document fixture (one table missing a caption, no
document language, a reading-order anomaly) so the worked example in the
design doc is a genuine regression test, not just prose.
"""

from datetime import datetime, timezone

import pytest

import src.accessibility.rules  # noqa: F401 - registers the real Phase 1 rules
from src.accessibility.debt import compute_debt_report
from src.accessibility.models import (
    AccessibilityRule,
    BarrierClass,
    RuleAutomation,
    RuleEvaluation,
    RuleImpact,
    RuleOutcome,
)
from src.accessibility.pipeline import evaluate_document
from src.accessibility.provenance import provenance_for
from src.accessibility.registry import AccessibilityRuleRegistry, DuplicateRuleIdError
from src.accessibility.registry import registry as real_registry
from src.accessibility.scoring import compose_score, predict_score, priority_key
from src.models.contracts import (
    BoundingBox,
    Document,
    Heading,
    HeadingLevel,
    Metadata,
    Page,
    Table,
    TableCell,
    TableRow,
    TextBlock,
)

_IMPACT = RuleImpact(affected_users=["x"], user_consequence="y", severity_rationale="z")


class _StubRule(AccessibilityRule):
    rule_id = "STUB_001"
    name = "stub"
    category = "Stub"
    wcag_criteria = []
    pdf_ua_clause = None
    barrier_class = BarrierClass.BARRIER
    automation = RuleAutomation.AUTOMATIC
    rationale = "stub"
    impact = _IMPACT

    def evaluate(self, document):
        return []


class TestRegistry:
    def test_register_and_get(self):
        reg = AccessibilityRuleRegistry()
        rule = _StubRule()
        reg.register(rule)
        assert reg.get("STUB_001") is rule
        assert reg.all() == [rule]

    def test_duplicate_rule_id_raises(self):
        reg = AccessibilityRuleRegistry()
        reg.register(_StubRule())
        with pytest.raises(DuplicateRuleIdError):
            reg.register(_StubRule())

    def test_by_category(self):
        reg = AccessibilityRuleRegistry()
        reg.register(_StubRule())
        assert reg.by_category("Stub") == reg.all()
        assert reg.by_category("Other") == []

    def test_real_registry_has_14_phase1_rules(self):
        assert len(real_registry.all()) == 14


def _evaluation(rule_id, outcome, object_id=None):
    return RuleEvaluation(rule_id=rule_id, outcome=outcome, message="", object_id=object_id)


class TestScoring:
    def _registry_with_two_rules(self):
        reg = AccessibilityRuleRegistry()

        class BarrierRule(_StubRule):
            rule_id = "R_BARRIER"
            barrier_class = BarrierClass.BARRIER

        class DegradationRule(_StubRule):
            rule_id = "R_DEGRADATION"
            barrier_class = BarrierClass.DEGRADATION
            required_for_export = False

        reg.register(BarrierRule())
        reg.register(DegradationRule())
        return reg

    def test_compose_score_all_pass_is_perfect(self):
        reg = self._registry_with_two_rules()
        evaluations = [_evaluation("R_BARRIER", RuleOutcome.PASS), _evaluation("R_DEGRADATION", RuleOutcome.PASS)]
        report = compose_score(evaluations, reg)
        assert report.overall_score == 1.0
        assert report.points_lost == 0
        assert report.export_ready is True

    def test_compose_score_fail_loses_exact_weight(self):
        reg = self._registry_with_two_rules()
        evaluations = [_evaluation("R_BARRIER", RuleOutcome.FAIL), _evaluation("R_DEGRADATION", RuleOutcome.PASS)]
        report = compose_score(evaluations, reg)
        assert report.points_lost == 10
        assert report.max_points == 15
        assert report.overall_score == pytest.approx((15 - 10) / 15)
        assert report.point_ledger == [("R_BARRIER", 10)]

    def test_required_export_barrier_fail_blocks_export(self):
        reg = self._registry_with_two_rules()
        evaluations = [_evaluation("R_BARRIER", RuleOutcome.FAIL), _evaluation("R_DEGRADATION", RuleOutcome.PASS)]
        report = compose_score(evaluations, reg)
        assert report.export_ready is False
        assert "R_BARRIER" in report.blocking_failures

    def test_non_required_degradation_fail_does_not_block_export(self):
        reg = self._registry_with_two_rules()
        evaluations = [_evaluation("R_BARRIER", RuleOutcome.PASS), _evaluation("R_DEGRADATION", RuleOutcome.FAIL)]
        report = compose_score(evaluations, reg)
        assert report.export_ready is True

    def test_manual_review_required_excluded_from_points_lost(self):
        reg = self._registry_with_two_rules()
        evaluations = [
            _evaluation("R_BARRIER", RuleOutcome.MANUAL_REVIEW_REQUIRED),
            _evaluation("R_DEGRADATION", RuleOutcome.PASS),
        ]
        report = compose_score(evaluations, reg)
        assert report.points_lost == 0
        assert report.manual_review_count == 1
        assert report.export_ready is False  # BARRIER-class, required_for_export

    def test_not_applicable_excluded_from_denominator(self):
        reg = self._registry_with_two_rules()
        evaluations = [_evaluation("R_BARRIER", RuleOutcome.NOT_APPLICABLE), _evaluation("R_DEGRADATION", RuleOutcome.PASS)]
        report = compose_score(evaluations, reg)
        assert report.max_points == 5  # only the degradation rule counted
        assert report.overall_score == 1.0

    def test_predict_score_reuses_compose_score_deterministically(self):
        reg = self._registry_with_two_rules()
        evaluations = [_evaluation("R_BARRIER", RuleOutcome.FAIL), _evaluation("R_DEGRADATION", RuleOutcome.PASS)]
        report = compose_score(evaluations, reg)
        prediction = predict_score(report, {"R_BARRIER"}, reg)
        assert prediction.current_score == report.overall_score
        assert prediction.predicted_score == 1.0
        assert prediction.points_recovered == 10

    def test_priority_key_ranks_barrier_before_degradation(self):
        reg = self._registry_with_two_rules()
        barrier_rule = reg.get("R_BARRIER")
        degradation_rule = reg.get("R_DEGRADATION")
        barrier_ev = _evaluation("R_BARRIER", RuleOutcome.FAIL)
        degradation_ev = _evaluation("R_DEGRADATION", RuleOutcome.FAIL)
        assert priority_key(barrier_ev, barrier_rule, 1) < priority_key(degradation_ev, degradation_rule, 1)


def _section21_document() -> Document:
    """Mirrors the design doc's Section 21 worked example: one
    caption-missing table, no document language, one reading-order
    anomaly page. Everything else (headings, image, other table) is
    well-formed so only these 3 rules fail.
    """
    table_missing_caption = Table(
        table_id="table1",
        page_number=1,
        row_count=1,
        col_count=1,
        rows=[TableRow(cells=[TableCell(text="a", row_index=0, col_index=0, is_header=True)], is_header_row=True)],
        caption=None,
        summary="A summary.",
    )
    table_compliant = Table(
        table_id="table2",
        page_number=2,
        row_count=1,
        col_count=1,
        rows=[TableRow(cells=[TableCell(text="a", row_index=0, col_index=0, is_header=True)], is_header_row=True)],
        caption="Table 2. Results",
        summary="A summary.",
    )
    anomaly_blocks = [
        TextBlock(page_number=1, text="later in order, higher on page", bbox=BoundingBox(x0=0, y0=500, x1=100, y1=520), order=0),
        TextBlock(page_number=1, text="earlier in order, lower on page", bbox=BoundingBox(x0=0, y0=100, x1=100, y1=120), order=1),
    ]
    return Document(
        source_pdf_path="dummy.pdf",
        metadata=Metadata(filename="dummy.pdf", page_count=2, image_count=0, language=None, title="A Title"),
        pages=[Page(page_number=1), Page(page_number=2)],
        headings=[Heading(level=HeadingLevel.H1, text="Title", page_number=1, document_order=0)],
        tables=[table_missing_caption, table_compliant],
        blocks=anomaly_blocks,
    )


class TestPipelineIntegration:
    def test_section21_worked_example_matches_design_doc(self):
        document = _section21_document()
        report = evaluate_document(document)

        assert report.export_ready is False  # LANG_001 and READING_ORDER_001 are required BARRIER fails

        ledger = dict(report.point_ledger)
        assert ledger["TABLE_A11Y_001:table1"] == 5
        assert ledger["LANG_001"] == 10
        assert ledger["READING_ORDER_001"] == 10
        assert "TABLE_A11Y_001:table2" not in ledger

    def test_debt_report_matches_barrier_classes(self):
        document = _section21_document()
        report = evaluate_document(document)
        debt = compute_debt_report(document, report)
        # LANG_001 (10) + READING_ORDER_001 (10) are BARRIER; TABLE_A11Y_001 (5) is DEGRADATION
        assert debt.critical_debt_points == 20
        assert debt.moderate_debt_points == 5
        assert debt.remaining_debt_points == 25
        assert debt.resolved_debt_points == 0  # no corrections exist in this fixture

    def test_provenance_for_scored_rule(self):
        document = _section21_document()
        report = evaluate_document(document)
        # LANG_001 FAILs in this fixture (no language set) - confidence is
        # 0.0 by construction (a boolean check has no genuine uncertainty).
        prov = provenance_for(report, "LANG_001")
        assert prov is not None
        assert prov.wcag_mapping == ["3.1.1 Language of Page (A)"]
        assert prov.internal_only is False
        assert prov.confidence == 0.0

        # META_A11Y_001 PASSes (title is set) - confidence 1.0.
        passing_prov = provenance_for(report, "META_A11Y_001")
        assert passing_prov.confidence == 1.0

    def test_provenance_internal_only_rule(self):
        document = _section21_document()
        report = evaluate_document(document)
        prov = provenance_for(report, "TABLE_A11Y_005", object_id="table1")
        assert prov is not None
        assert prov.internal_only is True

    def test_provenance_missing_evaluation_returns_none(self):
        document = _section21_document()
        report = evaluate_document(document)
        assert provenance_for(report, "LANG_001", object_id="nonexistent") is None
