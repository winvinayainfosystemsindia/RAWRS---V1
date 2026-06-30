"""Backward-compatible re-export — caption logic lives in src/captions/.

Import from src.captions.caption_detector or src.captions directly.
This shim is kept so existing imports in vector_border.py and
span_alignment.py continue to work without a mass rename.
"""

from src.captions.caption_detector import find_caption, _score_candidate  # noqa: F401

__all__ = ["find_caption", "_score_candidate"]
