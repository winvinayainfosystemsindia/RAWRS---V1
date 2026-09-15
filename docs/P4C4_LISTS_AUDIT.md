# P4c-4 — lists: migration audit

**Date:** 2026-08-15 · **Status:** audit only, nothing implemented, nothing committed
**Base:** `aa6fded` (P4c-3) · **Corpus:** 10 benchmark PDFs, both paths — native (`enable_ocr=False`) and Mathpix (`mmd_path=` + `image_dir=`), against `samples/benchmark/remediated_docx`.
Probes: `p4c4_mmd.py`, `p4c4_pipeline.py` (scratchpad, read-only).

**Headline:** the premise that RAWRS produces no lists is false for the path scanned documents actually use. On the Mathpix path RAWRS emits **204** list paragraphs where the human target has **161**, with **exact text-and-order parity on Nature of Enquiry (45/45)**. The defects are over-production and lost identity, not absence.

---

## 1. Counts — measured, all four stages

| Document | MMD item lines | model items (lists) | markdown list lines | **DOCX numbered ¶** | **human ¶** |
|---|---|---|---|---|---|
| 1. Nature of Enquiry | 45 | 45 (6) | 45 | **45** | **45** |
| 1. Aims of Education | 0 | 0 | 0 | 0 | 0 |
| 2. Bryman | 49 | 49 (15) | 49 | **49** | **49** |
| 2. Bruner | 51 | 51 (7) | 51 | **51** | **4** |
| 3. sockett | 4 | 4 (2) | 4 | 4 | 3 |
| 4. O'Leary | 50 | 50 (17) | 50 | **52** | **51** |
| 4. Teaching as a profession | 0 | 0 | 0 | 0 | 0 |
| 5. Calderhead | 0 | 0 | 0 | 0 | 0 |
| 6. Fullan & Hargreaves | 0 | 0 | 0 | **0** | **9** |
| 7. brinkman | 6 | 3 (1) | 3 | 3 | 0 |
| **Total** | **205** | **202 (48)** | **202** | **204** | **161** |

**Native path, same ten documents: 11 list paragraphs, all false positives** (Bruner 6, sockett 2, brinkman 3) — measured on the P4c-3 run's DOCX. Human total on those three: 4, 3, 0.

**Text fidelity vs human**, normalised: Nature of Enquiry **45/45 identical text in identical order**; Bryman 39/39 of the human's top-level items present; O'Leary 47 of 52 texts present, 33 in position.

**Bryman's human 49 = 39 top-level + 10 inside table cells.** The earlier 49-vs-39 disagreement is a counting artefact: `body.findall(w:p)` misses paragraphs in table cells. A list inside a table cell is unrepresentable in RAWRS today (`TableCell` holds text, not a `ListBlock`) — a new, previously unnamed gap.

---

## 2. What is actually lost or reconstructed

| Property | Where it lives | Survives to DOCX? | Evidence |
|---|---|---|---|
| item text | `ListItem.text` | **yes**, verbatim | 45/45 identical on Nature of Enquiry |
| item order | order within `ListBlock` | **yes** | same |
| list type | `ListBlock.list_type` → `-`/`1.` → regex | **yes** | bullet/decimal counts match the model on 6/6 |
| placement vs prose/headings | `source_line`, `_render_page_semantic` | **yes** (markdown line order) | 17 O'Leary lists render inline |
| **list identity** | `ListBlock.id` | **NO — `id` is `None`** | `<!-- list-id: None -->` ×48 |
| **list boundaries** | the anchor comment | **NO** — comment discarded, blank lines stripped | Bryman 15 lists → **14** rendered runs |
| **numbering restart** | not modelled | **NO** — one `numId` per style, document-wide | 4 docs have ≥2 numbered lists; Bruner's 7 number 1–51 continuously |
| **printed item number** | `P2Block.list_number` parsed, then dropped | **NO** — `ListItem` has no number field | `_render_lists` writes `1.` for every item |
| nesting level | `ListItem.level` | moot — always 0 | §4 |
| page assignment | `estimate_page(first item's source_line)` | approximate | a whole list takes its first item's estimated page |

---

## 3. Is the DOCX output genuine OOXML? — **Yes.**

| Check | Result |
|---|---|
| `word/numbering.xml` present | **yes**, in python-docx's default template (9 `num`, 9 `abstractNum`) |
| `ListBullet` style | `w:pPr/w:numPr/w:numId val="1"` → abstractNum 8 → ilvl 0 `numFmt=bullet` |
| `ListNumber` style | `numId val="5"` → abstractNum 7 → ilvl 0 `numFmt=decimal`, `lvlText="%1."` |
| paragraph-level `numPr` | none — **204/204 RAWRS list paragraphs inherit numbering from the style** |
| human target | **161/161 carry paragraph-level `numPr`**, 0 via style |
| `ilvl` | RAWRS 100% ilvl 0; human 100% ilvl 0 |

Style-level `numPr` is real numbering, not appearance: Word and screen readers resolve it identically to the paragraph-level form. **This is not broken.** Two consequences of the *shared* `numId` are real: every `List Number` paragraph in a document belongs to one numbering instance, so separate numbered lists never restart; and `numId 1`/`5` define **only ilvl 0**, so multi-level output is not expressible without adding levels.

---

## 4. Nesting — re-measured, and it is not there

| Measurement | Result |
|---|---|
| indented list markers across all 10 MMD sources | **0 of 205** |
| indented list lines in generated markdown | **0 of 202** |
| `ListItem.level != 0` in the model | **0 of 202** |
| `w:ilvl != 0` in the human target | **0 of 161** |
| levels defined by the template's list `abstractNum` | **1 (ilvl 0 only)** |

Three independent flatteners exist — `mmd_parser` matches against `line.strip()`, `ListItem(text=text, level=0)` is hard-coded at ingestion, and `docx_generator` strips every line again — but **nothing is being flattened**, because no source in the corpus carries a nested list. **Do not build multi-level numbering.**

---

## 5. O'Leary — the discrepancy, fully explained

Two unrelated things, and neither is "+1".

| Layer | Count | Cause |
|---|---|---|
| MMD → model | 50 | Mathpix marked 50 lines as list items |
| model → DOCX | **52** | `_BULLET_LIST_PATTERN` includes `✓`; two *paragraphs* beginning `✓ Is the question doable?` and `✓ Does the question get the tick of approval…` are promoted to `List Bullet` and the glyph deleted |
| human | 51 | the human made a list item of one such line — a partition difference, not a RAWRS defect |

The model **under**-detects by ~1 against the human (Mathpix wrote those lines as `✓`-prefixed paragraphs, not `-` items) and the projection **over**-produces by 2. The two errors partly cancel — which is exactly why a count-only gate would have called this correct.

---

## 6. The one defect class worth fixing: the projection invents lists

| Path | Count | What happens |
|---|---|---|
| native (`_add_stream_paragraph`) | **11** | `Paragraph.text` is re-matched against the list regexes. `12. A. C. Kruger and M. Tomasello, "Cultural Learning…"` → `List Number`, **the printed `12.` is deleted** and replaced by Word's own counter, continuous with an unrelated list. Bruner 6, sockett 2, brinkman 3; those documents' human targets have 4, 3 and 0. |
| Mathpix (line loop) | **2** | The `✓` case above. |

Both are one rule: **a line that looks like a list item is made one, whether or not any object says so.** No `ListBlock` stands behind these 13 paragraphs, so nothing can review, revert or verify them, and the number they destroyed is not recoverable from the model.

Adjacent, and *not* a projection defect: Bruner's 51 model items are 4 real conceptual points plus ~47 **reference/endnote entries** the MMD itself wrote as `1. Author…` (Bruner has 36 human note references). Reclassifying those is an ingestion heuristic, not a projection change.

---

## 7. Can `LIST` nodes be introduced now? — **No, and for a new reason.**

| Question | Answer |
|---|---|
| Do `LIST` nodes exist today? | **No — zero, on every document, both paths.** `ListBlock.id` is `None` and `build_content_stream`'s `emit()` returns early on a falsy id. `ContentKind.LIST` is dead code. |
| Does the Mathpix path have `PARAGRAPH` nodes? | **No — 0 on all 10.** Mathpix paragraphs record `source_line` and no `source_block_ids`, so `_paragraph_anchor()` returns None (unchanged since P3a). |
| What *is* in a Mathpix stream? | Bryman: 90 nodes = 53 heading + 26 page_marker + 10 image + 1 table. Nature of Enquiry: 2,938 nodes of which **2,931 are BODY_LINEs from the PDF's own blocks** — a different document from the one being rendered. |
| Did tables/notes/images need paragraph nodes to migrate? | No — they key on their own id and on `close_page()`. "Mathpix has no paragraph nodes" is **not** the blocker the W-3 audit named. |
| So is node-driven list emission safe? | **No.** Measured consequence of doing exactly that for tables: Bryman's Mathpix table sits at markdown line **462 of 676** but renders at DOCX body index **291 of 292** — P4c-1 moved it to its page's end. Mathpix lists are interleaved with prose by `source_line`; page-close emission would move **all 48** of them to page ends. |

**Item 8's answer: still true, different reason.** The blocker is not missing paragraph nodes — it is that the stream carries no ordering coordinate Mathpix prose shares, so any node-driven emission on that path relocates content. P4c-1 already demonstrated the failure mode on one table.

---

## 8. Markdown list path — classification

| Site | Class | Fate |
|---|---|---|
| `_render_lists` marker + text | legitimate syntax generation | keep |
| `_render_lists` `'  ' * item.level` indent | legitimate, currently always 0 | keep |
| `<!-- list-id: {lst.id} -->` | identity anchor, **emits `None`**, discarded by DOCX | fix the id; make DOCX consume it |
| `_LIST_ID_COMMENT_PATTERN` → `continue` | unnecessary parsing (no-op today) | becomes the list-scope signal |
| `_BULLET_LIST_PATTERN` / `_NUMBERED_LIST_PATTERN` in the line loop | semantic reconstruction — **the only way Mathpix's 202 items reach DOCX** | keep, scope to anchored lists |
| the same two patterns in `_add_stream_paragraph` | semantic **invention** on the native path | delete |
| `_render_page_semantic` list branch | still needed — Mathpix is outside the stream | keep |

---

## 9. Verdict

**C — a list-correctness fix, with the identity backfill that makes it possible. Not A, not B.**

* **A (direct DOCX `LIST`-node projection): rejected on evidence.** No `LIST` nodes exist, and creating and consuming them would relocate 48 Mathpix lists to page ends (§7).
* **B (Mathpix ContentStream integration): correct eventually, not now.** It is the largest projection gap in the product audit and is not a smallest-useful-slice.
* **D (defer entirely): rejected.** 13 paragraphs are actively wrong output today, including deleted citation numbers.
* **E:** the slice in §11.

---

## 10. Ranked against the other product gaps

Impact = wrong or missing output a remediator must fix by hand, measured on this corpus.

| # | Gap | Measured | Verdict |
|---|---|---|---|
| 1 | **Heading hierarchy — no H1 on 6/10 while emitting H2/H3** | 115 human headings vs 75 | unchanged, still first |
| 2 | **Notes undetected without a superscript glyph** (bug_005) | 47 notes on 2 docs | unchanged, second |
| 3 | **The projection invents lists** (this audit) | 13 ¶, 4 docs, citation numbers destroyed | **new; small, cheap, a deletion** |
| 4 | Reference lists ingested as numbered lists | 47 items on Bruner | ingestion heuristic; risky |
| 5 | Cross-page sentence stitching | checklist-mandated, unbuilt | promote (unchanged) |
| 6 | Printed page labels | 107/161 pages | unchanged |
| 7 | Numbered lists never restart | 4 docs with ≥2 numbered lists | follow-up, not now |
| 8 | List boundaries merge | 1 of 15 (Bryman) | follow-up |
| 9 | Lists inside table cells | 10 (Bryman human) | model gap; name only |
| 10 | **List nesting** | **0 evidence anywhere** | **do not build** |

Lists as a *class* are **not** the largest remediation gap — that framing came from a native-path-only measurement. The list-shaped-prose defect earns its place because it is small, deletes code, and stops RAWRS destroying content it cannot recover.

---

## 11. Proposed milestone — P4c-4′ "a paragraph is a list item only when an object says so"

**Exact problem.** 13 paragraphs across 4 documents are given Word list semantics by line shape alone, with no `ListBlock` behind them; the leading `12. ` / `✓ ` is deleted and replaced by Word's counter. Separately `ListBlock.id` is `None`, so list identity does not exist anywhere in the system.

**Proposed change.**
1. `ListBlock` backfills `id` in a `model_validator`, exactly as `Image` and `Paragraph` do. `<!-- list-id: … -->` stops emitting `None`; `LIST` nodes begin to exist (emitted, consumed by nothing).
2. `_add_stream_paragraph` stops re-matching `Paragraph.text` against the list regexes. A native-path paragraph is a paragraph.
3. The line loop's list branch applies only inside an anchored list block — from a `<!-- list-id: … -->` comment until the first non-list line. Markdown with no traversal keeps the FEATURE_016C line-shape behaviour untouched.

**Non-goals.** Native PDF list detection (measured unfit: 68 lists / 80 items, 45 false positives on one document). Numbering start/restart. `ListItem` identity. Multi-level `ilvl`. Reclassifying Bruner's reference entries. Mathpix ContentStream migration. Lists in table cells. Consuming `LIST` nodes in either projection (§7 forbids it today).

**Acceptance gates.**

| Gate | Target |
|---|---|
| Native DOCX list paragraphs | **11 → 0**, across all 10 |
| Mathpix DOCX list paragraphs | **204 → 202** — exactly the model's item count on every document |
| Nature of Enquiry vs human | 45/45 identical text and order, **unchanged** |
| `<!-- list-id: None -->` | **48 → 0** |
| `LIST` nodes | 0 → 48, consumed by nothing |
| Markdown hashes (native, uuid-masked) | unchanged on all 10 |
| Mathpix table/image/note placement | unchanged — no new page-close emission |
| FEATURE_016C list tests | unchanged and green |

**Commit decomposition.** Two.
1. `ListBlock.id` backfill → the anchor comment carries a real id and `LIST` nodes exist (no consumer). Small, isolated, independently testable.
2. The projection stops inventing list items: `_add_stream_paragraph` regexes deleted, line-loop branch scoped to anchored blocks, native 11 → 0 gate.

**Open question for the reviewer, not decided here.** Gate 2 turns brinkman's 3 native `List Number` paragraphs back into body paragraphs. The human target for brinkman has 0 list paragraphs, so this is a correction — but those three lines (`Inequality vs. equality`, …) do read as a genuine list in the source that neither path detects. After this milestone they are plain paragraphs with their printed markers intact, which is honest and reviewable; making them a real list needs native detection, which is out of scope.
