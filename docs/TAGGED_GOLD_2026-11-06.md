# Gold answers without a reviewer: PDFs people already made accessible (2026-11-06)

**Idea:** a PDF that passes PDF/UA-1 carries people's decisions in its tags (headings and levels, alt text, table headers). Read them, strip the tags, run RAWRS on the bare file, compare. No reviewer needed. Code: `src/benchmark/tagged_gold.py`, `scripts/tagged_gold_bench.py`.

| Source | Why it is worth it | Kept |
|---|---|---|
| PDF/UA Reference Suite 1.1 (PDF Association, CC-BY 4.0), via the opendataloader-pdf repo (Apache-2.0); pdfa.org itself refuses scripts (403) | Tagged by the PDF/UA committee as best-practice examples; every file re-checked with veraPDF here | 6 of 9 |

Vetting (`worth_it`): must pass veraPDF PDF/UA-1, have ≥ 3 tagged headings, and no filler alt text ("logo", "image1.png", < 3 words). Rejected: Invoice and Form (1 heading each), Danish magazine (13 filler alts).

## Headings (6 files, 487 gold headings; RAWRS DOCX output, page markers excluded)

| File | Gold | RAWRS | Recall | Precision | Step agreement |
|---|---|---|---|---|---|
| Academic abstract | 7 | 9 | 100% | 78% | 50% |
| Presentation | 8 | 11 | 50% | 36% | 100% |
| Book chapter (German) | 47 | 69 | 89% | 61% | 68% |
| Brochure | 11 | 11 | 82% | 82% | 100% |
| Book chapter | 55 | 150 | 89% | 33% | 67% |
| Scanned textbook | 359 | 167 | 45% | 97% | 32% |
| **Pooled** | **487** | **417** | **56%** | **65%** | **47% (267 steps)** |

- Text match ignores spacing and punctuation ("C H A P T E R 5" = "Chapter 5").
- **Exact level is not a fair measure:** the reference files make every top-level section H1; RAWRS uses one H1 for the title and sections below it. Both are valid. Exact-level agreement is 42%. *Step agreement* asks whether each next heading goes deeper, stays or comes back up as the person tagged it. RAWRS never skips a level (0 skips in all 6 DOCX).
- Main defects: (1) **too many headings on figure-heavy pages**: chart labels ("Age in years", "Height gain, cm/yr") become headings, so precision on the book chapter is 33%; (2) **flat hierarchy on deep documents**: the textbook uses H3–H5 (Example, Solution), RAWRS puts almost everything at H3.

## Alt text: detailed prompt, `qwen2.5vl:7b` (user: "a blind person should clearly see the image")

Prompt change: the description was capped at "one or two sentences"; it now asks for the main subject, layout, connections, people, meaningful colours, every piece of text word for word, every chart value, and no guessing. Quality warning raised from 150 to 300 words. Gold: the 10 human-written alt texts in the benchmark remediated DOCX (median 73 words); the reference suite's alt texts were too short (4.5-7 words) to judge detail.

| Run (7b, same 10 figures, content-word overlap with the human text) | Recall | Precision | Median words | Usable answers | Median time |
|---|---|---|---|---|---|
| Old prompt (licence audit, 2026-11-04) | 48.1% | 55.3% | not kept | 10/10 | 209 s |
| **Detailed prompt** | **53.7%** | 40.5% | **94** (human 73) | 10/10 (9 before the parser fix) | 238 s |

- More of what the person wrote is covered, and descriptions are longer than the human ones. Precision falls because the model adds visual detail people left out (colours, icons, layout); word overlap cannot tell true extra detail from invented detail.
- Read by hand: the flowchart description lists all six steps and their order; the research-cycle diagram names the book, gears and light bulb, but its arrow directions differ from the person's account (not checked against the image).
- Parser fix: one detailed answer skipped PURPOSE and wrapped VISIBLE_TEXT over several lines, so it was rejected and the image would have kept no alt text. Only IMAGE_TYPE and DESCRIPTION are now required; wrapped lines are joined (test added).
- Default model is now `qwen2.5vl:7b` (Apache-2.0); 3b is non-commercial. 7b needs about 6 GB more memory than 3b; not tried on an 8 GB machine.
- Not done: the reference-suite alt run (old vs new prompt) was stopped because its gold is too brief to measure detail.

## Bug found and fixed
| Bug | Fix |
|---|---|
| JPEG 2000 images (`.jpx`) could not be read by Pillow: no alt text, and missing from the DOCX | `image_extractor` stores them as PNG through MuPDF; test `test_jpeg2000_images_are_stored_as_png` |

## Limits
- 6 files, mostly short and from one source; the scanned file keeps its OCR text layer after stripping, so it does not test RAWRS's OCR.
- Alt-text gold in the scanned file is caption-like ("Figure 1 Graph of sin x."), so it is not used for alt text.
