"""Importing this package registers every Phase 1 rule (Section 16) -
registration is a side effect of import, not a hand-maintained list.
Callers that need the registry populated (the pipeline, the new API
endpoint, tests) import this module once.
"""

from . import headings, images, metadata, reading_order, tables  # noqa: F401
