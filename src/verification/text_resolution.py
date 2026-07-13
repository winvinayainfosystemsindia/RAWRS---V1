"""Generic semantic-object-to-PDF-region text resolution (M-5.3).

Every registered verifier that needs to find "where in the PDF does this
canonical object's text actually appear" faces the same problem
src/verification/headings.py's typography/whitespace/targeted-OCR signals
discovered on real documents (M-5.2's benchmark): an exact string-equality
lookup between two independently-produced text representations (Mathpix's
own text vs. PyMuPDF's own per-line extraction) rarely succeeds, because
the two paths segment/normalize text differently even when they agree on
content.

This is layered TEXT-TO-KEY resolution, not an object-identity decision —
that remains MultiSignalMatcher's job (src/verification/matching.py),
matching two canonical objects' *signals* to decide KEEP/REPAIR/RECOVER.
TextResolver answers a narrower, lower-level question: given one page's
dict of {raw_pdf_line_text: value} and a target string from a different
source, which (if any) key is "the same line"? Not extending
MultiSignalMatcher, since that operates on paired object lists via
weighted signals for an identity decision — a different abstraction level
than resolving one string against one page's raw-text dict.

Tiers, cheapest and safest first (a real diagnostic run against the
benchmark corpus — not a synthetic guess — shaped this ordering):

  1. Exact match.
  2. Normalized match (unicode NFKC, casefold, whitespace-collapsed,
     punctuation-stripped) — computed once per page at TextResolver
     construction, not per lookup.
  3. Containment match: after normalization, one string entirely
     contains the other. Handles the dominant real failure mode the
     benchmark diagnostic surfaced — a running header ("Folk Pedagogy")
     that doesn't equal any single PyMuPDF line because PyMuPDF grouped
     it with adjacent text (e.g. a page number) into one combined line.
     Only applied when exactly one candidate satisfies it — an
     ambiguous multi-match is a miss, not a guess.
  4. Fuzzy similarity (difflib), guarded by a minimum target length.
     Real example from the same diagnostic: Mathpix heading "47" vs.
     the actual nearby PDF text "49" — a single-digit difference, near
     the top of any reasonable similarity threshold, but a wrong match.
     Short strings (stray page-number "headings", single words) are
     exactly where fuzzy matching produces a confident-looking wrong
     answer, so it never runs below _MIN_FUZZY_LENGTH.
  5. No match. The existing graceful "signal unavailable" fallback
     already present in every caller (see headings.py's None-returning
     signal builders) handles this — reviewer intervention happens
     through the existing Finding/CorrectionRecord review flow, not a
     6th tier here.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Dict, Generic, List, Optional, Tuple, TypeVar

T = TypeVar("T")

_PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")

_MIN_FUZZY_LENGTH = 6
_FUZZY_SIMILARITY_THRESHOLD = 0.75


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = _PUNCTUATION_RE.sub("", normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip().casefold()
    return normalized


class TextResolver(Generic[T]):
    """Wraps one page's {raw_pdf_text: value} dict. Normalization is
    computed once here, at construction — build one TextResolver per
    page and reuse it across every candidate object on that page, rather
    than re-normalizing the same page's lines once per object (the
    "cached normalization" this module's docstring commits to).
    """

    def __init__(self, candidates: Dict[str, T]) -> None:
        self._candidates = candidates
        self._normalized: Dict[str, List[Tuple[str, T]]] = {}
        for raw_key, value in candidates.items():
            self._normalized.setdefault(_normalize(raw_key), []).append((raw_key, value))

    def resolve(self, target: str) -> Optional[Tuple[T, str]]:
        """Returns (value, tier_name) for the first tier that produces an
        unambiguous match, or None if every tier misses."""
        if target in self._candidates:
            return self._candidates[target], "exact"

        normalized_target = _normalize(target)
        if not normalized_target:
            return None

        # An ambiguous match at any tier stops resolution entirely rather
        # than falling through to a less reliable tier — a later tier
        # (fuzzy) has no way to correctly break a tie an earlier, more
        # precise tier already found genuinely ambiguous; falling through
        # would silently let fuzzy matching "resolve" an ambiguity a
        # stricter tier deliberately declined to guess at.
        exact_normalized = self._normalized.get(normalized_target)
        if exact_normalized:
            return (exact_normalized[0][1], "normalized") if len(exact_normalized) == 1 else None

        contains_matches = [
            (raw_key, value)
            for raw_key, value in self._candidates.items()
            if normalized_target in _normalize(raw_key) or _normalize(raw_key) in normalized_target
        ]
        if contains_matches:
            return (contains_matches[0][1], "containment") if len(contains_matches) == 1 else None

        if len(normalized_target) >= _MIN_FUZZY_LENGTH:
            best = difflib.get_close_matches(
                normalized_target, list(self._normalized.keys()), n=1, cutoff=_FUZZY_SIMILARITY_THRESHOLD
            )
            if best:
                fuzzy_candidates = self._normalized[best[0]]
                if len(fuzzy_candidates) == 1:
                    return fuzzy_candidates[0][1], "fuzzy"

        return None
