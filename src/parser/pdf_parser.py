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
from typing import Union

import fitz  # PyMuPDF
from loguru import logger

from src.models.contracts import Document, Metadata, Page, ProcessingStatus


class PDFParserError(Exception):
    """Raised when a PDF file cannot be opened or parsed."""


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
