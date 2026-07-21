# FE-0-002 — First-render data binding · Investigation

**Date:** 2026-07-21 · **Branch:** `fe-0-001-persistence-and-cleanup` · **HEAD:** `28c2881`
**Method:** live click-through, Chrome DevTools MCP against `localhost:3000` + `127.0.0.1:8001`

**Verdict: NOT REPRODUCIBLE on current HEAD. Closing FE-0-002 as already fixed.**

---

## Evidence

Three runs. In each, first render was compared against a post-reload render of the same job.

| Run | Path | Document | First render | After reload | Match |
|---|---|---|---|---|---|
| 1 | Hard nav during `processing` | Nature of Enquiry (28p) | Val 84 · Tab 3 · Lists 8 · RO 28 · Corr 45 · 50% | — | — |
| 2 | **Real flow** (upload → `router.push`) | Nature of Enquiry (28p) | Val 84 · Tab 3 · Lists 8 · RO 28 · Corr 45 · 50% | identical | ✅ |
| 3 | **Real flow**, original report's document | Dhankar (4p, canonical `.mmd`) | Val 7 · Head 2 · RO 4 · Corr 1 · 55% | identical | ✅ |

Run 3 uses the exact document from `FE0_VERIFICATION_REPORT_2026-07-19.md`. Backend truth cross-checked directly against the detail endpoints — matches the UI in every case.

Counts differ from the 2026-07-19 report (Val 14 → 7, Head 1 → 2, Corr 3 → 1, 36% → 55%) because FE-0-004/005/006 landed in between; those deltas are the expected effect of the phantom-`PAGE_001` and front-matter fixes.

## Probable cause of the original observation

Not provable after the fact; two candidates, both now closed:

| Candidate | Status |
|---|---|
| Silent per-slice fetch failure — pre-`d440890` the poller used bare `.catch(() => empty)`, so any transient failure rendered as zeros with no signal | Closed by `d440890` (P0-4 `tryLoad` + retryable `loadErrors` banner). This failure mode can no longer present as a clean document. |
| Next.js dev-server crash | Observed live this session (below) |

`d440890` and the FE-0 walkthrough are both dated 2026-07-19 with no finer ordering recorded, so neither candidate can be confirmed as *the* cause. The symptom is gone and the dangerous failure mode (errored slice rendering as "no issues") is structurally prevented.

## Incidental finding — dev-server instability

Mid-session the Next.js dev server died with `Jest worker encountered 2 child process exceptions, exceeding retry limit` and served HTTP 500 with an empty `<body>` on **every** route until restarted. Reload did not recover it; only a process restart did.

This is an environment failure, not an app defect, but it is worth recording: it produces a blank workspace that could easily be misread as a frontend state bug during live verification.

## Actions

- FE-0-002 → closed, no code change.
- P0 queue now: **FE-0-003** (regenerate endpoint + UI action) only.
