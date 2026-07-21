# FE-0-001 — Document Persistence

**Date:** 2026-07-21 · **Status: MERGED** · RES v1
Closes the highest-priority release blocker from `RELEASE_READINESS_AUDIT_2026-07-20.md`.

---

## 1. Problem Statement

### Original failure mode

A backend restart destroyed all reviewer work while the interface continued to report the document as complete.

| Symptom | Effect |
|---|---|
| Corrections, validation, headings empty after restart | Hours of review lost, silently |
| Job still reads `status=COMPLETE` | Product asserts a document is remediated when it is not |
| Exports serve pre-review files | Accepted fixes absent from the delivered DOCX/MD |

### Root cause

`_result_to_dict()` (`jobs.py`) serialized nine scalar/path fields and **omitted `document` entirely**. Measured checkpoint size: ~1 KB.

On restart `_result_from_dict()` rebuilt a `PipelineResult` with `document` defaulting to `None`, while faithfully restoring `status=COMPLETE`. That pairing — **`status=COMPLETE` + `document=None`** — is the defect. It was documented as intentional (`jobs.py`: *"result may be a stub PipelineResult with document=None … a valid state for recovered jobs"*), making this a design gap, not a coding error.

### Why reviewer work was lost

The Document existed in exactly one place: `jobs._jobs[job_id].result.document` — a plain in-process dict. No second store, no cache, no write-back at any of the 15 reviewer mutation endpoints. Process memory was the sole authority, and worker threads are `daemon=True`, so they die abruptly without flushing.

One root cause produced three of the release audit's four Critical risks. `_needs_export_regen()` short-circuits on `document is None`, so the stale-export defect was a direct consequence rather than an independent bug.

---

## 2. Final Architecture

One JSON sidecar per job, mirroring the existing `outputs/jobs/` convention. The whole `Document` tree is Pydantic (`Document` → `SemanticObject` → `BaseModel`), so no mapping layer was required.

### Persistence flow

```
reviewer mutation (15 endpoints)
  └─ with _lock:
       …mutate document…
       payload = _snapshot(document)      ← serialize INSIDE lock (CPU only)
     lock released
     _persist(job_id, payload)            ← file I/O OUTSIDE lock
       └─ save_document()
            write tmp → flush → fsync → os.replace   (atomic + durable)

pipeline completion (jobs._run_job)
  └─ same split: serialize in lock, save after release,
     then job.document_persisted = <result>, then _write_checkpoint()
```

Persistence is **synchronous and immediate**. Debounced write-behind was evaluated and rejected: it reintroduces a window in which accepted corrections are not on disk, which is the failure FE-0-001 exists to eliminate. At ~111 ms worst case for a single reviewer the latency is imperceptible.

### Recovery flow

```
startup (_lifespan)
  ├─ sweep_orphan_temp_files()     ← before recovery, so it never sees partials
  └─ load_persisted_jobs()
       └─ _job_from_dict()
            ├─ rebuild Job + PipelineResult from checkpoint
            └─ if result is not None:
                 document = load_document(job_id)     ← sidecar is source of truth
                 result.document = document
                 job.document_persisted = document is not None
```

**The sidecar on disk is authoritative, never the `document_persisted` flag.** That flag is written once at completion and can be stale in both directions (sidecar deleted out of band; save succeeded while the checkpoint write did not). The load is therefore attempted whenever a result exists, and the flag is corrected to match what was actually found. A flag/reality mismatch logs a warning and recovers without the document.

`load_document()` returns `None` for **every** failure mode — missing, unreadable, malformed, schema mismatch, failed validation. `None` reproduces the documented pre-FE-0-001 state that the rest of the system already handles, so no failure mode aborts recovery. A partially populated Document is never returned: it would look like real data, which is worse than no data.

### Locking strategy

`jobs._lock` is a plain **non-reentrant** `threading.Lock`, module-global across all jobs. All 15 mutation endpoints already ran under it, and FastAPI runs the 58 sync `def` handlers in a threadpool, so concurrency is genuine.

| Rule | Reason |
|---|---|
| `document_store` **never** acquires `_lock` | Re-acquiring inside a held non-reentrant lock deadlocks permanently. Enforced structurally: the module does not import `jobs` at all |
| **Serialize inside** the lock | `model_dump_json()` walks a mutable graph; concurrent mutation yields a torn snapshot that still validates on reload — silent, permanent corruption |
| **Write outside** the lock | A multi-megabyte write must not block the global lock; matches `_write_checkpoint`'s existing convention |

Both rules are pinned by tests (`test_module_never_imports_jobs`, `test_snapshot_precedes_persist_in_every_case`).

### Atomic write strategy

```
write {job_id}.json.tmp   (same directory ⇒ same volume)
flush()
os.fsync(fd)              ← atomic rename is NOT durability without this
os.replace(tmp, final)    ← atomic on POSIX and Windows
```

Without `fsync`, power loss can land the rename while data pages have not been written, producing a file that looks valid but is empty or stale. The temp file is co-located so the rename never crosses a volume boundary and degrades to a non-atomic copy.

`os.replace()` raises `PermissionError` on Windows when the destination is held open (antivirus, indexers), so replace is retried 5× with backoff. `save_document()` returns `False` rather than raising: the reviewer's mutation already succeeded in memory, so a disk fault must not fail their request.

### Schema envelope

```json
{
  "schema_version": 1,
  "saved_at": "2026-07-21T09:15:00.123456+00:00",
  "document": { "...": "Pydantic model_dump" }
}
```

Shipped from the first commit — retrofitting a version field onto files already on disk is not cleanly possible. Bump `SCHEMA_VERSION` when a change to `Document` makes existing sidecars unreadable (renamed/removed/retyped field); additive optional fields need no bump, since Pydantic supplies defaults. A mismatch is refused cleanly rather than surfacing as an opaque `ValidationError`.

The envelope is composed around a single `model_dump_json()` call rather than `json.dumps({..., "document": document.model_dump(mode="json")})`, which serializes the tree twice and would push the worst case toward the 250 ms threshold that would have invalidated this architecture. `test_envelope_is_valid_json` pins the composition.

---

## 3. Files Modified

| File | Purpose |
|---|---|
| `src/api/document_store.py` **(new, 265 ln)** | The whole persistence surface: `serialize_document`, `save_document`, `load_document`, `delete_document`, `sweep_orphan_temp_files`, `document_path`. Deliberately does not import `jobs` |
| `src/api/jobs.py` (+62/−5) | Persists the Document at job completion; rehydrates it during checkpoint recovery; adds `Job.document_persisted` |
| `src/api/routes.py` (+57) | `_snapshot()` / `_persist()` helpers and their use at **15** reviewer mutation endpoints |
| `src/api/main.py` (+8) | Invokes `sweep_orphan_temp_files()` at startup, before recovery |
| `tests/test_document_store.py` **(new, 316 ln)** | 33 unit tests — round-trip, atomicity, corruption, envelope, sweep, invariants |
| `tests/test_jobs_persistence.py` **(new, 555 ln)** | 33 tests — write path, recovery, restart flows, mutation wiring, startup sweep |

**Total: 4 source files (1 new), 2 new test files, ~1,263 lines.**

### Scope note — 15 sites, not 7

The approved design specified *"persist after each of the 7 `version += 1` sites."* Enumeration found **15** lock-guarded reviewer mutation endpoints, of which only ~6 bump `version`. Persisting at version-bump sites alone would have lost **heading review, footnote review, table create/edit/analyze/delete, metadata, and validation-issue review** on restart — precisely the class of loss this feature exists to prevent. All 15 are wired; `TestAllMutationSitesWired` pins the count so a new endpoint cannot be added unpersisted without failing.

---

## 4. Testing Summary

### New tests — 66

| Area | Tests |
|---|---|
| Round-trip fidelity | 5 — incl. a Mathpix-imported document with real nested headings |
| Durability / atomicity | 6 — **fsync-before-replace ordering asserted** |
| Corruption rejection | 8 — empty, malformed, wrong-shape, truncated, invalid model |
| Missing file | 4 — degrades to `None`, never raises |
| Schema envelope | 4 — version present, ISO-8601 UTC, future version refused |
| Orphan sweep | 3 + 2 |
| Review invariants | 3 — no `jobs` import; serialize/save separable |
| Write path | 14 |
| Restart / recovery | 11 |
| Mutation wiring | 2 — all 15 sites, correct lock-side indentation |
| Reviewer mutations via API | 4 |

### Regression results

| Metric | Baseline | After | Δ |
|---|---:|---:|---|
| Passed | 1645 | **1711** | **+66** |
| Failed | 0 | **0** | 0 |
| Skipped | 7 | 7 | 0 |

`+66` is exactly the new tests. No pre-existing test changed behaviour. Targeted runs: 66 persistence/recovery + 375 API tests pass; no import cycles.

### Restart validation

`test_end_to_end_restart_preserves_review_state` executes the full chain:

```
pipeline completes → document persisted → backend restart (_jobs cleared)
→ checkpoint reload → document restored → reviewer state preserved
  (title, language, version 21, 5 pages all intact)
```

Before this change, step 5 returned `None` and step 6 was impossible.

### Performance benchmark

| Stage | Cost |
|---|---|
| Serialize (10-doc corpus) | 1.3-101 ms; worst 3.36 MB (`sockett`, `brinkman`) |
| Atomic write | **+9.5 ms**, fsync-bound and **size-independent** |
| **Worst case per mutation** | **~111 ms** — within the accepted AMBER envelope (RED = 250 ms) |

Document size is driven by object density, not page count: a 9-page document serializes to 3.36 MB while a 26-page document serializes to 0.59 MB.

**Unresolved:** full-suite wall time rose 37m46s → 52m26s. Measured persistence overhead across the suite is ~5 s; explaining 880 s would require ~92,600 persisted mutations, which the suite does not perform. Observed runtimes across four runs of near-identical code span 32:07-52:26 (±38%), so this is *attributed to environment variance* — an inference, not a measurement. A controlled A/B would settle it.

---

## 5. Backward Compatibility

**Strictly additive. No data migration, no version gate.**

| Case | Behaviour |
|---|---|
| Legacy checkpoint (no `document_persisted` key) | `.get(..., False)` → loads unchanged, `status` preserved |
| Legacy checkpoint, no sidecar | `document=None` — **exactly** the pre-FE-0-001 behaviour |
| Existing checkpoint keys | All 10 unchanged; one key added |
| Missing / corrupt sidecar | Degrades to `None`, logs, never raises |

Pinned by `test_checkpoint_without_the_key_defaults_to_false`, `test_legacy_checkpoint_recovers_unchanged`, `test_existing_checkpoint_fields_are_unchanged`.

### Rollback

```bash
rm -rf outputs/documents/     # complete revert
```

Sidecars are additive and ignorable; with them gone the system returns to the previous behaviour. No irreversible step exists at any point. Reverting the source changes additionally removes one checkpoint key, which older readers already tolerate via `.get()`.

---

## 6. Remaining Limitations *(accepted, out of scope)*

| # | Limitation | Sev |
|---|---|---|
| L1 | **No sidecar lifecycle.** `outputs/documents/` grows unbounded (~3.4 MB/doc worst case). `delete_document()` exists but is uncalled | Medium |
| L2 | **Startup cost scales with corpus.** Every document deserialized at boot (~100 ms each; ~10 s per 100 documents) | Low |
| L3 | **Exports always regenerate after restart.** `markdown/docx_generated_at_version` are not in the checkpoint, so `_needs_export_regen` returns `True`. Safe direction — rebuilding beats serving stale | Low |
| L4 | **Orphaned sidecars.** A job that persisted then died before its terminal checkpoint leaves a sidecar that is never read or swept (sweep covers `.tmp` only) | Low |
| L5 | **Global lock held during serialization** — up to 101 ms blocks all endpoints. Acceptable for single-reviewer use; ADR-013 already gates multi-reviewer deployment | Low |
| L6 | **FE-0-002 unaffected.** The all-zero first render is frontend timing and survives perfect backend durability | — |

---

## 7. Future Work

### Sidecar lifecycle management (addresses L1, L4)

Retention and deletion policy: remove a sidecar when its job is deleted; age- or size-based pruning for `outputs/documents/`; extend the startup sweep to orphaned `.json` files whose job has no checkpoint. This is a general cleanup gap — the release audit found **zero** `unlink`/`rmtree` calls anywhere in `src/`, with `outputs/` already at 463 MB — so it deserves its own item rather than being bolted onto persistence.

### Lazy loading (addresses L2, L5)

Load a Document on first access instead of eagerly at startup, keyed off `document_persisted`. Removes the boot cost and shortens lock hold time. Warranted once the corpus reaches hundreds of documents; premature at Phase 1 scale.

### Export optimization (addresses L3)

Persist `markdown_generated_at_version` / `docx_generated_at_version` in the checkpoint so `_needs_export_regen` can distinguish "changed since export" from "unknown". Removes one unnecessary rebuild per download after restart. Requires a checkpoint schema change, deliberately excluded here.

### SQLite migration (ADR-012 / A12-1)

The pre-implementation review deferred SQLite because its value is per-object rows keyed by **stable identity**, and RAWRS still mints positional IDs (`fn-{idx}`, `table-p{p}-{i}`) that `A02-3` exists to retire. Building a relational store on unstable keys would bake the identity defect into a schema and force a later data migration. **Revisit after A02-1 (stable UUIDs).** The two-function seam — `serialize_document` / `save_document` / `load_document` — is where that swap happens; no caller changes.

Migration triggers from the agreed thresholds: serialization p95 **> 250 ms**, sidecar **> 20 MB**, or `outputs/documents/` **> 5 GB**.
