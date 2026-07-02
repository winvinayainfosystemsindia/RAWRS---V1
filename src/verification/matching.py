"""Generic multi-signal, priority-cascade matcher.

Asset-agnostic: this module has no knowledge of figures, images, headings,
or any other RAWRS domain type.  It matches two lists of arbitrary items
(``a_items`` of type ``A``, ``b_items`` of type ``B``) using an ordered list
of "signals" — functions that score how confidently a given (a, b) pair
refers to the same real-world thing.

Signals run in priority order.  Each signal only sees items neither an
earlier signal nor itself has already claimed, so a low-priority signal
(e.g. positional/document-order) never gets a chance to steal a pair a
higher-priority signal (e.g. an exact filename match) already resolved.
The last signal in any caller's list is expected to be a fallback (e.g.
positional matching) — this module doesn't enforce that, but callers
should order their signal lists that way, weakest/most-generic last.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Generic, List, Optional, TypeVar

A = TypeVar("A")
B = TypeVar("B")

# Returns a confidence in [0.0, 1.0], or None if this signal simply doesn't
# apply to this pair (not "doesn't match" — "has no opinion").
MatchSignal = Callable[[A, B], Optional[float]]


@dataclass
class WeightedSignal(Generic[A, B]):
    """One matching strategy plus the confidence threshold it can decide on."""

    name: str
    fn: MatchSignal
    min_confidence: float = 0.5


@dataclass
class MatchedPair(Generic[A, B]):
    """A resolved match, tagged with which signal produced it and how sure it was."""

    a: A
    b: B
    confidence: float
    matched_by: str


@dataclass
class MatchResult(Generic[A, B]):
    pairs: List[MatchedPair] = field(default_factory=list)
    unmatched_a: List[A] = field(default_factory=list)
    unmatched_b: List[B] = field(default_factory=list)


class MultiSignalMatcher(Generic[A, B]):
    """Matches two item lists by running signals in priority order.

    For each signal (in list order): score every remaining (a, b) pair,
    keep only scores >= that signal's min_confidence, then greedily claim
    pairs highest-score-first (each a/b can be claimed at most once this
    pass). Whatever remains unmatched is handed to the next signal.
    """

    def __init__(self, signals: List[WeightedSignal[A, B]]):
        self._signals = signals

    def match(self, a_items: List[A], b_items: List[B]) -> MatchResult[A, B]:
        # Tracked by id() rather than value equality — two distinct items
        # that happen to compare equal (e.g. two figures with the same
        # caption) must still be claimable independently.
        remaining_a = {id(a): a for a in a_items}
        remaining_b = {id(b): b for b in b_items}
        pairs: List[MatchedPair] = []

        for signal in self._signals:
            if not remaining_a or not remaining_b:
                break

            scored: List[tuple] = []
            for a in remaining_a.values():
                for b in remaining_b.values():
                    confidence = signal.fn(a, b)
                    if confidence is not None and confidence >= signal.min_confidence:
                        scored.append((confidence, a, b))

            if not scored:
                continue

            scored.sort(key=lambda t: t[0], reverse=True)
            for confidence, a, b in scored:
                if id(a) not in remaining_a or id(b) not in remaining_b:
                    continue
                pairs.append(MatchedPair(a=a, b=b, confidence=confidence, matched_by=signal.name))
                del remaining_a[id(a)]
                del remaining_b[id(b)]

        return MatchResult(
            pairs=pairs,
            unmatched_a=list(remaining_a.values()),
            unmatched_b=list(remaining_b.values()),
        )
