"""Tests for src/images/image_extractor.py."""

import struct
import zlib
from pathlib import Path
from typing import List

import fitz
import pytest

from src.images.image_extractor import ImageExtractionError, extract_images
from src.models.contracts import AltTextStatus, Document, Image, Metadata
from src.parser.pdf_parser import parse_pdf
from src.structure.structure_detector import detect_structure

SAMPLE_PDF_DIR = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"
SAMPLE_PDFS = sorted(SAMPLE_PDF_DIR.glob("*.pdf"))

# A specific, known-to-have-multiple-images PDF, named explicitly rather
# than taken as SAMPLE_PDFS[0] - that used to resolve to the one scanned
# PDF in the (then 4-PDF) benchmark corpus by sort-order coincidence,
# and silently broke (resolved to a 0-image PDF instead) once the corpus
# grew to 10 PDFs on 2026-06-24 with new, alphabetically-earlier names
# (see DECISIONS_LOG.md "Benchmark Corpus Expansion").
_PDF_WITH_MULTIPLE_IMAGES = SAMPLE_PDF_DIR / "4. O Leary_Developing the research questions.pdf"


def _make_png(path: Path, width: int = 100, height: int = 80) -> None:
    """A minimal real PNG, small enough to embed in a test PDF."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    signature = b"\x89PNG\r\n\x1a\n"
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw_rows = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    image_data = zlib.compress(raw_rows)
    png_bytes = (
        signature
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", image_data)
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png_bytes)


def _build_image_with_caption_pdf(
    tmp_path: Path,
    caption_text: str = "Figure 1: A test diagram showing something.",
    caption_y_offset: float = 8.0,
    image_rect: tuple = (72.0, 72.0, 172.0, 152.0),
) -> Path:
    """A real one-page PDF with one embedded image and one nearby text
    line, for exercising Phase F.2's proximity-based caption detection.
    """
    png_path = tmp_path / "embedded.png"
    _make_png(png_path)

    pdf_path = tmp_path / "with_caption.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(fitz.Rect(*image_rect), filename=str(png_path))
    if caption_text:
        page.insert_text(
            (image_rect[0], image_rect[3] + caption_y_offset),
            caption_text,
            fontname="helv",
            fontsize=10,
        )
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def _extract_with_structure(pdf_path: Path, output_dir: Path) -> Document:
    """Build a Document the way the real pipeline would, including
    Structure Detection (Phase H) before Image Extraction, since Phase
    F.2's caption linking reads document.blocks."""
    document = parse_pdf(pdf_path)
    detect_structure(document)
    return extract_images(document, output_dir=output_dir)


def _raw_image_ref_count(pdf_path: Path) -> int:
    """Count every image *referenced* in any page's resource dictionary.

    This is an upper bound, not the expected extraction count: Phase C
    filtering deliberately extracts fewer images than this (e.g.
    discarding images merely listed as available on a page but never
    actually painted there - see image_extractor.py's module docstring).
    """
    total = 0
    with fitz.open(pdf_path) as doc:
        for page in doc:
            total += len(page.get_images(full=True))
    return total


def _build_document(pdf_path: Path) -> Document:
    """Build a Document the way the real pipeline would (via the parser)."""
    return parse_pdf(pdf_path)


def _filtered_image_count(pdf_path: Path, tmp_path: Path) -> int:
    """Run real extraction once (no monkeypatching) to get the actual
    post-filter survivor count, independent of any raw reference count.
    """
    document = _build_document(pdf_path)
    result = extract_images(document, output_dir=tmp_path / "_baseline")
    return len(result.images)


def _build_text_only_pdf(path: Path) -> None:
    """Create a minimal PDF with text but no embedded images."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "This page intentionally contains no images.")
    doc.save(path)
    doc.close()


@pytest.fixture(params=SAMPLE_PDFS, ids=[p.name for p in SAMPLE_PDFS])
def sample_pdf_path(request: pytest.FixtureRequest) -> Path:
    return request.param


class TestExtractImagesWithRealPdfs:
    def test_extraction_never_exceeds_raw_reference_count(
        self, sample_pdf_path: Path, tmp_path: Path
    ) -> None:
        # Filtering only ever removes candidates, never adds - the
        # post-filter count must be a subset of the raw reference count.
        document = _build_document(sample_pdf_path)
        result = extract_images(document, output_dir=tmp_path)

        raw_count = _raw_image_ref_count(sample_pdf_path)
        assert len(result.images) <= raw_count

    def test_returns_same_document_instance(self, sample_pdf_path: Path, tmp_path: Path) -> None:
        document = _build_document(sample_pdf_path)
        result = extract_images(document, output_dir=tmp_path)
        assert result is document

    def test_page_numbers_are_within_document_range(
        self, sample_pdf_path: Path, tmp_path: Path
    ) -> None:
        document = _build_document(sample_pdf_path)
        result = extract_images(document, output_dir=tmp_path)

        page_numbers = {image.page_number for image in result.images}
        valid_range = set(range(1, len(document.pages) + 1))
        assert page_numbers.issubset(valid_range)

    def test_image_ids_are_unique(self, sample_pdf_path: Path, tmp_path: Path) -> None:
        document = _build_document(sample_pdf_path)
        result = extract_images(document, output_dir=tmp_path)

        image_ids = [image.image_id for image in result.images]
        assert len(image_ids) == len(set(image_ids))
        assert all(image_id for image_id in image_ids)

    def test_successful_extractions_write_real_files(
        self, sample_pdf_path: Path, tmp_path: Path
    ) -> None:
        document = _build_document(sample_pdf_path)
        result = extract_images(document, output_dir=tmp_path)

        # Not all benchmark PDFs contain images (2 of the current 4 have
        # none) - this verifies whatever was extracted is valid, rather
        # than assuming every sample PDF has at least one image.
        for image in result.images:
            assert image.extraction_failed is False
            output_path = Path(image.file_path)
            assert output_path.is_file()
            assert output_path.stat().st_size > 0

    def test_successful_extractions_have_width_and_height(
        self, sample_pdf_path: Path, tmp_path: Path
    ) -> None:
        document = _build_document(sample_pdf_path)
        result = extract_images(document, output_dir=tmp_path)

        for image in result.images:
            assert image.width is not None and image.width > 0
            assert image.height is not None and image.height > 0

    def test_images_written_under_document_specific_subfolder(
        self, sample_pdf_path: Path, tmp_path: Path
    ) -> None:
        document = _build_document(sample_pdf_path)
        result = extract_images(document, output_dir=tmp_path)

        expected_subfolder = tmp_path / sample_pdf_path.stem
        for image in result.images:
            assert Path(image.file_path).parent == expected_subfolder


class TestExtractImagesWithoutImages:
    def test_pdf_without_images_returns_empty_list(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "text_only.pdf"
        _build_text_only_pdf(pdf_path)

        document = _build_document(pdf_path)
        result = extract_images(document, output_dir=tmp_path / "out")

        assert result.images == []


class TestPrecisionImprovementOnRealBenchmarkPdfs:
    """Phase C: direct, measured proof of the precision improvement on
    the two benchmark PDFs known (from the benchmark gap analysis) to
    massively over-extract under the old, unfiltered behavior.
    """

    def test_teaching_as_professional_discipline_drops_from_54_to_2(
        self, tmp_path: Path
    ) -> None:
        # Before Phase C: 54 raw image references (the same 2 images
        # listed as "available" on every one of 27 pages via a shared
        # resource dictionary, but only ever painted on page 1).
        pdf_path = SAMPLE_PDF_DIR / "4.Teaching as a professional discipline-Chapter 1.pdf"
        raw_count = _raw_image_ref_count(pdf_path)
        assert raw_count == 54  # documents the known benchmark baseline

        document = _build_document(pdf_path)
        result = extract_images(document, output_dir=tmp_path)

        assert len(result.images) == 2
        assert all(image.page_number == 1 for image in result.images)

    def test_oleary_sliver_fragments_are_filtered(self, tmp_path: Path) -> None:
        # Before Phase C: 11 raw image references, all small rasterized
        # fragments of one composite chart (a "Print to PDF" artifact).
        # Most are decorative slivers/dividers with an extreme aspect
        # ratio; filtering removes those, keeping the more plausible
        # standalone-sized fragments.
        pdf_path = SAMPLE_PDF_DIR / "4. O Leary_Developing the research questions.pdf"
        raw_count = _raw_image_ref_count(pdf_path)
        assert raw_count == 11  # documents the known benchmark baseline

        document = _build_document(pdf_path)
        result = extract_images(document, output_dir=tmp_path)

        assert len(result.images) < raw_count
        assert len(result.images) == 4

    def test_no_duplicate_xref_listed_across_pages_for_teaching_doc(
        self, tmp_path: Path
    ) -> None:
        pdf_path = SAMPLE_PDF_DIR / "4.Teaching as a professional discipline-Chapter 1.pdf"
        document = _build_document(pdf_path)
        result = extract_images(document, output_dir=tmp_path)

        # both surviving images are genuinely distinct (different files,
        # different sizes) - not the same image kept twice
        file_paths = {image.file_path for image in result.images}
        assert len(file_paths) == len(result.images)


class TestFilterReasonUnit:
    """White-box tests of the filtering decision in isolation, covering
    each category named in the Phase C requirements directly against
    synthetic info dicts rather than requiring a crafted real PDF for
    every boundary case.
    """

    def _page_area(self) -> float:
        return 612.0 * 792.0  # US Letter, matches the benchmark PDFs

    def test_background_image_is_filtered(self) -> None:
        from src.images.image_extractor import _filter_reason

        info = {
            "xref": 1,
            "digest": b"a",
            "width": 1000,
            "height": 1000,
            "bbox": (0.0, 0.0, 612.0, 792.0),  # covers the whole page
        }
        assert _filter_reason(info, self._page_area(), set()) == "background"

    def test_sliver_image_is_filtered(self) -> None:
        from src.images.image_extractor import _filter_reason

        info = {
            "xref": 2,
            "digest": b"b",
            "width": 1887,
            "height": 28,
            "bbox": (140.0, 192.0, 366.0, 195.0),  # 226pt x 3pt - a hairline divider
        }
        assert _filter_reason(info, self._page_area(), set()) == "sliver"

    def test_tiny_raster_image_is_filtered(self) -> None:
        from src.images.image_extractor import _filter_reason

        info = {
            "xref": 3,
            "digest": b"c",
            "width": 8,
            "height": 8,
            "bbox": (100.0, 100.0, 110.0, 110.0),
        }
        assert _filter_reason(info, self._page_area(), set()) == "tiny"

    def test_duplicate_digest_is_filtered(self) -> None:
        from src.images.image_extractor import _filter_reason

        info = {
            "xref": 4,
            "digest": b"already-seen",
            "width": 200,
            "height": 300,
            "bbox": (100.0, 100.0, 200.0, 300.0),
        }
        assert _filter_reason(info, self._page_area(), {b"already-seen"}) == "duplicate"

    def test_reasonable_content_figure_is_not_filtered(self) -> None:
        from src.images.image_extractor import _filter_reason

        info = {
            "xref": 5,
            "digest": b"e",
            "width": 264,
            "height": 415,
            "bbox": (72.0, 128.3, 270.0, 439.6),  # ~13% of the page, normal proportions
        }
        assert _filter_reason(info, self._page_area(), set()) is None


class TestExtractImagesFailureHandling:
    def test_missing_source_pdf_raises_file_not_found(self, tmp_path: Path) -> None:
        document = Document(
            source_pdf_path=str(tmp_path / "missing.pdf"),
            metadata=Metadata(filename="missing.pdf"),
        )
        with pytest.raises(FileNotFoundError):
            extract_images(document, output_dir=tmp_path / "out")

    def test_corrupt_source_pdf_raises_image_extraction_error(self, tmp_path: Path) -> None:
        bad_pdf_path = tmp_path / "corrupt.pdf"
        bad_pdf_path.write_text("not a real pdf")

        document = Document(
            source_pdf_path=str(bad_pdf_path),
            metadata=Metadata(filename="corrupt.pdf"),
        )
        with pytest.raises(ImageExtractionError):
            extract_images(document, output_dir=tmp_path / "out")

    def test_per_image_extraction_failure_is_recorded_not_raised(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sample_path = _PDF_WITH_MULTIPLE_IMAGES
        # Failures only ever apply to images that survive filtering -
        # extract_image() is never even called for filtered-out images.
        expected_count = _filtered_image_count(sample_path, tmp_path)
        assert expected_count > 0  # sanity check on the fixture PDF

        def _always_fail(self: "fitz.Document", xref: int) -> dict:
            raise RuntimeError("simulated corrupt image data")

        monkeypatch.setattr(fitz.Document, "extract_image", _always_fail)

        document = _build_document(sample_path)
        result = extract_images(document, output_dir=tmp_path)

        assert len(result.images) == expected_count
        assert all(image.extraction_failed for image in result.images)
        for image in result.images:
            assert image.width is None
            assert image.height is None
            # the placeholder path must still satisfy the model's
            # non-empty file_path requirement, but no file was written
            assert image.file_path
            assert not Path(image.file_path).exists()

    def test_mixed_success_and_failure_does_not_abort_extraction(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sample_path = _PDF_WITH_MULTIPLE_IMAGES
        expected_count = _filtered_image_count(sample_path, tmp_path)
        assert expected_count > 1  # need at least 2 surviving images for a mixed scenario

        real_extract_image = fitz.Document.extract_image
        call_count = {"n": 0}

        def _fail_first_only(self: "fitz.Document", xref: int) -> dict:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated corrupt image data")
            return real_extract_image(self, xref)

        monkeypatch.setattr(fitz.Document, "extract_image", _fail_first_only)

        document = _build_document(sample_path)
        result = extract_images(document, output_dir=tmp_path)

        assert len(result.images) == expected_count
        failed: List[Image] = [img for img in result.images if img.extraction_failed]
        succeeded: List[Image] = [img for img in result.images if not img.extraction_failed]
        assert len(failed) == 1
        assert len(succeeded) == expected_count - 1
        for image in succeeded:
            assert Path(image.file_path).is_file()


class TestImageBboxPersistence:
    """Phase F.1: Image.bbox is populated from the same page.get_image_info
    data _filter_reason already reads for background-image filtering -
    previously computed and discarded, now persisted."""

    @pytest.mark.parametrize("sample_pdf_path", SAMPLE_PDFS, ids=[p.name for p in SAMPLE_PDFS])
    def test_successful_extractions_have_bbox(self, sample_pdf_path: Path, tmp_path: Path) -> None:
        document = _build_document(sample_pdf_path)
        result = extract_images(document, output_dir=tmp_path)

        for image in result.images:
            assert image.bbox is not None
            assert image.bbox.x1 > image.bbox.x0
            assert image.bbox.y1 > image.bbox.y0

    def test_bbox_is_set_even_for_failed_extractions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # bbox comes from page.get_image_info (page-level metadata),
        # independent of whether pdf_document.extract_image() itself
        # later succeeds - a failed extraction still knows where on the
        # page the (unrecoverable) image was.
        sample_path = _PDF_WITH_MULTIPLE_IMAGES
        expected_count = _filtered_image_count(sample_path, tmp_path)
        assert expected_count > 0

        def _always_fail(self: "fitz.Document", xref: int) -> dict:
            raise RuntimeError("simulated corrupt image data")

        monkeypatch.setattr(fitz.Document, "extract_image", _always_fail)

        document = _build_document(sample_path)
        result = extract_images(document, output_dir=tmp_path)

        assert all(image.extraction_failed for image in result.images)
        assert all(image.bbox is not None for image in result.images)


class TestFigureCaptionDetection:
    """Phase F.2: deterministic regex + bbox-proximity matching against
    document.blocks (Phase H Structure Detection)."""

    def test_caption_directly_below_image_is_linked(self, tmp_path: Path) -> None:
        pdf_path = _build_image_with_caption_pdf(tmp_path)
        document = _extract_with_structure(pdf_path, tmp_path / "out")

        assert len(document.images) == 1
        figure = document.images[0].figure
        assert figure is not None
        assert figure.label == "Figure 1"
        assert figure.number == 1
        assert figure.caption == "Figure 1: A test diagram showing something."

    def test_decimal_sub_numbering_is_preserved_in_label(self, tmp_path: Path) -> None:
        pdf_path = _build_image_with_caption_pdf(
            tmp_path, caption_text="Figure 3.1: Concept map of potential research topics."
        )
        document = _extract_with_structure(pdf_path, tmp_path / "out")

        figure = document.images[0].figure
        assert figure.label == "Figure 3.1"
        assert figure.number == 3  # leading integer only - Figure.number is int

    @pytest.mark.parametrize("caption_text", ["fig. 2: A diagram.", "FIGURE 2 A diagram.", "Fig 2: A diagram."])
    def test_caption_pattern_is_case_insensitive_and_flexible(
        self, tmp_path: Path, caption_text: str
    ) -> None:
        pdf_path = _build_image_with_caption_pdf(tmp_path, caption_text=caption_text)
        document = _extract_with_structure(pdf_path, tmp_path / "out")

        assert document.images[0].figure.caption == caption_text

    def test_caption_too_far_away_is_not_linked(self, tmp_path: Path) -> None:
        pdf_path = _build_image_with_caption_pdf(tmp_path, caption_y_offset=500.0)
        document = _extract_with_structure(pdf_path, tmp_path / "out")

        figure = document.images[0].figure
        assert figure is not None  # still gets a Figure (Phase F.3 placeholder)
        assert figure.caption is None
        assert figure.label is None

    def test_non_caption_text_near_image_is_not_linked(self, tmp_path: Path) -> None:
        pdf_path = _build_image_with_caption_pdf(
            tmp_path, caption_text="This is just a regular sentence near the image."
        )
        document = _extract_with_structure(pdf_path, tmp_path / "out")

        assert document.images[0].figure.caption is None

    def test_image_with_no_nearby_text_at_all_still_gets_a_figure(self, tmp_path: Path) -> None:
        pdf_path = _build_image_with_caption_pdf(tmp_path, caption_text="")
        document = _extract_with_structure(pdf_path, tmp_path / "out")

        figure = document.images[0].figure
        assert figure is not None
        assert figure.caption is None

    def test_each_caption_is_claimed_by_at_most_one_image(self, tmp_path: Path) -> None:
        # Two genuinely distinct images (different pixel dimensions) -
        # using the same bytes twice would hit Phase C's duplicate-digest
        # filter and collapse to one image, defeating the point of this test.
        png_path_1 = tmp_path / "embedded1.png"
        png_path_2 = tmp_path / "embedded2.png"
        _make_png(png_path_1, width=100, height=80)
        _make_png(png_path_2, width=120, height=90)

        pdf_path = tmp_path / "two_images.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_image(fitz.Rect(72, 72, 172, 152), filename=str(png_path_1))
        page.insert_text((72, 160), "Figure 1: First diagram.", fontname="helv", fontsize=10)
        page.insert_image(fitz.Rect(72, 400, 172, 480), filename=str(png_path_2))
        page.insert_text((72, 488), "Figure 2: Second diagram.", fontname="helv", fontsize=10)
        doc.save(str(pdf_path))
        doc.close()

        document = _extract_with_structure(pdf_path, tmp_path / "out")

        captions = sorted(image.figure.caption for image in document.images if image.figure)
        assert captions == ["Figure 1: First diagram.", "Figure 2: Second diagram."]

    def test_extraction_failure_does_not_get_a_figure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pdf_path = _build_image_with_caption_pdf(tmp_path)

        def _always_fail(self: "fitz.Document", xref: int) -> dict:
            raise RuntimeError("simulated corrupt image data")

        monkeypatch.setattr(fitz.Document, "extract_image", _always_fail)
        document = _extract_with_structure(pdf_path, tmp_path / "out")

        assert document.images[0].extraction_failed is True
        assert document.images[0].figure is None

    def test_no_structure_detection_run_yields_no_caption_match(self, tmp_path: Path) -> None:
        # document.blocks is empty if Structure Detection never ran -
        # every image still gets a Figure (Phase F.3 placeholder), just
        # with no caption, exactly as if no caption existed at all.
        pdf_path = _build_image_with_caption_pdf(tmp_path)
        document = parse_pdf(pdf_path)  # no detect_structure() call
        result = extract_images(document, output_dir=tmp_path / "out")

        assert result.images[0].figure is not None
        assert result.images[0].figure.caption is None


class TestXmlSanitization:
    """XML Sanitization Architecture, Layer 1: proves the specific
    production-relevant claim that figure captions are protected -
    not by any code in this module (image_extractor.py never
    sanitizes), but transitively, because src/structure/structure_detector.py
    (Phase H) now sanitizes TextBlock.text at the one point every block
    is created, and _link_figures() below reads caption_block.text
    verbatim from an already-clean block. See the XML Sanitization
    Architecture Review (docs/DECISIONS_LOG.md) for why this is a
    genuinely separate fix from src/ocr/extractor.py's equivalent."""

    def test_caption_with_control_character_comes_out_clean(self, tmp_path: Path) -> None:
        pdf_path = _build_image_with_caption_pdf(
            tmp_path, caption_text="Figure 1: A test\x01 diagram showing something."
        )
        document = _extract_with_structure(pdf_path, tmp_path / "out")

        figure = document.images[0].figure
        assert figure is not None
        assert "\x01" not in figure.caption
        assert figure.caption == "Figure 1: A test diagram showing something."

    def test_placeholder_alt_text_built_from_caption_is_also_clean(self, tmp_path: Path) -> None:
        # _build_placeholder_alt_text() interpolates the caption
        # directly into Figure.alt_text - if the caption were dirty,
        # this "RAWRS-generated" string would inherit the defect too.
        pdf_path = _build_image_with_caption_pdf(
            tmp_path, caption_text="Figure 1: A test\x01 diagram showing something."
        )
        document = _extract_with_structure(pdf_path, tmp_path / "out")

        alt_text = document.images[0].figure.alt_text
        assert "\x01" not in alt_text
        assert alt_text == "Figure 1: A test diagram showing something.: description pending human review"

    def test_sanitization_event_is_recorded_for_the_caption(self, tmp_path: Path) -> None:
        pdf_path = _build_image_with_caption_pdf(
            tmp_path, caption_text="Figure 1: A test\x01 diagram showing something."
        )
        document = _extract_with_structure(pdf_path, tmp_path / "out")

        assert len(document.sanitization_events) == 1
        assert document.sanitization_events[0].field == "text_block"
        assert document.sanitization_events[0].removed_codepoints == ["U+0001"]


class TestPlaceholderAltText:
    """Phase F.3: every successfully-extracted image gets a deterministic
    placeholder alt_text and alt_text_status=PENDING_REVIEW."""

    def test_image_with_caption_uses_caption_in_placeholder(self, tmp_path: Path) -> None:
        pdf_path = _build_image_with_caption_pdf(tmp_path)
        document = _extract_with_structure(pdf_path, tmp_path / "out")

        figure = document.images[0].figure
        assert figure.alt_text == (
            "Figure 1: A test diagram showing something.: description pending human review"
        )
        assert figure.alt_text_status == AltTextStatus.PENDING_REVIEW

    def test_image_without_caption_uses_page_number_fallback(self, tmp_path: Path) -> None:
        pdf_path = _build_image_with_caption_pdf(tmp_path, caption_text="")
        document = _extract_with_structure(pdf_path, tmp_path / "out")

        figure = document.images[0].figure
        assert figure.alt_text == "Image from page 1: description pending human review"
        assert figure.alt_text_status == AltTextStatus.PENDING_REVIEW

    def test_placeholder_text_is_deterministic_across_runs(self, tmp_path: Path) -> None:
        pdf_path = _build_image_with_caption_pdf(tmp_path)
        document_1 = _extract_with_structure(pdf_path, tmp_path / "out1")
        document_2 = _extract_with_structure(pdf_path, tmp_path / "out2")

        assert document_1.images[0].figure.alt_text == document_2.images[0].figure.alt_text

    @pytest.mark.parametrize("sample_pdf_path", SAMPLE_PDFS, ids=[p.name for p in SAMPLE_PDFS])
    def test_every_retained_benchmark_image_gets_a_placeholder(
        self, sample_pdf_path: Path, tmp_path: Path
    ) -> None:
        document = parse_pdf(sample_pdf_path)
        detect_structure(document)
        result = extract_images(document, output_dir=tmp_path)

        for image in result.images:
            assert image.figure is not None
            assert image.figure.alt_text
            assert image.figure.alt_text_status == AltTextStatus.PENDING_REVIEW
