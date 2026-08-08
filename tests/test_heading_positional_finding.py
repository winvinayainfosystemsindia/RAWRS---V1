"""The positional-H1 finding is gone, and its persisted decisions are not.

Until L3.2 the detector could make a line an H1 on document position
alone, and `HeadingVerifier` flagged that case (HEADING_VERIFY_006,
reason code HEADING_POSITIONAL_ONLY) so a reviewer could delete it. The
corpus settled the question instead: of 85 content headings, 8 sat in
the title position, and the 3 resting on position *alone* were all wrong
— 'Article' (a journal kicker, bug_003), 'xlv' (a roman page label), and
a sentence of body prose. So position stopped deciding, that class of
heading stopped existing, and the finding retired with it.

What survives is the reviewer decision already recorded against it. A
document persisted before L3.2 carries corrections whose field is
`positional_only_h1`; the apply/revert branch still handles them, and
these tests are why it may not be deleted.
"""

from typing import List

from src.models.contracts import Document, Heading, HeadingLevel, Metadata
from src.models.correction import CorrectionRecord, CorrectionStatus
from src.verification.engine import engine
from src.verification.evidence import EvidenceSignal
from src.verification.headings import HeadingVerifier, _encode_recovery

TITLE_POSITION = EvidenceSignal(
    name="title_position", score=0.35, weight=1.0, note="position only"
)
BOLD = EvidenceSignal(name="bold_contrast", score=0.70, weight=2.0, note="bold vs body")


def _heading(text: str, signals: List[EvidenceSignal], order: int = 0, level: int = 1) -> Heading:
    h = Heading(level=HeadingLevel(level), text=text, page_number=1, document_order=order)
    h.evidence_items = list(signals)
    h.confidence = 0.35 if signals == [TITLE_POSITION] else 0.7
    return h


def _document(*headings: Heading) -> Document:
    return Document(
        source_pdf_path="x.pdf",
        metadata=Metadata(filename="x.pdf", page_count=1),
        headings=list(headings),
    )


class TestTheRuleNoLongerFires:
    def test_a_position_corroborated_h1_is_not_flagged(self) -> None:
        # The shape the retired rule looked for cannot occur any more:
        # since L3.2 a bundle containing title_position always contains a
        # typographic signal beside it, because that signal is what made
        # the line a heading in the first place.
        document = _document(_heading("A Real Title", [BOLD, TITLE_POSITION]))
        assert HeadingVerifier().inspect(document) == []

    def test_even_a_position_only_bundle_is_not_flagged(self) -> None:
        # Belt and braces: a document persisted before L3.2 can still hold
        # such a bundle on disk. Re-inspecting it must not re-propose a
        # decision its reviewer may already have made.
        document = _document(_heading("Article", [TITLE_POSITION]))
        assert HeadingVerifier().inspect(document) == []

    def test_the_retired_rule_id_is_not_reissued(self) -> None:
        # A rule id names one meaning for the lifetime of the corpus; the
        # retired HEADING_VERIFY_006 must not come back as something else.
        table = HeadingVerifier().rule_table()
        assert "positional_only_h1" not in table
        assert all(spec.rule_id != "HEADING_VERIFY_006" for spec in table.values())


class TestPersistedDecisionsStillApply:
    """A correction recorded before L3.2 must still apply and still undo."""

    def test_legacy_correction_removes_and_undo_restores(self) -> None:
        import src.verification.headings  # noqa: F401 - registers HeadingVerifier

        stale = _heading("Article", [TITLE_POSITION], order=0)
        document = _document(stale, _heading("Real Heading", [BOLD], order=1, level=2))
        correction = CorrectionRecord(
            object_type="heading",
            object_id=stale.id,
            field="positional_only_h1",
            original_value=_encode_recovery(stale),
            proposed_value=_encode_recovery(stale),
            reason_code="HEADING_POSITIONAL_ONLY",
            status=CorrectionStatus.PROPOSED,
            provider="rawrs_native",
        )
        document.corrections.append(correction)

        engine.apply_correction(document, correction)
        assert [h.text for h in document.headings] == ["Real Heading"]

        engine.revert_correction(document, correction)
        assert "Article" in {h.text for h in document.headings}
