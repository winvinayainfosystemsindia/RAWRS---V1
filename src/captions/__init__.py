"""Generic caption detection for RAWRS visual objects.

Exposes find_caption() for use by any detector or extractor that needs
to locate a caption above a detected region — tables, figures, equations,
algorithms, or any future object type.
"""

from src.captions.caption_detector import find_caption

__all__ = ["find_caption"]
