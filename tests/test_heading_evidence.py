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
    """Each evidence-bearing tier still decides the same way it always did."""

    @pytest.mark.parametrize(
        "text,overrides,expected",
        [
            # Tier 1 - numbering depth sets the level from dot count.
            ("1.2.3.4 Deep", {}, HeadingLevel.H5),
            ("1.2.3 Deeper", {}, HeadingLevel.H4),
            ("1.2 Overview", {}, HeadingLevel.H3),
            # The document's title position, with nothing else: since L3.2
            # this is not a heading at all (see TestPositionCannotCreate).
            ("The Culture of Education", {"is_h1_slot": True}, None),
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

    def test_title_position_promotes_an_evidenced_chapter_heading(self) -> None:
        # A short excerpt whose first line is "Chapter 9" still gets H1 - it
        # IS this excerpt's title. What changed in L3.2 is why: the chapter
        # pattern makes it a heading, and the title position then ranks it,
        # rather than position deciding both questions at once.
        assert evaluate_heading(_candidate("Chapter 9", is_h1_slot=True)).level is HeadingLevel.H1
        assert evaluate_heading(_candidate("Chapter 9")).level is HeadingLevel.H2

    def test_numbering_states_its_own_level_and_keeps_it(self) -> None:
        # The only signal immune to the promotion: "1.2" declares depth 3
        # about itself, and opening the document does not make it the title.
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


class TestPositionCannotCreate:
    """L3.2: position ranks a heading; it never makes one.

    bug_003 - 'Article', a journal section kicker label, winning the title
    slot ahead of the real title - is the old assumption failing. L3.1
    made it visible by scoring it lowest; this is where it stops being
    produced at all.
    """

    def test_position_alone_is_not_a_heading(self) -> None:
        verdict = evaluate_heading(_candidate("Article", is_h1_slot=True))
        assert verdict.level is None
        assert verdict.bundle.signals == []

    def test_position_records_itself_when_it_promotes(self) -> None:
        # Bold makes it a heading (H2); the title position raises it to H1
        # and says so in the bundle, so a reviewer sees both reasons.
        verdict = evaluate_heading(
            _candidate("Aims of Education", layout=BOLD_LINE, is_h1_slot=True)
        )
        assert verdict.level is HeadingLevel.H1
        assert [s.name for s in verdict.bundle.signals] == ["bold_contrast", "title_position"]

    def test_promotion_does_not_change_what_the_evidence_was(self) -> None:
        # Same line off the title position: same evidence, one rank lower.
        assert evaluate_heading(_candidate("Aims of Education", layout=BOLD_LINE)).level is (
            HeadingLevel.H2
        )


class TestConfidenceDiscriminates:
    """A thinly-supported detection and a corroborated one must not score
    the same - that discrimination is what L3.1 exists to make possible."""

    def test_position_corroborated_heading_scores_below_a_specific_signal(self) -> None:
        promoted = evaluate_heading(
            _candidate("Aims of Education", layout=BOLD_LINE, is_h1_slot=True)
        )
        numbered = evaluate_heading(_candidate("1.2 Overview"))
        keyword = evaluate_heading(_candidate("References"))

        assert promoted.level is HeadingLevel.H1
        assert promoted.bundle.confidence < keyword.bundle.confidence
        assert promoted.bundle.confidence < numbered.bundle.confidence

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
                    # Bold, so the evidence makes it a heading; first, so the
                    # title position then ranks it H1. Size is deliberately
                    # not a heading signal (2 of 3 born-digital benchmark PDFs
                    # have a non-bold subtitle as the largest text on a page).
                    ("The Culture of Education", "hebo", 18.0),
                    ("1.2 Overview", "hebo", 12.0),
                    ("ordinary body prose that is not a heading", "helv", 10.0),
                    ("more ordinary body prose to settle the body profile", "helv", 10.0),
                ],
            )
        )
        content = {h.text: h for h in document.headings if not h.is_page_marker}

        overview = content["1.2 Overview"]
        assert overview.confidence is not None and overview.confidence > 0
        assert "section_numbering" in {s.name for s in overview.evidence_items}

        title = content["The Culture of Education"]
        assert title.level is HeadingLevel.H1
        assert {s.name for s in title.evidence_items} == {"bold_contrast", "title_position"}
        # The title's evidence is weaker than the numbered heading's, and
        # the confidence says so even though both are real headings.
        assert title.confidence < overview.confidence

    def test_an_unsupported_first_line_produces_no_title(self, tmp_path: Path) -> None:
        # L3.2's visible consequence end to end: a document whose opening
        # line has no typographic support now has no H1, rather than one
        # asserted from position. HEADING_003 is what tells a reviewer so.
        document = detect_headings(
            _one_page_document(
                tmp_path,
                [
                    ("The Culture of Education", "helv", 10.0),
                    ("ordinary body prose that is not a heading", "helv", 10.0),
                ],
            )
        )
        content = [h for h in document.headings if not h.is_page_marker]
        assert content == []

    def test_page_markers_carry_no_heading_evidence(self, tmp_path: Path) -> None:
        # H6 markers are built by page_markers.py, not by signal
        # evaluation - an empty list here means "no evidence recorded",
        # which is the correct and intended reading.
        document = detect_headings(_one_page_document(tmp_path, [("Body text", "helv", 10.0)]))
        markers = [h for h in document.headings if h.is_page_marker]
        assert markers
        assert all(marker.evidence_items == [] for marker in markers)
