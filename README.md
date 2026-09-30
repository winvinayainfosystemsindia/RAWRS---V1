# RAWRS — Remediation & Accessibility Work Reduction System

RAWRS is a local-first, accessibility remediation platform for academic PDFs, built for WinVinaya Foundation. It accepts either a PDF alone or a PDF paired with a Mathpix MMD export, verifies and enriches the extracted content, and produces accessible Word documents (DOCX) and Markdown with a human-review platform for every accessibility-critical decision.

> **Automation proposes. Validation decides. Humans make the judgement calls.**

---

## What it does

- **PDF-native path:** extracts text from born-digital PDFs (PyMuPDF) with OCR fallback (Docling → Surya); scanned/image PDFs get headings and lists from Docling's layout model.
- **Checklist-compliant DOCX:** every export is audited against both remediation checklists (`docs/CHECKLIST_COMPLIANCE.md`); alt text is written automatically by a local vision model (Ollama `qwen2.5vl:3b`), with statistics explained for charts and tables.
- **Mathpix import path:** imports a Mathpix MMD file as the primary extraction source; RAWRS provides verification, enrichment, and accessibility output. Every proposed correction is recorded as a `CorrectionRecord` (audit trail) — Mathpix extraction is never silently overwritten.
- Detects headings (H1–H6), footnotes/endnotes, images, tables, lists, callouts (boxed asides), and front matter.
- **Equations (Mathpix route, built 2026-10-01):** display and inline maths become native Word equations with the number outside the box, functions from the equation tool and cross-references; a subset of `\ce` chemistry is translated; anything not provably right is flagged for review instead of guessed (`docs/EQUATION_DESIGN.md`). PDF-only input does not get this yet.
- Generates structured Markdown and accessible DOCX (Word Heading styles, native table markup, `w:tblHeader`, `dc:language`, `dc:title`, bold/italic inline formatting, native Word footnotes and endnotes).
- Validates against ~68 accessibility, structural and cross-source verification rule IDs (WCAG 2.4.2, 3.1.1, H73, etc.), plus 40 checklist-audit checks on the exported DOCX.
- Cross-checks Mathpix-imported content against the original PDF via a generic evidence-fusion verification engine (`src/verification/`), proposing REPAIR/RECOVER/REMOVE corrections a reviewer accepts or rejects — never silently overwriting Mathpix output.
- Proven page alignment: on the Mathpix path, a block's page is *stated by the source package* (package DOCX markers, image filenames, PDF text layer) rather than estimated from its position; the estimate remains only as a documented fallback, and nothing is invented where evidence is absent.
- Provides a VS Code-style review workspace (full-width, fullscreen, PDF + editable Markdown + live DOCX preview side by side, optional reading-order markers) with workspaces for every reviewable object:
  - **Headings** — approve/level-change/reject, screen reader preview
  - **Reading Order** — drag-reorder blocks, approve pages
  - **Images** — automatic AI alt text, approve/reject/decorative/complex/skip/edit
  - **Markdown** — edit the text directly; the DOCX preview and downloads follow the saved edit
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
- **Local first** — runs on the filesystem. No database, cloud storage or queue. Docker (`docker-compose.yml`) is an optional way to host it, not a requirement.
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
ollama pull qwen2.5vl:3b             # optional — automatic alt text (https://ollama.com)

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
| `docs/STATUS_REPORT_2026-09-30.md` | Done / open / planned, hosting estimates, questions for the company |
| `docs/EQUATION_DESIGN.md` | How equations and `\ce` chemistry are remediated, and what real data showed |
| `docs/CHECKLIST_COMPLIANCE.md` | Every remediation-checklist item, how RAWRS meets it, and the audit check |
| `docs/DEPLOYMENT.md` | Hosting routes and what each one costs |

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

Equation tests are `tests/test_equation_*.py`. Most need `pandoc` (PATH or `pypandoc-binary`) and skip without it; `test_equation_groundtruth.py` also needs the arXiv samples under `data/cache/equation_samples/` (git-ignored, list in `SOURCES.txt`) and skips without them.

**CI status (2026-09-28, run 36454387742):** backend 2537 passed / **5 failed**, frontend 38 Jest tests passed. The 5 failures are all in `tests/test_pipeline.py`; three trace to a stale assertion that predates automatic alt text, two are not yet diagnosed. See `docs/STATUS_REPORT_2026-09-30.md` §4. The full suite takes tens of minutes and needs several GB of RAM — run it in batches.

---

## Dependencies

Core: `pydantic`, `pymupdf`, `python-docx`, `docling` (+ `onnxruntime`, its OCR backend), `surya-ocr`, `rapidocr`, `loguru`, `beautifulsoup4`, `fastapi`, `uvicorn`, `python-multipart`.

Automatic alt text uses a local [Ollama](https://ollama.com) server (`RAWRS_OLLAMA_URL`, `RAWRS_OLLAMA_MODEL`, default `qwen2.5vl:3b`, ~2.5 min per image on CPU). Without it RAWRS still exports and flags images for a human to write alt text. The in-process Qwen provider (`requirements-ai.txt`: `torch`, `transformers`, `qwen-vl-utils`, `psutil`) is the alternative; `GET /api/ai/status` reports availability, and a startup RAM/VRAM preflight (`src/ai/providers/qwen.py`) checks hardware before loading. Note that `torch` and `transformers` are pulled in as *base* dependencies of `docling` regardless — see `requirements-ai.txt`.

**Licences to be aware of before any commercial or networked use:** `pymupdf` is AGPL-3.0 (or a paid Artifex licence); the Surya model weights and `qwen2.5vl:3b` (Qwen Research licence) carry non-commercial or revenue-capped terms. Details and questions in `docs/STATUS_REPORT_2026-09-30.md` §7. The repository has no `LICENSE` file yet.

External runtime (for Surya on CPU): `llama-server` binary (llama.cpp) — required by `surya-ocr` on non-GPU hosts; set `LLAMA_CPP_BINARY` env var or add to PATH.

Dev: `pytest`, `pytest-cov`.

All packages are pinned exactly in `requirements.txt` (direct dependencies) and `requirements.lock` (the complete transitive graph) so a fresh clone reproduces the environment that produced the current test baseline.

---

## Scope

**In Phase 1** — OCR, reading-order analysis, OCR cleanup, header/footer removal, page markers, page-break preservation, heading detection, image extraction, figure detection, metadata capture, Markdown and DOCX generation, tables, notes, lists, cross-source verification, accessibility evaluation, human review.

**Out of Phase 1** — alt text published without human review (it is now generated automatically, but every image stays reviewable), STEM remediation beyond the Mathpix-route equations above (PDF-only formulas, structure diagrams), PDF/UA tag-tree generation, model training, knowledge graphs, multi-agent architecture, cloud infrastructure, database-backed or multi-tenant deployment, collaborative multi-reviewer workflow.

---

## Philosophy

RAWRS does not optimise for automation percentage. It optimises for **human minutes per 100 pages** while maintaining trustworthy accessibility quality.

A good result is not "AI changed 95% of the document." A good result is: the document is structurally correct, the remaining decisions are visible, the reviewer can resolve them quickly, and every important decision is traceable.

The long-term direction is an **Accessibility Decision Support Platform** where the reviewer workspace is the primary interface, rather than deep remediation happening in exported DOCX files.

---

## Maintainer note

Investigate before coding. Measure against the benchmark. Find the canonical owner. Reuse existing infrastructure. Make the smallest coherent change. Validate before claiming success. Do not hide uncertainty. Do not confuse infrastructure progress with remediation progress.

RAWRS should become simpler and more trustworthy as it grows, not merely larger.
