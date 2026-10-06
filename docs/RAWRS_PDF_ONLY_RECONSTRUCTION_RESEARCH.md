# RAWRS Research: PDF-Only Document Reconstruction vs Mathpix

**Status:** research only. No code changed, no dependencies installed, no models downloaded. All probes used libraries already installed in `.venv` (PyMuPDF 1.28.0, onnxruntime 1.30.0, rapidocr 3.9.0, surya-ocr 0.20.0).

**Test case:** `samples/benchmark/pdfs/4. O Leary_Developing the research questions.pdf` (O'Leary, *The Essential Guide to Doing Research*, ch. 3 — 13 pages, 11.5 MB / 11,451,177 bytes) compared against:
- `samples/mathpix/4. O Leary_Developing the research questions/` — the Mathpix MMD package (gold standard for comparison)
- RAWRS PDF-only output — job `a6ef1cb3ad02473d9dfc027805121272` (Markdown, DOCX, report JSON; copies in `outputs/` and `C:\Users\WVF-D\Downloads\`)

**Companion doc:** `docs/OCR_MATHPIX_REPLACEMENT_RESEARCH.md` (model-landscape research; this report cites it rather than repeating it).

**Evidence labels used throughout:**
- **[SUPPLIED]** — from the supplied files (PDF, MMD, RAWRS outputs) and probes run against them
- **[CODE]** — from RAWRS source code
- **[EXT]** — external research (benchmark leaderboards, model cards, licenses)
- **[INF]** — inference / recommendation

---

## 1. Executive conclusion

**The "born-digital" document was never born-digital.** The supplied PDF has **zero text layer** — 0 characters and 0 fonts on all 13 pages, all content drawn as vector paths (64–420 paths per page), producer `Microsoft: Print To PDF` printing an ebook PDF to file. Despite its provenance, it behaves exactly like a scan. [SUPPLIED, probed with PyMuPDF]

Two consequences reframe the whole question: [INF]

**1 — OCR is mandatory on every page, whatever we call the PDF.** The router did its job correctly (all 13 pages classified `OCR_REQUIRED`, since text < 20 chars). Nothing "failed to route." The real failure is *which recognizer* ran: RapidOCR (PP-OCRv6, Docling's engine) garbled the emphasized runs at every DPI tested, while Surya-2 — already installed as the fallback — read the same page perfectly, but took 347.7 s for one page on CPU. [SUPPLIED, probe]

**2 — "Scanned vs born-digital" is the wrong routing axis.** What matters is not how the PDF was made but whether the recognizer can *read the render*. This document proves a PDF can be born-digital in provenance and scan-like in behavior. Routing must be based on measured, render-based quality signals — not provenance labels. [INF]

**What would have closed the gap:**
1. A stronger recognizer on the rendered page (GLM-OCR 0.9B, MIT, via Ollama — the runtime already running on this machine — is the practical candidate).
2. Escalation on **poor quality**, not just emptiness (current escalation fires only when Docling returns an empty page, so it never ran here despite visibly garbled output).
3. The winner metric stays **human remediation minutes per 100 pages** — the only number that decides whether any of this matters.

**Bottom line:** Mathpix does not win because it "handles born-digital PDFs better." It wins because it runs a better recognizer on the same rendered pixels. Every meaningful defect in this document traces to one root cause — recognizer quality on emphasized runs — plus governance gaps that let the garbage through undetected (0 verification findings, overstated "medium" OCR confidence). [SUPPLIED + INF]

---

## 2. What actually went wrong in the supplied document

### 2.1 The PDF itself [SUPPLIED — probed with PyMuPDF]

| Property | Value | Consequence |
|---|---|---|
| Text layer | 0 chars, 0 fonts (all 13 pages) | Native extraction empty → OCR on 13/13 pages |
| Content | 64–420 vector paths/page across the document | Text exists only as vector glyph outlines |
| Raster images | 11 small rasters, all on page 6 | The 4 real textbook figures are mostly vector art, not embedded rasters |
| Producer | `Microsoft: Print To PDF` of an ebook PDF | Flattened; no ToUnicode maps, no logical structure, no tags |
| Size | 11.5 MB / 13 pages | Heavy vector payload per page |

### 2.2 The Mathpix MMD (comparison source — read in full) [SUPPLIED]

Near-perfect on this document:
- Bold bullet lead-ins intact (e.g. **"Indicate whether you foresee a relationship between concepts you are exploring"**), correct bullets, bold/italic runs, correct quotes/diacritics.
- 4 figures **cropped from page renders** (bbox-named crops like `...-04_718_1337_277_311.jpg`), each with an attached caption (`\caption{FIGURE 3.1 CONCEPT MAP...}`).
- Math spans preserved (`$25-45$`).

**Mathpix is not perfect either** — do not treat it as ground truth:
- Page number "3" became `\section*{3}` (a page number as a section heading).
- The two quote lines became `\section*` headings.
- `-Albert Szent-Gvorgi` attribution became a section.
- Checkmarks (✓) dropped entirely.

### 2.3 The RAWRS PDF-only output [SUPPLIED]

**Text (md + docx + report all consistent):**
- Bold/italic runs garbled by OCR: `- In nde o o ad  ie  ef o n adhn whether you are looking for impacts…` (should be "Indicate whether you foresee a relationship between concepts you are exploring…"), also `-  l   sdd  d  -d ence) … A welldefined research question will:` (should be "A well-articulated research question can provide you … A well-defined research question will:"). Note the exact strings carry irregular spacing — OCR output. Pattern: **bold/italic runs garbled; regular text fine** — the regular-text instance of "well-defined" (line 44 of the output) survived perfectly while the bold one became "welldefined".
- Checkmark ✓ glyphs vanished.
- "well-defined" → "welldefined" (hyphen lost).

**Structure:**
- 13 `###### N` H6 page-number headings. **These are a deliberate RAWRS feature** (`src/headings/page_markers.py`, `PAGE_RULES.md`: one H6 marker per page; the Mathpix path omits them and `markdown_builder` synthesizes them from package evidence). Parity difference, not an OCR defect. [CODE]
- HEADING_001 warning (H1→H3 jump); META_001/META_002 (no `dc:language`/`dc:title` on the PDF-only path). Accessibility score 95.0.
- Box 3.2 sub-headers promoted to H2 (wrong hierarchy).

**Figures (DOCX XML census):**
- All 4 images have `descr=""` (empty alt text → a checklist-audit failure class).
- All 4 images dumped consecutively at the end of page 6.
- Figure captions detached from images (FIGURE 3.2's caption text remains on the wrong page).

**Governance:**
- Verification found **0 findings, 0 corrections** — `import_provider=None` means every cross-source verifier skips. All structural collections persisted empty (0 blocks/paragraphs/lists/tables/equations/footnotes). [CODE + SUPPLIED]
- Per-page JSON: every page `extraction_method='docling'`, `routing_decision='route_to_docling'`, **`ocr_confidence='medium'`** — while the text was measurably garbled. No downstream signal could ever fire on "medium."
- Timing: 213 s for 13 pages (~16 s/page), last stage `run_validation`.

### 2.4 The decisive OCR probe [SUPPLIED, probe]

- **RapidOCR** (PP-OCRv6 det/rec_small via onnxruntime) at **150 / 300 / 400 DPI**: the bold bullet was *never* recovered at any DPI (fragments like `In nde o o ad` every time). → **The failure is the model, not resolution.**
- **Surya-2** (`surya-2.gguf` via llama.cpp — the already-installed fallback): recovered the bold bullet **perfectly**, first try. Cost: 347.7 s inference for one page on CPU (predictor ready in ~2 s).
- Housekeeping: a stray `llama-server` PID 17856 spawned by the probe is confirmed gone (netstat verified 2026-10-05).

---

## 3. RAWRS failure-provenance map

Every row: PDF evidence → RAWRS stage → observed error → downstream consequence. [SUPPLIED + CODE]

| # | PDF evidence | RAWRS stage | Observed error | Downstream consequence |
|---|---|---|---|---|
| 1 | 0-char text layer | `route_pages` (text < 20 chars → OCR_REQUIRED) | All 13 pages → `route_to_docling` | OCR on 100% of pages (routing itself correct) |
| 2 | Bold/italic runs in the render | Docling → RapidOCR recognition | Bold lead-ins garbled | Meaning destroyed; reviewer must retype from the PDF |
| 3 | ✓ glyphs drawn in the page | OCR | Checkmarks dropped | Checklist semantics lost (this is a research-methods book) |
| 4 | "well-defined" | OCR (hyphen loss) | "welldefined" | Typo ships in the remediated doc |
| 5 | 4 logical figures (vector art + 11 small rasters on page 6) | `image_extractor` + `_group_images_by_page` | 11 rasters extracted, 4 logical figures; images dumped consecutively; captions detached | Reader can't connect figure ↔ caption; DOCX shows all images at page-6 end |
| 6 | Figures without metadata | DOCX projection | 4 images all `descr=""` | Accessibility failure class; reviewer writes 4 alt texts from scratch |
| 7 | Box 3.2 sub-headers | Heading detection on garbled OCR text | Promoted to H2 | Wrong hierarchy in the remediated doc |
| 8 | Page numbers "3" etc. | `page_markers.py` | 13 H6 `###### N` headings | Parity noise vs Mathpix path (deliberate feature, not a defect) |
| 9 | Whole document | Verification engine | 0 findings, 0 corrections — `import_provider=None` skips cross-source verifiers; structural collections empty | Reviewer gets no safety net |
| 10 | Whole document | OCR confidence model | `medium` confidence while text garbled | No escalation or validation can ever fire |

**Reading the map:** [INF]
- Rows 2–4 are **recognizer-quality** losses.
- Rows 5–6 are **figure/caption assembly** losses.
- Rows 7–8 are **semantic/parity** issues.
- Rows 9–10 are **governance** losses — nothing detected the garbage.

**Which stage caused the loss:** extraction is fine (router correct); **OCR is the bottleneck** (rows 2–4); semantic classification degraded by bad OCR input (row 7); projection lost figure/caption assembly (rows 5–6); governance had no signal to act on (rows 9–10).

**Prevented with better evidence?** Rows 2–4: yes — a better recognizer on the render. Rows 5–6: yes — cross-source figure/caption evidence (the Mathpix path proves RAWRS can consume it). Rows 9–10: yes — quality-gated escalation and un-gated verification. [INF]

---

## 4. Why PDF-only processing loses quality (the actual bottleneck)

**The bottleneck is not extraction, layout, or projection. It is the recognizer — and the policies that never give the stronger recognizer a chance.** [INF, grounded in probes]

What information each source actually provides: [CODE]

- **A. PDF text extraction** — empty here. When present it is trustworthy but unstyled; when absent, nothing.
- **B. PDF geometry/layout** — strong (bboxes, drawings, images, fonts via PyMuPDF), but on this document it was only used for routing and caption proximity. The 4 figures on page 6 were still assembled wrong.
- **C. OCR** — the weak link. Measured failure on emphasized runs at every DPI.
- **D. Docling layout** — ran correctly; produced reading order and page labels; assigned `medium` confidence.
- **E. Mathpix MMD (when supplied)** — proves a better recognizer exists: bold bullets, figure crops with captions, math spans. It also proves the verification engine can exploit a second source (that's exactly the Mathpix path's design).
- **F. Page rendering** — available at any DPI via PyMuPDF; RAWRS already renders at 150 DPI for Surya. Everything a modern recognizer needs is one function call away.
- **G. Verification** — the engine itself is path-agnostic (`src/verification/engine.py`), but **the verifiers gate on `Document.import_provider` and skip when it is None.** The cheapest gap in the whole system to close.

**The gap is not "RAWRS can't OCR."** RAWRS *can* — Surya-2 read this document perfectly in-house. The gap is that the strong recognizer is gated behind an empty-page-only escalation policy, and no governance layer noticed the weak one failing. [INF]

---

## 5. Scanned vs born-digital: why the distinction is insufficient

The current mental model: born-digital → native extraction; scanned → OCR. This document breaks it: **born-digital in provenance, scan-like in behavior.** [SUPPLIED + INF]

- **Render-based evidence, not provenance, predicts quality.** The probe proves the recognizer, not the resolution and not the provenance, is what failed (identical garble at 150/300/400 DPI; perfect read by a different model on the same pixels).
- **VLM recognizers don't care how the page was produced.** Mathpix never saw the PDF internals — it rendered and read, like the 2026 VLM class (GLM-OCR, PaddleOCR-VL, TeleOCR, OvisOCR2).
- **The router's two tests are necessary but not sufficient.** `text < 20 chars` and `>10% control/U+FFFD chars` catch empty and control-garbled pages. They cannot catch recognizer-limited pages whose OCR confidently produces plausible-looking garbage.
- **Per-page routing is the right granularity** — `route_pages` is already per-page; the classification axis is just too coarse.

The replacement question is not "scanned or born-digital?" but **"how confident is the evidence that the recognized text is correct?"** — measurable via render-based self-checks, cross-engine disagreement, and native-text cross-checks when a text layer exists. [INF]

---

## 6. Current 2026 model/tool landscape

Full detail in `docs/OCR_MATHPIX_REPLACEMENT_RESEARCH.md` §2–3. Summary: [EXT]

Five free models ≤ 1.2B parameters now beat every frontier model and Mathpix-class services on OmniDocBench v1.6: **TeleOCR 96.91, OvisOCR2 96.47, PaddleOCR-VL-1.6 96.34, MinerU2.5-Pro 95.75, GLM-OCR 95.22** — vs Gemini 3 Pro 92.91, GPT-5.2 86.59. Mathpix on the formula-recognition subset (v1.0 eval): CDM 86.6, ExpRate@CDM 2.8%. Small specialized document models are the entire story of 2026.

---

## 7. Candidate comparison

| Model | Params | License | OmniDocBench v1.6 overall | Formula CDM | CPU path | RAWRS integration shape |
|---|---|---|---|---|---|---|
| **GLM-OCR** | 0.9B | **MIT** | 95.22 | 97.18 | Ollama (`glm-ocr:q8_0`, 1.6 GB) | New Ollama-backed engine module, mirroring `src/ai/providers/ollama.py` |
| PaddleOCR-VL-1.6 | 0.9B | Apache-2.0 | 96.34 | 97.53 | Official GGUF + official x64-CPU tutorial | More moving parts (PP-DocLayoutV3 stage outside llama.cpp) |
| TeleOCR | 1.2B | Apache-2.0 | 96.91 | 96.59 | Community GGUF only, very new | Watchlist |
| OvisOCR2 | 0.8B | Apache-2.0 | 96.47 | 97.49 | GGUF status unconfirmed | Watchlist |
| Surya-2 (installed) | VLM | Weights: modified OpenRAIL-M ≤$5M revenue/funding; code Apache-2.0 | n/a | n/a | llama.cpp (already working) | Current fallback; 347.7 s/page measured |
| RapidOCR PP-OCRv6 (installed) | small | Apache-2.0 | n/a | n/a | onnxruntime CPU (already working) | Current primary; proven insufficient on emphasized runs |
| Mathpix (cloud) | — | proprietary SaaS | v1.0 formula subset: CDM 86.6, ExpRate@CDM 2.8% | 86.6 | cloud API | Current premium path; wins today on speed + figure cropping |

**The decisive row:** GLM-OCR is the only candidate that is simultaneously high-benchmark, MIT-licensed, 0.9B, and served by a runtime already installed and running on this machine (Ollama, port 11434, verified listening 2026-10-05). [EXT + INF]

**Benchmark caveat, kept deliberately and not silently resolved:** Mathpix's 86.6 formula CDM comes from the v1.0 formula subset; the open models' 96.5–97.5 comes from v1.6 end-to-end. The comparison is directional, not apples-to-apples — but every model above Mathpix on the same v1.6 table is free. [EXT]

**GLM-OCR scoring note:** its own model card headlines **94.62 on OmniDocBench v1.5** (#1 overall at release); **95.22 is its v1.6 leaderboard entry**. Both figures are cited where used; they are not silently merged. Also noted for integration planning: GLM-OCR's full pipeline integrates PP-DocLayoutV3 for layout analysis, which is **separately licensed** from the MIT model weights — verify before redistribution. [EXT, verified against the official model card and Ollama library page 2026-10-05]

---

## 8. Licensing / commercial-use analysis

**Models RAWRS already ships:** [EXT]

- **Surya-2 weights: modified OpenRAIL-M** — free only for research/personal use or entities ≤ $5M revenue **and** funding; code Apache-2.0. **RAWRS's current fallback engine carries a commercial restriction.**
- **RapidOCR / PP-OCRv6: Apache-2.0** — clean.
- **PyMuPDF: AGPL-3.0** (or paid Artifex license) — already documented in README.
- **Pandoc (pypandoc-binary wheel): GPL-2** — already documented in `docs/STATUS_REPORT_2026-09-30.md` §7.
- **qwen2.5vl:3b: Qwen Research license** — alt-text only; non-commercial/revenue-capped; already documented.

**Candidates:** [EXT]

- **GLM-OCR: MIT** — cleanest possible.
- **PaddleOCR-VL-1.6: Apache-2.0** — clean.
- **Granite-Docling-258M: Apache-2.0** — clean (ideal CPU size, integrated into Docling, equation-enhanced).
- Ruled out: Chandra OCR 2 (OpenRAIL-M ≤$2M), MinerU pipeline (AGPL history + additional terms; the 2.5-Pro *weights* alone are cleaner), olmOCR 2 (Apache but 7B — CPU-infeasible), HunyuanOCR (no EU/UK/South Korea rights).

**What this means:** WinVinaya Foundation's commercial status is TBD, so the ≤$5M cap may be acceptable *today* — but the fallback engine's license is a documented commercial risk while better-scoring MIT/Apache alternatives exist. [INF]

---

## 9. CPU/runtime analysis

| Engine | Measured / estimated | Evidence |
|---|---|---|
| RapidOCR PP-OCRv6 (current primary) | ~16 s/page end-to-end (whole job: 213 s / 13 pages) | [SUPPLIED] |
| Surya-2 via llama.cpp (current fallback) | **347.7 s/page** (probe; predictor ready ~2 s) | [SUPPLIED, probe] |
| qwen2.5vl:3b alt text (Ollama) | ~2.5 min/image | [EXT, README] |
| GLM-OCR q8_0 via Ollama | est. tens of seconds/page — **to be measured** (Experiment 2) | [INF] |
| Granite-Docling-258M | 258M params; expected far lighter than Surya-2 — **to be measured** (Experiment 3) | [EXT + INF] |

Granite-Docling-258M (Apache-2.0, integrated into Docling, equation-enhanced, on Ollama as `ibm/granite-docling`) is the ideal CPU-size complement. [EXT]

---

## 10. Router / evidence-fusion architecture

**Evidence-fusion is the right architecture — and RAWRS already has roughly 70% of it.** [INF]

Already built: per-page routing (`route_pages`), per-page provenance fields (the document JSON proves `extraction_method`, `routing_decision`, `ocr_confidence`, `page_label`, `printed_label` are all populated), a path-agnostic verification engine, Mathpix import as a provider, placeholder alt-text infrastructure, H6 page markers, and a full reviewer rail.

Missing: **(a)** render-based routing signals, **(b)** quality-gated escalation, **(c)** a second evidence source on poor-quality pages, **(d)** a fusion rule, **(e)** verifier gating fixed for the PDF-only path.

### 10.1 Target state

```
PDF
 ↓
PDF characterization            (exists: text-layer stats, fonts, drawings, images)
 ↓
render-based quality signals    (NEW: recognize the render, then self-check)
   ├─ native-text cross-check   (when a text layer exists)
   ├─ two-engine disagreement   (RapidOCR vs Surya/GLM on the same render)
   └─ garble heuristics         (fragments, dictionary hit rate, glyph-census anomalies)
 ↓
routing decision (per page):    native | Docling+RapidOCR | VLM (GLM-OCR / Surya-2) | specialized (formulas/tables)
 ↓
evidence fusion                 (NEW: engines agree → accept; disagree → record a finding)
 ↓
canonical structure             (Document model — unchanged)
 ↓
verification                    (verifiers no longer skip when import_provider is None)
 ↑
reviewer rail                   (unchanged)
```

### 10.2 Components mapped to the current codebase

| Component | Current state [CODE] | Gap |
|---|---|---|
| PDF characterization | `route_pages` text-length + control-char tests | render-based quality signals |
| Native evidence | `src/ocr/extractor.py` | unchanged |
| Docling+RapidOCR evidence | running today | unchanged as primary |
| VLM evidence (Surya-2) | escalation fires only on Docling-empty pages (`src/ocr/surya_engine.py` candidate filter) | quality-gated escalation; GLM-OCR as the fast VLM |
| Specialized evidence | Docling `do_formula_enrichment` flag exists, off by default; `src/ocr/targeted.py` has a reusable `ocr_region(bbox)` pattern | consider enabling; region-level re-recognition for suspect regions |
| Fusion | none | agree→accept / disagree→finding rule |
| Verification gating | verifiers skip when `import_provider is None` | PDF-only checks that need no second *source*: self-consistency, layout plausibility, glyph census, confidence-faithfulness |
| Reviewer rail | complete | unchanged |

**Explicitly NOT proposed:** agent swarms, cloud dependency, databases, vector DBs, microservices, a giant VLM on every page, frontend/backend replacement, pipeline rewrite. [INF]

---

## 11. Mathpix replacement assessment (honest)

**Can RAWRS replace Mathpix today? Substantially yes — with two named gaps.** [INF]

**What open models win:**
- Benchmark accuracy (§7) — the equation moat is gone.
- Zero cost, zero data egress, unattended batch (job queue + progress UI already exist).
- The verification layer RAWRS adds on top: model output treated as verifiable evidence, never canonical truth. Mathpix output has never been cross-checked against the PDF; RAWRS's engine does exactly that on the Mathpix path today.

**What Mathpix still wins:**
- **Speed:** ~1–3 s/page cloud vs tens of seconds local CPU VLM.
- **Figure cropping:** bbox crops from page renders with captions attached — a genuine differentiator no open candidate matches today (dots.mocr's SVG figure reconstruction is the direction to watch).

**Named gaps after any replacement:** speed on difficult pages, and figure cropping.

**Engine verdicts:**
- **Surya-2 as replacement: qualified no.** Reads this document perfectly, but 347.7 s/page on CPU plus the OpenRAIL-M weights license. Stays as last-resort fallback under the documented license caveat.
- **GLM-OCR as the practical primary** for difficult pages: MIT, 0.9B, Ollama-served, 95.22 v1.6 / 97.18 formula CDM.
- **Granite-Docling-258M as the CPU-safest complement** (Apache-2.0, 258M, equation-enhanced).

**Reframe:** Mathpix's real remaining value is *speed* and *figure cropping*, not recognition quality. The replacement is therefore not like-for-like: RAWRS gains accuracy, auditability and independence; it accepts slower pages and a figure-cropping gap. [INF]

---

## 12. RAWRS-specific benchmark design

**Winner metric: human remediation minutes per 100 pages** — consistent with RAWRS's stated philosophy (README: "optimises for human minutes per 100 pages"). [INF]

### 12.1 Metric components

Per-document minutes, decomposed into:
1. **Retyping/fixing** — garbled text the reviewer must restore from the PDF (O'Leary's bold bullets are the exemplar).
2. **Alt text** — writing alt text for figures shipped with `descr=""`.
3. **Caption/image reassembly** — reattaching captions, reordering dumped images.
4. **Structure fixes** — wrong heading levels, lost hierarchies.

Instrumentation: the reviewer workspace already tracks per-object review actions; extend to timestamp fix-up actions beyond the rail (small task needed before Experiment 6).

**Absolute failure criterion (any arm):** silently dropping glyphs (✓) or garbling emphasized runs *without producing a finding* fails the arm regardless of minutes. Silent defects are worse than slow defects.

### 12.2 Comparison arms

(a) Current PDF-only path (the real O'Leary remediation already done provides ground truth for this arm) · (b) current + Experiment-1 knobs · (c) current + VLM escalation (Exp 2/3 engines) · (d) same as (c) + evidence fusion (Exp 5) · plus the Mathpix-assisted path as reference.

### 12.3 Why not OmniDocBench as the winner metric

OmniDocBench selects *models*; it cannot measure figure-crop attach rate, alt-text fill rate, or human minutes. It got us to GLM-OCR; it cannot pick the system configuration. The outcome of the minutes benchmark — not leaderboard claims — decides escalation thresholds, garble-heuristic tuning, and whether figure-cropping is worth building. [INF]

---

## 13. Recommended experiments

Six experiments, ordered; each is a spike/measure/decision, none changes production code. [INF]

### Experiment 1 — zero/low-code, existing capabilities
- **Objective:** how much of the gap closes with existing knobs?
- **Input:** O'Leary PDF.
- **Change under test:** Docling `do_formula_enrichment=True`; render/raster at 300–400 DPI; **escalate `medium`-confidence pages to Surya-2** (the probe already proved Surya-2 reads this document perfectly — this is a config-level change to the escalation filter in `src/ocr/surya_engine.py`, currently empty-page-only); `PageNumberingPolicy.DISABLED` for a clean A/B against the Mathpix path.
- **Metric:** bold-bullet fidelity vs MMD; ✓ retention; caption/image adjacency; verification findings count > 0.
- **Success:** bold-bullet fidelity ≈ the single-page Surya-2 probe; ≥ 3 findings raised on the garbled text.
- **Failure:** still garbled at 400 DPI → model-limited; go straight to Exp 2.
- **Effort:** config-level, ~half a day.
- **Decision enabled:** knob-tunable gap vs model-limited gap.

### Experiment 1b — PDF-only verification with a safety net
- **Objective:** what does the reviewer see when PDF-only gets cross-checks?
- **Input:** O'Leary + un-gated PDF-only verifiers (self-consistency, layout plausibility, confidence-faithfulness).
- **Metric:** findings raised on garbled text; false-finding rate on good pages.
- **Success:** garble findings fire; acceptable noise. **Failure:** noise overwhelms signal.
- **Effort:** half a day. **Decision enabled:** the shape of un-gated verification.

### Experiment 2 — GLM-OCR integration spike
- **Objective:** quality + speed on this machine.
- **Input:** the 13 O'Leary pages as PNGs, via Ollama's HTTP API. `glm-ocr:q8_0` (1.6 GB) is **already pulled locally** (verified via `ollama list`, 2026-10-05) — no download or approval needed for the spike.
- **Metric:** bold-bullet fidelity; ✓ retention; formula-span fidelity; s/page on this CPU.
- **Success:** bold bullet recovered, ✓ retained, ≤ 60 s/page → primary for difficult pages.
- **Failure:** > 60 s/page or quality below RapidOCR → pivot to Exp 3 candidates.
- **Effort:** 1 day (spike script outside the repo — research-only constraint).
- **Decision enabled:** difficult-page VLM selection.

### Experiment 3 — strongest alternative comparison
- **Objective:** is GLM-OCR right for *this* content, or is the general benchmark ranking wrong for RAWRS's domain?
- **Input:** the 13 pages + a stratified sample of the 10-PDF benchmark corpus (heading/list/table/notes-rich pages).
- **Candidates:** PaddleOCR-VL-1.6 (official GGUF + x64-CPU tutorial) and Granite-Docling-258M (Apache-2.0, 258M, equation-enhanced). Downloads require user approval.
- **Metric:** Exp 2's metrics on the stratified sample.
- **Success:** a candidate beats GLM-OCR on the RAWRS sample at acceptable CPU cost → adopt it; if GLM-OCR holds up → adopt it with confidence.
- **Failure:** nothing beats RapidOCR on the sample → don't add a VLM; invest only in figure/caption assembly + un-gated verification.
- **Effort:** 1–2 days. **Decision enabled:** final difficult-page engine.

### Experiment 4 — born-digital-difficult routing signals ⭐ most important
- **Objective:** detect "recognizer-limited" pages *before* trusting their text — generalizes beyond O'Leary.
- **Signals to test:** [INF, grounded in the probe]
  - **Two-DPI self-consistency** — a correct recognition is DPI-stable; O'Leary's garble was identical at 150/300/400 (stable-but-wrong is itself a signal class to measure).
  - **Two-engine disagreement** — RapidOCR garble vs Surya-2 perfect on the same render; the probe proves disagreement is extreme on this page.
  - **Garble heuristics** — fragment-word ratio, dictionary hit rate, short-word ratio.
  - **Glyph-census anomaly** — the PDF demonstrably draws a ✓; OCR emitted none → suspected drop. (Font/drawing census vs recognition output.)
  - **Native-text-vs-OCR cross-check** where a text layer exists.
- **Output:** thresholds from measured distributions on real pages ("difficult page" = f(signals)).
- **Metric:** detection rate on known-garbled pages at an acceptable false-positive rate on genuinely good pages.
- **Success:** O'Leary pages all flagged; < 5% false flags on the corpus's good pages.
- **Failure:** no signal separates them → simpler policy: escalate *all* `medium`/`low`-confidence pages.
- **Effort:** 2–3 days. **Decision enabled:** the router's second axis — quality-gated escalation on top of the text-length gate.

### Experiment 5 — evidence fusion
- **Objective:** when two recognizers run, what is the fusion rule?
- **Input:** Exp 4's difficult pages, two recognition results each.
- **Rule candidates:** agree→accept / disagree→**finding** (disagreement becomes a reviewer-rail item); prefer-by-domain (emphasized runs → VLM, plain text → RapidOCR, math → formula enrichment or VLM); region-level re-recognition of suspect regions only (reuse `src/ocr/targeted.py`'s `ocr_region(bbox)` pattern).
- **Metric:** post-fusion fidelity vs MMD gold standard; reviewer-agreement precision on disagreement findings.
- **Success:** post-fusion fidelity ≈ Mathpix-class on difficult pages; high finding precision.
- **Effort:** 2–3 days after Exp 4.

### Experiment 6 — end-to-end remediation-minutes benchmark
- **Design:** one reviewer, stopwatch, same corpus, the arms of §12.2. O'Leary is in the corpus.
- **Winner:** fewest minutes with zero silent defects.
- **Prerequisite:** reviewer-minutes instrumentation (§12.1).
- **Decision enabled:** the escalation policy, signal thresholds, and whether figure-cropping is worth building — decided by measured minutes, not leaderboard claims.

---

## 14. Recommended architecture

**The smallest architecture that materially improves RAWRS — five changes, no rewrite:** [INF]

1. **Quality-gated escalation** — escalate `medium`/`low`-confidence pages to the VLM, not only empty pages. One filter change in `src/ocr/surya_engine.py`'s candidate filter; later, GLM-OCR as the fast VLM.
2. **Render-based routing signals** (Exp 4) — two-DPI self-consistency, two-engine disagreement, garble heuristics, glyph census — added to the router as *measured* thresholds.
3. **One new engine module** — Ollama-backed VLM engine (GLM-OCR first), mirroring `src/ai/providers/ollama.py`; new `route_to_vlm` value alongside `route_to_docling`/`route_to_surya` in the page model.
4. **Fusion + disagreement-as-finding** — engines agree → accept; disagree → record. The reviewer rail already exists to display it.
5. **Un-gate PDF-only verification** — verifiers that need no second *source*: self-consistency, layout plausibility, glyph census, confidence-faithfulness. `import_provider is None` must never mean "no verification."

**Flow:** PDF → characterization → render-based signals → per-page routing → fusion → Document model → verification (un-gated) → reviewer → Markdown/DOCX. Consistent with RAWRS's principle: *evidence proposes, rules validate, reviewer decides, projection proves.* [INF]

---

## 15. Risks and unknowns

Known unknowns, listed honestly: [INF]

- **Will GLM-OCR recover the bold bullet?** Likely (VLM-class behavior + benchmark scores) but unmeasured until Exp 2.
- **GLM-OCR q8_0 wall-clock on this CPU** — est. tens of seconds/page; unmeasured until Exp 2.
- **Granite-Docling-258M on CPU** — expected far lighter than Surya-2's 347.7 s/page; unmeasured until Exp 3.
- **Benchmark saturation + odd PDFs:** OmniDocBench is saturated (LlamaIndex analysis, 2026-02-24) and O'Leary is an unusual PDF. Benchmarks don't predict this document; only Exp 4's measured thresholds on the real corpus decide routing.
- **Reviewer-minutes instrumentation** doesn't exist yet; small task required before Exp 6.
- **Figure-cropping parity** — no open candidate matches Mathpix's bbox crops with captions; open after any replacement.
- **Region-level fusion** — a page can be garbled in places and fine elsewhere; region-level fusion (reusing `ocr_region(bbox)`) is future work after page-level fusion works.
- **Prevalence:** "Print To PDF" of any ebook chapter reproduces this failure class — likely more common in the wild than good-quality true scans. [INF]

**Risks:** false-positive escalation to a slow VLM hurts wall-clock; mitigated by letting the minutes benchmark (Exp 6) set thresholds, and by the Surya-2 weights license (§8) which makes GLM-OCR/Granite-Docling the strategically safer VLMs. [INF]

---

## 16. Final recommendation

1. **Keep scanned/born-digital as provenance metadata, not as the routing axis.** Route by measured, render-based quality signals (Exp 4).
2. **Order of attack:** Exp 1 first (config-level, half a day) → Exp 4 (most important) → Exp 2 (GLM-OCR spike) → 3, 5, 6.
3. **Adopt GLM-OCR (MIT, 0.9B, Ollama) as the difficult-page VLM** if Exp 2 confirms bold-bullet recovery at ≤ 60 s/page. Granite-Docling-258M as CPU-safest complement. Surya-2 stays last-resort, OpenRAIL-M weights caveat documented.
4. **Un-gate PDF-only verification** — the cheapest governance fix in the system (§14, item 5).
5. **Human remediation minutes per 100 pages, with zero silent defects, is the winner metric** (§12). OmniDocBench selects models; minutes select systems.
6. **Keep the Mathpix import path.** It is built, it is the gold-standard comparison, and it still wins on speed and figure cropping. The goal is not to delete it — the goal is that the PDF-only path no longer *needs* it to be good.
7. **Do not silently resolve** the v1.0/v1.6 benchmark caveat (§7) or the licensing status quo (§8) — surface both as recorded caveats to the reviewer/company.

**One-sentence answer to the research question:** *Route pages by measured, render-based quality signals rather than scanned-vs-born-digital provenance; escalate poor-quality pages to a strong local VLM (GLM-OCR via Ollama being the best current fit); fuse evidence when recognizers disagree and record the disagreement as a finding; un-gate verification on the PDF-only path — and judge success by human remediation minutes per 100 pages with zero silent defects.* [INF]

---

*Probes (PDF characterization, DPI sweep, Surya-2 timing) were run 2026-10-04/05 with libraries already in `.venv`; probe scripts were ad hoc and deliberately not saved to the repo (research-only constraint). No code, dependencies, or repo files were changed beyond this report and its companion `docs/OCR_MATHPIX_REPLACEMENT_RESEARCH.md`.*

*Sources: supplied artifacts and probes [SUPPLIED]; RAWRS source [CODE] (`src/ocr/router.py`, `src/ocr/docling_config.py`, `src/ocr/surya_engine.py`, `src/ocr/targeted.py`, `src/pipeline/phase1_pipeline.py`, `src/verification/engine.py`, `src/headings/page_markers.py`, `src/images/image_extractor.py`, `src/markdown/markdown_builder.py`); external research [EXT] (details in companion doc §6); inference [INF].*
