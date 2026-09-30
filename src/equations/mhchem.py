"""mhchem ``\\ce{...}`` subset -> LaTeX (docs/EQUATION_DESIGN.md §3).

Supported: formulas with counts and parenthesised groups, leading
coefficients, explicit ``^`` charges, state symbols and the arrows
``->  <-  <=>  <->``. Anything else raises ``Unsupported`` and is flagged for
a human by the caller — it is never guessed.
"""

from __future__ import annotations

import re
from typing import List, Tuple

_ARROWS = {
    "<=>": r"\rightleftharpoons",
    "<->": r"\leftrightarrow",
    "->": r"\rightarrow",
    "<-": r"\leftarrow",
}
_ARROW_RE = re.compile("|".join(re.escape(a) for a in sorted(_ARROWS, key=len, reverse=True)))
_STATE_RE = re.compile(r"\((aq|s|l|g)\)")
_CHARGE_RE = re.compile(r"\^\{?(\d*[+-])\}?")
_ELEMENT_RE = re.compile(r"[A-Z][a-z]?")
_COUNT_RE = re.compile(r"\d+")


class Unsupported(ValueError):
    """The input is outside the supported mhchem subset."""


def _group_body(text: str, start: int) -> Tuple[str, int]:
    """Parse ``( ... )`` with element/count content; returns (latex, next index)."""
    end = text.find(")", start)
    if end == -1:
        raise Unsupported("unbalanced parenthesis")
    inner = text[start + 1:end]
    if not re.fullmatch(r"(?:[A-Z][a-z]?\d*)+", inner):
        raise Unsupported(f"unsupported group: ({inner})")
    body = re.sub(r"(?<=[A-Za-z])(\d+)", r"_{\1}", inner)
    return f"({body})", end + 1


def _species(text: str, i: int) -> Tuple[str, int]:
    """One formula starting at ``i`` (no coefficient); returns (mathrm body, next i)."""
    out: List[str] = []
    start = i
    while i < len(text):
        element = _ELEMENT_RE.match(text, i)
        count = _COUNT_RE.match(text, i)
        if element:
            out.append(element.group(0))
            i = element.end()
        elif text[i] == "(" and not _STATE_RE.match(text, i):
            group, i = _group_body(text, i)
            out.append(group)
        elif count and out:
            out.append(f"_{{{count.group(0)}}}")
            i = count.end()
        else:
            break
    if i == start:
        raise Unsupported(f"no formula at {text[start:start + 8]!r}")
    charge = _CHARGE_RE.match(text, i)
    if charge:
        out.append(f"^{{{charge.group(1)}}}")
        i = charge.end()
    state = _STATE_RE.match(text, i)
    if state:
        out.append(state.group(0))
        i = state.end()
    return "".join(out), i


def translate(body: str) -> str:
    """Translate the inside of ``\\ce{...}`` to LaTeX, or raise ``Unsupported``."""
    text = body.strip()
    if not text:
        raise Unsupported("empty")
    parts: List[str] = []
    i = 0
    while i < len(text):
        if text[i].isspace():
            i += 1
            continue
        arrow = _ARROW_RE.match(text, i)
        if arrow:
            parts.append(_ARROWS[arrow.group(0)])
            i = arrow.end()
            continue
        if text[i] == "+" and parts:
            # A reaction plus has a space on both sides. ``Na+`` is a charge
            # written without a caret — ambiguous, so outside the subset.
            if not (text[i - 1].isspace() and text[i + 1:i + 2].isspace()):
                raise Unsupported("'+' without spaces: charge or separator?")
            parts.append("+")
            i += 1
            continue
        coefficient = ""
        match = _COUNT_RE.match(text, i)
        if match:
            coefficient, i = match.group(0), match.end()
        formula, i = _species(text, i)
        parts.append(f"{coefficient}\\mathrm{{{formula}}}")
    return " ".join(parts)
