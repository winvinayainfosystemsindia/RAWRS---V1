"""AI provider registry for RAWRS.

Selects the best available AI provider, for any capability (alt text,
table analysis). The registry is the single point of provider
selection — callers never instantiate providers directly.

Provider selection order:
  1. RAWRS_AI_STUB env var set  →  StubProvider (tests / CI)
  2. QwenProvider available      →  QwenProvider (production, local GPU/CPU)
  3. No provider available       →  raises AIProviderUnavailableError

The registry does not cache provider instances — capabilities() is
cheap and reflects current availability (e.g., after a failed load the
QwenProvider reports available=False so the registry can skip it on
retry). Model weights are cached inside QwenProvider via module-level
globals.

Startup: init_ai() is called once from src/api/main.py's FastAPI
lifespan hook. It resolves the candidate provider and, for QwenProvider,
runs a resource preflight and kicks off model loading in a background
thread — so by the time any HTTP request arrives, the provider is
either already loaded, already known-unavailable (preflight failed), or
still warming up (reported as a transient "loading" unavailable_reason).
Nothing calls from_pretrained() from inside a request handler anymore.
"""

import os
from typing import List

from loguru import logger

from src.ai.provider import AIProvider, AIProviderUnavailableError


def get_provider() -> AIProvider:
    """Return the best available AI provider, for any capability.

    Raises:
        AIProviderUnavailableError: when no provider is currently available.
    """
    providers = _candidate_providers()
    for provider in providers:
        caps = provider.capabilities()
        if caps.available:
            logger.debug("AI provider selected: {}", provider.name)
            return provider

    # All providers unavailable — collect reasons for the error message
    reasons = []
    for provider in providers:
        caps = provider.capabilities()
        if caps.unavailable_reason:
            reasons.append(f"{provider.name}: {caps.unavailable_reason}")

    reason_text = "; ".join(reasons) if reasons else "no AI providers registered"
    raise AIProviderUnavailableError(f"No AI provider is available. {reason_text}")


def _candidate_providers() -> List[AIProvider]:
    """Return providers in priority order, filtered by environment."""
    from src.ai.providers.stub import StubProvider
    from src.ai.providers.qwen import QwenProvider

    if os.environ.get("RAWRS_AI_STUB"):
        return [StubProvider()]

    return [QwenProvider()]


def init_ai() -> None:
    """Resolve the AI provider at backend startup. Never raises.

    Called once from src/api/main.py's lifespan hook, before the app
    starts accepting requests. For StubProvider this is a no-op (nothing
    to load). For QwenProvider this runs the (fast) resource preflight
    synchronously, then — only if it passes — starts the actual model
    load on a background thread, so backend startup itself is not
    blocked by a 14GB model load.
    """
    try:
        providers = _candidate_providers()
        if not providers:
            logger.warning("AI init: no candidate providers registered.")
            return

        provider = providers[0]
        logger.info("AI init: candidate provider is {}", provider.name)

        start_background_load = getattr(provider, "start_background_load", None)
        if callable(start_background_load):
            start_background_load()
        # Providers without start_background_load (e.g. StubProvider) need
        # no initialization — capabilities() already reports available.
    except Exception as exc:  # noqa: BLE001 - startup must never fail because of AI
        logger.error("AI init failed unexpectedly (AI will report unavailable): {}", exc)
