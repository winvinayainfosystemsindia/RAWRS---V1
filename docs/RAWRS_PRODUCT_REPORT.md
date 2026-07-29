# RAWRS — Product Report

**RAWRS — Remediation & Accessibility Work Reduction System**
*An intelligent accessibility review platform*

---

## 1. Executive Summary

RAWRS is an intelligent accessibility review platform that turns inaccessible source documents — primarily PDFs — into standards-compliant, screen-reader-ready outputs, while keeping a qualified human reviewer in control of every accessibility decision.

Document accessibility remediation is traditionally slow, manual, and expensive. A single scanned or born-digital PDF can take hours of specialist effort to convert into a properly tagged, navigable, screen-reader-friendly document. RAWRS attacks the *effort*, not the *judgement*: it automates the repetitive, mechanical work — extraction, structure detection, verification, scoring — and presents the reviewer with a focused, prioritized set of decisions rather than a blank page.

The product is built on a clear philosophy:

- **Automation performs the repetitive work.**
- **Humans make the accessibility decisions.**
- **The system minimizes reviewer effort rather than replacing reviewers.**

Every automated action is proposed, never silently imposed. Every proposed change preserves the original value, is reversible, and is recorded in an audit trail. The result is a platform that is fast, transparent, and trustworthy — three properties that accessibility work has historically had to trade off against one another.

RAWRS today is a working, benchmark-validated system with a complete ingestion-to-export pipeline, a transparent accessibility scoring engine, and a full human-review workspace. Its trajectory is to converge into a single, authoritative accessibility platform where experts review, edit, validate, remediate, and export accessible documents from one place.

---

## 2. Problem Statement

Accessibility remediation is a high-stakes, high-effort discipline:

- **Regulatory pressure is rising.** WCAG 2.x, PDF/UA, Section 508 (US), and EN 301 549 (EU) impose real obligations on universities, publishers, government bodies, and enterprises. Non-compliance carries legal and reputational risk.
- **The work is manual and slow.** Making a document accessible means identifying its true reading order, heading hierarchy, tables, figures, alt text, language, and metadata — then correcting each one. Existing tools automate fragments of this and leave the rest to specialists.
- **Automated tools are untrustworthy at the decision layer.** Fully automatic remediation routinely makes confident but wrong choices — mislabeling a caption as a heading, inventing alt text, or scrambling reading order — with no visible signal that anything went wrong. For a compliance tool, *failing silently while claiming success* is the worst possible outcome.
- **Volume overwhelms reviewers.** A real document generates hundreds of potential findings. Presented as a flat list, this buries the handful of genuine decisions under noise and drives reviewers toward rubber-stamping.

The core problem RAWRS solves: **how to make accessibility remediation dramatically faster without surrendering human control or hiding uncertainty.**

---

## 3. What RAWRS Is Today

RAWRS is a document accessibility platform that ingests a source document, reconstructs its true semantic structure, verifies that structure against independent evidence, scores its accessibility, and hands the reviewer a prioritized, low-effort workspace to make and apply corrections — then exports a clean, accessible result.

It is best understood as three cooperating systems:

1. **A deterministic processing pipeline** that extracts and reconstructs document structure from the source.
2. **An accessibility intelligence layer** that verifies, scores, and gates the document against accessibility standards.
3. **A human review workspace** where a specialist reviews proposed corrections, edits object-level content, and drives the document to an export-ready state.

Crucially, RAWRS operates on a **canonical document model** — a single, structured representation of the document's headings, paragraphs, tables, figures, footnotes, lists, metadata, and reading order. Markdown and DOCX are *outputs* generated from this model, not the thing being edited. This model-centric design is what makes verification, scoring, and reversible correction possible.

---

## 4. How RAWRS Works

RAWRS processes a document through a sequence of deterministic stages, then opens it for human review.

**Ingestion and extraction.** RAWRS accepts a source PDF. It supports two extraction paths:

- A **high-fidelity import path**, in which a pre-processed extraction package (text, structure, tables, figures, and mathematical content in a rich Markdown form) is imported and reconciled against the PDF.
- A **native extraction path**, in which RAWRS parses the PDF directly and applies OCR to pages that require it, using a primary OCR engine with an automatic fallback engine for anything the first leaves unrecovered.

**Structural reconstruction.** RAWRS rebuilds the document's semantic structure: heading levels and hierarchy, paragraphs and reading order, tables (including borderless and academic-style tables), figures and captions, footnotes and endnotes, lists, callouts, and front-matter (title, authorship, affiliations). It also detects page-level artifacts such as printed page numbers and page markers.

**Cross-source verification.** Where two independent views of the document exist — the imported extraction and the PDF itself — RAWRS reconciles them. Disagreements (a heading whose level differs between sources, a table whose structure doesn't match, a figure that appears in one source but not the other) become *proposed corrections* for a human to accept or reject, rather than silent automatic edits.

**Accessibility evaluation.** The document is evaluated against a set of accessibility rules covering language, headings, images/alt text, tables, reading order, and metadata. This produces an accessibility score with a fully traceable breakdown and a hard **Export Ready** gate.

**Human review.** The reviewer works through a focused workspace: accepting or rejecting proposed corrections, writing or approving alt text, confirming table headers and captions, fixing reading order, setting document language and title, and reviewing headings and footnotes. Live scoring reflects the state of the work.

**Export.** RAWRS generates accessible Markdown and a semantically structured DOCX (real heading styles, structured tables, embedded and described images, traversable notes) from the reviewed document model. Outputs regenerate automatically as the reviewed document changes.

Throughout, the guiding rule holds: automation proposes, the human decides, and nothing is destroyed — the original value of every corrected element is preserved and every change is reversible.

---

## 5. Current Product Capabilities

The following capabilities are implemented and operational today.

| Capability | What it does |
|---|---|
| **PDF ingestion** | Accepts source PDFs through either a high-fidelity extraction-package import or native parsing. |
| **OCR & document extraction** | Recovers text from image-only and scanned pages using a primary OCR engine with an automatic fallback for unrecovered content. |
| **Structural analysis** | Reconstructs reading order, paragraph and block structure, and front-matter (title, authors, affiliations). |
| **Heading detection** | Identifies heading levels and hierarchy, including repaired wrapped/continued headings and printed page-number preservation. |
| **Table detection** | Detects bordered, borderless, and academic-style tables, including merged cells and header rows; supports manual table creation. |
| **Figure & image detection** | Extracts embedded content images, links captions, and prepares figures for alt-text review. |
| **Scanned-page reconstruction detection** | Recognizes scanned pages stored as tiled raster bands and filters them out so they aren't mistaken for content figures. |
| **Mathematical content handling** | Preserves and transforms mathematical/LaTeX content carried in the high-fidelity extraction package, keeping equations intact through to output. |
| **Cross-source verification** | Reconciles the imported extraction against the PDF, surfacing structural disagreements as reviewable proposals. |
| **Accessibility verification** | Evaluates the document against accessibility rules for language, headings, images, tables, reading order, and metadata. |
| **Validation reporting** | Generates a categorized, severity-ranked list of validation findings for reviewer triage. |
| **Correction workflow** | Manages proposed corrections through an accept / reject / edit / ignore / undo lifecycle, preserving the original value and a full audit trail. |
| **Accessibility Intelligence Engine** | Produces a live, evidence-backed accessibility evaluation of the current document state. |
| **Accessibility scoring** | Computes a weighted score with a transparent, line-by-line point breakdown and an accessibility-debt summary — no black-box percentages. |
| **Readiness reporting** | Provides a single **Export Ready** signal that combines accessibility correctness with reviewer completion. |
| **Review workspace** | Offers dedicated review surfaces for headings, tables, images/alt text, footnotes, reading order, metadata, page labels, and cross-source corrections. |
| **Human review workflow** | Tracks per-object review states (for example, multi-state alt-text review) so progress and decisions are explicit and durable. |
| **AI-assisted alt text** | Generates draft alt text on demand for a reviewer to approve or replace; optional and never auto-applied. |
| **DOCX generation** | Produces a semantically structured Word document with real heading styles, structured tables, embedded images, and traversable notes. |
| **Markdown generation** | Produces clean, structured Markdown as the canonical text representation of the reviewed document. |
| **Benchmark-driven validation** | Validates behavior against a curated corpus of real documents used as ground truth. |
| **Deterministic, reversible processing** | Runs a repeatable pipeline whose automated outputs are all proposals, all reversible, and all recorded. |

---

## 6. Current Architecture Overview (High Level)

RAWRS is organized around a single **canonical document model** and a strict separation between automated processing and human decision-making.

- **Input layer.** Two ingestion paths feed the same model: a high-fidelity extraction-package import and a native PDF-parsing-plus-OCR path. Both converge on one structured representation, so everything downstream is source-agnostic.
- **Processing pipeline.** A deterministic sequence of stages reconstructs structure (headings, tables, figures, footnotes, lists, reading order, front-matter) and runs cross-source verification. The pipeline is repeatable and does not mutate the document based on low-confidence guesses — uncertain reconciliations become proposals.
- **Accessibility intelligence layer.** A rules-based engine evaluates the live document against accessibility standards, producing a transparent score, an accessibility-debt view, and a hard export-readiness gate. Evaluation reads the *current* state of the document and its review decisions, so it always reflects the latest human work.
- **Correction and review layer.** Cross-source disagreements and object-level issues are represented as durable, reversible records with a preserved original value and a decision history. This is the authoritative trail of what the automation proposed and what the human decided.
- **Review workspace (frontend).** A reviewer-facing workspace surfaces prioritized work across dedicated panels, shows live accessibility scoring, and lets reviewers act with minimal effort.
- **Output layer.** Accessible Markdown and semantically structured DOCX are generated from the reviewed model and regenerate as the model changes.

Two architectural principles define the system: **deterministic processing** (repeatable, explainable, non-destructive) and **human-in-the-loop control** (automation proposes; humans decide; nothing is lost).

---

## 7. Current Competitive Advantages

- **Cross-source verification.** Rather than trusting a single extraction, RAWRS reconciles two independent views of the document and turns their disagreements into explicit, reviewable decisions. This directly targets the failure mode that undermines other tools: confident, invisible errors.
- **Human-in-the-loop by design.** Automation never silently overrides a human. Every automated conclusion is a proposal with preserved evidence and a reversible outcome, which makes the tool safe to trust in a compliance setting.
- **Transparent, traceable scoring.** The accessibility score is not a black-box percentage; it is a line-by-line ledger of what was checked, what was lost, and what fixing each item would recover. Reviewers and auditors can see exactly why a document scores what it does.
- **A single, honest readiness signal.** Export readiness combines accessibility correctness with reviewer completion, so "ready" means genuinely ready — not "ready except for the decisions nobody made."
- **Non-destructive and auditable.** Original values are always preserved and every change is recorded and reversible, producing a defensible audit trail suitable for regulated environments.
- **Deterministic and benchmark-validated.** Behavior is repeatable and continuously checked against a corpus of real documents, so quality is measured rather than asserted.
- **Effort reduction as the explicit goal.** The product is designed to minimize reviewer workload — prioritizing genuine actions and separating them from informational noise — rather than to maximize automation for its own sake.

---

## 8. Current Limitations

RAWRS is honest about its current boundaries. The following are known, deliberate, or in-progress limitations rather than hidden gaps.

- **Native mathematical/equation detection is not built.** Mathematical content is preserved when it arrives through the high-fidelity extraction package; RAWRS does not yet detect equations directly from raw PDF geometry.
- **Multi-column and cross-page reconstruction are limited.** Automatic multi-column reflow, cross-page paragraph stitching, and cross-page table joining are not yet implemented; these cases rely on the reviewer.
- **Reading-order correction is human-initiated.** RAWRS detects reading-order anomalies but does not automatically reorder content; reordering is a deliberate reviewer action.
- **AI alt text is on-demand, not automatic.** Draft alt text is generated only when a reviewer requests it and is always subject to human approval; automatic bulk generation is intentionally not enabled.
- **DOCX notes are not native Word footnote elements.** Notes are preserved as real, traversable references, but not as Word's built-in footnote/endnote objects that some downstream tooling specifically expects.
- **Single-reviewer scale.** The workspace is designed for one reviewer per document at a time; multi-reviewer, high-concurrency collaboration is not yet a first-class capability.
- **PDF/UA tag-tree export is out of current scope.** RAWRS produces accessible Markdown and structured DOCX; emitting a fully tagged PDF/UA artifact is a future consideration, not a current feature.
- **Editing still largely happens on exported outputs.** Rich, in-place editing of the document model inside RAWRS is an active roadmap item; today, deeper edits are often completed in the exported DOCX.

---

## 9. Product Roadmap

The roadmap advances a consistent thesis: converge on one authoritative model, let reviewers do everything in one place, and keep reducing the effort each decision requires.

### Short-term

- **Converge on a single readiness authority.** Complete the transition to one canonical accessibility-and-readiness evaluation, retiring duplicated or legacy readiness calculations so the whole product speaks with one voice about whether a document is ready.
- **Formalize Export Ready semantics.** Define readiness explicitly as the combination of *accessibility correctness* and *reviewer-workflow completion*, so a document is "ready" only when both the standards are met and the human decisions are made.
- **Intelligent grouping of related issues.** Reduce reviewer workload by grouping related findings into coherent decisions instead of presenting hundreds of independent items.

### Medium-term

- **Intelligent Document Artifact Detection.** Automatically identify recurring, non-content artifacts — repeated headers and footers, running titles, page numbers, recurring publisher text, watermarks, and repeated scanning artifacts — and hide them by default, while always allowing the reviewer to restore any of them. Nothing is ever permanently deleted automatically.
- **In-platform structured editing.** Transform RAWRS from a document generator into a document editing platform. Reviewers will edit headings, paragraphs, tables, images, captions, alt text, lists, and accessibility metadata directly inside RAWRS, operating on the document model itself. Markdown and DOCX become outputs of this editing process rather than the interface for it.
- **Live accessibility feedback while editing.** Accessibility scoring and verification update dynamically as reviewers make changes, so the impact of every edit is visible immediately.
- **Continued backend convergence.** Keep eliminating duplicated ownership of business rules and consolidating them into single, authoritative implementations.

### Long-term

- **A unified accessibility review workspace.** Redesign the reviewer experience around low cognitive load, keyboard-first workflows, batch review, structured editing, and one unified accessibility report.
- **Accessibility Decision Support Platform.** Evolve RAWRS from a remediation tool into the central workspace where accessibility experts review, edit, validate, remediate, and export accessible documents — a decision-support environment, not just a converter.

---

## 10. Future Vision

The long-term vision for RAWRS is to become an **Accessibility Decision Support Platform**: the single environment an accessibility specialist opens to take a document from "inaccessible source" to "verified, accessible, exportable result."

In that future, RAWRS is not a step in a toolchain but the workspace itself. A reviewer ingests a document and immediately sees a structured, verified model with a transparent accessibility score. Recurring artifacts are already tidied away but recoverable. Proposed corrections are grouped into a small number of meaningful decisions. The reviewer edits the document model directly — fixing a heading, rewriting alt text, restructuring a table — and watches the accessibility score and readiness signal respond live. When the document is genuinely ready, they export a clean, accessible result with a complete, auditable record of every decision made along the way.

The measure of success is not how much RAWRS automates, but how little effort a human expert has to spend to reach a confidently correct, standards-compliant outcome.

---

## 11. Why RAWRS Is Different

- **It reconciles evidence instead of trusting one source.** By cross-checking two independent extractions, RAWRS surfaces exactly the discrepancies that other tools silently get wrong.
- **It keeps humans in control without slowing them down.** Automation clears the repetitive work and hands the reviewer a prioritized, low-effort set of real decisions — control without drudgery.
- **It is transparent by construction.** The score is a visible ledger, readiness is an honest combined gate, and every automated action is a reversible proposal with preserved evidence.
- **It is safe for compliance.** Nothing is destroyed, everything is recorded, and the system is built to never present "failed" as "clean."
- **It measures itself.** Benchmark-driven validation against real documents means quality is demonstrated, not claimed.

Where most tools optimize for automation percentage, RAWRS optimizes for **trustworthy outcomes with minimal human effort** — a fundamentally different product goal.

---

## 12. Potential Real-World Applications

- **Higher education.** Universities remediating lecture notes, course packs, journal articles, and theses for students with disabilities, under Section 508 / EN 301 549 / WCAG obligations.
- **Academic and scholarly publishing.** Publishers converting article and book back-catalogs — including scanned and math-heavy material — into accessible formats at scale.
- **Government and public sector.** Agencies with statutory accessibility duties for public-facing documents, where auditability and defensible records matter.
- **Legal and regulated industries.** Organizations that must make contracts, filings, and reports accessible while preserving a verifiable trail of every change.
- **Corporate accessibility teams.** In-house teams standardizing document accessibility across large internal document estates.
- **Libraries, archives, and digitization programs.** Institutions turning scanned historical and reference collections into structured, screen-reader-navigable documents.
- **Accessibility service providers.** Specialist vendors seeking to increase reviewer throughput without compromising quality or auditability.

---

## 13. Conclusion

RAWRS exists because accessibility remediation has been forced to choose between speed, control, and trust — and organizations should not have to. By automating the repetitive work, reconciling independent evidence, scoring transparently, and keeping a human in control of every meaningful decision, RAWRS delivers all three at once.

Today, RAWRS is a working, benchmark-validated platform that carries a document from ingestion through structural reconstruction, cross-source verification, accessibility scoring, human review, and accessible export. Its direction is clear and already in motion: converge on one authoritative accessibility model, bring editing and live feedback directly into the platform, intelligently reduce reviewer effort, and grow into a full Accessibility Decision Support Platform.

The destination is a single, trusted workspace where accessibility experts do their entire job — review, edit, validate, remediate, and export — with less effort and more confidence than any current alternative allows. RAWRS is not just making documents accessible; it is redefining how accessibility work gets done.
