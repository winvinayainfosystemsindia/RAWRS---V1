"""The Document Merge Layer — generic KEEP / REPAIR / RECOVER / REMOVE
derivation.

Every AssetVerifier used to hand-write its own matched/unmatched_a/
unmatched_b loop (FigureAssetVerifier did this three times, ad hoc). This
module makes that decision once, generically, in two ways depending on
how many independent evidence sources a verifier has:

``compute_merge_decisions()`` — binary, one canonical (Mathpix) item vs.
one independently PDF-derived candidate, for any MatchResult:

- a matched pair the caller's ``is_mismatch`` predicate accepts  -> KEEP
- a matched pair the predicate rejects                           -> REPAIR
- an unmatched canonical (Mathpix) item                          -> KEEP
  (unconfirmed, not contradicted — a verifier's classify() may still flag
  this as low-confidence/missing, but the merge layer itself never removes
  or downgrades a Mathpix value just because the PDF side didn't confirm it)
- an unmatched PDF-side item                                     -> RECOVER

``decide_from_evidence()`` — N-source, for verifiers that accumulate an
arbitrary number of independent signals (Mathpix confidence, typography,
whitespace, running-header recurrence, targeted OCR, ...) into one
src/verification/evidence.py EvidenceBundle instead of a single pairwise
match (FEATURE_019 — see HeadingVerifier and CalloutVerifier).

REMOVE exists as a MergeAction (only decide_from_evidence() ever returns
it — compute_merge_decisions() never does) but the project's standing
safety invariant is otherwise unchanged: RAWRS never removes content
automatically. Every MergeAction, REMOVE included, only ever becomes a
CorrectionStatus.PROPOSED CorrectionRecord (see
engine.findings_to_corrections()) — a human must explicitly Accept it via
the Corrections API before anything is actually removed from the
document. Low confidence alone never produces REMOVE either (mirroring
the "unconfirmed, not contradicted" KEEP rule above) — only low
confidence *combined with* evidence that actively contradicts the
canonical value does.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, List, Optional

from src.verification.evidence import EvidenceBundle
from src.verification.matching import MatchResult


class MergeAction(str, Enum):
    KEEP = "keep"
    REPAIR = "repair"
    RECOVER = "recover"
    REMOVE = "remove"


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


@dataclass
class ConfidenceThresholds:
    """The confidence boundary that turns an EvidenceBundle's fused score
    into a MergeAction (see decide_from_evidence() below). Default is
    conservative; pass a different instance to tune per asset type.
    """

    repair: float = 0.5   # >= this: evidence is trusted enough to act on


def decide_from_evidence(
    bundle: EvidenceBundle,
    has_canonical: bool,
    is_mismatch: bool = False,
    thresholds: ConfidenceThresholds = ConfidenceThresholds(),
) -> MergeAction:
    """Turn a fused, N-source EvidenceBundle into one MergeAction.

    Complements compute_merge_decisions() (binary: one canonical vs. one
    PDF-derived candidate) for verifiers that accumulate an arbitrary
    number of independent signals instead — e.g. HeadingVerifier's
    Mathpix-confidence + typography + whitespace + running-header-
    recurrence bundle (FEATURE_019).

    has_canonical: True when a Mathpix-sourced object already exists for
        this candidate. False means there is nothing to keep/repair/
        remove — only RECOVER is possible, mirroring
        compute_merge_decisions()'s unmatched_b -> RECOVER case.
    is_mismatch: True when the evidence-preferred value differs from the
        canonical value. Ignored when has_canonical is False.

    Confidence at or above the threshold -> KEEP (no mismatch) or REPAIR
    (mismatch); the exact confidence number still travels with the
    resulting Finding, so a reviewer always sees how sure RAWRS was, not
    just which of these four buckets it landed in. Confidence below the
    threshold with no mismatch -> KEEP, the same "unconfirmed, not
    contradicted" rule compute_merge_decisions() already applies — weak
    evidence is never grounds to challenge Mathpix on its own. Confidence
    below the threshold *with* a mismatch -> REMOVE: evidence this weak
    that still actively disagrees with the canonical value is more often
    "this object doesn't belong at all" (e.g. a running header
    misclassified as a heading) than "the right value is slightly
    different." REMOVE is always emitted as a PROPOSED CorrectionRecord —
    see this module's docstring.
    """
    if not has_canonical:
        return MergeAction.RECOVER

    if bundle.confidence >= thresholds.repair:
        return MergeAction.REPAIR if is_mismatch else MergeAction.KEEP
    return MergeAction.REMOVE if is_mismatch else MergeAction.KEEP
