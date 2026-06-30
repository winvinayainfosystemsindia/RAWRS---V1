"""On-demand AI alt text generation for RAWRS image remediation.

AI generation is NEVER triggered automatically during pipeline execution.
It is only invoked when a human reviewer explicitly presses "Generate AI
Alt Text" in the review UI, which calls
POST /api/documents/{id}/images/{id}/generate-alt-text (src/api/routes.py),
which calls generate_alt_text() here.

Provider abstraction: this module does not know which AI model runs.
It requests a vision provider from src/ai/registry.py, which returns
the best available provider (Qwen2.5-VL in production; StubProvider in
tests). The provider does the inference; this module handles the
RAWRS-level concerns: input assembly, quality evaluation, and retry.

Quality evaluation: after generation, AltTextQualityEvaluator inspects
the result. If quality is poor (placeholder text, description just
restates caption, too short), generation is retried once automatically.
Only after one retry does a low-quality result reach the reviewer.

Stub mode: if RAWRS_AI_STUB is set, the stub provider returns
deterministic fake results without loading any model. All unit and API
tests use this mode.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from loguru import logger


class AltTextGenerationError(Exception):
    """Raised when AI generation fails for any reason.

    The message is human-readable and safe to surface to the frontend
    (it describes what went wrong, not a raw exception trace). The
    HTTP handler converts this to a 503 response.
    """


@dataclass
class AltTextRequest:
    """Everything the vision model needs to produce a structured alt text."""

    image_path: str
    caption: Optional[str]
    figure_label: Optional[str]
    nearby_text: List[str]     # up to 5 nearby TextBlock texts from the PDF
    page_number: int


@dataclass
class AltTextResult:
    """Structured output from the vision model — one field per prompt section."""

    description: str
    purpose: str
    visible_text: str
    confidence: float                    # 0.0–1.0
    image_type: str = "OTHER"           # CHART|GRAPH|PHOTOGRAPH|DIAGRAM|EQUATION|SCREENSHOT|TABLE|OTHER
    warnings: List[str] = field(default_factory=list)


def generate_alt_text(request: AltTextRequest) -> AltTextResult:
    """Invoke the AI provider and return a quality-evaluated result.

    Raises AltTextGenerationError on any failure.

    Retry logic: if the first result fails quality evaluation, generation
    is retried once. The second result is returned regardless of quality
    (the human reviewer is always the final gate).
    """
    from src.ai.registry import get_alt_text_provider
    from src.ai.quality import AltTextQualityEvaluator

    provider = get_alt_text_provider()
    result = provider.generate_alt_text(request)

    evaluator = AltTextQualityEvaluator()
    quality = evaluator.evaluate(result, request)
    if not quality.passes:
        logger.info(
            "Alt text quality check failed for image on page {} (score={:.2f}): {}; "
            "retrying once",
            request.page_number,
            quality.overall_score,
            "; ".join(quality.issues),
        )
        try:
            result = provider.generate_alt_text(request)
        except AltTextGenerationError:
            pass  # Return the original result on retry failure

    return result
