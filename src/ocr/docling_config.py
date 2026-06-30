"""Single configuration point for Docling OCR (Phase D.1).

Every Docling-specific setting - pipeline options, environment
workarounds - is defined here ONLY. No other module should construct
its own PdfPipelineOptions or DocumentConverter, or set Docling/
Hugging-Face-related environment variables directly. Import
build_converter() from here instead, so a future tuning change (e.g.
revisiting force_full_page_ocr, or adding language hints) never needs
to touch more than this one file.
"""

import os

# Hugging Face Hub's model cache defaults to symlinking blob files into
# its snapshot directories. On Windows, creating a symlink requires a
# privilege most accounts don't have by default
# (SeCreateSymbolicLinkPrivilege), which makes the first-time model
# download fail with:
#   OSError: [WinError 1314] A required privilege is not held by the client
# Disabling symlinks (falling back to plain file copies) avoids this
# entirely, at the cost of slightly more disk space. setdefault() never
# overrides a value an operator has already configured.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")

from docling.datamodel.base_models import InputFormat  # noqa: E402
from docling.datamodel.pipeline_options import PdfPipelineOptions  # noqa: E402
from docling.document_converter import DocumentConverter, PdfFormatOption  # noqa: E402

# force_full_page_ocr=True is required against this project's actual
# benchmark documents: Docling's default layout-driven OCR
# (force_full_page_ocr=False) returned ZERO text on real benchmark
# pages confirmed (by direct PDF inspection) to contain genuine prose -
# its bitmap-region detection missed content that full-page OCR
# correctly recovers (e.g. ~2,500 characters of real text recovered
# from a page that returned empty under the default setting). This is
# significantly slower per page (see
# BENCHMARK_RECONCILIATION_AND_PHASE1_PLAN.md Phase D.1 for measured
# timings), but the default setting was confirmed non-functional
# against this project's own documents, so the slower, correct setting
# is used unconditionally.
_FORCE_FULL_PAGE_OCR = True


def get_pipeline_options() -> PdfPipelineOptions:
    """Build the one, single PdfPipelineOptions configuration used
    everywhere Docling runs in this project."""
    options = PdfPipelineOptions()
    options.do_ocr = True
    options.ocr_options.force_full_page_ocr = _FORCE_FULL_PAGE_OCR
    return options


def build_converter() -> DocumentConverter:
    """Build a DocumentConverter configured per get_pipeline_options().

    Construct one of these per document/run and reuse it across pages -
    DocumentConverter lazily loads its models on first use, and that
    cost should only be paid once per process, not once per page.
    """
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=get_pipeline_options())}
    )
