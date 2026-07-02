"""SemanticVerifier — the base class every semantic object type implements
to participate in cross-source verification.

This used to be a plain ``AssetVerifier`` Protocol (still importable as an
alias below, for existing callers) that only declared a shape — every asset
type had to hand-write its own matched/unmatched loop inside ``classify()``.
``SemanticVerifier`` is a real base class with two concrete, generic
behaviors so a new verifier (Heading, List, and later Table, Footnote,
Callout, Equation, ...) needs to write only what's genuinely asset-specific:
matching signals and the domain mutation in ``apply()``.

``src/verification/engine.py`` never contains asset-specific logic — it
only calls these methods on whichever verifier is registered for a given
``asset_type`` string.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List

from src.models.correction import CorrectionRecord
from src.models.verification import Finding, RuleSpec
from src.verification.matching import MatchResult, MultiSignalMatcher
from src.verification.merge import MergeDecision, compute_merge_decisions


class SemanticVerifier(ABC):
    """Base class for one asset type's participation in cross-source
    verification.

    ``to_canonical`` is deliberately the only place asset-specific domain
    object construction happens — the engine never builds a Heading, Image,
    or ListBlock itself, since those models share no common shape beyond
    ``SemanticObject``. Matching signals and ``apply()``'s mutation are the
    other genuinely asset-specific pieces; everything else (merge-decision
    derivation, dispatch, translation to CorrectionRecord/ValidationIssue)
    is generic enough to live here or in the engine.
    """

    asset_type: str

    def build_import_matcher(self) -> MultiSignalMatcher:
        """Matcher used to pair provider-source items against
        uploaded/package assets at import time.

        Default: an empty-signal matcher, which — given
        ``MultiSignalMatcher.match(a_items, b_items=[])`` — cleanly yields
        every ``a_items`` entry as ``unmatched_a`` and nothing else. This is
        the right default for any asset type with no separate "uploaded
        asset" to match against (e.g. List: Mathpix's own extraction *is*
        the only import-time source). Override only when an import-time
        match against a second, independent source is meaningful (e.g.
        Figure, matching MMD figure blocks against uploaded image files).
        """
        return MultiSignalMatcher([])

    @abstractmethod
    def build_pdf_matcher(self) -> MultiSignalMatcher:
        """Matcher used to pair canonical (already-imported) objects
        against independently PDF-extracted candidates, for verification.
        Always asset-specific — this is real domain knowledge about what
        signals distinguish "the same real-world object" for this type."""
        ...

    @abstractmethod
    def to_canonical(self, match_result: MatchResult, **context: Any) -> List[Any]:
        """Build canonical Document objects from an import-time
        MatchResult. Every item worth keeping should produce a canonical
        object; nothing that was actually part of the imported package
        should be dropped here."""
        ...

    @abstractmethod
    def classify(self, match_result: MatchResult, **context: Any) -> List[Finding]:
        """Turn a MatchResult into generic Findings the engine can
        translate into corrections, repair suggestions, and validation
        issues. Typically built on top of ``self.merge_decisions(...)``
        rather than a hand-written matched/unmatched loop."""
        ...

    @abstractmethod
    def rule_table(self) -> Dict[str, RuleSpec]:
        """Maps this asset type's Finding.kind values to the rule_id /
        reason_code / severity the rest of RAWRS understands."""
        ...

    @abstractmethod
    def apply(self, document: Any, correction: CorrectionRecord) -> None:
        """Mutate ``document`` to actually perform an ACCEPTED (or EDITED)
        correction. Called only after a human reviewer accepts a
        CorrectionRecord — every correction stays PROPOSED until this runs.
        A no-op is the correct implementation for a kind that is purely
        informational and proposes no document mutation."""
        ...

    # ── Concrete, shared — this is what makes a new verifier cheap ──────

    def merge_decisions(
        self, match_result: MatchResult, is_mismatch: Callable[[Any, Any], bool]
    ) -> List[MergeDecision]:
        """The Document Merge Layer: generic KEEP/REPAIR/RECOVER derivation.
        See src/verification/merge.py. Every verifier's classify() should
        build on this instead of re-deriving matched/unmatched semantics."""
        return compute_merge_decisions(match_result, is_mismatch)

    def revert(self, document: Any, correction: CorrectionRecord) -> None:
        """Generic undo: replays apply() with proposed/original swapped.

        This is what makes "Undo" work for every verifier for free —
        a verifier only overrides this if reverting genuinely isn't just
        the inverse mutation (rare; e.g. a RECOVER correction whose
        "undo" must remove the recovered object rather than mutate a
        field back — such verifiers override this explicitly).
        """
        reversed_correction = correction.model_copy(
            update={"proposed_value": correction.original_value, "original_value": correction.proposed_value}
        )
        self.apply(document, reversed_correction)


# Backward-compatible alias: existing code/tests that import `AssetVerifier`
# (as a type hint, never as a base class anything currently inherits from —
# every asset type before this change was duck-typed against it) keep working
# unchanged.
AssetVerifier = SemanticVerifier
