"""The Document Merge Layer — generic KEEP / REPAIR / RECOVER derivation.

Every AssetVerifier used to hand-write its own matched/unmatched_a/
unmatched_b loop (FigureAssetVerifier did this three times, ad hoc). This
module makes that decision once, generically, for any MatchResult:

- a matched pair the caller's ``is_mismatch`` predicate accepts  -> KEEP
- a matched pair the predicate rejects                           -> REPAIR
- an unmatched canonical (Mathpix) item                          -> KEEP
  (unconfirmed, not contradicted — a verifier's classify() may still flag
  this as low-confidence/missing, but the merge layer itself never removes
  or downgrades a Mathpix value just because the PDF side didn't confirm it)
- an unmatched PDF-side item                                     -> RECOVER

REMOVE is deliberately not a MergeAction. Per the project's standing
invariant, RAWRS never removes content automatically — removal is always a
reviewer-initiated ReviewAction (see src/models/correction.py), never
something a verifier's classify() computes on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, List, Optional

from src.verification.matching import MatchResult


class MergeAction(str, Enum):
    KEEP = "keep"
    REPAIR = "repair"
    RECOVER = "recover"


@dataclass
class MergeDecision:
    """One resolved KEEP/REPAIR/RECOVER decision for a single object.

    ``canonical`` is the existing (typically Mathpix-sourced) object, when
    one exists. ``pdf_evidence`` is the independently PDF-derived candidate,
    when one exists. Exactly one of the two is None for RECOVER (no
    canonical yet) — both are set for KEEP/REPAIR.
    """

    action: MergeAction
    canonical: Optional[Any]
    pdf_evidence: Optional[Any]
    confidence: Optional[float]
    signal: Optional[str]


def compute_merge_decisions(
    match_result: MatchResult, is_mismatch: Callable[[Any, Any], bool]
) -> List[MergeDecision]:
    """One generic pass over any MatchResult.

    ``is_mismatch(canonical, pdf_evidence) -> bool`` is the only
    asset-specific input — everything else here is shape, not domain
    knowledge.
    """
    decisions: List[MergeDecision] = []

    for pair in match_result.pairs:
        action = MergeAction.REPAIR if is_mismatch(pair.a, pair.b) else MergeAction.KEEP
        decisions.append(
            MergeDecision(
                action=action,
                canonical=pair.a,
                pdf_evidence=pair.b,
                confidence=pair.confidence,
                signal=pair.matched_by,
            )
        )

    for a in match_result.unmatched_a:
        decisions.append(
            MergeDecision(action=MergeAction.KEEP, canonical=a, pdf_evidence=None, confidence=None, signal=None)
        )

    for b in match_result.unmatched_b:
        decisions.append(
            MergeDecision(action=MergeAction.RECOVER, canonical=None, pdf_evidence=b, confidence=None, signal=None)
        )

    return decisions
