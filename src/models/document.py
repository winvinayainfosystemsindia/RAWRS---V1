"""Document model for RAWRS - the root aggregate of the processing pipeline.

See docs/ARCHITECTURE.md for the canonical processing flow this model
moves through, and docs/RAWRS_PROJECT_CONTEXT.md for the overall
PDF -> Markdown -> DOCX goal.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from src.models.correction import CorrectionRecord
from src.models.footnote import Footnote
from src.models.front_matter import FrontMatter
from src.models.heading import Heading
from src.models.image import Image
from src.models.metadata import Metadata
from src.models.page import Page
from src.models.sanitization import SanitizationEvent
from src.models.table import Table
from src.models.text_block import TextBlock
from src.models.validation_issue import ValidationIssue


class ProcessingStatus(str, Enum):
    """Lifecycle status of a Document as it moves through the pipeline."""

    UPLOADED = "uploaded"
    PARSED = "parsed"
    OCR_COMPLETE = "ocr_complete"
    MARKDOWN_COMPLETE = "markdown_complete"
    DOCX_COMPLETE = "docx_complete"
    VALIDATED = "validated"
    FAILED = "failed"


class Document(BaseModel):
    """The root aggregate representing one PDF being processed by RAWRS.

    ``pages`` is the ordered list of PDF pages (no gaps, no reordering,
    per docs/PAGE_RULES.md). ``headings``, ``images``, and ``blocks``
    are the document-wide, flattened lists of every heading, image, and
    structural text block detected across all pages; each item carries
    its own ``page_number`` so a per-page view can be derived by
    filtering rather than by storing the same objects twice on both
    Document and Page. ``blocks`` is populated by
    src/structure/structure_detector.py (Phase H - see
    docs/ARCHITECTURE.md's "Structure Detection" stage); reading order
    reconstruction and multi-column detection still don't consume it,
    but src/footnotes/footnote_detector.py (Phase K) now does, for
    exactly the font-size/position signal it needs. ``footnotes``
    (Phase K) is the document-wide list of confidently detected
    footnotes/endnotes - see src/models/footnote.py for why this exists
    instead of just Page.footnote_references/endnote_references (kept,
    but now populated as a projection of this list, not a competing
    source of truth). ``validation_issues`` is the canonical attachment
    point for the Validation stage's output (see docs/VALIDATION_RULES.md
    and docs/ARCHITECTURE.md). ``sanitization_events`` (XML Sanitization
    Architecture, Layer 1) records every place src/utils/text_sanitization.py
    removed an XML/OOXML-illegal character from extracted text, at the
    moment it happened - see src/models/sanitization.py for why this
    can't be re-derived later from already-clean Page/TextBlock text.
    ``front_matter`` (Front-Matter Semantic Extraction) is the
    document's confidently-extracted title/author(s)/affiliation(s) -
    see src/models/front_matter.py and
    src/frontmatter/front_matter_extractor.py. None until that stage
    runs; never a guess when extraction finds no confident title.
    """

    source_pdf_path: str = Field(..., min_length=1)
    processing_status: ProcessingStatus = ProcessingStatus.UPLOADED
    metadata: Metadata
    pages: List[Page] = Field(default_factory=list)
    headings: List[Heading] = Field(default_factory=list)
    images: List[Image] = Field(default_factory=list)
    blocks: List[TextBlock] = Field(default_factory=list)
    footnotes: List[Footnote] = Field(default_factory=list)
    tables: List[Table] = Field(default_factory=list)
    validation_issues: List[ValidationIssue] = Field(default_factory=list)
    sanitization_events: List[SanitizationEvent] = Field(default_factory=list)
    front_matter: Optional[FrontMatter] = None
    # Verification audit trail: every RAWRS correction to imported content.
    # Preserves original provider value + proposed correction + reviewer decision.
    corrections: List[CorrectionRecord] = Field(default_factory=list)
