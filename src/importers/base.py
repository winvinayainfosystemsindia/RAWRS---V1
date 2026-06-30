"""ImportProvider protocol — provider-agnostic interface for document extraction.

Every extraction provider (Mathpix, Azure Document Intelligence, Docling,
native RAWRS PDF extraction, ABBYY, etc.) implements this protocol so that
the RAWRS pipeline, reviewer workspaces, and accessibility engine are
completely insulated from provider-specific details.

Only the Import Layer (src/importers/ and provider-specific packages such
as src/mathpix/) depends on a concrete provider.  Everything downstream of
the RAWRS Document model is provider-agnostic.

Usage::

    document = parse_pdf(pdf_path)            # geometry shell
    document = provider.import_document(      # content import
        document, mmd_path=mmd_path
    )
    # All downstream pipeline stages work from Document unchanged.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from src.models.contracts import Document


@runtime_checkable
class ImportProvider(Protocol):
    """Protocol for document extraction import providers.

    Each provider enriches a Document shell created by parse_pdf() with
    content extracted from the provider's source format (MMD, API response,
    etc.).

    The Document shell has page geometry and page count from the PDF.
    The provider fills in content fields: headings, page text, tables,
    footnotes, front_matter.  All downstream pipeline stages (verification,
    accessibility, export) then work from the Document model — never from
    the raw extraction source.

    Provider identifiers (name property values):
        "mathpix"       — Mathpix MMD + optional DOCX supplement
        "azure_doc_ai"  — Azure Document Intelligence
        "google_doc_ai" — Google Document AI
        "abbyy"         — ABBYY FineReader / Vantage
        "docling"       — IBM Docling
        "rawrs_native"  — RAWRS's own PyMuPDF extraction (the legacy path)
    """

    @property
    def name(self) -> str:
        """Stable machine-readable provider identifier.

        Used in CorrectionRecord.provider and Table.extraction_source.
        """
        ...

    def import_document(self, document: Document, **kwargs: Any) -> Document:
        """Enrich ``document`` with content from this provider.

        Args:
            document: Shell Document created by parse_pdf().  Provides
                page count, PDF geometry, and source_pdf_path.  The
                provider populates content fields and returns the same
                Document instance.
            **kwargs: Provider-specific inputs.
                Mathpix: ``mmd_path`` (Path) — path to the .mmd file.
                Azure:   ``endpoint`` (str), ``key`` (str).
                Docling: no extra args needed.

        Returns:
            The same Document with content fields populated from the
            provider's extraction output.
        """
        ...
