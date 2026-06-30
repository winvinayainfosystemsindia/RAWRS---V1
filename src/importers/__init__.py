"""Import provider layer for RAWRS.

Extraction providers implement the ImportProvider protocol defined in
src/importers/base.py.  Only this layer depends on provider-specific
details.  Everything downstream of the RAWRS Document model is
provider-agnostic.
"""

from src.importers.base import ImportProvider

__all__ = ["ImportProvider"]
