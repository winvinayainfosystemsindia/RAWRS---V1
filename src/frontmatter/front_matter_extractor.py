"""Front-matter extraction for RAWRS (title/author(s)/affiliation(s)).

Closes the gap found by the Scholarly Article Semantics Audit: a
document's title, author byline, and institutional affiliation were
previously detected as nothing at all - not a heading, not metadata -
and were silently flattened into ordinary, undifferentiated body text
(confirmed against the Brinkman benchmark: "Learner-centred education
reforms in India... Suzana Brinkmann Institute of Education, London,
UK" rendered as one run-on paragraph, indistinguishable from any other
body text).

SUPERSEDED (2026-07-20, ADR-003 · FE-0-005/006): the "wholly separate,
additive signal" constraint stated in the next paragraph was feature_006's
original scope rule. It no longer governs. ADR-003 (Artifact
Classification, verdict ACCEPT, docs/ADR_2026-07-19.md) formally adopts
semantic classification as an input to heading detection - "New pipeline
stage between detect_structure and detect_headings. Additive; detector
takes optional classification and falls back to current behaviour."
src/frontmatter/front_matter_roles.py implements that contract for
front-matter roles: heading_detector.py consults it and declines AUTHOR/
AFFILIATION lines, falling back to typography-only classification when no
front matter is present. This module itself is unchanged - it still only
produces FrontMatter; it is the *consumer* relationship that inverted.

This module remains deliberately isolated from
src/headings/heading_detector.py in the direction that still matters:
it does not call into it, import its private constants, or change any
of its classification tiers. It reads only src/structure/structure_detector.py's
already-persisted Document.blocks (Phase H) - no new PDF re-open, no new
PyMuPDF dependency beyond what's already been read - mirroring the
"operate on already-persisted TextBlock data" pattern
src/structure/paragraph_grouper.py already established, in preference
to src/footnotes/footnote_detector.py's "independently re-open the PDF
for one more signal" pattern, since every signal needed here
(per-line text, font_size, order, page_number) is already on TextBlock.

Detection strategy (page 1 only, deterministic, rule-based, no AI):

1. Find the "masthead-zone boundary": the first of page 1's first
   _MAX_MASTHEAD_LINES lines whose stripped, lowercased text exactly
   matches one of a small, independently-defined keyword set
   (_ZONE_BOUNDARY_KEYWORDS - deliberately not imported from
   heading_detector.py's own keyword list, matching this codebase's
   established convention of small, independent per-module constants
   over cross-module coupling - see e.g. footnote_detector.py's
   _NOTES_SECTION_PATTERN, defined independently of
   markdown_builder.py's near-identical pattern). No boundary found in
   that window -> no confidently-bounded front matter -> every field
   stays empty (fail closed; this is the expected, correct outcome for
   a PDF with no title page at all, e.g. 3 of the 4 benchmark PDFs).
2. Within that bounded zone, optionally skip one short "kicker" line
   (e.g. Brinkman's "Article") - a line shorter than _KICKER_MAX_LEN
   whose font size is below the title threshold.
3. Title = the maximal contiguous run of lines at or above
   _TITLE_MIN_SIZE_RATIO times the document's dominant body font size.
   Empty -> no title -> the whole FrontMatter stays empty; author/
   affiliation are never extracted without a title to anchor them.
4. Author = the contiguous run immediately following the title run,
   strictly between body size and the title threshold (a distinct
   "byline tier"), capped at _MAX_AUTHOR_LINES lines.
5. Affiliation = every remaining line in the already-bounded zone after
   the author run - safe to take unconditionally because the zone
   itself is already tightly bounded by step 1, not because this step
   has its own stopping logic.

Calibrated directly against the Brinkman benchmark's real geometry
(confirmed via Document.blocks, not guessed): kicker "Article" at
10.0pt, title (3 lines) at 17.9pt, author "Suzana Brinkmann" at 12.0pt,
affiliation "Institute of Education, London, UK" at 9.0pt, body/
"Abstract" at 10.0pt - body_font_size=10.0, title_threshold (x1.3)=13.0,
cleanly separating every tier with wide margin.

feature_008 (generalization, see
samples/regressions/feature_008_front_matter_generalization/notes_md/
front_matter_generalization_audit.md for the full audit): the above
journal-article shape (keyword-bounded zone, single global threshold
separating title from author) does not generalize to book/
chapter-excerpt front matter, which has no Abstract section at all and
can have an author line that is itself well above the 1.3x threshold
(e.g. Bruner: title 29.0pt, author 24.0pt). Three additive changes,
each independently validated against the real benchmark PDFs before
being adopted (see audit SS3-4):

1. Zone boundary: the keyword check (step 1 above) is tried first and
   unchanged - it still wins outright for any document that has a real
   Abstract section (Brinkman). Only if no keyword is found does
   _find_zone_boundary() fall back to a font-size signal: the first
   line whose size returns to (within _BODY_SIZE_BOUNDARY_TOLERANCE of)
   the document's body size, or the end of the masthead window if the
   page never drops back to body size at all (e.g. Bruner's half-title
   page, which simply ends after the publisher block).
2. Kicker-skip (step 2 above) now compares a short leading line against
   the *next* line's size, not the global threshold - this is what
   lets "Chapter 9"/"Chapter 7" (14.0pt, which exceeds Calderhead's and
   Fullan&Hargreaves' 13.0pt threshold) still be recognized as a kicker
   instead of corrupting the title run.
3. Title and author runs (steps 3-4 above) now stop at the first
   font-size change, not at the global threshold - this is what
   separates Bruner's title(29.0)/author(24.0) into two tiers instead
   of merging them (both exceed the 16.9pt threshold), and what
   separates Calderhead's kicker(14.0)/title(18.0)/author(14.0) despite
   the kicker and author sharing a coincidental size.

This generalization, on its own, introduced two real benchmark false-
positive "affiliations" (audit SS7): Aims' 55.5pt epigraph and Bruner's
"HARVARD UNIVERSITY PRESS" publisher imprint. Two mandatory guards
(_filter_affiliation_candidates(), see its docstring) were added
specifically to eliminate both, each calibrated against the real
benchmark geometry that proved the false positive, not guessed.

A third, optional guard (audit SS8.2: reject an affiliation candidate
whose exact text recurs elsewhere in the document - true of Bruner's
publisher imprint, false of Brinkman's genuine affiliation) was
evaluated but not implemented: unlike the two guards above, it needs
document-wide blocks (every page), not just the already-in-hand page-1
zone, which would mean threading a new parameter through
extract_front_matter()/_build_front_matter()/
_filter_affiliation_candidates() for a check the two mandatory guards
already make unnecessary - both real benchmark false positives are
eliminated without it.
"""

import re
from collections import Counter
from typing import List, Optional

from src.models.contracts import Document, TextBlock
from src.models.front_matter import FrontMatter

# A line at or above this many times the document's dominant body font
# size is part of the title run. 1.3x sits with wide margin between
# Brinkman's kicker/body tier (ratio 1.0) and its real title tier
# (ratio 1.79) - see module docstring's calibration note.
_TITLE_MIN_SIZE_RATIO = 1.3

# A short leading line below the title threshold (e.g. "Article") is a
# section-type kicker, not the title itself, and is skipped - bounded
# well above any real title's line length, well below a full sentence.
_KICKER_MAX_LEN = 30

# The masthead-zone boundary (see module docstring step 1) must be
# found within this many of page 1's lines, or front-matter extraction
# declines entirely rather than scan deep into unrelated body content.
_MAX_MASTHEAD_LINES = 20

# A defensive cap on the author run's line count - the zone is already
# tightly bounded by the boundary keyword, so this is a sanity bound,
# not a load-bearing stopping condition.
_MAX_AUTHOR_LINES = 5

# Independently defined from (not imported from) heading_detector.py's
# own _H2_KEYWORDS, matching this codebase's established convention of
# small, duplicated per-module constants over cross-module coupling.
_ZONE_BOUNDARY_KEYWORDS = {"abstract", "keywords", "introduction", "summary"}

# feature_008: two masthead-tier lines are treated as the same tier
# (the same title run, or the same author run) when their font sizes
# differ by less than this. Calibrated against this corpus's real
# tier-to-tier size gaps, every one of which is >=2pt (e.g. Bruner's
# title/author/publisher tiers: 29.0/24.0/14.0) - 0.3pt gives wide
# margin against float noise without risking merging two real,
# distinct tiers.
_TIER_SIZE_TOLERANCE = 0.3

# feature_008: when no _ZONE_BOUNDARY_KEYWORDS match is found, the
# masthead zone instead ends at the first line whose font size returns
# to within this many points of the document's body font size - the
# point real body prose begins. 0.5pt absorbs float rounding without
# risking conflating a real masthead-tier line with body text (every
# benchmark masthead tier sits >=1pt above body size).
_BODY_SIZE_BOUNDARY_TOLERANCE = 0.5

# feature_008 affiliation guard #2 (see _filter_affiliation_candidates):
# a candidate affiliation line is rejected if it sits more than this
# many multiples of the preceding line's own height below that line.
# Calibrated directly against the only two real examples in the
# benchmark corpus (front_matter_generalization_audit.md SS8.1):
# Brinkman's genuine affiliation sits gap_ratio=0.169 below its author
# line (the very next line on the page); Bruner's "HARVARD UNIVERSITY
# PRESS" publisher imprint sits gap_ratio=8.404 below its author line
# (a separate block near the bottom of the page). 2.0 sits with wide
# margin on both sides - over 10x Brinkman's real value, under a
# quarter of Bruner's.
_MAX_AFFILIATION_GAP_RATIO = 2.0

_AUTHOR_SPLIT_PATTERN = re.compile(r",| and | & ", re.IGNORECASE)


def extract_front_matter(document: Document) -> Document:
    """Populate document.front_matter from page 1's already-persisted
    Document.blocks (Phase H - Structure Detection must already have
    run). Never raises; an empty Document.blocks or a page 1 with no
    confidently-bounded masthead zone simply yields an all-empty
    FrontMatter, not an error.
    """
    page_one_blocks = sorted(
        (block for block in document.blocks if block.page_number == 1),
        key=lambda block: block.order,
    )
    body_font_size = _dominant_font_size(document.blocks)
    document.front_matter = _build_front_matter(page_one_blocks, body_font_size)
    return document


def _build_front_matter(
    zone_blocks: List[TextBlock], body_font_size: Optional[float]
) -> FrontMatter:
    if not zone_blocks or body_font_size is None or body_font_size <= 0:
        return FrontMatter()

    boundary = _find_zone_boundary(zone_blocks, body_font_size)
    if boundary is None:
        return FrontMatter()

    zone = zone_blocks[:boundary]
    title_threshold = body_font_size * _TITLE_MIN_SIZE_RATIO

    index = 0
    # feature_008: a short leading line is a kicker (e.g. "Article",
    # "Chapter 9") if it's smaller than the line right after it - not
    # (as before bug_007/feature_006) only when it's below the global
    # title threshold, which missed kickers that are themselves >1.3x
    # body size (Calderhead/Fullan&Hargreaves' "Chapter N" labels).
    if (
        index + 1 < len(zone)
        and len(zone[index].text) <= _KICKER_MAX_LEN
        and (zone[index].font_size or 0) < (zone[index + 1].font_size or 0)
    ):
        index += 1

    if index >= len(zone) or (zone[index].font_size or 0) < title_threshold:
        return FrontMatter()  # no confident title tier - nothing else is extracted either

    # feature_008: title run is the contiguous run at this line's own
    # size, not "every line >= threshold" - the latter would merge a
    # still-above-threshold author line into the title (Bruner: title
    # 29.0pt, author 24.0pt, threshold only 16.9pt).
    title_size = zone[index].font_size
    title_blocks: List[TextBlock] = []
    while index < len(zone) and abs((zone[index].font_size or 0) - title_size) < _TIER_SIZE_TOLERANCE:
        title_blocks.append(zone[index])
        index += 1

    # feature_008 title guard: reject a single-token/glyph title. Made
    # necessary by the boundary fallback above - on sockett_profession.pdf,
    # a lone OCR-garbled 29.0pt glyph ("e") passes the title-size gate
    # the same way a real title would, with no keyword boundary to have
    # screened it out first. Every real title in this corpus is multiple
    # words; this costs nothing for any of them.
    title_text = " ".join(block.text.strip() for block in title_blocks)
    if " " not in title_text.strip():
        return FrontMatter()

    # feature_008: author run is likewise the contiguous run at its own
    # single size (bounded by the *detected* title size, not the global
    # threshold) - separates Bruner's author(24.0) from the smaller
    # publisher-imprint line(14.0) that would otherwise also satisfy
    # "body < size < threshold" and be merged into the author list.
    author_blocks: List[TextBlock] = []
    author_size: Optional[float] = None
    while (
        index < len(zone)
        and len(author_blocks) < _MAX_AUTHOR_LINES
        and body_font_size < (zone[index].font_size or 0) < title_size
        and (author_size is None or abs((zone[index].font_size or 0) - author_size) < _TIER_SIZE_TOLERANCE)
    ):
        if author_size is None:
            author_size = zone[index].font_size
        author_blocks.append(zone[index])
        index += 1

    anchor_block = author_blocks[-1] if author_blocks else title_blocks[-1]
    affiliation_blocks = _filter_affiliation_candidates(zone[index:], title_size, anchor_block)

    author_text = " ".join(block.text.strip() for block in author_blocks)

    return FrontMatter(
        title=title_text,
        title_source_texts=[block.text for block in title_blocks],
        authors=_split_authors(author_text),
        author_source_texts=[block.text for block in author_blocks],
        affiliations=[block.text.strip() for block in affiliation_blocks],
        affiliation_source_texts=[block.text for block in affiliation_blocks],
    )


def _find_zone_boundary(zone_blocks: List[TextBlock], body_font_size: float) -> Optional[int]:
    """The first of page 1's first _MAX_MASTHEAD_LINES lines marking
    where the masthead zone ends and ordinary body content begins.

    Two signals, tried in order (feature_008): (1) a literal
    abstract/keywords/introduction/summary line - the original,
    journal-article-shaped signal, tried first so a document with a
    real Abstract section (Brinkman) is completely unaffected by the
    fallback below. (2) If no such line exists - book/chapter-excerpt
    fronts (Aims, Bruner, Calderhead, Fullan&Hargreaves) have no
    Abstract section at all - the first line at-or-below body font
    size, scanned only from index 1 onward (a masthead-tier line must
    come first); or, if neither signal ever fires in the window, the
    end of the window itself (the whole page is masthead - e.g.
    Bruner's half-title page, which simply ends after the publisher
    block with no body text on it at all).
    """
    limit = min(len(zone_blocks), _MAX_MASTHEAD_LINES)
    for index in range(limit):
        if zone_blocks[index].text.strip().lower() in _ZONE_BOUNDARY_KEYWORDS:
            return index
    for index in range(1, limit):
        if (zone_blocks[index].font_size or 0) <= body_font_size + _BODY_SIZE_BOUNDARY_TOLERANCE:
            return index
    return limit if limit > 0 else None


def _filter_affiliation_candidates(
    candidates: List[TextBlock], title_size: float, anchor_block: TextBlock
) -> List[TextBlock]:
    """feature_008's two mandatory affiliation guards - each proven
    necessary by a real benchmark false positive (see
    samples/regressions/feature_008_front_matter_generalization/
    notes_md/front_matter_generalization_audit.md SS7-8).

    Guard #1 (per-line): a candidate at or above the title's own font
    size is never a genuine affiliation anywhere in this corpus - it's
    a differently-purposed masthead element (Aims' 55.5pt epigraph
    against its 16.0pt title). Filtered line-by-line, not all-or-
    nothing, so a multi-line affiliation with one bad line doesn't lose
    every line.

    Guard #2 (whole-remainder): if the first surviving candidate sits
    more than _MAX_AFFILIATION_GAP_RATIO line-heights below the
    immediately preceding masthead line (the author's last line, or
    the title's last line if no author was found), the entire
    remainder is a separate, unrelated page element, not a
    continuation of the masthead (Bruner's publisher imprint,
    gap_ratio=8.404, vs. Brinkman's genuine affiliation, gap_ratio=
    0.169 - real corpus values, see module docstring/_MAX_AFFILIATION_
    GAP_RATIO). Applied once to the whole remainder, not per-line: a
    large gap means "this block doesn't belong here at all," not "this
    one line is individually suspect."
    """
    survivors = [block for block in candidates if (block.font_size or 0) < title_size]
    if not survivors:
        return []

    anchor_height = anchor_block.bbox.y1 - anchor_block.bbox.y0
    if anchor_height <= 0:
        return survivors  # no usable height to measure against - guard #2 can't evaluate

    gap_ratio = (survivors[0].bbox.y0 - anchor_block.bbox.y1) / anchor_height
    if gap_ratio > _MAX_AFFILIATION_GAP_RATIO:
        return []

    return survivors


def _split_authors(author_text: str) -> List[str]:
    if not author_text:
        return []
    return [name.strip() for name in _AUTHOR_SPLIT_PATTERN.split(author_text) if name.strip()]


def _dominant_font_size(blocks: List[TextBlock]) -> Optional[float]:
    """The document's most common font size, weighted by character
    count - independently defined, mirroring
    src/footnotes/footnote_detector.py's _dominant_font_size() exactly
    (same small-duplicated-constant convention as
    _ZONE_BOUNDARY_KEYWORDS above), not imported from it."""
    votes: Counter = Counter()
    for block in blocks:
        if block.font_size is not None:
            votes[block.font_size] += len(block.text)
    if not votes:
        return None
    return votes.most_common(1)[0][0]
