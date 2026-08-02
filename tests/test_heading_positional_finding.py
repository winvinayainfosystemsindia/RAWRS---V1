"""The heading detector states its uncertainty instead of asserting it.

The positional H1 slot claims a document's first productive line is its
title. It is the only signal in heading_signals with no typographic
corroboration, and measuring the benchmark corpus settled what that is
worth: of 87 content headings, exactly 4 rest on it alone, and all 4 are
wrong — 'Article' (a journal kicker, bug_003), 'Jerome Bruner' (an
author), 'xlv' (a roman page label), and a sentence of body prose. The
next tier up (positional + bold) is a genuine title.

So the detector now produces a *finding* for that case rather than
silently asserting a heading — the Finding Producer model applied to the
assumption blueprint step 10 was going to retire blind.
"""

from typing import List

import pytest

from src.models.contracts import Document, Heading, HeadingLevel, Metadata
from src.models.correction import CorrectionStatus
from src.verification.engine import engine
from src.verification.evidence import EvidenceSignal
from src.verification.headings import HeadingVerifier

POSITIONAL = EvidenceSignal(
    name="positional_h1_slot", score=0.35, weight=1.0, note="position only"
)
BOLD = EvidenceSignal(name="bold_contrast", score=0.70, weight=2.0, note="bold vs body")


def _heading(text: str, signals: List[EvidenceSignal], order: int = 0, level: int = 1) -> Heading:
    h = Heading(
        level=HeadingLevel(level), text=text, page_number=1, document_order=order
    )
    h.evidence_items = list(signals)
    h.confidence = 0.35 if signals == [POSITIONAL] else 0.7
    return h


def _document(*headings: Heading) -> Document:
    return Document(
        source_pdf_path="x.pdf",
        metadata=Metadata(filename="x.pdf", page_count=1),
        headings=list(headings),
    )


class TestWhatGetsFlagged:
    def test_uncorroborated_positional_h1_produces_a_finding(self) -> None:
        document = _document(_heading("Article", [POSITIONAL]))
        findings = HeadingVerifier().inspect(document)

        assert len(findings) == 1
        finding = findings[0]
        assert finding.kind == "positional_only_h1"
        assert finding.object_id == "heading-0"
        assert "Article" in finding.message
        # It proposes, never decides — deleting a document's only H1 is a
        # human's call, and 4 corpus instances is a small sample.
        assert finding.auto_apply is False

    def test_corroborated_positional_h1_is_left_alone(self) -> None:
        # positional + bold is the next tier up, and is a genuine title
        # ('AIMS OF EDUCATION: DO TEACHERS NEED TO BE PHILOSOPHERS?').
        document = _document(_heading("A Real Title", [POSITIONAL, BOLD]))
        assert HeadingVerifier().inspect(document) == []

    def test_headings_from_other_signals_are_left_alone(self) -> None:
        document = _document(_heading("1.2 Overview", [BOLD], level=3))
        assert HeadingVerifier().inspect(document) == []

    def test_provider_headings_are_silent_here(self) -> None:
        # Mathpix-supplied headings carry no RAWRS evidence, so the check
        # self-selects out rather than being gated by a path test.
        heading = Heading(level=HeadingLevel(1), text="Imported", page_number=1, document_order=0)
        document = _document(heading)
        assert HeadingVerifier()._uncorroborated_h1_findings(document) == []

    def test_page_markers_are_never_flagged(self) -> None:
        marker = Heading(
            level=HeadingLevel(6), text="1", page_number=1, document_order=0, is_page_marker=True
        )
        marker.evidence_items = [POSITIONAL]
        assert HeadingVerifier().inspect(_document(marker)) == []

    def test_the_finding_carries_the_evidence_that_justifies_it(self) -> None:
        finding = HeadingVerifier().inspect(_document(_heading("Article", [POSITIONAL])))[0]
        assert finding.confidence == 0.35
        assert [s.name for s in finding.evidence_items] == ["positional_h1_slot"]


class TestReviewerDecision:
    """Accepting removes the heading; undo puts it back."""

    def test_accept_removes_and_undo_restores(self) -> None:
        import src.verification.headings  # noqa: F401 - registers HeadingVerifier

        document = _document(
            _heading("Article", [POSITIONAL], order=0),
            _heading("Real Heading", [BOLD], order=1, level=2),
        )
        findings = HeadingVerifier().inspect(document)
        engine.record_findings(document, findings, provider="rawrs_native")

        correction = document.corrections[0]
        assert correction.status is CorrectionStatus.PROPOSED
        assert correction.reason_code == "HEADING_POSITIONAL_ONLY"
        # Proposing must not itself change the document.
        assert len(document.headings) == 2

        engine.apply_correction(document, correction)
        assert [h.text for h in document.headings] == ["Real Heading"]

        engine.revert_correction(document, correction)
        assert "Article" in {h.text for h in document.headings}

    def test_a_proposal_reaches_the_reviewer_queue(self) -> None:
        document = _document(_heading("Article", [POSITIONAL]))
        engine.record_findings(
            document, HeadingVerifier().inspect(document), provider="rawrs_native"
        )
        # PROPOSED is unresolved, so it is a review item — that is the
        # point: RAWRS asks instead of silently asserting a title.
        assert len(document.verification_findings) == 1
