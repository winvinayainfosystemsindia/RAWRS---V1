# RAWRS Large Document Mode — Design & Architecture — 2026-07-15 (Phase R-1.0)

Design + audit only, per the ticket — no code changed, no virtualization implemented, no refactoring performed. Grounded in direct inspection of `WorkspaceShell.tsx`, `DocumentWorkspace.tsx`, `PdfViewer.tsx`, `SemanticNavTree.tsx` (structure confirmed via prior sessions' direct reads and this session's `DocumentDataContext.tsx`/`DocumentProvider.tsx` reads), `SelectionContext.tsx`/`PdfViewportContext.tsx`/`MarkdownViewportContext.tsx`, `MarkdownEditor.tsx`, `DocxPreview.tsx`, and vendor documentation confirmed live via Context7 for `react-pdf` (page/scale remount behavior) and CodeMirror's `@codemirror/view` (viewport virtualization). Builds directly on `DOCUMENT_WORKSPACE_LAYOUT_AUDIT_2026-07-14.md` (named Large Document Mode as the single biggest UX gap) and `FRONTEND_STABILIZATION_AUDIT_2026-07-14.md` (confirmed the workspace architecture is sound and ready for this feature wave).

---

## 1. Current Rendering Architecture

**Data loading and state shape.** `DocumentProvider.tsx`'s `DocumentPoller` fetches the entire document's data in one shot on load: 13 parallel REST calls (`getValidation`, `getImages`, `getTables`, `getFootnotes`, `getHeadings`, `getLists`, `getCallouts`, `getMetadata`, `getPages`, `getReadingOrder`, `getPageLabels`, `getCorrections`, `getReadiness`), each returning its type's **full, unpaginated collection** for the whole document, dispatched as one `LOAD_RESULTS` action into `DocumentDataContext.tsx`'s `useReducer`. After that, `watchVersion()` polls only `getDocument` (a lightweight summary) every 4s and re-fetches **only Markdown** when `document_version` changes — the object collections themselves are never re-fetched from the server after initial load; they're updated in-place via optimistic `UPDATE_X`/`REPLACE_X` dispatches when the reviewer takes an action in this tab. This is a one-time-cost, not-recurring architecture — a real finding worth stating plainly, since it means the scaling concern is about *initial load* and *client-side render*, not repeated network cost.

**Selectors are unmemoized.** `selectHeadings(state)`, `selectTables(state)`, etc. (`DocumentDataContext.tsx:251-260`) are plain `Object.values()` calls with no memoization. `DocumentWorkspaceContent` (`DocumentWorkspace.tsx:156-162`) calls seven of these directly in its render body on every render, producing seven fresh array allocations regardless of whether the underlying data actually changed.

**PDF rendering.** `PdfViewer.tsx` uses `react-pdf`'s `<Document>`/`<Page>` in **single-page view** — exactly one page is ever mounted at a time (confirmed: no continuous-scroll, no thumbnail strip). Confirmed via Context7 (`react-pdf`'s own source): `Page` computes a `pageKey = "${pageIndex}@${scale}/${rotate}"` and uses it to key the `Canvas`/`TextLayer`/`AnnotationLayer` components — meaning **every page-turn or zoom-step change forces a full remount and re-rasterization** of those layers, not an incremental redraw. The underlying `pdfjs-dist` engine itself is not directly interrogated here, but its well-established behavior (parsed page objects are cached internally once requested) means re-visiting a previously-seen page skips PDF-stream re-parsing, even though the canvas redraw itself is not cached.

**Overlay rendering.** `DocumentWorkspace.tsx`'s `pdfOverlays` `useMemo` (lines 107-125) builds **one combined array spanning every semantic object on every page of the whole document**, with a dependency array of `[state]` — the entire reducer state object, not the specific collections it reads. `PdfViewer.tsx` then does `overlays?.filter(o => o.pageNumber === pageNumber)` (line 55) **on every render** to narrow this to the current page. This is a "rebuild everything, use a tiny fraction" pattern: any dispatch anywhere in the app (accepting one correction, for instance) invalidates the memo and rebuilds the full cross-document array, and every page-turn or zoom event re-runs an O(n) linear filter over that same full-document array just to find the handful of objects on one page.

**Nav tree rendering.** `SemanticNavTree.tsx`'s "By Type" mode renders `ExpandableCategory` accordions for Headings/Tables/Lists/Callouts/Footnotes with **every item in every category rendered as a full DOM row**, unconditionally, with no windowing. "Search" mode does a synchronous substring scan across all types on every keystroke (capped at 50 *results*, but not capped in *scan cost* — every keystroke re-scans the full corpus), with no debounce.

**Markdown rendering.** `MarkdownEditor.tsx` is CodeMirror 6, read-only in the main workspace. Confirmed via Context7 (`@codemirror/view`'s own documentation): *"The view efficiently handles large documents by only rendering visible portions while maintaining smooth scrolling and accurate positioning."* This is a real, already-built virtualization — RAWRS gets it for free from the editor library, not from any RAWRS-authored code.

**DOCX rendering.** `DocxPreview.tsx` converts the entire DOCX to HTML via `mammoth` and injects it via `dangerouslySetInnerHTML`, re-running on every `document_version` bump. Because `WorkspaceShell`'s `centerViews` prop holds JSX element *descriptions* for `pdf`/`markdown`/`docx` but only the currently-selected one(s) are actually reconciled into the rendered tree, **`DocxPreview`'s component function — and its `mammoth` conversion — only executes when the DOCX pane is actually visible** (one of the six center-view presets). This is already correctly lazy; no fix needed here.

**Synchronization contexts.** `SelectionContext`, `PdfViewportContext`, `MarkdownViewportContext` each hold **O(1) state** — a single current selection, a single jump target, never a collection — and are already `useMemo`'d and proven loop-safe (the M-4.2 infinite-loop fixes, cited in their own code comments). Document size does not change these contexts' complexity at all.

**Panel management.** `react-resizable-panels`, now with `autoSaveId` persistence and `maxSize` constraints (Phase F-4.3). No virtualization of panel *content* — that's each panel's own concern, addressed above per-component.

**Special Views** (Images/Tables/Headings/Footnotes/Lists/Callouts grids). Same unbounded-array-map pattern as the nav tree, one card per object, no windowing.

**Correction rendering.** `CorrectionsPanel`/`ReviewerWorkspace` map the full `selectCorrections(state)` array with no windowing.

---

## 2. Performance Bottlenecks (ranked by expected impact at the ticket's stated scale — 500+ pages, thousands of objects, hundreds of corrections/images)

1. **`pdfOverlays`'s rebuild-everything-then-filter pattern.** The single highest-impact bottleneck: an O(n) full-document rebuild on any state change, followed by an O(n) linear filter on every page-turn/zoom-step — compounding two costs that a page-indexed structure would each turn into O(1).
2. **Unmemoized top-level selectors.** Seven-plus fresh array allocations on every render of `DocumentWorkspaceContent`, regardless of cause (a zoom change, a selection change, anything).
3. **`SemanticNavTree`'s unwindowed "By Type" lists.** The single biggest *DOM-node-count* risk in the workspace — this is exactly where "thousands of semantic objects" becomes a real, not hypothetical, problem (long paint times, sluggish scroll, large accessibility tree).
4. **`SearchMode`'s un-debounced full-corpus scan on every keystroke.**
5. **Initial `loadResults()` fetch** — 13 unpaginated collection fetches; a one-time cost per document open, potentially significant for a genuinely large book, but not a recurring cost (confirmed: subsequent polling never re-fetches these collections).
6. **`react-pdf`'s per-navigation full remount of Canvas/TextLayer/AnnotationLayer** (confirmed via Context7's `pageKey` mechanism) — every page-turn/zoom-step is a full re-rasterization. Bounded per-page (only one page ever mounted), but combined with #1, page-turning on a large document could feel less than instant.
7. **`DocxPreview`'s full-document `mammoth` conversion** — potentially slow in absolute terms for a 500-page book's DOCX, but bounded in frequency (only runs when actually visible) and is the least-used of the six center-view modes. Lower priority.

**Not bottlenecks — confirmed sufficient, no action needed:** `MarkdownEditor` (CodeMirror already virtualizes, confirmed via vendor docs), `SelectionContext`/`PdfViewportContext`/`MarkdownViewportContext` (O(1) regardless of document size), panel management (`react-resizable-panels` scales fine, its cost is proportional to panel *count*, which never grows with document size).

---

## 3. Recommended Virtualization Strategy

For every proposed item: Why / Existing infra reused / Backend dependency / Expected gain / Complexity / Risk.

### (a) Index PDF overlays by page

- **Why:** eliminates the compounded rebuild-then-filter cost (bottleneck #1) — the single highest-leverage fix in this design.
- **Existing infra reused:** a pure restructuring of the existing `pdfOverlays` `useMemo` — same per-page output shape, computed once via `Map<number, Overlay[]>` keyed on the specific typed collections (`selectHeadings`, `selectTables`, etc.), not the whole `state` object. Zero new dependencies.
- **Backend dependency:** none.
- **Expected gain:** turns an O(n) filter (n = total document-wide object count) into an O(1) map lookup on every page-turn and zoom step, and narrows the memo's invalidation to only fire when the relevant collections actually change (not on selection/zoom/jump-target changes, which today all share the same `[state]` dependency and needlessly invalidate the memo).
- **Complexity:** low — a targeted, mechanical refactor of one `useMemo`.
- **Risk:** low — output shape is identical to today's; straightforward to verify.

### (b) Memoize the top-level collection selectors

- **Why:** avoids seven-plus unnecessary array reallocations on every render regardless of cause (bottleneck #2).
- **Existing infra reused:** `useMemo`, already the idiom this exact file uses for `pdfOverlays` and `markdownFlashLines` — not a new pattern.
- **Backend dependency:** none.
- **Expected gain:** at "thousands of objects" scale, avoids thousands of unnecessary array-copy operations per unrelated re-render (today, even a zoom-level change re-derives every collection).
- **Complexity:** trivial.
- **Risk:** trivial.

### (c) Virtualize `SemanticNavTree`'s "By Type" lists

- **Why:** the one place DOM-node count scales linearly and unboundedly with the ticket's own named target scale — the clearest case in this whole design where a real problem (not a hypothetical one) exists at 500+ pages / thousands of objects.
- **Existing infra reused:** **none currently exists.** Confirmed: no windowing/virtualization library is installed in this project today. This is the one place in this design where adding a small, focused, actively-maintained dependency (e.g., a headless virtualization primitive) is likely justified rather than avoidable — named explicitly here as a decision requiring approval, per the ticket's own instruction to only introduce new infrastructure where evidence demonstrates necessity. No dependency choice is being made in this design-only milestone; that decision belongs to the implementation milestone, informed by the benchmark in §5.
- **Backend dependency:** none.
- **Expected gain:** caps rendered DOM nodes to viewport size (dozens) regardless of total collection size (thousands) — the single highest-leverage accessibility-and-performance fix in this design for the ticket's stated scale.
- **Complexity:** medium — a windowed list must compose with the existing `ExpandableCategory` accordion pattern (per-category open/closed state), meaning each open category needs its own virtualized sub-list, not one flat virtualized list spanning categories; must also preserve existing keyboard/ARIA behavior.
- **Risk:** medium — this is the one item that touches a currently-working, already accessibility-tested surface and needs explicit care not to regress it (see §6).

**Explicitly not recommended without further evidence:** virtualizing the Special View grids (Images/Tables/etc.). "Hundreds of images," the ticket's own stated scale for that surface, is well within normal unvirtualized-React tolerance — a materially smaller order of magnitude than "thousands of semantic objects" (the nav tree's scale). Per the ticket's own "benchmark before optimizing" principle, this should not be preemptively virtualized; only add windowing there if a benchmark specifically shows a problem.

### (d) Debounce `SearchMode`'s input

- **Why:** currently un-debounced full-corpus linear scan on every keystroke (bottleneck #4).
- **Existing infra reused:** the canonical `useDebounce` hook is already documented as this project's own reference pattern (`.claude/rules/ecc/typescript/patterns.md`) — a tiny, zero-dependency, well-known idiom, not a new library.
- **Backend dependency:** none.
- **Expected gain:** bounds the linear scan to once per debounce window instead of once per keystroke.
- **Complexity / Risk:** trivial / trivial.

### (e) PDF page caching / lazy loading — confirm, don't build

- **Why named in the ticket, but evidence argues against building anything new:** confirmed via Context7 that (1) `<Document>` parses the whole PDF file once per load, a one-time cost, not recurring; (2) `pdfjs-dist` internally caches parsed page objects, so revisiting a page skips stream re-parsing; (3) the Canvas/TextLayer/AnnotationLayer *do* fully remount on every page/zoom change — this is inherent to canvas-based PDF rendering (a rasterized bitmap isn't cheaply resumable across a scale change), not a defect in RAWRS's code.
- **Recommendation:** the existing single-page-at-a-time view is already the correct, minimal architecture — a 500-page PDF costs the same to display page 250 as a 5-page PDF costs to display page 3. **Do not build a custom page-cache layer.**
- **Open question, not a proposed change:** whether the backend serves the source PDF with HTTP range-request support, which affects initial-load latency for a very large PDF file. This was not verified this session and should be confirmed against the actual static-file-serving configuration before assuming either way.
- **Backend dependency:** possibly, only if the benchmark (§5) shows the initial whole-file fetch is a real problem.

### (f) Markdown pane — no change

- **Why:** CodeMirror already virtualizes (confirmed via vendor docs above) — this is a solved problem RAWRS gets for free.
- **Separately noted, out of scope for this milestone:** the existing full-remount-on-version-bump pattern (`key={md-${version}}`, F-4.2's own finding) loses scroll position/cursor on every accepted correction — a live-update-experience issue, not a document-*size* issue, so not part of Large Document Mode narrowly defined.

### (g) DOCX preview — defer

- **Why:** the slowest single conversion in the pipeline for a large book's DOCX, but already correctly lazy (only runs when visible) and is the least-frequently-used view.
- **Recommendation:** not part of this rollout. Flag as a candidate for on-demand-conversion-plus-client-side-caching (keyed by `document_version`) only if a future benchmark specifically shows this pane is slow in practice.

### (h) Selection/Viewport contexts — no change

- **Why:** all three hold O(1) state; document size does not change their complexity. Confirmed, not assumed.

### (i) Memory management

- The in-memory JS object graph (not the DOM) holding thousands of objects as normalized dictionaries is generally a few MB at most for typical semantic-object shapes — not a concerning amount on modern hardware. No proposed change, but named explicitly as an unmeasured assumption (see Devil's Advocate) rather than silently taken for granted.

### (j) Scroll synchronization / (k) Jump-to-object behavior — no change needed

- Both already O(1) regardless of document size (a single jump target, not a list). The only scaling concern is the *source* of jump targets (nav-tree search, nav-tree list), which items (c) and (d) above already address.

---

## 4. Rollout Plan

A future implementation milestone (or milestones) should sequence work as follows — not attempted in this design-only pass:

1. **Benchmark first** (§5) — acquire or build a genuinely large synthetic test document before committing to anything, especially the virtualization library choice in (c).
2. **Cheap, zero-new-dependency wins**: (b) memoize selectors, (d) debounce search — small diffs, immediate measurable relief, can ship first.
3. **Overlay indexing refactor** (a) — still no new dependency, a moderate but bounded diff, directly reduces PDF page-turn cost.
4. **Nav-tree virtualization** (c) — the one item needing a new dependency and the most design/testing care. Sequenced last among the frontend work so the benchmark from step 1 can confirm it's actually needed at RAWRS's real corpus scale, and so the cheaper wins from steps 2-3 are already in place (which may reduce how urgently virtualization is needed).
5. **Confirm PDF range-request support** (e) — a backend-side follow-up question, independent of the frontend sequence above.
6. **Explicitly deferred, not part of the initial rollout**: Special View grid virtualization, DOCX-preview lazy-caching — revisit only if a benchmark specifically shows a need.

## 5. Benchmark Plan

- **Acquire or synthesize a benchmark document matching the ticket's stated scale** (500+ pages, thousands of semantic objects, hundreds of corrections, hundreds of images). RAWRS's existing benchmark corpus (per this project's own "benchmark corpus convention") is built from real academic PDFs in the tens-of-pages range — likely none reach 500+ pages, so a new corpus entry may need to be added specifically for this purpose, consistent with the project's own "benchmark before generalizing" convention rather than guessing.
- **Metrics to capture:** time-to-first-paint of the workspace; time-to-interactive for the nav tree's "By Type" mode; page-turn latency (P50/P95) in the PDF pane; search-input responsiveness (keystroke-to-result latency); initial `loadResults()` fetch duration; memory usage (a heap snapshot after full load).
- **Tooling:** Chrome DevTools Performance panel / Lighthouse — already recommended and never executed across three prior audits (F-1 item 39, F-4.2, F-5.0's own "no performance baseline" finding). This benchmark should be the first time this actually happens, closing a gap this project has named three times without acting on it.

## 6. Accessibility Considerations

- **Virtualized lists must preserve full keyboard/screen-reader navigability.** A naively virtualized list can break "jump between items" navigation or misrepresent list size to assistive tech if `aria-setsize`/`aria-posinset` (or an equivalent live-region announcement) isn't paired with whatever windowing approach is chosen — this needs explicit design attention when (c) is implemented, not an afterthought bolted on after the fact.
- **Roving-tabindex focus management assumes the focused element is actually in the DOM.** The existing `useArrowKeyTabs`/`useListReviewKeyboard` patterns (and any future keyboard work on the nav tree, per F-3.1's own recommendation) depend on this — a virtualized list that unmounts the focused row when it scrolls out of the rendered window would silently break keyboard navigation unless the windowing solution is chosen and configured with this interaction in mind.
- **Debounced search must not introduce perceptible lag** between typing and any live-region announcement of result counts — should stay well under commonly-cited ~300ms interaction-latency guidance.
- **No other accessibility surface is affected** by this design — color contrast, semantic HTML, and focus order are unchanged by anything proposed here; the risk is narrowly scoped to "does virtualization preserve existing, already-tested list navigation," not a broader regression.

## 7. Risks

- **Virtualization library choice risk** — picking a library that doesn't compose cleanly with the existing accordion/ARIA-tabs patterns could force a larger-than-expected redesign of `SemanticNavTree`. Mitigated by sequencing this last (§4) and benchmarking first.
- **Benchmark risk** — without a suitably large real or synthetic test document, any performance work here is guesswork rather than evidence-based, contradicting this project's own stated principle.
- **Scope-creep risk** — "Large Document Mode" could balloon into touching `PdfViewer`, `SemanticNavTree`, `DocumentWorkspace`'s selectors, and a new dependency all in one milestone. The phased rollout in §4 exists specifically to bound this.
- **Accessibility regression risk on the nav tree specifically** — the one currently-working, tested surface this design proposes to change (§6).
- **Unverified assumption: backend PDF range-request support** — if absent, a 500+ page PDF could have a genuinely slow initial load that no frontend-only fix addresses; needs confirming, not assuming, before or during implementation.

## 8. Recommendation

**Large Document Mode can be implemented incrementally. No dedicated rendering subsystem is required.**

The existing architecture — context-based synchronization, the `react-resizable-panels` shell, `react-pdf`'s single-page view, CodeMirror's own built-in virtualization — is fundamentally sound and already correctly bounded in most of the areas audited (PDF rendering is inherently per-page already; Markdown rendering is virtualized by the library itself; the sync contexts are O(1) regardless of document size). The real gaps are narrow and additive: two cheap, zero-new-dependency wins (memoized selectors, debounced search), one indexing refactor with no new dependency (page-indexed overlays), and exactly one component needing a genuinely new capability (windowed rendering in `SemanticNavTree`, and only there — not a document-wide rendering overhaul, not a new state-management layer, not a parallel pipeline). This mirrors the same conclusion pattern every prior F-4.x audit reached: the architecture is sound, the gaps are targeted, and the fix is extension, not replacement.

---

## Devil's Advocate — what would prove this design wrong

- **Assumption: "thousands of semantic objects" actually materializes in real RAWRS documents.** No real 500+ page book has been processed through RAWRS and measured in this session — every number here is reasoned from the ticket's stated target scale and from code-level analysis of what *would* happen at that scale, not from an actual observed slowdown. If RAWRS's real target corpus tops out at, say, 100 pages and a few hundred objects (much closer to the existing 10-document benchmark corpus), several of these "bottlenecks" may never manifest as user-visible problems, and the virtualization work in particular could be solving a problem that doesn't yet exist for RAWRS's actual users. The benchmark in §5 is the way to find out — this design should not proceed to implementation without it.
- **Assumption: a new virtualization dependency is worth adding at all.** An alternative reading of "reuse before rebuilding" is that `SemanticNavTree`'s "By Type" mode could instead just... not render everything by default — e.g., paginate the accordion itself (show 50 headings, a "show more" affordance) with plain React state, no library, no virtualization, and accept that a reviewer wanting to see item 4,000 clicks "show more" a few times. This is a real, simpler alternative to (c) that trades a small UX cost (extra clicks for a rare deep-scroll case) for zero new dependencies and much lower implementation/accessibility risk. This design recommends true virtualization because the ticket explicitly names "thousands of semantic objects" as a first-class target scale, where "show more" pagination would itself become a poor experience — but if the benchmark in §5 shows the practical scale is much smaller, the simpler pagination approach should be reconsidered before reaching for a new dependency.
- **Assumption: `react-pdf`'s remount-per-page/zoom behavior (confirmed via Context7) is acceptable as-is.** It's possible a large document's page-turn latency, even with overlay indexing (a) fixed, is still perceptibly slow due to the rasterization cost alone — this can only be confirmed by the benchmark, not asserted here. If it proves to be a real problem, the fix would likely be `react-pdf`'s own `renderMode="none"`/custom-renderer escape hatch for pre-rendering adjacent pages ahead of navigation (a "read-ahead" cache) — a heavier design change than anything else in this document, and explicitly not proposed here without benchmark evidence first.
- **What would change this recommendation:** if the benchmark reveals that even with items (a)/(b)/(d) fixed, page-turn latency or nav-tree interactivity remains poor at RAWRS's *actual* real-world document scale (not the ticket's hypothetical upper bound), that would be evidence for a more significant rendering investment (e.g., the read-ahead PDF cache above) — but nothing observed or reasoned about in this session's code review indicates that's necessary yet.
