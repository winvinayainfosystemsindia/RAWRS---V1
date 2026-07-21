# FE-0-003 — Accepted corrections reach the reviewer's output

**Date:** 2026-07-22 · **Branch:** `fe-0-001-persistence-and-cleanup`
**Status:** ✅ **COMPLETE** (Phases 1–2 shipped; Phase 3 evaluated and rejected)

---

## The ticket premise was wrong

FE0_VERIFICATION_REPORT_2026-07-19 recorded: *"Accepted corrections never reach the output; no regenerate endpoint exists."* Live investigation disproved the first half.

Accepting `HEADING_VERIFY_004` on a 4-page document, then reading each surface:

| Surface | Line 11 after Accept | Verdict |
|---|---|---|
| `GET /download/markdown` | `## Rohit Dhankar` | ✅ correction applied |
| `GET /download/docx` | regenerated, 42,538 bytes | ✅ correction applied |
| `GET /markdown` *(preview)* | `## "There is nothing more practical than theory." - Boltzmann` | ❌ stale |

The download handlers already regenerated on demand via `_needs_export_regen`. The **preview** endpoint (`routes.py:829`) read the static pipeline-time file unconditionally. The original repro checked the preview and generalised to the deliverables. Deliverables were always correct.

This halved the work and eliminated the proposed `POST /regenerate` endpoint entirely.

## Defects found

| ID | Defect | Effect | Phase |
|---|---|---|---|
| D1 | Preview served the static file, never regenerated | Accept appeared to do nothing — the entire perceived bug | 1 |
| D2 | `*_generated_at_version` never advanced | Exports labelled "(stale)" permanently, even when current | 2 |
| D3 | Regen wrote `NamedTemporaryFile(delete=False)`, never cleaned | One leaked temp file per download (measured: 3 → 3) | 2 |

## What shipped

**Phase 1** — `get_markdown` adopts `_needs_export_regen`; regenerates on divergence. Response schema and 404 behaviour unchanged. Build outside `_lock`; failure falls back rather than 500s.

**Phase 2** — `_ensure_current_export(job, kind)` shared by preview and both downloads, driven by an `_EXPORT_SPECS` table. Regenerate-and-cache keyed on `document.version`: at most one rebuild per version, not per request. Atomic writes (temp → `fsync` → `os.replace`) reusing `document_store._replace_with_retry`. Markers advance on success only. `tempfile` import removed.

**Architectural decision (approved):** the persisted Document is canonical; the pipeline-time artifact is a cache of it, overwritten in place. The "pre-review backup" framing in the old `download_docx` comment is retired.

### Live verification

| Check | Result |
|---|---|
| Marker before preview | `version=1, md_at=null` → stale |
| Marker after preview | `version=1, md_at=1` → **up to date** |
| Cached read | **9 ms** (was 110 ms rebuilding every request) |
| Preview == download | **True** |
| Line 11 | `## Rohit Dhankar` |

D2 closed with **zero frontend changes** — the existing `*_generated_at_version !== document_version` comparisons started telling the truth the moment markers advanced.

## Phase 3 — evaluated and rejected

**Proposal:** persist `markdown/docx_generated_at_version` through the checkpoint so markers survive restart, removing one rebuild per artifact.

**Implemented, unit-tested (7/7 passing), then rejected on production verification.**

| Step | Result |
|---|---|
| In-memory before restart | `version=1, md_at=1` ✅ |
| Checkpoint on disk | `markdown_generated_at_version = null` ❌ |
| After live restart | `md_at=null` — **marker did not survive** |

**Root cause:** `_write_checkpoint` is called only from `jobs.py:209, 264, 285, 307` — job creation, processing start, crash, completion. All lifecycle events. `_ensure_current_export` advances the marker during a **GET**, and nothing flushes it. The serialization round-trip was correct and provably so; it simply never fired in production.

Making it fire requires calling `_write_checkpoint` from the regeneration helper — which turns **a GET request into a checkpoint-writing operation**.

**Rejected.** The benefit is one rebuild per artifact after a restart: ~110 ms (Markdown), ~880 ms (DOCX), once. Paying for that by making every read path a disk writer is a bad trade. The architecture stays:

- GET requests perform regeneration and cache updates only.
- Checkpoint writes remain tied to job lifecycle events.
- One regeneration per artifact after restart is accepted.

Phase 3 code and tests were reverted; `src/api/jobs.py` is untouched.

**Why the residual cost is acceptable:** it is bounded (once per artifact per restart), self-correcting (the marker advances immediately after), and errs in the safe direction. Rebuilding a current artifact wastes under a second; serving a stale one as current is the exact failure mode this workstream exists to prevent.

## Files changed

| File | Change |
|---|---|
| `src/api/routes.py` | `_atomic_write` + `_ensure_current_export`; adopted in preview and both downloads; `tempfile` removed |
| `tests/test_fe0_003_preview_regeneration.py` | New — 16 tests |

## Test results

`test_fe0_003_preview_regeneration.py` (16) + `test_jobs_persistence.py` + `test_corrections_api.py` — **72 passed / 0 failed**.

Phase 1's behavioural tests were verified non-vacuous: stashing the fix (with `__pycache__` cleared per H-001) failed exactly the 3 behavioural tests and passed the 4 no-regression ones.

## Discoveries worth keeping

1. **`_replace_with_retry` matters more here than for the document sidecar.** These destinations are actively served by `FileResponse`, so a concurrent download can hold the file we are replacing — on top of the antivirus/indexer case its docstring already cites.
2. **Capture `document.version` before the build, not after.** With the build outside the lock, reading it after a render can mark a version that was never rendered — permanently serving stale content as current, invisibly.
3. **Preview and download now share one cache**, so they are structurally unable to disagree. The class of bug that produced this ticket's misdiagnosis is eliminated, not merely fixed.
4. **`build_markdown` has two rendering paths.** `is_mathpix_import` (`markdown_builder.py:257`) gates whether headings render from `document.headings` or by matching `page.cleaned_text`. A fixture setting neither silently produces empty scaffold.
5. **Three CRLF near-misses.** Comparing generated strings against files on this platform reports whole-file diffs that are pure line-ending noise. Normalise before every textual comparison.
6. **A passing test is not production verification.** Phase 3's tests passed because their fixtures called `_write_checkpoint` directly — a fair test of serialization, a poor proxy for the real path. Only the live restart caught it.

## Out of scope

Informational corrections (kinds with no safe generic repair) still produce no visible change on Accept, because there is nothing to apply. Correct behaviour, misleading UI — deserves its own ticket.
