# Heading Rules

> Implementation status and code citations: `PHASE_STATUS.md` (Phase B — currently PARTIALLY IMPLEMENTED: detection and Navigation Pane support are solid; font-color/size are output-formatting only, not detection checks — see the Detection Heuristics section below).

## Purpose

Heading hierarchy is one of the most important accessibility and navigation requirements in remediation.

RAWRS must preserve and reconstruct document hierarchy while maintaining logical reading order.

---

## Standard Hierarchy

### H1

Represents:

* Book Title
* Document Title
* Primary Document Heading

Rules:

* Only one H1 should typically exist.
* Must represent the highest level heading.

---

### H2

Represents:

* Unit
* Chapter
* Major Section

Examples:

Unit 1

Chapter 3

Introduction

---

### H3

Represents:

* Section

Examples:

3.1 Overview

4.2 Teaching Strategies

---

### H4

Represents:

* Subsection

Examples:

3.1.1 Learning Objectives

---

### H5

Represents:

* Lower-Level Subsection

Used only when required.

---

### H6

Reserved for:

PDF Page Markers

Examples:

###### 1

###### 2

###### 3

RAWRS must automatically generate page markers for every PDF page.

---

## Hierarchy Rules

Allowed:

H1 → H2

H2 → H3

H3 → H4

H4 → H5

H5 → H6

---

Not Allowed:

H1 → H3

H2 → H4

H3 → H5

Skipping levels should trigger validation warnings.

---

## Detection Heuristics (added after benchmark reconciliation — see DECISIONS_LOG.md C5/C6)

Real-world headings are frequently short, Title-Case, **unnumbered** phrases with no `Unit N`/`Chapter N`/`X.Y` pattern at all. Numbering/keyword patterns alone catch effectively none of these. Detection therefore uses, in order:

1. **Layout signal (primary):** rank the distinct heading font sizes found *within that document* — largest unique size → H1, next → H2, and so on — combined with a bold-relative-to-body-text check and line isolation (a heading candidate is a short, standalone line, not embedded in a longer paragraph). This is a relative, per-document signal, not a fixed point-size threshold.
2. **Numbering/keyword pattern (secondary/override):** `Unit N`, `Chapter N`, `X.Y` numbering still fires when present and can override the layout signal.
3. **Fixed keyword exception:** References, Bibliography, Appendix, and Acknowledgements always promote to H2 regardless of the layout signal, since these sections don't reliably get distinct formatting in source documents.

**Important distinction:** the heuristics above are what *detects* a heading in the source PDF. They do not inspect font *color*, and they use font size only in relative rank order. The Formatting Rules below (Times New Roman, exact pt sizes, black) describe what RAWRS *writes* into the generated DOCX — they are applied unconditionally to every detected heading regardless of how it was styled in the source, not used as a detection filter. See `PHASE_STATUS.md` (Phase B) for the gap this distinction closes: a heading detected from a non-black or unusually-sized source span is still detected and then reformatted, not rejected.

## Formatting Rules (applied to generated DOCX output, not used to detect headings)

H1

* Times New Roman
* 16 pt
* Bold
* Black

H2

* Times New Roman
* 14 pt
* Bold
* Black

H3-H6

* Times New Roman
* 12 pt
* Bold
* Black

---

## Navigation Requirements

Headings must:

* Appear in Word Navigation Pane
* Preserve hierarchy
* Support keyboard navigation
* Support screen readers

---

## Validation Checks

RAWRS must detect:

* Missing H1
* Invalid hierarchy jumps
* Duplicate hierarchy issues
* Empty headings
* Heading level skips

Validation should generate warnings rather than silently correcting structure.
