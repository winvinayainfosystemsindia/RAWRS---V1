# Validation Rules

> This document describes validation *categories and intent*. For the full list of rule IDs that actually exist in code today (with file:line citations), see `PHASE_STATUS.md`. 29 rules are currently implemented. Remaining gaps: broken-word detection and "Figure Validation" (missing captions, unlinked references, missing numbering) still have no rule IDs. See `KNOWN_LIMITATIONS.md`.

## Purpose

Validation is the core safety mechanism of RAWRS.

RAWRS follows the principle:

AI Proposes

Validation Decides

No output should be considered trustworthy until validation has completed.

---

## Validation Categories

### Structure Validation

Checks:

* Missing content
* Empty pages
* Missing headings
* Missing page markers
* Missing page breaks

---

### Heading Validation

Checks:

* Missing H1
* Invalid hierarchy jumps
* Duplicate headings
* Empty headings
* Skipped heading levels

Examples:

Invalid:

H1
→ H3

Invalid:

H2
→ H4

Valid:

H1
→ H2
→ H3
→ H4

---

### OCR Validation

Checks:

* Low confidence regions
* Broken words
* Excessive OCR artifacts
* Reading order anomalies

Examples:

Broken:

educa-
tion

Incorrect:

Iearning

instead of

learning

---

### Image Validation

Checks:

* Extraction failures
* Missing image files
* Duplicate extractions
* Missing figure references

---

### Figure Validation

Checks:

* Missing captions
* Unlinked figure references
* Missing figure numbering

Examples:

Figure 1

Figure 2

Figure 3

---

### Page Validation

Checks:

* Missing pages
* Duplicate pages
* Page order violations
* Missing page markers
* Missing page breaks

---

## Severity Levels

### Error

Critical issue.

Processing quality is compromised.

Examples:

* Missing page
* Corrupted extraction
* Failed markdown generation

---

### Warning

Potential issue.

Human review recommended.

Examples:

* Heading hierarchy issue
* OCR confidence low
* Caption ambiguity

---

### Info

Non-critical observation.

Examples:

* Footnote detected
* Endnote detected
* Large image detected

---

## Implemented Rule IDs (current, see PHASE_STATUS.md for citations)

| Rule ID | Severity | Checks |
|---|---|---|
| DOC_001 | WARNING | Document has pages but no extracted text, headings, or images |
| DOC_002 | WARNING/INFO | Metadata stale (page/image count mismatch) or missing processing date |
| DOC_003 | ERROR | Document has zero pages |
| DOC_004 | WARNING | XML-invalid character(s) found and removed from extracted text before export (XML Sanitization Architecture, Layer 2 - see below and docs/DECISIONS_LOG.md) |
| HEADING_001 | WARNING | Heading hierarchy jump (level increase >1) |
| HEADING_002 | WARNING | No H1 detected |
| HEADING_003 | WARNING | Empty/blank heading |
| HEADING_004 | WARNING | Duplicate (level, text) heading pair |
| PAGE_001 | ERROR | Page missing its H6 page marker |
| PAGE_002 | ERROR/WARNING | Duplicate page number, sequence gap, or out-of-order pages |
| PAGE_003 | WARNING | Reading-order anomaly (backward jump or block overlap) |
| IMAGE_001 | ERROR | Image reports success but file is missing |
| IMAGE_002 | ERROR | Image extraction failed |
| IMAGE_003 | ERROR | Duplicate image_id |
| IMAGE_004 | INFO | Alt text pending human review |
| IMAGE_005 | WARNING | Image successfully extracted but failed to embed into DOCX (CMYK JPEG or similar; added FEATURE_016E) |
| OCR_001 | WARNING | Page OCR confidence is LOW (Surya fallback recovery) |
| OCR_002 | WARNING | OCR-recovered text exceeds the unusable-character ratio threshold |
| NOTE_001 | INFO | Footnote detected |
| NOTE_002 | INFO | Endnote detected |
| TABLE_001 | WARNING | Table has no caption |
| TABLE_002 | WARNING | Table has no summary (WCAG H73) |
| TABLE_003 | WARNING | Table has no header row |
| TABLE_004 | WARNING | Table has empty header cell(s) |
| TABLE_005 | INFO | Auto-detected table has low confidence (<0.7) |
| TABLE_006 | WARNING | Table has merged cells (lost in Markdown; preserved in DOCX) |
| TABLE_007 | WARNING | Borderless-detected table has only one inferred column — column structure may need reviewer verification |
| HEADING_005 | WARNING | Multiple H1 headings detected (well-structured documents should have exactly one) |
| META_001 | INFO | No document language set (WCAG 3.1.1 — language must be programmatically determinable) |
| META_002 | INFO | No document title set (WCAG 2.4.2 — documents must have descriptive titles) |

Not yet implemented as discrete rules: broken-word detection, missing figure captions, unlinked figure references, missing figure numbering.

### DOC_004 severity: why WARNING, not ERROR

A production PDF crashed DOCX generation with an XML-compatibility error from an extracted character that cannot be represented in OOXML. The fix (XML Sanitization Architecture, see docs/DECISIONS_LOG.md) removes any such character at the point text first enters the Document model (Layer 1), before DOC_004 ever runs. This makes DOC_004 structurally different from every other rule in this table: **by the time it can possibly fire, the defect is already handled and the document has already generated successfully.**

Per this document's own Severity Levels (above): Error means "processing quality is compromised." That is false every time DOC_004 runs, by construction - nothing is missing, corrupted, or failed. What remains true matches Warning's own definition exactly: a potential issue (confirm the removed character's surrounding context still reads as intended) recommended for human review - not a confirmed defect, and not a processing failure. DOC_004 is therefore a **disclosure of an already-handled defect**, not a predictive "this will break something" signal - see docs/DECISIONS_LOG.md for the full architecture review this was explicitly re-derived from (an earlier draft of this rule was provisionally scoped as Error before Layer 1 existed; that recommendation no longer applies once sanitization is unconditional).

## Validation Output

Each validation issue must contain:

* Severity
* Rule ID
* Description
* Page Number
* Suggested Action

Example:

{
"severity": "warning",
"rule": "HEADING_001",
"page": 12,
"message": "Heading hierarchy jump detected"
}

---

## Design Principles

Validation must:

* Be auditable
* Be explainable
* Be reviewable

Validation must never:

* Silently modify content
* Hide uncertainty
* Auto-correct without traceability

---

## Success Condition

RAWRS is considered successful when validation identifies issues before human review rather than after delivery.
