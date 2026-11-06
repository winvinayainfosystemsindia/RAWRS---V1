# Task 3: accessible PDF export (2026-11-06)

**Result:** all 10 benchmark documents export to tagged PDF and pass veraPDF PDF/UA-1. LibreOffice was enough, so no other exporter is needed.

| Setup | |
|---|---|
| Export | LibreOffice 25.2.3 headless, `UseTaggedPDF` + `PDFUACompliance`. The tags come from the DOCX styles; no PDF tags are written by hand (`src/docx/pdf_export.py`) |
| Validator | veraPDF 1.30.3, `--flavour ua1` (independent of RAWRS) |
| Text check | pypdfium2 characters per page; a page under 20 characters counts as "no text" |
| Run | Codespace, `scripts/run_corpus_metrics.py` at production settings (OCR on, cache off, Ollama `qwen2.5vl:3b` + `glm-ocr:q8_0`), HEAD `ad147b4` + this change |
| Table | `python scripts/pdfua_report.py outputs/corpus_pdfua` (each veraPDF rule mapped to a checklist check) |

## Pass/fail by check

| Document | PDF/UA-1 | chars | pages | <20-char pages | table headers | alt text | reading order | language | title | equations |
|---|---|---|---|---|---|---|---|---|---|---|
| Nature of Enquiry | PASS | 140870 | 58 | 0 | pass | pass | pass | pass | pass | pass |
| Aims of Education | PASS | 14093 | 7 | 0 | pass | pass | pass | pass | pass | pass |
| Bryman (scan) | PASS | 105736 | 53 | 2 | pass | pass | pass | pass | pass | pass |
| Bruner | PASS | 55915 | 26 | 0 | pass | pass | pass | pass | pass | pass |
| Sockett | PASS | 48662 | 23 | 2 | pass | pass | pass | pass | pass | pass |
| O'Leary (scan) | PASS | 30777 | 24 | 2 | pass | pass | pass | pass | pass | pass |
| Teaching as a profession, Ch. 1 | PASS | 73703 | 34 | 5 | pass | pass | pass | pass | pass | pass |
| Calderhead | PASS | 11075 | 6 | 1 | pass | pass | pass | pass | pass | pass |
| Fullan & Hargreaves | PASS | 14551 | 9 | 1 | pass | pass | pass | pass | pass | pass |
| Brinkman | PASS | 60890 | 38 | 0 | pass | pass | pass | pass | pass | pass |

There are no failures, so no failure reasons to report. The under-20-character pages were not opened one by one; they are likely blank, figure-only or chapter-opening pages. In `python -m src.metrics`, the independent check reads 10/10 pass with 0 documents having no text, and it is kept apart from the self-graded checklist (79.1% median).

## Fixes needed to reach 10/10

| veraPDF rule | Cause | Fix |
|---|---|---|
| 7.4.2 (first heading must be H1) | Heading 6 is RAWRS's printed-page marker | The PDF copy restyles it as a plain "Page Number" paragraph; the DOCX keeps Heading 6 |
| 7.18.1 / 7.18.5 (link description) | Links had no ScreenTip | `docx_generator` writes one, and the PDF copy fills it in for older DOCX files (the demo DOCX failed with 4 links until then) |
| 7.9, 7.18.3, 7.3 | LibreOffice 7.4 (Debian package) | Requires LibreOffice ≥ 25.2 |

## What PDF/UA-1 does not catch (measured)

| Case | veraPDF | RAWRS checklist | Text check |
|---|---|---|---|
| OCR failed on every page of the 13-page O'Leary scan (HF cache missing, run 1) | **PASS** | 24 pass, 2 fail (neither about text) | 17 characters in the whole PDF; page markers hid it until the 20-character rule |

A total OCR failure still ends as a "successful" job. Only the text check flags it.

## Not tested
- The PDFs were not read with a screen reader (NVDA or JAWS), and veraPDF does not judge whether the reading order makes sense.
- Equations: none of the 10 documents has an equation object, so the equations column is vacuous.
- The download route and the checklist panel line were not clicked through in a live app.
- Matterhorn checks that need a human (about half the protocol) were not covered.

## Next step
Task 4 (crawler + free audit report), using the same veraPDF and text checks on third-party PDFs.
