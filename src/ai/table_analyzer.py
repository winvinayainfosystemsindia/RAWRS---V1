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

Model: text-only analysis uses the same Qwen2.5-VL model already loaded
for image alt text (lazy-cached). When a page image is supplied, the
model can also analyse visual structure (borders, shading, layout).

Stub mode: if the RAWRS_AI_STUB environment variable is set (any
non-empty value), analyze_table() returns a deterministic fake result
based on cell content patterns without loading any model. This is used
in all unit and API tests.
"""

import os
import re
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
    """Invoke the local AI model and return structured table analysis.

    Raises TableAnalysisError on any failure.

    In RAWRS_AI_STUB mode, returns a deterministic result derived from
    cell content patterns — no model is loaded or called.
    """
    if os.environ.get("RAWRS_AI_STUB"):
        return _stub_result(request)

    _ensure_model_loaded()
    return _run_inference(request)


# ---------------------------------------------------------------------------
# Stub (test mode)
# ---------------------------------------------------------------------------

def _stub_result(request: TableAnalysisRequest) -> TableAnalysisResult:
    """Deterministic stub that inspects cell patterns to make sensible guesses.

    This runs without any AI model and is used in all tests. It applies
    simple rules (first row non-numeric → likely header, first col
    non-numeric → likely row headers, all-numeric body → data table)
    so stub output is useful for acceptance testing even without a model.
    """
    warnings: List[str] = []
    rows = request.cells
    if not rows:
        return TableAnalysisResult(
            table_type="unknown",
            suggested_caption=None,
            suggested_summary=None,
            header_rows_detected=0,
            header_cols_detected=0,
            warnings=["Table has no cells"],
            confidence=0.1,
        )

    # Simple heuristics for stub
    first_row = rows[0] if rows else []
    first_col = [row[0] for row in rows if row] if rows else []
    body_rows = rows[request.header_row_count:]

    header_rows_detected = request.header_row_count or (
        1 if first_row and not all(_looks_numeric(c) for c in first_row) else 0
    )

    header_cols_detected = request.header_col_count or (
        1 if (
            len(first_col) >= 2
            and not _looks_numeric(first_col[0])
            and all(not _looks_numeric(c) for c in first_col[1:])
        ) else 0
    )

    # Decide table type
    all_numeric_body = body_rows and all(
        _looks_numeric(c) for row in body_rows for c in row if c
    )
    has_many_rows = request.row_count > 5
    table_type = "data" if all_numeric_body else ("complex" if has_many_rows else "simple")

    # Build stub caption
    suggested_caption = request.existing_caption
    if not suggested_caption and first_row:
        header_text = " / ".join(c for c in first_row[:3] if c)
        if header_text:
            suggested_caption = f"Table: {header_text}…"

    # Build stub summary
    suggested_summary = (
        f"A {request.row_count}-row by {request.col_count}-column {table_type} table. "
        f"Row headers: {'yes' if header_cols_detected else 'no'}. "
        "Review and edit this summary for screen reader users."
    )

    if request.row_count > 10:
        warnings.append("Large table — consider splitting or summarizing for screen readers.")
    if not request.existing_caption:
        warnings.append("No caption provided — add a descriptive caption for accessibility.")
    if header_rows_detected == 0:
        warnings.append("No clear column headers detected — verify header row assignment.")

    return TableAnalysisResult(
        table_type=table_type,
        suggested_caption=suggested_caption,
        suggested_summary=suggested_summary,
        header_rows_detected=header_rows_detected,
        header_cols_detected=header_cols_detected,
        warnings=warnings,
        confidence=0.5,
    )


def _looks_numeric(text: str) -> bool:
    """Return True when text looks like a number, percentage, or similar data value."""
    text = text.strip()
    if not text:
        return False
    return bool(re.match(r"^[-+]?\d[\d,.%\s]*$", text))


# ---------------------------------------------------------------------------
# Real inference path
# ---------------------------------------------------------------------------

_model = None
_processor = None


def _ensure_model_loaded() -> None:
    global _model, _processor
    if _model is not None:
        return

    try:
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration  # type: ignore
        import torch  # type: ignore
    except ImportError as exc:
        raise TableAnalysisError(
            "Qwen2.5-VL dependencies not installed. "
            "Run: pip install transformers qwen-vl-utils torch. "
            f"Original error: {exc}"
        ) from exc

    logger.info("Loading Qwen2.5-VL model for table analysis (first call)…")
    try:
        model_id = "Qwen/Qwen2.5-VL-7B-Instruct"
        import torch  # type: ignore
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
        _model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_id,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            device_map="auto" if device == "cuda" else None,
            trust_remote_code=True,
        )
        if device == "cpu":
            _model = _model.to(device)
        logger.info("Qwen2.5-VL loaded on {} for table analysis", device)
    except Exception as exc:
        raise TableAnalysisError(f"Failed to load Qwen2.5-VL model: {exc}") from exc


_TABLE_PROMPT_TEMPLATE = """\
You are an accessibility expert analyzing a data table from an academic document.

Table structure:
- {row_count} rows × {col_count} columns
- Existing caption: {caption}
- Cell content (first 5 rows shown):
{cell_preview}

Analyze this table and respond in EXACTLY this format (no other text before or after):
TABLE_TYPE: <simple|complex|data|layout>
SUGGESTED_CAPTION: <one concise sentence describing the table, or KEEP if the existing caption is good>
SUGGESTED_SUMMARY: <2-3 sentences describing what the table shows, for screen reader users>
HEADER_ROWS: <integer — how many leading rows are column headers, typically 1 or 2>
HEADER_COLS: <integer — how many leading columns are row headers, typically 0 or 1>
WARNINGS: <comma-separated accessibility warnings, or None>
CONFIDENCE: <0.0 to 1.0>
"""


def _run_inference(request: TableAnalysisRequest) -> TableAnalysisResult:
    import torch  # type: ignore

    # Build cell preview (first 5 rows)
    preview_rows = request.cells[:5]
    cell_preview = "\n".join(
        "  Row {}: {}".format(i + 1, " | ".join(f'"{c}"' for c in row))
        for i, row in enumerate(preview_rows)
    )

    prompt = _TABLE_PROMPT_TEMPLATE.format(
        row_count=request.row_count,
        col_count=request.col_count,
        caption=request.existing_caption or "None",
        cell_preview=cell_preview,
    )

    content: list
    if request.image_path:
        try:
            from pathlib import Path
            from PIL import Image as PILImage  # type: ignore
            pil_image = PILImage.open(Path(request.image_path)).convert("RGB")
            content = [
                {"type": "image", "image": pil_image},
                {"type": "text", "text": prompt},
            ]
        except Exception:
            content = [{"type": "text", "text": prompt}]
    else:
        content = [{"type": "text", "text": prompt}]

    messages = [{"role": "user", "content": content}]

    try:
        text_input = _processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        images = [content[0]["image"]] if request.image_path and len(content) > 1 else None
        if images:
            inputs = _processor(text=[text_input], images=images, return_tensors="pt")
        else:
            inputs = _processor(text=[text_input], return_tensors="pt")

        device = next(_model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            output_ids = _model.generate(**inputs, max_new_tokens=400, do_sample=False)
        response_text = _processor.decode(
            output_ids[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        )
    except Exception as exc:
        raise TableAnalysisError(f"Inference failed: {exc}") from exc

    return _parse_response(response_text)


def _parse_response(text: str) -> TableAnalysisResult:
    """Parse structured TABLE_TYPE/SUGGESTED_CAPTION/... response."""
    fields: dict = {}
    for line in text.strip().splitlines():
        m = re.match(
            r"^(TABLE_TYPE|SUGGESTED_CAPTION|SUGGESTED_SUMMARY|HEADER_ROWS|HEADER_COLS|WARNINGS|CONFIDENCE):\s*(.+)$",
            line.strip(),
        )
        if m:
            fields[m.group(1)] = m.group(2).strip()

    required = {"TABLE_TYPE", "SUGGESTED_CAPTION", "SUGGESTED_SUMMARY",
                "HEADER_ROWS", "HEADER_COLS", "WARNINGS", "CONFIDENCE"}
    missing = required - set(fields)
    if missing:
        raise TableAnalysisError(
            f"Model response missing required fields: {', '.join(sorted(missing))}. "
            f"Raw response: {text[:200]!r}"
        )

    try:
        confidence = float(fields["CONFIDENCE"])
        confidence = max(0.0, min(1.0, confidence))
    except ValueError:
        confidence = 0.0

    try:
        header_rows = int(fields["HEADER_ROWS"])
    except ValueError:
        header_rows = 1

    try:
        header_cols = int(fields["HEADER_COLS"])
    except ValueError:
        header_cols = 0

    raw_warnings = fields["WARNINGS"].strip()
    warnings = (
        [] if raw_warnings.lower() == "none"
        else [w.strip() for w in raw_warnings.split(",") if w.strip()]
    )

    caption = fields["SUGGESTED_CAPTION"]
    if caption.upper() == "KEEP":
        caption = None

    return TableAnalysisResult(
        table_type=fields["TABLE_TYPE"].lower(),
        suggested_caption=caption if caption else None,
        suggested_summary=fields["SUGGESTED_SUMMARY"],
        header_rows_detected=max(0, header_rows),
        header_cols_detected=max(0, header_cols),
        warnings=warnings,
        confidence=confidence,
    )
