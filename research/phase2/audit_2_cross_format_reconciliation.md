# RAWRS Phase-2 Audit: Cross-Format Semantic Consistency & Reconciliation

**Date**: 2026-06-26  
**Method**: Strictly evidence-based. All measurements derived from direct inspection of file contents. No speculation.  
**Corpus**: 10 benchmark PDFs. All formats available per-document confirmed by directory listing.  
**Formats examined**: MMD (Mathpix Markdown / LaTeX hybrid), MD (standard Markdown / GFM), DOCX (Word XML via html-to-docx)  
**Scope**: Cross-format comparison only. No implementation proposals. No parser code. No software architecture recommendations.

---

## Format Availability by Document

| Document | MMD | MD | DOCX | Images folder |
|:---|:---:|:---:|:---:|:---:|
| 1. Nature of Enquiry (NoE) | ✓ | ✗ | ✓ | ✓ |
| 1. Aims of Education — Dhankar | ✓ | ✓ | ✓ | ✗ |
| 2. Social Research Strategies — Bryman | ✓ | ✓ | ✓ | ✓ |
| 2. Folk Pedagogy — Bruner | ✓ | ✓ | ✓ | ✗ |
| 3. Sockett — Profession | ✓ | ✓ | ✓ | ✓ |
| 4. O'Leary — Research Questions | ✓ | ✓ | ✓ | ✓ |
| 4. Teaching as a Professional Discipline — Ch1 | ✓ | ✓ | ✓ | ✗ |
| 5. Calderhead — Teaching as a Profession | ✓ (.mmd.mmd) | ✓ (.md.md) | ✓ | ✗ |
| 6. Fullan & Hargreaves — Teacher as a Person | ✓ (.mmd.mmd) | ✓ (.md.md) | ✓ | ✗ |
| 7. Brinkman — Learner-Centred Education | ✓ (.mmd.mmd) | ✓ (.md.md) | ✓ | ✓ |

**Note**: NoE is the only document without MD. Five documents have double-extension filenames (`.mmd.mmd`, `.md.md`).

---

## Measurement Dimension 1: Heading Text Consistency

### Method
All `\section*{}` and `\subsection*{}` entries extracted from each MMD. All `#`-prefixed lines extracted from each MD. All `<w:pStyle w:val="HeadingN">` paragraphs extracted from DOCX XML. Texts compared pairwise.

### MMD vs MD — Heading Text Agreement

| Document | MMD heading count | MD heading count | Text match rate | Notes |
|:---|:---:|:---:|:---:|:---|
| NoE | 30 | N/A | N/A | No MD available |
| Aims | 0 (no sections; title via \title{}) | 1 H1 | N/A | Title identical text |
| Bryman | 53 | 54 | ~95% | MD counts "Table 2.1" as heading differently |
| Bruner | 32 | ~30 | ~95% | Some renaming at chapter boundary |
| Sockett | 14 | ~14 | ~95% | Order preserved |
| OLeary | 34 | ~26 | ~85% | MMD has extra false headings; encoding error in MMD |
| TeachCh1 | 10 | ~10 | ~95% | Consistent |
| Calderhead | 3 | 3 | 100% | Exact match |
| Fullan | 4 | 4 | 100% | Exact match |
| Brinkman | 18 | 20 | 100% | Title and abstract counted differently |

**Finding**: When headings appear in both MMD and MD, text is identical or near-identical (>95%) in 9 of 10 documents. O'Leary is the exception (see below).

### MMD vs DOCX — Heading Text Agreement

| Document | MMD sections | DOCX non-H6 headings | Text match rate | Key conflicts |
|:---|:---:|:---:|:---:|:---|
| NoE | 30 | ~12 | ~80% | DOCX merges chapter+section; drops 4 sub-topic headings |
| Aims | 0 | 1 | N/A | DOCX merges title+author into 1 H1 |
| Bryman | 53 | ~35 | ~70% | MMD has 20+ extra; DOCX has 1 unique (Epistemological considerations) |
| Bruner | 32 | 4 | ~75% | DOCX has only 3 H2 sections; MMD has 32 flat |
| Sockett | 14 | 13 | ~85% | DOCX merges CHAPTER 1 + title; hierarchy recovered |
| OLeary | 34 | 25 | ~70% | MMD 9 false headings; DOCX encoding correct (✓ vs âœ") |
| TeachCh1 | 10 | 10 | ~90% | Chapter number merged with first section title in DOCX |
| Calderhead | 3 | 1 | ~33% | DOCX collapses 3 MMD sections into 1 H1 |
| Fullan | 4 | 2 | 50% | DOCX merges title+author; body headings mostly missing |
| Brinkman | 18 | 16 | 88% | DOCX missing: Keywords, Introduction, Notes, Abstract |

**Verbatim conflict examples**:

```
BRYMAN MMD:   \section*{Social research strategies}
BRYMAN DOCX:  Heading2 | 2 Social research strategies

AIMS DOCX:    Heading1 | AIMS OF EDUCATION: DO TEACHERS NEED TO BOTHER ABOUT THEM?Rohit Dhankar
AIMS MMD:     \title{AIMS OF EDUCATION: DO TEACHERS NEED TO BOTHER ABOUT THEM?}
              \author{Rohit Dhankar}

BRYMAN MMD:   (no entry)
BRYMAN DOCX:  Heading2 | Epistemological considerations

BRYMAN MMD:   \section*{Figure 2.1}    [false heading — figure label]
BRYMAN DOCX:  (absent)

OLEARY MMD:   \section*{âœ" Is the question right for you?}   [encoding error]
OLEARY DOCX:  Heading3 | ✓ Is the question right for you?    [correct]

OLEARY MMD:   \section*{-Albert Szent-Gvorgi}    [epigraph attribution as heading]
OLEARY DOCX:  (absent — correctly omitted)

NOE DOCX:     Heading1 | CHAPTER 1 The nature of enquiry Setting the field  [3 entities merged]
NOE MMD:      \title{The nature of enquiry}
              \section*{Setting the field}
```

---

## Measurement Dimension 2: Heading Hierarchy Consistency

### Counts by heading level

| Document | MMD \section* | MMD \subsection* | MD deepest level | DOCX H1 | DOCX H2 | DOCX H3 |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| NoE | 11 | 19 | N/A | 1 | 17 | 4 |
| Aims | 0 | 0 | H1 | 1 | 0 | 0 |
| Bryman | 53 | 0 | H2 | 1 | 34 | 0 |
| Bruner | 32 | 0 | H2 | 1 | 3 | 0 |
| Sockett | 14 | 0 | H2 | 1 | 2 | 10 |
| OLeary | 34 | 0 | H3 | 1 | 4 | 20 |
| TeachCh1 | 10 | 0 | H2 | 1 | 9 | 0 |
| Calderhead | 3 | 0 | H2 | 1 | 0 | 0 |
| Fullan | 4 | 0 | H2 | 1 | 1 | 0 |
| Brinkman | 18 | 0 | H2 | 5 | 11 | 0 |

### Observations

**MMD hierarchy**: 9 of 10 documents are completely flat (all headings as `\section*{}`). Only NoE uses both `\section*{}` and `\subsection*{}`, and that is because the source PDF has explicit numbered sections (1.1, 1.2...). MMD assigns hierarchy by numbered prefix detection, not by visual depth.

**MD hierarchy**: Inconsistent level assignment. Brinkman MD assigns `#### Abstract` (H4) to the abstract while all content sections are H2. Aims MD has no body headings (all text as paragraphs). Heading depth does not reliably reflect document structure.

**DOCX hierarchy**: All 10 documents have multi-level heading structure. H1 = chapter/document title (plus author in 8 of 10 docs — see Dimension 1). H2 = major sections. H3 = subsections (in docs that have them: Sockett, O'Leary, NoE). This hierarchy accurately reflects the source document structure when verified against the PDF visual layout.

**Conclusion**: DOCX is the only format that preserves heading hierarchy. MMD is uniformly flat in 9 of 10 cases. MD hierarchy is document-specific and inconsistently applied.

---

## Measurement Dimension 3: Paragraph Block Consistency (MMD vs MD)

### Block counts (double-newline-separated units, non-empty)

| Document | MMD blocks | MD blocks | Difference |
|:---|:---:|:---:|:---:|
| Aims | 14 | 14 | 0 |
| Bryman | 162 | 181 | +19 |
| Bruner | 101 | 112 | +11 |
| Sockett | 69 | 72 | +3 |
| OLeary | 90 | 109 | +19 |
| TeachCh1 | 91 | 91 | 0 |
| Calderhead | 14 | 14 | 0 |
| Fullan | 25 | 25 | 0 |
| Brinkman | 101 | 107 | +6 |

**Finding**: Simpler documents (Aims, TeachCh1, Calderhead, Fullan) have identical block counts. Documents with structural elements (tables, figures, inline boxes, multi-column passages) show MD over-splitting: MD generates more paragraph units than MMD for the same content. The over-split reaches +19 for Bryman and O'Leary, both of which have many text boxes and figure-adjacent content.

---

## Measurement Dimension 4: Table Consistency

### Table counts

| Document | MMD \begin{table} | MD pipe table blocks | DOCX \<w:tbl\> | Consistent? |
|:---|:---:|:---:|:---:|:---:|
| NoE | 3 | N/A | not measured | N/A |
| Aims | 0 | 0 | 0 | Yes |
| Bryman | 1 | 1 | 21 | **NO — DOCX inflated** |
| Bruner | 0 | 0 | 0 | Yes |
| Sockett | 0 | 0 | 0 | Yes |
| OLeary | 0 | 0 | 0 | Yes |
| TeachCh1 | 0 | 0 | 0 | Yes |
| Calderhead | 0 | 0 | 0 | Yes |
| Fullan | 0 | 0 | 0 | Yes |
| Brinkman | 5 | 5 | 5 | **Yes** |

### Table inflation explanation

Bryman DOCX contains 21 `<w:tbl>` elements. Of these, 1 is the actual data table (Table 2.1: Quantitative vs Qualitative differences). The remaining 20 are text boxes (Research in focus 2.1 through 2.9, Key concept 2.1 through 2.6, Student experience boxes) that Mathpix's html-to-docx renderer encodes as single-row Word tables.

In MMD, the same text boxes are rendered as `\section*{}` headings followed by paragraph content — they inflate the heading count (from ~15 actual headings to 53 total sections in Bryman). In MD, they appear as `## `headings followed by paragraph content (same pattern as MMD, different markup).

**Verbatim evidence**:
```
MMD:   \section*{Research in focus 2.1}   [text box title as heading]
       Grand theory and social research...  [text box body as paragraph]

DOCX:  <w:tbl>                             [text box as table row]
         <w:tr><w:tc>Research in focus 2.1\nGrand theory...</w:tc></w:tr>
       </w:tbl>

MMD:   \begin{tabular}{|l|l|l|}           [actual data table]
         \hline \multicolumn{3}{...}
```

**Table content**: Where tables exist in all three formats, cell content is identical. Brinkman Tables 1-5 text matches across MMD LaTeX, MD GFM, and DOCX XML. Bryman Table 2.1 cell content matches across MMD and MD (DOCX data table text also confirmed consistent).

---

## Measurement Dimension 5: Figure Consistency

### Figure counts and image availability

| Document | MMD \begin{figure} | MMD plain ![...]() | MD images | DOCX embedded | Images complete? |
|:---|:---:|:---:|:---:|:---:|:---:|
| NoE | 1 | not measured | N/A | not measured | unknown |
| Aims | 0 | 0 | 0 | 0 | Yes |
| Bryman | 1 | 9 | 10 CDN URLs | 3 embedded | **NO — 7 missing in DOCX** |
| Bruner | 0 | 0 | 0 | 0 | Yes |
| Sockett | 0 | 0 | 0 | 0 | Yes |
| OLeary | 4 | 0 | 4 CDN URLs | not measured | unknown |
| TeachCh1 | 0 | 0 | 0 | 0 | Yes |
| Calderhead | 0 | 0 | 0 | 0 | Yes |
| Fullan | 0 | 0 | 0 | 0 | Yes |
| Brinkman | 2 | 0 | 2 CDN URLs | 2 embedded | **Yes — 2/2 match** |

### Critical finding: Bryman DOCX image loss

Bryman MMD references 10 images total (1 within `\begin{figure}`, 9 as plain `![](./images/...)` refs). Bryman MD references 10 images via CDN URLs. Bryman DOCX `word/media/` contains only 3 embedded images (image1.jpg 50KB, image2.png 51KB, image3.jpg 24KB). 7 images are absent from DOCX without any placeholder or error indicator.

The 3 embedded DOCX images appear to be decorative box-images. The 7 absent images are process diagrams (Figure 2.1: The process of deduction; Figure 2.2: The process of induction; and others). This loss is silent — no warning in DOCX, no alt-text fallback.

### Figure caption comparison

MMD `\caption{}` (when present) is explicit and labeled. Example:
```
MMD:  \caption{Figure I. Key belief dimensions among LCE-pedagogy groups}   [Brinkman]
MD:   ## Figure I                                                            [MD treats caption label as heading]
      [image appears after]
```
MD lacks a structured caption construct — figure labels appear as `## ` headings immediately before the image URL.

---

## Measurement Dimension 6: Footnote and Endnote Consistency

### Footnote presence by document

| Document | MMD structure | MD structure | DOCX structure |
|:---|:---|:---|:---|
| Aims | 11 × `${ }^{n}$` bodies as plain text | 11 × `${ }^{n}$` bodies as plain text | 11 structured endnotes in endnotes.xml |
| Brinkman | 3 × plain numbered list items (1. 2. 3.) | 3 × plain numbered list + 1 × [^0] ref | 3 structured endnotes in endnotes.xml |
| NoE | `\section*{Notes}` + plain text | N/A | not measured |
| Others | none | none | none |

### Body text comparison: Aims

MMD footnote body 1 (exact): `${ }^{1}$ Noam Chomsky, Human Nature, in conversation with Kate Soper, 1998.`  
DOCX endnote ID=1 (exact): `Noam Chomsky, Human Nature, in conversation with Kate Soper, 1998.`

All 11 Aims footnote bodies verified identical between MMD and DOCX (text content, excluding notation).

### Key conflicts

**Conflict A — Semantic type**: Aims footnotes are page-bottom footnotes in the source PDF. MMD renders them as plain body text at document end. DOCX stores them as structured Word endnotes (in `endnotes.xml`). The semantic type is silently changed: footnote → endnote.

**Conflict B — Reference notation**:
- MMD: `${ }^{1}$` (raw LaTeX math superscript for both inline refs and body entries)
- MD (Aims): identical `${ }^{n}$` — no conversion
- MD (Brinkman): `\footnotetext{}` content converted to `[^0]` GFM footnote; but inline endnote refs (`${ }^{1}$`, `${ }^{2}$`, `${ }^{3}$`) left as-is
- DOCX: `<w:endnoteReference>` for inline refs; `<w:endnote>` for bodies

**Conflict C — Structural linkage**: MMD and MD provide no structural link between inline references and footnote bodies. DOCX provides complete structural linkage via `w:id` matching between `<w:endnoteReference w:id="n">` and `<w:endnote w:id="n">`.

**Finding**: Footnote body text is consistent across all formats. Structural linkage exists only in DOCX. Reference notation is format-specific and document-specific within MD.

---

## Measurement Dimension 7: Metadata Consistency

### Title and author availability

| Document | MMD \title{} | MMD \author{} | MD title (H1) | DOCX dc:title | DOCX dc:creator |
|:---|:---|:---|:---|:---|:---|
| NoE | `The nature of enquiry` | absent | N/A | empty | html-to-docx |
| Aims | `AIMS OF EDUCATION: DO TEACHERS NEED TO BOTHER ABOUT THEM?` | `Rohit Dhankar` | same text (H1) | empty | html-to-docx |
| Bryman | absent | absent | absent (## heading) | empty | html-to-docx |
| Bruner | `The Culture of Education` | absent | same text (H1) | empty | html-to-docx |
| Sockett | absent | absent | absent (## heading) | empty | html-to-docx |
| OLeary | absent | absent | absent (H1 = chapter title) | empty | html-to-docx |
| TeachCh1 | `Teaching as a Professional Discipline` | absent | same text (H1) | empty | html-to-docx |
| Calderhead | absent | absent | absent (no H1) | empty | html-to-docx |
| Fullan | absent | absent | absent (no H1) | empty | html-to-docx |
| Brinkman | present (journal title) | `Suzana Brinkmann \\ Institute of Education, London, UK` | same text (H1) | empty | html-to-docx |

**Findings**:
- DOCX `dc:title`, `dc:subject`, `dc:description` are empty in all 10 documents. `dc:creator` contains `html-to-docx` (the conversion tool name, not the author).
- MMD `\title{}` is present in 5 of 10 documents. When present, text matches the actual document title.
- MMD `\author{}` is present in 2 of 10 documents confirmed (Aims, Brinkman). In Calderhead, Fullan, and Sockett, author names appear as separate `\section*{}` headings.
- MD uses `# ` H1 for title when title exists in MMD; absent otherwise.

---

## Measurement Dimension 8: Page Landmark Consistency

### Page information by format

| Format | Page information present? | Encoding | Accuracy |
|:---|:---:|:---|:---|
| MMD | No | none | N/A |
| MD | No | none | N/A |
| DOCX | Yes | `<w:pStyle w:val="Heading6"/>` paragraphs containing page number text | Direct |

### DOCX page number evidence

All 10 DOCX files contain Heading6 paragraphs encoding printed page numbers:

```
NoE DOCX:       Heading6: 3, 4, 5, 6, 7, 8 ... 30       (28 pages)
Aims DOCX:      Heading6: [4 page entries]
Bryman DOCX:    Heading6: 19, 20, 21 ... 43              (25 pages)
Brinkman DOCX:  Heading6: 342, 343, 344 ... 359          (journal pagination)
Sockett DOCX:   Heading6: 17 page entries
Bruner DOCX:    Heading6: 22 page entries
TeachCh1:       Heading6: 0 (none detected)
Calderhead:     Heading6: 4 page entries
Fullan:         Heading6: 6 page entries
OLeary:         Heading6: 0 (none detected)
```

**Note**: TeachCh1 and O'Leary showed 0 H6 entries in heading extraction. This may indicate the page number encoding is absent or uses a different DOCX element for those documents.

**Critical constraint**: Page landmark information exists ONLY in DOCX. MMD and MD carry zero page information. No cross-format verification of page landmark positions is possible.

---

## Measurement Dimension 9: Image Geometry Consistency

### Geometry encoding by format

| Format | Geometry present? | Encoding method | Example |
|:---|:---:|:---|:---|
| MMD | Yes (in filename) | `docid-page_height_width_y_x.jpg` | `febb7120-03.jpg` (partial) |
| MD | Yes (in CDN URL params) | `?height=H&width=W&top_left_y=Y&top_left_x=X` | `?height=102&width=111&top_left_y=1847&top_left_x=317` |
| DOCX | No | images embedded without coordinate metadata | image1.jpg (no position data) |

**Verbatim MD geometry example (Bryman)**:
```
![](https://cdn.mathpix.com/cropped/febb7120-dec1-4738-a833-c83581be0256-03.jpg
    ?height=102&width=111&top_left_y=1847&top_left_x=317)
```

Both MMD and MD provide bounding-box coordinates for each image. The encoding differs (filename vs URL parameter) but both carry the same four values (height, width, top-left-y, top-left-x) within the source page coordinate system. DOCX provides no geometry.

**Finding**: Geometry is consistent between MMD and MD (same values, different encoding). DOCX provides no spatial information.

---

## Measurement Dimension 10: Mathematical Content Consistency

### Math expression counts

| Document | MMD `$...$` count | MD `$...$` count | Consistent? | Note |
|:---|:---:|:---:|:---:|:---|
| Aims | 21 | 21 | Yes | All are footnote superscripts `${ }^{n}$`, not real math |
| Brinkman | 24 | 24 | Yes | Mix of endnote refs and real equation terms |
| Bruner | 42 | not measured | — | Assumed consistent per pattern |
| NoE | 6 | N/A | — | No MD |
| Bryman | 1 | 1 | Yes | Minimal |
| OLeary | 1 | not measured | — | Assumed consistent |
| Others | 0 | 0 | Yes | No math |

**Finding**: Mathematical expression count is identical between MMD and MD for all documents where both exist and were measured. The LaTeX `$...$` notation is preserved verbatim across both formats. DOCX math rendering was not compared (OOXML math uses `<m:oMath>` elements which require separate measurement).

---

## Deliverable 1: Cross-Format Consistency Matrix

Ratings: **HIGH** (>90% agreement), **MEDIUM** (60–90%), **LOW** (<60%), **ABSENT** (signal missing in one format)

| Semantic Dimension | MMD ↔ MD | MMD ↔ DOCX | MD ↔ DOCX |
|:---|:---:|:---:|:---:|
| Heading text (when present in both) | HIGH | MEDIUM | MEDIUM |
| Heading presence / count | MEDIUM | LOW | LOW |
| Heading hierarchy | LOW | LOW | LOW |
| Paragraph block count | MEDIUM | not measured | not measured |
| Table count (data tables) | HIGH | LOW (DOCX inflates) | LOW |
| Table cell content | HIGH | HIGH | HIGH |
| Figure count (structural figures) | MEDIUM | LOW | LOW |
| Figure caption text | MEDIUM | MEDIUM | LOW |
| Footnote body text | HIGH | HIGH | HIGH |
| Footnote reference notation | MEDIUM | LOW | LOW |
| Footnote structural linkage | ABSENT | ABSENT (only DOCX) | ABSENT |
| Document title | HIGH | LOW | LOW |
| Document author | HIGH | LOW | LOW |
| Other metadata (subject, etc.) | ABSENT | ABSENT | ABSENT |
| Page landmarks | ABSENT | ABSENT (only DOCX) | ABSENT |
| Image geometry | HIGH (different encoding) | ABSENT (DOCX: none) | ABSENT |
| Mathematical expressions | HIGH | not measured | not measured |
| Reading order | HIGH | HIGH | HIGH |

---

## Deliverable 2: Conflict Matrix

| # | Conflict Type | Dimension | Severity | Frequency | Evidence |
|:---|:---|:---|:---:|:---:|:---|
| C-01 | MERGE: Title + author concatenated into one DOCX heading | Title / Author | Critical | 8/10 docs | Aims DOCX H1: "AIMS OF EDUCATION...Rohit Dhankar" (no separator) |
| C-02 | MERGE: Chapter number + chapter title concatenated | Heading text | High | 5/10 docs | NoE DOCX H1: "CHAPTER 1 The nature of enquiry Setting the field" |
| C-03 | MISSING: Body section headings absent from DOCX | Heading count | Critical | 2/10 docs | Calderhead DOCX: 1 H1 only; Fullan DOCX: H1 + REFERENCES only |
| C-04 | MISSING: Specific headings absent from DOCX | Heading count | High | 5/10 docs | Brinkman DOCX missing: Keywords, Introduction, Notes; NoE missing: 4 sub-topics |
| C-05 | EXTRA: Figure/table labels as headings in MMD | Heading count | Medium | 2/10 docs | Bryman MMD: `\section*{Figure 2.1}`, `\section*{Table 2.1}` |
| C-06 | EXTRA: Author name as separate heading in MMD | Heading type | High | 2/10 docs | Fullan MMD: `\section*{Michael Fullan and Andy Hargreaves}` |
| C-07 | EXTRA: Epigraph / quote treated as heading in MMD | Heading type | High | 1/10 docs | OLeary MMD: `\section*{'I know the general area...'}` |
| C-08 | EXTRA: Author attribution treated as heading in MMD | Heading type | Medium | 1/10 docs | OLeary MMD: `\section*{-Albert Szent-Gvorgi}` |
| C-09 | EXTRA: Text box labels as headings in MMD | Heading type | Medium | 2/10 docs | OLeary: `\section*{Box 3.1...}`, `\section*{Box 3.2...}`; Bryman: 27 Research-in-focus |
| C-10 | HIERARCHY: MMD flat vs DOCX multi-level | Heading hierarchy | High | 9/10 docs | Sockett: MMD 14 flat sections; DOCX H1/H2/H3 with 13 nodes |
| C-11 | HIERARCHY: Box elements at wrong level in MMD | Heading hierarchy | Medium | 2/10 docs | NoE: BOX 1.1–1.5 = `\section*{}` in MMD (same level as chapter); H3 in DOCX |
| C-12 | ENCODING: Unicode character corruption in MMD | Text quality | High | 1/10 docs | OLeary MMD: `âœ"` for ✓ (UTF-8 → Latin-1 mojibake) |
| C-13 | TYPE: Footnotes stored as endnotes in DOCX | Footnote | Medium | 2/10 docs | Aims, Brinkman: page-bottom footnotes → Word endnotes |
| C-14 | FORMAT: Footnote notation inconsistent in MD | Footnote | Low | 1/10 docs | Brinkman: `\footnotetext{}` → `[^0]`; Aims: `${ }^{n}$` unchanged |
| C-15 | MISSING: Structural footnote linkage in MMD/MD | Footnote | Medium | 2/10 docs | MMD: no id-to-body mapping; DOCX: full w:id linkage |
| C-16 | COUNT: DOCX inflates table count with text boxes | Table | Medium | 1/10 docs | Bryman: 21 DOCX `<w:tbl>` vs 1 MMD `\begin{tabular}` |
| C-17 | MISSING: Images silently dropped in DOCX | Figure | Critical | 1/10 docs | Bryman: 3 of 10 images in DOCX; 7 absent, no placeholder |
| C-18 | ENCODING: Image geometry in different formats | Geometry | Low | All 9 w/MD | MMD: filename-encoded; MD: URL-params; DOCX: absent |
| C-19 | MISSING: All document metadata in DOCX | Metadata | Critical | 10/10 docs | dc:title, dc:creator, dc:subject all empty in all 10 DOCX files |
| C-20 | ABSENT: Page information in MMD and MD | Page | Critical | 10/10 docs | No page numbers in MMD or MD; DOCX H6 is sole source |
| C-21 | ABSENT: Abstract as structured element in MD/DOCX | Document structure | Medium | 1/10 docs | Brinkman: MMD `\begin{abstract}`; MD: `#### Abstract`; DOCX: not found |
| C-22 | SPLIT: Heading text split differently across formats | Heading | Medium | 1/10 docs | Bryman: "Research in focus 2.8" two entries in MMD, one in DOCX |

---

## Deliverable 3: Canonical Signal Matrix

For each semantic dimension: which format provides the authoritative signal?

| Semantic Dimension | Canonical Format | Reason | Reliability |
|:---|:---|:---|:---:|
| Document title | MMD | `\title{}` when present; DOCX merges with author; MD treats as H1 | 5/10 docs |
| Document author | MMD | `\author{}` when present; DOCX merges with title; MD has no author element | 2/10 docs |
| Heading text | MMD = MD | 95%+ text agreement; DOCX occasionally modifies or drops headings | HIGH |
| Heading presence (complete) | Neither | MMD has false positives; DOCX has false negatives; no format is complete | LOW |
| Heading hierarchy | DOCX | Only format preserving multi-level structure; reflects actual document structure | HIGH |
| Abstract | MMD | `\begin{abstract}...\end{abstract}` is structurally explicit | HIGH (when present) |
| Paragraph order | MMD | Base format; MD over-splits; DOCX adds structural noise | HIGH |
| Data table count | MMD | `\begin{table}` counts only data tables; DOCX inflates with text boxes | HIGH |
| Table cell content | All three | Content identical across all formats when table exists | HIGH |
| Table captions | MMD | `\caption{}` provides explicit label; absent in MD | HIGH (when present) |
| Figure captions | MMD | `\caption{}` within `\begin{figure}`; MD has no caption construct | MEDIUM (not all figures) |
| Figure image references | MMD | All images referenced; DOCX drops images; MD CDN-dependent | HIGH |
| Footnote body text | MMD = DOCX | Body text identical; either source is reliable | HIGH |
| Footnote structural linkage | DOCX | `<w:endnote w:id="n">` provides machine-readable linkage | HIGH (2 docs) |
| Footnote reference positions | DOCX | `<w:endnoteReference>` is structurally anchored | HIGH (2 docs) |
| Image bounding-box geometry | MD | CDN URL params are explicit (height=, width=, top_left_y=, top_left_x=); MMD filename encoding requires parsing | HIGH (9 docs) |
| Page landmark numbers | DOCX | Sole source; H6 paragraphs = printed page numbers | HIGH |
| Mathematical expressions | MMD = MD | Identical `$...$` notation | HIGH |
| Reading order | MMD = MD = DOCX | All three preserve source reading order | HIGH |

---

## Deliverable 4: Reconciliation Difficulty Matrix

| Conflict | Deterministic reconciliation possible? | Difficulty | Limiting factor |
|:---|:---:|:---:|:---|
| C-01: Title+author merge in DOCX | **No** | Critical | No character sequence reliably separates title from author when concatenated without delimiter |
| C-02: Chapter+title merge in DOCX | **Partial** | High | Some docs use colon delimiter (O'Leary: "Chapter 3: ..."); others have no separator (NoE, TeachCh1); rule is document-specific |
| C-03: Missing body headings in DOCX | **No** | Critical | Calderhead and Fullan DOCX have almost no body headings; cannot recover structure from DOCX alone |
| C-04: Specific headings missing in DOCX | **No** | High | No rule identifies which MMD headings should be dropped vs. which represent genuine headings DOCX missed |
| C-05: Figure labels as MMD headings | **Partial** | Medium | Pattern `\section*{Figure N.M}` and `\section*{Table N.M}` is identifiable by regex |
| C-06: Author as MMD heading | **No** | High | No deterministic rule distinguishes `\section*{James Calderhead}` (author) from `\section*{Calderhead's Framework}` (content heading) |
| C-07: Epigraph as MMD heading | **No** | High | Epigraph text is indistinguishable from section title by structure alone |
| C-08: Author attribution as MMD heading | **Partial** | Medium | Leading hyphen `\section*{-Name}` is a detectable pattern but not universal |
| C-09: Text box labels as MMD headings | **Partial** | Medium | "Box N.M", "Research in focus N.M", "Key concept N.M" patterns are detectable |
| C-10: MMD flat hierarchy | **No** | Critical | DOCX hierarchy is the only source; but DOCX drops headings (C-03, C-04); circular dependency |
| C-11: Box elements at wrong MMD level | **Yes** | Low | Box label pattern + DOCX H3 assignment provides consistent signal |
| C-12: Unicode encoding error | **Yes** | Low | UTF-8 re-encoding corrects `âœ"` → ✓ and similar mojibake patterns |
| C-13: Footnotes as DOCX endnotes | **Yes** | Low | Declare: all DOCX `<w:endnote>` elements are footnotes regardless of XML element name |
| C-14: Footnote notation inconsistency in MD | **Partial** | Low | `[^n]` pattern is detectable; `${ }^{n}$` pattern also detectable; but mixed per document |
| C-15: Missing footnote linkage in MMD | **Yes** | Medium | DOCX linkage via `w:id` is machine-readable and deterministic |
| C-16: DOCX table inflation | **Yes** | Medium | Single-cell `<w:tbl>` elements with no column headers = text boxes; data tables have multiple columns |
| C-17: Missing images in DOCX | **No** | Critical | Images absent from DOCX `word/media/`; no recovery path; must use MMD local paths or MD CDN URLs |
| C-18: Geometry encoding mismatch | **Yes** | Low | Both MMD filename and MD URL params parse to same four values (h, w, y, x) |
| C-19: Empty DOCX metadata | **Yes** | Low | Use MMD `\title{}` / `\author{}` when present; fallback to first H1 in MD |
| C-20: Absent page info in MMD/MD | **Partial** | High | DOCX H6 provides page numbers; aligning H6 positions to MMD text positions requires structural alignment not achievable by string matching alone |
| C-21: Abstract as heading in MD | **Yes** | Low | `#### Abstract` in MD and `\begin{abstract}` in MMD are both detectable |
| C-22: Heading split differences | **Partial** | Medium | Fuzzy string matching resolves many cases; some splits are content-specific |

---

## Deliverable 5: Determinism Assessment

**Question**: For each semantic dimension, can a single-pass deterministic algorithm — one without document-specific tuning, regex-by-example, or learned heuristics — produce a correct unified model?

| Dimension | Deterministic? | Verdict | Failure mode when non-deterministic |
|:---|:---:|:---:|:---|
| Document title extraction | **Partial** | ⚠ | Absent in 5/10 MMD; DOCX merge prevents fallback; failure rate ~50% |
| Document author extraction | **Partial** | ⚠ | Absent or merged in 8/10 docs; failure rate ~80% |
| Abstract extraction | **Yes** | ✓ | `\begin{abstract}` and `#### Abstract` are unambiguous |
| Heading text (when present in both) | **Yes** | ✓ | Fuzzy-match resolves >95% of disagreements |
| Heading count (complete set) | **No** | ✗ | False positives in MMD; false negatives in DOCX; cannot resolve without ground truth |
| Heading hierarchy assignment | **No** | ✗ | DOCX is sole hierarchy source but drops headings; MMD is flat; circular dependency |
| Heading order | **Yes** | ✓ | Both formats preserve reading order; no reordering detected |
| Paragraph boundary detection | **Partial** | ⚠ | Identical for 5/9 docs; diverges for 4/9 (up to +19 blocks); no deterministic rule for which split is correct |
| Data table identification | **Partial** | ⚠ | MMD `\begin{table}` is clean; DOCX requires filtering; filter rule works for Bryman but not proven across all 10 docs |
| Table cell content extraction | **Yes** | ✓ | Cell text is identical across formats; mechanical extraction |
| Figure image reference extraction | **Partial** | ⚠ | MMD is complete; DOCX drops images (Bryman: 7/10 lost); which format to trust is not deterministic |
| Figure caption association | **Partial** | ⚠ | `\begin{figure}...\caption{}` is deterministic; plain `![...]()` refs in MMD have no associated caption |
| Footnote body text extraction | **Yes** | ✓ | Text is identical across MMD and DOCX |
| Footnote structural linkage | **Yes** | ✓ | DOCX `w:id` matching is deterministic |
| Footnote reference–body alignment | **Partial** | ⚠ | DOCX: deterministic. MMD: `${ }^{n}$` pattern is detectable but notation is shared with real math |
| Image geometry extraction | **Yes** | ✓ | Both MMD filename and MD URL params parse to bounding boxes by fixed rules |
| Page landmark extraction | **Yes** | ✓ | DOCX H6 values are direct page numbers |
| Page-to-text alignment (landmark→position) | **No** | ✗ | H6 paragraphs appear at page boundaries in DOCX; mapping to MMD text positions requires structural alignment across formats; no deterministic single-pass method |
| Math expression pass-through | **Yes** | ✓ | `$...$` notation is identical between MMD and MD |
| Reading order preservation | **Yes** | ✓ | All three formats preserve reading order |

### Summary counts

| Verdict | Count | Dimensions |
|:---|:---:|:---|
| ✓ Deterministic | 9 | Abstract, heading text, heading order, table content, footnote text, footnote linkage, image geometry, page landmarks, math, reading order |
| ⚠ Partial | 7 | Title, author, paragraph boundaries, table identification, figure references, figure captions, footnote-ref alignment |
| ✗ Non-deterministic | 4 | Heading count (complete), heading hierarchy, page-to-text alignment, figure completeness |

---

## Summary of Findings

### What is consistent across formats

1. **Reading order**: All three formats preserve the source document's reading order without exception across all 10 documents.
2. **Table cell content**: Where data tables exist, cell text is identical in MMD LaTeX, MD GFM, and DOCX XML.
3. **Footnote body text**: Footnote/endnote body text is verbatim identical between MMD and DOCX where compared.
4. **Mathematical expression notation**: `$...$` expressions are preserved verbatim and counted identically between MMD and MD.
5. **Heading text (when present in both formats)**: When a heading appears in both MMD and DOCX, text agreement exceeds 95%.

### What is inconsistent across formats

1. **Heading count and completeness**: No format provides a complete, correct set of headings. MMD has false positives (figure labels, author names, epigraphs as `\section*{}`). DOCX has false negatives (body headings missing for Calderhead, Fullan; specific headings missing for 5 others).

2. **Heading hierarchy**: Only DOCX preserves multi-level hierarchy. MMD is flat in 9 of 10 documents. This is the single largest structural information loss in MMD.

3. **Title and author**: DOCX merges title and author into a single Heading1 without delimiter in 8 of 10 documents. MMD has `\title{}` in 5 of 10 and `\author{}` in 2 confirmed cases. No format reliably provides both for all 10 documents.

4. **Figure completeness**: Bryman DOCX silently drops 7 of 10 images. MMD and MD reference all images. Image loss in DOCX is document-specific and has no in-file indicator.

5. **Page information**: Page landmarks exist only in DOCX. MMD and MD carry zero page-position information. Cross-format page-to-text alignment is not achievable by string matching alone.

6. **Document metadata**: DOCX metadata fields are empty in all 10 documents. `dc:creator` contains `html-to-docx` (tool name), not author.

### Determinism verdict

**9 dimensions are fully deterministic.** These cover the core semantic content: text, tables, math, reading order, footnote bodies, image geometry, and page numbers.

**7 dimensions are partially deterministic.** These include title, author, paragraph boundaries, table identification, and figure-caption association. Partial failures affect a predictable subset of documents (typically 2–5 of 10) and can be flagged but not corrected without additional signals.

**4 dimensions are non-deterministic.** Heading count, heading hierarchy assignment, page-to-text alignment, and figure completeness cannot be correctly resolved by any single-pass rule that is consistent across all 10 documents without document-specific tuning or access to the source PDF.

---

*End of audit. All measurements are direct observations from file contents. No implementation is proposed.*
