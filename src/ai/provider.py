"""AI provider abstraction for RAWRS.

All AI operations (alt text generation, future caption generation, etc.)
go through this abstraction layer. The alt text generator does not know
which model produced the output — it requests accessibility descriptions
from an AIProvider interface and trusts the registry to supply the best
available provider.

This makes future model migration trivial: swap the provider in the
registry, update the provider's generate() implementation, done.

Provider contract:
  - capabilities(): return AICapability describing what this provider
    can do and whether it is currently available (model weights on disk,
    sufficient memory, etc.). Called once per request cycle so it can
    reflect real-time availability (e.g., OOM after first load).
  - generate_alt_text(): perform inference and return AltTextResult.
    Must raise AltTextGenerationError on any failure.

The provider does NOT handle quality evaluation or retry logic — that
is the caller's responsibility (src/ai/alt_text_generator.py).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class AICapability:
    """Describes what an AI provider can do and whether it is available.

    vision:             True if the provider can process images.
    max_image_size_px:  Maximum image dimension the provider accepts
                        (width or height). 0 = unlimited.
    available:          True if the provider is ready to accept requests
                        right now (model loaded or loadable).
    unavailable_reason: Human-readable message when available=False.
                        Shown to the reviewer in the UI.
    model_id:           Identifier of the underlying model (for logging
                        and audit trails).
    """

    vision: bool
    max_image_size_px: int
    available: bool
    model_id: str
    unavailable_reason: Optional[str] = None


class AIProvider(ABC):
    """Abstract base for RAWRS AI providers.

    Concrete implementations live in src/ai/providers/.
    The registry (src/ai/registry.py) selects and caches providers.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short display name (e.g. "Qwen2.5-VL-7B", "Stub")."""

    @abstractmethod
    def capabilities(self) -> AICapability:
        """Return current capabilities, including availability status."""

    @abstractmethod
    def generate_alt_text(self, request: "AltTextRequest") -> "AltTextResult":
        """Generate accessibility alt text for one image.

        request: AltTextRequest from src/ai/alt_text_generator.py.

        Returns AltTextResult.

        Raises AltTextGenerationError (from alt_text_generator.py) on
        any failure — model load error, inference error, parse error.
        """
