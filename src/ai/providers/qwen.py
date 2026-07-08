"""Qwen2.5-VL-7B-Instruct AI provider for RAWRS.

Implements the AIProvider interface for the local Qwen2.5-VL model —
both alt text generation and table analysis share this one model, one
processor, and one loader (see module-level cache below); nothing else
in the repo should call from_pretrained() for this model.

Memory requirements: Qwen2.5-VL-7B requires approximately 14 GB of
virtual memory on CPU (float32) or 14 GB VRAM on GPU (float16). Before
ever attempting to load the model, _check_resources() checks available
RAM/VRAM and refuses to call from_pretrained() if there isn't enough —
this is what prevents the OOM crash this provider used to be able to
cause. On Windows systems, if the check is skipped (psutil not
installed) and loading is attempted anyway, insufficient paging file
capacity fails with OSError winerror=1455 (ERROR_COMMITMENT_LIMIT) —
still caught and converted to a human-readable error as a last resort.

Startup: registry.init_ai() calls start_background_load() once when the
FastAPI backend starts. It runs the (fast) resource preflight
synchronously, then loads the model on a background thread so backend
startup itself isn't blocked by a ~14GB model load. capabilities()
reports available=False with a "still loading" reason until the
background load finishes, so no HTTP request can reach an
uninitialized model. _ensure_model_loaded() is also safe to call
directly (idempotent, re-checks resources) as a fallback for any code
path that doesn't go through the FastAPI lifespan (tests, scripts).
"""

import re
import threading
from pathlib import Path
from typing import Optional

from loguru import logger

from src.ai.provider import AICapability, AIProvider


_MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"
_MIN_REQUIRED_BYTES = 14 * 1024**3  # ~14 GB, see module docstring

# Module-level model cache — populated on first successful load, shared by
# both generate_alt_text() and analyze_table().
_model = None
_processor = None
_load_error: Optional[str] = None  # set when loading permanently failed
_loading = False  # True only while a background load is actively in flight


class QwenProvider(AIProvider):
    """Local Qwen2.5-VL-7B-Instruct vision model provider."""

    @property
    def name(self) -> str:
        return "Qwen2.5-VL-7B"

    def capabilities(self) -> AICapability:
        if _load_error:
            return AICapability(
                vision=True,
                max_image_size_px=0,
                available=False,
                model_id=_MODEL_ID,
                unavailable_reason=_load_error,
            )
        if _loading and _model is None:
            return AICapability(
                vision=True,
                max_image_size_px=0,
                available=False,
                model_id=_MODEL_ID,
                unavailable_reason="Model is still loading, try again shortly.",
            )
        return AICapability(
            vision=True,
            max_image_size_px=4096,
            available=True,
            model_id=_MODEL_ID,
        )

    def generate_alt_text(self, request: "AltTextRequest") -> "AltTextResult":
        _ensure_model_loaded()
        return _run_inference(request)

    def analyze_table(self, request: "TableAnalysisRequest") -> "TableAnalysisResult":
        _ensure_model_loaded()
        return _run_table_inference(request)


# ---------------------------------------------------------------------------
# Resource preflight
# ---------------------------------------------------------------------------

def _check_resources() -> Optional[str]:
    """Check available RAM/VRAM before attempting to load the model.

    Returns None if there's enough headroom, else a human-readable reason.
    Fails open (returns None) if the check itself can't run — from_pretrained's
    own OSError handling remains the last-resort guard in that case.
    """
    try:
        import torch  # type: ignore
    except ImportError:
        return None  # _ensure_model_loaded()'s own ImportError path reports this

    try:
        if torch.cuda.is_available():
            free_bytes, _total_bytes = torch.cuda.mem_get_info()
            if free_bytes < _MIN_REQUIRED_BYTES:
                return (
                    f"Insufficient GPU VRAM: {free_bytes / 1024**3:.1f} GB free, "
                    f"~{_MIN_REQUIRED_BYTES / 1024**3:.0f} GB required for Qwen2.5-VL-7B."
                )
            return None

        import psutil  # type: ignore

        available_bytes = psutil.virtual_memory().available
        if available_bytes < _MIN_REQUIRED_BYTES:
            return (
                f"Insufficient RAM: {available_bytes / 1024**3:.1f} GB available, "
                f"~{_MIN_REQUIRED_BYTES / 1024**3:.0f} GB required for Qwen2.5-VL-7B "
                "(CPU inference, float32). Free up memory, increase the Windows "
                "paging file, or use a machine with a CUDA GPU with ≥14 GB VRAM."
            )
        return None
    except ImportError as exc:
        logger.warning("AI preflight: psutil not installed, skipping RAM check ({})", exc)
        return None


# ---------------------------------------------------------------------------
# Startup / background loading
# ---------------------------------------------------------------------------

def start_background_load() -> None:
    """Kick off model loading on a background thread. Called once by
    registry.init_ai() at backend startup. Never raises.

    Runs the resource preflight synchronously (fast) so unavailability is
    known immediately; only spawns the background thread if preflight
    passes, so backend startup is never blocked by the ~14GB load itself.
    """
    global _load_error, _loading

    if _model is not None or _loading:
        return  # already loaded or already loading

    try:
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration  # noqa: F401
        import torch  # noqa: F401
    except ImportError as exc:
        _load_error = (
            "Qwen2.5-VL dependencies not installed. "
            "Run: pip install -r requirements-ai.txt. "
            f"Original error: {exc}"
        )
        logger.warning("AI preflight: {}", _load_error)
        return

    resource_reason = _check_resources()
    if resource_reason:
        _load_error = resource_reason
        logger.warning("AI preflight failed: {}", resource_reason)
        return

    _loading = True
    logger.info("AI preflight passed — loading {} in background thread…", _MODEL_ID)
    thread = threading.Thread(target=_background_load_worker, name="qwen-model-load", daemon=True)
    thread.start()


def _background_load_worker() -> None:
    global _loading
    try:
        _ensure_model_loaded()
    except Exception as exc:  # noqa: BLE001 - background thread must never crash the process
        logger.error("Background AI model load failed: {}", exc)
    finally:
        _loading = False


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def _ensure_model_loaded() -> None:
    global _model, _processor, _load_error
    if _model is not None:
        return
    if _load_error:
        # A previous attempt (preflight or load) already failed permanently;
        # don't hammer from_pretrained() again on every call.
        return

    from src.ai.alt_text_generator import AltTextGenerationError

    try:
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration  # type: ignore
        import torch  # type: ignore
    except ImportError as exc:
        msg = (
            "Qwen2.5-VL dependencies not installed. "
            "Run: pip install -r requirements-ai.txt. "
            f"Original error: {exc}"
        )
        _load_error = msg
        raise AltTextGenerationError(msg) from exc

    resource_reason = _check_resources()
    if resource_reason:
        _load_error = resource_reason
        raise AltTextGenerationError(resource_reason)

    logger.info("Loading {} (first call — may take 10–30 seconds)…", _MODEL_ID)
    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _processor = AutoProcessor.from_pretrained(_MODEL_ID, trust_remote_code=True)
        _model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            _MODEL_ID,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            device_map="auto" if device == "cuda" else None,
            trust_remote_code=True,
        )
        if device == "cpu":
            _model = _model.to(device)
        logger.info("{} loaded on {}", _MODEL_ID, device)
    except OSError as exc:
        winerror = getattr(exc, "winerror", None)
        if winerror == 1455:
            msg = (
                "Cannot load Qwen2.5-VL: Windows virtual memory is insufficient for this "
                "model (~14 GB required). To enable AI alt text: "
                "(1) Increase the Windows paging file to 20 GB+ in "
                "System Properties → Advanced → Performance → Virtual Memory, OR "
                "(2) Use a machine with a CUDA GPU with ≥14 GB VRAM."
            )
        else:
            msg = f"Failed to load Qwen2.5-VL model (OS error): {exc}"
        _load_error = msg
        raise AltTextGenerationError(msg) from exc
    except Exception as exc:
        msg = f"Failed to load Qwen2.5-VL model: {exc}"
        _load_error = msg
        raise AltTextGenerationError(msg) from exc


# ---------------------------------------------------------------------------
# Alt text inference
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
You are an accessibility expert writing alt text for a figure in an academic document.

Figure context:
- Label: {figure_label}
- Caption: {caption}
- Nearby document text: {nearby_text}

IMPORTANT: Do NOT simply restate the caption. The caption is provided as context only.
Your DESCRIPTION must describe what is visually shown in the image.

Analyze the image and respond in EXACTLY this format (no other text before or after):
IMAGE_TYPE: <CHART|GRAPH|PHOTOGRAPH|DIAGRAM|EQUATION|SCREENSHOT|TABLE|OTHER>
DESCRIPTION: <one or two sentences describing what the image visually shows>
PURPOSE: <why this figure appears in the document — what argument or data it supports>
VISIBLE_TEXT: <any text legible inside the image itself, or None>
CONFIDENCE: <a number from 0.0 to 1.0 reflecting how certain you are>
WARNINGS: <comma-separated concerns about image quality, complexity, or ambiguity, or None>
"""


def _run_inference(request: "AltTextRequest") -> "AltTextResult":
    import torch  # type: ignore
    from src.ai.alt_text_generator import AltTextGenerationError

    image_path = Path(request.image_path)
    if not image_path.is_file():
        raise AltTextGenerationError(
            f"Image file not found at {image_path}. "
            "The image may have been deleted or the job was restarted."
        )

    try:
        from PIL import Image as PILImage  # type: ignore
        pil_image = PILImage.open(image_path).convert("RGB")
    except Exception as exc:
        raise AltTextGenerationError(f"Cannot read image file: {exc}") from exc

    prompt_text = _PROMPT_TEMPLATE.format(
        figure_label=request.figure_label or "Unknown",
        caption=request.caption or "None provided",
        nearby_text="; ".join(request.nearby_text) if request.nearby_text else "None",
    )

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": pil_image},
                {"type": "text", "text": prompt_text},
            ],
        }
    ]

    try:
        text_input = _processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = _processor(text=[text_input], images=[pil_image], return_tensors="pt")
        device = next(_model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            output_ids = _model.generate(**inputs, max_new_tokens=512, do_sample=False)
        response_text = _processor.decode(
            output_ids[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        )
    except Exception as exc:
        raise AltTextGenerationError(f"Inference failed: {exc}") from exc

    return _parse_response(response_text)


def _parse_response(text: str) -> "AltTextResult":
    from src.ai.alt_text_generator import AltTextGenerationError, AltTextResult

    fields: dict = {}
    for line in text.strip().splitlines():
        m = re.match(
            r"^(IMAGE_TYPE|DESCRIPTION|PURPOSE|VISIBLE_TEXT|CONFIDENCE|WARNINGS):\s*(.+)$",
            line.strip(),
        )
        if m:
            fields[m.group(1)] = m.group(2).strip()

    required = {"IMAGE_TYPE", "DESCRIPTION", "PURPOSE", "VISIBLE_TEXT", "CONFIDENCE", "WARNINGS"}
    missing = required - set(fields)
    if missing:
        raise AltTextGenerationError(
            f"Model response missing required fields: {', '.join(sorted(missing))}. "
            f"Raw response: {text[:200]!r}"
        )

    try:
        confidence = float(fields["CONFIDENCE"])
        confidence = max(0.0, min(1.0, confidence))
    except ValueError:
        confidence = 0.0

    raw_warnings = fields["WARNINGS"].strip()
    warnings = (
        []
        if raw_warnings.lower() == "none"
        else [w.strip() for w in raw_warnings.split(",") if w.strip()]
    )

    return AltTextResult(
        image_type=fields["IMAGE_TYPE"].upper(),
        description=fields["DESCRIPTION"],
        purpose=fields["PURPOSE"],
        visible_text=fields["VISIBLE_TEXT"],
        confidence=confidence,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Table analysis inference
# ---------------------------------------------------------------------------

_TABLE_PROMPT_TEMPLATE = """\
You are an accessibility expert analyzing a data table from an academic document.

Table structure:
- {row_count} rows × {col_count} columns
- Existing caption: {caption}
- Cell content (first 5 rows shown):
{cell_preview}

Analyze this table and respond in EXACTLY this format (no other text before or after):
TABLE_TYPE: <simple|complex|data|layout>
SUGGESTED_CAPTION: <one concise sentence describing the table, or KEEP if the existing caption is good>
SUGGESTED_SUMMARY: <2-3 sentences describing what the table shows, for screen reader users>
HEADER_ROWS: <integer — how many leading rows are column headers, typically 1 or 2>
HEADER_COLS: <integer — how many leading columns are row headers, typically 0 or 1>
WARNINGS: <comma-separated accessibility warnings, or None>
CONFIDENCE: <0.0 to 1.0>
"""


def _run_table_inference(request: "TableAnalysisRequest") -> "TableAnalysisResult":
    import torch  # type: ignore
    from src.ai.table_analyzer import TableAnalysisError

    preview_rows = request.cells[:5]
    cell_preview = "\n".join(
        "  Row {}: {}".format(i + 1, " | ".join(f'"{c}"' for c in row))
        for i, row in enumerate(preview_rows)
    )

    prompt = _TABLE_PROMPT_TEMPLATE.format(
        row_count=request.row_count,
        col_count=request.col_count,
        caption=request.existing_caption or "None",
        cell_preview=cell_preview,
    )

    content: list
    if request.image_path:
        try:
            from PIL import Image as PILImage  # type: ignore
            pil_image = PILImage.open(Path(request.image_path)).convert("RGB")
            content = [
                {"type": "image", "image": pil_image},
                {"type": "text", "text": prompt},
            ]
        except Exception:
            content = [{"type": "text", "text": prompt}]
    else:
        content = [{"type": "text", "text": prompt}]

    messages = [{"role": "user", "content": content}]

    try:
        text_input = _processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        images = [content[0]["image"]] if request.image_path and len(content) > 1 else None
        if images:
            inputs = _processor(text=[text_input], images=images, return_tensors="pt")
        else:
            inputs = _processor(text=[text_input], return_tensors="pt")

        device = next(_model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            output_ids = _model.generate(**inputs, max_new_tokens=400, do_sample=False)
        response_text = _processor.decode(
            output_ids[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        )
    except Exception as exc:
        raise TableAnalysisError(f"Inference failed: {exc}") from exc

    return _parse_table_response(response_text)


def _parse_table_response(text: str) -> "TableAnalysisResult":
    from src.ai.table_analyzer import TableAnalysisError, TableAnalysisResult

    fields: dict = {}
    for line in text.strip().splitlines():
        m = re.match(
            r"^(TABLE_TYPE|SUGGESTED_CAPTION|SUGGESTED_SUMMARY|HEADER_ROWS|HEADER_COLS|WARNINGS|CONFIDENCE):\s*(.+)$",
            line.strip(),
        )
        if m:
            fields[m.group(1)] = m.group(2).strip()

    required = {"TABLE_TYPE", "SUGGESTED_CAPTION", "SUGGESTED_SUMMARY",
                "HEADER_ROWS", "HEADER_COLS", "WARNINGS", "CONFIDENCE"}
    missing = required - set(fields)
    if missing:
        raise TableAnalysisError(
            f"Model response missing required fields: {', '.join(sorted(missing))}. "
            f"Raw response: {text[:200]!r}"
        )

    try:
        confidence = float(fields["CONFIDENCE"])
        confidence = max(0.0, min(1.0, confidence))
    except ValueError:
        confidence = 0.0

    try:
        header_rows = int(fields["HEADER_ROWS"])
    except ValueError:
        header_rows = 1

    try:
        header_cols = int(fields["HEADER_COLS"])
    except ValueError:
        header_cols = 0

    raw_warnings = fields["WARNINGS"].strip()
    warnings = (
        [] if raw_warnings.lower() == "none"
        else [w.strip() for w in raw_warnings.split(",") if w.strip()]
    )

    caption = fields["SUGGESTED_CAPTION"]
    if caption.upper() == "KEEP":
        caption = None

    return TableAnalysisResult(
        table_type=fields["TABLE_TYPE"].lower(),
        suggested_caption=caption if caption else None,
        suggested_summary=fields["SUGGESTED_SUMMARY"],
        header_rows_detected=max(0, header_rows),
        header_cols_detected=max(0, header_cols),
        warnings=warnings,
        confidence=confidence,
    )
