"""Gold answers from PDFs that people already made accessible.

A well-tagged PDF carries human decisions in its structure tree: which lines
are headings and at what level, what each figure's alt text says, and which
table cells are headers. Reading those (pypdfium2, already installed), then
stripping the tags and running RAWRS on the bare PDF, measures RAWRS against
people without a reviewer (docs/PRODUCT_PROGRESS.md, Task 5).

Only files worth it are kept (``worth_it``): they must pass veraPDF PDF/UA-1
and have real headings, and any alt text must be real words, not filler.
"""
from __future__ import annotations

import ctypes
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pypdfium2 as pdfium
import pypdfium2.raw as raw

MIN_HEADINGS = 3
MIN_ALT_WORDS = 3
FILLER_ALT = re.compile(r"^(image|picture|figure|graphic|photo|logo|chart|img|untitled)?[\s\d_.-]*(\.(png|jpe?g|gif|tiff?))?$", re.I)
STOP = set("the and for are with that this from into over under its their than then them they these those has have was "
           "were been being which while what when where who whom why how not but all any each one two three also can may "
           "such per via of to in on at by an or as is be it a".split())


def words(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def content_words(text: str) -> Set[str]:
    return {w for w in words(text) if len(w) > 2 and w not in STOP}


def _wide(function, handle) -> str:
    """A UTF-16 string out of one of pdfium's two-call getters."""
    size = function(handle, None, 0)
    if size <= 2:
        return ""
    buffer = ctypes.create_string_buffer(size)
    function(handle, buffer, size)
    return buffer.raw[:size].decode("utf-16-le", "replace").rstrip("\x00").strip()


def _mcid_of(obj) -> int:
    """The innermost MCID on a page object's marked-content stack, or -1."""
    value = ctypes.c_int()
    for i in reversed(range(raw.FPDFPageObj_CountMarks(obj))):
        if raw.FPDFPageObjMark_GetParamIntValue(raw.FPDFPageObj_GetMark(obj, i), b"MCID", ctypes.byref(value)):
            return value.value
    return -1


def _texts_by_mcid(page: pdfium.PdfPage) -> Dict[int, str]:
    textpage = page.get_textpage()
    found: Dict[int, List[str]] = {}
    for obj in page.get_objects(max_depth=4):
        mcid = _mcid_of(obj.raw)
        if mcid < 0 or obj.type != raw.FPDF_PAGEOBJ_TEXT:
            continue
        size = raw.FPDFTextObj_GetText(obj.raw, textpage.raw, None, 0)
        buffer = ctypes.create_string_buffer(size)
        raw.FPDFTextObj_GetText(obj.raw, textpage.raw, ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ushort)), size)
        found.setdefault(mcid, []).append(buffer.raw[:size].decode("utf-16-le", "replace").rstrip("\x00"))
    textpage.close()
    return {mcid: " ".join("".join(parts).split()) for mcid, parts in found.items()}


def _mcids(element) -> List[int]:
    ids = [raw.FPDF_StructElement_GetMarkedContentIdAtIndex(element, i)
           for i in range(raw.FPDF_StructElement_GetMarkedContentIdCount(element))]
    for i in range(raw.FPDF_StructElement_CountChildren(element)):
        child = raw.FPDF_StructElement_GetChildAtIndex(element, i)
        if child:
            ids += _mcids(child)
    return [i for i in ids if i >= 0]


def _walk(element, page_number: int, texts: Dict[int, str], gold: Dict[str, Any]) -> None:
    kind = _wide(raw.FPDF_StructElement_GetType, element)
    if re.fullmatch(r"H[1-6]", kind):
        text = " ".join(texts.get(m, "") for m in _mcids(element)).strip()
        if text:
            gold["headings"].append({"level": int(kind[1]), "text": text, "page": page_number})
        return
    if kind == "Figure":
        gold["figures"].append({"alt": _wide(raw.FPDF_StructElement_GetAltText, element), "page": page_number})
        return
    if kind == "Table":
        gold["tables"] += 1
    if kind == "TH":
        gold["header_cells"] += 1
    for i in range(raw.FPDF_StructElement_CountChildren(element)):
        child = raw.FPDF_StructElement_GetChildAtIndex(element, i)
        if child:
            _walk(child, page_number, texts, gold)


def read_gold(pdf_path: Path) -> Dict[str, Any]:
    """Headings (level, text, page), figures (alt), tables and header cells from the tags.

    pdfium gives the tree per page, so an element spanning pages is read once
    per page; headings and figures almost never span pages."""
    gold: Dict[str, Any] = {"headings": [], "figures": [], "tables": 0, "header_cells": 0}
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        for number, page in enumerate(pdf, start=1):
            tree = raw.FPDF_StructTree_GetForPage(page.raw)
            if tree:
                texts = _texts_by_mcid(page)
                for i in range(raw.FPDF_StructTree_CountChildren(tree)):
                    child = raw.FPDF_StructTree_GetChildAtIndex(tree, i)
                    if child:
                        _walk(child, number, texts, gold)
                raw.FPDF_StructTree_Close(tree)
            page.close()
    finally:
        pdf.close()
    return gold


def real_alt(alt: str) -> bool:
    return len(words(alt)) >= MIN_ALT_WORDS and not FILLER_ALT.match(alt.strip())


def worth_it(gold: Dict[str, Any], pdfua1_compliant: Optional[bool]) -> List[str]:
    """Reasons to reject a file as gold; empty means keep it."""
    reasons = []
    if pdfua1_compliant is not True:
        reasons.append("does not pass PDF/UA-1")
    if len(gold["headings"]) < MIN_HEADINGS:
        reasons.append(f"fewer than {MIN_HEADINGS} tagged headings")
    filler = [f for f in gold["figures"] if f["alt"] and not real_alt(f["alt"])]
    if filler:
        reasons.append(f"{len(filler)} figure(s) with filler alt text")
    return reasons


def strip_tags(source: Path, target: Path) -> None:
    """The same pages with no structure tree, so RAWRS sees an untagged PDF."""
    import fitz  # PyMuPDF

    with fitz.open(str(source)) as doc:
        catalog = doc.pdf_catalog()
        for key in ("StructTreeRoot", "MarkInfo", "Lang"):
            doc.xref_set_key(catalog, key, "null")
        doc.set_metadata({**(doc.metadata or {}), "title": ""})
        doc.save(str(target), garbage=3)


def docx_headings(path: Path) -> List[tuple]:
    """(level, text) of the delivered DOCX's headings; Heading 6 is RAWRS's page marker."""
    import docx

    styled = ((q.style.name, q.text) for q in docx.Document(str(path)).paragraphs)
    return [(int(name[-1]), text) for name, text in styled if re.fullmatch(r"Heading [1-5]", name) and text.strip()]


def score(gold: Dict[str, Any], headings: List[tuple], alts: List[str]) -> Dict[str, Any]:
    """RAWRS's headings and alt texts against the gold.

    Headings: exact normalised text match, then level. Alt text: content-word
    overlap pooled per document, because which RAWRS image is which gold
    figure is not known (ponytail: per-figure matching by page and position
    is the upgrade if the pooled number proves too coarse)."""
    from src.benchmark.differ import _align_by_text, _pr

    # Letters and digits only: "C H A P T E R 5" and "Chapter 5" are the same heading.
    def key(text: str) -> str:
        return "".join(words(text))

    gold_texts = [key(h["text"]) for h in gold["headings"]]
    matched, per = _align_by_text(gold_texts, [key(text) for _, text in headings])
    level_of = {key(text): level for level, text in headings}
    gold_level = {key(h["text"]): h["level"] for h in gold["headings"]}
    same_level = sum(1 for p in per if p["status"] == "matched"
                     and level_of[p["rawrs"]] == gold_level[p["benchmark"]])
    # Convention-free: one H1 per document or one per section are both valid,
    # so also ask whether each next heading goes deeper, stays or comes back
    # up the same way the person tagged it.
    pairs = [(gold_level[p["benchmark"]], level_of[p["rawrs"]]) for p in per if p["status"] == "matched"]
    steps = [((g2 > g1) - (g2 < g1), (r2 > r1) - (r2 < r1)) for (g1, r1), (g2, r2) in zip(pairs, pairs[1:])]
    gold_alts = [f["alt"] for f in gold["figures"] if real_alt(f["alt"])]
    human = set().union(*map(content_words, gold_alts)) if gold_alts else set()
    machine = set().union(*map(content_words, alts)) if alts else set()
    return {
        "headings": {**_pr(matched, len(gold_texts), len(headings)), "gold": len(gold_texts), "rawrs": len(headings),
                     "matched": matched, "level_accuracy": round(same_level / matched, 4) if matched else None,
                     "step_agreement": round(sum(a == b for a, b in steps) / len(steps), 4) if steps else None,
                     "steps": len(steps)},
        "alt_text": {"gold_figures": len(gold_alts), "rawrs_alts": len(alts),
                     "gold_mean_words": round(sum(len(words(a)) for a in gold_alts) / len(gold_alts), 1) if gold_alts else None,
                     "rawrs_mean_words": round(sum(len(words(a)) for a in alts) / len(alts), 1) if alts else None,
                     "word_recall": round(len(human & machine) / len(human), 4) if human else None,
                     "word_precision": round(len(human & machine) / len(machine), 4) if machine else None},
        "tables": {"gold": gold["tables"], "gold_header_cells": gold["header_cells"]},
    }
