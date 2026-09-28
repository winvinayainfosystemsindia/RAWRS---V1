# Checklist Compliance

Every item of `Checklist for Document Remediation1.docx` and `ChecklistBeforeSubmittingDoc.xlsx`, how RAWRS meets it, and the audit check that verifies it. The audit (`src/validation/checklist_audit.py`) runs after every pipeline run (`reports/<stem>.checklist.json`), on demand at `GET /api/documents/{id}/checklist` (against the current export), in the workspace's Readiness and Overview panels, and from the CLI: `python -m src.validation.checklist_audit file.docx [source.pdf]`.

Statuses: **pass**, **fail**, **warn** (look at it), **manual** (needs a person in Word), **n/a**.

## Checklist for Document Remediation

| # | Item | How RAWRS does it | Check |
|---|---|---|---|
| 1 | Paragraph marks on | Word UI setting, not document content | — |
| 2 | Times New Roman 12 pt | Every style (theme fonts removed) and run | DR-02 |
| 3 | Content matches the PDF | Text from the PDF layer / OCR; audit compares word sets (≥95%) | DR-03 |
| 3 | Bold / italics match | Emphasis carried from PDF fonts (016G) | DR-03B manual |
| 4 | Screenshots of images | Extracted at source resolution; printed at the PDF's size and shape (Mathpix crop box or PDF bbox) | — |
| 5 | Images centred, inline; captions centred, Insert-Caption style | Always centred inline; captions in Word's `Caption` style | DR-05 |
| 6 | Page number at top left | Heading 6 opens every page | DR-06, SUB-PGNUM |
| 7 | Page break after each PDF page | One break per page | DR-07 |
| 8 | No extra spaces or sentence breaks | Spacing normalised; paragraphs split mid-sentence re-joined | DR-08 |
| 9 | Bullets and numbering as in the PDF | Word list styles; lone bullet glyphs become list items; Docling list items on scans | DR-09, SUB-LIST |
| 10 | Tables rebuilt, no merged cells | Spanning cells repeat their words; prose "tables" rejected | DR-10 |
| 11 | Abbreviations for screen readers (US → U S, UNESCO kept) | Letter-by-letter initialisms spaced; pronounceable acronyms kept | DR-11 |
| 12 | No sentence cut at a page end | First sentence of the next page moves up (past a trailing "Source:" line) | DR-12 |
| Eq 1–7 | Equation rules | No equations in the corpus; any found are flagged | DR-EQ |
| Headings | Levels in order; TNR black bold 16/14/12; H6 = page no.; `6.1 - INTRODUCTION` | Styles fixed; levels re-ranked without gaps; numbered headings hyphenated; title = H1 | DR-HD-FMT, DR-HD-ORDER, DR-HD-HYPHEN |
| Punctuation | Comma, bracket, hyphen spacing | Applied to all text outside URLs; ligatures and mis-mapped "=" repaired | DR-PUNCT |
| Final | Space before kg / units | Multi-letter units spaced | DR-UNITS |
| Final | Alt text for all images, no symbols | Automatic: decorative detection + local vision model; symbols stripped | DR-ALT |
| Final | Word Accessibility Checker | Automated equivalent = every check above | SUB-A11Y |

## Checklist before submitting

| Section | How RAWRS does it | Check |
|---|---|---|
| Language | `w:lang` + core property from metadata, the PDF's `/Lang`, else en-US | SUB-LANG, SUB-META-LANG |
| Page size, margins, orientation | Letter, 1" margins, portrait | SUB-PAGE |
| Blank pages | Reported, never deleted (a blank PDF page stays a page) | SUB-BLANK warn |
| No text boxes | Body text only | SUB-TEXTBOX |
| Heading styles, no manual formatting | Built-in Heading styles; bold one-liners flagged | SUB-HD-ORDER, SUB-STYLES, SUB-HD-STYLES |
| Tables: header row, captions/summaries | First row repeats when none is marked; factual summary when none exists | SUB-TBL-HDR, SUB-TBL-CAP |
| Images: alt text, decorative marked | Word's "Mark as decorative" flag | SUB-IMG |
| Hyperlinks | Every printed web address is a live link (display text kept as printed) | SUB-LINK, SUB-LINK-TEXT warn |
| Footnotes / endnotes | Native Word parts, linked both ways | SUB-NOTES |
| Table of Contents | Not generated (user decision 2026-09-28: no index-like headings); add in Word if a TOC is required | SUB-TOC manual |
| Title / Author / Subject | Reviewer value → front matter → PDF properties → first heading; author never invented | SUB-META |
| No personal/tool info | python-docx author/comment cleared | SUB-META-PRIV |
| Keyboard navigation, PDF export | Needs Word | SUB-KEYBOARD, SUB-PDF manual |

## Scanned PDFs and images

| Step | How |
|---|---|
| Text | Docling OCR, Surya fallback (`enable_ocr=True`) |
| Headings | Docling's layout model labels title/section headers → `Page.ocr_heading_levels` → Heading N |
| Lists | Docling list items keep Word list styles |
| Alt text | Decorative: no edges, repeats on 2+ pages, or < 50 px a side. Others: `qwen2.5vl:3b` via local Ollama (`RAWRS_OLLAMA_URL`, `RAWRS_OLLAMA_MODEL`); charts/graphs/tables get a "This means…" statistics explanation; status `AI_GENERATED`, still reviewable |
| Page placement | OCR text per page aligns Mathpix blocks to pages (was: all piled on the last page) |
| Heading outline | `src/headings/hierarchy.py`: quotes/attributions demoted to text, list glyphs stripped, lone chapter number merged ("3 - Title"), flat outlines inferred H1/H2/H3 |
| Evidence | O'Leary scan: 28 pass / 0 fail; 98.9 % of OCR words present |

## Human edits

| Step | How |
|---|---|
| Edit | Workspace Markdown pane; `PUT /api/documents/{id}/markdown` saves to `outputs/edits/<job>.json` |
| Preview | `POST /api/documents/{id}/docx-preview` renders the draft; shown live (700 ms debounce) |
| Export | Downloads serve the edited DOCX; `DELETE …/markdown` discards the edit |

## Open by design

| Item | Why it stays with a person |
|---|---|
| Author when no source states one | Inventing an author is worse than a blank |
| Punctuation rule 4 ("after an open bracket add a space") | Contradicts standard typography; not applied — confirm the house style |
| Hyperlink display text | Kept as printed so the text matches the PDF |
