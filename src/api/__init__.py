"""HTTP API for RAWRS.

Wraps src/pipeline/phase1_pipeline.py::run_pipeline behind a FastAPI app
so a frontend can drive it over HTTP. Adds no new processing logic of
its own - this layer only accepts uploads, runs the existing pipeline
in a background thread (OCR can take minutes per page, far too slow
for a single request/response cycle), tracks per-document job state in
memory, and serves the pipeline's own output files back out. No
database, per docs/ARCHITECTURE.md's "no databases" constraint - job
state is intentionally ephemeral and lost on restart, acceptable for a
first internal tool, not a production guarantee.
"""
