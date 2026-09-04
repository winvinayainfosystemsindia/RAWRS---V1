# RAWRS — Remediation Automation Workflow & Review System

RAWRS is a local-first document remediation workstation built for WinVinaya Foundation. It reduces repetitive accessibility-remediation effort while preserving document quality, human control, auditability and reversible decisions.

It turns educational and academic PDFs into a structured document model that can be reviewed, validated and exported to accessible Markdown and DOCX.

> **Automation proposes. Validation decides. Humans make the judgement calls.**

---

## Status

| | |
| --- | --- |
| Phase | 1 |
| Architecture | Frozen |
| Deployment | Local application, single reviewer |
| Users | Document remediators, accessibility specialists, QA reviewers |

RAWRS is no longer a PDF-to-DOCX converter. The architecture centres on a canonical document model, semantic objects, a ContentStream, reversible correction records, live accessibility evaluation, benchmark-driven validation and a reviewer workspace.

The project is in an architectural convergence phase: most infrastructure exists, and the current work is making the semantic model, review workflow, readiness logic and output projections agree with each other.

---

## Pipeline

```
PDF
 ├── Native PDF parsing + OCR
 └── High-fidelity extraction package (Mathpix import)
                    ↓
         Canonical Document Model
   pages · paragraphs · headings · tables · figures
   notes · lists · front matter · reading order
   metadata · provenance
                    ↓
         Structure + Verification
   heading/table/figure/list/note detection
   artifact suppression · cross-source verification
                    ↓
         Review / Correction Layer
   findings · CorrectionRecords
   accept / reject / edit / ignore · reversible
                    ↓
      Accessibility Intelligence Engine
   score · category scores · blocking failures
   accessibility debt · export_ready
                    ↓
      Structured Markdown  +  Structured DOCX
```

**Markdown and DOCX are outputs, not the authoritative editing model.** The model owns meaning; projections render it. A projection must not invent semantic objects that do not exist in the model.

---

## Design principles

- **Validation first** — extraction and interpretation are provisional until validated.
- **Human in the loop** — RAWRS does not silently make decisions requiring accessibility expertise.
- **Local first** — Phase 1 runs on the filesystem. No database, cloud storage, queue or container requirement.
- **Model agnostic** — no dependency on a single AI vendor.
- **Auditability** — decisions retain evidence, provenance and review state.
- **Reversibility** — corrections preserve the original value and support undo.
- **Single source of truth** — shared semantic models live in `src/models/`; downstream systems consume the canonical model rather than inventing parallel representations.
- **Evidence over assumption** — benchmark documents verify architectural assumptions before implementation.

---

## Core concepts

### Canonical model
`Document`, `Page`, `TextBlock`, `Paragraph`, `Heading`, `Table`, `TableCell`, `Image`, `Figure`, `Footnote`, `Endnote`, `ListBlock`, `ListItem`, `Callout`, `FrontMatter`, `Metadata`, `CorrectionRecord`, `ValidationIssue`, plus evidence/provenance and reading-order state. Objects carry confidence, so downstream systems can distinguish source evidence from interpreted structure.

### ContentStream
The canonical ordered representation consumed by both projections, so Markdown and DOCX never independently rebuild document order.

### Correction rail
`ValidationIssue` is a diagnostic snapshot. `CorrectionRecord` is live, reversible review state. These are deliberately different things.

```
Finding → CorrectionRecord → Reviewer decision → Model mutation
        → ContentStream → Projection → Validation
```

Lifecycle: proposed, pending review, accepted, edited, rejected, ignored, auto-applied, reverted. Every reviewer decision should be traceable and reversible.

### Accessibility Intelligence Engine
Evaluates the **live** document state rather than frozen pipeline findings, producing an `AccessibilityReport` with overall score, category scores, evidence, blocking failures, accessibility debt and `export_ready`.

The project previously carried three competing readiness concepts — snapshot readiness from `ValidationIssue`, object-state readiness, and engine readiness. The architecture is converging on the engine as the single canonical authority.

### Export Ready
```
Export Ready  ⇔  zero live accessibility blockers
              AND all required reviewer decisions terminal
```
Terminal: accepted, edited, rejected, ignored, auto-applied. Non-terminal: proposed, pending review, reverted.

**Accessibility state** describes the document. **Workflow state** describes whether the human decisions are done. A document can be structurally accessible and still not export-ready.

---

## Reviewer workspace

Review surfaces cover headings, tables, images and alt text, footnotes, endnotes, reading order, metadata, page labels and cross-source corrections.

The workspace exists to reduce reviewer cognitive load, not to expose every diagnostic as an independent task. Benchmark investigation found that hundreds of findings can be duplicate verification mirrors rather than distinct reviewer actions — on one run, ~550 validation findings resolved to ~165 genuine actions, with ~385 mirrors. The UI separates **Action Required** from **Verification Findings** rather than deleting the evidence.

AI-assisted alt text is on-demand and reviewer-controlled, never applied in bulk.

---

## Technology

**Frontend** — React, TypeScript, Vite, TailwindCSS, shadcn/ui, Zustand, Lucide React, react-resizable-panels, react-pdf. Inter and JetBrains Mono.

**Backend** — FastAPI, Python 3.11+, Uvicorn, Pydantic, python-multipart.

**Document processing** — Docling, PyMuPDF. OCR: Docling primary, Surya fallback. DOCX via python-docx. Logging via Loguru.

**Quality** — pytest, pytest-cov, Black, Ruff, MyPy.

**Storage** — local filesystem. No Phase 1 database, cloud storage, vector store, Redis, Celery or container requirement.

---

## Benchmark corpus

Ten educational and academic PDFs with corresponding remediated DOCX targets, testing extraction quality, heading structure, lists, tables, notes, images, page preservation, validation, DOCX projection and accessibility readiness.

**The benchmark is an architectural feedback mechanism, not a test suite.** It has repeatedly prevented incorrect assumptions from becoming architecture — the native list detector was shown unreliable, readiness convergence was shown to have behavioural consequences, and scanned-page reconstruction images were identified as false content images.

---

## Measured current reality

These are conservative, measured findings from the latest audit. They are published deliberately.

| Area | Finding |
| --- | --- |
| Heading hierarchy | No H1 produced on 6 of 10 benchmark documents, while producing H2/H3 |
| Lists (native path) | No semantic lists across the corpus; 11 produced, all false positives, against 161 human-target list paragraphs |
| Lists (Mathpix path) | 204 DOCX list paragraphs against 161 targets — over-production with identity and projection problems. Exact text/order parity on Nature of Enquiry: 45/45 |
| Notes | 47 notes missed across two documents; detection depends too heavily on literal superscript glyphs |
| Scanned images | One document produced 112 page-reconstruction images into DOCX against a human target of 3 |
| Metadata / navigation | Audited DOCX lacked populated core properties, bookmarks, hyperlinks and TOC |
| Endnotes | Endnote materialisation verified successfully on benchmark material |

These are measured limitations, not claims that the architecture cannot solve them.

---

## What works today

Canonical semantic document model with stable object identity · ContentStream architecture · cross-source verification with multiple registered verifiers · reversible correction rail · live Accessibility Intelligence Engine with scoring and export-readiness · heading detection · paragraph grouping · front-matter extraction · image extraction and artifact filtering · table detection and rendering · page preservation · DOCX semantic heading and table rendering · note type representation · endnote detection and materialisation · benchmark corpus and regression harness · reviewer correction workflows.

The engineering direction has shifted from *build more infrastructure* to *make existing infrastructure produce the remediation decisions reviewers actually need*.

---

## Gaps, by class

Each class needs a different fix, which is why they are tracked separately.

**Semantic model gaps** — the model cannot yet express list item identity, list numbering start/restart, list placement, figure-caption identity, image ordering, document-title identity, endnote section identity, span-level typography, hyperlinks, bookmarks, TOC, document language, or provenance for generated editorial content.

**Projection gaps** — the model knows it, the projection doesn't consume it: DOCX metadata, list nesting, some note information, image metadata, some ContentStream paths.

**Extraction gaps** — never becomes a semantic object at all: blockless scanned pages, some note markers, reliable native list detection.

---

## Next milestone — lists as a remediable object

Give `ListItem` semantic identity; add list create/update/delete operations; add a list correction type and verifier; let reviewers build a list from selected paragraphs; allow list type and item level correction; render from `LIST` ContentStream nodes; preserve nesting from the recorded level; validate list-shaped paragraphs lacking a `ListBlock`.

**Explicit non-goals:** promoting the native geometric detector, numbering start/restart, mixed-type nesting, lists in table cells, rebuilding the Mathpix rendering path, bookmarks/TOC.

**Deferred deliberately:** bookmarks, TOC, hyperlinks, a third output projection, equation/STEM support, a separate Caption object, automatic reading-order reconstruction, cross-page table detection, and anything that makes byte-identical DOCX a quality gate again.

---

## Scope

**In Phase 1** — OCR, reading-order analysis, OCR cleanup, header/footer removal, page markers, page-break preservation, heading detection, image extraction, figure detection, metadata capture, Markdown and DOCX generation, tables, notes, lists, cross-source verification, accessibility evaluation, human review.

**Out of Phase 1** — unattended alt-text automation, equation and STEM remediation, PDF/UA tag-tree generation, model training, knowledge graphs, multi-agent architecture, cloud infrastructure, database-backed or multi-tenant deployment, collaborative multi-reviewer workflow.

---

## Engineering workflow

```
Repository investigation → Runtime verification → Benchmark validation
→ Architecture review → Implementation plan → Small implementation
→ Regression validation → Commit
```

**Do:** use shared models from `src/models/`; keep business logic in one authoritative location; preserve evidence and provenance; make reviewer changes reversible; add tests for major modules; validate against the benchmark; prefer deterministic logic.

**Don't:** redesign the architecture casually; add frameworks, cloud services, databases or agent frameworks; duplicate shared models; create module-specific document formats; make silent semantic mutations; treat Markdown or DOCX as authoritative; trust extraction without validation.

A green test suite is not sufficient if benchmark output quality regresses.

---

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements-dev.txt
pip install -r requirements-ai.txt   # optional — AI alt text / table analysis

uvicorn src.api.main:app --reload

cd frontend && npm install && npm run dev
```

Direct pipeline use:

```python
from src.pipeline.phase1_pipeline import run_pipeline

result = run_pipeline(pdf_path="path/to/file.pdf", output_root="outputs/")
result = run_pipeline(pdf_path="path/to/file.pdf", mmd_path="path/to/file.mmd", output_root="outputs/")
```

Benchmark PDFs and Mathpix DOCX exports are **not committed** (copyrighted academic papers). Expected outputs and the manifest are included; place matching PDFs in `samples/benchmark/pdfs/` to run the full suite.

---

## Philosophy

RAWRS does not optimise for automation percentage. It optimises for **human minutes per 100 pages** while maintaining trustworthy accessibility quality.

A good result is not "AI changed 95% of the document." A good result is: the document is structurally correct, the remaining decisions are visible, the reviewer can resolve them quickly, and every important decision is traceable.

The long-term direction is an **Accessibility Decision Support Platform** where the reviewer workspace is the primary interface, rather than deep remediation happening in exported DOCX files.

---

## Reference documents

`RAWRS_PROJECT_CONTEXT.md` · `ARCHITECTURE.md` · `PHASE1_SCOPE.md` · `HEADING_RULES.md` · `PAGE_RULES.md` · `VALIDATION_RULES.md` · `OCR_RULES.md` · `TECH_STACK.md` · `CLAUDE_INSTRUCTIONS.md`

Consult the latest product audits and milestone investigations before implementing changes.

---

## Maintainer note

Investigate before coding. Measure against the benchmark. Find the canonical owner. Reuse existing infrastructure. Make the smallest coherent change. Validate before claiming success. Do not hide uncertainty. Do not confuse infrastructure progress with remediation progress.

RAWRS should become simpler and more trustworthy as it grows, not merely larger.
