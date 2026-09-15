# RAWRS product & architecture audit — 2026-08-12

**Base:** `4b2bfb1` (L2.3-c) · **Status:** audit only. No code changed, nothing committed.
**Evidence:** three read-only probes run this session over the 10 benchmark PDFs
(`enable_ocr=False`), the 10 human-remediated DOCX in `samples/benchmark/remediated_docx`,
and the Mathpix MMD packages in `samples/mathpix/`.

---

## 0. Governing standard, and where the docs disagree with the code

The governing standard for this audit is `docs/ChecklistBeforeSubmittingDoc.xlsx`
(50 rows, 10 sections, "Both" vs "STEM") and `docs/Checklist for Document Remediation1.docx`
(the WinVinaya house style: Times New Roman 12pt, H1 16pt / H2 14pt / H3–H5 12pt black bold,
page number as **Heading 6 at the top-left of each page**, page break at the end of every PDF page).

Disagreements found between project documents and the code, reported rather than resolved:

| Document | Claim | Reality in code |
|---|---|---|
| `RAWRS_PROJECT_CONTEXT.md` §Tech Stack | "Neither frontend nor backend has been started — there is no frontend directory and no FastAPI/server code anywhere in this repo" | Both exist (`src/api/`, 41 routes; `frontend/`). `KNOWN_LIMITATIONS.md` already corrects this; the context file was not updated. |
| `RAWRS_PROJECT_CONTEXT.md` §Current Scope | "Table Remediation — Not Supported" | Implemented (FEATURE_015.x, `_add_semantic_table`, TABLE_001–007). |
| `CURRENT_STATE.md` | Footnotes encoded "via bookmark/hyperlink, not native Word footnotes" | Superseded by L4b — real `word/footnotes.xml` / `word/endnotes.xml` parts. |
| `PAGE_RULES.md` §Page Break | "At the end of every PDF page insert a Word Page Break" | Correct as implemented, **but the checklist's page unit is the printed book page, not the PDF page.** See §3.4. |
| `P4C_DOCX_PROJECTION_AUDIT.md` §4 | "The corpus has zero lists" | True of `Document.lists` on the native path; **false of the corpus.** The human output has 161 list paragraphs across 6 of 10 documents, and Mathpix recovers 99 items. See §3.2. |
| brief's document list | `TASKS.md` does not exist in this repo | — |

**No generic accessibility assumption has been substituted for a project rule.** Where WCAG
would say more than the checklist (e.g. programmatic list semantics), the checklist already
says it too ("Ensure bulleted and numbered lists are formatted using Word's list features").

---

## 1. Current RAWRS capability — precise current-state model

### A. What RAWRS detects automatically

| Detected | Source | Corpus evidence |
|---|---|---|
| Pages, per-line blocks, bbox, font size, bold | PyMuPDF, `structure_detector` | 120 of 161 pages carry blocks; **41 carry none** |
| Physical zone (header/body/footer) + repetition | `layout_signals` | L1/L2 evidence on every block |
| Artifacts: running header/footer, page number, decorative repeat, running title | `classify_artifacts` (L2.1–L2.3-c) | 231 classifications, 197 suppressions |
| Headings H1–H6 by font-rank + bold + isolation + position-rank | `heading_detector`, `heading_signals` | 86 content headings corpus-wide |
| Printed page labels | `structure_detector` margin scan | **107 of 161 pages**; 0 on both scanned documents |
| Paragraph grouping | `paragraph_assembly` (Stage 5c) | 745 paragraphs |
| Front matter (title/author/affiliation roles) | `front_matter_extractor` | present on 10 of 10 |
| Footnotes/endnotes — **only literal Unicode superscript glyphs** | `footnote_detector` | 7 notes, all endnotes |
| Images + decorative/duplicate filtering + captions | `image_extractor` | 122 images, 2 captions |
| Tables — vector borders, horizontal rules, span/column alignment | `table_extractor` + 4 detectors | 5 tables, 640 cells |
| Reading-order anomalies (flag only) | PAGE_003 | — |
| OCR need per page; Docling → Surya fallback | `router`, `docling_engine`, `surya_engine` | text only, **no geometry** |

**Not detected on the native path at all: lists.** `detect_lists_from_pdf()` exists but is wired
only into `ListVerifier` as a cross-source candidate source. `Document.lists` is assigned in exactly
one place in `src/` — the Mathpix ingestor.

### B. What it can represent semantically

`Document` holds `pages`, `blocks`, `paragraphs`, `headings`, `footnotes`, `tables`, `images`,
`lists`, `callouts`, `front_matter`, `corrections`, `verification_findings`, plus provenance
(`import_provider`, per-object `provenance`, `evidence_items`, `confidence`) and identity
(`SemanticObject.id` on every renderable object; `TextBlock.block_id`; `Paragraph.id` from W-2a).

Cannot represent: list numbering start/restart, per-`ListItem` identity, `ListBlock` placement
(`source_block_ids`), figure-caption identity, image ordering, "this heading is the document title",
the `## Endnotes` section object, span-level typography (font name, per-char flags, baseline),
hyperlinks, bookmarks, a table of contents, language as a document property, abbreviation expansions.

### C. What is correctable through a reversible `CorrectionRecord`

Eight `object_type` values reach the rail: `heading`, `figure`, `table`, `paragraph`, `footnote`,
`metadata`, `reading_order`, `page_label`. Eleven verifiers are registered with the engine.
`revert()` exists for the registered asset types; the **page-label handler records a record but
mutates the document directly and has no verifier**, so its undo is not real.

### D. What Markdown projects directly from the ContentStream

Prose paragraphs (P3b), headings, page markers, page fences, note references/definitions,
front-matter blocks. Still text-keyed: the 41 blockless pages, tables/lists/captions on the
line path, and the Mathpix `_render_page_semantic` path.

### E. What DOCX projects directly from the ContentStream

Prose, headings, page identity and page breaks (P4b); tables via `TABLE` nodes (P4c-1);
emphasis via `format_runs`; note reference positions via `resolve_note_references`;
note **type** via `Footnote.note_type` (L4b).

### F. What still requires Markdown reconstruction

Per `P4C_DOCX_PROJECTION_AUDIT.md` §3, after `258d25f`: image path/alt (`_IMAGE_PATTERN`),
caption text **and its association**, note label+body (`_FOOTNOTE_DEFINITION_PATTERN` — P4c-2
is audited, not built), list item text and marker kind, the `## Endnotes` heading,
and everything on the blockless/Mathpix fallback paths.

### G. What still depends on physical source lines

The 41 blockless pages (`Page.cleaned_text` only), the Mathpix semantic render path,
`_front_matter_source_texts` / `_caption_source_texts` on the OCR path, and `Footnote` lookup
keyed on the renumber-sensitive `label` rather than `footnote_id` in `_NoteRegistries`.

### H. What is inaccessible to the Workspace

**Lists** (`GET /lists` only — no PATCH, no POST, no DELETE, no correction `object_type`),
**callouts** (GET only), figure captions (no identity), list items (no identity),
validation findings (cannot be acknowledged as intentional), and anything on a blockless page,
which has no object to select.

### I. Autonomous vs propose vs reviewer-only

| Tier | What |
|---|---|
| **Autonomous (AUTO)** | artifact suppression of running headers/footers/page numbers; paragraph grouping; page-break placement; heading level assignment; note part selection; image filtering; XML sanitisation. Corpus: 197 auto-applied suppressions, 161 auto-applied corrections. |
| **Propose (PROPOSE)** | running-title promotion (L2.3-c, 17 on the stress doc), cross-source findings, AI alt text, table detections needing header confirmation. Corpus: 60 proposed corrections. |
| **Reviewer-only** | alt-text acceptance, reading-order reordering, table creation, page-label schemes, heading promotion/demotion, paragraph text edits, metadata. |

---

## 2. Remediation capability matrix

Against the checklist. `Detect` = RAWRS finds it in a PDF · `Represent` = a model object holds it ·
`Verify` = a registered verifier/cross-source check exists · `Review` = a reviewer can see it in
the Workspace · `Correct` = reversible `CorrectionRecord` · `Project` = reaches DOCX from the model ·
`Validate` = a validation rule fires on it.

✅ complete · 🟡 partial · ❌ absent · ⚠️ present but architecturally unsafe

| Item | Detect | Represent | Verify | Review | Correct | Project | Validate |
|---|---|---|---|---|---|---|---|
| document metadata | 🟡 | ✅ | ✅ | ✅ | ✅ | ⚠️ | 🟡 |
| language | ❌ | ❌ | ❌ | ❌ | ❌ | 🟡 (`en-US` hardcoded in styles) | ❌ |
| title | 🟡 | ✅ | ✅ | ✅ | ✅ | ⚠️ (core property empty on 10/10) | 🟡 |
| author | 🟡 | ✅ | ✅ | ✅ | ✅ | ⚠️ (`python-docx` on 10/10) | 🟡 |
| headings | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 |
| heading hierarchy | ⚠️ | 🟡 | ❌ | 🟡 | 🟡 | ⚠️ (H2 with no H1 on 6/10) | 🟡 |
| page labels | 🟡 (107/161) | ✅ | 🟡 | ✅ | ⚠️ (no verifier → no real undo) | ✅ | ✅ |
| reading order | 🟡 (flag only) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| paragraphs | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 |
| lists | ❌ **native** / ✅ Mathpix | ✅ | ✅ | ❌ (GET only) | ❌ | ⚠️ (nesting destroyed) | ❌ |
| tables | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| table headers | ⚠️ (row 0 assumed) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| table captions | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 |
| table summaries | ❌ (human-entered) | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ |
| figures | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| alt text | 🟡 (placeholder + on-demand AI) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| decorative figures | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 |
| footnotes | ⚠️ (Unicode glyph only) | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 |
| endnotes | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 |
| note references | 🟡 | ✅ | ✅ | 🟡 | 🟡 | ✅ | ❌ (pairing unproven) |
| hyperlinks | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| bookmarks | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| table of contents | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| front matter | ✅ | ✅ | ✅ | 🟡 | 🟡 | ✅ | 🟡 |
| page breaks | ✅ | ✅ | ✅ (PI-10) | ❌ | ❌ | ✅ | ✅ |
| running headers/footers | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | 🟡 |
| OCR/extraction defects | 🟡 | 🟡 | ❌ | ✅ | ❌ | 🟡 | 🟡 (OCR_001/002) |
| malformed characters | ✅ (sanitiser) | n/a | ❌ | ❌ | ❌ | ✅ | 🟡 |
| ligature decomposition | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| abbreviation expansion ("US"→"U S") | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| cross-page sentence completion | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| duplicate content | 🟡 (images) | 🟡 | ✅ | 🟡 | ✅ | ✅ | 🟡 |
| artifacts | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | 🟡 |
| accessibility validation | 🟡 | ✅ | — | ✅ | ⚠️ (findings cannot be acknowledged) | n/a | 🟡 |
| DOCX structural semantics | n/a | ✅ | ✅ (PI-6/10/11) | ❌ | ❌ | ✅ | 🟡 |
| reviewer corrections | n/a | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 |
| undo/history | n/a | ✅ | ✅ | ✅ | 🟡 (page_label has no verifier) | ✅ | ❌ |
| generated remediation content | ❌ | ❌ | ❌ | ❌ | ❌ | 🟡 (`## Endnotes` only) | ❌ |

---

## 3. Real-output failure analysis

Ten benchmark PDFs, RAWRS native path vs the human-remediated DOCX for the same source.

| Document | PDF pp | RAWRS content headings (levels) | Human | RAWRS list paras | Human | RAWRS tables | Human | RAWRS note refs | Human |
|---|---|---|---|---|---|---|---|---|---|
| 1. Nature of Enquiry | 28 | 32 (H2 14, H3 18) | 23 (H1 1, H2 18, H3 4) | **0** | 45 | 2 | 2 | 4 | 4 |
| 1. Aims of Education | 4 | **0** | 1 (H1) | 0 | 0 | 0 | 0 | **0** | 11 |
| 2. Bryman (scanned) | 26 | **0** | 19 (H1 2, H2 8, H3 9) | **0** | 49 | **0** | 21 | 0 | 0 |
| 2. Bruner FolkPedagogy | 26 | 1 (H1) | 4 (H1 1, H2 3) | 0 | 4 | 0 | 0 | **0** | 36 |
| 3. sockett | 9 | 12 (H2) | 13 (H1 1, H2 2, H3 10) | 0 | 3 | 0 | 0 | 0 | 0 |
| 4. O'Leary (scanned) | 13 | **0** | 26 (H1 1, H2 5, H3 20) | **0** | 51 | 0 | 0 | 0 | 0 |
| 4. Teaching as a professional discipline | 27 | 10 (H1 1, H2 9) | 10 (H1 1, H2 9) | 0 | 0 | 0 | 0 | 0 | 0 |
| 5. Calderhead | 4 | 2 (H1 1, H2 1) | 1 (H1) | 0 | 0 | 0 | 0 | 0 | 0 |
| 6. Fullan & Hargreaves | 6 | 2 (H1 1, H2 1) | 2 (H1 1, H2 1) | 0 | 9 | 0 | 0 | 0 | 0 |
| 7. brinkman | 18 | 16 (H2) | 16 (H1 5, H2 11) | 0 | 0 | 3 | 5 | 3 | 3 |
| **Total** | 161 | **75** | **115** | **0** | **161** | **5** | **28** | **7** | **54** |

### 3.1 Heading hierarchy — the most visible defect

RAWRS produces **no H1 at all on 6 of 10 documents** while emitting H2 and H3 on them.
The checklist forbids exactly this ("Check hierarchical order of headings is correct — no skipped
heading levels"). It is a *consequence of a decision, not a bug*: L3.2 deliberately made position
alone insufficient to create an H1, so a title with no typographic support now yields no H1 rather
than a wrong one. The decision was right; **the missing half is that nothing routes the resulting
hierarchy violation to a reviewer as a decision to make.** `HEADING_002` reports absence of a title;
no rule reports "this document's outline starts at H2".

Layer: **semantic-model + validation gap**, not extraction, not projection. Genuinely automatable:
detecting the skip. Requires human judgement: which line is the title.

### 3.2 Lists — the largest single gap, and its cause is not what the roadmap says

RAWRS emits **zero list paragraphs on all ten documents**. The human output has **161**.

`P4C_DOCX_PROJECTION_AUDIT.md` deferred lists to last (P4c-4) on the grounds that "the corpus has
zero lists". That is true of `Document.lists` and false of the corpus. Root cause, traced:

```
detect_lists_from_pdf()   →  used ONLY by ListVerifier (cross-source candidate source)
Document.lists = ...      →  assigned in exactly one place in src/: the Mathpix ingestor
native pipeline           →  never populates lists at all
```

Measured this session, the existing geometric detector is **not fit to be promoted as-is**:

| Document | `detect_lists_from_pdf` lists / items | Human list paragraphs |
|---|---|---|
| Bruner | 45 / 57 | 4 |
| brinkman | 14 / 14 | 0 |
| Nature of Enquiry | 5 / 5 | 45 |
| Bryman | 0 / 0 | 49 |
| O'Leary | 0 / 0 | 51 |
| **Total** | **68 / 80** (1.18 items per "list") | **161** |

Mostly single-item false positives on the documents with no lists, and nothing on the two documents
with the most. **The Mathpix path, by contrast, is nearly exact:**

| Document | native path | Mathpix path | human |
|---|---|---|---|
| Bryman | 0 paragraphs, 0 content headings, 0 lists, 0 tables, 112 images | 171 paragraphs, 79 headings, **15 lists / 49 items**, 1 table | 19 headings, **49 list paragraphs**, 21 tables, 3 images |
| O'Leary | 0 paragraphs, 0 content headings, 0 lists | 61 paragraphs, 47 headings, **17 lists / 50 items** | 26 headings, **51 list paragraphs** |

49 items vs 49 human list paragraphs; 50 vs 51. **The semantic content exists — on the path the
projection architecture deliberately excludes.**

Layer: **detection gap on the native path, representation-complete, projection debt on Mathpix.**

### 3.3 Notes — bug_005 quantified on the corpus

Aims: RAWRS 0 note references, human 11. Bruner: RAWRS 0, human 36. **47 notes missed on two
documents** — consistent with `bug_005` (only a literal Unicode superscript glyph is recognised as
a marker). Layer: **extraction/representation** — span-level information is discarded in `TextBlock`
before any detector sees it (`feature_005_span_level_text_model`).

### 3.4 Page breaks — where the wrong decision originates

Traced through the chain:

```
source evidence:   PyMuPDF page count        → 161 physical pages, correct
semantic model:    Page objects              → 161, one per physical page, correct
ContentStream:     PAGE_MARKER per Page      → 161 nodes, correct
Markdown:          PAGE_BREAK_MARKER fence   → pages-1 fences, correct
DOCX:              open_page() emits a break because another Page exists (P4b)
```

RAWRS emits `pages − 1` breaks, plus one before the generated endnote section. Measured:
28 pp→28 breaks (27 + endnotes), 18→18 (17 + endnotes), and exactly `pages − 1` on the other eight.
**The mechanism is correct, and P4b made it a fact about `Page` rather than about a comment.**

The disagreement with the human output is elsewhere and is architectural:

| Document | PDF pages | RAWRS breaks | Human breaks | Human H6 markers |
|---|---|---|---|---|
| sockett | 9 | 8 | **17** | **17** |
| O'Leary | 13 | 12 | **0** | **0** |
| Bruner | 26 | 25 | 22 | 22 |

**RAWRS's page unit is the physical PDF page. The remediation standard's page unit is the printed
book page.** sockett is a 2-up scan: nine sheets carrying seventeen printed pages, and the human
remediator broke on the *printed* page. RAWRS has no representation for "this sheet contains two
pages", so it cannot make that decision — and cannot currently even record that a reviewer made it.
O'Leary shows the opposite: the human emitted no page markers or breaks at all.

**Does the architecture have enough information to fix this safely? No.** `Page` is 1:1 with the
physical page throughout the model and `printed_label` is one value per `Page`. A printed-page unit
needs either a `Page`-splitting representation or a label section mapping one sheet to two labels.
This is a **model gap**, not a projection bug, and it is in no current milestone.

### 3.5 Page labels

RAWRS's marker text disagrees with the human's on four documents:
Bryman all 26 (physical `1..26` vs printed `19..44`, because 0 labels were detected on a scanned
document), brinkman page 1 (`1` vs `342`), Bruner page 1 (`1` vs `44`), sockett
(`['1','2','I','4','I','6']` — **`I` is OCR garbage accepted as a printed label**).
Layer: detection + validation — no rule fires on a non-monotonic or non-numeric label sequence.

### 3.6 Images on the scanned document

Bryman: RAWRS embeds **112 images**, each with placeholder alt text; the human output has 3.
These are page-reconstruction raster bands. `_page_reconstruction_indices()` filters them for
`IMAGE_VERIFY_002` but they still reach the DOCX. Layer: **detection**, with a direct output
consequence — a screen-reader user meets 112 "Image, pending review" announcements.

### 3.7 Metadata, bookmarks, hyperlinks, TOC

RAWRS on 10/10: core `title` empty, `author` = `python-docx`, `subject` empty, **0 bookmarks,
0 hyperlinks, no TOC field**. Human: 2–121 bookmarks per document; Bryman carries a TOC field and
40 hyperlinks. Four checklist rows ("Set Title, Author and Subject", "Generate an automatic Table
of Contents", "Ensure navigation via bookmarks", "Hyperlinks have meaningful display text") are
unmet by construction. Layer: **projection + representation** — `title`/`author` are already in the
model and reviewable; DOCX simply never writes them. That part is pure projection debt.

### 3.8 Ground-truth caveat, stated rather than assumed

Eight of the ten `remediated_docx` carry core author `html-to-docx`. They are converted artifacts
(most likely from the Mathpix HTML), possibly hand-corrected afterwards. They are a sound **target
shape** and a sound source of "which objects should exist", but they are not proof of a human's
editorial judgement, and no claim above depends on them being hand-authored.

---

## 4. Remaining semantic gaps (the model cannot express it)

1. Printed-page unit ≠ physical page (§3.4).
2. Span-level typography → footnote markers, superscripts, subscripts (bug_005, 47 notes).
3. `ListItem` identity; `ListBlock.source_block_ids`; list numbering start/restart.
4. Figure-caption identity.
5. `Image` ordering.
6. "This heading is the document title."
7. The `## Endnotes` section as an object.
8. Hyperlinks, bookmarks, TOC.
9. Language as a document property, not a hardcoded style value.
10. Generated/editorial content (abbreviation expansion, cross-page sentence completion) has no representation for "RAWRS wrote this, a human approved it".

## 5. Remaining projection gaps (the model knows it; the projection cannot use it)

| Site | Knows it upstream? | Class |
|---|---|---|
| DOCX core properties never written from `Document.metadata` | **yes** | pure projection debt |
| Note definitions/labels re-parsed from Markdown | **yes** (P4c-2 audited, unbuilt) | projection debt |
| Image path/alt re-parsed from Markdown | **yes** | projection debt |
| Caption association by Markdown adjacency | partly (no identity) | model gap G1 |
| List nesting destroyed by `line.strip()` before matching | **yes** (`ListItem.level`) | projection debt |
| `_NoteRegistries` keyed on renumber-sensitive `label` | **yes** (`footnote_id`) | ⚠️ unsafe projection debt |
| Mathpix documents rendered by `_render_page_semantic`, outside the stream | **yes** | **the largest projection gap** |
| 41 blockless pages rendered from `Page.cleaned_text` | **no** — no blocks exist | genuine extraction/model gap |

## 6. Remaining correction / workspace gaps

Semantic mutations that bypass `finding → CorrectionRecord → verifier → model → stream → projection → validation → undo`:

1. **`src/mathpix/ingestor.py::_register_figures`** extends `verification_findings` directly — import-time findings can never be applied, rejected or undone (contradicts ADR-016).
2. **Page-label handler** records a `CorrectionRecord` but mutates the document directly; no `page_label` verifier exists, so `revert()` cannot work.
3. **Lists and callouts** have verifiers but no correction `object_type` and no PATCH/POST route — a reviewer cannot create, edit, split or delete a list.
4. **Table cell text** edits go through the Tables workspace but not a cell-level verifier.
5. **Validation findings cannot be acknowledged** as intentional — no state exists for "reviewed, acceptable".
6. **Export readiness counts `ValidationIssue` mirrors** of cross-source findings, so ~300 warnings already managed as `CorrectionRecord`s keep "Export Ready" red.

Not counted (correctly off the rail): lifecycle bookkeeping, issue triage, unaccepted AI suggestions, ingestion.

## 7. Autonomous vs reviewer-assisted boundary

| Genuinely automatable today | Needs reviewer confirmation | Needs human editorial judgement |
|---|---|---|
| page breaks, page markers, artifact suppression, paragraph grouping, heading **levels**, note part selection, image filtering, XML sanitisation, table rendering, DOCX metadata (once written) | which line is the title; heading promotion to H1; table header row; alt-text acceptance; page-label schemes; reading-order fixes; list creation on a scanned document | alt-text wording; table summaries; abbreviation expansion; cross-page sentence completion; whether a repeated line is furniture or content |

---

## 8. Mid-tier feasibility verdict

**"Mid-tier" defined from the project's own materials**: the checklist's 34 "Both" (non-STEM) rows —
structure, heading styles and hierarchy, lists, tables with headers and captions, alt text,
hyperlinks, footnotes/endnotes, page numbers and breaks, metadata, and a clean Word Accessibility
Checker run. The 16 STEM rows (equations, chemical notation, MathType) are explicitly out of Phase 1.

**Verdict: B — NOT YET, but the architecture is fundamentally capable.**

Not C: there is no architectural blocker to mid-tier. The correction rail, the identity model, the
ContentStream and both projections are real and measured. Not A: three object classes the checklist
treats as mandatory — **lists (161 paragraphs), heading hierarchy (6/10 documents with no H1), and
notes on superscript-encoded documents (47 missed)** — are not produced at all, so a reviewer has
nothing to accept or reject. A remediator receiving RAWRS's Bryman output today would have to build
the entire document structure by hand.

**Capability band: deterministic foundation, entering partial remediation.**
Not "reviewer-assisted remediation", because reviewer assistance requires the object to exist first.

**What prevents the next band**, precisely: for the document classes where remediation is most
expensive (scanned, list-heavy, note-heavy), RAWRS's native path produces no semantic objects, and
the path that *does* produce them (Mathpix) is excluded from the projection architecture by design.

---

## 9. Top 10 remaining blockers, ranked

| # | Blocker | Impact | Frequency | Centrality | Evidence | Risk |
|---|---|---|---|---|---|---|
| 1 | **Lists are never detected on the native path and have no review surface** | very high — 161 paragraphs | 6/10 docs | high | measured | medium |
| 2 | **Mathpix documents are outside the ContentStream/projection rail** | very high | every scanned doc | **highest** | measured (171 par / 79 headings / 49 items recovered) | high |
| 3 | **Blockless pages produce no blocks** — OCR emits text, no geometry | very high | 41/161 pages, 2 docs entirely | highest | measured | high |
| 4 | **Heading hierarchy: H2 with no H1, and no rule reports it** | high | 6/10 docs | medium | measured | low |
| 5 | **Notes undetected without a Unicode superscript glyph** (bug_005) | high | 47 notes, 2 docs | medium | measured | high (needs span model) |
| 6 | **DOCX never writes Title/Author/Subject** | medium | 10/10 | low | measured | **very low** |
| 7 | **112 raster bands embedded as figures with alt text** | high on that document | 1/10 | low | measured | low |
| 8 | **Page-label detection accepts OCR garbage; no monotonicity rule** | medium | 4/10 | medium | measured | low |
| 9 | **`_NoteRegistries` keyed on a renumber-sensitive label** | medium | latent | medium | code + P4c-2 audit | low |
| 10 | **Export readiness counts finding mirrors** | medium — blocks the product's own "done" signal | always | medium | 385/550 measured | medium |

**Bookmarks/TOC/hyperlinks sit deliberately below the line**: the checklist asks for them, but they
are additive output features, not blockers to representing the document.

---

## 10. Old-roadmap audit

| Milestone | Verdict | Why |
|---|---|---|
| P4c-2 (notes migration) | **KEEP**, demote from "next" | Fully audited, low risk, ~1 commit. Removes real projection debt (and the label-keying defect) but closes **zero** remediation gaps — the corpus's 7 notes already reach DOCX correctly. |
| P4c-3 (images + captions) | **KEEP, DEFER** | Same character: projection purity, no remediation gain. |
| P4c-4 (lists) | **REPLACE** | Its premise ("zero corpus coverage → lowest priority, highest risk") is falsified. Lists are the **most** frequently missed object. It must become a detection + review + projection milestone, not a parser-deletion step. |
| P4d (`markdown_content` leaves the signature) | **DEFER** | Cannot complete while the blockless and Mathpix paths exist. |
| P5 (`Projection` registry) | **DEFER** | Pure architecture; no remediation impact until a third format exists. |
| L2.3-a (physical-zone assignment) | **RETIRE** | Already falsified by measurement. |
| L6 | **RETIRE** (already done) | — |
| `feature_005` span-level text model | **KEEP, SPLIT** | The only route to bug_005, but a large model change. Split: (a) preserve span flags on `TextBlock`, (b) footnote markers, (c) sub/superscript, (d) equations. |
| Cross-page paragraph stitching | **PROMOTE from "deferred"** | The checklist mandates it in as many words: "The sentences should not be incomplete at the end of the page. Complete the sentence by taking it from next page." It has been sitting in `KNOWN_LIMITATIONS.md` as a scope-sign-off item while being an explicit customer requirement. |
| Blockless-page extraction | **PROMOTE to a named milestone** | Currently only a caveat in four documents. It is blocker #3 and the precondition for #1 on scanned input. |

---

## 11. ONE recommended next milestone

### **W-3 — Lists become a real remediable object**

**Problem statement.** RAWRS emits zero list structure for every document in the corpus, while the
target output contains 161 list paragraphs across six of ten documents. `ListBlock`, `ListItem`,
the `LIST` stream node, `ListVerifier`, the Markdown renderer and the DOCX list styles all already
exist. What is missing is a trustworthy source of lists per input path, a reviewer surface to
create/edit/reject one, and a projection that preserves nesting.

**Why it matters to real remediation.** "Ensure bulleted and numbered lists are formatted using
Word's list features", "Check that nested lists use correct hierarchy and indentation" and "Avoid
using manual symbols or numbers for lists" are three separate mandatory checklist rows. A list
rendered as plain paragraphs is a failure a screen-reader user hears immediately, and it is the
single most common object RAWRS drops.

**Evidence.** §3.2: 0 vs 161. `detect_lists_from_pdf` produces 68 lists / 80 items, with 45 false
positives on one document and 0 on the two documents that need it most. Mathpix produces 49 items
where the human has 49, and 50 where the human has 51.

**Current architectural owner.** `src/lists/list_detector.py` (candidate source, verification-only),
`src/mathpix/ingestor.py::_group_list_items_to_lists` (the only populator), `src/models/list_block.py`,
`src/structure/content_stream.py` (LIST node), `src/verification/lists.py`,
`markdown_builder._render_lists`, `docx_generator._add_list_paragraph`.

**Smallest coherent scope.**
1. `ListItem` becomes a `SemanticObject` (identity), so an item can be addressed by a correction.
2. `POST/PATCH/DELETE /documents/{job}/lists` + a `list` correction `object_type` with a verifier,
   so a reviewer can create a list from selected paragraphs, change its type, re-level an item, or
   reject a detection — the same rail tables already have.
3. DOCX renders lists from `LIST` nodes with `numPr`/`ilvl` from `ListItem.level`, replacing the
   `line.strip()` path that destroys nesting.
4. A validation rule: "paragraph looks like a list item but belongs to no `ListBlock`".

**Explicit non-goals.** Promoting `detect_lists_from_pdf` to the native pipeline (measured unfit).
List numbering start/restart. Mixed-type nesting. Migrating the Mathpix render path wholesale.
Solving blockless extraction. Bookmarks/TOC.

**Invariants.**
- **PI-13:** every `ListBlock` has exactly one `LIST` node; every node resolves by id; every item
  materialises exactly once, in order, at the level the model records.
- No `ListBlock` is ever created by a projection.

**Corpus measurement gate.** Mathpix path: 15 lists / 49 items (Bryman) and 17 / 50 (O'Leary) must
survive into DOCX as `numPr` paragraphs with matching `ilvl`. Native path: list count must remain
**0** — this milestone must not silently enable the false-positive detector.

**Regression gate.** Full suite green in sequential batches; the ten native Markdown hashes
unchanged (this milestone touches no native-path output).

**Projection gate.** `check_docx_projection` extended with `numPr@ilvl` per list paragraph, item
order and item text — the (d) row already proposed in `P4C_DOCX_PROJECTION_AUDIT.md` §7.

**Reviewer/workspace implications.** This is also the answer to §9's "first missing Workspace
primitive": **object creation for a class RAWRS cannot detect**. Tables already have it
(`POST /tables`, for borderless academic tables the detector misses). Lists do not. Giving lists the
same primitive is what turns RAWRS from "an engine that reports what it found" into "a workstation
where a reviewer completes what it missed".

**Expected commit boundaries.** (1) identity + verifier + correction type; (2) API routes;
(3) DOCX renders from `LIST` nodes with nesting + PI-13; (4) validation rule + fixtures.

### Unresolved architectural question — stopping here as instructed

**Should the Mathpix render path (`_render_page_semantic`) join the ContentStream before or after
this milestone?** Lists exist only on Mathpix documents today, so W-3's DOCX step must either
(a) render `LIST` nodes for Mathpix documents, which means the traversal must place them —
partially pre-empting blocker #2 and enlarging the scope above; or (b) keep Mathpix on its existing
renderer, delivering W-3's rail and review surface but no visible output change yet.
**(a) is right on the evidence and larger than the scope above.** I have not chosen. This needs a
decision before any code.

---

## 12. What should explicitly NOT be built yet

- Bookmarks, TOC, hyperlinks — checklist rows, but additive output, not blockers.
- `Projection` registry (P5) — no third format exists.
- Equation/STEM support — explicitly out of Phase 1.
- Promoting `detect_lists_from_pdf` into the native pipeline — measured unfit.
- A `Caption` semantic object — G1 is solvable from the image node.
- Automatic reading-order reconstruction — a standing decision, not a gap.
- Cross-page table detection.
- Anything that makes byte-identical DOCX a gate again.

---

## 13. Final answer

**"Is RAWRS actually becoming a viable remediation product, or are we building infrastructure
without reaching remediation?"**

Both, and the split is clean enough to name. The infrastructure is real and load-bearing: identity
on every object, a reversible correction rail with eleven verifiers, a single reading-order
authority, two projections that increasingly read the model instead of each other's output, and a
measurement discipline that has now falsified three of its own proposals (L2.3-a, the lockstep
cursor, and — in this audit — the list detector). That is not scaffolding.

But the last four milestones (P4a, P4b, P4c-1, and P4c-2's audit) closed **zero** remediation gaps.
They moved already-correct output from one code path to a better one. Meanwhile the objects a
remediator actually spends the day on — lists, heading hierarchy, notes on scanned pages — moved not
at all. The projection track has been improving the 120 pages that already worked, while the 41 that
produce nothing stayed exactly where they were.

The honest read: **RAWRS is a viable remediation product for born-digital, prose-dominant documents
with typographically-detectable headings, and is not yet one for anything else.** Four of the ten
benchmark documents are already close to mid-tier; two produce essentially nothing. Continuing
P4c-2 → P4c-3 → P4d → P5 would leave that ratio exactly where it is. The recommendation above is the
first milestone in some time whose success would be visible in the output rather than in the
architecture.
