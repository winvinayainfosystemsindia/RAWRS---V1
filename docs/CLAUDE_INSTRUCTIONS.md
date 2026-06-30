# Claude Code Instructions

You are contributing to the RAWRS project.

RAWRS stands for:

Remediation Automation Workflow & Review System

Before generating any code, always read:

1. RAWRS_PROJECT_CONTEXT.md
2. CURRENT_STATE.md
3. PHASE_STATUS.md
4. ARCHITECTURE.md
5. ARCHITECTURE_CURRENT.md
6. PHASE1_SCOPE.md
7. HEADING_RULES.md
8. PAGE_RULES.md
9. VALIDATION_RULES.md
10. OCR_RULES.md
11. TECH_STACK.md
12. KNOWN_LIMITATIONS.md
13. DECISIONS_LOG.md

These documents are the source of truth. See `DOCUMENTATION_MAP.md` for which document to trust when two of them appear to disagree (in short: `CURRENT_STATE.md`/`PHASE_STATUS.md`/`ARCHITECTURE_CURRENT.md` describe what's actually true today; the older rule/scope docs describe intent and are amended, not overridden, when code and doc disagree).

---

# Architecture Rules

Do not redesign architecture.

Do not modify folder structure.

Do not introduce new frameworks.

Do not introduce new services.

Do not introduce cloud dependencies.

Do not introduce databases.

Do not introduce agent frameworks.

Do not introduce unnecessary abstractions.

---

# Development Philosophy

Implement incrementally.

Prefer simple solutions.

Prefer maintainable code.

Prefer explicit logic over clever logic.

Prefer readability over optimization.

---

# Code Generation Rules

Generate production-ready code.

Generate modular code.

Generate typed code.

Generate testable code.

Generate docstrings.

Generate logging where appropriate.

---

# Data Model Rules

All modules must use shared models from:

src/models/

Do not create duplicate data structures.

Do not create module-specific document formats.

Use contracts.py as the canonical contract layer.

---

# Processing Rules

The canonical processing flow is:

PDF
→ Parser
→ OCR
→ Structure Detection
→ Footnote/Endnote Detection
→ Heading Detection
→ Image Extraction
→ Markdown Generation
→ Validation
→ DOCX Generation

Do not alter this workflow without updating both `ARCHITECTURE.md` and `ARCHITECTURE_CURRENT.md`. Note that the actual code today runs Image Extraction before Heading Detection and Validation after DOCX Generation — two tracked, deliberate deviations explained in `ARCHITECTURE_CURRENT.md` and `DECISIONS_LOG.md`, not an invitation to add a third without the same care.

---

# Phase 1 Scope

Phase 1 supports:

* OCR (direct extraction → Docling → Surya fallback)
* Structure Detection (per-line layout persistence)
* Footnote/Endnote Detection & Preservation
* Reading Order Validation (flagging only, not reconstruction)
* OCR Cleanup
* Header/Footer Removal
* Page Marker Detection
* Page Break Preservation
* Heading Detection
* Image Extraction & Filtering
* Figure Detection
* Alt-Text Infrastructure (deterministic placeholder + dataset logging only)
* Metadata Capture
* Markdown Generation
* DOCX Generation

Phase 1 does not support:

* AI-Generated Alt Text (the placeholder infrastructure above is in scope; model-generated descriptions are not)
* Reading Order Reconstruction/Correction
* Cross-Page Paragraph Stitching
* Table Remediation
* Equation Remediation
* Multi-Column Reconstruction
* Accessibility Tagging
* Knowledge Graphs
* AI Training

Do not implement out-of-scope features. Full current status: `PHASE_STATUS.md`.

---

# Testing Requirements

Every major module should have tests.

Do not generate code without considering tests.

Use the tests directory.

---

# Output Expectations

When asked to implement a feature:

1. Explain the implementation plan.
2. Identify affected files.
3. Generate code.
4. Explain how to test it.

Always preserve architecture consistency.
