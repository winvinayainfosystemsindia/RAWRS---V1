# RAWRS — Remediation and Accessibility Workflow for Research Sources

RAWRS is a local-first, accessibility remediation platform for academic PDFs. It accepts either a PDF alone or a PDF paired with a Mathpix MMD export, verifies and enriches the extracted content, and produces accessible Word documents (DOCX) and Markdown with a human-review platform for every accessibility-critical decision.

---

## What it does

- **PDF-native path:** Extracts text from born-digital PDFs (PyMuPDF) with OCR fallback (Docling → Surya)
- **Mathpix import path:** Imports a Mathpix MMD file as the primary extraction source; RAWRS provides verification, enrichment, and accessibility output. Every proposed correction is recorded as a `CorrectionRecord` (audit trail) — Mathpix extraction is never silently overwritten.
- Detects headings (H1–H6), footnotes/endnotes, images, tables, and front matter
- Generates structured Markdown and accessible DOCX (Word Heading styles, native table markup, `w:tblHeader`, `dc:language`, `dc:title`, bold/italic inline formatting)
- Validates 29 accessibility and structural rules (WCAG 2.4.2, 3.1.1, H73, etc.)
- Provides a web-based review platform with workspaces for every reviewable object:
  - **Headings** — approve/level-change/reject, screen reader preview
  - **Reading Order** — drag-reorder blocks, approve pages
  - **Images** — on-demand AI alt text (Qwen2.5-VL), approve/reject/decorative/complex/skip/edit
  - **Footnotes** — edit body, approve, reject
  - **Tables** — auto-detect bordered tables, manual create for borderless, edit cells, caption, summary, header rows; WCAG H73 screen reader simulation
  - **Metadata** — set `dc:language`, `dc:title`, `dc:creator`, `dc:subject`

---

## Architecture

**Pipeline (both paths share stages 3–8):**
```
PDF-native:  PDF → extract text → OCR → Document Model → Markdown + DOCX + report
Mathpix:     PDF + MMD → MathpixImportProvider → Document Model → Markdown + DOCX + report
```

`src/pipeline/phase1_pipeline.py` — `run_pipeline(pdf_path, mmd_path=None)`  
`src/importers/` — `ImportProvider` Protocol + `MathpixImportProvider`  
`src/mathpix/mmd_parser.py` — state-machine MMD → intermediate P2Document  
`src/mathpix/ingestor.py` — P2Document → RAWRS Document Model  
`src/models/correction.py` — `CorrectionRecord` audit trail  
`src/api/` — FastAPI HTTP interface (in-memory job tracking)  
`frontend/` — Next.js/React/TypeScript/Tailwind review platform

---

## Quick start

```bash
# Install dependencies
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements-dev.txt

# Run the backend
uvicorn src.api.main:app --reload

# Run the frontend (separate terminal)
cd frontend
npm install
npm run dev

# Run tests (fast subset, no real OCR)
pytest -m "not real_docling and not real_surya"
```

The pipeline can also be called directly:

```python
from src.pipeline.phase1_pipeline import run_pipeline

# PDF-native path (unchanged behavior)
result = run_pipeline(pdf_path="path/to/file.pdf", output_root="outputs/", enable_ocr=False)

# Mathpix import path
result = run_pipeline(pdf_path="path/to/file.pdf", mmd_path="path/to/file.mmd", output_root="outputs/")
```

---

## Project documentation

| File | Purpose |
|------|---------|
| `docs/CURRENT_STATE.md` | One-page summary of what RAWRS actually does today |
| `docs/PHASE_STATUS.md` | Per-feature implementation status with test citations |
| `docs/ARCHITECTURE_CURRENT.md` | Actual module inventory and pipeline order |
| `docs/DECISIONS_LOG.md` | Why things are the way they are — all architecture decisions |
| `docs/KNOWN_LIMITATIONS.md` | What's deliberately not built and confirmed gaps |
| `docs/VALIDATION_RULES.md` | All 29 validation rule IDs, severities, and checks |
| `docs/DOCUMENTATION_MAP.md` | Precedence order when documents conflict |

---

## Benchmark PDFs

The benchmark corpus (`samples/benchmark/pdfs/`) and Mathpix DOCX exports (`samples/mathpix/**/*.docx`) are **not included in this repository** (copyrighted academic papers). The test suite's expected outputs (`samples/benchmark/expected_md/`) and manifest (`samples/benchmark/manifest.json`) are included. To run the full benchmark suite (tests marked `real_docling`/`real_surya`), place the corresponding PDFs in `samples/benchmark/pdfs/` matching the manifest filenames.

## Test suite

Fast subset (no real OCR engines — runs in ~35 min):

```bash
pytest -m "not real_docling and not real_surya" -q
```

Full suite including real OCR benchmark tests:

```bash
pytest -q
```

Last confirmed full-suite count: **1296 passed, 0 failed, 7 skipped** (2026-06-30, all markers).

---

## Dependencies

Core: `pydantic`, `pymupdf`, `python-docx`, `fastapi`, `uvicorn`, `docling`, `surya-ocr==0.20.0`, `loguru`, `beautifulsoup4`, `python-multipart`

AI alt text (on-demand): `torch`, `transformers`, `qwen-vl-utils` — installed; model weights download on first inference call

Dev: `pytest`, `pytest-cov`

External runtime (for Surya on CPU): `llama-server` binary (llama.cpp) — required by `surya-ocr` on non-GPU hosts; set `LLAMA_CPP_BINARY` env var or add to PATH.
