"""Validation for RAWRS.

Inspects a Document and reports findings as ValidationIssue objects.
Per docs/VALIDATION_RULES.md, validation is the project's core safety
mechanism ("AI Proposes, Validation Decides") and must never modify
content, hide uncertainty, or auto-correct without traceability - every
function in this module is read-only: it inspects document state and
returns new ValidationIssue objects, never mutates the Document.

Rule ID scheme: HEADING_xxx, PAGE_xxx, IMAGE_xxx, DOC_xxx, NOTE_xxx,
OCR_xxx. HEADING_001 intentionally matches the literal example given
in docs/VALIDATION_RULES.md ("Heading hierarchy jump detected").
IMAGE_004 (Phase F.3) covers Figure-level alt-text review status under
the existing IMAGE_xxx prefix rather than introducing a new one, since
a Figure is always composed within an Image (see src/models/image.py).
NOTE_xxx (Phase K) is a genuinely new category - footnotes/endnotes
aren't a property of any existing Heading/Page/Image/Document entity,
so reusing one of those prefixes the way IMAGE_004 does would be a
forced fit rather than a natural one. PAGE_003 (Phase I.1) reuses the
existing PAGE_xxx prefix rather than introducing another new one -
reading order is a property of a page's own content sequence, the same
category docs/PAGE_RULES.md frames it under ("Reading order violations
should be reported by validation"), unlike NOTE_xxx's situation.
OCR_xxx (OCR_001/OCR_002) is a new category for the same reason
NOTE_xxx was: OCR confidence and recovered-text character quality are
properties of the extraction process itself, not of any existing
Heading/Page-sequence/Image/Document entity, and docs/VALIDATION_RULES.md
already names "OCR Validation" as its own category distinct from "Page
Validation" (which PAGE_003 belongs to) - so a new prefix is the
natural fit, not a forced one.

OCR_001/OCR_002 close the long-standing documented gap recorded in
docs/VALIDATION_RULES.md and docs/KNOWN_LIMITATIONS.md: "OCR
Validation" listed low-confidence regions and excessive OCR artifacts
as checks with no implementing rule ID for either. Both reuse existing
Phase D.0-D.2 data/logic rather than introducing anything new:
OCR_001 reads Page.ocr_confidence (already set by
src/ocr/extractor.py/docling_engine.py/surya_engine.py); OCR_002 reuses
src/ocr/router.py's existing _unusable_char_ratio() character-quality
heuristic, evaluated post-OCR instead of pre-routing. Broken-word
detection and region-level (sub-page) confidence remain explicitly out
of scope - see docs/KNOWN_LIMITATIONS.md.

DOC_004 (XML Sanitization Architecture, Layer 2) reuses the existing
DOC_xxx prefix rather than a new one - it is a document-content-
integrity concern (like DOC_001-003), not an OCR-process-quality signal
the way OCR_xxx is, and applies regardless of whether the affected text
ever went through an OCR engine at all (direct extraction and
structure-detected captions/footnotes are common sources too - see the
XML Sanitization Architecture Review, docs/DECISIONS_LOG.md). Critically,
DOC_004 does not detect anything itself: src/utils/text_sanitization.py
(Layer 1) has already removed the offending character from
Document.pages/Document.blocks by the time this rule runs, recording
what it did onto document.sanitization_events - DOC_004 only surfaces
that existing record as a ValidationIssue. It is therefore a disclosure
of an already-handled defect, never a prediction of an upcoming one.

Severity is assigned per docs/VALIDATION_RULES.md's Severity Levels
section: Error for issues that compromise processing quality (missing
pages, corrupted/failed extraction), Warning for issues needing human
review (hierarchy problems, content/metadata inconsistencies), and Info
for non-critical observations - IMAGE_004 and NOTE_001/NOTE_002 are all
Info, matching docs/VALIDATION_RULES.md's own Info-tier example list
verbatim ("Footnote detected", "Endnote detected"): these are
deterministic, always-expected observations once detection succeeds,
not defects. PAGE_003 is Warning - a reading-order anomaly is a
*potential* issue needing human review, matching the Severity Levels
section's Warning framing exactly, not a guaranteed defect (a real
single-column page can in principle still trip a conservative geometric
heuristic) and not merely an Info-level observation either (unlike a
footnote, this signals something may actually be wrong). OCR_001 and
OCR_002 are both Warning for the same reason as PAGE_003: a LOW
confidence page or a garbled-looking OCR output may still be perfectly
correct (e.g. unusual but legitimate symbols), so neither is treated as
a guaranteed defect - but both signal something a human reviewer should
specifically check, not merely a deterministic, expected observation
(ruling out Info) and not a confirmed processing failure (ruling out
Error).

DOC_004 is Warning, not Error, despite an XML-illegal character being
*unconditionally* fatal to DOCX generation if it ever reached that
stage unhandled - an architecture review explicitly revisited this
question (see docs/DECISIONS_LOG.md) and reversed an earlier Error
recommendation once Layer 1 actually existed: by the time DOC_004 can
possibly fire, the character is already gone and the document already
generated successfully - "Processing quality is compromised" (Error's
own definition) is false at the moment this rule runs, every time, by
construction. What remains true and worth a human's attention is
exactly Warning's definition: a potential issue (confirm the removal
didn't change meaning) recommended for review - not a guaranteed
defect, and not a processing failure.

IMAGE_005 (016E) is Warning: fires after DOCX generation when an image
file exists and extraction succeeded, but _add_image() still returned
False (e.g. run.add_picture() raised despite a readable file). Unlike
IMAGE_001/002 this is not a confirmed processing failure - the DOCX was
generated; an image is simply absent. Not fired for images whose
extraction_failed=True (IMAGE_002 already covers those) or whose file
is missing (IMAGE_001 already covers those). Only fires when
Image.embedded_in_docx is explicitly False, i.e. after a generation
run; None (pre-generation) is never flagged.
"""

from pathlib import Path
from typing import Dict, List, Set, Tuple

from loguru import logger

from src.models.contracts import (
    AltTextStatus,
    Document,
    ExtractionMethod,
    HeadingLevel,
    NoteType,
    OCRConfidence,
    Severity,
    TextBlock,
    ValidationIssue,
)
from src.ocr.router import _MAX_UNUSABLE_CHAR_RATIO, _unusable_char_ratio


def validate_document(document: Document) -> List[ValidationIssue]:
    """Run all Phase 1 validation checks against a Document.

    Args:
        document: The Document to validate. Not modified.

    Returns:
        A list of ValidationIssue objects describing every finding
        across heading, page, image, and document-level checks. Empty
        if no issues were found.
    """
    logger.info("Validating document '{}'", document.source_pdf_path)

    issues: List[ValidationIssue] = []
    issues.extend(_check_zero_pages(document))
    issues.extend(_check_empty_document(document))
    issues.extend(_check_metadata_consistency(document))
    issues.extend(_check_missing_h1(document))
    issues.extend(_check_empty_headings(document))
    issues.extend(_check_duplicate_headings(document))
    issues.extend(_check_skipped_heading_levels(document))
    issues.extend(_check_multiple_h1(document))
    issues.extend(_check_document_accessibility_properties(document))
    issues.extend(_check_missing_page_markers(document))
    issues.extend(_check_page_ordering(document))
    issues.extend(_check_reading_order_anomalies(document))
    issues.extend(_check_low_ocr_confidence(document))
    issues.extend(_check_ocr_artifacts(document))
    issues.extend(_check_xml_invalid_characters(document))
    issues.extend(_check_missing_image_files(document))
    issues.extend(_check_failed_image_extraction(document))
    issues.extend(_check_duplicate_image_ids(document))
    issues.extend(_check_pending_alt_text_review(document))
    issues.extend(_check_docx_embedding_failures(document))
    issues.extend(_check_footnotes_detected(document))
    issues.extend(_check_endnotes_detected(document))
    issues.extend(_check_table_accessibility(document))

    error_count = sum(1 for issue in issues if issue.severity == Severity.ERROR)
    warning_count = sum(1 for issue in issues if issue.severity == Severity.WARNING)
    info_count = sum(1 for issue in issues if issue.severity == Severity.INFO)
    logger.info(
        "Validation complete for '{}': {} error(s), {} warning(s), {} info ({} total)",
        document.source_pdf_path,
        error_count,
        warning_count,
        info_count,
        len(issues),
    )
    return issues


# --- Document-level checks -------------------------------------------------


def _check_zero_pages(document: Document) -> List[ValidationIssue]:
    if len(document.pages) == 0:
        return [
            ValidationIssue(
                severity=Severity.ERROR,
                rule_id="DOC_003",
                message="Document has zero pages.",
                page_number=None,
                suggested_action="Re-run the parser; a document must have at least one page.",
            )
        ]
    return []


def _check_empty_document(document: Document) -> List[ValidationIssue]:
    if not document.pages:
        return []  # already reported by _check_zero_pages

    has_text = any((page.cleaned_text or page.raw_text).strip() for page in document.pages)
    has_content_headings = any(not heading.is_page_marker for heading in document.headings)
    has_images = len(document.images) > 0

    if not has_text and not has_content_headings and not has_images:
        return [
            ValidationIssue(
                severity=Severity.WARNING,
                rule_id="DOC_001",
                message="Document has pages but no extracted text, content headings, or images.",
                page_number=None,
                suggested_action=(
                    "Confirm OCR/text extraction has run; the document currently has no "
                    "processable content."
                ),
            )
        ]
    return []


def _check_metadata_consistency(document: Document) -> List[ValidationIssue]:
    """Flag Metadata fields that have drifted from the Document's actual state.

    Metadata.filename/page_count/image_count cannot be None or blank at
    the model level (see src/models/metadata.py), so a literal
    null-check for "missing metadata" can never fire. The meaningful,
    reachable interpretation of "missing/incomplete metadata" is
    metadata going stale relative to the document it describes - in
    particular, this is the exact image_count staleness risk flagged
    during the Image Extraction review, since nothing currently keeps
    Metadata.image_count in sync after extraction.
    """
    issues: List[ValidationIssue] = []
    metadata = document.metadata

    if metadata.page_count != len(document.pages):
        issues.append(
            ValidationIssue(
                severity=Severity.WARNING,
                rule_id="DOC_002",
                message=(
                    f"Metadata page_count ({metadata.page_count}) does not match the actual "
                    f"page count ({len(document.pages)})."
                ),
                page_number=None,
                suggested_action="Refresh Document.metadata.page_count from the current pages list.",
            )
        )

    if metadata.image_count != len(document.images):
        issues.append(
            ValidationIssue(
                severity=Severity.WARNING,
                rule_id="DOC_002",
                message=(
                    f"Metadata image_count ({metadata.image_count}) does not match the actual "
                    f"image count ({len(document.images)})."
                ),
                page_number=None,
                suggested_action="Refresh Document.metadata.image_count from the current images list.",
            )
        )

    if metadata.processing_date is None:
        issues.append(
            ValidationIssue(
                severity=Severity.INFO,
                rule_id="DOC_002",
                message="Metadata.processing_date was not recorded.",
                page_number=None,
                suggested_action="Ensure the pipeline stage that finalizes Metadata sets processing_date.",
            )
        )

    return issues


# --- Heading checks ----------------------------------------------------------


def _check_missing_h1(document: Document) -> List[ValidationIssue]:
    if not document.pages:
        return []

    has_h1 = any(heading.level == HeadingLevel.H1 for heading in document.headings)
    if not has_h1:
        return [
            ValidationIssue(
                severity=Severity.WARNING,
                rule_id="HEADING_002",
                message="No H1 heading was detected in the document.",
                page_number=None,
                suggested_action=(
                    "Confirm the document has a clear title and that heading detection ran on "
                    "populated page text."
                ),
            )
        ]
    return []


def _check_empty_headings(document: Document) -> List[ValidationIssue]:
    """Defense-in-depth: Heading itself rejects blank text at construction
    (see src/models/heading.py), so this should be unreachable in
    practice. Kept so a future relaxation of that constraint, or a
    Heading constructed via model_construct(), is still caught here.
    """
    issues: List[ValidationIssue] = []
    for heading in document.headings:
        if not heading.text.strip():
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule_id="HEADING_003",
                    message="An empty heading was detected.",
                    page_number=heading.page_number,
                    suggested_action="Remove or populate the empty heading.",
                )
            )
    return issues


def _check_duplicate_headings(document: Document) -> List[ValidationIssue]:
    """Flag repeated (level, text) pairs anywhere in document.headings.

    Scoped across all headings, including H6 page markers, so two
    pages that both produced an identical marker (e.g. "3" twice)
    are caught by this same generic rule rather than needing a
    separate duplicate-page-marker check.
    """
    issues: List[ValidationIssue] = []
    seen: Dict[Tuple[HeadingLevel, str], int] = {}

    for heading in document.headings:
        key = (heading.level, heading.text)
        if key in seen:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule_id="HEADING_004",
                    message=(
                        f"Duplicate heading detected: H{heading.level.value} '{heading.text}' "
                        f"(first seen on page {seen[key]})."
                    ),
                    page_number=heading.page_number,
                    suggested_action=(
                        "Confirm this repeated heading is intentional, not a detection or "
                        "page-marker error."
                    ),
                )
            )
        else:
            seen[key] = heading.page_number

    return issues


def _check_skipped_heading_levels(document: Document) -> List[ValidationIssue]:
    """Flag content-heading level jumps of more than one step.

    Page markers (H6) are excluded from this sequence: they interrupt
    the content outline at arbitrary points (every page boundary), and
    docs/HEADING_RULES.md's allowed/disallowed transition table is
    about the content hierarchy, not the page-marker mechanism.
    Decreasing transitions (e.g. H4 -> H2) are not flagged, since
    nothing in docs/HEADING_RULES.md restricts moving back up to a
    higher-level section.
    """
    issues: List[ValidationIssue] = []
    content_headings = sorted(
        (heading for heading in document.headings if not heading.is_page_marker),
        key=lambda heading: heading.document_order,
    )

    for previous, current in zip(content_headings, content_headings[1:]):
        if current.level.value - previous.level.value > 1:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule_id="HEADING_001",
                    message=(
                        f"Heading hierarchy jump detected: H{previous.level.value} "
                        f"('{previous.text}') is directly followed by H{current.level.value} "
                        f"('{current.text}')."
                    ),
                    page_number=current.page_number,
                    suggested_action=(
                        "Insert the missing intermediate heading level(s), or confirm this jump "
                        "is intentional."
                    ),
                )
            )

    return issues


# --- HEADING_005 / META_001–002 (FEATURE_016) ---------------------------------


def _check_multiple_h1(document: Document) -> List[ValidationIssue]:
    """HEADING_005 (WARNING): more than one H1 detected.

    A well-structured document has exactly one H1 (the document title).
    Multiple H1s typically indicate a detection error or a structural
    problem — screen readers announce H1 as the primary document landmark,
    so duplicates confuse navigation.
    """
    h1_headings = [
        h for h in document.headings
        if not h.is_page_marker and h.level.value == 1
    ]
    if len(h1_headings) <= 1:
        return []
    texts = ", ".join(f'"{h.text}"' for h in h1_headings[:3])
    return [
        ValidationIssue(
            severity=Severity.WARNING,
            rule_id="HEADING_005",
            message=(
                f"{len(h1_headings)} H1 headings detected ({texts}{'…' if len(h1_headings) > 3 else ''}). "
                "A well-structured document should have exactly one H1."
            ),
            page_number=h1_headings[0].page_number,
            suggested_action=(
                "Review H1 headings in the Headings workspace. Downgrade incorrect H1s "
                "to the appropriate level, or mark false positives as rejected."
            ),
        )
    ]


def _check_document_accessibility_properties(document: Document) -> List[ValidationIssue]:
    """META_001/META_002 (FEATURE_016F): missing DOCX accessibility properties.

    META_001 (INFO): no document language set — WCAG 3.1.1 requires the
    human language of each page to be programmatically determinable.
    META_002 (INFO): no document title set — WCAG 2.4.2 requires web
    pages / documents to have descriptive titles; screen readers announce
    the title when a document is opened.
    """
    issues: List[ValidationIssue] = []
    m = document.metadata
    if not m.language:
        issues.append(
            ValidationIssue(
                severity=Severity.INFO,
                rule_id="META_001",
                message=(
                    "No document language set. WCAG 3.1.1 requires the language to be "
                    "programmatically determinable so screen readers use the correct voice."
                ),
                page_number=None,
                suggested_action=(
                    "Set the document language (e.g. 'en-US') in the Metadata panel. "
                    "It will be written to dc:language in the exported DOCX."
                ),
            )
        )
    if not m.title:
        issues.append(
            ValidationIssue(
                severity=Severity.INFO,
                rule_id="META_002",
                message=(
                    "No document title set. WCAG 2.4.2 requires documents to have a "
                    "descriptive title so screen readers can identify the document when opened."
                ),
                page_number=None,
                suggested_action=(
                    "Set the document title in the Metadata panel. "
                    "It will be written to dc:title in the exported DOCX."
                ),
            )
        )
    return issues


# --- Page checks ---------------------------------------------------------


def _check_missing_page_markers(document: Document) -> List[ValidationIssue]:
    marker_pages = {heading.page_number for heading in document.headings if heading.is_page_marker}
    issues: List[ValidationIssue] = []

    for page in document.pages:
        if page.page_number not in marker_pages:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_id="PAGE_001",
                    message=f"Page {page.page_number} has no H6 page marker.",
                    page_number=page.page_number,
                    suggested_action="Re-run heading detection; every page must have exactly one H6 page marker.",
                )
            )

    return issues


def _check_page_ordering(document: Document) -> List[ValidationIssue]:
    """Flag duplicate page numbers, gaps in the page sequence, and pages
    stored out of page-number order.

    Duplicates and gaps are Errors (the page sequence is structurally
    broken). A page list that is complete and unique but simply stored
    out of order is a Warning, since it is recoverable (markdown_builder
    already defensively re-sorts pages before rendering).
    """
    if not document.pages:
        return []

    issues: List[ValidationIssue] = []
    page_numbers = [page.page_number for page in document.pages]

    seen: Set[int] = set()
    duplicates: Set[int] = set()
    for number in page_numbers:
        if number in seen:
            duplicates.add(number)
        seen.add(number)

    for number in sorted(duplicates):
        issues.append(
            ValidationIssue(
                severity=Severity.ERROR,
                rule_id="PAGE_002",
                message=f"Page number {number} appears more than once in document.pages.",
                page_number=number,
                suggested_action="Remove the duplicate page entry; page numbers must be unique.",
            )
        )

    expected = set(range(1, len(document.pages) + 1))
    missing = expected - seen
    for number in sorted(missing):
        issues.append(
            ValidationIssue(
                severity=Severity.ERROR,
                rule_id="PAGE_002",
                message=f"Page {number} is missing from the page sequence.",
                page_number=number,
                suggested_action="Re-run the parser; the page sequence must have no gaps.",
            )
        )

    if not duplicates and not missing and page_numbers != sorted(page_numbers):
        issues.append(
            ValidationIssue(
                severity=Severity.WARNING,
                rule_id="PAGE_002",
                message="Pages are present and complete but stored out of page-number order.",
                page_number=None,
                suggested_action="Re-sort document.pages by page_number to preserve page sequence.",
            )
        )

    return issues


# Backward vertical jump must exceed this multiple of the page's own
# median line height to count as an anomaly - self-calibrating per page
# (rather than a fixed point value) so it scales with whatever font
# size that page actually uses, and generous enough to absorb ordinary
# jitter between same-line spans without flagging anything.
_READING_ORDER_JUMP_RATIO = 1.5

# Two blocks must overlap by at least this fraction of the smaller
# block's area to count as an anomaly - ordinary flowing text lines
# never overlap at all, so this stays conservative even at a
# relatively low fraction.
_READING_ORDER_OVERLAP_FRACTION = 0.5


def _check_reading_order_anomalies(document: Document) -> List[ValidationIssue]:
    """Warning-level: flags pages whose Phase H structure blocks
    (src/structure/structure_detector.py) show a strong, conservative
    geometric signal that the page's text was not extracted in a
    coherent top-to-bottom reading order - e.g. PyMuPDF interleaving
    two columns, or two blocks occupying overlapping space.

    Closes the documented gap in docs/VALIDATION_RULES.md ("OCR
    Validation" lists "Reading order anomalies" as a check) and
    docs/PAGE_RULES.md ("Reading order violations should be reported by
    validation"). Phase I.1 scope: detection only, operating entirely on
    Document.blocks (already populated by Phase H) - this never
    reorders, restitches, or otherwise modifies content; reconstruction
    is an explicitly later, separately-scoped phase (see the Phase I
    architecture audit).

    Deliberately conservative (prefer under-reporting over false
    positives, per the Phase I.1 brief): each signal requires a
    geometric anomaly that is large relative to the page's own typical
    line size, not merely present. A page with no blocks (e.g. a
    scanned page with no native text layer - Phase H's documented,
    expected zero-block case) or fewer than two blocks cannot exhibit
    either signal and is silently skipped, not flagged.
    """
    blocks_by_page: Dict[int, List[TextBlock]] = {}
    for block in document.blocks:
        blocks_by_page.setdefault(block.page_number, []).append(block)

    issues: List[ValidationIssue] = []
    for page_number in sorted(blocks_by_page):
        ordered_blocks = sorted(blocks_by_page[page_number], key=lambda block: block.order)
        if len(ordered_blocks) < 2:
            continue

        jump_count = _count_backward_jumps(ordered_blocks)
        overlap_count = _count_overlapping_pairs(ordered_blocks)
        if jump_count == 0 and overlap_count == 0:
            continue

        details = []
        if jump_count:
            details.append(f"{jump_count} backward vertical jump(s)")
        if overlap_count:
            details.append(f"{overlap_count} overlapping block pair(s)")

        issues.append(
            ValidationIssue(
                severity=Severity.WARNING,
                rule_id="PAGE_003",
                message=f"Reading order anomaly on page {page_number}: {', '.join(details)}.",
                page_number=page_number,
                suggested_action=(
                    "Review this page's content order; the extracted text may not follow a "
                    "single coherent top-to-bottom sequence (e.g. a multi-column layout)."
                ),
            )
        )

    return issues


def _count_backward_jumps(ordered_blocks: List[TextBlock]) -> int:
    """Count consecutive-in-order block pairs where the later block sits
    meaningfully *above* the earlier one (a "jump back up the page") -
    the signature of column-interleaved or otherwise scrambled emission
    order. Threshold is relative to the page's own median line height,
    so it self-calibrates per document instead of using one fixed value.
    """
    heights = [
        block.bbox.y1 - block.bbox.y0 for block in ordered_blocks if block.bbox.y1 > block.bbox.y0
    ]
    if not heights:
        return 0
    median_height = _median(heights)
    if median_height <= 0:
        return 0
    threshold = median_height * _READING_ORDER_JUMP_RATIO

    jump_count = 0
    for previous, current in zip(ordered_blocks, ordered_blocks[1:]):
        backward_distance = previous.bbox.y0 - current.bbox.y0
        if backward_distance > threshold:
            jump_count += 1
    return jump_count


def _count_overlapping_pairs(blocks: List[TextBlock]) -> int:
    """Count block pairs whose bounding boxes overlap by at least
    _READING_ORDER_OVERLAP_FRACTION of the smaller block's area -
    ordinary single-column flowing text lines never overlap at all."""
    overlap_count = 0
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            if _bbox_overlap_fraction(blocks[i], blocks[j]) >= _READING_ORDER_OVERLAP_FRACTION:
                overlap_count += 1
    return overlap_count


def _bbox_overlap_fraction(first: TextBlock, second: TextBlock) -> float:
    x_overlap = max(0.0, min(first.bbox.x1, second.bbox.x1) - max(first.bbox.x0, second.bbox.x0))
    y_overlap = max(0.0, min(first.bbox.y1, second.bbox.y1) - max(first.bbox.y0, second.bbox.y0))
    overlap_area = x_overlap * y_overlap
    if overlap_area <= 0:
        return 0.0

    first_area = (first.bbox.x1 - first.bbox.x0) * (first.bbox.y1 - first.bbox.y0)
    second_area = (second.bbox.x1 - second.bbox.x0) * (second.bbox.y1 - second.bbox.y0)
    smaller_area = min(first_area, second_area)
    if smaller_area <= 0:
        return 0.0

    return overlap_area / smaller_area


def _median(values: List[float]) -> float:
    ordered = sorted(values)
    count = len(ordered)
    midpoint = count // 2
    if count % 2 == 0:
        return (ordered[midpoint - 1] + ordered[midpoint]) / 2
    return ordered[midpoint]


# --- OCR checks --------------------------------------------------------


def _check_low_ocr_confidence(document: Document) -> List[ValidationIssue]:
    """Warning-level: flags pages whose Page.ocr_confidence is LOW.

    Closes the documented gap in docs/VALIDATION_RULES.md ("OCR
    Validation" lists "Low confidence regions" as a check, with no
    implementing rule ID before OCR_001). Per docs/OCR_RULES.md's
    three-tier confidence model (HIGH = direct extraction, MEDIUM =
    Docling, LOW = Surya fallback), only LOW is documented as needing
    the extra "flagged for validation review" scrutiny - it is the
    tier only ever reached after the primary OCR engine (Docling) has
    already failed on that same page. MEDIUM is deliberately NOT
    flagged here: it is Docling's normal, successful outcome for any
    OCR_REQUIRED page, and flagging every one of those would bury the
    genuinely uncertain LOW signal under noise from the expected common
    case - the same "hide uncertainty" failure mode
    docs/VALIDATION_RULES.md's Design Principles warn against, just
    inverted (noise hides signal as effectively as silence does).
    """
    issues: List[ValidationIssue] = []
    for page in document.pages:
        if page.ocr_confidence != OCRConfidence.LOW:
            continue
        issues.append(
            ValidationIssue(
                severity=Severity.WARNING,
                rule_id="OCR_001",
                message=(
                    f"Page {page.page_number} has LOW OCR confidence "
                    f"(recovered only by the Surya fallback engine after Docling failed)."
                ),
                page_number=page.page_number,
                suggested_action=(
                    "Review this page's extracted text against the source PDF image; "
                    "it was only recovered after the primary OCR engine failed on it."
                ),
            )
        )
    return issues


def _check_ocr_artifacts(document: Document) -> List[ValidationIssue]:
    """Warning-level: flags pages where an OCR engine ran (Docling or
    Surya) and the recovered text is still dominated by control
    characters or the Unicode replacement character - i.e. the OCR
    attempt itself produced garbled output, not merely empty output.

    Closes the documented gap in docs/VALIDATION_RULES.md ("OCR
    Validation" lists "Excessive OCR artifacts" as a check, with no
    implementing rule ID before OCR_002). Deliberately reuses
    src/ocr/router.py's existing _unusable_char_ratio() and
    _MAX_UNUSABLE_CHAR_RATIO rather than defining a second, possibly
    drifting threshold: the same character signature that disqualifies
    pre-OCR text as usable (Phase D.0's routing decision) is exactly
    what should disqualify post-OCR text as clean - that signature's
    meaning ("a broken font/recognition encoding, not legitimate prose"
    per docs/OCR_RULES.md) doesn't change depending on which side of an
    OCR engine the text came from.

    Scoped to extraction_method DOCLING/SURYA only: DIRECT_TEXT pages
    already passed this exact same character-quality gate at
    classification time (src/ocr/router.py's classify_page) and gain
    nothing from being re-evaluated here, and pages where OCR was never
    attempted (still OCR_PENDING) or recovered nothing at all (empty
    cleaned_text) have a ratio of 0.0 by construction
    (_unusable_char_ratio's empty-string case) and cannot trigger this
    rule - "OCR recovered nothing" is a separate, already-observable
    condition (an empty page), not noise within recovered text.
    """
    issues: List[ValidationIssue] = []
    for page in document.pages:
        if page.extraction_method not in (ExtractionMethod.DOCLING, ExtractionMethod.SURYA):
            continue

        text = (page.cleaned_text or page.raw_text).strip()
        ratio = _unusable_char_ratio(text)
        if ratio <= _MAX_UNUSABLE_CHAR_RATIO:
            continue

        issues.append(
            ValidationIssue(
                severity=Severity.WARNING,
                rule_id="OCR_002",
                message=(
                    f"Page {page.page_number} OCR output is {ratio:.0%} unusable characters "
                    f"(control characters or the Unicode replacement character)."
                ),
                page_number=page.page_number,
                suggested_action=(
                    "Inspect this page's source image quality and the OCR engine's output; "
                    "the recovered text appears garbled rather than genuine prose."
                ),
            )
        )
    return issues


def _check_xml_invalid_characters(document: Document) -> List[ValidationIssue]:
    """Warning-level: surfaces every src/utils/text_sanitization.py
    (Layer 1) sanitization event as an audit-trail disclosure.

    This is a read-only re-statement of document.sanitization_events,
    not detection - by design, Layer 1 has already removed the
    offending character from every Page/TextBlock field by the time
    this function runs (see module docstring's DOC_004 section for why
    this rule structurally cannot fire before the fact). One
    ValidationIssue per event, so a reviewer can see exactly which
    page and which kind of text ("page_text" or "text_block") was
    affected and what was removed from it.
    """
    issues: List[ValidationIssue] = []
    for event in document.sanitization_events:
        codepoints = ", ".join(event.removed_codepoints)
        issues.append(
            ValidationIssue(
                severity=Severity.WARNING,
                rule_id="DOC_004",
                message=(
                    f"Removed {len(event.removed_codepoints)} XML-invalid character(s) "
                    f"({codepoints}) from {event.field} on page {event.page_number} "
                    f"before export."
                ),
                page_number=event.page_number,
                suggested_action=(
                    "Confirm the surrounding text still reads correctly. The source PDF "
                    "contained one or more characters that cannot be represented in "
                    "DOCX/XML output; they were automatically removed before export."
                ),
            )
        )
    return issues


# --- Image checks ----------------------------------------------------------


def _check_missing_image_files(document: Document) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    for image in document.images:
        if image.extraction_failed:
            continue  # already reported by _check_failed_image_extraction
        if not Path(image.file_path).is_file():
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_id="IMAGE_001",
                    message=(
                        f"Image '{image.image_id}' reports successful extraction but its file "
                        f"is missing: {image.file_path}"
                    ),
                    page_number=image.page_number,
                    suggested_action="Re-run image extraction for this page; the output file is missing from disk.",
                )
            )
    return issues


def _check_failed_image_extraction(document: Document) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    for image in document.images:
        if image.extraction_failed:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_id="IMAGE_002",
                    message=f"Image extraction failed for image '{image.image_id}' on page {image.page_number}.",
                    page_number=image.page_number,
                    suggested_action="Inspect the source PDF's image data on this page; extraction may need manual recovery.",
                )
            )
    return issues


def _check_pending_alt_text_review(document: Document) -> List[ValidationIssue]:
    """Flag every image whose Figure.alt_text_status is still
    PENDING_REVIEW (Phase F.3) - i.e. every image carrying a
    deterministic placeholder a human has not yet confirmed or edited.
    Images with no Figure at all (extraction failed - already covered
    by _check_failed_image_extraction) are not double-reported here.
    """
    issues: List[ValidationIssue] = []
    for image in document.images:
        if image.figure is None:
            continue
        if image.figure.alt_text_status != AltTextStatus.PENDING_REVIEW:
            continue
        issues.append(
            ValidationIssue(
                severity=Severity.INFO,
                rule_id="IMAGE_004",
                message=(
                    f"Image '{image.image_id}' alt text is a placeholder pending human review."
                ),
                page_number=image.page_number,
                suggested_action=(
                    "Review and, if needed, replace the placeholder alt text before "
                    "publishing this document."
                ),
            )
        )
    return issues


def _check_duplicate_image_ids(document: Document) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    seen: Dict[str, int] = {}

    for image in document.images:
        if image.image_id in seen:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_id="IMAGE_003",
                    message=f"Duplicate image_id '{image.image_id}' (first seen on page {seen[image.image_id]}).",
                    page_number=image.page_number,
                    suggested_action="Ensure image_id generation produces globally unique values.",
                )
            )
        else:
            seen[image.image_id] = image.page_number

    return issues


def _check_docx_embedding_failures(document: Document) -> List[ValidationIssue]:
    """IMAGE_005 (016E / Warning): image file exists and extraction succeeded
    but _add_image() returned False during DOCX generation.

    Only fires after generation (embedded_in_docx explicitly False). Skips
    images already covered by IMAGE_001 (missing file) or IMAGE_002
    (extraction failed) to avoid double-reporting.
    """
    issues: List[ValidationIssue] = []
    for image in document.images:
        if image.embedded_in_docx is not False:
            continue
        if image.extraction_failed:
            continue  # already reported by IMAGE_002
        if not Path(image.file_path).is_file():
            continue  # already reported by IMAGE_001
        issues.append(
            ValidationIssue(
                severity=Severity.WARNING,
                rule_id="IMAGE_005",
                message=(
                    f"Image '{image.image_id}' was not embedded in the generated DOCX "
                    f"(file exists and extraction succeeded, but add_picture() failed)."
                ),
                page_number=image.page_number,
                suggested_action=(
                    "Inspect the image file for format issues preventing DOCX embedding. "
                    "Converting the image to PNG and regenerating may resolve this."
                ),
            )
        )
    return issues


# --- Footnote/Endnote checks (Phase K) ---------------------------------


def _check_footnotes_detected(document: Document) -> List[ValidationIssue]:
    """Info-level: one issue per confidently-detected footnote, matching
    docs/VALIDATION_RULES.md's documented Info example ("Footnote
    detected") verbatim. Not a defect - footnotes are expected content,
    and Phase K never auto-remediates one (per docs/PAGE_RULES.md),
    so this exists purely to surface what was found for human review.
    """
    issues: List[ValidationIssue] = []
    for note in document.footnotes:
        if note.note_type != NoteType.FOOTNOTE:
            continue
        issues.append(
            ValidationIssue(
                severity=Severity.INFO,
                rule_id="NOTE_001",
                message=f"Footnote detected: marker '{note.marker}' on page {note.anchor_page_number}.",
                page_number=note.anchor_page_number,
                suggested_action="Confirm the footnote body was captured correctly; Phase 1 does not auto-remediate footnote content.",
            )
        )
    return issues


def _check_endnotes_detected(document: Document) -> List[ValidationIssue]:
    """Info-level: one issue per confidently-detected endnote, matching
    docs/VALIDATION_RULES.md's documented Info example ("Endnote
    detected") verbatim. page_number is the marker's anchor page (where
    a reviewer is reading), not the endnotes-section page holding the
    body - consistent with how this rule is meant to be acted on.
    """
    issues: List[ValidationIssue] = []
    for note in document.footnotes:
        if note.note_type != NoteType.ENDNOTE:
            continue
        issues.append(
            ValidationIssue(
                severity=Severity.INFO,
                rule_id="NOTE_002",
                message=f"Endnote detected: marker '{note.marker}' on page {note.anchor_page_number}.",
                page_number=note.anchor_page_number,
                suggested_action="Confirm the endnote body was captured correctly; Phase 1 does not auto-remediate endnote content.",
            )
        )
    return issues


# --- Table accessibility checks (FEATURE_015.1) ----------------------------


def _check_table_accessibility(document: Document) -> List[ValidationIssue]:
    """Accessibility-oriented checks for every table in the document.

    Rules:
      TABLE_001 (WARNING): table has no caption — captions are required
        for blind users to know what a table is about before entering it.
      TABLE_002 (WARNING): table has no WCAG H73 summary — complex tables
        need a prose description so screen reader users can understand
        the table's purpose without having to navigate every cell.
      TABLE_003 (WARNING): table has no header row — without a header row,
        screen readers cannot announce column context when navigating cells.
      TABLE_004 (WARNING): one or more header cells are empty — empty
        header cells give screen readers nothing to announce for that
        column or row, leaving blind users without navigation context.
      TABLE_005 (INFO): auto-detected table has low confidence score
        (<0.7) — the detection may have produced an incorrect structure
        that requires careful human review before the table is accessible.

    Severity rationale:
      TABLE_001–004 are Warning, not Error: the table content is still
      present and processable; the accessibility issue is a human-review
      gap, not a processing failure.
      TABLE_005 is Info: low confidence is an observation about detection
      uncertainty, not a confirmed defect — the table may still be correct.
    """
    issues: List[ValidationIssue] = []

    for table in document.tables:
        page = table.page_number

        if not table.caption:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule_id="TABLE_001",
                    message=(
                        f"Table '{table.table_id}' on page {page} has no caption. "
                        "Blind users cannot know what this table is about without a caption."
                    ),
                    page_number=page,
                    suggested_action=(
                        "Add a descriptive caption (e.g. 'Table 1. Summary of results') "
                        "in the Tables workspace."
                    ),
                )
            )

        if not table.summary:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule_id="TABLE_002",
                    message=(
                        f"Table '{table.table_id}' on page {page} has no accessibility summary "
                        "(WCAG H73). Screen readers cannot describe complex table structure without it."
                    ),
                    page_number=page,
                    suggested_action=(
                        "Add a prose summary explaining what the table shows in the "
                        "Tables workspace 'Accessibility summary' field."
                    ),
                )
            )

        has_header_row = any(row.is_header_row for row in table.rows)
        if not has_header_row:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule_id="TABLE_003",
                    message=(
                        f"Table '{table.table_id}' on page {page} has no header row. "
                        "Screen readers cannot announce column context when navigating cells."
                    ),
                    page_number=page,
                    suggested_action=(
                        "In the Tables workspace, click a row to mark it as the header row."
                    ),
                )
            )
        else:
            # TABLE_004: empty header cells
            for row in table.rows:
                if not row.is_header_row:
                    continue
                for cell in row.cells:
                    if cell.is_header and not cell.text.strip():
                        issues.append(
                            ValidationIssue(
                                severity=Severity.WARNING,
                                rule_id="TABLE_004",
                                message=(
                                    f"Table '{table.table_id}' on page {page} has an empty "
                                    f"header cell at row {cell.row_index}, col {cell.col_index}. "
                                    "Screen readers will announce nothing for this column/row."
                                ),
                                page_number=page,
                                suggested_action=(
                                    "Fill in the empty header cell or mark the cell as not a header."
                                ),
                            )
                        )

        from src.models.table import TableStatus
        if table.status == TableStatus.AUTO_DETECTED and table.confidence < 0.7:
            issues.append(
                ValidationIssue(
                    severity=Severity.INFO,
                    rule_id="TABLE_005",
                    message=(
                        f"Table '{table.table_id}' on page {page} was auto-detected with "
                        f"low confidence ({table.confidence:.0%}). Structure may be incorrect."
                    ),
                    page_number=page,
                    suggested_action=(
                        "Review this table's structure carefully; the auto-detected cell "
                        "layout may not match the source PDF."
                    ),
                )
            )

        has_merged = any(
            cell.col_span > 1 or cell.row_span > 1
            for row in table.rows
            for cell in row.cells
        )
        if has_merged:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule_id="TABLE_006",
                    message=(
                        f"Table '{table.table_id}' on page {page} has merged cells. "
                        "Markdown pipe tables cannot represent cell merges; the merged "
                        "structure will be preserved in the DOCX but lost in Markdown."
                    ),
                    page_number=page,
                    suggested_action=(
                        "Verify the DOCX export preserves the merged cell structure. "
                        "The Markdown version will show empty cells in merged positions."
                    ),
                )
            )

        # TABLE_007: detected by a borderless detector (horizontal rule or
        # column alignment) with single-column layout — structure may need
        # reviewer verification since column inference is less reliable when
        # no vertical separators exist.
        borderless_signals = {"horizontal_rules", "column_x_alignment", "span_column_alignment"}
        detected_signal_names = {s.get("name", "") for s in table.evidence_signals}
        is_borderless_only = (
            detected_signal_names & borderless_signals
            and "vector_borders" not in detected_signal_names
        )
        if is_borderless_only and table.col_count <= 1:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule_id="TABLE_007",
                    message=(
                        f"Table '{table.table_id}' on page {page} was detected without "
                        "explicit border lines and has only one inferred column. "
                        "Column structure could not be reliably determined from text alignment."
                    ),
                    page_number=page,
                    suggested_action=(
                        "Review the table in the Tables workspace. If the source PDF has "
                        "multiple columns, manually edit the table structure or recreate it."
                    ),
                )
            )

    return issues
