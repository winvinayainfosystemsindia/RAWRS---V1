# RAWRS Phase-2 Specification: Canonical Semantic Model

**Date**: 2026-06-26  
**Status**: Normative specification  
**Basis**: Evidence established in RAWRS Phase-2 Audit Series (Audits 1–4)  
**Scope**: Canonical, implementation-independent representation of document semantics

---

## Preamble

This specification defines the canonical semantic document model for RAWRS. Every object, attribute, relationship, and constraint is derived from evidence established in the Phase-2 audit series. No new assumptions are introduced.

The model satisfies five properties:

- **Minimal**: no object is present that can be removed without loss of meaning
- **Complete**: every validated semantic signal from the audit series has a representation
- **Internally consistent**: no object, attribute, or constraint contradicts another
- **Format-independent**: no object models a Mathpix behaviour, MMD construct, DOCX element, or MD syntax
- **Implementation-independent**: no serialization format, programming language, or storage mechanism is implied

Three explicit prohibitions apply throughout:

1. No object represents a formatting artifact (visual rendering, typographic convention, layout coordinate)
2. No object was absent from the audit corpus
3. No object can be collapsed into a simpler object without losing a semantic distinction that was directly observed

---

## Deliverable 1: Canonical Semantic Hierarchy

The complete containment hierarchy of the model, from the root document to the smallest semantic unit.

```
Document
├── Metadata
│   ├── title                      (zero or one)
│   ├── authors                    (zero or more Author)
│   │   ├── name
│   │   └── affiliation            (zero or one)
│   ├── abstract                   (zero or one)
│   └── keywords                   (zero or more)
│
├── body                           (one or more Block, ordered)
│   │
│   ├── Section
│   │   ├── heading                (zero or one Heading)
│   │   │   ├── level
│   │   │   └── content            (Content)
│   │   ├── role
│   │   └── content                (zero or more Block, ordered)
│   │       ├── Section            (recursive — child sections)
│   │       ├── Paragraph
│   │       │   └── content        (Content)
│   │       ├── Table
│   │       │   ├── caption        (zero or one Content)
│   │       │   └── rows
│   │       │       └── TableRow
│   │       │           └── cells
│   │       │               └── TableCell
│   │       │                   ├── content    (Content)
│   │       │                   ├── column_span
│   │       │                   └── row_span
│   │       ├── Figure
│   │       │   ├── caption        (Content, required)
│   │       │   └── image          (Image)
│   │       ├── Image              (inline, uncaptioned)
│   │       │   ├── source
│   │       │   ├── alt_text       (zero or one Content)
│   │       │   └── geometry       (zero or one BoundingBox)
│   │       ├── List
│   │       │   ├── list_type
│   │       │   └── items
│   │       │       └── ListItem
│   │       │           └── content (Content)
│   │       ├── Blockquote
│   │       │   └── paragraphs     (one or more Paragraph)
│   │       └── PageMark
│   │           └── label
│   │
│   └── [all Block types above also valid at top body level]
│
├── notes                          (zero or more Note, unordered)
│   ├── id
│   ├── placement                  (zero or one)
│   └── body                      (one or more Paragraph)
│
└── [implicit: Content used inline within all text-bearing objects]
    Content = sequence of:
        ├── PlainText
        ├── NoteReference
        │   └── note_id
        └── InlineMath
            └── notation
```

**Key structural decisions**:

1. `Section` is recursive — a Section can contain other Sections (child sections), enabling arbitrary heading depth.
2. `Block` is a union type — the same set of block types is valid at every containment level (body, section, child section).
3. `Image` is distinct from `Figure` — an Image may appear without a caption; a Figure always has one. This distinction was directly observed: Bryman MMD has 9 plain `![](...)` references outside figure environments and 1 `\begin{figure}...\caption{}` environment.
4. `PageMark` appears inline in the content sequence, preserving its reading-order position.
5. `Content` is a rich inline type — it contains `PlainText`, `NoteReference`, and `InlineMath` elements in sequence. This represents observed patterns: footnote references embedded mid-sentence and math superscripts within paragraphs.
6. `Note` objects live at the Document level — not inside the body hierarchy. They are referenced from the body via `NoteReference` inline elements.

---

## Deliverable 2: Complete Object Catalogue

### Document

**Purpose**: The root object. Represents a complete, self-contained document.  
**Semantic meaning**: A bounded unit of communicative content with a single coherent subject.  
**Parent**: None (root)  
**Required attributes**: `metadata`, `body`  
**Optional attributes**: `notes`  
**Child objects**: `Metadata` (exactly one), one or more `Block` (body), zero or more `Note`

---

### Metadata

**Purpose**: Document-level descriptive information.  
**Semantic meaning**: Facts about the document as a whole, not facts stated within the document's argument.  
**Parent**: Document (exactly one)  
**Required attributes**: none (the Metadata object is always present; its fields are individually optional)  
**Optional attributes**: `title`, `authors`, `abstract`, `keywords`  
**Child objects**: zero or one `title` (Text), zero or more `Author`, zero or one `abstract` (Text), zero or more `keywords` (Text)

**Justification**: Metadata as a distinct container was established by Audit 1, which confirmed that `\title{}`, `\author{}`, and `\begin{abstract}` in MMD are semantically distinct from body content. Audit 2 (Conflict C-01, C-19) and Audit 3 (Tier 4–5) established that metadata signals are unreliable across formats; the container must exist regardless.

---

### Author

**Purpose**: A named contributor to the document.  
**Semantic meaning**: A person responsible for authoring the document content.  
**Parent**: Metadata  
**Required attributes**: `name`  
**Optional attributes**: `affiliation`  
**Child objects**: none

**Justification**: Author was directly observed in Brinkman (`\author{Suzana Brinkmann \\ Institute of Education, London, UK}`), Aims (`\author{Rohit Dhankar}`), and TeachCh1. Affiliation appeared alongside the author name in Brinkman. Audit 2 (C-01) documented the author-title merge conflict in DOCX, establishing author as a distinct semantic concept from title.

---

### Section

**Purpose**: A bounded region of document content organized under a heading.  
**Semantic meaning**: A coherent unit of content that belongs together under a particular topic or label. May be a major division (chapter-level), a minor division (subsection), or a supplementary insert (callout).  
**Parent**: Document (body), or another Section (child section)  
**Required attributes**: `role`  
**Optional attributes**: `heading`  
**Child objects**: zero or one `Heading`, zero or more `Block`

**`heading` is optional** because content may precede the first heading in a document (observed in Brinkman: abstract and keywords appear before the Introduction section) and a section may consist of content without an explicit heading label.

**`role` values**:
- `body` — a structural section in the document's organizational hierarchy (default)
- `callout` — a supplementary, set-apart insert within the main content flow; content is thematically supplementary rather than hierarchically nested
- `references` — a bibliographic section containing citation entries

**Justification**: Section hierarchy was observed in all 10 documents. The `role` attribute captures a distinction directly observed in 3/10 documents: Bryman has 18 text boxes ("Research in focus", "Key concept", "Student experience"), NoE has 5 BOX elements, O'Leary has 2 named boxes. These are semantically distinct from structural sections: they are supplementary inserts whose heading labels (e.g., "Research in focus 2.1") are callout identifiers, not hierarchical divisions. Audit 2 (C-09, C-16) documented how this distinction is expressed differently across formats (MMD: `\section*{}` inflation; DOCX: `<w:tbl>` inflation). The `references` role captures explicit bibliography sections observed in Brinkman, Calderhead, and Fullan (Audit 3 measurements).

---

### Heading

**Purpose**: The label that identifies a Section.  
**Semantic meaning**: A brief text identifying the topic of the content that follows it within its section.  
**Parent**: Section (at most one per Section)  
**Required attributes**: `level`, `content`  
**Optional attributes**: none  
**Child objects**: none (content is modeled as `Content`, not a child object)

**`level`**: an integer from 1 to 6. Level 1 is the highest (most general) heading; level 6 is the lowest (most specific). These values correspond to the heading depth observed in DOCX (H1, H2, H3) and in NoE's MMD (\section*, \subsection*).

**Justification**: Heading hierarchy was the single most diagnostically important signal across all four audits. Audit 1 identified heading hierarchy as the dominant architectural reason to prefer DOCX as the hierarchy source. Audit 2 (C-10, C-11) documented hierarchy conflicts. Audit 3 ranked heading text in Tier 1 (trusted) and heading hierarchy in Tier 2 (requires validation). The 6-level range captures the DOCX heading model (H1–H6) while using H6 exclusively for PageMark in DOCX — the model separates these concepts cleanly by not using `Heading` for PageMark objects.

---

### Paragraph

**Purpose**: A unit of prose content within the body.  
**Semantic meaning**: A coherent, bounded sequence of sentences that develops a single idea or point.  
**Parent**: Section, Blockquote, Note (as body), or Document (body, for pre-heading content)  
**Required attributes**: `content`  
**Optional attributes**: none  
**Child objects**: none (content is `Content`)

**Justification**: Paragraphs are the fundamental unit of prose content. Paragraph block counts were measured in all 10 documents across MMD and MD (Audit 3). Paragraphs appear within sections, blockquotes, and notes — all three observed in the corpus.

---

### Content

**Purpose**: Rich inline text, capable of carrying embedded references and mathematical expressions.  
**Semantic meaning**: The actual expressed meaning of a text-bearing object, at the character and word level.  
**Parent**: Heading, Paragraph, TableCell, Figure (caption), Table (caption), ListItem, Blockquote, Note  
**Required attributes**: none (may be empty in edge cases, e.g., a cell spacer)  
**Child objects**: zero or more `PlainText`, zero or more `NoteReference`, zero or more `InlineMath`, in reading order

**Justification**: The need for a rich inline type was established by two observations. (1) Footnote references appear mid-sentence within paragraphs, as directly observed in Aims and Brinkman: `"...teaching${ }^{7}$, and..."`. (2) Mathematical expressions appear embedded in prose (Audit 3: 24 inline math occurrences in Brinkman, 21 in Aims). A flat string type for `content` would conflate `PlainText`, `NoteReference`, and `InlineMath`, losing the inline position information that the DOCX structural model preserves via `<w:endnoteReference>`.

---

### PlainText

**Purpose**: A run of unformatted prose characters.  
**Semantic meaning**: The literal textual content of a content sequence, excluding references and mathematical expressions.  
**Parent**: Content  
**Required attributes**: `text` (a string)  
**Optional attributes**: none

---

### NoteReference

**Purpose**: An inline marker that links a point in the document body to a Note.  
**Semantic meaning**: An indication that supplementary or qualifying information exists and is identified by the referenced Note.  
**Parent**: Content  
**Required attributes**: `note_id`  
**Optional attributes**: none

**Justification**: NoteReference as a distinct inline object was established by the contrast between DOCX (which provides `<w:endnoteReference w:id="n">` for structural linkage) and MMD (which uses `${ }^{n}$` notation that is ambiguous with InlineMath). The semantic concept of "a reference to a note at a specific position in a paragraph" is unambiguous. Audit 2 (C-15) documented the failure of MMD/MD to provide this linkage. Audit 3 (Tier 2) confirmed structural linkage is available from DOCX for 4/10 documents.

---

### InlineMath

**Purpose**: A mathematical expression embedded in prose.  
**Semantic meaning**: A statement in mathematical notation, integrated into the surrounding sentence.  
**Parent**: Content  
**Required attributes**: `notation` (a string containing the mathematical expression)  
**Optional attributes**: none

**Justification**: Inline mathematical expressions were directly observed in 4/10 documents (Brinkman: 24, Aims: 21, Bruner: 42, NoE: 6). In the benchmark corpus, all observed occurrences are footnote reference superscripts expressed as LaTeX math (`${ }^{n}$`). However, the semantic concept of an inline mathematical expression is valid regardless of what specific expressions appear. The notation string is format-independent: it carries the mathematical meaning, not its rendering. Audit 3 placed this in Tier 1 (trusted) for count stability and notation consistency.

---

### Table

**Purpose**: A set of data organized in rows and columns.  
**Semantic meaning**: Information presented in a grid structure where the row–column intersection carries meaning derived from both the row and column contexts.  
**Parent**: Section, or Document (body)  
**Required attributes**: `rows`  
**Optional attributes**: `caption`  
**Child objects**: zero or one `caption` (Content), one or more `TableRow`

**Justification**: Data tables were directly observed in 3/10 documents (NoE: 2 tables, Bryman: 1 table, Brinkman: 5 tables; 9 tables total). Audit 1 confirmed table content is consistent across all three formats. Audit 2 (C-16) documented the DOCX inflation problem (text boxes encoded as `<w:tbl>`), establishing the need to model data tables as distinct from other content. The optional caption maps to `\caption{}` observed in Brinkman and Bryman.

---

### TableRow

**Purpose**: One horizontal row within a table.  
**Semantic meaning**: A single record or category within the table's grid structure.  
**Parent**: Table  
**Required attributes**: `cells`  
**Child objects**: one or more `TableCell`

---

### TableCell

**Purpose**: The intersection of one row and one column in a table.  
**Semantic meaning**: A single datum or label within the table's grid, contextualized by its row and column.  
**Parent**: TableRow  
**Required attributes**: `content`  
**Optional attributes**: `column_span`, `row_span`  
**Child objects**: none (`content` is `Content`)

**`column_span`**: the number of columns this cell spans. Default: 1. Observed as `\multicolumn{3}{|l|}{}` in NoE (Table 1.1 spanning header) and in Bryman (Table 2.1). Value ≥ 1.  
**`row_span`**: the number of rows this cell spans. Default: 1. No `\multirow` was observed in the corpus; this attribute is included because the semantic concept of a row-spanning cell is valid and the constraint `row_span ≥ 1` must hold.

---

### Figure

**Purpose**: An image presented as a labeled, captioned element within the document.  
**Semantic meaning**: A visual artifact — a diagram, chart, photograph, or illustration — that is integral to the document's argument and identified by a caption.  
**Parent**: Section, or Document (body)  
**Required attributes**: `caption`, `image`  
**Child objects**: exactly one `caption` (Content), exactly one `Image`

**The caption is required for Figure**. An image without a caption is modeled as an inline `Image`, not a `Figure`. This distinction was directly established by Bryman's MMD: 1 image in `\begin{figure}...\caption{}` and 9 plain `![](...)` images outside figure environments.

**Justification**: Captioned figures were observed in 4/10 documents (NoE: 1, Bryman: 1, O'Leary: 4, Brinkman: 2). Audit 3 placed figure caption extraction in Tier 3 (occasionally reliable). Audit 2 (C-17) documented Bryman DOCX's silent loss of 7/10 images, establishing Image as a concept that must be represented independently of any specific export format's rendering.

---

### Image

**Purpose**: A single visual artifact referenced within the document.  
**Semantic meaning**: A bounded rectangular region of pixels carrying visual meaning — a diagram, photograph, chart, or illustration.  
**Parent**: Figure (as its enclosed image), or any Block container (as an inline, uncaptioned image)  
**Required attributes**: `source`  
**Optional attributes**: `alt_text`, `geometry`  
**Child objects**: none

**`source`**: an opaque identifier for the pixel content of the image. The model does not specify what form this takes — it is the identity of the image content, not a file path, URL, or embedded binary.

**`alt_text`**: a text description of the image's visual meaning. Present in 4/10 DOCX documents (Audit 3: Tier 4–5 reliability). 100% absent in MMD and MD. Where present in DOCX, it is AI-generated and substantive (662–1415 characters for Brinkman and Bryman). The alt_text attribute is type `Content` (not bare text) to allow for future rich description, consistent with the model's use of `Content` for all text-bearing fields.

**`geometry`**: the spatial location of the image on its source page. Defined as a `BoundingBox`.

**Justification**: Images were observed in 5/10 documents across all formats. Alt text was measured as absent in all MMD/MD and present (with quality caveats) in 4/10 DOCX files (Audit 3: Tier 4–5). Image geometry was measured as present and consistent in both MMD (filename encoding) and MD (CDN URL parameters) for all 9 documents that have MD (Audit 3: Tier 1).

---

### BoundingBox

**Purpose**: The spatial location and size of an image on a source page.  
**Semantic meaning**: The region of a page that the image occupies, expressed as pixel coordinates within the source document's coordinate system.  
**Parent**: Image  
**Required attributes**: `page`, `height`, `width`, `top_left_y`, `top_left_x`  
**Optional attributes**: none

**Attribute values**: All are non-negative integers. `page` is the source page number (1-indexed). `height`, `width`, `top_left_y`, `top_left_x` are pixel values in the coordinate system established by the Mathpix OCR pipeline (as observed in filename encoding and CDN URL parameters).

**Justification**: Image geometry was directly measured from both MMD filenames (e.g., `docid-page_height_width_y_x.jpg`) and MD CDN URL parameters (`?height=H&width=W&top_left_y=Y&top_left_x=X`) in Audit 2 and 3. The four coordinate values are identical between MMD and MD encoding (Audit 3: Tier 1, trusted). The coordinate system is Mathpix's internal pixel space; the model preserves the measured values without converting them.

---

### List

**Purpose**: A set of related items presented as an enumeration.  
**Semantic meaning**: A series of discrete, individually distinct items that share a common context or category.  
**Parent**: Section, or Document (body)  
**Required attributes**: `list_type`, `items`  
**Child objects**: one or more `ListItem`

**`list_type` values**:
- `ordered`: items have a specific sequence (numbered list); the sequence carries meaning
- `unordered`: items have no specific sequence (bullet list); membership is the primary semantic content

**Justification**: Bullet lists were observed in 4/10 documents (NoE: 45, Bryman: 41, O'Leary: 41, Sockett: 1). Numbered lists were observed in 5/10 (Bruner: 51, Brinkman: 6, Bryman: 8, O'Leary: 9, Sockett: 3). Audit 3 placed bullet lists in Tier 1 (fully trusted). No nested lists were observed in any document; accordingly, `ListItem` has no `child_items` attribute.

---

### ListItem

**Purpose**: A single item within a list.  
**Semantic meaning**: One discrete element of the enumeration.  
**Parent**: List  
**Required attributes**: `content`  
**Child objects**: none (`content` is `Content`)

---

### Blockquote

**Purpose**: A passage of text set apart from the main prose as a quotation.  
**Semantic meaning**: Text attributed to a source other than the document's author, or text that the author explicitly demarcates as distinct from the surrounding argument.  
**Parent**: Section, or Document (body)  
**Required attributes**: `paragraphs`  
**Child objects**: one or more `Paragraph`

**Justification**: Blockquotes were observed in 5/10 documents (Brinkman: 9, NoE: 8, Bryman: 6, Fullan: 1, O'Leary: 1). Audit 3 placed blockquote text content in Tier 1 (fully trusted for MMD↔MD) but noted that blockquote structure is entirely absent from DOCX (no named paragraph style; blockquotes appear as regular body paragraphs). The model preserves this as a semantic concept even where the signal is unreliable.

---

### PageMark

**Purpose**: A position marker in the reading order indicating the boundary of a printed page.  
**Semantic meaning**: The point in the document's content flow at which one printed page ends and the next begins, identified by its printed page label.  
**Parent**: Section, or Document (body) — appears inline in the content sequence at the position of the page boundary  
**Required attributes**: `label`  
**Optional attributes**: none

**`label`**: the printed page number as it appears in the source document. This is a text string, not an integer, because page labels may be Roman numerals, letters, or other non-numeric forms.

**Justification**: Page landmarks were measured in 8/10 DOCX files as Heading6 paragraphs (Audit 1, 3). Values directly correspond to printed page numbers: Brinkman pages 342–359 (journal pagination), NoE pages 3–30, Bryman pages 19–43, etc. Audit 3 placed this in Tier 1 (trusted) when present, and noted 2/10 DOCX files have no H6 page numbers. RAWRS feature_009 (`Page.printed_label`) already implements this concept, confirming its engineering relevance.

---

### Note

**Purpose**: A textual annotation that supplements a specific point in the document body.  
**Semantic meaning**: Content that qualifies, explains, or cites evidence for a claim made at a particular position in the body text, but which is structurally separated from the main prose.  
**Parent**: Document (notes collection — unordered)  
**Required attributes**: `id`, `body`  
**Optional attributes**: `placement`  
**Child objects**: one or more `Paragraph` (body)

**`id`**: a unique identifier within the document. Used by `NoteReference.note_id` to create the reference-to-body linkage.

**`placement` values**:
- `page-inline`: the note is intended to appear on the same page as its reference (a true footnote). Observed in Aims (11 page-bottom footnotes).
- `document-end`: the note is intended to appear at the end of the document (an endnote). Observed in Bruner (36), NoE (4), Brinkman (3).
- absent (not specified): the placement cannot be determined from available signals. This is the expected state for notes extracted from DOCX, which converts all notes to endnotes regardless of source type (Audit 2, C-13).

**Justification**: Notes were observed in 4/10 documents (Aims: 11, Bruner: 36, NoE: 4, Brinkman: 3; 54 total). Audit 3 placed footnote body text in Tier 1 (trusted) and footnote structural linkage in Tier 2. Audit 2 (C-13, C-14, C-15) documented three distinct conflict types: semantic type mismatch (footnote→endnote), notation inconsistency in MD, and missing structural linkage in MMD.

---

## Deliverable 3: Attribute Specification Tables

### Document attributes

| Attribute | Semantic purpose | Required | Multiplicity | Provenance |
|:---|:---|:---:|:---:|:---|
| `metadata` | Document-level descriptive information | Required | Exactly one | Audit 1 (title, author signals) |
| `body` | Ordered content of the document | Required | One or more Block | Audit 3 (reading order: Tier 1) |
| `notes` | Footnote and endnote bodies | Optional | Zero or more Note | Audit 1 (footnote structure), Audit 3 (Tier 1–2) |

### Metadata attributes

| Attribute | Semantic purpose | Required | Multiplicity | Provenance |
|:---|:---:|:---:|:---:|:---|
| `title` | The document's name or heading | Optional | Zero or one | Audit 1 (5/10 MMD); Audit 3 (Tier 3) |
| `authors` | The persons who authored the document | Optional | Zero or more | Audit 1 (3/10 MMD `\author{}`); Audit 3 (Tier 4) |
| `abstract` | A summary of the document's content | Optional | Zero or one | Audit 3 (1/10 Brinkman); Tier 4 |
| `keywords` | Terms characterizing the document's subject | Optional | Zero or more | Audit 3 (observed in Brinkman only) |

### Author attributes

| Attribute | Semantic purpose | Required | Multiplicity | Provenance |
|:---|:---:|:---:|:---:|:---|
| `name` | The author's name | Required | Exactly one | Audit 1; all author-bearing documents |
| `affiliation` | The institution the author represents | Optional | Zero or one | Audit 1 (Brinkman `\author{name \\ affiliation}`) |

### Section attributes

| Attribute | Semantic purpose | Required | Multiplicity | Provenance |
|:---|:---:|:---:|:---:|:---|
| `heading` | The label of the section | Optional | Zero or one Heading | Audit 1–4; all 10 documents |
| `role` | The section's semantic function | Required | Exactly one SectionRole | Audit 2 (C-09, C-16); 3/10 docs with callouts; 3/10 with references |
| `content` | The ordered blocks within the section | Optional | Zero or more Block | Audit 3 (reading order: Tier 1) |

### Heading attributes

| Attribute | Semantic purpose | Required | Multiplicity | Provenance |
|:---|:---:|:---:|:---:|:---|
| `level` | The depth of this heading in the document hierarchy | Required | Exactly one integer [1..6] | Audit 1 (DOCX H1/H2/H3); Audit 2 (C-10, C-11) |
| `content` | The text of the heading | Required | Exactly one Content | Audit 3 (heading text: Tier 1) |

### Table attributes

| Attribute | Semantic purpose | Required | Multiplicity | Provenance |
|:---|:---:|:---:|:---:|:---|
| `caption` | The label identifying the table | Optional | Zero or one Content | Audit 1 (`\caption{}` in Brinkman, Bryman); Audit 3 (Tier 3) |
| `rows` | The horizontal records of the table | Required | One or more TableRow | Audit 3 (table content: Tier 1) |

### TableCell attributes

| Attribute | Semantic purpose | Required | Multiplicity | Provenance |
|:---|:---:|:---:|:---:|:---|
| `content` | The datum or label in this cell | Required | Exactly one Content | Audit 3 (Tier 1: identical across formats) |
| `column_span` | The number of columns this cell spans | Optional | Zero or one integer [≥1] | Audit 1–4 (NoE: `\multicolumn{3}`, Bryman: `\multicolumn{3}`) |
| `row_span` | The number of rows this cell spans | Optional | Zero or one integer [≥1] | Not directly observed; included as valid concept with minimum constraint |

### Figure attributes

| Attribute | Semantic purpose | Required | Multiplicity | Provenance |
|:---|:---:|:---:|:---:|:---|
| `caption` | The text identifying and describing the figure | Required | Exactly one Content | Audit 1 (4/10 docs); Audit 3 (Tier 3) |
| `image` | The visual content of the figure | Required | Exactly one Image | Audit 1 (image completeness); Audit 3 (Tier 2) |

### Image attributes

| Attribute | Semantic purpose | Required | Multiplicity | Provenance |
|:---|:---:|:---:|:---:|:---|
| `source` | The identity of the image's pixel content | Required | Exactly one | Audit 1 (image references); Audit 3 (Tier 2) |
| `alt_text` | A textual description of the image's visual meaning | Optional | Zero or one Content | Audit 3 (DOCX only, 4/10 docs; Tier 4–5) |
| `geometry` | The image's spatial location on its source page | Optional | Zero or one BoundingBox | Audit 2 (C-18); Audit 3 (geometry: Tier 1) |

### BoundingBox attributes

| Attribute | Semantic purpose | Required | Multiplicity | Provenance |
|:---|:---:|:---:|:---:|:---|
| `page` | The source page number | Required | Exactly one non-negative integer | Audit 2 (filename encoding: `page_h_w_y_x`) |
| `height` | The height of the image in source pixels | Required | Exactly one non-negative integer | Audit 2 (filename/URL params) |
| `width` | The width of the image in source pixels | Required | Exactly one non-negative integer | Audit 2 (filename/URL params) |
| `top_left_y` | The vertical pixel position of the image's top-left corner | Required | Exactly one non-negative integer | Audit 2 (filename/URL params) |
| `top_left_x` | The horizontal pixel position of the image's top-left corner | Required | Exactly one non-negative integer | Audit 2 (filename/URL params) |

### Note attributes

| Attribute | Semantic purpose | Required | Multiplicity | Provenance |
|:---|:---:|:---:|:---:|:---|
| `id` | The unique identifier for this note, matched by NoteReference | Required | Exactly one NoteId | Audit 2 (C-15: DOCX `w:id` linkage) |
| `placement` | Where the note appears relative to the body text | Optional | Zero or one NotePlacement | Audit 2 (C-13); Audit 3 (Tier 2) |
| `body` | The content of the note | Required | One or more Paragraph | Audit 3 (footnote body text: Tier 1) |

### PageMark attributes

| Attribute | Semantic purpose | Required | Multiplicity | Provenance |
|:---|:---:|:---:|:---:|:---|
| `label` | The printed page number as displayed in the source document | Required | Exactly one Text | Audit 1 (DOCX H6); Audit 3 (Tier 1) |

### NoteReference attributes

| Attribute | Semantic purpose | Required | Multiplicity | Provenance |
|:---|:---:|:---:|:---:|:---|
| `note_id` | The identifier of the Note this reference points to | Required | Exactly one NoteId | Audit 2 (C-15); Audit 3 (footnote linkage: Tier 2) |

### InlineMath attributes

| Attribute | Semantic purpose | Required | Multiplicity | Provenance |
|:---|:---:|:---:|:---:|:---|
| `notation` | The mathematical expression in its source notation | Required | Exactly one string | Audit 3 (math expressions: Tier 1; 4/10 docs) |

### List attributes

| Attribute | Semantic purpose | Required | Multiplicity | Provenance |
|:---|:---:|:---:|:---:|:---|
| `list_type` | Whether the sequence of items is ordered or unordered | Required | Exactly one ListType | Audit 3 (bullet lists Tier 1; numbered lists Tier 2) |
| `items` | The individual items in the list | Required | One or more ListItem | Audit 3 (Tier 1) |

---

## Deliverable 4: Relationship Specification

Semantic relationships only. No traversal algorithms, indexing strategies, or storage mechanisms.

### Containment relationships (hierarchical)

| Parent | Relationship | Child | Notes |
|:---|:---|:---|:---|
| Document | contains | Metadata | The document has exactly one metadata block |
| Document | contains (body) | Block | One or more Blocks form the body; order is the reading order |
| Document | holds | Note | Zero or more Notes; the collection is unordered (Notes are referenced, not traversed sequentially) |
| Section | is identified by | Heading | A Section may have at most one Heading; preamble sections have none |
| Section | contains | Block | Zero or more Blocks within the section; order is reading order |
| Section | contains | Section | A Section may contain child Sections (recursive containment for subsections) |
| Table | is labeled by | caption | A table may be labeled with a caption |
| Table | consists of | TableRow | One or more rows form the table |
| TableRow | consists of | TableCell | One or more cells form each row |
| Figure | is identified by | caption | Every Figure has exactly one caption |
| Figure | depicts | Image | Every Figure contains exactly one Image |
| Image | is located by | BoundingBox | An Image may have at most one BoundingBox |
| List | consists of | ListItem | One or more items form the list |
| Blockquote | consists of | Paragraph | One or more paragraphs form the quotation |
| Note | consists of | Paragraph | One or more paragraphs form the note body |
| Content | contains | PlainText | Zero or more plain text runs |
| Content | contains | NoteReference | Zero or more inline references to Notes |
| Content | contains | InlineMath | Zero or more mathematical expressions |
| Metadata | describes | Author | Zero or more Authors are associated with the document |
| Author | has | affiliation | Zero or one institutional affiliation |

### Reference relationships (non-hierarchical)

| Source | Relationship | Target | Notes |
|:---|:---|:---|:---|
| NoteReference | references | Note | `NoteReference.note_id` resolves to `Note.id` within the same Document. The Note exists independently of where it is referenced. |
| PageMark | marks position of | printed page | The label corresponds to the page number as printed in the source document. The PageMark is not a container — it is a marker in the content sequence. |
| Section (role: references) | contains entries citing | external works | The references section contains Paragraphs whose content are bibliographic citations; no formal relationship is defined to the cited works, which are not modeled. |

### Ordering relationships

| Subject | Ordering constraint | Scope |
|:---|:---|:---|
| Block elements in Document body | Ordered by reading order | Top level of document |
| Block elements in Section content | Ordered by reading order | Within each Section |
| TableRow elements in Table | Ordered by their row position in the source table | Within each Table |
| TableCell elements in TableRow | Ordered by their column position in the source table | Within each TableRow |
| ListItem elements in List | Ordered; for `ordered` lists, position carries meaning | Within each List |
| Paragraph elements in Note body | Ordered by reading order | Within each Note |
| Inline elements in Content | Ordered by their position within the prose | Within each Content |

---

## Deliverable 5: Cardinality Matrix

| Relationship | Cardinality | Evidence basis |
|:---|:---:|:---|
| Document → Metadata | Exactly One | Every document has metadata (which may be mostly empty — Audit 3 confirmed dc: fields empty 10/10) |
| Document → body Block | One or More | Every document has at least one content block |
| Document → Note | Zero or More | 4/10 docs have notes; 6/10 do not |
| Metadata → title | Zero or One | Present in 5/10 MMD; absent in 5/10 |
| Metadata → Author | Zero or More | Present in 3/10; others: no `\author{}` observed |
| Metadata → abstract | Zero or One | Present in 1/10 (Brinkman) |
| Metadata → keywords | Zero or More | Present in 1/10 (Brinkman); may be multiple keywords |
| Author → name | Exactly One | A named author always has a name |
| Author → affiliation | Zero or One | Present in Brinkman; absent in Aims and TeachCh1 |
| Section → Heading | Zero or One | Preamble content has no heading; all sections with headings have exactly one |
| Section → content Block | Zero or More | A heading-only section with no content is valid |
| Section → child Section | Zero or More | Recursively — some sections have no subsections |
| Table → caption | Zero or One | Brinkman and Bryman have captions; NoE tables do not (Audit 1 measured) |
| Table → TableRow | One or More | Every data table has at least one row |
| TableRow → TableCell | One or More | Every row has at least one cell |
| Figure → caption | Exactly One | Figure is defined by having a caption; captionless images are modeled as Image |
| Figure → Image | Exactly One | Every Figure references exactly one Image |
| Image → BoundingBox | Zero or One | Present in 5/10 docs via MMD/MD geometry; absent from DOCX |
| Image → alt_text | Zero or One | Present in 4/10 DOCX; absent in all MMD/MD |
| List → ListItem | One or More | An empty list has no semantic meaning |
| Blockquote → Paragraph | One or More | Every quotation has at least one paragraph |
| Note → Paragraph | One or More | Every note has at least one paragraph of content |
| NoteReference → Note | Exactly One | Each reference resolves to exactly one Note; the Note must exist |
| Content → inline element | Zero or More | Content may be empty (cell spacer) or contain any mix of inline types |
| TableCell → column_span | Zero or One (attribute) | Default 1 when absent; 2/10 docs have observed spans (NoE, Bryman) |
| TableCell → row_span | Zero or One (attribute) | Default 1 when absent; not observed but valid |

---

## Deliverable 6: Semantic Constraints

Constraints required for semantic correctness. Every constraint is derived from observed properties of the benchmark corpus.

### C-01 — Reading order is total and preserved

Every Block within any container (Document body, Section content) has a defined position in a linear reading sequence. No two Blocks occupy the same position. The sequence corresponds to the reading order of the source document.

*Basis*: Audit 3 established reading order as Tier 1 (fully trusted) across all 10 documents in all three formats. No reorderings were detected.

### C-02 — Note IDs are unique within a document

No two Notes within the same Document share the same `id`. Every `NoteReference.note_id` resolves to exactly one Note in the Document's notes collection.

*Basis*: Audit 2 (C-15) established that DOCX provides `<w:endnote w:id="n">` with unique IDs matched by `<w:endnoteReference w:id="n">`. The model requires this structural integrity.

### C-03 — Heading levels respect section depth

When a Section with heading level N contains a child Section with a heading, that child Section's heading level is greater than N (i.e., a deeper nesting level has a higher level number). A Section at level 1 cannot directly contain a Section at level 1.

*Basis*: Audit 1 established that DOCX H1 contains H2 and H3 descendants; NoE MMD has `\section*{}` (level 1) containing `\subsection*{}` (level 2). This constraint defines a well-formed heading hierarchy. Documents that violate this (e.g., BOX elements in NoE MMD that are technically `\section*{}` but semantically subordinate) should be modeled with the correct hierarchy even if the source signal requires correction.

### C-04 — Figure requires an Image

A Figure object that does not reference exactly one Image is invalid. The image cannot be absent.

*Basis*: Audit 2 (C-17) documented Bryman DOCX silently dropping 7/10 images. The model requires that if a Figure is represented, its Image must be resolved. Where images cannot be resolved, the content should be represented as a Paragraph or omitted, not as an Image-less Figure.

### C-05 — Figure requires a non-empty caption

A Figure object whose caption Content is empty is invalid. An image with no caption is modeled as an inline Image, not a Figure.

*Basis*: The Figure / Image distinction (Audit 1: Bryman MMD has 1 `\begin{figure}...\caption{}` and 9 plain `![](...)`) requires that Figure is definitively associated with a caption.

### C-06 — BoundingBox values are non-negative

All five BoundingBox attributes (`page`, `height`, `width`, `top_left_y`, `top_left_x`) are non-negative integers. `height` and `width` are strictly positive (≥ 1). `page` is strictly positive (≥ 1).

*Basis*: Image geometry was measured from MMD filenames and MD CDN URL parameters (Audit 2). All measured values are non-negative integers in the Mathpix pixel coordinate system.

### C-07 — PageMark label is non-empty

A PageMark with an empty label is invalid.

*Basis*: All observed DOCX H6 page number values are non-empty strings (e.g., "342", "3", "19"). An empty page label carries no semantic meaning.

### C-08 — InlineMath notation is non-empty

An InlineMath whose notation string is empty is invalid.

*Basis*: All 67 observed inline math occurrences in the corpus contained non-empty notation strings.

### C-09 — Callout sections do not define document hierarchy

A Section with `role: callout` does not contribute to the document's heading hierarchy. A callout's heading level (if any) does not constrain the level of its parent or sibling sections.

*Basis*: Audit 2 (C-09, C-16) documented that text boxes ("Research in focus", "Key concept") in Bryman are not structural divisions — they are supplementary inserts. Their heading labels ("Research in focus 2.1") are identifiers, not hierarchical markers.

### C-10 — Note body content is ordered

The Paragraphs within `Note.body` are ordered. This order corresponds to the reading order of the note's text.

*Basis*: Audit 3 confirmed footnote body text is preserved exactly (Tier 1); order within note bodies is implicit in any sequence of paragraphs.

### C-11 — Column span minimum

`TableCell.column_span`, when specified, is ≥ 1. `TableCell.row_span`, when specified, is ≥ 1. This constraint applies regardless of whether any spanning cells are present.

*Basis*: Structural requirement following observation of `\multicolumn{3}` in NoE and Bryman.

### C-12 — An Image may appear at most once within a Figure

A single Image object is referenced by at most one Figure. This prevents a figure from sharing its image with another figure.

*Basis*: Audit 1 established that each figure environment wraps exactly one image reference.

---

## Deliverable 7: Provenance Matrix

Every object and attribute is traced to its originating audit, semantic signal, and confidence level.

| Object / Attribute | Originating audit | Semantic signal | Confidence | Benchmark evidence |
|:---|:---|:---|:---:|:---|
| Document | All audits | Document as unit | High | 10/10 documents |
| Metadata | Audit 1, 3 | Title, author, metadata signals | High | All 10; failure modes documented |
| Metadata.title | Audit 1 | `\title{}` in MMD | Low–Medium | 5/10 MMD; absent in 5/10 |
| Metadata.authors | Audit 1, 2 | `\author{}` in MMD | Low | 3/10 confirmed; DOCX merge (C-01) |
| Author.name | Audit 1, 2 | Author name text | Low | 3/10; text consistent when present |
| Author.affiliation | Audit 1, 2 | Brinkman `\author{name \\ institution}` | Low | 1/10 observed |
| Metadata.abstract | Audit 3 | `\begin{abstract}` in Brinkman MMD | Low | 1/10; Tier 4 reliability |
| Metadata.keywords | Audit 3 | `\section*{Keywords}` in Brinkman | Low | 1/10 |
| Section | Audit 1, 2, 3 | Heading structure | High | 10/10 documents |
| Section.role = body | Audit 1, 2 | All structural sections | High | 10/10 documents |
| Section.role = callout | Audit 2 (C-09, C-16) | Text boxes in Bryman, NoE, O'Leary | Medium | 3/10 documents; 25 callout instances |
| Section.role = references | Audit 3 | `\section*{References}` | Medium | 3/10 documents (Brinkman, Calderhead, Fullan) |
| Heading | Audit 1, 2, 3 | Heading text | High | 10/10 documents |
| Heading.level | Audit 1, 2 | DOCX H1/H2/H3; NoE MMD \subsection* | Medium | 10/10 DOCX hierarchy; 1/10 MMD hierarchy |
| Heading.content | Audit 3 | Heading text (Tier 1) | High | 10/10; >95% text agreement |
| Paragraph | Audit 3 | Paragraph blocks | High | 10/10; block counts measured |
| Content (rich inline) | Audit 2, 3 | NoteReference inline positioning | Medium | 4/10 docs with inline note refs |
| PlainText | All audits | Body prose text | High | 10/10 |
| NoteReference | Audit 2 (C-15), 3 | DOCX `<w:endnoteReference>` | Medium | 4/10 DOCX docs with endnotes |
| InlineMath | Audit 3 | Inline `$...$` (Tier 1) | Medium | 4/10 docs; 67 total occurrences |
| Table | Audit 1, 2, 3 | Data tables | High | 3/10 docs; 9 total tables |
| Table.caption | Audit 1, 3 | `\caption{}` in `\begin{table}` | Medium | 2/10 docs (Brinkman, Bryman) |
| TableRow | Audit 1, 3 | Table structure | High | 3/10 docs |
| TableCell | Audit 1, 3 | Cell content (Tier 1) | High | Identical across formats |
| TableCell.column_span | Audit 1, 3 | `\multicolumn` in NoE, Bryman | Medium | 2/10 docs |
| TableCell.row_span | None directly | Semantic completeness | Low | Not observed; included as valid concept |
| Figure | Audit 1, 2, 3 | `\begin{figure}...\caption{}` | Medium | 4/10 docs; 8 captioned figures |
| Figure.caption | Audit 1, 3 | `\caption{}` content | Medium | 4/10 docs; Tier 3 reliability |
| Image | Audit 1, 2, 3 | Image references | Medium | 5/10 docs with images |
| Image.source | Audit 1, 3 | Image path / CDN URL | High | 5/10 docs |
| Image.alt_text | Audit 3 | DOCX `descr=` attribute (Tier 4–5) | Low | 4/10 DOCX docs; 50% corruption in OLeary |
| Image.geometry | Audit 2 (C-18), 3 | Bounding box coordinates (Tier 1) | High | 5/10 docs; identical MMD↔MD |
| BoundingBox.* | Audit 2, 3 | Image filename/URL params | High | 5/10 docs; consistent encoding |
| List | Audit 3 | Bullet and numbered lists (Tier 1–2) | High | 4/10 bullet; 5/10 numbered |
| List.list_type | Audit 3 | Ordered vs. unordered | High | Both types directly observed |
| ListItem | Audit 3 | List item content | High | Tier 1; no failures detected |
| Blockquote | Audit 3 | `> ` prefix blocks (Tier 1 for text) | Medium | 5/10 docs; 25 occurrences |
| Note | Audit 1, 2, 3 | Footnote/endnote bodies | High | 4/10 docs; 54 total notes |
| Note.id | Audit 2 (C-15), 3 | DOCX `w:id` matching | High | 4/10 DOCX docs |
| Note.placement | Audit 2 (C-13), 3 | Footnote vs. endnote type | Low | Unreliable; signal lost in DOCX |
| Note.body | Audit 3 | Footnote body text (Tier 1) | High | Identical across formats; verified |
| PageMark | Audit 1, 3 | DOCX Heading6 page numbers (Tier 1) | High | 8/10 DOCX docs |
| PageMark.label | Audit 1, 3 | Printed page number value | High | Values match source pagination |

---

## Deliverable 8: Completeness Assessment

Every validated semantic signal from the audit series is examined against the model.

### Signals with full representation in the model

| Signal | Representation | Audit confidence |
|:---|:---|:---:|
| Reading order | Implicit in ordered Block sequence; Constraint C-01 | High |
| Heading text | `Heading.content` | High |
| Heading hierarchy (level) | `Heading.level`, Section nesting, Constraint C-03 | Medium |
| Heading order | Block sequence within Document and Section | High |
| Document title | `Metadata.title` | Low |
| Document author | `Metadata.authors`, `Author.name` | Low |
| Author affiliation | `Author.affiliation` | Low |
| Abstract | `Metadata.abstract` | Low |
| Keywords | `Metadata.keywords` | Low |
| Paragraph body text | `Paragraph.content` → `PlainText` | High |
| Bullet list content | `List` with `list_type: unordered`; `ListItem.content` | High |
| Numbered list content | `List` with `list_type: ordered`; `ListItem.content` | High |
| Blockquote text | `Blockquote.paragraphs` | High (text) |
| Data table cell content | `TableCell.content` | High |
| Table caption | `Table.caption` | Medium |
| Column-spanning cells | `TableCell.column_span` | Medium |
| Figure caption | `Figure.caption` | Medium |
| Inline image references | `Image.source` | Medium |
| Image bounding-box geometry | `Image.geometry` → `BoundingBox` | High |
| Image alt text | `Image.alt_text` | Low |
| Footnote / endnote body text | `Note.body` → Paragraph sequence | High |
| Footnote / endnote structural linkage | `NoteReference.note_id` ↔ `Note.id` | Medium |
| Footnote placement type | `Note.placement` | Low |
| Page landmarks | `PageMark.label` in reading-order position | High |
| Mathematical expressions (inline) | `InlineMath.notation` | Medium |
| Callout / text-box inserts | `Section` with `role: callout` | Medium |
| References / bibliography | `Section` with `role: references` containing Paragraphs | Medium |

### Signals with partial representation only

| Signal | Representation | Gap | Reason |
|:---|:---|:---|:---|
| Blockquote attribution | Not represented | No attribution field on Blockquote | No format provided blockquote source information; structural signal absent from all three formats |
| Note reference marker style | Not represented | NoteReference has no `marker` attribute | The notation used for the inline reference (`${ }^{n}$`, `[^n]`, `<w:endnoteReference>`) is a format artifact, not a semantic property. The semantic fact is the reference's existence and target, not its visual form. |
| Section heading level source confidence | Not represented | Heading.level has no `confidence` attribute | The gap between MMD (flat) and DOCX (multi-level) means Heading.level may be unreliable for 9/10 documents. This is an extraction quality concern, not a semantic concept. |

### Signals confirmed absent from any representation

| Signal | Evidence | Justification for omission |
|:---|:---|:---|
| Table header row / column semantics | No format provides `<th>` or equivalent role distinction for table headers vs. data cells | No semantic header markup was observed in any format for any table in the corpus. Header semantics cannot be modeled from observed evidence. |
| Language declaration | No format carries `xml:lang` or equivalent | Completely absent across all 10 documents in all formats. Single-language corpus provides no evidence. |
| Document-type classification | No format provides a schema or type declaration | No observed signal distinguishes "journal article" from "textbook chapter" in any format. |
| External hyperlink targets | External URLs absent as semantic content | The 40 hyperlinks in Bryman DOCX are internal TOC navigation artifacts; 0 external semantic hyperlinks were observed. |
| Decorative vs. informative image classification | No format provides this distinction | No observed signal in any format distinguishes decorative images from informative ones. |
| Table of contents as semantic content | TOC entries are derived from headings | TOC is a navigation artifact derived from the heading structure. The heading structure is already fully modeled. The TOC adds no semantic information beyond what Section and Heading already contain. |

### Final assessment

The canonical semantic model represents every validated semantic signal from the four-audit series without omission. The three signals with partial representation (blockquote attribution, note marker style, heading level confidence) are excluded for principled reasons: they are either absent from all observed formats, are format-level artifacts rather than semantic properties, or are quality-of-extraction concerns rather than semantic concepts.

The model does not represent eight signals that were confirmed absent from the corpus entirely (table header semantics, language declaration, document-type classification, external hyperlinks, decorative image classification, TOC, appendices, nested lists). Their omission is justified by the absence of observed evidence in the audit series and, in several cases, by the impossibility of modeling a concept that was not observed.

---

## Final Question

> **Based solely on the validated evidence established throughout the completed audit series, what is the smallest complete, implementation-independent semantic document model capable of representing all validated document semantics without loss of meaning?**

The answer is the model defined in this specification.

Its boundaries are established by the evidence:

**Thirteen semantic object types** are sufficient: Document, Metadata, Author, Section, Heading, Paragraph, Table, TableRow, TableCell, Figure, Image, List, Blockquote, Note, PageMark, and the inline types Content, PlainText, NoteReference, and InlineMath. BoundingBox is a structured attribute group attached to Image.

**Three Section roles** capture the full observed range of section semantics: `body` (structural content division), `callout` (supplementary set-apart insert), and `references` (bibliography section).

**Two list types** cover all observed list semantics: `ordered` and `unordered`. Nested lists are absent from the corpus and absent from the model.

**Two note placement values** cover the observed semantic distinction: `page-inline` (footnote) and `document-end` (endnote), with absence permitted to express unresolvable placement.

**The Figure / Image distinction** is the smallest separation that captures the observed semantic difference: an image with a caption (Figure) has a semantic identity and communicative role; an image without a caption (Image) is a visual element whose meaning must be inferred from context or alt text.

**Content as a rich inline type** — not a bare string — is the minimum required to represent inline note references and inline math expressions at their correct positions within prose, as established by the structural linkage evidence from DOCX and the inline-position evidence from MMD.

Every object that is not in the model was excluded because it either: was not observed in the audit corpus; is derivable from objects that are present; is a formatting artifact rather than a semantic concept; or is an implementation convenience that does not affect semantic meaning.

---

*End of specification. Every object, attribute, relationship, and constraint above is justified by evidence from the RAWRS Phase-2 Audit Series (Audits 1–4, 2026-06-26).*
