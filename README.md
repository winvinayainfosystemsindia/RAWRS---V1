# RAWRS — Remediation & Accessibility Work Reduction System

RAWRS is a local-first, accessibility remediation platform for academic PDFs, built for WinVinaya Foundation. It accepts either a PDF alone or a PDF paired with a Mathpix MMD export, verifies and enriches the extracted content, and produces accessible Word documents (DOCX) and Markdown with a human-review platform for every accessibility-critical decision.

> **Automation proposes. Validation decides. Humans make the judgement calls.**

---

## What it does

- **PDF-native path:** extracts text from born-digital PDFs (PyMuPDF) with OCR fallback (Docling → Surya).
- **Mathpix import path:** imports a Mathpix MMD file as the primary extraction source; RAWRS provides verification, enrichment, and accessibility output. Every proposed correction is recorded as a `CorrectionRecord` (audit trail) — Mathpix extraction is never silently overwritten.
- Detects headings (H1–H6), footnotes/endnotes, images, tables, lists, callouts (boxed asides), and front matter.
- Generates structured Markdown and accessible DOCX (Word Heading styles, native table markup, `w:tblHeader`, `dc:language`, `dc:title`, bold/italic inline formatting, native Word footnotes and endnotes).
- Validates 40 accessibility and structural rules (WCAG 2.4.2, 3.1.1, H73, etc.), including cross-source verification findings.
- Cross-checks Mathpix-imported content against the original PDF via a generic evidence-fusion verification engine (`src/verification/`), proposing REPAIR/RECOVER/REMOVE corrections a reviewer accepts or rejects — never silently overwriting Mathpix output.
- Proven page alignment: on the Mathpix path, a block's page is *stated by the source package* (package DOCX markers, image filenames, PDF text layer) rather than estimated from its position; the estimate remains only as a documented fallback, and nothing is invented where evidence is absent.
- Provides a web-based review platform (PDF/Markdown/DOCX split-view workspace, PDF object inspector, theme toggle) with workspaces for every reviewable object:
  - **Headings** — approve/level-change/reject, screen reader preview
  - **Reading Order** — drag-reorder blocks, approve pages
  - **Images** — on-demand AI alt text (Qwen2.5-VL), approve/reject/decorative/complex/skip/edit
  - **Footnotes** — edit body, approve, reject
  - **Tables** — auto-detect bordered tables, manual create for borderless, edit cells, caption, summary, header rows; WCAG H73 screen reader simulation
  - **Page Labels** — override individual pages or apply a bulk numbering scheme (arabic/roman, start number, prefix/suffix) per page range
  - **Corrections** — accept/reject/edit every cross-source verification finding, with full history
  - **Metadata** — set `dc:language`, `dc:title`, `dc:creator`, `dc:subject`

---

## Architecture

**Pipeline (both paths share stages 3–8):**

```
PDF-native:  PDF → extract text → OCR → Document Model → Markdown + DOCX + report
Mathpix:     PDF + MMD → MathpixImportProvider → Document Model → Markdown + DOCX + report
```

`src/pipeline/phase1_pipeline.py` — `run_pipeline(pdf_path, mmd_path=None, image_dir=None)`
`src/importers/` — `ImportProvider` Protocol + `MathpixImportProvider`
`src/mathpix/mmd_parser.py` — state-machine MMD → intermediate P2Document
`src/mathpix/page_alignment.py` — proven block→page alignment from the package DOCX, image filenames and the PDF text layer
`src/mathpix/ingestor.py` — P2Document → RAWRS Document Model
`src/models/` — the canonical semantic objects (`Document`, `Page`, `Heading`, `Paragraph`, `Table`, `Image`, `Figure`, `Footnote`, `ListBlock`, `Callout`, `FrontMatter`, `Metadata`, `CorrectionRecord`, `ValidationIssue`, …)
`src/verification/` — evidence-fusion cross-source verification engine
`src/api/` — FastAPI HTTP interface (in-memory job tracking)
`frontend/` — Next.js/React/TypeScript/Tailwind review platform

---

## Design principles

- **Validation first** — extraction and interpretation are provisional until validated.
- **Human in the loop** — RAWRS does not silently make decisions requiring accessibility expertise.
- **Local first** — runs on the filesystem. No database, cloud storage, queue or container requirement.
- **Model agnostic** — no dependency on a single AI vendor.
- **Auditability** — decisions retain evidence, provenance and review state.
- **Reversibility** — corrections preserve the original value and support undo.
- **Single source of truth** — shared semantic models live in `src/models/`; downstream systems consume the canonical model rather than inventing parallel representations. Markdown and DOCX are outputs, not the authoritative editing model — a projection must not invent semantic objects that do not exist in the model.
- **Evidence over assumption** — benchmark documents verify architectural assumptions before implementation.

---

## Quick start

```bash
# Install dependencies
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.lock     # reproducible install (preferred)
pip install -r requirements-ai.txt   # optional — only needed for real AI alt text/table analysis

# Run the backend
uvicorn src.api.main:app --reload

# Run the frontend (separate terminal)
cd frontend
npm install
npm run dev
```

**Open the frontend at `http://localhost:3000`, not `http://127.0.0.1:3000`.** Next.js's dev server blocks cross-origin dev requests (including its own hot-reload WebSocket) for any host other than the exact one it printed. Using `127.0.0.1` or a LAN IP silently breaks hot reload and can cause the browser to fall back to rapid full-page reloads, wiping in-progress form state (e.g. a file just selected in the upload form). See `frontend/next.config.ts`'s `allowedDevOrigins` and `docs/DECISIONS_LOG.md` Part 24.

The pipeline can also be called directly:

```python
from src.pipeline.phase1_pipeline import run_pipeline

# PDF-native path (unchanged behavior)
result = run_pipeline(pdf_path="path/to/file.pdf", output_root="outputs/", enable_ocr=False)

# Mathpix import path
result = run_pipeline(
    pdf_path="path/to/file.pdf",
    mmd_path="path/to/file.mmd",
    image_dir="path/to/images/",
    output_root="outputs/",
)
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
| `docs/VALIDATION_RULES.md` | All validation rule IDs, severities, and checks |
| `docs/DOCUMENTATION_MAP.md` | Precedence order when documents conflict |

The `docs/` folder also carries dated product audits (`RAWRS_PRODUCT_AUDIT_*.md`, `M1_*`, `P4C4_*`, `N2_*`, `N3_*`, `RAWRS_REMEDIATION_AUDIT_*.md`) that measure the benchmark corpus against the human-remediated targets and record what was deliberately *not* built at each step. Consult the latest one before implementing changes.

---

## Benchmark corpus

Ten educational and academic PDFs with corresponding remediated DOCX targets, testing extraction quality, heading structure, lists, tables, notes, images, page preservation, validation, DOCX projection and accessibility readiness.

**The benchmark is an architectural feedback mechanism, not a test suite.** It has repeatedly prevented incorrect assumptions from becoming architecture.

The benchmark PDFs (`samples/benchmark/pdfs/`) and Mathpix DOCX exports (`samples/mathpix/**/*.docx`) are **not included in this repository** (copyrighted academic papers). The test suite's expected outputs (`samples/benchmark/expected_md/`) and manifest (`samples/benchmark/manifest.json`) are included. To run the full benchmark suite (tests marked `real_docling`/`real_surya`), place the corresponding PDFs in `samples/benchmark/pdfs/` matching the manifest filenames.

## Test suite

Fast subset (no real OCR engines):

```bash
pytest -m "not real_docling and not real_surya" -q
```

Full suite including real OCR benchmark tests:

```bash
pytest -q
```

---

## Dependencies

Core: `pydantic`, `pymupdf`, `python-docx`, `docling` (+ `onnxruntime`, its OCR backend), `surya-ocr`, `rapidocr`, `loguru`, `beautifulsoup4`, `fastapi`, `uvicorn`, `python-multipart`.

AI alt text (on-demand, optional — `requirements-ai.txt`): `torch`, `transformers`, `qwen-vl-utils`, `psutil`. The base install runs fully without these; `GET /api/ai/status` reports unavailability with a clear reason if they're not installed, and a startup RAM/VRAM preflight (`src/ai/providers/qwen.py`) checks hardware suitability before attempting to load the model. Model weights download on first real inference call. Note that `torch` and `transformers` are pulled in as *base* dependencies of `docling` regardless — see `requirements-ai.txt`.

External runtime (for Surya on CPU): `llama-server` binary (llama.cpp) — required by `surya-ocr` on non-GPU hosts; set `LLAMA_CPP_BINARY` env var or add to PATH.

Dev: `pytest`, `pytest-cov`.

All packages are pinned exactly in `requirements.txt` (direct dependencies) and `requirements.lock` (the complete transitive graph) so a fresh clone reproduces the environment that produced the current test baseline.

---

## Scope

**In Phase 1** — OCR, reading-order analysis, OCR cleanup, header/footer removal, page markers, page-break preservation, heading detection, image extraction, figure detection, metadata capture, Markdown and DOCX generation, tables, notes, lists, cross-source verification, accessibility evaluation, human review.

**Out of Phase 1** — unattended alt-text automation, equation and STEM remediation, PDF/UA tag-tree generation, model training, knowledge graphs, multi-agent architecture, cloud infrastructure, database-backed or multi-tenant deployment, collaborative multi-reviewer workflow.

---

## Philosophy

RAWRS does not optimise for automation percentage. It optimises for **human minutes per 100 pages** while maintaining trustworthy accessibility quality.

A good result is not "AI changed 95% of the document." A good result is: the document is structurally correct, the remaining decisions are visible, the reviewer can resolve them quickly, and every important decision is traceable.

The long-term direction is an **Accessibility Decision Support Platform** where the reviewer workspace is the primary interface, rather than deep remediation happening in exported DOCX files.

---

## Maintainer note

Investigate before coding. Measure against the benchmark. Find the canonical owner. Reuse existing infrastructure. Make the smallest coherent change. Validate before claiming success. Do not hide uncertainty. Do not confuse infrastructure progress with remediation progress.

RAWRS should become simpler and more trustworthy as it grows, not merely larger.
