"""LaTeX -> native Word equation (OMML), verified by a round trip
(docs/EQUATION_DESIGN.md §2).

Conversion is pandoc (texmath) as a subprocess, one batch per document. Two
things are added because texmath alone is not enough for the checklist:

* Eq 3 - ``\\sin``, ``\\cos`` ... must come from the equation tool, which in
  OMML means ``m:func``. texmath emits plain upright runs, so they are wrapped
  here.
* Eq 6 - an equation must look like the source. Every converted equation is
  written into a scratch .docx, read back by pandoc as LaTeX and compared,
  normalised, with the LaTeX it came from. A mismatch is reported; the caller
  flags that equation for a human and still ships the OMML it has.

Failure is always loud: an unknown macro makes texmath render raw TeX text, and
that is reported as a failed conversion, never passed on as maths.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from docx import Document as DocxDocument
from lxml import etree
from loguru import logger

from src.equations import latex as tex

_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS = {"m": _M, "w": _W}
_TIMEOUT_SECONDS = 120
# pandoc writes a paragraph holding a bare ``m:oMath`` as ``\(...\)`` and an
# ``m:oMathPara`` as ``\[...\]``; accept both.
_MATH_RE = re.compile(r"\\\[(?P<display>.*?)\\\]|\\\((?P<inline>.*?)\\\)", re.S)
_OPERATOR_TEXT = set("+-−=<>≤≥≠≈±×÷·,;:)")


@dataclass(frozen=True)
class Conversion:
    """One equation's outcome. ``omml`` is an ``m:oMath`` element as XML text."""

    omml: Optional[str]
    reason: Optional[str] = None
    verified: bool = False


def pandoc_path() -> Optional[str]:
    """The pandoc executable: the ``pypandoc-binary`` copy when installed, else PATH."""
    try:
        import pypandoc  # type: ignore

        return pypandoc.get_pandoc_path()
    except (ImportError, OSError):
        return shutil.which("pandoc")


def _m(tag: str) -> str:
    return f"{{{_M}}}{tag}"


def _run_pandoc(args: List[str], source: Optional[str] = None) -> subprocess.CompletedProcess:
    executable = pandoc_path()
    return subprocess.run(
        [executable, *args],
        input=source,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )


# ── LaTeX -> OMML ──────────────────────────────────────────────────────
def _body_paragraphs(docx_path: Path) -> List[etree._Element]:
    with zipfile.ZipFile(docx_path) as package:
        root = etree.fromstring(package.read("word/document.xml"))
    body = root.find(f"{{{_W}}}body")
    return [child for child in body if child.tag == f"{{{_W}}}p"]


def _omml_of(paragraph: etree._Element) -> Optional[etree._Element]:
    found = paragraph.find(".//m:oMath", _NS)
    return found


def _convert_with_pandoc(latexes: Sequence[str]) -> List[Optional[etree._Element]]:
    source = "\n\n".join(f"\\[{latex}\\]" for latex in latexes) + "\n"
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "equations.docx"
        result = _run_pandoc(["-f", "latex", "-t", "docx", "-o", str(target)], source)
        if result.returncode != 0 or not target.exists():
            raise RuntimeError(result.stderr.strip() or "pandoc failed")
        paragraphs = _body_paragraphs(target)
    if len(paragraphs) != len(latexes):
        raise RuntimeError(f"pandoc returned {len(paragraphs)} paragraphs for {len(latexes)} equations")
    return [_omml_of(paragraph) for paragraph in paragraphs]


# ── Eq 3: m:func ───────────────────────────────────────────────────────
def _run_text(element: etree._Element) -> str:
    return "".join(element.itertext())


def _is_function_run(element: etree._Element) -> bool:
    return element.tag == _m("r") and _run_text(element).strip() in tex.FUNCTIONS


def _function_name_element(element: etree._Element) -> bool:
    """A bare function run, or a script whose base is one (``sin^{-1}``)."""
    if _is_function_run(element):
        return True
    if element.tag in (_m("sSup"), _m("sSub"), _m("sSubSup")):
        base = element.find("m:e", _NS)
        return base is not None and len(base) == 1 and _is_function_run(base[0])
    return False


def _starts_with_operator(element: etree._Element) -> bool:
    text = _run_text(element).strip()
    return element.tag == _m("r") and bool(text) and text[0] in _OPERATOR_TEXT


def _wrap_one_function(root: etree._Element) -> bool:
    """Wrap the first function name that has an argument; False when none is left."""
    for parent in root.iter():
        children = list(parent)
        for index, child in enumerate(children[:-1]):
            argument = children[index + 1]
            if not _function_name_element(child):
                continue
            if _starts_with_operator(argument) or argument.tag == _m("func"):
                continue
            func = etree.Element(_m("func"))
            name = etree.SubElement(func, _m("fName"))
            parent.replace(child, func)
            name.append(child)
            parent.remove(argument)
            etree.SubElement(func, _m("e")).append(argument)
            return True
    return False


def _wrap_functions(root: etree._Element) -> None:
    """Eq 3: every function name followed by its argument becomes ``m:func``."""
    while _wrap_one_function(root):
        pass


# ── Round trip ─────────────────────────────────────────────────────────
def _scratch_docx(elements: Sequence[etree._Element], path: Path) -> None:
    document = DocxDocument()
    for element in elements:
        paragraph = document.add_paragraph()
        paragraph._p.append(etree.fromstring(etree.tostring(element)))
    document.save(str(path))


def round_trip(latexes: Sequence[str], omml_xml: Sequence[Optional[str]]) -> List[bool]:
    """Whether each OMML reads back, through pandoc, as the LaTeX it came from."""
    outcomes = [False] * len(latexes)
    indexes = [i for i, xml in enumerate(omml_xml) if xml]
    if not indexes:
        return outcomes
    elements = [etree.fromstring(omml_xml[i].encode("utf-8")) for i in indexes]
    with tempfile.TemporaryDirectory() as folder:
        scratch = Path(folder) / "roundtrip.docx"
        _scratch_docx(elements, scratch)
        result = _run_pandoc(["-f", "docx", "-t", "latex", str(scratch)])
    if result.returncode != 0:
        logger.warning("pandoc round trip failed: {}", result.stderr.strip())
        return outcomes
    read_back = [
        match.group("display") if match.group("display") is not None else match.group("inline")
        for match in _MATH_RE.finditer(result.stdout)
    ]
    if len(read_back) != len(indexes):
        logger.warning("round trip returned {} equations for {}", len(read_back), len(indexes))
        return outcomes
    for index, back in zip(indexes, read_back):
        outcomes[index] = tex.normalise(latexes[index]) == tex.normalise(back)
    return outcomes


# ── Public API ─────────────────────────────────────────────────────────
def convert_batch(latexes: Sequence[str]) -> List[Conversion]:
    """Convert every equation; one result per input, in order, never raising."""
    if not latexes:
        return []
    if pandoc_path() is None:
        return [Conversion(None, "pandoc is not installed") for _ in latexes]
    try:
        elements = _convert_with_pandoc(latexes)
    except (RuntimeError, OSError, subprocess.SubprocessError, etree.XMLSyntaxError) as error:
        logger.warning("equation conversion failed: {}", error)
        return [Conversion(None, f"conversion failed: {error}") for _ in latexes]
    for element in elements:
        if element is not None:
            _wrap_functions(element)
    xml = [None if e is None else etree.tostring(e, encoding="unicode") for e in elements]
    verified = round_trip(list(latexes), xml)
    return [
        Conversion(None, "pandoc could not convert this expression")
        if text is None
        else Conversion(text, None if ok else "converted equation differs from the source", ok)
        for text, ok in zip(xml, verified)
    ]
