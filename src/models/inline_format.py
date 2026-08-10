"""What a paragraph's own typography says, independent of any format.

P4a. This rule used to live inside the Markdown projection: it decided
whether a paragraph was bold or italic, wrapped the text in ``**``/``*``,
and the DOCX generator then *parsed those asterisks back* to set
``run.font.bold``. One semantic question — "is this prose emphasised?" —
answered in a renderer and recovered by the next renderer down, which is
the defect ADR-019 named.

The answer comes from the model and always did: ``TextBlock.spans`` carry
PyMuPDF font flags, and 016G reads them. What P4a moves is *where the
reading happens*, not what it concludes.

**Semantic runs, not markup.** ``format_runs`` returns ``TextRun`` objects
carrying text and two booleans. Markdown turns a bold run into ``**...**``;
DOCX will set ``w:b``. Neither has to know how the other spells it.

**One run per paragraph, today.** 016G decides at paragraph granularity: a
paragraph is emphasised only when *every* contributing block agrees, so the
list this returns always has exactly one element. The list shape is what a
run-consuming projection needs, and it is what a future span-level rule
would fill in — but splitting text at span boundaries is a different
decision, with its own evidence, and is deliberately not made here. A
paragraph of mixed emphasis renders unemphasised, exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Sequence

#: PyMuPDF span font flags. Named because a bare ``s.font_flags & 16`` in
#: three places is three chances to use the wrong bit.
SUPERSCRIPT_FLAG = 1
ITALIC_FLAG = 2
BOLD_FLAG = 16


@dataclass(frozen=True)
class TextRun:
    """A stretch of text and the emphasis the document gives it.

    Frozen: a run is an answer about the document, not a buffer a renderer
    accumulates into.
    """

    text: str
    bold: bool = False
    italic: bool = False


def format_runs(text: str, blocks: Sequence[Any]) -> List[TextRun]:
    """The emphasis runs for ``text``, as its ``blocks`` describe it.

    ``blocks`` are the ``TextBlock``s a paragraph was assembled from
    (``Paragraph.source_block_ids``, resolved). With none of them — a
    paragraph whose blocks are gone, or a caller with no block data at all
    — the text comes back unemphasised rather than guessed at.
    """
    if not blocks:
        return [TextRun(text)]
    return [TextRun(text, bold=all_blocks_bold(blocks), italic=all_blocks_italic(blocks))]


def all_blocks_bold(blocks: Sequence[Any]) -> bool:
    """True when every block's non-superscript spans are bold (016G).

    A footnote marker's superscript span is decoration, not body
    formatting, so it is excluded; a block whose spans are *all*
    superscript says nothing either way and is skipped rather than counted
    against. ``TextBlock.is_bold`` — structure_detector's majority-vote
    line signal — is the fallback for a block with no span data.
    """
    if not blocks:
        return False
    for block in blocks:
        spans = getattr(block, "spans", None)
        if spans:
            body_spans = [s for s in spans if not (s.font_flags & SUPERSCRIPT_FLAG)]
            if not body_spans:
                continue
            if not all(s.font_flags & BOLD_FLAG for s in body_spans):
                return False
        elif getattr(block, "is_bold", None) is True:
            continue
        else:
            return False
    return True


def all_blocks_italic(blocks: Sequence[Any]) -> bool:
    """True when every block's non-superscript spans are italic (016G).

    No line-level fallback exists — ``TextBlock`` has no ``is_italic`` — so
    a block without spans cannot confirm italic and the paragraph is not
    italic. That asymmetry with bold is deliberate and predates P4a:
    asserting italic from nothing would italicise ordinary prose.
    """
    if not blocks:
        return False
    for block in blocks:
        spans = getattr(block, "spans", None)
        if not spans:
            return False
        body_spans = [s for s in spans if not (s.font_flags & SUPERSCRIPT_FLAG)]
        if not body_spans:
            continue
        if not all(s.font_flags & ITALIC_FLAG for s in body_spans):
            return False
    return True
