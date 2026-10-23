"""OCR text repair — accepted second readings onto the correction rail.

src/ocr/reread.py reads garbled OCR regions again with a document VLM and
judges each reading; it never touches page text. This verifier turns every
*accepted* reading into an auto-applied CorrectionRecord, so the repair is
recorded and undoable through the corrections API exactly like artifact
suppression (src/verification/artifacts.py): ``apply()`` swaps the region's
text inside ``Page.cleaned_text``, and the generic ``revert()`` swaps it
back.

Single-source by nature (the second reading is RAWRS's own evidence about
the PDF), so it runs on any path that produced OCR regions, with an empty
matcher like CalloutVerifier and ArtifactSuppressionVerifier.

Rejected readings and regions nobody could read again produce no finding
here; validation rule OCR_004 keeps them in front of the reviewer.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.models.correction import CorrectionRecord
from src.models.verification import Finding, RuleSpec
from src.verification.base import SemanticVerifier
from src.verification.evidence import EvidenceSignal
from src.verification.matching import MatchResult, MultiSignalMatcher

ASSET_TYPE = "ocr_text"
REREAD = "garbled_ocr_reread"


def page_object_id(page_number: int) -> str:
    return f"page-{page_number}"


def _page(document: Any, object_id: Optional[str]) -> Any:
    for page in getattr(document, "pages", []):
        if page_object_id(page.page_number) == object_id:
            return page
    return None


class OcrTextVerifier(SemanticVerifier):
    asset_type = ASSET_TYPE

    def build_pdf_matcher(self) -> MultiSignalMatcher:
        """Nothing to pair: the second reading is already attached to the
        region it reads (see module docstring)."""
        return MultiSignalMatcher([])

    def to_canonical(self, match_result: MatchResult, **context: Any) -> List[Any]:
        return []

    def classify(self, match_result: MatchResult, **context: Any) -> List[Finding]:
        return []

    def inspect(self, document: Any, **context: Any) -> List[Finding]:
        findings: List[Finding] = []
        for page in getattr(document, "pages", []):
            for region in page.ocr_rereads:
                if not region.accepted or not region.reading or region.original not in page.cleaned_text:
                    continue
                findings.append(
                    Finding(
                        asset_type=ASSET_TYPE,
                        kind=REREAD,
                        object_id=page_object_id(page.page_number),
                        confidence=region.agreement,
                        evidence=(
                            f"OCR output matched the garble signature; {region.engine} read the region "
                            f"again and kept {region.agreement:.0%} of its readable words"
                        ),
                        message=(
                            f"Garbled OCR text on page {page.page_number} was read again by "
                            f"{region.engine}: {region.original[:80]!r} → {region.reading[:80]!r}"
                        ),
                        original_value=region.original,
                        proposed_value=region.reading,
                        evidence_items=[
                            EvidenceSignal(
                                name="word_agreement",
                                score=region.agreement or 0.0,
                                weight=1.0,
                                note="share of the original's readable words the second reading kept",
                            )
                        ],
                        auto_apply=True,
                    )
                )
        return findings

    def rule_table(self) -> Dict[str, RuleSpec]:
        return {
            REREAD: RuleSpec(rule_id="OCR_REREAD_001", reason_code="GARBLED_OCR_REREAD", severity="info"),
        }

    def apply(self, document: Any, correction: CorrectionRecord) -> None:
        """Replace the region's text in the page text, once. A page whose text
        no longer holds the expected value (edited since) is left alone: the
        audit row survives, the mutation has nothing to act on."""
        page = _page(document, correction.object_id)
        if page is None or not correction.original_value:
            return
        if correction.original_value in page.cleaned_text:
            page.cleaned_text = page.cleaned_text.replace(
                correction.original_value, correction.proposed_value, 1
            )


def _register() -> None:
    from src.verification.engine import engine

    engine.register(OcrTextVerifier())


_register()
