# RAWRS Phase 1

> **For current implementation status of every item below, see `PHASE_STATUS.md`.** This document records intended/agreed scope; it does not track what's actually built. Last reconciled against code in this documentation audit.

## Objective

Transform educational and academic PDFs into structured, reviewable, and exportable formats while reducing repetitive remediation effort.

Phase 1 establishes the production automation foundation for WinVinaya Foundation.

---

# Input

PDF

Supported Inputs:

* Educational documents
* Reports
* Manuals
* Academic content
* Single-column PDFs
* Image-based PDFs
* Text-based PDFs

---

# Outputs

Primary Output:

* Accessible DOCX

Intermediate Output:

* Structured Markdown

Generated Artifacts:

* Extracted Images
* Validation Reports
* Processing Logs
* Document Metadata

---

# Processing Pipeline

PDF
→ Parsing
→ OCR (when required)
→ Structure Detection
→ Footnote/Endnote Detection
→ Reading Order Validation
→ OCR Cleanup
→ Header/Footer Removal
→ Page Detection
→ Heading Detection
→ Image Extraction
→ Figure Detection
→ Markdown Generation
→ Validation
→ DOCX Generation
→ Human Review

See `ARCHITECTURE_CURRENT.md` for the exact current stage order including two known deviations from this list (Image Extraction before Heading Detection; Validation after DOCX Generation).

---

# Capabilities

## OCR

* Text extraction
* Layout extraction
* Reading order extraction

## Structure Detection

Persist per-line layout metadata (position, font size, bold) for every page, as a foundation for downstream features (footnote detection, reading-order validation) without re-deriving it.

## Footnote / Endnote Detection & Preservation

* Detect inline footnote and endnote markers
* Link each marker to its matching note body by number
* Preserve the relationship into both Markdown (footnote syntax) and DOCX (bookmark/hyperlink, not native Word footnote fields)
* Detection and preservation only — Phase 1 does not automatically remediate or rewrite note content

## Reading Order Validation

* Detect backward reading-order jumps and overlapping content blocks
* **Detection only.** Phase 1 does not reconstruct or correct reading order, and does not stitch a paragraph that spans two pages back into one — see `KNOWN_LIMITATIONS.md`.

## OCR Error Cleanup

* Broken word repair
* Hyphenation cleanup
* Common OCR artifact cleanup

## Header/Footer Removal

Remove:

* Running headers
* Running footers
* Download notices
* Repeated page artifacts

## Page Marker Detection

Generate:

H6 Page Markers

Example:

###### 1

###### 2

## Page Break Preservation

Maintain PDF page boundaries.

No page loss.

No page reordering.

## Heading Detection

Detect:

* H1
* H2
* H3
* H4
* H5
* H6

Using Phase 1 heading rules.

## Image Extraction

Extract:

* Images
* Figures
* Diagrams
* Charts

Store as separate assets.

Filter out background images, decorative artifacts, full-page noise, and duplicate extractions before storing — only meaningful figures are retained.

## Figure Detection

Detect:

* Figure labels
* Figure references
* Figure captions

## Alt-Text Infrastructure (not Alt-Text Generation)

Generate a deterministic, rule-based placeholder alt-text string for every retained image, and mark it pending human review. Log image metadata, context, caption, and placeholder alt text to a dataset file for future model training.

This is infrastructure only — see "Explicitly Excluded" below for what remains out of scope.

## Metadata Capture

Capture:

* Filename
* Page count
* Processing date
* Processing duration
* Image count

## Markdown Generation

Generate canonical structured markdown.

Markdown acts as the source of truth for downstream processing.

## Validation

Validate:

* Structure
* Heading hierarchy
* Missing content
* OCR issues
* Extraction failures

## DOCX Generation

Generate:

* Times New Roman formatting
* Heading hierarchy
* Page markers
* Page breaks
* Inline centered images
* Centered figure captions
* Navigation structure

---

# Explicitly Excluded

Not included in Phase 1:

* AI-Generated Alt Text (deterministic placeholder alt-text *infrastructure* is in scope and built — see "Alt-Text Infrastructure" above; generating a real descriptive alt-text string via a model is not)
* Table Remediation
* Equation Remediation
* Accessibility Tagging
* PDF Tagging
* Knowledge Graphs
* AI Model Training
* Custom Foundation Models
* Multi-Agent Systems
* Advanced Analytics

---

# Success Criteria

RAWRS Phase 1 is successful when:

1. PDFs can be processed reliably.
2. Structured markdown is generated.
3. Accessible DOCX files are generated.
4. Heading hierarchy is preserved.
5. Page boundaries are preserved.
6. Images are extracted correctly.
7. Validation reports are produced.
8. Human remediation effort is reduced.

---

# North Star Metric

Human Minutes Per 100 Pages

All Phase 1 decisions should support reducing this metric while maintaining accessibility quality.
