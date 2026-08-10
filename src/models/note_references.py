"""Where a note's reference sits inside a piece of text.

P4a. Locating a note's printed marker used to live inside the Markdown
projection, which resolved the position *and* spelled the result
``[^label]``. The DOCX generator then found those brackets again with a
regex to emit ``w:footnoteReference``. Two renderers, one question: "where
in this text does note N appear, and which note is it?"

The evidence has been on the model since bug_005: ``Footnote.anchor_text``
is the exact source line the marker came from, and ``Footnote.anchor_offset``
is the marker's position *within that line*. This module applies that
evidence and returns positions. It spells nothing.

**Offsets are relative to the anchor line, not to the paragraph.** That is
what makes them survive paragraph assembly: ``Paragraph.text`` joins
several source lines and repairs hyphenation, so an offset into the
paragraph would be meaningless, while the anchor line is still findable
inside it. Callers may pass any text containing the anchor line — a raw
line, an assembled paragraph, or one already wrapped in emphasis markers —
because the line is located first and the offset applied relative to it.

**Two tiers, in this order.** An offset that lands exactly on the marker is
used as-is. Otherwise the marker is searched for *within the anchor line's
own region only*, never the whole text: a plain-digit marker (bug_005's
span signal) collides with years, page numbers and counts elsewhere in the
same paragraph. A reference that resolves neither way is not returned at
all — the caller leaves the text alone, which is what both projections did
before this module existed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class NoteReference:
    """One resolved reference: where it is, and which note it names.

    ``start``/``length`` delimit the printed marker inside the text that
    was searched, so a projection replaces exactly that slice — Markdown
    with ``[^label]``, DOCX with a reference run. The note itself is
    carried rather than copied, so identity, kind and printed number are
    read from the model and cannot drift.
    """

    start: int
    length: int
    note: Any

    @property
    def note_id(self) -> Optional[str]:
        return getattr(self.note, "footnote_id", None)

    @property
    def label(self) -> str:
        return self.note.label

    @property
    def number(self) -> int:
        return self.note.number

    @property
    def note_type(self) -> Any:
        return self.note.note_type


def resolve_note_references(text: str, notes: Sequence[Any]) -> List[NoteReference]:
    """Every reference in ``notes`` that can be located inside ``text``.

    Returned in ascending position. A projection that rewrites the text
    should apply them in *descending* position, so an earlier replacement's
    length change cannot invalidate a later one.

    A note whose anchor line is absent from ``text`` is skipped silently and
    deliberately: one call may be handed a whole page's notes while
    rendering a single paragraph, and a note belonging to a different
    paragraph must never touch this one.
    """
    by_anchor: Dict[str, List[Any]] = {}
    for note in notes:
        by_anchor.setdefault(note.anchor_text, []).append(note)

    resolved: List[NoteReference] = []
    deferred: List[Tuple[int, Any]] = []  # (anchor position, note)

    for anchor_text, group in by_anchor.items():
        anchor_position = text.find(anchor_text)
        if anchor_position == -1:
            continue
        for note in group:
            start = _exact_position(text, anchor_position, note)
            if start is None:
                deferred.append((anchor_position, note))
            else:
                resolved.append(NoteReference(start, len(note.marker), note))

    # Searched second, and never over a slice an exact hit already owns: two
    # notes can share an anchor line, and the one with a usable offset has
    # the stronger claim to the marker it points at.
    claimed = [(r.start, r.start + r.length) for r in resolved]
    for anchor_position, note in deferred:
        start = _searched_position(text, anchor_position, note, claimed)
        if start is None:
            continue
        resolved.append(NoteReference(start, len(note.marker), note))
        claimed.append((start, start + len(note.marker)))

    resolved.sort(key=lambda reference: reference.start)
    return resolved


def _exact_position(text: str, anchor_position: int, note: Any) -> Optional[int]:
    """The recorded offset, when it still lands on the marker."""
    offset = getattr(note, "anchor_offset", None)
    if offset is None:
        return None
    start = anchor_position + offset
    if not (0 <= start <= len(text) - len(note.marker)):
        return None
    return start if text[start : start + len(note.marker)] == note.marker else None


def _searched_position(
    text: str, anchor_position: int, note: Any, claimed: Sequence[Tuple[int, int]]
) -> Optional[int]:
    """The first unclaimed marker inside the anchor line's own region."""
    region_end = anchor_position + len(note.anchor_text)
    search = anchor_position
    while True:
        hit = text.find(note.marker, search, region_end)
        if hit == -1:
            return None
        if not any(start <= hit < end for start, end in claimed):
            return hit
        search = hit + 1
