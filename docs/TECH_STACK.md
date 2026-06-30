# RAWRS Tech Stack

> **Implementation status:** Everything in the Frontend and Backend sections below is the *target* stack and has not been started — no frontend directory, no `package.json`, no FastAPI/Uvicorn code or dependency anywhere in this repo as of this audit. The Document Processing, PDF Utilities, and DOCX Generation sections are accurate and implemented. The Code Quality section (Black/Ruff/MyPy) is also aspirational — none of the three are installed or configured (`requirements-dev.txt` has only `pytest`/`pytest-cov`). See `CURRENT_STATE.md` for the actually-installed dependency list.

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

Framework:

React

Language:

TypeScript

Build Tool:

Vite

Styling:

TailwindCSS

UI Components:

shadcn/ui

State Management:

Zustand

Icons:

Lucide React

Panel Layouts:

react-resizable-panels

PDF Viewer:

react-pdf

Typography:

Inter

JetBrains Mono

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

* Docker
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
