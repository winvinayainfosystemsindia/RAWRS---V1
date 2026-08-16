"""PDF parsing for RAWRS.

Loads a PDF from disk and produces the initial Document model: one Page
per PDF page, populated Metadata, and processing_status set to PARSED.

Per docs/ARCHITECTURE.md, the Parser module's scope is PDF loading, page
extraction, and basic document analysis only. Text extraction/OCR,
heading detection, image extraction, markdown/DOCX generation, and
validation are handled by later pipeline stages and are out of scope
here - Page objects are created with empty text content for those
stages to populate.
"""

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import List, Union

import fitz  # PyMuPDF
from loguru import logger

from src.models.contracts import Document, Metadata, Page, ProcessingStatus


class PDFParserError(Exception):
    """Raised when a PDF file cannot be opened or parsed."""


def page_text_layer(file_path: Union[str, Path]) -> List[str]:
    """The PDF's own text, one string per physical page, in page order.

    P-1 evidence reader. A Mathpix-imported document knows the *order* its
    blocks came in and nothing about the page each one sits on: the ingestor
    estimates that from proportional line position, which is exact on 11% of
    the benchmark corpus. The PDF the same job already carries states it —
    a page whose text contains a block's text is the page that block is on.
    This function hands that text over and stops there: locating a block in
    it is the alignment module's job, not the parser's.

    ``Page.raw_text`` is not an alternative source. Stage 1 leaves it empty
    (see ``parse_pdf``) and on the Mathpix path Stage 2 fills it from the MMD
    (``src/mathpix/ingestor.py``'s ``_assign_page_text``), so by the time
    anything downstream could look, the PDF's own text is gone.

    Args:
        file_path: Path to the PDF file on the local filesystem.

    Returns:
        One string per physical PDF page, index 0 being page 1, exactly as
        PyMuPDF extracts it — no normalisation, no stripping, no OCR, and
        nothing cached. A page with no text layer (a scan) yields ``""``,
        which is evidence too: it says this page can prove nothing.

    Raises:
        FileNotFoundError: If file_path does not point to an existing file.
        PDFParserError: If the file cannot be opened or read as a PDF.
            Both match ``parse_pdf``'s existing behaviour deliberately —
            one module, one contract.
    """
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"PDF file not found: {path}")

    try:
        with fitz.open(path) as pdf_document:
            return [page.get_text() for page in pdf_document]
    except Exception as exc:  # PyMuPDF raises various error types on bad input
        raise PDFParserError(f"Failed to read text layer of PDF '{path}': {exc}") from exc


def parse_pdf(file_path: Union[str, Path]) -> Document:
    """Parse a PDF file into an initial Document model.

    Args:
        file_path: Path to the PDF file on the local filesystem.

    Returns:
        A Document with one Page per PDF page (in order, starting at 1),
        populated Metadata (filename, page count, processing date and
        duration), and processing_status set to ProcessingStatus.PARSED.

    Raises:
        FileNotFoundError: If file_path does not point to an existing file.
        PDFParserError: If the file cannot be opened as a PDF, or the PDF
            contains no pages.
    """
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"PDF file not found: {path}")

    logger.info("Opening PDF: {}", path)
    start_time = perf_counter()

    try:
        with fitz.open(path) as pdf_document:
            page_count = pdf_document.page_count
            logger.debug("PDF internal metadata for '{}': {}", path.name, pdf_document.metadata)

            if page_count == 0:
                raise PDFParserError(f"PDF '{path}' contains no pages")

            pages = [Page(page_number=i + 1) for i in range(page_count)]
    except PDFParserError:
        raise
    except Exception as exc:  # PyMuPDF raises various error types on bad input
        raise PDFParserError(f"Failed to open PDF '{path}': {exc}") from exc

    duration_seconds = perf_counter() - start_time

    metadata = Metadata(
        filename=path.name,
        page_count=page_count,
        processing_date=datetime.now(timezone.utc),
        processing_duration_seconds=duration_seconds,
    )

    document = Document(
        source_pdf_path=str(path),
        processing_status=ProcessingStatus.PARSED,
        metadata=metadata,
        pages=pages,
    )

    logger.info(
        "Parsed '{}' into {} page(s) in {:.3f}s",
        path.name,
        page_count,
        duration_seconds,
    )

    return document
