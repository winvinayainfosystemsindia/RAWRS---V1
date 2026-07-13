"""Footnote/Endnote detection for RAWRS (Phase K).

Populates Document.footnotes with every footnote/endnote whose
marker-to-body relationship can be confidently, deterministically
detected, reusing src/structure/structure_detector.py's (Phase H)
per-line text/bbox/font_size data wherever possible - this module only
independently re-opens the source PDF for one additional signal Phase H
doesn't persist: each page's height, needed to test whether a candidate
note body sits in the bottom zone of its page (the same "independently
re-open the PDF for one more signal" pattern already used throughout
this codebase, e.g. src/headings/heading_detector.py for layout,
src/images/image_extractor.py for bbox).

Detection signals used (all deterministic, no AI, no OCR changes):

- Superscript marker, signal 1 (Unicode glyph): an inline reference is
  one or more Unicode superscript digits
  (U+00B9/U+00B2/U+00B3/U+2070/U+2074-U+2079) immediately following a
  non-space character within a TextBlock's text - i.e. glued onto a
  word, not a standalone superscript elsewhere.
- Superscript marker, signal 2 (span-level, bug_005/feature_005): a
  plain digit (1-3 characters) sharing its line's ordinary Unicode
  representation but carrying PyMuPDF's own TEXT_FONT_SUPERSCRIPT span
  flag bit, with a font size strictly smaller than the largest span
  size on the same line, and glued onto the immediately preceding
  span's text with no space between them. This is the far more common
  real-world PDF encoding for footnote markers - confirmed directly via
  span dump on a real regression PDF (docs/DECISIONS_LOG.md Part 8) -
  and was previously undetectable because Phase H's TextBlock collapsed
  every span on a line into one (font_size, is_bold) scalar pair before
  this module ever saw it. `TextBlock.spans` (feature_005) makes this
  signal available; see `_find_span_marker_candidates()`. Additive only
  - signal 1 is unchanged, and this signal silently contributes nothing
  on any TextBlock with no span data (e.g. one built before feature_005
  existed, or a non-DIRECT_TEXT page).
- Font-size-drop + page-position (footnotes): a candidate note body is
  a TextBlock whose font_size is meaningfully smaller than the
  document's dominant body font size AND whose bbox sits in the bottom
  quarter of its page - the print convention for footnotes.
- Structure-based (endnotes): a TextBlock whose stripped text is
  exactly "Notes" or "Endnotes" marks the start of an endnotes section;
  every marker-prefixed line from there to the end of the document is a
  candidate endnote body, regardless of font size or position (endnote
  sections vary more in typography than footnotes, which are
  standardized by print convention).

Linking: footnotes are matched marker-to-body by number, scoped to a
single page (footnote numbering conventionally resets per page - the
same number on two different pages must never be linked to each
other's body). Endnotes are matched by number across the whole
document (outside any detected Notes section), since endnote numbering
is conventionally continuous. A marker with no matching body, or a
body with no matching marker, is never promoted to a Footnote - only
confidently-linked pairs are (per the Phase K brief: "when a
relationship can be confidently detected").

Explicitly out of scope (see the Phase K architecture audit): reading
order reconstruction, multi-column detection, table/equation detection,
and any OCR or image pipeline change. This module reads document.blocks
and the source PDF's page geometry only; it never touches
Page.cleaned_text/raw_text, Document.images, or any OCR-stage output.

Continuation-line absorption (footnote preservation audit fix): a real
note body is frequently wrapped across more than one physical PDF
line, but body detection originally treated exactly one TextBlock as a
note's entire body - silently truncating every multi-line note to its
first line, with the remaining lines leaking into ordinary body text
as unlabeled, orphaned paragraphs (confirmed against the Brinkman
regression PDF's expected_md gold standard, where this cut every
endnote off mid-sentence). _collect_body_candidates()/
_is_continuation_line() now absorb every immediately-following line
that reads as a tight same-note line wrap - geometrically calibrated,
not a new marker/linking signal - into the already-detected note's
body, stopping at the next marker line, an unrelated wide gap (a
section boundary), or the end of the scanned region. Marker detection
and marker-to-body linking by number are both unchanged.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import fitz  # PyMuPDF
from loguru import logger

from src.models.contracts import Document, Footnote, NoteType, Span, TextBlock

_SUPERSCRIPT_DIGITS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
_SUPERSCRIPT_TO_DIGIT = str.maketrans(_SUPERSCRIPT_DIGITS, "0123456789")

# An inline marker: superscript digit(s) immediately glued onto a
# preceding non-space character - never a standalone leading character.
_INLINE_MARKER_PATTERN = re.compile(f"(?<=\\S)([{_SUPERSCRIPT_DIGITS}]+)")

# A note body's leading marker: superscript digits, or a plain digit
# followed by a period/parenthesis/colon (the body's own restated
# number, even when the inline reference itself was superscript).
_BODY_MARKER_PATTERN = re.compile(rf"^(?:([{_SUPERSCRIPT_DIGITS}]+)|(\d+)[.\):])\s*(\S.*)$")

_NOTES_SECTION_PATTERN = re.compile(r"^(notes|endnotes)$", re.IGNORECASE)

# bug_005 / feature_005: PyMuPDF span flags bit 0 - confirmed exhaustively
# against the installed PyMuPDF version during the feature_005 design
# review (SUPERSCRIPT=1, ITALIC=2, SERIFED=4, MONOSPACED=8, BOLD=16; no
# dedicated subscript bit exists).
_SUPERSCRIPT_FONT_FLAG = 1

# A span-level marker candidate's own text: 1-3 plain digits, no more -
# bounds this signal to realistic footnote-marker lengths and keeps it
# from firing on a multi-digit number (e.g. a year) that happens to
# carry a stray superscript flag.
_SPAN_MARKER_DIGIT_PATTERN = re.compile(r"^\d{1,3}$")

# A footnote body candidate's font must be at most this fraction of the
# document's dominant body font size (a "font-size-drop").
_FOOTNOTE_FONT_SIZE_RATIO = 0.85

# A footnote body candidate must sit at or below this fraction of the
# way down its page (0.0 = top, 1.0 = bottom).
_FOOTNOTE_BOTTOM_ZONE_FRACTION = 0.75

# A non-marker line immediately following a note's marker line (or one
# of its already-absorbed continuation lines) is itself a continuation
# of that same note's body when the vertical gap to it is at most this
# many multiples of the previous line's own height - i.e. an ordinary
# line wrap, not a new section starting. Calibrated directly against
# the Brinkman regression PDF's real endnotes section: every genuine
# line-wrap there has gap/line-height ~0.23 (gap ~2.0pt, line height
# ~9.0pt), while the real boundary out of that section (into
# "References") measures ~1.82 (gap ~16.3pt, same ~9.0pt line height) -
# this threshold sits with wide margin between the two.
_CONTINUATION_GAP_RATIO = 1.0


@dataclass
class _MarkerCandidate:
    number: int
    marker_text: str
    page_number: int
    anchor_text: str
    order: int
    # feature_005/bug_005: exact character offset of marker_text within
    # anchor_text, when known - see Footnote.anchor_offset's docstring
    # for why this exists (a plain-digit marker can collide with an
    # unrelated number elsewhere in the same line).
    anchor_offset: Optional[int] = None


@dataclass
class _BodyCandidate:
    number: int
    body_text: str
    source_text: str
    page_number: int
    order: int
    # Continuation-line absorption fix: the exact source line of every
    # additional physical PDF line merged into body_text beyond the
    # marker's own first line, in document order. See
    # _collect_body_candidates()/_is_continuation_line().
    continuation_source_texts: List[str] = field(default_factory=list)


def detect_footnotes(document: Document) -> Document:
    """Detect footnotes/endnotes and populate document.footnotes.

    Args:
        document: A Document that has already been through
            src/structure/structure_detector.py (Phase H) - this
            function reads document.blocks for its primary signal and
            does nothing if that list is empty (e.g. Structure
            Detection never ran, or the source PDF has no native text
            layer - same as Phase H's own scanned-page behavior).
            Independently re-opens source_pdf_path only for page
            height; never raises if that fails, since this signal is
            optional and footnote detection degrades gracefully
            without it (see _read_page_heights()).

    Returns:
        The same Document instance with document.footnotes populated
        (possibly empty) and Page.footnote_references/endnote_references
        projected from it. Never raises.
    """
    logger.info("Detecting footnotes/endnotes for '{}'", document.source_pdf_path)
    document.footnotes = _compute_footnotes(document)
    _populate_page_reference_lists(document)

    footnote_count = sum(1 for note in document.footnotes if note.note_type == NoteType.FOOTNOTE)
    endnote_count = sum(1 for note in document.footnotes if note.note_type == NoteType.ENDNOTE)
    logger.info(
        "Footnote/endnote detection complete for '{}': {} footnote(s), {} endnote(s)",
        document.source_pdf_path,
        footnote_count,
        endnote_count,
    )
    return document


def detect_footnote_pdf_candidates(document: Document) -> List[Footnote]:
    """Pure PDF-side candidate source for cross-source verification
    (src/verification/footnotes.py::FootnoteVerifier).

    Identical detection logic to detect_footnotes() (this module's only
    other public entry point) - reuses document.blocks, which
    detect_structure() always populates regardless of extraction source
    (Mathpix or RAWRS-native), plus source_pdf_path for page heights.
    Returned as a plain list instead of being assigned to
    document.footnotes, so a Mathpix-imported document's own canonical
    footnotes are never overwritten. Zero duplicated detection logic -
    see _compute_footnotes().
    """
    return _compute_footnotes(document)


def _compute_footnotes(document: Document) -> List[Footnote]:
    """Shared detection body for detect_footnotes() and
    detect_footnote_pdf_candidates() - see both docstrings above."""
    if not document.blocks:
        logger.info(
            "No structure blocks available for '{}'; skipping footnote detection "
            "(requires Phase H Structure Detection to have run with a native text layer)",
            document.source_pdf_path,
        )
        return []

    sorted_blocks = sorted(document.blocks, key=lambda block: (block.page_number, block.order))
    page_heights = _read_page_heights(document.source_pdf_path)
    body_font_size = _dominant_font_size(sorted_blocks)
    notes_heading = _find_notes_section_start(sorted_blocks)
    notes_page = notes_heading[0] if notes_heading is not None else None

    blocks_by_page: Dict[int, List[TextBlock]] = {}
    for block in sorted_blocks:
        blocks_by_page.setdefault(block.page_number, []).append(block)

    footnotes: List[Footnote] = []
    claimed_bodies: Set[Tuple[int, int]] = set()

    # Footnotes: every page strictly before the Notes section (or every
    # page, if there is no Notes section at all) - numbering resets per page.
    for page_number, page_blocks in blocks_by_page.items():
        if notes_page is not None and page_number >= notes_page:
            continue
        markers = _first_occurrence_per_number(_find_marker_candidates(page_blocks))
        if not markers:
            continue
        bodies = _find_footnote_body_candidates(
            page_blocks, body_font_size, page_heights.get(page_number)
        )
        _link_and_collect(NoteType.FOOTNOTE, markers, bodies, footnotes, claimed_bodies)

    # Endnotes: markers from anywhere before the Notes section; bodies
    # from inside it (the heading's own page, after the heading block,
    # through the end of the document) - numbering is document-wide.
    if notes_heading is not None:
        pre_section_blocks = [block for block in sorted_blocks if block.page_number < notes_page]
        markers = _first_occurrence_per_number(_find_marker_candidates(pre_section_blocks))
        section_blocks = [
            block for block in sorted_blocks if (block.page_number, block.order) > notes_heading
        ]
        bodies = _find_endnote_body_candidates(section_blocks)
        _link_and_collect(NoteType.ENDNOTE, markers, bodies, footnotes, claimed_bodies)

    for idx, note in enumerate(footnotes):
        note.footnote_id = f"fn-{idx}"
    return footnotes


def _link_and_collect(
    note_type: NoteType,
    markers: Dict[int, _MarkerCandidate],
    bodies: Dict[int, _BodyCandidate],
    footnotes: List[Footnote],
    claimed_bodies: Set[Tuple[int, int]],
) -> None:
    """Link markers to bodies by number and append confirmed pairs to
    footnotes - a marker with no matching body, or a body already
    claimed by an earlier marker, is silently skipped (not confidently
    detected)."""
    for number, marker in markers.items():
        body = bodies.get(number)
        if body is None:
            continue
        body_key = (body.page_number, body.order)
        if body_key in claimed_bodies:
            continue
        claimed_bodies.add(body_key)
        footnotes.append(
            Footnote(
                note_type=note_type,
                number=number,
                marker=marker.marker_text,
                anchor_page_number=marker.page_number,
                anchor_text=marker.anchor_text,
                anchor_offset=marker.anchor_offset,
                body=body.body_text,
                body_page_number=body.page_number,
                body_source_text=body.source_text,
                body_continuation_source_texts=body.continuation_source_texts,
            )
        )


def _find_marker_candidates(blocks: List[TextBlock]) -> List[_MarkerCandidate]:
    candidates: List[_MarkerCandidate] = []
    for block in blocks:
        for match in _INLINE_MARKER_PATTERN.finditer(block.text):
            superscript = match.group(1)
            candidates.append(
                _MarkerCandidate(
                    number=int(superscript.translate(_SUPERSCRIPT_TO_DIGIT)),
                    marker_text=superscript,
                    page_number=block.page_number,
                    anchor_text=block.text,
                    order=block.order,
                    anchor_offset=match.start(1),
                )
            )
        candidates.extend(_find_span_marker_candidates(block))
    return candidates


def _find_span_marker_candidates(block: TextBlock) -> List[_MarkerCandidate]:
    """bug_005 / feature_005: a second, additive marker-detection signal
    using PyMuPDF's own per-span superscript flag and size, for markers
    encoded as a plain digit rather than a literal Unicode superscript
    glyph (see module docstring, "Superscript marker, signal 2").

    Requires ALL of:
      - the span's text is 1-3 plain digits (``_SPAN_MARKER_DIGIT_PATTERN``)
      - the span carries PyMuPDF's TEXT_FONT_SUPERSCRIPT flag bit
      - its font size is strictly smaller than the largest span size on
        the same line (confirms a visible size-drop, not just a flag
        with no visual cue)
      - it is glued onto the immediately preceding span's text with no
        space between them - the same "glued onto a word, not a
        standalone digit elsewhere" requirement signal 1 enforces via
        its own flat-text lookbehind, applied here at the span level
        since this signal has no flat-text lookbehind to use.

    Returns [] for any TextBlock with fewer than 2 spans - a marker
    glued onto nothing has no preceding span to glue to, and this is
    also what happens for free on a TextBlock with no span data at all
    (e.g. one built before feature_005 existed, or a non-DIRECT_TEXT
    page) - this signal contributes nothing rather than erroring.
    """
    spans = block.spans
    if len(spans) < 2:
        return []

    max_size = max(span.font_size for span in spans)
    candidates: List[_MarkerCandidate] = []
    for index in range(1, len(spans)):
        span = spans[index]
        text = span.text.strip()
        if not _SPAN_MARKER_DIGIT_PATTERN.match(text):
            continue
        if not (span.font_flags & _SUPERSCRIPT_FONT_FLAG):
            continue
        if span.font_size >= max_size:
            continue
        previous_text = spans[index - 1].text
        if not previous_text or previous_text[-1].isspace():
            continue
        offset = _span_marker_offset(spans, index, block.text, text)
        if offset is None:
            continue  # fail closed: don't risk an incorrectly-positioned substitution
        candidates.append(
            _MarkerCandidate(
                number=int(text),
                marker_text=text,
                page_number=block.page_number,
                anchor_text=block.text,
                order=block.order,
                anchor_offset=offset,
            )
        )
    return candidates


def _span_marker_offset(
    spans: List[Span], index: int, line_text: str, marker_text: str
) -> Optional[int]:
    """Character offset of ``spans[index]``'s marker text within
    ``line_text`` (``TextBlock.text``).

    ``TextBlock.text`` is built by concatenating every span's text on
    the line, then stripping the whole result
    (src/structure/layout_signals.py::line_layout()) - so the offset is
    the length of every preceding span's text, minus however much
    leading whitespace that final strip() removed. Returns None (fail
    closed) if the computed offset doesn't actually land on
    marker_text in line_text, rather than risk a markdown substitution
    at the wrong position later - the same "only confidently-detected"
    philosophy already applied throughout this module.
    """
    unstripped = "".join(span.text for span in spans)
    leading_trim = len(unstripped) - len(unstripped.lstrip())
    prefix_len = len("".join(span.text for span in spans[:index]))
    offset = prefix_len - leading_trim
    if 0 <= offset <= len(line_text) - len(marker_text):
        if line_text[offset : offset + len(marker_text)] == marker_text:
            return offset
    return None


def _first_occurrence_per_number(
    candidates: List[_MarkerCandidate],
) -> Dict[int, _MarkerCandidate]:
    """Keep only the first (page, order) occurrence of each marker
    number - a marker referenced more than once is linked once."""
    result: Dict[int, _MarkerCandidate] = {}
    for candidate in sorted(candidates, key=lambda c: (c.page_number, c.order)):
        result.setdefault(candidate.number, candidate)
    return result


def _find_footnote_body_candidates(
    page_blocks: List[TextBlock],
    body_font_size: Optional[float],
    page_height: Optional[float],
) -> Dict[int, _BodyCandidate]:
    if body_font_size is None or not page_height or page_height <= 0:
        return {}

    zone_blocks = [
        block
        for block in page_blocks
        if block.font_size is not None
        and block.font_size < body_font_size * _FOOTNOTE_FONT_SIZE_RATIO
        and block.bbox.y1 / page_height >= _FOOTNOTE_BOTTOM_ZONE_FRACTION
    ]
    return _collect_body_candidates(zone_blocks)


def _find_endnote_body_candidates(section_blocks: List[TextBlock]) -> Dict[int, _BodyCandidate]:
    return _collect_body_candidates(section_blocks)


def _collect_body_candidates(ordered_blocks: List[TextBlock]) -> Dict[int, _BodyCandidate]:
    """Scan blocks (already filtered/scoped to a note-body region, in
    document order) and parse them into note-body candidates, absorbing
    continuation lines (continuation-line absorption fix - see
    _is_continuation_line()).

    A block that itself parses as a new marker-prefixed body
    (_parse_body_candidate) always starts a fresh candidate - unchanged
    "first occurrence per number wins" linking semantics, preserved
    exactly via the same ``setdefault``-equivalent check used before
    this fix. Every other block is absorbed into whichever candidate is
    currently open (if any) only when it reads as a tight same-note
    line wrap; otherwise the open candidate is closed (set to None) -
    this is what makes absorption correctly stop at the next marker, an
    unrelated wide gap (a section boundary, e.g. a "References"
    heading), or simply running out of blocks to scan.
    """
    candidates: Dict[int, _BodyCandidate] = {}
    current: Optional[_BodyCandidate] = None
    previous_block: Optional[TextBlock] = None

    for block in ordered_blocks:
        candidate = _parse_body_candidate(block)
        if candidate is not None:
            if candidate.number not in candidates:
                candidates[candidate.number] = candidate
                current = candidate
            else:
                current = None  # duplicate marker number - not confidently a continuation target
        elif current is not None and _is_continuation_line(previous_block, block):
            current.body_text = f"{current.body_text} {block.text.strip()}".strip()
            current.continuation_source_texts.append(block.text)
        else:
            current = None
        previous_block = block

    return candidates


def _is_continuation_line(previous_block: Optional[TextBlock], block: TextBlock) -> bool:
    """Whether ``block`` is a tight line-wrap continuation of whatever
    immediately precedes it in the same scanning order (see
    _CONTINUATION_GAP_RATIO for the evidence behind the threshold).
    Never true across an overlapping/negative gap (e.g. a different
    visual column) or when the previous line's own height is
    degenerate/unknown - both fail closed to "not a continuation,"
    matching this module's existing "only confidently detected" policy.
    """
    if previous_block is None:
        return False
    line_height = previous_block.bbox.y1 - previous_block.bbox.y0
    if line_height <= 0:
        return False
    gap = block.bbox.y0 - previous_block.bbox.y1
    if gap < 0:
        return False
    return gap <= line_height * _CONTINUATION_GAP_RATIO


def _parse_body_candidate(block: TextBlock) -> Optional[_BodyCandidate]:
    match = _BODY_MARKER_PATTERN.match(block.text)
    if match is None:
        return None
    superscript, plain, rest = match.group(1), match.group(2), match.group(3)
    number = int((superscript or plain).translate(_SUPERSCRIPT_TO_DIGIT))
    return _BodyCandidate(
        number=number,
        body_text=rest.strip(),
        source_text=block.text,
        page_number=block.page_number,
        order=block.order,
    )


def _find_notes_section_start(blocks: List[TextBlock]) -> Optional[Tuple[int, int]]:
    """The (page_number, order) of the first block that is exactly
    "Notes" or "Endnotes" (whole line, case-insensitive) - the start of
    a detected endnotes section, or None if there is no such heading.
    """
    for block in blocks:
        if _NOTES_SECTION_PATTERN.match(block.text.strip()):
            return (block.page_number, block.order)
    return None


def _dominant_font_size(blocks: List[TextBlock]) -> Optional[float]:
    """The document's most common font size, weighted by character
    count - mirrors src/headings/heading_detector.py's body-profile
    vote, but reads it from already-persisted Phase H blocks instead of
    re-opening the PDF for a second pass."""
    votes: Counter = Counter()
    for block in blocks:
        if block.font_size is not None:
            votes[block.font_size] += len(block.text)
    if not votes:
        return None
    return votes.most_common(1)[0][0]


def _read_page_heights(source_pdf_path: str) -> Dict[int, float]:
    """Each page's height in PDF points - the one signal this module
    needs that Phase H's TextBlock doesn't carry. Never raises; returns
    {} if the PDF can't be read, in which case footnote body detection
    (which needs this) finds nothing, while endnote detection (which
    doesn't) is unaffected.
    """
    pdf_path = Path(source_pdf_path)
    if not pdf_path.is_file():
        logger.warning("Source PDF not found for footnote page-height signal: {}", pdf_path)
        return {}

    try:
        pdf_document = fitz.open(pdf_path)
    except Exception as exc:  # PyMuPDF raises various error types on bad input
        logger.warning("Could not open PDF for footnote page-height signal '{}': {}", pdf_path, exc)
        return {}

    try:
        return {
            page_index + 1: pdf_document[page_index].rect.height
            for page_index in range(pdf_document.page_count)
        }
    finally:
        pdf_document.close()


def _populate_page_reference_lists(document: Document) -> None:
    """Project document.footnotes onto Page.footnote_references/
    endnote_references - a per-page convenience index of marker
    strings, not a second source of truth (see src/models/footnote.py).
    """
    footnote_markers: Dict[int, List[str]] = {}
    endnote_markers: Dict[int, List[str]] = {}
    for note in document.footnotes:
        target = footnote_markers if note.note_type == NoteType.FOOTNOTE else endnote_markers
        target.setdefault(note.anchor_page_number, []).append(note.marker)

    for page in document.pages:
        page.footnote_references = footnote_markers.get(page.page_number, [])
        page.endnote_references = endnote_markers.get(page.page_number, [])
