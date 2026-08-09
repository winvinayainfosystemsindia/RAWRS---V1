"""Paragraph prose: the eleventh registered asset type (W-2b).

``CorrectionRecord``'s docstring has named ``"paragraph"`` as an expected
``object_type`` since Phase M-1, and until now nothing could produce one:
ordinary prose was the one kind of content a reviewer could read in both
projections and not correct. Every other semantic object had an edit path
— a heading's level and text, a note's body, a table's cells, an image's
alt text — while a typo in a sentence had none.

**The Semantic Document is where prose is edited.** ``Paragraph.text`` is
read directly by ``markdown_builder._render_paragraph``, and the DOCX is
generated from that Markdown, so changing the model changes both
projections and nothing else has to know. The alternative — editing the
generated Markdown and parsing it back — would make a renderer the source
of truth, which is the inversion ADR-020 exists to prevent.

**Whole paragraph, not a character range.** ``Paragraph.text`` is a
*transformed* string: hyphen repair and same-baseline fragment merging
happen during grouping (src/structure/paragraph_grouper.py), so an offset
into it maps to no single ``TextBlock``. A range edit needs a
transformation mapping that does not exist, and inventing one
speculatively is how a correction ends up applied to the wrong span.

**Identity is W-2a's, unchanged.** ``object_id`` is ``Paragraph.id`` —
derived from the first contributing block id, or from the .mmd source
line on the import path — so two paragraphs carrying identical prose stay
independently addressable, and inserting an earlier paragraph renames
nothing.

**Source is never touched.** The contributing ``TextBlock``s keep their
own text, which is what ``_render_paragraph`` still reads to decide bold
and italic (016G) and to place footnote markers. The edit changes what
the paragraph *says*, not what extraction *found* — the same split that
makes ``corrected_order`` reversible for reading order.
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.models.correction import CorrectionRecord
from src.verification.base import SemanticVerifier
from src.verification.matching import MatchResult, MultiSignalMatcher

ASSET_TYPE = "paragraph"

#: The field a reviewer's prose edit travels under. One kind, because a
#: paragraph has exactly one editable attribute — its text.
TEXT_EDIT = "text_edit"


class ParagraphVerifier(SemanticVerifier):
    """Single-source: a paragraph's prose is this document's own, so there
    is no second source to reconcile it against."""

    asset_type = ASSET_TYPE

    def build_pdf_matcher(self) -> MultiSignalMatcher:
        """No second source — the documented default every single-source
        verifier uses (ReadingOrderVerifier, MetadataVerifier,
        CalloutVerifier, FrontMatterVerifier)."""
        return MultiSignalMatcher([])

    def to_canonical(self, match_result: MatchResult, **context: Any) -> List[Any]:
        """An edit creates no paragraph; it changes one that exists."""
        return []

    def classify(self, match_result: MatchResult, **context: Any) -> List[Any]:
        """Not a producer. RAWRS has no basis for proposing that a
        sentence should read differently — that judgement is the
        reviewer's, and this verifier exists to carry their answer rather
        than to invent a question."""
        return []

    def rule_table(self) -> Dict[str, Any]:
        from src.models.verification import RuleSpec

        return {
            TEXT_EDIT: RuleSpec(
                rule_id="PARAGRAPH_001",
                reason_code="PARAGRAPH_TEXT_EDITED_BY_REVIEWER",
                severity="info",
            )
        }

    def apply(self, document: Any, correction: CorrectionRecord) -> None:
        """Set the paragraph's text to what this correction carries.

        Symmetric and idempotent: the payload is the paragraph's whole
        text, so ``SemanticVerifier.revert()``'s generic swap restores the
        previous wording with no paragraph-specific undo logic, and
        applying twice writes the same string.

        Deliberately no blank guard. Blankness is rejected at the trust
        boundary (``PATCH .../paragraphs/{id}`` answers 422, as the
        footnote body endpoint does), and a guard here would break the
        symmetry revert depends on — the verifier applies exactly what the
        record says, in both directions.

        A correction naming a paragraph that is gone is a no-op, matching
        every other verifier: the audit row survives, the mutation has
        nothing to act on.
        """
        if correction.field != TEXT_EDIT or correction.object_id is None:
            return

        paragraph = next(
            (
                p
                for p in (getattr(document, "paragraphs", []) or [])
                if p.id == correction.object_id
            ),
            None,
        )
        if paragraph is None:
            return

        paragraph.text = correction.proposed_value


def _register() -> None:
    from src.verification.engine import engine

    engine.register(ParagraphVerifier())


_register()
