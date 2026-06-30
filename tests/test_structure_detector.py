"""Tests for src/structure/structure_detector.py (Phase H: Structure
Detection foundation).

Mirrors tests/test_headings.py's pattern of building real, tiny PDFs
with fitz so layout/bbox signal is read from a genuine file rather than
mocked - bbox/font data is exactly what this module exists to persist,
so a synthetic Document with no backing PDF can't exercise it.
"""

from pathlib import Path
from typing import List, Tuple

import fitz
import pytest

from src.models.contracts import (
    Document,
    ExtractionMethod,
    Metadata,
    OCRConfidence,
    Page,
    PageType,
    RoutingDecision,
)
from conftest import BENCHMARK_MANIFEST, a_scanned_pdf
from src.ocr.extractor import extract_text
from src.parser.pdf_parser import parse_pdf
from src.structure.structure_detector import detect_structure

SAMPLE_PDF_DIR = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"
SAMPLE_PDFS = sorted(SAMPLE_PDF_DIR.glob("*.pdf"))
SCANNED_PDF = a_scanned_pdf()  # manifest-declared (samples/benchmark/manifest.json)


def _build_real_pdf(tmp_path: Path, pages_lines: List[List[Tuple[str, str, float]]]) -> Path:
    """Build a real, multi-page PDF with controlled per-line text/font.

    pages_lines: one list of (text, fontname, fontsize) per page.
    fontname should be a PyMuPDF builtin alias, e.g. "helv" (Helvetica)
    or "hebo" (Helvetica-Bold).
    """
    pdf_path = tmp_path / "structure.pdf"
    doc = fitz.open()
    for lines in pages_lines:
        page = doc.new_page()
        y = 72.0
        for text, fontname, fontsize in lines:
            page.insert_text((72, y), text, fontname=fontname, fontsize=fontsize)
            y += fontsize + 10
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def _ocr_pending_page(page_number: int) -> Page:
    """A page Docling/Surya have not (yet, in this test) recovered text
    for - mirrors the real OCR_PENDING state on a freshly-routed,
    not-yet-OCR'd scanned page."""
    return Page(
        page_number=page_number,
        page_type=PageType.OCR_REQUIRED,
        extraction_method=ExtractionMethod.OCR_PENDING,
        routing_decision=RoutingDecision.ROUTE_TO_OCR_PLACEHOLDER,
    )


def _ocr_recovered_page(page_number: int, text: str) -> Page:
    """A page whose Page.cleaned_text was populated by OCR (Docling or
    Surya) - not by a native PDF text layer. Used to prove Structure
    Detection's documented boundary: it reads the PDF's own text layer,
    never Page.cleaned_text, so OCR-recovered text alone yields zero
    blocks unless the underlying PDF page also has real text objects."""
    return Page(
        page_number=page_number,
        cleaned_text=text,
        raw_text=text,
        ocr_confidence=OCRConfidence.MEDIUM,
        page_type=PageType.OCR_REQUIRED,
        extraction_method=ExtractionMethod.DOCLING,
        routing_decision=RoutingDecision.ROUTE_TO_DOCLING,
    )


class TestBlockExtraction:
    def test_extracts_one_block_per_line(self, tmp_path: Path) -> None:
        pdf_path = _build_real_pdf(
            tmp_path,
            [[("First line", "helv", 12.0), ("Second line", "helv", 12.0)]],
        )
        document = extract_text(parse_pdf(pdf_path))

        detect_structure(document)

        assert [b.text for b in document.blocks] == ["First line", "Second line"]
        assert all(b.page_number == 1 for b in document.blocks)

    def test_blank_lines_are_not_extracted_as_blocks(self, tmp_path: Path) -> None:
        # insert_text with an empty string still creates a span in some
        # PyMuPDF versions; line_layout() must filter it out regardless.
        pdf_path = _build_real_pdf(tmp_path, [[("Only real line", "helv", 12.0)]])
        document = extract_text(parse_pdf(pdf_path))

        detect_structure(document)

        assert all(b.text.strip() for b in document.blocks)

    def test_font_size_and_bold_signal_are_captured(self, tmp_path: Path) -> None:
        pdf_path = _build_real_pdf(
            tmp_path,
            [[("Bold Heading", "hebo", 16.0), ("regular body text", "helv", 10.0)]],
        )
        document = extract_text(parse_pdf(pdf_path))

        detect_structure(document)

        heading_block = next(b for b in document.blocks if b.text == "Bold Heading")
        body_block = next(b for b in document.blocks if b.text == "regular body text")

        assert heading_block.is_bold is True
        assert heading_block.font_size == 16.0
        assert body_block.is_bold is False
        assert body_block.font_size == 10.0


class TestXmlSanitization:
    """XML Sanitization Architecture, Layer 1: this is the one call
    site that protects src/images/image_extractor.py's figure captions
    and src/footnotes/footnote_detector.py's footnote/endnote text, both
    of which read TextBlock.text downstream without further extraction
    - structure_detector.py re-reads the PDF independently of
    src/ocr/extractor.py, so sanitizing one does not sanitize the
    other (see the XML Sanitization Architecture Review,
    docs/DECISIONS_LOG.md, for the full text-flow map this was derived
    from)."""

    def test_control_character_is_removed_from_block_text(self, tmp_path: Path) -> None:
        pdf_path = _build_real_pdf(tmp_path, [[("before\x01after", "helv", 12.0)]])
        document = parse_pdf(pdf_path)

        detect_structure(document)

        assert len(document.blocks) == 1
        assert "\x01" not in document.blocks[0].text
        assert document.blocks[0].text == "beforeafter"

    def test_sanitization_event_is_recorded(self, tmp_path: Path) -> None:
        pdf_path = _build_real_pdf(tmp_path, [[("before\x01after", "helv", 12.0)]])
        document = parse_pdf(pdf_path)

        detect_structure(document)

        assert len(document.sanitization_events) == 1
        event = document.sanitization_events[0]
        assert event.page_number == 1
        assert event.field == "text_block"
        assert event.removed_codepoints == ["U+0001"]

    def test_clean_page_records_no_sanitization_events(self, tmp_path: Path) -> None:
        pdf_path = _build_real_pdf(tmp_path, [[("Perfectly ordinary line", "helv", 12.0)]])
        document = parse_pdf(pdf_path)

        detect_structure(document)
        assert document.sanitization_events == []

    def test_font_size_and_bbox_are_still_captured_alongside_sanitization(
        self, tmp_path: Path
    ) -> None:
        # Sanitization must not interfere with the rest of this
        # module's job - layout signal capture is unaffected by the
        # text-content fix.
        pdf_path = _build_real_pdf(tmp_path, [[("bad\x01line", "hebo", 14.0)]])
        document = parse_pdf(pdf_path)

        detect_structure(document)

        block = document.blocks[0]
        assert block.text == "badline"
        assert block.is_bold is True
        assert block.font_size == 14.0


class TestBboxPreservation:
    def test_bbox_fields_are_populated_and_plausible(self, tmp_path: Path) -> None:
        pdf_path = _build_real_pdf(tmp_path, [[("Some text", "helv", 12.0)]])
        document = extract_text(parse_pdf(pdf_path))

        detect_structure(document)

        bbox = document.blocks[0].bbox
        assert bbox.x1 > bbox.x0
        assert bbox.y1 > bbox.y0
        assert bbox.x0 >= 0

    def test_lower_lines_have_greater_y_than_earlier_lines(self, tmp_path: Path) -> None:
        # PyMuPDF's coordinate origin is top-left, y increases downward -
        # a line inserted further down the page must have a strictly
        # greater y0 than one inserted above it.
        pdf_path = _build_real_pdf(
            tmp_path,
            [[("Top line", "helv", 12.0), ("Bottom line", "helv", 12.0)]],
        )
        document = extract_text(parse_pdf(pdf_path))

        detect_structure(document)

        top = next(b for b in document.blocks if b.text == "Top line")
        bottom = next(b for b in document.blocks if b.text == "Bottom line")
        assert bottom.bbox.y0 > top.bbox.y0


class TestOrderingPreservation:
    def test_order_increments_in_extraction_sequence(self, tmp_path: Path) -> None:
        pdf_path = _build_real_pdf(
            tmp_path,
            [[("Line A", "helv", 12.0), ("Line B", "helv", 12.0), ("Line C", "helv", 12.0)]],
        )
        document = extract_text(parse_pdf(pdf_path))

        detect_structure(document)

        assert [b.order for b in document.blocks] == [0, 1, 2]
        assert [b.text for b in document.blocks] == ["Line A", "Line B", "Line C"]

    def test_order_is_scoped_per_page_not_document_wide(self, tmp_path: Path) -> None:
        # Structure Detection deliberately does not produce a
        # document-wide order (that is reading-order reconstruction,
        # explicitly out of scope) - each page's blocks restart at 0.
        pdf_path = _build_real_pdf(
            tmp_path,
            [
                [("Page one line", "helv", 12.0)],
                [("Page two line", "helv", 12.0)],
            ],
        )
        document = extract_text(parse_pdf(pdf_path))

        detect_structure(document)

        page_1_blocks = [b for b in document.blocks if b.page_number == 1]
        page_2_blocks = [b for b in document.blocks if b.page_number == 2]
        assert [b.order for b in page_1_blocks] == [0]
        assert [b.order for b in page_2_blocks] == [0]

    def test_blocks_are_not_reordered_relative_to_extraction(self, tmp_path: Path) -> None:
        # This stage must not reorder anything - a regression here would
        # silently start doing reading-order reconstruction, which is
        # explicitly deferred to a later phase.
        pdf_path = _build_real_pdf(
            tmp_path,
            [[("Zebra first", "helv", 12.0), ("Apple second", "helv", 12.0)]],
        )
        document = extract_text(parse_pdf(pdf_path))

        detect_structure(document)

        assert [b.text for b in document.blocks] == ["Zebra first", "Apple second"]


class TestEmptyPages:
    def test_blank_page_contributes_zero_blocks(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "blank.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(str(pdf_path))
        doc.close()

        document = extract_text(parse_pdf(pdf_path))
        detect_structure(document)

        assert document.blocks == []

    def test_mixed_document_only_blank_page_yields_no_blocks(self, tmp_path: Path) -> None:
        pdf_path = _build_real_pdf(tmp_path, [[("Has text", "helv", 12.0)], []])

        document = extract_text(parse_pdf(pdf_path))
        detect_structure(document)

        assert all(b.page_number == 1 for b in document.blocks)
        assert len(document.blocks) > 0


class TestScannedPages:
    def test_scanned_pdf_with_no_native_text_layer_yields_zero_blocks(self) -> None:
        document = parse_pdf(SCANNED_PDF)

        detect_structure(document)

        assert document.blocks == []

    def test_scanned_page_does_not_crash_alongside_real_pages(self, tmp_path: Path) -> None:
        # A page with no text objects at all (standing in for a scanned
        # page's image-only content) mixed with a real text page must
        # not raise and must not fabricate blocks for the page with
        # nothing to read.
        pdf_path = _build_real_pdf(tmp_path, [[], [("Real text page", "helv", 12.0)]])

        document = extract_text(parse_pdf(pdf_path))
        detect_structure(document)

        assert all(b.page_number == 2 for b in document.blocks)
        assert len(document.blocks) > 0


class TestOCRPages:
    def test_ocr_pending_page_yields_zero_blocks_when_pdf_has_no_text(self) -> None:
        document = Document(
            source_pdf_path=str(SCANNED_PDF),
            metadata=Metadata(filename=SCANNED_PDF.name),
            pages=[_ocr_pending_page(1)],
        )

        detect_structure(document)

        assert document.blocks == []

    def test_ocr_recovered_text_alone_does_not_produce_blocks(self, tmp_path: Path) -> None:
        # Page.cleaned_text populated by Docling/Surya is a different
        # signal source than the PDF's native text layer this module
        # reads - confirms the documented boundary explicitly, so a
        # future change that conflates the two is caught here.
        pdf_path = tmp_path / "scanned_no_text.pdf"
        doc = fitz.open()
        doc.new_page()  # no text objects - simulates a scanned page
        doc.save(str(pdf_path))
        doc.close()

        document = Document(
            source_pdf_path=str(pdf_path),
            metadata=Metadata(filename="scanned_no_text.pdf"),
            pages=[_ocr_recovered_page(1, "Text recovered by OCR, not in the PDF text layer.")],
        )

        detect_structure(document)

        assert document.blocks == []


class TestErrorHandling:
    def test_missing_pdf_returns_document_unchanged(self, tmp_path: Path) -> None:
        document = Document(
            source_pdf_path=str(tmp_path / "missing.pdf"),
            metadata=Metadata(filename="missing.pdf"),
            pages=[Page(page_number=1)],
        )

        result = detect_structure(document)  # must not raise

        assert result is document
        assert document.blocks == []

    def test_corrupt_pdf_returns_document_unchanged(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "corrupt.pdf"
        pdf_path.write_bytes(b"not a real pdf")
        document = Document(
            source_pdf_path=str(pdf_path),
            metadata=Metadata(filename="corrupt.pdf"),
            pages=[Page(page_number=1)],
        )

        result = detect_structure(document)  # must not raise

        assert result is document
        assert document.blocks == []


class TestPreservesExistingState:
    def test_page_fields_are_untouched(self, tmp_path: Path) -> None:
        pdf_path = _build_real_pdf(tmp_path, [[("Some text", "helv", 12.0)]])
        document = extract_text(parse_pdf(pdf_path))
        original_text = document.pages[0].cleaned_text
        original_confidence = document.pages[0].ocr_confidence

        detect_structure(document)

        assert document.pages[0].cleaned_text == original_text
        assert document.pages[0].ocr_confidence == original_confidence

    def test_fresh_document_has_empty_blocks_by_default(self) -> None:
        document = Document(
            source_pdf_path="dummy.pdf", metadata=Metadata(filename="dummy.pdf")
        )
        assert document.blocks == []


@pytest.mark.parametrize("sample_pdf_path", SAMPLE_PDFS, ids=[p.name for p in SAMPLE_PDFS])
class TestBenchmarkDocuments:
    def test_structure_detection_does_not_crash(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(sample_pdf_path)
        detect_structure(document)  # must not raise

    def test_born_digital_benchmark_pdfs_produce_blocks(self, sample_pdf_path: Path) -> None:
        if not BENCHMARK_MANIFEST[sample_pdf_path.name]["born_digital"]:
            pytest.skip("scanned PDF has no native text layer - covered by TestScannedPages")

        document = parse_pdf(sample_pdf_path)
        detect_structure(document)

        assert len(document.blocks) > 0
        assert all(b.page_number >= 1 for b in document.blocks)
        assert all(b.bbox.x1 > b.bbox.x0 and b.bbox.y1 > b.bbox.y0 for b in document.blocks)

    def test_per_page_order_resets_for_every_benchmark_pdf(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(sample_pdf_path)
        detect_structure(document)

        by_page: dict = {}
        for block in document.blocks:
            by_page.setdefault(block.page_number, []).append(block.order)

        for page_number, orders in by_page.items():
            assert orders == list(range(len(orders))), f"page {page_number} order not sequential"
