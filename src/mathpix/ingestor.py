"""Mathpix import provider for RAWRS.

Implements the ImportProvider protocol (src/importers/base.py).
Consumes a Mathpix MMD file and enriches a Document shell (produced by
parse_pdf()) with headings, text, tables, footnotes, and front matter
that Mathpix extracted.

Ownership model
===============
* Mathpix is the **extraction provider** — it owns the initial text,
  headings, tables, footnotes, and front matter values.
* The RAWRS **Document model** is the canonical representation — all
  downstream pipeline stages read from and write to Document only, never
  from the raw MMD.
* The original PDF is the **verification source** — used by later
  pipeline stages to cross-check Mathpix's extraction; never for initial
  content.
* This module does **not** verify, correct, or modify Mathpix's content.
  That is the Verification Engine's responsibility (Phase M-2 / M-3).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, List, Optional

from loguru import logger

from src.frontmatter.front_matter_roles import build_title_heading
from src.headings.page_markers import build_page_marker
from src.mathpix.mmd_parser import parse_mmd
from src.mathpix.page_alignment import PageAlignment, align_blocks_to_pages
from src.mathpix.page_estimation import estimate_page
from src.models.contracts import (
    Callout,
    Document,
    ExtractionMethod,
    Footnote,
    FrontMatter,
    Heading,
    HeadingLevel,
    NoteType,
    OCRConfidence,
    Paragraph,
    Table,
    TableCell,
    TableRow,
    TableStatus,
)
from src.models.list_block import ListBlock, ListItem, ListType
from src.models.phase2_document import (
    P2BlockType,
    P2Footnote,
    P2Heading,
    P2ListStyle,
    P2Table,
)
from src.models.semantic_object import ProvenanceSource
from src.parser.pdf_parser import PDFParserError, page_text_layer


def _align_to_pdf_pages(document: Document, p2doc: Any) -> Optional[PageAlignment]:
    """The page evidence for this import, or None to keep the estimator.

    P-1 C3. The MMD states block order; the PDF that arrived with it states
    which page each block's text is on. ``page_alignment`` turns the second
    into evidence, and this is where the import asks for it.

    None means "no usable evidence" and is returned for every case where the
    evidence does not hold up: no PDF path, an unreadable PDF, a pure scan
    whose pages carry no text layer, or an alignment the module rejected
    because its anchors contradicted each other. All of them collapse to the
    same behaviour — the document keeps ``estimate_page`` exactly as before,
    whole, never half-applied.
    """
    source = getattr(document, "source_pdf_path", None)
    if not source:
        return None
    try:
        page_texts = page_text_layer(Path(source))
    except (FileNotFoundError, PDFParserError) as exc:
        logger.warning("Mathpix page alignment: PDF text layer unavailable ({})", exc)
        return None

    alignment = align_blocks_to_pages(p2doc.blocks, page_texts)
    logger.info(
        "Mathpix page alignment: {} ({} anchor(s), {} ambiguous, {} short, "
        "{} backwards, {} unmatched over {} page(s))",
        alignment.status.value,
        alignment.accepted,
        alignment.rejected_ambiguous,
        alignment.rejected_short,
        alignment.rejected_backwards,
        alignment.unmatched,
        alignment.page_count,
    )
    return alignment if alignment.usable else None


def _resolved_page(
    source_line: Optional[int],
    total_blocks: int,
    page_count: int,
    alignment: Optional[PageAlignment] = None,
) -> int:
    """One block's page: proven where the PDF proves it, estimated otherwise.

    Every page assignment on this path goes through here, so the rule is
    stated once: the estimator still runs, and the evidence either replaces
    its answer (a block anchored to one page) or constrains it (a block known
    only to lie between two anchors). No alignment, no change — the default
    is exactly the call this function replaced.
    """
    estimate = estimate_page(source_line, total_blocks, page_count)
    if alignment is None:
        return estimate
    return alignment.resolve_page(source_line, estimate)


class MathpixImportProvider:
    """Import provider that ingests Mathpix MMD into the RAWRS Document model.

    Implements ImportProvider (src/importers/base.py) as a concrete class
    so it can be tested and used without loading the Protocol.

    Usage::

        document = parse_pdf(pdf_path)
        provider = MathpixImportProvider()
        document = provider.import_document(document, mmd_path=mmd_path)

    After this call, document.headings, document.front_matter,
    document.tables, document.footnotes, and each page's cleaned_text
    are populated from the MMD.  All Heading objects carry
    ``source="mathpix"``; all Footnote objects carry ``source="mathpix"``;
    tables carry ``extraction_source="mathpix"``.
    """

    @property
    def name(self) -> str:
        return "mathpix"

    def import_document(self, document: Document, **kwargs: Any) -> Document:
        """Enrich ``document`` with content from a Mathpix MMD file.

        Keyword args:
            mmd_path (Path | str): Path to the Mathpix MMD file.
                Handles double extensions (.mmd.mmd, .md.md) transparently.
            image_dir (Path | str | None): Directory of uploaded image files
                that accompanied the MMD. When supplied, every figure block
                in the MMD is matched against an uploaded file (and every
                uploaded file is registered even if unmatched) via the
                cross-source verification engine (src/verification/) — see
                that package for the matching/registration logic. When
                omitted, no figures are registered here (the RAWRS-native
                PDF image extractor remains the only source, unchanged).

        Returns:
            The same ``document`` with headings, page text, tables,
            footnotes, front_matter, and (when image_dir is supplied)
            images populated from the MMD.
        """
        mmd_path = Path(kwargs["mmd_path"])
        content = mmd_path.read_text(encoding="utf-8")
        p2doc = parse_mmd(content)

        page_count = max(len(document.pages), 1)
        total_blocks = max(len(p2doc.blocks), 1)

        logger.info(
            "Mathpix import: {} block(s), {} footnote(s) parsed from '{}'",
            len(p2doc.blocks),
            len(p2doc.footnotes),
            mmd_path.name,
        )

        # P-1 C3: asked once, consulted by every page assignment below.
        alignment = _align_to_pdf_pages(document, p2doc)

        # ── 1. Front matter ────────────────────────────────────────────
        if p2doc.front_matter:
            fm = p2doc.front_matter
            if fm.title or fm.authors:
                document.front_matter = FrontMatter(
                    title=fm.title,
                    authors=fm.authors or [],
                    affiliations=getattr(fm, "affiliation_list", []),
                )

        # ── 2. Headings (+ Callouts, FEATURE_019) ───────────────────────
        heading_order = 0
        callout_order = 0

        # FE-0-005: the document title becomes H1. Mathpix marks the
        # title with \title{}, not \section{}, so it never reached the
        # heading loop below and Mathpix documents had no H1 at all
        # (HEADING_002). The native path already promotes its title via
        # the H1 slot; this gives the Mathpix path the same result from
        # the same canonical source.
        title_heading = build_title_heading(
            document.front_matter, page_number=1, document_order=heading_order
        )
        if title_heading is not None:
            document.headings.append(title_heading)
            heading_order += 1
        for block in p2doc.blocks:
            if block.block_type == P2BlockType.HEADING and block.heading:
                page_num = _resolved_page(
                    block.source_line, total_blocks, page_count, alignment
                )
                h = _p2heading_to_heading(block.heading, page_num, heading_order, source_line=block.source_line)
                if h is not None:
                    document.headings.append(h)
                    heading_order += 1
                    if block.heading.callout_type:
                        document.callouts.append(
                            Callout(
                                callout_type=block.heading.callout_type,
                                label=h.text,
                                heading_id=h.id,
                                page_number=page_num,
                                document_order=callout_order,
                                provenance=ProvenanceSource.MATHPIX,
                                source_line=block.source_line,
                            )
                        )
                        callout_order += 1

        # ── 2b. Page markers (FE-0-004) ────────────────────────────────
        # Every page carries an H6 page marker in the canonical model,
        # exactly as detect_headings() produces for the native PDF path.
        # Built via the shared helper so the two ingestion paths cannot
        # diverge again.
        #
        # Without this, markdown output still LOOKED correct — the
        # renderer synthesizes a replacement marker when the model has
        # none — but Document.headings held no markers, so PAGE_001
        # reported every page as missing one and those phantom errors
        # drove the readiness score.
        #
        # Markers are appended after the content headings rather than
        # interleaved: the Mathpix renderer projects content by
        # source_line and resolves markers by page_number, so relative
        # document_order between the two groups does not affect output.
        for page in document.pages:
            marker = build_page_marker(page, document_order=heading_order)
            if marker is not None:
                document.headings.append(marker)
                heading_order += 1

        # ── 3. Page text (proportional distribution) ───────────────────
        _assign_page_text(document, p2doc, page_count, total_blocks, alignment)

        # ── 3b. Lists ──────────────────────────────────────────────────
        # Consecutive LIST_ITEM blocks are grouped into canonical
        # ListBlocks here (mirroring how headings are built directly,
        # not through engine.run_import — there is no second "uploaded
        # asset" source for either). Previously these blocks were routed
        # through _assign_page_text's _PARA_TYPES and flattened into
        # plain paragraph text — the exact "lists becoming paragraphs"
        # defect. ListVerifier (src/verification/lists.py) later recovers
        # any real PDF list Mathpix didn't even tag as a list at all.
        document.lists.extend(
            _group_list_items_to_lists(p2doc, page_count, total_blocks, alignment)
        )

        # ── 4. Footnotes ───────────────────────────────────────────────
        for p2fn in p2doc.footnotes:
            fn = _p2footnote_to_footnote(p2fn, page_count, total_blocks, alignment)
            if fn is not None:
                document.footnotes.append(fn)

        # ── 5. Tables ──────────────────────────────────────────────────
        table_count = 0
        for block in p2doc.blocks:
            if block.block_type == P2BlockType.TABLE and block.table:
                page_num = _resolved_page(
                    block.source_line, total_blocks, page_count, alignment
                )
                document.tables.append(
                    _p2table_to_table(block.table, page_num, source_line=block.source_line)
                )
                table_count += 1

        # ── 6. Figures (uploaded Mathpix package images) ───────────────
        # No matching/construction logic lives here — this only calls the
        # cross-source verification engine (src/verification/), which
        # dispatches to FigureAssetVerifier. Every uploaded image is
        # registered, matched or not; the engine never drops one.
        image_count = 0
        image_dir = kwargs.get("image_dir")
        if image_dir:
            image_count = self._register_figures(
                document, p2doc, Path(image_dir), page_count, total_blocks, alignment
            )

        logger.info(
            "Mathpix import complete: {} heading(s), {} table(s), {} footnote(s), {} image(s)",
            len(document.headings),
            table_count,
            len(document.footnotes),
            image_count,
        )
        return document

    @staticmethod
    def _register_figures(
        document: Document,
        p2doc: Any,
        image_dir: Path,
        page_count: int,
        total_blocks: int,
        alignment: Optional[PageAlignment] = None,
    ) -> int:
        from src.verification.engine import engine
        import src.verification.figures  # noqa: F401 - registers FigureAssetVerifier

        figure_blocks = [
            block for block in p2doc.blocks if block.block_type == P2BlockType.FIGURE
        ]
        uploaded_files = (
            sorted(p for p in image_dir.iterdir() if p.is_file())
            if image_dir.is_dir()
            else []
        )

        images, findings = engine.run_import(
            "figure",
            figure_blocks,
            uploaded_files,
            page_count=page_count,
            total_blocks=total_blocks,
            # P-1 C3: a figure's page comes from the same evidence as every
            # other block's, and the verifier asks it two questions - what was
            # proven, and how to hold an estimate inside what was proven.
            page_evidence=alignment,
        )
        document.images.extend(images)
        document.verification_findings.extend(findings)
        return len(images)


# ── Conversion helpers ─────────────────────────────────────────────────

def _p2heading_to_heading(
    p2h: P2Heading, page_num: int, order: int, source_line: Optional[int] = None
) -> Optional[Heading]:
    """Map a P2Heading to a RAWRS Heading.

    H6 is reserved for page markers in RAWRS — clamp any Mathpix heading
    at level 5 or above to H5.
    """
    level_int = min(p2h.level, 5)
    try:
        level = HeadingLevel(level_int)
    except ValueError:
        logger.warning(
            "Mathpix heading level {} is invalid; skipping '{}'",
            p2h.level, p2h.text,
        )
        return None

    return Heading(
        level=level,
        text=p2h.text,
        page_number=page_num,
        document_order=order,
        is_page_marker=False,
        source="mathpix",
        source_line=source_line,
    )


def _assign_page_text(
    document: Document,
    p2doc: Any,
    page_count: int,
    total_blocks: int,
    alignment: Optional[PageAlignment] = None,
) -> None:
    """Distribute paragraph text from the P2Document across Document pages.

    Each page's cleaned_text becomes the concatenation of paragraphs whose
    page number matches.  Sets extraction_method to MATHPIX_IMPORT on every
    page so downstream OCR routing knows these pages are already populated.

    ``alignment`` is the P-1 C3 page evidence; None keeps the estimator, which
    is what every caller predating it gets.
    """
    # Bucket paragraph-type blocks by estimated page.
    # LIST_ITEM is deliberately excluded — those blocks are grouped into
    # canonical ListBlocks instead (see _group_list_items_to_lists() and
    # step 3b above); including them here would render list content
    # twice, once as flattened paragraph text and once as a real list.
    _PARA_TYPES = {P2BlockType.PARAGRAPH, P2BlockType.ABSTRACT}
    page_lines: dict[int, list[str]] = {p: [] for p in range(1, page_count + 1)}
    paragraph_order = 0

    for block in p2doc.blocks:
        if block.block_type in _PARA_TYPES:
            text = block.text or ""
            if not text:
                continue
            page_num = _resolved_page(
                block.source_line, total_blocks, page_count, alignment
            )
            page_lines[page_num].append(text)
            # FEATURE_020 — a real object alongside the flattened
            # page.cleaned_text string below (kept, not replaced: other
            # readers still use it), so markdown_builder.py can sort
            # this against headings/lists/tables/images/callouts by
            # source_line instead of scanning page.cleaned_text.
            document.paragraphs.append(
                Paragraph(
                    page_number=page_num,
                    text=text,
                    document_order=paragraph_order,
                    source_line=block.source_line,
                    provenance=ProvenanceSource.MATHPIX,
                )
            )
            paragraph_order += 1

    for page in document.pages:
        lines = page_lines.get(page.page_number, [])
        page.cleaned_text = "\n".join(lines)
        page.raw_text = page.cleaned_text
        page.ocr_confidence = OCRConfidence.HIGH
        page.extraction_method = ExtractionMethod.MATHPIX_IMPORT


def _group_list_items_to_lists(
    p2doc: Any,
    page_count: int,
    total_blocks: int,
    alignment: Optional[PageAlignment] = None,
) -> List[ListBlock]:
    """Group consecutive P2BlockType.LIST_ITEM blocks into canonical
    ListBlocks. A run ends at any non-list-item block, or at a change of
    list_style (bullet -> numbered or vice versa) — either starts a new
    ListBlock rather than merging unrelated lists together."""
    lists: List[ListBlock] = []
    order = 0
    current_style: Optional[P2ListStyle] = None
    current_items: List[ListItem] = []
    current_page: Optional[int] = None
    current_source_line: Optional[int] = None

    def flush() -> None:
        nonlocal current_style, current_items, current_page, current_source_line, order
        if current_style is not None and current_items:
            lists.append(
                ListBlock(
                    list_type=ListType.BULLET if current_style == P2ListStyle.BULLET else ListType.NUMBERED,
                    items=list(current_items),
                    page_number=current_page,
                    document_order=order,
                    provenance=ProvenanceSource.MATHPIX,
                    source_line=current_source_line,
                )
            )
            order += 1
        current_style = None
        current_items = []
        current_page = None
        current_source_line = None

    for block in p2doc.blocks:
        if block.block_type != P2BlockType.LIST_ITEM:
            flush()
            continue
        if current_style is not None and block.list_style != current_style:
            flush()
        if current_style is None:
            current_style = block.list_style
            current_page = _resolved_page(
                block.source_line, total_blocks, page_count, alignment
            )
            current_source_line = block.source_line
        text = block.text or ""
        if text:
            current_items.append(ListItem(text=text, level=0))

    flush()
    return lists


def _p2footnote_to_footnote(
    p2fn: P2Footnote,
    page_count: int,
    total_blocks: int = 1,
    alignment: Optional[PageAlignment] = None,
) -> Optional[Footnote]:
    """Map a P2Footnote to a RAWRS Footnote.

    **The anchor is evidence now, not a placeholder (N-2).** It used to be
    unknown from MMD alone: ``anchor_text`` was the note's own number as a
    string, ``anchor_offset`` was None and every note claimed page 1. N-1
    proves each marker/body correspondence while parsing and records where the
    marker sat, so the three fields ``src/models/note_references.py`` already
    resolves for the native path can be filled from the source rather than
    guessed. A note whose body N-1 proved but whose marker the package never
    contained keeps the old placeholders — its anchor is genuinely unknown,
    and searching the prose for a number would invent the reference N-1
    deliberately refused to invent.

    **Endnotes, not footnotes.** This mapping said ``NoteType.FOOTNOTE``
    because nothing here knew better; L4b's measurement is that all 54 notes
    in the benchmark's human-remediated files are ``w:endnoteReference`` in
    word/endnotes.xml, and RAWRS's own native path already emits endnotes for
    the same two documents. A Mathpix apparatus is printed after the prose
    that cites it, which is what an endnote is. Emitting footnotes put the
    same document's notes in a different part depending on which pipeline
    read it.
    """
    if not p2fn.body:
        return None
    # The marker is the substring a renderer replaces, and in a Mathpix
    # document that substring is the bracketed form transform_inline_math
    # wrote for ``${ }^{12}$`` — which is also what anchor_offset points at.
    # A bare "12" would make the offset miss by one bracket and leave the
    # brackets stranded around the reference.
    marker = f"[{p2fn.number}]"
    body_source = f"[{p2fn.number}] {p2fn.body}"
    # Footnote bodies collected at the end of MMD have no page attribution —
    # assign to the last page as a conservative placeholder.
    body_page = page_count
    anchored = p2fn.anchor_text is not None and p2fn.anchor_line is not None
    return Footnote(
        note_type=NoteType.ENDNOTE,
        number=p2fn.number,
        marker=marker,
        anchor_page_number=(
            _resolved_page(p2fn.anchor_line, total_blocks, page_count, alignment)
            if anchored
            else 1
        ),
        anchor_text=p2fn.anchor_text if anchored else marker,
        anchor_offset=p2fn.anchor_offset if anchored else None,
        body=p2fn.body,
        body_page_number=body_page,
        body_source_text=body_source,
        footnote_id=f"mathpix-{p2fn.number}",
        source="mathpix",
    )


def _p2table_to_table(p2t: P2Table, page_num: int, source_line: Optional[int] = None) -> Table:
    """Map a P2Table to a RAWRS Table."""
    rawrs_rows: List[TableRow] = []
    col_count = 0

    for r_idx, p2_row in enumerate(p2t.rows):
        is_header_row = r_idx == 0 and p2t.has_header_row
        cells = [
            TableCell(
                text=cell.text,
                row_index=r_idx,
                col_index=c_idx,
                row_span=cell.row_span,
                col_span=cell.col_span,
                is_header=is_header_row,
            )
            for c_idx, cell in enumerate(p2_row)
        ]
        col_count = max(col_count, len(cells))
        rawrs_rows.append(TableRow(cells=cells, is_header_row=is_header_row))

    return Table(
        table_id=str(uuid.uuid4()),
        page_number=page_num,
        row_count=len(rawrs_rows),
        col_count=col_count,
        rows=rawrs_rows,
        caption=p2t.caption,
        status=TableStatus.AUTO_DETECTED,
        extraction_source="mathpix",
        source_line=source_line,
        confidence=0.9,
    )
