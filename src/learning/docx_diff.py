"""What a remediator changed in Word after RAWRS exported the DOCX.

The remediator downloads RAWRS's DOCX, finishes it in Word, and uploads the
result back. This module compares the two files and classifies every
difference into a stable category - heading level changed, alt text
rewritten, table header row added, text edited - so the changes can be counted
across documents and turned into "what RAWRS still gets wrong".

Built from what the codebase and the standard library already have, not from
scratch: the DOCX is read with the checklist auditor's own probes
(src/validation/checklist_audit.py - the body walk, heading levels, the
alt-text and decorative-image reads that audit every export), and alignment is
``difflib.SequenceMatcher``. No third-party diff library: the maintained ones
are AGPL (scitex-msword, jubarte-redlines) or commercial (Aspose).

Alignment works on a sequence of *units* - one per heading, paragraph, list
item, caption, image and table - keyed by case- and space-insensitive text, so
a paragraph promoted to a heading, or retyped in Title Case, still lines up
with the paragraph it was and is reported as exactly that change.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from docx import Document as open_docx
from docx.oxml.ns import qn

from src.validation.checklist_audit import (
    PLACEHOLDER_ALT_MARK,
    _A16_DECORATIVE,
    _WP,
    _body_blocks,
    _style_name,
    _text,
)

TEXT_KINDS = frozenset({"title", "heading", "paragraph", "list_item", "caption"})
PAIR_SIMILARITY = 0.6  # below this a replaced unit is a removal plus an addition
# ponytail: pairing inside one replaced run is O(n*m) ratio calls; a run larger
# than this (a whole chapter rewritten) is reported as removed + added instead.
PAIRING_BUDGET = 40_000
MAX_VALUE_CHARS = 500
MAX_WORD_CHANGES = 20

_OBJECT_TYPE = {
    "title": "heading",
    "heading": "heading",
    "paragraph": "paragraph",
    "list_item": "list",
    "caption": "caption",
    "image": "figure",
    "table": "table",
}
_SPACE = re.compile(r"\s+")
_METADATA_FIELDS = ("title", "subject", "author", "keywords", "language")


@dataclass(frozen=True)
class Unit:
    kind: str
    text: str = ""
    style: str = ""
    level: Optional[int] = None
    alt: str = ""
    decorative: bool = False
    header_rows: int = 0
    shape: Tuple[int, int] = (0, 0)

    @property
    def key(self) -> str:
        if self.kind in TEXT_KINDS:
            return _collapse(self.text).lower()
        return "\0" + self.kind  # images and tables align by position among their own kind


def _collapse(text: str) -> str:
    return _SPACE.sub(" ", text).strip()


def _clip(text: str) -> str:
    return text if len(text) <= MAX_VALUE_CHARS else text[: MAX_VALUE_CHARS - 1] + "…"


# --- reading ---------------------------------------------------------------------


class _StyleNames:
    """paragraph -> style name, resolved from a table built once per document.

    Same answer as checklist_audit._style_name (python-docx's ``p.style.name``),
    which rescans every style on each call - 3.4 of 3.6 s of a diff on a real
    161-unit export. Falls back to it for anything the table cannot answer.
    """

    def __init__(self, doc) -> None:
        self._by_id = {s.style_id: s.name for s in doc.styles}
        default = doc.styles.default(1)  # WD_STYLE_TYPE.PARAGRAPH
        self._default = default.name if default is not None else "Normal"

    def __call__(self, paragraph) -> str:
        p_pr = paragraph._p.pPr
        style_id = p_pr.pStyle.val if p_pr is not None and p_pr.pStyle is not None else None
        if style_id is None:
            return self._default
        return self._by_id.get(style_id) or _style_name(paragraph)


_HEADING_STYLE = re.compile(r"Heading (\d)$")  # the rule checklist_audit._heading_level applies


def _paragraph_kind(paragraph, style: str) -> Tuple[str, Optional[int]]:
    match = _HEADING_STYLE.match(style)
    if match:
        return "heading", int(match.group(1))
    if style == "Title":
        return "title", None
    if style == "Caption":
        return "caption", None
    p_pr = paragraph._p.pPr
    if style.startswith("List") or (p_pr is not None and p_pr.find(qn("w:numPr")) is not None):
        return "list_item", None
    return "paragraph", None


def _image_units(paragraph) -> List[Unit]:
    units = []
    drawings = paragraph._p.findall(f".//{{{_WP}}}inline") + paragraph._p.findall(f".//{{{_WP}}}anchor")
    for drawing in drawings:
        doc_pr = drawing.find(f"{{{_WP}}}docPr")
        descr = (doc_pr.get("descr") or "").strip() if doc_pr is not None else ""
        decorative = doc_pr is not None and any(
            el.tag == _A16_DECORATIVE and el.get("val") in ("1", "true") for el in doc_pr.iter()
        )
        units.append(Unit(kind="image", alt=descr, decorative=decorative))
    return units


def _table_unit(table) -> Unit:
    rows = table._tbl.findall(qn("w:tr"))
    header_rows = sum(
        1 for row in rows if row.trPr is not None and row.trPr.find(qn("w:tblHeader")) is not None
    )
    cells_text = [
        " | ".join(_collapse("".join(t.text or "" for t in cell.iter(qn("w:t")))) for cell in row.findall(qn("w:tc")))
        for row in rows
    ]
    columns = max((len(row.findall(qn("w:tc"))) for row in rows), default=0)
    return Unit(kind="table", text="\n".join(cells_text), header_rows=header_rows, shape=(len(rows), columns))


def read_units(doc) -> List[Unit]:
    style_of = _StyleNames(doc)
    units: List[Unit] = []
    for block in _body_blocks(doc):
        if block.kind == "table":
            units.append(_table_unit(block.table))
            continue
        paragraph = block.paragraph
        units.extend(_image_units(paragraph))
        text = _collapse(_text(paragraph))
        if text:
            style = style_of(paragraph)
            kind, level = _paragraph_kind(paragraph, style)
            units.append(Unit(kind=kind, text=text, style=style, level=level))
    return units


def read_metadata(doc) -> Dict[str, str]:
    props = doc.core_properties
    metadata = {name: (getattr(props, name, None) or "").strip() for name in _METADATA_FIELDS}
    defaults = doc.styles.element.find(qn("w:docDefaults"))
    lang = defaults.find(f".//{qn('w:lang')}") if defaults is not None else None
    metadata["default_language"] = (lang.get(qn("w:val")) or "") if lang is not None else ""
    return metadata


# --- comparing -------------------------------------------------------------------


def _edit(category: str, unit: Unit, before: str, after: str, i: Optional[int], j: Optional[int], **extra) -> Dict:
    return {
        "category": category,
        "object_type": _OBJECT_TYPE[unit.kind],
        "before": _clip(before),
        "after": _clip(after),
        "position_before": i,
        "position_after": j,
        **extra,
    }


def _label(unit: Unit) -> str:
    if unit.kind == "heading":
        return f"H{unit.level}"
    return unit.style or unit.kind


def word_changes(before: str, after: str) -> List[Dict[str, str]]:
    """The replaced, deleted and inserted word runs between two texts."""
    a, b = before.split(), after.split()
    changes = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            changes.append({"op": tag, "from": " ".join(a[i1:i2]), "to": " ".join(b[j1:j2])})
            if len(changes) == MAX_WORD_CHANGES:
                break
    return changes


def _compare_text(u: Unit, v: Unit, i: int, j: int) -> List[Dict]:
    edits = []
    if u.kind == "heading" and v.kind == "heading":
        if u.level != v.level:
            edits.append(_edit("HEADING_LEVEL_CHANGED", u, _label(u), _label(v), i, j, text=_clip(v.text)))
    elif v.kind in ("heading", "title") and u.kind not in ("heading", "title"):
        edits.append(_edit("PROMOTED_TO_HEADING", v, _label(u), _label(v), i, j, text=_clip(v.text)))
    elif u.kind in ("heading", "title") and v.kind not in ("heading", "title"):
        edits.append(_edit("DEMOTED_FROM_HEADING", u, _label(u), _label(v), i, j, text=_clip(v.text)))
    elif u.kind != v.kind or u.style != v.style:
        edits.append(_edit("STYLE_CHANGED", v, _label(u), _label(v), i, j, text=_clip(v.text)))
    if u.text != v.text:
        edits.append(
            _edit(
                "TEXT_EDITED",
                v,
                u.text,
                v.text,
                i,
                j,
                similarity=round(SequenceMatcher(None, u.text, v.text, autojunk=False).ratio(), 3),
                word_changes=word_changes(u.text, v.text),
            )
        )
    return edits


def _is_placeholder(alt: str) -> bool:
    return not alt or PLACEHOLDER_ALT_MARK in alt


def _compare_image(u: Unit, v: Unit, i: int, j: int) -> List[Dict]:
    if u.decorative != v.decorative:
        category = "MARKED_DECORATIVE" if v.decorative else "UNMARKED_DECORATIVE"
        return [_edit(category, v, u.alt, v.alt, i, j)]
    if u.alt != v.alt and not v.decorative:
        category = "ALT_TEXT_WRITTEN" if _is_placeholder(u.alt) else "ALT_TEXT_REWRITTEN"
        return [_edit(category, v, u.alt, v.alt, i, j)]
    return []


def _compare_table(u: Unit, v: Unit, i: int, j: int) -> List[Dict]:
    edits = []
    if u.header_rows != v.header_rows:
        edits.append(_edit("TABLE_HEADER_CHANGED", v, f"{u.header_rows} header rows", f"{v.header_rows} header rows", i, j))
    if u.shape != v.shape:
        edits.append(_edit("TABLE_STRUCTURE_CHANGED", v, "%dx%d" % u.shape, "%dx%d" % v.shape, i, j))
    if u.text != v.text:
        edits.append(_edit("TABLE_CONTENT_EDITED", v, u.text, v.text, i, j))
    return edits


def compare_units(u: Unit, v: Unit, i: int, j: int) -> List[Dict]:
    if u.kind in TEXT_KINDS:
        return _compare_text(u, v, i, j)
    if u.kind == "image":
        return _compare_image(u, v, i, j)
    return _compare_table(u, v, i, j)


def _added(unit: Unit, j: int) -> Dict:
    category = {"image": "IMAGE_ADDED", "table": "TABLE_ADDED"}.get(unit.kind, "CONTENT_ADDED")
    return _edit(category, unit, "", unit.alt if unit.kind == "image" else unit.text, None, j, kind=unit.kind)


def _removed(unit: Unit, i: int) -> Dict:
    category = {"image": "IMAGE_REMOVED", "table": "TABLE_REMOVED"}.get(unit.kind, "CONTENT_REMOVED")
    return _edit(category, unit, unit.alt if unit.kind == "image" else unit.text, "", i, None, kind=unit.kind)


def _similarity(u: Unit, v: Unit) -> float:
    if (u.kind in TEXT_KINDS) != (v.kind in TEXT_KINDS) or (u.kind not in TEXT_KINDS and u.kind != v.kind):
        return 0.0
    if u.kind not in TEXT_KINDS:
        return 1.0
    matcher = SequenceMatcher(None, u.key, v.key, autojunk=False)
    if matcher.real_quick_ratio() < PAIR_SIMILARITY or matcher.quick_ratio() < PAIR_SIMILARITY:
        return 0.0
    return matcher.ratio()


def _diff_replaced(a: List[Unit], b: List[Unit], i0: int, j0: int) -> Tuple[List[Dict], int]:
    """Pair each unit of a replaced run with its most similar successor, in order."""
    if len(a) * len(b) > PAIRING_BUDGET:
        return [_removed(u, i0 + k) for k, u in enumerate(a)] + [_added(v, j0 + k) for k, v in enumerate(b)], 0
    edits: List[Dict] = []
    kept = 0
    next_j = 0
    for k, u in enumerate(a):
        scored = [(_similarity(u, b[jj]), jj) for jj in range(next_j, len(b))]
        best_score, best = max(scored, default=(0.0, -1))
        if best_score < PAIR_SIMILARITY:
            edits.append(_removed(u, i0 + k))
            continue
        edits.extend(_added(b[jj], j0 + jj) for jj in range(next_j, best))
        changes = compare_units(u, b[best], i0 + k, j0 + best)
        kept += not changes
        edits.extend(changes)
        next_j = best + 1
    edits.extend(_added(b[jj], j0 + jj) for jj in range(next_j, len(b)))
    return edits, kept


def diff_units(before: List[Unit], after: List[Unit]) -> Tuple[List[Dict], int]:
    """(edits, units kept unchanged) turning ``before`` into ``after``."""
    matcher = SequenceMatcher(None, [u.key for u in before], [u.key for u in after], autojunk=False)
    edits: List[Dict] = []
    kept = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                changes = compare_units(before[i], after[j], i, j)
                kept += not changes
                edits.extend(changes)
        elif tag == "delete":
            edits.extend(_removed(before[i], i) for i in range(i1, i2))
        elif tag == "insert":
            edits.extend(_added(after[j], j) for j in range(j1, j2))
        else:
            replaced, replaced_kept = _diff_replaced(before[i1:i2], after[j1:j2], i1, j1)
            edits.extend(replaced)
            kept += replaced_kept
    return edits, kept


def diff_metadata(before: Dict[str, str], after: Dict[str, str]) -> List[Dict]:
    return [
        {"category": "METADATA_CHANGED", "object_type": "metadata", "field": name,
         "before": before.get(name, ""), "after": after.get(name, ""),
         "position_before": None, "position_after": None}
        for name in sorted(set(before) | set(after))
        if before.get(name, "") != after.get(name, "")
    ]


def diff_docx(exported: Union[str, Path], final: Union[str, Path]) -> Dict:
    """Every change between RAWRS's export and the remediator's final DOCX."""
    before_doc, after_doc = open_docx(str(exported)), open_docx(str(final))
    before, after = read_units(before_doc), read_units(after_doc)
    edits, kept = diff_units(before, after)
    metadata_before, metadata_after = read_metadata(before_doc), read_metadata(after_doc)
    edits.extend(diff_metadata(metadata_before, metadata_after))
    return {
        "summary": {
            "units_exported": len(before),
            "units_final": len(after),
            "units_kept": kept,
            "kept_share": round(kept / len(before), 4) if before else None,
            "edits": len(edits),
            "by_category": dict(Counter(edit["category"] for edit in edits).most_common()),
        },
        "edits": edits,
        "metadata_exported": metadata_before,
        "metadata_final": metadata_after,
    }
