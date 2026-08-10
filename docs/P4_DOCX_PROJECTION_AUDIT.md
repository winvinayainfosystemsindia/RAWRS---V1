# P4 — DOCX projection audit

**Date:** 2026-08-10 · **Status:** audit only, nothing implemented · **Base:** `f5c610d`
**Corpus:** 10 native benchmark PDFs, `enable_ocr=False`, no Mathpix.

---

## 1. Current DOCX architecture

```
Document ──build_markdown()──> Markdown string ──generate_docx(document, markdown)──> OOXML
                                                        │
                                                        └── also reads Document directly (hybrid)
```

Two call sites, both passing Markdown as the body source of truth:
`src/pipeline/phase1_pipeline.py:477` (Stage 7) and `src/api/routes.py:1934` (re-generation).

`generate_docx()` is a **single-pass line state machine** over
`markdown_content.splitlines()` (`docx_generator.py:343`), carrying four pieces of
mutable state: `pending_caption_after_image`, `in_front_matter_zone`,
`pending_table_id`, `pipe_table_rows`. It is *already partly hybrid* — it reads
`Document` for image alignment, decorative status, table models, note kinds and
front-matter roles, and already imports `build_content_stream` (L5'a).

---

## 2. Markdown-parsing inventory

Every regex and line test, with what it recovers and where that truth already lives.

| # | Pattern / test | Line | Recovers | Real source of truth | Class |
|---|---|---|---|---|---|
| 1 | `splitlines()` | 343 | body order | `ContentStream` node order | **D** |
| 2 | `_HEADING_PATTERN` `^(#{1,6})\s+(.+)$` | 244 | heading level + text | `Heading.level`, `.text` | **D** |
| 3 | `line == PAGE_BREAK_MARKER` | 408 | page boundary | `ContentNode.page_number` change | **D** |
| 4 | H6 at `index == 0` opens front-matter zone | 429 | front-matter *position* | `FRONT_MATTER` nodes | **D** |
| 5 | `_IMAGE_PATTERN` `^!\[alt\]\(path\)$` | 245 | image path + alt text | `Image.file_path`, `Figure.alt_text` | **D** |
| 6 | `_CAPTION_PATTERN` `^\*(.+)\*$` | 246 | figure caption | `Figure.caption` | **D** |
| 7 | `_FOOTNOTE_DEFINITION_PATTERN` | 253 | note label + **body text** | `Footnote.label`, `.body` | **D** |
| 8 | `_FOOTNOTE_REFERENCE_PATTERN` `\[\^label\]` | 252 | reference *position in text* | `Footnote.anchor_text` + `.anchor_offset` | **D** |
| 9 | `_LABEL_DISPLAY_NUMBER_PATTERN` `-(\d+)$` | 254 | printed number from label | `Footnote.number` | **D** |
| 10 | `_PIPE_TABLE_ROW/SEPARATOR_PATTERN` | 259–260 | table grid (fallback only) | `Table.rows` / `TableCell` | **D** (never fires on corpus) |
| 11 | `_TABLE_ID_COMMENT_PATTERN` | 269 | which `Table` model | `TABLE` node `object_id` | **D** → trivially B |
| 12 | `_TABLE_SUMMARY_COMMENT_PATTERN` | 264 | (skip only) | `Table.summary` | **C** |
| 13 | `_LIST_ID_COMMENT_PATTERN` | 276 | (skip only — no lookup) | `LIST` node `object_id` | **D** |
| 14 | `_BULLET_LIST_PATTERN` / `_NUMBERED_LIST_PATTERN` | 289/292 | list item text + kind | `ListBlock.list_type`, `ListItem.text/.level` | **D** |
| 15 | `_INLINE_FORMAT_PATTERN` `***`/`**`/`*` | 299 | bold / italic | `TextBlock.spans[].font_flags` (derived) | **D**, see §5 |
| 16 | plain line → `_add_body_paragraph` | 498 | paragraph text | `Paragraph.text` | **D** |

**Nothing here is mere format conversion.** All 16 recover a semantic fact that
exists upstream. Only #12 is pure mechanics (a skip); #10 is a fallback that never
fires on the corpus (all 5 tables resolve their model).

Already model-consuming, and therefore *not* to be touched: `_build_image_alignment_map`,
`_build_decorative_set`, `images_by_path` → `embedded_in_docx`, `_add_semantic_table`,
`_NoteRegistries(document.footnotes)` (L4b's `NoteType` → correct OOXML part),
`_front_matter_groups` (already reads `FRONT_MATTER` nodes).

---

## 3. Classification of every DOCX decision

| Class | Meaning | Items |
|---|---|---|
| **A** semantic fact in the model | — | note kind (L4b), table cells/merges/header rows, image alignment, decorative flag, front-matter roles/text, core properties |
| **B** ordering in ContentStream | — | paragraph, heading, image, table, list, note-definition, front-matter, page-marker placement |
| **C** projection-only OOXML mechanics | keep in DOCX | fonts/sizes/colours, `w:footnoteReference` vs `w:endnoteReference` emission, bookmarks, `tblHeader`, cell merges, `docPr` alt text, page-break element, `_safe_run_text` XML sanitation, list styles |
| **D** reconstructed from Markdown | the 16 rows in §2 | all recoverable from A+B **except** #15 (see §5) |
| **E** genuinely absent from model | — | hyperlinks (no model field, and Markdown emits none either — absent from *both* projections, so not a P4 regression); sub-paragraph mixed formatting; blockless-page text (§6) |

---

## 4. ContentStream coverage — measured

`NODES BY KIND` — 1,526 nodes over 161 pages:

| kind | count |
|---|---|
| page_marker | 161 |
| paragraph | 745 |
| heading | 82 |
| body_line | 385 |
| image | 122 |
| front_matter | 19 |
| note_definition | 7 |
| table | 5 |
| list | 0 |

| object type | in document | represented by a node | missing |
|---|---|---|---|
| paragraphs | 745 | 745 | **0** |
| headings (content) | 82 | 82 | **0** |
| page markers | 161 | 161 | **0** |
| images | 122 | 122 | **0** |
| tables | 5 | 5 | **0** |
| footnotes/endnotes | 7 | 7 | **0** |
| front-matter items | 19 | 19 | **0** |
| lists | 0 | 0 | — |

**Duplicate nodes: 0. Unplaceable objects: 0. Blockless pages: 41.**

Attributes reachable from an object a node already names (no node of their own, and
none needed): 122 alt texts, 2 figure captions, 87 printed page labels, 0 table
captions, 0 table summaries.

**Conclusion: the stream is sufficient for P4 for every object type.** No further
representation milestone is required — with the single exception in §6.

---

## 5. Inline formatting

| Question | Answer |
|---|---|
| Where does bold/italic originate? | `TextBlock.spans[].font_flags` — bit 16 bold, bit 2 italic, bit 1 superscript (excluded); `TextBlock.is_bold` is the no-span fallback. Italic has no line-level fallback. |
| Where is it decided? | `markdown_builder._all_blocks_bold` / `_all_blocks_italic` / `_apply_inline_format` — **at render time**, 016G. |
| What does DOCX do? | Re-parses the `***`/`**`/`*` markers it was just handed (`_parse_inline_format`). |
| Granularity | **Whole paragraph only.** 016G emits a wrapper only when *every* non-superscript span agrees. No sub-paragraph formatting exists in Markdown today. |
| Does `Paragraph` carry it? | **No.** `Paragraph` has `text`, `bbox`, `source_block_ids`, `document_order`, `source_line`, `id` — no `is_bold` / `is_italic`. |

**Model gap, stated plainly:** reproducing current DOCX inline formatting without
Markdown needs the paragraph-level bold/italic *decision*, which today exists only as a
computation inside the Markdown projection. It is **not** an information gap — the
evidence (`spans`) is in the model — it is a **layer gap**: the rule sits in a
projection. `docs/KNOWN_LIMITATIONS.md` already records this and already says "P4 needs
it moved anyway".

Two options, both small, neither inventing an abstraction:
- **(i)** move `_all_blocks_bold`/`_all_blocks_italic` into the model layer (beside
  `paragraph_assembly`) and have both projections call it — no new field, no migration;
- **(ii)** populate `Paragraph.is_bold`/`is_italic` at Stage 5c; both projections read it.

(i) is the smaller diff. (ii) matches how every previous decision was moved (decide once,
store on the model) and is what `KNOWN_LIMITATIONS` anticipates. Recommend **(i) for P4**,
leaving (ii) available if the workspace later needs the field to be editable.

---

## 6. Exact blockers

**B1 — blockless pages are invisible to the stream. The only hard blocker.**

| evidence | value |
|---|---|
| corpus pages with no `TextBlock` | 41 of 161 (25%) |
| documents entirely blockless | 2 of 10 — Bryman (26 pp), O'Leary (13 pp) |
| paragraphs those 2 documents contribute | **0** |
| Markdown they nonetheless produce | 23,004 and 1,261 bytes |

Their body text exists only in `Page.cleaned_text`, rendered by
`_render_page_body_line_by_line`. A DOCX projection reading only the stream would emit
those two documents as page markers and images with **no text at all**. Any P4 that
removes the Markdown path wholesale silently destroys 25% of the corpus.

**B2 — the inline-formatting rule lives in the Markdown projection** (§5). Soft: data exists.

**B3 — note-reference placement inside paragraph text.** `_substitute_markers` resolves
`anchor_text` + `anchor_offset` into a position (with a line-bounded fallback), and lives
in `markdown_builder`. DOCX receives the answer pre-baked as `[^label]`. Same class as B2:
the model data exists (`Footnote.anchor_offset`, bug_005), the rule sits in the wrong
layer. It must be **shared, not duplicated** — a second implementation of a semantic
decision is precisely the defect this architecture removes.

**Not blockers:** tables (models already used), note kinds/parts (L4b), front matter
(already stream-driven), images (alignment/decorative already model-driven), page labels
(`Page.printed_label` on the marker `Heading`), lists (0 on corpus; model is complete).

---

## 7. What can migrate immediately

The stream is 100% covering, so none of these needs new model information:

| Object | DOCX consumes | Retires inventory row |
|---|---|---|
| paragraph | `PARAGRAPH` node → `Paragraph.text` | #1, #16 |
| heading | `HEADING` node → `Heading.level/.text`, minus absorbed | #2 |
| page marker | `PAGE_MARKER` node → marker `Heading` (carries `printed_label`) | #2 (H6 case) |
| page break | `node.page_number` transition | #3 |
| front matter | `FRONT_MATTER` nodes (already read) → drop the positional zone | #4 |
| image | `IMAGE` node → `Image.file_path`, `Figure.alt_text`, existing alignment/decorative maps | #5 |
| caption | `Figure.caption` on the image the node names | #6 |
| table | `TABLE` node → `_add_semantic_table` (unchanged) | #10, #11, #12 |
| list | `LIST` node → `ListBlock.list_type`, `ListItem.text/.level` | #13, #14 |
| note definition | `NOTE_DEFINITION` node → `Footnote.body`, `.label`, `.number`, `NoteType` | #7, #9 |

---

## 8. What must remain until another milestone

| Item | Why | Milestone |
|---|---|---|
| Markdown line path for the 41 blockless pages | no blocks ⇒ no nodes ⇒ no text | a *blockless-page representation* milestone (make OCR text produce `TextBlock`s, or add a page-level content object). **Not P4's job** — but P4 must not delete the path. |
| Mathpix documents | `_render_page_semantic` is a separate ordering (`source_line`); the stream deliberately places nothing for them | its own milestone |
| Sub-paragraph / mixed inline formatting | absent from model *and* Markdown today | future; not a regression |
| Hyperlinks | class E, absent everywhere | future |

---

## 9. Proposed decomposition

| Phase | Scope | Gate |
|---|---|---|
| **P4a** | Move the two shared *rules* out of the Markdown projection — paragraph bold/italic (§5) and note-marker placement (B3) — so both projections call one implementation. **No DOCX change.** | Markdown byte-identical; suite green |
| **P4b** | DOCX renders **paragraphs + headings + page markers + page breaks** from the stream; every other line class still falls through to the existing parser. | Semantic profile parity (§11) on all 10 |
| **P4c** | DOCX renders images, captions, tables, lists, notes, front matter from the stream. Markdown parsing reduced to the blockless-page fallback. | Semantic profile parity + PI-6 + accessibility checks |
| **P4d** *(optional)* | Formal split — `generate_docx(document)` with no `markdown_content`, blockless pages served by a declared limitation. | contract/limitation declared, as `PROJECTION_CONTRACT` does |

`markdown_content` cannot leave the signature before the blockless-page milestone; P4b
and P4c keep it and simply consult it less.

---

## 10. Corpus measurements

| Metric | Value |
|---|---|
| documents / pages | 10 / 161 |
| stream nodes | 1,526 |
| paragraphs = nodes = rendered (P3b) | 745 / 745 / 745 |
| semantic objects unrepresented | **0** |
| duplicate nodes | **0** |
| BODY_LINE remaining | 385 (273 table-owned, 79 heading anchors, 33 note/caption/front-matter) |
| blockless pages | 41 (25%), 2 documents entirely |
| tables / notes / front-matter items / images | 5 / 7 / 19 / 122 |
| lists on corpus | 0 — the list path is **untested by the corpus**; P4c needs fixtures |
| PI-1…PI-6 | ok=True |
| PI-8 / PI-9 | 0 violations |

---

## 11. Existing parity gates — what they can and cannot prove

| Harness | Location | Proves | Cannot prove |
|---|---|---|---|
| `profile_from_docx` | `src/benchmark/profile.py:116` | headings (level+text), paragraph count, tables (rows×cols), footnotes/endnotes **from the XML parts**, page-break count, figure alt text (`docPr@descr`), core metadata, running-header candidates | run-level formatting (bold/italic), within-page reading order, caption association, list styles, bookmarks |
| `check_docx_notes` (PI-6) | `src/benchmark/projection.py:627` | every note materialized **as the right kind** in the right part | body-text fidelity beyond presence |
| `compute_docx_fidelity` | `src/verification/docx_fidelity.py` | 5 structural counts vs the human benchmark DOCX | anything semantic; it is a count ratio |
| `check_projection` (PI-1…PI-6) | `projection.py:467` | Markdown-side object presence/absence | nothing about DOCX |

**Recommended P4 gate — before/after on the same 10 documents, not byte identity:**

1. `profile_from_docx(before)` == `profile_from_docx(after)` — headings, paragraph count, tables, notes, page breaks, figure alts, metadata. **This is the primary gate and it already exists.**
2. PI-6 `check_docx_notes` unchanged.
3. **New, small:** a run-level bold/italic count comparison — the one semantic thing `profile` misses and §5 puts most at risk.
4. `compute_docx_fidelity` vs benchmark unchanged (guards against silent structural drift).

Categories: (1)+(2) semantic; (1) also structural-OOXML; (3) presentation fidelity;
(4) benchmark-relative; accessibility is covered indirectly by (1) alt text + (2) note
kinds. **No visual/layout comparison exists, and none is proposed.**

---

## 12. Recommended smallest first implementation

**P4a, then P4b's paragraph case only.** Move the bold/italic rule into the model layer
with both projections calling it, prove Markdown byte-identical, then let DOCX render
`PARAGRAPH` nodes. That is the smallest change that removes a real semantic
reconstruction — rows #15 and #16, the two highest-frequency in §2 (745 paragraphs and
every formatted run) — while leaving the other 14 rows on the existing path.

Everything in §7 becomes easy afterwards, and each item can land on its own evidence.

---

## 13. Non-goals

- Byte-identical DOCX.
- Solving blockless-page extraction (B1) — P4 *preserves* that path, it does not fix it.
- Mathpix placement.
- Removing `markdown_content` from `generate_docx`'s signature.
- New semantic objects, new abstractions, or a `Projection` registry (that is P5).
- Sub-paragraph inline formatting or hyperlinks.
- Touching BODY_LINE semantics or the three known duplications.
- Any change to Markdown output.
