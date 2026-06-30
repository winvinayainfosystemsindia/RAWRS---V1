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

import math
import uuid
from pathlib import Path
from typing import Any, List, Optional

from loguru import logger

from src.mathpix.mmd_parser import parse_mmd
from src.models.contracts import (
    Document,
    ExtractionMethod,
    Footnote,
    FrontMatter,
    Heading,
    HeadingLevel,
    NoteType,
    OCRConfidence,
    Table,
    TableCell,
    TableRow,
    TableStatus,
)
from src.models.phase2_document import (
    P2BlockType,
    P2Footnote,
    P2Heading,
    P2Table,
)


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

        Returns:
            The same ``document`` with headings, page text, tables,
            footnotes, and front_matter populated from the MMD.
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

        # ── 1. Front matter ────────────────────────────────────────────
        if p2doc.front_matter:
            fm = p2doc.front_matter
            if fm.title or fm.authors:
                document.front_matter = FrontMatter(
                    title=fm.title,
                    authors=fm.authors or [],
                    affiliations=getattr(fm, "affiliation_list", []),
                )

        # ── 2. Headings ────────────────────────────────────────────────
        heading_order = 0
        for block in p2doc.blocks:
            if block.block_type == P2BlockType.HEADING and block.heading:
                page_num = _estimate_page(
                    block.source_line, total_blocks, page_count
                )
                h = _p2heading_to_heading(block.heading, page_num, heading_order)
                if h is not None:
                    document.headings.append(h)
                    heading_order += 1

        # ── 3. Page text (proportional distribution) ───────────────────
        _assign_page_text(document, p2doc, page_count, total_blocks)

        # ── 4. Footnotes ───────────────────────────────────────────────
        for p2fn in p2doc.footnotes:
            fn = _p2footnote_to_footnote(p2fn, page_count)
            if fn is not None:
                document.footnotes.append(fn)

        # ── 5. Tables ──────────────────────────────────────────────────
        table_count = 0
        for block in p2doc.blocks:
            if block.block_type == P2BlockType.TABLE and block.table:
                page_num = _estimate_page(
                    block.source_line, total_blocks, page_count
                )
                document.tables.append(
                    _p2table_to_table(block.table, page_num)
                )
                table_count += 1

        logger.info(
            "Mathpix import complete: {} heading(s), {} table(s), {} footnote(s)",
            len(document.headings),
            table_count,
            len(document.footnotes),
        )
        return document


# ── Conversion helpers ─────────────────────────────────────────────────

def _estimate_page(source_line: int, total_lines: int, page_count: int) -> int:
    """Estimate which physical page a block belongs to.

    Uses proportional position in the MMD line sequence as a proxy for
    position in the physical document.  This is an approximation; a later
    phase will refine using DOCX H6 page markers when available.
    """
    if total_lines <= 0 or page_count <= 1:
        return 1
    frac = source_line / total_lines
    page = math.ceil(frac * page_count)
    return max(1, min(page, page_count))


def _p2heading_to_heading(
    p2h: P2Heading, page_num: int, order: int
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
    )


def _assign_page_text(
    document: Document,
    p2doc: Any,
    page_count: int,
    total_blocks: int,
) -> None:
    """Distribute paragraph text from the P2Document across Document pages.

    Each page's cleaned_text becomes the concatenation of paragraphs whose
    estimated page number matches.  Sets extraction_method to MATHPIX_IMPORT
    on every page so downstream OCR routing knows these pages are already
    populated.
    """
    # Bucket paragraph-type blocks by estimated page
    _PARA_TYPES = {P2BlockType.PARAGRAPH, P2BlockType.LIST_ITEM, P2BlockType.ABSTRACT}
    page_lines: dict[int, list[str]] = {p: [] for p in range(1, page_count + 1)}

    for block in p2doc.blocks:
        if block.block_type in _PARA_TYPES:
            text = block.text or ""
            if not text:
                continue
            page_num = _estimate_page(block.source_line, total_blocks, page_count)
            page_lines[page_num].append(text)

    for page in document.pages:
        lines = page_lines.get(page.page_number, [])
        page.cleaned_text = "\n".join(lines)
        page.raw_text = page.cleaned_text
        page.ocr_confidence = OCRConfidence.HIGH
        page.extraction_method = ExtractionMethod.MATHPIX_IMPORT


def _p2footnote_to_footnote(p2fn: P2Footnote, page_count: int) -> Optional[Footnote]:
    """Map a P2Footnote to a RAWRS Footnote.

    Anchor details are unknown from MMD alone — populated with minimal
    valid placeholders.  The Verification Engine (Phase M-2) will cross-
    reference PDF span data to enrich anchor page, offset, and text.
    """
    if not p2fn.body:
        return None
    marker = str(p2fn.number)
    body_source = f"[{p2fn.number}] {p2fn.body}"
    # Footnote bodies collected at the end of MMD have no page attribution —
    # assign to the last page as a conservative placeholder.
    body_page = page_count
    return Footnote(
        note_type=NoteType.FOOTNOTE,
        number=p2fn.number,
        marker=marker,
        anchor_page_number=1,       # placeholder; enriched by Verification Engine
        anchor_text=marker,          # placeholder; enriched by Verification Engine
        anchor_offset=None,
        body=p2fn.body,
        body_page_number=body_page,
        body_source_text=body_source,
        footnote_id=f"mathpix-{p2fn.number}",
        source="mathpix",
    )


def _p2table_to_table(p2t: P2Table, page_num: int) -> Table:
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
        confidence=0.9,
    )
