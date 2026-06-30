# OCR Rules

> Implementation status and code citations: `PHASE_STATUS.md` (Phases A, D.0, D.1, D.2). This document's page-classification and engine-routing description below already matches the implemented code closely. **Corrected by a Surya Backend Architecture Audit:** the installed `surya-ocr` (0.20.0, "Surya2") is a vision-language-model-backed OCR engine, not the classical torch transformer model an earlier pass assumed. On this project's CPU-only deployment, `RecognitionPredictor`/`SuryaInferenceManager` auto-select a `llamacpp` inference backend that spawns the real upstream `llama-server` binary and runs the `surya-2.gguf` model through it. An intermediate documentation pass incorrectly stated Surya does *not* use llama.cpp — that statement was itself wrong and has been reversed here. See `DECISIONS_LOG.md`.

## Purpose

OCR converts PDF content into machine-readable text while preserving document structure.

OCR output is considered provisional until validation completes.

---

## Processing Engines

Primary Engine:

Docling

Fallback Engine:

Surya OCR

---

## OCR Responsibilities

* Text extraction
* Reading order extraction
* Layout understanding
* Structure preservation

---

## Reading Order Requirements

RAWRS must preserve:

* Heading order
* Paragraph order
* Figure placement
* Caption placement

Examples:

Correct:

Heading

Paragraph

Figure

Caption

Incorrect:

Figure

Heading

Paragraph

Caption

---

## OCR Cleanup Rules

RAWRS should automatically attempt to correct:

### Hyphenation Artifacts

Example:

educa-
tion

becomes

education

---

### OCR Character Errors

Examples:

Iearning

becomes

learning

rn

becomes

m

where confidence supports correction.

---

### Excessive Whitespace

Normalize:

* Multiple spaces
* Repeated line breaks
* Empty lines

---

## Header and Footer Removal

RAWRS should detect and remove:

### Running Headers

Examples:

Chapter Names

Book Titles

Repeated Section Names

---

### Running Footers

Examples:

Copyright Notices

Repeated URLs

Download Notices

Repeated Footer Text

---

### Preserve

RAWRS must preserve:

* Actual page numbers
* Footnote references
* Endnote references

---

## Confidence Handling

Confidence should be tracked when available.

Categories:

High Confidence

Medium Confidence

Low Confidence

Low-confidence regions should be flagged for validation review.

---

## Page Classification and Routing

Before any OCR engine runs, each page is classified using its already-
extracted text - not PDF metadata.

Categories:

DIRECT_TEXT

OCR_REQUIRED

A page is OCR_REQUIRED when:

* No usable text was extracted, or
* The extracted text is dominated by control characters or the Unicode
  replacement character (a broken font encoding, not legitimate prose)

Classification is per page, not per document. A single PDF may contain
both DIRECT_TEXT and OCR_REQUIRED pages.

Routing:

DIRECT_TEXT pages use the existing direct text extraction pipeline.

OCR_REQUIRED pages are routed to Docling (full-page OCR mode). If
Docling fails or recovers no text for a page, Surya OCR runs
automatically as a fallback for that page only - DIRECT_TEXT pages and
pages Docling already recovered text for are never sent to Surya. If
Surya also fails or recovers nothing, that page is left as-is for a
future phase to retry.

OCR-recovered text is treated as Medium Confidence (Docling) or Low
Confidence (Surya fallback) - never High. High Confidence is reserved
for direct text extraction, which has no recognition uncertainty.
Surya's text is graded one rung below Docling's because it is only
ever produced after the primary engine has already failed on that same
page, which warrants the extra scrutiny low-confidence regions get
under validation review.

Docling runs with `force_full_page_ocr=True` rather than its default
layout-driven OCR mode - the default setting returned zero text on
real benchmark pages confirmed (by direct PDF inspection) to contain
genuine prose, so full-page OCR is required despite being slower per
page.

Surya's actual inference backend is environment-dependent: its
`SuryaInferenceManager` auto-selects `vllm` when an NVIDIA GPU is
present, or `llamacpp` otherwise. On this project's CPU-only
deployment, that means Surya OCR runs by spawning the upstream
`llama-server` binary (resolved via the `LLAMA_CPP_BINARY` environment
variable or PATH) and serving the `surya-2.gguf` vision-language model
through it over a local OpenAI-compatible HTTP API - confirmed by a
dedicated backend audit (real `llama-server` process, real GGUF model
download, real per-token generation logs). This is a real, mandatory
runtime dependency on this deployment, not an optional or bundled one:
without a resolvable `llama-server` binary, Surya cannot run at all.
`requirements.txt` has no `llama-cpp-python` entry because RAWRS/Surya
never use the Python bindings - they shell out to the standalone
binary instead, which is why a plain dependency-file scan misses it.

---

## Common OCR Risks

### Broken Words

Example:

accessi bility

---

### Character Substitutions

Example:

0 instead of O

1 instead of l

---

### Reading Order Errors

Common in:

* Scanned PDFs
* Complex layouts
* Academic papers

---

## Phase 1 Limitations

Phase 1 does not guarantee:

* Perfect OCR
* Table understanding
* Equation recognition
* Multi-column reconstruction

These are future-phase concerns.

---

## Success Condition

OCR is successful when:

* Text is extracted correctly
* Reading order is preserved
* Structural information is retained
* Validation can identify uncertain regions
