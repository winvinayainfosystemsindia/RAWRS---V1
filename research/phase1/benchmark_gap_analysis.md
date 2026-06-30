# RAWRS Benchmark Gap Analysis

**Scope:** Audit only. No implementation code was written or modified. This document compares current RAWRS pipeline output against the new benchmark set (4 production PDFs + 4 expected Markdown files + 4 expected DOCX files) and categorizes every observed difference.

**A required input could not be read:** a "Checklist for Document Remediation" document was requested as required reading but does not exist anywhere in the repository (no matching filename; `README.md` is empty). Per direction from the user, this audit proceeds without it, using the 8 docs in `docs/` as the acceptance criteria. If that checklist exists elsewhere, re-running this audit against it may change findings, particularly around what counts as "remediation quality."

**Architecture constraints honored throughout this audit:** no redesign proposed, no new frameworks/databases/cloud dependencies/agent frameworks assumed available. Several findings below explicitly note where the benchmark's own ground truth appears to require capabilities (e.g. AI-generated alt text) that conflict with these constraints — those are flagged as decisions for the team, not engineering tasks.

---

## 1. Benchmark Inventory

| # | Source PDF | Pages | Text layer? | Raw image refs (PyMuPDF) | Expected MD size | Expected DOCX size |
|---|---|---|---|---|---|---|
| 1 | `4. O Leary_Developing the research questions.pdf` | 13 | **None** (0 extractable chars — fully scanned) | 11 | 356 lines / 31 KB | 421 KB |
| 2 | `4.Teaching as a professional discipline-Chapter 1.pdf` | 27 | Yes (72,959 chars) | 54 | 362 lines / 73 KB | 105 KB |
| 3 | `5.Teachingas a profession_Calderhead.pdf` | 4 | Yes (10,913 chars) | 0 | 65 lines / 11 KB | 19 KB |
| 4 | `6. Fullan&Hargreaves_teacherasaperson.pdf` | 6 | Yes (14,331 chars) | 0 | 120 lines / 15 KB | 22 KB |

**Immediate observation:** unlike the old benchmark set (where every PDF was a fully-scanned image with zero text), 3 of these 4 new PDFs are **born-digital with a real, directly-extractable text layer**. This changes the OCR story significantly — see §4.1.

## 2. Current RAWRS Output (ran via `run_pipeline` against all 4 PDFs, unmodified)

| # | Pages | Content headings detected | Images extracted | Markdown size | Validation issues |
|---|---|---|---|---|---|
| 1 (O'Leary) | 13 | 0 | 11 | 1,801 chars | `HEADING_002` (missing H1) |
| 2 (Teaching Ch.1) | 27 | 0 | 54 | 7,855 chars | `HEADING_002` |
| 3 (Calderhead) | 4 | 0 | 0 | 138 chars | `DOC_001` (empty document), `HEADING_002` |
| 4 (Fullan & Hargreaves) | 6 | 0 | 0 | 208 chars | `DOC_001`, `HEADING_002` |

**Root cause for all four:** `src/ocr/extractor.py` is unimplemented. `pdf_parser.py` deliberately leaves `Page.cleaned_text`/`raw_text` empty by design (OCR's job). Heading Detection, Markdown Generation, and DOCX Generation all then operate on empty text — this is true even for the 3 PDFs with perfectly extractable, real text. **RAWRS is currently discarding text that PyMuPDF could trivially extract**, because no stage exists yet to put it into `Page.cleaned_text`.

---

## 3. Per-Document Findings

### 3.1 — O'Leary (`4. O Leary...`)

- Fully scanned, zero text layer — true OCR is unavoidable here (Docling/Surya, not just PyMuPDF text extraction).
- Expected MD: 1 H1, 5 H2, 20 H3, **zero `######` page markers**, **zero image references**, 12 `<!-- pagebreak -->` markers.
- Expected DOCX: 26 heading paragraphs (1×H1, 5×H2, 20×H3), **0 page breaks of any kind** (confirmed via raw OOXML inspection — no `<w:br w:type="page">`, no `pageBreakBefore`), 4 inline images (vs. 11 raw refs detected by PyMuPDF), each image has rich multi-sentence descriptive **alt text** (`descr` attribute).
- A figure caption ("FIGURE 3.1 CONCEPT MAP OF POTENTIAL RESEARCH TOPICS") is glued mid-sentence onto the preceding word with no space ("...following a path, orFIGURE 3.1 CONCEPT MAP...") in *both* the expected MD and (apparently) the DOCX — i.e., even this hand-curated ground truth has at least one uncorrected reading-order/caption artifact. The bar is "much better than empty," not "flawless."

### 3.2 — Teaching as a Professional Discipline, Ch. 1

- Real text layer; heading structure is **all short Title-Case phrases with zero numeric prefixes** ("Teaching as a Common-sense Activity", "Teaching as an Art", "Teaching as a Craft", "Conclusion") — none of them match `Unit N`/`Chapter N`/keyword patterns except the book title and "Chapter 1" itself.
- Expected MD: 1 H1 (book title), 9 H2 (chapter heading + 8 section headings), 0 H3+, **zero page markers**, **zero image refs**, 26 `<!-- pagebreak -->` markers.
- Expected DOCX: 10 heading paragraphs, 25 real page breaks (confirmed via OOXML — for 27 pages, meaning the *last* page's trailing break is correctly omitted), only **1 inline image retained out of 54 raw refs** — and that one is the book's **cover page**, with alt text "Cover page of the book 'Teaching as a Professional Discipline' Geoffrey Squires."
- The H1 paragraph's raw text is `"Teaching as a Professional Discipline\nGeoffrey Squires"` — a soft line break inside one Heading-1 paragraph, combining title + author into a single heading (contrast with the expected *Markdown* for this same document, where this isn't reproduced the same way — see §5.3).

### 3.3 — Calderhead (4-page excerpt, printed pages 80–83)

- Confirmed by direct visual inspection of the PDF (see below): each page has a real printed page number ("80", "81", "82", "83") in its footer, plus a running header repeating the chapter title / a short page-top label ("Teachers" / "Teaching as a professional activity 81").
- Expected MD: title block is 3 separate plain lines under one H1 ("Chapter 9" is H1; "Teaching as a professional activity" and "James Calderhead" stay **plain text**, not H2). Page markers are `###### 80`, `###### 81`, `###### 82`, `###### 83` — **bare printed page number, no "Page" word, and not 1/2/3/4**. "REFERENCES" stays **plain text**, not a heading.
- Expected DOCX: H1 = `"Chapter 9\nTeaching as a professional activity\nJames Calderhead"` as **one heading paragraph with soft line breaks** (different structure than the Markdown's 3 separate plain lines — see §5.3). 4× Heading 6 ("80"–"83"). 3 real page breaks (correct for a 4-page document).
- Running headers/footers ("Teaching as a professional activity 81", "82 Teachers") are correctly absent from both expected outputs — confirming header/footer removal is expected to actually happen, with the bare page number salvaged and repurposed as the page marker.

### 3.4 — Fullan & Hargreaves (6-page excerpt, printed pages 67–72)

- Same pattern as Calderhead: H1 = "Chapter 7" only; subtitle + author stay plain. Page markers `###### 67`–`###### 72` (bare number). 5 real page breaks (correct for 6 pages).
- Inconsistency vs. Calderhead: here `## REFERENCES` **is** an H2 heading, whereas in Calderhead "REFERENCES" stayed plain text. Two documents, same literal keyword, different expected treatment — see §5.1.

---

## 4. Cross-Cutting Gap Catalog

Each gap below: **Severity** (Critical/High/Medium/Low), **Frequency** (how many of the 4 docs it affects), **Effort** (S/M/L/XL), **Impact on remediation quality**.

### 4.1 OCR
**Gap:** No OCR/text-extraction stage exists. Even for 3 PDFs with a perfect, directly-extractable text layer, `Page.cleaned_text` stays empty because no module ever calls `page.get_text()` (or Docling) and writes the result there.
**Severity:** Critical. **Frequency:** 4/4 (100%) — root cause of nearly every other gap. **Effort:** L for the scanned PDF (true OCR engine needed — Docling/Surya per `OCR_RULES.md`); **S–M** for the 3 born-digital PDFs (PyMuPDF `get_text()` would work immediately, no OCR engine needed at all for those three).
**Impact:** Total. Nothing downstream can be meaningfully evaluated until this exists. **Recommendation:** consider splitting this into two paths — a fast win using PyMuPDF text extraction for born-digital PDFs (covers 3/4 of this benchmark with low effort) plus the real OCR engine for scanned PDFs (needed for 1/4 here, but likely the majority case for WinVinaya's actual remediation backlog).

### 4.2 Reading Order
**Gap A:** Page markers in the expected output are inserted **at the exact point the PDF paginates**, including mid-sentence ("...wealth of other particular | ###### 81 | information resulting from..." — one continuous sentence split across the page boundary). RAWRS's `Page`/`Document` model treats each page's text as a fully separate block rendered in its own chunk; there is currently no way to represent "one paragraph spanning two Page objects" with a marker embedded mid-paragraph.
**Severity:** Critical (architecture-level). **Frequency:** 4/4 — will occur anywhere a sentence happens to straddle a page boundary, which is common in continuous prose. **Effort:** XL — requires rethinking how Page-level text and Document-level markers interact, which touches the frozen `Page`/`Document` model. **This needs an explicit architecture decision, not a quick fix** — flagged, not solved, here.
**Gap B:** The "FIGURE 3.1" caption-glued-onto-body-text artifact is present in the source content's natural reading order. RAWRS doesn't currently do anything with figure captions at all (see §4.7), so this isn't a regression — it's an open problem either way.
**Impact:** Without solving Gap A, page markers can only ever be approximately placed (at page-block boundaries, never mid-paragraph), which will look visibly wrong to a reviewer for any paragraph that spans a page break — i.e., most paragraphs in a multi-page document.

### 4.3 Heading Detection
**Gap:** Current rules (`Unit N`/`Chapter N`/fixed keyword list for H2; dot-numbering depth for H3–H5) match **almost none of the real headings** in this benchmark. Real headings are short Title-Case phrases with no numbering at all ("Defining the Investigation", "Boundaries", "Teaching as an Art", "Teaching as a Craft"). Of the 9 H2s + 20 H3s + 1 H1 expected in the O'Leary and Teaching-Ch.1 documents, the current rule set would catch **0**, even with perfect OCR text feeding it.
**Severity:** Critical. **Frequency:** 4/4 (every document's heading structure relies on patterns the current rules don't cover). **Effort:** L — requires a fundamentally different signal than line-content regex, most plausibly font-size/boldness/position metadata (available from PyMuPDF's `page.get_text("dict")` span-level output, or from Docling's layout model) rather than text pattern matching alone.
**Impact:** Highest of any single category — heading hierarchy is the backbone of DOCX Navigation Pane support, screen-reader navigation, and most of `VALIDATION_RULES.md`'s heading checks. A rule-based regex approach cannot reach acceptable recall against this benchmark's actual heading style.
**Secondary finding:** "REFERENCES" is heading in one document and plain text in another (§3.4) — even a perfect layout-based detector will need a documented, consistent rule for this, since the ground truth itself disagrees with itself.
**Tertiary finding:** Title-block handling is inconsistent even within Markdown vs. DOCX for the *same* document (§5.3) — H1 detection logic needs a clear, single specification of what exactly becomes the heading vs. stays plain text (subtitle/byline).

### 4.4 Page Markers
**Gap A (format):** Expected markers use the **bare printed page number** ("80", not "Page 1" and not "80" prefixed by the word Page). `HEADING_RULES.md`/`PAGE_RULES.md`'s own documented example (`###### Page 1`) does **not** match this benchmark's ground truth.
**Severity:** High. **Frequency:** 2/4 (the only 2 documents whose ground truth has page markers at all — see Gap B). **Effort:** M — requires reading the actual printed page number off each page (header/footer text), which for born-digital PDFs is a position-based text lookup via PyMuPDF, not full OCR.
**Gap B (presence):** 2/4 documents' expected Markdown have **zero `######` markers anywhere**, despite `PAGE_RULES.md` mandating one per page with no stated exception. This is either a genuine inconsistency in the new benchmark set, or a real, undocumented product rule ("only add page markers when meaningful printed numbers exist / for book excerpts, not full chapters") that hasn't made it into `PAGE_RULES.md`.
**Severity:** flagged as **ground-truth inconsistency requiring a product decision**, not an engineering gap — RAWRS's current behavior (always emit a marker) already matches the *documented* spec; whether to match this benchmark instead requires resolving the conflict first.
**Impact:** High once resolved — wrong/missing page markers break the PDF-to-DOCX page traceability that is explicitly called a "mandatory remediation requirement" in `PAGE_RULES.md`.

### 4.5 Page Breaks
**Finding (validates existing work, not a gap):** Of the 3 documents whose expected DOCX has any page breaks at all, the break count is consistently `page_count - 1` (3 breaks for 4 pages, 5 for 6 pages, 25 for 27 pages) — i.e., **no break after the final page**. This exactly matches the deliberate design decision already made in `docx_generator.py` (skip the trailing break to avoid a spurious blank final page). **No change needed here.**
**Gap:** The O'Leary document's expected DOCX has **zero page breaks at all** (13 pages, but neither `<w:br w:type="page">` nor `pageBreakBefore` appears anywhere) — direct contradiction of `PAGE_RULES.md`'s "preserve page boundaries" / "no page loss" requirement, and inconsistent with that same document's own expected Markdown (which has 12 `<!-- pagebreak -->` markers). This looks like a defect in this one benchmark file rather than an intentional rule, and is flagged as a **ground-truth inconsistency**, not something to replicate.
**Severity:** Low (current behavior is already correct against 3/4 evidence; the 4th is contradictory). **Frequency:** 1/4 anomalous. **Effort:** N/A (no code change indicated). **Impact:** Low — existing `docx_generator.py` behavior should be kept as-is.

### 4.6 Image Extraction
**Gap:** Massive precision problem. PyMuPDF's `page.get_images()` (used today) detects **11 and 54** raw image references in the two image-containing PDFs; the curated expected DOCX retains only **4 and 1** respectively. The current extractor has no filtering at all — every embedded raster is extracted and (per `markdown_builder.py`) referenced in markdown.
**Severity:** High. **Frequency:** 2/4 documents have any images at all, but for those 2, the over-extraction ratio is extreme (2.75× and 54×).
**Effort:** M — likely tractable with simple heuristics even without OCR: discard images whose bounding box covers most of the page (background/scan layer, not a content figure), dedupe repeated images, and/or require a minimum size threshold below which an image is decorative.
**Impact:** High — without filtering, every DOCX would be cluttered with dozens of meaningless full-page background images per document, actively harming reviewability (the opposite of "reducing remediation effort").

### 4.7 Figure Detection
**Gap:** RAWRS has a `Figure` model (label/number/caption) but no module populates it — `figure_detector` logic doesn't exist; `image_extractor.py` never sets `Image.figure`. The benchmark shows real figure captions exist and matter (e.g. "FIGURE 3.2 FROM TOPICS TO RESEARCHABLE QUESTIONS", center-aligned, sharing a paragraph with its image) for the one document that has real content figures.
**Severity:** Medium. **Frequency:** 1/4 (only O'Leary has real, captioned content figures in this set). **Effort:** M, but gated behind Gap 4.6 (no point detecting captions for images that shouldn't have been extracted in the first place).
**Impact:** Medium today (low frequency in this specific benchmark) but likely higher across WinVinaya's broader real-world document mix, where figures/diagrams are common in academic/educational PDFs.

### 4.8 Captions
**Gap:** `markdown_builder.py`/`docx_generator.py` already have working caption rendering logic (italic, centered, paired with the preceding image) — but it has never been exercised against a document with real figures, because Image Extraction never produces a populated `Image.figure.caption` today (see 4.7). The expected DOCX structure differs slightly from RAWRS's convention: ground truth puts the caption text in the **same paragraph** as the image; RAWRS currently renders image and caption as **two separate paragraphs**.
**Severity:** Low (structural difference, not a correctness defect — both are centered and visually similar). **Frequency:** 1/4. **Effort:** S, once Gap 4.7 exists. **Impact:** Low-Medium — minor DOCX structural divergence, cosmetic rather than functional.

### 4.9 DOCX Formatting
**Finding:** RAWRS's current heading-formatting decisions (16pt/14pt/12pt, bold, pure black, Times New Roman, explicit run-level overrides) already match `HEADING_RULES.md` **more consistently than the ground truth itself does**. The 4 expected DOCX files disagree with each other and with the documented spec: O'Leary uses 20pt/16pt/14pt headings in a dark-blue theme color (`#0F4761`), not 16/14/12pt black; Calderhead's H2/H3 use a teal/blue accent color and slightly different point sizes (13pt, not 14pt); only Heading 1 (16pt, black, Times New Roman, bold) and, where present, Heading 6 (12pt, black, Times New Roman, bold) are consistently correct across documents.
**Severity:** Low (no action indicated — current code is arguably already the more spec-compliant option). **Frequency:** N/A. **Effort:** N/A. **Impact:** Low, but worth flagging: if literal benchmark-matching becomes a hard pass/fail metric later, this category will show "failures" that are actually the benchmark being internally inconsistent, not RAWRS being wrong.
**Secondary structural note:** the ground truth relies on **style-level** font definitions (`doc.styles['Heading N'].font...`) more than per-run overrides; RAWRS's `docx_generator.py` always sets explicit run-level overrides. Both achieve the same visual result, but style-driven formatting is arguably more maintainable (a reviewer can restyle every heading by editing one style). Not a correctness gap — a design-quality observation.

### 4.10 Navigation Pane
**Finding:** Not an independent gap. `docx_generator.py` already maps every heading to Word's built-in `Heading 1`–`Heading 6` styles, which is exactly what the expected DOCX files do, and exactly what populates Word's Navigation Pane. This category's only real-world failure mode is **downstream of Gap 4.3 (Heading Detection)** — if no content headings are ever detected, there's nothing for the Nav Pane to show beyond page markers, which is the current state for all 4 documents.
**Severity/Effort/Impact:** N/A as a standalone item — resolves automatically once Heading Detection (4.3) and OCR (4.1) are fixed.

### 4.11 Accessibility
**Finding:** Both RAWRS and the benchmark's expected DOCX files leave `core_properties.title` and `core_properties.language` empty. No gap relative to the benchmark. Broader accessibility tagging (PDF/UA-equivalent structure tags) is explicitly out of Phase 1 scope per `PHASE1_SCOPE.md` and the benchmark doesn't appear to require it either — consistent, no action needed.

### 4.12 Alt Text
**Gap — the most strategically important finding in this audit:** every real image in the expected DOCX files carries **rich, multi-sentence, interpretive alt text** (e.g., a 5-sentence description of a concept-map diagram's three branches and their sub-topics). This is unambiguously beyond what OCR, layout analysis, or rule-based logic can produce — it reads like either human-written or vision-language-model-generated descriptive text.
**Conflict:** `RAWRS_PROJECT_CONTEXT.md`, `PHASE1_SCOPE.md`, and this engagement's own constraints ("No AI", "Do not introduce agent frameworks") explicitly place Alt Text Generation **out of Phase 1 scope**. The benchmark's acceptance bar appears to require exactly the capability Phase 1 says it won't build.
**Severity:** Critical, but **not an engineering task** — this is a scope/architecture decision for the team: either (a) the benchmark's alt text requirement is out-of-scope for what Phase 1 is graded against and should be excluded from any automated comparison, (b) Alt Text Generation needs to be pulled into scope (which would require introducing some model-backed capability, a real architecture change requiring sign-off), or (c) alt text is expected to be added entirely by a human reviewer post-DOCX-generation, and the benchmark DOCX files reflect *post-human-review* output rather than RAWRS's own output target. **This needs a decision before any related work is planned**, not a ticket.

### 4.13 Validation
**Finding:** Current `validator.py` checks are behaving correctly given current (empty) pipeline output — `DOC_001`/`HEADING_002` are accurate findings, not bugs. No validator defect was found relative to what's currently observable.
**Gap:** Figure-level validation checks (missing captions, missing figure numbering, unlinked references — all listed in `VALIDATION_RULES.md`) remain unimplemented, consistent with the earlier-flagged scope note that only Image-level checks were built. Given the low frequency of real figures in this specific benchmark (1/4 documents), this is lower priority than other gaps.
**Severity:** Low (for this benchmark). **Frequency:** 1/4. **Effort:** S–M (mirrors the existing Image-check pattern in `validator.py`). **Impact:** Low today, would rise if/when Figure Detection (4.7) is built, since validation should follow shortly after to keep the "AI Proposes, Validation Decides" principle intact.

---

## 5. Ground-Truth Inconsistencies (decisions needed, not bugs to fix)

These are differences *within the benchmark set itself*, not gaps in RAWRS. Flagging them because matching "the benchmark" isn't a single well-defined target until these are resolved.

1. **"REFERENCES" heading treatment disagrees between documents** (§3.3 vs §3.4) — heading in one, plain text in the other, same literal keyword.
2. **Page markers present in 2/4 documents, entirely absent in the other 2/4** — direct tension with `PAGE_RULES.md`'s unconditional "every page" requirement.
3. **O'Leary's expected DOCX has zero page breaks** despite its own expected Markdown having 12 `<!-- pagebreak -->` markers — internal inconsistency between that document's two "expected" artifacts.
4. **Title-block structure (Chapter N / subtitle / author) differs between a document's own expected Markdown and expected DOCX** (Markdown: 3 separate plain-text lines under one H1; DOCX: all 3 lines merged into one Heading-1 paragraph via soft line breaks) — suggests the two expected artifacts for the same source were not mechanically derived from each other, which also means "Markdown as source of truth for downstream processing" (`ARCHITECTURE.md`) may not literally hold for this benchmark's own ground truth.
5. **Alt text requirement directly conflicts with documented Phase 1 scope exclusion** (§4.12) — the single highest-stakes inconsistency in this set.

---

## 6. ROI Ranking — Highest to Lowest

| Rank | Gap | Severity | Frequency | Effort | Why this rank |
|---|---|---|---|---|---|
| 1 | **OCR — text extraction (born-digital path)** | Critical | 4/4 | S–M | Unlocks 3 of 4 documents almost immediately via PyMuPDF `get_text()` alone — no new engine needed. Single highest leverage-per-effort item; blocks every other category. |
| 2 | **Alt Text scope conflict** | Critical (strategic) | 4/4 | Decision, not build | Not gated behind any other work — needs resolving *before* effort is spent elsewhere, since it determines whether a whole category of work belongs in Phase 1 at all. |
| 3 | **Image extraction precision (filter background/full-page images)** | High | 2/4 (severe where applicable) | M | Pure-heuristic, OCR-independent fix; removes the most visibly absurd current defect (54 images extracted where 1 was wanted). |
| 4 | **Heading Detection — replace numbering/keyword rules with layout-based signal** | Critical | 4/4 | L | Highest-impact category overall, but large effort and most of its value can't be *verified* until #1 lands — ranked just below the items that are independently actionable today. |
| 5 | **Page marker format (printed page number, no "Page" prefix)** | High | 2/4 (where markers exist) | M | Concrete, bounded fix once minimal text/position extraction exists; depends on #1 for the scanned document only. |
| 6 | **OCR — true engine for scanned PDFs (Docling/Surya)** | Critical | 1/4 (this benchmark), likely higher in the real backlog | L | Necessary but only for the fully-scanned case; larger effort than the born-digital path, so ranked below it despite similar ultimate importance. |
| 7 | **Reading order — page markers mid-paragraph / cross-page text stitching** | Critical (architectural) | 4/4 (latent) | XL | Highest long-term importance but requires a model/architecture decision before any implementation — not actionable without that conversation happening first. |
| 8 | **Figure Detection (caption/label extraction)** | Medium | 1/4 | M (gated on #3) | Real but narrow in this benchmark; depends on #3 being done first to be worth building. |
| 9 | **Captions — same-paragraph vs. separate-paragraph structure** | Low | 1/4 | S (gated on #8) | Cosmetic once #8 exists. |
| 10 | **Figure-level validation checks** | Low | 1/4 | S–M | Natural follow-on to #8, not urgent on its own. |
| — | DOCX Formatting (heading colors/sizes) | Low | N/A | N/A | No action — current output is already more spec-compliant than the benchmark itself. |
| — | Navigation Pane | N/A | N/A | N/A | Resolves automatically once #1 and #4 land. |
| — | Page Breaks (trailing-break logic) | N/A | N/A | N/A | Already correct against 3/4 evidence; no change indicated. |
| — | Accessibility (doc properties) | N/A | N/A | N/A | Already matches benchmark (both empty). |
| — | Page markers missing in 2/4 ground truth | — | — | — | Ground-truth inconsistency, not a RAWRS gap — needs a product decision (§5.2), not engineering. |

---

## 7. Summary for Stakeholders

The single biggest blocker remains exactly what every prior session in this project flagged: **no OCR/text-extraction stage exists**, and three of these four new benchmark PDFs didn't even need real OCR to fix that — they have clean, directly-extractable text that RAWRS currently throws away. That is the highest-ROI, most tractable first move.

Beyond that, this benchmark reveals two things the old benchmark set never could, because it had no real text to compare against:

1. **The current rule-based heading detector doesn't work against real content.** It was designed against the literal numbered/keyworded examples in `HEADING_RULES.md`, but real headings in this benchmark are plain Title-Case phrases with no numbering — a fundamentally different detection problem requiring layout signal (font size/weight/position), not text patterns.
2. **The benchmark's own ground truth asks for a capability (rich, AI-quality alt text) that Phase 1's own scope explicitly excludes.** This is a decision for the team, surfaced here rather than guessed at.

No code was changed as part of this audit, per instructions.
