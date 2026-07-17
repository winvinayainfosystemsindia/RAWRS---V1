# RAWRS Reviewer Experience Audit — 2026-07-17

**Status: Audit only. No code changed.** Produced by direct, live interaction with the shipped frontend (both dev servers running, real processed jobs, Chrome DevTools Protocol) plus a full re-read of `docs/RAWRS_DESIGN_BIBLE_v1.0.md` (§0-45, Final Outputs) and direct inspection of `WorkspaceShell.tsx`, `NavChips.tsx`, `ValidationIssueTable.tsx`, `ContextInspectorRail.tsx`, `ObjectInspectorFrame.tsx`, `PdfViewer.tsx`, `globals.css`. Scope, per the request: frontend reviewer experience only, backend treated as fixed, missing backend capabilities ignored.

**Disclosed limitation, upfront:** every processed job in this dev environment (29 checked) has 0 validation issues, 0 images, 0 tables, 0 footnotes/lists/callouts, and every source PDF 404s (a pre-existing corpus/environment gap disclosed since Phase F-4.3/F-4.5). This audit could exercise the empty/orientation states live but **not** the populated Inspector, PDF-overlay-click, or object-review flows — those are assessed from direct code reading (`ContextInspectorRail.tsx`, `ObjectInspectorFrame.tsx`, `PdfViewer.tsx`), not live interaction. Flagged per finding below where this distinction matters.

---

## Executive Summary

The architecture is sound — this audit does not dispute the Design Bible's 7.5/10 or its "extend, don't replace" verdict on `WorkspaceShell`'s 3-zone model. But **the reviewer's actual first five minutes with a document are worse than the architecture underneath them deserves.** The gap isn't structural, it's that recent additions (the R-1.1 toolbar/nav-chips work) were bolted onto a screen that already had unresolved density and hierarchy problems, and in two places (Overview, Validation) actually made redundancy worse rather than better. A remediator doing this 8-10 hours a day will feel this in the first hour, every day: five stacked rows of chrome before any document content, two controls with the same name, three places to see the same validation data, and a toolbar with no visual hierarchy at all — every element (Score 100%, Page 1, Search, Export, theme toggle) reads at identical weight.

None of this requires new backend capability. All of it is fixable within the existing component set.

---

## Strengths

1. **The 3-zone shell genuinely works.** Nav / Center / Rail with persisted layout, `maxSize` guards, and Focus Mode is not just architecturally defensible — it *feels* right live. Collapsing to Focus Mode and back was instant, no layout jank, no lost state.
2. **The Inspector tab shell (`ObjectInspectorFrame`) is a real strength.** One shared component, real ARIA tabs (`role="tablist"`/`role="tab"`/`role="tabpanel"`, roving tabindex via `useArrowKeyTabs`), used identically across all 6 object types. This is the single best piece of reuse discipline in the codebase — confirmed by reading it directly, not just citing the Bible's claim.
3. **Keyboard fundamentals are real, not cosmetic.** Focus-visible rings are computed (verified via the accessibility tree, not just source), the skip link works, and every tab bar in this session's testing was a genuine ARIA-tabs pattern, not a div-soup approximation.
4. **The Export menu is exactly right.** A native `<details>`/`<summary>` disclosure with three real download links, correct URLs, no JS dropdown machinery — the kind of restraint the product's register calls for.
5. **Empty states, where they exist, are honest and specific** ("No footnotes or endnotes were detected in this document," not a generic "No data"). Low effort, real payoff for trust.
6. **The color system is already accessible and battle-tested** — GitHub's dark/light pairing (`#0d1117`/`#58a6ff` family), not a novel unverified palette. This is a strength this audit found worth defending explicitly (see Bible Challenge #1 below).
7. **Layout persistence is invisible and correct.** Reload, and panel sizes/Focus Mode/center-view mode all survive — exactly the kind of "don't make me re-set-up my screen" detail that matters at 8-10hr scale and is easy to skip.

---

## Weaknesses, by Critique Axis

### Workflow & Cognitive Load
The Bible's own Journey Mapping (§5) correctly identifies Review/Compare as the highest-fatigue stages — but this audit's live testing surfaces a **Stage 0/1 problem the Bible under-weights**: before a reviewer reaches any document content, they parse five stacked rows (collapsible Overview bar → 14-chip nav row → filename/score/toolbar row → center-view tab row → nav-tree mode-tab row). That's roughly 200px of pure chrome, all at equal visual weight, before a single piece of document data is visible. Opening the Overview panel — the most prominent, full-width, pre-expanded-looking element on the page — surfaces a **13-step internal pipeline checklist** ("Load Mathpix Markdown," "Compare Mathpix Output ↔ Source PDF," "OCR Verification," "Layout Analysis") as the first content a reviewer sees. This is engineering telemetry, not reviewer orientation — it answers "did the pipeline run," not "how bad is this document, where do I start" (the actual Stage 1 question the Bible itself names in §5). The reviewer-relevant "Verification Summary" content exists but is scrolled below 13 rows of plumbing a remediation professional has no vocabulary for.

### Navigation & Discoverability
**Confirmed live, a real bug, not a style nit:** there are two separate controls both accessible-named "Overview" (`WorkspaceShell`'s section-header button and `NavChips`' "Overview" chip), positioned two rows apart, both bound to the identical `overviewOpen` state toggle in `DocumentWorkspace.tsx`. A keyboard or screen-reader user tabbing through hears "button, Overview … button, Overview" with zero differentiation. This is a direct byproduct of the R-1.1 NavChips work landing on top of a control that already existed, without checking for the collision.

Separately: `NavChips` renders 14-18 items (every object type plus Metadata/OCR/Reading Order/Page Labels/Corrections/Readiness/disabled Bookmarks) as **undifferentiated, icon-free text pills**. Every category gets identical visual weight whether it's the thing the reviewer needs most (Validation, on a document with real issues) or something structurally irrelevant to this specific document (Callouts, on a document with none). There is no visual signal for "this category has something you need to look at" versus "this category is empty" beyond a small `0` badge that's low-contrast against the dark pill.

### Panel Organization / Inspector
Structurally sound (see Strengths #2), but one real redundancy: **the same validation data is reachable through three different surfaces simultaneously** — the full `ValidationIssueTable` in the Special View (via the Validation chip), the *same* full `ValidationIssueTable` again inside `ContextInspectorRail` whenever nothing is selected (its default/fallback state, confirmed in `ContextInspectorRail.tsx` lines 27-40), and a one-line summary in `BottomPanel`'s "Validation" tab. Three surfaces, three different fidelities, no indication they're the same underlying data, no cross-navigation between them.

### PDF Interaction *(assessed from code, not live-populated — see disclosed limitation)*
`PdfViewer.tsx`'s overlay/highlight/zoom/scroll-to-highlight machinery reads as correct and appropriately scoped (confirmed this session: `jumpTarget.nonce`-keyed `scrollIntoView`, same pattern as the Markdown pane). The one live-confirmable finding: **the 404 error state is a raw, developer-facing string** — `Unexpected server response (404) while retrieving PDF "http://127.0.0.1:8000/api/documents/.../source-pdf".` — including a bare backend URL. In this dev environment it's a corpus artifact, but the error-rendering *code path itself* is not written for a reviewer-facing audience; if a source file is ever moved/deleted in production, a remediation professional sees a raw fetch error with an internal API URL in it, not an actionable message ("The source PDF is unavailable — try re-uploading" or similar).

### Markdown Interaction
Read-only CodeMirror pane with a discoverable "Find / Replace (Ctrl+F)" control and a visible `read-only` badge — both good, both actually present in the live UI. No new issues found beyond the Bible's own disclosed open item (scroll/cursor position lost on every `document_version` remount) — not escalated here, it's genuinely low-frequency.

### Reviewer Context Preservation
This is the Bible's own §9 finding (context-preserving-editing gap in bulk grids), and this audit's live pass corroborates it structurally: the moment a reviewer clicks a full-width Special View chip (Images/Tables/Validation/etc.), the PDF and Markdown panes disappear entirely from the DOM (`WorkspaceShell`'s `mode="special"` renders a single full-width pane, confirmed in `WorkspaceShell.tsx`). Bible §9's source-strip/Peek resolution is the right fix and this audit does not propose an alternative — but flags that it is **still the single largest unresolved reviewer-experience gap in the product**, unchanged since F-4.2 first found it, now three audits deep without landing in code.

### Visual Hierarchy & Typography
Confirmed live: **the toolbar row has zero typographic hierarchy.** "Score 100%" (arguably the single most important orientation number in the product, per the Bible's own Journey Stage 1) renders at the same size/weight as "Page 1," the theme-toggle button, and "Focus Mode" — all `text-xs`/`text-sm` variants with no scale differentiation. The Bible's own §39 token set (`heading-md`, `body-sm`, `label-caps`) is specified but **not implemented anywhere in the toolbar** — confirmed by direct inspection of the rendered page and `WorkspaceShell.tsx`'s className strings, which use ad hoc `text-xs`/`text-sm` throughout, not a scale. The document title (`<h1>`) is the only element that reads with real weight, and it's a long filename, not a value that helps orientation.

### Spacing & Information Density
14-18 nav chips + a full toolbar row + 6 center-view tabs + 5 nav-tree-mode tabs is a genuinely high control count for the first screenful. At a realistic professional-laptop width (tested at 1024px live), the chip row wraps to two lines, which *increases* the chrome-before-content tax rather than degrading gracefully. Nothing breaks, nothing overflows — but density keeps climbing every time a new top-level affordance is added (Search, Export, page indicator, readiness score all landed in the same R-1.1 pass that also added the chip row), and nothing in the current design has an explicit "chrome budget" to push back against that.

### Accessibility
Foundations are real (see Strengths #3), but this audit found one genuine, confirmed defect (the duplicate "Overview" control above) that automated `jest-axe` testing would not catch on its own (both elements are individually valid buttons; the problem is discoverability/redundancy, not a rule violation) — a reminder that the Bible's own §37 finding (test coverage shrinking relative to surface area) has a live consequence, not just a ratio problem. Live screen-reader testing (NVDA/JAWS) still has never been performed (Bible §43 already names this as a standing, unclosed gap) — this audit does not close it either, only re-confirms it's overdue given how much surface area has shipped since the last CDP-based pass.

### Keyboard Workflow
**New finding, not in the Bible:** natural DOM tab order puts all 14-18 NavChips *before* Search/Export/Focus Mode/theme toggle. A keyboard-only reviewer must tab through the entire chip row every time to reach the toolbar's actual action controls — a tax that didn't exist before R-1.1 added the chip row above the toolbar. This compounds the Bible's own §21 finding (keyboard coverage stops at `ReviewerWorkspace`) with a second, narrower problem: even where keyboard support *does* exist, its reach order is now worse than before this session's own additions.

### Interaction Quality / Micro-Friction
- The "Completed in 16.3s" element renders as a real `<button>` (confirmed via the accessibility tree) with no visual or semantic indication of what activating it does — an affordance mismatch: it reads as a status readout but behaves like a control.
- The Export disclosure and the "Overview" section both use a chevron-rotation pattern for expand/collapse, but NavChips' "Overview" *chip* uses `aria-pressed` styling instead — three different visual languages for "this is currently open/active" within one screen.
- Severity tabs (this session's own R-1.1 addition, `ValidationIssueTable`) are keyboard-correct but untested against real multi-issue data in this environment — flagged, not claimed.

### Responsiveness
Confirmed live at 1024×768: nothing overflows or breaks, chips wrap cleanly. This audit does not dispute the Bible's §29 "Postpone, desktop-first by design" verdict — RAWRS is correctly not designing for phone/tablet. The only addition: the wrap behavior at laptop-adjacent widths makes the density problem above measurably worse, which is a reason to solve the chrome-density problem on its own merits, not a reason to reopen responsive design.

---

## Where This Audit Challenges the Design Bible

**1. Do not migrate to V3 Sentinel's specific color hex values — keep the shipped token *values*, adopt only the token *architecture*.**
The Bible (§26, §39) recommends adopting V3's indigo/teal/amber/coral palette wholesale as the formal token set. Live inspection of `globals.css` shows the shipped palette is not an ad hoc placeholder — it's a deliberate, sourced choice ("GitHub's light/dark pairing — a proven, accessible hue match," per the file's own comment), already contrast-verified, already familiar to the exact user population RAWRS targets (technical professionals who likely already read GitHub/VS Code dark themes daily). Swapping to V3's unverified mockup values buys aesthetic parity with a Stitch screenshot at the cost of re-verifying every contrast pair from scratch, for a population that already finds the current palette legible. **Recommendation:** adopt §39's spacing scale, type scale, and icon system (real, currently-missing gaps) but keep the current color hex values under the existing token names — the Bible conflates "formalize the token architecture" (worth doing) with "replace the values" (not justified by any evidence gathered this session or the Bible's own).

**2. §13's "Merge the progress bar and BottomPanel" recommendation should be resequenced *before*, not after, the R-1.1-style toolbar additions it's adjacent to.**
This audit found the Overview-button duplication precisely because a new affordance (NavChips) landed without checking for collision with an existing one. The Bible's roadmap (§41) ranks Review Queue consolidation implicitly low (folded into general Bottom Panel discussion, not separately ranked) — this audit recommends treating **redundant-affordance audits as a mandatory pre-check on every future toolbar/nav addition**, not just a one-time §13 cleanup item, because this session is direct proof the failure mode recurs each time new chrome is added to an already-dense header.

**3. The Bible's §32 Empty States "no shared component yet, YAGNI" call is right for *content* empty states but should be revisited for the Overview panel specifically.**
§32 correctly declines to build a shared `<EmptyState>` component for scattered per-panel messages. But the Overview panel's default content (`ResultsDashboard`'s pipeline checklist) is not an empty state — it's a **wrong-audience state**: real content, rendered to the wrong reader. This is a different problem than §32 addresses and deserves its own line item rather than being implicitly covered by it.

**4. §24/§25 (Typography, Icons) were explicitly flagged "not independently audited this session" in the Bible — this audit closes that gap with a negative finding the Bible didn't have.**
The Bible recommended adopting Material Symbols Outlined and V3's type scale, reasoning from Stitch screenshots. This audit's live inspection confirms neither is implemented anywhere in the shipped toolbar/nav-chip chrome (zero icons in interactive controls; toolbar text is uniform `text-xs`/`text-sm`, no scale). This isn't a disagreement with the Bible's recommendation — it's confirmation the recommendation is correct and now has a concrete, live-verified reason to move up in priority: the toolbar's *current* lack of hierarchy is measurably worse than the Bible's abstract "not yet audited" framing suggested.

---

## Concrete Recommendations

1. **Remove the duplicate Overview control.** Keep exactly one — the NavChips "Overview" chip is the more consistent location (same row as every other section toggle); remove the separate `WorkspaceShell`-level "OVERVIEW" section-header button, or merge its chevron affordance into the chip itself.
2. **Re-order DOM/tab sequence** so Search/Export/Focus Mode/theme toggle precede the NavChips row, or give the chip row a `role="navigation"` landmark with a "skip to toolbar" affordance — either removes the 14-18-stop keyboard tax.
3. **Demote `ResultsDashboard`'s pipeline checklist**, or retitle/relocate it under a clearly-labeled "Processing Log" / "Pipeline Diagnostics" disclosure separate from "Overview," and promote the reviewer-relevant Verification Summary to be the *first* thing Overview shows.
4. **Collapse the three validation surfaces into one navigable set**: keep the Special View as the canonical full table; make the Rail's fallback state and the Bottom Panel's Validation tab both *link into* that same view (jump + scroll-to-issue) rather than re-rendering independent copies.
5. **Add real typographic hierarchy to the toolbar**: promote Score/readiness to a visually distinct treatment (larger, colored by ready/not-ready state — the banner-and-badge pattern already built for the Validation Center readiness banner this session is the right reusable shape) versus everything else staying at current secondary weight.
6. **Add icons to NavChips and toolbar actions** (Material Symbols, per Bible §25) — even without full V3 token adoption, icon+label pills read faster than text-only pills at this item count, independent of the color-token debate above.
7. **Rewrite the PDF-load error message** for a reviewer audience — no raw URLs, an action-oriented recovery hint.
8. **Give "Completed in Xs" either a real affordance (make it visibly clickable, e.g., to expand pipeline timing detail) or render it as static text**, not an unlabeled-purpose button.
9. **Standardize the expand/collapse visual language** (chevron rotation, consistently, everywhere a section opens/closes) rather than mixing chevron and `aria-pressed`-pill patterns for the same semantic action.

---

## Prioritized Implementation Roadmap

| Rank | Item | Effort | Reviewer Productivity Gain | Why this rank |
|---|---|---|---|---|
| 1 | Remove duplicate Overview control | Trivial (<1hr) | Low magnitude, but removes a confirmed, embarrassing-if-noticed defect at zero risk | Free — no design ambiguity, ships same-day as `error.tsx` |
| 2 | Toolbar typographic hierarchy for Score/Page/readiness | Small (half-day) | Medium — directly serves Journey Stage 1 orientation, the thing a reviewer does dozens of times a day | Reuses the readiness-banner pattern already built this session; no new component |
| 3 | Re-sequence keyboard tab order (chips after toolbar) | Small (half-day) | Medium — compounds across every keyboard-first reviewer, every session, every day | Pure DOM/markup reorder, no new state |
| 4 | Demote/retitle the pipeline checklist, promote Verification Summary | Small (half-day–1 day) | Medium-High — fixes the very first thing a reviewer sees on every document | Content/layout change only, `ResultsDashboard` itself untouched |
| 5 | Collapse the 3 redundant validation surfaces into 1 canonical + 2 linked views | Medium (1-2 days) | High — removes a real "which of these is the real one" confusion, compounds over 8-10hr sessions | Touches 3 components; needs the jump-to-issue plumbing `PdfViewportContext` already has a precedent for |
| 6 | Icons on NavChips + toolbar (Material Symbols) | Medium (1-2 days, one-time icon-system wiring + retrofit) | Medium — scanability gain on the highest-traffic navigation surface in the product | Bible §25 already specified this; this audit just raises its priority |
| 7 | Reviewer-facing PDF error message | Trivial-Small (a few hours) | Low day-to-day (rare trigger), High when it matters (a real missing-file incident shouldn't look like a stack trace) | Low effort, asymmetric downside if skipped |
| 8 | Standardize expand/collapse visual language | Small (half-day, opportunistic) | Low-Medium, mostly a polish/trust signal | Bundle into whichever of the above touches the most affected components |
| — | *(Unranked, cross-reference only)* Context-preserving editing / source-strip (Bible §9) | Per Bible §40 (Medium) | Per Bible (High) | Already the Bible's own #2 roadmap item — this audit does not re-rank it, only confirms it remains the single largest gap found by any method this session |

**Sequencing note:** items 1-4 and 7-8 have no dependency on Bible §41's `error.tsx` milestone and could land in the same or an adjacent milestone without disrupting that roadmap's own sequencing. Item 5 (validation-surface consolidation) is new-to-this-audit and should be added to the Bible's roadmap as its own line item — it wasn't previously named because the Bible's §10/§13 sections analyzed each surface independently rather than as three simultaneous views of one dataset.

---

## What This Audit Does Not Change

Per the Bible's §44 Implementation Contract, restated here: this document recommends, it does not authorize implementation. Nothing here should be built without the same plan → implement → test → verify → document → wait-for-approval cycle every prior milestone has followed. This audit's roadmap is additive to, not a replacement for, the Bible's own §41 roadmap — `error.tsx` remains the most overdue single item in the project regardless of anything found here.
