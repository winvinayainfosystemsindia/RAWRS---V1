
"""Phase 1 pipeline orchestration for RAWRS.

Wires together the individually-implemented stages into the end-to-end
workflow: PDF -> Document -> Markdown -> DOCX -> Validation Report.

Pipeline order:
    1. Parse PDF
    2. Extract Text (direct extraction - Phase A) + route pages by
       extraction quality (Phase D.0 - DIRECT_TEXT vs OCR_REQUIRED) +
       run Docling OCR on OCR_REQUIRED pages only (Phase D.1) + run
       Surya OCR as a fallback on whatever Docling left empty (Phase
       D.2) - both gated by the enable_ocr parameter (see
       BENCHMARK_RECONCILIATION_AND_PHASE1_PLAN.md)
    3. Detect Structure (Phase H) - persists per-line bbox/font-layout
       metadata into Document.blocks; does not read or alter reading
       order, columns, tables, or equations (see
       src/structure/structure_detector.py). Also runs Footnote/Endnote
       Detection (Phase K) immediately after, reusing those same blocks
       to populate Document.footnotes (see
       src/footnotes/footnote_detector.py), and Front-Matter Extraction
       (title/author/affiliation) right after that, for the same
       reason - see src/frontmatter/front_matter_extractor.py.
    4. Extract Images
    5. Detect Headings
    6. Generate Markdown
    7. Generate DOCX
    8. Run Validation

Note: Extract Text now sits right after Parse PDF, matching the
canonical flow in docs/ARCHITECTURE.md / docs/CLAUDE_INSTRUCTIONS.md
(Parser -> OCR -> ...), and Detect Structure (new in Phase H) sits
right after it, also matching that same canonical flow's named
"Structure Detection" stage. Two discrepancies against that canonical
order remain and are unchanged by this phase: Heading Detection runs
after Image Extraction (canonical has it before), and Validation runs
after DOCX Generation (canonical has it before). Both are tracked as
later roadmap items, not addressed here.

Each stage is read-only with respect to upstream content (per
docs/VALIDATION_RULES.md's "never silently modify content" principle,
applied here to the orchestrator as well): failures are caught,
logged, and reported on a structured PipelineResult rather than raised,
and the pipeline halts at the first failed stage rather than guessing
how to continue past broken state.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Callable, Dict, List, Optional, Union

from loguru import logger

from src.config.page_numbering import PageNumberingPolicy
from src.docx.docx_generator import generate_docx
from src.footnotes.footnote_detector import detect_footnotes
from src.frontmatter.front_matter_extractor import extract_front_matter
from src.headings.heading_detector import detect_headings, detect_headings_from_pdf
from src.lists.list_detector import detect_lists_from_pdf
from src.images.image_extractor import _extract_images_from_pdf, extract_images
from src.markdown.markdown_builder import build_markdown
from src.models.contracts import Document, ProcessingStatus, Severity, ValidationIssue
from src.ocr.docling_engine import OCRTimingMetrics, run_docling_ocr
from src.ocr.extractor import extract_text
from src.ocr.router import route_pages
from src.ocr.surya_engine import run_surya_ocr
from src.parser.pdf_parser import parse_pdf
from src.structure.structure_detector import detect_structure
from src.tables.table_extractor import extract_tables
from src.validation.validator import validate_document

DEFAULT_OUTPUT_ROOT = Path("outputs")


@dataclass
class PipelineResult:
    """Structured outcome of a single run_pipeline() call.

    Always returned, whether the pipeline succeeded or failed partway
    through - on failure, document/markdown_path/docx_path reflect
    whatever was actually produced before the failing stage, so callers
    can see exactly how far processing got.
    """

    source_pdf_path: str
    success: bool
    status: ProcessingStatus
    duration_seconds: float
    document: Optional[Document] = None
    markdown_path: Optional[Path] = None
    docx_path: Optional[Path] = None
    report_path: Optional[Path] = None
    alt_text_dataset_path: Optional[Path] = None
    validation_issues: List[ValidationIssue] = field(default_factory=list)
    failed_stage: Optional[str] = None
    error_message: Optional[str] = None
    ocr_metrics: Optional[OCRTimingMetrics] = None
    surya_metrics: Optional[OCRTimingMetrics] = None
    # FEATURE_020 — document.version at the moment this file was written,
    # so a download endpoint can tell "has the Document changed since"
    # with one integer comparison instead of routes.py enumerating every
    # correction type that should invalidate a cached export.
    markdown_generated_at_version: Optional[int] = None
    docx_generated_at_version: Optional[int] = None


def run_pipeline(
    pdf_path: Union[str, Path],
    output_root: Union[str, Path] = DEFAULT_OUTPUT_ROOT,
    enable_ocr: bool = True,
    page_numbering_policy: Optional[PageNumberingPolicy] = None,
    mmd_path: Optional[Path] = None,
    image_dir: Optional[Path] = None,
    on_stage_complete: Optional[Callable[[str], None]] = None,
) -> PipelineResult:
    """Run the full Phase 1 pipeline against a single PDF.

    Args:
        pdf_path: Path to the source PDF.
        output_root: Base directory for all generated artifacts.
            Markdown is written to {output_root}/markdown/<stem>.md,
            DOCX to {output_root}/docx/<stem>.docx, the validation
            report to {output_root}/reports/<stem>.json, and extracted
            images to {output_root}/images/<stem>/.
        enable_ocr: Whether to run Docling OCR on OCR_REQUIRED pages
            (Phase D.1), followed by Surya as a fallback on whatever
            Docling left empty (Phase D.2). Defaults to True, matching
            production behavior. Docling's full-page OCR pipeline is
            slow (roughly 1-3 minutes per OCR_REQUIRED page - see
            BENCHMARK_RECONCILIATION_AND_PHASE1_PLAN.md Phase D.1), so
            tests that aren't specifically exercising OCR pass
            enable_ocr=False to keep their fixtures' original,
            pre-Docling text state and runtime. Has no effect on
            documents with no OCR_REQUIRED pages either way.
            Ignored when ``mmd_path`` is supplied (Mathpix is the OCR).
        page_numbering_policy: Controls which pages receive H6 markers
            and what text they contain.  Passed through unchanged to
            detect_headings() (Stage 5) and build_markdown() (Stage 6)
            so both stages stay consistent.  When None (default), the
            legacy behaviour is preserved: every page receives a marker
            whose text is the detected printed label when available,
            falling back to the physical page number.
        mmd_path: Optional path to a Mathpix MMD file.  When supplied,
            the Mathpix Import Layer runs after Stage 1 (parse_pdf) and
            populates headings, text, tables, footnotes, and front_matter
            from the MMD.  Stages that would duplicate Mathpix's work
            (extract_text, route_pages, OCR engines, detect_footnotes,
            extract_front_matter, extract_tables, detect_headings) are
            skipped.  All other stages (detect_structure, extract_images,
            build_markdown, generate_docx, validate_document) run
            unchanged.  When None (default), the existing RAWRS-only
            extraction path runs exactly as before — zero behavioral
            change for all existing callers.
        image_dir: Optional directory of uploaded image files that
            accompanied the MMD (the "Mathpix package"). Only meaningful
            when ``mmd_path`` is also supplied. Every uploaded image is
            registered as a Document.images entry via the cross-source
            verification engine (src/verification/) during Stage 2 — never
            silently dropped, matched or not. Stage 4's PDF image
            extraction still runs on the Mathpix path, but only to verify
            the package (src/verification/figures.py's PDF matcher); it
            never overwrites document.images there.

    Returns:
        A PipelineResult describing what was produced (or where and why
        processing stopped, on failure). Never raises - all stage
        failures are caught and reported on the result instead.
    """
    pdf_path = Path(pdf_path)
    output_root = Path(output_root)
    stem = pdf_path.stem
    start_time = perf_counter()

    logger.info("=== Starting Phase 1 pipeline for '{}' ===", pdf_path)

    # Stage 1: Parse PDF
    try:
        document = parse_pdf(pdf_path)
        logger.info("Stage 1/8 (Parse PDF) complete: {} page(s)", len(document.pages))
        if on_stage_complete: on_stage_complete("parse_pdf")
    except Exception as exc:
        logger.error("Stage 1/8 (Parse PDF) failed: {}", exc)
        return _build_result(
            pdf_path,
            document=None,
            success=False,
            status=ProcessingStatus.FAILED,
            start_time=start_time,
            failed_stage="parse_pdf",
            error_message=str(exc),
        )

    # Stage 2: Extract Text + OCR, OR Mathpix Import (mutually exclusive).
    #
    # Mathpix path (mmd_path supplied):
    #   The MathpixImportProvider populates headings, page text, tables,
    #   footnotes, and front_matter from the MMD.  extract_text / route_pages
    #   / OCR engines are skipped because Mathpix is the extraction source.
    #
    # RAWRS-native path (mmd_path is None):
    #   Unchanged from before: direct extraction, OCR routing, Docling,
    #   Surya fallback.
    ocr_metrics: Optional[OCRTimingMetrics] = None
    surya_metrics: Optional[OCRTimingMetrics] = None
    alt_text_dataset_path: Optional[Path] = None
    _mathpix_path = bool(mmd_path)
    try:
        if _mathpix_path:
            from src.mathpix.ingestor import MathpixImportProvider
            document = MathpixImportProvider().import_document(
                document, mmd_path=mmd_path, image_dir=image_dir
            )
        else:
            document = extract_text(document)
            document = route_pages(document)
            if enable_ocr:
                ocr_metrics = OCRTimingMetrics()
                document = run_docling_ocr(document, metrics=ocr_metrics)
                surya_metrics = OCRTimingMetrics()
                document = run_surya_ocr(document, metrics=surya_metrics)
        document.processing_status = ProcessingStatus.OCR_COMPLETE
        logger.info(
            "Stage 2/8 (Extract Text) complete [{}]",
            "mathpix" if _mathpix_path else "rawrs-native",
        )
        if on_stage_complete: on_stage_complete("extract_text")
    except Exception as exc:
        logger.error("Stage 2/8 (Extract Text) failed: {}", exc)
        document.processing_status = ProcessingStatus.FAILED
        return _build_result(
            pdf_path,
            document=document,
            success=False,
            status=ProcessingStatus.FAILED,
            start_time=start_time,
            failed_stage="extract_text",
            error_message=str(exc),
            ocr_metrics=ocr_metrics,
            surya_metrics=surya_metrics,
            alt_text_dataset_path=alt_text_dataset_path,
        )

    # Stage 3: Detect Structure (always) + content detection substages
    # (gated: skipped on the Mathpix path because Mathpix already supplied
    # footnotes, front matter, tables, and headings).
    #
    # detect_structure() always runs — its bbox and font-flag data are needed
    # by all downstream stages regardless of extraction source (reading order,
    # bold/italic accessibility signals, printed page label detection, table
    # bbox suppression in markdown, image proximity scoring).
    #
    # On the Mathpix path the content substages are skipped:
    #   detect_footnotes   → Mathpix supplied these (Phase M-3: recovery mode)
    #   extract_front_matter → Mathpix supplied this
    #   extract_tables     → Mathpix supplied these (Phase M-3: recovery mode)
    # detect_headings (Stage 5) is also skipped on the Mathpix path for the
    # same reason; it is noted there.
    try:
        document = detect_structure(document)
        if not _mathpix_path:
            document = detect_footnotes(document)
            document = extract_front_matter(document)
            document.tables = extract_tables(document, pdf_path)
        logger.info(
            "Stage 3/8 (Detect Structure) complete: {} block(s), {} footnote(s)/endnote(s), "
            "title {}, {} table(s)",
            len(document.blocks),
            len(document.footnotes),
            "found" if document.front_matter and document.front_matter.title else "not found",
            len(document.tables),
        )
        if on_stage_complete: on_stage_complete("detect_structure")
    except Exception as exc:
        logger.error("Stage 3/8 (Detect Structure) failed: {}", exc)
        document.processing_status = ProcessingStatus.FAILED
        return _build_result(
            pdf_path,
            document=document,
            success=False,
            status=ProcessingStatus.FAILED,
            start_time=start_time,
            failed_stage="detect_structure",
            error_message=str(exc),
            ocr_metrics=ocr_metrics,
            surya_metrics=surya_metrics,
            alt_text_dataset_path=alt_text_dataset_path,
        )

    # Stage 4: Extract Images.
    #
    # RAWRS-native path: unchanged — extract_images() is the sole source
    # of document.images (Phase F.1-F.3 link each retained image to a
    # Figure with a position, any detected caption, and a deterministic
    # placeholder alt text - see image_extractor.py).
    #
    # Mathpix path: document.images was already populated in Stage 2 from
    # the uploaded package (authoritative). The PDF is opened here only to
    # verify that package — via the cross-source verification engine
    # (src/verification/) — never to replace it. _extract_images_from_pdf()
    # returns a plain list rather than assigning document.images, so a
    # PDF that fails to open or extract anything simply yields fewer
    # verification signals; it can never remove a package-derived figure.
    try:
        if _mathpix_path:
            pdf_images = _extract_images_from_pdf(document, output_dir=output_root / "images")
            from src.verification.engine import engine
            import src.verification.figures  # noqa: F401 - registers FigureAssetVerifier

            findings = engine.run_pdf_verification("figure", document.images, pdf_images)
            document.verification_findings.extend(findings)
            engine.findings_to_corrections(document, findings)
        else:
            document = extract_images(document, output_dir=output_root / "images")
        document.metadata.image_count = len(document.images)
        alt_text_dataset_path = _write_alt_text_dataset(
            document, output_root / "alt_text_dataset" / f"{stem}.json"
        )
        logger.info("Stage 4/8 (Extract Images) complete: {} image(s)", len(document.images))
        if on_stage_complete: on_stage_complete("extract_images")
    except Exception as exc:
        logger.error("Stage 4/8 (Extract Images) failed: {}", exc)
        document.processing_status = ProcessingStatus.FAILED
        return _build_result(
            pdf_path,
            document=document,
            success=False,
            status=ProcessingStatus.FAILED,
            start_time=start_time,
            failed_stage="extract_images",
            error_message=str(exc),
            ocr_metrics=ocr_metrics,
            surya_metrics=surya_metrics,
            alt_text_dataset_path=alt_text_dataset_path,
        )

    # Stage 5: Detect Headings
    #
    # RAWRS-native path: unchanged — detect_headings() is the sole source
    # of document.headings.
    #
    # Mathpix path: document.headings was already populated in Stage 2
    # from the imported package (authoritative). detect_headings_from_pdf()
    # independently re-derives content headings (H1-H5) from the PDF's own
    # typography, purely as verification evidence — via the same generic
    # cross-source verification engine figures use (src/verification/) —
    # never to replace Mathpix's headings. This is HeadingVerifier
    # (src/verification/headings.py), the second registered asset type.
    try:
        if _mathpix_path:
            pdf_headings = detect_headings_from_pdf(document.source_pdf_path)
            content_headings = [h for h in document.headings if not h.is_page_marker]
            from src.verification.engine import engine
            import src.verification.headings  # noqa: F401 - registers HeadingVerifier

            findings = engine.run_pdf_verification(
                "heading", content_headings, pdf_headings, pdf_path=document.source_pdf_path
            )
            document.verification_findings.extend(findings)
            engine.findings_to_corrections(document, findings)

            # Lists: document.lists was already populated in Stage 2 from
            # the imported package's own list markup (see
            # _group_list_items_to_lists() in src/mathpix/ingestor.py).
            # detect_lists_from_pdf() independently re-derives lists from
            # PDF geometry, purely to recover a real list Mathpix didn't
            # even tag as one at all (flattened to plain paragraphs) —
            # ListVerifier (src/verification/lists.py), the third
            # registered asset type.
            pdf_lists = detect_lists_from_pdf(document.source_pdf_path)
            import src.verification.lists  # noqa: F401 - registers ListVerifier

            list_findings = engine.run_pdf_verification("list", document.lists, pdf_lists)
            document.verification_findings.extend(list_findings)
            engine.findings_to_corrections(document, list_findings)

            # Callouts: document.callouts was already populated in Stage 2
            # from the imported package's own label-pattern classification
            # (src/mathpix/mmd_parser.py::classify_callout_type()). No
            # independent PDF-side box detector exists yet (see
            # src/verification/callouts.py's module docstring) — this
            # verifier's job is evaluating the classification's own
            # confidence (label specificity, anchoring-heading integrity),
            # not cross-source matching. FEATURE_019 — the fourth
            # registered asset type, and the first proving the framework
            # generalizes beyond Heading/List/Table.
            if document.callouts:
                import src.verification.callouts  # noqa: F401 - registers CalloutVerifier

                callout_findings = engine.run_pdf_verification(
                    "callout", document.callouts, [], document=document
                )
                document.verification_findings.extend(callout_findings)
                engine.findings_to_corrections(document, callout_findings)
        else:
            document = detect_headings(document, page_numbering_policy=page_numbering_policy)
            # Detect Headings re-sets OCR_COMPLETE; harmless no-op now that
            # Stage 2 already sets it correctly for its own (real) reason.
            document.processing_status = ProcessingStatus.OCR_COMPLETE
        logger.info("Stage 5/8 (Detect Headings) complete: {} heading(s)", len(document.headings))
        if on_stage_complete: on_stage_complete("detect_headings")
    except Exception as exc:
        logger.error("Stage 5/8 (Detect Headings) failed: {}", exc)
        document.processing_status = ProcessingStatus.FAILED
        return _build_result(
            pdf_path,
            document=document,
            success=False,
            status=ProcessingStatus.FAILED,
            start_time=start_time,
            failed_stage="detect_headings",
            error_message=str(exc),
            ocr_metrics=ocr_metrics,
            surya_metrics=surya_metrics,
            alt_text_dataset_path=alt_text_dataset_path,
        )

    # Stage 6: Generate Markdown
    markdown_path: Optional[Path] = None
    markdown_generated_at_version: Optional[int] = None
    try:
        markdown_content = build_markdown(document, page_numbering_policy=page_numbering_policy)
        markdown_path = output_root / "markdown" / f"{stem}.md"
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(markdown_content, encoding="utf-8")
        markdown_generated_at_version = document.version
        document.processing_status = ProcessingStatus.MARKDOWN_COMPLETE
        logger.info("Stage 6/8 (Generate Markdown) complete: {}", markdown_path)
        if on_stage_complete: on_stage_complete("generate_markdown")
    except Exception as exc:
        logger.error("Stage 6/8 (Generate Markdown) failed: {}", exc)
        document.processing_status = ProcessingStatus.FAILED
        return _build_result(
            pdf_path,
            document=document,
            success=False,
            status=ProcessingStatus.FAILED,
            start_time=start_time,
            failed_stage="generate_markdown",
            error_message=str(exc),
            ocr_metrics=ocr_metrics,
            surya_metrics=surya_metrics,
            alt_text_dataset_path=alt_text_dataset_path,
        )

    # Stage 7: Generate DOCX
    docx_path: Optional[Path] = None
    docx_generated_at_version: Optional[int] = None
    try:
        docx_path = generate_docx(
            document, markdown_content, output_path=output_root / "docx" / f"{stem}.docx"
        )
        docx_generated_at_version = document.version
        document.processing_status = ProcessingStatus.DOCX_COMPLETE
        logger.info("Stage 7/8 (Generate DOCX) complete: {}", docx_path)
        if on_stage_complete: on_stage_complete("generate_docx")
    except Exception as exc:
        logger.error("Stage 7/8 (Generate DOCX) failed: {}", exc)
        document.processing_status = ProcessingStatus.FAILED
        return _build_result(
            pdf_path,
            document=document,
            success=False,
            status=ProcessingStatus.FAILED,
            start_time=start_time,
            failed_stage="generate_docx",
            error_message=str(exc),
            markdown_path=markdown_path,
            markdown_generated_at_version=markdown_generated_at_version,
            ocr_metrics=ocr_metrics,
            surya_metrics=surya_metrics,
            alt_text_dataset_path=alt_text_dataset_path,
        )

    # Stage 8: Run Validation
    try:
        issues = validate_document(document)
        document.validation_issues = issues
        document.processing_status = ProcessingStatus.VALIDATED
        report_path = _write_validation_report(
            document, issues, output_root / "reports" / f"{stem}.json"
        )
        logger.info("Stage 8/8 (Run Validation) complete: {} issue(s)", len(issues))
        if on_stage_complete: on_stage_complete("run_validation")
    except Exception as exc:
        logger.error("Stage 8/8 (Run Validation) failed: {}", exc)
        document.processing_status = ProcessingStatus.FAILED
        return _build_result(
            pdf_path,
            document=document,
            success=False,
            status=ProcessingStatus.FAILED,
            start_time=start_time,
            failed_stage="run_validation",
            error_message=str(exc),
            markdown_path=markdown_path,
            docx_path=docx_path,
            markdown_generated_at_version=markdown_generated_at_version,
            docx_generated_at_version=docx_generated_at_version,
            ocr_metrics=ocr_metrics,
            surya_metrics=surya_metrics,
            alt_text_dataset_path=alt_text_dataset_path,
        )

    logger.info(
        "=== Phase 1 pipeline complete for '{}' in {:.2f}s ===",
        pdf_path,
        perf_counter() - start_time,
    )
    return _build_result(
        pdf_path,
        document=document,
        success=True,
        status=ProcessingStatus.VALIDATED,
        start_time=start_time,
        markdown_path=markdown_path,
        docx_path=docx_path,
        markdown_generated_at_version=markdown_generated_at_version,
        docx_generated_at_version=docx_generated_at_version,
        report_path=report_path,
        alt_text_dataset_path=alt_text_dataset_path,
        validation_issues=issues,
        ocr_metrics=ocr_metrics,
        surya_metrics=surya_metrics,
    )


def _build_result(
    pdf_path: Path,
    *,
    document: Optional[Document],
    success: bool,
    status: ProcessingStatus,
    start_time: float,
    failed_stage: Optional[str] = None,
    error_message: Optional[str] = None,
    markdown_path: Optional[Path] = None,
    docx_path: Optional[Path] = None,
    markdown_generated_at_version: Optional[int] = None,
    docx_generated_at_version: Optional[int] = None,
    report_path: Optional[Path] = None,
    alt_text_dataset_path: Optional[Path] = None,
    validation_issues: Optional[List[ValidationIssue]] = None,
    ocr_metrics: Optional[OCRTimingMetrics] = None,
    surya_metrics: Optional[OCRTimingMetrics] = None,
) -> PipelineResult:
    return PipelineResult(
        source_pdf_path=str(pdf_path),
        success=success,
        status=status,
        duration_seconds=perf_counter() - start_time,
        document=document,
        markdown_path=markdown_path,
        docx_path=docx_path,
        markdown_generated_at_version=markdown_generated_at_version,
        docx_generated_at_version=docx_generated_at_version,
        report_path=report_path,
        alt_text_dataset_path=alt_text_dataset_path,
        validation_issues=validation_issues or [],
        failed_stage=failed_stage,
        error_message=error_message,
        ocr_metrics=ocr_metrics,
        surya_metrics=surya_metrics,
    )


def _write_validation_report(
    document: Document, issues: List[ValidationIssue], report_path: Path
) -> Path:
    report_path.parent.mkdir(parents=True, exist_ok=True)

    severity_counts = {severity.value: 0 for severity in Severity}
    for issue in issues:
        severity_counts[issue.severity.value] += 1

    from src.verification.benchmark_report import aggregate as aggregate_benchmark

    report = {
        "source_pdf_path": document.source_pdf_path,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {**severity_counts, "total": len(issues)},
        "issues": [issue.model_dump(mode="json") for issue in issues],
        # FEATURE_019 — objects preserved/repaired/recovered per asset
        # type, Mathpix accuracy, recovery rate. Empty per_asset_type on
        # the RAWRS-native path (no cross-source verification runs there
        # at all) — not an error, an accurate "nothing to report".
        "benchmark": aggregate_benchmark(document),
    }

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report_path


# Vertical window (PDF points) of document.blocks lines captured as
# "nearby context" per image in the dataset sidecar - deliberately
# wider than image_extractor.py's _CAPTION_PROXIMITY_PT (36pt), since
# this is exploratory context for a future human reviewer/dataset
# consumer, not a precision caption-match decision.
_DATASET_CONTEXT_WINDOW_PT = 100.0
_DATASET_CONTEXT_MAX_BLOCKS = 5


def _write_alt_text_dataset(document: Document, dataset_path: Path) -> Path:
    """Write a filesystem dataset sidecar of per-image alt-text context
    (Phase F.5 - see the Phase H.5 Alt Text Architecture Audit's Dataset
    Collection Strategy).

    One JSON record per successfully-extracted image: its position,
    whatever Figure metadata src/images/image_extractor.py linked to it
    (placeholder alt text and PENDING_REVIEW status included), and the
    nearest few document.blocks (Phase H) lines on its page, as context
    for whoever - human reviewer or a future, separately-scoped
    capability - eventually needs to produce a real description. This
    captures data passively; it does not generate, infer, or interpret
    anything about an image's actual visual content.

    Mirrors _write_validation_report's shape (same directory-per-stem
    convention, same plain-JSON-file approach) - RAWRS has no database
    (docs/ARCHITECTURE.md), so a filesystem sidecar is the only
    consistent place for this to live.
    """
    dataset_path.parent.mkdir(parents=True, exist_ok=True)

    blocks_by_page: Dict[int, List] = {}
    for block in document.blocks:
        blocks_by_page.setdefault(block.page_number, []).append(block)

    image_records = []
    for image in document.images:
        if image.extraction_failed:
            continue  # nothing was actually retained - no context to capture

        record = {
            "image_id": image.image_id,
            "page_number": image.page_number,
            "file_path": image.file_path,
            "bbox": image.bbox.model_dump(mode="json") if image.bbox else None,
            "figure": image.figure.model_dump(mode="json") if image.figure else None,
            "nearby_text": _nearby_block_texts(image, blocks_by_page.get(image.page_number, [])),
        }
        image_records.append(record)

    dataset = {
        "source_pdf_path": document.source_pdf_path,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "images": image_records,
    }

    dataset_path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    return dataset_path


def _nearby_block_texts(image, page_blocks: List) -> List[str]:
    """The closest few same-page TextBlocks (Phase H) to this image's
    bbox, by vertical distance, within _DATASET_CONTEXT_WINDOW_PT - any
    text near an image, not just lines matching a caption pattern (that
    precision match is image_extractor.py's separate, stricter job)."""
    if image.bbox is None or not page_blocks:
        return []

    candidates = []
    for block in page_blocks:
        if block.bbox.y0 >= image.bbox.y1:
            distance = block.bbox.y0 - image.bbox.y1
        elif block.bbox.y1 <= image.bbox.y0:
            distance = image.bbox.y0 - block.bbox.y1
        else:
            distance = 0.0
        if distance <= _DATASET_CONTEXT_WINDOW_PT:
            candidates.append((distance, block))

    candidates.sort(key=lambda pair: pair[0])
    return [block.text for _, block in candidates[:_DATASET_CONTEXT_MAX_BLOCKS]]
