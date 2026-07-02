"""PDF-side list detection — the geometric candidate source ListVerifier
(src/verification/lists.py) matches against Mathpix-derived ``ListBlock``s.

Reuses the exact bullet/numbered-marker regexes already defined in
``src/docx/docx_generator.py`` (FEATURE_016C) rather than redefining an
equivalent pattern — those regexes already encode which glyphs/prefixes
are unambiguous list markers, calibrated against the real benchmark
corpus. This module adds the one thing that convention doesn't do:
clustering consecutive marked lines (by PyMuPDF reading order and
left-indent) into a single ``ListBlock``, and a minimal nesting signal
(indent-relative level) — the geometry analysis a plain per-line regex
match can't provide on its own.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import fitz  # PyMuPDF
from loguru import logger

from src.docx.docx_generator import _BULLET_LIST_PATTERN, _NUMBERED_LIST_PATTERN
from src.models.list_block import ListBlock, ListItem, ListType

# Two consecutive list lines whose left-indent (x0) differs by at least
# this many points are treated as different nesting levels. Deliberately
# coarse — this is a minimal nesting signal, not a full outline-level
# reconstruction.
# ponytail: single fixed indent-step threshold, not calibrated per PDF
# producer; revisit with real per-level indent measurements if a
# benchmark PDF turns up 3+ genuine nesting levels this misclassifies.
_INDENT_LEVEL_STEP_PT = 15.0


def _classify_marker(text: str) -> Optional[ListType]:
    if _BULLET_LIST_PATTERN.match(text):
        return ListType.BULLET
    if _NUMBERED_LIST_PATTERN.match(text):
        return ListType.NUMBERED
    return None


def _strip_marker(text: str, list_type: ListType) -> str:
    pattern = _BULLET_LIST_PATTERN if list_type == ListType.BULLET else _NUMBERED_LIST_PATTERN
    match = pattern.match(text)
    return match.group(2).strip() if match else text


def detect_lists_from_pdf(pdf_path: Path) -> List[ListBlock]:
    """Pure PDF-side candidate source for cross-source verification.

    Never touches a Document; never raises — an unreadable PDF yields [].
    Content only — this has no concept of a canonical list's identity, so
    every call produces a fresh candidate list to be matched against
    canonical (Mathpix-derived) ListBlocks by ListVerifier.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        return []

    try:
        pdf_document = fitz.open(pdf_path)
    except Exception as exc:  # PyMuPDF raises various error types on bad input
        logger.warning("Could not open PDF for list candidate detection '{}': {}", pdf_path, exc)
        return []

    lists: List[ListBlock] = []
    order = 0

    try:
        for page_index in range(pdf_document.page_count):
            page_number = page_index + 1
            page_dict = pdf_document[page_index].get_text("dict")

            current_type: Optional[ListType] = None
            current_items: List[ListItem] = []
            base_indent: Optional[float] = None

            def flush() -> None:
                nonlocal current_type, current_items, base_indent, order
                if current_type is not None and current_items:
                    lists.append(
                        ListBlock(
                            list_type=current_type,
                            items=list(current_items),
                            page_number=page_number,
                            document_order=order,
                        )
                    )
                    order += 1
                current_type = None
                current_items = []
                base_indent = None

            for block in page_dict.get("blocks", []):
                for line_dict in block.get("lines", []):
                    spans = line_dict.get("spans", [])
                    text = "".join(span.get("text", "") for span in spans).strip()
                    if not text:
                        flush()
                        continue

                    list_type = _classify_marker(text)
                    if list_type is None or (current_type is not None and list_type != current_type):
                        flush()
                        if list_type is None:
                            continue

                    x0 = line_dict.get("bbox", [0.0])[0]
                    if current_type is None:
                        current_type = list_type
                        base_indent = x0
                    level = 0
                    if base_indent is not None and x0 - base_indent >= _INDENT_LEVEL_STEP_PT:
                        level = int((x0 - base_indent) // _INDENT_LEVEL_STEP_PT)

                    current_items.append(ListItem(text=_strip_marker(text, list_type), level=level))

            flush()
    finally:
        pdf_document.close()

    return lists
