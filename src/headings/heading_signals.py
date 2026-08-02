"""Heading signal evaluation for RAWRS (L3.1).

The evidence layer beneath heading classification. Every signal that can
argue a line is a heading lives here as a named function that returns a
graded ``EvidenceSignal``, and ``evaluate_heading()`` runs *all* of them
and returns both the decided level and the full evidence bundle.

Why this module exists
----------------------
``src/headings/heading_detector.py::_classify_line`` grew as a
first-match-wins cascade of five tiers, each with its own accumulated
special-case guards (see that module's docstring for the audit trail
behind each one). Three problems followed from the shape, not from any
individual tier:

1. **Short-circuiting discards evidence.** The moment a tier fired, no
   later tier was consulted, so nothing recorded whether the decision had
   corroboration or rested on a single weak assumption. A heading matched
   only by the positional H1 slot was indistinguishable, downstream, from
   one matched by numbering *and* typography.
2. **No explanation reached the output.** ``Heading`` inherits
   ``SemanticObject.confidence`` and never populated it, so neither a
   reviewer nor the correction rail could tell a strong detection from a
   guess.
3. **Every new failure became a new guard.** ``already_emitted``,
   ``is_bare_page_number``, ``is_sole_line``, the minimum-alpha-chars
   floor and the >=body-size gate are each one observed defect patched
   inside the tier that produced it.

This module addresses (1) and (2) and leaves the decision itself
untouched; (3) is L3.2's concern (see "Transitional policy" below).

Reuses ``src/verification/evidence.py``'s ``EvidenceSignal`` /
``EvidenceBundle`` - the shared evidence-fusion primitive (FEATURE_019)
already used by the table detectors, every verifier, and
``CorrectionRecord.evidence_items`` - rather than introducing a
heading-specific evidence vocabulary. ``src/structure/layout_signals.py``
is the equivalent module for the L1/L2 layout passes; this is its
heading-side counterpart, and the naming is deliberate.

Transitional policy (L3.1)
--------------------------
``evaluate_heading()`` currently decides by **declared precedence**: the
highest-priority signal that fired wins, which reproduces the historical
cascade decision for decision. That is deliberate and temporary - this
commit changes what is *recorded*, never what is *decided*, so it is
KPI-neutral by construction and independently revertible. Genuine
evidence fusion (letting a weak signal be outvoted, and converting the
guards above into negative evidence) is a following, separately
benchmark-gated commit. Until then the scores below are honest about
relative strength but are **not** corpus-calibrated weights - they encode
the specificity ordering the cascade already asserted, nothing more.
"""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from src.models.contracts import HeadingLevel
from src.structure.layout_signals import LineLayout
from src.verification.evidence import EvidenceBundle, EvidenceSignal

_SOURCE_MODULE = "src.headings.heading_signals"

# Lines longer than this are treated as body text, not heading candidates.
_MAX_HEADING_LENGTH = 120

# Numbering depth determines level: one dot -> H3, two dots -> H4, three -> H5
# (docs/HEADING_RULES.md: "3.1 Overview" / "3.1.1 Learning Objectives").
_H5_PATTERN = re.compile(r"^\d+(?:\.\d+){3}\s+\S")
_H4_PATTERN = re.compile(r"^\d+(?:\.\d+){2}\s+\S")
_H3_PATTERN = re.compile(r"^\d+\.\d+\s+\S")

# H2: "Unit 1", "Chapter 3" (docs/HEADING_RULES.md)
_H2_CHAPTER_PATTERN = re.compile(r"^(unit|chapter)\s+\d+\b", re.IGNORECASE)

# H2: common structural section names. "references"/"bibliography" etc. are
# kept as a fixed keyword list rather than relying on the bold layout
# signal, because the benchmark's own ground truth disagrees with itself
# on whether "REFERENCES" is a heading even though it has the identical
# bold layout signal in every document that has it - a keyword rule is
# the only way to be internally consistent here.
_H2_KEYWORDS = {
    "introduction",
    "conclusion",
    "summary",
    "references",
    "abstract",
    "bibliography",
    "appendix",
    "acknowledgements",
    "acknowledgments",
    # Front-Matter Semantic Extraction follow-up: "Keywords" was
    # previously absent from this list, so a PDF's "Keywords" line was
    # never detected as a heading at all (unlike "Abstract"/
    # "References" right next to it) - confirmed against the Brinkman
    # benchmark, where it fell through into an ordinary, unsuppressed
    # body paragraph merged with the keyword list itself.
    "keywords",
}

# Tier 4 Recurrence Guard: a bare page number (e.g. a running footer/
# header digit) is bold in every benchmark PDF that has one, satisfying
# the bold signal's only other condition on every page - but it is never
# identical text twice (each page number differs), so the already-emitted
# recurrence check alone cannot catch it. No legitimate bold heading
# anywhere in the benchmark corpus is digit-only (every real one -
# "Chapter 9", "CHAPTER 1", "TABLE 1.1 ..." - contains at least one real
# word), so this is a safe, content-only (not position-based) second
# condition for the same signal.
_DIGIT_ONLY_PATTERN = re.compile(r"^\d+$")

# bug_002 recurring-font signal: a (font, size) pair must recur at least
# this many times across the document to be treated as a reused heading
# style rather than a one-off title/byline line that merely happens to use
# a distinct font (e.g. Calderhead's/Fullan & Hargreaves' non-bold 18pt
# chapter titles, each of which occurs exactly once).
_FALLBACK_MIN_RECURRENCE = 2

# Signal strength. Scores grade how much *this* signal alone argues for a
# heading; weights grade how much that argument should count. Both encode
# the specificity ordering the historical cascade already asserted (see
# module docstring: numbering is "most specific/unambiguous", position is
# the weakest because it is position alone) - they are NOT corpus-fitted,
# and calibrating them against the benchmark is L3.2's job. A signal that
# does not fire contributes nothing to the bundle rather than a zero:
# a heading having no numbering is genuinely no evidence, not evidence
# against.
_NUMBERING_SCORE, _NUMBERING_WEIGHT = 0.95, 3.0
_KEYWORD_SCORE, _KEYWORD_WEIGHT = 0.90, 2.5
_HEADING_FONT_SCORE, _HEADING_FONT_WEIGHT = 0.75, 2.0
_BOLD_SCORE, _BOLD_WEIGHT = 0.70, 2.0
# Deliberately the weakest signal in the set: it asserts "the document's
# first productive line is its title" from position alone, with no
# typographic corroboration whatsoever. bug_003 (a journal section kicker
# label winning the slot ahead of the real title) is this assumption
# failing. Recording it as weak evidence is what lets L3.2 retire it on
# measured grounds rather than by adding another guard.
_H1_SLOT_SCORE, _H1_SLOT_WEIGHT = 0.35, 1.0


class FallbackFontSignal:
    """Per-line font signal for the recurring-heading-font tier (bug_002).

    Deliberately separate from LineLayout (size, is_bold) - this is a
    different signal (font name + block isolation) for a different,
    later tier, and keeping it out of the shared LineLayout/line_layout()
    avoids touching the signal src/structure/structure_detector.py also
    depends on for TextBlock.is_bold.

    Lives here rather than in heading_detector.py so the signal functions
    below can read it without importing their own caller. Re-exported from
    heading_detector as ``_FallbackSignal`` for existing importers.
    """

    __slots__ = ("font_name", "size", "is_sole_line")

    def __init__(self, font_name: str, size: float, is_sole_line: bool) -> None:
        self.font_name = font_name
        self.size = size
        self.is_sole_line = is_sole_line


@dataclass(frozen=True)
class HeadingCandidate:
    """Everything any signal is allowed to read about one candidate line.

    One explicit input surface for every signal, so adding a signal never
    means threading a new argument through the detector's call chain (the
    growth pattern that produced ``_classify_line``'s eight-parameter
    signature). Optional members mean "signal unavailable" - e.g. a PDF
    whose layout could not be read - and every signal must decline rather
    than assume when its input is absent.
    """

    text: str
    is_h1_slot: bool = False
    layout: Optional[LineLayout] = None
    body_profile: Optional[LineLayout] = None
    font_signal: Optional[FallbackFontSignal] = None
    body_font_name: Optional[str] = None
    signature_counts: Optional[Counter] = None
    already_emitted: bool = False


@dataclass(frozen=True)
class SignalVerdict:
    """One signal's finding: the level it argues for, plus why."""

    level: HeadingLevel
    evidence: EvidenceSignal


@dataclass(frozen=True)
class HeadingVerdict:
    """The decided level (None = not a heading) and the full evidence bundle.

    ``bundle`` holds every signal that fired, including ones that did not
    win the decision - that corroboration record is the point of this
    layer. ``bundle.confidence`` is the weighted mean of those signals'
    scores and is what reaches ``Heading.confidence``.
    """

    level: Optional[HeadingLevel]
    bundle: EvidenceBundle


def _signal(name: str, score: float, weight: float, note: str) -> EvidenceSignal:
    return EvidenceSignal(
        name=name, score=score, weight=weight, note=note, source_module=_SOURCE_MODULE
    )


def numbering_depth(candidate: HeadingCandidate) -> Optional[SignalVerdict]:
    """Explicit decimal section numbering: dot depth sets the level.

    The most specific signal available - "1.2.3 Foo" states its own depth
    rather than having one inferred from typography.
    """
    for pattern, level in (
        (_H5_PATTERN, HeadingLevel.H5),
        (_H4_PATTERN, HeadingLevel.H4),
        (_H3_PATTERN, HeadingLevel.H3),
    ):
        if pattern.match(candidate.text):
            dots = int(level) - 2  # H3 = one dot, H4 = two, H5 = three
            return SignalVerdict(
                level=level,
                evidence=_signal(
                    "section_numbering",
                    _NUMBERING_SCORE,
                    _NUMBERING_WEIGHT,
                    f"decimal section number of depth {dots} sets level {level.name}",
                ),
            )
    return None


def positional_h1_slot(candidate: HeadingCandidate) -> Optional[SignalVerdict]:
    """The document's first productive line, claimed as its title.

    Position only - no typographic corroboration is required or checked,
    which is why this carries the lowest score in the set. The caller owns
    what "productive" means and whether the slot is still open; this
    signal only reports that the slot was claimed.
    """
    if not candidate.is_h1_slot or not any(ch.isalpha() for ch in candidate.text):
        return None
    return SignalVerdict(
        level=HeadingLevel.H1,
        evidence=_signal(
            "positional_h1_slot",
            _H1_SLOT_SCORE,
            _H1_SLOT_WEIGHT,
            "first productive line of the document; position only, no typographic support",
        ),
    )


def structural_keyword(candidate: HeadingCandidate) -> Optional[SignalVerdict]:
    """A chapter/unit number or a known structural section name."""
    if _H2_CHAPTER_PATTERN.match(candidate.text):
        return SignalVerdict(
            level=HeadingLevel.H2,
            evidence=_signal(
                "chapter_pattern",
                _KEYWORD_SCORE,
                _KEYWORD_WEIGHT,
                "matches the chapter/unit numbering pattern",
            ),
        )
    if candidate.text.lower() in _H2_KEYWORDS:
        return SignalVerdict(
            level=HeadingLevel.H2,
            evidence=_signal(
                "structural_keyword",
                _KEYWORD_SCORE,
                _KEYWORD_WEIGHT,
                f"'{candidate.text}' is a known structural section name",
            ),
        )
    return None


def bold_contrast(candidate: HeadingCandidate) -> Optional[SignalVerdict]:
    """Bold where the document's body text is not.

    Font size alone was tried and rejected: in 2 of 3 born-digital
    benchmark PDFs the largest text on the page is a non-bold subtitle
    that must not become a heading, while the real heading is smaller but
    bold - so bold is the gate, not size.

    ``already_emitted`` and the digit-only check remain hard gates here
    (the Running Header/Footer Heading Pollution Audit's findings) rather
    than negative evidence, because turning them into scores would change
    the decision. L3.2 converts them; see module docstring.
    """
    if candidate.layout is None or candidate.body_profile is None:
        return None
    _, line_is_bold = candidate.layout
    _, body_is_bold = candidate.body_profile
    if not line_is_bold or body_is_bold:
        return None
    if candidate.already_emitted:
        return None
    if _DIGIT_ONLY_PATTERN.match(candidate.text):
        return None
    return SignalVerdict(
        level=HeadingLevel.H2,
        evidence=_signal(
            "bold_contrast",
            _BOLD_SCORE,
            _BOLD_WEIGHT,
            "bold against non-bold body text",
        ),
    )


def recurring_heading_font(candidate: HeadingCandidate) -> Optional[SignalVerdict]:
    """A distinct, document-wide reused heading font on an isolated line.

    Last resort for headings whose PDF producer renders "bold-looking"
    section headings via a distinct embedded font subset with no bold flag
    and no "bold" in the font name (confirmed on the Brinkman regression
    PDF: heading font AdvP7D0F vs body AdvTimes, neither bold-flagged).

    Every condition is required (AND, not OR) - deliberately conservative,
    since this signal has no text pattern to fall back on if the font
    evidence misleads. See ``font_signal_supports_heading`` for what each
    condition rules out.
    """
    if not font_signal_supports_heading(candidate):
        return None
    return SignalVerdict(
        level=HeadingLevel.H2,
        evidence=_signal(
            "recurring_heading_font",
            _HEADING_FONT_SCORE,
            _HEADING_FONT_WEIGHT,
            "isolated line in a non-body font reused as a heading style across the document",
        ),
    )


def font_signal_supports_heading(candidate: HeadingCandidate) -> bool:
    """The AND-ed conditions behind ``recurring_heading_font``.

    - not the H1 slot: that signal already resolved this line.
    - the line has at least one alphabetic character.
    - font differs from the document's dominant body font.
    - the (font, size) pair recurs: a one-off title/byline in a distinct
      font (e.g. Calderhead's 18pt chapter title) is not a reused *style*.
      Recurrence counts sole-line contributions only - without that,
      "Chapter 9"/"Chapter 7" (non-sole, sharing a masthead block with the
      chapter title) inflated the count for the separately-blocked byline
      beneath them enough to wrongly satisfy the threshold.
    - sole line in its own PyMuPDF block: a real heading is reliably a
      1-line block; a running header sharing a block with its page number
      ("Brinkmann" + "343" on one baseline) is not. Enforced here and only
      here, never as a global heading requirement - "Chapter 9"/"Chapter 7"
      are real headings that are not sole-line blocks, but the H1-slot
      signal resolves them before this one is consulted.
    - font size at least the body size: table/figure captions and table
      footnotes satisfy every condition above just as real headings do.
      All 12 real Brinkman headings are 12pt against a 10pt body; every
      caption/footnote false positive found was 8-9pt.
    """
    signal = candidate.font_signal
    if candidate.is_h1_slot:
        return False
    if signal is None or candidate.body_font_name is None or candidate.signature_counts is None:
        return False
    if not any(ch.isalpha() for ch in candidate.text):
        return False
    if signal.font_name == candidate.body_font_name:
        return False
    if candidate.signature_counts.get((signal.font_name, signal.size), 0) < _FALLBACK_MIN_RECURRENCE:
        return False
    if not signal.is_sole_line:
        return False
    if candidate.body_profile is not None and signal.size < candidate.body_profile[0]:
        return False
    return True


# Declared precedence, highest first. The order reproduces the historical
# cascade exactly (numbering, then the positional H1 slot, then structural
# keywords, then bold contrast, then the recurring-font last resort), and
# is the whole of the current decision policy - see the module docstring's
# "Transitional policy" note.
_SIGNALS: Tuple[Callable[[HeadingCandidate], Optional[SignalVerdict]], ...] = (
    numbering_depth,
    positional_h1_slot,
    structural_keyword,
    bold_contrast,
    recurring_heading_font,
)


def evaluate_heading(candidate: HeadingCandidate) -> HeadingVerdict:
    """Run every signal over one candidate line and decide its heading level.

    Unlike the cascade this replaces, no signal short-circuits the rest:
    all five are evaluated (they are pure and cheap), so the returned
    bundle records the full corroboration picture even though the decision
    still goes to the highest-precedence signal that fired. A line matched
    only by ``positional_h1_slot`` is therefore now visibly distinct from
    one matched by numbering *and* bold contrast, at identical output.

    Returns a verdict with ``level=None`` and an empty bundle when nothing
    fired, or when the line is too long to be a heading at all.
    """
    if len(candidate.text) > _MAX_HEADING_LENGTH:
        return HeadingVerdict(level=None, bundle=EvidenceBundle())

    verdicts: List[SignalVerdict] = []
    for signal_fn in _SIGNALS:
        verdict = signal_fn(candidate)
        if verdict is not None:
            verdicts.append(verdict)

    bundle = EvidenceBundle(signals=[v.evidence for v in verdicts])
    return HeadingVerdict(level=verdicts[0].level if verdicts else None, bundle=bundle)
