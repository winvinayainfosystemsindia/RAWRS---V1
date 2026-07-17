# RAWRS Workspace Mode Design Audit — 2026-07-14 (Phase F-4.4)

Audit + UX design only, per the ticket — no code changed, no UI redesigned, no context-preserving editing implemented. Grounded in direct inspection of `frontend/app/documents/[id]/DocumentWorkspace.tsx`'s `specialViews`/`renderSpecialView()` switch, `frontend/components/workspace/ContextInspectorRail.tsx`'s `selection.objectType` switch, `WorkspaceShell.tsx`'s `mode` prop and its own in-code design comment, and every per-type detail/bulk component (`ImageGrid`/`ImageDetailPanel`, `TableGrid`/`TableDetailPanel`, `HeadingGrid`/`HeadingDetailPanel`, `FootnoteTable`/`FootnoteDetailPanel`, `ListPanel`/`ListDetailPanel`, `CalloutPanel`/`CalloutDetailPanel`, `ReadingOrderPanel`, `PageLabelManagerPanel`, `CorrectionsPanel`/`CorrectionHistoryList`, `ValidationIssueTable`). Builds directly on `DOCUMENT_WORKSPACE_LAYOUT_AUDIT_2026-07-14.md` (Phase F-4.2), which flagged the table/image context-loss pattern as "likely unintentional, needs confirmation" — this audit is that confirmation, and it revises that earlier finding.

---

## 0. Headline Finding (revises the F-4.2 audit)

The F-4.2 audit treated the table/image grid-vs-rail context difference as a probable oversight. Direct inspection of `WorkspaceShell.tsx` disproves that: the shell's `mode: "document" | "special"` prop carries an explicit, pre-existing design comment —

> `"special" = a whole-document workspace (Images gallery, Page Labels, Reading Order, ...) that takes over the full center+right width, same as the rest of the app's dedicated editors.`

This is a deliberate architectural decision, not an accident: "special" mode is *designed* to drop the PDF/Markdown panes and take the full width, consistently, for every workspace that uses it. **The dual-model itself (a full-width bulk workspace alongside a context-preserving rail) is intentional.**

The real, previously-unnoticed gap is different: **three object types (Footnotes, Lists, Callouts) have fully-built bulk components — `FootnoteTable`, `ListPanel`, `CalloutPanel` — that are never rendered anywhere in the app.** Confirmed by grep: zero JSX usages of `<FootnoteTable>`, `<ListPanel>`, or `<CalloutPanel>` exist outside their own definition files; only their co-located `*DetailPanel` exports (`FootnoteDetailPanel`, `ListDetailPanel`, `CalloutDetailPanel`) are reachable, exclusively via `ContextInspectorRail`. Each of these three files already implements the identical master-detail bulk pattern `TableGrid`/`ImageGrid` use (a selectable list + inline detail pane, same file, same shape) — fully coded, fully typed, apparently complete — but never wired into `DocumentWorkspace.tsx`'s `specialViews` array or `renderSpecialView()` switch. This is strong evidence the *intended* design was Model-A+B parity across all six selectable object types, and Footnotes/Lists/Callouts are an **incomplete rollout**, not a deliberate simplification.

---

## 1. Workspace Interaction Inventory

| Object Type | Entry Point(s) | Current Layout | Context Retained | Context Lost | Existing Reusable Infra | Accessibility Impact | Cognitive Load |
|---|---|---|---|---|---|---|---|
| **Images** | (A) Nav tree "Workspaces" → `ImageGrid` special view. (B) PDF-overlay click / nav "By Type" row → rail's `ImageDetailPanel`. | (A) Full-width grid + inline detail pane, no PDF/Markdown. (B) Detail panel in the always-visible rail, alongside PDF+Markdown. | (B) full document context. (A) none. | (A) PDF/Markdown entirely. | `ObjectInspectorFrame` (shared tab shell), `ContextInspectorRail` | Medium — bulk AI alt-text review (path A) is the highest-volume workflow and the one that drops visual PDF reference, exactly when verifying "what does this image show" matters most. | Path A: low (dedicated triage screen). Path B: low (context is present, no view-switching). |
| **Tables** | Same dual pattern as Images: (A) `TableGrid` special view, (B) rail's `TableDetailPanel`. | Identical structure to Images. | Same as Images. | Same as Images. | Same as Images. | Medium — table structure is easiest to verify against source PDF layout, which path A hides. | Same as Images. |
| **Headings** | Same dual pattern: (A) `HeadingGrid` special view, (B) rail's `HeadingDetailPanel`. | Identical structure. | Same as Images/Tables. | Same as Images/Tables. | Same as Images/Tables. | Low — heading text/level is usually legible without the source PDF open. | Low. |
| **Footnotes** | **Only path B exists today**: PDF-overlay click / nav "By Type" row → rail's `FootnoteDetailPanel`. `FootnoteTable` (a complete bulk master-detail component, same shape as `TableGrid`) is built but never rendered anywhere — confirmed via grep, zero call sites. | Rail-only, full document context always present. | Full context, always. | Nothing today — but no bulk/triage screen exists for reviewing footnotes as a batch. | `FootnoteTable`'s dead code is a ready-made Model-A path; `ObjectInspectorFrame`. | Low for the rail path itself; a real gap for a reviewer who wants to triage all footnotes at once (no batch view exists, unlike Images/Tables). | Low per-item, but no way to see "how many footnotes still need review" without the nav "By Type"/"Pending" list. |
| **Lists** | Same as Footnotes: rail-only via `ListDetailPanel`; `ListPanel`'s bulk export is dead code (zero call sites). | Same as Footnotes. | Same as Footnotes. | Same as Footnotes. | `ListPanel`'s dead code, `ObjectInspectorFrame`. | Low. | Same gap as Footnotes — no batch triage view. |
| **Callouts** | Same as Footnotes/Lists: rail-only via `CalloutDetailPanel`; `CalloutPanel`'s bulk export is dead code. | Same. | Same. | Same. | `CalloutPanel`'s dead code, `ObjectInspectorFrame`. | Low. | Same gap. |
| **Reading Order** | Nav tree "Workspaces" → `ReadingOrderPanel` special view only. No rail equivalent — reordering is inherently a page-level operation across multiple blocks, not a single-object edit, so a rail (which shows one selected object) is structurally the wrong shape for this task. | Full-width, no PDF/Markdown; up/down reorder controls, explicit Save/Approve/Reset. | None. | PDF view of the page being reordered. | `WorkspaceShell`'s special-view mode. | Medium — losing the visual PDF reference while reordering blocks is a real cognitive cost; this is the one case in the inventory where Model A is intentional *and* still has a real, unaddressed drawback (no rail equivalent could fix it either, since the task needs the PDF pane, not a narrow rail). | Medium-High — a reviewer must remember block content/position from a separate PDF glance, since neither is visible at the same time. |
| **Page Labels** | Nav tree "Workspaces" → `PageLabelManagerPanel` special view only. Same structural reasoning as Reading Order — bulk section rules and per-page overrides are list/table operations, not single-object edits. | Full-width, no PDF/Markdown; bulk section form (immediate-save) + per-page override rows (immediate-save). | None. | PDF view of the page being labeled (lower stakes than Reading Order — page numbers are usually verified against the page itself, less often against surrounding visual layout). | `WorkspaceShell`'s special-view mode. | Low — page-number verification rarely depends on visual PDF layout. | Low. |
| **Corrections** | (A) Nav tree "Workspaces"/"Pending" → `CorrectionsPanel` special view (full list, status-tab filtered). (B) Nav "Pending" mode's individual rows, or PDF-overlay/object click → rail's `CorrectionHistoryList` for one correction. | Same dual structure as Images/Tables. | (B) full context. (A) none. | (A) PDF/Markdown. | `CorrectionHistoryList` (already the single best reuse example in the workspace — one implementation, 4 call sites), `correctionFilters.ts`. | Low — corrections are typically evaluated as text (problem/reason/suggested value), less often against the PDF's visual layout. | Low both paths. |
| **Validation** | (A) Nav tree "Workspaces" → `ValidationIssueTable` special view (full list). (B) Rail's own *default* (no-selection) state renders the same `ValidationIssueTable`. | Both paths render literally the same component; (B) is not a narrower/detail view, just the same list embedded in the rail alongside PDF/Markdown. | Both — this is the one type where the "grid" path doesn't even lose context, since path A and B render identical content, just at different widths. | Effectively none — this is already the most consistent object type in the inventory. | Fully reused already (2 contexts, 1 component). | Low. | Low. |

---

## 2. Current UX Model

RAWRS's Document Workspace runs a **deliberate hybrid model**, not an accidental one:

- **Model A (bulk workspace, full-width, no document context)** is used for whole-document or batch operations: Images, Tables, Headings, Corrections, Validation, Reading Order, Page Labels, Readiness, Metadata, OCR Pages — anything reachable from the nav tree's "Workspaces" section.
- **Model B (context-preserving rail, PDF+Markdown always visible)** is used for single-object inspection: any object selected via a PDF-overlay click, a nav "By Type" row, or a search result renders in `ContextInspectorRail`, which is always present in `mode="document"`.
- **For most object types, both models coexist by design** — a reviewer chooses bulk triage (Model A) or point inspection with context (Model B) depending on the task, exactly as `WorkspaceShell.tsx`'s own design comment states.
- **Reading Order and Page Labels are Model-A-only, correctly** — these are page/document-level operations with no single-object shape, so a rail equivalent wouldn't make sense; this is not a gap.
- **Footnotes, Lists, and Callouts are Model-B-only today, but not by design** — their Model-A components exist, fully built, and are simply never wired into the workspace's special-view switch.

---

## 3. Is the Inconsistency Intentional?

**Split answer, because there are two different things that could be called "inconsistent," and they have opposite answers:**

1. **"Does entering via the bulk workspace lose PDF/Markdown context, while entering via the rail keeps it?"** — **Yes, and this is intentional.** `WorkspaceShell.tsx`'s own code comment explicitly designs "special" mode to take over the full width, "same as the rest of the app's dedicated editors." This is a considered architectural decision already made and already shipped consistently across every type that has a Model-A path.
2. **"Why do Images/Tables/Headings/Corrections/Validation get both models, while Footnotes/Lists/Callouts only get one?"** — **No, this is not intentional; it's an incomplete rollout.** The dead `FootnoteTable`/`ListPanel`/`CalloutPanel` components are the tell: nobody would fully build a master-detail bulk component, in the exact shape `TableGrid`/`ImageGrid` already use, and then simply never call it, as a deliberate design choice. The far more likely explanation is that Footnotes/Lists/Callouts were added as newer, thinner asset types (consistent with the Phase F-1 Frontend Completion Audit's own framing of them as "lighter treatment... consistent with being a simpler, more recently-added asset type") and their Model-A wiring was never finished.

---

## 4. Recommended Interaction Model

**Keep the current hybrid model as canonical. Document it, don't redesign it.** The model is coherent and matches how a professional remediation tool should work: bulk triage for batch review, point inspection with context for detailed verification. Neither "pure Model A" nor "pure Model B" would serve this product better — Reading Order and Page Labels already prove Model A is correct when the task is inherently page/document-scoped, and the rail's ubiquity for single-object selection already proves Model B is correct when the task is inherently object-scoped.

The one real, evidence-backed gap is coverage: Footnotes/Lists/Callouts should get the same Model-A option Images/Tables/Headings already have — via the dead code that already implements it. This is a **small, mechanical completion of an already-decided design**, not a new interaction model to invent.

---

## 5. Migration Strategy (if needed)

No migration is needed for the model itself — it doesn't need to change. If a future milestone chooses to close the Footnotes/Lists/Callouts coverage gap, the work is narrow and low-risk:

1. Add `"footnotes"`, `"lists"`, `"callouts"` cases to `DocumentWorkspace.tsx`'s `specialViews` array and `renderSpecialView()` switch, following the exact `images`/`tables`/`headings` pattern already there.
2. Render the already-built `FootnoteTable`/`ListPanel`/`CalloutPanel` components directly — no new component design, no new state shape (each already accepts the same `{items, jobId, onXUpdated}` shape the existing grids use).
3. No backend dependency — this is purely wiring already-fetched data (`state.footnotesById`/`listsById`/`calloutsById`, already used by the rail path) into a new render branch.

This is explicitly **not** part of this milestone (implementation is a non-goal here) — named only because the ticket asks for a migration strategy "if required," and a small one exists.

---

## 6. Expected Productivity Improvement

If the coverage gap above were closed: reviewers get workflow parity across all six selectable object types — the ability to triage all footnotes/lists/callouts in one batch view, the same way Images/Tables/Headings already support, rather than only discovering them one at a time via the nav tree or a PDF click. This directly serves "efficient workflows for remediators working for hours," since batch review is measurably faster than one-at-a-time discovery for documents with many footnotes (academic PDFs, this product's primary corpus, often have dozens). The improvement is bounded — Footnotes/Lists/Callouts are lower-volume object types than Images/Tables in most benchmark documents — so this is a real but smaller win than, say, Large Document Mode (F-4.2's biggest gap).

---

## 7. Accessibility Considerations

- The hybrid model itself is accessibility-neutral-to-positive: Model B (rail) already gives keyboard/screen-reader users full document context without an extra navigation step, which is the harder case to get right — it's already correct today for every type that has it.
- The Footnotes/Lists/Callouts coverage gap has a real accessibility angle: a screen-reader user who wants to review every footnote in a long document currently has no batch/list view for that object type (unlike Images/Tables), only one-at-a-time discovery via the nav tree's "By Type" accordion — closing the gap would give this workflow the same efficient, single-screen review that sighted/keyboard reviewers already get for Images and Tables.
- No accessibility regression risk in wiring the dead components into `specialViews`, since `FootnoteTable`/`ListPanel`/`CalloutPanel` already follow the same list+`ObjectInspectorFrame` pattern already accessibility-tested (Phase F-2.1/F-2.2/F-3.2) for `TableGrid`/`ImageGrid`.
- Reading Order remains the one workflow in this entire inventory with a real, unresolved accessibility/cognitive-load cost (losing the PDF while reordering) that neither model change addresses — flagged here again as a carry-forward from F-4.2, not solved by this audit's recommendation.

---

## 8. Recommendation

**Retain the current hybrid (Model A + Model B) split. Do not implement a single universal context-preserving model, and do not treat the current design as broken.**

This audit set out to determine whether the coexistence of a full-width bulk workspace and a context-preserving rail was an accident or a decision — it is a decision, evidenced directly by `WorkspaceShell.tsx`'s own design comment, and it is the right one: bulk triage and point inspection are genuinely different tasks that deserve genuinely different layouts. Implementing "all editing retains PDF/Markdown context" (pure Model B) would be a regression, not an improvement — it would force every batch-review workflow (approving 40 images' alt text in a row, for instance) into a cramped rail width for no benefit, contradicting the ticket's own "adequate preview space" and "no dashboard-style clutter" requirements just as much as the reverse would.

The one concrete, evidence-backed action item — wiring the dead `FootnoteTable`/`ListPanel`/`CalloutPanel` components into `specialViews` to close the Model-A coverage gap — is real, small, and low-risk, but it is *completing* an existing decision, not migrating to a new one. It is a reasonable candidate for a future milestone, not a mandate this audit is issuing.

---

## Devil's Advocate — what would prove this audit wrong

- **Assumption:** that the dead `FootnoteTable`/`ListPanel`/`CalloutPanel` code proves intent to build Model-A parity, rather than being abandoned exploratory work that should be deleted instead of wired up. Both readings are consistent with the evidence — this audit cannot distinguish "unfinished feature" from "abandoned experiment" from code alone. Whoever built these three components (or the Phase 1 IDE redesign that introduced the grid pattern) should confirm intent before a future milestone spends effort wiring them up.
- **Assumption:** that `WorkspaceShell.tsx`'s design comment reflects an actual, considered product decision rather than one engineer's after-the-fact rationalization written while implementing the Phase 1 IDE redesign. The comment is real and specific enough to be strong evidence, but "a comment says it's intentional" is weaker than a design document or a UX decision record confirming it — no such document was found in `docs/DECISIONS_LOG.md` specifically addressing this split.
- **What would change this recommendation:** actual reviewer usage data (the same recurring blind spot named in the F-1 and F-4.2 audits) showing that reviewers frequently want to cross-reference the PDF while triaging images/tables in bulk — if that need is real and common, a hybrid "grid with a collapsed PDF strip" (a genuinely new third layout, not pure Model A or B) might be worth designing, rather than either retaining the current split unchanged or forcing full Model B. No such data exists yet to justify that additional design work now.
