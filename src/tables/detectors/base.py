"""Abstract base for RAWRS table detectors.

Each concrete detector inspects one signal category per PDF page and
returns zero or more CandidateRegion objects. The caller (table_extractor.py)
runs all registered detectors, merges overlapping candidates, aggregates
their evidence bundles, and converts the final candidates to Table models.

Detector contract:
  - detect() must never raise; exceptions are logged and empty list returned.
  - detect() is called once per page; detectors are stateless.
  - Detector instances may be reused across pages and documents.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

import fitz

from src.tables.evidence import EvidenceBundle


@dataclass
class CandidateRegion:
    """One proposed table region, with evidence from its detector.

    page_number: 1-based page number.
    bbox:        (x0, y0, x1, y1) in PyMuPDF page coordinates.
    evidence:    Signals contributed by the detecting detector.
    raw_rows:    Optional[List[List[str]]] — cell content already
                 extracted by the detector. When None, a default
                 extraction runs during Table construction.
    caption:     Caption text detected above this region, if any.
    """

    page_number: int
    bbox: tuple                           # (x0, y0, x1, y1)
    evidence: EvidenceBundle
    raw_rows: Optional[List[List[str]]] = None
    caption: Optional[str] = None


class TableDetector(ABC):
    """Base class for one evidence-contributing table detector.

    Concrete detectors:
      VectorBorderDetector  — src/tables/detectors/vector_border.py
      SpanAlignmentDetector — src/tables/detectors/span_alignment.py
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable snake_case label used in EvidenceSignal.name."""

    @abstractmethod
    def detect(self, fitz_page: fitz.Page, page_number: int) -> List[CandidateRegion]:
        """Return candidate table regions for a single PDF page.

        Never raises. Returns empty list when this detector finds nothing.
        """
