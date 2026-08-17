"""Which physical page a Mathpix block came from — stated, never guessed.

P-1 commit 2. An MMD gives block order and nothing else; the ingestor turns
that order into a page by proportional position (``page_estimation.py``),
which is exact on 11% of the benchmark corpus and more than one page out on
75% of the blocks that can be checked. The PDF that arrived with the same
upload states the answer: a page whose text contains a block's text is the
page that block is on. ``src/parser/pdf_parser.py``'s ``page_text_layer``
hands that text over; this module turns it into evidence.

**It decides nothing about a document.** It produces, per ``source_line``, the
narrowest page interval the evidence proves — a single page where an anchor
lands, an interval where only the neighbours are known, and an open end where
nothing is known. Choosing a page inside that interval is the consumer's job,
because the fallback it must clamp is the estimate this module deliberately
never calls.

**What may become an anchor.** Only a block whose normalised text is long
enough to be distinctive, appears on **exactly one** page, and sits in a
non-decreasing page sequence with every anchor already accepted. The three
conditions carry their weight together: length alone admits a running header,
uniqueness alone admits a phrase that recurs once per chapter, and either
alone admits a hit that would send the document backwards. Containment is the
*mechanism*; the identity decision is uniqueness plus monotonicity, which is
why a substring hit on its own is never enough.

Nothing here repairs text. A word Mathpix de-hyphenated and the PDF broke
across lines simply does not match, and that block is left unanchored — one
fewer anchor is a smaller error than a fabricated one.

**Whole-document fail-closed.** Anchors that would move backwards are rejected
individually, but a document producing more than 5% of them is not a document
whose PDF and MMD correspond: the alignment is rejected entirely rather than
half-applied. A document with no anchors at all — a pure scan, whose pages
carry no text layer — is reported as having no evidence, which is exactly the
state the caller must leave on the estimate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

# The project's approved normalisation (NFKC, punctuation stripped, whitespace
# collapsed, casefolded), reused rather than restated: two normalisations that
# drift produce anchors that exist in one module's opinion only.
from src.verification.text_resolution import _normalize as normalize_text

# A shorter probe is not distinctive enough to identify a page: 30 normalised
# characters is roughly five words, below which section titles, page furniture
# and citation fragments start colliding across pages.
MIN_ANCHOR_CHARS = 30
# Only the head of a block is compared. A paragraph's opening survives PDF
# line-breaking intact far more often than its whole body, which accumulates
# every hyphenation and column-break difference between the two extractions.
ANCHOR_WINDOW_CHARS = 60
# Above this share of backwards anchors the two sources are not the same
# document (a different edition, a 2-up scan, a re-ordered export).
MAX_CONFLICT_RATIO = 0.05


class AlignmentStatus(str, Enum):
    """The three states a caller must tell apart."""

    ALIGNED = "aligned"          # usable evidence; brackets may be consulted
    NO_EVIDENCE = "no_evidence"  # nothing anchored — a scan, or text that never matched
    REJECTED = "rejected"        # anchors contradicted each other; the document is unusable


@dataclass(frozen=True)
class PageBracket:
    """The narrowest page interval the evidence proves for one block.

    ``lower``/``upper`` are inclusive physical page numbers, or None where
    that side is unproven — before the first anchor there is no lower bound
    and after the last there is no upper one. ``stated`` is set only when the
    two bounds are the same page, which happens when the block is itself an
    anchor.
    """

    lower: Optional[int] = None
    upper: Optional[int] = None

    @property
    def stated(self) -> Optional[int]:
        if self.lower is not None and self.lower == self.upper:
            return self.lower
        return None

    @property
    def is_open(self) -> bool:
        return self.lower is None and self.upper is None

    def clamp(self, estimate: int) -> int:
        """The consumer's rule (C3): evidence beats the estimate, and where
        there is only an interval the estimate is *constrained*, never
        replaced.

        A stated page wins outright. Otherwise the caller's own estimate is
        kept unless it falls outside a proven bound, in which case it moves to
        that bound and no further — no interpolation, no midpoint, no nearest
        anchor. An open side constrains nothing.
        """
        stated = self.stated
        if stated is not None:
            return stated
        page = estimate
        if self.lower is not None and page < self.lower:
            page = self.lower
        if self.upper is not None and page > self.upper:
            page = self.upper
        return page


UNPROVEN = PageBracket()


@dataclass(frozen=True)
class PageAlignment:
    """Every block's page evidence, plus why each candidate was refused.

    The counters are not decoration: they are how a corpus probe shows that a
    document lost its anchors to duplicate text rather than to a bug, and how
    the conflict ratio that rejects a document stays auditable afterwards.
    """

    status: AlignmentStatus
    page_count: int
    brackets: Dict[int, PageBracket] = field(default_factory=dict)
    candidates: int = 0
    accepted: int = 0
    rejected_ambiguous: int = 0
    rejected_short: int = 0
    rejected_backwards: int = 0
    unmatched: int = 0
    anchor_pages: Tuple[int, ...] = ()

    @property
    def usable(self) -> bool:
        return self.status is AlignmentStatus.ALIGNED

    def bracket_for(self, source_line: Optional[int]) -> PageBracket:
        """The evidence for one block. An unknown line, or an unusable
        alignment, yields the open bracket — which constrains nothing, so a
        caller clamping its own estimate into it changes nothing."""
        if source_line is None:
            return UNPROVEN
        return self.brackets.get(source_line, UNPROVEN)

    def stated_page(self, source_line: Optional[int]) -> Optional[int]:
        """The page the evidence proves, or None when it proves an interval."""
        return self.bracket_for(source_line).stated

    def resolve_page(self, source_line: Optional[int], estimate: int) -> int:
        """This block's page: proven where proven, otherwise the caller's
        estimate held inside whatever the evidence does prove.

        The estimate is passed in rather than computed, so this module still
        never calls ``estimate_page`` and a caller with no estimator of its
        own is not forced to acquire one.
        """
        return self.bracket_for(source_line).clamp(estimate)


def align_blocks_to_pages(
    blocks: Sequence[Any], page_texts: Sequence[str]
) -> PageAlignment:
    """Anchor ``blocks`` to the pages of ``page_texts``.

    ``blocks`` are duck-typed: each needs ``source_line`` (int or None) and
    ``text``. They are read in ``source_line`` order and never mutated or
    reordered — the sort is a local view, and the document's reading order is
    the caller's business, untouched here.

    ``page_texts`` is ``page_text_layer()``'s output: one string per physical
    page, index 0 being page 1. An empty string is a page that can prove
    nothing, and never matches anything.
    """
    page_count = len(page_texts)
    if page_count == 0:
        return PageAlignment(status=AlignmentStatus.NO_EVIDENCE, page_count=0)

    normalized_pages = [normalize_text(text or "") for text in page_texts]

    ordered = sorted(
        (
            (block.source_line, index, block)
            for index, block in enumerate(blocks)
            if getattr(block, "source_line", None) is not None
        ),
        key=lambda item: (item[0], item[1]),
    )

    anchors: List[Tuple[int, int]] = []  # (source_line, page)
    counts = {"candidates": 0, "ambiguous": 0, "short": 0, "backwards": 0, "unmatched": 0}
    last_page = 0

    for source_line, _index, block in ordered:
        probe = normalize_text(getattr(block, "text", "") or "")
        if len(probe) < MIN_ANCHOR_CHARS:
            counts["short"] += 1
            continue
        probe = probe[:ANCHOR_WINDOW_CHARS]
        hits = [
            number
            for number, page in enumerate(normalized_pages, start=1)
            if page and probe in page
        ]
        if not hits:
            counts["unmatched"] += 1
            continue
        if len(hits) > 1:
            counts["ambiguous"] += 1
            continue
        counts["candidates"] += 1
        page = hits[0]
        if page < last_page:
            # Reading order is monotone in source_line, so a page behind an
            # anchor already accepted cannot be right. Refuse this one; never
            # move the document to accommodate it.
            counts["backwards"] += 1
            continue
        anchors.append((source_line, page))
        last_page = page

    if not anchors:
        return PageAlignment(
            status=AlignmentStatus.NO_EVIDENCE,
            page_count=page_count,
            candidates=counts["candidates"],
            rejected_ambiguous=counts["ambiguous"],
            rejected_short=counts["short"],
            rejected_backwards=counts["backwards"],
            unmatched=counts["unmatched"],
        )

    if counts["backwards"] > MAX_CONFLICT_RATIO * counts["candidates"]:
        return PageAlignment(
            status=AlignmentStatus.REJECTED,
            page_count=page_count,
            candidates=counts["candidates"],
            accepted=len(anchors),
            rejected_ambiguous=counts["ambiguous"],
            rejected_short=counts["short"],
            rejected_backwards=counts["backwards"],
            unmatched=counts["unmatched"],
        )

    return PageAlignment(
        status=AlignmentStatus.ALIGNED,
        page_count=page_count,
        brackets=_brackets(ordered, anchors),
        candidates=counts["candidates"],
        accepted=len(anchors),
        rejected_ambiguous=counts["ambiguous"],
        rejected_short=counts["short"],
        rejected_backwards=counts["backwards"],
        unmatched=counts["unmatched"],
        anchor_pages=tuple(page for _line, page in anchors),
    )


def _brackets(
    ordered: Sequence[Tuple[int, int, Any]], anchors: Sequence[Tuple[int, int]]
) -> Dict[int, PageBracket]:
    """One bracket per block, from the anchors on either side of it.

    An anchor brackets itself exactly. A block between two anchors is bounded
    by both, because reading order is monotone in ``source_line``. A block
    before the first anchor has an upper bound only, and one after the last
    has a lower bound only — the missing side is genuinely unknown and is left
    that way rather than filled with the nearest number to hand.
    """
    anchor_page_by_line = dict(anchors)
    brackets: Dict[int, PageBracket] = {}

    cursor = 0
    lower: Optional[int] = None
    for source_line, _index, _block in ordered:
        while cursor < len(anchors) and anchors[cursor][0] < source_line:
            lower = anchors[cursor][1]
            cursor += 1
        stated = anchor_page_by_line.get(source_line)
        if stated is not None:
            brackets[source_line] = PageBracket(lower=stated, upper=stated)
            continue
        upper = anchors[cursor][1] if cursor < len(anchors) else None
        brackets[source_line] = PageBracket(lower=lower, upper=upper)
    return brackets
