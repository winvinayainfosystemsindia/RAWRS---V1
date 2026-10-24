# Scanned-page structure

Added 2026-10-24. Five structural defects on scanned PDFs, fixed in `src/ocr/scan_structure.py` (runs on Docling pages only, native path), `src/images/image_extractor.py`, `src/markdown/markdown_builder.py`, `src/docx/docx_generator.py`. Docling's layout (labels, bboxes, page furniture, text inside pictures) is kept per page as `Page.ocr_layout`.

## What runs now

| Defect | Fix | Where |
|---|---|---|
| Page numbers were PDF indices | Folios from Docling's page header/footer; the offset most pages agree on labels every page. Printed and matching → confidence 1.0; inferred → 0.5; a folio that contradicts the offset (O'Leary p12 read "63") takes the sequence and raises PAGE_007/008 | `_apply_printed_labels` |
| Chapter number dropped | A number item at or above the title's top, first on the page, joins the title ("2 - Social research strategies"). A small picture there is read by RapidOCR (Bryman's pale "2") | `_merge_chapter_number` |
| Heading levels flattened | Each heading's printed size (ascender-to-baseline height at 200 DPI) is measured. The first size gap ≥1.2× with ≥2 headings each side splits H2 from H3; a lone larger first-page heading is H1. No gap → `hierarchy.py` capitals rule as before | `_tier_heading_levels`, `split_tiers` |
| Boxes not boxed | Tinted panels at 72 DPI (strokes erased, faded gradient edges followed). Items inside that map to contiguous page lines become a `Callout` with page and line range; first-line heading is the title, other in-box headings become text. Markdown fences `<!-- box-start/end -->`; DOCX sets a one-cell table with the title as a heading inside (as the remediated gold does) | `_detect_boxes`, `_wrap_in_box` |
| Decorative clutter, figures lost | On Docling pages, figures are Docling picture crops (150–300 DPI), not the scan's embedded image objects. Skipped: < 72 pt a side, ≥85% of the page, >50% covered by a table. Caption from the text Docling found inside the picture, else the nearest caption item within 36 pt. Placed before the next layout item | `_extract_layout_pictures`, `_layout_image_anchors` |

The checklist audit opens one-cell tables (`_body_blocks(open_boxes=True)`), so a box's heading and prose are audited as body content and not as a data table.

## Evidence (Codespace, full pipeline, vs the human-remediated DOCX)

| Measure | `main` (`bf6901e`) | This change |
|---|---|---|
| Bryman heading levels matching gold | 17 / 44 | **43 / 44** |
| Bryman page labels | 1–26 (PDF index) | **18–43** (p1 inferred) |
| Bryman boxes | 0 | **20** (gold 20; all 20 checked against the printed panels) |
| Bryman images | 112 | **3** (gold 3) |
| Bryman gold paragraphs lost | 4 / 146 | 1 / 146 (the gold's own cover note) |
| Bryman 4-gram recall / precision | 96.1% / 87.9% | **96.7% / 96.2%** |
| O'Leary heading levels matching gold | 22 / 26 | **24 / 26** |
| O'Leary page labels | 1–13 | **28–40**, p12 flagged |
| O'Leary boxes | 0 | **3** (Box 3.1 + its continuation, Box 3.2) |
| O'Leary figures | 4 icon fragments from p6; Figures 3.1–3.4 missing | **4 figures with captions** |
| O'Leary 4-gram recall / precision (alt text excluded) | 98.5% / 98.1% | 98.5% / 97.5% (the 4 added captions are not in the gold's text) |
| Checklist audit | — | O'Leary 28 pass / 0 fail; Bryman 28 pass / 3 fail (DR-08 a quotation split inside Box 2.7, SUB-LINK a URL set as a heading, SUB-META no author) plus their SUB-A11Y roll-up, all present on `main` too |
| Born-digital corpus Markdown (8 PDFs) | — | 7 byte-identical (after path normalising); Squires' scanned page 1 now gives the cover image and title as text, as the gold does (was cover + title-page image) |
| Tests | — | `tests/test_scan_structure.py`, 42 |

## Still open

| Gap | Effect |
|---|---|
| Heading text style | Chapter title format follows RAWRS's "N - Title"; gold varies ("2 Social research strategies", "Chapter 3: …") |
| Bryman "Chapter guide" | H2 (gold H1) |
| O'Leary "Chapter Preview" | H3 (gold H2): one printed size, so the capitals rule decides |
| Boxes with a border but no tint | Not detected |
| Mathpix-route callouts | Still unrendered (no line range) |
