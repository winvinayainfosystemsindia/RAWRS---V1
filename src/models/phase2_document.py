"""Phase 2 document model.

Separate from the Phase 1 Document model — Phase 1 is PDF-centric and
carries OCR / bbox / layout data that has no meaning for Mathpix MMD
ingestion. Phase 2 is text-centric: the source is already extracted text
in LaTeX-like MMD syntax.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class P2BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    FIGURE = "figure"
    FOOTNOTE_BODY = "footnote_body"
    ABSTRACT = "abstract"
    BLOCKQUOTE = "blockquote"
    LIST_ITEM = "list_item"
    PAGE_MARKER = "page_marker"
    SEPARATOR = "separator"
    PUBLISHER_LINE = "publisher_line"


class P2ListStyle(str, Enum):
    BULLET = "bullet"
    NUMBERED = "numbered"


@dataclass
class P2FrontMatter:
    title: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    affiliation: Optional[str] = None
    publisher: Optional[str] = None


@dataclass
class P2Heading:
    level: int  # 1-6
    text: str
    source: str = "mmd"  # "mmd" | "docx_supplement"
    is_running_header: bool = False
    mmd_command: str = "section*"  # "title" | "section*" | "subsection*" | etc.
    # Set by src/mathpix/mmd_parser.py::classify_callout_type() when this
    # heading's text matches a known boxed-aside label pattern (Case
    # study/Thinking point/Key ideas/Summary/Activity) — None for an
    # ordinary content heading. See src/models/callout.py.
    callout_type: Optional[str] = None


@dataclass
class P2TableCell:
    text: str
    col_span: int = 1
    row_span: int = 1


@dataclass
class P2Table:
    rows: List[List[P2TableCell]] = field(default_factory=list)
    caption: Optional[str] = None
    has_header_row: bool = False


@dataclass
class P2Figure:
    image_path: Optional[str] = None
    caption: Optional[str] = None
    alt_text: Optional[str] = None
    is_cover_figure: bool = False


@dataclass
class P2Footnote:
    number: int
    body: str


@dataclass
class P2Block:
    block_type: P2BlockType
    heading: Optional[P2Heading] = None
    text: Optional[str] = None
    table: Optional[P2Table] = None
    figure: Optional[P2Figure] = None
    footnote: Optional[P2Footnote] = None
    page_label: Optional[str] = None
    list_style: Optional[P2ListStyle] = None
    list_number: Optional[int] = None
    source_line: int = 0


@dataclass
class P2ValidationIssue:
    rule_id: str
    message: str
    severity: str = "WARNING"


@dataclass
class P2Document:
    source_path: Optional[str] = None
    front_matter: Optional[P2FrontMatter] = None
    blocks: List[P2Block] = field(default_factory=list)
    footnotes: List[P2Footnote] = field(default_factory=list)
    page_count: Optional[int] = None
    has_docx_supplement: bool = False
    running_headers_detected: List[str] = field(default_factory=list)
    validation_issues: List[P2ValidationIssue] = field(default_factory=list)
