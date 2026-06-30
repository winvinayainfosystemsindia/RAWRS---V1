# RAWRS Architecture

> This document describes the **canonical/intended** architecture. For the actual current pipeline order (including two tracked deviations from the diagram below) and the full current module list, see `ARCHITECTURE_CURRENT.md`.

## Purpose

RAWRS is a modular document remediation pipeline designed for educational and academic PDFs.

The architecture prioritizes simplicity, maintainability, auditability, and future extensibility.

---

## High-Level Workflow

PDF
→ Parser
→ OCR
→ Structure Detection
→ Footnote/Endnote Detection
→ Heading Detection
→ Image Extraction
→ Markdown Generation
→ Validation
→ DOCX Generation
→ Output

**Current implementation deviates from this diagram in two places** (Image Extraction runs before Heading Detection; Validation runs after DOCX Generation, not before) — both deliberate, tracked, and explained in `ARCHITECTURE_CURRENT.md` and `DECISIONS_LOG.md`. Treat this diagram as the target to realign to, not as a description of what runs today.

---

## Core Modules

### Parser

Location:

src/parser/

Responsibilities:

* PDF loading
* Page extraction
* Basic document analysis

Output:

Document Model

---

### OCR

Location:

src/ocr/

Responsibilities:

* Direct text extraction for born-digital pages (no OCR engine invoked)
* Per-page routing (DIRECT_TEXT vs OCR_REQUIRED) before any OCR engine runs
* Docling as the primary OCR engine for OCR_REQUIRED pages
* Surya as a CPU-based fallback engine for pages Docling leaves empty
* Reading order extraction
* OCR cleanup

Output:

Structured Page Content

---

### Structure Detection

Location:

src/structure/

Responsibilities:

* Persist per-line layout metadata (bounding box, font size, bold flag, page order) into Document.blocks
* Purely additive — never reads or alters reading order, columns, tables, or equations
* Foundation for downstream features (footnote detection, reading-order validation) that need this data without recomputing it

Output:

Document.blocks (List[TextBlock])

---

### Footnote / Endnote Detection

Location:

src/footnotes/

Responsibilities:

* Detect inline footnote/endnote markers and their note bodies
* Link marker to body by number, scoped per-page (footnotes) or document-wide (endnotes, via a "Notes"/"Endnotes" section heading)
* Populate Document.footnotes for downstream Markdown/DOCX rendering

Output:

Footnote Models

---

### Heading Detection

Location:

src/headings/

Responsibilities:

* Detect H1-H6 hierarchy
* Validate heading sequence

Output:

Heading Models

---

### Image Extraction

Location:

src/images/

Responsibilities:

* Extract images
* Filter background/decorative/duplicate images, keeping only meaningful figures
* Extract figures and link nearby captions
* Generate a deterministic placeholder alt-text string per retained image
* Store image metadata, including bounding box

Output:

Image Models

---

### Markdown Generation

Location:

src/markdown/

Responsibilities:

* Generate canonical markdown
* Preserve page structure
* Preserve heading hierarchy

Output:

Markdown Files

---

### Validation

Location:

src/validation/

Responsibilities:

* Structure validation
* Heading validation
* OCR issue detection
* Missing content detection

Output:

Validation Reports

---

### DOCX Generation

Location:

src/docx/

Responsibilities:

* Convert markdown to DOCX
* Apply heading hierarchy
* Insert page markers
* Insert page breaks
* Wire image alt-text into docPr attributes
* Preserve footnote/endnote marker-to-body relationships via bookmark/hyperlink (not native Word footnote fields)
* Format content

Output:

Accessible DOCX

---

## Shared Models

All modules must use models from:

src/models/

No module should create its own data structures.

---

## Processing Flow

PDF
↓
Document Model
↓
Page Models
↓
Heading Models
↓
Image Models
↓
Markdown
↓
Validation
↓
DOCX

---

## Architectural Constraints

* Local-first
* No cloud dependencies
* No databases
* No microservices
* No containers required
* No AI agents in Phase 1

All processing should remain modular and testable.
