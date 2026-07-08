"""On-demand AI table analysis for RAWRS table remediation.

AI analysis is NEVER triggered automatically during pipeline execution.
It is only invoked when a human reviewer explicitly presses "Analyze
with AI" in the Tables workspace, which calls
POST /api/documents/{id}/tables/{table_id}/analyze (src/api/routes.py),
which calls analyze_table() here.

The analyzer inspects the table's cell content patterns (text, layout,
and optionally a rendered page image) and returns:
  - table_type: "simple", "complex", "data", or "layout"
  - suggested_caption: a one-line caption the reviewer can accept/edit
  - suggested_summary: a WCAG H73 prose description for complex tables
  - header_rows_detected: best-guess header row count (0, 1, or 2)
  - header_cols_detected: best-guess row-header column count (0 or 1)
  - warnings: list of accessibility concerns (e.g. merged cells needed,
    empty headers, complex hierarchy)
  - confidence: 0.0–1.0

Provider abstraction: this module does not know which AI model runs.
It requests a provider from src/ai/registry.py — the same provider and
model instance already loaded for alt text generation (see
src/ai/providers/qwen.py) — so the model is never loaded twice.

Stub mode: if RAWRS_AI_STUB is set, the registry returns StubProvider,
which returns a deterministic fake result derived from cell content
patterns without loading any model. Used in all unit and API tests.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from loguru import logger


class TableAnalysisError(Exception):
    """Raised when AI analysis fails for any reason.

    Human-readable; the HTTP handler converts this to a 503 response.
    """


@dataclass
class TableAnalysisRequest:
    """Everything the analyzer needs to inspect a table."""

    table_id: str
    page_number: int
    row_count: int
    col_count: int
    header_row_count: int
    header_col_count: int
    cells: List[List[str]]           # [row][col] cell text, already stripped
    existing_caption: Optional[str]  # reviewer-supplied caption so far, if any
    image_path: Optional[str]        # page image for visual analysis (optional)


@dataclass
class TableAnalysisResult:
    """Structured output from the analyzer."""

    table_type: str
    suggested_caption: Optional[str]
    suggested_summary: Optional[str]
    header_rows_detected: int
    header_cols_detected: int
    warnings: List[str] = field(default_factory=list)
    confidence: float = 0.0


def analyze_table(request: TableAnalysisRequest) -> TableAnalysisResult:
    """Invoke the AI provider and return structured table analysis.

    Raises TableAnalysisError on any failure, including "no AI provider
    is currently available" (model not loaded, insufficient resources,
    dependencies not installed).
    """
    from src.ai.provider import AIProviderUnavailableError
    from src.ai.registry import get_provider

    try:
        provider = get_provider()
    except AIProviderUnavailableError as exc:
        logger.warning("Table AI analysis unavailable: {}", exc)
        raise TableAnalysisError(str(exc)) from exc

    return provider.analyze_table(request)
