# Licence audit (2026-11-01)

Not legal advice. Every licence below was read at its source on 2026-11-01. Installed versions come from `.venv` metadata (133 Python packages) and `frontend/node_modules` (720 packages).

## Read this first

| | Component | Licence | Blocks selling RAWRS? |
|---|---|---|---|
| 1 | `qwen2.5vl:3b` (alt text) | Qwen **Research** Licence: "FOR NON-COMMERCIAL PURPOSES ONLY" | **Yes**, any commercial use |
| 2 | Surya OCR weights `datalab-to/surya-ocr-2` (fallback OCR) | modified AI Pubs OpenRAIL-M | **Yes**, above $5M revenue or funding, **and** for any service that competes with Datalab's |
| 3 | PyMuPDF 1.28.0 (PDF reading, 26 source files) | AGPL-3.0 or a paid Artifex licence | **Yes**, unless RAWRS's own source is offered to every user under AGPL |
| 4 | pandoc in `pypandoc-binary` (equations) | GPL-2.0-or-later, run as a separate program | No for a hosted service; shipping an image means also offering pandoc's source |
| — | The RAWRS repository itself | **no LICENSE file** | Public but "all rights reserved"; it must get a licence before point 3 can be settled |

Everything else is permissive (MIT, BSD, Apache-2.0, ISC, HPND, CDLA-Permissive-2.0) or file-level copyleft (MPL-2.0) that asks nothing of unmodified use.

## Restrictive components

| Component | Exact licence (source) | What it blocks | Permissive replacement or paid route | Swap effort |
|---|---|---|---|---|
| `qwen2.5vl:3b` via Ollama, `src/ai/providers/ollama.py` | Qwen Research Licence Agreement, §2(a) "non-commercial purposes only", §1(i) "research or evaluation purposes only" ([LICENSE](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct/blob/main/LICENSE)) | All commercial use, hosted or on-premises | `qwen3-vl:4b` Apache-2.0 ([card](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct)); `granite3.2-vision:2b` Apache-2.0 ([card](https://huggingface.co/ibm-granite/granite-vision-3.2-2b)); `qwen2.5vl:7b` Apache-2.0 ([card](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct)) | Configuration: `RAWRS_OLLAMA_MODEL` and the default in `ollama.py`. Hours. See the measured comparison below |
| Surya 0.20.0 weights `surya-ocr-2(-gguf)`: `src/ocr/surya_engine.py` (fallback for pages Docling leaves empty), `src/ocr/targeted.py` (heading region OCR) | Code: Apache-2.0 (package metadata). Weights: "modified AI Pubs Open Rail-M", free only for "research, personal use, and startups under $5M funding/revenue" ([card](https://huggingface.co/datalab-to/surya-ocr-2-gguf)). [MODEL_LICENSE](https://github.com/datalab-to/surya/blob/master/MODEL_LICENSE) Att. A §2(c): no use in a product or service "that competes with any product or service … offered by Licensor" | Datalab sells PDF-to-document conversion, so a paid PDF remediation service plausibly competes **at any revenue**. Also breaks if WinVinaya or a self-hosting customer is over $5M | GLM-OCR `glm-ocr:q8_0`, MIT ([card](https://huggingface.co/zai-org/GLM-OCR)), already used by `src/ocr/reread.py`; Tesseract 5, Apache-2.0 ([LICENSE](https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE)). Paid: Datalab licence ([pricing](https://www.datalab.to/pricing)), no public price | Small: 3 files (`surya_engine.py`, `surya_config.py`, `targeted.py`) and their tests. Days |
| PyMuPDF 1.28.0 (`fitz`): about 80 call sites in 26 `src` files, and 31 test files; `get_text("dict"/"rawdict")` span fonts and flags, `get_pixmap`, `get_drawings`, `extract_image` | "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License" (package metadata). Artifex: you cannot deploy it in a server-based service "without disclosing your own application's full source code under AGPL to any users interacting with it" ([licensing](https://artifex.com/licensing)) | A closed-source hosted or shipped RAWRS | (a) License RAWRS under AGPL-3.0 and link users to the source: **zero cost**, but anyone may run a competing copy. (b) Artifex commercial licence: "crafted based on your individual use case", no public price; a third-party blog's $10k–50k/yr is **unverified**. (c) Rewrite on `pypdfium2` (Apache-2.0/BSD-3, already installed via Surya and Docling) for rendering, images and chars, plus `pdfplumber`/`pdfminer.six` (MIT, new) for span fonts and vector lines | (a) a LICENSE file and a source link in the UI: a day. (b) a sales call. (c) **weeks**: span-level font flags drive headings, footnotes, tables and lists, so every structure stage would need the corpus regression diff again |
| pandoc 3.x inside `pypandoc-binary` 1.17, `src/equations/` | GPL-2.0-or-later ([COPYRIGHT](https://github.com/jgm/pandoc/blob/main/COPYRIGHT)); called as a separate executable | Nothing for a hosted service. Distributing a Docker image or installer means shipping or offering pandoc's source | None needed. `latex2mathml` (MIT) plus an OMML stylesheet is possible, but Microsoft's `MML2OMML.XSL` is not redistributable | — |

## Checked and clear

| Group | Licences |
|---|---|
| Docling 2.87 + core/parse/ibm-models | MIT; layout model `docling-layout-heron` Apache-2.0 ([card](https://huggingface.co/docling-project/docling-layout-heron)); TableFormer `docling-models` CDLA-Permissive-2.0 / Apache-2.0 ([card](https://huggingface.co/docling-project/docling-models)) |
| RapidOCR 3.9 + PP-OCRv6 ONNX models, onnxruntime | Apache-2.0, MIT |
| GLM-OCR weights, Ollama, llama.cpp | MIT |
| torch, transformers, qwen-vl-utils, opencv, pypdfium2 (+PDFium) | BSD-3, Apache-2.0 |
| saxonche 13 (via docling-core → doclang), certifi, tqdm | MPL-2.0 (file-level; saxonche's own wheel declares no licence, so Saxonica's [conditions](https://www.saxonica.com/html/documentation10/conditions) page is the source) |
| Frontend (Next, React, react-pdf/pdf.js, mammoth, CodeMirror) | MIT, Apache-2.0, BSD; `sharp`'s libvips is LGPL-3.0 (dynamically linked, fine); `jszip` is "MIT OR GPL-3.0" (take MIT) |

## Measured comparison (Codespace, 4 vCPU AMD EPYC 7763, 16 GB, CPU only)

All scores are **estimates**: similarity to an independent human-remediated DOCX, not reviewer behaviour. They are floored to one decimal place. Script: `scripts/licence_bench.py`. OCR cache off.

### OCR (word 4-gram recall / precision against the human-remediated text)

| Engine (licence) | O'Leary, 13 scanned pages | Bryman, 26 pages | Seconds per page |
|---|---|---|---|
| Docling + RapidOCR (MIT / Apache-2.0), **current primary** | 95.4% / 96.4% | 96.1% / 97.5% | 11.7 / 10.6 |
| Surya (weights OpenRAIL-M), **current fallback** | 98.5% / 96.8% | not run (≈1.6 h on CPU) | 224.5 / — |
| Tesseract 5.3 (Apache-2.0) | 92.5% / 89.2% | 91.6% / 90.9% | 2.6 / 3.5 |
| GLM-OCR full page (MIT) | not workable: ≥ 6 min 33 s per page | not run | ≥ 393 |

- Docling left **0 pages empty** in both documents, so on this corpus the Surya fallback never fires in production. Surya's higher score on O'Leary is what it would add *if* it ran on every page; in RAWRS it only runs on pages Docling leaves empty.
- GLM-OCR on a whole 200 DPI page uses about 4,048 of Ollama's default 4,096 tokens of context for the image alone. With `num_ctx` raised to 16,384, one page still took more than 9 minutes. GLM-OCR stays workable on the small region crops `src/ocr/reread.py` already sends it.
- n = 2 documents and 39 pages. These are both scanned books from one corpus, so they say nothing about other layouts or languages.

### Alt text (10 human-described figures from 4 remediated DOCX files)

Each model gets RAWRS's production prompt and parser (`src/ai/providers/qwen.py`), and production's 900 s limit (`_GENERATE_TIMEOUT_SECONDS`). A reply that times out or can't be parsed is a failure and scores 0. "Overlap" is content-word recall and precision against the human alt text. That is a rough proxy: it rewards using the same words, not getting the meaning right.

| Model (licence) | Usable replies | Overlap recall / precision | Median s per figure (max) | Loaded size |
|---|---|---|---|---|
| `qwen2.5vl:3b` (Qwen Research, **non-commercial**), **current** | 10/10 | 37.6% / 48.6% | 111.0 (318) | 2.8 GB |
| `qwen2.5vl:7b` (Apache-2.0) | **10/10** | **48.1% / 55.3%** | 208.7 (634) | 5.7 GB |
| `qwen3-vl:4b` (Apache-2.0) | 9/10 (1 empty reply) | 47.6% / 44.3% | 371.1 (636) | 3.6 GB |
| `granite3.2-vision:2b` (Apache-2.0) | 8/10 (2 over 900 s) | 33.1% / 24.7% | 455.3 (900) | 3.1 GB |

- `qwen3-vl:4b` is a thinking model, and Ollama turns thinking on by default (`ollama show`: thinking default `true`). RAWRS's provider doesn't send `think: false`. That probably explains both its slow median and the empty reply, where the thinking used up the 4,096-token context. **Not tested:** a run with `think: false`.
- `qwen2.5vl:7b` scores best on both measures with no failures. The cost is about twice the time and twice the memory. RAWRS's provider notes an 8 GB reference machine, and 5.7 GB loaded has **not** been tried there.
- n = 10 figures from 4 documents, all academic books (charts, diagrams, one book cover). One run, temperature 0, CPU only.

## Recommended swap order

| # | Swap | Why first | Effort | Evidence |
|---|---|---|---|---|
| 1 | `qwen2.5vl:3b` → `qwen2.5vl:7b` (default in `src/ai/providers/ollama.py`, or `RAWRS_OLLAMA_MODEL`) | It blocks **all** commercial use today, and the replacement measured better | Hours: one constant, plus a note on memory | Overlap 37.6→48.1% recall, 48.6→55.3% precision; median 111→209 s per figure. Fallback for 8 GB machines: `qwen3-vl:4b` with `think: false` (to test first) |
| 2 | Surya → Docling-only, or Tesseract for pages Docling leaves empty; GLM-OCR for heading region OCR (`src/ocr/targeted.py`, the same calls `reread.py` already makes) | Blocks companies over $5M and plausibly any competing service. On this corpus it never runs, because Docling left 0 pages empty | Days: `surya_engine.py`, `surya_config.py`, `targeted.py` and their tests; then re-run the corpus heading diff | Tesseract 92.5/89.2% (O'Leary) and 91.6/90.9% (Bryman), 2.6–3.5 s per page, against Surya's 98.5/96.8% at 224.5 s per page. The lower quality only matters on pages Docling can't read |
| 3 | PyMuPDF: a **business decision**, not an engineering one | AGPL forces RAWRS's own source open for every user of a hosted service | (a) AGPL-license RAWRS: a day. (b) Artifex quote: a sales call. (c) Rewrite on `pypdfium2` + `pdfplumber`: weeks | No measurement possible until (a), (b) or (c) is chosen. Choose before any paid pilot |
| — | pandoc | Nothing to swap for a hosted service | — | — |

The repository needs a LICENSE file in every case. Which one depends on decision 3.
