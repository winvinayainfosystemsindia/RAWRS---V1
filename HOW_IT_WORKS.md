# How RAWRS Works — Start to End

The flow of a document through RAWRS, then every technical aspect explained with its **how** and its **why**. (Stack/versions: [techstack.md](techstack.md). Deep dives: map at the bottom.)

**The philosophy everything below serves:** *Automation proposes. Validation decides. Humans make the judgement calls.* The success metric is **human remediation minutes per 100 pages** — not "% automated", because the real cost of remediation is human time, and a percentage can be gamed by fast-but-wrong output.

---

## Part 1 — The flow of work

1. **Upload** — reviewer opens the web app (Next.js, `localhost:3000`) and submits **a PDF alone** or **a PDF + a Mathpix MMD package** (premium OCR export). The FastAPI backend (`localhost:8001`) creates a job, tracked in memory.
2. **Read** — every page is classified individually: native text extraction when the page has real text, OCR otherwise. If a Mathpix package was supplied, *it* becomes the text and the PDF becomes verification evidence instead.
3. **Understand** — deterministic detectors find headings, paragraphs, footnotes, tables, figures + captions, front matter; a local AI drafts alt text.
4. **One model** — everything lands in the canonical Document model (`src/models/`).
5. **Verify** — ~68 validation rules fire; on the Mathpix path a cross-source engine compares text against the PDF and proposes corrections; every export is audited against two remediation checklists.
6. **Human decides** — the VS Code-style workspace (PDF + editable Markdown + live DOCX preview) has a review panel for every decision type: headings, reading order, images/alt text, tables, footnotes, page labels, equations, corrections, metadata.
7. **Export** — accessible DOCX (real Word styles, native tables, native equations, alt text embedded), structured Markdown, and a validation report. Artifacts land under `outputs/` with full per-page provenance.

---

## Part 2 — Every technical aspect: how and why

### Ingestion & OCR

| Aspect | How | Why |
|---|---|---|
| **Two input paths** | PDF-only runs extraction+OCR; the Mathpix path parses the MMD as the text and skips those stages entirely. Both converge on the same Document model. | Born-digital PDFs need no paid service; hard documents buy quality via Mathpix. Converging on one model means verification, review, and projection are identical code for both paths. |
| **Per-page routing** (`src/ocr/router.py`) | Each page classified `DIRECT_TEXT` or `OCR_REQUIRED`: OCR if usable text < 20 chars or >10% control/replacement chars. | A single PDF can mix born-digital and scanned pages, so classification must be per-page. Native extraction is faster *and* more reliable than OCR when real text exists — OCR is used only where it must be. |
| **Docling + RapidOCR as primary OCR** | Pages needing OCR run through Docling 2.87 with `force_full_page_ocr=True`; RapidOCR (PP-OCRv6, ONNX) does recognition on CPU. | Local-first, no cloud, CPU-capable, Apache-licensed. The force flag exists because Docling's *default* layout-driven OCR returned **zero text on real benchmark pages with genuine prose** — measured, not assumed. |
| **Surya-2 fallback** | Runs only on pages Docling left **empty**; on this CPU box it auto-selects llama.cpp and spawns the upstream `llama-server` with `surya-2.gguf`. Its text is marked LOW confidence. | A vision-language model reads what classical OCR cannot — but costs ~6 min/page on CPU, so it's gated to run only when the primary failed. Confidence drops one rung because it only ever sees the hardest pages. |
| **OCR result cache** (`src/ocr/cache.py`) | Raw engine output per page, keyed by PDF hash + page + engine versions + engine source. Re-processing a scanned page drops from ~98 s to 0.26 s. | Reruns of the same PDF (re-upload, settings change) paid full OCR again. Caching the *raw* output keeps every downstream step live, so output is identical. See [docs/LEARNING_LOOP.md](docs/LEARNING_LOOP.md). |
| **Confidence + provenance per page** | Each page stores `extraction_method`, `routing_decision`, `ocr_confidence` (HIGH native / MEDIUM Docling / LOW Surya), printed page label. | A trust gradient lets downstream logic (reviewer attention, escalation) treat pages differently — and auditability is a core principle: every result must be traceable to its origin. |

### Understanding the document

| Aspect | How | Why |
|---|---|---|
| **Heading detection** | Font-size ranking (largest unique → H1, next → H2…), boldness, numbering patterns ("3.1", "Chapter N"), keyword list, plus a last-resort tier for headings in distinct font subsets; multi-line headings absorbed with a calibrated gap window. | Academic PDFs carry hierarchy *visually*, not in tags. No single signal survives real documents — each tier was added after a benchmark regression proved a misfire, not from theory. |
| **Paragraph reconstruction** | Lines merged into paragraphs via their shared source block + baseline/x-continuity guards against column false-merges. | Two measured bugs: PyMuPDF mis-splits justified lines, and the old renderer emitted one Markdown paragraph per raw PDF line. The fix took a real document from 2,037 lines to 545. |
| **Footnotes/endnotes** | Unicode superscript markers matched to marker-numbered bodies; a "Notes" heading switches to document-wide endnote scoping. Orphaned markers or bodies are dropped, not guessed. | Notes are accessibility-critical and easy to hallucinate; linking both sides by number is the only provable match. (Known limit: only superscript *glyphs* are seen, not styled small digits.) |
| **Table detection** | PyMuPDF `find_tables(strategy='lines')` on born-digital pages; merged cells read from the None-cell pattern; borderless tables are created manually in the reviewer UI. | Vector borders are provable evidence. A full-page grid strategy was benchmark-tested and **rejected** (one journal page became a 40×8 phantom table) — guessing is worse than asking. |
| **Figure/caption linking** | Five filter criteria kill junk images (backgrounds, slivers, tiny rasters, duplicates, unreferenced); captions attach by `Figure N`-pattern + 36pt proximity, each text block claimable once. | Deterministic and auditable — the reviewer can see exactly why a caption was linked. Placeholder alt text guarantees every image enters review rather than shipping empty. |
| **Reading order** | A read-only validator (`PAGE_003`) flags backward jumps (>1.5× median line height) and overlapping blocks; reviewers can drag-reorder blocks in the workspace. | Reconstruction without evidence would be guessing; detection-only keeps the pipeline honest — anomalies are surfaced for a human, never silently reordered. |
| **Printed page labels** | Per-page detection of the number actually printed on the page ("3", "xlv"); falls back to `None` when ambiguous. Configurable marker policy (AUTO/MANUAL/DISABLED). | A single global page-offset was **proven wrong** on a benchmark PDF that splices non-contiguous chapters — per-page evidence beats a global guess. |
| **H6 page markers** | Exactly one `###### N` marker per page in the Markdown (policy-configurable); the Mathpix path synthesizes them from package evidence instead. | Reviewers verify content against source pages; consistent page addressing across both paths makes the review rail comparable. |

### The correctness spine

| Aspect | How | Why |
|---|---|---|
| **Canonical Document model** | All semantic objects (headings, tables, figures, notes…) live in `src/models/`. Markdown and DOCX are one-way *projections* of it. | Single source of truth: a projection may render the model but never invent objects it doesn't contain (formalized in ADR-020 as "semantic parity"). This is what keeps MD and DOCX consistent. |
| **Correction rail** | Every proposed change is a `CorrectionRecord`: original value preserved, `apply()`/`revert()`, full history. | The "never silently overwrite" rule made concrete. Reversibility means a reviewer can experiment without fear; the history is the audit trail. |
| **Cross-source verification** | On the Mathpix path, an evidence-fusion engine compares MMD content against the PDF and proposes REPAIR / RECOVER / REMOVE findings for the reviewer. | Mathpix text arrived unverified; RAWRS's differentiator is treating extraction as *provisional until validated*. (Known gap: on the PDF-only path most verifiers skip — the cheapest fix identified in current research.) |
| **~68 validation rules + 40 checklist checks** | Read-only rules (WCAG 2.4.2, 3.1.1, H73, heading hierarchy, table captions/headers, metadata…) produce severity-tagged issues; a checklist audit runs on every exported DOCX. | A deterministic gate catches what machines can prove before spending human attention; rules never mutate the document — they only report. |
| **Three-layer XML sanitization** | Layer 1 sanitizes text at every entry point into the model; Layer 2 discloses every action via rule `DOC_004`; Layer 3 guards every OOXML write as a last resort. | A production DOCX crashed on an illegal character (U+0002) from a broken font map. Three layers because *generated* text (alt text, equations) has no PDF-extraction call to attach a sanitizer to — defense in depth by construction. |

### Output & AI

| Aspect | How | Why |
|---|---|---|
| **DOCX generation** | python-docx writes Word's built-in Heading 1–6 styles (Navigation Pane works), native tables with `w:tblHeader`, merged cells, alt text in `docPr@descr`, `dc:title`/`dc:language`. | Accessibility means *real Word semantics*, not visual mimicry — screen readers and the Navigation Pane consume styles and OOXML attributes, not looks. |
| **Native equations** | LaTeX → OMML via pandoc/texmath with a round-trip check; a `\\ce` chemistry subset is translated; anything not provably right is flagged for a human instead of guessed. (Mathpix path; PDF-only route not built yet.) | Equations are the hardest accessibility problem; a wrong equation is worse than a flagged one. The round-trip check proves the conversion didn't silently mangle the math. |
| **AI subsystem (Ollama, qwen2.5vl:3b)** | Local HTTP calls to Ollama draft alt text and table captions/summaries; `GET /api/ai/status` reports availability; a stub mode exists for tests; the reviewer approves before anything applies. | Local-first and model-agnostic — no cloud, no vendor lock-in; a missing model degrades to human review instead of crashing. Every AI suggestion passes the same correction rail as everything else. |

### Platform choices

| Aspect | How | Why |
|---|---|---|
| **Storage** | Filesystem only (`outputs/`); jobs tracked in memory; no database, no queue, no cloud. | Phase 1 is single-user and local-first; infrastructure is cost and risk with no benefit yet. Docker exists as an *optional* hosting route, not a requirement. |
| **Testing posture** | Fast suite (`pytest -m "not real_docling and not real_surya"`) for iteration; full suite with real OCR run in batches (tens of minutes, GBs of RAM). Frontend: typecheck + Jest + build. | Real-OCR tests are the only ones that catch real extraction regressions, but they're too slow for tight loops — so both exist, deliberately. CI currently red on 5 known backend failures (3 stale assertions, 2 undiagnosed). |
| **Benchmark corpus** | 10 academic PDFs with human-remediated DOCX targets, plus dated audit docs reconciling docs-against-code. | The benchmark is an *architectural feedback mechanism*: it repeatedly killed wrong assumptions before they became code. Every bug/feature leaves a root-cause audit folder with before/after evidence. |

---

## Why these specific models and libraries

Every choice below is either measured against the benchmark corpus or documented in `docs/DECISIONS_LOG.md` — and the honest caveats are included, not hidden.

**OCR & document engines**

| Choice | Why this one | Why not the obvious alternative |
|---|---|---|
| **PyMuPDF** | One library does native text extraction, geometry/fonts, image access, page rendering *and* table finding — fast, CPU-only, precise. Rendering matters twice: it feeds OCR pages and it's what makes figure work possible. | pdfminer/pdfplumber are slower and can't render. Caveat: AGPL-3.0 — documented, company question pending. |
| **Docling (primary OCR + layout)** | Open-source (Apache-2.0, IBM), gives layout understanding + reading order on OCR-needed pages, not just text; runs fully local on CPU. `force_full_page_ocr=True` is on because Docling's default mode returned **zero text on real benchmark pages with genuine prose** — measured, then pinned. | Tesseract: no layout model, weaker accuracy on academic pages. Cloud OCR: violates local-first. |
| **RapidOCR / PP-OCRv6 via onnxruntime** | Deterministic, CPU-fast recognition inside Docling; Apache-2.0. Pinned exactly (3.9.0) because its torch backend rejects the PP-OCRv6 model family — onnxruntime is the working path, and pinning makes failures reproducible instead of drifting. | Weakness known and measured: garbles bold/italic runs on flattened PDFs (see the research report); mitigation planned via quality-gated escalation. |
| **Surya-2 as fallback (via llama.cpp)** | A vision-language model reads what classical OCR can't — proved on the failure case: perfect read where RapidOCR failed at every DPI. Gated to empty-page-only escalation so its ~6 min/page CPU cost is paid rarely. Runs through llama.cpp because on a CPU-only host surya-ocr auto-selects its llamacpp backend (vllm needs NVIDIA). | As primary: too slow on CPU. Weights carry an OpenRAIL-M ≤$5M commercial cap — documented; MIT/Apache VLMs (GLM-OCR, Granite-Docling) are the researched successors. |
| **Other 2026 OCR models (Chandra, MinerU, olmOCR 2…)** | Evaluated in `docs/OCR_MATHPIX_REPLACEMENT_RESEARCH.md` — several now beat Mathpix on benchmarks. GLM-OCR (MIT weights, 0.9B, Ollama-served) is the planned adoption if experiments confirm — and is **already pulled locally** (`glm-ocr:q8_0`, verified 2026-10-05). | Rejected for *now* on license (OpenRAIL caps, AGPL history) or size (7B won't run on this CPU box). Caveat: GLM-OCR's layout component (PP-DocLayoutV3) is separately licensed from the MIT weights. |

**LLMs & AI serving**

| Choice | Why this one | Why not the obvious alternative |
|---|---|---|
| **Ollama as serving runtime** | Zero-infrastructure local model serving with model management; RAWRS is model-agnostic — a missing model degrades to human review instead of crashing (`/api/ai/status`). | Cloud APIs (OpenAI-style): violate local-first/privacy, add per-call cost, and make alt text undeterministic across runs. |
| **qwen2.5vl:3b for alt text & tables** | Vision-capable (required for images), small enough for CPU (~2.5 min/image), good enough for *drafts* — because every suggestion is human-approved, top-1 accuracy isn't the requirement; usefulness at low cost is. | Bigger VLMs: CPU-infeasible per-image at this scale. Specialized doc models (GLM-OCR class): wrong tool — they transcribe documents, they don't write descriptive alt text. |
| **torch + transformers** | Not an AI choice per se — Docling depends on them regardless; the in-process Qwen provider is the optional no-Ollama alternative, with a RAM preflight and a stub mode for tests. | — |
| **pandoc via pypandoc-binary** | texmath is the most complete LaTeX→Word (OMML) converter available; the wheel bundles the executable so conversion works without a system install. Fail-safe by design: anything not provably right is flagged for a human, never dropped. | Hand-rolled OMML: hopeless coverage of LaTeX. Caveat: the wheel is GPL-2 — documented. |

**Libraries & platform**

| Choice | Why this one | Why not the obvious alternative |
|---|---|---|
| **FastAPI + Pydantic** | The API layer can reuse the exact same typed models as the pipeline (`src/models/`) — one source of truth from extraction to endpoint. | Flask/Django: no native pydantic model sharing, more boilerplate. |
| **python-docx** | Low-level enough to write the accessibility attributes that matter (`docPr@descr` alt text, `w:tblHeader`, built-in heading styles) — exactly the things higher-level abstractions hide. | docx4j-style templating or pandoc-only DOCX: less control over OOXML accessibility details. |
| **Next.js 16 + React 19 + Tailwind 4; Context + useReducer** | App Router suits the workspace shell (panels, tabs); built this way, and the built stack is the decided stack — no state library was added because no measured performance problem exists. | Redux/Zustand, shadcn/ui: named in an old plan, deliberately not migrated (`docs/TECH_STACK.md` note). |
| **react-pdf + mammoth + CodeMirror 6** | Page-by-page PDF rendering keeps browser memory sane on big academic PDFs; mammoth previews the *real* DOCX the reviewer will download; CodeMirror gives a proper editor, not a textarea. | — |
| **No database, no queue, filesystem only** | Phase 1 is single-user and local-first; a DB is infrastructure cost and attack surface with zero benefit yet. Jobs are tracked in memory; `outputs/` is the persistence layer. Docker exists as an *optional* hosting route. | PostgreSQL/Redis/Celery: explicitly excluded until a multi-user requirement actually exists. |
| **pytest (dual suite) + Jest + GitHub Actions** | Fast suite for iteration; real-OCR tests run in batches because they're the only ones that catch real extraction regressions. Frontend trio (tsc/Jest/build) verified green. | — |

---

## Will a better CPU / more RAM make it faster?

Yes for **machine minutes** — but unevenly, and not for what matters most. Runtime is dominated by local model inference, which on this CPU-only machine is cores-and-memory-bound.

**What improves (estimates; per-page numbers measured on the current box):**

| Work | Now | With stronger CPU + RAM | Why the gain looks like that |
|---|---|---|---|
| Primary OCR, PDF-only jobs (Docling+RapidOCR) | ~16 s/page end-to-end | roughly 1.5–3× faster | torch/onnxruntime already use all cores per page; gains are real but sublinear once memory bandwidth saturates |
| Surya-2 fallback OCR | 347.7 s/page | 2–3× faster — still minutes per page | llama.cpp generation is memory-bandwidth-bound: faster RAM helps nearly as much as more cores |
| Alt text (qwen2.5vl:3b via Ollama) | ~2.5 min/image | same class of gain as Surya | same llama.cpp inference path |
| Full pytest suite | run in batches | runs unbatched; real-OCR tests finish sooner | RAM headroom was the batching reason |
| Future local VLMs (GLM-OCR-class, 7B-class) | est. tens of s/page | faster — and bigger models become *loadable at all* | RAM decides which models are feasible; CPU decides their speed |

**What would NOT change:**

- **Output quality.** The bold-text OCR garbling is *model-limited*, not hardware-limited — the probe proved raising DPI didn't help but a different model read it perfectly. Faster hardware returns the same wrong text sooner.
- **Human review minutes** — the project's actual winner metric. Only better models, escalation, and verification shrink human time; hardware shrinks machine wait time around it.
- **The Mathpix path's recognition step** — that runs on Mathpix's cloud; local hardware affects only parsing, verification, and export.
- **Deterministic structure work** (headings, footnotes, tables, Markdown, DOCX, validation) — already fast; a negligible share of runtime.
- **Parallelism across pages/documents** — the pipeline is sequential; extra cores are used *within* each model's ops, not across jobs, unless the code learns to batch (a software change, not a purchase).

**The honest hierarchy of speedups:** GPU ≫ CPU+RAM upgrade > software batching > nothing. A modest GPU would do more for Surya-2, alt text, and any future VLM than any CPU money can buy — it's the one change that turns the ~6-min/page fallback into seconds. A CPU/RAM upgrade still helps everything on the box; it just doesn't change what's *possible*, only how fast the possible arrives.

---

## What it took to get here

| Dimension | Scale |
|---|---|
| Timeline & size | Started June 2026 · ~100 commits · 486 project files |
| Tests | **103 backend test files** — 2,537 passed / 5 known failures (CI 2026-09-28); frontend 15 suites / 45 tests, re-verified green locally 2026-10-05 |
| Decision record | **20 formal ADRs** + a decisions log with 25+ numbered entries, including documented reversals |
| Documentation | 60+ documents with a defined precedence order (`docs/DOCUMENTATION_MAP.md`) |
| Research | 3 research reports (2026 OCR model landscape, Mathpix replacement, and a full failure-case forensics study with hands-on probes: OCR DPI sweeps, engine timing, PDF vector analysis) |
| Regression discipline | bug_001–007 and feature_005–015 each get a root-cause audit with benchmark evidence |

---

## What's honest-but-imperfect today

- The PDF-only path has only one cross-source verifier (OCR text vs a GLM-OCR second reading); the others skip when no Mathpix source exists
- OCR garbles bold/italic text on some flattened PDFs — now detected and re-read by GLM-OCR with undoable auto-corrections; garbled headings are flagged, not repaired (`docs/OCR_QUALITY.md`)
- PDF-only documents don't get equations yet (Mathpix path does)
- Nothing deployed — packaging exists, hosting undecided

Full list: [techstack.md §10](techstack.md).

---

## Where to dig deeper

| Want… | Read |
|---|---|
| Stack + versions + licenses | [techstack.md](techstack.md) |
| What's actually built, phase by phase | `docs/PHASE_STATUS.md` |
| The reasoning behind every decision above | `docs/DECISIONS_LOG.md`, `docs/ADR_2026-07-19.md`, `docs/ADR_2026-08-03.md` |
| What's deliberately not built | `docs/KNOWN_LIMITATIONS.md` |
| How RAWRS learns from remediators (decisions, workspace edits, finished-in-Word diffs) | `docs/LEARNING_LOOP.md` |
| The OCR research | `docs/OCR_MATHPIX_REPLACEMENT_RESEARCH.md`, `docs/RAWRS_PDF_ONLY_RECONSTRUCTION_RESEARCH.md` |
