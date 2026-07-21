"""FastAPI application entry point for the RAWRS API.

Run with: uvicorn src.api.main:app --reload --port 8000

CORS is open to the local Next.js dev server only - this is an
internal tool with no deployment story yet (docs/CURRENT_STATE.md: no
auth, no multi-tenant features, local-first), not a publicly-exposed
service, so a permissive local-only CORS policy is appropriate without
being a real security boundary that would need hardening later.
"""

import faulthandler
import sys

# Enable C-level crash interception before any C extension can be loaded.
# If the process receives a SIGSEGV or Windows access violation, Python
# prints a native-thread traceback to stderr before dying.  Does not fire
# on OOM kills (Windows TerminateProcess), but the absence of this output
# combined with an abrupt process death is itself evidence of OOM.
faulthandler.enable(file=sys.stderr, all_threads=True)

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from src.api.document_store import sweep_orphan_temp_files
    from src.api.jobs import load_persisted_jobs
    from src.ai.registry import init_ai

    # FE-0-001 — clear *.json.tmp left by a process killed mid-write.
    # Orphans are always safe to delete: a temp file only becomes
    # authoritative via os.replace(), so any survivor is a write that
    # never completed. Runs before load_persisted_jobs() so recovery
    # never sees them. Deliberately limited to temp artifacts — sidecar
    # lifecycle (retention, deletion) is out of scope for FE-0-001.
    sweep_orphan_temp_files()
    load_persisted_jobs()
    init_ai()  # resolves AI provider; never raises, never blocks on model load
    yield


app = FastAPI(
    title="RAWRS API",
    description="HTTP interface over RAWRS's existing PDF remediation pipeline.",
    version="0.1.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
