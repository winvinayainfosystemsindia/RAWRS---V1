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
# Markdown-flavoured MMD (what Mathpix emits for many scans): "## Heading"
# and "![alt](https://cdn.mathpix.com/cropped/...-04.jpg?height=..)".
_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_MARKDOWN_IMAGE_RE = re.compile(r"^!\[([^\]]*)\]\((\S+?)\)\s*$")
# Pipe separator row: |---|:---:|---| (only dashes, colons, pipes, spaces)
_PIPE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|\s*$")
# List items
_BULLET_RE = re.compile(r"^[-*]\s+(.+)$")
_NUMBERED_RE = re.compile(r"^(\d+)\.\s+(.+)$")
# N-1: an inline superscript number, in the three forms Mathpix emits.
# ``${ }^{12}$`` is by far the common one — src/mathpix/math_transformer.py's
# first rule already calls it a footnote reference and renders it ``[12]``.
# Recognising the *marker* is not the same as proving a *note*: see
# _prove_note_apparatus() for what turns these into notes and what does not.
_SUPERSCRIPT_MARKER_RE = re.compile(
    r"\$\{\s*\}\^\{(\d{1,3})\}\$|\^\{(\d{1,3})\}|\\textsuperscript\{(\d{1,3})\}"
)
# Publisher caption labels printed on the page: "FIGURE 1.1 ..."
_PUBLISHER_LABEL_RE = re.compile(
    r"^(FIGURE|TABLE|CHART|BOX|APPENDIX|FIG\.?)\s+[\d.]", re.IGNORECASE
)

# Boxed-aside label patterns (FEATURE_019, forensic-audit DEF-04): a
# heading whose text matches one of these is a Callout label, not an
# ordinary content heading — see src/models/callout.py. Deliberately a
# short, explicit list rather than a single greedy pattern: each entry
# names the exact vocabulary confirmed against a real textbook (Patrick &
# McPhee, "Contemporary Issues in Learning and Teaching"); a publisher
# using different box names extends this dict, not the classifier logic.
# Numbering ("11.2") and a following name ("Kate") are both optional.
_CALLOUT_LABEL_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"^Case\s+stud(?:y|ies)\b", re.IGNORECASE), "case_study"),
    (re.compile(r"^Thinking\s+points?\b", re.IGNORECASE), "thinking_point"),
    (re.compile(r"^Key\s+ideas?\b", re.IGNORECASE), "key_ideas"),
    (re.compile(r"^Activit(?:y|ies)\b", re.IGNORECASE), "activity"),
    (re.compile(r"^Summary\b", re.IGNORECASE), "summary"),
]


def classify_callout_type(heading_text: str) -> Optional[str]:
    """Return the callout_type for a heading whose text matches a known
    boxed-aside label pattern, else None (an ordinary content heading).
    "Summary" is intentionally last and exact — it's common enough as a
    plain section title that it should only match once the more specific,
    numbered patterns above have already declined."""
    stripped = heading_text.strip()
    for pattern, callout_type in _CALLOUT_LABEL_PATTERNS:
        if pattern.match(stripped):
            return callout_type
    return None


def _prove_note_apparatus(doc: P2Document, markers: List[Tuple[int, int]]) -> None:
    """Turn the document's numbered note apparatus into ``P2Footnote`` bodies.

    N-1. Mathpix marks a note reference in the prose (``${ }^{12}$``) and prints
    the note bodies as an ordinary numbered run, which is indistinguishable *by
    shape* from a list: on the benchmark corpus one document's numbered runs are
    a four-item conceptual list, a thirty-six-item note apparatus and an
    eleven-item citation list, all identical line shapes. Classifying by
    typography would have made all three notes, or none.

    So the source has to prove it, and two facts do:

    1. **The run begins after the last marker.** Notes are printed after the
       prose that cites them; a list interleaved with that prose is not the
       apparatus. This is what rejects the four-item run, which sits *inside*
       the marker span.
    2. **The run's numbers cover every marker number.** The apparatus is what
       the markers point into, so a run missing any marker's number is not it.
       This is what rejects the eleven-item citation list, which covers only
       eleven of thirty-three markers.

    The first run satisfying both is the apparatus, and the **whole** run
    becomes note bodies — including a body no marker names. Three of the
    corpus' thirty-six bodies are in that state, because Mathpix dropped those
    superscripts from the prose; the body is still printed, still numbered, and
    still part of the proven apparatus. Emitting the referenced ones only would
    split one apparatus across two representations. A body without a reference
    is valid model state (``Footnote.anchor_offset`` is already Optional); a
    *reference* without a body is never invented, which is the asymmetry this
    function exists to keep.

    Fails closed everywhere else: no markers, no apparatus (an ordinary numbered
    list stays a list); markers but no covering run, and nothing is created —
    on the corpus that is one document with twenty-one markers whose bodies the
    package simply does not contain.
    """
    if not markers:
        return
    marker_numbers = {number for _, number, _, _ in markers}
    last_marker_line = max(line for line, _, _, _ in markers)
    # The first marker naming each number — a note carries one anchor, and a
    # number cited twice is one note referenced twice, not two notes.
    anchor_by_number = {}
    for line, number, text, offset in markers:
        anchor_by_number.setdefault(number, (line, text, offset))

    numbered = [
        block
        for block in doc.blocks
        if block.block_type is P2BlockType.LIST_ITEM
        and block.list_style is P2ListStyle.NUMBERED
        and block.list_number is not None
    ]
    runs: List[List[P2Block]] = []
    for block in numbered:
        if runs and block.list_number == runs[-1][-1].list_number + 1:
            runs[-1].append(block)
        else:
            runs.append([block])

    apparatus = next(
        (
            run
            for run in runs
            if run[0].source_line > last_marker_line
            and marker_numbers <= {block.list_number for block in run}
        ),
        None,
    )
    if apparatus is None:
        return

    bodies = set(id(block) for block in apparatus)
    doc.blocks = [block for block in doc.blocks if id(block) not in bodies]
    block_by_line = {
        block.source_line: block
        for block in doc.blocks
        if block.source_line is not None
    }
    for block in apparatus:
        anchor = anchor_by_number.get(block.list_number)
        if anchor is not None:
            anchor = _anchor_on_its_block(anchor, block_by_line.get(anchor[0]))
        doc.footnotes.append(
            P2Footnote(
                number=block.list_number,
                body=(block.text or "").strip(),
                anchor_line=None if anchor is None else anchor[0],
                anchor_text=None if anchor is None else anchor[1],
                anchor_offset=None if anchor is None else anchor[2],
            )
        )


def _anchor_on_its_block(
    anchor: Tuple[int, str, int], block: Optional[P2Block]
) -> Tuple[int, str, int]:
    """The same anchor, expressed against the block that line became.

    A marker is recorded against its source *line*, but what a projection
    renders is the *block* that line became — and the two are not always the
    same string. A numbered list item drops its ``"1. "`` marker prefix when
    it becomes a block, so an anchor kept against the line is contained in
    nothing that is ever rendered, and the two proven markers inside Bruner's
    four-item conceptual list resolved to nothing.

    The correction is a coordinate change, not a search: when the block's text
    is an exact *suffix* of the line, the prefix the block dropped is exactly
    ``len(line) - len(block text)`` characters, so the marker's offset within
    the block follows by subtraction. Nothing is looked for, nothing is
    normalised, and no marker becomes proven that was not proven already.

    Any other relationship - a block that merged several lines, a block whose
    text was rewritten - fails closed to the line anchor, which is what every
    caller had before. A shift that would push the offset negative fails the
    same way.
    """
    line, text, offset = anchor
    if block is None or block.source_line != line:
        return anchor
    block_text = block.text or ""
    if not block_text or block_text == text or not text.endswith(block_text):
        return anchor
    shift = len(text) - len(block_text)
    if offset < shift:
        return anchor
    return (line, block_text, offset - shift)


_MATH_SPAN_RE = re.compile(r"\$\$.+?\$\$|\$[^$\n]+?\$|\\\(.+?\\\)|\\\[.+?\\\]")


def _maths_body(span: str) -> str:
    """The content of a ``$..$`` / ``$$..$$`` / ``\\(..\\)`` / ``\\[..\\]`` span."""
    width = 2 if span.startswith(("$$", "\\(", "\\[")) else 1
    return span[width:-width].strip()


def _is_exponent_in_maths(line: str, marker: "re.Match[str]") -> bool:
    """True when ``marker`` is an exponent inside a maths span that holds more
    than the marker itself.

    ``${ }^{12}$`` and ``$^{12}$`` are the note-marker spellings and have the
    marker as their whole content. ``x^{2}`` inside ``$x^{2}=4$`` is an
    exponent: read as footnote 2, it made STEM prose "prove" a numbered list a
    note apparatus (docs/EQUATION_DESIGN.md)."""
    for span in _MATH_SPAN_RE.finditer(line):
        if span.start() <= marker.start() and marker.end() <= span.end():
            text = marker.group(0)
            return span.group(0) != text and _maths_body(span.group(0)) != text
    return False


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
    # N-1: every inline superscript, recorded where it was seen. Collected
    # before transform_inline_math() rewrites it, and used only after the
    # whole document is parsed — the apparatus cannot be proven from one line.
    markers: List[Tuple[int, int, str, int]] = []

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # ── Blank line ─────────────────────────────────────────────────
        if not stripped:
            i += 1
            continue

        for marker in _SUPERSCRIPT_MARKER_RE.finditer(stripped):
            if _is_exponent_in_maths(stripped, marker):
                continue
            # N-2: the marker's position in the line *as the block will store
            # it*. transform_inline_math() rewrites ``${ }^{12}$`` to ``[12]``,
            # so a raw offset would not survive; transforming the prefix gives
            # the offset in the transformed text exactly, because the rewrite
            # is a substitution over independent spans and the cut is always a
            # span boundary. Computed, never searched for.
            markers.append(
                (
                    i,
                    int(next(g for g in marker.groups() if g)),
                    transform_inline_math(stripped),
                    len(transform_inline_math(stripped[: marker.start()])),
                )
            )

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

        # ── Display maths: $$ ... $$ and \[ ... \] ──
        # Before this, all three lines of a delimited equation became three
        # PARAGRAPH blocks (docs/EQUATION_DESIGN.md F2).
        display = _collect_display(lines, i, n)
        if display is not None:
            body, next_i = display
            doc.blocks.append(
                P2Block(
                    block_type=P2BlockType.EQUATION,
                    text=body,
                    equation_env="display",
                    source_line=i,
                )
            )
            i = next_i
            continue

        # ── \begin{env} environment ────────────────────────────────────
        begin_m = _BEGIN_RE.match(stripped)
        if begin_m:
            env = begin_m.group(1)
            start_line = i
            env_lines, i = _collect_env(lines, i, n, env)
            if env.rstrip("*") in _EQUATION_ENVS:
                # Positioned at the environment's first line so it sorts
                # between the paragraphs around it.
                doc.blocks.append(_equation_block(env, env_lines, start_line))
                continue
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

        # ── Markdown heading: ## text ──────────────────────────────────
        # Mathpix writes headings of scanned books this way instead of as
        # \section{...}. Without this they became paragraphs reading "## 3".
        md_h = _MARKDOWN_HEADING_RE.match(stripped)
        if md_h:
            text = transform_inline_math(md_h.group(2).strip())
            doc.blocks.append(
                P2Block(
                    block_type=P2BlockType.HEADING,
                    heading=P2Heading(
                        level=len(md_h.group(1)),
                        text=text,
                        mmd_command="markdown",
                        callout_type=classify_callout_type(text),
                    ),
                    source_line=i,
                )
            )
            i += 1
            continue

        # ── Markdown image: ![alt](url) ────────────────────────────────
        md_img = _MARKDOWN_IMAGE_RE.match(stripped)
        if md_img:
            doc.blocks.append(
                P2Block(
                    block_type=P2BlockType.FIGURE,
                    figure=P2Figure(image_path=md_img.group(2), caption=md_img.group(1).strip() or None),
                    source_line=i,
                )
            )
            i += 1
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

    _prove_note_apparatus(doc, markers)
    _place_publisher_lines(doc)
    return doc


#: Display-maths environments whose body is kept as an EQUATION block.
#: Any other ``\begin`` still falls to ``_parse_env``.
_EQUATION_ENVS = {"equation", "align", "gather"}


def _equation_block(env: str, env_lines: List[str], source_line: int) -> P2Block:
    r"""One EQUATION block from a collected ``\begin{env}...\end{env}``."""
    inner = env_lines[1:-1] if len(env_lines) >= 2 else []
    return P2Block(
        block_type=P2BlockType.EQUATION,
        text="\n".join(line.strip() for line in inner).strip(),
        equation_env=env,
        source_line=source_line,
    )


def _collect_display(lines: List[str], i: int, n: int) -> Optional[Tuple[str, int]]:
    r"""Body and next line index of a ``$$`` / ``\[`` display block starting
    at ``lines[i]``, or None when the line is not one.

    A block is only taken when it is closed and nothing trails the closing
    delimiter; anything else stays ordinary paragraph text, so no content is
    dropped by guessing (``$`` is ambiguous with currency)."""
    first = lines[i].strip()
    for opener, closer in (("$$", "$$"), (r"\[", r"\]")):
        if not first.startswith(opener):
            continue
        rest = first[len(opener):]
        if closer in rest:
            body, tail = rest.split(closer, 1)
            return (body.strip(), i + 1) if body.strip() and not tail.strip() else None
        parts = [rest.strip()] if rest.strip() else []
        j = i + 1
        while j < n:
            current = lines[j].strip()
            if closer in current:
                head, tail = current.split(closer, 1)
                if tail.strip():
                    return None
                if head.strip():
                    parts.append(head.strip())
                body = "\n".join(parts).strip()
                return (body, j + 1) if body else None
            parts.append(current)
            j += 1
        return None
    return None


# How far (in blocks) a printed label may sit from the figure or table it names.
_LABEL_REACH = 2


def _place_publisher_lines(doc: P2Document) -> None:
    """Give every printed label ("FIGURE 3.1 CONCEPT MAP ...", "TABLE 2 ...")
    a home, so none is lost.

    PUBLISHER_LINE blocks were recognised and then consumed by nothing: all
    four of O'Leary's figure captions vanished from the output. A FIGURE/FIG
    label becomes the caption of the figure beside it, a TABLE label the
    caption of the table beside it (when that caption is empty); every other
    label - and one with nothing to attach to - stays in the text as the
    paragraph it was printed as.
    """
    blocks = doc.blocks
    for index, block in enumerate(blocks):
        if block.block_type != P2BlockType.PUBLISHER_LINE:
            continue
        label = (block.text or "").strip()
        kind = label.split()[0].upper().rstrip(".") if label else ""
        target_type = {"FIGURE": P2BlockType.FIGURE, "FIG": P2BlockType.FIGURE, "TABLE": P2BlockType.TABLE}.get(kind)
        neighbour = None
        if target_type is not None:
            for distance in range(1, _LABEL_REACH + 1):
                for candidate in (index - distance, index + distance):
                    if 0 <= candidate < len(blocks) and blocks[candidate].block_type == target_type:
                        neighbour = blocks[candidate]
                        break
                if neighbour is not None:
                    break
        holder = None
        if neighbour is not None:
            holder = neighbour.figure if target_type == P2BlockType.FIGURE else neighbour.table
        if holder is not None and not holder.caption:
            holder.caption = label
            block.text = None  # now the caption; dropped below
        else:
            block.block_type = P2BlockType.PARAGRAPH
    doc.blocks = [b for b in blocks if not (b.block_type == P2BlockType.PUBLISHER_LINE and b.text is None)]


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
                    callout_type=classify_callout_type(text),
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
