"""What reviewers decided about RAWRS's proposals, and what they changed themselves.

Reads the correction log every Document already carries (``CorrectionRecord``
plus its M-4.4 telemetry, which until now nothing read). Two populations, told
apart by who originated the record:

* **proposals** - RAWRS (a verifier, a cross-source check, artifact
  suppression) suggested or auto-applied a change. A reviewer's verdict on it
  is a label: was RAWRS right?
* **human edits** - a reviewer changed something RAWRS never proposed
  (provider ``manual_reviewer``, or a ``*_BY_REVIEWER`` / ``*_MANUAL_*`` /
  ``*_REVIEWED`` reason code). These show where detectors still miss.

Rates carry a Wilson score interval, so three acceptances out of three are not
reported as "100% right" (the lower bound is 44%), and nothing is recommended
below ``MIN_DECISIONS`` judgements. Recommendations are advice for a person;
nothing here changes what the pipeline does.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from statistics import median
from typing import Dict, Iterable, List, Optional, Tuple

from src.models.correction import CorrectionRecord, CorrectionStatus, CorrectionTelemetryAction

# Evidence thresholds. Named so the policy reads as policy, and tuned only
# with data: each is the bar a rule must clear, at 95% confidence.
MIN_DECISIONS = 30
AUTO_APPLY_FLOOR = 0.95  # lower bound of "reviewers agree" before suggesting auto-apply
AUTO_APPLY_MAX_EDIT_SHARE = 0.10  # ...and they rarely had to fix the proposed value
APPROACHING_FLOOR = 0.80  # reported as on its way to auto-apply, not yet there
RETIRE_CEILING = 0.20  # upper bound of "reviewers agree" below which a rule is noise
EDIT_SHARE_FLOOR = 0.30  # right place, wrong value this often -> improve the value
AUTO_UNDO_FLOOR = 0.05  # lower bound of "humans undo it" that questions auto-apply
Z_95 = 1.96
SHORT_VALUE = 40  # longer values are prose, not a pattern worth counting
TOP_CHANGES = 5

_HUMAN_PROVIDERS = frozenset({"manual_reviewer"})
_HUMAN_MARKERS = ("REVIEWER", "REVIEWED", "MANUAL")
_DECISION_ACTIONS = frozenset(
    {
        CorrectionTelemetryAction.ACCEPTED,
        CorrectionTelemetryAction.REJECTED,
        CorrectionTelemetryAction.EDITED,
        CorrectionTelemetryAction.IGNORED,
    }
)
_STATUS_OUTCOME = {
    CorrectionStatus.ACCEPTED: "accepted",
    CorrectionStatus.EDITED: "edited",
    CorrectionStatus.REJECTED: "rejected",
    CorrectionStatus.IGNORED: "ignored",
    CorrectionStatus.AUTO_APPLIED: "auto_kept",
}
OUTCOMES = ("accepted", "edited", "rejected", "ignored", "undone", "auto_kept", "auto_undone", "pending")


def wilson_interval(successes: int, trials: int, z: float = Z_95) -> Tuple[float, float]:
    """95% Wilson score interval for a binomial proportion; (0, 1) with no trials."""
    if trials <= 0:
        return 0.0, 1.0
    p = successes / trials
    denominator = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denominator
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def is_human_edit(correction: CorrectionRecord) -> bool:
    return correction.provider in _HUMAN_PROVIDERS or any(
        marker in correction.reason_code for marker in _HUMAN_MARKERS
    )


def outcome(correction: CorrectionRecord) -> str:
    """One of OUTCOMES: what finally happened to a RAWRS proposal."""
    if correction.status is CorrectionStatus.REVERTED:
        undone_from = {
            event.previous_status
            for event in correction.telemetry_events
            if event.action is CorrectionTelemetryAction.UNDONE
        }
        return "auto_undone" if CorrectionStatus.AUTO_APPLIED.value in undone_from else "undone"
    return _STATUS_OUTCOME.get(correction.status, "pending")


def _decision_seconds(correction: CorrectionRecord) -> List[float]:
    return [
        event.latency_seconds
        for event in correction.telemetry_events
        if event.action in _DECISION_ACTIONS and event.latency_seconds is not None
    ]


@dataclass
class RuleStats:
    object_type: str
    reason_code: str
    counts: Dict[str, int]
    documents: int
    decided: int
    precision: Optional[float]
    precision_low: float
    precision_high: float
    edit_share: Optional[float]
    auto_applied: int
    auto_undo_rate: Optional[float]
    median_decision_seconds: Optional[float]
    recommendation: str = ""
    rationale: str = ""


@dataclass
class HumanEditStats:
    object_type: str
    reason_code: str
    count: int
    documents: int
    top_changes: List[Dict[str, object]] = field(default_factory=list)


def _recommend(stats: RuleStats) -> Tuple[str, str]:
    counts = stats.counts
    auto_total = stats.auto_applied
    if auto_total >= MIN_DECISIONS:
        low, _ = wilson_interval(counts["auto_undone"], auto_total)
        if low >= AUTO_UNDO_FLOOR:
            return (
                "revisit_auto_apply",
                f"Reviewers undid it {counts['auto_undone']} of {auto_total} times after RAWRS applied it "
                f"automatically (at least {low:.0%} at 95% confidence) - consider proposing instead.",
            )
        if stats.decided < MIN_DECISIONS:
            return "auto_apply_holding", f"Applied automatically {auto_total} times, undone {counts['auto_undone']}."
    if stats.decided < MIN_DECISIONS:
        return (
            "collect_more",
            f"{stats.decided} reviewer judgements so far; {MIN_DECISIONS} are needed before recommending a change.",
        )
    positives = counts["accepted"] + counts["edited"]
    if stats.precision_low >= AUTO_APPLY_FLOOR and (stats.edit_share or 0.0) <= AUTO_APPLY_MAX_EDIT_SHARE:
        return (
            "candidate_auto_apply",
            f"Accepted {positives} of {stats.decided} times (at least {stats.precision_low:.0%} at 95% "
            "confidence) and rarely edited - a candidate to apply automatically, with undo.",
        )
    if stats.precision_high <= RETIRE_CEILING:
        return (
            "candidate_retire",
            f"Accepted only {positives} of {stats.decided} times (at most {stats.precision_high:.0%} at 95% "
            "confidence) - reviewers mostly reject it.",
        )
    if (stats.edit_share or 0.0) >= EDIT_SHARE_FLOOR:
        return (
            "improve_proposed_value",
            f"Reviewers agreed something was wrong but rewrote RAWRS's value {counts['edited']} of "
            f"{positives} times - the detection is right, the proposed value is not.",
        )
    if stats.precision_low >= APPROACHING_FLOOR:
        return (
            "approaching_auto_apply",
            f"Accepted {positives} of {stats.decided} times (at least {stats.precision_low:.0%} at 95% "
            f"confidence); auto-apply needs {AUTO_APPLY_FLOOR:.0%} - more consistent judgements will get it there.",
        )
    return "keep_asking", f"Accepted {positives} of {stats.decided} times - mixed enough that a person should decide."


def summarize(jobs: Iterable[Tuple[str, Iterable[CorrectionRecord]]]) -> Dict[str, object]:
    """Aggregate every job's correction log into per-rule statistics.

    ``jobs`` is ``(job_id, corrections)`` pairs. Returns JSON-ready dicts:
    ``rules`` (RAWRS proposals, by object type + reason code), ``human_edits``
    (changes reviewers originated) and ``totals``.
    """
    outcome_counts: Dict[Tuple[str, str], Counter] = defaultdict(Counter)
    rule_jobs: Dict[Tuple[str, str], set] = defaultdict(set)
    seconds: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    edit_counts: Counter = Counter()
    edit_jobs: Dict[Tuple[str, str], set] = defaultdict(set)
    edit_changes: Dict[Tuple[str, str], Counter] = defaultdict(Counter)
    job_ids: set = set()

    for job_id, corrections in jobs:
        for correction in corrections:
            job_ids.add(job_id)
            key = (correction.object_type, correction.reason_code or correction.field)
            if is_human_edit(correction):
                edit_counts[key] += 1
                edit_jobs[key].add(job_id)
                before, after = correction.original_value.strip(), correction.proposed_value.strip()
                if before != after and len(before) <= SHORT_VALUE and len(after) <= SHORT_VALUE:
                    edit_changes[key][(before, after)] += 1
                continue
            outcome_counts[key][outcome(correction)] += 1
            rule_jobs[key].add(job_id)
            seconds[key].extend(_decision_seconds(correction))

    rules: List[RuleStats] = []
    for key, counter in outcome_counts.items():
        counts = {name: counter.get(name, 0) for name in OUTCOMES}
        positives = counts["accepted"] + counts["edited"]
        decided = positives + counts["rejected"] + counts["undone"]
        low, high = wilson_interval(positives, decided)
        auto_total = counts["auto_kept"] + counts["auto_undone"]
        stats = RuleStats(
            object_type=key[0],
            reason_code=key[1],
            counts=counts,
            documents=len(rule_jobs[key]),
            decided=decided,
            precision=positives / decided if decided else None,
            precision_low=low,
            precision_high=high,
            edit_share=counts["edited"] / positives if positives else None,
            auto_applied=auto_total,
            auto_undo_rate=counts["auto_undone"] / auto_total if auto_total else None,
            median_decision_seconds=median(seconds[key]) if seconds[key] else None,
        )
        stats.recommendation, stats.rationale = _recommend(stats)
        rules.append(stats)
    rules.sort(key=lambda r: (-(r.decided + r.auto_applied), r.object_type, r.reason_code))

    human_edits = [
        HumanEditStats(
            object_type=key[0],
            reason_code=key[1],
            count=count,
            documents=len(edit_jobs[key]),
            top_changes=[
                {"from": before, "to": after, "count": n}
                for (before, after), n in edit_changes[key].most_common(TOP_CHANGES)
            ],
        )
        for key, count in edit_counts.most_common()
    ]

    return {
        "rules": [asdict(rule) for rule in rules],
        "human_edits": [asdict(edit) for edit in human_edits],
        "totals": {
            "documents": len(job_ids),
            "proposals": sum(sum(c.values()) for c in outcome_counts.values()),
            "human_edits": sum(edit_counts.values()),
        },
    }
