"""Headings: the second asset type registered with the cross-source
verification engine, and the first built directly on the Document Merge
Layer + SemanticVerifier base class from day one (see
src/verification/figures.py for the first, migrated-after-the-fact,
asset type).

Only PDF-verification matters here — Mathpix already builds canonical
``Heading`` objects directly (src/mathpix/ingestor.py), so there is no
separate "uploaded asset" to match at import time the way Figure has.
The PDF-side candidates come from
``src/headings/heading_detector.py::detect_headings_from_pdf()``, a pure
function that reuses that module's existing classification helpers —
zero duplicated detection logic, and ``detect_headings()`` (the
Mathpix-independent native path) is untouched.

Content headings only (H1-H5); page markers (H6) are out of scope for
this verifier (a future PageLabelVerifier's job — see the roadmap in
docs/DECISIONS_LOG.md).
"""

from __future__ import annotations

import difflib
import json
from typing import Any, Dict, List, Optional

from src.models.correction import CorrectionRecord
from src.models.heading import Heading, HeadingLevel
from src.models.verification import EvidenceItem, Finding, RuleSpec, VerificationStatus
from src.verification.base import SemanticVerifier
from src.verification.matching import MatchResult, MultiSignalMatcher, WeightedSignal
from src.verification.merge import MergeAction

# Two headings whose normalized text similarity is at least this high are
# considered "the same heading" for matching purposes even when the exact
# text differs (e.g. an OCR/recognition typo) — classify() then reports
# the text difference as a text_correction finding rather than treating
# them as two unrelated headings.
_TEXT_SIMILARITY_MATCH_MIN = 0.6


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _exact_text_signal(a: Heading, b: Heading) -> Optional[float]:
    return 1.0 if _normalize(a.text) == _normalize(b.text) else None


def _text_similarity_signal(a: Heading, b: Heading) -> Optional[float]:
    ratio = difflib.SequenceMatcher(None, _normalize(a.text), _normalize(b.text)).ratio()
    return ratio if ratio >= _TEXT_SIMILARITY_MATCH_MIN else None


def _page_proximity_signal(a: Heading, b: Heading) -> Optional[float]:
    diff = abs(a.page_number - b.page_number)
    if diff == 0:
        return 0.55
    if diff == 1:
        return 0.5
    return None


def _positional_signal(_a: Any, _b: Any) -> Optional[float]:
    """Last-resort fallback, identical in spirit to figures.py's own —
    pairs the Nth remaining canonical heading with the Nth remaining PDF
    candidate via MultiSignalMatcher's stable-sort/dict-insertion-order
    behavior, not by inspecting indices itself."""
    return 0.05


def _encode_recovery(pdf_heading: Heading) -> str:
    return json.dumps(
        {"level": int(pdf_heading.level), "text": pdf_heading.text, "page_number": pdf_heading.page_number}
    )


def _decode_recovery(payload: str) -> Heading:
    data = json.loads(payload)
    return Heading(
        level=HeadingLevel(data["level"]),
        text=data["text"],
        page_number=data["page_number"],
        document_order=0,  # placeholder — _insert_recovered_heading assigns the real slot
        is_page_marker=False,
        source="rawrs_recovery",
    )


def _insert_recovered_heading(document: Any, recovered: Heading) -> None:
    """Insert a RECOVER'd heading into document.headings at the right
    document_order slot, shifting every subsequent heading's order by one
    to preserve uniqueness — rather than merely appending, which would
    put a page-3 recovery after a page-10 heading in document order."""
    insert_after: Optional[int] = None
    for h in document.headings:
        if h.page_number <= recovered.page_number:
            if insert_after is None or h.document_order > insert_after:
                insert_after = h.document_order
    new_order = insert_after + 1 if insert_after is not None else 0
    for h in document.headings:
        if h.document_order >= new_order:
            h.document_order += 1
    recovered.document_order = new_order
    document.headings.append(recovered)
    document.headings.sort(key=lambda h: h.document_order)


class HeadingVerifier(SemanticVerifier):
    asset_type = "heading"

    def build_pdf_matcher(self) -> MultiSignalMatcher:
        return MultiSignalMatcher(
            [
                WeightedSignal(name="exact_text", fn=_exact_text_signal, min_confidence=0.99),
                WeightedSignal(name="text_similarity", fn=_text_similarity_signal, min_confidence=_TEXT_SIMILARITY_MATCH_MIN),
                WeightedSignal(name="page_proximity", fn=_page_proximity_signal, min_confidence=0.5),
                WeightedSignal(name="positional_fallback", fn=_positional_signal, min_confidence=0.01),
            ]
        )

    def to_canonical(self, match_result: MatchResult, **context: Any) -> List[Heading]:
        """Headings arrive from Mathpix already as canonical Heading
        objects (src/mathpix/ingestor.py) — there is no separate uploaded
        asset to match at import time (unlike Figure). Identity passthrough;
        not currently invoked by the pipeline (headings only go through
        run_pdf_verification this session) — implemented for base-class
        completeness and future import-time use."""
        return list(match_result.unmatched_a) + [pair.a for pair in match_result.pairs]

    def _is_mismatch(self, canonical: Heading, pdf_heading: Heading) -> bool:
        return canonical.level != pdf_heading.level or _normalize(canonical.text) != _normalize(pdf_heading.text)

    def classify(self, match_result: MatchResult, **context: Any) -> List[Finding]:
        findings: List[Finding] = []

        for decision in self.merge_decisions(match_result, self._is_mismatch):
            if decision.pdf_evidence is None:
                # KEEP, unconfirmed: a canonical heading the PDF pass didn't match.
                canonical: Heading = decision.canonical
                canonical.verification_status = VerificationStatus.MISSING_FROM_PDF
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="unconfirmed",
                        object_id=canonical.id,
                        confidence=None,
                        evidence=f"page={canonical.page_number}",
                        message=f"Heading '{canonical.text}' could not be confirmed against the PDF.",
                    )
                )
                continue

            if decision.canonical is None:
                # RECOVER: a real PDF heading Mathpix flattened to body text.
                pdf_heading: Heading = decision.pdf_evidence
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="missing_from_package",
                        object_id=None,
                        confidence=None,
                        evidence=f"pdf_page={pdf_heading.page_number}; pdf_level=H{int(pdf_heading.level)}",
                        message=(
                            f"PDF page {pdf_heading.page_number} has a heading "
                            f"('{pdf_heading.text}') not present in the Mathpix package."
                        ),
                        proposed_value=_encode_recovery(pdf_heading),
                        evidence_items=[
                            EvidenceItem(signal="pdf_typography", detail=f"H{int(pdf_heading.level)} by font-size rank"),
                            EvidenceItem(signal="pdf_page", detail=str(pdf_heading.page_number)),
                        ],
                    )
                )
                continue

            # Matched pair: KEEP (agree) or REPAIR (level and/or text disagree).
            canonical = decision.canonical
            pdf_heading = decision.pdf_evidence
            canonical.confidence = decision.confidence

            if decision.action != MergeAction.REPAIR:
                canonical.verification_status = VerificationStatus.VERIFIED
                continue

            canonical.verification_status = VerificationStatus.MISMATCH
            if canonical.level != pdf_heading.level:
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="level_mismatch",
                        object_id=canonical.id,
                        confidence=decision.confidence,
                        evidence=f"mathpix_level=H{int(canonical.level)}; pdf_level=H{int(pdf_heading.level)}",
                        message=(
                            f"Heading level disagrees: Mathpix says H{int(canonical.level)}, "
                            f"PDF typography suggests H{int(pdf_heading.level)}."
                        ),
                        original_value=str(int(canonical.level)),
                        proposed_value=str(int(pdf_heading.level)),
                        evidence_items=[
                            EvidenceItem(signal="pdf_typography", detail=f"H{int(pdf_heading.level)} by font-size rank"),
                        ],
                    )
                )
            if _normalize(canonical.text) != _normalize(pdf_heading.text):
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="text_correction",
                        object_id=canonical.id,
                        confidence=decision.confidence,
                        evidence=f"mathpix_text={canonical.text!r}; pdf_text={pdf_heading.text!r}",
                        message="Heading text differs from the PDF — possible OCR/recognition error.",
                        original_value=canonical.text,
                        proposed_value=pdf_heading.text,
                        evidence_items=[EvidenceItem(signal="pdf_text", detail=pdf_heading.text)],
                    )
                )

        return findings

    def rule_table(self) -> Dict[str, RuleSpec]:
        return {
            "unconfirmed": RuleSpec(
                rule_id="HEADING_VERIFY_001", reason_code="HEADING_UNCONFIRMED_BY_PDF", severity="info"
            ),
            "missing_from_package": RuleSpec(
                rule_id="HEADING_VERIFY_002", reason_code="HEADING_MISSING_FROM_PACKAGE", severity="warning"
            ),
            "level_mismatch": RuleSpec(
                rule_id="HEADING_VERIFY_003", reason_code="HEADING_LEVEL_MISMATCH", severity="warning"
            ),
            "text_correction": RuleSpec(
                rule_id="HEADING_VERIFY_004", reason_code="HEADING_TEXT_OCR_ERROR", severity="warning"
            ),
        }

    def apply(self, document: Any, correction: CorrectionRecord) -> None:
        if correction.field == "missing_from_package":
            if not correction.proposed_value:
                return
            _insert_recovered_heading(document, _decode_recovery(correction.proposed_value))
            return

        if correction.object_id is None:
            return
        heading = next((h for h in document.headings if h.id == correction.object_id), None)
        if heading is None:
            return

        if correction.field == "level_mismatch" and correction.proposed_value:
            heading.level = HeadingLevel(int(correction.proposed_value))
        elif correction.field == "text_correction" and correction.proposed_value:
            heading.text = correction.proposed_value
        # "unconfirmed" is informational only — no proposed_value, no-op.


def _register() -> None:
    from src.verification.engine import engine

    engine.register(HeadingVerifier())


_register()
