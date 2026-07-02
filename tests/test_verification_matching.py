"""Tests for src/verification/matching.py's MultiSignalMatcher.

Deliberately uses toy types instead of any RAWRS domain object (Image,
Figure, ...) to prove the matcher is genuinely asset-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.verification.matching import MultiSignalMatcher, WeightedSignal


@dataclass
class Left:
    tag: str


@dataclass
class Right:
    tag: str


def _exact_tag_signal(a: Left, b: Right) -> Optional[float]:
    return 1.0 if a.tag == b.tag else None


def _weak_constant_signal(_a: Left, _b: Right) -> Optional[float]:
    return 0.1


class TestPriorityOrder:
    def test_high_priority_signal_wins_over_fallback(self) -> None:
        matcher = MultiSignalMatcher(
            [
                WeightedSignal(name="exact", fn=_exact_tag_signal, min_confidence=0.9),
                WeightedSignal(name="fallback", fn=_weak_constant_signal, min_confidence=0.01),
            ]
        )
        a1, a2 = Left("x"), Left("y")
        b1, b2 = Right("y"), Right("x")

        result = matcher.match([a1, a2], [b1, b2])

        matched_by_name = {(p.a.tag, p.b.tag): p.matched_by for p in result.pairs}
        assert matched_by_name[("x", "x")] == "exact"
        assert matched_by_name[("y", "y")] == "exact"
        assert result.unmatched_a == []
        assert result.unmatched_b == []

    def test_positional_fallback_only_used_when_nothing_else_matches(self) -> None:
        matcher = MultiSignalMatcher(
            [
                WeightedSignal(name="exact", fn=_exact_tag_signal, min_confidence=0.9),
                WeightedSignal(name="fallback", fn=_weak_constant_signal, min_confidence=0.01),
            ]
        )
        a1, a2 = Left("no-match-1"), Left("no-match-2")
        b1, b2 = Right("other-1"), Right("other-2")

        result = matcher.match([a1, a2], [b1, b2])

        assert len(result.pairs) == 2
        assert all(p.matched_by == "fallback" for p in result.pairs)
        # Stable-sort + insertion-order encounter guarantees index-aligned
        # pairing when every candidate scores identically.
        assert (result.pairs[0].a.tag, result.pairs[0].b.tag) == ("no-match-1", "other-1")
        assert (result.pairs[1].a.tag, result.pairs[1].b.tag) == ("no-match-2", "other-2")


class TestThresholds:
    def test_signal_below_its_own_threshold_never_claims(self) -> None:
        def _always_low(_a, _b) -> Optional[float]:
            return 0.2

        matcher = MultiSignalMatcher([WeightedSignal(name="low", fn=_always_low, min_confidence=0.5)])
        result = matcher.match([Left("a")], [Right("a")])
        assert result.pairs == []
        assert len(result.unmatched_a) == 1
        assert len(result.unmatched_b) == 1

    def test_signal_returning_none_is_treated_as_inapplicable_not_rejected(self) -> None:
        def _no_opinion(_a, _b) -> Optional[float]:
            return None

        matcher = MultiSignalMatcher(
            [
                WeightedSignal(name="no_opinion", fn=_no_opinion, min_confidence=0.0),
                WeightedSignal(name="fallback", fn=_weak_constant_signal, min_confidence=0.01),
            ]
        )
        result = matcher.match([Left("a")], [Right("a")])
        assert len(result.pairs) == 1
        assert result.pairs[0].matched_by == "fallback"


class TestUnmatched:
    def test_extra_a_items_are_unmatched(self) -> None:
        matcher = MultiSignalMatcher([WeightedSignal(name="exact", fn=_exact_tag_signal, min_confidence=0.9)])
        result = matcher.match([Left("x"), Left("y")], [Right("x")])
        assert len(result.pairs) == 1
        assert [a.tag for a in result.unmatched_a] == ["y"]
        assert result.unmatched_b == []

    def test_extra_b_items_are_unmatched(self) -> None:
        matcher = MultiSignalMatcher([WeightedSignal(name="exact", fn=_exact_tag_signal, min_confidence=0.9)])
        result = matcher.match([Left("x")], [Right("x"), Right("y")])
        assert len(result.pairs) == 1
        assert result.unmatched_a == []
        assert [b.tag for b in result.unmatched_b] == ["y"]

    def test_empty_inputs_produce_empty_result(self) -> None:
        matcher = MultiSignalMatcher([WeightedSignal(name="exact", fn=_exact_tag_signal, min_confidence=0.9)])
        result = matcher.match([], [])
        assert result.pairs == []
        assert result.unmatched_a == []
        assert result.unmatched_b == []


class TestIdentityNotEquality:
    def test_value_equal_but_distinct_items_are_claimed_independently(self) -> None:
        """Two items that compare equal by value must still be matchable
        to two different partners — the matcher tracks by identity, not
        value equality."""
        a1, a2 = Left("dup"), Left("dup")
        b1, b2 = Right("dup"), Right("dup")
        matcher = MultiSignalMatcher([WeightedSignal(name="exact", fn=_exact_tag_signal, min_confidence=0.9)])

        result = matcher.match([a1, a2], [b1, b2])

        assert len(result.pairs) == 2
        assert result.unmatched_a == []
        assert result.unmatched_b == []
