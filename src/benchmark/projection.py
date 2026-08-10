"""Projection correctness (PI-1 … PI-5) — see docs/ADR_PROJECTION_CORRECTNESS_2026-08-03.md.

Answers a different question from the rest of this package. ``differ.py``
asks "did RAWRS find the right objects?" and needs a human-remediated corpus
to answer. This asks **"does the output faithfully express what RAWRS
found?"** and needs no ground truth at all - the Semantic Document is its own
specification. That is what makes it the stronger gate: it applies to every
document RAWRS ever processes, not only the ten in the benchmark corpus.

It replaces byte comparison, which was the wrong criterion. Byte comparison
asserts that today's output equals yesterday's, so it defends a renderer
defect exactly as hard as it defends correct behaviour - and it did: the
pre-P2 Markdown renderer silently discarded 20 detected headings across three
benchmark documents, and byte parity would have protected that indefinitely.

Read-only, benchmark-only. Production must never import this module.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

from src.structure.paragraph_assembly import (
    NOTES_SECTION_HEADING_PATTERN,
    absorbed_block_ids,
)

_CONTENT_HEADING = re.compile(r"^(#{1,5})\s+(.*\S)\s*$")
_PAGE_MARKER = re.compile(r"^#{6}\s+(.*\S)\s*$")
_TABLE_ANCHOR = re.compile(r"<!--\s*table-id:\s*(.+?)\s*-->")
_LIST_ANCHOR = re.compile(r"<!--\s*list-id:\s*(.+?)\s*-->")
_IMAGE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<path>[^)]*)\)")
_NOTE_DEF = re.compile(r"^\[\^(?P<label>[^\]]+)\]:\s")
# An inline note reference. Stripped before words are counted: a label is an
# identity, already verified exactly by the note-definition set check, and
# counting it as prose would compare one model label against its two
# projection occurrences (the reference and the definition).
_NOTE_REF = re.compile(r"\[\^[^\]]+\]")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_WORD = re.compile(r"\w+", re.UNICODE)

# Text a projection may emit that no object in the model holds. Every entry is
# a *generation rule* documented in the renderer, not a licence to invent:
# "Endnotes" is the heading RAWRS writes in place of a source "Notes" line
# when it collects endnote definitions into one section.
_GENERATED_LITERALS = ("Endnotes",)

# Which headings a projection may generate, and which absences it may have,
# now come from the projection's own declaration
# (src/architecture/contract.py) rather than from a list maintained here. The
# difference matters: a hardcoded allowance could be widened inside the
# checker, where nobody reviewing the renderer would see it. A declaration
# lives next to the code it excuses.
from src.markdown.markdown_builder import PROJECTION_CONTRACT as _MARKDOWN_CONTRACT


@dataclass(frozen=True)
class Violation:
    """One breach of a projection invariant."""

    invariant: str  # "PI-1" … "PI-5"
    kind: str  # lost_object | invented_object | content_loss | content_invention | duplicate
    detail: str

    def __str__(self) -> str:  # pragma: no cover - diagnostic only
        return f"[{self.invariant}/{self.kind}] {self.detail}"


@dataclass
class ProjectionReport:
    """Two channels, deliberately.

    ``violations`` are projection defects - the renderer failed to express the
    model. They block, because a projection that loses or invents is not
    repairable by tuning.

    ``findings`` are everything the check surfaces that is *not* the
    projection's fault: a containment edge that claims text the owning object
    does not reproduce (a detector defect), or a heading the renderer
    generates because the model has nowhere to put it (architectural debt).
    They are reported and tracked, never silently dropped, but they belong to
    Layer 2 of docs/ADR_PROJECTION_CORRECTNESS_2026-08-03.md §6 and are graded
    rather than gated.
    """

    document: str
    violations: List[Violation] = field(default_factory=list)
    findings: List[Violation] = field(default_factory=list)
    counts: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.violations

    def by_kind(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for v in self.violations:
            out[v.kind] = out.get(v.kind, 0) + 1
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document": self.document,
            "ok": self.ok,
            "counts": self.counts,
            "violations": [
                {"invariant": v.invariant, "kind": v.kind, "detail": v.detail}
                for v in self.violations
            ],
            "findings": [
                {"invariant": v.invariant, "kind": v.kind, "detail": v.detail}
                for v in self.findings
            ],
        }


def _norm(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _words(texts: Iterable[str]) -> Counter:
    bag: Counter = Counter()
    for t in texts:
        bag.update(_WORD.findall(t or ""))
    return bag


# --------------------------------------------------------------------------- #
# what the model says exists
# --------------------------------------------------------------------------- #

def _authorized_absent_headings(document: Any) -> Dict[str, str]:
    """Heading text -> the limitation code that explains its absence.

    Never a bare set. Every unmaterialized object must name the declared
    limitation permitting it, so "missing" and "missing for a stated reason"
    can never be confused - PI-1 read strictly: *every semantic object is
    either materialized or explicitly diagnosed*. A code the projection has
    not declared is itself a violation (see check_projection).
    """
    absent: Dict[str, str] = {}
    fm = getattr(document, "front_matter", None)
    if fm is not None and fm.title:
        absent[_norm(fm.title)] = "front_matter_title_rendered_as_block"

    blocks = getattr(document, "blocks", []) or []
    by_page: Dict[int, List[Any]] = {}
    for b in blocks:
        by_page.setdefault(b.page_number, []).append(b)

    for page_number, page_blocks in by_page.items():
        absorbed = absorbed_block_ids(document, page_number, page_blocks)
        for h in getattr(document, "headings", []) or []:
            if h.page_number != page_number or h.is_page_marker:
                continue
            if h.source_block_id is not None and h.source_block_id in absorbed:
                absent.setdefault(_norm(h.text), "absorbed_by_another_object")
    return absent


def _model_words(document: Any) -> Counter:
    """Every word the model holds, from every field a projection may render."""
    texts: List[str] = []

    for b in getattr(document, "blocks", []) or []:
        texts.append(b.text)
    for h in getattr(document, "headings", []) or []:
        texts.append(h.text)
    for p in getattr(document, "pages", []) or []:
        texts += [str(p.page_number), p.page_label or "", getattr(p, "printed_label", "") or ""]
    for t in getattr(document, "tables", []) or []:
        texts += [t.caption or "", t.summary or ""]
        for row in t.rows:
            texts += [c.text for c in row.cells]
    for lst in getattr(document, "lists", []) or []:
        texts += [item.text for item in lst.items]
    for n in getattr(document, "footnotes", []) or []:
        texts += [n.body, n.label, n.marker]
    for img in getattr(document, "images", []) or []:
        if img.figure is not None:
            texts += [img.figure.caption or "", img.figure.alt_text or ""]
    fm = getattr(document, "front_matter", None)
    if fm is not None:
        texts += [fm.title or ""] + list(fm.authors) + list(fm.affiliations)
    texts += list(_GENERATED_LITERALS)

    return _words(texts)


def _absorption(document: Any) -> tuple:
    """(block ids some object absorbed, words those objects carry instead).

    Absorption is a *substitution*, not a deletion: a line claimed by a table,
    a note body, a caption, the front matter or a wrapped heading still has to
    reach the output - through the absorbing object rather than the prose
    stream. So the check deducts the absorbed lines and adds back what the
    absorbers carry, instead of simply forgiving the absence. A renderer that
    emitted an empty note definition would still be caught.
    """
    blocks = getattr(document, "blocks", []) or []
    by_page: Dict[int, List[Any]] = {}
    for b in blocks:
        by_page.setdefault(b.page_number, []).append(b)

    absorbed: Set[str] = set()
    for page_number, page_blocks in by_page.items():
        absorbed |= absorbed_block_ids(document, page_number, page_blocks)

    carried: List[str] = []

    # A wrapped heading absorbs its own anchor as well as its continuations
    # (absorbed_block_ids holds only the latter) and carries the joined text -
    # unless the heading is itself authorized-absent, in which case something
    # else renders those words and counting them here would expect the same
    # text twice. The front-matter title is exactly that case: it is both a
    # detected heading and the front-matter block, absorbed from one set of
    # lines and rendered once.
    absent = _authorized_absent_headings(document)
    for h in getattr(document, "headings", []) or []:
        if not h.continuation_block_ids:
            continue
        if h.source_block_id:
            absorbed.add(h.source_block_id)
        if _norm(h.text) not in absent:
            carried.append(h.text)

    for t in getattr(document, "tables", []) or []:
        carried += [c.text for row in t.rows for c in row.cells]
        carried += [t.caption or "", t.summary or ""]
    for n in getattr(document, "footnotes", []) or []:
        carried.append(n.body)
    for img in getattr(document, "images", []) or []:
        if img.figure is not None:
            carried.append(img.figure.caption or "")
    fm = getattr(document, "front_matter", None)
    if fm is not None:
        carried += [fm.title or ""] + list(fm.authors) + list(fm.affiliations)

    return absorbed, _words(carried)


def _visible_block_words(document: Any) -> Counter:
    """Words a projection must reproduce.

    Every extracted line's text has to reach the output somewhere. A line an
    object absorbed is replaced by that object's own text (see
    ``_absorption``); the only content that may vanish outright is a
    suppressed artifact - an applied CorrectionRecord, revertible - and the
    "Notes" source line RAWRS replaces with its generated "## Endnotes"
    heading. Both are in ``absorbed`` with nothing carried back, which is the
    honest way to say "authorized to disappear".

    Anything else missing is content loss.
    """
    blocks = getattr(document, "blocks", []) or []
    absorbed, carried = _absorption(document)
    bag = _words(b.text for b in blocks if b.block_id not in absorbed)
    bag += carried
    # A note's printed marker is replaced in the prose by its ``[^label]``
    # reference, and a reference is identity rather than content - it is
    # verified exactly by the note-definition check and stripped before words
    # are counted. Deduct the markers so the substitution is not read as loss.
    bag -= _words(n.marker for n in getattr(document, "footnotes", []) or [])
    return bag


def _check_absorption_backed(document: Any, report: ProjectionReport) -> None:
    """Does each absorbing object actually account for the lines it claims?

    An absorption authorizes a line to vanish from prose. If the absorber does
    not reproduce its words, the authorization is unbacked and the text is
    simply gone - which is how a table bbox that over-captures, or an author
    line parsed into a list, deletes real content with no record.

    Reported as a *finding*, not a violation: the projection did exactly what
    the model instructed. The defect is in the edge - in table extraction or
    front-matter parsing - and belongs to Layer 2.
    """
    blocks_by_id = {b.block_id: b for b in getattr(document, "blocks", []) or []}

    for table in getattr(document, "tables", []) or []:
        if not table.source_block_ids:
            continue
        claimed = _words(
            blocks_by_id[bid].text for bid in table.source_block_ids if bid in blocks_by_id
        )
        carried = _words(
            [c.text for row in table.rows for c in row.cells]
            + [table.caption or "", table.summary or ""]
        )
        gap = claimed - carried
        if gap:
            report.findings.append(
                Violation(
                    "PI-4",
                    "unbacked_authorization",
                    f"table {table.table_id!r} (page {table.page_number}) claims "
                    f"{len(table.source_block_ids)} line(s) but its cells do not carry "
                    f"{sum(gap.values())} of their word(s): {dict(list(gap.items())[:6])}",
                )
            )

    fm = getattr(document, "front_matter", None)
    if fm is not None:
        claimed = _words(
            fm.title_source_texts + fm.author_source_texts + fm.affiliation_source_texts
        )
        carried = _words([fm.title or ""] + list(fm.authors) + list(fm.affiliations))
        gap = claimed - carried
        if gap:
            report.findings.append(
                Violation(
                    "PI-4",
                    "unbacked_authorization",
                    f"front matter claims its source lines but does not carry "
                    f"{sum(gap.values())} of their word(s): {dict(list(gap.items())[:6])}",
                )
            )


# --------------------------------------------------------------------------- #
# what the projection realized
# --------------------------------------------------------------------------- #

@dataclass
class _Realized:
    headings: List[str] = field(default_factory=list)
    markers: List[str] = field(default_factory=list)
    table_ids: List[str] = field(default_factory=list)
    list_ids: List[str] = field(default_factory=list)
    image_paths: List[str] = field(default_factory=list)
    note_labels: List[str] = field(default_factory=list)
    words: Counter = field(default_factory=Counter)


def _parse_markdown(markdown: str) -> _Realized:
    out = _Realized()
    prose: List[str] = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            continue

        out.table_ids += _TABLE_ANCHOR.findall(line)
        out.list_ids += _LIST_ANCHOR.findall(line)
        for m in _IMAGE.finditer(line):
            out.image_paths.append(m.group("path"))
            prose.append(m.group("alt"))  # alt text is content and must trace to a Figure
        # Anchors and pagebreak markers carry ids, not prose; they are checked
        # by identity above rather than counted as words on either side.
        line = _IMAGE.sub(" ", line)
        line = _HTML_COMMENT.sub(" ", line).strip()
        if not line:
            continue

        note = _NOTE_DEF.match(line)
        if note:
            out.note_labels.append(note.group("label"))
        line = _NOTE_REF.sub(" ", line).strip()
        if not line:
            continue

        marker = _PAGE_MARKER.match(line)
        if marker:
            out.markers.append(_norm(marker.group(1)))
            prose.append(marker.group(1))
            continue

        heading = _CONTENT_HEADING.match(line)
        if heading:
            out.headings.append(_norm(heading.group(2)))
            prose.append(heading.group(2))
            continue

        prose.append(line)

    out.words = _words(prose)
    return out


# --------------------------------------------------------------------------- #
# the invariants
# --------------------------------------------------------------------------- #

def _check_set(
    report: ProjectionReport,
    label: str,
    expected: Counter,
    realized: Counter,
    authorized_absent: Optional[Dict[str, str]] = None,
    contract: Any = None,
) -> None:
    """PI-1 / PI-2 / PI-5 for one object type, by identity.

    An expected object that is absent is a **lost object** unless the
    projection declared a limitation covering it, in which case a
    ``diagnosed_absence`` finding is emitted naming that limitation. A
    limitation code the projection has not declared is itself a violation -
    the checker will not invent an excuse the projection did not make.

    Read strictly, that is PI-1: every semantic object is either materialized
    or explicitly diagnosed. There is no third state.
    """
    authorized_absent = authorized_absent or {}
    declared = contract.limitation_codes() if contract is not None else frozenset()
    generated = contract.generated_identities(label) if contract is not None else frozenset()

    for key, want in expected.items():
        got = realized.get(key, 0)
        if got == 0:
            code = authorized_absent.get(key)
            if code is None:
                report.violations.append(
                    Violation(
                        "PI-1", "lost_object", f"{label} in model but not in projection: {key!r}"
                    )
                )
            elif code not in declared:
                report.violations.append(
                    Violation(
                        "PI-1",
                        "undeclared_limitation",
                        f"{label} {key!r} is absent under limitation {code!r}, which the "
                        f"projection does not declare",
                    )
                )
            else:
                report.findings.append(
                    Violation(
                        "PI-1",
                        "diagnosed_absence",
                        f"{label} {key!r} not materialized - declared limitation {code!r}",
                    )
                )
        elif got > want:
            report.violations.append(
                Violation(
                    "PI-5",
                    "duplicate_realization",
                    f"{label} realized {got}x for {want} model object(s): {key!r}",
                )
            )

    for key, got in realized.items():
        if key in expected:
            continue
        if key in generated:
            # Declared, but not free: the projection is creating a semantic
            # object the model has nowhere to hold. Recorded on every document
            # where it fires so the debt stays visible (PI-6).
            report.findings.append(
                Violation(
                    "PI-6",
                    "renderer_generated_object",
                    f"{label} {key!r} is generated by the projection; no model object holds it",
                )
            )
            continue
        report.violations.append(
            Violation("PI-2", "invented_object", f"{label} in projection but not in model: {key!r}")
        )


def check_projection(
    document: Any, markdown: str, name: str = "", contract: Any = None
) -> ProjectionReport:
    """Verify a Markdown projection against the Semantic Document behind it.

    Returns a report; an empty ``violations`` list means every invariant in
    docs/ADR_PROJECTION_CORRECTNESS_2026-08-03.md §4 holds. Never raises on a
    violation - the caller decides whether a violation is a gate failure.
    """
    report = ProjectionReport(document=name or str(getattr(document, "source_pdf_path", "") or "?"))
    contract = contract if contract is not None else _MARKDOWN_CONTRACT
    realized = _parse_markdown(markdown)

    headings = getattr(document, "headings", []) or []
    content_headings = Counter(_norm(h.text) for h in headings if not h.is_page_marker)
    markers = Counter(_norm(h.text) for h in headings if h.is_page_marker)

    _check_set(
        report,
        "heading",
        content_headings,
        Counter(realized.headings),
        authorized_absent=_authorized_absent_headings(document),
        contract=contract,
    )
    _check_set(report, "page marker", markers, Counter(realized.markers))
    _check_set(
        report,
        "table",
        Counter(t.table_id for t in getattr(document, "tables", []) or [] if t.rows),
        Counter(realized.table_ids),
    )
    _check_set(
        report,
        "list",
        Counter(str(lst.id) for lst in getattr(document, "lists", []) or [] if lst.items),
        Counter(realized.list_ids),
    )
    _check_set(
        report,
        "image",
        Counter(
            str(i.file_path)
            for i in getattr(document, "images", []) or []
            if not i.extraction_failed
        ),
        Counter(realized.image_paths),
    )
    _check_set(
        report,
        "note definition",
        Counter(n.label for n in getattr(document, "footnotes", []) or []),
        Counter(realized.note_labels),
    )

    # PI-3, both directions.
    invented = realized.words - _model_words(document)
    if invented:
        report.violations.append(
            Violation(
                "PI-3",
                "content_invention",
                f"{sum(invented.values())} word(s) in projection with no source in the model: "
                f"{dict(list(invented.items())[:8])}",
            )
        )
    lost = _visible_block_words(document) - realized.words
    if lost:
        report.violations.append(
            Violation(
                "PI-3",
                "content_loss",
                f"{sum(lost.values())} word(s) of extracted text absent from the projection "
                f"with no authorizing fact: {dict(list(lost.items())[:8])}",
            )
        )

    _check_absorption_backed(document, report)

    report.counts = {
        "model_headings": sum(content_headings.values()),
        "realized_headings": len(realized.headings),
        "model_page_markers": sum(markers.values()),
        "realized_page_markers": len(realized.markers),
        "model_tables": len(getattr(document, "tables", []) or []),
        "realized_tables": len(realized.table_ids),
        "model_images": len(getattr(document, "images", []) or []),
        "realized_images": len(realized.image_paths),
        "model_notes": len(getattr(document, "footnotes", []) or []),
        "realized_notes": len(realized.note_labels),
        "projection_words": sum(realized.words.values()),
    }
    return report


def summarize(reports: List[ProjectionReport]) -> Dict[str, Any]:
    """Corpus roll-up. ``ok`` is the gate: one violation anywhere fails it."""
    kinds: Dict[str, int] = {}
    finding_kinds: Dict[str, int] = {}
    for r in reports:
        for k, n in r.by_kind().items():
            kinds[k] = kinds.get(k, 0) + n
        for f in r.findings:
            finding_kinds[f.kind] = finding_kinds.get(f.kind, 0) + 1
    return {
        "schema": "rawrs.projection-correctness/v1",
        "document_count": len(reports),
        "ok": all(r.ok for r in reports),
        "documents_with_violations": sum(0 if r.ok else 1 for r in reports),
        "violations_by_kind": kinds,
        # Non-blocking. Layer 2 - detector defects and renderer-owned
        # decisions that PI-6 says should move into the model.
        "findings_by_kind": finding_kinds,
        "documents": [r.to_dict() for r in reports],
    }


# --- DOCX note materialization (L4b) -----------------------------------------
#
# A second projection, checked the same way and for the same reason. The
# Markdown check above asks whether every note *definition* survives; this
# asks whether every note survives **as the kind of note the model says it
# is**. They are different questions because Markdown has one note syntax and
# Word has two parts, and for the whole life of this codebase before L4b the
# DOCX projection had only one of them: every endnote was written into
# word/footnotes.xml as a w:footnoteReference, and Word rendered a document's
# endnotes at the foot of its pages. Nothing failed, nothing was logged, and
# the benchmark's 54 gold endnotes were being compared against 54 RAWRS
# footnotes.
#
# The invariant is deliberately stated over the OOXML package rather than over
# generate_docx()'s inputs: the package is what a reader opens, and reading it
# back is the only evidence that cannot be satisfied by the renderer agreeing
# with itself.

_DOCX_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_DOCX_FOOTNOTES_PART = "word/footnotes.xml"
_DOCX_ENDNOTES_PART = "word/endnotes.xml"
# Word's own separator entries, present in both parts and belonging to no
# Footnote in the model.
_DOCX_STRUCTURAL_NOTE_TYPES = frozenset({"separator", "continuationSeparator"})


def _docx_note_bodies(zf: Any, part: str, tag: str) -> List[str]:
    """Every real note body in one part, in document order."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(zf.read(part))
    except KeyError:
        return []
    w = "{%s}" % _DOCX_W
    bodies = []
    for el in root.iter(w + tag):
        if el.get(w + "type") in _DOCX_STRUCTURAL_NOTE_TYPES:
            continue
        bodies.append(_norm("".join(t.text or "" for t in el.iter(w + "t"))))
    return bodies


def check_docx_notes(document: Any, docx_path: Any, name: str = "") -> ProjectionReport:
    """PI-6 · every note is materialized as the kind of note it is.

    Three claims, each checked against the generated package itself:

    * every ``NoteType.ENDNOTE`` appears in ``word/endnotes.xml``
    * no ``NoteType.ENDNOTE`` appears in ``word/footnotes.xml``
    * no ``NoteType.FOOTNOTE`` appears in ``word/endnotes.xml``

    Matching is by normalized body text, because that is the one thing the
    model and the package independently agree on: OOXML ``w:id`` values are
    per-part plumbing assigned by the renderer, and ``Footnote.label`` is
    consumed by the renderer rather than written into the part. A note whose
    body text does not survive at all is a lost object under PI-1 and is
    reported as one here.
    """
    import zipfile

    report = ProjectionReport(
        document=name or str(getattr(document, "source_pdf_path", "") or "?")
    )
    notes = list(getattr(document, "footnotes", []) or [])
    if not notes:
        report.counts["notes"] = 0
        return report

    with zipfile.ZipFile(str(docx_path)) as zf:
        in_footnotes = _docx_note_bodies(zf, _DOCX_FOOTNOTES_PART, "footnote")
        in_endnotes = _docx_note_bodies(zf, _DOCX_ENDNOTES_PART, "endnote")

    def _present(body: str, bodies: List[str]) -> bool:
        # The renderer prefixes a separating space onto the body run, and
        # Word's auto-number mark contributes no w:t, so an exact normalized
        # equality is right - containment would let a truncated body pass.
        return _norm(body) in bodies

    for note in notes:
        is_endnote = str(getattr(note.note_type, "value", note.note_type)) == "endnote"
        want, wrong = (
            (in_endnotes, in_footnotes) if is_endnote else (in_footnotes, in_endnotes)
        )
        want_part = _DOCX_ENDNOTES_PART if is_endnote else _DOCX_FOOTNOTES_PART
        wrong_part = _DOCX_FOOTNOTES_PART if is_endnote else _DOCX_ENDNOTES_PART
        label = getattr(note, "label", "?")

        if _present(note.body, wrong):
            report.violations.append(
                Violation(
                    "PI-6",
                    "wrong_note_part",
                    f"note {label} is a {note.note_type} but was materialized in {wrong_part}",
                )
            )
        elif not _present(note.body, want):
            report.violations.append(
                Violation(
                    "PI-6",
                    "lost_object",
                    f"note {label} ({note.note_type}) is absent from {want_part}",
                )
            )

    report.counts.update(
        {
            "notes": len(notes),
            "footnotes_part": len(in_footnotes),
            "endnotes_part": len(in_endnotes),
        }
    )
    return report


# --- Front matter in the traversal (L5'a) -------------------------------------
#
# Front matter was the last detected content the ContentStream could not carry,
# and the reason was structural: ContentNode holds the id of the object it
# points at, and a title or byline had no id — FrontMatter stored bare strings.
# The Markdown projection compensated by deciding the rendering itself, which
# its own PROJECTION_CONTRACT declared as a limitation.
#
# This checks the five properties that make the fix real rather than cosmetic.
# Property 5 is the one that would catch a regression to text-keyed placement:
# two items with identical text must resolve to different blocks, which a text
# key cannot do and a recorded source_block_id does for free.

_FRONT_MATTER_ROLES = ("title", "author", "affiliation")


def check_front_matter_stream(document: Any, name: str = "") -> ProjectionReport:
    """PI-7 · every front-matter item is placed once, by recorded identity.

    * identity — every item has a stable, unique ``id``
    * position — every item records a ``source_block_id`` that names a real block
    * presence — every placeable item appears in the stream exactly once
    * role     — the item's role survives onto the object the node points at
    * ordering — stream order follows the recorded blocks, not the text

    An item with no ``source_block_id`` is a *finding*, not a violation: the
    Mathpix path records no position in the PDF at all, and calling that a
    projection defect would blame the renderer for what the provider never
    supplied.
    """
    from src.structure.content_stream import build_content_stream
    from src.models.content_stream import ContentKind

    report = ProjectionReport(
        document=name or str(getattr(document, "source_pdf_path", "") or "?")
    )
    front_matter = getattr(document, "front_matter", None)
    items = list(getattr(front_matter, "items", []) or []) if front_matter else []
    if not items:
        report.counts["front_matter_items"] = 0
        return report

    block_ids = {b.block_id for b in (getattr(document, "blocks", []) or [])}
    ids = [str(item.id) for item in items]
    if len(set(ids)) != len(ids):
        report.violations.append(
            Violation("PI-7", "duplicate", "front-matter items share an id")
        )

    placeable = []
    for item in items:
        if not str(item.id):
            report.violations.append(
                Violation("PI-7", "lost_object", f"front-matter {item.role} has no id")
            )
            continue
        if item.role.value not in _FRONT_MATTER_ROLES:
            report.violations.append(
                Violation("PI-7", "invented_object", f"unknown front-matter role {item.role}")
            )
        if not item.source_block_id:
            report.findings.append(
                Violation(
                    "PI-7",
                    "no_recorded_position",
                    f"front-matter {item.role.value} {str(item.id)!r} records no source block, "
                    "so the traversal cannot place it",
                )
            )
            continue
        if item.source_block_id not in block_ids:
            report.violations.append(
                Violation(
                    "PI-7",
                    "lost_object",
                    f"front-matter {str(item.id)!r} names block {item.source_block_id!r}, "
                    "which is not in the document",
                )
            )
            continue
        placeable.append(item)

    nodes = [
        node
        for node in build_content_stream(document).nodes
        if node.kind is ContentKind.FRONT_MATTER
    ]
    node_ids = [node.object_id for node in nodes]
    for item in placeable:
        seen = node_ids.count(str(item.id))
        if seen == 0:
            report.violations.append(
                Violation("PI-7", "lost_object", f"front-matter {str(item.id)!r} is not in the stream")
            )
        elif seen > 1:
            report.violations.append(
                Violation("PI-7", "duplicate", f"front-matter {str(item.id)!r} appears {seen} times")
            )

    # A front-matter block must not also be emitted as body text: the same
    # line cannot be two things, and this is how it would silently become so.
    body_ids = {
        node.object_id
        for node in build_content_stream(document).nodes
        if node.kind is ContentKind.BODY_LINE
    }
    for item in placeable:
        if item.source_block_id in body_ids:
            report.violations.append(
                Violation(
                    "PI-7",
                    "duplicate",
                    f"front-matter {str(item.id)!r}'s block is also a body line",
                )
            )

    report.counts.update(
        {
            "front_matter_items": len(items),
            "placeable": len(placeable),
            "in_stream": len(nodes),
        }
    )
    return report


# --------------------------------------------------------------------------- #
# PI-8 · paragraph stream integrity
# --------------------------------------------------------------------------- #
#
# Prose was the last detected content the ContentStream restated instead of
# naming: 95% of its BODY_LINE nodes (7,474 of 7,859 corpus blocks) were source
# lines the model had already grouped into Paragraphs, so the traversal
# disagreed with the document about what its own content was.
#
# The properties below are what make PARAGRAPH nodes a semantic reference
# rather than a second text representation. Exclusivity is the one that would
# catch a regression to line-level duplication, and distinctness the one that
# would catch a regression to text-keyed identity — two paragraphs reading
# identically must still be two nodes.


def check_paragraph_stream(document: Any, name: str = "") -> ProjectionReport:
    """PI-8 · every placeable paragraph is in the traversal exactly once.

    * identity     — every paragraph has a stable, unique ``id``
    * presence     — every placeable paragraph appears exactly once
    * reference    — ``node.object_id`` is that id, and carries no text
    * exclusivity  — no paragraph-owned block is also a ``BODY_LINE``
    * ordering     — placement follows the first source block's effective
                     reading order, so a reviewer's ``corrected_order``
                     moves the paragraph with its opening line
    * distinctness — identical prose still yields distinct nodes

    **Placeable** means the paragraph records ``source_block_ids`` whose
    entries resolve to real blocks in this document. A paragraph with no
    recorded block is a *finding*, not a violation: the Mathpix import
    path positions by ``source_line`` in a coordinate system this
    traversal does not share, and calling that a defect would blame the
    traversal for what the provider never supplied. A paragraph naming a
    block the document does not have is a violation — a broken edge, not
    a missing one.
    """
    from src.models.content_stream import ContentKind
    from src.structure.content_stream import build_content_stream

    report = ProjectionReport(
        document=name or str(getattr(document, "source_pdf_path", "") or "?")
    )
    paragraphs = list(getattr(document, "paragraphs", []) or [])
    if not paragraphs:
        report.counts["paragraphs"] = 0
        return report

    blocks = getattr(document, "blocks", []) or []
    block_ids = {b.block_id for b in blocks}

    ids = [str(p.id) for p in paragraphs if p.id]
    if len(set(ids)) != len(ids):
        report.violations.append(Violation("PI-8", "duplicate", "paragraphs share an id"))

    placeable = []
    owned: Dict[str, str] = {}  # block id -> the paragraph id that owns it
    for paragraph in paragraphs:
        if not paragraph.id:
            report.violations.append(
                Violation(
                    "PI-8",
                    "lost_object",
                    f"paragraph on page {paragraph.page_number} has no id",
                )
            )
            continue
        if not paragraph.source_block_ids:
            report.findings.append(
                Violation(
                    "PI-8",
                    "no_recorded_position",
                    f"paragraph {str(paragraph.id)!r} records no source block, "
                    "so the traversal cannot place it",
                )
            )
            continue
        unknown = [b for b in paragraph.source_block_ids if b not in block_ids]
        if unknown:
            report.violations.append(
                Violation(
                    "PI-8",
                    "lost_object",
                    f"paragraph {str(paragraph.id)!r} names block(s) {unknown!r} "
                    "which are not in the document",
                )
            )
            continue
        for block_id in paragraph.source_block_ids:
            prior = owned.get(block_id)
            if prior is not None:
                report.violations.append(
                    Violation(
                        "PI-8",
                        "duplicate",
                        f"block {block_id!r} is claimed by both {prior!r} "
                        f"and {str(paragraph.id)!r}",
                    )
                )
            owned[block_id] = str(paragraph.id)
        placeable.append(paragraph)

    nodes = build_content_stream(document).nodes
    paragraph_nodes = [n for n in nodes if n.kind is ContentKind.PARAGRAPH]
    node_ids = [n.object_id for n in paragraph_nodes]

    for paragraph in placeable:
        seen = node_ids.count(str(paragraph.id))
        if seen == 0:
            report.violations.append(
                Violation(
                    "PI-8", "lost_object", f"paragraph {str(paragraph.id)!r} is not in the stream"
                )
            )
        elif seen > 1:
            report.violations.append(
                Violation(
                    "PI-8", "duplicate", f"paragraph {str(paragraph.id)!r} appears {seen} times"
                )
            )

    known = {str(p.id) for p in placeable}
    for object_id in node_ids:
        if object_id not in known:
            report.violations.append(
                Violation(
                    "PI-8",
                    "invented_object",
                    f"stream holds paragraph node {object_id!r} with no placeable paragraph",
                )
            )

    # Exclusivity: a line a paragraph absorbed must not also stand alone.
    body_ids = {n.object_id for n in nodes if n.kind is ContentKind.BODY_LINE}
    for block_id, paragraph_id in sorted(owned.items()):
        if block_id in body_ids:
            report.violations.append(
                Violation(
                    "PI-8",
                    "duplicate",
                    f"block {block_id!r} is inside paragraph {paragraph_id!r} "
                    "and is also emitted as a body line",
                )
            )

    # Ordering: the node sits at its first block's effective position, so
    # paragraphs must appear in the same relative order as those blocks.
    effective = {
        b.block_id: (b.corrected_order if b.corrected_order is not None else b.order)
        for b in blocks
    }
    by_id = {str(p.id): p for p in placeable}
    for page_number in sorted({n.page_number for n in paragraph_nodes}):
        page_nodes = [n for n in paragraph_nodes if n.page_number == page_number]
        expected = [
            n.object_id
            for n in sorted(
                page_nodes, key=lambda n: effective[by_id[n.object_id].source_block_ids[0]]
            )
        ]
        if [n.object_id for n in sorted(page_nodes, key=lambda n: n.order)] != expected:
            report.violations.append(
                Violation(
                    "PI-8",
                    "content_loss",
                    f"page {page_number}: paragraph order does not follow the "
                    "effective reading order of their first blocks",
                )
            )

    report.counts.update(
        {
            "paragraphs": len(paragraphs),
            "placeable": len(placeable),
            "in_stream": len(paragraph_nodes),
            "owned_blocks": len(owned),
            "body_line_nodes": len(body_ids),
        }
    )
    return report


# --------------------------------------------------------------------------- #
# PI-9 · the projection consumes the stream's paragraphs
# --------------------------------------------------------------------------- #
#
# PI-8 proves the traversal holds every paragraph once. PI-9 proves the
# Markdown projection *renders what the traversal handed it* — one paragraph
# per PARAGRAPH node, in the stream's order, carrying the text the semantic
# object carries. Without it P3b could regress to rediscovering prose from
# lines while the stream still looked correct, which is the split-brain
# ADR-020 exists to prevent.
#
# The check reads rendered Markdown, so it compares by normalized text — the
# only handle a rendered format offers. That is a *verification* technique,
# not a placement one: the projection resolves paragraphs by id and never
# searches by text. Order is the property that catches a text-keyed
# regression, since two paragraphs reading identically must still land in
# their own stream positions.


def check_paragraph_projection(
    document: Any, markdown: str, name: str = ""
) -> ProjectionReport:
    """PI-9 · every stream PARAGRAPH becomes exactly one Markdown paragraph.

    * presence   — each PARAGRAPH node's ``Paragraph.text`` is rendered
    * uniqueness — rendered once, never twice
    * order      — rendered order equals stream order
    * provenance — the rendered prose is the paragraph's own text

    Pages with no ``TextBlock`` (an OCR-recovered page — 41 of the corpus'
    161) are rendered by the line-by-line fallback, which has no blocks to
    build a traversal from. Their paragraphs are reported as findings, not
    violations: the projection is obeying a documented limitation rather
    than losing an object.
    """
    from src.models.content_stream import ContentKind
    from src.structure.content_stream import build_content_stream

    report = ProjectionReport(
        document=name or str(getattr(document, "source_pdf_path", "") or "?")
    )
    paragraphs = {
        str(p.id): p for p in (getattr(document, "paragraphs", []) or []) if p.id is not None
    }
    if not paragraphs:
        report.counts["stream_paragraphs"] = 0
        return report

    pages_with_blocks = {b.page_number for b in (getattr(document, "blocks", []) or [])}
    nodes = [n for n in build_content_stream(document).nodes if n.kind is ContentKind.PARAGRAPH]

    expected: List[tuple] = []  # (paragraph id, normalized text) in stream order
    for node in nodes:
        paragraph = paragraphs.get(node.object_id)
        if paragraph is None:
            report.violations.append(
                Violation(
                    "PI-9",
                    "invented_object",
                    f"stream paragraph {node.object_id!r} resolves to no Paragraph",
                )
            )
            continue
        if node.page_number not in pages_with_blocks:
            report.findings.append(
                Violation(
                    "PI-9",
                    "renderer_generated_object",
                    f"paragraph {node.object_id!r} is on page {node.page_number}, which has "
                    "no blocks and is rendered by the line-by-line fallback",
                )
            )
            continue
        expected.append((node.object_id, _paragraph_probe(paragraph.text)))

    rendered = [_paragraph_probe(block) for block in _rendered_prose(markdown)]
    cursor = 0
    for object_id, text in expected:
        if not text:
            continue
        hit = next((i for i in range(cursor, len(rendered)) if text in rendered[i]), -1)
        if hit < 0:
            behind = any(text in block for block in rendered[:cursor])
            report.violations.append(
                Violation(
                    "PI-9",
                    "duplicate" if behind else "content_loss",
                    f"paragraph {object_id!r} is "
                    + ("rendered out of stream order" if behind else "not rendered"),
                )
            )
            continue
        cursor = hit + 1

    report.counts.update(
        {
            "stream_paragraphs": len(nodes),
            "expected_rendered": len(expected),
            "prose_blocks": len(rendered),
        }
    )
    return report


def _paragraph_probe(text: str) -> str:
    """A paragraph's text reduced to what survives being rendered.

    The projection legitimately decorates prose on its way out: 016G wraps
    a uniformly bold or italic paragraph in ``**``/``*``, and a footnote
    anchor's printed marker is replaced by ``[^label]``. So the rendered
    block is not ``Paragraph.text`` character for character, and a checker
    demanding that would report every noted paragraph as lost — measured:
    3 of brinkman's, each differing only by the digit that became a note
    reference.

    Emphasis characters and digits are therefore dropped from *both*
    sides. Digits are safe to drop symmetrically: prose digits appear on
    both sides and cancel, while a substituted marker appears on only one.
    What remains is enough to say which paragraph a block is, which is all
    PI-9 asks. Whether the words themselves survived is PI-3's question.
    """
    return _norm(re.sub(r"[\d*]", "", text or ""))


def _rendered_prose(markdown: str) -> List[str]:
    """The Markdown's prose blocks, in order, normalized.

    Everything that is not body prose is dropped: page markers, headings,
    note definitions, table and list rows, image references and the
    pagebreak marker. What remains is what a paragraph could have produced.
    """
    out: List[str] = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = _IMAGE.sub(" ", line)
        line = _HTML_COMMENT.sub(" ", line).strip()
        if not line or _NOTE_DEF.match(line):
            continue
        if _PAGE_MARKER.match(line) or _CONTENT_HEADING.match(line):
            continue
        if line.startswith("|") or line.startswith("- ") or line.startswith("* "):
            continue
        normalized = _norm(_NOTE_REF.sub(" ", line))
        if normalized:
            out.append(normalized)
    return out


# --------------------------------------------------------------------------- #
# PI-10 · the DOCX projection consumes the stream's prose
# --------------------------------------------------------------------------- #
#
# PI-8 proves the traversal holds every paragraph once; PI-9 proves the Markdown
# projection renders what the traversal handed it. PI-10 makes the same claim
# for DOCX, which until P4b recovered its structure by re-reading the Markdown
# that PI-9 checks — so a regression there would have shown up as *nothing*,
# both projections agreeing because one was reading the other.
#
# Expectations are derived here from the stream and the two documented filters
# (absorbed-beats-heading, and the front-matter title FE-0-005), not from the
# renderer's own plan: a checker that asked the renderer what it meant to do
# could only ever confirm it did that.
#
# Resolution is by identity; the comparison against the package is by text,
# because a .docx keeps no object ids. Order is what catches a text-keyed
# regression, since two paragraphs reading identically must still land in their
# own stream positions.


def _docx_body_items(docx_path: Any) -> List[tuple]:
    """(heading level or None, normalized text, is-list-styled) per paragraph."""
    import xml.etree.ElementTree as ET
    import zipfile

    w = "{%s}" % _DOCX_W
    items: List[tuple] = []
    with zipfile.ZipFile(str(docx_path)) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    body = root.find(w + "body")
    for paragraph in [] if body is None else body.findall(w + "p"):
        text = _norm("".join(t.text or "" for t in paragraph.iter(w + "t")))
        if not text:
            continue
        style = paragraph.find(f"{w}pPr/{w}pStyle")
        name = style.get(w + "val") if style is not None else ""
        level = None
        if name and name.lower().startswith("heading"):
            digits = "".join(c for c in name if c.isdigit())
            level = int(digits) if digits else None
        items.append((level, text, bool(name) and "List" in name))
    return items


def check_docx_projection(document: Any, docx_path: Any, name: str = "") -> ProjectionReport:
    """PI-10 · every stream node DOCX consumes becomes one DOCX operation.

    * ``PAGE_MARKER`` -> one heading paragraph carrying the marker's text
    * ``HEADING``     -> one heading paragraph at ``Heading.level``
    * ``PARAGRAPH``   -> one body paragraph carrying ``Paragraph.text``
    * order           -> the traversal's, not the markdown's

    Pages with no ``TextBlock`` are reported as findings rather than
    violations: with no blocks the traversal places no paragraph, so DOCX
    keeps rendering them from the markdown lines — the declared P4b
    limitation, obeyed rather than a lost object.
    """
    from src.models.content_stream import ContentKind
    from src.structure.content_stream import build_content_stream

    report = ProjectionReport(
        document=name or str(getattr(document, "source_pdf_path", "") or "?")
    )
    headings = {str(h.id): h for h in (getattr(document, "headings", []) or [])}
    paragraphs = {
        str(p.id): p
        for p in (getattr(document, "paragraphs", []) or [])
        if p.id is not None
    }
    if not paragraphs:
        report.counts["stream_prose"] = 0
        return report

    blocks_by_page: Dict[int, list] = {}
    for block in getattr(document, "blocks", []) or []:
        blocks_by_page.setdefault(block.page_number, []).append(block)
    absorbed = {
        page: absorbed_block_ids(document, page, page_blocks)
        for page, page_blocks in blocks_by_page.items()
    }
    front_matter = getattr(document, "front_matter", None)
    title = getattr(front_matter, "title", None) if front_matter is not None else None

    nodes = build_content_stream(document).nodes
    pages_with_prose = {
        node.page_number
        for node in nodes
        if node.kind is ContentKind.PARAGRAPH and node.object_id in paragraphs
    } & set(blocks_by_page)

    expected: List[tuple] = []  # (object id, heading level or None, probe text)
    for node in nodes:
        if node.page_number not in pages_with_prose:
            if node.kind in (ContentKind.PARAGRAPH, ContentKind.HEADING):
                report.findings.append(
                    Violation(
                        "PI-10",
                        "renderer_generated_object",
                        f"{node.kind.value} {node.object_id!r} is on page "
                        f"{node.page_number}, which DOCX renders from markdown lines",
                    )
                )
            continue
        if node.kind is ContentKind.PARAGRAPH:
            paragraph = paragraphs.get(node.object_id)
            if paragraph is None:
                report.violations.append(
                    Violation(
                        "PI-10",
                        "invented_object",
                        f"stream paragraph {node.object_id!r} resolves to no Paragraph",
                    )
                )
                continue
            expected.append((node.object_id, None, _paragraph_probe(paragraph.text)))
        elif node.kind in (ContentKind.HEADING, ContentKind.PAGE_MARKER):
            heading = headings.get(node.object_id)
            if heading is None:
                continue
            if node.kind is ContentKind.HEADING:
                if title is not None and heading.text == title:
                    continue
                if heading.source_block_id in absorbed.get(node.page_number, ()):
                    continue
            expected.append((node.object_id, heading.level.value, _norm(heading.text)))

    # Prose is compared through the same probe PI-9 uses: DOCX replaces a
    # note's printed marker with a reference run that contributes no text, so
    # a rendered paragraph is never ``Paragraph.text`` character for
    # character. Headings carry no markers and are compared as they are.
    rendered = [
        (level, text, _paragraph_probe(text), is_list)
        for level, text, is_list in _docx_body_items(docx_path)
    ]
    cursor = 0
    for object_id, level, text in expected:
        if not text:
            continue
        # Exact first, containment only if nothing matches exactly. A page's
        # running header survives OCR as several near-identical garbled
        # lines, and a substring match against the first of them would claim
        # the wrong paragraph and drag the cursor past the right one.
        hit = -1
        for exact_only in (True, False):
            for position in range(cursor, len(rendered)):
                candidate_level, candidate_text, candidate_probe, is_list = rendered[position]
                if level is not None:
                    if candidate_level == level and text == candidate_text:
                        hit = position
                        break
                    continue
                if candidate_level is not None or not candidate_probe:
                    continue
                if text == candidate_probe:
                    hit = position
                    break
                if exact_only:
                    continue
                # A list-styled paragraph renders without its own marker —
                # Word draws the bullet or number, so repeating the source
                # one would double it (FEATURE_016C). Containment therefore
                # runs the other way for those, and only for those.
                if text in candidate_probe or (is_list and candidate_probe in text):
                    hit = position
                    break
            if hit >= 0:
                break
        if hit < 0:
            behind = any(
                text in (probe if level is None else body)
                for body_level, body, probe, _ in rendered[:cursor]
                if (level is None) == (body_level is None)
            )
            report.violations.append(
                Violation(
                    "PI-10",
                    "duplicate" if behind else "content_loss",
                    f"{'heading' if level else 'paragraph'} {object_id!r} is "
                    + ("rendered out of stream order" if behind else "not rendered"),
                )
            )
            continue
        cursor = hit + 1

    report.counts.update(
        {
            "stream_prose": len(expected),
            "docx_body_items": len(rendered),
            "pages_from_stream": len(pages_with_prose),
        }
    )
    return report


# --------------------------------------------------------------------------- #
# PI-11 · the DOCX projection consumes the stream's tables
# --------------------------------------------------------------------------- #
#
# P4c-1. DOCX used to learn which Table it was rendering from a
# ``<!-- table-id: ... -->`` comment in the markdown, and learn that a table was
# there at all by accumulating pipe rows. The grid it then rendered came from the
# model — so the identity was real but its *transport* was a rendered string, and
# a renderer that stopped emitting the comment would silently fall back to
# parsing pipes.
#
# PI-11 states the claim by identity: one Table, one TABLE node, one rendered
# table, in the traversal's order, with none of the table's own source lines
# also appearing as prose. The last of those is the part no count can catch —
# 277 of the corpus' 385 BODY_LINE nodes are table-owned, and a projection that
# rendered them as paragraphs would still produce the right number of tables.


def _docx_tables(docx_path: Any) -> List[List[str]]:
    """Each body table's cell text, in document order."""
    import xml.etree.ElementTree as ET
    import zipfile

    w = "{%s}" % _DOCX_W
    with zipfile.ZipFile(str(docx_path)) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    body = root.find(w + "body")
    tables: List[List[str]] = []
    for table in [] if body is None else body.findall(w + "tbl"):
        cells = []
        for row in table.findall(w + "tr"):
            for cell in row.findall(w + "tc"):
                cells.append(_norm("".join(t.text or "" for t in cell.iter(w + "t"))))
        tables.append(cells)
    return tables


def check_table_projection(document: Any, docx_path: Any, name: str = "") -> ProjectionReport:
    """PI-11 · every Table is one node, rendered once, in stream order.

    * completeness — every ``Table`` has exactly one ``TABLE`` node
    * resolution   — every ``TABLE`` node names a ``Table`` that exists
    * uniqueness   — the package holds exactly as many tables as nodes
    * order        — rendered order equals traversal order
    * containment  — no table-owned ``TextBlock`` also renders as a paragraph

    Cell text is how a rendered table is recognised, because a ``.docx`` keeps
    no object ids; the *resolution* above it is by ``Table.table_id`` alone.
    """
    from src.models.content_stream import ContentKind
    from src.structure.content_stream import build_content_stream

    report = ProjectionReport(
        document=name or str(getattr(document, "source_pdf_path", "") or "?")
    )
    tables = {str(t.table_id): t for t in (getattr(document, "tables", []) or [])}
    nodes = [n for n in build_content_stream(document).nodes if n.kind is ContentKind.TABLE]
    if not tables and not nodes:
        report.counts["tables"] = 0
        return report

    seen = Counter(n.object_id for n in nodes)
    for table_id in tables:
        if seen[table_id] == 0:
            report.violations.append(
                Violation("PI-11", "lost_object", f"table {table_id!r} is not in the stream")
            )
        elif seen[table_id] > 1:
            report.violations.append(
                Violation(
                    "PI-11", "duplicate", f"table {table_id!r} appears {seen[table_id]} times"
                )
            )
    for node in nodes:
        if node.object_id not in tables:
            report.violations.append(
                Violation(
                    "PI-11",
                    "invented_object",
                    f"stream table {node.object_id!r} resolves to no Table",
                )
            )

    expected = [
        [
            _norm(cell.text)
            for row in tables[n.object_id].rows
            for cell in row.cells
        ]
        for n in nodes
        if n.object_id in tables
    ]
    rendered = _docx_tables(docx_path)
    if len(rendered) != len(expected):
        report.violations.append(
            Violation(
                "PI-11",
                "content_loss" if len(rendered) < len(expected) else "invented_object",
                f"{len(expected)} table(s) in the stream, {len(rendered)} in the package",
            )
        )
    else:
        for position, (want, got) in enumerate(zip(expected, rendered)):
            # A cell the model holds but the package does not is a real loss;
            # the package may hold extra empty cells where a row was short of
            # Table.col_count, which _add_semantic_table pads deliberately.
            missing = [c for c in want if c and c not in got]
            if missing:
                report.violations.append(
                    Violation(
                        "PI-11",
                        "content_loss",
                        f"table at stream position {position} is missing "
                        f"{len(missing)} cell(s), e.g. {missing[0]!r}",
                    )
                )

    # Containment, by ownership rather than by text. A table's source line
    # leaks only if a *Paragraph* also claims that block, because a paragraph
    # is the only thing the projection renders as prose. Comparing rendered
    # strings instead would be meaningless here: a table cell reading "6"
    # matches any short paragraph anywhere in the document, and on the corpus
    # that alone produced 22 phantom leaks against 0 real ones.
    paragraph_blocks = {
        block_id
        for paragraph in (getattr(document, "paragraphs", []) or [])
        for block_id in (getattr(paragraph, "source_block_ids", []) or [])
    }
    leaked = 0
    for table_id, table in tables.items():
        for block_id in getattr(table, "source_block_ids", []) or []:
            if block_id in paragraph_blocks:
                leaked += 1
                report.violations.append(
                    Violation(
                        "PI-11",
                        "duplicate",
                        f"table {table_id!r} source line {block_id!r} is also claimed "
                        "by a Paragraph, so it renders twice",
                    )
                )

    report.counts.update(
        {
            "tables": len(tables),
            "table_nodes": len(nodes),
            "rendered_tables": len(rendered),
            "table_source_blocks": sum(
                len(getattr(t, "source_block_ids", []) or []) for t in tables.values()
            ),
            "leaked_source_blocks": leaked,
        }
    )
    return report
