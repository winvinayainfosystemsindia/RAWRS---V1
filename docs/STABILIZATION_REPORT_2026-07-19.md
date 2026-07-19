# Stabilization Report — 2026-07-19

Commit `d440890`. Gates: tsc clean · jest 7/7 (9/9) · backend 38 correction tests · `next build` clean · live backend confirms `CorrectionOut.reviewed_at`.

**Verified column:** `build+test` = compiles + suites pass · `runtime` = checked against live server · `code-traced` = render path verified, live click-through still advised.

## Findings

| # | Issue | Root cause | Solution | Key files | Status | Verified |
|---|---|---|---|---|---|---|
| P0-1 | Score frozen after review | `watchVersion` refetched only markdown; nothing recomputed score | Shared `useReviewAction` refetches readiness+report per action; `watchVersion` also refreshes on version bump | `useReviewAction.ts`, `DocumentProvider.tsx`, `DocumentDataContext.tsx` | ✅ | build+test |
| P0-2 | Review Queue hidden (bottom panel closed) | `bottomOpen` always defaulted false | Default open when pending work + no stored pref; collapsed bar labelled "Review Queue — N pending" | `WorkspaceShell.tsx`, `DocumentWorkspace.tsx` | ✅ | code-traced |
| P0-3 | Timeline sorted by pipeline time | `reviewed_at` existed on model but wasn't serialized | Serialize `reviewed_at`; sort Recent Activity by it, exclude auto_applied | `schemas.py`, `routes.py`, `api.ts`, `BottomPanel.tsx` | ✅ | runtime |
| P0-4 | Fetch errors shown as "empty" | every `loadResults` fetch `.catch(()=>empty)` | Per-slice `tryLoad` records failures → `loadErrors` → retryable banner (`REQUEST_RELOAD`) | `DocumentProvider.tsx`, `DocumentDataContext.tsx`, `DocumentWorkspace.tsx` | ✅ | code-traced |
| P1-5 | Keyboard path bypassed toast/undo/errors | two duplicated action impls | Single `useReviewAction`; both button + keyboard consume it | `useReviewAction.ts`, `CorrectionHistoryList.tsx`, `ReviewerWorkspace.tsx` | ✅ | build+test |
| P1-6 | Category cards switched views, not filtered queue | filter state trapped in queue local state; hardcoded catMap | `ReviewQueueContext` (filter + focus signal); cards call `focusQueue(objectType)`, panel opens; Fix Next opens prioritized queue | `ReviewQueueContext.tsx`, `DocumentWorkspace.tsx`, `ReviewerWorkspace.tsx` | ✅ | code-traced |
| P1-7 | Filter not remembered | local `useState` | Object-type filter persisted in `ReviewQueueContext` (adds to existing sort/tab persistence) | `ReviewQueueContext.tsx` | 🟡 | code-traced |
| P2-8 | Impact missing for some types | 6-entry map, silent fallback | Added list/callout/paragraph/caption/front_matter + generic fallback (never blank) | `CorrectionHistoryList.tsx` | ✅ | build+test |
| P2-9 | No bulk review | — | "Accept N high-confidence in view" (≥0.95) with single Undo-all | `ReviewerWorkspace.tsx`, `useReviewAction.ts` | ✅ | code-traced |
| P2-10 | Coverage = resolution, counted auto_applied | measured wrong thing | `visitedPages` in viewport ctx → coverage = pages visited + pages with *your* decisions (auto_applied excluded) | `PdfViewportContext.tsx`, `BottomPanel.tsx` | ✅ | code-traced |
| P2-11 | Shortcuts overlay: no focus trap/Escape/aria-modal | hand-rolled div | Native `<dialog>` + `showModal()` (trap/Escape/aria-modal/restore for free) | `DocumentWorkspace.tsx` | ✅ | code-traced |

## Notes / honest gaps

- **P1-7 partial:** "last reviewed correction" and "last viewed page" restore not implemented; only the queue filter (plus prior sort/tab/layout) persists. Session-recovery of the exact item is still a follow-up.
- **P2-10:** `visitedPages` is session-scoped (not persisted) and counts programmatic jumps as visits — a reasonable attention proxy, not eye-tracking.
- **Live click-through not performed** for the `code-traced` rows (browser-driving was out of budget). Servers are up (`:3000` / `:8001`) for spot-check; the flows to click are: accept an item → score moves; category "Review →" → queue filters + opens; `?` → focus trapped in dialog.

---

# Updated Feature Reality Audit

| Score | Before | After |
|---|---|---|
| Delivery | 6/10 | 8.5/10 |
| Visibility | 5/10 | 8/10 |
| Engineering integrity | 7/10 | 8/10 |

**Now delivered (was broken/hidden):** live score, visible Review Queue, honest timeline, non-silent errors, keyboard/button parity, category→queue filtering, bulk review, attention coverage, accessible dialog, impact for all types.

**Remaining issues:**
1. 🟡 Session recovery of last item/page (P1-7) — not done.
2. 🟡 Live end-to-end UI verification pending for code-traced rows.
3. ⚪ `visitedPages` not persisted across reloads (by design; revisit if reviewers span sessions).
4. ⚪ Category→queue map (`QUEUE_OBJECT_TYPE`) is still a small explicit map; acceptable but not fully data-driven.

**Phase 4 readiness:** trust + visibility gaps closed. Ready once the live click-through confirms the code-traced rows.
