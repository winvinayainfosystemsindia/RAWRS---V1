r"""Equations in the DOCX projection (docs/EQUATION_DESIGN.md §2, §4).

One ``EquationRender`` per document. It converts every non-plain equation in a
single pandoc batch up front, downgrades to FLAGGED any equation whose
conversion failed or did not survive the round trip (the equation is kept as
text, never dropped), and then renders:

* display equations as a native Word equation, centred when unnumbered, or
  ``tab + equation + tab + (n)`` with a right-aligned number *outside* the
  equation box when numbered (Eq 4), the number bookmarked so ``\ref`` /
  ``\eqref`` in the prose can point at it;
* PLAIN equations as ordinary text (Eq 7);
* inline equations as native equations inside their sentence;
* a reviewer's description as a normal paragraph after the equation.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Sequence, Tuple, Union

from docx.enum.text import WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from loguru import logger
from lxml import etree

from src.equations import omml
from src.models.equation import Equation, EquationStatus

_INLINE_MATH_RE = re.compile(r"(?<![\\$])\$(?!\s)([^$\n]+?)(?<!\s)\$(?!\d)")
_REFERENCE_RE = re.compile(r"\\(?:eq)?ref\{([^}]+)\}")
_BOOKMARK_SANITIZE_RE = re.compile(r"[^A-Za-z0-9]")
_FIRST_BOOKMARK_ID = 10_000

AddText = Callable[[Paragraph, str], None]
Piece = Tuple[str, Union[str, Equation]]


class EquationRender:
    def __init__(self, document, add_text: AddText) -> None:
        self._add_text = add_text
        self._equations = list(document.equations)
        self.by_id: Dict[str, Equation] = {e.id: e for e in self._equations if e.id}
        self._by_label: Dict[str, Equation] = {
            e.label: e for e in self._equations if e.display and e.label and e.number
        }
        self._inline_by_latex: Dict[str, Equation] = {
            e.latex: e
            for e in self._equations
            if not e.display and e.status is not EquationStatus.PLAIN
        }
        self._conversions: Dict[str, omml.Conversion] = {}
        self._bookmark_ids = iter(range(_FIRST_BOOKMARK_ID, 10**9))
        self._convert()

    # ── conversion ─────────────────────────────────────────────────────
    def _convert(self) -> None:
        targets = [e for e in self._equations if e.status is not EquationStatus.PLAIN]
        for equation, result in zip(targets, omml.convert_batch([e.latex for e in targets])):
            self._conversions[equation.id] = result
            if result.omml is not None and result.verified:
                continue
            equation.status = EquationStatus.FLAGGED
            reason = result.reason or "conversion failed"
            if reason not in equation.flag_reasons:
                equation.flag_reasons.append(reason)
            logger.info("Equation {} flagged: {}", equation.id, reason)

    def _omml(self, equation: Equation):
        result = self._conversions.get(equation.id)
        return None if result is None or result.omml is None else etree.fromstring(result.omml.encode("utf-8"))

    # ── display ────────────────────────────────────────────────────────
    def display(self, docx_document, equation_id: str) -> bool:
        """Render one display equation; False when the id names nothing."""
        equation = self.by_id.get(equation_id)
        if equation is None:
            return False
        element = None if equation.status is EquationStatus.PLAIN else self._omml(equation)
        paragraph = docx_document.add_paragraph()
        if element is not None and equation.number:
            self._numbered(docx_document, paragraph, equation, element)
        elif element is not None:
            wrapper = etree.SubElement(paragraph._p, f"{{{omml._M}}}oMathPara")
            wrapper.append(element)
        else:
            self._plain(docx_document, paragraph, equation)
        if equation.description:
            docx_document.add_paragraph(equation.description)
        return True

    @staticmethod
    def _text_width(docx_document):
        section = docx_document.sections[-1]
        return section.page_width - section.left_margin - section.right_margin

    def _tabs(self, docx_document, paragraph: Paragraph, centred: bool) -> None:
        width = self._text_width(docx_document)
        stops = paragraph.paragraph_format.tab_stops
        if centred:
            stops.add_tab_stop(int(width / 2), WD_TAB_ALIGNMENT.CENTER)
        stops.add_tab_stop(int(width), WD_TAB_ALIGNMENT.RIGHT)

    def _bookmark_name(self, equation: Equation) -> str:
        return "Eq_" + _BOOKMARK_SANITIZE_RE.sub("_", equation.label or equation.number or equation.id)

    def _number_run(self, paragraph: Paragraph, equation: Equation) -> None:
        bookmark_id = next(self._bookmark_ids)
        start = OxmlElement("w:bookmarkStart")
        start.set(qn("w:id"), str(bookmark_id))
        start.set(qn("w:name"), self._bookmark_name(equation))
        paragraph._p.append(start)
        self._add_text(paragraph, f"({equation.number})")
        end = OxmlElement("w:bookmarkEnd")
        end.set(qn("w:id"), str(bookmark_id))
        paragraph._p.append(end)

    def _numbered(self, docx_document, paragraph: Paragraph, equation: Equation, element) -> None:
        self._tabs(docx_document, paragraph, centred=True)
        self._add_text(paragraph, "\t")
        paragraph._p.append(element)
        self._add_text(paragraph, "\t")
        self._number_run(paragraph, equation)

    def _plain(self, docx_document, paragraph: Paragraph, equation: Equation) -> None:
        text = equation.text if equation.status is EquationStatus.PLAIN else equation.latex
        if equation.number:
            self._tabs(docx_document, paragraph, centred=False)
            self._add_text(paragraph, text + "\t")
            self._number_run(paragraph, equation)
        else:
            self._add_text(paragraph, text)

    # ── inline ─────────────────────────────────────────────────────────
    def split_inline(self, text: str) -> List[Piece]:
        """Split a line into text, inline equations and equation references."""
        found: List[Tuple[int, int, str, Union[str, Equation]]] = []
        for match in _INLINE_MATH_RE.finditer(text):
            equation = self._inline_by_latex.get(match.group(1).strip())
            if equation is not None:
                found.append((match.start(), match.end(), "equation", equation))
        for match in _REFERENCE_RE.finditer(text):
            equation = self._by_label.get(match.group(1))
            if equation is not None:
                found.append((match.start(), match.end(), "reference", equation))
        pieces: List[Piece] = []
        position = 0
        for start, end, kind, payload in sorted(found, key=lambda item: item[0]):
            if start < position:
                continue
            if start > position:
                pieces.append(("text", text[position:start]))
            pieces.append((kind, payload))
            position = end
        if position < len(text) or not pieces:
            pieces.append(("text", text[position:]))
        return pieces

    def add_inline(self, paragraph: Paragraph, equation: Equation) -> None:
        element = self._omml(equation)
        if element is not None:
            paragraph._p.append(element)
        else:
            self._add_text(paragraph, equation.text)

    def add_reference(self, paragraph: Paragraph, equation: Equation) -> None:
        """A ``REF`` field showing the equation's number, pointing at its bookmark."""
        def field(kind: str):
            run = OxmlElement("w:r")
            char = OxmlElement("w:fldChar")
            char.set(qn("w:fldCharType"), kind)
            run.append(char)
            paragraph._p.append(run)

        field("begin")
        instruction = OxmlElement("w:r")
        code = OxmlElement("w:instrText")
        code.set(qn("xml:space"), "preserve")
        code.text = f" REF {self._bookmark_name(equation)} \\h "
        instruction.append(code)
        paragraph._p.append(instruction)
        field("separate")
        self._add_text(paragraph, f"({equation.number})")
        field("end")
