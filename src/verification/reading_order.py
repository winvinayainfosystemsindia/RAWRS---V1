"""Reading order: the ninth registered asset type (W-1 Group B).

``CorrectionRecord``'s own docstring has always named ``"reading_order"``
as an expected ``object_type``. It simply never had a verifier, so the
one endpoint that changes a page's reading order mutated the Semantic
Document directly — and it is the most consequential bypass in the
system, because ``build_content_stream`` reads
``TextBlock.corrected_order`` in preference to ``order``. A reorder
therefore silently rewrote both projections with no audit row and no
undo.

**Page owns reading order.** The status lives on
``Page.reading_order_status`` and the ordering override lives on the
page's ``TextBlock``s; no other asset type has a claim on either, and
forcing it into Heading or Paragraph would be borrowing an owner rather
than naming one.

**``corrected_order`` is the decision layer, not the fact.**
``TextBlock.order`` is what extraction found and is never overwritten;
``corrected_order`` is ``None`` until a human overrides it. That split is
what makes this correction reversible: the original state is recoverable
because it was never destroyed.

**One page reorder is one decision.** The reviewer's judgement is "this
page reads in this order" — not sixty independent block judgements — so
one page produces one CorrectionRecord carrying the page's complete
override map, keyed by ``block_id``. Identity is the block's own id, so
nothing here matches text.

Approving an order is deliberately *not* a correction. It sets
``reading_order_status`` and changes no ordering, and that field is read
by no projection and no validation rule (verified) — it is review-queue
state, not document content. Manufacturing a correction for it would put
bookkeeping in the audit trail and teach the rail to lie about what a
decision is.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.models.correction import CorrectionRecord
from src.verification.base import SemanticVerifier
from src.verification.matching import MatchResult, MultiSignalMatcher

ASSET_TYPE = "reading_order"
BLOCK_ORDER = "block_order"


def encode_page_order(page: Any, page_blocks: List[Any]) -> str:
    """One page's complete reading-order state, as a correction payload.

    Complete rather than differential, and that is the point: undo has to
    restore "no override at all" as faithfully as it restores a previous
    override, so every block on the page appears — including the ones
    whose ``corrected_order`` is ``None``.
    """
    return json.dumps(
        {
            "status": getattr(getattr(page, "reading_order_status", None), "value", None),
            "order": {block.block_id: block.corrected_order for block in page_blocks},
        }
    )


class ReadingOrderVerifier(SemanticVerifier):
    """Single-source: a page's reading order is this document's own
    layout, so there is no second source to reconcile against."""

    asset_type = ASSET_TYPE

    def build_pdf_matcher(self) -> MultiSignalMatcher:
        """No second source — the documented default every single-source
        verifier uses (CalloutVerifier, ArtifactSuppressionVerifier,
        FrontMatterVerifier)."""
        return MultiSignalMatcher([])

    def to_canonical(self, match_result: MatchResult, **context: Any) -> List[Any]:
        """A reorder creates no object; it repositions ones that exist."""
        return []

    def classify(self, match_result: MatchResult, **context: Any) -> List[Any]:
        """Not a producer. Reading-order *proposals* already exist as
        PAGE_003 validation issues; this verifier exists to carry the
        reviewer's answer, not to ask the question again."""
        return []

    def rule_table(self) -> Dict[str, Any]:
        from src.models.verification import RuleSpec

        return {
            BLOCK_ORDER: RuleSpec(
                rule_id="READING_ORDER_001",
                reason_code="READING_ORDER_CORRECTED_BY_REVIEWER",
                severity="info",
            )
        }

    def apply(self, document: Any, correction: CorrectionRecord) -> None:
        """Restore the page ordering state this correction carries.

        Symmetric by construction: the payload is a complete map, so
        ``SemanticVerifier.revert()``'s generic swap replays the previous
        state — including ``None``, meaning "no override" — with no
        reading-order-specific undo logic. Idempotent for the same reason:
        applying twice writes the same values.

        A correction whose page or blocks are gone is a no-op, matching
        every other verifier: the audit row survives, the mutation has
        nothing to act on.
        """
        if correction.field != BLOCK_ORDER or not correction.proposed_value:
            return

        state = json.loads(correction.proposed_value)
        order: Dict[str, Optional[int]] = state.get("order") or {}

        for block in getattr(document, "blocks", []) or []:
            if block.block_id in order:
                block.corrected_order = order[block.block_id]

        status = state.get("status")
        page = self._page_for(document, correction.object_id)
        if page is not None and status:
            from src.models.page import ReadingOrderStatus

            page.reading_order_status = ReadingOrderStatus(status)

    @staticmethod
    def _page_for(document: Any, object_id: Optional[str]) -> Any:
        """The page this correction is about.

        ``object_id`` is the page number as a string — Page has no id
        field of its own, and its number is already its stable identity
        everywhere else in the model.
        """
        if object_id is None:
            return None
        try:
            page_number = int(object_id)
        except (TypeError, ValueError):
            return None
        return next(
            (p for p in (getattr(document, "pages", []) or []) if p.page_number == page_number),
            None,
        )


def _register() -> None:
    from src.verification.engine import engine

    engine.register(ReadingOrderVerifier())


_register()
