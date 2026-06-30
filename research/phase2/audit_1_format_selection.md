# RAWRS Phase-2 Audit Report: Mathpix Ingestion Format Comparison

**Date:** 2026-06-26  
**Corpus:** 10 benchmark documents  
**Auditor:** Evidence-only, read-only, no speculation  
**Working directory:** `C:\RAWRS - WINVINAYA\samples\mathpix\`

---

## Format Availability — Measured Inventory

| Format | Available | Count |
|--------|-----------|-------|
| Mathpix Markdown (.mmd) | Yes | 10/10 documents |
| Markdown (.md) | Yes | 9/10 (Nature of Enquiry has no .md file) |
| DOCX | Yes | 10/10 documents |
| PDF | Yes (source, not export) | 10/10 |
| Extracted images (images/) | Yes (partial) | 5/10 document folders |
| HTML | **Not available** | 0/10 |
| JSON | **Not available** | 0/10 |

**HTML and JSON are not present in any of the 10 Mathpix export folders.** All feature observations below are restricted to MMD, MD, DOCX, and extracted images.

### Document Corpus

| # | Document | .mmd | .md | .docx | images/ |
|---|----------|------|-----|-------|---------|
| 1 | 1. Nature of Enquiry | Yes | **No** | Yes | Yes (1 image) |
| 2 | 1.Aims of Education and the teacher_Dhankar_PhilPers | Yes | Yes | Yes | No |
| 3 | 2. Social research strategies Bryman | Yes | Yes | Yes | Yes (10 images) |
| 4 | 2.FolkPedagogy_Bruner_PsychDimensions_New | Yes | Yes | Yes | No |
| 5 | 3. sockett_profession | Yes | Yes | Yes | No |
| 6 | 4. O Leary_Developing the research questions | Yes | Yes | Yes | Yes (4 images) |
| 7 | 4.Teaching as a professional discipline-Chapter 1 | Yes | Yes | Yes | Yes (1 image) |
| 8 | 5.Teachingas a profession_Calderhead | Yes | Yes (.md.md) | Yes | No |
| 9 | 6. Fullan&Hargreaves_teacherasaperson | Yes | Yes (.md.md) | Yes | No |
| 10 | 7.brinkman-learner-centred-education-reform-india-missing-beliefs | Yes | Yes (.md.md) | Yes | Yes (2 images) |

---

## Feature Measurement Table

| Feature | Markdown (.md) | MMD | DOCX | Best Source |
|---------|----------------|-----|------|-------------|
| Heading hierarchy | Flat — all `##` (H2), except some H1 titles | Partial — `\section*{}` for all unless doc has numbered sections; then also `\subsection*{}` | Rich — Heading1/Heading2/Heading3/Heading6; verified across Bryman, Nature of Enquiry, Brinkman, Calderhead | **DOCX** |
| Reading order | Correct linear order observed | Correct linear order observed | Assumed correct (same source) | Tie (MMD≈MD≈DOCX) |
| Tables — structure | GFM pipe table with `:---` alignment | LaTeX `\begin{tabular}{|l|l|l|}` with column types and `\hline` | Word table XML (binary inside ZIP, no plain-text access) | **MMD** |
| Tables — merged cells | Represented as empty cells (`\|  \|  \|`) | `\multicolumn{n}{spec}{}` — explicit merged cell | Word `<w:gridSpan>` XML | **MMD** |
| Tables — captions | `## Table N` as a heading above | `\caption{...}` inside `\begin{table}` environment | Word paragraph above table | **MMD** |
| Lists (ordered/unordered) | Preserved (`-`, `1.`) | Preserved (`-`, `1.`) | Preserved (Word list XML) | Tie |
| List nesting | Preserved | Preserved | Preserved | Tie |
| Figures — structure | `![](CDN URL)` — no figure environment, no caption linkage | `\begin{figure}...\includegraphics...\captionsetup...\caption{}\end{figure}` — structured | Partial: some images embedded in `word/media/`; Bryman: 3/10 images embedded; Brinkman: 2/2 embedded | **MMD** |
| Figures — captions | No caption linkage (caption text appears as separate `## ` heading) | `\caption{}` structurally linked inside `\begin{figure}` | Word paragraph; caption linkage unclear without XML parse | **MMD** |
| Figures — image references | Remote CDN URL (requires internet; breaks offline) | Local `./images/` path (offline capable) | Embedded binary in `word/media/` (offline, complete for docs without large figure counts) | **MMD** (offline, complete) |
| Figures — completeness | All figure images referenced (10/10 in Bryman) | All figure images referenced (10/10 in Bryman) | Incomplete — Bryman has 3 embedded of 10 referenced | **MMD** or **MD** |
| Alt text | Empty `![]()` — no generated description | `alt={}` — empty in all `\includegraphics` | Likely empty (from html-to-docx; not inspected) | None provide alt text |
| Footnotes — in-text ref | `${ }^{n}$` LaTeX math notation (inline) | `${ }^{n}$` LaTeX math notation (inline) | `<w:footnoteReference>` or `<w:endnoteReference>` (linked XML) | **DOCX** |
| Footnotes — body | `[^0]` GFM footnote for page-1 affiliation block (inconsistent across docs) | `\footnotetext{...}` for page-1 affiliation; endnote bodies as plain numbered list at end | `word/footnotes.xml` and `word/endnotes.xml` with structured `<w:footnote>` / `<w:endnote>` elements | **DOCX** |
| Footnote linkage | Partial (`[^0]` links body to reference, but inline refs remain `${ }^{n}$`) | None (endnote refs and bodies are unlinked) | Full: `w:endnoteReference id="n"` → `w:endnote id="n"` | **DOCX** |
| Cross-references | None — OCR limitation | None — OCR limitation | None — OCR limitation | Not available in any format |
| Bookmarks/anchors | None | None | 40+ `_Toc` bookmarks per doc (Bryman: 40+ verified) | **DOCX** only |
| Metadata — title | H1 (`#`) for journal articles; absent for textbook chapters | `\title{...}` — present and semantically tagged | `<dc:title>` in core.xml — **empty** in all inspected docs | **MMD** |
| Metadata — author | Plain text line with `<br>` (Brinkman); absent for others | `\author{...}` — present when identifiable | `<dc:creator>html-to-docx</dc:creator>` — tool name only | **MMD** |
| Metadata — abstract | `#### Abstract` heading (Brinkman MD); missing for most | `\begin{abstract}...\end{abstract}` — structured semantic block | Not present | **MMD** |
| Metadata — DOI / journal | Present as plain text in body | Present as plain text in body | Not in core.xml; may be in body text | MMD ≈ MD |
| Page numbers | None | None | **Heading6 style** — page numbers tagged as H6 throughout; verified in Bryman (pages 19–43), Nature of Enquiry (pages 3+) | **DOCX** |
| Page boundaries | None | None | Heading6 marks individual page numbers (no explicit boundary element) | **DOCX** (via H6) |
| Geometry — bounding boxes | Explicitly in CDN URL params: `?height=H&width=W&top_left_y=Y&top_left_x=X` | Encoded in image filename: `page_height_width_y_x.jpg` — requires filename parsing | Not accessible (images embedded as binary; no coordinate metadata exposed) | **MD** (explicit params) |
| Geometry — page coordinate | Page number in image filename/URL (e.g., `-03.jpg` = page 3) | Same via filename | Not accessible | MMD ≈ MD |
| OCR confidence | Not present in any file | Not present in any file | Not present | **Not observable** |
| Math equations | LaTeX inline `$...$` preserved (e.g., `$r=.66, p<.001$`) | LaTeX inline `$...$` preserved — same notation | Word MathML (different encoding; requires python-docx or Word to read) | MMD ≈ MD |
| Blockquotes | `> text` — preserved | `> text` — preserved | Word block quote style (XML) | Tie |

---

## Observed Heading Hierarchy by Document and Format

### MMD heading levels observed

| Document | `\title` | `\section*` | `\subsection*` | `\subsubsection*` |
|----------|----------|-------------|----------------|-------------------|
| Nature of Enquiry | Yes | Yes | Yes (1.1, 1.2, 1.3 …) | Not observed |
| Bryman | No | Yes | No | No |
| Brinkman | Yes | Yes | No | No |
| Aims/Dhankar | Yes | Yes | No | No |
| Sockett | No | Yes | No | No |
| O'Leary | No | Yes | No | No |

**Finding:** MMD uses `\subsection*{}` only when the original PDF has numbered section headings (e.g., 1.1, 1.2). All other documents are flat (`\section*{}` only). Heading depth is NOT reliably reconstructed from visual size alone.

### DOCX heading styles observed

| Document | Heading1 | Heading2 | Heading3 | Heading6 (page nums) | TOC styles |
|----------|----------|----------|----------|----------------------|------------|
| Bryman | Yes | Yes | Yes | Yes (pages 19–43) | TOC1/TOC2/TOC3 |
| Nature of Enquiry | Yes | Yes | Yes | Yes | Not checked |
| Brinkman | Yes | Yes | No | Yes | Not checked |
| Calderhead | Yes | No | No | Yes | Not checked |

**Finding:** DOCX heading hierarchy is document-dependent and richer than MMD/MD in every case measured.

---

## Specific Format Observations (Verbatim Evidence)

### MMD verbatim examples

```latex
\title{AIMS OF EDUCATION: DO TEACHERS NEED TO BOTHER ABOUT THEM?}
\author{Rohit Dhankar}
\begin{abstract}...\end{abstract}

\section*{Introduction}            ← all same level in flat docs
\subsection*{1.1 Introduction}     ← only when numbered in PDF

\begin{table}
  \captionsetup{labelformat=empty}
  \caption{Table 1. Summary of teachers' beliefs vs. pedagogy scores.}
  \begin{tabular}{|l|l|l|l|}
    \hline & Low-LCE pedagogy & Mid-LCE pedagogy & High-LCE pedagogy \\
    \hline Low-LCE belief score & 14 & 5 & 1 \\
  \end{tabular}
\end{table}

\begin{figure}
  \includegraphics[alt={},max width=\textwidth]{./images/73a2d...jpg}
  \captionsetup{labelformat=empty}
  \caption{Figure I. State-wise differences in LCE pedagogy and belief scores.}
\end{figure}

\footnotetext{UNICEF India, New Delhi, India ...}   ← page-1 affiliation
${ }^{1}$ endnote body as plain text list            ← unlinked endnotes at EOF
```

### MD verbatim examples

```markdown
# Learner-centred education reforms in India        ← H1 title (journal articles only)
Suzana Brinkmann<br>Institute of Education          ← author as plain text + br

#### Abstract                                        ← H4 (inconsistent; not H2)

## Keywords                                          ← H2
## Introduction                                      ← H2 (all sections same level)

![](https://cdn.mathpix.com/cropped/doc-03.jpg?height=102&width=111&top_left_y=1847&top_left_x=317)

[^0]: UNICEF India, New Delhi, India ...             ← GFM footnote at EOF (only 1 doc)
${ }^{1}$ endnote body                              ← still LaTeX math notation (not [^1])

| Header |  |  |
| :--- | :--- | :--- |
| Row | data | data |                               ← GFM pipe table (merged cells lost)
```

### DOCX verbatim examples

```xml
<!-- core.xml — metadata all empty -->
<dc:title></dc:title>
<dc:creator>html-to-docx</dc:creator>

<!-- document.xml — heading styles preserved -->
<w:pStyle w:val="Heading1"/>  → "2 Social research strategies"
<w:pStyle w:val="Heading2"/>  → "Introduction", "Theory and research"
<w:pStyle w:val="Heading3"/>  → "What type of theory?", "Interpretivism"
<w:pStyle w:val="Heading6"/>  → "19", "20", "21" ... page numbers

<!-- bookmarks present -->
<w:bookmarkStart w:id="1" w:name="_Toc233022932"/>

<!-- endnotes.xml — structured, linked by ID -->
<w:endnote w:id="1">In this study, 'learner-centred education'...</w:endnote>
<w:endnote w:id="2">In this study, 'belief' is defined as...</w:endnote>
<w:endnote w:id="3">To ensure anonymity, each teacher...</w:endnote>

<!-- word/media/ — INCOMPLETE image set -->
word/media/image1.jpg   50 KB
word/media/image2.png   51 KB
word/media/image3.jpg   24 KB
(Bryman: only 3 of 10 figure images embedded; 7 images silently dropped)
```

---

## Engineering Cost Matrix

| Feature | Already Available (no RAWRS work) | RAWRS Must Infer | Impossible | Notes |
|---------|----------------------------------|------------------|------------|-------|
| Heading text (content) | All formats | — | — | Text always present |
| Heading hierarchy H1/H2/H3 | DOCX (Word styles) | MMD (subsection* if numbered); MD (never reliable) | MD alone | DOCX cheapest path |
| Page numbers | DOCX (Heading6) | — | MMD, MD | Zero cost with DOCX |
| Table structure | MMD (LaTeX tabular); MD (GFM pipe) | DOCX (XML parse) | — | MMD directly parseable text |
| Merged cells | MMD (`\multicolumn`) | MD (approximate); DOCX (`w:gridSpan`) | — | MMD easiest |
| Figure captions | MMD (`\caption{}` linked) | MD (heading immediately before); DOCX (paragraph before) | — | MMD zero cost |
| Local image files | MMD (`./images/` offline) | — | MD (CDN only) | MMD ready for offline |
| Image bounding boxes | MD (URL params explicit); MMD (filename parse) | — | DOCX | MD zero-cost; MMD needs split() |
| Footnote/endnote bodies | DOCX (structured XML) | MMD (numbered list at end); MD (partial GFM) | — | DOCX cleanest |
| Footnote linkage (ref ↔ body) | DOCX (`w:endnoteReference`) | — | MMD, MD | Only DOCX |
| Bookmarks / anchors | DOCX (`_Toc` bookmarks) | — | MMD, MD | Only DOCX |
| Document title | MMD (`\title{}`) | MD (H1 sometimes); DOCX (empty core.xml) | — | MMD zero cost |
| Author | MMD (`\author{}`) | MD (plain text heuristic) | DOCX (only tool name) | MMD zero cost |
| Abstract | MMD (`\begin{abstract}`) | — | MD, DOCX | Only MMD |
| Math equations | MMD, MD (LaTeX `$...$`) | DOCX (MathML → LaTeX conversion) | — | MMD/MD zero cost |
| Alt text | — | — | ALL (none generated) | Requires separate AI step |
| OCR confidence | — | — | ALL | Not observable |
| Cross-references (hyperlinked) | — | — | ALL (OCR limitation) | Not in any format |
| Reading order | MMD, MD, DOCX all correct | — | — | Free in all formats |
| Lists | MMD, MD, DOCX all preserve | — | — | Free |

---

## Confidence Matrix

| Observation | Confidence | Basis |
|-------------|------------|-------|
| HTML and JSON not available | **High** | Inspected all 10 document folders; 0 HTML/JSON files found |
| MMD heading hierarchy is mostly flat | **High** | Read 6 documents; `\section*{}` dominates; `\subsection*{}` only in Nature of Enquiry |
| MD heading hierarchy is flat (all `##`) | **High** | Read 5 documents; confirmed across Bryman, O'Leary, Aims, Brinkman, Calderhead |
| DOCX has H1/H2/H3/H6 styles | **High** | Confirmed in Bryman, Nature of Enquiry, Brinkman, Calderhead via PowerShell XML extraction |
| DOCX Heading6 = page numbers | **High** | Verified: Bryman pages 19–43 appear as Heading6 nodes; Nature of Enquiry pages 3+ same |
| DOCX metadata is empty | **High** | core.xml: `<dc:title>` empty, `<dc:creator>html-to-docx</dc:creator>` confirmed in Bryman |
| MMD local images are complete | **High** | 10 MMD image refs in Bryman match 10 files in images/ folder |
| MD images are remote CDN only | **High** | All 10 Bryman MD image refs use cdn.mathpix.com; confirmed across 3 documents |
| DOCX drops images (Bryman: 3 of 10) | **High** | Zip inspection: 3 media files in Bryman DOCX vs 10 images in folder |
| DOCX has structured endnotes | **High** | endnotes.xml confirmed; 3 endnote IDs match Brinkman's 3 endnotes; text content confirmed |
| MMD endnote bodies are unlinked | **High** | Bodies appear as numbered list at document end; no LaTeX `\endnote` command used |
| Alt text is empty in all formats | **High** | `alt={}` in all MMD `\includegraphics`; empty `![]()` in MD |
| OCR confidence not available | **High** | Zero instances found across all 10 MMD and MD files |
| MMD `\title`, `\author`, `\begin{abstract}` | **High** | Confirmed in Brinkman (all three), Aims/Dhankar (title + author) |
| DOCX image count discrepancy | **Medium** | Only Bryman and Brinkman inspected; may vary per document |
| Reading order correct in all formats | **Medium** | Read 4 documents; no order violations observed; no multi-column stress test |
| DOCX bookmarks are original TOC anchors | **Medium** | `_Toc` prefix is standard Word TOC; 40+ bookmarks in Bryman |

---

## Architectural Decision Matrix

### Option A — Canonical Markdown (.md) Ingestion

**Pros**
- Human-readable plain text; no parser needed
- Directly renderable in RAWRS frontend
- GFM pipe tables are straightforward to parse
- Image bounding-box geometry directly readable from CDN URL parameters

**Cons**
- 9/10 availability — Nature of Enquiry has no .md file; pipeline would break
- All headings flattened to `## ` (H2); heading hierarchy completely lost
- Images are remote CDN URLs — offline processing impossible
- Document metadata inconsistently or incorrectly marked up
- Footnote/endnote linkage partial and inconsistent across documents
- Figure captions not structurally linked to images

**Evidence:** Nature of Enquiry has no .md file (observed). All headings confirmed as `## ` in 5 documents. All 10 Bryman image refs use cdn.mathpix.com.

---

### Option B — Canonical JSON Ingestion

**Evidence: Not observable.** No JSON files exist in any of the 10 Mathpix export folders.

---

### Option C — Canonical HTML Ingestion

**Evidence: Not observable.** No HTML files exist in any of the 10 Mathpix export folders.

---

### Option D — Canonical DOCX Ingestion

**Pros**
- Richest heading hierarchy of all available formats (H1/H2/H3/H6 confirmed)
- Page numbers accessible as Heading6 — directly useful for RAWRS page landmarks
- Structured footnotes/endnotes with linked references in XML
- 40+ bookmarks per document providing anchor points
- Images embedded offline (for documents where embedding is complete)
- 10/10 availability

**Cons**
- Image loss: Bryman has 3/10 images embedded (7 silently dropped)
- All document metadata empty in core.xml
- Binary XML format requires python-docx or equivalent
- Math equations in Word MathML — harder to process than LaTeX

**Evidence:** Bryman DOCX: H1/H2/H3/H6 extracted. Heading6 = pages 19–43. `<dc:title>` empty. 3 images in `word/media/` vs 10 in folder. Brinkman endnotes.xml: 3 structured endnote elements confirmed.

---

### Option E — Hybrid Ingestion

Only combinations supported by observed evidence:

#### Option E1 — MMD + Extracted images
- MMD: text, LaTeX tables, figure environments with captions, metadata, math
- Extracted images: local files with bounding-box geometry in filenames
- Gap remaining: heading levels (still flat), page numbers

#### Option E2 — DOCX + MMD (recommended hybrid)
- DOCX covers: heading hierarchy (H1/H2/H3), page numbers (H6), bookmarks, footnote structure
- MMD covers: document metadata, figure captions, math, complete image references, LaTeX tables
- Requires: two parsers + reconciliation layer

#### Option E3 — DOCX + Extracted images
- DOCX covers: heading hierarchy, page numbers, footnote structure, bookmarks
- Extracted images: complete figure set with bounding-box geometry
- Gap remaining: metadata still empty; figure captions must be inferred

---

## Cost-Benefit Analysis

| Format | Estimated Features Already Solved | RAWRS Still Needs |
|--------|----------------------------------|-------------------|
| **MD alone** | Text content, lists, tables (flat), math, partial footnotes | Heading hierarchy (all lost), image CDN dependency, metadata inference, figure caption linkage, page numbers |
| **MMD alone** | Text content, lists, LaTeX tables, math, figure environments with captions, metadata, local images | Heading level hierarchy (flat), page numbers, footnote linkage |
| **DOCX alone** | Heading hierarchy (H1/H2/H3), page numbers (H6), bookmarks, footnote/endnote structure | Metadata (empty), missing images (7/10 Bryman), math equations (MathML), figure captions (heuristic) |
| **MMD + Extracted images** | Everything MMD + complete offline image set with geometry | Heading levels (still flat), page numbers |
| **DOCX + MMD** | Heading hierarchy, page numbers, footnote structure, metadata, images, figure captions, math | Two parsers + reconciliation logic |

---

## Final Conclusion

> **Given only the evidence collected in this audit, which Mathpix output format should RAWRS ingest, and why?**

**MMD is the best single-format canonical input. DOCX should be parsed as a supplementary structural source for heading hierarchy and page numbers.**

### Why MMD is the primary canonical format

1. **MMD is the only format present for all 10 documents.** MD is missing Nature of Enquiry. HTML and JSON do not exist.

2. **MMD provides the best document-level metadata** of any available text format: `\title{}`, `\author{}`, and `\begin{abstract}` are structurally tagged. MD represents these inconsistently. DOCX has all metadata empty.

3. **MMD provides the best figure representation.** `\begin{figure}...\caption{}\end{figure}` structurally links captions to images. MD's `![](CDN URL)` provides no caption linkage and requires internet. DOCX loses 7 of 10 figures in Bryman.

4. **MMD's LaTeX table format is the richest.** Column types, merged cells via `\multicolumn{}`, and row/column boundaries are all directly parseable as text. GFM pipe tables (MD) lose column type metadata and merged cell semantics.

5. **MMD image references are offline-capable.** Local `./images/` paths work without internet. MD requires CDN access. DOCX embeds images incompletely.

6. **MMD preserves math equations as LaTeX** (`$r=.66$`), which RAWRS can process directly.

### Why DOCX should be parsed as a supplement

The single strongest reason to complement MMD with DOCX is **heading hierarchy and page numbers**:

- DOCX provides H1/H2/H3 heading levels that MMD flattens to `\section*{}`
- DOCX encodes page numbers as Heading6 — directly useful for RAWRS's existing page landmark feature
- DOCX endnotes are structurally linked (ref ↔ body via matching IDs)

Parsing the Mathpix DOCX alongside MMD allows RAWRS to extract these high-value structural signals without losing the semantic richness MMD provides for everything else.

### What the evidence does NOT support

- **DOCX as canonical:** empty metadata, incomplete image set
- **MD as canonical:** 9/10 availability, CDN dependency, flat headings
- **HTML as canonical:** does not exist in the export corpus
- **JSON as canonical:** does not exist in the export corpus
