# RAWRS Project Context

> See `CURRENT_STATE.md` for what's actually implemented right now and `DOCUMENTATION_MAP.md` for which document governs which question.

Project Name:
RAWRS (Remediation Automation Workflow & Review System)

Organization:
WinVinaya Foundation

Status:
Architecture Frozen

Current Phase:
Phase 1

## Purpose

RAWRS is a local-first document remediation workstation designed to reduce repetitive remediation effort while preserving accessibility quality.

The system transforms educational and academic PDFs into structured outputs suitable for remediation workflows.

## Phase 1 Goal

PDF
→ Structured Markdown
→ Accessible DOCX

## Primary Users

* Document Remediators
* Accessibility Specialists
* QA Reviewers

## Core Principles

* Validation First
* Human Review
* Local First
* Accessibility Focused
* Auditability
* Model Agnostic
* No Vendor Lock-In

## Tech Stack

Frontend:

* React
* TypeScript
* Vite
* TailwindCSS
* shadcn/ui
* Zustand

Backend:

* FastAPI

Processing:

* Docling
* Surya OCR (CPU-based fallback, PyTorch inference — not Docling's only OCR path)
* PyMuPDF

DOCX:

* python-docx

**Note:** Frontend and Backend rows above describe the target stack. Neither has been started — there is no frontend directory and no FastAPI/server code anywhere in this repo as of this audit. RAWRS today is a Python pipeline invoked directly, not a served application. See `CURRENT_STATE.md`.

## Current Scope

Supported:

* OCR (direct extraction → Docling → Surya fallback; see `OCR_RULES.md`)
* Structure Detection (per-line bbox/font/bold persistence)
* Footnote/Endnote Detection & Preservation (not just detection — marker↔body linking into Markdown and DOCX)
* Reading Order Validation (flagging only — see "Not Supported")
* OCR Cleanup
* Header/Footer Removal
* Page Marker Detection
* Page Break Preservation
* Heading Detection
* Image Extraction & Filtering
* Figure Detection
* Alt-Text Infrastructure (deterministic placeholder + dataset logging — not generation)
* Metadata Capture
* Markdown Generation
* DOCX Generation

Not Supported:

* AI-Generated Alt Text (placeholder infrastructure is supported; model-generated descriptions are not)
* Reading Order Reconstruction/Correction (validation/flagging only)
* Cross-Page Paragraph Stitching
* Table Remediation
* Equation Remediation
* Multi-Column Reconstruction
* Accessibility Tagging
* Knowledge Graphs
* AI Training

Full per-item status with code citations: `PHASE_STATUS.md`. Full limitation detail: `KNOWN_LIMITATIONS.md`.

## Development Rules

* Do not redesign architecture.
* Do not modify folder structure.
* Do not introduce unnecessary frameworks.
* Build incrementally.
* Prefer maintainability over complexity.
* Shared models must be used across all modules.

## Current Development Target

Upload PDF
→ Process PDF
→ Generate Structure Tree
→ Generate Markdown
→ Generate DOCX
