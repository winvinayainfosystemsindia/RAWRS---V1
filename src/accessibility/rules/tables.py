"""Table rules - Section 20 "Tables" table, TABLE_A11Y_001-005.

Object-scoped: one RuleEvaluation per Table. Each wraps an existing
src/validation/validator.py check (TABLE_001-004, TABLE_005/007 folded into
one confidence-gate rule per Section 20) - same conditions, read straight
off document.tables, no new detection logic.
"""

from __future__ import annotations

from typing import List

from src.accessibility.models import (
    AccessibilityRule,
    BarrierClass,
    RuleAutomation,
    RuleEvaluation,
    RuleImpact,
    RuleOutcome,
)
from src.accessibility.registry import registry
from src.models.contracts import Document, TableStatus
from src.verification.evidence import EvidenceBundle, EvidenceSignal

_TABLES_IMPACT = RuleImpact(
    affected_users=[
        "Screen reader users navigating cell-by-cell (JAWS/NVDA table mode)",
        "Users with cognitive disabilities relying on captions for orientation",
    ],
    user_consequence=(
        "No header row: every cell is announced with zero row/column context, "
        "forcing the user to count cells manually. No caption/summary: the "
        "user must read the entire table before learning what it's even about."
    ),
    severity_rationale=(
        "Header-row structure is the one piece table navigation mode depends "
        "on entirely (Barrier); caption/summary loses orientation, not access "
        "(Degradation)."
    ),
)


def _evaluation(rule_id: str, table_id: str, outcome: RuleOutcome, signal_name: str, note: str, message: str) -> RuleEvaluation:
    bundle = EvidenceBundle()
    bundle.add(
        EvidenceSignal(name=signal_name, score=1.0 if outcome == RuleOutcome.PASS else 0.0, weight=1.0, note=note)
    )
    return RuleEvaluation(rule_id=rule_id, outcome=outcome, message=message, object_id=table_id, evidence=bundle)


class _TableFieldPresentRule(AccessibilityRule):
    """Shared shape for the 4 "does this table have field X" checks."""

    signal_name = "field_present"

    def _field_present(self, table) -> bool:  # pragma: no cover - overridden
        raise NotImplementedError

    def _fail_message(self, table) -> str:  # pragma: no cover - overridden
        raise NotImplementedError

    def evaluate(self, document: Document) -> List[RuleEvaluation]:
        evaluations: List[RuleEvaluation] = []
        for table in document.tables:
            present = self._field_present(table)
            evaluations.append(
                _evaluation(
                    self.rule_id,
                    table.table_id,
                    RuleOutcome.PASS if present else RuleOutcome.FAIL,
                    self.signal_name,
                    "Present." if present else "Missing.",
                    "" if present else self._fail_message(table),
                )
            )
        return evaluations


class TableCaptionRule(_TableFieldPresentRule):
    rule_id = "TABLE_A11Y_001"
    name = "Table has a caption"
    category = "Tables"
    wcag_criteria = ["1.3.1 Info and Relationships (A)"]
    pdf_ua_clause = "ISO 14289-1 §7.5"
    barrier_class = BarrierClass.DEGRADATION
    automation = RuleAutomation.AUTOMATIC
    rationale = "Blind users cannot know what a table is about without a caption."
    impact = _TABLES_IMPACT
    required_for_export = False
    signal_name = "caption_present"

    def _field_present(self, table) -> bool:
        return bool(table.caption)

    def _fail_message(self, table) -> str:
        return f"Table '{table.table_id}' on page {table.page_number} has no caption."


class TableSummaryRule(_TableFieldPresentRule):
    rule_id = "TABLE_A11Y_002"
    name = "Table has an accessibility summary"
    category = "Tables"
    wcag_criteria = ["1.3.1 Info and Relationships (A)"]
    pdf_ua_clause = "ISO 14289-1 §7.5"
    barrier_class = BarrierClass.DEGRADATION
    automation = RuleAutomation.AUTOMATIC
    rationale = "WCAG H73: complex tables need a prose description so screen reader users understand the table's purpose without navigating every cell."
    impact = _TABLES_IMPACT
    required_for_export = False
    signal_name = "summary_present"

    def _field_present(self, table) -> bool:
        return bool(table.summary)

    def _fail_message(self, table) -> str:
        return f"Table '{table.table_id}' on page {table.page_number} has no accessibility summary."


class TableHeaderRowRule(_TableFieldPresentRule):
    rule_id = "TABLE_A11Y_003"
    name = "Table has a header row"
    category = "Tables"
    wcag_criteria = ["1.3.1 Info and Relationships (A)"]
    pdf_ua_clause = "ISO 14289-1 §7.5"
    barrier_class = BarrierClass.BARRIER
    automation = RuleAutomation.AUTOMATIC
    rationale = "Without a header row, screen readers cannot announce column context when navigating cells."
    impact = _TABLES_IMPACT
    signal_name = "header_row_present"

    def _field_present(self, table) -> bool:
        return any(row.is_header_row for row in table.rows)

    def _fail_message(self, table) -> str:
        return f"Table '{table.table_id}' on page {table.page_number} has no header row."


class TableHeaderCellsFilledRule(AccessibilityRule):
    rule_id = "TABLE_A11Y_004"
    name = "No empty header cells"
    category = "Tables"
    wcag_criteria = ["1.3.1 Info and Relationships (A)"]
    pdf_ua_clause = "ISO 14289-1 §7.5"
    barrier_class = BarrierClass.BARRIER
    automation = RuleAutomation.AUTOMATIC
    rationale = "Empty header cells give screen readers nothing to announce for that column or row."
    impact = _TABLES_IMPACT

    def evaluate(self, document: Document) -> List[RuleEvaluation]:
        evaluations: List[RuleEvaluation] = []
        for table in document.tables:
            if not any(row.is_header_row for row in table.rows):
                continue  # covered by TABLE_A11Y_003, not double-counted here
            empty_cells = [
                cell
                for row in table.rows
                if row.is_header_row
                for cell in row.cells
                if cell.is_header and not cell.text.strip()
            ]
            outcome = RuleOutcome.PASS if not empty_cells else RuleOutcome.FAIL
            evaluations.append(
                _evaluation(
                    self.rule_id,
                    table.table_id,
                    outcome,
                    "header_cells_filled",
                    "All header cells filled." if not empty_cells else f"{len(empty_cells)} empty header cell(s).",
                    "" if outcome == RuleOutcome.PASS else (
                        f"Table '{table.table_id}' on page {table.page_number} has an empty header cell."
                    ),
                )
            )
        return evaluations


class TableConfidenceGateRule(AccessibilityRule):
    rule_id = "TABLE_A11Y_005"
    name = "Detection confidence high enough to trust"
    category = "Tables"
    wcag_criteria = []
    pdf_ua_clause = None
    barrier_class = BarrierClass.OBSERVATION
    automation = RuleAutomation.MANUAL
    rationale = (
        "A low-confidence auto-detected table, or one detected without explicit "
        "border lines and only one inferred column, may have an incorrect "
        "structure; review it before trusting TABLE_A11Y_001-004's result on it."
    )
    impact = _TABLES_IMPACT
    # OBSERVATION-class: a review prompt about detection confidence, not
    # itself an accessibility barrier - never blocks export on its own
    # (Section 9's default: True only for BARRIER-class rules).
    required_for_export = False

    _BORDERLESS_SIGNALS = {"horizontal_rules", "column_x_alignment", "span_column_alignment"}

    def evaluate(self, document: Document) -> List[RuleEvaluation]:
        evaluations: List[RuleEvaluation] = []
        for table in document.tables:
            low_confidence = table.status == TableStatus.AUTO_DETECTED and table.confidence < 0.7

            # TABLE_007: borderless-detected with only one inferred column -
            # column structure is less reliable without vertical separators.
            # Mirrors validator.py::_check_table_accessibility's TABLE_007
            # condition exactly (same evidence_signals field, same signal
            # names, same col_count<=1 threshold).
            detected_signal_names = {s.get("name", "") for s in table.evidence_signals}
            borderless_only = (
                detected_signal_names & self._BORDERLESS_SIGNALS
                and "vector_borders" not in detected_signal_names
            )
            unreliable_columns = borderless_only and table.col_count <= 1

            needs_review = low_confidence or unreliable_columns
            outcome = RuleOutcome.MANUAL_REVIEW_REQUIRED if needs_review else RuleOutcome.PASS

            if low_confidence and unreliable_columns:
                note = f"confidence={table.confidence:.2f}; borderless with <=1 inferred column"
            elif low_confidence:
                note = f"confidence={table.confidence:.2f}"
            elif unreliable_columns:
                note = "borderless with <=1 inferred column"
            else:
                note = f"confidence={table.confidence:.2f}"

            evaluations.append(
                _evaluation(
                    self.rule_id,
                    table.table_id,
                    outcome,
                    "detection_confidence",
                    note,
                    "" if outcome == RuleOutcome.PASS else (
                        f"Table '{table.table_id}' on page {table.page_number} needs review: {note}."
                    ),
                )
            )
        return evaluations


registry.register(TableCaptionRule())
registry.register(TableSummaryRule())
registry.register(TableHeaderRowRule())
registry.register(TableHeaderCellsFilledRule())
registry.register(TableConfidenceGateRule())
