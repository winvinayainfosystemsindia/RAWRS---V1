# RAWRS Tech Stack

> **Implementation status (reconciled 2026-09-16, `DECISIONS_LOG.md` Part 25):** the Frontend and Backend sections below describe the stack that is **built and in use** (`frontend/package.json`, `requirements.txt`). The frontend was built on Next.js + React Context rather than the originally planned Vite + Zustand + shadcn/ui + Lucide, and that built stack is now the decided stack — do not migrate it. The Code Quality section (Black/Ruff/MyPy) is still aspirational — none of the three are installed or configured. See `CURRENT_STATE.md` for the installed dependency list.

## Philosophy

Technology choices must prioritize:

* Simplicity
* Maintainability
* Accessibility
* Local-first operation
* Low operational cost
* Long-term flexibility

Avoid unnecessary complexity.

---

# Frontend

| Concern | Choice | Where |
|---|---|---|
| Framework | Next.js 16 (App Router) + React 19 | `frontend/app/` |
| Language | TypeScript | |
| Styling | Tailwind CSS 4 + semantic theme tokens (light/dark) | `frontend/app/globals.css`, `frontend/lib/theme/` |
| State | React Context + `useReducer` | `frontend/lib/store/` |
| UI components | Project components (no component library) | `frontend/components/` |
| Icons | Project SVG icons | `frontend/components/icons.tsx` |
| Panel layouts | react-resizable-panels | `frontend/components/workspace/WorkspaceShell.tsx` |
| PDF viewer | react-pdf (one page rendered at a time) | `frontend/components/PdfViewer.tsx` |
| DOCX preview | mammoth | `frontend/components/DocxPreview.tsx` |
| Markdown view | CodeMirror, read-only (Markdown is a projection, never edited) | `frontend/components/MarkdownEditor.tsx` |
| Tests | Jest + Testing Library + jest-axe | `frontend/__tests__/` |
| Typography | Inter (UI), JetBrains Mono (technical/evidence) | `frontend/app/layout.tsx` |

Rules:

* **No framework migration.** Do not move to Vite, Zustand, or a shadcn/ui rewrite because an older document named them.
* Lucide or shadcn/ui may be introduced for a single component only when a concrete UI need justifies it.
* Do not add a state library or split Contexts without a measured performance problem.
* Export readiness, and safe-vs-semantic classification of a proposed correction, come from the backend; the frontend displays them and never computes them.

Application UI styling is separate from generated-document styling (Times New Roman, `HEADING_RULES.md`).

---

# Backend

Framework:

FastAPI

Language:

Python 3.11+

Server:

Uvicorn

Validation:

Pydantic

File Uploads:

python-multipart

---

# Document Processing

Primary Engine:

Docling

Fallback Engine:

Surya OCR (version 0.20.0, pinned in `requirements.txt`) - a vision-language-model-backed OCR engine. On this project's CPU-only deployment it auto-selects a `llamacpp` inference backend and runs inference by spawning the upstream `llama-server` binary against the `surya-2.gguf` model. This requires `llama-server` to be installed/resolvable on the host (e.g. via `LLAMA_CPP_BINARY`) - it is a real external runtime prerequisite, not an internal Python dependency. See `OCR_RULES.md` and `DECISIONS_LOG.md` for the full backend trace.

Responsibilities:

* OCR
* Layout Understanding
* Structure Detection
* Reading Order

---

# PDF Utilities

Library:

PyMuPDF

Responsibilities:

* PDF Inspection
* Page Handling
* Metadata Access
* Image Access

---

# DOCX Generation

Library:

python-docx

Responsibilities:

* DOCX Creation
* Style Application
* Heading Mapping
* Page Break Insertion
* Image Placement

---

# Logging

Library:

Loguru

Responsibilities:

* Pipeline Logs
* Processing Logs
* Error Logs

---

# Testing

Framework:

Pytest

Coverage:

pytest-cov

---

# Code Quality

Formatter:

Black

Linter:

Ruff

Type Checking:

MyPy

---

# Storage

Phase 1 Storage:

Local Filesystem

No Database.

No Cloud Storage.

No Vector Database.

---

# Deployment

Phase 1:

Local Application

Single User

No Authentication

No Multi-Tenant Features

---

# Explicitly Excluded

* Docker (exception: the `Dockerfile`/`docker-compose.yml` exist only for the optional zero-cost hosted deployment in `DEPLOYMENT.md`; local use needs neither)
* Kubernetes
* Redis
* MongoDB
* PostgreSQL
* Celery
* LangChain
* Agent Frameworks
* Vector Databases

These are unnecessary for Phase 1.

---

# Guiding Principle

Prefer the simplest technology that reliably solves the problem.
