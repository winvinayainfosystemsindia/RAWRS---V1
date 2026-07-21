# RAWRS — Release Readiness Audit

> **PARTIALLY SUPERSEDED 2026-07-21.** Blocker #1 — **FE-0-001, document
> persistence — is CLOSED** (`FE-0-001_document_persistence_2026-07-21.md`).
> That retires three of the four Critical risks: silent work loss on restart,
> the post-restart false-clean state, and the stale export. Suite baseline is
> now **1711 passed / 0 failed / 7 skipped**.
>
> **The NOT READY verdict below still stands**, on the remaining blockers —
> FE-0-002 (all-zero first render), FE-0-003, no resource cleanup, no CI, no
> ErrorBoundary, no upload limit, screen reader untested. Everything else in
> this audit is a point-in-time record of 2026-07-20 and is left unedited.

**Date:** 2026-07-20 · **Mode:** Release Audit · audit only, no code changed · RES v1
**Basis:** suite `1645 passed / 0 failed / 7 skipped / 37m46s`; source inspection at `a30fa7a` + working tree; FE-0 live findings (2026-07-19).

## Evidence limits (read first)

| Section | Evidence | Trust |
|---|---|---|
| 1, 4, 7, 8, 10, 11 | Source-verified this session | High |
| 2, 3 | FE-0 live walkthrough, **one document, no images/tables/footnotes/lists** | Medium |
| 5, 6 | **Code-traced only — not exercised live** | **Low** |

Sections 5 and 6 are the weakest claims here. This project has twice produced confident, wrong conclusions from code tracing (FE-0; H-001). Treat a11y and performance ratings below as *unverified hypotheses*, not findings.

---

## 1. Core Pipeline — **PASS (with one gap)**

| Stage | State | Evidence |
|---|---|---|
| PDF → MMD → Import | PASS | `MathpixImportProvider`, `mmd_parser.py`; suite green |
| Import → canonical Document | PASS | `ingestor.py`; FE-0-004/005/006 closed |
| Document → Review | PASS in-session | All workspaces present |
| Review → Markdown/DOCX | **PARTIAL** | Regen works in-session; **breaks after restart** |

**Gap:** `_needs_export_regen` (`routes.py:1611`) returns `False` when `document is None`. After a restart the document *is* `None` (`jobs.py:60` docstring), so exports silently serve the stale pipeline-time file. FE-0-003 is fixed within a session and re-broken across one — by the same root cause as FE-0-001.

## 2. User Workflow — **FAIL**

A remediator can complete a document **only if the backend never restarts and they never reload at the wrong moment.**

| # | Blocker | Impact |
|---|---|---|
| B1 | Backend restart → all corrections/validation/headings gone; job still reads `complete` | Hours of work lost, silently |
| B2 | First render after pipeline shows all-zero counters until manual reload | Document looks clean when it isn't |
| B3 | Post-restart export serves stale file | Accepted fixes absent from deliverable |

B1 is disqualifying on its own. The failure is silent and the UI reports success.

## 3. Frontend — **PARTIAL**

| Area | Rating | Evidence |
|---|---|---|
| Navigation / editing / selection / review flow | PASS | FE-0: "information architecture is sound; no screen requires redesign" |
| Sync | FAIL | FE-0-002 all-zero first render |
| Validation workflow | PASS in-session | FE-0 verified |
| Empty states | PASS | 19/59 components |
| Error handling | **PARTIAL** | 19/59 have `catch`; **zero ErrorBoundary in 59 components** — one render throw blanks the app and loses unsaved review state |
| Loading states | PARTIAL | 6/59 components |
| Discoverability | UNVERIFIED | Not exercised |
| **Logic tests** | **NOT IMPLEMENTED** | 7 test files, all `*.a11y.test.tsx`; 0 logic tests over 59 components |

## 4. Backend — **PARTIAL**

| Area | Rating | Evidence |
|---|---|---|
| API stability | PASS | Suite green; typed schemas (`schemas.py`, 591 ln) |
| Serialization | PASS | Pydantic throughout |
| Error handling | PASS | Explicit `HTTPException`, typed details |
| Job persistence | PARTIAL | Job *records* persist (`jobs.py:198`); **Document does not** |
| Document persistence | **NOT IMPLEMENTED** | `result.document = None` after restart — by design, documented |
| Long-running jobs | **PARTIAL** | `threading.Thread(daemon=True)` (`jobs.py:167`) — killed abruptly on exit, mid-write; **no pool, no queue, no cap** |
| Resource cleanup | **NOT IMPLEMENTED** | Zero `unlink`/`rmtree` in all of `src/`; `NamedTemporaryFile(delete=False)` ×2 never removed; `outputs/` measured at **463 MB / 1010 files** |
| Versioning | NOT IMPLEMENTED | No API version prefix; acceptable while single-client |

## 5. Accessibility — **PARTIAL (low confidence)**

| Area | Rating | Evidence |
|---|---|---|
| Automated a11y coverage | PASS | 7 `jest-axe` suites over the main workspaces |
| ARIA | PARTIAL | `aria-*` in 24/59, `role=` in 16/59 |
| Keyboard / focus / screen reader / contrast | **UNVERIFIED** | Never tested with a real AT |
| Runs in CI | **NOT IMPLEMENTED** | No CI exists — `npm test` is manual and unenforced |

An accessibility tool that has never been driven by a screen reader is a credibility risk with this specific user base. FE-0 did not exercise keyboard or AT.

## 6. Performance — **PARTIAL (low confidence)**

| Area | Rating | Evidence |
|---|---|---|
| Upload size | **NOT IMPLEMENTED** | No limit; `await file.read()` loads whole file into RAM (`routes.py:153`), images too |
| Concurrent jobs | **NOT IMPLEMENTED** | Unbounded daemon threads; N uploads = N full pipelines |
| Timeouts | NOT IMPLEMENTED | No job timeout; OCR observed at 416s for one test |
| Large PDFs / images / tables | **UNVERIFIED** | Benchmark corpus is 10 academic papers; no stress case |
| Memory | UNVERIFIED | No profiling performed |

## 7. Reliability — **FAIL**

| Failure | Severity | Mechanism |
|---|---|---|
| Reviewer work lost on restart | **Critical** | Document never persisted |
| Silent false-clean state | **Critical** | Restart + zero-counter render both report clean |
| Stale export after restart | **Critical** | `document is None` disables regen |
| Partial write on shutdown | High | `daemon=True` threads die mid-pipeline |
| Two reviewers clobber silently | High | ADR-013 — gated, documented, not enforced in code |
| Disk exhaustion | Medium | No cleanup anywhere; 463 MB already accrued locally |

## 8. Deployment — **PARTIAL**

| Artifact | State |
|---|---|
| README | **PASS** — genuinely good; install, run, pitfalls, direct API |
| Fresh clone works | **PASS** — verified: code defaults to `localhost:8000`, README's `uvicorn` defaults to 8000. *(The 8001 requirement is a local-only artifact of an untracked `.env.local`; earlier session notes overstate it as general.)* |
| `.env.example` | MISSING — `NEXT_PUBLIC_API_BASE_URL` documented nowhere |
| Dockerfile / compose | MISSING |
| CI | **MISSING** — nothing gates a merge; the 1645-test suite runs manually on one machine |
| LICENSE | MISSING — blocks external distribution outright |
| Seed data | PARTIAL — benchmark PDFs excluded (copyright), manifest included |

## 9. Documentation — **PASS (with drift)**

45 docs. Architecture, decisions, limitations, validation rules all present and unusually thorough.

| Issue | Detail |
|---|---|
| Rule count conflict | README says "41 rules"; doc table says "29"; source shows **31** distinct rule IDs |
| Stale suite figure | README cites `1296 passed (2026-06-30)`; actual is 1645 |
| "Fast subset ~35 min" | README's own fast path is not fast — consistent with P0-0/P0-2 |
| **Reviewer guide** | **MISSING** — no end-user documentation for remediators, only developer docs |
| Troubleshooting | MISSING as a standalone doc |

## 10. Technical Debt (release-affecting only)

| Pri | Item |
|---|---|
| **P0** | Document not persisted (FE-0-001) — root cause of 3 separate failures |
| **P0** | All-zero first render (FE-0-002) |
| **P0** | No resource cleanup — temp files + `outputs/` unbounded |
| **P1** | No ErrorBoundary anywhere in the frontend |
| **P1** | No CI — green suite is unenforced |
| **P1** | No upload size limit / job concurrency cap |
| **P1** | Zero frontend logic tests |
| **P2** | No LICENSE |
| **P2** | Doc drift (rule counts, suite figures) |
| **P2** | `routes.py` 1914 ln / `validator.py` 1290 ln exceed the project's own 800-line standard |

## 11. Security — **PARTIAL** (adequate local-first; unsafe if exposed)

| Area | Rating | Evidence |
|---|---|---|
| Secrets | **PASS** | `.env` gitignored, untracked, and empty; no hardcoded credentials found |
| Path traversal | **PASS** | `Path(original_name).name` strips directories (`jobs.py`); job-ID-prefixed paths |
| File type validation | PASS | Extension-checked for PDF, MMD, images |
| File content validation | PARTIAL | Extension only — no magic-byte check |
| Upload size | **FAIL** | No limit; trivial memory-exhaustion DoS |
| Temp files | **FAIL** | `delete=False`, never cleaned |
| Auth | **NOT IMPLEMENTED** | Deliberate (`main.py:7`, local-first single-user) |
| CORS | PASS *for its stated scope* | Localhost dev origins only |

**No auth + no size limit + no cleanup is coherent for a localhost desktop tool and unacceptable on any shared host.** The deployment story must state this explicitly; today nothing prevents someone binding it to `0.0.0.0`.

## 12. Production Risks

| Sev | Risk |
|---|---|
| **Critical** | Restart destroys reviewer work while UI reports success |
| **Critical** | Document presented as clean when data failed to load (FE-0-002) |
| **Critical** | Shipped DOCX silently missing accepted corrections after restart |
| **High** | Frontend render error blanks app; no boundary, no recovery |
| **High** | Two reviewers on one document clobber silently (ADR-013) |
| **High** | Regression reaches main — no CI |
| **Medium** | Disk exhaustion from uncleaned outputs/temp files |
| **Medium** | Memory exhaustion from large or concurrent uploads |
| **Medium** | a11y regression unnoticed — a11y tests never run automatically |
| **Low** | Model weights download on first inference; no offline story |

---

# Final Report

## Release Score: **58 / 100**

| Dimension | Wt | Score | Note |
|---|---|---|---|
| Core pipeline correctness | 25 | 21 | Genuinely strong; 1645 green |
| Data integrity / durability | 25 | 5 | **Confirmed silent loss** |
| Reviewer workflow | 15 | 8 | Complete only in an uninterrupted session |
| Frontend robustness | 10 | 5 | No boundary, no logic tests |
| Accessibility of RAWRS itself | 10 | 6 | Automated only, unenforced, no AT test |
| Ops / deployment / CI | 10 | 4 | No CI, no container, no license |
| Documentation | 5 | 5 | Excellent for developers |
| Security posture | 5 | 4 | Coherent for local-first |

## Recommendation: **NOT READY**

Not for external users, and not for internal remediators doing real work.

The disqualifier is single and specific: **a backend restart destroys all review work while the interface continues to report the document as complete.** For a tool whose entire purpose is accessibility remediation, the worst possible failure is asserting a document is remediated when it is not — and RAWRS does that in three distinct ways today (FE-0-001, FE-0-002, stale export).

This is emphatically **not** a verdict on engineering quality. The pipeline is sound, the suite is green and honest, the architecture is ratified, and the documentation is better than most shipped products. The gap is durability, not capability. It is also *narrow*: FE-0-001 is the root cause of three of the four Critical risks, and closing it plus FE-0-002 moves this to **READY FOR PILOT** with a named single reviewer — likely a week of work, not a quarter.

**Conditional path:** `READY FOR PILOT` becomes defensible when blockers 1-3 close and 4-5 have a workaround. `READY FOR LIMITED BETA` additionally requires CI, an ErrorBoundary, cleanup, and one screen-reader session.

## Top 10 Blockers (by impact)

| # | Blocker | Sev | Why it blocks |
|---|---|---|---|
| 1 | **Document not persisted** (FE-0-001) | Critical | Root cause of #3 and post-restart false-clean. Fixing it alone retires three Critical risks. |
| 2 | **All-zero first render** (FE-0-002) | Critical | Tool reports a document clean when data hasn't loaded — the one thing it must never do |
| 3 | **Stale export after restart** | Critical | Deliverable silently omits accepted fixes; `document is None` disables regen |
| 4 | **No resource cleanup** | High | Temp files never removed; `outputs/` at 463 MB already; unbounded on any real workload |
| 5 | **No CI** | High | 1645 green tests enforce nothing; next regression reaches main unseen |
| 6 | **No ErrorBoundary** | High | One render throw blanks the app and discards unsaved review state |
| 7 | **No upload limit / job cap** | High | Memory exhaustion from one large or several concurrent uploads |
| 8 | **Screen reader never tested** | High | Unacceptable unknown for an a11y tool sold to a11y professionals |
| 9 | **No reviewer guide** | Medium | Remediators are not the developer audience all 45 docs address |
| 10 | **No LICENSE** | Medium | Legally blocks external distribution regardless of readiness |

## What this audit could not determine

1. **Behaviour on figure/table/footnote-rich documents.** FE-0's document had none. Every workspace except headings and corrections is effectively unexercised live.
2. **Real performance ceilings.** No large-document stress test exists.
3. **Actual accessibility.** Automated axe checks are a floor, not evidence of usability with AT.

Items 1 and 3 are the highest-value next verification work, and neither is discoverable by reading code — which is precisely how the last three confident wrong answers in this project were produced.
