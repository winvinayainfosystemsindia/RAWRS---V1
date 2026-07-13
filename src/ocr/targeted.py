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

M-5.4.1 (OCR reliability): the Surya-facing call (predictor construction
+ inference) is bounded by a timeout, not called directly. A real
benchmark run (docs/m52_ocr_evidence_benchmark.json's M-5.4.1 re-run)
observed this call hang indefinitely on an already-warm predictor -
ocr_region() is "evidence of last resort" for one heading; it must never
be able to block the whole document pipeline forever for it.
"""

import os
import queue
import threading
from pathlib import Path
from typing import Callable, TypeVar, Union

import fitz  # PyMuPDF
from loguru import logger
from PIL import Image

from src.models.contracts import BoundingBox
from src.ocr.surya_config import build_recognition_predictor
from src.ocr.surya_engine import page_result_to_text

# Same rasterization DPI src/ocr/surya_config.py's full-page render uses -
# a small cropped region has no reason to differ.
_RASTER_DPI = 150

_T = TypeVar("_T")

# Bounds only the Surya-facing portion of ocr_region() (predictor
# construction + inference) - never PyMuPDF rendering, which is fast,
# local, and has never been observed to hang. Configurable via env var
# rather than hardcoded, since a slower environment (CPU-only inference,
# a still-cold model/weights cache) needs headroom a value tuned for an
# already-warm predictor would cut off too early. 120s comfortably
# covers the ~64s *cold* call measured after the M-5.4/predictor-caching
# fix (docs/m52_ocr_evidence_benchmark.json's re-run) while still
# bounding the multi-hour hang that same benchmark hit on a warm
# predictor - the failure this exists to contain.
DEFAULT_OCR_TIMEOUT_SECONDS = float(os.environ.get("RAWRS_TARGETED_OCR_TIMEOUT_SECONDS", "120"))


class TargetedOCRError(Exception):
    """Raised when the source PDF cannot be opened, or the requested page
    number does not exist."""


class TargetedOCRTimeoutError(TargetedOCRError):
    """Raised when Surya predictor construction or inference does not
    complete within the configured timeout (DEFAULT_OCR_TIMEOUT_SECONDS /
    RAWRS_TARGETED_OCR_TIMEOUT_SECONDS). A subclass of TargetedOCRError so
    every existing caller's ``except TargetedOCRError`` handling (e.g.
    src/verification/headings.py::_targeted_ocr_signal - evidence of last
    resort degrades to "no signal", never a crash) already covers this
    without any change there."""


def _run_with_timeout(fn: Callable[[], _T], timeout_seconds: float) -> _T:
    """Runs fn() on a fresh daemon thread and waits up to timeout_seconds
    for its result, raising TargetedOCRTimeoutError on expiry instead of
    blocking the caller indefinitely.

    A fresh thread per call, not a shared worker (e.g. a module-level
    ThreadPoolExecutor): if fn truly never returns - the exact failure
    this exists to bound - a shared single worker would wedge every
    later call behind that one stuck thread forever, turning one hang
    into a permanent outage. An abandoned, per-call thread has no effect
    on later calls. daemon=True matters too: concurrent.futures.
    ThreadPoolExecutor registers an atexit hook that joins every worker
    thread it ever created, so a stuck non-daemon worker would hang
    process *shutdown* instead of the call site - the same symptom,
    just moved. A daemon thread is simply abandoned by the runtime on
    exit, never joined.
    """
    result_box: "queue.Queue" = queue.Queue(maxsize=1)

    def _target() -> None:
        try:
            result_box.put(("ok", fn()))
        except Exception as exc:  # noqa: BLE001 - forwarded to the caller thread, not swallowed
            result_box.put(("error", exc))

    thread = threading.Thread(target=_target, name="targeted-ocr-worker", daemon=True)
    thread.start()
    try:
        status, value = result_box.get(timeout=timeout_seconds)
    except queue.Empty as exc:
        raise TargetedOCRTimeoutError(
            f"Targeted OCR did not complete within {timeout_seconds:.0f}s"
        ) from exc
    if status == "error":
        raise value
    return value


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


def ocr_region(
    pdf_path: Union[str, Path],
    page_number: int,
    bbox: BoundingBox,
    timeout_seconds: float = DEFAULT_OCR_TIMEOUT_SECONDS,
) -> str:
    """Run OCR on just one bounding box of one PDF page and return the
    recognized text (stripped, empty string if nothing was recognized).

    Never raises for "nothing found" - only for a genuinely unusable
    input (missing PDF, out-of-range page), or if the Surya call (predictor
    construction + inference) doesn't complete within timeout_seconds
    (TargetedOCRTimeoutError, a TargetedOCRError - see M-5.4.1). A verifier
    calling this as an evidence-of-last-resort fallback should treat any
    TargetedOCRError, including a timeout, as "still ambiguous", not as a
    crash - this function must never block its caller indefinitely.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise TargetedOCRError(f"Source PDF not found: {pdf_path}")

    image = _render_region_to_image(pdf_path, page_number, bbox)

    def _run_surya() -> object:
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
        return result

    # M-5.4.1: predictor construction + inference both happen inside
    # _run_with_timeout, not just inference - the observed hang (M-5.4.1's
    # benchmark re-run) was on a *warm* predictor, but build_recognition_
    # predictor() is only cheap once it has already succeeded once; bounding
    # this whole closure means a stall in either step degrades the same way
    # (a timeout, never an indefinite block), without needing to know in
    # advance which step is slow.
    result = _run_with_timeout(_run_surya, timeout_seconds)
    text = page_result_to_text(result)
    if not text:
        logger.debug(
            "Targeted OCR recovered no text for page {} region ({:.0f},{:.0f})-({:.0f},{:.0f}) in '{}'",
            page_number, bbox.x0, bbox.y0, bbox.x1, bbox.y1, pdf_path,
        )
    return text.strip()
