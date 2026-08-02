"""Artifact suppression — turning L2 classifications into reversible decisions.

The seventh registered asset type, and the first that is *single-source*
by nature: there is no second provider to compare against, only RAWRS's
own layout evidence (``src/structure/layout_signals.py``). It follows the
precedent ``CalloutVerifier`` set (see docs/DECISIONS_LOG.md Part 23,
"empty PDF matcher, not a skipped verifier") — the framework was
explicitly designed to generalize beyond "always have two sources".

Why this module exists
----------------------
L2 has been attaching ``TextBlock.artifact`` since commit 9999418, and
until now exactly one thing read it: heading candidacy. Running headers,
running footers and page numbers therefore stayed in the rendered
Markdown and DOCX — the very content a human remediator deletes first,
and a measured benchmark KPI.

The naive fix (``if block.artifact: skip`` in the renderer) would have
made RAWRS silently delete content with no record and no undo, which is
precisely what docs/DECISIONS_LOG.md Part 22 ("Why CorrectionRecord, not
direct edit of Mathpix data") rejects. So suppression is expressed the
same way every other content change in RAWRS is: a Finding becomes a
CorrectionRecord, and only ``apply()`` mutates the document. Reject and
undo work through the existing corrections API with no new plumbing,
because ``SemanticVerifier.revert()`` is generic.

**Classification is not decision.** L2 says what a line *is*; this module
decides what to *do* about it. Keeping those separate is the point — the
same separation the future auto-remediation composer (L7) needs in order
to be a scheduler over transformations rather than a pile of heuristics.

Which classes are safe to act on, and why
-----------------------------------------
Measured over the 10-PDF benchmark corpus (178 artifact-classified
blocks). Confidence turned out to be the *wrong* gate: it is
``recurrence_ratio * positional_stability``, which measures how much of a
document a line covers, not how certain the classification is —
'FOLK PEDAGOGY' is a genuine running header scoring 0.135, while every
page number scores a flat 0.9 from a constant. Ranking by confidence
would suppress page numbers and keep running headers.

What actually separates the reliable classes is whether the
classification rests on **two independent signals** or on repetition
alone:

| class                | n  | signals                     | policy  |
|----------------------|----|-----------------------------|---------|
| PAGE_NUMBER          | 85 | printed-label match + zone  | AUTO    |
| RUNNING_HEADER       | 76 | repetition + HEADER zone    | AUTO    |
| RUNNING_FOOTER       | -  | repetition + FOOTER zone    | AUTO    |
| RUNNING_TITLE        | 4  | repetition only (BODY zone) | PROPOSE |
| DECORATIVE_REPEATED  | 13 | repetition only (BODY zone) | NEVER   |

DECORATIVE_REPEATED is excluded on evidence, not caution: across the
corpus it is catching repeated *body fragments* — 'or', 'practice.',
'for children.', 'Accountability,' — not decorations. Auto-suppressing it
would delete real prose; even proposing it would be reviewer noise. That
is a defect in the L2 classifier's fallback branch (repetition in the
BODY zone with no corroborating signal), recorded here and deliberately
not worked around by tuning a threshold. RUNNING_TITLE shares the same
single-signal weakness but its four corpus instances are all genuine, so
it is proposed for review rather than dropped or auto-applied.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from src.models.correction import CorrectionRecord
from src.models.text_block import ArtifactClass, TextBlock
from src.models.verification import Finding, RuleSpec
from src.verification.base import SemanticVerifier
from src.verification.matching import MatchResult, MultiSignalMatcher

ASSET_TYPE = "text_block"

# The Finding.kind this verifier produces. One kind, not one per artifact
# class: the *decision* is identical ("remove this line from rendered
# output") regardless of which classification produced it, and the
# artifact class travels in the evidence where a reviewer can see it.
SUPPRESS_ARTIFACT = "suppress_artifact"

# Encoded in Finding.original_value/proposed_value so the generic
# SemanticVerifier.revert() (which simply swaps the two and replays
# apply()) undoes a suppression with no verifier-specific undo logic.
VISIBLE = "visible"
SUPPRESSED = "suppressed"


class SuppressionPolicy(str, Enum):
    """What to do about one artifact class. See the module docstring's
    table for the corpus evidence behind each assignment."""

    AUTO = "auto"        # suppress immediately; recorded as AUTO_APPLIED
    PROPOSE = "propose"  # record as PROPOSED; a reviewer decides
    NEVER = "never"      # emit nothing at all


# Data, not branching: a new ArtifactClass adds a row here (and must,
# since _POLICY.get() returns None for an unknown class and unknown
# classes are never acted on).
_POLICY: Dict[ArtifactClass, SuppressionPolicy] = {
    ArtifactClass.PAGE_NUMBER: SuppressionPolicy.AUTO,
    ArtifactClass.RUNNING_HEADER: SuppressionPolicy.AUTO,
    ArtifactClass.RUNNING_FOOTER: SuppressionPolicy.AUTO,
    ArtifactClass.RUNNING_TITLE: SuppressionPolicy.PROPOSE,
    ArtifactClass.DECORATIVE_REPEATED: SuppressionPolicy.NEVER,
}


def block_id(block: TextBlock) -> str:
    """Stable identity for one TextBlock within its Document.

    Delegates to ``TextBlock.block_id``, where this scheme now lives — it
    was defined here first (L2.2), and P1 promoted it to the model so
    ContentNode and CorrectionRecord.object_id name blocks the same way
    rather than two modules agreeing by coincidence. Kept as a function
    because it is this module's documented call shape.
    """
    return block.block_id


def propose_suppressions(blocks: List[TextBlock]) -> Dict[SuppressionPolicy, List[Finding]]:
    """Turn L2 artifact classifications into suppression Findings.

    Returns findings grouped by policy so the caller records AUTO ones as
    AUTO_APPLIED (terminal — does not block export via REVIEW_001) and
    PROPOSE ones as PROPOSED. Pure: reads ``block.artifact``, mutates
    nothing. Blocks already suppressed are skipped so a re-run of the
    pipeline over a restored document does not duplicate corrections.
    """
    grouped: Dict[SuppressionPolicy, List[Finding]] = {
        SuppressionPolicy.AUTO: [],
        SuppressionPolicy.PROPOSE: [],
    }
    for block in blocks:
        classification = block.artifact
        if classification is None or block.suppressed:
            continue
        policy = _POLICY.get(classification.artifact_class)
        if policy is None or policy is SuppressionPolicy.NEVER:
            continue
        grouped[policy].append(
            Finding(
                asset_type=ASSET_TYPE,
                kind=SUPPRESS_ARTIFACT,
                object_id=block_id(block),
                confidence=classification.confidence,
                evidence="; ".join(classification.evidence),
                message=(
                    f"{classification.artifact_class.value.replace('_', ' ')} on page "
                    f"{block.page_number}: {block.text!r} is a document artifact, "
                    f"not content"
                ),
                original_value=VISIBLE,
                proposed_value=SUPPRESSED,
                # Autonomy travels on the finding: the engine records
                # AUTO ones AUTO_APPLIED and applies them, and leaves the
                # rest for a reviewer. See engine.record_findings.
                auto_apply=policy is SuppressionPolicy.AUTO,
            )
        )
    return grouped


def _find_block(document: Any, object_id: Optional[str]) -> Optional[TextBlock]:
    if not object_id:
        return None
    for block in getattr(document, "blocks", []):
        if block_id(block) == object_id:
            return block
    return None


class ArtifactSuppressionVerifier(SemanticVerifier):
    """Owns the ``text_block`` asset type for the correction rail.

    Only ``apply()`` and ``rule_table()`` carry real weight here. The
    matcher/canonical hooks exist because every asset type implements the
    same interface, and this type genuinely has nothing to match — see the
    module docstring on single-source assets.
    """

    asset_type = ASSET_TYPE

    def build_pdf_matcher(self) -> MultiSignalMatcher:
        """No second source: artifact classification is derived from this
        document's own layout, so there is nothing to pair against.
        Same documented default CalloutVerifier uses."""
        return MultiSignalMatcher([])

    def to_canonical(self, match_result: MatchResult, **context: Any) -> List[Any]:
        """A suppression creates no canonical object — it removes rendering
        of one that already exists. Always empty, by construction."""
        return []

    def classify(self, match_result: MatchResult, **context: Any) -> List[Finding]:
        """Not the producer for this asset type: suppression findings come
        from ``propose_suppressions(document.blocks)``, which reads L2
        evidence directly rather than a cross-source MatchResult. Returns
        empty so a caller that drives every verifier generically gets
        nothing rather than an error."""
        return []

    def inspect(self, document: Any, **context: Any) -> List[Finding]:
        """Every suppression this document's own layout evidence supports.

        The single-source producer hook (see SemanticVerifier.inspect).
        Living here rather than being called directly from the pipeline is
        what makes artifact suppression path-agnostic: the engine asks
        every registered verifier, so no pipeline branch decides whether
        this asset type participates.
        """
        grouped = propose_suppressions(getattr(document, "blocks", []))
        return grouped[SuppressionPolicy.AUTO] + grouped[SuppressionPolicy.PROPOSE]

    def rule_table(self) -> Dict[str, RuleSpec]:
        return {
            SUPPRESS_ARTIFACT: RuleSpec(
                rule_id="ARTIFACT_001",
                reason_code="RUNNING_ARTIFACT_SUPPRESSED",
                severity="info",
            )
        }

    def apply(self, document: Any, correction: CorrectionRecord) -> None:
        """Set (or clear) the block's live suppression state.

        Reads the target state from ``proposed_value`` rather than
        assuming "apply means suppress", which is what lets the generic
        ``SemanticVerifier.revert()`` — swap original/proposed, replay
        apply() — restore the line with no undo logic of its own. A
        correction whose block is gone (a document rebuilt with different
        blocks) is a no-op rather than an error: the audit row survives,
        the mutation simply has nothing to act on.
        """
        block = _find_block(document, correction.object_id)
        if block is None:
            return
        block.suppressed = correction.proposed_value == SUPPRESSED


def _register() -> None:
    # Imported inside the function, matching every other verifier module:
    # the engine must not import verifiers (it would be circular), so each
    # verifier registers itself when its own module is imported.
    from src.verification.engine import engine

    engine.register(ArtifactSuppressionVerifier())


_register()
