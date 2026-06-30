"""Image extraction for RAWRS.

Extracts embedded content images from each page of a Document's source
PDF, filters out non-content assets, saves the rest to disk, populates
Document.images, and (Phase F.1-F.3) links each retained image to a
Figure carrying its position, any detected caption, and a deterministic
placeholder alt text.

Per docs/ARCHITECTURE.md, the Images module's documented responsibilities
already include "Extract figures" and "Store image metadata" - this is
the first phase that actually builds those, inside this same module
rather than a new one. OCR and validation remain out of scope here.
Real (AI-generated, descriptive) alt text remains out of Phase 1 scope
per docs/PHASE1_SCOPE.md and is not attempted anywhere in this module -
see _build_placeholder_alt_text(): every string it returns is a fixed,
deterministic template, never inferred from the image's actual visual
content.

Filtering (Phase C - see BENCHMARK_RECONCILIATION_AND_PHASE1_PLAN.md
and BENCHMARK_GAP_ANALYSIS.md 4.6 for the benchmark evidence this was
derived from; one real benchmark PDF extracted 54 images where only a
couple were real content):

- Placement: page.get_image_info(xrefs=True) is used instead of
  page.get_images(full=True). The latter lists every image merely
  *referenced* in a page's resource dictionary, which for PDFs with
  shared per-document resources can include images that are available
  to every page but only actually painted on one of them. This single
  change took one benchmark PDF from 54 "extracted" images to 2 - the
  same 2 images were listed as present on all 27 pages but only ever
  drawn on page 1.
- Background: an image whose bounding box covers most of the page
  (>= 85% of page area) is almost certainly a full-page scan/background
  layer, not a content figure.
- Sliver: an image with an extreme aspect ratio (> 8:1) and a small
  short-side dimension (< 50pt, i.e. on-page physical size) is almost
  certainly a decorative divider/hairline/chart-axis fragment rather
  than a standalone figure.
- Tiny: an image with either raster dimension under 16px is almost
  certainly a spacer/bullet icon, not content.
- Duplicate: an image whose exact byte content (PyMuPDF's per-image
  digest) already appeared earlier in the same document is skipped,
  keeping only its first occurrence.

These are independent, individually-justified geometric/structural
rules, not tuned to reproduce any one benchmark document's exact image
count - no AI, no OCR, no visual/content understanding. PyMuPDF cannot
distinguish "11 rasterized fragments of one composite chart" from "4
real figures" without that understanding, so fragmentary composite
images are not reconstructed here; they are filtered as too small/
sliver-like to stand alone, which is an honest, conservative outcome
rather than a false claim of recovering the original figure.

Figure/caption linking (Phase F.2 - see the Phase H.5 Alt Text
Architecture Audit for the design this implements): for each retained
image, look for a same-page src/structure/structure_detector.py
TextBlock (Phase H) matching a "Figure N" / "Fig. N" pattern within
_CAPTION_PROXIMITY_PT of the image's bbox (above or below - whichever
is closer); each TextBlock can be claimed by at most one image. This is
deterministic text-pattern + geometry only, the same kind of rule this
module already used for filtering above - no layout-model inference, no
OCR, no AI. An image with no matching caption nearby still gets a
Figure (see _build_placeholder_alt_text() below); it just has no
label/number/caption populated.

Alt text placeholders (Phase F.3): every retained image's Figure
(matched a caption or not) gets a fixed-template alt_text and
alt_text_status=AltTextStatus.PENDING_REVIEW unconditionally - never
left unset, so "processed but not yet human-reviewed" is always
distinguishable from "never processed" (the same "attempted regardless
of outcome" rule src/ocr/docling_engine.py and src/ocr/surya_engine.py
already use for OCR attempts, applied here to accessibility metadata).

Caption-line suppression (figure-caption duplication fix): a matched
caption is a real same-page line of body text (e.g. "Figure 1. ..."),
not metadata invented separately - until this fix, Figure carried the
caption's text but nothing letting a renderer recognize that line as
already spoken for, so it rendered once in the ordinary body flow and
a second time, italicized, attached to the image (confirmed against
the Brinkman benchmark). _link_figures() now also records the matched
TextBlock's exact text onto Figure.caption_source_text, so
src/markdown/markdown_builder.py can suppress that one line - the same
exact-line-matching technique already used for footnote bodies. Figure
detection, caption detection, and the figure-to-caption association
itself are all unchanged by this fix.
"""

import re
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

import fitz  # PyMuPDF
from loguru import logger

from src.models.contracts import AltTextStatus, BoundingBox, Document, Figure, Image, TextBlock

DEFAULT_OUTPUT_DIR = Path("outputs/images")

# Matches a caption line's leading "Figure 3" / "Fig. 3.1" / "FIGURE 3" -
# case-insensitive, optional decimal sub-numbering preserved verbatim in
# the label but truncated to its leading integer for Figure.number.
_CAPTION_PATTERN = re.compile(r"^(?:figure|fig\.?)\s*(\d+(?:\.\d+)?)", re.IGNORECASE)

# Vertical gap (PDF points) within which a text line is considered
# "near" an image for caption-matching - roughly half an inch:
# comfortably wider than typical caption-to-image spacing, without
# reaching far enough to catch unrelated body text.
_CAPTION_PROXIMITY_PT = 36.0

# An image covering this much of the page is treated as a full-page
# background/scan layer, not a content figure.
_BACKGROUND_AREA_FRACTION = 0.85

# An image is treated as a decorative sliver/divider when its long-to-
# short physical (on-page) side ratio exceeds this, and its short side
# is below _SLIVER_SHORT_SIDE_MAX_PT points.
_SLIVER_ASPECT_RATIO = 8.0
_SLIVER_SHORT_SIDE_MAX_PT = 50.0

# An image with either raster dimension below this is treated as a
# negligible spacer/bullet icon, not content.
_TINY_MIN_PIXELS = 16


class ImageExtractionError(Exception):
    """Raised when the source PDF cannot be opened for image extraction."""


def extract_images(
    document: Document, output_dir: Union[str, Path] = DEFAULT_OUTPUT_DIR
) -> Document:
    """Extract embedded content images from a Document's source PDF.

    Args:
        document: A Document whose source_pdf_path points to a readable
            PDF. Re-opens the PDF independently of the parser stage.
        output_dir: Base directory extracted image files are written
            under. Each document's images are written to a subfolder
            named after the source PDF's filename stem, to avoid
            filename collisions between different documents.

    Returns:
        The same Document instance with document.images populated.
        Images identified as non-content (page backgrounds, decorative
        slivers, negligibly tiny graphics, or exact duplicates of an
        already-extracted image) are filtered out entirely - unlike a
        genuine extraction failure, they get no Image entry at all,
        since they were never real content. Images that fail to extract
        for technical reasons are still recorded, with
        extraction_failed=True, so failures stay visible, but are not
        linked to a Figure (see _link_figures()) - there is no file to
        describe. Every successfully-extracted image gets a populated
        Image.figure: a detected caption when one was found nearby
        (Phase F.2), and always a placeholder Figure.alt_text with
        Figure.alt_text_status=PENDING_REVIEW regardless (Phase F.3).
        Figure/caption linking reads document.blocks (Phase H's
        Structure Detection) - if that stage hasn't run, every image
        simply gets no caption match, exactly as if none were found.

    Raises:
        FileNotFoundError: If document.source_pdf_path does not exist.
        ImageExtractionError: If the PDF exists but cannot be opened.
    """
    pdf_path = Path(document.source_pdf_path)

    if not pdf_path.is_file():
        raise FileNotFoundError(f"Source PDF not found: {pdf_path}")

    document_output_dir = Path(output_dir) / pdf_path.stem
    logger.info("Extracting images from '{}'", pdf_path)

    try:
        pdf_document = fitz.open(pdf_path)
    except Exception as exc:  # PyMuPDF raises various error types on bad input
        raise ImageExtractionError(
            f"Failed to open PDF '{pdf_path}' for image extraction: {exc}"
        ) from exc

    extracted_images: List[Image] = []
    seen_digests: Set[bytes] = set()
    filtered_count = 0

    try:
        document_output_dir.mkdir(parents=True, exist_ok=True)

        for page_index in range(pdf_document.page_count):
            page_number = page_index + 1
            page = pdf_document[page_index]
            page_area = page.rect.width * page.rect.height

            for ref_index, info in enumerate(page.get_image_info(xrefs=True), start=1):
                reason = _filter_reason(info, page_area, seen_digests)
                if reason is not None:
                    filtered_count += 1
                    logger.debug(
                        "Filtered non-content image (xref={}) on page {}: {}",
                        info.get("xref"),
                        page_number,
                        reason,
                    )
                    continue

                digest = info.get("digest")
                if digest is not None:
                    seen_digests.add(digest)

                image = _extract_single_image(
                    pdf_document=pdf_document,
                    xref=info["xref"],
                    page_number=page_number,
                    ref_index=ref_index,
                    output_dir=document_output_dir,
                    bbox=info.get("bbox"),
                )
                extracted_images.append(image)
    finally:
        pdf_document.close()

    blocks_by_page = _group_blocks_by_page(document.blocks)
    _link_figures(extracted_images, blocks_by_page)

    failed_count = sum(1 for image in extracted_images if image.extraction_failed)
    linked_count = sum(1 for image in extracted_images if image.figure and image.figure.caption)
    logger.info(
        "Extracted {} image(s) from '{}' ({} failed, {} filtered as non-content, "
        "{} caption(s) linked)",
        len(extracted_images),
        pdf_path.name,
        failed_count,
        filtered_count,
        linked_count,
    )

    document.images = extracted_images
    return document


def _filter_reason(info: Dict, page_area: float, seen_digests: Set[bytes]) -> Optional[str]:
    """Return a short reason if this image is non-content and should be
    filtered out, or None if it should be extracted as real content.
    """
    digest = info.get("digest")
    if digest is not None and digest in seen_digests:
        return "duplicate"

    width_px = info.get("width") or 0
    height_px = info.get("height") or 0
    if width_px < _TINY_MIN_PIXELS or height_px < _TINY_MIN_PIXELS:
        return "tiny"

    bbox = info.get("bbox")
    if bbox is not None and page_area > 0:
        bbox_width = bbox[2] - bbox[0]
        bbox_height = bbox[3] - bbox[1]
        bbox_area = bbox_width * bbox_height

        if bbox_area / page_area >= _BACKGROUND_AREA_FRACTION:
            return "background"

        long_side = max(bbox_width, bbox_height)
        short_side = min(bbox_width, bbox_height)
        if (
            short_side > 0
            and (long_side / short_side) > _SLIVER_ASPECT_RATIO
            and short_side < _SLIVER_SHORT_SIDE_MAX_PT
        ):
            return "sliver"

    return None


def _extract_single_image(
    pdf_document: "fitz.Document",
    xref: int,
    page_number: int,
    ref_index: int,
    output_dir: Path,
    bbox: Optional[tuple] = None,
) -> Image:
    """Extract and save one embedded image, returning its Image model.

    Failures are caught and logged rather than propagated, so that one
    corrupt image does not abort extraction for the rest of the
    document (see "Handle extraction failures gracefully").

    Args:
        bbox: This image's (x0, y0, x1, y1) position on its page, from
            the same page.get_image_info(xrefs=True) entry _filter_reason
            already reads to decide background/sliver filtering (Phase
            F.1 - previously read once for that decision and discarded;
            now also persisted onto Image.bbox).
    """
    image_id = uuid.uuid4().hex
    intended_path = output_dir / f"page{page_number}_img{ref_index}_{image_id}.bin"
    image_bbox = BoundingBox(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3]) if bbox else None

    try:
        image_data = pdf_document.extract_image(xref)
        extension = image_data["ext"]
        output_path = intended_path.with_suffix(f".{extension}")
        output_path.write_bytes(image_data["image"])

        return Image(
            image_id=image_id,
            page_number=page_number,
            file_path=str(output_path),
            width=image_data.get("width"),
            height=image_data.get("height"),
            bbox=image_bbox,
            extraction_failed=False,
        )
    except Exception as exc:
        logger.error(
            "Failed to extract image (xref={}) on page {}: {}",
            xref,
            page_number,
            exc,
        )
        # file_path records the intended location for traceability, even
        # though no file was written; extraction_failed=True is the
        # authoritative signal that this entry did not succeed.
        return Image(
            image_id=image_id,
            page_number=page_number,
            file_path=str(intended_path),
            width=None,
            height=None,
            bbox=image_bbox,
            extraction_failed=True,
        )


def _group_blocks_by_page(blocks: List[TextBlock]) -> Dict[int, List[TextBlock]]:
    grouped: Dict[int, List[TextBlock]] = {}
    for block in blocks:
        grouped.setdefault(block.page_number, []).append(block)
    return grouped


def _link_figures(images: List[Image], blocks_by_page: Dict[int, List[TextBlock]]) -> None:
    """Populate Image.figure for every successfully-extracted image
    in place (Phase F.2 caption matching + Phase F.3 alt-text
    placeholders - see module docstring).
    """
    used_blocks: Set[Tuple[int, int]] = set()  # (page_number, order) already claimed

    for image in images:
        if image.extraction_failed:
            continue

        caption_block = _find_caption_block(image, blocks_by_page.get(image.page_number, []), used_blocks)

        if caption_block is not None:
            used_blocks.add((caption_block.page_number, caption_block.order))
            match = _CAPTION_PATTERN.match(caption_block.text)
            number_token = match.group(1)
            image.figure = Figure(
                label=f"Figure {number_token}",
                number=int(number_token.split(".")[0]),
                caption=caption_block.text,
                alt_text=_build_placeholder_alt_text(image.page_number, caption_block.text),
                alt_text_status=AltTextStatus.PENDING_REVIEW,
                caption_source_text=caption_block.text,
            )
        else:
            image.figure = Figure(
                alt_text=_build_placeholder_alt_text(image.page_number, None),
                alt_text_status=AltTextStatus.PENDING_REVIEW,
            )


def _find_caption_block(
    image: Image, page_blocks: List[TextBlock], used_blocks: Set[Tuple[int, int]]
) -> Optional[TextBlock]:
    """Nearest unclaimed same-page TextBlock matching the caption
    pattern within _CAPTION_PROXIMITY_PT of image.bbox, or None."""
    if image.bbox is None:
        return None

    candidates = []
    for block in page_blocks:
        if (block.page_number, block.order) in used_blocks:
            continue
        if not _CAPTION_PATTERN.match(block.text):
            continue
        distance = _vertical_distance(image.bbox, block.bbox)
        if distance <= _CAPTION_PROXIMITY_PT:
            candidates.append((distance, block))

    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0])
    return candidates[0][1]


def _vertical_distance(image_bbox: BoundingBox, block_bbox: BoundingBox) -> float:
    """Vertical gap between an image and a candidate caption line -
    0.0 if they vertically overlap (e.g. same row, different column,
    still "near"), else the gap above or below."""
    if block_bbox.y0 >= image_bbox.y1:
        return block_bbox.y0 - image_bbox.y1  # block is below the image
    if block_bbox.y1 <= image_bbox.y0:
        return image_bbox.y0 - block_bbox.y1  # block is above the image
    return 0.0


def _build_placeholder_alt_text(page_number: int, caption: Optional[str]) -> str:
    """A fixed, deterministic alt-text template - never inferred from
    the image's actual visual content (see module docstring's "no AI"
    note). Mirrors the placeholder shape already specified in
    BENCHMARK_RECONCILIATION_AND_PHASE1_PLAN.md §5.
    """
    if caption:
        return f"{caption}: description pending human review"
    return f"Image from page {page_number}: description pending human review"
