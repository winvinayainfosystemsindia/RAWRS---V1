"""Single configuration point for Surya OCR fallback (Phase D.2).

Every Surya-specific setting - the rasterization DPI used to render a
PDF page into the image Surya OCRs, predictor construction - is defined
here ONLY, mirroring src/ocr/docling_config.py's role for Docling. No
other module should construct its own SuryaInferenceManager,
RecognitionPredictor, or rasterize a page directly. Import
build_recognition_predictor() / render_page_to_image() from here
instead, so a future tuning change (e.g. revisiting the raster DPI)
never needs to touch more than this one file.
"""

import os
from functools import lru_cache

# Same Windows symlink privilege issue documented in docling_config.py
# applies to any Hugging Face Hub model download, not just Docling's -
# Surya's models are also pulled from the Hub. setdefault() never
# overrides a value an operator has already configured.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")

import fitz  # PyMuPDF  # noqa: E402
from PIL import Image  # noqa: E402
from surya.inference import SuryaInferenceManager  # noqa: E402
from surya.recognition import RecognitionPredictor  # noqa: E402

# DPI used to rasterize a PDF page into the image handed to Surya.
# 150 balances OCR accuracy against rasterization/inference cost for a
# fallback path that, by definition, only ever runs on pages Docling
# has already failed on - it does not need to match Docling's own
# internal resolution choices.
_RASTER_DPI = 150


@lru_cache(maxsize=1)
def build_recognition_predictor() -> RecognitionPredictor:
    """Build a RecognitionPredictor for full-page Surya OCR.

    Cached process-wide: model construction lazily loads weights on
    first use, and that cost should only be paid once per process, not
    once per call. src/ocr/surya_engine.py already builds one and
    reuses it across every page in a document; src/ocr/targeted.py
    calls this function once per targeted region with no caching of its
    own (see FEATURE_019/M-5.1) - without this cache, a document with
    several ambiguous headings rebuilds the whole model once per
    heading (measured: ~87 min/call, see docs/m52_ocr_evidence_benchmark.json).
    Tests monkeypatch this name at the call-site module (e.g.
    `src.ocr.targeted.build_recognition_predictor`), replacing the
    reference entirely, so the cache on the real function never affects
    them.
    """
    return RecognitionPredictor(SuryaInferenceManager())


def render_page_to_image(pdf_path, page_number: int) -> Image.Image:
    """Rasterize one 1-indexed PDF page into a PIL image for Surya.

    Args:
        pdf_path: Path to the source PDF.
        page_number: 1-indexed page number (matches Page.page_number).

    Returns:
        An RGB PIL.Image.Image of the page rendered at _RASTER_DPI.
    """
    with fitz.open(pdf_path) as pdf_document:
        pixmap = pdf_document[page_number - 1].get_pixmap(dpi=_RASTER_DPI, alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
