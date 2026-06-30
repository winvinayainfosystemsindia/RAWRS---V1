"""AI provider registry for RAWRS.

Selects the best available AI provider for each capability request.
The registry is the single point of provider selection — callers never
instantiate providers directly.

Provider selection order:
  1. RAWRS_AI_STUB env var set  →  StubProvider (tests / CI)
  2. QwenProvider available      →  QwenProvider (production, local GPU/CPU)
  3. No provider available       →  raises AltTextGenerationError with guidance

The registry does not cache provider instances — capabilities() is
cheap and reflects current availability (e.g., after a failed load the
QwenProvider reports available=False so the registry can skip it on
retry). Model weights are cached inside QwenProvider via module-level
globals.
"""

import os
from typing import List

from loguru import logger

from src.ai.provider import AIProvider


def get_alt_text_provider() -> AIProvider:
    """Return the best available provider for alt text generation.

    Raises:
        AltTextGenerationError: when no provider can generate alt text.
    """
    from src.ai.alt_text_generator import AltTextGenerationError

    providers = _candidate_providers()
    for provider in providers:
        caps = provider.capabilities()
        if caps.available and caps.vision:
            logger.debug("AI provider selected: {}", provider.name)
            return provider

    # All providers unavailable — collect reasons for the error message
    reasons = []
    for provider in providers:
        caps = provider.capabilities()
        if caps.unavailable_reason:
            reasons.append(f"{provider.name}: {caps.unavailable_reason}")

    reason_text = "; ".join(reasons) if reasons else "no AI providers registered"
    raise AltTextGenerationError(
        f"No AI vision provider is available. {reason_text}"
    )


def _candidate_providers() -> List[AIProvider]:
    """Return providers in priority order, filtered by environment."""
    from src.ai.providers.stub import StubProvider
    from src.ai.providers.qwen import QwenProvider

    if os.environ.get("RAWRS_AI_STUB"):
        return [StubProvider()]

    return [QwenProvider()]
