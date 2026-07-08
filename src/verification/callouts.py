"""Callouts: the fourth asset type registered with the cross-source
verification engine, and the first that exists purely to prove the
Evidence Fusion Engine (FEATURE_019) generalizes beyond the asset types it
was built and proven against (Heading, List, Table) — see the forensic
audit (RAWRS_forensic_audit.md, DEF-04): a Case Study/Thinking Point/Key
Ideas/Summary/Activity box had no semantic object to become at all before
this, only a heading (if headings even survived to render).

Every Callout in document.callouts already passed
src/mathpix/mmd_parser.py::classify_callout_type()'s label-pattern match
by construction — there is no independent, geometric PDF-side box
detector to cross-verify against yet (that is a separate, larger future
detector: recognizing a bordered/shaded region in the PDF's own drawing
commands). build_pdf_matcher() is therefore deliberately an empty-signal
matcher (the same documented default SemanticVerifier.build_import_matcher()
already uses for "no second source to match against" asset types, applied
here to the PDF-verification path instead) — every callout is
"unmatched_a", and classify() builds its EvidenceBundle from signals that
don't require PDF geometry: label-pattern specificity (a numbered "Case
study 11.2" is much stronger evidence than a bare "Summary", which is
common enough as an ordinary section title to be genuinely ambiguous) and
whether the anchoring Heading this Callout references is still intact.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from src.models.callout import Callout
from src.models.correction import CorrectionRecord
from src.models.verification import Finding, RuleSpec, VerificationStatus
from src.verification.base import SemanticVerifier
from src.verification.evidence import EvidenceBundle, EvidenceSignal
from src.verification.matching import MatchResult, MultiSignalMatcher
from src.verification.merge import MergeAction, decide_from_evidence

# A label containing an explicit "N.M" number (e.g. "11.2") is much
# stronger evidence of a real, deliberately-numbered boxed aside than a
# bare keyword match — "Summary" alone is common enough as an ordinary
# section title that keyword-only matches are genuinely ambiguous.
_NUMBERED_LABEL_RE = re.compile(r"\d+\.\d+")


def _label_pattern_signal(callout: Callout) -> EvidenceSignal:
    if _NUMBERED_LABEL_RE.search(callout.label):
        return EvidenceSignal(
            name="label_pattern",
            score=0.95,
            weight=1.5,
            note=f"'{callout.label}' matches a numbered {callout.callout_type} label",
        )
    return EvidenceSignal(
        name="label_pattern",
        score=0.6,
        weight=1.5,
        note=f"'{callout.label}' matches {callout.callout_type} by keyword only, no numbering",
    )


def _heading_intact_signal(callout: Callout, document: Any) -> Optional[EvidenceSignal]:
    """Sanity/integrity check: the Heading this Callout anchors to should
    still exist in document.headings. None when no document was supplied
    in context (e.g. a unit test exercising classify() in isolation)."""
    if document is None:
        return None
    headings = getattr(document, "headings", None)
    if headings is None:
        return None
    intact = any(h.id == callout.heading_id for h in headings)
    return EvidenceSignal(
        name="heading_intact",
        score=1.0 if intact else 0.0,
        weight=1.0,
        note="anchoring heading present" if intact else "anchoring heading missing — likely a stale reference",
    )


class CalloutVerifier(SemanticVerifier):
    asset_type = "callout"

    def build_pdf_matcher(self) -> MultiSignalMatcher:
        """No independent PDF-side candidate source exists yet (see
        module docstring) — every callout goes through classify() as
        unmatched_a, exactly as build_import_matcher()'s own documented
        default already does for asset types with no second source."""
        return MultiSignalMatcher([])

    def to_canonical(self, match_result: MatchResult, **context: Any) -> List[Callout]:
        """Callouts arrive from Mathpix already built (src/mathpix/ingestor.py)
        — same reasoning as Heading/List. Identity passthrough."""
        return list(match_result.unmatched_a) + [pair.a for pair in match_result.pairs]

    def classify(self, match_result: MatchResult, **context: Any) -> List[Finding]:
        findings: List[Finding] = []
        document = context.get("document")

        for callout in match_result.unmatched_a:
            bundle = EvidenceBundle()
            bundle.add(_label_pattern_signal(callout))
            heading_signal = _heading_intact_signal(callout, document)
            if heading_signal is not None:
                bundle.add(heading_signal)
            callout.confidence = bundle.confidence

            action = decide_from_evidence(bundle, has_canonical=True, is_mismatch=bundle.confidence < 0.5)
            if action != MergeAction.REMOVE:
                callout.verification_status = VerificationStatus.VERIFIED
                continue

            callout.verification_status = VerificationStatus.LOW_CONFIDENCE
            findings.append(
                Finding(
                    asset_type=self.asset_type,
                    kind="weak_callout_label",
                    object_id=callout.id,
                    confidence=bundle.confidence,
                    evidence=bundle.explanation,
                    message=(
                        f"'{callout.label}' was classified as a {callout.callout_type} callout "
                        "on weak evidence — likely an ordinary heading, not a boxed aside."
                    ),
                    original_value=callout.callout_type,
                    proposed_value="",
                    evidence_items=list(bundle.signals),
                )
            )

        return findings

    def rule_table(self) -> Dict[str, RuleSpec]:
        return {
            "weak_callout_label": RuleSpec(
                rule_id="CALLOUT_VERIFY_001", reason_code="CALLOUT_WEAK_LABEL_MATCH", severity="info"
            ),
        }

    def apply(self, document: Any, correction: CorrectionRecord) -> None:
        """REMOVE, reviewer-accepted: declassify — drop the Callout, the
        underlying Heading (if any) is untouched and stays an ordinary
        heading, exactly what "this was a false-positive classification"
        means. Every REMOVE lands PROPOSED and only reaches apply() once
        a human has Accepted it via the Corrections API (see
        src/verification/merge.py)."""
        if correction.object_id is None:
            return
        document.callouts = [c for c in document.callouts if c.id != correction.object_id]


def _register() -> None:
    from src.verification.engine import engine

    engine.register(CalloutVerifier())


_register()
