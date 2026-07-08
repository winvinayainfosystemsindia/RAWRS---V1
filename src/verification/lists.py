"""Lists: the third asset type registered with the cross-source
verification engine, and the second built directly on the Document Merge
Layer + SemanticVerifier base class (alongside Heading).

Canonical ListBlocks arrive from Mathpix already grouped
(src/mathpix/ingestor.py, mirroring how Heading is built directly rather
than through engine.run_import — there is no second "uploaded asset"
source for either). The PDF-side candidates come from
``src/lists/list_detector.py::detect_lists_from_pdf()``, a pure geometric
detector. The RECOVER case here is the brief's exact "Mathpix converts a
list into paragraphs" example: when the PDF pass finds a real list with
no canonical counterpart at all, that's Mathpix having flattened it to
plain paragraph text entirely (not even tagged as a list item in the
MMD) — this verifier's job is exactly to catch and recover that.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set

from src.models.correction import CorrectionRecord
from src.models.list_block import ListBlock, ListItem, ListType
from src.models.semantic_object import ProvenanceSource
from src.models.verification import Finding, RuleSpec, VerificationStatus
from src.verification.base import SemanticVerifier
from src.verification.evidence import EvidenceSignal
from src.verification.matching import MatchResult, MultiSignalMatcher, WeightedSignal
from src.verification.merge import MergeAction

# Two lists whose item-text overlap (Jaccard over normalized item strings)
# is at least this high are considered "the same list" for matching.
_ITEM_OVERLAP_MATCH_MIN = 0.4


def _normalize_item(text: str) -> str:
    return " ".join(text.lower().split())


def _item_set(lst: ListBlock) -> Set[str]:
    return {_normalize_item(item.text) for item in lst.items}


def _item_overlap_signal(a: ListBlock, b: ListBlock) -> Optional[float]:
    a_items, b_items = _item_set(a), _item_set(b)
    if not a_items or not b_items:
        return None
    overlap = len(a_items & b_items) / len(a_items | b_items)
    return overlap if overlap >= _ITEM_OVERLAP_MATCH_MIN else None


def _page_proximity_signal(a: ListBlock, b: ListBlock) -> Optional[float]:
    diff = abs(a.page_number - b.page_number)
    if diff == 0:
        return 0.45
    if diff == 1:
        return 0.4
    return None


def _positional_signal(_a: Any, _b: Any) -> Optional[float]:
    return 0.05


def _encode_recovery(pdf_list: ListBlock) -> str:
    return json.dumps(
        {
            "list_type": pdf_list.list_type.value,
            "items": [{"text": item.text, "level": item.level} for item in pdf_list.items],
            "page_number": pdf_list.page_number,
        }
    )


def _decode_recovery(payload: str) -> ListBlock:
    data = json.loads(payload)
    return ListBlock(
        list_type=ListType(data["list_type"]),
        items=[ListItem(text=i["text"], level=i["level"]) for i in data["items"]],
        page_number=data["page_number"],
        document_order=0,  # placeholder — apply() assigns the real slot
        provenance=ProvenanceSource.PDF_RECOVERED,
    )


class ListVerifier(SemanticVerifier):
    asset_type = "list"

    def build_pdf_matcher(self) -> MultiSignalMatcher:
        return MultiSignalMatcher(
            [
                WeightedSignal(name="item_overlap", fn=_item_overlap_signal, min_confidence=_ITEM_OVERLAP_MATCH_MIN),
                WeightedSignal(name="page_proximity", fn=_page_proximity_signal, min_confidence=0.4),
                WeightedSignal(name="positional_fallback", fn=_positional_signal, min_confidence=0.01),
            ]
        )

    def to_canonical(self, match_result: MatchResult, **context: Any) -> List[ListBlock]:
        """Lists arrive from Mathpix already grouped into canonical
        ListBlocks (src/mathpix/ingestor.py) — same reasoning as
        HeadingVerifier.to_canonical. Not currently invoked by the
        pipeline; implemented for base-class completeness."""
        return list(match_result.unmatched_a) + [pair.a for pair in match_result.pairs]

    def _is_mismatch(self, canonical: ListBlock, pdf_list: ListBlock) -> bool:
        return len(canonical.items) != len(pdf_list.items)

    def classify(self, match_result: MatchResult, **context: Any) -> List[Finding]:
        findings: List[Finding] = []

        for decision in self.merge_decisions(match_result, self._is_mismatch):
            if decision.pdf_evidence is None:
                canonical: ListBlock = decision.canonical
                canonical.verification_status = VerificationStatus.MISSING_FROM_PDF
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="unconfirmed",
                        object_id=canonical.id,
                        confidence=None,
                        evidence=f"page={canonical.page_number}; item_count={len(canonical.items)}",
                        message=f"A {len(canonical.items)}-item list could not be confirmed against the PDF.",
                    )
                )
                continue

            if decision.canonical is None:
                # RECOVER: Mathpix flattened a real PDF list into plain
                # paragraph text (no list_item tagging at all in the MMD)
                # — the brief's exact "reconstruct the semantic list" case.
                pdf_list: ListBlock = decision.pdf_evidence
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="recovered_from_pdf",
                        object_id=None,
                        confidence=None,
                        evidence=f"pdf_page={pdf_list.page_number}; item_count={len(pdf_list.items)}",
                        message=(
                            f"PDF page {pdf_list.page_number} contains a {len(pdf_list.items)}-item "
                            "list not present as structured list content in the Mathpix package."
                        ),
                        proposed_value=_encode_recovery(pdf_list),
                        evidence_items=[
                            EvidenceSignal(name="pdf_item_count", score=1.0, weight=1.0, note=str(len(pdf_list.items))),
                            EvidenceSignal(name="pdf_list_type", score=1.0, weight=1.0, note=pdf_list.list_type.value),
                        ],
                    )
                )
                continue

            canonical = decision.canonical
            pdf_list = decision.pdf_evidence
            canonical.confidence = decision.confidence

            if decision.action != MergeAction.REPAIR:
                canonical.verification_status = VerificationStatus.VERIFIED
                continue

            canonical.verification_status = VerificationStatus.MISMATCH
            findings.append(
                Finding(
                    asset_type=self.asset_type,
                    kind="item_count_mismatch",
                    object_id=canonical.id,
                    confidence=decision.confidence,
                    evidence=f"mathpix_items={len(canonical.items)}; pdf_items={len(pdf_list.items)}",
                    message=(
                        f"List item count disagrees: Mathpix has {len(canonical.items)}, "
                        f"PDF geometry suggests {len(pdf_list.items)}."
                    ),
                    original_value=str(len(canonical.items)),
                    proposed_value=str(len(pdf_list.items)),
                    evidence_items=[EvidenceSignal(name="pdf_item_count", score=1.0, weight=1.0, note=str(len(pdf_list.items)))],
                )
            )

        return findings

    def rule_table(self) -> Dict[str, RuleSpec]:
        return {
            "unconfirmed": RuleSpec(
                rule_id="LIST_VERIFY_001", reason_code="LIST_UNCONFIRMED_BY_PDF", severity="info"
            ),
            "recovered_from_pdf": RuleSpec(
                rule_id="LIST_VERIFY_002", reason_code="LIST_MISSING_FROM_PACKAGE", severity="warning"
            ),
            "item_count_mismatch": RuleSpec(
                rule_id="LIST_VERIFY_003", reason_code="LIST_ITEM_COUNT_MISMATCH", severity="warning"
            ),
        }

    def apply(self, document: Any, correction: CorrectionRecord) -> None:
        if correction.field == "recovered_from_pdf":
            if not correction.proposed_value:
                return
            recovered = _decode_recovery(correction.proposed_value)
            recovered.document_order = len(document.lists)
            document.lists.append(recovered)
            return
        # item_count_mismatch / unconfirmed: informational only this
        # session — unlike a scalar correction (heading level, page
        # number), "the item count disagrees" has no single safe
        # generic repair; a reviewer edits list content directly via a
        # future List workspace UI (see roadmap) rather than RAWRS
        # silently adding/removing items it can't attribute correctly.
        # ponytail: no-op repair, add per-item add/remove apply() once the
        # List workspace UI exists to let a reviewer pick which items.


def _register() -> None:
    from src.verification.engine import engine

    engine.register(ListVerifier())


_register()
