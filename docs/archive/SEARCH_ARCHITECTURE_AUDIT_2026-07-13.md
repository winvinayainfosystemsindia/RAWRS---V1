# RAWRS Search Architecture Audit — 2026-07-13 (Phase F-4.1)

Audit + design only, per the ticket — no code changed. Grounded in direct code inspection (`\bsearch\b`/`\bSearch\b` word-boundary grep across `frontend/**/*.tsx`, followed by reading each match's actual implementation), not assumption.

---

## 1. Search Inventory

Exactly **three** real search/find mechanisms exist in the frontend. A broader, looser grep (matching `filter(` too) initially returned 21 files, but nearly all of those were components using `.filter()` for ordinary discrete-value filtering (status, severity, category — see Duplication Analysis below), not search. Tightened to a word-boundary match for "search," only three files contain an actual search feature:

| # | Location | Searches over | Match strategy | Purpose |
|---|---|---|---|---|
| 1 | `ReviewerWorkspace.tsx` (`matchesSearch()`, M-4.1) | `CorrectionItem` fields: `problem`, `reason`, `current_value`, `suggested_value`, `rule_id` | Case-insensitive substring (`.toLowerCase().includes()`) over a concatenated haystack string | Find a specific **proposed correction** to review, within the reviewer's already-filtered queue |
| 2 | `SemanticNavTree.tsx` (`SearchMode`, one of its 5 nav modes) | 6 structural object types: heading `.text`, table `.caption`, image `.figure.caption`/`.alt_text`, footnote `.body`, list items joined, callout `.label` | Case-insensitive substring per-field, one pass per object type, results capped at 50 | Navigate to a specific **document content object** (jump the PDF/selection to it) |
| 3 | `MarkdownEditor.tsx` (imports `openSearchPanel` from `@codemirror/search`) | Raw Markdown source text inside the editor pane | CodeMirror's own built-in find/replace (regex-capable, third-party) | Standard text-editor find/replace — same category as any code editor's Ctrl+F |

**Not search, and correctly not built as search:** `ImageGrid` (Missing Alt/Needs Review/Accepted/.../Low Res — discrete filter buttons), `ValidationIssueTable` (severity/category dropdowns), `CorrectionsPanel`/`ReviewerWorkspace`'s own status tabs (Pending/Accepted/Rejected/Ignored/All). These narrow a list by a fixed set of known values, not a free-text query — they are filters, a different and already-appropriate UI pattern, not search under a different name.

---

## 2. Duplication Analysis

**No architectural duplication.** Each of the three searches operates over a genuinely different data domain for a genuinely different user goal:

- #1 searches **proposal metadata** (what's wrong, what's suggested) to help a reviewer triage corrections.
- #2 searches **the document's own structural content** to help any user jump to a specific heading/table/image/etc.
- #3 searches **raw editor text** — a generic text-editing convenience, not domain-specific at all.

The only thing they share is surface shape ("a text input filters something"), which is not itself an architectural commitment — nearly every search feature in nearly every application shares that shape. Treating "has a text input" as the unification criterion would be over-abstracting on form rather than function.

**One real, but trivial, low-level duplication found:** the substring-match primitive itself. `ReviewerWorkspace.matchesSearch()` and `SemanticNavTree.SearchMode`'s inline per-type loops both independently write `haystack.toLowerCase().includes(query.toLowerCase())`. This is duplicated logic, technically — but it is a single stdlib method call, not a system. Extracting a one-line `matchesQuery(haystack, query)` helper would save near-zero code and add an import + a name to look up, for a line simple enough that reading it inline is already self-documenting. Per "do not abstract prematurely," this specific duplication is judged **not worth fixing** — noted here so it isn't silently missed, not silently promoted into a mandate either.

**Filter-logic duplication (a related but distinct question the ticket also asked about):** `STATUS_TABS`/`statusTabMatches`/`isResolved` (`frontend/lib/correctionFilters.ts`, extracted in Phase M-4.1) are already shared between `CorrectionsPanel` and `ReviewerWorkspace` — this is **existing reuse already done correctly**, not a gap. No other filter duplication was found across the audited components; `ImageGrid`'s and `ValidationIssueTable`'s filter predicates are domain-specific enough (image review states vs. validation severity/category) that a shared abstraction would need a generic-enough shape to be nearly meaningless, or specific enough to just be two separate, clearer functions — which is what exists today.

---

## 3. Existing Infrastructure Reused (by this audit's own analysis)

This audit's conclusion itself reuses two things already established this session, rather than proposing new machinery:
- The Phase F-3.2 "tabs vs. filter" distinction test (does selecting an option swap content panels, or narrow one list?) — applied here as "does this box search one query across a domain, or pick among fixed known values?" to correctly separate the 3 real searches from the filter-style controls that superficially look similar.
- `correctionFilters.ts`'s existing extraction pattern (shared predicate module, not a shared component) is the template this report recommends *if* any future unification were ever justified — see below.

---

## 4. Proposed Architecture

**Not justified for the three real searches as they exist today.** Given no shared data domain and no shared user goal, a unified search architecture would need to either (a) flatten three different object shapes into one generic searchable-item interface (losing the type-specific fields — `rule_id` for corrections, `bbox`/`sourceLine` for navigable objects — that each search's *result handling* actually depends on), or (b) keep three separate implementations underneath a shared UI shell that provides no real behavior, just a consistent look. Option (a) is a real cost for no real benefit (nothing today needs to search across corrections *and* document objects *and* editor text in one box). Option (b) is cosmetic consistency dressed as architecture.

**If a fourth search need ever appears** with a genuinely overlapping shape to an existing one (e.g., a future "search across all reviewer-facing text everywhere" feature), the right unit to extract at that point is a small, generic `useSubstringSearch<T>(items: T[], query: string, getHaystack: (item: T) => string): T[]` hook — a composable primitive, not a monolithic search system, consistent with "prefer composable primitives" per this ticket's own instruction. This is a recommendation for *if the need arises*, not a proposal to build now.

---

## 5. Migration Plan

**None proposed.** There is nothing to migrate — recommending "keep current design" (see Recommendation, item 8) means the three existing implementations continue exactly as built, since none is broken, none conflicts with another, and unifying them would cost real type-safety and clarity for a benefit no current use case needs.

---

## 6. Accessibility Considerations

- `ReviewerWorkspace`'s search input has `aria-label="Search corrections"` and a documented `/`-to-focus keyboard shortcut (verified in Phase F-2.2/F-3.1's live and code-level passes) — already accessible.
- `SemanticNavTree`'s search input uses `type="search"` (correct semantic input type, gives browsers/AT the standard search-field affordance) with a `placeholder` but **no `aria-label`** — placeholder text is not a reliable accessible name for screen readers (it can be enunciated inconsistently across AT/browser combinations, and disappears once the user starts typing, which some AT re-reads as empty). This is a genuine, small, real accessibility gap found during this audit — flagged here since fixing it is out of scope for an audit-only milestone, but it's a natural, very low-effort candidate for whichever future milestone next touches `SemanticNavTree`.
- CodeMirror's `openSearchPanel` accessibility is upstream/third-party — not something RAWRS's own code controls, out of scope for this audit.
- Unifying the three searches would not, by itself, fix or worsen accessibility — the gap above is local to `SemanticNavTree` regardless of architecture.

---

## 7. Performance Considerations

- All three searches run client-side over already-fetched, in-memory data (no network round-trip per keystroke) — appropriate given the "low hundreds, not thousands" per-document object volumes noted in `ReviewerWorkspace`'s own design comments (Phase M-4 design review).
- `SemanticNavTree.SearchMode` recomputes its full 6-domain scan on every keystroke via `useMemo` keyed on `query` plus all 6 object arrays — fine at current volumes; the existing `.slice(0, 50)` cap already bounds worst-case render cost regardless of how large the underlying document gets.
- No debouncing exists on any of the three inputs. Given the data volumes involved (hundreds of items, not thousands) and simple `.includes()` matching (not a heavier fuzzy-match library), this is very unlikely to be a real bottleneck — flagged as a theoretical, not observed, consideration, consistent with not fabricating a performance problem that hasn't been measured.
- A unified architecture would not obviously improve any of this — the current per-feature scans are already about as cheap as this class of operation gets.

---

## 8. Recommendation

**Keep the current design. Do not implement a unified search architecture.**

The milestone's own instruction to "attempt to prove the milestone unnecessary" succeeds: the three existing searches serve three different data domains and three different user goals, share no state, and would lose type-specific behavior if flattened into one system for the sake of surface-level consistency. The one real duplication found (the substring-match one-liner) is too trivial to justify an abstraction. The one real gap found (`SemanticNavTree`'s missing `aria-label`) is unrelated to search architecture — it's a small, local accessibility fix, worth doing whenever that component is next touched, not a reason to build a search framework around it.

**Partial unification is also not recommended** — there is no natural seam between exactly two of the three (e.g., unifying #1 and #2 but not #3) that isn't already served by the trivial shared substring-match logic being just as easy to leave inline as to extract.
