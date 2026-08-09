"""Footnotes: the fifth asset type registered with the cross-source
verification engine — and the mechanism that finally resolves a real,
long-standing data bug rather than only adding a new capability.

src/mathpix/ingestor.py::_p2footnote_to_footnote() has always populated
every Mathpix-sourced Footnote's ``anchor_page_number`` with a hard-coded
placeholder (``1``), documented in its own comment as "enriched by
Verification Engine" — a promise Phase M-2 (docs/PHASE_STATUS.md,
docs/KNOWN_LIMITATIONS.md) recorded as already closed, but the placeholder
was still live in code. This verifier is that enrichment mechanism: it
matches each canonical (Mathpix) Footnote against an independently
PDF-detected candidate (src/footnotes/footnote_detector.py, reused
unchanged via its new detect_footnote_pdf_candidates() entry point) and
proposes the PDF-derived anchor page as a REPAIR correction.

Mirrors src/verification/figures.py's shape (a clean binary
canonical-vs-PDF-candidate match, built on
merge.compute_merge_decisions()) rather than headings.py's multi-signal
EvidenceBundle fusion — footnotes have one real identity question ("is
this the same real-world note"), not several independent typography/
whitespace/recurrence signals to fuse, so the simpler pattern is the
correct-sized one here (see src/verification/base.py for both patterns).
"""

from __future__ import annotations

import difflib
import json
from typing import Any, Dict, List, Optional

from src.models.correction import CorrectionRecord
from src.models.footnote import Footnote, NoteType
from src.models.verification import Finding, RuleSpec
from src.verification.base import SemanticVerifier
from src.verification.matching import MatchResult, MultiSignalMatcher, WeightedSignal
from src.verification.merge import MergeAction

# Two footnotes whose normalized body text is at least this similar are
# considered "the same real-world note" for matching purposes even when
# not identical (e.g. an OCR/recognition difference between Mathpix and
# the PDF's own text extraction).
_BODY_SIMILARITY_MATCH_MIN = 0.6


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _exact_body_signal(a: Footnote, b: Footnote) -> Optional[float]:
    return 0.97 if _normalize(a.body) == _normalize(b.body) else None


def _body_similarity_signal(a: Footnote, b: Footnote) -> Optional[float]:
    ratio = difflib.SequenceMatcher(None, _normalize(a.body), _normalize(b.body)).ratio()
    return ratio if ratio >= _BODY_SIMILARITY_MATCH_MIN else None


def _number_and_type_signal(a: Footnote, b: Footnote) -> Optional[float]:
    """Weak fallback identity signal for a note whose body text Mathpix
    and the PDF extracted too differently for body similarity to catch
    (e.g. heavy OCR noise) — same note_type and printed number is still
    real, if weaker, evidence. Footnote numbering resets per page, so
    this alone cannot be trusted as strongly as body-text agreement;
    kept below both body signals in matcher priority."""
    return 0.4 if a.note_type == b.note_type and a.number == b.number else None


def _positional_signal(_a: Any, _b: Any) -> Optional[float]:
    """Last-resort fallback, identical in spirit to figures.py/headings.py's
    own — pairs the Nth remaining canonical note with the Nth remaining
    PDF candidate via MultiSignalMatcher's stable ordering."""
    return 0.05


def _encode_anchor(footnote: Footnote) -> str:
    return json.dumps(
        {
            "anchor_page_number": footnote.anchor_page_number,
            "anchor_text": footnote.anchor_text,
            "anchor_offset": footnote.anchor_offset,
        }
    )


def _decode_anchor(payload: str) -> Dict[str, Any]:
    return json.loads(payload)


def _encode_footnote(footnote: Footnote) -> str:
    return json.dumps(
        {
            "note_type": footnote.note_type.value,
            "number": footnote.number,
            "marker": footnote.marker,
            "anchor_page_number": footnote.anchor_page_number,
            "anchor_text": footnote.anchor_text,
            "anchor_offset": footnote.anchor_offset,
            "body": footnote.body,
            "body_page_number": footnote.body_page_number,
            "body_source_text": footnote.body_source_text,
        }
    )


def _decode_footnote(payload: str) -> Footnote:
    data = json.loads(payload)
    return Footnote(
        note_type=NoteType(data["note_type"]),
        number=data["number"],
        marker=data["marker"],
        anchor_page_number=data["anchor_page_number"],
        anchor_text=data["anchor_text"],
        anchor_offset=data.get("anchor_offset"),
        body=data["body"],
        body_page_number=data["body_page_number"],
        body_source_text=data["body_source_text"],
        footnote_id=f"rawrs-recovery-{data['note_type']}-{data['number']}-p{data['anchor_page_number']}",
        source="rawrs_recovery",
    )


# W-1: the field a reviewer's note-body edit travels under.
BODY_EDIT = "body_edit"


class FootnoteVerifier(SemanticVerifier):
    asset_type = "footnote"

    def build_pdf_matcher(self) -> MultiSignalMatcher:
        return MultiSignalMatcher(
            [
                WeightedSignal(name="exact_body", fn=_exact_body_signal, min_confidence=0.95),
                WeightedSignal(name="body_similarity", fn=_body_similarity_signal, min_confidence=_BODY_SIMILARITY_MATCH_MIN),
                WeightedSignal(name="number_and_type", fn=_number_and_type_signal, min_confidence=0.35),
                WeightedSignal(name="positional_fallback", fn=_positional_signal, min_confidence=0.01),
            ]
        )

    def to_canonical(self, match_result: MatchResult, **context: Any) -> List[Footnote]:
        """Footnotes arrive from Mathpix already built
        (src/mathpix/ingestor.py) — same reasoning as Heading/List/Callout.
        Identity passthrough."""
        return list(match_result.unmatched_a) + [pair.a for pair in match_result.pairs]

    def _is_mismatch(self, canonical: Footnote, pdf_footnote: Footnote) -> bool:
        return canonical.anchor_page_number != pdf_footnote.anchor_page_number

    def classify(self, match_result: MatchResult, **context: Any) -> List[Finding]:
        findings: List[Finding] = []

        for decision in self.merge_decisions(match_result, self._is_mismatch):
            if decision.canonical is None:
                # RECOVER: a real PDF footnote Mathpix's package is missing entirely.
                pdf_footnote: Footnote = decision.pdf_evidence
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="missing_from_package",
                        object_id=None,
                        confidence=None,
                        evidence=f"pdf_page={pdf_footnote.anchor_page_number}; number={pdf_footnote.number}",
                        message=(
                            f"PDF page {pdf_footnote.anchor_page_number} has a "
                            f"{pdf_footnote.note_type.value} (marker '{pdf_footnote.marker}') "
                            "not present in the Mathpix package."
                        ),
                        proposed_value=_encode_footnote(pdf_footnote),
                    )
                )
                continue

            canonical: Footnote = decision.canonical
            pdf_footnote = decision.pdf_evidence

            if pdf_footnote is None:
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="unconfirmed",
                        object_id=canonical.footnote_id,
                        confidence=None,
                        evidence="no PDF-side match found",
                        message=(
                            f"{canonical.note_type.value.capitalize()} {canonical.number} "
                            f"(page {canonical.anchor_page_number}) could not be confirmed "
                            "against the PDF — its anchor page may still be a placeholder."
                        ),
                    )
                )
                continue

            if decision.action == MergeAction.REPAIR:
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="wrong_page",
                        object_id=canonical.footnote_id,
                        confidence=decision.confidence,
                        evidence=f"mathpix_page={canonical.anchor_page_number}; pdf_page={pdf_footnote.anchor_page_number}",
                        message=(
                            f"{canonical.note_type.value.capitalize()} {canonical.number}'s anchor "
                            f"page disagrees: Mathpix says page {canonical.anchor_page_number}, "
                            f"PDF evidence suggests page {pdf_footnote.anchor_page_number}."
                        ),
                        original_value=_encode_anchor(canonical),
                        proposed_value=_encode_anchor(pdf_footnote),
                    )
                )
            # action == KEEP -> confirmed, no finding.

        return findings

    def rule_table(self) -> Dict[str, RuleSpec]:
        return {
            "missing_from_package": RuleSpec(
                rule_id="FOOTNOTE_VERIFY_001", reason_code="FOOTNOTE_MISSING_FROM_PACKAGE", severity="warning"
            ),
            "unconfirmed": RuleSpec(
                rule_id="FOOTNOTE_VERIFY_002", reason_code="FOOTNOTE_UNCONFIRMED_BY_PDF", severity="info"
            ),
            "wrong_page": RuleSpec(
                rule_id="FOOTNOTE_VERIFY_003", reason_code="FOOTNOTE_ANCHOR_WRONG_PAGE", severity="warning"
            ),
            # L4a. Informational, and informational is the honest level:
            # RAWRS can say a line reads as a note body and that nothing
            # claimed it, but not what it belongs to. Same shape as
            # "unconfirmed" above - no proposed_value, apply() is a no-op.
            "unlinked_note_body": RuleSpec(
                rule_id="FOOTNOTE_VERIFY_004", reason_code="FOOTNOTE_BODY_UNLINKED", severity="info"
            ),
        }

    def apply(self, document: Any, correction: CorrectionRecord) -> None:
        if correction.field == "missing_from_package":
            if not correction.proposed_value:
                return
            document.footnotes.append(_decode_footnote(correction.proposed_value))
            return

        if correction.object_id is None:
            return
        footnote = next((f for f in document.footnotes if f.footnote_id == correction.object_id), None)
        if footnote is None:
            return

        if correction.field == "wrong_page" and correction.proposed_value:
            anchor = _decode_anchor(correction.proposed_value)
            footnote.anchor_page_number = anchor["anchor_page_number"]
            footnote.anchor_text = anchor["anchor_text"]
            footnote.anchor_offset = anchor.get("anchor_offset")
        elif correction.field == BODY_EDIT and correction.proposed_value:
            # W-1. The note body is rendered in both projections, so editing
            # it is a semantic mutation and belongs on the rail. Symmetric:
            # revert replays this with the previous body, restoring it.
            footnote.body = correction.proposed_value
        # "unconfirmed" is informational only — no proposed_value, no-op.


    def inspect(self, document, **context):
        """Everything this verifier has to say about the document's notes.

        Two strategies, each self-selecting (see SemanticVerifier.inspect:
        how a producer reaches its findings is its own business).

        * ``_unlinked_body_findings`` needs only RAWRS's own reading of the
          PDF, so it runs on any document.
        * Cross-source reconciliation is only meaningful when a provider
          supplied document.footnotes: on the RAWRS-native path both sides
          would come from the same detector, so the comparison would be a
          tautology. That condition is read from the document, not from a
          pipeline branch — see Document.import_provider. It is also the
          mechanism that resolves _p2footnote_to_footnote()'s
          anchor_page_number=1 placeholder (src/mathpix/ingestor.py) into a
          real, PDF-confirmed page.
        """
        findings = self._unlinked_body_findings(document)
        if not getattr(document, "import_provider", None):
            return findings
        from src.footnotes.footnote_detector import detect_footnote_pdf_candidates
        from src.verification.engine import engine

        pdf_footnotes = detect_footnote_pdf_candidates(document)
        findings.extend(
            engine.run_pdf_verification("footnote", document.footnotes, pdf_footnotes)
        )
        return findings

    @staticmethod
    def _unlinked_body_findings(document: Any) -> List[Finding]:
        """Note bodies RAWRS read but could not attach to a marker (L4a).

        The detector only ever promotes confidently-linked marker/body
        pairs, which is right — a note with an invented anchor is worse
        than no note. What was wrong is what happened to the other side:
        an unlinked body silently became ordinary body text, so a document
        losing every one of its notes looked exactly like a document that
        had none. The Brinkman PDF drops two this way, and a PDF whose
        markers are unreadable drops all of them.

        So this states the loss instead of hiding it. It proposes nothing:
        with no marker there is no anchor page, no anchor text and no
        offset, and inventing them is the guess this milestone must not
        make. The reviewer gets the line, its printed number, its page and
        which region it was found in, and decides.
        """
        from src.footnotes.footnote_detector import detect_unlinked_note_bodies

        findings: List[Finding] = []
        for body in detect_unlinked_note_bodies(document):
            findings.append(
                Finding(
                    asset_type="footnote",
                    kind="unlinked_note_body",
                    object_id=None,
                    confidence=None,
                    evidence=(
                        f"page={body.page_number}; number={body.number}; "
                        f"region={body.note_type.value}"
                    ),
                    message=(
                        f"Page {body.page_number} has a line that reads as "
                        f"{body.note_type.value} {body.number}'s body "
                        f"({body.text[:60]!r}), but no marker in the text "
                        "referenced it — the note is not being preserved as a note."
                    ),
                )
            )
        return findings


def _register() -> None:
    from src.verification.engine import engine

    engine.register(FootnoteVerifier())


_register()
