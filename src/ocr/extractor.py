"""Text extraction for RAWRS (Phase A: direct extraction only).

Populates Page.raw_text and Page.cleaned_text for born-digital PDFs by
reading PyMuPDF's native text layer directly - no OCR engine involved.
Per docs/ARCHITECTURE.md, this module's full responsibilities are text
extraction, reading order extraction, and OCR cleanup; Phase A covers
only the first of those, and only the directly-extractable case.

Pages with no extractable text (fully scanned pages) are left
untouched here. They remain pending for a future phase that wires in
an actual OCR engine (Docling primary, Surya fallback, per
docs/OCR_RULES.md / docs/TECH_STACK.md) - see
BENCHMARK_RECONCILIATION_AND_PHASE1_PLAN.md, Phase D. No OCR engine
code is added in this phase.

Cleanup scope: cleaned_text here is whitespace-normalized raw_text
only (collapsing repeated blank lines, trimming trailing whitespace -
the "Excessive Whitespace" rule in docs/OCR_RULES.md), plus (XML
Sanitization Architecture, Layer 1) stripped of any character illegal
in OOXML/XML - see src/utils/text_sanitization.py for why this lives
alongside whitespace cleanup rather than as a separate pass: both are
"make this text safe for every downstream consumer" cleanup, applied
once, here, rather than left to each consumer. raw_text is deliberately
NOT sanitized - it stays a true, unmodified record of exactly what
PyMuPDF returned, for forensics/comparison; cleaned_text is the field
every downstream stage actually reads, so it is the one made safe.
Hyphenation repair and character-error correction are explicitly NOT
done here: docs/OCR_RULES.md scopes those to cases "where confidence
supports correction," which requires the OCR confidence machinery a
later phase will bring - applying that judgment with only a
HIGH/deterministic direct-extraction signal would be guessing, not
correcting.
"""

import re
from pathlib import Path
from typing import Dict

import fitz  # PyMuPDF
from loguru import logger

from src.models.contracts import Document, OCRConfidence, Page, SanitizationEvent
from src.utils.text_sanitization import sanitize_xml_text


class TextExtractionError(Exception):
    """Raised when the source PDF cannot be opened for text extraction."""


def extract_text(document: Document) -> Document:
    """Populate Page.raw_text/cleaned_text via direct PyMuPDF text extraction.

    Args:
        document: A Document whose source_pdf_path points to a readable
            PDF, with Page objects already created by the parser.
            Re-opens the PDF independently of the parser stage.

    Returns:
        The same Document instance. Each page with a usable text layer
        gets raw_text (verbatim PyMuPDF output), cleaned_text
        (whitespace-normalized and XML-sanitized - see module
        docstring), and ocr_confidence=HIGH (direct extraction has no
        recognition uncertainty). Any XML-illegal character removed
        from cleaned_text is recorded onto
        document.sanitization_events. Pages with no extractable text
        are left exactly as the parser created them -
        page_number set, text fields empty, ocr_confidence still None -
        so it stays visible that they are pending OCR, not "processed
        with low confidence."

    Raises:
        FileNotFoundError: If document.source_pdf_path does not exist.
        TextExtractionError: If the PDF exists but cannot be opened.
    """
    pdf_path = Path(document.source_pdf_path)

    if not pdf_path.is_file():
        raise FileNotFoundError(f"Source PDF not found: {pdf_path}")

    logger.info("Extracting text from '{}'", pdf_path)

    try:
        pdf_document = fitz.open(pdf_path)
    except Exception as exc:  # PyMuPDF raises various error types on bad input
        raise TextExtractionError(
            f"Failed to open PDF '{pdf_path}' for text extraction: {exc}"
        ) from exc

    pages_by_number: Dict[int, Page] = {page.page_number: page for page in document.pages}
    extracted_count = 0

    try:
        for page_index in range(pdf_document.page_count):
            page_number = page_index + 1
            page_model = pages_by_number.get(page_number)
            if page_model is None:
                continue  # Document.pages has no entry for this PDF page; nothing to populate

            raw_text = pdf_document[page_index].get_text()
            if not raw_text.strip():
                continue  # no extractable text - leave pending for a future OCR stage

            page_model.raw_text = raw_text
            cleaned, removed = sanitize_xml_text(normalize_whitespace(raw_text))
            page_model.cleaned_text = cleaned
            page_model.ocr_confidence = OCRConfidence.HIGH
            extracted_count += 1

            if removed:
                document.sanitization_events.append(
                    SanitizationEvent(
                        page_number=page_number, field="page_text", removed_codepoints=removed
                    )
                )
    finally:
        pdf_document.close()

    logger.info(
        "Extracted text from {}/{} page(s) of '{}' via direct extraction",
        extracted_count,
        len(document.pages),
        pdf_path.name,
    )
    return document


def normalize_whitespace(text: str) -> str:
    """Collapse repeated blank lines and trim trailing whitespace per line.

    Deliberately mechanical only - see module docstring for why
    hyphenation/character-error correction are out of scope here.

    Public (not module-private) because src/ocr/docling_engine.py
    (Phase D.1) reuses it for OCR-recovered text too - the same
    whitespace cleanup applies regardless of which extraction path
    produced the raw text, and duplicating this logic in a second
    module would violate "no duplicate data structures/logic."
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    collapsed = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return collapsed.strip()
