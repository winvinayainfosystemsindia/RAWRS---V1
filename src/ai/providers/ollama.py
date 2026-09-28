"""Ollama provider: a local vision model served by Ollama.

Qwen2.5-VL-7B through transformers needs ~14 GB of memory, which most
reviewer machines (8 GB here) do not have, so ``QwenProvider`` reports
itself unavailable and every image kept its placeholder alt text. Ollama
runs a 4-bit ``qwen2.5vl:3b`` (3.2 GB) on CPU, locally and for free, and
this provider speaks to it over its HTTP API with the standard library -
no new dependency. It reuses QwenProvider's prompt and parser, so the two
produce the same structured result and nothing downstream can tell them
apart.

Configuration (environment):
  RAWRS_OLLAMA_URL    default http://localhost:11434
  RAWRS_OLLAMA_MODEL  default qwen2.5vl:3b
"""

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from loguru import logger

from src.ai.provider import AICapability, AIProvider

_DEFAULT_URL = "http://localhost:11434"
_DEFAULT_MODEL = "qwen2.5vl:3b"
# CPU inference measured at 150-180 s per figure on the 8 GB reference
# machine; the timeout leaves headroom for a slower one.
_GENERATE_TIMEOUT_SECONDS = 900
_PROBE_TIMEOUT_SECONDS = 3


def _url() -> str:
    return os.environ.get("RAWRS_OLLAMA_URL", _DEFAULT_URL).rstrip("/")


def _model() -> str:
    return os.environ.get("RAWRS_OLLAMA_MODEL", _DEFAULT_MODEL)


class OllamaProvider(AIProvider):
    @property
    def name(self) -> str:
        return f"Ollama ({_model()})"

    def capabilities(self) -> AICapability:
        reason = _unavailable_reason()
        return AICapability(
            vision=True,
            max_image_size_px=0,
            available=reason is None,
            model_id=_model(),
            unavailable_reason=reason,
        )

    def generate_alt_text(self, request):
        from src.ai.alt_text_generator import AltTextGenerationError
        from src.ai.providers.qwen import _PROMPT_TEMPLATE, _parse_response

        image_path = Path(request.image_path)
        if not image_path.is_file():
            raise AltTextGenerationError(f"Image file not found at {image_path}.")
        prompt = _PROMPT_TEMPLATE.format(
            figure_label=request.figure_label or "Unknown",
            caption=request.caption or "None provided",
            nearby_text="; ".join(request.nearby_text) if request.nearby_text else "None",
        )
        try:
            text = _generate(prompt, image_path)
        except Exception as exc:
            raise AltTextGenerationError(f"Ollama inference failed: {exc}") from exc
        return _parse_response(text)

    def analyze_table(self, request):
        from src.ai.providers.qwen import _TABLE_PROMPT_TEMPLATE, _parse_table_response
        from src.ai.table_analyzer import TableAnalysisError

        cell_preview = "\n".join(
            "  Row {}: {}".format(i + 1, " | ".join(f'"{c}"' for c in row))
            for i, row in enumerate(request.cells[:5])
        )
        prompt = _TABLE_PROMPT_TEMPLATE.format(
            row_count=request.row_count,
            col_count=request.col_count,
            caption=request.existing_caption or "None",
            cell_preview=cell_preview,
        )
        image = Path(request.image_path) if request.image_path else None
        try:
            text = _generate(prompt, image if image and image.is_file() else None)
        except Exception as exc:
            raise TableAnalysisError(f"Ollama inference failed: {exc}") from exc
        return _parse_table_response(text)


def _generate(prompt: str, image_path: Optional[Path]) -> str:
    payload = {
        "model": _model(),
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
    }
    if image_path is not None:
        payload["images"] = [base64.b64encode(image_path.read_bytes()).decode("ascii")]
    request = urllib.request.Request(
        f"{_url()}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=_GENERATE_TIMEOUT_SECONDS) as response:
        return json.loads(response.read())["response"]


def _unavailable_reason() -> Optional[str]:
    """None when Ollama answers and has the configured model pulled."""
    try:
        with urllib.request.urlopen(f"{_url()}/api/tags", timeout=_PROBE_TIMEOUT_SECONDS) as response:
            models = {m.get("name") for m in json.loads(response.read()).get("models", [])}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return f"Ollama is not reachable at {_url()} ({exc})"
    if _model() not in models:
        logger.debug("Ollama is up but {} is not pulled (have: {})", _model(), sorted(models))
        return f"Ollama model {_model()} is not pulled (run: ollama pull {_model()})"
    return None
