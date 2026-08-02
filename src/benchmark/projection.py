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

# Headings a projection creates that no model object holds. Exhaustive and
# named on purpose: each entry is a renderer-owned semantic decision that
# PI-6 says should eventually move into the model, so the list is the
# outstanding-debt register, not an escape hatch. Every entry is reported as
# a non-blocking finding on every document where it fires.
_GENERATED_HEADINGS = {"Endnotes"}


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

def _authorized_absent_headings(document: Any) -> Set[str]:
    """Headings a projection may legitimately not emit as a heading.

    Two documented rules, both recorded in the model rather than decided at
    render time:

      * the front-matter title - rendered as the front-matter block instead,
        so the H1 deliberately does not compete with it (FE-0-005);
      * a heading whose anchor block some other object absorbed (a table cell,
        the endnotes section line) - absorbed beats heading, by ADR §3.

    Anything else missing is a lost object.
    """
    absent: Set[str] = set()
    fm = getattr(document, "front_matter", None)
    if fm is not None and fm.title:
        absent.add(_norm(fm.title))

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
                absent.add(_norm(h.text))
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
    authorized_absent: Optional[Set[str]] = None,
) -> None:
    """PI-1 / PI-2 / PI-5 for one object type, by identity."""
    authorized_absent = authorized_absent or set()
    for key, want in expected.items():
        got = realized.get(key, 0)
        if got == 0 and key not in authorized_absent:
            report.violations.append(
                Violation("PI-1", "lost_object", f"{label} in model but not in projection: {key!r}")
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
        if label == "heading" and key in _GENERATED_HEADINGS:
            # Authorized, but not free: the renderer is creating a semantic
            # object the model has nowhere to hold. Recorded on every document
            # where it fires so the debt stays visible (PI-6).
            report.findings.append(
                Violation(
                    "PI-6",
                    "renderer_generated_object",
                    f"heading {key!r} is generated by the projection; no model object holds it",
                )
            )
            continue
        report.violations.append(
            Violation("PI-2", "invented_object", f"{label} in projection but not in model: {key!r}")
        )


def check_projection(document: Any, markdown: str, name: str = "") -> ProjectionReport:
    """Verify a Markdown projection against the Semantic Document behind it.

    Returns a report; an empty ``violations`` list means every invariant in
    docs/ADR_PROJECTION_CORRECTNESS_2026-08-03.md §4 holds. Never raises on a
    violation - the caller decides whether a violation is a gate failure.
    """
    report = ProjectionReport(document=name or str(getattr(document, "source_pdf_path", "") or "?"))
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
