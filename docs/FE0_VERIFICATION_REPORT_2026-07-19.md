# FE-0 Verification Report

**Date:** 2026-07-19 · **Method:** live click-through, Chrome DevTools MCP against `localhost:3000` + `127.0.0.1:8001`
**Document under test:** `1.Aims of Education and the teacher_Dhankar_PhilPers (1)` (4 pages, Mathpix `.mmd` + source PDF)

First live verification ever performed in this project. All prior frontend claims were code-traced only.

---

## Scope Caveat (read first)

The test document contained **zero images, tables, footnotes, lists and callouts**. Those five inspector surfaces rendered their empty states and were **never exercised with real data**. Focus Mode, Search, keyboard shortcuts, filter combinations and DOCX Preview interaction were also not exercised — budget was consumed by the defects found in the first three surfaces.

**This report is evidence for the surfaces listed below and for nothing else.** It reduces the frontend evidence gap; it does not close it.

---

## Verified Workflows

| Surface | Result | Evidence |
|---|---|---|
| Upload (Mathpix + PDF) | **PASS** | Filename, size, "Loaded" badge, remove buttons, submit correctly gated on both inputs |
| Pipeline run | **PASS** | 3.6s, `status=complete`, artifacts generated |
| Job persistence across restart | **PARTIAL** | Job list + artifacts survive; all semantic data lost — FE-0-001 |
| Document workspace first render | **FAIL** | All counters zero — FE-0-002 |
| Document workspace after reload | **PASS** | Validation 14, Headings 1, Reading Order 4, Corrections 3, Score 36% |
| Review queue — Accept | **PASS** | Single clean click → `accepted`, version 0→1 |
| Review queue — Reject | **PASS** | → `rejected` |
| Correction → output | **FAIL** | Never applied, no regenerate path — FE-0-003 |
| Export staleness labelling | **PASS** | "Accessible DOCX (stale)" rendered correctly |
| Markdown pane | **READ-ONLY** | No editing capability — FE-0-009 |
| Outline / By Type / Pending / Issues tabs | **PASS (render)** | Populate after reload |
| Backend-unreachable handling | **PARTIAL** | Error on submit only; idle state silent — FE-0-007 |

---

## Newly Discovered Issues

### FE-0-001 — Backend restart silently empties every document · **CRITICAL** · Data Loss

- **Current:** After a backend restart, jobs rehydrate from disk and report `status=complete` with artifacts available, but `corrections`, `validation` and `headings` all return `[]`. The UI renders the document as Complete with zero counters and the text *"No validation issues were found for this document."*
- **Expected:** Either full state restoration, or an explicit "review state unavailable — reprocess required" state. Never a false clean bill of health.
- **Repro:** Process a document → accept a correction → restart backend → reload. `GET /corrections` → `{"corrections":[]}`.
- **Evidence:** `corrections:[]`, `validation:{"issues":[],"error_count":0}`, `headings:{"headings":[]}` — all after restart, for a job that held 3 corrections and 14 issues.
- **Why it matters:** A reviewer's entire session is destroyed by a restart, and the resulting empty document is visually indistinguishable from a fully remediated one. This is the most dangerous defect found: it can ship an unremediated document as clean.
- **Fix:** Persist corrections/validation/headings with the job; on partial rehydration surface a degraded state, never zeros.
- **Phase:** Phase 0 / A02

### FE-0-002 — First render after processing shows a false clean state · **CRITICAL** · State Bug

- **Current:** Immediately after the pipeline completes, the workspace shows Validation 0, Headings 0, Corrections 0, *"No headings detected."*, *"No validation issues were found."* — while all 13 detail endpoints returned HTTP 200 with real data. A manual reload populates everything (Validation 14, Headings 1, Corrections 3, Score 36%).
- **Expected:** Data renders on completion without a reload.
- **Repro:** Upload → Run → observe workspace → reload → compare.
- **Evidence:** Pre-reload snapshot all zeros; post-reload Validation 14 / Headings 1 / Corrections 3 / Score 36%. Network log shows all endpoints 200 before the reload.
- **Why it matters:** The reviewer's *first* view of every document is a false "nothing to do" state. Shares its visual signature with FE-0-001.
- **Fix:** Bind the workspace to the fetched detail payloads rather than to whatever snapshot exists at mount.
- **Phase:** Phase 0

### FE-0-003 — Accepted corrections never reach the output; no regenerate path · **HIGH** · Dead End

- **Current:** Accepting a correction records it and bumps `document_version` 0→1, but `markdown_generated_at_version` stays 0 and content is unchanged. Export correctly labels artifacts "(stale)" — and offers no way to refresh them. No `regenerate`/`rebuild` endpoint exists (`src/api/routes.py` has no such POST/PUT).
- **Expected:** Accepting a correction regenerates artifacts, or an explicit "Regenerate outputs" action exists.
- **Repro:** Accept `HEADING_VERIFY_004` (retitle heading) → `GET /markdown` → line 11 still `## "There is nothing more practical than theory." - Boltzmann`.
- **Why it matters:** The reviewer loop is open. Review work can never reach a deliverable except by re-running the pipeline, which discards all decisions.
- **Fix:** Add regenerate endpoint + UI action; invalidate artifacts on version bump.
- **Phase:** A14

### FE-0-004 — PAGE_001 fires 4 false errors on every Mathpix import · **HIGH** · Correctness

- **Current:** Validation reports ERROR *"Page N has no H6 page marker"* for all 4 pages. The markers demonstrably exist in the output (`###### 1`, `###### 2`, `###### 3`, `###### 4`).
- **Root cause:** `validator.py:481` reads `document.headings` where `is_page_marker=True`. The Mathpix import path renders `###### N` directly in the markdown builder but never registers page-marker `Heading` objects, so the check — written for the PDF-native path — always fails.
- **Why it matters:** These 4 phantom errors are the document's *entire* error count and drive `ready:false` and the 36% readiness score. Mathpix is now the primary input path, so every document is affected.
- **Fix:** Populate page-marker `Heading` objects during Mathpix ingestion (preferred), or scope PAGE_001 to the native path.
- **Phase:** A01

### FE-0-005 — Document title never becomes H1 · **MEDIUM** · Semantic Correctness

- **Current:** "AIMS OF EDUCATION: DO TEACHERS NEED TO BOTHER ABOUT THEM?" renders as bold body text. `HEADING_002` warns "No H1 heading was detected." The only heading in the document is a chapter epigraph, promoted to H2.
- **Expected:** Document title → H1.
- **Fix:** Front-matter title promotion during Mathpix ingestion.
- **Phase:** A01

### FE-0-006 — Author byline proposed as a heading · **MEDIUM** · Semantic Correctness

- **Current:** `HEADING_VERIFY_002` proposes adding "Rohit Dhankar" (the author byline) as **H2**, evidence *"H2 by font-size rank"* at confidence 1.00.
- **Expected:** Bylines classified as front-matter metadata, not headings.
- **Why it matters:** Font-size ranking with no semantic guard produces confident wrong proposals; reviewers trained to trust high-confidence items will accept them.
- **Fix:** Front-matter role classification ahead of typography ranking.
- **Phase:** A01

### FE-0-007 — Backend-unreachable is invisible until submit, and names the wrong port · **MEDIUM** · Missing Feedback

- **Current:** With the backend down, the landing page renders normally — "RECENT DOCUMENTS / No documents have been processed yet." — identical to a healthy empty state; the failure appears only as a console `ERR_CONNECTION_REFUSED`. On submit the error reads *"Confirm the backend is running on port 8000"* while `.env.local` sets `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001`.
- **Fix:** Surface connectivity state on load; derive the port from the configured base URL.
- **Phase:** Phase 0 (message fix is trivial)

### FE-0-008 — Job list endpoint returns null summary counts · **MEDIUM** · State Bug

- **Current:** `GET /api/documents` returns `page_count:null, heading_count:null, error_count:null, document_version:null` for all 40 jobs, including one whose detail endpoint returns real values.
- **Impact:** Recent Documents cannot show meaningful status.
- **Phase:** A02

### FE-0-009 — Markdown editor is read-only · **MEDIUM** · Missing Feature

- **Current:** Markdown pane is a CodeMirror instance badged `read-only`. No editing of any kind.
- **Note:** Confirms backlog **FE-2** is genuinely unbuilt, not merely non-semantic.
- **Phase:** A01-3 / FE-2

### FE-0-010 — Correction filter page spinner has an impossible range · **LOW** · Visual Defect

- **Current:** Page spinbutton renders `valuemax="0" valuemin="1"`.
- **Fix:** Derive max from page count; disable when corrections carry no page numbers.
- **Phase:** Phase 4

### FE-0-011 — Review queue card duplicated in the DOM · **LOW** · Visual Defect

- **Current:** The focused correction card renders twice in the accessibility tree (inspector + queue), doubling every control. Screen-reader users encounter two "Accept" buttons for one correction.
- **Phase:** Phase 4

### FE-0-012 — Counter semantics inconsistent · **LOW** · Consistency

- **Current:** Toolbar shows "Corrections 1" (pending) while the queue shows "All 3" / "1 accepted · 1 rejected".
- **Phase:** Phase 4

### FE-0-013 — Polling continues after completion · **LOW** · Performance

- **Current:** `GET /api/documents/{id}` repeats indefinitely after `status=complete` (7+ observed post-completion).
- **Phase:** Phase 4

---

## Updated Frontend Backlog

| ID | Change |
|---|---|
| **FE-0-001** | NEW · P0 · Persist review state; never render restored-empty as clean |
| **FE-0-002** | NEW · P0 · Fix first-render data binding |
| **FE-0-003** | NEW · P0 · Regenerate endpoint + UI action |
| **FE-0-004** | NEW · P0 · Page-marker Heading objects on Mathpix ingest |
| **FE-0-005/006** | NEW · P1 · Front-matter role classification (title → H1, byline ≠ heading) |
| **FE-0-007** | NEW · P1 · Connectivity indicator + port from config |
| **FE-0-008** | NEW · P1 · Populate job-list summary counts |
| **FE-2** | **UPDATED** — confirmed unbuilt; editor is read-only. Absorbs FE-0-009 |
| **FE-4** | **UPDATED** — session recovery is worse than assumed; FE-0-001 must land first |
| **FE-0-010..013** | NEW · P2 · Spinner range, duplicate card, counter semantics, polling |
| FE-1, FE-3, FE-5, FE-6 | Unchanged — not exercised |

---

## Screens Requiring Redesign

**None.** Every defect is a data-binding, persistence or semantic-classification bug. The information architecture — toolbar counters, tabbed panes, review queue with evidence cards and keyboard hints — is sound and, where it works, good. Evidence display (weighted scores, per-signal breakdown) is better than the planning documents credited.

---

## High-Priority Fixes

1. **FE-0-001** — restart destroys review work and presents it as clean
2. **FE-0-002** — first render always shows a false clean state
3. **FE-0-003** — accepted corrections cannot reach a deliverable
4. **FE-0-004** — 4 phantom errors on every document, corrupting readiness

1, 2 and 4 all produce *false confidence*: the product tells the reviewer the document is fine when it is not. That is the most damaging failure mode for an accessibility tool.

---

## Backend Dependencies

| Frontend issue | Backend work |
|---|---|
| FE-0-001 | Correction/validation/heading persistence (A02) |
| FE-0-003 | Regenerate endpoint (A14) |
| FE-0-004 | Mathpix ingest emits page-marker Headings (A01) |
| FE-0-005/006 | Front-matter role classification (A01) |
| FE-0-008 | Job list serialiser populates counts |

Only FE-0-002 and FE-0-007 are frontend-only.

---

## Updated Implementation Phases

| Phase | Change |
|---|---|
| **Phase 0** | **+FE-0-002, +FE-0-007.** P0-1 unaffected — still the correct first commit |
| **A01** | **+FE-0-004, +FE-0-005, +FE-0-006.** Confirms A01 as critical path |
| **A02** | **+FE-0-001, +FE-0-008.** Priority raised — FE-0-001 is active data loss |
| **A14** | **+FE-0-003** |
| **Phase 4** | +FE-0-010..013 |

Critical path is unchanged: `P0-1 → P0-0 → P0-2 → P0-3 → A01-1 → A01-2/3/4 → A14-1`. FE-0 confirmed it rather than altering it.

---

## Method Note

One finding was nearly recorded falsely. An ambiguous two-click sequence (both clicks returned tool errors) left a correction marked `rejected`, which read as "Accept produces Reject" — a CRITICAL. A clean single-click retest showed Accept works correctly. **Accept and Reject both function.** Recorded here because the near-miss is the argument for this sprint: two errored clicks and a plausible story almost became a critical defect report.
