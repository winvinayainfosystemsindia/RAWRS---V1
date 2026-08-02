"""Tests for src/headings/heading_signals.py (L3.1 heading evidence layer).

Two obligations, and they pull in opposite directions:

1. **Nothing decided changed.** This unit restructured a first-match-wins
   tier cascade into named signals plus a precedence resolver. If any
   line's decided level moved, the heading KPI moves with it, so the
   precedence tests below pin each historical tier's outcome - including
   the cases where one tier deliberately beats another.
2. **Something recorded did change.** Every signal now runs, so the
   evidence bundle shows corroboration (or its absence) even when it did
   not win the decision. That is the whole point of the unit, and the
   confidence tests pin it.
"""

from collections import Counter
from pathlib import Path
from typing import List, Tuple

import fitz
import pytest

from src.headings.heading_detector import detect_headings
from src.headings.heading_signals import (
    FallbackFontSignal,
    HeadingCandidate,
    evaluate_heading,
)
from src.models.contracts import HeadingLevel
from src.ocr.extractor import extract_text
from src.parser.pdf_parser import parse_pdf

BODY = (10.0, False)  # (font size, is_bold) profile for non-bold body text
BOLD_LINE = (12.0, True)


def _candidate(text: str, **overrides) -> HeadingCandidate:
    """A candidate with the layout inputs a real document supplies."""
    fields = dict(text=text, body_profile=BODY)
    fields.update(overrides)
    return HeadingCandidate(**fields)


def _signal_names(text: str, **overrides) -> List[str]:
    return [s.name for s in evaluate_heading(_candidate(text, **overrides)).bundle.signals]


class TestDecisionIsUnchanged:
    """Each historical tier still decides the same way it always did."""

    @pytest.mark.parametrize(
        "text,overrides,expected",
        [
            # Tier 1 - numbering depth sets the level from dot count.
            ("1.2.3.4 Deep", {}, HeadingLevel.H5),
            ("1.2.3 Deeper", {}, HeadingLevel.H4),
            ("1.2 Overview", {}, HeadingLevel.H3),
            # Tier 2 - the positional H1 slot.
            ("The Culture of Education", {"is_h1_slot": True}, HeadingLevel.H1),
            # Tier 3 - chapter pattern and structural keywords.
            ("Chapter 3", {}, HeadingLevel.H2),
            ("Unit 12", {}, HeadingLevel.H2),
            ("References", {}, HeadingLevel.H2),
            ("keywords", {}, HeadingLevel.H2),
            # Tier 4 - bold against non-bold body.
            ("Teaching as an Art", {"layout": BOLD_LINE}, HeadingLevel.H2),
            # Nothing fires: plain body text with no signal at all.
            ("a sentence of ordinary prose", {}, None),
        ],
    )
    def test_tier_outcomes(self, text: str, overrides: dict, expected) -> None:
        assert evaluate_heading(_candidate(text, **overrides)).level is expected

    def test_h1_slot_still_outranks_the_chapter_pattern(self) -> None:
        # A short excerpt whose first line is "Chapter 9" gets H1 - it IS
        # this excerpt's title. The historical cascade checked the slot
        # before the chapter rule specifically to preserve this, so the
        # declared precedence has to keep doing it.
        assert evaluate_heading(_candidate("Chapter 9", is_h1_slot=True)).level is HeadingLevel.H1
        assert evaluate_heading(_candidate("Chapter 9")).level is HeadingLevel.H2

    def test_numbering_still_outranks_the_h1_slot(self) -> None:
        assert (
            evaluate_heading(_candidate("1.2 Overview", is_h1_slot=True)).level is HeadingLevel.H3
        )

    def test_bold_signal_declines_on_the_running_artifact_guards(self) -> None:
        # Both guards are the Running Header/Footer Pollution Audit's, and
        # both must stay hard gates for now: converting them to negative
        # evidence would change the decision, which this unit must not do.
        assert evaluate_heading(_candidate("Brinkmann", layout=BOLD_LINE)).level is HeadingLevel.H2
        assert (
            evaluate_heading(_candidate("Brinkmann", layout=BOLD_LINE, already_emitted=True)).level
            is None
        )
        assert evaluate_heading(_candidate("343", layout=BOLD_LINE)).level is None

    def test_line_longer_than_the_cap_is_never_a_heading(self) -> None:
        verdict = evaluate_heading(_candidate("1.2 " + "x" * 200, layout=BOLD_LINE))
        assert verdict.level is None
        assert verdict.bundle.signals == []


class TestEvidenceIsRecorded:
    """Every signal that fired is recorded, not just the winning one."""

    def test_winning_signal_is_named(self) -> None:
        assert _signal_names("1.2 Overview") == ["section_numbering"]
        assert _signal_names("References") == ["structural_keyword"]
        assert _signal_names("Chapter 3") == ["chapter_pattern"]
        assert _signal_names("Teaching as an Art", layout=BOLD_LINE) == ["bold_contrast"]

    def test_losing_signals_are_recorded_too(self) -> None:
        # A bold, numbered line: numbering wins the level, but the bold
        # corroboration is the new information - the old cascade returned
        # at the numbering tier and never consulted the bold one.
        verdict = evaluate_heading(_candidate("1.2 Overview", layout=BOLD_LINE))
        assert verdict.level is HeadingLevel.H3
        assert [s.name for s in verdict.bundle.signals] == ["section_numbering", "bold_contrast"]

    def test_recurring_font_signal_fires_when_bold_cannot_see_the_heading(self) -> None:
        # bug_002's shape: a distinct embedded font subset with no bold
        # flag, reused across the document, on its own line.
        verdict = evaluate_heading(
            _candidate(
                "Qualitative Inquiry",
                layout=(12.0, False),
                font_signal=FallbackFontSignal("AdvP7D0F", 12.0, is_sole_line=True),
                body_font_name="AdvTimes",
                signature_counts=Counter({("AdvP7D0F", 12.0): 12}),
            )
        )
        assert verdict.level is HeadingLevel.H2
        assert [s.name for s in verdict.bundle.signals] == ["recurring_heading_font"]

    def test_signals_carry_their_source_module(self) -> None:
        signal = evaluate_heading(_candidate("1.2 Overview")).bundle.signals[0]
        assert signal.source_module == "src.headings.heading_signals"
        assert signal.note  # every signal explains itself to a reviewer


class TestConfidenceDiscriminates:
    """A guess and a corroborated detection must not score the same.

    This is what the unit exists to make possible: bug_003 (a journal
    section kicker label winning the H1 slot ahead of the real title) is
    the positional signal firing alone, and until now that was
    indistinguishable downstream from a heading three signals agreed on.
    """

    def test_positional_only_heading_scores_lowest(self) -> None:
        positional = evaluate_heading(_candidate("Article", is_h1_slot=True))
        numbered = evaluate_heading(_candidate("1.2 Overview"))
        keyword = evaluate_heading(_candidate("References"))

        assert positional.level is HeadingLevel.H1
        assert positional.bundle.confidence < keyword.bundle.confidence
        assert positional.bundle.confidence < numbered.bundle.confidence

    def test_corroboration_raises_confidence_above_the_weaker_signal_alone(self) -> None:
        bold_only = evaluate_heading(_candidate("Teaching as an Art", layout=BOLD_LINE))
        corroborated = evaluate_heading(_candidate("1.2 Overview", layout=BOLD_LINE))
        assert corroborated.bundle.confidence > bold_only.bundle.confidence

    def test_no_signal_means_no_confidence(self) -> None:
        verdict = evaluate_heading(_candidate("a sentence of ordinary prose"))
        assert verdict.level is None
        assert verdict.bundle.confidence == 0.0

    def test_explanation_lists_every_contributing_signal(self) -> None:
        explanation = evaluate_heading(
            _candidate("1.2 Overview", layout=BOLD_LINE)
        ).bundle.explanation
        assert "section_numbering" in explanation
        assert "bold_contrast" in explanation


def _one_page_document(tmp_path: Path, lines: List[Tuple[str, str, float]]):
    """Real PDF -> real parser -> real extraction, so detect_headings reads
    genuine layout signal rather than a hand-built fixture."""
    pdf_path = tmp_path / "evidence.pdf"
    doc = fitz.open()
    page = doc.new_page()
    y = 72.0
    for text, fontname, fontsize in lines:
        page.insert_text((72, y), text, fontname=fontname, fontsize=fontsize)
        y += fontsize + 10
    doc.save(str(pdf_path))
    doc.close()
    return extract_text(parse_pdf(pdf_path))


class TestEvidenceReachesTheDocument:
    """The bundle has to survive the trip onto Heading, or none of the
    above is visible to a reviewer or to the correction rail."""

    def test_detected_headings_carry_confidence_and_evidence(self, tmp_path: Path) -> None:
        document = detect_headings(
            _one_page_document(
                tmp_path,
                [
                    # Large but NOT bold - the shape that makes the H1 slot
                    # fire alone, with no typographic corroboration. Size is
                    # deliberately not a heading signal (2 of 3 born-digital
                    # benchmark PDFs have a non-bold subtitle as the largest
                    # text on the page).
                    ("The Culture of Education", "helv", 18.0),
                    ("1.2 Overview", "hebo", 12.0),
                    ("ordinary body prose that is not a heading", "helv", 10.0),
                ],
            )
        )
        content = {h.text: h for h in document.headings if not h.is_page_marker}

        overview = content["1.2 Overview"]
        assert overview.confidence is not None and overview.confidence > 0
        assert "section_numbering" in {s.name for s in overview.evidence_items}

        title = content["The Culture of Education"]
        assert title.level is HeadingLevel.H1
        assert {s.name for s in title.evidence_items} == {"positional_h1_slot"}
        # The title rests on position alone; the numbered heading does not.
        assert title.confidence < overview.confidence

    def test_page_markers_carry_no_heading_evidence(self, tmp_path: Path) -> None:
        # H6 markers are built by page_markers.py, not by signal
        # evaluation - an empty list here means "no evidence recorded",
        # which is the correct and intended reading.
        document = detect_headings(_one_page_document(tmp_path, [("Body text", "helv", 10.0)]))
        markers = [h for h in document.headings if h.is_page_marker]
        assert markers
        assert all(marker.evidence_items == [] for marker in markers)
