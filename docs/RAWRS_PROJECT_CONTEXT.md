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

Frontend (built, `frontend/`):

* Next.js (App Router) + React
* TypeScript
* Tailwind CSS
* React Context (`frontend/lib/store/`)
* react-pdf, react-resizable-panels

Backend (built, `src/api/`):

* FastAPI + Pydantic

Processing:

* Docling
* Surya OCR (CPU-based fallback, PyTorch inference — not Docling's only OCR path)
* PyMuPDF

DOCX:

* python-docx

**Note (2026-09-16):** the frontend was originally planned on Vite + Zustand + shadcn/ui. It was built on Next.js + React Context, and that built stack is the decided one — no migration. Full table and rules: `TECH_STACK.md`; decision: `DECISIONS_LOG.md` Part 25.

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

Not in the original Phase 1 scope (items marked *built* were delivered later — see `PHASE_STATUS.md`; do not re-implement them):

* AI-Generated Alt Text — *built* as on-demand, human-reviewed proposals (FEATURE_012)
* Automatic Reading Order Reconstruction (human-initiated correction is *built*, 016B; automatic reordering is not)
* Cross-Page Paragraph Stitching
* Table Remediation — *built* (FEATURE_015, 015.3)
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
