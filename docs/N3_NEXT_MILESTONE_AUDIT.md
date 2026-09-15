# N-3 — what to build next, measured at `ca0547c`

**Date:** 2026-08-16 · **HEAD:** `ca0547c` · **Status:** audit only — no code, no fixtures, no commit, no push.
**Authority for "correct":** `docs/ChecklistBeforeSubmittingDoc.xlsx` (40 "Both" rows), `docs/PHASE1_SCOPE.md`
(north-star metric: *human minutes per 100 pages*). **Primary path:** Mathpix. Native = regression path.

---

## 0. Three findings that overturn the previous ranking

| # | Previously believed | Measured now |
|---|---|---|
| 1 | Page identity is fine — "page breaks parity 153 / 151 / 144" | **Only 11% of Mathpix blocks are on the right page.** Counts matched; placement never did. §1 |
| 2 | The benchmark holds a **human-remediated** DOCX target | The ten files in `samples/benchmark/remediated_docx` are **byte-identical (SHA-256) to the `.docx` that ships inside each Mathpix package**. The "human target" is Mathpix's own export. §2 |
| 3 | Bryman's 21 tables "are not in the input" | Not in the `.mmd` (1 `tabular`) — **but the package's own DOCX has all 21**. The input is richer than the file RAWRS reads. §2 |

Consequences: heading "over-production" (204 vs 115) is not a defect — RAWRS reproduces the MMD's own
`\section` count exactly, and the "target" is just Mathpix's other rendering of the same source. Heading
*hierarchy skips* are **0 across the corpus**. Both prior candidates are dead.

---

## 1. The defect nobody measured: which page a block is on

`src/mathpix/page_estimation.py` assigns every Mathpix object a page by *proportional line position*
(`ceil(source_line / total_blocks × page_count)`). Measured against an independent oracle — the PDF's own
text layer, block by block:

| Document | verifiable blocks | exact page | off by 1 | off by >1 | worst error |
|---|---|---|---|---|---|
| Nature of Enquiry | 247 | 12 | 22 | 213 | 12 |
| Aims of Education | 22 | 10 | 9 | 3 | 2 |
| FolkPedagogy (Bruner) | 67 | 11 | 0 | 56 | 12 |
| sockett | 16 | 0 | 7 | 9 | 4 |
| Teaching as a professional | 93 | 0 | 4 | 89 | 15 |
| Calderhead | 16 | 8 | 7 | 1 | 2 |
| Fullan & Hargreaves | 24 | 5 | 12 | 7 | 2 |
| brinkman | 119 | 21 | 24 | 74 | 9 |
| Bryman / O'Leary | 0 | — | — | — | scanned, no text layer |
| **TOTAL** | **604** | **67 (11%)** | **85 (14%)** | **452 (75%)** | **15** |

Second, independent oracle — Mathpix names every extracted image `{uuid}-{PAGE}_{x}_{y}_{w}_{h}.jpg`.
Of the **8** figure blocks whose filename states a page, **0** are placed on it; every error is **+3 to +6
pages, always late**.

Reading *order* is unaffected (the estimate is monotone in `source_line`); **page identity is what is wrong**.
What that breaks today: every validation issue's `page_number` (652 issues corpus-wide), DOCX page-break
placement, per-page image/table/note placement, printed page labels (87 of 161 pages), and the reviewer's
page navigation in the IDE — the reviewer is sent to the wrong page for most findings.

---

## 2. What the package actually contains, per document

`img/enc` = images present / images whose filename encodes a page. `pkg` = the `.docx` shipped in the package.

| Document | PDF pages | pkg page breaks | pkg H6 page labels | pkg tables | pkg endnote refs | pkg hyperlinks | img/enc | MMD `\section`+`\subsection` | MMD `tabular` | MMD `${ }^{N}$` |
|---|---|---|---|---|---|---|---|---|---|---|
| Nature of Enquiry | 28 | 27 | **28** | 2 | 4 | 1 | 1/0 | 12+18 | 3 | 4 |
| Aims of Education | 4 | 3 | **4** | 0 | **11** | 0 | 0/0 | 1+0 | 0 | 21 |
| Bryman | 26 | 25 | 25 | **21** | 0 | **40** | 10/10 | 53+0 | 1 | 0 |
| Bruner | 26 | 22 | 22 | 0 | 36 | 0 | 0/0 | 32+0 | 0 | 33 |
| sockett | 9 | 17 | 17 | 0 | 0 | 0 | 0/0 | 14+0 | 0 | 0 |
| O'Leary | 13 | **0** | **0** | 0 | 0 | 0 | 4/4 | 34+0 | 0 | 0 |
| Teaching as a professional | 27 | 25 | **0** | 0 | 0 | 0 | 1/1 | 10+0 | 0 | 0 |
| Calderhead | 4 | 3 | **4** | 0 | 0 | 0 | 0/0 | 3+0 | 0 | 0 |
| Fullan & Hargreaves | 6 | 5 | **6** | 0 | 0 | 0 | 0/0 | 4+0 | 0 | 0 |
| brinkman | 18 | 17 | **18** | 5 | 3 | 7 | 2/2 | 18+0 | 9 | 3 |

* The H6 paragraphs carry the **printed page number as text** (`'3'`, `'4'`, `'5'` …) — page boundary *and*
  printed label, in document order. Present on **8 of 10**; the two exceptions (O'Leary, Teaching as a
  professional) are pandoc-style exports.
* sockett: 9 PDF pages, 17 printed pages — a 2-up scan. Physical page ≠ printed page, by construction.
* **Nothing in `src/` reads the package `.docx` or parses an image filename** — zero call sites.

**Alignment feasibility (MMD block text ↔ package DOCX paragraph text, exact after normalisation):**
770 of 1,089 body blocks match, 766 of them uniquely, order-monotone on 8 of 10 documents with a naive
dictionary lookup. A sequence-anchored walk raises both figures; 71% is the floor, not the ceiling.

---

## 3. Chain audit, per class (Mathpix path at `ca0547c`)

| Class | corpus now | package says | identity | stream | Markdown | DOCX | reviewer route | validation | class of gap |
|---|---|---|---|---|---|---|---|---|---|
| **Page identity** | **11% correct** | boundaries + labels on 8/10 | `Page.page_number` | `PAGE_MARKER` | ✅ markers | ✅ breaks | PATCH page-labels | PAGE_001-008 | **parser/ingestor loss** |
| Printed labels | 87 / 161 pages | every page on 8/10 | `Page.printed_label` | — | ✅ | ✅ | PATCH + PUT sections | PAGE_* | same evidence |
| Headings | 204 content, 0 skips, no H1 on 5/10 | 22–36 per doc | `Heading.id` | `HEADING` | ✅ | ✅ | PATCH /headings | HEADING_001-005 | **policy** (title choice), not a defect |
| Lists | 45 blocks / 163 items | ListParagraph only | `ListBlock.id` | `LIST` | ✅ | ✅ | **none** | LIST_VERIFY_001-003 | **correction/workspace gap** |
| Notes | 39 bodies / 36 refs | **54 refs** (Aims 11, Nature 4 absent from the MMD) | `footnote_id` | `NOTE_DEFINITION` | ✅ | ✅ endnotes | PATCH /footnotes | NOTE_001/002 | **missing from MMD, present in pkg DOCX** |
| Tables | 8 | **28** (Bryman 21) | `Table.id` | `TABLE` | ✅ | ✅ | POST/PATCH/DELETE | TABLE_001-007 | **not in MMD; in pkg DOCX** |
| Figures | 18, all alt-texted, 8 captioned, 0 decorative | 11 drawings | `image_id` | `IMAGE` | ✅ | ✅ | PATCH + bulk + AI alt | IMAGE_001-005 | **closed (M-1)**; only the page is wrong |
| Metadata | language 0/10, `w:lang` 0/10 | 1/10 | — | — | — | writes `props.language` **if set** | PATCH /metadata | META_001/002 | **detection gap** (projection exists) |
| Hyperlinks | 0 | 48 (PDFs hold 12 real URI links) | — | — | ❌ | ❌ | none | none | parser + projection gap |
| Bookmarks / TOC | 0 | 233 / 1 | — | — | — | — | — | — | **conversion artefact**; checklist says "if required" |
| Cross-page stitching | n/a | — | — | — | — | — | — | — | **not a Mathpix defect** — the package delivers whole paragraphs |
| Blockless / scanned | 4 of 10 have no text layer | package still carries structure | — | — | — | — | — | — | why the package matters more than the PDF |
| Validation load | **652 issues** (Bryman 209, Bruner 200) | — | — | — | — | — | PATCH validation-issues | 41 rules | **triage gap** — §4 |

---

## 4. Candidates, with the numbers that decide them

| # | Candidate | corpus now | reference | deficit | evidence | blocker | complexity | unlocks | deterministic gate |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Page identity from the package** | 11% correct, 87/161 labels | 8/10 packages state every page | 537 of 604 blocks misplaced | pkg DOCX H6 + image filenames + PDF text layer | none — ingestor only | **medium-small** | correct issue pages, breaks, labels, per-page placement; the alignment #2 needs | PDF text layer + filename pages (neither is the reference file) |
| 2 | Package DOCX as a second source | tables 8, notes 36, links 0 | 28 / 54 / 48 | 20 tables, 18 refs, 48 links | pkg DOCX | needs #1's alignment | large | three classes at once | counts + cross-source verifier |
| 3 | Verifier-noise triage | 652 issues; 72 of Bruner's 200 are `FOOTNOTE_VERIFY_002/004` on *correct* imports | — | two findings per correct note | already in model | none | small | reviewer minutes | issue counts per class on unchanged output |
| 4 | List correction route | 163 items | — | not addressable | model complete | none | small-medium | reviewer edits lists | route + rail tests |
| 5 | Document language | 0/10 | 1/10 | two checklist rows | text is present | detection only | trivial | META_001, WCAG 3.1.1 | `w:lang` + `dc:language` on 10/10 |

Rejected after measurement: heading over-production (RAWRS is faithful to the MMD), hierarchy skips (0),
cross-page stitching (not a defect on this path), bookmarks/TOC (conversion artefacts), native span-model
notes (large, native-only), table *detection* on scanned pages (unnecessary once #2 reads the package).

---

## 5. Recommendation — **P-1: "a block's page is stated by the package, not estimated from its position"**

The only defect that is (a) wrong in 89% of instances, (b) invisible in every prior audit, (c) fully evidenced
in the primary input, (d) provable against two oracles that are *not* the reference file, and (e) a
prerequisite for the milestone after it.

**Non-goals.** Tables, notes, hyperlinks or headings from the package DOCX (that is X-1). No reviewer routes.
No new validation rules. No native-path change. No ContentStream change. No renumbering policy. No OCR.
No change to what an object *is* — only to which page it is on.

**Sequence / commit decomposition.**

| # | Scope | Output change | Gate |
|---|---|---|---|
| 1 | `src/mathpix/package.py` — read the sibling `.docx`: ordered paragraph texts + H6 printed labels. Pure reader. | none | 10/10 packages read; 8/10 expose labels; unit tests |
| 2 | `src/mathpix/page_alignment.py` — order-preserving alignment MMD block ↔ package paragraph (exact normalised text, strictly increasing anchors); unmatched blocks inherit the nearest preceding anchor; nothing matched ⇒ no answer | none — nothing consumes it | corpus report: ≥90% of body blocks receive a page on the 8 labelled documents |
| 3 | `src/mathpix/ingestor.py` — pages for paragraphs, headings, lists, tables, figures and note anchors come from the map; `Page.printed_label` from the marker text; `estimate_page` stays as the documented fallback | pages move | the gate below |
| 4 | figures fall back to the page encoded in their filename when the alignment has none | figure pages move | 8/8 encoded figures exact |

**Fail-closed property.** No package DOCX, no alignment, or a non-monotone anchor ⇒ the block keeps today's
estimate and no printed label is invented. A page is only ever *stated*, never guessed, and the fallback is
exactly current behaviour — the milestone cannot make any document worse than `ca0547c`.

**Acceptance gate (both oracles independent of the package DOCX).**

| Scope | Gate |
|---|---|
| PDF-text-layer verification | exact-page **11% → ≥ 90%**, off-by->1 **452 → ≤ 20**, over the 604 verifiable blocks |
| Figure filenames | **0/8 → 8/8** exact |
| Printed labels | **87 → ≥ 140** of 161 pages, each copied from a stated marker |
| Notes | Bruner 36 bodies / 33 refs / identity-paired 33 — unchanged |
| Headings, lists, tables, images | counts unchanged on all ten documents |
| Native path | byte-identical on all ten |
| Fallback documents (O'Leary, Teaching as a professional) | output unchanged — no labels invented |
| Validation | issue counts unchanged in kind; page numbers move only where the alignment states a page |

**Stopping point.** After commit 3 (commit 4 if the figure fallback is wanted) and the gate above. Do not start
X-1. Do not touch the correction rail, validation rules, or the native path.

**Open product decision (for the user, not decided here).** P-1 assumes the customer's Mathpix package
includes the `.docx` alongside the `.mmd` — true for 10 of 10 packages here. If that cannot be assumed,
commit 2's alignment falls back to the PDF text layer, which covers 6 of these 10 documents and none of the
pure scans; the milestone still holds, at reduced coverage.
