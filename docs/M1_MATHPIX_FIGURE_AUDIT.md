# M-1 — Mathpix figures reaching the DOCX: independent audit

**Date:** 2026-08-15 · **HEAD:** `c12d121` · **Status:** audit only — no code, no fixtures, no commit, no push.
**Probes (scratchpad, read-only):** `m1_trace.py` (full lifecycle, 5 documents), plus inline measurements of `docx.image.SIGNATURES`, Pillow round-trips per input class, and the native image inventory.

**Verdict up front: the previous audit's conclusion is right, its stated cause is wrong.** The failure is not a colour-mode problem. It is a JPEG *container marker* problem, and the CMYK branch only fixes marker problems by accident.

---

## 1. Why the figures disappear — the precise path

```
_add_stream_image()                                   src/docx/docx_generator.py (P4c-3)
└─ _add_image(path, alt_text, alignment, decorative)
   ├─ path.is_file()                                  → True  (files verified present)
   ├─ docx_document.add_paragraph()                   ← the paragraph is created BEFORE the attempt
   ├─ run = paragraph.add_run()
   ├─ picture_source = _docx_compatible_picture_source(path)
   │     PILImage.open(path).mode == "RGB"  → not "CMYK" → returns str(path) UNCHANGED
   ├─ run.add_picture(str(path))
   │     └─ docx.image.image._ImageHeaderFactory(stream)
   │           SIGNATURES = Png@0, Jfif@6, Exif@6, Gif@0, Tiff@0, Bmp@0
   │           file bytes[0:4] = ff d8 ff db      (SOI then DQT — a bare JPEG)
   │           file bytes[6:10] = 00 08 06 06     (neither "JFIF" nor "Exif")
   │           → raise UnrecognizedImageError
   └─ except Exception → logger.warning(...) → return False
      → image.embedded_in_docx = False
      → the caption still renders (a caption under nothing)
      → the empty paragraph stays in the body
```

Three consequences, all measured: **0 drawings, 0 media parts**, and **18 stray empty paragraphs** plus **8 orphaned captions** in the Mathpix DOCX.

---

## 2. Re-measured evidence

Independently re-run over all five image-bearing Mathpix documents:

| Claim | Measured | Verdict |
|---|---|---|
| 18/18 files affected | 18 files, `embedded_in_docx` False on 18, True on 0 | ✅ |
| 5/5 documents | Nature 1, Bryman 10, O'Leary 4, Teaching 1, brinkman 2 | ✅ |
| headers `FF D8 FF DB` | 18/18; bytes[6:10] = `00 08 06 06` | ✅ |
| images present in the model | 18 model images | ✅ |
| IMAGE nodes present | 18 nodes, **18/18 resolve to an Image** | ✅ |
| Markdown contains them | yes — but **26 lines for 18 images** (Bryman 19/10, Teaching 2/1) | ⚠ **new defect** |
| image files exist | 18/18, valid JPEGs Pillow opens | ✅ |
| `embedded_in_docx=False` | 18/18 | ✅ |
| zero DOCX drawings | 0 drawings **and 0 media parts** on all five | ✅ |

**Identity checked, as required:** 18 distinct `image_id`s, 18 distinct file paths, **18 distinct content SHA-256 values**. These are 18 separate semantic images, not duplicates of fewer. Alt text on 18/18; captions on 8; decorative on 0.

**New finding, not M-1's to fix:** the Mathpix Markdown renders 26 image lines for 18 images. DOCX is unaffected (P4c-3 drops every line whose path belongs to a placed image and emits from nodes), so after M-1 the DOCX will show 18 while that Markdown still shows 26.

---

## 3. What `_docx_compatible_picture_source` actually does

| Question | Answer |
|---|---|
| What does it handle? | **Only `mode == "CMYK"`.** Every other mode returns `str(path)` untouched. |
| What is it *for*? | Its own docstring names the python-docx JFIF/Exif signature limitation — it was written for the marker problem but its guard tests colour mode. |
| Why does CMYK "work"? | Converting CMYK→RGB and re-saving through Pillow writes a **JFIF header** as a side effect. |
| Is the mode conversion load-bearing? | **Yes.** Measured: a CMYK image saved by Pillow as JPEG *without* the mode conversion is **still rejected** by python-docx (Pillow writes Adobe APP14, not JFIF). |
| Is the reported failure caused by mode/encoding compatibility? | **No.** All 18 files are `mode=RGB`, `format=JPEG`, single-frame, no transparency, no EXIF orientation. They are rejected purely for lacking a JFIF/Exif marker. |

**Correction to the previous audit:** it said "the CMYK guard is one condition too narrow", implying a colour-mode fix. The accurate statement is that the function is a *marker normaliser* whose trigger condition happens to be colour mode, and the marker — not the mode — is what python-docx rejects.

---

## 4. Conversion policy, measured before choosing

Round-trip through Pillow, per input class, with acceptance re-tested against `_ImageHeaderFactory`:

| Source mode | save JPEG | accepted after | save PNG | accepted after |
|---|---|---|---|---|
| RGB (all 18 here) | ok | ✅ JFIF written | ok | ✅ |
| L grayscale | ok | ✅ | ok | ✅ |
| 1 bilevel | ok | ✅ | ok | ✅ |
| RGBA / LA / P (alpha, palette) | **OSError** | — | ok | ✅ |
| **CMYK** | ok | **✗ still rejected** | **OSError** | — |

Fidelity and cost on the real 18 (722,253 bytes on disk):

| Policy | total bytes | worst pixel delta | dimensions | notes |
|---|---|---|---|---|
| JPEG `quality=95` | 1,223,367 | 8 (mean 0.114) | preserved | one extra generation of loss |
| JPEG `quality=100` | ~1.6× | 4 (mean 0.022) | preserved | |
| **PNG** | 3,463,677 | **0 (lossless)** | preserved | 4.8× the source bytes |
| JPEG `quality="keep"` | 722,078 | **27** | preserved | smallest, but re-encodes on the source's own coarse tables |

**Damage assessment against the list asked for:** transparency — no source has any, and any future alpha source must go to PNG because JPEG raises; grayscale — safe in both formats; CMYK — **must keep the existing convert-to-RGB-then-JPEG path, since PNG cannot store CMYK at all**; alpha channels — PNG only; quality — measurable but sub-perceptual at q95, zero with PNG; EXIF orientation — 18/18 have none, but a Pillow re-save drops EXIF, so an orientation-bearing source would need `ImageOps.exif_transpose` before saving; dimensions — preserved by every option measured; accessibility metadata — untouched, because `descr`/`title` are written from `Figure.alt_text` after `add_picture`, never from the file.

**Conclusion: no single format is safe for every class.** PNG cannot carry CMYK; JPEG cannot carry alpha. The minimum correct policy has two branches keyed on the source image, not one blanket conversion.

---

## 5. The smallest correct fix

Not "make these 18 work". The rule that generalises:

> If python-docx can already read the file, hand it the path unchanged. Otherwise normalise it once through the Pillow path that already exists: alpha or palette → PNG; anything else → convert to RGB if the mode is not directly JPEG-storable, then JPEG.

Properties this preserves by construction, because none of them is read from the file: **identity** (`image_id` names the object; the source is only bytes), **order and traversal placement** (`_stream_images` and `close_page` are untouched), **dimensions/aspect** (measured preserved; `_MAX_IMAGE_WIDTH` scaling runs on the returned picture as before), **alt text / captions / decorative state** (written after `add_picture` from `Figure`), **embedded state** (`_add_image` still returns the truth).

The conservative shape keeps the existing CMYK branch byte-identical and adds the general fallback beneath it, so the 3 native CMYK images produce exactly the bytes they produce today.

---

## 6. Native behaviour must not move — the gate

Measured native inventory (122 extracted files, all 122 embed today):

| Marker at offset 6 | count | path taken today |
|---|---|---|
| `JFIF` | 118 | returned unchanged |
| `Adob` (CMYK) | 3 | CMYK→RGB→JPEG buffer |
| PNG signature at 0 | 1 | returned unchanged |

Before/after gate: native DOCX drawing count **122 → 122**; media parts unchanged; `extent cx/cy` identical per drawing; `descr` strings identical position-by-position; placement/order identical (P4c-3's body fingerprint); captions 2 → 2; decorative 0 → 0; the 3 CMYK images still embed with identical bytes.

---

## 7. Is anything upstream malformed?

**No.** Model 18, ids 18 distinct, nodes 18 all resolving, files present and readable, alt text 18/18, captions 8, `extraction_failed` 0. The Mathpix ingestion, the identity, the traversal and the Markdown all carry the figure correctly. **The defect is entirely at the projection boundary, in one function, and the fix belongs there.**

---

## 8. Validation

| Rule | Fires now | After M-1 |
|---|---|---|
| **IMAGE_005** — file exists, extraction succeeded, `_add_image` returned False | **18** (exactly the failures) | **0**, automatically |
| IMAGE_004 — alt text is a placeholder pending review (Info) | 18 | unchanged, unrelated |
| IMAGE_VERIFY_002/003/006/007/008 | 105/10/3/16/1 | unrelated (cross-source matching) |

**IMAGE_005 is precisely the right rule, it already fires on every affected image, and it goes green automatically. M-1 needs no validation change.**

---

## 9. Remediation consequence

Traced end to end for an edited Mathpix figure:

```
PATCH /documents/{job}/images/{image_id}   (review_image)
  → _record_reviewer_edit(...)             W-1 correction rail, FigureVerifier registered
  → Figure.alt_text / alt_text_status      on the model, revertible
GET /documents/{job}/download/docx
  → _ensure_current_export(job, "docx")    regenerates from CURRENT document state
  → _add_stream_image() reads Figure.alt_text → docPr@descr/@title
```

The rail is complete and the export is not stale. **Today that reviewed alt text is written onto a drawing that does not exist.** After M-1 it reaches the delivered file. This is what makes M-1 a remediation fix rather than a cosmetic one: it is the precondition for every hour already spent on FEATURE_012 alt text, caption identity and figure verification on the primary path.

---

## 10. Ranking against the other high-ranked gaps

| Gap | Corpus impact | Risk | Size | Decidable by rule? |
|---|---|---|---|---|
| **M-1 Mathpix figures** | **18/18 lost — 100% of an object class on the primary path** | **very low** — one function, one boundary, exact gate | **~10 lines** | yes, mechanical |
| Mathpix heading over-production | 199 vs 115 (+84) | high — needs a decision rule and reviewer surface | large | no, judgement |
| 47 superscript notes | 47 across 2 docs | high natively (span model); medium on Mathpix | large / medium | partly |
| Cross-page stitching | most documents | medium — editorial content generation | medium | no, judgement |
| Printed page labels | 107/161 | low | small | partly |
| Reference-list misclassification | 47 items, Bruner | high — heuristic, easily wrong | medium | no |

M-1 is the only one that is a **total** loss of an object class, has **zero** upstream dependencies, needs **no** new judgement, and has an **exactly checkable** gate.

---

## 11. Implementation plan (if approved)

**Commits: one.** The change is a single function's guard plus its tests; splitting it would produce a commit that cannot be gated.

| Item | Detail |
|---|---|
| **Files** | `src/docx/docx_generator.py` (`_docx_compatible_picture_source` only) · `tests/test_docx.py` **or** a new `tests/test_image_normalisation.py` |
| **Tests** | bare JPEG (no JFIF) → embedded; RGBA PNG → embedded with alpha preserved; grayscale → embedded; CMYK → unchanged existing behaviour; already-valid JPEG/PNG → **returned unchanged, not re-encoded**; unreadable file → still returns False, no crash; dimensions preserved in every case |
| **Corpus measurement** | Mathpix `embedded_in_docx=False` 18 → 0; Mathpix drawings 0 → 18; media parts 0 → 18; `IMAGE_005` 18 → 0; per-image `descr` equals that image's `Figure.alt_text`; 8 captions now sit under a real drawing |
| **Regression gates** | native drawings 122 → 122, media parts unchanged, `extent` per drawing unchanged, `descr` unchanged position-by-position, body fingerprint unchanged, 3 CMYK images byte-identical; PI-13 green; Markdown unchanged on both paths (this touches no renderer) |
| **Test batches** | `test_docx*.py`, `test_images.py`, `test_feature016_accessibility.py`, `test_image_review_api.py`, `test_projection_correctness.py` — sequential, only runs printing a completed summary count |
| **Non-goals** | native image behaviour; CMYK policy; the 26-vs-18 Markdown duplication; alt-text generation or wording; caption identity; decorative policy; `ContentStream`; image model changes; general image remediation |

---

## Recommendation

# IMPLEMENT M-1

**Evidence.** 18 of 18 Mathpix figures — verified as 18 distinct semantic images by id, path and content hash — are present in the model, present as resolving `IMAGE` nodes, present in the Markdown, present on disk with valid JPEG data and alt text, and produce **zero** drawings and **zero** media parts in the DOCX, leaving 18 empty paragraphs and 8 captions with nothing above them. The cause is one condition in one function: `_docx_compatible_picture_source` normalises only CMYK, while python-docx rejects these files for a missing JFIF/Exif marker that a Pillow re-save writes automatically. `IMAGE_005` already reports all 18 and turns green without a validation change; the correction rail and the regenerating export are already complete, so reviewed alt text reaches the file the moment a drawing exists to carry it. The conversion policy is measured rather than assumed — PNG for alpha/palette, RGB-then-JPEG otherwise, path untouched when python-docx can already read it — because PNG cannot store CMYK and JPEG cannot store alpha. The native path is provably unaffected: its 122 images are 118 JFIF, 3 CMYK on the existing branch, 1 PNG, and none reaches the new branch.

The one caveat worth stating: M-1 fixes **delivery**, not **selection**. Bryman's Mathpix run yields 10 figures against a human target of 3, and its Markdown emits 26 image lines for 18 images. Neither is M-1's to fix, and neither is a reason to defer it — a figure that is wrongly selected can be rejected by a reviewer, whereas a figure that never reaches the document cannot be reviewed at all.
