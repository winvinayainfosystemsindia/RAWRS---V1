# RAWRS API image.
#
# Targets Oracle Cloud's Always Free Ampere shape (aarch64), and builds on
# x86_64 unchanged. Python is pinned to 3.11 to match the development
# interpreter (3.11.14).
#
# torch is installed from PyTorch's CPU index rather than PyPI: the default
# PyPI wheel on x86_64 drags in ~2.5 GB of CUDA runtime that this deployment
# has no GPU to use. On aarch64 the wheels are CPU-only either way, so the
# index is correct on both architectures.
#
# torch is NOT optional despite living in requirements-ai.txt — docling
# imports it directly (see that file's own note), so an image built from
# requirements.txt alone would fail at import time, not at first AI call.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/outputs/.cache/huggingface

# libgl/libglib: PyMuPDF and docling's image handling need them at import
# time. curl is here for the healthcheck below.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-ai.txt ./
RUN pip install --upgrade pip \
    && pip install --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.txt -r requirements-ai.txt

COPY src/ ./src/

# Job records, document sidecars and every extracted image/DOCX/markdown live
# here. Mounted as a named volume by docker-compose so a rebuild does not
# discard a reviewer's work.
RUN mkdir -p /app/outputs
VOLUME ["/app/outputs"]

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8001/api/health || exit 1

# One worker on purpose: src/api/jobs.py keeps job state in memory with JSON
# sidecars, so a second worker would serve a different view of the same jobs.
# Horizontal scaling needs a shared store first — see docs/DEPLOYMENT.md.
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
