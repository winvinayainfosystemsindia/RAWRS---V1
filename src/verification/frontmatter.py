"""Front-matter verification — the review rail for evidence RAWRS can
see but cannot classify (L5'b-2).

Not a missing-front-matter detector. L5'b-1 fixed the one demonstrated
detection defect (a title found by typography rather than by block
order), and where the source carries no extractable text there is
nothing to find — ``DOC_001`` owns that case and this verifier stays
silent.

What is left is narrower and more honest: a line the evidence places
inside the front matter, that no supported role fits. The corpus has
two, and they differ in kind, which is the point:

* Nature of Enquiry's "Setting the field" — a subtitle. 18.0pt between a
  9.5pt body and a 24.0pt title, immediately after the title.
  ``FrontMatterRole`` has no SUBTITLE member, and L5'b-1 deliberately
  stopped the author tier from claiming it.
* FolkPedagogy's "HARVARD UNIVERSITY PRESS" — a publisher imprint that
  feature_008's affiliation guard rejects *as an affiliation*, correctly,
  while saying nothing about what it actually is.

Both are cases where the machine knows something is there and knows it
cannot name it. So it says that and asks. The finding proposes no role,
no text and no object: ``proposed_value`` is empty, which is the literal
statement "RAWRS has no answer here."

**The reviewer's answer is the proposal.** A reviewer resolves the
finding by editing ``proposed_value`` to a supported role and accepting
it, at which point ``apply()`` creates the ``FrontMatterItem`` — with the
role the human chose, and the text and block the document already
recorded. Reject and Ignore are terminal and mutate nothing, exactly as
they do for every other asset type.

Undo needs no code here: ``apply()`` reads the target role from
``proposed_value``, so ``SemanticVerifier.revert()``'s generic swap
replays it with the original empty value and removes the item again. The
same trick ``ArtifactSuppressionVerifier`` uses, and the reason a
reviewer decision on front matter is transaction-safe for free.
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.models.correction import CorrectionRecord
from src.models.front_matter import FrontMatterItem, FrontMatterRole
from src.verification.base import SemanticVerifier
from src.verification.matching import MatchResult, MultiSignalMatcher

ASSET_TYPE = "front_matter"
UNRESOLVED_LINE = "unresolved_front_matter_line"

# A reviewer-created item is identified by the block it resolves, so
# applying the same correction twice cannot produce two items and revert
# can find exactly what apply made.
_REVIEWER_ITEM_ID = "frontmatter-reviewed-{block_id}"

_SUPPORTED_ROLES = {role.value: role for role in FrontMatterRole}


class FrontMatterVerifier(SemanticVerifier):
    """Single-source: front matter is derived from this document's own
    page-1 typography, so there is nothing to reconcile against."""

    asset_type = ASSET_TYPE

    def build_pdf_matcher(self) -> MultiSignalMatcher:
        """No second source — the same documented default
        CalloutVerifier and ArtifactSuppressionVerifier use."""
        return MultiSignalMatcher([])

    def to_canonical(self, match_result: MatchResult, **context: Any) -> List[Any]:
        """A finding creates no canonical object on its own; only an
        accepted reviewer decision does, in ``apply()``."""
        return []

    def classify(self, match_result: MatchResult, **context: Any) -> List[Any]:
        """Not the producer for this asset type — see ``inspect()``."""
        return []

    def inspect(self, document: Any, **context: Any) -> List[Any]:
        """Every front-matter line this document's own evidence places but
        cannot name.

        The single-source producer hook. The evidence is computed by
        src/frontmatter/front_matter_extractor.py, which owns what front
        matter is; this module owns only what to do about the part it
        could not resolve.
        """
        from src.frontmatter.front_matter_extractor import unresolved_front_matter_lines
        from src.models.verification import Finding

        findings: List[Any] = []
        for line in unresolved_front_matter_lines(document):
            findings.append(
                Finding(
                    asset_type=ASSET_TYPE,
                    kind=UNRESOLVED_LINE,
                    object_id=line.block_id,
                    # Deliberately None. There is no calibrated confidence
                    # for "I cannot classify this", and inventing a number
                    # would be the same error as inventing the role.
                    confidence=None,
                    evidence=(
                        f"page={line.page_number}; font_size={line.font_size}; "
                        f"body_font_size={line.body_font_size}; "
                        f"title_font_size={line.title_font_size}; block={line.block_id}"
                    ),
                    message=(
                        f"{line.text!r} sits between the body text and the title in size "
                        f"({line.font_size}pt against a {line.body_font_size}pt body and a "
                        f"{line.title_font_size}pt title), directly after the document's "
                        "title, but no supported front-matter role fits it. RAWRS has not "
                        "guessed one."
                    ),
                    original_value="",
                    # RAWRS proposes nothing; the reviewer's answer is the proposal.
                    proposed_value="",
                )
            )
        return findings

    def rule_table(self) -> Dict[str, Any]:
        from src.models.verification import RuleSpec

        return {
            UNRESOLVED_LINE: RuleSpec(
                rule_id="FRONT_MATTER_001",
                reason_code="FRONT_MATTER_ROLE_UNRESOLVED",
                severity="info",
            )
        }

    def apply(self, document: Any, correction: CorrectionRecord) -> None:
        """Record the role the reviewer chose, or take it back.

        ``proposed_value`` is the decision: a supported role name creates
        the ``FrontMatterItem`` for the block; anything else — including
        the empty string the finding was recorded with, and the empty
        string a revert swaps back in — removes it. That symmetry is why
        this verifier needs no ``revert()`` of its own.

        Nothing is invented: the role comes from the human, the text and
        the block from what the document already recorded. A correction
        whose block or front matter is gone is a no-op, matching every
        other verifier — the audit row survives, the mutation simply has
        nothing to act on.
        """
        front_matter = getattr(document, "front_matter", None)
        block_id = correction.object_id
        if front_matter is None or not block_id:
            return

        item_id = _REVIEWER_ITEM_ID.format(block_id=block_id)
        front_matter.items = [item for item in front_matter.items if item.id != item_id]

        role = _SUPPORTED_ROLES.get((correction.proposed_value or "").strip().lower())
        if role is None:
            return

        block = next(
            (b for b in (getattr(document, "blocks", []) or []) if b.block_id == block_id), None
        )
        if block is None or not block.text.strip():
            return

        front_matter.items.append(
            FrontMatterItem(
                id=item_id,
                role=role,
                text=block.text.strip(),
                source_block_id=block_id,
                document_order=len(front_matter.items),
                page_number=block.page_number,
            )
        )


def _register() -> None:
    from src.verification.engine import engine

    engine.register(FrontMatterVerifier())


_register()
