"""Table model for RAWRS — accessible table remediation.

A Table represents one table detected on a PDF page (via PyMuPDF
page.find_tables(), which detects tables with explicit border lines)
or manually created by a reviewer in the workspace when automated
detection missed it (e.g. borderless academic tables).

TableCell fields:
  - is_header: marks a cell as a column header (row dimension)
  - is_row_header: marks a cell as a row header (stub/column dimension)
  - row_span/col_span: merged regions — 1 means no merge, >1 means the
    cell spans that many rows/columns. Both model fields and DOCX
    generation respect these; Markdown pipe table rendering is flat
    (pipe tables have no merge syntax) with spans noted in a comment.
  - header_level: for multi-level headers, 1 = primary, 2 = secondary,
    0 = not a header. Used when column headers span multiple rows.

Table accessibility fields:
  - caption: visible label ("Table 1. Summary of..."). Renders as
    italic above the pipe table in Markdown; as a Caption-styled
    paragraph above the DOCX table.
  - summary: WCAG H73 prose description for complex tables — not
    visible in Markdown (stored as HTML comment); rendered as a small
    italic descriptive paragraph below the DOCX table.
  - header_col_count: how many leading columns (0-indexed from left)
    are row headers. 0 = no row headers. Set by extractor from font
    signals and editable by reviewer.
  - confidence: 0.0–1.0 detection confidence. AUTO_DETECTED tables get
    a signal-based score; MANUALLY_CREATED tables get 1.0 (reviewer
    confirmed). Low confidence (<0.7) triggers TABLE_005 validation.
  - ai_suggestions: structured output from the AI table analyzer
    (src/ai/table_analyzer.py), populated on demand when a reviewer
    clicks "Analyze with AI". None until explicitly requested.

Table.bbox stores the source page bounding box so markdown_builder.py
can suppress the raw text lines that originated from inside the table
area, preventing those lines from appearing twice (once as body text,
once as the pipe-table rendering). On manually-created tables bbox is
None since there was no automated detection to extract it from.

Table.status tracks whether the table was auto-detected or manually
created, and whether a reviewer has confirmed the structure. The
pipeline only auto-detects; status transitions to REVIEWED via
PATCH /documents/{id}/tables/{table_id}.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from src.models.bounding_box import BoundingBox
from src.models.lifecycle import ObjectLifecycleStatus


class TableStatus(str, Enum):
    AUTO_DETECTED = "auto_detected"
    MANUALLY_CREATED = "manually_created"
    REVIEWED = "reviewed"


class TableCell(BaseModel):
    text: str
    row_index: int
    col_index: int
    row_span: int = 1
    col_span: int = 1
    is_header: bool = False
    is_row_header: bool = False
    header_level: int = 0
    bbox: Optional[BoundingBox] = None


class TableRow(BaseModel):
    cells: List[TableCell]
    is_header_row: bool = False


class TableAISuggestions(BaseModel):
    """Structured output from the AI table analyzer.

    Populated on demand only — never by the pipeline automatically.
    All fields are Optional so a partial response (e.g. only caption
    suggested) is still usable.
    """

    table_type: Optional[str] = None
    suggested_caption: Optional[str] = None
    suggested_summary: Optional[str] = None
    header_rows_detected: int = 0
    header_cols_detected: int = 0
    warnings: List[str] = []
    confidence: float = 0.0


class Table(BaseModel):
    table_id: str
    page_number: int
    row_count: int
    col_count: int
    rows: List[TableRow]
    caption: Optional[str] = None
    summary: Optional[str] = None
    status: TableStatus = TableStatus.AUTO_DETECTED
    extraction_source: str = "pymupdf"
    bbox: Optional[BoundingBox] = None
    header_col_count: int = 0
    confidence: float = 1.0
    ai_suggestions: Optional[TableAISuggestions] = None
    # Evidence-fusion: list of serialised EvidenceSignal dicts so Table
    # is JSON-serialisable without importing src.tables.evidence here.
    # Shape: [{"name": str, "score": float, "weight": float, "note": str}]
    evidence_signals: List[Dict[str, Any]] = []
    # Universal lifecycle tracking (see src/models/lifecycle.py).
    lifecycle_status: ObjectLifecycleStatus = ObjectLifecycleStatus.DETECTED
    # FEATURE_020 — see Heading.source_line's docstring (src/models/heading.py).
    source_line: Optional[int] = None
