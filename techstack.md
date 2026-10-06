# RAWRS Tech Stack

A one-file orientation for a new tech lead: what RAWRS is, what it's built with, how the pieces fit, and what state it's actually in today (2026-10-05).

For deeper reading, every claim here has a home doc — see the map at the bottom.

---

## 1. What RAWRS is

**RAWRS** (Remediation & Accessibility Work Reduction System) is a local-first platform that turns difficult academic PDFs into **accessible Word (DOCX) documents and Markdown** for WinVinaya Foundation — with a human reviewer approving every accessibility-critical decision.

It accepts two kinds of input:

1. **PDF only** → extraction/OCR pipeline (Docling + RapidOCR, Surya fallback)
2. **PDF + Mathpix MMD package** → Mathpix supplies the text, RAWRS verifies it against the PDF

Both paths converge on one canonical document model, then produce Markdown + DOCX + a validation report, reviewed in a web workspace.

**The one-line philosophy:** *Automation proposes. Validation decides. Humans make the judgement calls.* The success metric is **human remediation minutes per 100 pages** — not "percent automated."

---

## 2. Current state snapshot

| Area | State |
|---|---|
| Branch | `main` (feature branches like `fe-0-001-persistence-and-cleanup` for frontend work) |
| Backend tests | 2,537 passed / **5 failed** — all 5 in `tests/test_pipeline.py`; 3 are stale assertions from before automatic alt text, 2 undiagnosed (CI run 36454387742, 2026-09-28) |
| Frontend tests | Green: `tsc` + Jest (15 suites / 45 tests) + production build all pass locally |
| CI | GitHub Actions runs frontend (typecheck/Jest/build) and batched backend pytest; backend red on the last runs due to the 5 failures above |
| Deployment | Docker/compose exists (API + Ollama + Cloudflare tunnel); **nothing is actually deployed** |
| Hosting | Local Windows machine, **CPU-only** (no CUDA/NVIDIA) |
| License file | **No repository LICENSE yet**; several dependency licenses need review before commercial use (see §9) |

---

## 3. How the system fits together

```
PDF ──────────────┐
                  │
Mathpix MMD ──────┤ (optional)
+ images          │
                  ▼
        ┌──────────────────────┐
        │  Import providers    │   src/importers/, src/mathpix/
        │  (native / Mathpix)  │
        └──────────┬───────────┘
                   ▼
        ┌──────────────────────┐
        │  Pipeline (8 stages) │   src/pipeline/phase1_pipeline.py
        └──────────┬───────────┘
                   ▼
        ┌──────────────────────┐
        │  Document model      │   src/models/  (single source of truth)
        └──────────┬───────────┘
                   ▼
   ┌───────────────┼────────────────┐
   ▼               ▼                ▼
 Markdown        DOCX           Validation
 (src/markdown/) (src/docx/)    (src/validation/, src/verification/)
   └───────────────┴────────────────┘
                   ▼
        ┌──────────────────────┐
        │  FastAPI backend     │   src/api/main.py  (port 8001)
        └──────────┬───────────┘
                   ▼
        ┌──────────────────────┐
        │  Next.js frontend    │   frontend/  (port 3000)
        │  review workspace    │
        └──────────────────────┘
```

**The 8 pipeline stages** (`run_pipeline(pdf_path, mmd_path=None, ...)`): parse PDF → extract text / route pages → OCR (Docling→RapidOCR, Surya fallback) → detect structure (headings, footnotes, front matter, tables) → build Markdown → generate DOCX → validate. The Mathpix path **skips** the extraction/OCR/heading stages — the MMD *is* the text, and the PDF becomes verification evidence instead.

**The two golden rules of the architecture:**

- **Markdown and DOCX are projections, not the editing model.** Nothing may exist in the output that doesn't exist in `src/models/`.
- **Never silently overwrite.** Every proposed change is a `CorrectionRecord` a reviewer accepts or rejects, with the original preserved.

---

## 4. Backend

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | |
| API framework | FastAPI 0.138.2 | `src/api/main.py` |
| Server | Uvicorn 0.49.0 | run: `uvicorn src.api.main:app --port 8001` |
| Validation | Pydantic 2.13.4 | all models |
| Uploads | python-multipart | |
| Logging | loguru | |
| DOCX generation | python-docx 1.2.0 | Word Heading styles, native tables, `w:tblHeader`, alt text via `docPr@descr` |
| Persistence | **Local filesystem only** | `outputs/` artifacts; jobs tracked in memory. No DB, no cloud storage, no queue — deliberate |
| Equation → native Word | pypandoc-binary 1.17 (pandoc/texmath) | Mathpix route only; PDF-only equations not built yet (`docs/EQUATION_DESIGN.md`) |

Everything is pinned exact in `requirements.txt`, with the full transitive graph in `requirements.lock` (preferred install). `requirements-ai.txt` adds the optional AI extras.

### Document processing / OCR (the heart of the backend)

| Engine | Role | Details |
|---|---|---|
| **PyMuPDF 1.28** | PDF inspection, native text extraction, page rendering, image/table detection | AGPL-3.0 — see §9 |
| **Docling 2.87.0** | Primary OCR + layout for OCR-needed pages, with `force_full_page_ocr=True` | Uses **RapidOCR 3.9.0** (PP-OCRv6) via **onnxruntime 1.30.0** on CPU |
| **Surya-2 (surya-ocr 0.20.0)** | Fallback OCR — only for pages Docling returns **empty** | VLM-backed; on this CPU box it auto-selects a **llama.cpp** backend and spawns the upstream `llama-server` binary against `surya-2.gguf` (~1.27 GB). Needs `LLAMA_CPP_BINARY` or PATH |
| **Page router** (`src/ocr/router.py`) | Per-page classification: native text if ≥20 usable chars and <10% control chars, else OCR | Per-page, so one PDF can mix both |

**Known OCR weakness (measured, not hypothetical):** on the O'Leary benchmark PDF, RapidOCR garbles bold/italic text runs at every DPI (150/300/400), while Surya-2 reads them perfectly — but at 347 s/page on CPU. Escalation currently fires only on *empty* pages, so poor-quality-but-nonempty pages never escalate. Full forensics and the fix plan: `docs/RAWRS_PDF_ONLY_RECONSTRUCTION_RESEARCH.md`.

---

## 5. AI subsystem (optional, pluggable)

| Capability | Provider | Notes |
|---|---|---|
| Automatic alt text for images | Ollama `qwen2.5vl:3b` (local) | ~2.5 min/image on CPU; every image stays reviewer-approvable |
| Table analysis (captions, summaries, header detection) | Same Ollama provider | On-demand via API; reviewer approves before applying |
| In-process alternative | torch 2.12.1 + transformers 4.57.6 + qwen-vl-utils | `requirements-ai.txt`; includes a RAM/VRAM startup preflight; `RAWRS_AI_STUB=1` for tests |
| Status endpoint | `GET /api/ai/status` | Reports availability; never crashes the backend when models are missing |
| Planned (researched, not yet integrated) | `glm-ocr:q8_0` (1.6 GB, **already pulled locally**, verified 2026-10-05) | The recommended difficult-page OCR VLM (MIT weights, 0.9B) from the research reports; adoption pending the experiment plan in `docs/RAWRS_PDF_ONLY_RECONSTRUCTION_RESEARCH.md` |

torch/transformers are actually **base** deps (docling needs them) — `requirements-ai.txt` only adds `qwen-vl-utils` and `psutil` on top.

---

## 6. Frontend

| Concern | Choice | Notes |
|---|---|---|
| Framework | Next.js 16.2.9 (App Router) + React 19.2.4 | Turbopack dev |
| Language | TypeScript | |
| Styling | Tailwind CSS 4 + semantic theme tokens (light/dark) | `frontend/app/globals.css`, `frontend/lib/theme/` |
| State | React Context + `useReducer` | `frontend/lib/store/` — deliberately no Redux/Zustand |
| PDF viewer | react-pdf (one page at a time) | |
| DOCX preview | mammoth | live preview follows saved Markdown edits |
| Markdown editor | CodeMirror 6 | **editable** since 2026-09-28; a saved edit drives the DOCX preview and downloads |
| Panels | react-resizable-panels | VS Code-style workspace shell |
| Tests | Jest + Testing Library + jest-axe | 15 suites / 45 tests |

**UI surfaces:** documents dashboard, batch upload, document workspace with tabs for Headings, Reading Order, Images (alt text), Markdown, Footnotes, Tables (incl. WCAG H73 screen-reader simulation), Page Labels, Equations, Corrections, Metadata; plus Settings and Export Center.

**Do not migrate the stack.** An older plan named Vite + Zustand + shadcn/ui; the built Next/Context stack is the decided stack (`docs/TECH_STACK.md` header note).

---

## 7. Running it (developer quickstart)

```bash
# Backend (from repo root)
pip install -r requirements.lock        # reproducible install
uvicorn src.api.main:app --port 8001

# Frontend (separate terminal)
cd frontend && npm install
npm run dev -- -p 3000                  # naked `npm run dev` picks a RANDOM port
```

Gotchas that have bitten people:

- **Open `http://localhost:3000`, never `http://127.0.0.1:3000`** — Next's dev server rejects other hosts and silently breaks hot reload (wipes in-progress form state).
- CORS on the backend allows ports **3000 and 3001**; frontend reads `NEXT_PUBLIC_API_BASE_URL` from `frontend/.env.local` (currently `http://127.0.0.1:8001`).
- Ollama must be running for alt text/table analysis (`ollama pull qwen2.5vl:3b`); without it, exports still work and images are flagged for human alt text.
- Surya fallback needs `llama-server` (llama.cpp) on PATH or via `LLAMA_CPP_BINARY`.
- Backend tests: fast subset `pytest -m "not real_docling and not real_surya" -q` (minutes); the full suite including real OCR takes tens of minutes and several GB of RAM — run it in batches.

### Outputs layout (per job, under `outputs/`)

`documents/{id}.json` (canonical model, incl. per-page `extraction_method` / `routing_decision` / `ocr_confidence` provenance) · `markdown/` · `docx/` · `reports/` · `jobs/` · `alt_text_dataset/`.

---

## 8. Testing & verification posture

- **~68 validation rule IDs** (WCAG 2.4.2, 3.1.1, H73, HEADING_001, META_001/002, TABLE_001–006, NOTE_001/002, DOC_004, PAGE_003…) + **40 checklist-audit checks** on every exported DOCX (`docs/CHECKLIST_COMPLIANCE.md`).
- **Cross-source verification** (`src/verification/`): on the Mathpix path, the engine cross-checks MMD content against the PDF and proposes REPAIR/RECOVER/REMOVE corrections. It is path-agnostic, but today most verifiers **skip when `import_provider` is None** — meaning the PDF-only path currently ships with no cross-checks. (Identified as the cheapest high-value fix in the research report.)
- **Three-layer XML sanitization** keeps illegal OOXML characters out of DOCX (entry sanitization → `DOC_004` disclosure → export guard).
- Frontend trio verify: `tsc` + Jest + production build.

---

## 9. Licensing caveats (read before any commercial or networked use)

| Dependency | License | Caveat |
|---|---|---|
| PyMuPDF | **AGPL-3.0** | Or paid Artifex license — question for the company |
| Surya-2 **weights** | Modified OpenRAIL-M | Free only ≤ $5M revenue **and** funding; code is Apache-2.0. This is RAWRS's current *fallback* engine |
| qwen2.5vl:3b | Qwen Research license | Non-commercial/revenue-capped |
| pandoc (pypandoc-binary wheel) | GPL-2 | Binary bundles the executable |
| GLM-OCR (planned) | MIT (weights) | Its layout component, PP-DocLayoutV3, is **separately licensed** — verify before redistribution |
| Repo itself | **No LICENSE file yet** | |

Candidate replacements researched (GLM-OCR: MIT; PaddleOCR-VL-1.6 / Granite-Docling-258M: Apache-2.0) are cleaner — see `docs/OCR_MATHPIX_REPLACEMENT_RESEARCH.md` and `docs/RAWRS_PDF_ONLY_RECONSTRUCTION_RESEARCH.md` §8.

---

## 10. Honest gaps (what a tech lead should know on day one)

1. **5 failing backend tests** in `tests/test_pipeline.py` — 3 stale assertions, 2 undiagnosed; CI is red because of them (`docs/STATUS_REPORT_2026-09-30.md` §4).
2. **OCR quality on emphasized runs** — RapidOCR garbles bold/italic text; escalation only fires on empty pages; Surya-2 fixes it but is CPU-prohibitive at ~6 min/page. Research + 6-experiment plan written up, not yet implemented (`docs/RAWRS_PDF_ONLY_RECONSTRUCTION_RESEARCH.md`).
3. **PDF-only path has no verification safety net** (verifiers gate on `import_provider is None`).
4. **Equations panel** is built and tested (Mathpix route) but **not yet validated against real docs in the UI**, and the PDF-only route has no equations at all.
5. **Batch upload cancel** has known limits.
6. **Nothing is deployed** — Docker packaging exists, hosting is undecided (`docs/DEPLOYMENT.md`).
7. **bug_003 (open):** H1 detection assumes page 1's first line is the title; a kicker line like "Article" can steal the H1 slot.
8. **Footnote detection** only sees Unicode superscript glyphs, not styled smaller-font digits (root cause: span-level data discarded in the text model; design done, not implemented — `feature_005`).

---

## 11. Documentation map (where to look next)

| Question | Doc |
|---|---|
| What does RAWRS do today? | `docs/PHASE_STATUS.md`, `README.md` |
| How is it architected? | `docs/ARCHITECTURE_CURRENT.md`, `docs/RAWRS_PROJECTION_ARCHITECTURE.md` |
| Why was X decided? | `docs/DECISIONS_LOG.md` (every architecture decision, including reversals) |
| What's deliberately not built? | `docs/KNOWN_LIMITATIONS.md` |
| Validation rules? | `docs/VALIDATION_RULES.md` |
| OCR behavior/rules? | `docs/OCR_RULES.md`, `docs/PAGE_RULES.md`, `docs/HEADING_RULES.md` |
| Equations? | `docs/EQUATION_DESIGN.md` |
| Done/open/planned + cost estimates? | `docs/STATUS_REPORT_2026-09-30.md` |
| Checklists compliance? | `docs/CHECKLIST_COMPLIANCE.md` |
| Latest product audits | `docs/RAWRS_REMEDIATION_AUDIT_2026-08-16.md`, `docs/RAWRS_POST_P4C_AUDIT_2026-08-15.md` |
| OCR/Mathpix research (2 reports) | `docs/OCR_MATHPIX_REPLACEMENT_RESEARCH.md`, `docs/RAWRS_PDF_ONLY_RECONSTRUCTION_RESEARCH.md` |

Precedence when docs conflict: `docs/DOCUMENTATION_MAP.md`.

---

*Built with: Python 3.11+, FastAPI, Pydantic, PyMuPDF, Docling+RapidOCR (ONNX), Surya-2 (llama.cpp), python-docx, pandoc; Ollama + Qwen2.5-VL; Next.js 16 + React 19 + TypeScript + Tailwind 4; Jest; pytest; GitHub Actions; Docker (optional). CPU-only deployment, local-first, no databases.*
