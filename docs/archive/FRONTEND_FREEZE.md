# RAWRS Frontend Freeze

**Status: Frozen as of Phase R-4 (2026-07-17).** This document records why, records what "done" meant, and — more importantly — records exactly what would justify reopening it. A freeze that can't be broken by evidence isn't a freeze, it's neglect wearing a freeze's name.

## Why the Frontend Is Considered Complete

Not because every idea in `docs/RAWRS_DESIGN_BIBLE_v1.0.md` shipped — it didn't, deliberately. Complete means: the architecture is proven, the reviewer workflow works end-to-end for real work today, the known reliability gaps are closed, and everything left unbuilt is optimization on top of a working tool, not a prerequisite for one.

The path here was four consecutive milestones, each gated on the previous one's live verification, not just its code review:

- **R-1.1** (Global Reviewer Toolbar) — Search/Export/readiness-score toolbar, quick-jump nav chips, Validation Center severity tabs + readiness banner.
- **R-2** (Reviewer Experience Refinement) — closed every concrete defect the Reviewer Experience Audit found live: a duplicate "Overview" control, three simultaneously-rendered copies of validation data, a keyboard tab-order regression, a raw developer-facing PDF error, an Overview panel that led with pipeline internals instead of reviewer-relevant content.
- **R-3** (Visual System Completion) — icon system, toolbar/nav-chip hierarchy and polish, component consistency (radius, disclosure controls), all without touching color values.
- **R-4** (Reliability Hardening) — the route-level error boundary (`app/error.tsx`, the single most-repeated "most overdue item" across every prior review, finally closed and live-verified to actually catch a thrown error), a real `react-resizable-panels` layout-persistence correctness fix, and accessibility test coverage for everything R-2/R-3 had shipped without it.

Between R-3 and R-4, a Frontend Completion Review independently scored the result 84/100 and explicitly recommended one narrowly-scoped hardening milestone (not another UX phase) before freezing — that milestone is R-4, and it's done.

## Acceptance Criteria Achieved

- **Architecture confirmed sound**, independently, by four separate review passes (F-4.2, F-4.4, F-5.0, R-1.0) plus this session's own live testing — not asserted once and repeated.
- **Every concrete, live-reproduced defect found by the Reviewer Experience Audit is fixed and re-verified live**, not just patched and assumed: duplicate Overview control, redundant validation surfaces, keyboard tab-order tax, toolbar/Overview-panel hierarchy, raw PDF error message.
- **`app/error.tsx` exists and was proven to work**, not just to compile — verified by deliberately triggering a real render exception and confirming React's own `<ErrorBoundaryHandler>` caught it, the reviewer-facing recovery UI rendered, and the raw error still reached the console for diagnostics.
- **Accessibility test suite covers the current surface**: 7 files, 9 tests, all passing, all added or extended to reach the interactive elements (icons, consolidated controls, the rail's validation-summary button) that had shipped ahead of their tests.
- **Keyboard fundamentals hold**: ARIA tabs throughout via one shared hook, computed focus-visible rings (not just declared), a working skip link, correct tab order confirmed live after every phase's changes.
- **No known regressions**: `tsc`, `jest`, and `next build` all clean at every milestone boundary, not just at the end.

## Conditions That Justify Breaking the Freeze

The freeze is about *effort allocation*, not a ban on frontend edits. Reopen it — for the specific fix only, not a new open-ended phase — when:

1. **A viewer-correctness bug is found that requires a frontend change to fix.** Phase V-1 exists precisely because "the viewer is correct" is a claim that needs checking, not an assumption baked into the freeze. If V-1 (or any later testing) finds a real coordinate/sync/overlay defect, fixing it is in-scope despite the freeze — that's what "extend, never redesign" during a freeze means in practice.
2. **A backend change adds or changes a data shape the frontend must render** (e.g., Repair Action Plan's DOM-transformation payload, once built) — the frontend change to consume it is a required extension, not new scope creep.
3. **An accessibility regression is found** — screen-reader testing (never yet performed with a real NVDA/JAWS pass, still an open, disclosed gap) surfaces something the CDP-simulated tree missed.
4. **A real reviewer, using the tool for real work, reports a workflow-blocking problem** — the freeze reflects confidence based on everything tested so far, not a claim that testing was exhaustive.

The freeze does **not** mean: no more icons, no more hierarchy tweaks, no Command Palette, no Triple Compare, no context-preserving-editing source-strip. Those are real, named, legitimate future value — deliberately deferred, not forgotten, and listed below.

## Remaining Work Intentionally Deferred

Every item below was evaluated and explicitly *not* built, on the record, not overlooked:

- **Context-preserving editing / source-strip** (Design Bible §9) — the single largest remaining reviewer-productivity gap, named across four separate reviews now. Real, valuable, deliberately not a freeze-blocker: nothing today prevents a reviewer from doing correct work without it.
- **Keyboard-coverage expansion beyond `ReviewerWorkspace`** (Bible §21) — Validation/Image/Table/Heading grids are still mouse-only for list-review triage.
- **Triple Compare / cross-pane synchronized highlight** (Bible §7) — explicitly gated on a performance benchmark that has never been run; building it now would be reasoning, not measuring.
- **Command Palette** (Bible §20) — expert-user delight, not a correctness or workflow blocker.
- **Repair Action Plan** (Bible §9) — has a named, real backend dependency (specific DOM-transformation data the backend doesn't expose yet); frontend work here would be speculative against an API that doesn't exist.
- **AI Confidence slider** (Bible §10) — real gap, not urgent; existing severity/category filtering already supports effective triage.
- **A real screen-reader (NVDA/JAWS) validation pass** — every accessibility claim to date rests on Chrome DevTools Protocol's accessibility-tree simulation, explicitly disclosed as "not a real screen reader" since F-2.2. Still the single most important unclosed accessibility validation gap, independent of the freeze.
- **A first real performance measurement** — no Lighthouse run, no bundle-size table, no large-document benchmark has ever been produced. `next build` with Turbopack doesn't even surface bundle sizes in this project's current configuration; this was checked directly during the Frontend Completion Review, not assumed.
- **Formal Design Bible §39 type/spacing tokens as literal CSS variables** — the rendered result is already coherent (verified, not assumed) via Tailwind's default scale; formalizing it as named tokens would matter more at team scale than it does today.
- **Responsive/mobile layout** — correctly out of scope by deliberate product decision (RAWRS is a desktop-only professional tool, per Product Principle 3), not a gap to revisit.

## What Comes Next

Phase V-1 (Viewer Stabilization) begins immediately after this freeze — testing whether the claim "the viewer is correct" actually holds, using real coordinate data traced from backend output through to rendered overlays. See `docs/PHASE_STATUS.md` "Phase V-1" for results.
