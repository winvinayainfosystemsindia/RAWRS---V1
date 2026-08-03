"""W-2/W-3: history is append-only, and the unit of undo is the transaction.

One judgement is one undo. Suppressing 34 running headers is a single act, and
before ``transaction_id`` existed there was no way to recover that grouping
after the fact — ``created_at`` orders the log but cannot say which records
belong together.

These lock the grouping rule, the LIFO guarantee, and the append-only property.
The guarantee that matters most is the refusal: undo replays ``apply()`` with
original and proposed swapped, which is sound only while nothing later touched
the same field, so an out-of-order request must be refused rather than risked.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from src.models.correction import (
    APPLIED_STATUSES,
    CorrectionRecord,
    CorrectionStatus,
    CorrectionTelemetryAction,
    transactions,
)
from src.models.verification import Finding, RuleSpec
from src.verification.base import SemanticVerifier
from src.verification.engine import CrossSourceVerificationEngine, NonLifoUndoError
from src.verification.matching import MultiSignalMatcher


class _ToggleVerifier(SemanticVerifier):
    """The smallest verifier that really mutates something.

    ``apply()`` reads its target state from ``proposed_value`` rather than
    assuming a direction, which is what lets the inherited ``revert()`` undo it
    with no undo logic of its own — the same shape the artifact suppressor uses.
    """

    asset_type = "toggle"

    def build_pdf_matcher(self) -> MultiSignalMatcher:
        return MultiSignalMatcher([])

    def to_canonical(self, match_result: Any, **context: Any) -> List[Any]:
        return []

    def classify(self, match_result: Any, **context: Any) -> List[Finding]:
        return []

    def rule_table(self) -> Dict[str, RuleSpec]:
        return {"flip": RuleSpec(rule_id="TOGGLE_001", reason_code="TOGGLED", severity="info")}

    def apply(self, document: Any, correction: CorrectionRecord) -> None:
        document.state[correction.object_id] = correction.proposed_value


def _engine() -> CrossSourceVerificationEngine:
    engine = CrossSourceVerificationEngine()
    engine.register(_ToggleVerifier())
    return engine


def _document() -> SimpleNamespace:
    return SimpleNamespace(
        corrections=[], verification_findings=[], version=0, state={"a": "off", "b": "off"}
    )


def _finding(object_id: str, auto_apply: bool = True) -> Finding:
    return Finding(
        asset_type="toggle",
        kind="flip",
        object_id=object_id,
        original_value="off",
        proposed_value="on",
        auto_apply=auto_apply,
    )


def _record(transaction_id, status=CorrectionStatus.AUTO_APPLIED, minute=0) -> CorrectionRecord:
    return CorrectionRecord(
        object_type="toggle",
        object_id="a",
        field="flip",
        original_value="off",
        proposed_value="on",
        status=status,
        transaction_id=transaction_id,
        created_at=datetime(2026, 8, 3, 12, minute, tzinfo=timezone.utc),
    )


class TestGrouping:
    def test_records_sharing_a_transaction_group_together(self) -> None:
        shared = "txn-1"
        groups = transactions([_record(shared), _record(shared), _record("txn-2")])
        assert sorted(len(g) for g in groups) == [1, 2]

    def test_a_record_with_no_transaction_is_a_transaction_of_one(self) -> None:
        # Every correction persisted before the field existed. Reading them
        # back as singletons is what makes this need no migration.
        groups = transactions([_record(None), _record(None)])
        assert [len(g) for g in groups] == [1, 1]

    def test_groups_are_ordered_oldest_first(self) -> None:
        groups = transactions([_record("late", minute=5), _record("early", minute=1)])
        assert [g[0].transaction_id for g in groups] == ["early", "late"]

    def test_grouping_is_derived_not_stored(self) -> None:
        log = [_record("txn-1")]
        transactions(log)
        assert "transactions" not in log[0].model_dump()
        assert len(log) == 1

    def test_an_empty_log_has_no_transactions(self) -> None:
        assert transactions([]) == []


class TestRecordingStampsTransactions:
    def test_a_batch_becomes_one_transaction(self) -> None:
        engine, document = _engine(), _document()
        engine.record_findings(document, [_finding("a"), _finding("b")])
        assert len({c.transaction_id for c in document.corrections}) == 1

    def test_the_autonomous_batch_and_the_review_batch_are_different_judgements(self) -> None:
        # "RAWRS decided this" and "RAWRS is asking about this" are two acts,
        # so undoing the first must not disturb the second.
        engine, document = _engine(), _document()
        engine.record_findings(document, [_finding("a"), _finding("b", auto_apply=False)])
        assert len({c.transaction_id for c in document.corrections}) == 2


class TestUndoIsTransactional:
    def test_one_undo_reverses_the_whole_batch(self) -> None:
        engine, document = _engine(), _document()
        engine.record_findings(document, [_finding("a"), _finding("b")])
        assert document.state == {"a": "on", "b": "on"}

        reverted = engine.undo_last_transaction(document)

        assert len(reverted) == 2
        assert document.state == {"a": "off", "b": "off"}

    def test_history_is_append_only(self) -> None:
        # W-2: nothing is deleted. The record keeps its place and its values.
        engine, document = _engine(), _document()
        engine.record_findings(document, [_finding("a")])
        engine.undo_last_transaction(document)

        assert len(document.corrections) == 1
        assert document.corrections[0].proposed_value == "on"
        assert document.corrections[0].status is CorrectionStatus.REVERTED

    def test_an_undo_records_why_it_happened(self) -> None:
        engine, document = _engine(), _document()
        engine.record_findings(document, [_finding("a")])
        engine.undo_last_transaction(document)

        event = document.corrections[0].telemetry_events[-1]
        assert event.action is CorrectionTelemetryAction.UNDONE
        assert event.previous_status == CorrectionStatus.AUTO_APPLIED.value

    def test_undo_walks_back_one_transaction_at_a_time(self) -> None:
        engine, document = _engine(), _document()
        engine.record_findings(document, [_finding("a")])
        engine.record_findings(document, [_finding("b")])

        engine.undo_last_transaction(document)
        assert document.state == {"a": "on", "b": "off"}

        engine.undo_last_transaction(document)
        assert document.state == {"a": "off", "b": "off"}

    def test_proposals_are_not_a_transaction_to_undo(self) -> None:
        # A batch that changed nothing must not shadow the last real change,
        # or undo would appear to do nothing.
        engine, document = _engine(), _document()
        engine.record_findings(document, [_finding("a")])
        engine.record_findings(document, [_finding("b", auto_apply=False)])

        engine.undo_last_transaction(document)

        assert document.state["a"] == "off"

    def test_a_rejected_decision_is_never_reverted(self) -> None:
        # REVERTED is non-terminal, so reverting a REJECTED record would
        # silently re-open a closed question and re-block export.
        engine, document = _engine(), _document()
        document.corrections.append(_record("txn-1", status=CorrectionStatus.REJECTED))

        assert engine.undo_last_transaction(document) == []
        assert document.corrections[0].status is CorrectionStatus.REJECTED

    def test_undoing_nothing_is_not_an_error(self) -> None:
        assert _engine().undo_last_transaction(_document()) == []

    def test_undo_is_idempotent_at_the_bottom_of_the_stack(self) -> None:
        engine, document = _engine(), _document()
        engine.record_findings(document, [_finding("a")])
        engine.undo_last_transaction(document)

        assert engine.undo_last_transaction(document) == []
        assert document.state["a"] == "off"


class TestOutOfOrderUndoIsRefused:
    def test_naming_an_older_transaction_is_refused(self) -> None:
        engine, document = _engine(), _document()
        engine.record_findings(document, [_finding("a")])
        older = document.corrections[0].transaction_id
        engine.record_findings(document, [_finding("b")])

        with pytest.raises(NonLifoUndoError):
            engine.undo_last_transaction(document, expect_transaction_id=older)

    def test_a_refusal_changes_nothing(self) -> None:
        engine, document = _engine(), _document()
        engine.record_findings(document, [_finding("a")])
        older = document.corrections[0].transaction_id
        engine.record_findings(document, [_finding("b")])

        with pytest.raises(NonLifoUndoError):
            engine.undo_last_transaction(document, expect_transaction_id=older)

        assert document.state == {"a": "on", "b": "on"}
        assert all(c.status is CorrectionStatus.AUTO_APPLIED for c in document.corrections)

    def test_naming_the_most_recent_transaction_succeeds(self) -> None:
        engine, document = _engine(), _document()
        engine.record_findings(document, [_finding("a")])
        newest = document.corrections[0].transaction_id

        assert engine.undo_last_transaction(document, expect_transaction_id=newest)


class TestStatusPartition:
    def test_applied_and_non_terminal_do_not_overlap(self) -> None:
        # A status cannot both have changed the document and still be awaiting
        # a decision; REVERTED belongs to the second set only.
        from src.models.correction import NON_TERMINAL_STATUSES

        assert not (APPLIED_STATUSES & NON_TERMINAL_STATUSES)
        assert CorrectionStatus.REVERTED in NON_TERMINAL_STATUSES
