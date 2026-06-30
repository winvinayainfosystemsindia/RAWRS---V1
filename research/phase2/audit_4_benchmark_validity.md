# RAWRS Phase-2 Audit: Benchmark Validity, Coverage & Representativeness

**Date**: 2026-06-26  
**Method**: Strictly evidence-based. All classifications and measurements derived from direct file inspection. No speculation.  
**Corpus**: 10 benchmark PDFs with corresponding MMD, MD (9 of 10), and DOCX exports.  
**Scope**: Scientific evaluation of the benchmark corpus itself — coverage, diversity, bias, and confidence.

---

## Deliverable 1: Benchmark Composition Matrix

Classifications are derived from observable evidence: pagination style, document structure, presence of abstract/keywords/author affiliation, publisher signals, companion website references, chapter numbering conventions, and reference formatting.

| Document | Type | Domain | PDF Size | Page Count | Words (MMD) | Column Layout | Key Structural Features |
|:---|:---|:---|---:|---:|---:|:---|:---|
| Nature of Enquiry (NoE) | Textbook chapter | Educational research | 0.76 MB | 28 | 20,866 | Single | Numbered sections 1.1–1.18; 5 BOX elements; Companion website |
| Aims of Education — Dhankar | Journal essay | Philosophy of education | 0.02 MB | 4 | 2,298 | Single | 11 page-bottom footnotes; explicit journal citation at foot |
| Social Research Strategies — Bryman | Textbook chapter | Research methods | 30.83 MB | 25 | 16,207 | Single | 18 text boxes; TOC with bookmarks; review questions; online resource centre |
| Folk Pedagogy — Bruner | Book chapter | Education psychology | 2.49 MB | 22 | 9,167 | Single | 36 numbered endnotes; chapter from "The Culture of Education" |
| Sockett — The Profession | Book chapter | Teacher professionalism | 7.63 MB | 17 | 7,504 | Single | 3-level heading hierarchy; case study subsections |
| O'Leary — Research Questions | Textbook chapter | Research methods | 10.92 MB | unknown | 5,065 | Single | 4 concept-map figures; checklists; boxed features |
| Teaching as Professional Discipline Ch1 | Book chapter | Teacher education | 0.17 MB | unknown | 11,662 | Single | Cover-page image embedded; 9 conceptual sections |
| Calderhead — Teaching as Professional Activity | Book chapter | Teacher professionalism | 0.10 MB | 4 | 1,615 | Single | Extremely short; from edited volume |
| Fullan & Hargreaves — Teacher as a Person | Book chapter | Teacher professionalism | 0.09 MB | 6 | 2,303 | Single | Co-authored; from edited volume |
| Brinkman — Learner-Centred Education | Journal article | Educational research | 0.29 MB | 18 (pp.342–359) | 8,859 | Likely 2-column† | Abstract/keywords/affiliation; 5 data tables; 3 endnotes; APA references |

**†Multi-column inference**: Brinkman images show p06 figure at width=727 and p12 figure at width=1157 within a Mathpix coordinate space. The ratio (narrow single-column figure vs. wide two-column-spanning figure) is consistent with standard journal 2-column layout. This is geometric inference, not direct observation.

### Type and Domain Distribution

| Category | Count | Documents |
|:---|:---:|:---|
| Textbook chapter (research methods) | 3 | NoE, Bryman, O'Leary |
| Book chapter (edited academic volume) | 4 | Sockett, Calderhead, Fullan, Bruner |
| Book chapter (single-authored academic book) | 1 | TeachCh1 |
| Journal article | 2 | Brinkman, Aims |
| **Domain: Education / Teaching / Educational Research** | **10/10** | **ALL** |
| Domain: STEM | 0 | — |
| Domain: Law | 0 | — |
| Domain: Medicine | 0 | — |
| Domain: Government / Policy | 0 | — |
| Domain: Business / Finance | 0 | — |
| Language: English | 10/10 | ALL |
| Language: Non-English | 0 | — |
| Layout: Single-column | 9 | All except Brinkman |
| Layout: Multi-column | 1 (likely) | Brinkman |
| PDF origin: Born-digital or clean scan | 10 | ALL |
| PDF origin: Low-quality scan / OCR-dependent | 0 | — |

---

## Deliverable 2: Feature Coverage Matrix

### Structural features

| Feature | Docs present | Count | Docs absent | Represented? |
|:---|:---:|:---:|:---:|:---:|
| Data tables | 3 | 9 total tables | 7 | Partially |
| Tables with column-spanning headers (`\multicolumn`) | 2 | 3 occurrences | 8 | Partially |
| Tables with row-spanning cells (`\multirow`) | 0 | 0 | 10 | **Not represented** |
| Captioned figures (`\begin{figure}...\caption{}`) | 4 | 8 figures | 6 | Partially |
| Non-captioned plain image refs | 2 | 9 refs | 8 | Partially |
| Bullet lists | 4 | 128 items | 6 | Partially |
| Numbered lists | 5 | 77 items (incl. endnote bodies) | 5 | Partially |
| Nested lists (indented) | 0 | 0 | 10 | **Not represented** |
| Blockquotes | 5 | 25 occurrences | 5 | Partially |
| Text boxes (boxed inserts) | 3 | 25 total boxes | 7 | Partially |
| Footnotes (page-bottom, true) | 1 | 11 | 9 | Rarely |
| Endnotes (document-end) | 4 | 54 total | 6 | Partially |
| Abstract | 1 | 1 | 9 | Rarely |
| Author affiliation block | 1 | 1 | 9 | Rarely |
| Appendix | 0 | 0 | 10 | **Not represented** |
| Table of contents (in document) | 1 | 1 (Bryman only) | 9 | Rarely |
| Multi-column layout | 1 (likely) | 1 | 9 | Rarely |
| Real mathematical equations | 0 | 0 | 10 | **Not represented** |
| Numbered equations | 0 | 0 | 10 | **Not represented** |
| Chemical formulas | 0 | 0 | 10 | **Not represented** |
| Form fields | 0 | 0 | 10 | **Not represented** |
| Hyperlinks (external, semantic) | 0 | 0 | 10 | **Not represented** |
| Cross-references (`\ref{}`, `\cite{}`) | 0 | 0 | 10 | **Not represented** |
| In-document navigation links | 1 | 40 (Bryman TOC) | 9 | Rarely |
| Index / glossary | 0 | 0 | 10 | **Not represented** |
| Review questions / exercises | 1 | 1 (Bryman) | 9 | Rarely |

### Accessibility-specific features

| Accessibility Feature | Docs present | Notes |
|:---|:---:|:---|
| Informative images requiring alt text | 5 | Concept maps (O'Leary), research diagrams (Bryman), bar charts + framework (Brinkman), NoE, TeachCh1 cover |
| Decorative images | Unknown | No format provides sufficient signal to classify images as decorative |
| Images with AI-generated alt text (DOCX) | 4 | Brinkman, Bryman, O'Leary, TeachCh1 |
| Images with AI alt text corruption | 1 | O'Leary: 4/8 DOCX `descr` entries contain CDN URLs, not descriptions |
| Images with no alt text in any format | 10 | MMD and MD: 100% empty `alt=''` |
| Complex multi-column data tables | 1 | NoE: 24-row conceptual matrix (Subjective/Objective dimensions) |
| Simple grid data tables | 3 | Brinkman Tables 1–5; Bryman Table 2.1; NoE Table 1.1 |
| Table headers (first-row or first-column) | 3 | Present but not marked with semantic header attributes in any format |
| Mathematical notation (accessibility-critical) | 0 | No real equations; only footnote-reference superscripts |
| Page navigation (landmarks) | 8 | DOCX H6 page numbers; absent in MMD/MD |
| Heading hierarchy (for navigation) | 10 (DOCX); 1 (MMD) | DOCX H1/H2/H3 present in all 10; MMD flat in 9/10 |
| Numbered sections (for skip navigation) | 1 | NoE only (numbered subsections 1.1–1.18) |
| Footnote/endnote linkage (for AT users) | 4 | DOCX `<w:endnote>` linkage in Aims, Brinkman, NoE, Bruner |
| Reading order (verified correct) | 10 | All 10 documents preserve source reading order |
| Document title signal | 5 | MMD `\title{}` in 5/10; absent in 5/10 |
| Language declaration | 0 | No format provides xml:lang or equivalent in any document |

---

## Deliverable 3: Corpus Bias Matrix

Each bias is stated with measured evidence. No speculation.

| Bias | Evidence | Severity |
|:---|:---|:---|
| **Domain monoculture: education only** | All 10 of 10 documents are from the education, teaching, and educational research domain. Zero documents from STEM, law, medicine, government, business, journalism, arts, or any other field. | Critical |
| **Document type: no reports or policy documents** | 0/10 documents are government reports, policy papers, white papers, or institutional publications. All are academic chapters or articles. | High |
| **Document type: no forms or structured data** | 0/10 documents have form fields, tables as primary content (invoices, spreadsheet exports, data sheets), or structured administrative documents. | High |
| **Language monoculture: English only** | All 10 documents are in English. 0 multilingual, 0 right-to-left scripts, 0 mixed-language. | Critical |
| **Layout bias: single-column dominance** | 9/10 documents are single-column. 1/10 (Brinkman) is likely 2-column. 3-column, newspaper-column, and magazine-column layouts are absent. | High |
| **Mathematical content: entirely absent** | 0/10 documents contain substantive mathematical equations, numbered formulas, matrices, or formal mathematical notation. The 67 `$...$` instances in the corpus are exclusively footnote reference superscripts (`${ }^{n}$`), not equations. | Critical — for STEM generalization |
| **Image type: conceptual diagrams only** | All images in the corpus are conceptual diagrams (concept maps, flowcharts, framework diagrams, bar charts). 0 photographs, 0 scientific plots with axes, 0 anatomical diagrams, 0 geographic maps, 0 equations-as-images. | High |
| **Publisher bias: academic publishing** | All documents are from academic publishers (Oxford University Press, Harvard University Press, Taylor & Francis, and similar). 0 government publications, 0 journalism, 0 self-published. | Medium |
| **Era bias: 1990s–2010s** | Observable publication dates: Aims (2002), Brinkman (~2012), Bruner (mid-1990s based on citations). All are relatively contemporary academic texts. 0 historical documents, 0 pre-digital-era sources. | Low |
| **Complexity bias: no low-quality scans** | All 10 PDFs appear to be born-digital or high-quality scans. 0 documents with low OCR confidence, handwriting, mixed scan quality, or degraded text. | Medium |
| **Size distribution skew** | PDF sizes: min=0.02 MB (Aims), max=30.83 MB (Bryman), ratio=1,540:1. Small documents (Aims 4 pages, Calderhead 4 pages) are likely unrepresentative of the full length range. Document length in words: min=1,615 (Calderhead), max=20,866 (NoE). The very short documents (3 documents under 3,000 words) may not stress heading extraction, list parsing, or multi-page layout handling. | Low |
| **No appendices** | 0/10 documents have appendices. Many academic texts have appendices (instruments, data, proofs). Appendix behavior is entirely untested. | Medium |
| **No external hyperlinks** | 0/10 documents contain semantic hyperlinks to external resources. The 40 hyperlinks in Bryman are internal TOC navigation links. | Low |
| **No nested list structures** | 0/10 documents contain nested (indented) lists. All 128 bullet items across the corpus are at the same depth (top-level only). | Medium |
| **Table complexity ceiling** | The most complex table is NoE's 24-row 3-column matrix with one `\multicolumn` header. No `\multirow`, no nested tables, no merged cells in non-header rows. | Medium |
| **Footnotes vs. endnotes: footnotes underrepresented** | Only 1/10 documents (Aims) has genuine page-bottom footnotes. Most footnote-like content is stored as endnotes in DOCX. The distinction is collapsed in all formats. | Low |

---

## Deliverable 4: Missing Coverage Matrix

The following document types and features are entirely absent from the benchmark. Each absence is stated from observation, not from assumed importance.

### Missing Document Types

| Missing Document Type | Evidence of Absence |
|:---|:---|
| STEM textbook (mathematics, physics, chemistry, biology) | 0/10 documents; 0 real mathematical equations in entire corpus |
| Scientific research paper with equations | 0/10 documents; the one journal article (Brinkman) is social science with no equations |
| Legal document (court ruling, contract, statute, brief) | 0/10 documents |
| Government report or policy document | 0/10 documents |
| Medical or clinical document | 0/10 documents |
| Financial document (invoice, statement, form) | 0/10 documents |
| Newspaper or magazine article | 0/10 documents |
| Non-English document | 0/10 documents |
| Multilingual document (mixed language) | 0/10 documents |
| Document with right-to-left script | 0/10 documents |
| Document with 3-column layout | 0/10 documents |
| Document with newspaper-column layout | 0/10 documents |
| Low-quality or partial scan | 0/10 documents |
| Handwritten-content PDF | 0/10 documents |
| PDF with embedded forms (fillable fields) | 0/10 documents |
| Slide deck (presentation) converted to PDF | 0/10 documents |
| Government form or administrative template | 0/10 documents |
| Technical manual or specification document | 0/10 documents |
| Book with index | 0/10 documents |
| Document with appendix | 0/10 documents |
| Document with numbered equations | 0/10 documents |
| Document with chemical formulas | 0/10 documents |
| Document with data tables as primary content (not inline) | 0/10 documents |
| Spreadsheet exported to PDF | 0/10 documents |
| Document with external hyperlinks (semantic) | 0/10 documents |

### Missing Accessibility Scenarios

| Missing Accessibility Scenario | Evidence of Absence |
|:---|:---|
| Real mathematical notation requiring MathML or alt text | 0/10 documents contain substantive equations |
| Complex nested tables with `rowspan`/`colspan` | 0/10 documents; only 2 documents have any `\multicolumn` (NoE, Bryman) |
| Decorative image classification | 0/10 formats distinguish decorative from informative images |
| Language declaration signal | 0/10 formats provide language metadata |
| Right-to-left text rendering | 0/10 documents |
| Data visualization requiring axis/legend description | 0/10 documents contain charts with quantitative axes (Brinkman's bar charts are the closest; DOCX has AI alt text for these) |
| Nested list structure | 0/10 documents have lists with more than one indentation level |
| Scanned content with OCR confidence data | 0/10 documents |
| Mixed font/script text (e.g., Greek letters in STEM) | 0/10 documents (excluding math superscript placeholders) |
| Tables with row headers and column headers | 0/10 documents have semantic header markup in any format |

---

## Deliverable 5: Confidence Matrix

For each major conclusion from the previous three audits, this matrix states whether the 10-document, education-domain-only corpus provides sufficient evidence to support the conclusion confidently.

### From Audit 1 (Format Selection)

| Audit 1 Conclusion | Corpus support | Confidence | Limiting factor |
|:---|:---|:---:|:---|
| DOCX dc:title is empty in Mathpix exports | Measured in all 10/10 docs | High | Consistent across all 10; no exceptions |
| MMD preserves reading order | Measured in all 10/10 docs | High | Consistent; no multi-column test case |
| DOCX encodes page numbers as Heading6 | Measured in 8/10 docs; absent in 2 | Medium | 2 docs with no H6; pattern not explained |
| DOCX merges title+author in Heading1 | Observed in 8/10 docs that have titles | High | Consistent failure mode |
| MMD is flat (no hierarchy) in most docs | Observed in 9/10 docs | High | Only exception (NoE) has numbered sections |
| Bryman DOCX drops 7/10 images | Direct observation | High | Only 1/10 docs affected; frequency unknown |
| Alt text absent in MMD and MD | Measured in all 10/10 and 9/9 | High | Consistent; no exceptions |
| DOCX generates AI alt text for some images | Observed in 4/10 docs | Medium | Only 4 docs have embedded images |
| Math notation identical between MMD and MD | Measured in 4 docs with math | Medium | "Math" is exclusively footnote superscripts — no real equations tested |

### From Audit 2 (Cross-Format Reconciliation)

| Audit 2 Conclusion | Corpus support | Confidence | Limiting factor |
|:---|:---|:---:|:---|
| Heading text is >95% consistent MMD↔DOCX | Measured across all 10 docs | High | Education-domain text; may not generalize to non-ASCII, mixed-script, or formula-heavy headings |
| Table cell content is identical across formats | Measured in 3/10 docs with tables | Medium | Only 9 data tables total in corpus; all are simple grids |
| Footnote body text is identical across formats | Measured in 4/10 docs with endnotes | Medium | All footnotes are academic citations; other footnote types untested |
| Blockquote text is stable MMD↔MD | Measured in 5/10 docs | Medium | Textual blockquotes only; no code blocks, no structured quotes |
| Reading order is stable across all formats | Measured in all 10 docs | High | Single-column documents dominate; multi-column reading order untested at scale |
| Page-to-text alignment is impossible without structural linkage | Measured absence across 10 docs | High | Consistent finding; no counter-examples in corpus |

### From Audit 3 (Signal Reliability)

| Audit 3 Conclusion | Corpus support | Confidence | Limiting factor |
|:---|:---|:---:|:---|
| Reading order: Tier 1 (trusted) | All 10 docs | High | Multi-column reading order: only 1 doc; LOW confidence for multi-column generalization |
| Bullet list content: Tier 1 (trusted) | 4/10 docs with bullets | Medium | Only top-level lists; nested list behavior untested |
| Math expressions: Tier 1 (trusted) | 4/10 docs with "math" | Low | All "math" is footnote superscripts; real mathematical equations completely absent |
| Image geometry: Tier 1 (trusted) | 5/10 docs with images | Medium | 5 docs; conceptual diagrams only; complex image types untested |
| Heading hierarchy DOCX-only: Tier 3 | All 10 docs | High | Consistent finding; no exceptions |
| Alt text absent in MMD/MD: Tier 5 | All 10/9 docs | High | Consistent failure; no exceptions across all formats |
| Domain generalization | 0 non-education docs | None | The corpus provides zero evidence for any other domain |
| Multi-column reading order | 1 doc (likely) | Very Low | A single document is insufficient to characterize multi-column behavior |
| Complex table accessibility | 0 complex tables | None | Row-spanning, nested, or header-marked tables are untested |
| Real math preservation | 0 real math docs | None | Cannot assess; no evidence either way |

### Confidence summary by signal class

| Signal class | Evidence depth | Confidence for THIS corpus | Confidence for generalization |
|:---|:---:|:---:|:---:|
| Metadata (title, author, dc: fields) | 10/10 docs | High | Medium (education domain only) |
| Reading order (single-column) | 10/10 docs | High | Medium (only 1 multi-column doc) |
| Heading text | 10/10 docs | High | Medium (ASCII text; no formula headings) |
| Heading hierarchy | 10/10 docs | High | Medium (all educational text structure) |
| Alt text absence | 10/10 docs | High | High (format-level property; not domain-specific) |
| Table content | 3/10 docs, 9 tables | Medium | Low (simple grids only; no complex tables) |
| Footnote/endnote handling | 4/10 docs | Medium | Low (academic citations only) |
| Image completeness | 5/10 docs | Medium | Low (only 1 doc with significant loss) |
| Image alt text quality | 4/10 docs | Medium | Low (single domain of images) |
| Mathematical content | 0/10 docs (real math) | None | None |
| Multi-column layout | 1/10 doc (likely) | Very Low | None |
| Non-English text | 0/10 docs | None | None |
| Form fields | 0/10 docs | None | None |
| Complex tables | 0/10 docs | None | None |

---

## Final Question: Generalizability of Engineering Conclusions

> **To what extent can the engineering conclusions drawn in the previous audits be generalized beyond this benchmark corpus?**

### Conclusions with high generalization confidence

The following findings are structural properties of the Mathpix export formats, not properties of the document content. They are observed consistently across all 10 documents and are likely to hold beyond the corpus:

1. **DOCX dc:title is always empty** — 10/10 observations; format-level property of Mathpix's html-to-docx pipeline.
2. **Alt text is always empty in MMD and MD** — 10/10 and 9/9 observations; format-level property.
3. **MMD heading hierarchy is flat by default** — 9/10 observations; the 1 exception (NoE) has explicitly numbered sections, and even there the exception is partial.
4. **DOCX merges title and author into Heading1** — 8/10 observations; consistent failure of the html-to-docx converter to separate these semantic units.
5. **Page landmarks exist only in DOCX** — 10/10 observations; format-level property.
6. **Reading order is preserved** (single-column documents) — 10/10 observations; format-level property.

### Conclusions with medium generalization confidence

These findings hold across the corpus but are constrained by corpus composition:

7. **Heading text is consistent (>95%) across formats** — valid for English, ASCII-dominant educational text. Generalization to non-ASCII headings, formula-containing headings, or right-to-left script headings is unsupported.
8. **Footnote body text is preserved exactly** — measured in 4/10 docs; all are academic citation footnotes. Footnote types with special characters, non-Latin scripts, or embedded formulas are untested.
9. **Table cell content is consistent** — measured in 3/10 docs; all are simple 3-to-5 column grids. Complex tables with merged cells (beyond single-column spanning headers), nested tables, or tables as primary document content are untested.
10. **Blockquote text is preserved MMD↔MD** — measured in 5/10 docs; all are textual quotations. Code blocks, structured quotations, or non-English blockquotes are untested.

### Conclusions that cannot be generalized

The corpus provides zero evidence for the following areas. The previous audits' absence of failures in these areas is not evidence of reliability — it reflects the absence of test cases:

11. **Mathematical content** — the corpus contains zero substantive mathematical equations. No conclusion about equation preservation, MathML fidelity, or accessibility of mathematical content can be drawn from this benchmark.
12. **Multi-column layout** — only one document is likely 2-column (Brinkman), and this was classified by geometric inference from image metadata, not by direct observation of column-break behavior, reading-order reordering, or cross-column figure placement. Multi-column behavior cannot be characterized from this corpus.
13. **Non-English and multilingual content** — completely absent. Conclusions about character encoding, RTL text, mixed-script handling, or language metadata are entirely unsupported.
14. **Complex table accessibility** — no document has `\multirow`, nested tables, or tables with both row headers and column headers. The accessibility of complex tabular data is untested.
15. **Scanned / OCR-dependent content** — all documents appear to be born-digital or high-quality scans. OCR error handling, confidence scoring, and degraded-image behavior are entirely untested.
16. **Non-education domains** — all 10 documents are from the same academic subject area. Whether the measured behaviors (heading extraction, image handling, metadata failure) hold for legal, scientific, government, or commercial documents is unsupported by evidence.
17. **Long documents** — no document exceeds 28 pages (NoE at 600 MMD lines). Behavior at 50, 100, or 500+ pages is untested.
18. **Appendices** — no document has an appendix. Appendix detection, labeling, and accessibility are untested.

### Quantified generalizability statement

Based solely on the measured corpus:

- **8 format-level conclusions** (metadata behavior, alt text absence, reading order, page landmark encoding, hierarchy flattening, title-author merge): can be stated with high confidence and generalized to other document types because they reflect Mathpix pipeline behavior, not document content.
- **4 content-level conclusions** (heading text consistency, footnote text preservation, table content consistency, blockquote text stability): hold within the corpus but are constrained to English-language, single-column, education-domain, ASCII-dominant documents.
- **7 signal classes** (real math, multi-column layout, non-English text, complex tables, scanned content, form fields, long documents): are completely untested by this corpus. The benchmark provides no evidence in these areas in either direction.

The 10-document, single-domain, single-language, single-layout benchmark is sufficient to characterize Mathpix format-level behavior reliably. It is insufficient to characterize content-processing behavior across the diversity of documents RAWRS may encounter beyond education-domain academic texts.

---

*End of audit. All measurements and classifications are derived from direct observation of file contents and metadata. No document types, specifications, or behaviors were assumed.*
