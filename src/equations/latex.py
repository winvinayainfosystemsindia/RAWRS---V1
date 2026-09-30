"""Pure LaTeX helpers for equation remediation (docs/EQUATION_DESIGN.md §2).

Row splitting (Eq 2), tag/label extraction (Eq 4), spacing (Eq 1), the
command allowlist behind "confident vs flag", edge-text peeling (Eq 5),
simple/non-maths classification (Eq 7), a readable Unicode rendering, and
the normalisation the converter's round trip compares with.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

# ── Allowlist (design §2, "CONVERTED only if every command is on it") ──
_GREEK = (
    "alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi "
    "pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi psi omega "
    "Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega"
).split()
FUNCTIONS = "sin cos tan cot sec csc log ln exp lim".split()
_ALLOWED_COMMANDS: Set[str] = set(
    "frac dfrac sqrt sum prod int oint lim pm mp times div cdot leq geq neq le ge ne approx equiv "
    "propto infty partial nabla to rightarrow Rightarrow leftrightarrow left right "
    "leftarrow rightleftharpoons "
    "mathrm mathbf text hat bar vec dot overline begin end".split()
) | set(_GREEK) | set(FUNCTIONS)
_ALLOWED_ENVS = {"pmatrix", "bmatrix", "vmatrix", "Vmatrix", "matrix", "cases", "aligned"}

_COMMAND_RE = re.compile(r"\\([A-Za-z]+)")
_ENV_RE = re.compile(r"\\(?:begin|end)\{([^}]*)\}")
_LABEL_RE = re.compile(r"\\label\{([^}]*)\}")
_TAG_RE = re.compile(r"\\tag\*?\{([^}]*)\}")
_NONUMBER_RE = re.compile(r"\\(?:nonumber|notag)(?![A-Za-z])")
_ALIGNED_WRAPPER_RE = re.compile(
    r"^\\begin\{(aligned|split|gathered|alignedat)\}(?:\{\d+\})?(.*)\\end\{\1\}$", re.S
)
_SPACING_RE = re.compile(r"\\(?:,|;|:|!)|\\q?quad(?![A-Za-z])")
_UNIT_SPACING_RE = re.compile(r"(?<=[0-9}])\s*\\[,;:!]\s*(?=\\(?:mathrm|text)\{)")
_NUMBERED_BASES = {"equation", "align", "gather"}


@dataclass(frozen=True)
class Row:
    """One equation after splitting a display environment."""

    latex: str
    number: Optional[str] = None
    label: Optional[str] = None
    numbered_without_tag: bool = False
    multi_column: bool = False


# ── Row splitting ──────────────────────────────────────────────────────
def _split_top_level(text: str, separator: str) -> List[str]:
    """Split on ``separator`` outside braces and ``\\begin``/``\\end`` bodies."""
    parts: List[str] = []
    brace = env = start = i = 0
    while i < len(text):
        if text.startswith(r"\begin{", i):
            env += 1
        elif text.startswith(r"\end{", i):
            env -= 1
        elif text.startswith(separator, i) and brace == 0 and env == 0:
            parts.append(text[start:i])
            i += len(separator)
            start = i
            continue
        elif text[i] == "\\" and i + 1 < len(text) and text[i + 1] in "{}":
            i += 2
            continue
        elif text[i] == "{":
            brace += 1
        elif text[i] == "}":
            brace -= 1
        i += 1
    parts.append(text[start:])
    return parts


def _clean_row(raw: str, *, strip_alignment: bool) -> Tuple[str, Optional[str], Optional[str], bool]:
    label_match = _LABEL_RE.search(raw)
    tag_match = _TAG_RE.search(raw)
    text = _TAG_RE.sub("", _LABEL_RE.sub("", _NONUMBER_RE.sub("", raw)))
    multi_column = False
    if strip_alignment:
        columns = _split_top_level(text, "&")
        multi_column = len(columns) > 2
        text = " ".join(columns)
    text = re.sub(r"\s+", " ", text).strip()
    return (
        text,
        tag_match.group(1).strip() if tag_match else None,
        label_match.group(1).strip() if label_match else None,
        multi_column,
    )


def split_display(body: str, env: str) -> List[Row]:
    """Split one display environment into one ``Row`` per equation (Eq 2)."""
    base = env.rstrip("*")
    numbered = not env.endswith("*") and base in _NUMBERED_BASES
    text = body.strip()
    wrapped = _ALIGNED_WRAPPER_RE.match(text)
    unwrapped = wrapped is not None
    if unwrapped:
        text = wrapped.group(2).strip()
    multi_row = base in ("align", "gather") or unwrapped
    raw_rows = _split_top_level(text, "\\\\") if multi_row else [text]
    rows: List[Row] = []
    for raw in raw_rows:
        if not raw.strip():
            continue
        latex, number, label, multi_column = _clean_row(raw, strip_alignment=multi_row)
        if not latex:
            continue
        rows.append(
            Row(
                latex=latex,
                number=number,
                label=label,
                numbered_without_tag=numbered and number is None and not _NONUMBER_RE.search(raw),
                multi_column=multi_column,
            )
        )
    return rows


# ── Spacing (Eq 1) ─────────────────────────────────────────────────────
def strip_spacing(latex: str) -> str:
    """Drop explicit spacing macros; keep one space before a unit."""
    text = _UNIT_SPACING_RE.sub(r"\\ ", latex)
    return _SPACING_RE.sub("", text)


# ── Allowlist / confidence boundary ────────────────────────────────────
def unsupported_commands(latex: str) -> Set[str]:
    """Commands and environments outside the allowlist (empty = confident)."""
    bad = {f"\\{name}" for name in _COMMAND_RE.findall(latex) if name not in _ALLOWED_COMMANDS}
    bad |= {f"\\begin{{{name}}}" for name in _ENV_RE.findall(latex) if name not in _ALLOWED_ENVS}
    return bad


def _text_spans(latex: str) -> List[re.Match]:
    return list(re.finditer(r"\\text\{[^{}]*\}", latex))


def has_inner_text(latex: str) -> bool:
    """True when a ``\\text{...}`` sits in the middle of the equation (Eq 5)."""
    stripped = latex.strip()
    for span in _text_spans(stripped):
        at_start = stripped[: span.start()].strip() == ""
        at_end = stripped[span.end():].strip() == ""
        if not (at_start or at_end):
            return True
    return False


def peel_edge_text(latex: str) -> Tuple[str, str, str]:
    """Move leading/trailing ``\\text{...}`` out of the box (Eq 5)."""
    text = latex.strip()
    before = after = ""
    lead = re.match(r"\\text\{([^{}]*)\}\s*", text)
    if lead and text[lead.end():].strip():
        before = lead.group(1).strip()
        text = text[lead.end():]
    trail = re.search(r"\s*\\text\{([^{}]*)\}$", text)
    if trail and text[: trail.start()].strip():
        after = trail.group(1).strip()
        text = text[: trail.start()]
    return text.strip(), before, after


# ── Eq 7: simple equations and non-maths ───────────────────────────────
_SIMPLE_COMMANDS = re.compile(r"\\(?:times|div|cdot|pm|leq|geq|neq|approx|%)")
_SIMPLE_REST_RE = re.compile(r"^[A-Za-z0-9\s.,+\-=<>()/%]+$")
_NON_MATHS_RES = [
    re.compile(r"^\(?\s*\d{4}(?:\s*[,\u2013\-]\s*\d{4})*\s*\)?$"),  # years, citations
    re.compile(r"^\\?\$\s*\d[\d,]*(?:\.\d+)?$"),  # currency
    re.compile(r"^\d+\s*[\u2013\-]\s*\d+$"),  # ranges
    re.compile(r"^\d+(?:[.,]\d+)?$"),  # bare numbers
]


def is_simple(latex: str) -> bool:
    """No fraction/root/script/matrix: the equation belongs outside a box."""
    # ``\mathrm{A}`` is the letter A: a style wrapper changes how it is set,
    # not whether it needs an equation box.
    unwrapped = latex
    for _ in range(3):
        unwrapped = _STYLE_WRAPPER_RE.sub(r"\1", unwrapped)
    rest = _SIMPLE_COMMANDS.sub("", unwrapped).strip()
    return bool(rest) and _SIMPLE_REST_RE.match(rest) is not None


def is_non_maths(latex: str) -> bool:
    """Years, currency, ranges: wrapped as maths by the source, not maths."""
    text = latex.strip()
    return any(pattern.match(text) for pattern in _NON_MATHS_RES)


# ── Readable Unicode rendering ─────────────────────────────────────────
_SYMBOLS = {
    r"\leq": "≤", r"\le": "≤", r"\geq": "≥", r"\ge": "≥", r"\neq": "≠", r"\ne": "≠",
    r"\approx": "≈", r"\equiv": "≡", r"\propto": "∝", r"\times": "×", r"\div": "÷",
    r"\cdot": "·", r"\pm": "±", r"\mp": "∓", r"\infty": "∞", r"\partial": "∂",
    r"\nabla": "∇", r"\to": "→", r"\rightarrow": "→", r"\Rightarrow": "⇒",
    r"\leftrightarrow": "↔", r"\%": "%", r"\sum": "∑", r"\prod": "∏", r"\int": "∫",
    r"\oint": "∮",
}
_GREEK_UNICODE = dict(
    zip(
        _GREEK,
        "α β γ δ ε ε ζ η θ ϑ ι κ λ μ ν ξ π ϖ ρ ϱ σ ς τ υ φ ϕ χ ψ ω Γ Δ Θ Λ Ξ Π Σ Υ Φ Ψ Ω".split(),
    )
)
_SUPERSCRIPTS = str.maketrans("0123456789+-=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ")
_SUBSCRIPTS = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
_SUP_CHARS = set("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ")
_SUB_CHARS = set("₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
_RELATIONS = "=<>≤≥≠≈≡∝±∓×÷→⇒↔"


def to_text(latex: str) -> str:
    """A readable one-line Unicode rendering (used for ``Paragraph.text``)."""
    text = latex
    for command in ("left", "right", "displaystyle"):
        text = re.sub(rf"\\{command}(?![A-Za-z])\.?", "", text)
    for _ in range(4):
        text = re.sub(r"\\(?:mathrm|text|mathbf|operatorname)\{([^{}]*)\}", r"\1", text)
        text = re.sub(r"\\d?frac\{([^{}]*)\}\{([^{}]*)\}", _fraction, text)
        text = re.sub(r"\\sqrt\{([^{}]*)\}", lambda m: "√" + _group(m.group(1)), text)
    for name, symbol in sorted(_GREEK_UNICODE.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"\\{name}(?![A-Za-z])", symbol, text)
    for command, symbol in sorted(_SYMBOLS.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(re.escape(command) + r"(?![A-Za-z])", f" {symbol} ", text)
    text = re.sub(r"\\([A-Za-z]+)", r"\1", text)
    text = re.sub(r"\^\{([^{}]*)\}|\^(\w)", lambda m: _sup(m.group(1) if m.group(1) is not None else m.group(2)), text)
    text = re.sub(r"_\{([^{}]*)\}|_(\w)", lambda m: _sub(m.group(1) if m.group(1) is not None else m.group(2)), text)
    text = text.replace("{", "").replace("}", "").replace("\\ ", " ")
    return _tidy(text)


def _group(body: str) -> str:
    return body if len(body) == 1 else f"({body})"


def _fraction(match: re.Match) -> str:
    top, bottom = match.group(1), match.group(2)
    if len(top) == 1 and len(bottom) == 1:
        return f"{top}/{bottom}"
    return f"{_group(top)}/{_group(bottom)}"


def _sup(body: str) -> str:
    mapped = body.translate(_SUPERSCRIPTS)
    return mapped if set(mapped) <= _SUP_CHARS else f"^({body})"


def _sub(body: str) -> str:
    mapped = body.translate(_SUBSCRIPTS)
    return mapped if set(mapped) <= _SUB_CHARS else f"_({body})"


def _tidy(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(?<=\w)\s+(?=\w)", "", text)
    text = re.sub(r"\s*([" + re.escape(_RELATIONS) + r"])\s*", r" \1 ", text)
    text = re.sub(r"(?<=[\w)²³¹⁰-⁹₀-₉])\s*([+\-\u2212])\s*(?=[\w(√])", r" \1 ", text)
    text = text.replace(" - ", " − ")
    return re.sub(r"\s+", " ", text).strip()


# ── Round-trip normalisation ───────────────────────────────────────────
_MATRIX_BODY_RE = re.compile(
    r"(\\begin\{(?:[pbvV]?matrix|cases)\})(.*?)(\\end\{(?:[pbvV]?matrix|cases)\})", re.S
)
_EQUIVALENT_COMMANDS = {
    r"\dfrac": r"\frac", r"\tfrac": r"\frac", r"\le": r"\leq", r"\ge": r"\geq", r"\ne": r"\neq",
    r"\rightarrow": r"\to", r"\overrightarrow": r"\vec", r"\lbrack": "[", r"\rbrack": "]",
    r"\lbrace": r"\{", r"\rbrace": r"\}",
    r"\widehat": r"\hat", r"\widetilde": r"\tilde",
}
_ACCENT_BARE_ARGUMENT_RE = re.compile(r"(\\(?:hat|tilde|bar|vec|dot))\s*(\\[A-Za-z]+|[A-Za-z0-9])")
_ACCENT_GROUP_RE = re.compile(r"\{(\\(?:hat|tilde|bar|vec|dot)\{[^{}]*\})\}")
_EMPTY_SCRIPT_RE = re.compile(r"[\^_]\{\}")
_STYLE_WRAPPER_RE = re.compile(r"\\(?:mathrm|text|mathbf|operatorname)\{((?:[^{}]|\{[^{}]*\})*)\}")
_PRIME_BEFORE_SCRIPT_RE = re.compile(r"'(_[A-Za-z0-9]+)")


def _rows_to_token(match: re.Match) -> str:
    body = match.group(2).replace("\\\\", "@ROW@")
    body = re.sub(r"\\ ", "@ROW@", body)
    return match.group(1) + body + match.group(3)


def normalise(latex: str) -> str:
    """Canonical form for comparing source LaTeX with the round-tripped one."""
    text = re.sub(r"\\begin\{cases\}", lambda _m: r"\left\{\begin{matrix}", latex)
    text = re.sub(r"\\end\{cases\}", lambda _m: r"\end{matrix}\right.", text)
    text = _MATRIX_BODY_RE.sub(_rows_to_token, text)
    text = re.sub(r"\\(?:left|right)(?![A-Za-z])", "", text)
    for source, target in _EQUIVALENT_COMMANDS.items():
        text = re.sub(re.escape(source) + r"(?![A-Za-z])", lambda _m, t=target: t, text)
    # Script braces first, so ``\mathrm{H_{2}}`` has no inner braces left and
    # the wrapper can be unwrapped (one nested group is allowed, for
    # ``\mathrm{\hat{J}}``).
    text = _EMPTY_SCRIPT_RE.sub("", text)
    text = re.sub(r"([\^_])\{([A-Za-z0-9.]+)\}", r"\1\2", text)
    for _ in range(4):
        text = _STYLE_WRAPPER_RE.sub(r"\1", text)
    # Accents: ``\hat\lambda`` and ``{\widehat{\lambda}}`` are one thing.
    text = _ACCENT_BARE_ARGUMENT_RE.sub(lambda m: f"{m.group(1)}{{{m.group(2)}}}", text)
    text = _ACCENT_GROUP_RE.sub(lambda m: m.group(1), text)
    # ``U'_{eff}`` and ``U_{eff}'`` are the same symbol.
    text = _PRIME_BEFORE_SCRIPT_RE.sub(r"\1'", text)
    text = _SPACING_RE.sub("", text)
    text = re.sub(r"\\ ", "", text)
    return re.sub(r"\s+", "", text)
