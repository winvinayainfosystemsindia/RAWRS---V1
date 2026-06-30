"""F-017: Inline math and footnote reference transformer.

Converts Mathpix LaTeX math snippets that appear inline in MMD body text
to readable plain-text equivalents.

Rules applied in order
======================
1. Footnote references  ``${ }^{N}$`` → ``[N]``
2. Statistical math     ``$p \\leq 0.001$`` → ``_p_ ≤ 0.001``
3. Footnote body opener ``${ }^{N}$ rest`` at line start → ``N rest``
4. Unknown / complex    left as-is, logged

Footnote body opener (rule 3) is only used by the MMD parser when
processing standalone paragraph lines that look like footnote bodies
(line starts with ${ }^{N}$).

Statistical math heuristic
===========================
A math span is "statistical" when it contains exactly one Latin/Greek
letter or short word (p, t, F, df, r, χ², etc.) optionally followed by
a comparison operator and a numeric value.  These are converted to
``_letter_ OP value`` markdown italic form with Unicode operator symbols.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Unicode operator table ─────────────────────────────────────────────
_LATEX_OPS: dict[str, str] = {
    r"\leq": "≤",
    r"\geq": "≥",
    r"\neq": "≠",
    r"\approx": "≈",
    r"\sim": "~",
    r"\times": "×",
    r"\cdot": "·",
    r"\pm": "±",
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\delta": "δ",
    r"\chi": "χ",
    r"\mu": "μ",
    r"\sigma": "σ",
    r"\eta": "η",
    r"\kappa": "κ",
    r"\lambda": "λ",
    r"\omega": "ω",
    r"\pi": "π",
    r"\rho": "ρ",
    r"\tau": "τ",
    r"\phi": "φ",
    r"\psi": "ψ",
    r"\theta": "θ",
    r"\infty": "∞",
    r"\%": "%",
    r"\^{2}": "²",
    r"\^2": "²",
    r"^{2}": "²",
}

# Footnote reference: ${ }^{N}$ or ${}^{N}$  (N = one or two digits)
_FN_REF_RE = re.compile(r"\$\{?\s*\}?\^\{?(\d{1,3})\}?\$")

# Statistical math: $LETTER OP NUMBER$ or $LETTER OP LETTER$
_STAT_RE = re.compile(
    r"^\$\s*([a-zA-Zαβγδχμσ²₂ˉ_\-]{1,4}(?:\^2)?)\s*"
    r"(\\leq|\\geq|\\neq|\\approx|=|<|>)\s*"
    r"([0-9.]+(?:e[-+]?\d+)?|[a-zA-Z]{1,4}(?:\^2)?)\s*\$$"
)

# Superscript digits in a math span: $N$ where N is a short integer
_SIMPLE_SUP_RE = re.compile(r"^\$\{?\s*\}?\^\{?(\d{1,3})\}?\$$")


def _latex_to_unicode(s: str) -> str:
    """Replace LaTeX command sequences with Unicode equivalents."""
    for latex, uni in _LATEX_OPS.items():
        s = s.replace(latex, uni)
    return s


def transform_inline_math(text: str) -> str:
    """Replace all math spans in *text* with readable equivalents."""

    def _replace(m: re.Match) -> str:
        span = m.group(0)
        inner = m.group(1).strip() if m.lastindex else span[1:-1].strip()

        # Rule 1: footnote reference  ${ }^{N}$
        fn_m = _FN_REF_RE.fullmatch(span)
        if fn_m:
            return f"[{fn_m.group(1)}]"

        # Rule 2: statistical math
        stat_m = _STAT_RE.match(span)
        if stat_m:
            letter = _latex_to_unicode(stat_m.group(1))
            op = _latex_to_unicode(stat_m.group(2))
            value = _latex_to_unicode(stat_m.group(3))
            return f"_{letter}_ {op} {value}"

        # Unknown: leave as-is, log at DEBUG to avoid flooding
        logger.debug("Unknown inline math kept verbatim: %s", span[:60])
        return span

    # Match $...$ spans (non-greedy, single-line)
    return re.sub(r"\$[^$\n]+?\$", _replace, text)


def transform_footnote_ref(text: str) -> str:
    """Replace all ${ }^{N}$ patterns with [N] in text."""
    return _FN_REF_RE.sub(lambda m: f"[{m.group(1)}]", text)


def extract_footnote_opener(line: str) -> Optional[tuple[int, str]]:
    """If *line* starts with a footnote body opener ${ }^{N}$ rest, return (N, rest).

    Returns None otherwise.
    """
    m = _FN_REF_RE.match(line)
    if not m:
        return None
    rest = line[m.end():].strip()
    return int(m.group(1)), rest
