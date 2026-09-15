# N-2 — Mathpix note references: projection audit

**Date:** 2026-08-16 · **HEAD:** `bb3f708` (N-1) · **Status:** audit only — no code, no commit, no push.
**Measured on:** the ten Mathpix packages, the ten native runs, and the ten human-remediated DOCX.

**Verdict up front: the default assumption (A, projection-only) does not hold.** The projection cannot
recover the 33 proven references, because N-1 proved them and then dropped them at the `P2Footnote`
boundary. The fields to carry them already exist on `Footnote`; only the transport is missing.

---

## 1. The note model after N-1 — measured, not assumed

| Field | Bruner (36 notes) | brinkman (3) | Meaning |
|---|---|---|---|
| `footnote_id` | `mathpix-1` … `mathpix-36` | `mathpix-1..3` | **identity exists and is unique** |
| `number` | 1..36 | 1..3 | the printed number |
| `body` | the citation text | the definitional note | correct |
| `label` (derived) | `p26-1` … `p26-36`, **36/36 unique** | `p18-1..3` | `p{body_page_number}-{number}` |
| `note_type` | **`footnote` x36** | **`footnote` x3** | **wrong part — see §5** |
| `anchor_page_number` | **1 for all 36** | **1 for all 3** | placeholder |
| `anchor_text` | **`"1"` … `"36"`** — the number as a string | `"1".."3"` | placeholder |
| `anchor_offset` | **None on all 36** | None | **the reference position, absent** |

**The 33 Bruner references are not represented in the model.** Only `number` survives.
`_p2footnote_to_footnote` (`src/mathpix/ingestor.py:405`) fills the anchor fields with documented
placeholders because `P2Footnote` is `(number: int, body: str)` — nothing else. So N-1 proved
"marker N sits at line L, offset O" and discarded L and O at the P2 boundary.

**No new reference abstraction is needed.** `Footnote.anchor_text` + `.anchor_offset` are exactly the
relationship, they are already the native path's representation, and `NoteReference`
(`src/models/note_references.py`) is already the resolved form both projections consume.

---

## 2. Both projections traced

```
NATIVE                                              N-1 MATHPIX
footnote_detector sets anchor_text = the real       _p2footnote_to_footnote sets anchor_text = "12",
source line, anchor_offset = marker position        anchor_offset = None, anchor_page_number = 1
        |                                                   |
        v                                                   v
markdown: _spell_note_references(text, notes)       markdown: _render_page_semantic() appends
  -> resolve_note_references() -> "[^p26-12]"         obj.text verbatim — the helper is NEVER called
        |                                                   |
        v                                                   v
DOCX line loop: _FOOTNOTE_REFERENCE_PATTERN         DOCX line loop sees "[12]" — literal text,
  matches [^label] -> _add_note_reference_run()       no pattern matches, no reference emitted
        |                                                   |
        v                                                   v
w:endnoteReference + word/endnotes.xml              word/footnotes.xml body only, 0 references
```

**The exact point of loss is two-stage:**

1. **Transport** — `P2Footnote` cannot carry the anchor, so `resolve_note_references` has nothing to
   resolve. With `anchor_text="12"` it would fall back to searching for the substring `12` inside a
   paragraph, which is precisely the text matching the safety property forbids.
2. **Renderer** — even with correct anchors, `_render_page_semantic` never calls the spelling helper,
   so a Mathpix paragraph is emitted verbatim.

DOCX itself needs **nothing**: `_add_note_reference_run(paragraph, key, registries)` is fully
identity-keyed and already picks the part from `NoteType` and reuses one `w:id` per key.

---

## 3. ContentStream after `bb3f708`

| Measure | Bruner | brinkman |
|---|---|---|
| `Footnote` objects | 36 | 3 |
| `NOTE_DEFINITION` nodes | **36** | **3** |
| resolvable / duplicates | **36 / 0** | **3 / 0** |
| node pages | **all 36 on page 1** | all 3 on page 1 |
| `NOTE_REFERENCE` node kind | **does not exist in `ContentKind`** | — |
| `note_type` distribution | footnote x36 | footnote x3 |

Bodies are already in the stream, resolvable by identity, with no duplicates — P4c-2 is working. Two
observations: every definition collapses onto **page 1** because `anchor_page_number` is the
placeholder `1` (a footnote is emitted at its anchor page); and **there is no reference node kind at
all**, which is correct and should stay that way — see §9.

---

## 4. Markdown contract

**`[^label]` is the right representation** — it already exists, the DOCX line loop already consumes
it, and it is what the native path emits.

**Label derivation needs no text matching and no reconstruction:** `Footnote.label` is a model
property, `p{body_page_number}-{number}`, measured unique 36/36 on Bruner and 3/3 on brinkman. It is
deliberately not `footnote_id` (P2: identity must survive a reviewer's renumbering; the label must
not).

What is missing is only the **position** at which to spell it, which is `anchor_text` +
`anchor_offset` — the same evidence the native path uses.

---

## 5. DOCX contract

`_NoteRegistries` after P4c-2 is already sufficient:

| Concern | Existing behaviour | Verdict |
|---|---|---|
| reference emission | `_add_note_reference_run(paragraph, key, registries)` | reuse as-is |
| part selection | `part_for(key)` from `NoteType` (L4b) | reuse as-is |
| repeated references | `get_or_assign_id(key)` — same key, same `w:id` | already correct |
| body registration | `_add_note_definition(registries, key, body)` from `close_page()` | reuse as-is |
| identity lookup | `key_for(note)` = `footnote_id`; `key_for_label` for rendered brackets | reuse as-is |
| unreferenced body | registered, never referenced — no synthetic reference is possible | already correct |
| reviewer renumbering | identity is `footnote_id`, not the label (P4c-2) | already correct |

**The one thing that is wrong is the part.** `_p2footnote_to_footnote` hardcodes
`NoteType.FOOTNOTE`, so Bruner's 36 land in `word/footnotes.xml`. Measured against both references:

* the **human target contains 0 footnote references across all ten documents** — Nature 4, Aims 11,
  Bruner **36**, brinkman 3, all `w:endnoteReference`;
* the **native path already emits endnotes** — Nature 4 and brinkman 3 in `word/endnotes.xml`, no
  footnotes part anywhere.

So brinkman currently produces endnotes natively and footnotes via Mathpix — the same document, two
different parts. L4b's own docstring cites this exact measurement as the reason the part matters.
This is pre-existing in the ingestor, not introduced by N-1; N-1 only made it visible.

---

## 6. Safety property — how it is preserved

The projection never decides what a note is. It renders **only** what N-1 proved:

* a reference is spelled only where a preserved `anchor_offset` says a marker was found;
* a body with no preserved anchor is registered and never referenced — bodies **15, 26 and 34**
  (confirmed) stay bodies;
* no body text is matched, no number is searched for in prose, no missing marker is inferred;
* Aims keeps 21 literal `[N]` markers and 0 notes, because N-1 proved no apparatus there.

---

## 7. Bruner end-to-end gate

| Expected | Value |
|---|---|
| note bodies | **36** |
| actual references | **33** |
| bodies without references | **3 — numbered 15, 26, 34** (confirmed) |
| fabricated references | **0** |
| remaining list paragraphs | **15** (`1-4` conceptual + `1-11` citations) |
| duplicate bodies | 0 |
| missing proven references | 0 |

**Word id mapping for the three orphans:** `get_or_assign_id(key)` assigns ids in registration order,
so all 36 bodies receive an id and 15/26/34 simply have no reference pointing at theirs. That is legal
OOXML. Practical consequence to state plainly: **Word renders a note where its reference sits, so an
orphan entry is not displayed** — today that applies to all 36, after N-2 to 3.

---

## 8. Native regression baseline

Only two native documents have notes at all:

| Document | references | bodies | parts |
|---|---|---|---|
| Nature of Enquiry | 4 `endnoteReference` | 4 | `word/endnotes.xml` |
| brinkman | 3 `endnoteReference` | 3 | `word/endnotes.xml` |
| the other 8 | 0 | 0 | **no note part** |
| **total** | **7** | **7** | endnotes only |

N-2 must leave all of this byte-identical: it changes the Mathpix ingest path and the Mathpix
renderer only.

---

## 9. P4c-2 interaction

**Do not rewrite it, and do not extend the stream.** Reused unchanged: `_NoteRegistries`,
`key_for`/`key_for_label`, `part_for`, `registry_for`, `get_or_assign_id`, `_add_note_definition`,
`_add_note_reference_run`, `close_page()`'s body registration, and `NOTE_DEFINITION` placement.

**A `NOTE_REFERENCE` node kind is not needed and should not be added.** A reference is a position
*inside* a paragraph's text, not a sibling of it; the stream orders blocks. The native path already
resolves references from the model at render time via `resolve_note_references`, and that is the
architecture N-2 should join, not diverge from.

---

## 10. Scope recommendation

**B — a minimal transport extension plus one renderer call. Not A, not C.**

* **Not A (projection-only):** disproved by measurement. `anchor_text` is `"12"` and `anchor_offset`
  is `None` on 39 of 39 notes; no projection can resolve a position from that without text matching.
* **Not C (parser rewrite):** N-1's *rule* is correct and its output is correct. What it lacks is
  persistence of two values it already computed. That is an additive change, not a redesign.
* **B, scoped tightly:** two optional fields on the `P2Footnote` dataclass, the ingestor mapping them
  onto the `Footnote` fields that already exist, and `_render_page_semantic` calling the spelling
  helper the native path already uses. **No `Footnote` change, no `ContentStream` change, no DOCX
  change, no correction-rail change.**

---

## 11. Acceptance gates

| Scope | Gate |
|---|---|
| **Bruner** | 36 bodies · **33** references · 3 unreferenced (15, 26, 34) · 0 fabricated · 15 list paragraphs |
| **DOCX Bruner** | **33** `w:endnoteReference` · each pointing at the body with the same number · one part · no duplicate body definitions |
| **brinkman (Mathpix)** | 3 references, 3 bodies |
| **Aims** | 0 references, 0 bodies, 21 literal markers untouched |
| **Nature (Mathpix)** | 0 references, 0 bodies |
| **Native** | Nature 4/4 and brinkman 3/3 `endnoteReference` + `word/endnotes.xml`; 8 documents with no note part — **all unchanged** |
| **Markdown** | changes only where a proven marker becomes `[^label]`; Aims/Nature/Bryman/sockett/O'Leary byte-identical |
| **Everything else** | headings, lists, images, tables, metadata, page placement unchanged on both paths |
| **Invariants** | PI-12 green, including pairing; `NOTE_001/002` fire for the new notes |

---

## 12. Commit decomposition

| # | Scope | Output change | Gate |
|---|---|---|---|
| 1 | `mmd_parser.py` + `phase2_document.py`: `P2Footnote` gains the anchor the parser already proved (line text + offset); parser fills it | **none** — nothing consumes it yet | parser tests; corpus note counts unchanged at 39 |
| 2 | `ingestor.py`: map anchors onto `anchor_text`/`anchor_offset`/`anchor_page_number`; set `NoteType.ENDNOTE` | bodies move `footnotes.xml` -> `endnotes.xml`; definitions move to the document end | Bruner 36 endnote bodies, no footnotes part; native unchanged |
| 3 | `markdown_builder._render_page_semantic`: spell `[^label]` via the existing helper | 33 + 3 references appear in Markdown, and DOCX emits them automatically | the full §11 gate |

Commits 1 and 2 may reasonably merge; 3 must stay separate, because it is the one that changes
rendered references and therefore the one whose gate is the product claim.

**Open question for the reviewer, not decided here:** commit 2 changes the note *part* for Mathpix
documents from footnotes to endnotes. It matches the human target (54/54 endnotes), the native path,
and L4b's stated rationale — but it is a deliberate behaviour change and should be approved, not
assumed.
