"""Tests for src/accessibility/rules/*.py - one class per rule category,
matching this project's test_headings.py/test_images.py/test_table_*.py
per-module convention. Documents are built directly (no PDF parse), the
same lightweight-fixture pattern tests/test_validation.py uses.
"""

from datetime import datetime, timezone

import pytest

from src.accessibility.models import RuleOutcome
from src.accessibility.rules.headings import (
    EmptyHeadingRule,
    HeadingHierarchyJumpRule,
    MissingH1Rule,
    MultipleH1Rule,
)
from src.accessibility.rules.images import AltTextConfirmedRule, ImageEmbeddedRule
from src.accessibility.rules.metadata import DocumentLanguageDeclaredRule, DocumentTitleSetRule
from src.accessibility.rules.reading_order import ReadingOrderAnomalyRule
from src.accessibility.rules.tables import (
    TableCaptionRule,
    TableConfidenceGateRule,
    TableHeaderCellsFilledRule,
    TableHeaderRowRule,
    TableSummaryRule,
)
from src.models.contracts import (
    AltTextStatus,
    BoundingBox,
    Document,
    Figure,
    Heading,
    HeadingLevel,
    Image,
    Metadata,
    Table,
    TableCell,
    TableRow,
    TableStatus,
    TextBlock,
)


def _document(**overrides) -> Document:
    defaults = dict(
        source_pdf_path="dummy.pdf",
        metadata=Metadata(filename="dummy.pdf", page_count=1, image_count=0, processing_date=datetime.now(timezone.utc)),
        pages=[],
    )
    defaults.update(overrides)
    return Document(**defaults)


def _with_pages(n: int, **overrides) -> Document:
    from src.models.contracts import Page

    return _document(pages=[Page(page_number=i + 1) for i in range(n)], **overrides)


class TestHeadingRules:
    def test_missing_h1_fails_on_document_with_no_h1(self):
        doc = _with_pages(1, headings=[Heading(level=HeadingLevel.H2, text="Intro", page_number=1, document_order=0)])
        [ev] = MissingH1Rule().evaluate(doc)
        assert ev.outcome == RuleOutcome.FAIL

    def test_missing_h1_passes_when_h1_present(self):
        doc = _with_pages(1, headings=[Heading(level=HeadingLevel.H1, text="Title", page_number=1, document_order=0)])
        [ev] = MissingH1Rule().evaluate(doc)
        assert ev.outcome == RuleOutcome.PASS
        assert ev.confidence == 1.0

    def test_missing_h1_skips_empty_document(self):
        doc = _document(pages=[])
        assert MissingH1Rule().evaluate(doc) == []

    def test_hierarchy_jump_fails_h1_to_h3(self):
        doc = _with_pages(
            1,
            headings=[
                Heading(level=HeadingLevel.H1, text="Title", page_number=1, document_order=0),
                Heading(level=HeadingLevel.H3, text="Sub", page_number=1, document_order=1),
            ],
        )
        [ev] = HeadingHierarchyJumpRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.FAIL

    def test_hierarchy_no_jump_passes(self):
        doc = _with_pages(
            1,
            headings=[
                Heading(level=HeadingLevel.H1, text="Title", page_number=1, document_order=0),
                Heading(level=HeadingLevel.H2, text="Sub", page_number=1, document_order=1),
            ],
        )
        [ev] = HeadingHierarchyJumpRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.PASS

    def test_multiple_h1_fails(self):
        doc = _with_pages(
            1,
            headings=[
                Heading(level=HeadingLevel.H1, text="A", page_number=1, document_order=0),
                Heading(level=HeadingLevel.H1, text="B", page_number=1, document_order=1),
            ],
        )
        [ev] = MultipleH1Rule().evaluate(doc)
        assert ev.outcome == RuleOutcome.FAIL

    def test_empty_heading_fails(self):
        # Heading itself rejects blank text at construction; bypass via
        # model_construct() purely to exercise this otherwise-unreachable
        # defensive case - same technique tests/test_validation.py already
        # uses for the equivalent HEADING_003 check.
        blank_heading = Heading.model_construct(
            level=HeadingLevel.H1, text="   ", page_number=1, document_order=0, is_page_marker=False
        )
        doc = _with_pages(1, headings=[blank_heading])
        [ev] = EmptyHeadingRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.FAIL


class TestImageRules:
    def _image(self, **overrides):
        defaults = dict(image_id="img1", page_number=1, file_path=__file__)
        defaults.update(overrides)
        return Image(**defaults)

    def test_alt_text_pending_review_requires_manual_review(self):
        image = self._image(figure=Figure(alt_text_status=AltTextStatus.PENDING_REVIEW))
        doc = _document(images=[image])
        [ev] = AltTextConfirmedRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.MANUAL_REVIEW_REQUIRED

    def test_alt_text_human_reviewed_passes(self):
        image = self._image(figure=Figure(alt_text_status=AltTextStatus.HUMAN_REVIEWED))
        doc = _document(images=[image])
        [ev] = AltTextConfirmedRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.PASS

    def test_alt_text_ai_generated_still_requires_human_review(self):
        # AI ran but no human has confirmed it yet - must not silently PASS
        # (Design Bible Product Principle 2: "Human Review, Always").
        image = self._image(figure=Figure(alt_text_status=AltTextStatus.AI_GENERATED))
        doc = _document(images=[image])
        [ev] = AltTextConfirmedRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.MANUAL_REVIEW_REQUIRED

    def test_alt_text_approved_passes(self):
        image = self._image(figure=Figure(alt_text_status=AltTextStatus.APPROVED))
        doc = _document(images=[image])
        [ev] = AltTextConfirmedRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.PASS

    def test_no_figure_produces_no_evaluation(self):
        doc = _document(images=[self._image(figure=None)])
        assert AltTextConfirmedRule().evaluate(doc) == []

    def test_embedded_true_passes(self):
        doc = _document(images=[self._image(embedded_in_docx=True)])
        [ev] = ImageEmbeddedRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.PASS

    def test_embedded_false_fails(self):
        doc = _document(images=[self._image(embedded_in_docx=False)])
        [ev] = ImageEmbeddedRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.FAIL

    def test_never_generated_produces_no_evaluation(self):
        doc = _document(images=[self._image(embedded_in_docx=None)])
        assert ImageEmbeddedRule().evaluate(doc) == []


class TestTableRules:
    def _table(self, **overrides):
        defaults = dict(
            table_id="t1",
            page_number=1,
            row_count=1,
            col_count=1,
            rows=[TableRow(cells=[TableCell(text="a", row_index=0, col_index=0)])],
        )
        defaults.update(overrides)
        return Table(**defaults)

    def test_caption_missing_fails(self):
        doc = _document(tables=[self._table(caption=None)])
        [ev] = TableCaptionRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.FAIL

    def test_caption_present_passes(self):
        doc = _document(tables=[self._table(caption="Table 1. Results")])
        [ev] = TableCaptionRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.PASS

    def test_summary_missing_fails(self):
        doc = _document(tables=[self._table(summary=None)])
        [ev] = TableSummaryRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.FAIL

    def test_no_header_row_fails(self):
        doc = _document(tables=[self._table(rows=[TableRow(cells=[TableCell(text="a", row_index=0, col_index=0)], is_header_row=False)])])
        [ev] = TableHeaderRowRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.FAIL

    def test_header_row_present_passes(self):
        doc = _document(tables=[self._table(rows=[TableRow(cells=[TableCell(text="a", row_index=0, col_index=0, is_header=True)], is_header_row=True)])])
        [ev] = TableHeaderRowRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.PASS

    def test_empty_header_cell_fails(self):
        row = TableRow(cells=[TableCell(text="", row_index=0, col_index=0, is_header=True)], is_header_row=True)
        doc = _document(tables=[self._table(rows=[row])])
        [ev] = TableHeaderCellsFilledRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.FAIL

    def test_no_header_row_skips_header_cells_rule(self):
        row = TableRow(cells=[TableCell(text="", row_index=0, col_index=0)], is_header_row=False)
        doc = _document(tables=[self._table(rows=[row])])
        assert TableHeaderCellsFilledRule().evaluate(doc) == []

    def test_low_confidence_auto_detected_requires_manual_review(self):
        doc = _document(tables=[self._table(status=TableStatus.AUTO_DETECTED, confidence=0.4)])
        [ev] = TableConfidenceGateRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.MANUAL_REVIEW_REQUIRED

    def test_high_confidence_passes(self):
        doc = _document(tables=[self._table(status=TableStatus.AUTO_DETECTED, confidence=0.95)])
        [ev] = TableConfidenceGateRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.PASS

    def test_manually_created_table_never_manual_review_gated(self):
        doc = _document(tables=[self._table(status=TableStatus.MANUALLY_CREATED, confidence=0.1)])
        [ev] = TableConfidenceGateRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.PASS

    def test_borderless_single_column_requires_manual_review_even_at_high_confidence(self):
        # TABLE_007 condition (validator.py) folded into TABLE_A11Y_005:
        # detected via horizontal-rule/column-alignment signals with no
        # vector borders and only one inferred column.
        doc = _document(
            tables=[
                self._table(
                    status=TableStatus.MANUALLY_CREATED,  # not AUTO_DETECTED - confidence check alone wouldn't fire
                    confidence=0.95,
                    col_count=1,
                    evidence_signals=[{"name": "horizontal_rules"}],
                )
            ]
        )
        [ev] = TableConfidenceGateRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.MANUAL_REVIEW_REQUIRED

    def test_vector_border_detected_table_not_flagged_as_borderless(self):
        doc = _document(
            tables=[
                self._table(
                    status=TableStatus.MANUALLY_CREATED,
                    confidence=0.95,
                    col_count=1,
                    evidence_signals=[{"name": "horizontal_rules"}, {"name": "vector_borders"}],
                )
            ]
        )
        [ev] = TableConfidenceGateRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.PASS

    def test_confidence_gate_rule_not_required_for_export(self):
        assert TableConfidenceGateRule().required_for_export is False

    def test_zero_tables_produces_no_evaluations(self):
        doc = _document(tables=[])
        assert TableCaptionRule().evaluate(doc) == []


class TestMetadataLanguageRules:
    def test_no_language_fails(self):
        doc = _document(metadata=Metadata(filename="d.pdf", page_count=0, image_count=0, language=None))
        [ev] = DocumentLanguageDeclaredRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.FAIL

    def test_language_set_passes(self):
        doc = _document(metadata=Metadata(filename="d.pdf", page_count=0, image_count=0, language="en-US"))
        [ev] = DocumentLanguageDeclaredRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.PASS

    def test_no_title_fails(self):
        doc = _document(metadata=Metadata(filename="d.pdf", page_count=0, image_count=0, title=None))
        [ev] = DocumentTitleSetRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.FAIL

    def test_title_set_passes(self):
        doc = _document(metadata=Metadata(filename="d.pdf", page_count=0, image_count=0, title="A Title"))
        [ev] = DocumentTitleSetRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.PASS


class TestReadingOrderRule:
    def test_no_blocks_no_anomaly_passes(self):
        doc = _with_pages(1, blocks=[])
        [ev] = ReadingOrderAnomalyRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.PASS

    def test_backward_jump_fails(self):
        # Second block sits far above the first, in reading order - the
        # signature _count_backward_jumps() flags.
        blocks = [
            TextBlock(page_number=1, text="second visually, first in order", bbox=BoundingBox(x0=0, y0=500, x1=100, y1=520), order=0),
            TextBlock(page_number=1, text="first visually, second in order", bbox=BoundingBox(x0=0, y0=100, x1=100, y1=120), order=1),
        ]
        doc = _with_pages(1, blocks=blocks)
        [ev] = ReadingOrderAnomalyRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.FAIL

    def test_normal_top_to_bottom_flow_passes(self):
        blocks = [
            TextBlock(page_number=1, text="first", bbox=BoundingBox(x0=0, y0=100, x1=100, y1=120), order=0),
            TextBlock(page_number=1, text="second", bbox=BoundingBox(x0=0, y0=130, x1=100, y1=150), order=1),
        ]
        doc = _with_pages(1, blocks=blocks)
        [ev] = ReadingOrderAnomalyRule().evaluate(doc)
        assert ev.outcome == RuleOutcome.PASS

    def test_empty_document_produces_no_evaluation(self):
        doc = _document(pages=[])
        assert ReadingOrderAnomalyRule().evaluate(doc) == []
