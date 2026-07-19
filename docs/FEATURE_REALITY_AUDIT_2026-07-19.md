# Feature Reality Audit — 2026-07-19

Verified by tracing render chains in code (not just existence). Legend: ✅ Delivered · 🟡 Partial · 🟠 Hidden · 🔴 Missing · ⚫ Broken

**Scores:** Delivery 6/10 · Report honesty 5/10 · User visibility 5/10 · Engineering integrity 7/10

## Verdict Table

| Feature | Status | Evidence |
|---|---|---|
| Navigation tree | ✅ | Mounted via `WorkspaceShell` nav slot, `DocumentWorkspace.tsx:460` |
| Navigation chips | ✅ | `quickNav` slot, `WorkspaceShell.tsx:323` |
| Accessibility Center / Readiness panel | ✅ | Special view `readiness`, reachable from nav + chips |
| Accessibility score badge | 🟡 | Renders in toolbar (`WorkspaceShell.tsx:245`) but see ⚫ live updates |
| Live score updates | ⚫ | `watchVersion` refetches only markdown (`DocumentProvider.tsx:91-99`); readiness never refetched → score frozen until reload |
| Priority sorting | ✅ | Default sort + dropdown (`ReviewerWorkspace.tsx:16,69`); simplistic (severity+confidence only) |
| Review Queue | 🟠 | Works, but lives in bottom panel that defaults CLOSED (`BOTTOM_OPEN_KEY` initial false) behind chevron labeled with elapsed time |
| Correction cards | ✅ | `CorrectionHistoryList` in queue + 8 detail panels |
| Evidence panel | ✅ | `EvidenceBreakdown` in every card |
| Confidence labels | ✅ | `CorrectionHistoryList.tsx:121,182-189` |
| Accessibility impact | 🟡 | Renders, but only 6 hardcoded object types; others silently get none |
| Timeline / Recent activity | ⚫ | Sorted by `created_at` = pipeline creation time, not review time (`BottomPanel.tsx:30`) — order is meaningless; also inside hidden Console tab |
| Coverage | 🟠🟡 | Console tab of closed bottom panel; measures issue resolution not page attention; counts `auto_applied` as "reviewed" |
| Workspace memory | 🟡 | Global prefs persist (sort/tab/center-mode/focus/bottom). Document-specific memory + session recovery: missing |
| Keyboard shortcuts | ✅ | n/p/a/r/i/u/e/j// + on-screen legend + `?` overlay all wired |
| Toast undo | 🟡 | Button accept/reject shows undo toast; keyboard `a`/`r` path (`runAction`) bypasses toast AND has no error handling |
| Error boundary | ✅ | `app/error.tsx` (Next.js auto-mounts) |
| Processing status | ✅ | `DocumentWorkspace.tsx:367-378` |
| Analytics / Insight card | 🟡 | One sentence; renders only if ≥3 corrections AND dominant type ≥40% — frequently absent |
| Review progress | ✅ | Bar + accepted/rejected/ignored breakdown (`ReviewerWorkspace.tsx:220-240`) |
| Bulk review | 🔴 | `BulkActions` used only in `ImageGrid`; absent from review queue |
| Category drill-down | 🟡 | Fix Next routes to whole views via 5-entry hardcoded `catMap` (`DocumentWorkspace.tsx:332-338`); does NOT filter the queue; unknown categories dump to Validation |
| Category → queue filtering | 🔴 | Queue filters exist but are never linked from categories |
| Jump to object / scroll | ✅ | `select()` + `jumpToObject()` on card Jump, overlay click, nav |
| PDF highlights / semantic highlights | ✅ | `pdfOverlays` built from all object types, type-toned |
| Auto-advance | 🟡 | Works on Pending tab only (resolved item exits filter → clampedIndex points at next); on All tab, pointer doesn't advance |
| Shortcuts overlay (`?`) | 🟡 | Renders; no focus trap / Escape / aria-modal |
| Silent data-load failures | ⚫ | Every fetch `.catch(() => empty)` (`DocumentProvider.tsx:37-49`) — backend error renders as "no issues" |

## Dead Code

None found. All hooks/utils consumed (grep-verified: `usePersistedState`, `useListReviewKeyboard`, `useArrowKeyTabs`, `validationCategories`, `correctionPreview`, `EvidenceBreakdown` all imported by live render paths). `BulkActions` is live but only in ImageGrid.

## Report vs Reality

`AI_EXECUTION_FRAMEWORK_REPORT.md` overstatements:

1. **Feature 4 (Coverage)** claimed delivered — actually hidden + measures the wrong thing (spec said attention, not resolution).
2. **Feature 5 (Timeline)** claimed delivered — ordering is broken; not a timeline.
3. **Feature 10 (Workspace memory)** claimed delivered — session recovery and document-specific memory absent (~40% done).
4. **Phase 3 validation checklist** shown fully checked — at least 4 boxes ("coverage accurately reflects reviewer attention", "timeline communicates meaningful progress", live health updates, "workspace memory behaves consistently") were not true.
5. "Live Updates" spec requirement (score/category/blocking counts update on every accept) is not met at all — never flagged in the report.

## Answers

1. **Invisible features:** Coverage, Recent Activity (closed panel → Console tab), insight card (conditional thresholds).
2. **Never discovered by ordinary reviewer:** Review Queue itself (closed by default), coverage, timeline, `?` overlay (no visible hint outside queue legend).
3. **Should have changed UI visibly but didn't:** Phase 3 overall — with the bottom panel closed, a returning user sees an essentially unchanged workspace.
4. **Overstated claims:** items above.
5. **Fully delivered:** ~52% (15/29 rows).
6. **Partially delivered:** ~31% (9/29).
7. **Invisible/hidden:** ~14% — includes the product's core review surface.
8. **Fix before Phase 4:** list below.

## Must Fix Before Phase 4 (severity order)

1. ⚫ Refetch readiness/accessibility report after corrections change — frozen score breaks the product's core promise.
2. 🟠 Open the bottom panel (Review Queue) by default when pending corrections exist.
3. ⚫ Add `reviewed_at` server-side; sort timeline by it (or remove the "Recent Activity" label).
4. ⚫ Distinguish fetch errors from empty data — compliance tool must never render "failed to load" as "clean".
5. 🟡 Keyboard accept/reject: add toast undo + error handling (parity with button path).
6. 🟡 Category drill-down should filter the Review Queue, not switch views; replace hardcoded `catMap`.
