"""src/learning/decisions.py - reviewer verdicts on RAWRS's proposals."""

from datetime import datetime, timezone

import pytest

from src.learning.decisions import (
    MIN_DECISIONS,
    is_human_edit,
    outcome,
    summarize,
    wilson_interval,
)
from src.models.correction import (
    CorrectionRecord,
    CorrectionStatus,
    CorrectionTelemetryAction,
    CorrectionTelemetryEvent,
)


def _record(status, reason_code="HEADING_LEVEL_MISMATCH", provider="mathpix", latency=None,
            original="3", proposed="1", object_type="heading"):
    record = CorrectionRecord(object_type=object_type, field="level_mismatch", original_value=original,
                              proposed_value=proposed, reason_code=reason_code, provider=provider, status=status)
    if latency is not None:
        record.telemetry_events.append(CorrectionTelemetryEvent(
            correction_id=record.correction_id, timestamp=datetime.now(timezone.utc),
            action=CorrectionTelemetryAction.ACCEPTED, latency_seconds=latency))
    return record


def _undone(previous):
    record = _record(CorrectionStatus.REVERTED)
    record.telemetry_events.append(CorrectionTelemetryEvent(
        correction_id=record.correction_id, timestamp=datetime.now(timezone.utc),
        action=CorrectionTelemetryAction.UNDONE, previous_status=previous))
    return record


def _rule(summary, reason_code="HEADING_LEVEL_MISMATCH"):
    return next(r for r in summary["rules"] if r["reason_code"] == reason_code)


def test_wilson_interval_matches_reference_values():
    low, high = wilson_interval(3, 3)
    assert low == pytest.approx(0.4385, abs=1e-4) and high == 1.0
    low, high = wilson_interval(50, 100)
    assert (low, high) == (pytest.approx(0.4038, abs=1e-4), pytest.approx(0.5962, abs=1e-4))
    assert wilson_interval(0, 0) == (0.0, 1.0)


@pytest.mark.parametrize("status, expected", [
    (CorrectionStatus.ACCEPTED, "accepted"),
    (CorrectionStatus.EDITED, "edited"),
    (CorrectionStatus.REJECTED, "rejected"),
    (CorrectionStatus.IGNORED, "ignored"),
    (CorrectionStatus.AUTO_APPLIED, "auto_kept"),
    (CorrectionStatus.PROPOSED, "pending"),
    (CorrectionStatus.PENDING_REVIEW, "pending"),
])
def test_outcome_from_status(status, expected):
    assert outcome(_record(status)) == expected


def test_undo_of_an_auto_applied_correction_is_told_apart():
    assert outcome(_undone("auto_applied")) == "auto_undone"
    assert outcome(_undone("accepted")) == "undone"


def test_human_edits_are_recognised_by_provider_or_reason_code():
    assert is_human_edit(_record(CorrectionStatus.EDITED, provider="manual_reviewer"))
    assert is_human_edit(_record(CorrectionStatus.EDITED, reason_code="PAGE_LABEL_MANUAL_REVIEW", provider="rawrs_native"))
    assert is_human_edit(_record(CorrectionStatus.EDITED, reason_code="FIGURE_ALT_TEXT_REVIEWED"))
    assert not is_human_edit(_record(CorrectionStatus.ACCEPTED))


def test_reliably_accepted_rule_becomes_auto_apply_candidate():
    jobs = [("job-a", [_record(CorrectionStatus.ACCEPTED, latency=4.0) for _ in range(80)])]
    rule = _rule(summarize(jobs))
    assert rule["recommendation"] == "candidate_auto_apply"
    assert rule["decided"] == 80
    assert rule["median_decision_seconds"] == 4.0


def test_forty_out_of_forty_is_promising_but_not_yet_proof():
    # Wilson lower bound of 40/40 is ~91%: below the 95% bar auto-apply needs.
    rule = _rule(summarize([("j", [_record(CorrectionStatus.ACCEPTED) for _ in range(MIN_DECISIONS + 10)])]))
    assert rule["recommendation"] == "approaching_auto_apply"
    assert "auto-apply needs 95%" in rule["rationale"]


def test_mostly_rejected_rule_becomes_retire_candidate():
    records = [_record(CorrectionStatus.REJECTED) for _ in range(40)] + [_record(CorrectionStatus.ACCEPTED)]
    assert _rule(summarize([("j", records)]))["recommendation"] == "candidate_retire"


def test_often_edited_rule_needs_a_better_proposed_value():
    records = [_record(CorrectionStatus.ACCEPTED) for _ in range(20)] + [_record(CorrectionStatus.EDITED) for _ in range(20)]
    assert _rule(summarize([("j", records)]))["recommendation"] == "improve_proposed_value"


def test_too_few_judgements_recommend_nothing():
    rule = _rule(summarize([("j", [_record(CorrectionStatus.ACCEPTED) for _ in range(5)])]))
    assert rule["recommendation"] == "collect_more"
    assert rule["precision"] == 1.0 and rule["precision_low"] < 0.6


def test_frequently_undone_auto_apply_is_flagged():
    records = [_record(CorrectionStatus.AUTO_APPLIED) for _ in range(30)] + [_undone("auto_applied") for _ in range(10)]
    rule = _rule(summarize([("j", records)]))
    assert rule["recommendation"] == "revisit_auto_apply"
    assert rule["auto_applied"] == 40 and rule["auto_undo_rate"] == 0.25


def test_pending_and_ignored_do_not_count_as_judgements():
    records = [_record(CorrectionStatus.PROPOSED), _record(CorrectionStatus.IGNORED), _record(CorrectionStatus.ACCEPTED)]
    rule = _rule(summarize([("j", records)]))
    assert rule["decided"] == 1
    assert rule["counts"]["pending"] == 1 and rule["counts"]["ignored"] == 1


def test_human_edits_are_counted_separately_with_their_common_changes():
    edits = [_record(CorrectionStatus.EDITED, reason_code="HEADING_LEVEL_MANUAL_EDIT", provider="manual_reviewer",
                     original="2", proposed="3") for _ in range(3)]
    edits.append(_record(CorrectionStatus.EDITED, reason_code="HEADING_LEVEL_MANUAL_EDIT", provider="manual_reviewer",
                         original="1", proposed="2"))
    summary = summarize([("a", edits[:2]), ("b", edits[2:])])
    assert summary["rules"] == []
    edit = summary["human_edits"][0]
    assert (edit["reason_code"], edit["count"], edit["documents"]) == ("HEADING_LEVEL_MANUAL_EDIT", 4, 2)
    assert edit["top_changes"][0] == {"from": "2", "to": "3", "count": 3}
    assert summary["totals"] == {"documents": 2, "proposals": 0, "human_edits": 4}


def test_long_values_are_not_counted_as_patterns():
    long = "x" * 200
    summary = summarize([("j", [_record(CorrectionStatus.EDITED, provider="manual_reviewer",
                                        reason_code="PARAGRAPH_TEXT_EDITED_BY_REVIEWER", original=long, proposed=long + "y")])])
    assert summary["human_edits"][0]["top_changes"] == []
