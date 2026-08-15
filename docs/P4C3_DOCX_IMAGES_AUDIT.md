# P4c-3 — DOCX images and captions: migration audit

**Date:** 2026-08-15 · **Status:** audited, then **implemented** — §14 records the two things implementation changed about §12.
**Base:** `ab7f904` (P4c-2) · **Corpus:** 10 native benchmark PDFs, `enable_ocr=False`, no Mathpix.
Probes: `p4c3_probe.py`, `p4c3_probe2.py`, `p4c3_gate.py`, `order_probe.py` (scratchpad, read-only).

---

## 1. IMAGE coverage — measured

| | value |
|---|---|
| `Image` objects | **122** |
| `IMAGE` nodes | **122** |
| nodes resolving to an `Image` by `image_id` | **122** |
| unresolvable nodes / duplicate nodes / images with no node | **0 / 0 / 0** |
| `bbox` / `document_order` | **122 / 122** |
| `source_block_id` | **2** of 122 |
| `source_block_id` naming a block that no longer exists | **0** |
| on block-bearing pages / blockless pages | **4 (3 pages) / 118 (24 pages)** |
| duplicate `file_path` | **0** |
| `extraction_failed` | **0** |
| `embedded_in_docx` True / False / None after generation | **122 / 0 / 0** |

**The 118 blockless images, accounted for:** 24 scanned pages across 3 documents (Bryman 112, O'Leary 4, "Teaching as a profession" 2). On those pages the stream holds **only** `page_marker` (24) and `image` (118) nodes — **zero** prose nodes. Their text exists solely in `Page.cleaned_text`.

**Node placement rule (`src/structure/content_stream.py:287-320`):** an image with `document_order` and no `source_block_id` is emitted at position `-1` — *before* all body on its page — because "no anchor" means "above every line". 120 of 122 images are in that state. On a blockless page that claim is **vacuous**: there is no prose node for the image to precede.

| where the traversal puts an image | count |
|---|---|
| before all prose on its page (`stream_image_first`) | 120 |
| after all prose (`stream_image_last`) | 2 |
| **strictly between two prose nodes** | **0** |

The last row is the decisive measurement: **no corpus image needs a mid-prose insertion point.** Two emission slots per page — before the prose run, or at page close — cover 122 of 122.

---

## 2. The current path

```
Image(+Figure) ──_render_images──> "![alt](path)" + "*caption*"   (markdown_builder)
   └── IMAGE node ─── used by markdown_builder's stream walk (P3b) — and by nothing in DOCX
                                   ↓
                       docx_generator re-parses those two lines
                                   ↓
   _add_image(path, alt, alignment, decorative) + _add_caption(text)
```

Markdown emits each image exactly once (122 lines / 122 images): the stream walk places it on block-bearing pages, a page-end sweep catches anything unplaced, and `_render_page` appends the whole set on a blockless page. `extraction_failed` images are skipped there — **their `IMAGE` node still exists**, so a node-driven emitter must skip them too.

---

## 3. Can DOCX render a stream-backed image from the model alone?

| need | model answer | today's transport | verdict |
|---|---|---|---|
| identity | `Image.image_id` | **the file path** (3 lookups keyed on `file_path`) | model, already |
| file/source | `Image.file_path` | markdown `(path)` | model |
| alt text | `Figure.alt_text` (122/122) | markdown `![alt]` | model |
| decorative | `Figure.alt_text_status == DECORATIVE` | **already read from the model** (`_build_decorative_set`) | model |
| figure metadata | `Figure.caption/label/number` | markdown `*caption*` adjacency | model (see §4) |
| placement | `document_order` + `source_block_id` | markdown line position | model **where the stream carries the page's prose**; page-end otherwise |
| alignment | `Image.bbox` + `Page.width_pt` | **already read from the model** (`_build_image_alignment_map`) | model |
| page relationship | `Image.page_number` | the page fence the line sits inside | model |
| embedded/generated media | `embedded_in_docx`; CMYK→RGB conversion in memory | — | pure DOCX mechanics, untouched |

Only three things actually come out of the markdown line today: **that an image exists, its path, and its alt text.** Everything else is already model-sourced and merely *keyed* by the parsed path.

---

## 4. Captions — the architectural question

| question | answer |
|---|---|
| how is a caption associated with its image? | **By composition.** `Figure` is a field of `Image` (architecture decision #4). The association is explicit in the model and cannot dangle. |
| is the association ever reconstructed? | Only in transport: markdown writes `*caption*` on the line after `![...]`, and DOCX recovers it by `pending_caption_after_image` adjacency. |
| does every corpus caption have exactly one image? | **Yes — 2 captions, 2 images, 1:1.** A caption cannot exist without an image, by composition. |
| any image with multiple or ambiguous captions? | **No.** `Figure.caption` is a single field; 0 caption strings shared by two images. |
| is caption ordering stable? | **Yes.** It renders immediately after its own image in markdown (2/2) and in the package (2/2 italic+centred paragraphs, both matching `Figure.caption` verbatim). |
| is caption text in the model? | **Yes**, plus `caption_source_text` (2/2), whose exact source line is on the caption's own page (2/2) and is suppressed from prose (0 captions leak into a `Paragraph`). |

**A caption needs no identity of its own to migrate.** It is a field of the image the node already names, exactly as `Table.caption` is for `_add_semantic_table` (P4c-1 shipped that shape). Inventing a `Caption` object for symmetry would add an id the model has no use for.

**One real hazard, retired by the migration:** `_CAPTION_PATTERN` is `^\*(.+)\*$`, which also matches a **bold** line `**Title**` — the corpus has 20 such single-line italic/bold blocks against 2 real captions. Only `pending_caption_after_image` keeps the other 18 from being eaten. Reading `Figure.caption` removes the ambiguity rather than guarding it.

---

## 5. Block-bearing vs blockless — the trap

| | block-bearing | blockless |
|---|---|---|
| pages carrying images | 3 | 24 |
| images | 4 | 118 |
| prose nodes on those pages | 22 paragraph + 41 body_line + 5 heading | **0** |
| markdown puts the image | at its node (2 mid-page, 2 page-end) | page end |

**Migration must be keyed on the image's own node, never on `is_stream_page()`** — that guard is False on all 24 blockless pages, so keying emission on it would drop 118 images. **But placement must still respect the guard**, because on a blockless page the node carries no prose-relative information at all. The safe rule:

> Emit every image from its `IMAGE` node. Place it **before the page's prose run** when the node precedes the page's prose *and the stream carries that prose*; otherwise **at page close** — the slot the markdown line already occupies.

Duplication is prevented the same way P4c-1/P4c-2 do it: the `![...]` line (and its caption line) is dropped for any image the traversal placed — which is all 122.

---

## 6. Decorative state

| stage | source | markdown involved? |
|---|---|---|
| `Figure.alt_text_status = DECORATIVE` | reviewer (FEATURE_012) | no |
| markdown | **does not carry it** — `_render_images` emits `alt_text` regardless | n/a |
| DOCX `docPr@descr=""` + `title=""` | `_build_decorative_set(document)` | **no — already model-read**, only *keyed* by file path |
| validation | `IMAGE_005` / `IMAGE_A11Y_002` read `embedded_in_docx` | no |

**Corpus: 0 decorative — all 122 are `pending_review`.** The decorative branch is fixture-only today and stays fixture-only after migration. Node-driven emission strictly improves it: the status is read off the image the node names instead of a path lookup.

---

## 7. Markdown parse sites in `src/docx/docx_generator.py`

| # | Site | Recovers | Class | Fate |
|---|---|---|---|---|
| 1 | `_IMAGE_PATTERN` (line ~838) | that an image exists; its path | **A** semantic recovery | retire for stream-placed images |
| 2 | `_IMAGE_PATTERN` group(1) | alt text | **A** | retire — `Figure.alt_text` |
| 3 | `_CAPTION_PATTERN` + `pending_caption_after_image` | caption text **and its association** | **A**, and ambiguous (§4) | retire — `Figure.caption` |
| 4 | `images_by_path` → `embedded_in_docx` | which `Image` this was | **A** (path as identity) | retire — the node names it |
| 5 | `_build_image_alignment_map` (path-keyed) | alignment | **C** model-read, path-keyed | keep, rekey to `image_id` |
| 6 | `_build_decorative_set` (path-keyed) | decorative | **C** model-read, path-keyed | keep, rekey to `image_id` |
| 7 | `_add_image` (`add_picture`, `_MAX_IMAGE_WIDTH` scaling, `docPr` descr/title) | — | **D** pure OOXML mechanics | untouched |
| 8 | `_docx_compatible_picture_source` (CMYK→RGB, in memory) | — | **D** | untouched |
| 9 | `_add_caption` (centred italic run) | — | **D** | untouched |

---

## 8. Projection gate — semantic profile, not bytes

Per document, before vs after:

| # | Measured | Why it is not covered today |
|---|---|---|
| 1 | image count: model / `IMAGE` nodes / `w:drawing` / `word/media/*` parts | `profile_from_docx` counts `docPr` only |
| 2 | image order, aligned to traversal order (already 122/122) | nothing checks order |
| 3 | `docPr@descr` **as three states** — set / `""` / absent | `profile_from_docx` normalizes `None` → `""`, so decorative and missing collapse |
| 4 | descr equals *that* image's `Figure.alt_text` (position-aligned) | set-membership only today |
| 5 | caption text, and its **adjacency** to its own image | absent |
| 6 | caption paragraph style (italic + centred) | absent |
| 7 | page placement: body items between the page marker and the image; before/after the page's prose run | absent |
| 8 | `extent cx/cy` (max-width scaling) | absent |
| 9 | `embedded_in_docx` True/False/None per image after generation | only via `IMAGE_A11Y_002` |
| 10 | relationship target per drawing (`word/media/*`) | absent |

**Proposed PI-13** (mirrors PI-11/PI-12): every `Image` that did not fail extraction has exactly one `IMAGE` node; every node resolves by `image_id`; each renders exactly once, in traversal order; each caption renders exactly once, immediately after its own image; and no caption's `caption_source_text` also renders as prose.

---

## 9. Corpus evidence — what is actually exercised

| Case | Corpus | Status |
|---|---|---|
| image on a blockless page | 118 | **proven** |
| image on a block-bearing page | 4 (3 pages) | thin but real |
| image anchored to a block (`source_block_id`) | 2 | thin |
| image preceding all text on its page | 120 | proven |
| multi-image page | 22 pages (up to 10 images) | proven |
| alt text present | 122 (24 distinct; a per-page placeholder) | proven |
| **decorative** | **0** | **fixture-only** |
| **`extraction_failed` with a live node** | **0** | **fixture-only** |
| caption | **2**, both Brinkman, both `Figure N.` labelled | **thin — fixtures needed** |
| caption on a blockless page | 0 | fixture-only |
| two images, one caption text | 0 | fixture-only |
| duplicate `file_path` | 0 | fixture-only |
| alt text containing `]`/`)`/newline | 0 | fixture-only (would break `_IMAGE_PATTERN` today) |
| Mathpix image (no anchor, no order) | 0 | out of scope |

---

## 10. Pre-existing defects this migration would expose (do not fix here)

| # | Defect | Evidence | Disposition |
|---|---|---|---|
| D1 | **Three different page-1 orders.** Stream: marker → IMG → IMG → paragraph → front_matter ×5. Markdown/DOCX: marker → title → author → affiliation → IMG → IMG → prose. | Brinkman page 1 | P4c-3 must reproduce the **rendered** order, not adopt the stream's. Front-matter placement is L5'a/P4b debt, not an image defect. |
| D2 | **Path as identity** in three lookups (alignment, decorative, `embedded_in_docx`). 0 collisions today; two images sharing a path would silently share alignment, decorative state and the embed flag. | 0 duplicate paths | Removed as a *side effect* of node-driven emission. Not a separate fix. |
| D3 | `_CAPTION_PATTERN` matches `**bold**` lines (18 non-caption matches on the corpus, all currently guarded by adjacency). | 20 italic/bold single lines vs 2 captions | Site retires for stream images; survives only for markdown with no traversal. |
| D4 | `profile_from_docx` cannot distinguish `descr=""` (decorative) from absent. | `src/benchmark/profile.py:161` | Gate weakness — addressed **in the new profile**, not by editing `profile.py`. |
| D5 | An `extraction_failed` image has an `IMAGE` node but no markdown line, so today it never reaches `_add_image`. A naive node walk would try to embed it and set `embedded_in_docx=False`. | 0 on corpus | The emitter must skip failed extractions, mirroring `_render_images`. Named, not "fixed". |

---

## 11. Fit with P4c-1 / P4c-2

Same three-step shape, third time: **resolve the node → call the existing model-driven renderer → drop the markdown line.** `close_page()` already emits this page's tables and registers its notes; images join it as the third resident, plus one new slot ("before the prose run") that tables and notes did not need. After P4c-3, `Document → ContentStream → DOCX` covers page identity, prose, headings, tables, notes, images and captions; markdown remains the transport only for blockless-page **prose**, lists, and the `## Endnotes` heading.

---

## 12. Proposed scope

| | |
|---|---|
| **Commits** | **One.** Captions cannot be split from images (no independent identity), and splitting "images by identity" from "images by placement" would ship a half-keyed emitter. |
| **In scope** | IMAGE-node emission for all 122 images; caption from `Figure.caption` right after its image; alignment/decorative/`embedded_in_docx` rekeyed from `file_path` to `image_id`; markdown image + caption lines dropped for placed images; PI-13; the §8 profile; fixtures for decorative, `extraction_failed`, caption-on-blockless-page, two-images-one-caption-text, duplicate `file_path`, alt text with markdown-breaking characters. |
| **Non-goals** | Byte identity; blockless-page **prose**; front-matter order (D1); a `Caption` object; changing any image's rendered position; Mathpix images; lists (P4c-4); `markdown_content` in `generate_docx`'s signature (P4d); fixing D2/D4 anywhere other than as a consequence of this change. |
| **Invariants** | PI-13 as stated; PI-1/PI-2 (markdown) unchanged — `markdown_builder` is not in the diff. |
| **Regression gates** | §8 profile identical before/after on all 10 documents; all 10 markdown hashes unchanged; `tests/test_docx*.py`, `test_feature016_accessibility.py`, `test_table_accessibility.py`, `test_projection_correctness.py` green. |
| **Corpus acceptance** | 122 images / 122 drawings / 122 media parts; descr strings identical position-by-position; 2 captions adjacent to the same 2 images; page placement unchanged for 122/122; `embedded_in_docx` True for 122. |
| **Known limitations after P4c-3** | Blockless-page images keep the page-end slot (118 of 122) because the traversal carries no prose there; decorative and `extraction_failed` remain fixture-only; a caption still has no identity, so no per-caption correction or verification can address one. |

---

## 13. Recommendation

**A — P4c-3 can proceed as IMAGE-node direct projection, with captions riding on the image**, subject to the two-slot placement rule of §5 (before the prose run / at page close), which is not a guess: 0 of 122 corpus images require a mid-prose insertion point, and the 118 blockless images have no prose in the stream to be ordered against.

---

## 14. What implementation changed about this audit

Two of §12's claims did not survive the regression gate, both because the audit measured where each image sits *relative to prose* and never compared the two projections' **order among the images on one page**.

| # | §12 said | Measured on implementation | Disposition |
|---|---|---|---|
| 1 | Non-goal: "changing any image's rendered position"; corpus acceptance: "page placement unchanged for 122/122" | `document.images` is PyMuPDF's return order; `IMAGE` nodes are sorted by `Image.document_order`, which is reading order. The two disagree on **17 of 22** image-bearing scanned pages, all in Bryman. Node-driven emission moves **60 of 112** Bryman images. Brinkman page 1 is the clearest case: the image at `y0=5.0` is `document_order` 0 but extracted second, so it rendered *below* the image at `y0=63.4`. | **Accepted, not reverted.** Reading order is the correct order for a remediation target, and preserving extraction order would have meant hard-coding a list position over the traversal — the exact thing P4c-3 removes. Reported as P4c-3's one semantic difference, the way P4b reported `*****`. |
| 2 | Invariant: "PI-1/PI-2 (markdown) unchanged — `markdown_builder` is not in the diff"; gate: "all 10 markdown hashes unchanged" | Leaving `markdown_builder` alone would have left the two projections disagreeing about image order on 17 pages, since only DOCX had moved to the traversal. | **One line changed** in `_render_page`: the blockless page-end list is sorted by `document_order` before rendering. Nothing else in `markdown_builder` is in the diff. |

Also corrected: **markdown hashes are not a stable gate for image-bearing documents at all.** Each extracted image file is named with its `image_id`, a fresh `uuid4` per run, so 4 of the 10 documents' markdown hashes differ between two runs of unmodified code. `p4c3_gate.py` masks the uuids; the 6 image-free documents hash identically either way.

**Final gate result** (`before.json` vs `after.json`, 10 documents): identical in drawing count, media parts, relationship targets, `descr` strings position-by-position, `descr` three-state, extents, alignment, caption adjacency, `embedded_in_docx`, body sequence and masked markdown hash — **except** Bryman's image order in both projections, as above. Suites green: `test_docx*.py`, `test_markdown.py`, `test_image*.py`, `test_feature016_accessibility.py`, `test_table_accessibility.py`, `test_projection_correctness.py`, `test_architectural_invariants.py`, `test_benchmark_*.py` — 812 tests across 6 batches, 0 failures, plus 17 new tests in `tests/test_docx_image_projection.py`.
