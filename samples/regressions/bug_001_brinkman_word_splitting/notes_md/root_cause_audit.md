# bug_001_brinkman_word_splitting — Root Cause Audit

Audit only. No source files modified, no fixes implemented.

## Root Cause Summary

This is **two independent, compounding bugs**, not one:

**Bug 1 (extraction-level, the dramatic word-per-line splitting):** PyMuPDF's own text-layout reconstruction (`page.get_text()` / `page.get_text("dict")`) mis-segments one fully-justified visual line on page 1 into 8 separate "line" objects — one per word/short-phrase. This happens *before any RAWRS code runs*; RAWRS inherits it verbatim. It is specific to lines where inter-word gaps are encoded as absolute text-positioning jumps rather than literal space-character glyphs (see Evidence) — a known PyMuPDF limitation on justified text from certain PDF producers, not a bug in RAWRS's own logic.

**Bug 2 (rendering-level, pervasive across the entire document):** `markdown_builder.py::_render_page_body()` never reconstructs paragraphs. It runs `page.cleaned_text.splitlines()` and appends **every single line as its own independent markdown paragraph block**, with no logic anywhere to merge PDF line-wraps back into continuous prose. This is why *every* paragraph in the whole document — title, abstract, introduction, body alike — renders as one-PDF-line-per-markdown-paragraph instead of flowing text, matching `expected_md`'s fully-joined paragraphs.

Bug 2 alone would still produce multi-word paragraphs for ~95% of the document (most real PDF lines contain multiple words) — it's "wrong but mild" on its own. Bug 1 alone would only corrupt this one sentence. **Together**, Bug 1 feeds Bug 2 already-fragmented single-word "lines," which Bug 2 then dutifully renders as 8 separate one-word paragraphs — producing the dramatic vertically-stacked-word symptom reported.

## Answers to the Audit Questions

1. **Does the corruption already exist immediately after PDF extraction?** Yes, for Bug 1 — confirmed via raw PyMuPDF `get_text("dict")` dump (see Evidence), independent of any RAWRS code.
2. **Does it appear during block construction?** No new corruption introduced — `structure_detector.py` independently re-derives from `page.get_text("dict")` and reproduces the identical 8-way split (same bboxes, consecutive `order` values), confirming it's inherited, not introduced there.
3. **Does it appear during layout analysis (`layout_signals.py`)?** No — `line_layout()` only aggregates spans *within* whatever line PyMuPDF already segmented; it has no opportunity to merge or split lines itself.
4. **Does it appear during heading detection?** No — this paragraph contains no heading candidates; `heading_detector.py` reads `Page.cleaned_text`/layout signals to *find* headings but never rewrites body text, and `markdown_builder.py` only substitutes a line when it exact-matches a detected heading's text. Confirmed irrelevant by inspection of `heading_detector.py`'s module docstring and matching logic.
5. **Does it appear during markdown rendering?** Yes — Bug 2 lives entirely here. `_render_page_body()` (`markdown_builder.py:218-244`) has zero paragraph-joining logic.
6. **Is this a single bug or multiple independent bugs?** Two independent bugs (see Root Cause Summary).
7. **Cause category:**
   - Bug 1: **line grouping** (PyMuPDF's own line-clustering heuristic, upstream of RAWRS).
   - Bug 2: **markdown rendering** (missing paragraph-reconstruction logic).
   - Not implicated: block grouping (blocks aren't consumed by markdown at all today), reading-order reconstruction (this text's reading order is already correct — it's a segmentation problem, not an ordering one), multi-column interpretation (this PDF page is single-column at this point; no evidence of column-merge error), coordinate sorting (no sort step exists in this path — `structure_detector.py` preserves PyMuPDF's emission order verbatim, see its own docstring: "never validated, corrected, related across pages, or reordered here").
   - `image_extractor.py`: not relevant — no image in this region.

## Evidence

### Generated vs. expected divergence

`generated_md` lines 37-54:
```
beliefs of 60 elementary teachers in three Indian states are explored through written

questionnaires,

semi-structured

interviews,

and

open-ended

life-narratives,

while

their

pedagogy is analysed through classroom observations. ...
```

`expected_md` (same sentence, single paragraph, line 20):
```
...The beliefs of 60 elementary teachers in three Indian states are explored through written
questionnaires, semi-structured interviews, and open-ended life-narratives, while their pedagogy
is analysed through classroom observations. ...
```
(rendered as one continuous markdown line in the actual file)

Also confirms Bug 2's pervasiveness — *every* other paragraph in `generated_md` (title, abstract intro sentence, "Introduction" section body, etc.) is likewise split into one markdown block per PDF source line, never joined, throughout all 2037 lines vs. expected's 362.

### Bug 1 — raw PyMuPDF dict-mode dump, page 1, block 4

All 8 fragments share **identical y-coordinates** (y0=361.78, y1=371.74) — i.e., PyMuPDF itself knows they're on the same baseline — yet emits them as 8 separate `line` dict entries:

| order | text | bbox (x0, y0, x1, y1) |
|---|---|---|
| — | `beliefs of 60 elementary teachers in three Indian states are explored through written` | (42.5, 349.8, 433.6, 359.8) — **one normal line, for contrast** |
| 18 | `questionnaires,` | (42.52, 361.78, 103.18, 371.74) |
| 19 | `semi-structured` | (112.14, 361.78, 176.24, 371.74) |
| 20 | `interviews,` | (185.21, 361.78, 228.99, 371.74) |
| — | `and` (not individually dumped, sits at x≈237-255) | same y |
| 22 | `open-ended` | (261.29, 361.78, 309.42, 371.74) |
| 23 | `life-narratives,` | (318.44, 361.78, 375.24, 371.74) |
| — | `while` | (384.20, 361.78, 405.45, 371.74) |
| — | `their` | (414.48, 361.78, 433.65, 371.74) |

**Mechanism:** in the normal line above, inter-word gaps are real space-character spans (`text=' '`, width ≈6.8pt each — measured directly from span bboxes, e.g. 74.55-67.72=6.83). In the broken line, **no space-character span exists between fragments at all** — the gap (≈9.0pt, consistently, across all 5 measured boundaries) is achieved purely by absolute text-positioning, not a literal space glyph. PyMuPDF's line-clustering treats the absence of a bridging space glyph as a new-line signal even when y-coordinates are unchanged. This is a property of how this PDF's producer (`3B2 Total Publishing System` / `Adobe LiveCycle PDFG ES` per the file's own metadata) encoded justified-text spacing on this line — not something RAWRS's code does.

**Confirmed inherited, not introduced, by both consumers:** running `extract_text()` then `detect_structure()` against the real `Document` model reproduces the exact same 8-way split independently in both `Page.cleaned_text` (`\n`-joined, one fragment per line) and `Document.blocks` (8 consecutive `TextBlock`s, `order=18-23`, identical bboxes to the raw dump above) — proving structure_detector.py doesn't cause this, it just faithfully re-derives the same PyMuPDF artifact a second time via its own independent `get_text("dict")` call.

### Bug 2 — code inspection, `markdown_builder.py`

```python
# _render_page_body(), lines 218, 227-244
text = page.cleaned_text or page.raw_text
...
for raw_line in text.splitlines():
    line = raw_line.strip()
    if not line:
        continue
    ...
    blocks.append(line)   # <-- every line becomes its own block; nothing merges lines
```
And in `extractor.py::normalize_whitespace()`, the only text-shape transform applied before this point collapses 3+ blank lines to 1 — it does not join single-newline-separated lines either. No function anywhere in the traced modules (`extractor.py`, `structure_detector.py`, `layout_signals.py`, `heading_detector.py`, `image_extractor.py`) performs paragraph reconstruction. `markdown_builder.py` is the first and only place line-to-paragraph decisions are made, and it makes none.

## Exact Files / Functions

| Bug | File | Function |
|---|---|---|
| 1 | *(upstream of RAWRS — PyMuPDF itself)*; first RAWRS contact points: `src/ocr/extractor.py`, `src/structure/structure_detector.py` | `extract_text()` (calls `page.get_text()` with no post-processing); `_extract_page_blocks()` (calls `page.get_text("dict")`, same artifact) |
| 2 | `src/markdown/markdown_builder.py` | `_render_page_body()` |

## Confidence Level

- **Bug 1 (PyMuPDF line mis-segmentation): High.** Directly confirmed via raw bbox/span dumps showing identical y-coordinates and the absence of a bridging space glyph at exactly the fragment boundaries. Reproduced identically through both of RAWRS's two independent re-derivation paths.
- **Bug 2 (missing paragraph reconstruction): Very high.** Directly visible in source — no ambiguity, no inference required. Confirmed pervasive via the line-count divergence (2037 vs. 362 lines) across the entire document, not just the reported sentence.
- **Two-independent-bugs framing: High.** Bug 2 alone is observably present on lines that have no Bug-1-style fragmentation (e.g. "originating 'learner-centred' approaches..." still gets its own paragraph per PDF line, normally segmented by PyMuPDF) — proving Bug 2 exists independently of Bug 1.

## Recommended Fix Location

- **Bug 2 (fix this first — highest value, lowest risk per unit of impact):** `markdown_builder.py::_render_page_body()` needs a paragraph-reconstruction pass between reading `page.cleaned_text` and appending to `blocks` — merge consecutive non-heading, non-suppressed lines into one paragraph until a real paragraph-break signal (blank line in source, or a heading/footnote line), instead of one block per raw line. Must preserve the existing exact-line-match logic used for heading substitution and footnote-line suppression, which currently assumes one-line-per-line-of-source — that assumption will need to be revisited as part of this fix (not now, per audit-only scope).
- **Bug 1 (fix second — narrower trigger, higher design risk):** belongs in a bbox-aware merge step, since plain `get_text()` string mode has no coordinate data to detect "same baseline, different fragment." Natural home is either (a) `structure_detector.py`, which already has bbox per `TextBlock` and could merge same-y0/overlapping-y, x-sequential, small-gap fragments before they're used, or (b) a new step in `extractor.py` that rebuilds `cleaned_text` from bbox data instead of PyMuPDF's plain-text mode. Either way, **any fix must NOT key off y-coordinate alone** — `docs/KNOWN_LIMITATIONS.md` already documents multi-column reconstruction as unsupported/out of scope, and two genuinely different columns can share a y-coordinate; a same-y merge heuristic needs an x-continuity/gap-size guard to avoid stitching unrelated column content together.

## Estimated Regression Risk

- **Bug 2 fix: High blast radius, but well-contained.** Changes body-text rendering for every page of every document processed — this is the single most central code path in markdown generation. Expect every existing test in `tests/test_markdown.py` (and likely `tests/test_docx.py`, since DOCX generation consumes the same markdown) that asserts specific line-by-line text to need updating, and the full benchmark corpus (`samples/benchmark/`) re-validated against its `expected_md` set, not just this regression case. This is the right fix to make, but should not be treated as a small patch.
- **Bug 1 fix: Lower blast radius, higher design risk.** Only affects pages whose PDF producer encodes justified-text spacing without bridging space glyphs (currently observed on exactly one PDF in the corpus) — narrower surface area — but a same-baseline-merge heuristic is the kind of code that's easy to get subtly wrong against documents with genuine multi-column layouts or tables, both explicitly out of scope per `KNOWN_LIMITATIONS.md`. Needs its own dedicated test fixtures (synthetic same-y multi-column PDF) before being trusted, not just this one regression PDF.
