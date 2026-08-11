# P4c-2 — DOCX notes: migration audit

**Date:** 2026-08-11 · **Status:** audit only, nothing implemented, nothing committed
**Base:** `258d25f` (P4c-1) · **Corpus:** 10 native benchmark PDFs, `enable_ocr=False`.

---

## 1. The current path, and what each site does

```
Footnote ──build_markdown──> "[^p3-1]" in prose + "[^p3-1]: body" definition
         └─NOTE_DEFINITION node (already correct, already unread by DOCX)
                                        ↓
                        docx_generator parses the markdown back
                                        ↓
                    _NoteRegistries → word/footnotes.xml | word/endnotes.xml
```

| # | Site | Recovers | Class | Fate |
|---|---|---|---|---|
| 1 | `_FOOTNOTE_DEFINITION_PATTERN` → `_add_note_definition` | note **label + body text** | **A** semantic recovery | retire |
| 2 | `_NoteRegistries._endnote_labels` (label → part) | note **type** | **A** — keyed on a *label*, see §4 | retire |
| 3 | `_FootnoteRegistry.get_or_assign_id(label)` | OOXML `w:id` | **C** genuine mechanics (per-part id space) | keep, rekey |
| 4 | `_FOOTNOTE_REFERENCE_PATTERN` in `_add_text_with_note_references` | reference **position** in list items and blockless prose | **A** on those two paths | keep — fallback only |
| 5 | `_add_runs_with_note_references` (P4a/P4b) | reference position in **prose paragraphs** | already model-driven | already done |
| 6 | `## Endnotes` heading line | that an endnote section exists | **B** markdown syntax | keep — markdown's own generated heading |
| 7 | endnote page break | that endnotes start a new page | already model-driven (`has_endnotes`) | already done |
| 8 | `_build_notes_xml` / `_attach_notes_part` / `_NotePartSpec` | OOXML vocabulary per part | **C** | untouched |
| 9 | `_display_number` / `_LABEL_DISPLAY_NUMBER_PATTERN` | nothing — **no call site** | dead | delete |

**Only sites 1 and 2 are semantic recovery on the main path.** Site 3 is real OOXML plumbing and must survive. Site 4 is real but reachable only from paths P4c-2 does not own.

---

## 2. Stream verification — measured

| | value |
|---|---|
| Footnote objects | **7** |
| `NoteType.ENDNOTE` / `NoteType.FOOTNOTE` | **7 / 0** |
| `NOTE_DEFINITION` nodes | **7** |
| nodes resolving to a Footnote by `footnote_id` | **7** |
| duplicate nodes | **0** |
| notes with no node | **0** |
| notes carrying `footnote_id` / `anchor_offset` | **7 / 7** |
| documents where node order equals `Footnote.number` order | **2 of 2** |
| references the model can locate **without markdown** | **7 of 7** |

**No representation gap.** Every note is in the stream exactly once, in number order, and `resolve_note_references` locates every one of the 7 references inside the paragraphs the projection already renders.

Package side, same run: `word/endnotes.xml` holds 7 bodies and the body holds 7 `w:endnoteReference`; `word/footnotes.xml` holds 0 and there are 0 `w:footnoteReference`. **0 references without a body, 0 bodies without a reference.** L4b is intact.

---

## 3. References — already migrated, with a bounded remainder

P4a moved reference resolution to `note_references.resolve_note_references()`, and P4b made prose paragraphs consume it. DOCX does **not** regex prose for `[^label]` any more, does not recompute offsets, and does not duplicate the bounded-search fallback.

`_FOOTNOTE_REFERENCE_PATTERN` survives on exactly two paths, both rendering text that is *not* a `Paragraph`:

* `_add_list_paragraph` — list item text (0 lists on the corpus)
* `_add_body_text_with_inline_format` — blockless-page prose (41 of 161 pages)

Neither has a `Paragraph` to hand `resolve_note_references` a text plus its contributing blocks, so **the API is not insufficient — the callers have no semantic object to ask about.** That is the blockless/list boundary again, not a note gap. No new capability is required.

---

## 4. Note type — authoritative, with one identity flaw

`Footnote.note_type` is the only thing consulted to choose a part, and the two `_NotePartSpec` records keep the vocabularies separate: own partname, own content type, own relationship, own element names, own reference style, **own `w:id` space** (`_FootnoteRegistry` is instantiated once per part, each starting at 1). Nothing infers type from placement, headings, rendered text or position. ENDNOTE does not collapse into FOOTNOTE.

**But the lookup is keyed on `Footnote.label`, and the model says in as many words that a label is not identity:**

```python
# src/models/footnote.py
return f"p{self.body_page_number}-{self.number}"
# "Deliberately not footnote_id: that is this object's identity …
#  Identity must stay stable when a reviewer renumbers; the label must not."
```

Measured: `label == footnote_id` for **0 of 7** notes. So `_NoteRegistries` resolves type, id and body through a *derived, renumber-sensitive* string. `part_for()` also silently defaults an unrecognised label to FOOTNOTE. This is the defect class P4c-1 just retired for tables, where `<!-- table-id -->` carried real identity through a rendered string — here the string is not even identity to begin with.

---

## 5. Placement — sufficient, no new mapping needed

| evidence | present? |
|---|---|
| `anchor_offset` | 7/7 |
| `anchor_text` (the exact source line) | 7/7 |
| `Paragraph.source_block_ids` → contributing blocks | yes |
| `footnote_id` | 7/7 |
| `number` (printed) | 7/7 |
| `NOTE_DEFINITION` node per note | 7/7 |

`resolve_note_references` already turns these into `(start, length, note)` against assembled paragraph text, and it located 7 of 7. **No `SourceRange` is needed and none should be invented.** Definition placement likewise needs nothing new: the stream puts a footnote's definition on its anchor page and an endnote's after the last page, which is where both projections already put them.

---

## 6. Endnote materialization

`_build_notes_xml` and `_attach_notes_part` are already parameterised by `_NotePartSpec` and read only `(id, body_text)` pairs. Feeding those pairs from `NOTE_DEFINITION` nodes instead of from parsed `[^label]: body` lines changes the *source* of the pair, not the builder. **No second endnote implementation is required or proposed.** The printed number stays Word's auto-number element (`w:endnoteRef`), as L4b intends — `Footnote.number` remains the model's printed number and is not written into the part.

---

## 7. Corpus limitation and the minimum fixture set

The corpus proves: endnote detection, endnote materialization into `word/endnotes.xml`, endnote references, endnote ordering, reference↔body pairing, and that **no footnote is accidentally materialized** (0 bodies, 0 references in the footnote part).

It cannot prove anything about footnotes, because it contains none. Minimum synthetic fixtures — six, no more:

| Fixture | Proves |
|---|---|
| one FOOTNOTE, referenced once | `w:footnoteReference` + `word/footnotes.xml` exist at all |
| one FOOTNOTE + one ENDNOTE in one document | both parts coexist; neither steals the other's note |
| two FOOTNOTEs + two ENDNOTEs | **the two id spaces are independent** (both parts start at 1) |
| two notes sharing a printed `number` on different pages | identity, not label, decides which body is which |
| a note whose `number` changes after markdown is built | renumbering does not re-target the note (the §4 defect) |
| a note with no reference locatable in prose | the body still materializes; nothing is invented |

Fixtures only — no corpus claim will be made for footnote materialization.

---

## 8. Existing checks, and where they are weak

| Claim | Proven by | Strength |
|---|---|---|
| endnote bodies land in `endnotes.xml` | PI-6 `check_docx_notes` | strong |
| no ENDNOTE in the footnote part, no FOOTNOTE in the endnote part | PI-6 | strong |
| a note body survives at all | PI-6 (normalized body text) | strong |
| note **count** | PI-6 indirectly; `profile_from_docx` lists bodies | adequate |
| **reference → body pairing** | nothing | **absent** |
| **reference count** | nothing | **absent** |
| **note identity preservation** | nothing — PI-6 matches on body text | **weak by construction** |
| **printed numbering** | nothing | absent (Word auto-numbers; arguably not ours to prove) |
| **reference placement in prose** | PI-9 for Markdown only; nothing for DOCX | **absent** |
| endnote part existence | PI-6 | strong |

PI-6 matches by normalized body text because a `.docx` keeps no object ids — a real limit, documented in the checker. The gap worth closing is **pairing**: today nothing would catch a reference pointing at the wrong body, which is exactly what a label-keyed registry can get wrong.

---

## 9. Proposed parity profile (before/after, not byte identity)

Per document: note count; per note `footnote_id` → `note_type` → part; body text per part in id order; `w:footnoteReference` / `w:endnoteReference` id lists in document order; reference-id → part-body pairing; references per part; the position of each reference relative to the paragraph carrying it; and the `## Endnotes` heading plus its preceding page break. Corpus baseline to beat: 7 endnote bodies, 7 endnote references, 0 footnote bodies, 0 footnote references, 0 orphans either way.

---

## 10. Recommended scope — one commit

The architecture is already sufficient; nothing here proves an independent semantic gap that would justify splitting.

| Category | Content |
|---|---|
| **migrates immediately** | note **definitions** from `NOTE_DEFINITION` nodes (site 1); note **type** from `Footnote.note_type` per node (site 2); registry rekeyed from `label` to `footnote_id` (site 3); `_display_number` deleted (site 9) |
| **needs a model change** | **none** |
| **needs a semantic helper** | **none** — `resolve_note_references` already exists and already serves prose |
| **needs synthetic fixtures** | footnote materialization, mixed documents, independent id spaces (six fixtures, §7) |
| **remains Markdown fallback only** | `_FOOTNOTE_REFERENCE_PATTERN` for list items and blockless prose (site 4); `_FOOTNOTE_DEFINITION_PATTERN` for a Document whose notes the traversal cannot place; the `## Endnotes` heading line (site 6) |

**Proposed invariant, PI-12:** every `Footnote` has exactly one `NOTE_DEFINITION` node; every node resolves by `footnote_id`; every note materializes exactly once, in the part its `note_type` names; every reference id in the body resolves to a body in the same part; and no note is materialized that the model does not hold.

---

## 11. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Rekeying the registry changes `w:id` assignment order, so ids shift even when nothing else does | low — ids are per-part plumbing, and PI-6 matches on body text | compare *pairing*, not id values, in the parity profile |
| Definitions arriving from the stream rather than from markdown lines changes body **order** within a part | low — node order matched `number` order 2 of 2 | assert order explicitly in the profile |
| Footnote path is corpus-unproven | **medium** — it is the whole point of the fixtures | six fixtures, and no corpus claim |
| The `## Endnotes` heading stays Markdown-driven, so P4c-2 does not fully retire note parsing | accepted | classified fallback-only, not claimed as eliminated |

**Recommendation: proceed with a single P4c-2 commit** covering sites 1, 2, 3 and 9, adding PI-12 and the six fixtures, and leaving site 4 and the `## Endnotes` heading explicitly as fallback. The one thing I would not defer is the rekey: leaving DOCX to resolve notes through a renumber-sensitive label is the defect this milestone exists to remove, and it is cheaper to fix while the definition path is already being rewritten.
