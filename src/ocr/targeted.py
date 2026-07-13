"""Region-targeted OCR for RAWRS (FEATURE_019).

Every existing OCR engine (src/ocr/docling_engine.py, src/ocr/surya_engine.py)
runs on a whole page, once, as the page's primary extraction path. This
module is a different thing: a small, cheap, on-demand OCR call scoped to
one known bounding box, for a verifier that already knows roughly WHERE
to look and just needs to read the text there — e.g.
src/verification/headings.py::HeadingVerifier when its typography/
whitespace/running-header evidence is still ambiguous after everything
else, or a future printed-page-number recovery pass for scanned,
text-layer-less pages (the forensic audit's DEF-08:
RAWRS_forensic_audit.md).

Reuses src/ocr/surya_config.py's build_recognition_predictor() (never
constructs a second SuryaInferenceManager) - the only new piece is
rendering just the requested region instead of the whole page, via
PyMuPDF's own ``clip`` parameter (a real crop at raster time, not a
full-page render sliced afterward).
"""

from pathlib import Path
from typing import Union

import fitz  # PyMuPDF
from loguru import logger
from PIL import Image

from src.models.contracts import BoundingBox
from src.ocr.surya_config import build_recognition_predictor
from src.ocr.surya_engine import page_result_to_text

# Same rasterization DPI src/ocr/surya_config.py's full-page render uses -
# a small cropped region has no reason to differ.
_RASTER_DPI = 150


class TargetedOCRError(Exception):
    """Raised when the source PDF cannot be opened, or the requested page
    number does not exist."""


def _render_region_to_image(pdf_path: Path, page_number: int, bbox: BoundingBox) -> Image.Image:
    """Rasterize just ``bbox`` of one 1-indexed PDF page into a PIL image."""
    with fitz.open(pdf_path) as pdf_document:
        page_index = page_number - 1
        if page_index < 0 or page_index >= pdf_document.page_count:
            raise TargetedOCRError(
                f"Page {page_number} does not exist in '{pdf_path}' ({pdf_document.page_count} page(s))"
            )
        clip = fitz.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
        pixmap = pdf_document[page_index].get_pixmap(dpi=_RASTER_DPI, clip=clip, alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def ocr_region(pdf_path: Union[str, Path], page_number: int, bbox: BoundingBox) -> str:
    """Run OCR on just one bounding box of one PDF page and return the
    recognized text (stripped, empty string if nothing was recognized).

    Never raises for "nothing found" - only for a genuinely unusable
    input (missing PDF, out-of-range page). A verifier calling this as an
    evidence-of-last-resort fallback should treat an empty result as
    "still ambiguous", not as a crash.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise TargetedOCRError(f"Source PDF not found: {pdf_path}")

    image = _render_region_to_image(pdf_path, page_number, bbox)
    predictor = build_recognition_predictor()
    # M-5.4: full_page=True, not False. In installed surya-ocr 0.20.0,
    # full_page is the "treat this image as one region to recognize
    # directly" mode (a single HIGH_ACCURACY_BBOX_PROMPT request, no
    # layout_results needed) — exactly this function's case, since the
    # image is already a known, isolated crop (one heading's own bbox) via
    # PyMuPDF's own clip at raster time. full_page=False means the
    # opposite of what the old comment here assumed: "this image contains
    # MULTIPLE layout blocks that need per-block OCR requests," which
    # requires a LayoutResult this function never had — the exact cause
    # of the "layout_results required when full_page=False" error M-5.3's
    # real-corpus benchmark surfaced. The result shape (PageOCRResult.
    # blocks[].html/.skipped/.reading_order) is identical either way, so
    # the same page_result_to_text() parsing helper still applies.
    [result] = predictor([image], full_page=True)
    text = page_result_to_text(result)
    if not text:
        logger.debug(
            "Targeted OCR recovered no text for page {} region ({:.0f},{:.0f})-({:.0f},{:.0f}) in '{}'",
            page_number, bbox.x0, bbox.y0, bbox.x1, bbox.y1, pdf_path,
        )
    return text.strip()
