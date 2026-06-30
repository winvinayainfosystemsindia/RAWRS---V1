"""FastAPI application entry point for the RAWRS API.

Run with: uvicorn src.api.main:app --reload --port 8000

CORS is open to the local Next.js dev server only - this is an
internal tool with no deployment story yet (docs/CURRENT_STATE.md: no
auth, no multi-tenant features, local-first), not a publicly-exposed
service, so a permissive local-only CORS policy is appropriate without
being a real security boundary that would need hardening later.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router

app = FastAPI(
    title="RAWRS API",
    description="HTTP interface over RAWRS's existing PDF remediation pipeline.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
