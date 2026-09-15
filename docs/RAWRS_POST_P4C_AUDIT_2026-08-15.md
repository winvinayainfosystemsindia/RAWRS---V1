# RAWRS post-P4c product & architecture audit

**Date:** 2026-08-15 · **HEAD:** `c12d121` (P4c-4′ complete) · **Status:** audit only, no code, no commit.
**Corpus:** the 10 benchmark PDFs, measured on **both** pipelines and against `samples/benchmark/remediated_docx`.
Probes (scratchpad, read-only): `p4c4_gate.py`, `p4c4_mmd.py`, `p4c4_pipeline.py`, `p4c_postaudit.py`, `p4c4_inspect.py`.

**Supersedes** `RAWRS_PRODUCT_AUDIT_2026-08-12.md` on §3, §9 and §11. Three of its conclusions are falsified below.

---

## 1. The measurement everything else rests on

Generated DOCX vs the human target, whole corpus:

| Object | native | Mathpix | human | read |
|---|---|---|---|---|
| headings (incl. H6 page markers) | 236 | **360** | 256 | native under, **Mathpix over** |
| — content headings only | 75 | **199** | 115 | −40 vs +84 |
| list paragraphs | **0** | **202** | 161 | native silent, Mathpix over |
| tables | 5 | 8 | **28** | both far under |
| **images (drawings)** | 122 | **0** | 11 | **Mathpix loses 100%** |
| note references | 7 | **0** | **54** | both far under |
| captions (italic+centred) | 2 | 8 | 0 | target styles them differently |
| page breaks | 153 | 151 | 144 | close |
| core properties set | 20 | 20 | 8 | **RAWRS already exceeds** |

Per-document, the two paths disagree far more than either disagrees with the target:

| Document | headings n/m/h | lists n/m/h | tables n/m/h | images n/m/h | note refs n/m/h |
|---|---|---|---|---|---|
| Nature of Enquiry | 60/58/51 | 0/45/45 | 2/2/2 | 0/0/1 | 4/0/4 |
| Bryman (scanned) | 26/**79**/61 | 0/49/49 | 0/1/**21** | 112/**0**/3 | 0/0/0 |
| Bruner | 27/**58**/26 | 0/**51**/4 | 0/0/0 | 0/0/0 | 0/**0**/**36** |
| O'Leary (scanned) | 13/**47**/26 | 0/50/51 | 0/0/0 | 4/**0**/4 | 0/0/0 |
| Teaching as a profession | **37**/37/10 | 0/0/0 | 0/0/0 | 2/0/1 | 0/0/0 |
| brinkman | 34/36/34 | 0/3/0 | 3/5/5 | 4/**0**/2 | 3/0/3 |

---

## 2. Object-by-object capability matrix

D=detected · M=in model · A=addressable (stable id) · S=in ContentStream · MD=Markdown consumes · DX=DOCX consumes · R=correction rail (verifier **and** route) · V=validation rule · **RR**=actually reviewer-remediable

| Object | D | M | A | S | MD | DX | R | V | **RR** |
|---|---|---|---|---|---|---|---|---|---|
| Heading | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ PATCH | ✅ 001–005 | **✅** |
| Paragraph | ✅ native | ✅ | ✅ W-2a | ✅ native only | ✅ | ✅ | ✅ PATCH | ❌ | **✅ native** |
| Table | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ P4c-1 | ✅ POST/PATCH/DELETE | ✅ 001–007 | **✅** |
| Footnote/endnote | ⚠ glyph-only | ✅ | ✅ | ✅ | ✅ | ✅ P4c-2 | ✅ PATCH | ✅ 001–002 | **✅ where detected** |
| Image + Figure | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ P4c-3 | ✅ PATCH/bulk/alt-text | ✅ 001–005 | **✅ native only** |
| Front matter | ✅ | ✅ | ✅ | ✅ L5'a | ✅ | ✅ | ✅ verifier | ❌ | ⚠ no route |
| **ListBlock** | ⚠ Mathpix only | ✅ | ✅ **new** `7d12932` | ✅ **48 nodes, unconsumed** | ✅ | ✅ anchored | ❌ **verifier, no route** | ❌ | **❌** |
| Callout | ✅ Mathpix | ✅ | ✅ | ❌ no node kind | ⚠ via heading | ⚠ via heading | ❌ GET only | ❌ | ❌ |
| Artifact classification | ✅ | ✅ | n/a | suppression | ✅ | ✅ | ✅ verifier | ❌ | ✅ |
| Reading order | ⚠ flag only | ✅ | n/a | ✅ order | ✅ | ✅ | ✅ PATCH | ✅ PAGE_003 | ✅ |
| Metadata | ✅ | ✅ | n/a | n/a | n/a | ✅ core props | ✅ PATCH | ✅ META_001/002 | ✅ |
| Page label | ✅ 107/161 | ✅ | n/a | ✅ marker text | ✅ | ✅ | ⚠ record, no verifier | ✅ PAGE_* | ⚠ undo broken |

**Genuinely complete end-to-end (detected → model → id → stream → both projections → rail → validated): headings, tables, images (native), notes (where detected), metadata, reading order.** Six classes — more than any previous audit could claim.

---

## 3. Corrections to earlier audits

| # | Earlier claim | Measured now | Cause |
|---|---|---|---|
| 1 | "RAWRS emits **zero** list paragraphs; human has 161" — ranked blocker #1 | native 0 **by design** (no ListBlocks on that path), **Mathpix 202** vs human 161 | native-only measurement |
| 2 | "Heading hierarchy: RAWRS under-produces (75 vs 115)" — blocker #4 | native 75, **Mathpix 199** vs 115 | native-only measurement; the Mathpix defect has the *opposite sign* and is larger |
| 3 | "DOCX never writes Title/Author/Subject" — blocker #6 | **20 core-property fields set on 10/10**; human sets 8 | already fixed by `_apply_core_properties`; claim is stale |
| 4 | bug_005 framed as requiring the span-level model | true natively; on Mathpix the markers are **literal markup** (33 in Bruner, 21 in Aims) needing no span model | path not separated |
| 5 | (unreported anywhere) | **Mathpix embeds 0 of 18 figures** | never measured on that path |

The common error: the corpus was measured on the native pipeline while the product's primary input is the Mathpix package. **Every ranking derived from native-only counts is unsafe.**

---

## 4. The new finding, root-caused

**On the Mathpix path every figure is silently dropped from the DOCX.** 18 of 18 files, 5 of 5 documents that have any.

```
Mathpix .jpg header = FF D8 FF DB   (bare JPEG: no JFIF APP0, no EXIF APP1)
python-docx recognises a JPEG only by "JFIF"/"Exif" at byte 6  -> UnrecognizedImageError
_docx_compatible_picture_source() re-encodes via Pillow - but ONLY when mode == "CMYK"
all 18 files are mode RGB -> returned as a plain path -> add_picture() raises -> embedded_in_docx=False
```

Measured (brinkman; identical shape on all five): `model images 2 · IMAGE nodes 2 · markdown image lines 2 · files exist True · embedded False · drawings in DOCX 0`. Pillow is already imported in that function and its docstring already names this exact python-docx limitation — the capability exists and the guard is one condition too narrow. `IMAGE_005` does fire, so the product already reports the loss it causes.

---

## 5. Reassessment of the fourteen named areas

| Area | Status now | Class |
|---|---|---|
| Heading hierarchy / missing H1 | native 75 vs 115 **and** Mathpix 199 vs 115; no rule reports "outline starts at H2" | D + E |
| Page-label / printed-page mapping | 107/161 detected; correction record exists but **no verifier ⇒ undo cannot work** | B |
| Superscript-encoded notes | native needs the span model; **Mathpix has literal markers the parser ignores** (33+21) | A (native E) |
| Cross-page sentence stitching | still unbuilt; explicitly checklist-mandated | A |
| Blockless / scanned documents | 41/161 pages carry no blocks; prose renders from `cleaned_text` | F natively; solved by Mathpix |
| **Mathpix vs native divergence** | the dominant fact of this audit: every class differs by path and no rule reconciles them | E |
| Metadata projection | **done** — 20 fields on 10/10 | ✅ |
| Table defects | 5/8 vs 28; Bryman 21 human vs 1 | A |
| List numbering / restarts | one `numId` per style ⇒ 4 documents with ≥2 numbered lists never restart | C |
| List nesting | **0 evidence anywhere** (0/205 MMD, 0/202 model, 0/161 human; template defines ilvl 0 only) | **retire** |
| Captions | model-owned since P4c-3; target uses a different style, so adjacency parity is unmeasurable | ✅ / measurement gap |
| Front matter | placed from the traversal; verifier exists, **no route** | B |
| Reading order | detect-and-flag plus PATCH; complete for what it claims | ✅ |
| Accessibility validation | 41 rules; **none for lists, paragraphs, front matter, or heading-hierarchy skips** | D |

---

## 6. Gap classification

| Class | Gaps |
|---|---|
| **A — missing capability** | native list detection; table detection on scanned pages; cross-page stitching; note markers from Mathpix superscripts |
| **B — capability exists, not wired** | **Mathpix figure embedding**; list correction route; front-matter route; page-label verifier |
| **C — projection-only defect** | list numbering restart; caption style parity |
| **D — validation-only gap** | heading-hierarchy skip rule; list rules; paragraph rules |
| **E — evidence/model gap** | span-level typography (native notes); Mathpix prose outside ContentStream; `ListItem` identity; lists inside table cells |
| **F — unsupported by current input** | geometry on blockless pages (native); notes where the source encodes nothing |

---

## 7. Ranked remaining gaps

| # | Gap | Impact | Frequency | Deps | Size | Visible value | Class |
|---|---|---|---|---|---|---|---|
| 1 | **Mathpix figures never embed** | total loss of every figure on the primary path | 18/18 files, 5/10 docs | none | **~5 lines** | **high, immediate** | B |
| 2 | Mathpix heading over-production (199 vs 115) | reviewer must delete ~84 headings | 4/10 docs | needs a decision rule | medium | high | D+E |
| 3 | Notes: 54 human vs 7 native / 0 Mathpix | whole apparatus missing | 47 notes, 2–3 docs | Mathpix none; native span model | small / large | high | A |
| 4 | Tables 28 human vs 5/8 | structure absent where densest | Bryman 21 | detection work | large | high | A |
| 5 | Heading hierarchy unreported | checklist violation invisible | 6/10 | none | small | medium | D |
| 6 | List correction route absent | 202 items no reviewer can touch | 6/10 | rail exists | medium | medium | B |
| 7 | Cross-page stitching | explicit customer requirement | most docs | none | medium | medium | A |
| 8 | Page-label undo broken | silent rail hole | 4/10 | verifier | small | low | B |
| 9 | List numbering restart | wrong numbers on 4 docs | 4/10 | none | small | low | C |
| 10 | List nesting | **none** | 0 | — | — | none | **retire** |

---

## 8. Mid-tier status, recalculated

The 2026-08-12 verdict (**B — not yet**) rested on "three object classes are not produced at all: lists, heading hierarchy, notes". Measured on the primary path that is now wrong on one count and half-wrong on another: **lists are produced (202, matching the model exactly), headings are produced in excess, and six classes are complete end-to-end.**

**Revised verdict: B+ — reviewer-assisted remediation is real for six object classes on the native path, and is blocked on the Mathpix path by one embedding bug and one accuracy problem.** The architecture is not the limit; what remains are ordinary product defects of decreasing size. What still prevents an unqualified mid-tier claim: a scanned document's DOCX contains **no figures at all** (#1) and carries roughly twice the headings it should (#2).

---

## 9. Recommended next milestone

### **M-1 — a figure that reached the model reaches the page**

**Problem.** `_docx_compatible_picture_source` re-encodes only CMYK images. All 18 Mathpix figures are RGB JPEGs with no JFIF/EXIF marker, which python-docx rejects, so `add_picture()` raises and the figure is dropped. 0 of 18 embed today.

**Change.** Widen the existing Pillow round-trip from "mode is CMYK" to "python-docx cannot recognise this file". The conversion, the in-memory buffer and the never-write-to-disk guarantee already exist in that function.

**Dependency chain.** None. One function; no model, stream, rail or object change.

**Acceptance gates.** Mathpix `embedded_in_docx=False` 18 → 0; Mathpix DOCX drawings 0 → 18; `IMAGE_005` on that path → 0; native path byte-identical (its 122 images already embed, and the Brinkman CMYK regression images must stay correct); PI-13 green; alt text and decorative state unchanged on every embedded figure.

**Why it beats the alternatives.** It is the only item where the capability is already built, the defect is total rather than partial, and the fix is smaller than the paragraph describing it. #2 needs a decision rule and a reviewer surface; #3 native notes need the span model; #4 needs new detection — each is a milestone. This is an afternoon, and until it ships, every hour spent on alt-text quality, caption identity or figure verification on the Mathpix path is spent on figures that never reach the deliverable.

**Explicit non-goals.** Native image behaviour; CMYK handling; alt-text generation; caption identity; the heading, note, table and list gaps above; anything in ContentStream.
