"""Audit a finished DOCX against the two remediation checklists.

``docs/Checklist for Document Remediation1.docx`` and
``docs/ChecklistBeforeSubmittingDoc.xlsx`` are what a human remediator
ticks before a document ships. This module ticks them for RAWRS: every
item a machine can decide from the Word file (and the source PDF, for the
"content matches the PDF" item) is decided here with evidence; the few that
need a person in front of Word (keyboard testing, a PDF export check) are
reported as ``manual`` rather than silently passed.

It reads only the DOCX, never the Document model, so it audits what a
reader actually opens - including a DOCX regenerated after review.

CLI: ``python -m src.validation.checklist_audit file.docx [source.pdf]``
"""

import json
import re
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple, Union

from docx import Document as open_docx
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from lxml import etree

from src.docx.remediation_text import (
    URL_PATTERN,
    is_label,
    is_unformatted_numbered_heading,
    normalize_punctuation_spacing,
    space_units,
    unspaced_initialisms,
)

FONT = "Times New Roman"
BODY_PT = 12.0
HEADING_PT = {1: 16.0, 2: 14.0, 3: 12.0, 4: 12.0, 5: 12.0, 6: 12.0}
PLACEHOLDER_ALT_MARK = "pending human review"
TERMINAL = re.compile(r"[.?!:;…][\"'”’)\]]*$")
MANUAL_BULLET = re.compile(r"^\s*(?:[•▪▸▶◦○◉●→⁃✓✗✔✘\-]\s+|\(?\d{1,2}[.)]\s+[A-Z])")
MIN_TEXT_RECALL = 0.95
EXAMPLES = 3
CENTER = 1  # WD_ALIGN_PARAGRAPH.CENTER

_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
_MATH = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_A16_DECORATIVE = "{http://schemas.microsoft.com/office/drawing/2017/decorative}decorative"


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    NOT_APPLICABLE = "not_applicable"
    MANUAL = "manual"


@dataclass
class CheckResult:
    item_id: str
    source: str  # "remediation_docx" | "submission_xlsx"
    section: str
    requirement: str
    status: Status
    evidence: str = ""
    count: int = 0


@dataclass
class ChecklistReport:
    docx_path: str
    results: List[CheckResult] = field(default_factory=list)

    @property
    def summary(self) -> Dict[str, int]:
        counts = {status.value: 0 for status in Status}
        for result in self.results:
            counts[result.status.value] += 1
        return counts

    @property
    def passed(self) -> bool:
        return not any(r.status is Status.FAIL for r in self.results)

    def failing(self) -> List[str]:
        return [r.item_id for r in self.results if r.status is Status.FAIL]

    def to_dict(self) -> dict:
        return {
            "docx_path": self.docx_path,
            "passed": self.passed,
            "summary": self.summary,
            "results": [{**asdict(r), "status": r.status.value} for r in self.results],
        }


# --- reading the DOCX ----------------------------------------------------------


@dataclass
class _Block:
    kind: str  # "p" | "table"
    paragraph: Optional[Paragraph] = None
    table: Optional[Table] = None


def _body_blocks(doc) -> Iterator[_Block]:
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield _Block("p", paragraph=Paragraph(child, doc))
        elif child.tag == qn("w:tbl"):
            yield _Block("table", table=Table(child, doc))


def _text(p: Paragraph) -> str:
    return "".join(t.text or "" for t in p._p.iter(qn("w:t")))


def _is_page_break(p: Paragraph) -> bool:
    return any(br.get(qn("w:type")) == "page" for br in p._p.iter(qn("w:br")))


def _has_image(p: Paragraph) -> bool:
    return bool(p._p.findall(f".//{{{_WP}}}inline")) or bool(p._p.findall(f".//{{{_WP}}}anchor"))


def _style_name(p: Paragraph) -> str:
    return p.style.name if p.style is not None else "Normal"


def _heading_level(p: Paragraph) -> Optional[int]:
    match = re.match(r"Heading (\d)$", _style_name(p))
    return int(match.group(1)) if match else None


def _is_generated_notes_page(first: Paragraph, number: int, pages: list) -> bool:
    """The endnotes section RAWRS appends after the last PDF page: it is not a
    page of the PDF, so it has no printed number to carry."""
    return number == len(pages) and _heading_level(first) is not None and bool(
        re.match(r"(end)?notes$", _text(first).strip(), re.IGNORECASE)
    )


def _field_codes(p: Paragraph) -> str:
    codes = [el.get(qn("w:instr")) or "" for el in p._p.iter(qn("w:fldSimple"))]
    codes += [el.text or "" for el in p._p.iter(qn("w:instrText"))]
    return " ".join(codes)


def _style_chain(style) -> Iterator:
    while style is not None:
        yield style
        style = style.base_style


def _doc_default(doc, tag: str, attr: str) -> Optional[str]:
    found = doc.styles.element.find(
        f"{qn('w:docDefaults')}/{qn('w:rPrDefault')}/{qn('w:rPr')}/{qn(tag)}"
    )
    return found.get(qn(attr)) if found is not None else None


def _font_value(font, prop: str):
    if prop == "name":
        return font.name
    if prop == "size":
        return font.size.pt if font.size else None
    if prop == "color":
        return str(font.color.rgb) if font.color and font.color.rgb else None
    return getattr(font, prop)


def _effective(doc, p: Paragraph, run_el, prop: str):
    """A run's effective font name / size (pt) / bold / italic / color, resolved
    run -> paragraph style chain -> document defaults, as Word resolves it."""
    direct = _font_value(Run(run_el, p).font, prop)
    if direct is not None:
        return direct
    for style in _style_chain(p.style):
        value = _font_value(style.font, prop)
        if value is not None:
            return value
        if prop == "color" and style.font.color is not None and style.font.color.theme_color is not None:
            return f"theme:{style.font.color.theme_color}"
        if prop == "name":
            rfonts = style.element.find(f"{qn('w:rPr')}/{qn('w:rFonts')}")
            if rfonts is not None and rfonts.get(qn("w:asciiTheme")):
                return f"theme:{rfonts.get(qn('w:asciiTheme'))}"
    if prop == "name":
        return _doc_default(doc, "w:rFonts", "w:ascii") or "theme:minorHAnsi"
    if prop == "size":
        half_points = _doc_default(doc, "w:sz", "w:val")
        return int(half_points) / 2 if half_points else 10.0
    if prop in ("bold", "italic"):
        return False
    return None


def _text_runs(p: Paragraph) -> List:
    """Runs that carry visible text (note-reference and drawing runs excluded)."""
    return [
        r for r in p._p.iter(qn("w:r"))
        if any((t.text or "").strip() for t in r.iter(qn("w:t")))
    ]


def _is_black(color: Optional[str]) -> bool:
    return color in (None, "000000")


def _examples(items: List[str]) -> str:
    shown = "; ".join(repr(i[:70]) for i in items[:EXAMPLES])
    return f"{len(items)} found, e.g. {shown}" if items else ""


def _notes_text(parts: Dict[str, bytes]) -> str:
    text = []
    for name in ("word/footnotes.xml", "word/endnotes.xml"):
        if name in parts:
            text += [t.text or "" for t in etree.fromstring(parts[name]).iter(qn("w:t"))]
    return " ".join(text)


def _words(text: str) -> List[str]:
    text = re.sub(r"-\s*\n\s*", "", text)  # hyphenated line ends in the PDF
    return re.findall(r"[a-z]{4,}", text.lower())


# --- the audit -------------------------------------------------------------------


class _Audit:
    def __init__(
        self,
        docx_path: Path,
        pdf_path: Optional[Path],
        expected_pages: Optional[int],
        equation_objects: Optional[Sequence] = None,
    ):
        # The document's Equation objects when the caller has them; None for a
        # bare .docx (CLI), where only the structure of the boxes can be read.
        self.equation_objects = None if equation_objects is None else list(equation_objects)
        self.path = docx_path
        self.doc = open_docx(str(docx_path))
        self.pdf_path = pdf_path
        self.expected_pages = expected_pages
        self.blocks = list(_body_blocks(self.doc))
        self.paragraphs = [b.paragraph for b in self.blocks if b.kind == "p"]
        self.pages = self._split_pages()
        self.results: List[CheckResult] = []
        with zipfile.ZipFile(docx_path) as package:
            self.parts = {name: package.read(name) for name in package.namelist()}

    def _split_pages(self) -> List[List[_Block]]:
        pages: List[List[_Block]] = [[]]
        for block in self.blocks:
            if block.kind == "p" and _is_page_break(block.paragraph):
                if _text(block.paragraph).strip():
                    pages[-1].append(block)
                pages.append([])
            else:
                pages[-1].append(block)
        return pages

    def add(self, item_id, source, section, requirement, status, evidence="", count=0):
        self.results.append(CheckResult(item_id, source, section, requirement, status, evidence, count))

    def prose(self) -> List[Paragraph]:
        return [
            p for p in self.paragraphs
            if _heading_level(p) is None
            and _style_name(p) not in ("Title", "Subtitle", "TOC Heading")
            and not _style_name(p).startswith("toc")
            and not _style_name(p).startswith("TOC")
            and not _field_codes(p)
            and _text(p).strip()
        ]

    def run(self) -> ChecklistReport:
        for check in (
            self.fonts, self.content_matches_pdf, self.images, self.page_numbers,
            self.page_breaks, self.extra_spaces, self.lists, self.tables,
            self.abbreviations, self.page_end_sentences, self.equations,
            self.heading_styles, self.heading_hierarchy, self.numbered_headings,
            self.punctuation, self.units, self.document_setup, self.hyperlinks,
            self.notes, self.toc, self.metadata, self.manual_items,
        ):
            check()
        return ChecklistReport(str(self.path), self.results)

    # -- Checklist for Document Remediation -------------------------------------

    def fonts(self):
        bad = []
        for p in self.prose():
            for r in _text_runs(p):
                name, size = _effective(self.doc, p, r, "name"), _effective(self.doc, p, r, "size")
                if name != FONT or size != BODY_PT:
                    bad.append(f"{name} {size}pt: {_text(p)}")
                    break
        self.add("DR-02", "remediation_docx", "General Formatting",
                 "Normal text is Times New Roman 12 pt",
                 Status.FAIL if bad else Status.PASS, _examples(bad), len(bad))

    def content_matches_pdf(self):
        requirement = "Content matches the PDF (spelling, words)"
        if self.pdf_path is None or not Path(self.pdf_path).is_file():
            self.add("DR-03", "remediation_docx", "General Formatting", requirement,
                     Status.MANUAL, "no source PDF supplied")
            return
        import fitz

        with fitz.open(str(self.pdf_path)) as pdf:
            source = " ".join(page.get_text() for page in pdf)
        pdf_words = set(_words(source))
        if len(pdf_words) < 50:
            self.add("DR-03", "remediation_docx", "General Formatting", requirement,
                     Status.MANUAL, "source PDF has no text layer (scanned): text came from OCR")
            return
        docx_text = " ".join(_text(p) for p in self.paragraphs)
        for block in self.blocks:
            if block.kind == "table":
                docx_text += " " + " ".join(c.text for row in block.table.rows for c in row.cells)
        docx_text += " " + _notes_text(self.parts)
        # A Word equation's characters are content like any other; they are
        # not w:t text, so without this a maths page would "lose" its symbols.
        docx_text += " " + " ".join(
            t.text or "" for t in self.doc.element.body.iter(f"{{{_MATH}}}t")
        )
        # Spelled-out initialisms ("U S") are the checklist's own change, not a loss.
        docx_text = re.sub(r"\b([A-Z]) (?=[A-Z]\b)", r"\1", docx_text)
        missing = sorted(pdf_words - set(_words(docx_text)))
        recall = 1 - len(missing) / len(pdf_words)
        self.add("DR-03", "remediation_docx", "General Formatting", requirement,
                 Status.PASS if recall >= MIN_TEXT_RECALL else Status.FAIL,
                 f"{recall:.1%} of the PDF's distinct words are in the DOCX; missing e.g. {missing[:8]}",
                 len(missing))

    def images(self):
        inline = self.doc.element.body.findall(f".//{{{_WP}}}inline")
        anchored = self.doc.element.body.findall(f".//{{{_WP}}}anchor")
        if not inline and not anchored:
            self.add("DR-05", "remediation_docx", "General Formatting",
                     "Images centered and inline with text; captions centered",
                     Status.NOT_APPLICABLE, "no images")
            self.add("DR-ALT", "remediation_docx", "Final Formatting",
                     "Alt text for all images, without symbols a screen reader skips",
                     Status.NOT_APPLICABLE, "no images")
            self.add("SUB-IMG", "submission_xlsx", "Images & Graphics",
                     "Informative images have alt text; decorative ones are marked",
                     Status.NOT_APPLICABLE, "no images")
            return
        off_center, bad_caption, missing_alt, placeholder, symbols = [], [], [], [], []
        for index, p in enumerate(self.paragraphs):
            drawings = p._p.findall(f".//{{{_WP}}}inline")
            if not drawings:
                continue
            if p.alignment != CENTER:
                off_center.append(f"image {index}")
            for drawing in drawings:
                doc_pr = drawing.find(f"{{{_WP}}}docPr")
                descr = (doc_pr.get("descr") or "").strip() if doc_pr is not None else ""
                decorative = doc_pr is not None and any(
                    el.tag == _A16_DECORATIVE and el.get("val") in ("1", "true") for el in doc_pr.iter()
                )
                if decorative:
                    continue
                if not descr:
                    missing_alt.append(f"image {index}")
                elif PLACEHOLDER_ALT_MARK in descr:
                    placeholder.append(descr)
                elif re.search(r"[^\w\s.,;:'\"()\-?!%/&]", descr):
                    symbols.append(descr)
            nxt = self.paragraphs[index + 1] if index + 1 < len(self.paragraphs) else None
            if nxt is not None and _style_name(nxt) == "Caption" and nxt.alignment != CENTER:
                bad_caption.append(_text(nxt))
        failures = len(off_center) + len(bad_caption) + len(anchored)
        self.add("DR-05", "remediation_docx", "General Formatting",
                 "Images centered and inline with text; captions centered",
                 Status.FAIL if failures else Status.PASS,
                 f"{len(inline)} inline, {len(anchored)} floating, {len(off_center)} not centered, "
                 f"{len(bad_caption)} captions not centered", failures)
        alt_failures = missing_alt + placeholder
        self.add("DR-ALT", "remediation_docx", "Final Formatting",
                 "Alt text for all images, without symbols a screen reader skips",
                 Status.FAIL if alt_failures else (Status.WARN if symbols else Status.PASS),
                 f"{len(missing_alt)} missing, {len(placeholder)} still placeholder, "
                 f"{len(symbols)} with symbols", len(alt_failures) + len(symbols))
        self.add("SUB-IMG", "submission_xlsx", "Images & Graphics",
                 "Informative images have alt text; decorative ones are marked",
                 Status.FAIL if alt_failures else Status.PASS,
                 f"{len(inline)} images; {len(alt_failures)} without real alt text", len(alt_failures))

    def page_numbers(self):
        missing, misaligned, labels = [], [], []
        for number, page in enumerate(self.pages, start=1):
            first = next(
                (b.paragraph for b in page
                 if b.kind == "p" and (_text(b.paragraph).strip() or _has_image(b.paragraph))),
                None,
            )
            if first is None or _style_name(first).startswith(("TOC", "toc")) or _field_codes(first):
                continue
            if _heading_level(first) != 6:
                if _is_generated_notes_page(first, number, self.pages):
                    continue
                missing.append(f"page {number}: {_text(first) or '[image]'}")
                continue
            labels.append(_text(first).strip())
            if first.alignment not in (None, 0):
                misaligned.append(f"page {number}")
        self.add("DR-06", "remediation_docx", "General Formatting",
                 "Page number (Heading 6) at the top left of every page",
                 Status.FAIL if missing or misaligned else Status.PASS,
                 _examples(missing) or f"{len(labels)} pages numbered", len(missing) + len(misaligned))
        numeric = [int(label) for label in labels if label.isdigit()]
        jumps = [f"{a}->{b}" for a, b in zip(numeric, numeric[1:]) if b != a + 1]
        self.add("SUB-PGNUM", "submission_xlsx", "Page Layout & Navigation",
                 "Running page numbers are correct",
                 Status.WARN if jumps else Status.PASS,
                 f"non-consecutive: {jumps[:6]}" if jumps else f"{len(numeric)} consecutive", len(jumps))

    def page_breaks(self):
        breaks = sum(1 for p in self.paragraphs if _is_page_break(p))
        numbered = sum(
            1 for page in self.pages if any(b.kind == "p" and _heading_level(b.paragraph) == 6 for b in page)
        )
        if self.expected_pages is None:
            status, evidence = Status.PASS, f"{breaks} page breaks, {numbered} numbered pages"
        else:
            status = Status.PASS if numbered == self.expected_pages else Status.FAIL
            evidence = f"{numbered} numbered pages for {self.expected_pages} PDF pages ({breaks} breaks)"
        self.add("DR-07", "remediation_docx", "General Formatting",
                 "A page break at the end of each PDF page", status, evidence)
        blank = [
            str(n) for n, page in enumerate(self.pages, start=1)
            if page and all(
                b.kind == "p" and not _has_image(b.paragraph)
                and (_heading_level(b.paragraph) == 6 or not _text(b.paragraph).strip())
                for b in page
            )
        ]
        self.add("SUB-BLANK", "submission_xlsx", "Document Setup & Structure",
                 "No unnecessary blank pages",
                 Status.WARN if blank else Status.PASS,
                 f"pages with only a page number: {blank[:10]}" if blank else "none", len(blank))

    def extra_spaces(self):
        doubled = [_text(p) for p in self.prose() if re.search(r"\S {2,}\S", _text(p))]
        empty = sum(
            1 for p in self.paragraphs
            if not _text(p).strip() and not _is_page_break(p) and not _has_image(p) and not _field_codes(p)
        )
        broken = []
        prose = [p for p in self.prose() if _style_name(p) == "Normal"]
        for a, b in zip(prose, prose[1:]):
            ta, tb = _text(a).strip(), _text(b).strip()
            if a._p.getnext() is b._p and not TERMINAL.search(ta) and tb[:1].islower():
                broken.append(ta[-40:] + " | " + tb[:30])
        total = len(doubled) + empty + len(broken)
        self.add("DR-08", "remediation_docx", "General Formatting",
                 "No extra spaces or broken sentences",
                 Status.FAIL if total else Status.PASS,
                 f"{len(doubled)} paragraphs with double spaces, {empty} empty paragraphs, "
                 f"{len(broken)} sentences split across paragraphs {_examples(broken)}", total)

    def lists(self):
        manual = [_text(p) for p in self.prose() if _style_name(p) == "Normal" and MANUAL_BULLET.match(_text(p))]
        listed = sum(1 for p in self.paragraphs if _style_name(p).startswith("List"))
        self.add("DR-09", "remediation_docx", "General Formatting",
                 "Bullets and numbering use Word list styles, as in the PDF",
                 Status.WARN if manual else Status.PASS,
                 f"{listed} list paragraphs; typed markers: {_examples(manual) or 'none'}", len(manual))
        self.add("SUB-LIST", "submission_xlsx", "Lists & Numbering",
                 "No manual symbols or numbers for lists",
                 Status.WARN if manual else Status.PASS, _examples(manual) or "none", len(manual))

    def tables(self):
        tables = [b.table for b in self.blocks if b.kind == "table"]
        if not tables:
            for item_id, source, section, req in (
                ("DR-10", "remediation_docx", "General Formatting", "Tables have no merged cells (words repeated instead)"),
                ("SUB-TBL-HDR", "submission_xlsx", "Tables", "Header rows are marked 'Repeat Header Row'"),
                ("SUB-TBL-CAP", "submission_xlsx", "Tables", "Tables have captions or summaries"),
            ):
                self.add(item_id, source, section, req, Status.NOT_APPLICABLE, "no tables")
            return
        merged = sum(
            1 for t in tables
            if t._tbl.findall(f".//{qn('w:gridSpan')}") or t._tbl.findall(f".//{qn('w:vMerge')}")
        )
        no_header = sum(1 for t in tables if not t._tbl.findall(f".//{qn('w:tblHeader')}"))
        undescribed = 0
        for t in tables:
            described = False
            for el in (t._tbl.getprevious(), t._tbl.getnext()):
                if el is not None and el.tag == qn("w:p"):
                    p = Paragraph(el, self.doc)
                    described |= _style_name(p) == "Caption" or _text(p).startswith("Table summary:")
            undescribed += not described
        self.add("DR-10", "remediation_docx", "General Formatting",
                 "Tables have no merged cells (words repeated instead)",
                 Status.FAIL if merged else Status.PASS, f"{merged} of {len(tables)} tables merge cells", merged)
        self.add("SUB-TBL-HDR", "submission_xlsx", "Tables",
                 "Header rows are marked 'Repeat Header Row'",
                 Status.FAIL if no_header else Status.PASS, f"{no_header} of {len(tables)} tables lack one", no_header)
        self.add("SUB-TBL-CAP", "submission_xlsx", "Tables",
                 "Tables have captions or summaries",
                 Status.FAIL if undescribed else Status.PASS, f"{undescribed} of {len(tables)} undescribed", undescribed)

    def abbreviations(self):
        found = [tok for p in self.prose() for tok in unspaced_initialisms(_text(p))]
        self.add("DR-11", "remediation_docx", "General Formatting",
                 "Initialisms spelled for screen readers (US -> U S; UNESCO kept)",
                 Status.FAIL if found else Status.PASS, _examples(sorted(set(found))) or "none", len(found))

    def page_end_sentences(self):
        broken = []
        for page, nxt in zip(self.pages, self.pages[1:]):
            last = next((b.paragraph for b in reversed(page)
                         if b.kind == "p" and _style_name(b.paragraph) in ("Normal", "List Bullet")
                         and _text(b.paragraph).strip() and not is_label(_text(b.paragraph))), None)
            first = next((b.paragraph for b in nxt
                          if b.kind == "p" and _text(b.paragraph).strip()
                          and _heading_level(b.paragraph) != 6), None)
            if last is None or first is None or _style_name(first) != "Normal":
                continue
            tail, head = _text(last).strip(), _text(first).strip()
            if not TERMINAL.search(tail) and (head[:1].islower() or tail.endswith(",")):
                broken.append(f"...{tail[-35:]} | {head[:25]}...")
        self.add("DR-12", "remediation_docx", "General Formatting",
                 "No sentence left incomplete at the end of a page",
                 Status.FAIL if broken else Status.PASS, _examples(broken) or "none", len(broken))

    def equations(self):
        """Eq 1-7 (docs/EQUATION_DESIGN.md §1). The structural rules are read
        off the DOCX itself; whether a converted equation matches the PDF was
        proven when it was converted (round trip), so only a FLAGGED one, or a
        DOCX audited with no model to ask, still needs a person."""
        section = "Rules to follow for Equation Box"
        requirement = "Equations use Word's equation tool and look like the PDF (Eq 6)"
        boxes = list(self.doc.element.body.iter(f"{{{_MATH}}}oMath"))
        objects = self.equation_objects
        if not boxes and not objects:
            self.add("DR-EQ", "remediation_docx", section, requirement,
                     Status.NOT_APPLICABLE, "no equations")
            return
        flagged = [e for e in objects or [] if e.status.value == "flagged"]
        if objects is None:
            status, evidence = Status.MANUAL, f"{len(boxes)} equations - check against the PDF"
        else:
            counts = {s: sum(1 for e in objects if e.status.value == s) for s in ("converted", "flagged", "plain")}
            evidence = (f"{len(boxes)} Word equations; {counts['converted']} converted (round trip verified), "
                        f"{counts['flagged']} flagged, {counts['plain']} plain text")
            if flagged:
                status = Status.MANUAL
                evidence += "; check against the PDF: " + "; ".join(
                    f"{e.id} ({', '.join(e.flag_reasons) or 'flagged'})" for e in flagged[:5])
            else:
                status = Status.PASS
        self.add("DR-EQ", "remediation_docx", section, requirement, status, evidence, len(flagged))
        failing = [f"{rule}: {detail}" for rule, detail in self._equation_structure(boxes)]
        self.add("DR-EQ-STRUCT", "remediation_docx", section,
                 "Equation box rules: no extra spaces (Eq 1), one equation per box (Eq 2), functions from the "
                 "equation tool (Eq 3), number outside (Eq 4), no connecting text (Eq 5), simple equations "
                 "outside the box (Eq 7)",
                 Status.FAIL if failing else Status.PASS, _examples(failing) or "none", len(failing))

    def _equation_structure(self, boxes) -> List[Tuple[str, str]]:
        """(rule, detail) for every Eq 1-5/7 breach in the equation boxes."""
        from src.equations import latex as tex

        def m(tag):
            return f"{{{_MATH}}}{tag}"

        def run_text(run):
            return "".join(t.text or "" for t in run.iter(m("t")))

        problems: List[Tuple[str, str]] = []
        for box in boxes:
            text = "".join(t.text or "" for t in box.iter(m("t")))
            runs = list(box.iter(m("r")))
            shown = text[:40]
            if box.find(f".//{m('eqArr')}") is not None:
                problems.append(("Eq 2", f"several equations in one box: {shown}"))
            for run in runs:
                word = run_text(run).strip()
                if word in tex.FUNCTIONS and not any(a.tag == m("fName") for a in run.iterancestors()):
                    problems.append(("Eq 3", f"'{word}' typed, not from the equation tool: {shown}"))
            if re.search(r"\(\s*\d+(?:\.\d+)*\s*\)\s*$", text):
                problems.append(("Eq 4", f"equation number inside the box: {shown}"))
            edge = [runs[0], runs[-1]] if runs else []
            if any(r.find(f".//{m('nor')}") is not None for r in edge):
                problems.append(("Eq 5", f"connecting text inside the box: {shown}"))
            if runs and (not run_text(runs[0]).strip() or not run_text(runs[-1]).strip() or "  " in text):
                problems.append(("Eq 1", f"extra spaces in the equation: {shown!r}"))
            if all(child.tag == m("r") for child in box) and text.strip() and (
                tex.is_simple(text) or tex.is_non_maths(text)
            ):
                problems.append(("Eq 7", f"simple equation inside a box: {shown}"))
        return problems

    def heading_styles(self):
        wrong = []
        for p in self.paragraphs:
            level = _heading_level(p)
            if level is None or not _text(p).strip():
                continue
            for r in _text_runs(p):
                name, size, bold, italic, color = (
                    _effective(self.doc, p, r, prop) for prop in ("name", "size", "bold", "italic", "color")
                )
                if name != FONT or size != HEADING_PT[level] or not bold or italic or not _is_black(color):
                    wrong.append(f"H{level} {name}/{size}/bold={bold}/italic={italic}/{color}: {_text(p)}")
                    break
        self.add("DR-HD-FMT", "remediation_docx", "Heading Level",
                 "Headings: Times New Roman, black, bold; H1 16 pt, H2 14 pt, H3-H6 12 pt",
                 Status.FAIL if wrong else Status.PASS, _examples(wrong) or "all headings", len(wrong))
        fake = [
            _text(p) for p in self.prose()
            if _style_name(p) == "Normal" and len(_text(p).split()) <= 10
            and not TERMINAL.search(_text(p).strip())
            and all(_effective(self.doc, p, r, "bold") for r in _text_runs(p))
        ]
        self.add("SUB-STYLES", "submission_xlsx", "Headings & Styles",
                 "Headings use heading styles, not manual bold text",
                 Status.WARN if fake else Status.PASS, _examples(fake) or "none", len(fake))

    def heading_hierarchy(self):
        levels = []
        for p in self.paragraphs:
            level = _heading_level(p)
            if level is not None and level != 6 and _text(p).strip():
                levels.append((level, _text(p)))
        numbered_pages = sum(1 for p in self.paragraphs if _heading_level(p) == 6)
        self.add("SUB-HD-STYLES", "submission_xlsx", "Headings & Styles",
                 "Headings carry heading styles",
                 Status.WARN if not levels and numbered_pages >= 3 else Status.PASS,
                 f"{len(levels)} content headings over {numbered_pages} pages", len(levels))
        skips = [f"H{a}->H{b} at {t[:40]!r}" for (a, _), (b, t) in zip(levels, levels[1:]) if b > a + 1]
        if levels and levels[0][0] > 2:
            skips.insert(0, f"document starts at H{levels[0][0]}")
        for item_id, source, section in (
            ("DR-HD-ORDER", "remediation_docx", "Heading Level"),
            ("SUB-HD-ORDER", "submission_xlsx", "Headings & Styles"),
        ):
            self.add(item_id, source, section, "Heading levels in hierarchical order (no skips)",
                     Status.FAIL if skips else Status.PASS,
                     "; ".join(skips[:EXAMPLES]) or f"{len(levels)} headings in order", len(skips))

    def numbered_headings(self):
        bad = [_text(p) for p in self.paragraphs
               if _heading_level(p) not in (None, 6) and is_unformatted_numbered_heading(_text(p))]
        self.add("DR-HD-HYPHEN", "remediation_docx", "Heading Level",
                 "Numbered headings written '6.1 - INTRODUCTION'",
                 Status.FAIL if bad else Status.PASS, _examples(bad) or "none", len(bad))

    def punctuation(self):
        bad = []
        for p in self.prose():
            text = URL_PATTERN.sub("URL", _text(p))
            if normalize_punctuation_spacing(text) != text:
                bad.append(text)
        self.add("DR-PUNCT", "remediation_docx", "Proper spacing between the punctuations",
                 "Comma, bracket and hyphen spacing",
                 Status.FAIL if bad else Status.PASS, _examples(bad) or "none", len(bad))

    def units(self):
        bad = [_text(p) for p in self.prose() if space_units(_text(p)) != _text(p)]
        self.add("DR-UNITS", "remediation_docx", "Final Formatting",
                 "A space before kg and other units",
                 Status.FAIL if bad else Status.PASS, _examples(bad) or "none", len(bad))

    # -- Checklist before submitting ----------------------------------------------

    def document_setup(self):
        lang = _doc_default(self.doc, "w:lang", "w:val")
        self.add("SUB-LANG", "submission_xlsx", "Document Setup & Structure",
                 "Document language is set", Status.PASS if lang else Status.FAIL,
                 f"w:lang={lang}, core language={self.doc.core_properties.language or None}")
        section = self.doc.sections[0]
        margins = [section.left_margin, section.right_margin, section.top_margin, section.bottom_margin]
        ok = bool(section.page_width) and all(m is not None and m >= Pt(36) for m in margins)
        portrait = bool(section.page_width) and section.page_width < section.page_height
        self.add("SUB-PAGE", "submission_xlsx", "Document Setup & Structure",
                 "Page size, margins and portrait orientation set",
                 Status.PASS if ok and portrait else Status.FAIL,
                 f"{section.page_width.inches:.2f}x{section.page_height.inches:.2f} in, margins "
                 f"{[round(m.inches, 2) for m in margins]}")
        boxes = sum(1 for _ in self.doc.element.body.iter(qn("w:txbxContent")))
        self.add("SUB-TEXTBOX", "submission_xlsx", "Document Setup & Structure",
                 "All content in the main body, not text boxes",
                 Status.FAIL if boxes else Status.PASS, f"{boxes} text boxes", boxes)

    def hyperlinks(self):
        external = [h for h in self.doc.element.body.iter(qn("w:hyperlink")) if h.get(qn("r:id"))]
        unlinked = []
        for p in self.paragraphs:
            outside = "".join(
                t.text or "" for t in p._p.iter(qn("w:t"))
                if not any(a.tag == qn("w:hyperlink") for a in t.iterancestors())
            )
            unlinked += URL_PATTERN.findall(outside)
        raw_display = [
            h for h in external
            if URL_PATTERN.fullmatch("".join(t.text or "" for t in h.iter(qn("w:t"))).strip())
        ]
        none = not external and not unlinked
        self.add("SUB-LINK", "submission_xlsx", "Hyperlinks & Cross References",
                 "Web addresses are working hyperlinks",
                 Status.NOT_APPLICABLE if none else (Status.FAIL if unlinked else Status.PASS),
                 f"{len(external)} hyperlinks, {len(unlinked)} unlinked addresses {_examples(unlinked)}",
                 len(unlinked))
        self.add("SUB-LINK-TEXT", "submission_xlsx", "Hyperlinks & Cross References",
                 "Hyperlinks have meaningful display text",
                 Status.NOT_APPLICABLE if none else (Status.WARN if raw_display else Status.PASS),
                 f"{len(raw_display)} show the printed address (kept verbatim to match the PDF)",
                 len(raw_display))

    def notes(self):
        refs, bodies = set(), set()
        for kind in ("footnote", "endnote"):
            for el in self.doc.element.body.iter(qn(f"w:{kind}Reference")):
                refs.add((kind, el.get(qn("w:id"))))
            part = self.parts.get(f"word/{kind}s.xml")
            if part:
                for el in etree.fromstring(part).iter(qn(f"w:{kind}")):
                    if el.get(qn("w:type")) is None:
                        bodies.add((kind, el.get(qn("w:id"))))
        requirement = "Native Word notes, markers linked to their notes"
        if not refs and not bodies:
            self.add("SUB-NOTES", "submission_xlsx", "Footnotes & Endnotes", requirement,
                     Status.NOT_APPLICABLE, "no notes")
            return
        dangling, orphan = refs - bodies, bodies - refs
        self.add("SUB-NOTES", "submission_xlsx", "Footnotes & Endnotes", requirement,
                 Status.FAIL if dangling else (Status.WARN if orphan else Status.PASS),
                 f"{len(refs)} references, {len(bodies)} bodies, {len(dangling)} references without a body, "
                 f"{len(orphan)} bodies never referenced", len(dangling) + len(orphan))

    def toc(self):
        """RAWRS does not insert a Table of Contents: reviewers found the
        generated index cluttered the document (2026-09-28). The headings are
        real Word headings, so Word builds one in two clicks where a
        publisher wants it."""
        has_toc = any("TOC" in _field_codes(p) for p in self.paragraphs)
        self.add("SUB-TOC", "submission_xlsx", "Page Layout & Navigation",
                 "Automatic Table of Contents, fields updated",
                 Status.PASS if has_toc else Status.MANUAL,
                 "present" if has_toc else "not generated; add in Word (References > Table of Contents) if required")

    def metadata(self):
        props = self.doc.core_properties
        missing = [n for n in ("title", "author", "subject") if not (getattr(props, n) or "").strip()]
        self.add("SUB-META", "submission_xlsx", "Metadata & Properties",
                 "Title, Author and Subject set",
                 Status.FAIL if missing else Status.PASS,
                 f"missing {missing}" if missing else f"title={props.title!r}", len(missing))
        leaks = [f"{n}={getattr(props, n)!r}" for n in ("author", "comments", "last_modified_by")
                 if "python-docx" in (getattr(props, n) or "")]
        self.add("SUB-META-PRIV", "submission_xlsx", "Metadata & Properties",
                 "No stray personal or tool information in properties",
                 Status.FAIL if leaks else Status.PASS, ", ".join(leaks) or "clean", len(leaks))
        self.add("SUB-META-LANG", "submission_xlsx", "Metadata & Properties",
                 "Language set in properties",
                 Status.PASS if props.language else Status.FAIL, f"language={props.language!r}")

    def manual_items(self):
        for item_id, source, section, requirement, why in (
            ("DR-03B", "remediation_docx", "General Formatting", "Bold and italics match the PDF",
             "emphasis is carried from the PDF's fonts; spot-check against the PDF"),
            ("SUB-KEYBOARD", "submission_xlsx", "Final QA & Accessibility Check",
             "Keyboard-only navigation", "needs a person in Word"),
            ("SUB-PDF", "submission_xlsx", "Final QA & Accessibility Check",
             "Export to PDF and verify accessibility", "needs Word's PDF export"),
        ):
            self.add(item_id, source, section, requirement, Status.MANUAL, why)
        failing = [r.item_id for r in self.results if r.status is Status.FAIL]
        self.add("SUB-A11Y", "submission_xlsx", "Final QA & Accessibility Check",
                 "Accessibility checker issues resolved (this audit's automated equivalent)",
                 Status.FAIL if failing else Status.PASS,
                 f"failing: {failing}" if failing else "all automated checks pass", len(failing))


# --- entry points ----------------------------------------------------------------


def audit_docx(
    docx_path: Union[str, Path],
    pdf_path: Optional[Union[str, Path]] = None,
    expected_pages: Optional[int] = None,
    equations: Optional[Sequence] = None,
) -> ChecklistReport:
    """``equations`` is the Document's ``Equation`` list when the caller has it;
    without it DR-EQ can only ask a person (docs/EQUATION_DESIGN.md §5)."""
    return _Audit(
        Path(docx_path), Path(pdf_path) if pdf_path else None, expected_pages, equations
    ).run()


def write_checklist_report(report: ChecklistReport, report_path: Union[str, Path]) -> Path:
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def format_report(report: ChecklistReport) -> str:
    marks = {"pass": "PASS", "fail": "FAIL", "warn": "WARN", "not_applicable": "n/a ", "manual": "MANU"}
    lines = [f"{report.docx_path}: {report.summary}"]
    for r in report.results:
        lines.append(f"  {marks[r.status.value]} {r.item_id:<13} {r.requirement[:55]:<55} {r.evidence[:120]}")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python -m src.validation.checklist_audit file.docx [source.pdf]")
    result = audit_docx(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(format_report(result))
    sys.exit(0 if result.passed else 1)
