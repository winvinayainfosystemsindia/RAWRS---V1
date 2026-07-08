"""Canonical contract layer for RAWRS shared models.

Per docs/CLAUDE_INSTRUCTIONS.md (Data Model Rules), every module in the
pipeline (parser, ocr, headings, images, markdown, validation, docx)
must import shared data models from this module rather than importing
model files directly or defining module-specific data structures.

This module does not define any new model - it re-exports the model
classes from their individual files so that the internal layout of
src/models/ can change without changing every other module's imports.
"""

from src.models.bounding_box import BoundingBox
from src.models.callout import Callout
from src.models.correction import CorrectionRecord, CorrectionStatus
from src.models.document import Document, ProcessingStatus
from src.models.figure import AltTextStatus, Figure
from src.models.footnote import Footnote, FootnoteReviewStatus, NoteType
from src.models.front_matter import FrontMatter
from src.models.heading import Heading, HeadingLevel, HeadingReviewStatus
from src.models.image import Image
from src.models.lifecycle import ObjectLifecycleStatus
from src.models.list_block import ListBlock, ListItem, ListType
from src.models.metadata import Metadata
from src.models.page import (
    ExtractionMethod,
    OCRConfidence,
    Page,
    PageLabelSection,
    PageLabelStatus,
    PageLabelStyle,
    PageType,
    ReadingOrderStatus,
    RoutingDecision,
)
from src.models.paragraph import Paragraph
from src.models.sanitization import SanitizationEvent
from src.models.semantic_object import ProvenanceSource, SemanticObject
from src.models.span import Span
from src.models.table import Table, TableAISuggestions, TableCell, TableRow, TableStatus
from src.models.text_block import TextBlock
from src.models.validation_issue import Severity, ValidationIssue
from src.models.verification import (
    BenchmarkOutcome,
    Finding,
    ImportSource,
    RepairSuggestion,
    RuleSpec,
    VerificationStatus,
)
from src.verification.evidence import EvidenceBundle, EvidenceSignal

__all__ = [
    "AltTextStatus",
    "BenchmarkOutcome",
    "BoundingBox",
    "Callout",
    "CorrectionRecord",
    "CorrectionStatus",
    "Document",
    "ProcessingStatus",
    "EvidenceBundle",
    "EvidenceSignal",
    "ExtractionMethod",
    "Figure",
    "Finding",
    "Footnote",
    "FootnoteReviewStatus",
    "FrontMatter",
    "Heading",
    "HeadingLevel",
    "HeadingReviewStatus",
    "Image",
    "ImportSource",
    "ListBlock",
    "ListItem",
    "ListType",
    "Metadata",
    "ObjectLifecycleStatus",
    "NoteType",
    "OCRConfidence",
    "Page",
    "PageLabelSection",
    "PageLabelStatus",
    "PageLabelStyle",
    "PageType",
    "Paragraph",
    "ProvenanceSource",
    "ReadingOrderStatus",
    "RepairSuggestion",
    "RoutingDecision",
    "RuleSpec",
    "SanitizationEvent",
    "SemanticObject",
    "Severity",
    "Span",
    "Table",
    "TableAISuggestions",
    "TableCell",
    "TableRow",
    "TableStatus",
    "TextBlock",
    "ValidationIssue",
    "VerificationStatus",
]
