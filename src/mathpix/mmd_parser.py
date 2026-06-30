"""Mathpix MMD parser — converts Mathpix Markdown (MMD) to a P2Document.

MMD is a LaTeX-like format produced by the Mathpix OCR platform.  This
parser converts it into a structured P2Document (src/models/phase2_document.py)
which the MathpixImportProvider then maps to the canonical RAWRS Document
model.

Supported constructs
====================
* ``\\title{...}``                        → P2FrontMatter.title
* ``\\author{...}``                       → P2FrontMatter.authors
* ``\\section*{...}``                     → P2Heading(level=2)
* ``\\subsection*{...}``                  → P2Heading(level=3)
* ``\\subsubsection*{...}``               → P2Heading(level=4)
* ``\\begin{abstract}...\\end{abstract}`` → P2Block(ABSTRACT)
* ``\\begin{figure}...\\end{figure}``     → P2Block(FIGURE, P2Figure)
* ``\\begin{tabular}...\\end{tabular}``   → P2Block(TABLE, P2Table)
* ``| pipe | tables |``                   → P2Block(TABLE, P2Table)
* ``- item`` / ``1. item``               → P2Block(LIST_ITEM)
* ``${ }^{N}$``                           → inline ``[N]`` (via math_transformer)
* ``\\footnotetext{N}{body}``             → P2Footnote
* Free paragraph text                     → P2Block(PARAGRAPH)

File extension quirks: some Mathpix exports have double extensions
(.mmd.mmd, .md.md).  Callers resolve extensions before passing ``content``.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from src.mathpix.math_transformer import transform_inline_math
from src.models.phase2_document import (
    P2Block,
    P2BlockType,
    P2Document,
    P2Figure,
    P2FrontMatter,
    P2Heading,
    P2ListStyle,
    P2Table,
    P2TableCell,
    P2Footnote,
)

# ── Heading command → level mapping ───────────────────────────────────
_HEADING_LEVEL: dict[str, int] = {
    "title": 1,
    "section": 2,
    "subsection": 3,
    "subsubsection": 4,
    "subsubsubsection": 5,
    "paragraph": 5,
}

# ── Compiled patterns ─────────────────────────────────────────────────

# \cmd{content} or \cmd*{content} — all on one line
_HEADING_INLINE_RE = re.compile(
    r"^\\(title|author|section|subsection|subsubsection|subsubsubsection|paragraph)\*?\{(.+)\}\s*$"
)
# \cmd{ — opening of a multiline braced argument
_HEADING_OPEN_RE = re.compile(
    r"^\\(title|author|section|subsection|subsubsection|subsubsubsection|paragraph)\*?\{\s*$"
)
# \begin{env} and \end{env}
_BEGIN_RE = re.compile(r"^\\begin\{(\w+\*?)\}")
_END_RE = re.compile(r"^\\end\{(\w+\*?)\}")
# \includegraphics[options]{path}
_INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
# \caption{text}
_CAPTION_RE = re.compile(r"\\caption\{([^}]*)\}")
# \footnotetext{N}{body}
_FOOTNOTETEXT_RE = re.compile(r"^\\footnotetext\{(\d+)\}\{(.+)\}\s*$")
# Pipe table row: | ... |
_PIPE_ROW_RE = re.compile(r"^\|.+\|\s*$")
# Pipe separator row: |---|:---:|---| (only dashes, colons, pipes, spaces)
_PIPE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|\s*$")
# List items
_BULLET_RE = re.compile(r"^[-*]\s+(.+)$")
_NUMBERED_RE = re.compile(r"^(\d+)\.\s+(.+)$")
# Publisher caption labels printed on the page: "FIGURE 1.1 ..."
_PUBLISHER_LABEL_RE = re.compile(
    r"^(FIGURE|TABLE|CHART|BOX|APPENDIX|FIG\.?)\s+[\d.]", re.IGNORECASE
)


def parse_mmd(content: str) -> P2Document:
    """Parse Mathpix MMD content into a P2Document.

    Args:
        content: Raw MMD text (UTF-8 string).

    Returns:
        P2Document with front_matter, blocks, and footnotes populated.
        Never raises — malformed constructs are silently emitted as
        PARAGRAPH blocks to preserve content rather than lose it.
    """
    doc = P2Document()
    doc.front_matter = P2FrontMatter()

    lines = content.splitlines()
    n = len(lines)
    i = 0

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # ── Blank line ─────────────────────────────────────────────────
        if not stripped:
            i += 1
            continue

        # ── \footnotetext{N}{body} ─────────────────────────────────────
        fn_m = _FOOTNOTETEXT_RE.match(stripped)
        if fn_m:
            doc.footnotes.append(
                P2Footnote(number=int(fn_m.group(1)), body=fn_m.group(2).strip())
            )
            i += 1
            continue

        # ── Heading: single-line \cmd{content} ────────────────────────
        h_m = _HEADING_INLINE_RE.match(stripped)
        if h_m:
            cmd, text = h_m.group(1), h_m.group(2).strip()
            i += 1
            i = _apply_heading(doc, cmd, text, i)
            continue

        # ── Heading: multiline \cmd{\n content \n} ────────────────────
        h_open = _HEADING_OPEN_RE.match(stripped)
        if h_open:
            cmd = h_open.group(1)
            text, i = _collect_to_closing_brace(lines, i + 1, n)
            _apply_heading(doc, cmd, text, i)
            continue

        # ── \begin{env} environment ────────────────────────────────────
        begin_m = _BEGIN_RE.match(stripped)
        if begin_m:
            env = begin_m.group(1)
            env_lines, i = _collect_env(lines, i, n, env)
            block = _parse_env(env, env_lines, i)
            if block is not None:
                doc.blocks.append(block)
            continue

        # ── Pipe table ─────────────────────────────────────────────────
        if _PIPE_ROW_RE.match(stripped):
            table_lines, i = _collect_pipe_table(lines, i, n)
            block = _parse_pipe_table(table_lines, i)
            if block is not None:
                doc.blocks.append(block)
            continue

        # ── Publisher caption label ────────────────────────────────────
        if _PUBLISHER_LABEL_RE.match(stripped):
            doc.blocks.append(
                P2Block(
                    block_type=P2BlockType.PUBLISHER_LINE,
                    text=stripped,
                    source_line=i,
                )
            )
            i += 1
            continue

        # ── Bullet list item ───────────────────────────────────────────
        b_m = _BULLET_RE.match(stripped)
        if b_m:
            doc.blocks.append(
                P2Block(
                    block_type=P2BlockType.LIST_ITEM,
                    text=transform_inline_math(b_m.group(1)),
                    list_style=P2ListStyle.BULLET,
                    source_line=i,
                )
            )
            i += 1
            continue

        # ── Numbered list item ─────────────────────────────────────────
        nb_m = _NUMBERED_RE.match(stripped)
        if nb_m:
            doc.blocks.append(
                P2Block(
                    block_type=P2BlockType.LIST_ITEM,
                    text=transform_inline_math(nb_m.group(2)),
                    list_style=P2ListStyle.NUMBERED,
                    list_number=int(nb_m.group(1)),
                    source_line=i,
                )
            )
            i += 1
            continue

        # ── Plain paragraph ────────────────────────────────────────────
        doc.blocks.append(
            P2Block(
                block_type=P2BlockType.PARAGRAPH,
                text=transform_inline_math(stripped),
                source_line=i,
            )
        )
        i += 1

    return doc


# ── Internal helpers ───────────────────────────────────────────────────

def _apply_heading(doc: P2Document, cmd: str, text: str, next_i: int) -> int:
    """Store a parsed heading/title into doc; return next_i unchanged."""
    if not text:
        return next_i
    if cmd == "title":
        doc.front_matter.title = text
    elif cmd == "author":
        doc.front_matter.authors.append(text)
    else:
        level = _HEADING_LEVEL.get(cmd, 2)
        doc.blocks.append(
            P2Block(
                block_type=P2BlockType.HEADING,
                heading=P2Heading(
                    level=level,
                    text=text,
                    mmd_command=cmd + "*",
                ),
                source_line=next_i,
            )
        )
    return next_i


def _collect_to_closing_brace(
    lines: List[str], start: int, n: int
) -> Tuple[str, int]:
    """Collect lines until a bare '}' line; return (joined_text, next_i)."""
    parts: List[str] = []
    i = start
    while i < n:
        stripped = lines[i].strip()
        if stripped == "}":
            return " ".join(p for p in parts if p), i + 1
        if stripped:
            parts.append(stripped)
        i += 1
    return " ".join(p for p in parts if p), i


def _collect_env(
    lines: List[str], start: int, n: int, env: str
) -> Tuple[List[str], int]:
    """Collect all lines from \\begin{env} through \\end{env} inclusive."""
    collected = [lines[start]]
    i = start + 1
    depth = 1
    # Normalise env name: strip trailing * for depth tracking
    base = env.rstrip("*")
    while i < n:
        l = lines[i]
        s = l.strip()
        collected.append(l)
        bm = _BEGIN_RE.match(s)
        if bm and bm.group(1).rstrip("*") == base:
            depth += 1
        em = _END_RE.match(s)
        if em and em.group(1).rstrip("*") == base:
            depth -= 1
            if depth == 0:
                return collected, i + 1
        i += 1
    return collected, i


def _parse_env(
    env: str, env_lines: List[str], src_line: int
) -> Optional[P2Block]:
    """Convert an environment's collected lines into a P2Block."""
    base = env.rstrip("*")
    if base == "figure":
        return _parse_figure_env(env_lines, src_line)
    if base in ("tabular", "tabularx", "longtable", "tabulary"):
        return _parse_tabular_env(env_lines, src_line)
    if base == "table":
        # Float wrapper — look for a nested tabular environment
        for idx, line in enumerate(env_lines):
            tab_m = _BEGIN_RE.match(line.strip())
            if tab_m and tab_m.group(1).rstrip("*") in (
                "tabular", "tabularx", "longtable", "tabulary"
            ):
                inner_lines, _ = _collect_env(
                    env_lines, idx, len(env_lines), tab_m.group(1)
                )
                return _parse_tabular_env(inner_lines, src_line)
        return None
    if base == "abstract":
        parts = [
            l.strip() for l in env_lines
            if l.strip()
            and not _BEGIN_RE.match(l.strip())
            and not _END_RE.match(l.strip())
        ]
        text = " ".join(parts)
        if text:
            return P2Block(
                block_type=P2BlockType.ABSTRACT, text=text, source_line=src_line
            )
    return None


def _parse_figure_env(
    env_lines: List[str], src_line: int
) -> P2Block:
    caption: Optional[str] = None
    image_path: Optional[str] = None
    for line in env_lines:
        if caption is None:
            cap_m = _CAPTION_RE.search(line)
            if cap_m:
                caption = cap_m.group(1).strip() or None
        if image_path is None:
            img_m = _INCLUDEGRAPHICS_RE.search(line)
            if img_m:
                image_path = img_m.group(1).strip()
    return P2Block(
        block_type=P2BlockType.FIGURE,
        figure=P2Figure(image_path=image_path, caption=caption),
        source_line=src_line,
    )


def _parse_tabular_env(
    env_lines: List[str], src_line: int
) -> Optional[P2Block]:
    """Parse a LaTeX tabular environment into a P2Table."""
    rows: List[List[P2TableCell]] = []
    for line in env_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _BEGIN_RE.match(stripped) or _END_RE.match(stripped):
            continue
        # \hline (possibly with content after it on the same line)
        if stripped.startswith(r"\hline"):
            stripped = stripped[len(r"\hline"):].strip()
            if not stripped:
                continue
        # Row: cells separated by & terminated by \\
        if r"\\" in stripped or "&" in stripped:
            row_text = stripped.rstrip("\\").rstrip()
            cell_texts = [c.strip() for c in row_text.split("&")]
            row = [
                P2TableCell(
                    text=transform_inline_math(c),
                    col_span=1,
                    row_span=1,
                )
                for c in cell_texts
            ]
            if row:
                rows.append(row)
    if not rows:
        return None
    return P2Block(
        block_type=P2BlockType.TABLE,
        table=P2Table(rows=rows, has_header_row=bool(rows)),
        source_line=src_line,
    )


def _collect_pipe_table(
    lines: List[str], start: int, n: int
) -> Tuple[List[str], int]:
    """Collect consecutive pipe-table rows (including separator rows)."""
    collected = [lines[start]]
    i = start + 1
    while i < n:
        stripped = lines[i].strip()
        if _PIPE_ROW_RE.match(stripped):
            collected.append(lines[i])
            i += 1
        else:
            break
    return collected, i


def _parse_pipe_table(
    table_lines: List[str], src_line: int
) -> Optional[P2Block]:
    """Parse markdown pipe table rows into a P2Table."""
    rows: List[List[P2TableCell]] = []
    has_header = False
    for line in table_lines:
        stripped = line.strip()
        if _PIPE_SEP_RE.match(stripped):
            has_header = bool(rows)
            continue
        # Strip leading/trailing pipes and split on |
        inner = stripped.strip("|")
        cell_texts = [c.strip() for c in inner.split("|")]
        if not any(cell_texts):
            continue
        row = [
            P2TableCell(
                text=transform_inline_math(c),
                col_span=1,
                row_span=1,
            )
            for c in cell_texts
        ]
        rows.append(row)
    if not rows:
        return None
    return P2Block(
        block_type=P2BlockType.TABLE,
        table=P2Table(rows=rows, has_header_row=has_header),
        source_line=src_line,
    )
