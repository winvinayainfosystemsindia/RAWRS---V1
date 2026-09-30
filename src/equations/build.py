r"""Build ``Equation`` objects from a parsed Mathpix document (docs/EQUATION_DESIGN.md §2-§3).

Display blocks become one Equation per row; inline ``$...$`` / ``\(...\)``
spans inside paragraphs become anchored Equations and their paragraph text is
rewritten to a readable Unicode rendering. A footnote anchored in a rewritten
paragraph is re-expressed against the new text, so note references still land
on their marker.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from src.equations import latex as tex
from src.equations.mhchem import Unsupported, translate
from src.models.equation import Equation, EquationStatus
from src.models.phase2_document import P2Block, P2BlockType

_NUMBER_REASON = "numbered environment without \\tag: number unknown"

# Inline maths, with the same rules pandoc uses for ``$`` so prose currency is
# never maths: the opener is followed by a non-space, the closer is preceded by
# a non-space and not followed by a digit, and an escaped ``\$`` never counts.
_INLINE_RE = re.compile(
    r"(?<![\\$])\$(?!\s)(?P<dollar>[^$\n]+?)(?<!\s)\$(?!\d)|\\\((?P<paren>.+?)\\\)"
)


@dataclass(frozen=True)
class Prepared:
    latex: str
    before: str
    after: str
    status: EquationStatus
    reasons: Tuple[str, ...]
    text: str


def _matching_brace(text: str, open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def translate_chemistry(latex: str) -> Tuple[str, List[str]]:
    r"""Replace every ``\ce{...}`` with its LaTeX; report what is outside the subset."""
    out: List[str] = []
    reasons: List[str] = []
    position = 0
    while True:
        start = latex.find("\\ce{", position)
        if start == -1:
            out.append(latex[position:])
            return "".join(out), reasons
        end = _matching_brace(latex, start + 3)
        if end == -1:
            reasons.append("mhchem: unbalanced \\ce{")
            out.append(latex[position:])
            return "".join(out), reasons
        out.append(latex[position:start])
        body = latex[start + 4:end]
        try:
            out.append(translate(body))
        except Unsupported as error:
            reasons.append(f"mhchem: {error}")
            out.append(latex[start:end + 1])
        position = end + 1


def prepare(
    source: str, *, numbered_without_tag: bool = False, multi_column: bool = False
) -> Prepared:
    """Clean one expression and decide CONVERTED / FLAGGED / PLAIN."""
    translated, chemistry_reasons = translate_chemistry(source)
    cleaned = tex.strip_spacing(translated)
    equation, before, after = tex.peel_edge_text(cleaned)
    reasons = list(chemistry_reasons)
    reasons += [f"unsupported command {name}" for name in sorted(tex.unsupported_commands(equation))]
    if tex.has_inner_text(equation):
        reasons.append("text inside the equation")
    if numbered_without_tag:
        reasons.append(_NUMBER_REASON)
    if multi_column:
        reasons.append("multi-column alignment")
    if tex.is_non_maths(equation):
        status = EquationStatus.PLAIN
    elif reasons:
        status = EquationStatus.FLAGGED
    elif tex.is_simple(equation):
        status = EquationStatus.PLAIN
    else:
        status = EquationStatus.CONVERTED
    return Prepared(equation, before, after, status, tuple(reasons), tex.to_text(equation))


def _equation(
    prepared: Prepared, *, source: str, page: int, order: int, line: int, row: int, **extra
) -> Equation:
    return Equation(
        latex_source=source,
        latex=prepared.latex or source,
        status=prepared.status,
        flag_reasons=list(prepared.reasons),
        text=prepared.text,
        before_text=prepared.before,
        after_text=prepared.after,
        page_number=page,
        document_order=order,
        source_line=line,
        row=row,
        **extra,
    )


def _display_equations(block: P2Block, page: int, order: int) -> List[Equation]:
    rows = tex.split_display(block.text or "", block.equation_env or "display")
    return [
        _equation(
            prepare(
                row.latex,
                numbered_without_tag=row.numbered_without_tag,
                multi_column=row.multi_column,
            ),
            source=row.latex,
            page=page,
            order=order + index,
            line=block.source_line,
            row=index,
            number=row.number,
            label=row.label,
            numbered_environment=row.numbered_without_tag or row.number is not None,
            display=True,
        )
        for index, row in enumerate(rows)
    ]


def _rewrite_inline(
    block: P2Block, page: int, order: int
) -> Tuple[Optional[str], List[Equation], List[Tuple[int, int]]]:
    """(new text, equations, [(old span end, length delta)]); None when nothing matched."""
    text = block.text or ""
    pieces: List[str] = []
    equations: List[Equation] = []
    shifts: List[Tuple[int, int]] = []
    position = 0
    for match in _INLINE_RE.finditer(text):
        source = (match.group("dollar") or match.group("paren") or "").strip()
        if not source:
            continue
        prepared = prepare(source)
        pieces.append(text[position:match.start()])
        offset = sum(len(piece) for piece in pieces)
        pieces.append(prepared.text)
        shifts.append((match.end(), len(prepared.text) - (match.end() - match.start())))
        equations.append(
            _equation(
                prepared,
                source=source,
                page=page,
                order=order + len(equations),
                line=block.source_line,
                row=len(equations),
                display=False,
                paragraph_id=f"paragraph-line-{block.source_line}",
                anchor_offset=offset,
                anchor_length=len(prepared.text),
            )
        )
        position = match.end()
    if not equations:
        return None, [], []
    pieces.append(text[position:])
    return "".join(pieces), equations, shifts


def _shift(offset: int, shifts: List[Tuple[int, int]]) -> int:
    return offset + sum(delta for end, delta in shifts if end <= offset)


def build_equations(p2doc, resolve_page: Callable[[int], int]) -> List[Equation]:
    """Equations for every display block and inline span; rewrites ``p2doc`` in place
    (paragraph text and the anchors of notes that point into it)."""
    equations: List[Equation] = []
    blocks: List[P2Block] = []
    footnotes = list(p2doc.footnotes)
    for block in p2doc.blocks:
        page = resolve_page(block.source_line)
        if block.block_type == P2BlockType.EQUATION:
            equations.extend(_display_equations(block, page, len(equations)))
            blocks.append(block)
            continue
        if block.block_type != P2BlockType.PARAGRAPH:
            blocks.append(block)
            continue
        new_text, found, shifts = _rewrite_inline(block, page, len(equations))
        if new_text is None:
            blocks.append(block)
            continue
        equations.extend(found)
        blocks.append(dataclasses.replace(block, text=new_text))
        footnotes = [
            dataclasses.replace(
                note,
                anchor_text=new_text,
                anchor_offset=None if note.anchor_offset is None else _shift(note.anchor_offset, shifts),
            )
            if note.anchor_line == block.source_line and note.anchor_text == block.text
            else note
            for note in footnotes
        ]
    p2doc.blocks = blocks
    p2doc.footnotes = footnotes
    return equations
