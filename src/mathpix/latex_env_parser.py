"""F-014: LaTeX environment parser.

Tokenises MMD text into a flat list of raw tokens that the MMD parser
then converts to P2Block objects.  Handles multi-line brace groups and
nested \begin{...}...\end{...} environments.

Token shapes
============
    ('cmd',   line_no, name, arg)          single-line \name{arg}
    ('env',   line_no, name, body)         \begin{name}...\end{name}
    ('text',  line_no, text)               plain paragraph text
    ('quote', line_no, text)               > blockquote line
    ('item',  line_no, text, numbered, n)  list item
    ('sep',   line_no)                     ***** separator

Commands recognised at top level (arg extraction applied)
==========================================================
    title, author, section*, subsection*, subsubsection*,
    footnotetext, caption, includegraphics
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

# Raw token type alias
Token = tuple


_KNOWN_CMDS = frozenset({
    "title", "author",
    "section*", "subsection*", "subsubsection*",
    "footnotetext", "footnotetext*",
    "caption", "captionsetup",
    "includegraphics",
})

_SEPARATOR_RE = re.compile(r"^\*{3,}$")
_ITEM_BULLET_RE = re.compile(r"^[-•▪▸▶◦○◉●→⁃✓✗✔✘]\s+(.+)$")
_ITEM_NUMBERED_RE = re.compile(r"^(\d+)\.\s+(.+)$")
_QUOTE_RE = re.compile(r"^>\s*(.*)")

# Matches \cmdname{ or \cmdname*{ at start of (stripped) line
_CMD_RE = re.compile(r"^\\([A-Za-z]+\*?)\s*\{")
# Optional arg before brace: \includegraphics[...]{
_CMD_OPT_RE = re.compile(r"^\\([A-Za-z]+\*?)\s*(?:\[[^\]]*\])?\s*\{")


def _extract_braced(lines: List[str], start_line: int, start_col: int) -> Tuple[str, int, int]:
    """Return (content, end_line_index, end_col) for the first complete {...} group.

    start_col points at the opening '{'.  Handles nested braces.
    Returns content without the outer braces.
    """
    depth = 0
    content_chars: List[str] = []
    li = start_line
    ci = start_col

    while li < len(lines):
        line = lines[li]
        while ci < len(line):
            ch = line[ci]
            if ch == "{":
                depth += 1
                if depth > 1:
                    content_chars.append(ch)
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return "".join(content_chars).strip(), li, ci + 1
                else:
                    content_chars.append(ch)
            else:
                content_chars.append(ch)
            ci += 1
        if li < len(lines) - 1:
            content_chars.append("\n")
        li += 1
        ci = 0

    return "".join(content_chars).strip(), li, ci


def _find_env_end(lines: List[str], start_line: int, env_name: str) -> Tuple[str, int]:
    """Collect body between \begin{env} and matching \end{env}.

    Returns (body_text, line_index_after_end).
    Handles one level of nesting (nested same-name envs).
    """
    body: List[str] = []
    depth = 1
    li = start_line

    while li < len(lines):
        line = lines[li]
        stripped = line.strip()
        if stripped == f"\\begin{{{env_name}}}":
            depth += 1
            body.append(line)
        elif stripped == f"\\end{{{env_name}}}":
            depth -= 1
            if depth == 0:
                return "\n".join(body), li + 1
            else:
                body.append(line)
        else:
            body.append(line)
        li += 1

    return "\n".join(body), li


def tokenize(text: str) -> List[Token]:
    """Convert raw MMD string to a flat list of tokens."""
    lines = text.split("\n")
    tokens: List[Token] = []
    i = 0
    para_buf: List[str] = []
    para_start = 0

    def flush_para() -> None:
        if para_buf:
            tokens.append(("text", para_start, "\n".join(para_buf)))
            para_buf.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Blank line → flush paragraph
        if not stripped:
            flush_para()
            i += 1
            continue

        # Separator line (****)
        if _SEPARATOR_RE.match(stripped):
            flush_para()
            tokens.append(("sep", i))
            i += 1
            continue

        # \begin{env}
        if stripped.startswith(r"\begin{"):
            m = re.match(r"\\begin\{([^}]+)\}", stripped)
            if m:
                flush_para()
                env_name = m.group(1)
                body, i = _find_env_end(lines, i + 1, env_name)
                tokens.append(("env", i, env_name, body))
                continue

        # Known LaTeX commands that take a {arg}
        m = _CMD_OPT_RE.match(stripped)
        if m:
            cmd = m.group(1)
            if cmd in _KNOWN_CMDS:
                flush_para()
                # Find opening brace on this line
                brace_pos = stripped.index("{")
                content, end_li, _ = _extract_braced(lines, i, line.index("{"))
                tokens.append(("cmd", i, cmd, content))
                i = end_li if end_li > i else i + 1
                continue

        # Blockquote
        qm = _QUOTE_RE.match(stripped)
        if qm:
            flush_para()
            tokens.append(("quote", i, qm.group(1)))
            i += 1
            continue

        # Bullet list item
        bm = _ITEM_BULLET_RE.match(stripped)
        if bm:
            flush_para()
            tokens.append(("item", i, bm.group(1), False, None))
            i += 1
            continue

        # Numbered list item
        nm = _ITEM_NUMBERED_RE.match(stripped)
        if nm:
            flush_para()
            tokens.append(("item", i, nm.group(2), True, int(nm.group(1))))
            i += 1
            continue

        # Everything else: accumulate as paragraph text
        if not para_buf:
            para_start = i
        para_buf.append(stripped)
        i += 1

    flush_para()
    return tokens
