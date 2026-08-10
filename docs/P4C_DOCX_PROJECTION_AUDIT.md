# P4c — images, captions, tables, lists, notes: migration audit

**Date:** 2026-08-10 · **Status:** audit only, nothing implemented, nothing committed
**Base:** `81a8a36` (P4b) · **Corpus:** 10 native benchmark PDFs, `enable_ocr=False`, no Mathpix.

---

## 1. Object-by-object migration matrix

| | IMAGE | CAPTION (figure) | TABLE | LIST | NOTE |
|---|---|---|---|---|---|
| semantic owner | `Image` | `Figure.caption` on the `Image` | `Table` | `ListBlock` | `Footnote` |
| identity | `Image.image_id` | **none of its own** | `Table.table_id` | `ListBlock.id`; **items have none** | `Footnote.footnote_id` |
| stream node | `IMAGE` | — (none) | `TABLE` | `LIST` | `NOTE_DEFINITION` |
| placement info | `source_block_id` + `document_order` | inherited from its image | `source_block_ids`; node emitted after the body | `document_order` only | `anchor_page_number`; endnotes after last page |
| current DOCX parser | `_IMAGE_PATTERN` | `_CAPTION_PATTERN` + `pending_caption_after_image` | `_TABLE_ID_COMMENT` + pipe rows | `_BULLET_/_NUMBERED_LIST_PATTERN` | `_FOOTNOTE_DEFINITION_PATTERN` |
| recovered from Markdown | path, alt text | caption text **and its association** | which model, and the trigger to flush | item text, marker kind | label, body text |
| already on the model | path, alt, decorative, alignment, w/h, `embedded_in_docx` | `Figure.caption`, `.caption_source_text` | everything `_add_semantic_table` renders | `list_type`, `items[].text`, `items[].level` | `note_type`, `label`, `number`, `body` |
| still missing | nothing | caption **identity + placement** | nothing | numbering start; item identity; block anchor | nothing |
| projection-only OOXML | `docPr@descr`, max-width scaling, alignment enum | centred italic run | `tblHeader`, merges, Table Grid style | `List Bullet`/`List Number` styles | `w:footnoteReference` vs `w:endnoteReference`, parts |

**They do not belong in one implementation.** Tables and notes are already model-driven and need only a trigger swap. Images need a placement swap. Captions have no identity. Lists have a real model gap *and* zero corpus coverage.

---

## 2. ContentStream coverage — measured

| kind | objects | nodes | resolving | duplicates | unplaceable | without a node |
|---|---|---|---|---|---|---|
| image | 122 | 122 | 122 | 0 | 0 | **0** |
| table | 5 | 5 | 5 | 0 | 0 | **0** |
| note | 7 | 7 | 7 | 0 | 0 | **0** |
| list | 0 | 0 | — | — | — | — |
| caption | 2 (`Figure.caption`) | **0 — no node kind exists** | — | — | — | **2** |

`BODY_LINE` = 385, of which **277** are table-owned and **2** are figure-caption source lines; **0** are image anchors. Nothing else in these five kinds is represented twice.

**Attribute coverage:** 122/122 images carry bbox and width/height; 122/122 have `figure.alt_text`; **0** are decorative; **2** have a caption. 5/5 tables carry `source_block_ids`; **0** have a caption, **0** a summary, **0** a merged cell; 640 cells, 5 header rows. 7/7 notes carry an id and an `anchor_offset`, and **all 7 are endnotes — the corpus contains zero footnotes.**

---

## 3. Markdown reconstruction inventory after `81a8a36`

| # | Site | Serves | Class |
|---|---|---|---|
| 1 | `_IMAGE_PATTERN` | image path + alt | **A** |
| 2 | `_CAPTION_PATTERN` + `pending_caption_after_image` | figure caption text + association | **E** (association is Markdown-only) |
| 3 | `_TABLE_ID_COMMENT_PATTERN` | which `Table` | **A** |
| 4 | `_PIPE_TABLE_ROW/SEPARATOR_PATTERN` | flush trigger; fallback grid | **A** (fallback never fires) |
| 5 | `_TABLE_SUMMARY_COMMENT_PATTERN` | skip only | **A** |
| 6 | `_LIST_ID_COMMENT_PATTERN` | skip only — no lookup | **A** |
| 7 | `_BULLET_LIST_PATTERN` (on lines) | list item text + kind | **B** (needs fixtures) |
| 8 | `_NUMBERED_LIST_PATTERN` (on lines) | list item text + kind | **B** |
| 9 | `_FOOTNOTE_DEFINITION_PATTERN` | note label + body | **A** |
| 10 | `_FOOTNOTE_REFERENCE_PATTERN` | references inside non-prose runs | **B** (only list/caption text still routes here) |
| 11 | `PAGE_BREAK_MARKER` | page fence for the residual lines | **C** |
| 12 | `_HEADING_PATTERN` | blockless markers, synthesized markers, `## Endnotes` | **C** |
| 13 | `_INLINE_FORMAT_PATTERN` / `_parse_inline_format` | emphasis on blockless + list text | **C** |
| 14 | `_BULLET_/_NUMBERED_LIST_PATTERN` on `Paragraph.text` | list styling of prose | **D** — genuine projection mechanics |
| — | `_display_number` / `_LABEL_DISPLAY_NUMBER_PATTERN` | nothing | **dead code**, no call site |

**A = removable in P4c (6 sites + 1 dead). B = later milestone (3). C = blockless fallback only (3). D = genuine (1). E = model gap (1).**

---

## 4. List semantic audit — the critical one

**The corpus has zero lists. Nothing below is corpus-validated.**

| Question | Answer |
|---|---|
| Can `ListBlock` fully drive DOCX without Markdown? | **Almost.** `list_type`, `items[].text`, `items[].level` cover everything DOCX renders today. |
| Does ContentStream preserve list ordering? | **Between lists, yes** (`LIST` node per block). **Within the page, no** — `ListBlock` has no `source_block_ids`, so the node is emitted at the page end, after all prose. |
| Does the model preserve nesting? | **Yes** — `ListItem.level`. |
| Does DOCX preserve nesting today? | **No.** `_render_lists` encodes level as a leading two-space indent, and `generate_docx` does `line.strip()` before matching. **Nesting is destroyed in the current DOCX output.** Migration would *fix* this, i.e. change output. |
| Ordered vs unordered preserved? | Yes on the model; in Markdown a numbered list renders every item as `1.`, so DOCX recovers "numbered" but not the sequence. |
| Numbering semantics? | **Gap.** No start value, no restart/continue flag. Word auto-numbers. Acceptable only while no source needs a non-1 start. |
| Are list items independently identifiable? | **No.** `ListItem` is a plain `BaseModel` — no id, not a `SemanticObject`. A per-item correction or per-item verification cannot address one. |
| Does DOCX derive any of this from Markdown syntax? | Yes — item text and marker kind, sites 7–8. |

**Two real gaps: `ListBlock.source_block_ids` (placement) and `ListItem` identity.** Neither blocks a first list migration that preserves today's page-end placement, but both must be named rather than implemented around.

---

## 5. Exact model / stream gaps

| # | Gap | Consequence | Smallest honest fix |
|---|---|---|---|
| G1 | **Figure captions have no identity and no stream node.** `Figure.caption` is a string on the image; DOCX associates it by Markdown adjacency. | Caption placement cannot move to the stream without inventing something. | None needed for P4c: render the caption *from the image node*, immediately after it, exactly as `_add_semantic_table` already does for table captions. No `Caption` object. |
| G2 | `ListBlock` has no `source_block_ids`. | LIST nodes sit at page end; a list cannot be placed mid-prose. | Defer. Preserves today's behaviour. |
| G3 | `ListItem` has no identity. | No per-item correction/verification; PI-style checks can only count. | Defer; note it. |
| G4 | No list numbering start/restart. | Cannot express "starts at 7". | Defer until a source needs it. |
| G5 | Corpus has **zero footnotes** (7/7 notes are endnotes). | `word/footnotes.xml` is unexercised by the corpus. | Fixture, not model change. |
| G6 | Corpus has **zero** table captions, summaries and merged cells. | Three `_add_semantic_table` branches unexercised by the corpus. | Fixture, not model change. |

---

## 6. Blockless-page boundary

41 of 161 pages, 2 documents entirely (Bryman 26pp, O'Leary 13pp). Their text exists only in `Page.cleaned_text`.

**The important correction to the P4b framing:** the blockless limit is about *prose*, not about all five kinds.

| kind | on blockless pages |
|---|---|
| image | **118 of 122** — a scanned page *is* an image |
| table | 0 of 5 |
| note | 0 of 7 |
| list | 0 |
| caption | 0 of 2 |

Tables, notes, captions and lists never occur on a blockless page, so those migrations are unaffected by the boundary. **Images are the opposite:** 97% of them are on blockless pages, and the stream already places all 122. So image migration must be keyed on *the image's own node*, not on `is_stream_page()` — otherwise it would move only 4 images and leave 118 on the old path.

P4c can safely leave blockless pages' **prose** on the Markdown fallback while stream pages become fully native.

---

## 7. Parity gates — what can actually be proven

Existing harness: `profile_from_docx` (headings, paragraph count, tables rows×cols, note bodies per part, page breaks, `docPr@descr`, metadata), PI-6 `check_docx_notes`, PI-10 `check_docx_projection`, `compute_docx_fidelity` (5-count ratio vs the human benchmark), plus the P4b before/after semantic profile.

| Object | Provable now | Needs a new probe | Not provable |
|---|---|---|---|
| image | count, alt text, order relative to prose | decorative (`descr=""` vs unset), dimensions (`extent cx/cy`), `embedded_in_docx` | visual placement |
| caption | text presence, style (centred italic) | **association** — that caption *i* follows image *i* | — |
| table | count, rows×cols, cell text | header rows (`w:tblHeader`), merges (`gridSpan`/`vMerge`), caption/summary paragraphs | — |
| list | — (zero on corpus) | numbering XML (`numPr`/`ilvl`), item order, type, **nesting level** | — |
| note | part membership, bodies, type (PI-6) | reference→definition pairing, printed numbering | — |

**Proposed P4c gate:** the P4b before/after semantic profile extended with (a) `docPr@descr` present-vs-empty-vs-absent, (b) `extent` dimensions, (c) `w:tblHeader` / `gridSpan` / `vMerge` counts, (d) `numPr@ilvl` per list paragraph, (e) reference-id → part → body triples. Byte identity is not the gate; these invariants are.

---

## 8. Recommended decomposition

Ordering follows dependency, coverage and provability — **not** the example ordering in the brief.

| Step | Scope | Why here | Corpus evidence | Risk |
|---|---|---|---|---|
| **P4c-1** | **Tables** | `_add_semantic_table` is already fully model-driven; only the *trigger* is Markdown. Deletes sites 3, 4, 5 and `_add_pipe_table` outright. | 5 tables, 640 cells, 277 body-line overlap | lowest |
| **P4c-2** | **Notes** | Bodies/kinds/parts already model-driven (L4b, P4a). Deletes site 9, and site 10 for prose. | 7 notes, all endnotes | low, but **footnote part unexercised** |
| **P4c-3** | **Images + captions together** | Caption association is only recoverable as "the caption of the image node just emitted" — it has no independent identity (G1), so it cannot be a separate step. Deletes sites 1, 2. | 122 images, 2 captions, 118 on blockless pages | medium — touches the blockless path's images |
| **P4c-4** | **Lists** | Blocked on fixtures; migration *changes output* by restoring nesting. | zero | highest |

**Captions are coupled to images** (G1) and, for tables, are already inside `_add_semantic_table`. There is no standalone caption step.

**Recommended first implementation: P4c-1, tables only.** It is the largest reduction in Markdown parsing per unit of risk: three parse sites plus a dead fallback renderer, against a rendering function that already reads the model, with 277 body-line duplications visible as the follow-on prize. It also establishes the "resolve the node, call the existing model-driven renderer" shape that P4c-2 and P4c-3 reuse.

---

## 9. List fixture suite (define now, build at P4c-4)

Only cases the repository actually supports — `ListType` has two values and `ListItem` has `text` + `level`, nothing else.

| Fixture | Proves |
|---|---|
| bullet list, 3 flat items | `ListType.BULLET` → `List Bullet`, item text, order |
| numbered list, 3 flat items | `ListType.NUMBERED` → `List Number`, order |
| bullet list with `level` 0/1/2 | **nesting survives** — the case DOCX loses today |
| numbered list with `level` 0/1 | nesting on ordered lists |
| two lists on one page | `document_order` decides sequence |
| lists on consecutive pages | LIST nodes stay on their page |
| list adjacent to prose and to a table | page-end placement (G2) is preserved, not silently changed |
| list whose item text contains `[^label]` | note references inside items still resolve |
| empty `items` | `_render_lists` skips it; DOCX must too |

Not included, deliberately: numbering start values, restart/continue, mixed-type nesting, per-item ids — the model cannot express any of them (G3, G4), and a fixture asserting them would be asserting a feature that does not exist.

---

## 10. Non-goals

- Byte-identical DOCX.
- Solving blockless extraction, or moving blockless **prose** off the Markdown path.
- Inventing a `Caption` semantic object (G1 is solved by rendering from the image node).
- Adding `ListBlock.source_block_ids`, `ListItem` identity, or list numbering semantics (G2–G4) — named, deferred.
- Removing `markdown_content` from `generate_docx`'s signature — that is P4d.
- Mathpix placement; `ContentStream` redesign; the `Projection` registry (P5).
- Touching the three known BODY_LINE duplications.
