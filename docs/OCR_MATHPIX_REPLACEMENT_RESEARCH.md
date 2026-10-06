# OCR Research: Replacing Mathpix with Free Models (2026-10-02)

Research-only document — no code was changed. Question asked: *what is the world's best
free OCR model (or combination) that fits RAWRS, could entirely replace the Mathpix MMD
package, and is faster and more precise than Mathpix?*

Short answer: **yes, Mathpix can be replaced today, entirely, for free, by small open
models that now outscore it on the standard benchmark — and the best fit for this
machine is GLM-OCR (0.9B, MIT) served through the Ollama RAWRS already runs.**

---

## 1. What RAWRS actually needs (grounding)

Current architecture (from `src/pipeline/phase1_pipeline.py`, `src/ocr/*`,
`src/mathpix/*`):

- **Born-digital PDFs** → Docling 2.87 layout + PDF text layer + RapidOCR (PP-OCRv6,
  ONNX, CPU) — no cloud, already fast. No Mathpix involvement.
- **Scanned pages** → Docling, then Surya-2 (VLM via llama.cpp, `surya-2.gguf` 1.27 GB)
  fallback (`src/ocr/surya_engine.py`, DECISIONS_LOG line 121).
- **Mathpix MMD package (optional, user-supplied)** → imported by
  `src/mathpix/ingestor.py` as the *canonical* text (headings, tables, equations in
  LaTeX, footnotes); the PDF then *verifies* it (`src/verification/*`).
- **Deployment**: Windows, **CPU-only** (`torch.cuda.is_available() == False`, no
  NVIDIA GPU), Ollama with `qwen2.5vl:3b` for alt-text/tables, llama.cpp
  (`llama-server`) already installed for Surya-2.

So "replace Mathpix" concretely means: **a local model that turns a scanned page into
structured Markdown with equations in LaTeX and tables in HTML, of quality good enough
to be the canonical text the verification engine cross-checks against the PDF.**

---

## 2. The benchmark picture (OmniDocBench v1.6, leaderboard updated 2026-09-11)

OmniDocBench (OpenDataLab, CVPR 2025) is the standard document-parsing benchmark:
1,651 pages (papers, textbooks, exams, reports, newspapers, handwritten notes);
**Overall = mean of text accuracy, table TEDS, and formula CDM** — i.e. math formulas
carry one third of the score. Mathpix itself was evaluated on it (2026-03-31 update).

End-to-end leaderboard (v1.6_full), excerpt:

| Model | Size | License | Overall↑ | Formula CDM↑ | Table TEDS↑ | Notes |
|---|---|---|---|---|---|---|
| TeleOCR | 1.2B | Apache-2.0 | **96.91** | 96.59 | **96.82** | Aug 2026; robust to photographed/curved pages |
| OvisOCR2 | 0.8B | Apache-2.0 | 96.47 | 97.49 | 94.58 | best text edit distance (0.0265) |
| PaddleOCR-VL-1.6 | 0.9B | Apache-2.0 | 96.34 | **97.53** | 94.76 | 111 languages; official CPU/llama.cpp path |
| MinerU2.5-Pro | 1.2B | Apache-2.0 (weights, extra terms) | 95.75 | 97.45 | 93.42 | full framework around the VLM |
| GLM-OCR | 0.9B | **MIT** | 95.22 (v1.6) | 97.18 | 92.83 | in Ollama's official library; v1.5 leaderboard headline is **94.62** (see note) |
| Gemini 3 Pro | API | closed | 92.91 | 95.99 | 89.15 | frontier, paid |
| Qwen3-VL-235B | 235B | Apache-2.0 | 89.78 | 92.55 | 83.07 | general VLM, huge |
| GPT-5.2 | API | closed | 86.59 | 88.21 | 82.95 | frontier, paid |
| olmOCR 2 | 7B | Apache-2.0 | 85.74 | 88.10 | 83.00 | too heavy for this CPU box |
| DeepSeek-OCR 2 | 3B | Apache-2.0 | 90.25 | 91.84 | 83.89 | |
| Marker | pipeline | GPL/commercial | 78.44 | 85.24 | 65.77 | Datalab |

**The headline: five free models ≤ 1.2 B parameters now beat every frontier model and
Mathpix-class solutions.** Small specialized models are the whole story of 2026.

> **GLM-OCR scoring note (verified against the HF model card and leaderboard sources,
> 2026-10-05):** two figures circulate and must not be merged. **94.62 overall** is
> GLM-OCR's headline on its own model card, from the **OmniDocBench v1.5** evaluation;
> **95.22 overall / 97.18 formula CDM / 92.83 table TEDS** is its **v1.6** leaderboard
> entry (leaderboard updated 2026-09-11). Both are correct; they belong to different
> benchmark versions. Separately: GLM-OCR's MIT licence covers the **model weights**;
> its layout component (PP-DocLayoutV3, used in the PaddleOCR-style pipeline) is
> **separately licensed** — verify before commercial use of that specific component.

### Mathpix directly

On the component-level formula-recognition subset (v1.0 eval, the table where Mathpix
appears explicitly): Mathpix scored **CDM 86.6** with **ExpRate@CDM 2.8 %** (i.e. only
~3 % of display formulas exactly right by rendered-equation match) vs UniMERNet-B 85.0
CDM / 60.2 % ExpRate and GPT-4o 86.8 / 65.5 %. The 2026 specialized models post formula
CDM of **96.5–97.5** end-to-end. Mathpix was the 2021–2023 state of the art; the
equation moat is gone. (Caveat kept deliberately: the 86.6 and the 97.5 come from
different dataset versions — but every model above it on the same v1.6 table is free.)

---

## 3. Recommendation for RAWRS

### Primary: **GLM-OCR (0.9B, MIT) via Ollama**

- **Zero new infrastructure**: `ollama pull glm-ocr:q8_0` (1.6 GB) — the exact runtime
  RAWRS already integrates (`src/ai/providers/qwen.py` pattern) and the exact
  llama.cpp-based serving path already used for Surya-2.
- 95.22 overall / 97.18 formula CDM on v1.6 (94.62 on v1.5, the model-card headline) —
  above GPT-5.2, Gemini-class results, and
  Mathpix's published formula numbers; SOTA-class for tables, formulas, code, stamps.
- **MIT license** — cleanest possible for a product; no usage thresholds.
- 0.9B params / 128K context; element-level prompts (`Text Recognition:`,
  `Table Recognition:`, `Figure Recognition:`) plus full-page markdown mode.
- English is supported (8 languages: en/zh/fr/es/ru/de/ja/ko — fine for RAWRS).

### Strong alternate: **PaddleOCR-VL-1.6 (0.9B, Apache-2.0)**

Highest published formula CDM (97.53), 111 languages, and PaddlePaddle ships an
**official GGUF plus an official x64-CPU tutorial** for llama.cpp. Choose this if
non-English/Indic-script documents become common. Caveats: llama.cpp integration is
noted in community docs as "may have degraded performance" vs GLM-OCR, and its
two-stage layout model (PP-DocLayoutV3) sits outside llama.cpp — more moving parts
than GLM-OCR-on-Ollama.

### Watchlist (re-check quarterly)

- **TeleOCR** (1.2B, Apache-2.0) — current #1 (96.91); best on photographed/curved
  pages (87.36 on Wild-OmniDocBench per its card); community GGUF only, very new.
- **OvisOCR2** (0.8B, Apache-2.0) — #2 overall, best text accuracy.
- **dots.mocr** (3B, MIT) — best robustness to phone-photo pages; unique SVG
  reconstruction of figures (interesting for RAWRS figure remediation someday).

### Ruled out for this project

- **Chandra OCR 2** — best on olmOCR-Bench (85.8, great handwriting), but modified
  OpenRAIL-M: free only for research/personal/<$2M revenue *and* funding, no
  competing with Datalab. Legally fragile for a company product.
- **MinerU framework** — AGPL history + "Apache with additional terms" (revenue
  thresholds, must disclose MinerU in online services). The MinerU2.5-Pro *weights*
  alone are cleaner, but the pipeline terms are a footgun.
- **olmOCR 2 (7B)** — Apache-2.0 but 7B: CPU-infeasible here.
- **HunyuanOCR** — license grants no rights in EU/UK/South Korea.
- **qwen2.5vl:3b** (current alt-text model) — keep it for alt-text; its class scores
  far below dedicated doc models on OmniDocBench; do not use it as the OCR engine.

---

## 4. "Faster" — the honest accounting

- **Born-digital PDFs** (most real input): RAWRS's native path is *already* faster than
  Mathpix — text-layer extraction, no OCR, no cloud round trip, no manual step of
  running Mathpix and uploading the .mmd. Replacing Mathpix removes a manual chore.
- **Scanned/math pages on this CPU box**: a 0.9B Q8 VLM generating full-page markdown
  will be **slower per page than Mathpix's cloud API** (est. tens of seconds to minutes
  vs ~1–3 s cloud). It wins on: zero cost, zero data egress, unattended batch (the job
  queue + progress UI already exist), and no per-seat pricing. Two-stage/element-level
  prompting and routing only math/low-confidence pages to the VLM keep wall-clock low.
- **Precision**: top open models beat Mathpix on the benchmark, and RAWRS adds a layer
  Mathpix alone never had — the verification engine cross-checks VLM output against
  the PDF text layer. Nothing "fixes accuracy forever"; the honest claim is: *free
  models are now measurably more accurate than Mathpix at parsing, and RAWRS's
  architecture treats model output as verifiable, not canonical truth.*

## 5. Proposed combination (when implementation is scheduled)

1. `ollama pull glm-ocr:q8_0` — new OCR engine module speaking to Ollama's local HTTP
   API, mirroring `src/ai/providers/qwen.py` (startup resource check + `/api/ai/status`
   reporting, same as FEATURE_012's pattern). *(Status 2026-10-05: the model is already
   pulled locally — 1.6 GB, Ollama official library — so a spike needs no download/approval.)*
2. Router: keep Docling + RapidOCR for plain pages; route pages with detected math /
   low text confidence to GLM-OCR (the `route_to_docling` / `route_to_surya` enum in
   `src/models/page.py` gains `route_to_vlm`).
3. Ingest VLM markdown through a new provider in `src/importers/base.py` ("vlm"),
   mapping headings/tables/equations the way `src/mathpix/ingestor.py` does — the
   verification engine then works unchanged.
4. Cheap immediate experiment (zero code): Docling's built-in
   `do_formula_enrichment=True` (`src/ocr/docling_config.py`) already produces LaTeX
   for detected display equations on born-digital PDFs (IBM's in-house equation model;
   known issue: spacing quirks, docling#2374).

## 6. Sources (checked 2026-10-02)

- OmniDocBench leaderboard & Mathpix eval — github.com/opendatalab/OmniDocBench
- Roboflow, "Best Open-Source OCR Models in 2026" (2026-08-03) — blog.roboflow.com
- Docsumo, "Best OCR Models 2026" (checked 2026-09-29 by its author) — docsumo.com/blog/best-ocr-models
- LlamaIndex, "OmniDocBench is Saturated…" (2026-02-24) — llamaindex.ai/blog
- PaddleOCR-VL-1.6-GGUF (official, 2026-06) & CPU tutorial — huggingface.co / github.com/PaddlePaddle/PaddleOCR
- GLM-OCR — ollama.com/library/glm-ocr, github.com/zai-org/GLM-OCR
- llama.cpp OCR models guide (2026-04-10) — blog.ngxson.com/using-ocr-models-with-llama-cpp
- Datalab "Cracking Math OCR" (2025-09-19) — datalab.to/blog
- RAWRS constraints — DECISIONS_LOG line 121 (CPU-only, Surya-2 via llama.cpp),
  requirements.txt (docling 2.87.0, surya-ocr 0.20.0, PP-OCRv6 via RapidOCR)
