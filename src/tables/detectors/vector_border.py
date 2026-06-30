"""Vector border table detector for RAWRS.

Detects tables drawn with explicit PDF line graphics (vector borders) using
PyMuPDF's page.find_tables(strategy='lines'). This is the highest-confidence
detection path: if a table has visible borders, the vector line strategy
reliably finds it with a precise cell bounding box.

strategy='text' was evaluated and rejected — it treats multi-column academic
page layouts as a single large table on every page. See table_extractor.py
module docstring for the full decision history.

Only direct-text (born-digital) pages are processed. OCR pages lack the
native PDF vector graphics that this strategy relies on.
"""

from typing import List

import fitz
from loguru import logger

from src.tables.detectors.base import CandidateRegion, TableDetector
from src.tables.detectors.caption import find_caption
from src.tables.evidence import EvidenceBundle, EvidenceSignal


class VectorBorderDetector(TableDetector):
    """Detect tables with explicit PDF vector border lines (high confidence)."""

    @property
    def name(self) -> str:
        return "vector_border"

    def detect(self, fitz_page: fitz.Page, page_number: int) -> List[CandidateRegion]:
        try:
            finder = fitz_page.find_tables()
        except Exception as exc:
            logger.warning("VectorBorderDetector: find_tables() failed on page {}: {}", page_number, exc)
            return []

        if not finder.tables:
            return []

        page_dict = None  # lazy load for caption detection
        page_width = fitz_page.rect.width
        results: List[CandidateRegion] = []

        for fitz_table in finder.tables:
            raw_bbox = fitz_table.bbox
            if raw_bbox is None:
                continue
            bbox = (raw_bbox[0], raw_bbox[1], raw_bbox[2], raw_bbox[3])

            # Extract raw cell content
            try:
                raw_rows_fitz = fitz_table.extract()
                raw_rows = [
                    [str(cell) if cell is not None else "" for cell in row]
                    for row in raw_rows_fitz
                ]
            except Exception:
                raw_rows = None

            # Build evidence bundle
            bundle = EvidenceBundle()
            bundle.add(EvidenceSignal(
                name="vector_borders",
                score=1.0,
                weight=1.0,
                note="PyMuPDF find_tables(strategy='lines') found explicit PDF border lines",
            ))
            bundle.add(EvidenceSignal(
                name="pymupdf_cell_count",
                score=min(1.0, (fitz_table.row_count * fitz_table.col_count) / 4),
                weight=0.3,
                note=f"{fitz_table.row_count} rows × {fitz_table.col_count} cols",
            ))

            # Caption detection
            if page_dict is None:
                try:
                    page_dict = fitz_page.get_text("dict")
                except Exception:
                    page_dict = {"blocks": []}

            caption, caption_score = find_caption(page_dict, bbox, page_width)
            if caption_score > 0:
                bundle.add(EvidenceSignal(
                    name="caption_found",
                    score=caption_score,
                    weight=0.4,
                    note=f"Caption detected above region: {caption[:50]!r}" if caption else "caption signal",
                ))

            results.append(CandidateRegion(
                page_number=page_number,
                bbox=bbox,
                evidence=bundle,
                raw_rows=raw_rows,
                caption=caption,
            ))

        return results
