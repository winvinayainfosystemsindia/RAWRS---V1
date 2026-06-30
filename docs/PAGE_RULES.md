# Page Rules

## Purpose

Page preservation is a mandatory remediation requirement.

The remediated output must maintain a clear mapping between PDF pages and generated content.

---

## Page Marker Requirement

H6 page markers map DOCX content back to source PDF pages. The marker text is only the numeric or roman-numeral value — the word "Page" must never appear in a generated marker. Each marker renders as Heading 6 in the output DOCX.

Example:

###### 367

NOT `###### Page 367`. NOT `###### Page 12`.

---

## Page Numbering Policy (Configurable)

The default behavior and all four configurable modes are implemented in `src/config/page_numbering.py` (`PageNumberingPolicy`) and threaded through `detect_headings()`, `build_markdown()`, and `run_pipeline()`.

### Mode 1 — Automatic (Default when a policy is explicitly provided)

Detect the printed page number from each page's margin text (`Page.printed_label`, populated by `structure_detector.py`). Emit a marker only for pages where a confident printed label was detected. Pages with no detected printed number receive no marker — synthetic numbering is never substituted.

### Mode 2 — Manual Range

The remediator specifies an inclusive physical-page range `[range_start, range_end]`. Only pages within that range receive markers. Pages outside the range receive none. Marker text is the detected printed label when available, otherwise the physical page number.

### Mode 3 — Manual Number Override

The remediator specifies a `number_start` value. Every page receives a marker numbered sequentially from that value: page 1 → `number_start`, page 2 → `number_start + 1`, and so on. Useful for scanned extracts that begin mid-book.

### Mode 4 — Disabled

No page markers are generated.

---

## Legacy Behavior (no policy passed)

When `page_numbering_policy=None` (the default for `run_pipeline()`, `detect_headings()`, and `build_markdown()`), the original behavior is preserved for backward compatibility: every page receives a marker whose text is the detected printed label (`Page.printed_label`) when available, or the physical page number (`str(Page.page_number)`) otherwise. This is identical to the behavior before the configurable policy was introduced.

---

## Page Break Requirement

At the end of every PDF page:

Insert:

Word Page Break

This preserves page alignment between:

Original PDF

and

Generated DOCX

---

## Page Preservation Rules

RAWRS must:

* Preserve all pages
* Preserve page sequence
* Preserve page boundaries

RAWRS must not:

* Merge pages
* Remove pages
* Reorder pages

---

## Header and Footer Handling

Repeated headers should be removed.

Examples:

* Running chapter titles
* Repeated book titles
* Download notices

Repeated footers should be removed.

Examples:

* Website references
* Repeated copyright notices
* Repeated footer artifacts

Page numbers themselves should be preserved.

---

## Footnotes

Footnotes are common in remediation workflows.

Phase 1 Responsibilities:

* Detect footnotes
* Preserve footnote references
* Record footnote locations

Phase 1 will not automatically remediate footnotes.

Human review may still be required.

---

## Endnotes

Endnotes should be detected and preserved.

Phase 1 will not automatically reconstruct endnote systems.

---

## Reading Order Rules

RAWRS must preserve:

* Paragraph sequence
* Heading sequence
* Figure placement
* Caption placement

Reading order violations should be reported by validation.

---

## Validation Checks

RAWRS must detect:

* Missing page markers
* Missing page breaks
* Duplicate page markers
* Page ordering issues
* Header/footer extraction failures

Validation should report these issues for human review.

**Caveat — `PAGE_001` and configurable policy:** `PAGE_001` fires when a page has no H6 marker. Under `AUTO` or `DISABLED` policy, suppressed pages are intentionally markerless, so `PAGE_001` will fire as a false positive for those pages. This is a known gap; `PAGE_001` does not yet receive the active policy and cannot distinguish intentional suppression from an accidental omission. See `KNOWN_LIMITATIONS.md`.
