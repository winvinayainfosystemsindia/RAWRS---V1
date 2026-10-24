# OCR quality: garble detection and GLM-OCR re-reading

Added 2026-10-24. Closes most of gap 2 of `techstack.md` §10 (and is the first verifier on the PDF-only path, gap 3) and implements Experiments 1b/2/4/5 of `docs/RAWRS_PDF_ONLY_RECONSTRUCTION_RESEARCH.md` on the PDF-only path.

## The problem

Docling's recognizer (RapidOCR, PP-OCRv6) garbles bold and italic runs on scanned and flattened pages, and it does so confidently. For example, "Indicate whether you foresee a relationship…" comes out as `In nde o o ad  ie  ef o n adhn`. The page still gets `ocr_confidence=medium` and no rule fires, so the garbled text ships.

## What runs now

| Step | Where | What it does |
|---|---|---|
| Detect | `src/ocr/quality.py` | A line is garbled when a 6-token window holds ≥3 nonsense tokens (1–2 letters that aren't English words, or vowelless), or when ≥2 irregular spacing gaps come with ≥1 nonsense token. Lexicon-free. |
| Mark | `src/ocr/docling_engine.py` | Each garbled Docling text item, with its bbox, is stored on `Page.ocr_rereads`. Heading lines are skipped. |
| Re-read | `src/ocr/reread.py` | Only the garbled crop (200 DPI) goes to `glm-ocr:q8_0` (MIT, 0.9B) on the local Ollama. Readings are cached per PDF page. |
| Judge | `reread._judge` | A reading is accepted only if it isn't garbled itself, keeps ≥85% of the original's readable words (the anti-hallucination check), and is 0.7–2× the original's length. |
| Apply | `src/verification/ocr_text.py` | Each accepted reading becomes an `AUTO_APPLIED` CorrectionRecord (`OCR_REREAD_001`), undoable in the Corrections panel. Each asset type now gets its own undo transaction. |
| Flag | validator `OCR_004` | Any line still garbled (reading rejected, or no model available) is a warning that says why. |

The stage is skipped when `RAWRS_OCR_REREAD=off`, in AI stub mode (tests/CI), or when Ollama or the model is missing. In those cases OCR_004 still flags the lines. Model: `RAWRS_OCR_REREAD_MODEL`, default `glm-ocr:q8_0`.

## Evidence (Codespace, 4 cores, CPU only)

| Measure | Result |
|---|---|
| Detector vs eye-labelled Docling items (O'Leary + Bryman, 368) | 17/17 garbled flagged, 0/351 clean flagged (`tests/fixtures/ocr_quality/`) |
| O'Leary: garbled regions re-read / accepted | 12 / 12; 4–20 s each; OCR_004 issues 12 → 0 |
| O'Leary 4-gram recall vs human-remediated DOCX | 94.8% → **98.5%** (Mathpix MMD scores 97.0%) |
| O'Leary 4-gram precision vs human-remediated DOCX | 94.0% → **96.7%** |
| Bryman: garbled regions re-read / accepted | 5 / 5; 4-gram recall 96.1% → 96.2% (the garble was 5 short paragraphs) |
| 8 born-digital PDFs, main vs branch, OCR on | 0 garbled regions; Markdown identical apart from random image-file ids |

## Limits

- Only Docling text items are re-read. Surya pages and heading lines are flagged, not repaired.
- A dropped ✓ is restored only when the VLM output omits a non-ASCII symbol that starts the item.
- Garble made only of plausible-looking long words is caught through its spacing alone. A dictionary hit rate is the upgrade if that ever misses.
