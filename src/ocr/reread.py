"""Second reading of garbled OCR regions by a document VLM.

Docling's recognizer garbles emphasized runs (src/ocr/quality.py), and the
only fallback the pipeline had - Surya, ~6 min/page on CPU - ran solely on
pages Docling left *empty*, so garbled pages shipped as they were. This stage
crops just the garbled items (src/ocr/docling_engine.py marks them on
``Page.ocr_rereads``) and asks GLM-OCR, served by the local Ollama, to read
each one again. Measured on the O'Leary chapter in a 4-core codespace: 13
garbled paragraphs, 4-20 s each, every bold lead-in recovered ("Hyp s o l i
ol ss it" -> "Hypothesis: Logical conjecture (hunch or educated guess) about
the nature of"). See docs/OCR_QUALITY.md.

A reading is evidence, not truth. It is *accepted* only when it is not
garbled itself, keeps the original's readable words (``quality.agreement``,
the anti-hallucination check - the garble is usually a few words, the rest of
the paragraph is fine and must survive) and has a plausible length. Accepted
readings become auto-applied, undoable corrections
(src/verification/ocr_text.py); rejected ones and regions that could not be
read stay flagged for the reviewer (validation rule OCR_004).

Nothing here changes page text. Skipped entirely when there is nothing
garbled, when ``RAWRS_OCR_REREAD=off``, in AI stub mode (tests/CI), or when
Ollama or the model is unavailable - the regions then stay flagged.

Configuration (environment):
  RAWRS_OCR_REREAD        on (default) / off
  RAWRS_OCR_REREAD_MODEL  default glm-ocr:q8_0
  RAWRS_OLLAMA_URL        shared with the alt-text provider
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from loguru import logger

from src.models.contracts import Document, OCRReread
from src.ocr import cache as ocr_cache
from src.ocr.quality import agreement, is_garbled
from src.utils.text_sanitization import sanitize_xml_text

_DEFAULT_MODEL = "glm-ocr:q8_0"
_OFF_VALUES = frozenset({"0", "off", "false", "no"})
_PROMPT = "Text Recognition:"  # GLM-OCR's own task prompt for plain text
_DPI = 200
_PADDING_PT = 4.0
_TIMEOUT_SECONDS = 600
_PROBE_TIMEOUT_SECONDS = 3

# Acceptance: measured on the 13 O'Leary regions, every correct reading kept
# >= 0.9 of the original's readable words; a reading cut short by the token
# cap kept 0.8. A garbled original is shorter than the truth (letters lost),
# never much longer.
MIN_AGREEMENT = 0.85
MAX_LENGTH_RATIO = 2.0
MIN_LENGTH_RATIO = 0.7

Reader = Callable[[bytes, int], str]


def model() -> str:
    return os.environ.get("RAWRS_OCR_REREAD_MODEL", _DEFAULT_MODEL)


def enabled() -> bool:
    if os.environ.get("RAWRS_AI_STUB"):
        return False
    return os.environ.get("RAWRS_OCR_REREAD", "on").strip().lower() not in _OFF_VALUES


def reread_garbled_regions(document: Document, reader: Optional[Reader] = None) -> Document:
    """Read every still-unread garbled region of ``document`` again.

    ``reader`` (png bytes, original length -> text) is injectable for tests;
    by default GLM-OCR through Ollama, probed once. Returns the same Document
    with each region's ``reading``/``engine``/``agreement``/``accepted``/
    ``reason`` filled in where a reading was obtained.
    """
    pending = [(page, region) for page in document.pages for region in page.ocr_rereads if region.reading is None]
    if not pending:
        return document
    engine_name = model()
    if reader is None:
        if not enabled():
            logger.info("OCR re-reading off; {} garbled region(s) stay flagged", len(pending))
            return document
        reason = _unavailable_reason()
        if reason is not None:
            logger.warning("OCR re-reading unavailable ({}); {} garbled region(s) stay flagged", reason, len(pending))
            return document
        reader = _ollama_read

    pdf_path = Path(document.source_pdf_path)
    try:
        import fitz

        pdf = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning("OCR re-reading cannot open '{}': {}", pdf_path, exc)
        return document

    accepted = 0
    with pdf:
        by_page: Dict[int, List[OCRReread]] = {}
        for page, region in pending:
            by_page.setdefault(page.page_number, []).append(region)
        for page_number, regions in by_page.items():
            cached = _cached_reads(pdf_path, page_number, engine_name)
            fresh: Dict[str, str] = {}
            for region in regions:
                key = _region_key(region)
                reading = cached.get(key)
                if reading is None:
                    reading = _read_region(pdf, page_number, region, reader)
                    if reading is None:
                        continue
                    fresh[key] = reading
                _judge(region, reading, engine_name)
                accepted += region.accepted
            if fresh:
                _store_reads(pdf_path, page_number, engine_name, {**cached, **fresh})

    logger.info(
        "OCR re-reading: {} garbled region(s), {} accepted, by {}", len(pending), accepted, engine_name
    )
    return document


def clean_reading(reading: str, original: str) -> str:
    """One line of plain text: markdown emphasis and a bullet the original
    did not have are dropped; a leading symbol the original had (a ☑ the VLM
    skipped) is kept."""
    text = re.sub(r"\s+", " ", reading).strip()
    text = re.sub(r"(\*\*|__)", "", text)
    text = re.sub(r"^(?:[-*•]\s+)", "", text) if not re.match(r"^[-*•]\s", original) else text
    # Non-ASCII symbols only: a garbled original often starts with ASCII junk
    # ("-  l   sdd") that must not be carried over.
    symbols = re.match(r"^((?:(?![\w\s])[^\x00-\x7f])+)", original)
    if symbols and not text.startswith(symbols.group(1)):
        text = f"{symbols.group(1)} {text}"
    cleaned, _ = sanitize_xml_text(text)
    return cleaned


def _judge(region: OCRReread, raw_reading: str, engine_name: str) -> None:
    reading = clean_reading(raw_reading, region.original)
    region.reading = reading
    region.engine = engine_name
    region.agreement = round(agreement(region.original, reading), 3)
    ratio = len(reading) / max(len(region.original), 1)
    if not reading:
        region.reason = "the second reading was empty"
    elif is_garbled(reading):
        region.reason = "the second reading is garbled too"
    elif region.agreement < MIN_AGREEMENT:
        region.reason = (
            f"the second reading keeps only {region.agreement:.0%} of the original's readable words"
        )
    elif not MIN_LENGTH_RATIO <= ratio <= MAX_LENGTH_RATIO:
        region.reason = f"the second reading is {ratio:.1f}x the original's length"
    else:
        region.accepted = True
        region.reason = ""


def _read_region(pdf, page_number: int, region: OCRReread, reader: Reader) -> Optional[str]:
    if not region.bbox:
        return None
    try:
        import fitz

        page = pdf[page_number - 1]
        x0, y0, x1, y1 = region.bbox
        clip = fitz.Rect(x0 - _PADDING_PT, y0 - _PADDING_PT, x1 + _PADDING_PT, y1 + _PADDING_PT) & page.rect
        png = page.get_pixmap(clip=clip, dpi=_DPI).tobytes("png")
        return reader(png, len(region.original))
    except Exception as exc:  # one region failing must not cost the others
        logger.warning("OCR re-reading of a page {} region failed: {}", page_number, exc)
        return None


def _region_key(region: OCRReread) -> str:
    raw = json.dumps([region.original, region.bbox], ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _cached_reads(pdf_path: Path, page_number: int, engine_name: str) -> Dict[str, str]:
    entry = ocr_cache.lookup("glm", pdf_path, page_number)
    if not entry or entry.get("model") != engine_name or not isinstance(entry.get("reads"), dict):
        return {}
    return {k: v for k, v in entry["reads"].items() if isinstance(v, str)}


def _store_reads(pdf_path: Path, page_number: int, engine_name: str, reads: Dict[str, str]) -> None:
    # "text" is the cache's required field; region readings live in "reads".
    ocr_cache.store("glm", pdf_path, page_number, {"text": "", "model": engine_name, "reads": reads})


def _ollama_url() -> str:
    from src.ai.providers.ollama import _url

    return _url()


def _unavailable_reason() -> Optional[str]:
    try:
        with urllib.request.urlopen(f"{_ollama_url()}/api/tags", timeout=_PROBE_TIMEOUT_SECONDS) as response:
            models = {m.get("name") for m in json.loads(response.read()).get("models", [])}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return f"Ollama is not reachable at {_ollama_url()} ({exc})"
    if model() not in models:
        return f"{model()} is not pulled (run: ollama pull {model()})"
    return None


def _ollama_read(png: bytes, original_length: int) -> str:
    # Token cap: a garbled original is shorter than the truth, and an
    # uncapped VLM can loop; ~1 token per 4 characters plus generous room.
    payload = {
        "model": model(),
        "prompt": _PROMPT,
        "stream": False,
        "images": [base64.b64encode(png).decode("ascii")],
        "options": {"temperature": 0, "num_predict": max(256, original_length)},
    }
    request = urllib.request.Request(
        f"{_ollama_url()}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        return json.loads(response.read())["response"]


def summary(document: Document) -> Tuple[int, int, int]:
    """(garbled regions, read again, accepted) across the document."""
    regions = [r for page in document.pages for r in page.ocr_rereads]
    return len(regions), sum(r.reading is not None for r in regions), sum(r.accepted for r in regions)
