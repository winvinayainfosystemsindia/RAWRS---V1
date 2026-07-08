"""Heading detection for RAWRS.

Detects content headings (H1-H5) from each page's text using
deterministic, rule-based pattern matching plus PDF layout signals
(font size, bold), and generates the H6 page marker required for every
PDF page (see docs/HEADING_RULES.md and docs/PAGE_RULES.md). Populates
Document.headings in document-wide reading order.

Per docs/HEADING_RULES.md, Phase 1 uses rule-based detection only - no
AI, no LLMs, no machine learning. Layout signals are read directly from
the source PDF via PyMuPDF (already a project dependency, no new
package); no OCR is performed, and Page.cleaned_text/raw_text (already
populated by the upstream direct-text-extraction stage) remains the
primary text source. This module independently re-opens
document.source_pdf_path for layout metadata only, following the same
pattern already used by src/images/image_extractor.py and
src/docx/docx_generator.py - the Document/Page models are unchanged.

Detection strategy (see BENCHMARK_RECONCILIATION_AND_PHASE1_PLAN.md
Phase B for the full taxonomy this was derived from):

1. Numbering patterns (H3/H4/H5 dot-depth) - most specific, checked first.
2. The positional H1 slot (first *productive* non-blank line of the
   whole document - see _is_productive_h1_candidate()) - checked before
   the H2 keyword/chapter pattern, so a short excerpt whose first line is
   "Chapter 9" gets H1 (it IS this excerpt's title), while a full book
   whose first line is the book title still leaves "Chapter 1" further
   down to fall through to the H2 rule correctly. H1-slot Robustness
   Repair: the slot stays open across unproductive lines - a bare footer
   page number or a lone decorative drop-cap glyph extracted as its own
   line - rather than being permanently spent on whichever line happens
   to come first in the PDF's raw (not necessarily visual-order)
   extraction order. Confirmed against the benchmark corpus: two
   born-digital PDFs ("1. Nature of Enquiry.pdf", "1.Aims of Education
   and the teacher...pdf") have a footer page number as their literal
   first extracted line, which previously disabled H1 detection for the
   entire document even though a real chapter/title line existed just a
   few lines later on the same page.
3. "Unit N"/"Chapter N" and a fixed structural-keyword list
   (Introduction/Conclusion/References/...) -> H2.
4. Bold-relative-to-body-text layout signal -> H2. This is the
   primary fix for real benchmark headings like "Teaching as an Art" or
   "Teaching as a Common-sense Activity", which are plain Title-Case
   phrases with no numbering at all - the old rule set caught none of
   these. Font SIZE alone was tried and rejected: in 2 of 3 born-digital
   benchmark PDFs, the largest text on the page is a non-bold subtitle
   that must NOT become a heading, while the actual heading line is
   smaller but bold - so bold is the gate, not size. Multi-tier bold
   *sizes* are not used to differentiate H2 vs H3+, since no benchmark
   document exercises more than one bold-heading level. Tier 4
   Recurrence Guard: two additional, content-only conditions (no new
   document pass, no position/geometry signal) confirmed necessary by
   the Running Header/Footer Heading Pollution Audit: (a) declines on a
   line whose exact text already produced a heading earlier in the
   document - the running-header/running-title signature, since a
   repeating bold masthead line satisfies this tier's only other
   condition on every page it appears on, with the first occurrence
   unaffected (it hasn't been emitted yet) and only later repeats
   declined; (b) declines on a bare digit-only line - the running
   page-number signature, which (a) cannot catch since consecutive page
   numbers are never identical text. See _classify_line()'s tier 4
   branch.
5. NEW (bug_002): a last-resort fallback tier for headings whose PDF
   producer renders "bold-looking" section headings via a distinct
   embedded font subset that signal 4 cannot see - the font name has no
   "bold" substring and PyMuPDF sets no bold flag bit (confirmed via
   direct span dump on the Brinkman regression PDF: heading font
   AdvP7D0F vs. body AdvTimes, neither bold-flagged). Reached only when
   tiers 1-4 have all already declined. Fires only when ALL of: the
   line's font differs from the document's dominant body font; that
   (font, size) pair recurs at least twice across the document (a
   one-off title/byline in a distinct font, e.g. Calderhead's 18pt
   "Teaching as a professional activity", is not a reused heading
   style); the line did not already consume the H1 slot; the line has
   at least one alphabetic character; and - this is the part that keeps
   recurring non-body-font elements like running headers/journal
   metadata out - the line is the *sole* line in its own PyMuPDF block
   (a real heading is reliably emitted as a 1-line block in every
   sampled instance; a running header sharing a block with its page
   number, e.g. "Brinkmann" + "343" on the same baseline, is not). See
   notes_md/heading_isolation_signal_review.md (design review) for the
   audit this implements, including why "Chapter 9"/"Chapter 7" (which
   are NOT sole-line blocks - they share a 3-line masthead block with
   the chapter title) are unaffected: both are already resolved by the
   higher-priority H1-slot rule (tier 2) before this tier is ever
   reached, so sole-line-block is enforced only within this tier, never
   as a global heading requirement. A seventh condition, found during
   verification (not part of the original six-condition audit): the
   candidate's font size must be at least the document's body size.
   Table/figure captions and table-footnote lines turned out to satisfy
   all six original gates just as real section headings do - all of
   Brinkman's 12 real headings are 12pt against a 10pt body, while every
   caption/footnote false positive found was 8-9pt, smaller than body.

bug_002 also required one correction to the recurrence count itself:
a (font, size) pair only counts toward recurrence from sole-line
contributions. Without this, "Chapter 9"/"Chapter 7" (non-sole, 14pt
Helvetica, same masthead block as the chapter title) inflated recurrence
for the unrelated, separately-blocked, sole-line byline beneath them
("James Calderhead" / "Michael Fullan and Andy Hargreaves", also 14pt
Helvetica) enough to wrongly satisfy the threshold - a real regression
caught by the benchmark suite, not a hypothetical.

Hierarchy validation (e.g. detecting an H1 -> H3 skip) is explicitly
out of scope here - see docs/VALIDATION_RULES.md. This module's only
job is to faithfully detect and record headings in document order,
even when the detected sequence is hierarchically invalid; the
Validation stage is responsible for flagging that later.

feature_007 (Wrapped Heading Continuation Repair, implemented 2026-06-25
per a dedicated benchmark audit - see
samples/regressions/feature_007_wrapped_heading_continuation_repair/
notes_md/wrapped_heading_continuation_repair_audit.md): a single logical
heading that a PDF's column width wraps onto 2-4 physical lines (e.g.
"1.16  Subjectivity and objectivity in" / "educational research") was
previously emitted as two or more separate Heading objects at the wrong
levels, since every tier above classifies one line at a time with no
cross-line memory. After any tier above has classified a line as a
heading, and only when that line's own layout is bold,
_absorb_continuations() looks ahead and merges subsequent lines that are
confirmed - by matching (font size, is_bold) plus either the same
PyMuPDF block or a narrow, corpus-calibrated cross-block gap_ratio
window - to be the same heading, not a new one or body text. See
_absorb_continuations()'s own docstring for the full gate list.
"""

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

import fitz  # PyMuPDF
from loguru import logger

from src.config.page_numbering import PageNumberingPolicy
from src.models.contracts import Document, Heading, HeadingLevel
from src.structure.layout_signals import LineLayout, line_layout
from src.utils.text_sanitization import sanitize_xml_text

# Lines longer than this are treated as body text, not heading candidates.
_MAX_HEADING_LENGTH = 120

# bug_002 fallback tier: a (font, size) pair must recur at least this many
# times across the document to be treated as a reused heading style rather
# than a one-off title/byline line that merely happens to use a distinct
# font (e.g. Calderhead's/Fullan & Hargreaves' non-bold 18pt chapter
# titles, each of which occurs exactly once).
_FALLBACK_MIN_RECURRENCE = 2

# H1-slot Robustness Repair: a candidate line must contain at least this
# many alphabetic characters to "productively" consume the H1 slot (see
# _is_productive_h1_candidate()). Calibrated against the real benchmark
# corpus: every currently-correct H1 the detector produces is well above
# this - "Article" (7 alpha chars, Brinkman), "Chapter 1"/"Chapter 7"/
# "Chapter 9" (7 alpha chars each), "THE CULTURE OF EDUCATION" (21 alpha
# chars) - while the two confirmed defects are a bare footer page number
# ("3"/"1", 0 alpha chars) and a stray decorative drop-cap glyph
# extracted as its own line ("e", 1 alpha char, sockett_profession.pdf).
# 2 sits with a wide margin above both defects and far below the
# shortest genuine H1 (7), so it excludes the known-bad cases without
# coming anywhere close to a real title.
_MIN_H1_SLOT_ALPHA_CHARS = 2

# Tier 4 Recurrence Guard: a bare page number (e.g. a running footer/
# header digit) is bold in every benchmark PDF that has one, satisfying
# tier 4's only other condition on every page - but it is never
# identical text twice (each page number differs), so the
# emitted_heading_texts recurrence check alone cannot catch it. No
# legitimate bold heading anywhere in the benchmark corpus is
# digit-only (every real one - "Chapter 9", "CHAPTER 1", "TABLE 1.1
# ..." - contains at least one real word), so this is a safe,
# content-only (not position-based) second condition for the same tier.
_DIGIT_ONLY_PATTERN = re.compile(r"^\d+$")

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

# Numbering depth determines level: one dot -> H3, two dots -> H4, three -> H5
# (docs/HEADING_RULES.md: "3.1 Overview" / "3.1.1 Learning Objectives").
_H5_PATTERN = re.compile(r"^\d+(?:\.\d+){3}\s+\S")
_H4_PATTERN = re.compile(r"^\d+(?:\.\d+){2}\s+\S")
_H3_PATTERN = re.compile(r"^\d+\.\d+\s+\S")

# Wrapped Heading Continuation Repair (feature_007): geometric continuity
# window for the cross-block fallback path only (same-block continuations
# need no ratio check at all - see _is_confirmed_continuation()). Bounds
# corpus-confirmed, not assumed: an exhaustive sweep of every bold,
# font/size-matching, cross-block adjacent line pair across the entire
# 10-PDF benchmark corpus found exactly one real continuation
# (gap_ratio=+0.377, Aims of Education's title) and 7 confirmed
# non-continuations (running-header/page-number pairs and one
# reading-order-inverted masthead, ratios -2.317 and +0.917 to +1.500) -
# see samples/regressions/feature_007_wrapped_heading_continuation_repair/
# notes_md/wrapped_heading_continuation_repair_audit.md Section 7. This
# window sits with margin on both sides of the single confirmed positive
# example and is nowhere near any confirmed negative example.
_CROSS_BLOCK_GAP_RATIO_MIN = -0.20
_CROSS_BLOCK_GAP_RATIO_MAX = 0.45

# Defensive cap on how many continuation lines a single heading can
# absorb - comfortably above the largest confirmed real case (3
# continuation lines, heading 1.11's 4-line total), pure insurance
# against a pathological document rather than a calibrated value.
_MAX_CONTINUATION_LINES = 4


def detect_headings(
    document: Document,
    page_numbering_policy: Optional[PageNumberingPolicy] = None,
) -> Document:
    """Detect headings across a Document and populate document.headings.

    Args:
        document: A Document with Page.cleaned_text (or raw_text)
            already populated for each page by the upstream text
            extraction stage, and source_pdf_path pointing to a
            readable PDF (used here only to read layout signals - if
            it cannot be read, detection falls back to text-pattern
            rules only, it does not raise).
        page_numbering_policy: Controls which pages receive H6 markers
            and what text those markers contain.  When None (default)
            the legacy behaviour is preserved: every page receives a
            marker whose text is the detected printed label if available,
            falling back to the physical page number — identical to the
            behaviour before this parameter existed.

    Returns:
        The same Document instance with document.headings populated, in
        document-wide reading order: pages in order, and within each
        page, that page's H6 marker first (when the policy permits one),
        followed by its content headings (H1-H5) in line order.
    """
    logger.info("Detecting headings for '{}'", document.source_pdf_path)

    # _build_layout_index's third return value (bbox_index) feeds
    # feature_007 (Wrapped Heading Continuation Repair, see
    # _absorb_continuations() below) - see DECISIONS_LOG.md Part 10 for
    # why this call site previously discarded it (a half-finished prior
    # edit, fixed as bug_007) before this feature existed to consume it.
    layout_index, body_profile, bbox_index = _build_layout_index(document.source_pdf_path)
    fallback_index, body_font_name, signature_counts = _build_fallback_tier_index(
        document.source_pdf_path
    )

    headings: List[Heading] = []
    order = 0
    h1_slot_open = True  # only the first non-blank line in the whole document is eligible for H1
    # Tier 4 Recurrence Guard: texts that have already produced a heading
    # (any tier), so tier 4 (the bold-layout signal) can decline on a
    # repeat occurrence of the same exact text - see _classify_line()'s
    # tier 4 branch and the Running Header/Footer Heading Pollution Audit.
    emitted_heading_texts: Set[str] = set()

    for page in document.pages:
        # Resolve the marker text for this page according to the active
        # policy.  When no policy is supplied (legacy callers) the
        # original feature_009 behaviour is preserved: prefer the
        # reviewed page_label (FEATURE_018; falls back to printed_label
        # when no reviewer action has been taken), then the physical page
        # number, and always emit a marker.  When a policy IS supplied it
        # acts as the sole decision point: returning None suppresses the
        # marker entirely (e.g. AUTO mode on a page with no detected
        # printed number, or DISABLED, or a page outside MANUAL_RANGE).
        effective_label = page.page_label or page.printed_label
        if page_numbering_policy is not None:
            marker_text: Optional[str] = page_numbering_policy.resolve_marker_text(
                page.page_number, effective_label
            )
        else:
            marker_text = effective_label or str(page.page_number)

        if marker_text is not None:
            headings.append(
                Heading(
                    level=HeadingLevel.H6,
                    text=marker_text,
                    page_number=page.page_number,
                    document_order=order,
                    is_page_marker=True,
                )
            )
            order += 1

        text = page.cleaned_text or page.raw_text
        page_layouts = layout_index.get(page.page_number, {})
        page_bboxes = bbox_index.get(page.page_number, {})
        page_fallback_signals = fallback_index.get(page.page_number, {})

        # Materialized (not the plain generator used before) so feature_007
        # can look ahead at subsequent lines and skip past any it absorbs -
        # a page is at most a few hundred lines, trivial cost.
        page_lines = list(_iter_candidate_lines(text))
        line_index = 0
        while line_index < len(page_lines):
            line = page_lines[line_index]
            # H1-slot Robustness Repair: the slot stays open across
            # unproductive lines (bare footer page numbers, stray
            # single-character decorative glyphs) instead of being
            # consumed by whichever line happens to come first in the
            # PDF's raw extraction order - see _is_productive_h1_candidate().
            line_claims_h1_slot = h1_slot_open and _is_productive_h1_candidate(line)
            layout = page_layouts.get(line)
            level = _classify_line(
                line,
                is_h1_slot=line_claims_h1_slot,
                layout=layout,
                body_profile=body_profile,
                fallback_signal=page_fallback_signals.get(line),
                body_font_name=body_font_name,
                signature_counts=signature_counts,
                emitted_heading_texts=emitted_heading_texts,
            )
            if line_claims_h1_slot:
                h1_slot_open = False  # consumed productively - never re-opens

            if level is None:
                line_index += 1
                continue

            # feature_007 (Wrapped Heading Continuation Repair): only
            # ever attempted after the existing, unmodified tier chain
            # above has already classified this line as a heading -
            # every tier's own logic is untouched. Gated on this line's
            # own layout being bold: confirmed by the benchmark audit to
            # be exactly what separates the 9 real wrap cases from the
            # "Chapter 3);" false-positive trap (a tier-3 text-pattern
            # match on a plain, non-bold body-text line, which must
            # never be allowed to start absorbing the rest of its own
            # paragraph) - see notes_md/
            # wrapped_heading_continuation_repair_audit.md Section 1.5.
            heading_text = line
            lines_absorbed = 0
            if layout is not None and layout[1]:
                heading_text, lines_absorbed = _absorb_continuations(
                    anchor_text=line,
                    anchor_layout=layout,
                    page_lines=page_lines,
                    anchor_index=line_index,
                    page_layouts=page_layouts,
                    page_bboxes=page_bboxes,
                )

            emitted_heading_texts.add(heading_text)

            headings.append(
                Heading(
                    level=level,
                    text=heading_text,
                    page_number=page.page_number,
                    document_order=order,
                    is_page_marker=False,
                )
            )
            order += 1
            line_index += 1 + lines_absorbed

    document.headings = headings

    content_heading_count = sum(1 for h in headings if not h.is_page_marker)
    logger.info(
        "Detected {} content heading(s) and {} page marker(s) for '{}'",
        content_heading_count,
        len(headings) - content_heading_count,
        document.source_pdf_path,
    )
    return document


def detect_headings_from_pdf(pdf_path: Path) -> List[Heading]:
    """Pure PDF-side candidate source for cross-source verification
    (src/verification/headings.py::HeadingVerifier).

    Sources line text directly from PyMuPDF instead of
    ``Document.pages[i].cleaned_text`` — on the Mathpix import path that
    field holds Mathpix's text, not the PDF's own, so it cannot be reused
    as independent PDF evidence. Reuses the exact same classification
    helpers ``detect_headings()`` calls (``_build_layout_index``,
    ``_build_fallback_tier_index``, ``_classify_line``,
    ``_absorb_continuations``, ``_iter_candidate_lines``) — zero
    duplicated classification logic, and ``detect_headings()`` itself is
    completely untouched by this addition.

    Content headings (H1-H5) only; H6 page markers are
    ``detect_headings()``'s/the Mathpix import's concern (see
    ``src/verification/pagelabels.py``, a future asset type — not this
    one), not reproduced here.

    Never touches a Document; never raises — an unreadable PDF yields [].
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        return []

    try:
        pdf_document = fitz.open(pdf_path)
    except Exception as exc:  # PyMuPDF raises various error types on bad input
        logger.warning("Could not open PDF for heading candidate detection '{}': {}", pdf_path, exc)
        return []
    try:
        page_texts: Dict[int, str] = {
            page_index + 1: pdf_document[page_index].get_text()
            for page_index in range(pdf_document.page_count)
        }
    finally:
        pdf_document.close()

    layout_index, body_profile, bbox_index = _build_layout_index(str(pdf_path))
    fallback_index, body_font_name, signature_counts = _build_fallback_tier_index(str(pdf_path))

    headings: List[Heading] = []
    order = 0
    h1_slot_open = True
    emitted_heading_texts: Set[str] = set()

    for page_number in sorted(page_texts):
        text = page_texts[page_number]
        page_layouts = layout_index.get(page_number, {})
        page_bboxes = bbox_index.get(page_number, {})
        page_fallback_signals = fallback_index.get(page_number, {})

        page_lines = list(_iter_candidate_lines(text))
        line_index = 0
        while line_index < len(page_lines):
            line = page_lines[line_index]
            line_claims_h1_slot = h1_slot_open and _is_productive_h1_candidate(line)
            layout = page_layouts.get(line)
            level = _classify_line(
                line,
                is_h1_slot=line_claims_h1_slot,
                layout=layout,
                body_profile=body_profile,
                fallback_signal=page_fallback_signals.get(line),
                body_font_name=body_font_name,
                signature_counts=signature_counts,
                emitted_heading_texts=emitted_heading_texts,
            )
            if line_claims_h1_slot:
                h1_slot_open = False

            if level is None:
                line_index += 1
                continue

            heading_text = line
            lines_absorbed = 0
            if layout is not None and layout[1]:
                heading_text, lines_absorbed = _absorb_continuations(
                    anchor_text=line,
                    anchor_layout=layout,
                    page_lines=page_lines,
                    anchor_index=line_index,
                    page_layouts=page_layouts,
                    page_bboxes=page_bboxes,
                )

            emitted_heading_texts.add(heading_text)
            headings.append(
                Heading(
                    level=level,
                    text=heading_text,
                    page_number=page_number,
                    document_order=order,
                    is_page_marker=False,
                    source="pdf_native",
                )
            )
            order += 1
            line_index += 1 + lines_absorbed

    return headings


def _iter_candidate_lines(text: str) -> Iterator[str]:
    """Yield non-blank, whitespace-trimmed lines from page text."""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line:
            yield line


def _is_productive_h1_candidate(line: str) -> bool:
    """Whether this line is substantial enough to claim the H1 slot.

    H1-slot Robustness Repair: requires at least _MIN_H1_SLOT_ALPHA_CHARS
    alphabetic characters, not just one. A bare footer page number ("3",
    "1") has zero alphabetic characters and must not claim the slot - the
    real title/chapter line several lines later should get the chance
    instead. A lone decorative drop-cap glyph extracted as its own line
    ("e") has exactly one alphabetic character and is exactly as
    unproductive a claim as the page number - both are PDF-extraction
    artifacts, not real heading text, so both leave the slot open rather
    than spending it on a fragment.
    """
    return sum(1 for ch in line if ch.isalpha()) >= _MIN_H1_SLOT_ALPHA_CHARS


def _classify_line(
    line: str,
    is_h1_slot: bool,
    layout: Optional[LineLayout],
    body_profile: Optional[LineLayout],
    fallback_signal: Optional["_FallbackSignal"] = None,
    body_font_name: Optional[str] = None,
    signature_counts: Optional[Counter] = None,
    emitted_heading_texts: Optional[Set[str]] = None,
) -> Optional[HeadingLevel]:
    """Classify a single line as a heading level, or None if it is not one.

    Numbering patterns first (most specific/unambiguous), then the
    positional H1 slot, then the chapter/structural-keyword rules, then
    the bold layout signal, then (bug_002) the distinct-recurring-font
    isolation fallback as a last resort for headings none of the rules
    above can see. Every tier above the new one is unchanged from before
    bug_002 - the new tier is appended last and only ever reached when
    all of them have already declined.

    Tier 4 Recurrence Guard (Running Header/Footer Heading Pollution
    Repair): tier 4 (the bold-layout signal immediately below) declines
    on a line whose exact text has already produced a heading earlier in
    this document - confirmed by benchmark audit to be the running
    header/footer/page-number signature (a repeating bold masthead line
    or page number satisfies tier 4's only condition, "bold and larger
    than body," on every page it appears on, with no recurrence check of
    its own, unlike tier 5's signature_counts/is_sole_line guard a few
    lines below). The first occurrence of a recurring bold title (e.g. a
    book/chapter title that also happens to be a running header) is
    unaffected - it has not yet been emitted when it is itself
    classified, so it still becomes a heading exactly as before; only
    its later repeats are declined here. Tiers 1, 2, 3, and 5 are not
    consulted against emitted_heading_texts at all - confirmed safe
    because tier 3's _H2_KEYWORDS entries (e.g. "References"/
    "Conclusion") are expected to legitimately recur across a
    multi-chapter document, and must keep doing so.
    """
    if len(line) > _MAX_HEADING_LENGTH:
        return None

    if _H5_PATTERN.match(line):
        return HeadingLevel.H5
    if _H4_PATTERN.match(line):
        return HeadingLevel.H4
    if _H3_PATTERN.match(line):
        return HeadingLevel.H3

    if is_h1_slot and any(ch.isalpha() for ch in line):
        return HeadingLevel.H1

    if _H2_CHAPTER_PATTERN.match(line) or line.lower() in _H2_KEYWORDS:
        return HeadingLevel.H2

    if layout is not None and body_profile is not None:
        _, line_is_bold = layout
        _, body_is_bold = body_profile
        already_emitted = emitted_heading_texts is not None and line in emitted_heading_texts
        is_bare_page_number = bool(_DIGIT_ONLY_PATTERN.match(line))
        if line_is_bold and not body_is_bold and not already_emitted and not is_bare_page_number:
            return HeadingLevel.H2

    if _is_fallback_heading(
        line,
        is_h1_slot=is_h1_slot,
        fallback_signal=fallback_signal,
        body_font_name=body_font_name,
        signature_counts=signature_counts,
        body_profile=body_profile,
    ):
        return HeadingLevel.H2

    return None


def _is_fallback_heading(
    line: str,
    is_h1_slot: bool,
    fallback_signal: Optional["_FallbackSignal"],
    body_font_name: Optional[str],
    signature_counts: Optional[Counter],
    body_profile: Optional[LineLayout],
) -> bool:
    """bug_002 last-resort fallback tier.

    Every condition below is required (AND, not OR) - this is
    deliberately conservative, since this tier has no text-pattern
    signal to fall back on if the layout signal is wrong. Sole-line-block
    is enforced here, and only here, never as a global heading
    requirement (see module docstring point 5 and
    notes_md/heading_isolation_signal_review.md): "Chapter 9"/"Chapter 7"
    are real headings that are NOT sole-line blocks, but they are
    resolved by the H1-slot tier above before this function is ever
    called for them, so the restriction is safe.

    One condition beyond the originally-audited six: the candidate's
    font size must be at least the document's body size. Verification
    against the real Brinkman PDF found that table/figure captions and
    table-footnote lines (8-9pt, in a font distinct from body, sole-line,
    and recurring across the document's several tables/figures) satisfy
    every one of the original six gates just as the 12 real section
    headings do - the six gates alone cannot tell "a font reused for
    section headings" apart from "a font reused for captions." All 12
    real Brinkman headings are 12pt against a 10pt body; every caption/
    footnote false positive found was 8-9pt - smaller than body, not
    larger. This reuses body_profile's already-computed body size (no
    new PDF pass) and does not touch any of the six original conditions.
    """
    if is_h1_slot:
        return False
    if fallback_signal is None or body_font_name is None or signature_counts is None:
        return False
    if not any(ch.isalpha() for ch in line):
        return False
    if fallback_signal.font_name == body_font_name:
        return False
    signature = (fallback_signal.font_name, fallback_signal.size)
    if signature_counts.get(signature, 0) < _FALLBACK_MIN_RECURRENCE:
        return False
    if not fallback_signal.is_sole_line:
        return False
    if body_profile is not None:
        body_size, _ = body_profile
        if fallback_signal.size < body_size:
            return False
    return True


def _absorb_continuations(
    anchor_text: str,
    anchor_layout: LineLayout,
    page_lines: List[str],
    anchor_index: int,
    page_layouts: Dict[str, LineLayout],
    page_bboxes: Dict[str, Tuple[int, float, float]],
) -> Tuple[str, int]:
    """feature_007 (Wrapped Heading Continuation Repair): absorb up to
    _MAX_CONTINUATION_LINES subsequent candidate lines into a single
    already-classified heading, when each one is confirmed - not
    assumed - to be the same logical heading wrapped onto another
    physical PDF line.

    Caller already confirmed anchor_layout's bold flag is True before
    calling this - see the benchmark audit's Section 1.5 for why that
    gate is load-bearing (it is what excludes the "Chapter 3);"
    false-positive trap, a tier-3 text-pattern match on a non-bold body
    line, from ever starting an absorption attempt).

    Returns (merged_text, lines_absorbed). lines_absorbed is 0 - no
    absorption, anchor_text returned unchanged - when bbox data for the
    anchor is missing (the PDF could not be opened for layout analysis;
    decline gracefully rather than guess) or when the very next line
    fails any gate.
    """
    anchor_bbox = page_bboxes.get(anchor_text)
    if anchor_bbox is None:
        return anchor_text, 0

    merged_text = anchor_text
    current_bbox = anchor_bbox
    absorbed = 0

    while absorbed < _MAX_CONTINUATION_LINES:
        next_index = anchor_index + absorbed + 1
        if next_index >= len(page_lines):
            break
        candidate = page_lines[next_index]

        # Never absorb a line that is itself unambiguously a new
        # heading - the direct code expression of "preserve all
        # existing tiers unless a continuation is confirmed" for the
        # one scenario the benchmark audit could not rule out
        # structurally (two genuine headings with no body text between
        # them). No corpus case currently exercises this path.
        if _matches_new_heading_pattern(candidate):
            break

        candidate_layout = page_layouts.get(candidate)
        if candidate_layout != anchor_layout:
            break

        candidate_bbox = page_bboxes.get(candidate)
        if candidate_bbox is None:
            break

        if not _is_confirmed_continuation(current_bbox, candidate_bbox):
            break

        merged_text = _join_with_local_hyphen_repair(merged_text, candidate)
        current_bbox = candidate_bbox
        absorbed += 1

    return merged_text, absorbed


def _matches_new_heading_pattern(line: str) -> bool:
    """feature_007 guard: True when `line` independently matches one of
    the text-pattern tiers (numbering, chapter, or keyword) - an
    unambiguous signal it is meant to be its own heading, never a
    continuation of the one before it, regardless of layout/geometry."""
    if _H5_PATTERN.match(line) or _H4_PATTERN.match(line) or _H3_PATTERN.match(line):
        return True
    return _H2_CHAPTER_PATTERN.match(line) is not None or line.lower() in _H2_KEYWORDS


def _is_confirmed_continuation(
    current_bbox: Tuple[int, float, float], candidate_bbox: Tuple[int, float, float]
) -> bool:
    """feature_007's geometric continuity gate - two independently
    evidenced paths (see notes_md/
    wrapped_heading_continuation_repair_audit.md):

    1. Same PyMuPDF block - the strong signal. All 9 Nature of Enquiry
       defects, including every link of the 3- and 4-line chains, are
       same-block; no ratio check is needed once this matches.
    2. Different block, but gap_ratio (the candidate's y0 minus the
       current line's y1, divided by the current line's own height)
       within _CROSS_BLOCK_GAP_RATIO_MIN/_MAX - the window an
       exhaustive corpus-wide sweep confirmed separates the one real
       cross-block defect (Aims of Education's title, +0.377) from
       every other bold cross-block candidate in the benchmark corpus
       (7 confirmed non-continuations, nearest at +0.917) by a 0.54
       margin.
    """
    current_block, current_y0, current_y1 = current_bbox
    candidate_block, candidate_y0, _ = candidate_bbox

    if current_block == candidate_block:
        return True

    height = current_y1 - current_y0
    if height <= 0:
        return False
    ratio = (candidate_y0 - current_y1) / height
    return _CROSS_BLOCK_GAP_RATIO_MIN <= ratio <= _CROSS_BLOCK_GAP_RATIO_MAX


def _join_with_local_hyphen_repair(previous_text: str, next_text: str) -> str:
    """Join two wrapped heading lines for feature_007.

    Deliberately a local, heading-only helper rather than a shared
    import of src/structure/paragraph_grouper.py's near-identical
    _join_with_hyphen_repair() - matching this codebase's established
    convention of small, independently-defined per-module helpers over
    cross-module coupling (e.g. footnote_detector.py's
    _NOTES_SECTION_PATTERN, front_matter_extractor.py's
    _ZONE_BOUNDARY_KEYWORDS, both defined independently of a
    near-identical pattern elsewhere).

    Extends that same join logic with one addition the benchmark audit
    found necessary: a trailing soft hyphen (U+00AD) is stripped before
    checking for a literal trailing "-" - confirmed present at a real
    join boundary in the corpus (heading 1.15's first line ends
    "...post-\xad", surviving untouched into Page.cleaned_text since
    Layer 1 sanitization correctly leaves this XML-legal character
    alone). Without this, joining would produce "post-\xad
    structuralist" (stray soft hyphen plus a space inside the word)
    instead of "post-structuralist". Known, accepted limitation shared
    with paragraph_grouper.py's own version: a bare trailing \xad with
    no literal "-" before it is not treated as a hyphen break (no
    current corpus case exercises that distinction, in either module).
    """
    if previous_text.rstrip("\xad").endswith("-"):
        return previous_text.rstrip("\xad") + next_text
    return f"{previous_text} {next_text}"


def _build_layout_index(
    source_pdf_path: str,
) -> Tuple[
    Dict[int, Dict[str, LineLayout]],
    Optional[LineLayout],
    Dict[int, Dict[str, Tuple[int, float, float]]],
]:
    """Read per-line (font size, is_bold) layout signals from the PDF.

    Returns ({}, None, {}) if the PDF cannot be opened or has no text -
    detection then falls back to text-pattern rules only, exactly as
    before this signal existed. This function never raises.

    feature_007 (Wrapped Heading Continuation Repair): also returns a
    third index, page -> text -> (block_index, y0, y1), read from the
    exact same per-block, per-line loop already iterating here - no new
    document pass is introduced, and block_index is the same `bi` value
    already in scope from enumerate()-ing this loop's own blocks.
    """
    pdf_path = Path(source_pdf_path)
    if not pdf_path.is_file():
        logger.warning("Source PDF not found for layout analysis: {}", pdf_path)
        return {}, None, {}

    try:
        pdf_document = fitz.open(pdf_path)
    except Exception as exc:  # PyMuPDF raises various error types on bad input
        logger.warning("Could not open PDF for layout analysis '{}': {}", pdf_path, exc)
        return {}, None, {}

    index: Dict[int, Dict[str, LineLayout]] = {}
    bbox_index: Dict[int, Dict[str, Tuple[int, float, float]]] = {}
    body_char_votes: Counter = Counter()

    try:
        for page_index in range(pdf_document.page_count):
            page_number = page_index + 1
            page_lines: Dict[str, LineLayout] = {}
            page_bboxes: Dict[str, Tuple[int, float, float]] = {}

            page_dict = pdf_document[page_index].get_text("dict")
            for block_index, block in enumerate(page_dict.get("blocks", [])):
                for line_dict in block.get("lines", []):
                    parsed = line_layout(line_dict)
                    if parsed is None:
                        continue
                    text, size, is_bold, char_count = parsed
                    # XML Sanitization Architecture, Layer 1 consistency:
                    # this dict's keys are matched against lines of
                    # page.cleaned_text (src/headings/heading_detector.py's
                    # main loop), which src/ocr/extractor.py now sanitizes
                    # (see src/utils/text_sanitization.py). This is a
                    # separate, independent PyMuPDF read - sanitize the
                    # same way here too, purely so the two representations
                    # of "the same line" still match after either one
                    # contained an XML-illegal character; the canonical
                    # SanitizationEvent for that character is already
                    # recorded once via the cleaned_text path, so it is
                    # deliberately not re-recorded here.
                    clean_text, _ = sanitize_xml_text(text)
                    page_lines[clean_text] = (size, is_bold)
                    body_char_votes[(size, is_bold)] += char_count
                    _, y0, _, y1 = line_dict["bbox"]
                    page_bboxes[clean_text] = (block_index, y0, y1)

            index[page_number] = page_lines
            bbox_index[page_number] = page_bboxes
    finally:
        pdf_document.close()

    if not body_char_votes:
        return index, None, bbox_index

    (body_size, body_is_bold), _ = body_char_votes.most_common(1)[0]
    return index, (body_size, body_is_bold), bbox_index


@dataclass
class HeadingLayoutContext:
    """Raw per-line typography/whitespace signals for one PDF, exposed for
    verifiers that need more than a classified heading level — HeadingVerifier's
    multi-signal EvidenceBundle (FEATURE_019, src/verification/headings.py).

    layout_index[page][text]   -> (font_size, is_bold)
    body_profile               -> the document's own (font_size, is_bold) baseline
    bbox_index[page][text]     -> (block_index, y0, y1)
    """

    layout_index: Dict[int, Dict[str, LineLayout]]
    body_profile: Optional[LineLayout]
    bbox_index: Dict[int, Dict[str, Tuple[int, float, float]]]


def build_heading_layout_context(pdf_path: Path) -> HeadingLayoutContext:
    """Public wrapper around _build_layout_index (the exact same per-line
    scan detect_headings_from_pdf() already runs — no second PDF read) for
    callers that need the raw signals themselves, not just a classified
    heading level."""
    layout_index, body_profile, bbox_index = _build_layout_index(str(pdf_path))
    return HeadingLayoutContext(layout_index=layout_index, body_profile=body_profile, bbox_index=bbox_index)


class _FallbackSignal:
    """Per-line signal for the bug_002 fallback tier only.

    Deliberately separate from LineLayout (size, is_bold) - this is a
    different signal (font name + block isolation) for a different,
    later tier, and keeping it out of the shared LineLayout/line_layout()
    avoids touching the signal src/structure/structure_detector.py also
    depends on for TextBlock.is_bold.
    """

    __slots__ = ("font_name", "size", "is_sole_line")

    def __init__(self, font_name: str, size: float, is_sole_line: bool) -> None:
        self.font_name = font_name
        self.size = size
        self.is_sole_line = is_sole_line


def _majority_font_name(line_dict: dict) -> Optional[str]:
    """The font name covering the most characters on this line.

    Mirrors the char-majority approach src/structure/layout_signals.py
    already uses for is_bold, applied to font name instead - so a line
    with one stray differently-fonted character (e.g. a symbol glyph)
    still gets the font that actually represents the line.
    """
    votes: Counter = Counter()
    for span in line_dict.get("spans", []):
        votes[span.get("font", "")] += len(span.get("text", ""))
    if not votes:
        return None
    return votes.most_common(1)[0][0]


def _build_fallback_tier_index(
    source_pdf_path: str,
) -> Tuple[Dict[int, Dict[str, _FallbackSignal]], Optional[str], Counter]:
    """Read per-line (font name, size, sole-line-in-block) signals for the
    bug_002 fallback tier.

    A separate, independent pass over the PDF from _build_layout_index -
    same "independently re-open the PDF for one more signal" pattern
    already used throughout this codebase (see
    src/footnotes/footnote_detector.py's module docstring for the same
    justification) - so the existing (size, is_bold) signal path and its
    behavior are completely untouched by this addition.

    Returns ({}, None, Counter()) if the PDF cannot be opened or has no
    text - the fallback tier then simply never fires, identical to
    behavior before bug_002 existed. This function never raises.
    """
    pdf_path = Path(source_pdf_path)
    if not pdf_path.is_file():
        return {}, None, Counter()

    try:
        pdf_document = fitz.open(pdf_path)
    except Exception as exc:  # PyMuPDF raises various error types on bad input
        logger.warning(
            "Could not open PDF for fallback-tier layout analysis '{}': {}", pdf_path, exc
        )
        return {}, None, Counter()

    index: Dict[int, Dict[str, _FallbackSignal]] = {}
    body_font_char_votes: Counter = Counter()
    signature_counts: Counter = Counter()

    try:
        for page_index in range(pdf_document.page_count):
            page_number = page_index + 1
            page_lines: Dict[str, _FallbackSignal] = {}

            page_dict = pdf_document[page_index].get_text("dict")
            for block in page_dict.get("blocks", []):
                lines = block.get("lines", [])
                is_sole_line = len(lines) == 1
                for line_dict in lines:
                    parsed = line_layout(line_dict)
                    if parsed is None:
                        continue
                    text, size, _is_bold, char_count = parsed
                    font_name = _majority_font_name(line_dict)
                    if font_name is None:
                        continue
                    # Same XML Sanitization Architecture consistency
                    # rationale as _build_layout_index above: match keys
                    # against page.cleaned_text's already-sanitized lines.
                    clean_text, _ = sanitize_xml_text(text)
                    page_lines[clean_text] = _FallbackSignal(
                        font_name=font_name, size=size, is_sole_line=is_sole_line
                    )
                    body_font_char_votes[font_name] += char_count
                    # Recurrence only counts sole-line contributions: a
                    # masthead block that happens to share a (font, size)
                    # with an unrelated sole-line byline (e.g. Calderhead's
                    # "Chapter 9", a 3-line block, sharing 14pt Helvetica
                    # with the separately-blocked "James Calderhead") must
                    # not inflate recurrence for that byline - confirmed via
                    # a real regression this guard was added to fix, not
                    # speculative.
                    if is_sole_line:
                        signature_counts[(font_name, size)] += 1

            index[page_number] = page_lines
    finally:
        pdf_document.close()

    if not body_font_char_votes:
        return index, None, signature_counts

    body_font_name, _ = body_font_char_votes.most_common(1)[0]
    return index, body_font_name, signature_counts


