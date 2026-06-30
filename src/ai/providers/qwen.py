"""Qwen2.5-VL-7B-Instruct AI provider for RAWRS.

Implements the AIProvider interface for the local Qwen2.5-VL model.
Model loading is lazy (on first generate_alt_text() call) and cached
for the process lifetime.

Memory requirements: Qwen2.5-VL-7B requires approximately 14 GB of
virtual memory on CPU (float32) or 14 GB VRAM on GPU (float16). On
Windows systems with insufficient paging file capacity, loading will
fail with OSError winerror=1455 (ERROR_COMMITMENT_LIMIT). This error is
caught and converted to a human-readable AltTextGenerationError with
instructions for the user to increase their paging file size.
"""

import re
from pathlib import Path
from typing import Optional

from loguru import logger

from src.ai.provider import AICapability, AIProvider


_MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"

# Module-level model cache — populated on first successful load.
_model = None
_processor = None
_load_error: Optional[str] = None  # set when loading permanently failed


class QwenProvider(AIProvider):
    """Local Qwen2.5-VL-7B-Instruct vision model provider."""

    @property
    def name(self) -> str:
        return "Qwen2.5-VL-7B"

    def capabilities(self) -> AICapability:
        global _load_error
        if _load_error:
            return AICapability(
                vision=True,
                max_image_size_px=0,
                available=False,
                model_id=_MODEL_ID,
                unavailable_reason=_load_error,
            )
        return AICapability(
            vision=True,
            max_image_size_px=4096,
            available=True,
            model_id=_MODEL_ID,
        )

    def generate_alt_text(self, request: "AltTextRequest") -> "AltTextResult":
        from src.ai.alt_text_generator import AltTextGenerationError, AltTextResult

        _ensure_model_loaded()
        return _run_inference(request)


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def _ensure_model_loaded() -> None:
    global _model, _processor, _load_error
    if _model is not None:
        return

    from src.ai.alt_text_generator import AltTextGenerationError

    try:
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration  # type: ignore
        import torch  # type: ignore
    except ImportError as exc:
        msg = (
            "Qwen2.5-VL dependencies not installed. "
            "Run: pip install transformers qwen-vl-utils torch. "
            f"Original error: {exc}"
        )
        _load_error = msg
        raise AltTextGenerationError(msg) from exc

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
# Inference
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
    from src.ai.alt_text_generator import AltTextGenerationError, AltTextResult

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
