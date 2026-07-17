# RAWRS Design Bible v1.0

**Status: Permanent Product Constitution.** This document is the authoritative design specification for RAWRS. It supersedes ad-hoc screen-by-screen judgment calls, supersedes any single `DESIGN.md` snapshot, and is binding on all future frontend work until formally revised. Where this Bible conflicts with a prior audit's narrower recommendation, this Bible wins for anything it explicitly addresses; where it is silent, the prior audit stands (see §0.3, Precedent Index).

Produced 2026-07-15, Phase R-2.0. Grounded in: (a) direct inspection of the shipped RAWRS frontend (`WorkspaceShell.tsx`, `DocumentWorkspace.tsx`, `ContextInspectorRail.tsx`, `ObjectInspectorFrame.tsx`, `PdfViewer.tsx`, `SemanticNavTree.tsx`, `MarkdownEditor.tsx`, `DocxPreview.tsx`, all sync contexts, `DocumentDataContext.tsx`/`DocumentProvider.tsx`, `useArrowKeyTabs`/`useListReviewKeyboard`, `ThemeProvider.tsx`); (b) three Stitch design explorations (V1 `stitch_rawrs_remediation_workstation.zip`, V2 `...(1).zip`, V3 `...(2).zip` — extracted and reviewed screen-by-screen, code and screenshot, in full); (c) every prior RAWRS audit (F-1 Frontend Completion Audit, F-2.1/F-2.2 Accessibility, F-3.1/F-3.2 Keyboard, F-4.1 Search, F-4.2 Layout, F-4.3 Persistence, F-4.4 Mode Design, F-4.5 Coverage Parity, F-5.0 Stabilization, R-1.0 Large Document Mode Design); (d) `RAWRS_PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, `TASKS.md`.

---

## §0. How to Use This Document

### §0.1 Authority
Every recommendation below carries one of three weights, stated explicitly per item so nothing is silently ambiguous:
- **DECIDED** — already shipped and confirmed correct by a prior audit (e.g., F-4.4's hybrid Special-View/Rail model). Do not re-litigate; extend only.
- **SPECIFIED** — new in this Bible, not yet built. Binding once this Bible is approved.
- **OPEN** — a genuine tradeoff this Bible flags but does not resolve; requires a product decision before it becomes SPECIFIED.

### §0.2 Evaluation Categories
Every screen, component, and pattern reviewed in this Bible is scored against one of seven categories — **Keep, Improve, Remove, Merge, Replace, Reject, or Invent** — never left unscored:
- **Keep** — already correct; ship as-is.
- **Improve** — correct direction, needs a specific, named change.
- **Remove** — delete; it adds cost with no offsetting value.
- **Merge** — two things doing the same job; collapse into one.
- **Replace** — the concept is right, the current implementation is wrong; swap the implementation, not the concept.
- **Reject** — the concept itself is wrong for RAWRS; do not build it, regardless of execution quality.
- **Invent** — a real gap that no source (not the shipped app, not any Stitch exploration) proposed a solution for; this Bible originates the recommendation.

### §0.3 Precedent Index (do not re-litigate)
| Prior decision | Source | This Bible's stance |
|---|---|---|
| Hybrid Special-View (bulk, no doc context) + Inspector Rail (context-preserving) is intentional and correct | F-4.4 | DECIDED — extended in §8-9, not reopened |
| Unified search across the 3 existing search implementations is unnecessary | F-4.1 | DECIDED — not reopened |
| Large Document Mode: incremental fixes (memoized selectors, page-indexed overlays, debounced search, one new virtualization dependency in `SemanticNavTree` only) — no dedicated rendering subsystem | R-1.0 | DECIDED — restated in §30, not redesigned |
| Panel persistence, `maxSize` constraints, PDF scroll-to-highlight | F-4.3 | DECIDED — shipped, referenced in §8 |
| Footnotes/Lists/Callouts bulk-workspace coverage parity | F-4.5 | DECIDED — shipped |
| Route-level `error.tsx` still missing, aged 6 milestones | F-5.0 | DECIDED gap — carried into §34, §40 as the standing highest-priority engineering debt |
| Context-preserving table/image editing gap (Special View grids drop PDF/Markdown context; Rail path doesn't) | F-4.2/F-4.4 | OPEN, addressed with a concrete resolution in §9 |
| No performance baseline exists anywhere in the project | F-1, F-4.2, F-5.0, R-1.0 | DECIDED gap — folded into §38/§43 as a mandatory pre-condition, not repeated as a fourth separate finding |

### §0.4 Source Discipline
Every "what exists today" claim below cites a real file. Every adopted or rejected Stitch idea cites which version (V1/V2/V3) and screen. Nothing is asserted from memory alone where the code could instead be cited.

---

## §1. Product Principles & Anti-Patterns

*(Distinct from §2's visual Design Principles — these govern product **behavior and prioritization**, not appearance.)*

### Product Principles
1. **Validation First.** No output ships without a validation pass the reviewer can see and act on. (Inherited from `RAWRS_PROJECT_CONTEXT.md`'s Core Principles — still valid, still binding.)
2. **Human Review, Always.** AI proposes; a human disposes. No auto-apply of any repair without an explicit accept action, ever — this is not negotiable even for "high confidence" suggestions (matches the shipped `CorrectionRecord` accept/reject/edit/ignore lifecycle; do not add a bulk "auto-accept all ≥95% confidence" shortcut — see Anti-Pattern 4 below).
3. **Local First, Single Reviewer.** No multi-tenancy, no auth, no "batches," no "projects" spanning multiple documents at once. One document, fully reviewed, before the next. This is an architecture decision already made (F-1 audit: "not a gap") — restated here as a product principle so it stops being independently rediscovered and second-guessed by every new design exploration (see §3, §17 for what this rules out).
4. **Auditability Over Convenience.** Every accepted correction is traceable to the evidence that justified it (`CorrectionHistoryList`, `EvidenceBreakdown` — already shipped). Never trade this away for a faster-looking flow.
5. **Model Agnostic, No Vendor Lock-In.** The UI must never assume a specific AI provider's capabilities or branding are load-bearing to the workflow (already true of the shipped AI-suggestion surfaces; keep it true).
6. **One Interaction Model Per Workflow.** Where a workflow already has a correct pattern (list-review keyboard shortcuts, ARIA-tabs), extend it to new surfaces before inventing a second pattern for the same job (F-3.1/F-3.2's own standing rule).
7. **The Document Is the Product.** Every screen exists to serve reviewing one document. A screen that doesn't reference the current document within one click is suspect by default (see §3).

### Anti-Patterns (product-behavior level; visual anti-patterns are in §2/§25)
1. **The Multi-Tenant Reflex.** Do not add Sign In, Pricing, Plans, "New Batch," or an Enterprise sales nav item because a design exploration or a generic SaaS instinct suggests it. RAWRS has no multi-user concept. Every one of the three Stitch explorations fell into this reflex (see §16 for the full rejection).
2. **The Vanity Metric Reflex.** Do not add "Hours Saved," "Documents Processed This Month," or any trend sparkline that exists to make the product look impressive rather than to help the current review. If a number doesn't change what the reviewer does next, it doesn't belong on screen (this is `/impeccable`'s own "hero-metric template" ban, restated as a product rule, not just a visual one — see §16 Dashboard verdict).
3. **The Silent Auto-Apply Reflex.** Never let "AI confidence is high" become a reason to skip the accept click. Confidence is input to the reviewer's decision, never a substitute for it.
4. **The New-Page-Per-Feature Reflex.** Adding a new capability should default to a new tab/mode/pane within the existing workspace shell, not a new top-level route. Check whether `WorkspaceShell`'s `mode`/`centerViews`/`specialViews` pattern already covers it before proposing a new page (already the shipped pattern; keep proposing within it, per Product Principle 6).
5. **The Re-litigation Reflex.** Do not reopen a DECIDED item (§0.3) because a new design exploration suggests a different answer. Cite the precedent and move on.

---

## §2. Overall Philosophy

RAWRS is reviewed, not browsed. Every design decision is judged against one question: *does this help a reviewer detect, review, compare, repair, verify, or export faster, with less fatigue, over an 8-10 hour session* — not "does this look impressive in a screenshot." The product's own purpose (auditing documents for accessibility) obligates its own interface to model the standard it enforces: if RAWRS's UI would fail the WCAG checks it runs on other people's documents, that is not a cosmetic defect, it is a credibility failure (this framing is not new — the F-1 Frontend Completion Audit already named it as "the single most important finding," carried forward here as permanent doctrine, not a one-time audit note).

The three Stitch explorations collectively prove one thing worth stating as philosophy: **the underlying visual language (dark IDE-adjacent theme, tonal panel layering, monospaced technical data, sharp/precise shapes) is right for this product's register** — it reads as a professional instrument, not a consumer app or an enterprise CRUD shell. **The product framing layered on top of that language (SaaS dashboard, multi-tenant batches, marketing funnel) is wrong** — it was never RAWRS's actual shape, and adopting it would be redesigning the product to match a demo rather than designing the interface RAWRS actually needs. This Bible keeps the former, rejects the latter, and is explicit about exactly where that line falls in every section below.

---

## §3. Information Architecture

**What exists today (DECIDED, shipped):** two-page architecture — `/` (upload/landing, real responsive breakpoints, dual dropzone, `RecentDocuments` live-polling list) and `/documents/[id]` (the entire reviewing surface, one document at a time). No `/dashboard`, no `/projects`, no `/settings`, no `/profile`, no auth routes exist, and per Product Principle 3, none should.

**What the Stitch explorations propose:** a left-nav admin shell — Overview/Dashboard, Documents, Review Queue, Objects, Validation, Accessibility, Exports, Reports, Settings — as separate top-level pages (all 3 versions, most fully in V3's `RAWRS Sentinel` dashboard).

**Verdict, per screen concept, using the mandatory 7-category framework:**

| Stitch concept | Verdict | Why |
|---|---|---|
| Dashboard / "System Overview" as a top-level page | **Reject** | Assumes multiple documents in flight, batch IDs, MTD trend metrics — contradicts Product Principle 3 and the Anti-Pattern-2 vanity-metric reflex. The real information reviewers need on open (recent documents, status) already exists on `/` today. |
| Separate "Documents" list page | **Reject** | `/`'s `RecentDocuments` already is this, correctly scoped to "recent," not a full CRM-style document library RAWRS doesn't need. |
| Separate "Objects" top-level page (multi-file-type grid: `.dwg`, `.svg`, `.tiff`) | **Reject** | Wrong content model entirely — RAWRS's real "Images"/"Tables"/"Headings" special views already exist *within* one document's workspace (`DocumentWorkspace.tsx`'s `specialViews`), which is the correct scope. A top-level cross-document file manager has no place here. |
| Separate "Review Queue" top-level page | **Merge** | This already exists correctly as `ReviewerWorkspace.tsx`, reached from within the document, not as a sibling top-level nav item competing with the document itself. |
| Separate "Settings"/"Profile" pages | **Postpone** | Real gap (F-1 audit item 31: "needs a product decision on what's actually configurable" — still true; not resolved by this Bible, no product decision has been made). Not designed here; see §41. |
| Left-nav IA shape itself (persistent rail, top-level sections) | **Reject as top-level architecture, Keep as a *within-workspace* nav pattern** | The shape is fine — it's exactly what `SemanticNavTree`'s left rail already is *inside* the Document Workspace. The error is applying it at the *application* level (implying multiple documents/projects) rather than the *document* level (where it correctly lives today). |

**Invent:** none required at the IA level — the real gap this Bible identifies is not a missing page, it's under-designed *within-document* navigation density at scale (see §30 Large Document Mode) and the context-preserving-editing inconsistency (see §9). No new top-level route is warranted anywhere in this review.

---

## §4. Navigation Architecture

**What exists today (DECIDED, shipped):** `SemanticNavTree`'s 5 modes (Outline / By Type / Pending / Issues / Search), `WorkspaceShell`'s center-view switcher (6 presets: PDF/MD/DOCX/3 split combinations), both using the shared `useArrowKeyTabs` ARIA-tabs hook (F-3.2). Nav tree's "Workspaces" section links every whole-document special view (Images/Tables/Headings/Footnotes/Lists/Callouts/Validation/Corrections/Reading Order/Page Labels/Metadata/OCR/Readiness — F-4.5 closed the last three-type gap).

**What Stitch proposes, worth adopting:** V2 Table Workspace's **"Tables in this document" secondary rail** (Table 1 (Pg 3) / Table 2 (Pg 8) / ... with status dots) is a genuinely better in-context navigation pattern than RAWRS's current "By Type" accordion for *dense single-type* review sessions (e.g., a reviewer specifically clearing every table in a table-heavy document). V2's Triple Compare **Document Outline + Remediation Layers** dual-rail (outline tree above, layer-visibility toggles below, in the same left column) is a clean way to keep both "where am I" and "what am I looking at" visible without consuming the main canvas.

**Verdict:**
| Item | Verdict | Why |
|---|---|---|
| Current 5-mode `SemanticNavTree` | **Keep** | Already correct, already accessibility-tested, already keyboard-consistent. |
| "Tables/Images/etc. in this document" per-type secondary list | **Invent** | Neither the shipped app nor any Stitch screen builds this as a *reusable, scale-with-object-type* pattern — V2 hand-built it once for tables only. Generalize it: when a reviewer opens any single-type Special View (Images/Tables/Headings/...), show a lightweight in-page jump-list of that type's items with status dots, reusing the same virtualization work already planned for the nav tree at scale (§30). |
| Remediation Layers toggle | **Invent** | Genuinely novel, present in no shipped RAWRS surface. See §14 (PDF Interaction Standards) for the concrete design. |
| A distinct global top nav bar (RAWRS logo / Platform / AI Engine / Enterprise) | **Reject** | Marketing-site chrome; RAWRS has no multi-product surface to navigate between (Anti-Pattern 1). |

---

## §5. Professional Reviewer Journey Mapping

*(New section, per amendment — the concrete narrative every other section is judged against.)*

A remediator's real session, stage by stage, with the fatigue/decision points that must be designed for:

| Stage | What the reviewer is doing | Cognitive load / fatigue risk | Design obligation |
|---|---|---|---|
| **0. Open** | Picks up a document from `/`'s recent list or uploads a new one. | Low — but a slow/ambiguous upload flow costs trust before review even starts. | `/`'s dual dropzone + readiness checklist already correct (F-1: "Production Ready"). No change. |
| **1. Orient** | First look at a freshly-processed document: how bad is it, where do I start? | Medium — too many numbers (a Dashboard) delays orientation; too few (a blank workspace) forces guesswork. | Validation Center's severity counts (Errors/Warnings/Needs Review/Resolved) *are* the correct orientation surface — already shipped, no dashboard needed on top of it (reinforces §3's Dashboard rejection). |
| **2. Detect** | Scans validation issues grouped by category, decides review order. | Medium-High over hours — repetitive category-by-category triage is where the AI Confidence filter (Stitch V2/V3, not yet shipped) earns its place: lets a reviewer defer low-confidence flags to a second pass instead of context-switching on every item. | **Invent**: adopt the AI Confidence slider filter into `ValidationIssueTable` (see §10). |
| **3. Review** | Opens one flagged object, reads the AI's reasoning, checks it against source. | High — this is the single most fatigue-sensitive stage across an 8hr day; every removable click here compounds. | Reasoning & Evidence card pattern (V1) formalized in §12; Repair Action Plan pattern (V3) formalized in §9. |
| **4. Compare** | Cross-references Source PDF ↔ Semantic structure ↔ Output, to confirm the fix is right, not just plausible. | High — losing visual correlation between panes is the single biggest cause of re-checking work already done. | Cross-pane synchronized highlight (V2) formalized in §7 (Comparison Modes) — this is the concrete fix for the F-4.2/F-4.4 "context-preserving editing" OPEN item (§9 resolves it). |
| **5. Repair** | Accepts, edits, or rejects the AI's suggestion. | Medium — decision fatigue from *inconsistent* accept/reject affordances across object types is worse than the decision itself. | §21 Keyboard Model: one consistent accept/reject/edit shortcut set across every object type, not just `ReviewerWorkspace` (closes the F-3.1-disclosed keyboard-coverage gap explicitly, with a concrete plan). |
| **6. Verify** | Confirms the repair actually produced valid output (screen-reader preview, structural re-check). | Medium — a repair that "looks fixed" but wasn't actually verified is the single worst failure mode for a *credibility* product. | §19 Screen Reader Preview is SPECIFIED as mandatory verification UI, not optional polish. |
| **7. Export** | Downloads the final DOCX/report, confident it's compliant. | Low, but a silent stale-export (already fixed once per F-4.2/F-4.3's document_version sync work) destroys trust instantly if it regresses. | §35 Export Experience must surface the same `document_version` staleness guard already proven elsewhere in the app. |
| **8. Next document** | Closes this one, opens the next. | Fatigue accumulates *across* documents, not just within one — layout/focus-mode/panel-size persistence (F-4.3, already shipped) is what prevents re-setup cost every single time. | Already DECIDED and shipped — restated here as the reason it mattered, not re-designed. |

**The one cross-cutting finding this journey mapping surfaces that no individual section would catch alone:** stages 3 and 4 (Review, Compare) are where 8-10hr fatigue actually accumulates, and they are exactly the two stages where the current shipped app's Special-View-vs-Rail split (F-4.4's DECIDED hybrid model) forces a reviewer to choose between *seeing the document* and *seeing a batch of objects* — never both at once for object types with a bulk workspace. §9 resolves this directly, informed by this journey mapping rather than by IA theory alone.

---

## §6. Workflow Architecture

Everything revolves around **Detect → Review → Compare → Repair → Verify → Export**, never around pages (mission mandate; matches §5's journey stages 1-7 one-to-one).

**What exists today (DECIDED, shipped):** the pipeline itself already produces Detect (validation issues, evidence signals) and the reviewer-facing Repair loop (`CorrectionRecord` accept/reject/edit/ignore) — this is real, working, and auditable end-to-end. What's *architecturally* under-expressed is **Compare** and **Verify** as distinct, named moments in the UI — today they're implicit in "look at the split view" and "trust the validation re-check," not surfaced as their own step.

**Verdict:**
| Stage | Current UI expression | Verdict |
|---|---|---|
| Detect | Validation Center, Evidence signals | **Keep** |
| Review | Object Inspector Rail / Special View grids | **Keep**, with §9's context-preserving fix |
| Compare | Implicit in split-view center panes | **Improve** — formalize as Triple Compare mode (§7), not just an informal side-by-side |
| Repair | `CorrectionRecord` lifecycle | **Keep**, with §9's Repair Action Plan addition |
| Verify | Implicit (re-run validation, trust it worked) | **Invent** — Screen Reader Preview (§19) as an explicit, named verification step, not folded silently into "repair" |
| Export | Download buttons, no unified UI | **Improve** — see §35 |

No workflow stage requires a new backend capability to become visible in the UI — every one is already backed by real data (`ValidationIssue`, `EvidenceSignal`, `CorrectionRecord`, `document_version`). This is a UI-surfacing problem, not a missing-capability problem, which is why it's addressable now rather than postponed (contrast with §42's genuinely backend-blocked items).

---

## §7. Comparison Modes

**What exists today (DECIDED, shipped):** `WorkspaceShell`'s 3 split presets (PDF+MD, PDF+DOCX, MD+DOCX) — always exactly 2 panes, never 3, and never with cross-pane highlight correlation. `PdfViewer`'s overlay/highlight system and `MarkdownEditor`'s scroll-to-line are independently triggered by the same `SelectionContext`/`PdfViewportContext`/`MarkdownViewportContext` but do not visually connect to each other beyond both reacting to the same selection.

**What Stitch proposes:** V2's **Triple Compare** (Source PDF / Semantic AST / Output, three columns) with a single detected issue highlighted *simultaneously* in all three — a dashed red box on the PDF page, a red-bordered code block in the AST view, and (implied, cut off in the captured screenshot) a corresponding highlight in Output. V3's Table Repair Workspace achieves a similar 2-pane version of this (Source PDF crop | Semantic DOM Output) with the same one-selection-highlights-everywhere idea.

**Verdict:**
| Item | Verdict | Why |
|---|---|---|
| 3-way Triple Compare as a 4th `centerMode` option | **Invent** | Real gap — `WorkspaceShell`'s `CENTER_MODES`/`SPLIT_PAIRS` already generalize to N panes structurally (§8), but a true 3-pane split has never been built. This directly serves Journey Stage 4 (Compare). |
| Cross-pane synchronized highlight (one selection, three highlighted regions) | **Invent** | The sync *plumbing* already exists (`SelectionContext` is already the single source of truth every pane reads) — what's missing is each pane rendering its *own* highlight from that shared selection, not a new sync mechanism. Low architectural risk: extend, don't rebuild. |
| A dedicated "Semantic AST" pane as a 4th first-class view (alongside PDF/MD/DOCX) | **Improve, don't Invent** | Real RAWRS already exposes semantic structure via the Evidence/AI Logic inspector tabs (`ObjectInspectorFrame`) — Stitch's AST pane is a *presentation* upgrade of data RAWRS already surfaces, not new data. Scope it as a richer rendering within the existing Evidence tab (§12) rather than a whole new center-view mode, to avoid duplicating what the Inspector already does (Product Principle 6). |

**Engineering constraint:** Triple Compare needs a 3-way `PanelGroup` nesting (the existing 2-way split already nests one `PanelGroup` inside another per `WorkspaceShell.tsx`'s current code — a 3-way split is the same pattern one level deeper, not a new panel library). No backend dependency. Complexity: Medium (must decide `minSize`/`maxSize` for 3 panes without repeating F-4.3's "don't blindly copy identical values" mistake — see §38).

---

## §8. Workspace Architecture

**What exists today (DECIDED, shipped, F-4.2/F-4.3/F-4.4/F-4.5 confirmed sound):** `WorkspaceShell`'s 3-zone model (Nav / Center / Rail), `mode: "document" | "special"` toggle, `react-resizable-panels` with `autoSaveId` persistence and per-panel `maxSize` reasoning, Focus Mode (collapses Nav+Rail), Bottom Panel. This architecture is **confirmed correct by four separate prior audits** — this Bible does not redesign it (mission's own "preserve architectural consistency" instruction, and Product Principle 6).

**What Stitch proposes that maps onto this correctly, with no architectural conflict:** V3's `RAWRS Sentinel` DESIGN.md names the exact same 4-zone model in its own words ("Global Navigation (Left), Main Canvas (Center), Inspector (Right), Review Queue (Bottom)") — independent convergent validation that the shipped architecture is the right shape, not a coincidence to dismiss.

**Verdict:** **Keep**, wholesale, as architecture. The design work remaining here is entirely visual (tokens, density, panel chrome — §22-29) and one concrete interaction gap (§9), not structural.

---

## §9. Object Workspace Standards — Resolving the Context-Preserving-Editing OPEN Item

This section exists specifically to resolve the one OPEN item carried from F-4.2/F-4.4 (§0.3), using the Journey Mapping in §5 as the deciding evidence.

**The problem, restated precisely:** for object types with both a Special View (bulk grid) and a Rail path (`ContextInspectorRail`) — Images, Tables, Headings, Corrections — entering via the grid drops PDF/Markdown context entirely; entering via the Rail keeps it. F-4.4 confirmed this split is *architecturally intentional* (bulk triage vs. point inspection are different tasks) but flagged that the *specific* context-loss in the grid path was not conclusively proven intentional vs. accidental.

**This Bible's resolution:** it is **Improve**, not Reject or Replace. The two-mode split stays (per F-4.4, DECIDED); what's missing is a **third state, not a third mode**: a **"Peek" affordance** inside the Special View grid — selecting a card/row in the bulk grid opens the same Rail-style detail panel *inline, within the grid's existing layout*, with a "Show source" toggle that reveals a collapsed PDF strip (not the full PDF pane, a thumbnail-height strip pinned to the relevant page) without leaving the grid. This is exactly the "hybrid grid-with-a-collapsed-PDF-strip" option F-4.4's own Devil's Advocate section named as worth designing if reviewer data ever showed the need — the Journey Mapping in §5 (stage 3-4 fatigue analysis) is that evidence, made concrete rather than hypothetical.

**Verdict, per object type:**
| Object type | Current grid path | Verdict |
|---|---|---|
| Images, Tables, Headings, Corrections | Full-width grid, no source | **Improve** — add the Peek/source-strip affordance above |
| Footnotes, Lists, Callouts | Grid just shipped (F-4.5), same context-loss | **Improve**, same fix, applied consistently — do not let the newest object types regress behind the improvement the older ones get |
| Reading Order, Page Labels | Special-View-only, no Rail equivalent (correctly, per F-4.2 — these are page-level, not object-level) | **Keep as-is for the grid/rail split**, but **Invent** a *lighter* version of the same source-strip idea for Reading Order specifically — F-4.2/F-4.4 both independently flagged losing the PDF while reordering blocks as the single worst unaddressed cognitive-load case in the whole workspace; this is the most valuable single application of the source-strip pattern in the entire Bible. |

**Repair Action Plan, adopted (V3):** every accept/repair action across every object type should show the concrete, reviewable list of transformations before commit (e.g., "Convert `<td>Revenue</td>` to `<th scope=\"row\">`") rather than an opaque "Repair" button. **Invent** relative to shipped RAWRS (no current `TableDetailPanel`/`ImageDetailPanel` does this); **adopted from Stitch V3**, not novel to this Bible, but genuinely absent today and directly serves Journey Stage 5 (Repair) by making the AI's action auditable *before* acceptance, not just after (reinforces Product Principle 4, Auditability).

**Engineering constraints:** the source-strip toggle needs no new sync mechanism (`PdfViewportContext`'s existing `jumpToObject`/page-number state already carries everything a collapsed strip needs to render the right page) — it is a rendering/layout addition, not a new architecture. Complexity: Medium per object type (must be built once as a shared pattern, not six times — see §27 Component Library). No backend dependency. The Repair Action Plan requires the backend to expose the *specific* DOM transformations a repair will make, not just accept/reject the whole correction — **this is a real, named backend dependency**, flagged honestly rather than assumed away (see §40).

---

## §10. Validation Workflow

**What exists today (DECIDED, shipped):** `ValidationIssueTable` groups issues by rule-category into `<details>` accordions, with severity/category filter dropdowns and persistent triage actions (defer/ignore) — already correctly designed IA (F-4.2 confirmed this independently before any Stitch review happened).

**What Stitch proposes, worth adopting:**
- **AI Confidence slider filter** (V2/V3) — lets a reviewer show only issues above/below a confidence threshold. Genuinely absent today.
- **Running compliance score in the header** ("Score: 92%", V2) with an adjacent "Export Accessibility Report" action — surfaces the Journey Stage 1 orientation question ("how bad is it") without a separate Dashboard.
- **Severity tabs with live counts** (Errors/Warnings/Needs Review/Resolved, both V2 and V3) — already effectively what RAWRS's severity filter does, just styled as tabs rather than a dropdown; a legitimate visual upgrade, same underlying data.

**Verdict:**
| Item | Verdict | Why |
|---|---|---|
| Category-accordion IA | **Keep** | Already correct, F-4.2-confirmed. |
| AI Confidence slider | **Invent** | Real, valuable, absent gap — directly serves Journey Stage 2. |
| Severity-tabs-not-dropdown visual restyle | **Improve** | Same data, better scan-ability at a glance; use `useArrowKeyTabs` since this is a genuine ARIA-tabs case (swaps visible content), not a filter-checkbox case — apply the F-3.2 tabs-vs-filter test explicitly here. |
| Running score + Export Report in header | **Invent** | Real gap; also the correct, minimal answer to "reviewers want an orientation number" *without* reopening the Dashboard rejection (§3) — one number, in-context, not a separate page. |

---

## §11. Inspector Standards

**What exists today (DECIDED, shipped):** `ObjectInspectorFrame`'s shared tab shell (Properties/Evidence/History/AI/Actions), used identically across every object type, driven by `useArrowKeyTabs` (F-3.2). This is real architectural strength — Stitch's V3 inspector (Properties/Evidence/AI Logic/History) is *the same four-tab shape independently arrived at*, confirming rather than contradicting the shipped design.

**Verdict:** **Keep** the tab shell wholesale. The remaining gap is exactly what F-4.2 already identified and this Bible does not need to rediscover: **Inspector Compression** (narrow-rail behavior is undesigned — CSS wrap only, no icon-only fallback). This Bible does not re-litigate that OPEN item; it restates the F-4.2 recommendation as still binding and adds one concrete constraint: whatever compression design is eventually built must reuse `useArrowKeyTabs` unchanged (already true of the hook's API — it only needs `ids`/`active`/`onChange`, not a fixed label-rendering shape, so icon-only tabs are a pure consumer-side change, not a hook change).

---

## §12. Evidence Visualization Standards

**What exists today (DECIDED, shipped):** `EvidenceBreakdown.tsx` — per-signal confidence breakdown, embedded inline in every `CorrectionHistoryList` row (one implementation, reused across `CorrectionsPanel`, every object detail panel's History tab, and `ContextInspectorRail`'s single-correction case — F-5.0 called this the single best reuse example in the whole workspace).

**What Stitch proposes:** V1's **Reasoning & Evidence card** — one visual row per signal, each with its own icon (Font Size Variance / Font Weight / Numbering Pattern), a bold label, and a one-line plain-language explanation ("Text is 20pt, visually distinct from surrounding 12pt body text"), plus an aggregate AI Confidence meter above the list and WCAG rule-citation pills below it.

**Verdict:** **Replace the visualization, keep the data model and reuse pattern.** `EvidenceBreakdown`'s underlying signal data already structurally matches what V1 renders — this is a rendering upgrade (icon-per-signal, one-line plain-language explanation per signal, WCAG pill citations), not a new evidence architecture, and it should stay exactly as reused today (one component, every call site) rather than being redesigned per-object-type. **Engineering constraint:** requires each `EvidenceSignal` to carry a short human-readable explanation string, not just a numeric weight — confirm this field already exists in the backend's evidence-signal shape before committing to the icon-plus-one-liner layout; if it doesn't, this becomes a small, named backend dependency (a one-line addition to an existing model, not new architecture).

---

## §13. Review Queue Standards

**What exists today (DECIDED, shipped):** `ReviewerWorkspace.tsx` — filters/search/sort, full `useListReviewKeyboard` shortcut set (a/r/i/u/e/j, next/prev, search), progress tracking, synced to PDF/selection (F-3.1's proven, shipped keyboard-parity reference implementation). `BottomPanel.tsx` — a separate, simpler collapsible bar (validation/export/console summary tabs), distinct from the Review Queue concept.

**What Stitch proposes:** a persistent **bottom bar** across every workspace screen (all 3 versions) — "Document Progress" bar, "Issues Remaining X / Out of Y found," Reject/Repair/Accept buttons, sometimes a keyboard-shortcut coach-mark. V3 additionally frames this as "Systematic Audit Mode Active," a session-state indicator.

**Verdict:**
| Item | Verdict | Why |
|---|---|---|
| Persistent progress + issues-remaining bottom bar | **Merge** | RAWRS already has *two* bottom-adjacent concepts (`ReviewerWorkspace`'s own progress tracking, and `BottomPanel`'s validation/export summary) that should converge into one persistent bar, not stay split. Consolidating avoids the exact "two things doing the same job" case §0.2 defines Merge for. |
| Global Accept/Reject/Repair buttons in the bar, always visible regardless of what's selected | **Improve** | Real productivity idea — removes a scroll-to-the-inspector step during rapid list-review — but must be built to *only* activate meaningfully when an object is actually selected (a global-looking bar acting on nothing selected is a real usability trap the Stitch mockups don't visibly guard against; this is a concrete implementation constraint, not a rejection). |
| "Systematic Audit Mode Active" session-state framing | **Reject as copy, Keep as concept** | The specific wording reads like marketing flourish ("Mode Active" badges are exactly the kind of decorative status theater `/impeccable`'s anti-pattern list warns about when it isn't functionally informative) — the *functional* content (progress %, issues remaining) is worth keeping; the ceremonial framing around it is not. |
| Keyboard-shortcut coach-mark hints inline in the bar (e.g., "⌘+↵ Accept") | **Invent** | Genuinely useful, absent today — ties directly into §21's Keyboard Model as the *discoverability* mechanism that model currently lacks. |

---

## §14. PDF Interaction Standards

**What exists today (DECIDED, shipped, R-1.0-confirmed sound):** `react-pdf` single-page view, semantic-object overlays (clickable boxes, current-page-only), reading-order numbered badges, jump-to-highlight with `scrollIntoView` (F-4.3), zoom 0.5-3× (`PdfViewportContext`). R-1.0 confirmed this architecture is correct and needs only targeted, incremental fixes (page-indexed overlays, no custom page-cache) — not redesigned here.

**What Stitch proposes:**
- **Remediation Layers toggle** (V2) — Structural Tags / Alt Text Zones / Reading Order Flow, each independently show/hideable, like Illustrator/Figma layer visibility.
- **Inline violation annotations directly on the rendered page** (V1, V2) — a red dashed box with a small tag label ("⚠ 1.3.1 Info & Relationships") drawn directly over the offending content, not just a sidebar list entry.

**Verdict:**
| Item | Verdict | Why |
|---|---|---|
| Remediation Layers toggle | **Invent** | Novel, valuable — lets a reviewer isolate one concern (e.g., only reading-order issues) visually on a dense page instead of parsing every overlay type at once. Directly reduces Journey Stage 3 cognitive load. |
| Inline violation tag-labels on the PDF overlay | **Improve** | RAWRS's overlay already draws a box per object (`PdfViewer.tsx`); it doesn't currently label *which rule* is violated directly on the box, only in the separate Inspector rail. Adding the label to the overlay itself removes a rail-glance for the common "what's wrong here" question. |
| Zoom/page-nav toolbar | **Keep** | Already correct, no Stitch idea materially improves it. |

**Engineering constraint:** Remediation Layers is a filter on the existing `overlays` prop passed into `PdfViewer` (partition by `objectType`/violation-category, toggle visibility client-side) — no new sync architecture, no backend dependency, composes directly with R-1.0's planned page-indexed overlay refactor (build the layer-filter on top of the same restructured data, not before it — sequence after R-1.0's §4(a) if both are ever scheduled together).

---

## §15. Markdown Interaction Standards

**What exists today (DECIDED, shipped, R-1.0-confirmed):** `MarkdownEditor.tsx`, CodeMirror 6, read-only in the main workspace (editing happens via per-object detail panels), already internally virtualized by the library (R-1.0, confirmed via vendor docs) — no large-document work needed here. Full remount on `document_version` bump (a live-update-experience tradeoff, not a size problem — R-1.0's own scoping).

**What Stitch proposes:** none of the three explorations meaningfully engage with the Markdown pane as its own interaction surface — it appears only as a labeled column in Triple Compare, with no distinct interaction ideas beyond what's already shipped.

**Verdict:** **Keep**, no changes recommended by this Bible. The one open cosmetic question (losing scroll position/cursor on every version-bump remount) remains an F-4.2-named, low-priority item — not escalated here.

---

## §16. DOCX Interaction Standards

**What exists today (DECIDED, shipped, R-1.0-confirmed):** `DocxPreview.tsx`, client-side `mammoth` conversion, correctly lazy (only mounts/converts when the DOCX pane is actually visible — R-1.0 confirmed this directly from `WorkspaceShell`'s rendering behavior, not assumed).

**What Stitch proposes:** nothing DOCX-specific in any of the three explorations beyond it being one labeled column/tab alongside PDF and Markdown.

**Verdict:** **Keep.** R-1.0 already named the one legitimate future improvement (on-demand-conversion-plus-caching if a benchmark ever shows this pane is slow) — deferred, not escalated, consistent with R-1.0's own sequencing.

### The Landing/Marketing/Auth Screens — Full Rejection, Documented Once
*(Placed here rather than duplicated across §3/§4/§17 — every marketing/SaaS-framing element across all three Stitch zips converges on one verdict, stated fully once and referenced elsewhere.)*

| Screen/element | Source | Verdict | Why |
|---|---|---|---|
| Full marketing landing page ("The Definitive Workstation," "v2.0 Now Available," Start Free Trial/Watch Demo, 3D abstract hero art) | V1 `rawrs_industry_standard_remediation_desktop`, V2 `rawrs_the_global_standard_for_remediation` | **Reject** | RAWRS's real `/` is an upload/landing utility page, not a marketing conversion funnel (Anti-Pattern 1). The 3D abstract circuit/cube hero art is also exactly the generic AI-generated-looking decorative imagery `/impeccable`'s anti-pattern list warns against. |
| "Sign In" / "Get Started" / "Enterprise" nav items | V1, V2 | **Reject** | No auth exists or should exist (Product Principle 3). |
| "Pro Plan" user-menu badge | V2 | **Reject** | No billing/plan concept exists or should exist. |
| Product screenshot mini-preview used as marketing collateral ("Engineered for Velocity" 3-pane illustration, V2) | V2 | **Keep the *technique*, discard the *placement*** | Showing real product UI instead of generic stock art is the right instinct for any marketing surface RAWRS *does* legitimately need (e.g., a README screenshot, an About section) — just not as a full landing-page section, since RAWRS's actual landing page is a working tool, not a sales pitch. |

---

## §17. Accessibility View

**What exists today (DECIDED, shipped):** no single "Accessibility View" exists as its own named screen — accessibility concerns are distributed across Validation Center, the Readiness special view (`ReadinessPanel.tsx`), and per-object Evidence/AI tabs. This distribution is itself a defensible design (accessibility isn't a separate mode, it's the whole product — Product Principle 7 restated), but the mission explicitly asks for this as a named screen concept to evaluate.

**What Stitch proposes:** none of the three explorations build a screen literally named "Accessibility Center/View" as distinct from Validation Center — V2's left nav lists both "Review" and "Accessibility" as separate items but neither zip's captured screens show what the latter contains.

**Verdict:** **Reject a new, separate "Accessibility View" screen.** Accessibility is not a mode you enter and leave in RAWRS — it is validated continuously (Validation Center), scored on readiness (`ReadinessPanel`), and verified per-object (Evidence tabs) and at export time (§19 Screen Reader Preview). Building a distinct "Accessibility View" would fragment a concern that is correctly already everywhere, contradicting Product Principle 7. This is a **Reject**, not an **Improve** — the fragmentation the mission's screen list implicitly worries about doesn't actually exist in the shipped app; consolidating deliberately-distributed accessibility signal into one screen would be the regression, not the fix.

---

## §18. Reading Order View

**What exists today (DECIDED, shipped):** `ReadingOrderPanel.tsx` — master-detail (flagged-pages list + per-page block reorder), up/down buttons (no drag-and-drop, deliberately, per `KNOWN_LIMITATIONS.md`'s human-only scope), explicit Save/Approve/Reset, full-width Special View (loses PDF context — F-4.2's named worst-case for this exact reason).

**What Stitch proposes:** none of the three explorations build a dedicated reading-order reorder screen with the same block-level granularity RAWRS already has — this is one area where shipped RAWRS is ahead of all three Stitch explorations, not behind.

**Verdict:** **Keep** the reorder mechanism and human-only scope (both already correct, already documented decisions). **Improve** via §9's source-strip pattern — Reading Order was independently named there as the single highest-value application of that fix, and this section exists to cross-reference that resolution rather than re-derive it.

---

## §19. Screen Reader Preview

**What exists today (DECIDED, shipped):** no dedicated screen-reader-preview UI exists. `FootnoteDetailPanel.tsx` has a small, real, working precedent — a "Screen Reader Announcement" card showing the literal string a screen reader would speak for that one footnote (`"Footnote 3: ..."`), plus NVDA/JAWS keyboard-hint copy. This is a genuinely good, narrow existing pattern that nothing else in the app currently generalizes.

**What Stitch proposes:** none of the three explorations build this at all.

**Verdict:** **Invent**, generalizing an existing narrow pattern rather than inventing from nothing. Every object type with screen-reader-relevant output (headings, images/alt-text, tables/summaries, footnotes — already has one instance) should get the same "Screen Reader Announcement" preview card in its detail panel, and — per Journey Stage 6 (Verify) — this should be positioned as the **explicit verification step** before a reviewer marks an object as resolved, not an optional curiosity. **Engineering constraint:** the announcement string is derivable client-side from data RAWRS's DOCX generator already computes (heading level, alt text, table summary, footnote number/body) — no new backend capability required, this is a rendering/generalization task only.

---

## §20. Command Palette

**What exists today (DECIDED, shipped):** none. No `⌘K`-style command palette exists anywhere in the shipped app.

**What Stitch proposes:** V3's Dashboard toolbar shows a search bar with a visible `⌘K` badge ("Search objects, rules, or issues..."), unopened/unimplemented in the captured screenshot (no modal state was rendered) — an aspirational UI element, not a working feature to copy wholesale.

**Verdict:** **Invent**, using the visible affordance as a legitimate signal of intent, not as a finished design to copy. A command palette is a strong fit for RAWRS's "expert users, 8-10hr sessions" register (Linear/Cursor/JetBrains-caliber precision tooling all have one) — but it must be scoped to what RAWRS actually has: jump to any object by name/type (reusing `SemanticNavTree`'s existing search-substring logic, R-1.0's planned debounce applies here too), switch center-view mode, toggle Focus Mode, jump to next/prev flagged issue. **Reject** anything resembling cross-document or cross-"workspace" command scope (e.g., "switch project," "open recent batch") — that would smuggle back the multi-tenant framing this Bible rejects everywhere else (Anti-Pattern 1). **Engineering constraint:** no backend dependency; built entirely from data already in `DocumentDataContext`. Complexity: Medium (a new global keyboard-trap layer must not conflict with `useArrowKeyTabs`/`useListReviewKeyboard`'s existing key handling — needs an explicit precedence rule, e.g., `⌘K` always wins, documented in §21).

---

## §21. Keyboard Model

**What exists today (DECIDED, shipped, F-3.1/F-3.2's own honest scoping):** two shared, proven hooks — `useArrowKeyTabs` (WAI-ARIA tabs pattern; 4 real consumers) and `useListReviewKeyboard` (list-review triage shortcuts — a/r/i/u/e/j, next/prev, search; 1 real consumer, `ReviewerWorkspace`). F-3.1 explicitly, honestly scoped down rather than shallow-rolling keyboard support everywhere — and named concrete per-workspace recommendations that were never built: Validation Center needs a `currentIndex`-over-filtered-array concept before `useListReviewKeyboard` can apply; Image/Table grids need the same "current card" concept; Corrections Center was deliberately excluded (reviewers already have `ReviewerWorkspace` for that data).

**This Bible's verdict:** **Invent** the missing `currentIndex`/roving-focus state F-3.1 identified as the actual blocker (not the hook itself, which already exists and is proven) — Validation Center and the Image/Table/Heading grids all need this one shared prerequisite before `useListReviewKeyboard` can be wired in. This is not a new pattern to design; it's finishing the one F-3.1 already scoped in detail and deliberately deferred under session-cost pressure at the time. Building it closes Journey Stage 5's "inconsistent affordances across object types" fatigue source directly.

**One consolidated shortcut table (SPECIFIED, binding across every future list-review surface):**
| Key | Action | Already shipped where |
|---|---|---|
| `j` / `→` (n) | Next item | `ReviewerWorkspace` |
| `k` / `←` (p) | Previous item | `ReviewerWorkspace` |
| `a` | Accept | `ReviewerWorkspace` |
| `r` | Reject | `ReviewerWorkspace` |
| `i` | Ignore/defer | `ReviewerWorkspace` |
| `u` | Undo/reopen | `ReviewerWorkspace` |
| `e` | Edit | `ReviewerWorkspace` |
| `/` | Focus search | `ReviewerWorkspace` |
| `⌘K` | Command palette (§20) | Invent |
| Arrow keys (within a tab bar) | Move focus + selection | `useArrowKeyTabs`, 4 consumers |

**Anti-pattern, explicit:** no object type gets a *different* letter for the *same* action (e.g., Tables must not bind `s` for "save" while Images binds `a` for the equivalent — this is exactly the "inconsistent affordances" fatigue source Journey Stage 5 names). Any new keyboard work must reuse this table's bindings, not invent parallel ones.

---

## §22. Animation Principles

**What exists today (DECIDED, shipped):** minimal, functional only — `transition-colors`/`transition-opacity` on hover states (39 occurrences, F-1 audit), one `animate-spin` (`DocxPreview`'s loading spinner), one `animate-pulse` ("Running…" text, `PipelineView`). No motion library, no page-transition choreography.

**What Stitch proposes:** the captured screenshots show no animation (static exports) — DESIGN.md text mentions none. No evidence either way from the source material.

**Verdict:** **Keep** the current restraint, sharpened into an explicit principle rather than left as an absence: motion in RAWRS exists only to (a) confirm an action registered (accept/reject button state), (b) draw the eye to what changed after a live update (the existing `flashLines`/markdown-flash pattern), or (c) communicate loading. **Reject** any decorative motion (page-transition flourishes, hover-lift shadows, entrance animations on static content) — this is a precision instrument used 8-10hrs/day; gratuitous motion is fatigue, not delight, for this register (`/impeccable`'s own register guidance: product surfaces earn motion through clarity, not personality). Every animation must respect `prefers-reduced-motion` (a real gap today — F-1 never confirmed this is honored anywhere; **flag as unverified**, not assumed compliant).

---

## §23. Spacing

**What exists today (DECIDED, shipped):** Tailwind utility spacing, no formalized token scale documented (existing `globals.css` uses ad hoc values per F-5.0's audit, not a violation, just undocumented).

**What Stitch proposes:** V3's Sentinel system: 4px base unit, explicit named scale (`xs:4px, sm:8px, md:16px, lg:24px, xl:32px`), `sidebar_width:260px`, `inspector_width:320px`, `header_height:64px`. V1/V2's Precision System: identical unit/scale values, different component-level radii only.

**Verdict:** **Adopt V3's spacing scale as the formal token set** (§39 Design Tokens) — it's more specific and already validated against real panel-width numbers close to RAWRS's shipped `WorkspaceShell` panel defaults (`sidebar_width:260px` vs. RAWRS's actual `defaultSize={18}` nav panel — compatible orders of magnitude, not a conflict to resolve). This closes a real, if minor, documentation gap (spacing was never formalized) at zero implementation cost, since it's expressing values already close to what's shipped.

---

## §24. Typography

**What exists today (DECIDED, shipped):** not independently audited this session at the font-stack level; F-1/F-4.x audits focused on layout/behavior, not type scale specifically.

**What Stitch proposes:** both DESIGN.md lineages agree: **Inter** for all UI text (tall x-height, legibility, "critical for an accessibility-focused tool" per V1/V2's own reasoning), **JetBrains Mono** for technical/monospaced content (AST trees, keyboard hints, OCR/code-like data). V3 adds a slightly tighter, more IDE-native scale (display-lg 48px/700 weight, heading-md 24px/600, body-base 16px, body-sm 14px, label-caps 12px/600/0.05em tracking, code-mono 13px).

**Verdict:** **Keep/Adopt** — Inter+JetBrains Mono is a well-justified, non-generic pairing for this register (contrast axis: humanist sans for UI, monospace for technical data — matches `/impeccable`'s own font-pairing guidance) and both Stitch lineages independently converged on it, which is real signal, not coincidence. Adopt V3's tighter scale as the formal type scale (§39) — `display-lg` reserved for the (rare, per V1/V2's own DESIGN.md) marketing/dashboard-overview context this Bible mostly rejects (§3), so in practice the workstation itself lives almost entirely in `heading-md`/`body-sm`/`label-caps`/`code-mono` — confirm this reads as **intentionally restrained**, not under-designed. **Verify**, don't assume: confirm 4.5:1 body-text contrast and 1.5× line-height on body text against the actual chosen surface colors before shipping (`/impeccable`'s own contrast-verification rule, doubly binding given Product Principle 7).

---

## §25. Icons

**What exists today (DECIDED, shipped):** not independently audited this session at the icon-system level.

**What Stitch proposes:** V3 specifies **Material Symbols Outlined** (fill:0 default, fill:1 for active/selected states) at 20px, stroke-based. V1/V2 show icons in screenshots but don't name a specific icon set in DESIGN.md.

**Verdict:** **Adopt** Material Symbols Outlined as the formal icon system (§39) — free, comprehensive, well-suited to a technical/IDE register, and the fill:0/fill:1 active-state convention is a genuinely useful, cheap-to-implement pattern (matches V3's own Document Outline Tree spec: "fill:0 for folder states, fill:1 for active selection"). **Reject** any icon that exists purely for decoration (e.g., a large illustrative icon on an empty state purely for visual interest with no functional labeling role — see §31 Empty States for the actual empty-state standard, which should use icons functionally, not decoratively).

---

## §26. Color System

**What exists today (DECIDED, shipped):** RAWRS's theme-token system (`bg-surface-*`, `text-text-*`, `border-border`, `accent`, `success`/`warning`/`danger`) — F-5.0 confirmed 98%+ consistent application, with `Badge.tsx` and `DocxPreview.tsx`'s two documented, deliberate exceptions (not re-litigated here — F-5.0's own verdict stands).

**What Stitch proposes:** V3's Sentinel palette — dark-first (`surface-dim: #131315` as the canvas base, 5-tier surface-container hierarchy from `#0e0e10` to `#353437`), primary indigo (`#4f46e5`/`primary-container`), secondary teal (`#6bd8cb`), tertiary amber (`#ffb95f`), error coral (`#ffb4ab`), plus a **specialized syntax-highlight sub-palette** (cyan/amber/lavender) used *exclusively* inside the Semantic AST panel to distinguish tags/attributes/values, mimicking a code editor.

**Verdict:**
| Item | Verdict | Why |
|---|---|---|
| Dark-first, 5-tier tonal surface hierarchy | **Adopt as the formal token set** | Matches RAWRS's existing dark-mode-first approach (`ThemeProvider` already defaults dark, per this session's direct read); V3's specific tier values are more precise than what's currently documented — adopt as the reference, reconcile against actual shipped hex values during implementation (a verification task, not a design decision — see §40). |
| Indigo primary / teal success / amber warning / coral error | **Adopt** | Directly compatible with RAWRS's existing `accent`/`success`/`warning`/`danger` token *names* — this is a values-fill, not a new token architecture. |
| Syntax-highlight sub-palette, scoped only to code/AST views | **Invent, scoped narrowly** | Genuinely useful precedent for §7's Semantic AST rendering upgrade — but must stay scoped to that one context, per V3's own DESIGN.md discipline ("used exclusively within the Semantic AST panel") — do not let syntax colors leak into general UI as decorative accents (a real anti-pattern risk if adopted carelessly). |
| Light mode ("Paper," V1/V2 only — V3 dropped it) | **Reject reintroducing dual-mode complexity if V3 already correctly dropped it** | RAWRS's `ThemeProvider` already supports light/dark toggle (shipped, tested) — this is not actually in conflict; V3 simply didn't design a light variant in its own DESIGN.md. **OPEN**: confirm whether RAWRS's product decision is to keep true dual-theme support (current shipped behavior) or follow V3's dark-only technical-instrument framing — this Bible does not resolve that tradeoff unilaterally since it's a real product-level call, not a visual nit. |

---

## §27. Component Library

*(Every component below must justify its existence — per amendment, no entry ships without a one-line "why does this need to exist" answer.)*

| Component | Exists today? | Why it exists (mandatory justification) | Verdict |
|---|---|---|---|
| `ObjectInspectorFrame` (shared tab shell) | Yes | One tab shell, 6 object types — without it, every detail panel reinvents tab semantics (proven risk: this was a real bug before F-3.2, per that audit's own finding). | **Keep** |
| `CorrectionHistoryList` | Yes | One correction-history renderer, 4 call sites — the single best reuse example in the app (F-5.0). Removing it would mean 4 divergent history UIs. | **Keep** |
| `useArrowKeyTabs` | Yes | Every ARIA-tabs surface needs identical roving-tabindex logic; without a shared hook, each surface either reinvents it or (as F-2.2 found) omits it entirely. | **Keep** |
| `useListReviewKeyboard` | Yes | Same justification, for list-review shortcuts — proven in `ReviewerWorkspace`, needed everywhere §21 identifies. | **Keep, extend consumers** |
| Repair Action Plan card | No (Invent, §9) | Without it, a reviewer accepts a repair without seeing what DOM change it actually performs — an auditability gap (Product Principle 4) with no existing substitute. | **Invent** |
| Source-strip / Peek panel | No (Invent, §9) | Without it, bulk-grid editing has no way to reference the source document short of leaving the grid entirely — the single largest fatigue source Journey Stage 3-4 identifies. | **Invent** |
| Screen Reader Announcement card (generalized) | Partial (one instance, `FootnoteDetailPanel`) | Verification (Journey Stage 6) currently has no explicit UI anywhere except this one object type — every other type needs the same, or verification stays inconsistent. | **Invent, generalize existing** |
| Command Palette | No (Invent, §20) | 8-10hr/day expert users benefit measurably from a keyboard-first jump mechanism; every comparable-register tool (Linear/Cursor/JetBrains) has one — its absence is a real gap for this specific user base, not a nice-to-have. | **Invent** |
| Remediation Layers toggle | No (Invent, §14) | Without it, a dense page's overlays are all-or-nothing — no way to isolate one concern visually. | **Invent** |
| AI Confidence slider (Validation Center) | No (Invent, §10) | Without it, a reviewer cannot defer low-confidence flags to a second pass — forces uniform-effort triage regardless of AI certainty. | **Invent** |
| Vanity-metric Dashboard cards (Hours Saved, Documents Processed, sparklines) | Proposed by Stitch, not shipped | **No justification survives scrutiny** — none of these numbers change what a reviewer does next (Anti-Pattern 2's own test). | **Reject** — do not build |
| Generic multi-file-type Objects grid (`.dwg`/`.svg`/`.tiff`) | Proposed by Stitch, not shipped | Wrong content model — RAWRS's real "Objects" are figures/tables/headings *within* one PDF, not a cross-format file manager. | **Reject** — do not build |
| "Systematic Audit Mode Active" ceremonial badge | Proposed by Stitch, not shipped | Decorative status theater with no functional payload beyond what the progress bar already communicates. | **Reject** — do not build |

---

## §28. Micro-interactions

**What exists today (DECIDED, shipped):** hover-state color transitions (39 occurrences), focus-visible rings (F-2.2 confirmed real, computed, not just source-level), `aria-pressed`/`aria-selected` state toggles on Focus Mode and tab bars.

**What Stitch proposes:** V3's DESIGN.md specifies a **20% glow shadow on primary "Accept" actions** specifically (not all primary buttons) — a deliberate micro-emphasis distinguishing the single highest-stakes, highest-frequency action (accepting a repair, Journey Stage 5) from ordinary primary buttons.

**Verdict:** **Invent** (adopted from V3) — a subtle, distinct visual treatment on Accept specifically is a legitimate, narrow use of `/impeccable`'s "premium motion materials" allowance (glow/shadow used sparingly, purposefully, not decoratively) and reinforces the single most-repeated action in the whole product. **Reject** applying the same glow to every primary button generically — that would dilute exactly the emphasis this idea is worth adopting for.

---

## §29. Responsive Behaviour

**What exists today (DECIDED, F-4.2/F-5.0 confirmed, and explicitly out of scope for this Bible):** zero responsive breakpoints anywhere in the Document Workspace, by omission not decision (F-1's original finding, restated and left unresolved through 5 subsequent audits). RAWRS is a desktop-based professional tool by design (Product Principle 3's "local-first, single-reviewer" framing implies a dedicated workstation, not a phone-in-hand context) — this Bible does **not** design responsive layouts for the workspace, per the mission's own explicit non-goal ("Do NOT implement responsive layouts" has been standing instruction across every workspace-track milestone this session).

**What Stitch proposes:** both DESIGN.md lineages describe responsive collapse behavior (side panels to overlays on mobile/tablet) in the abstract, but no captured screenshot shows a narrow-viewport state to evaluate concretely.

**Verdict:** **Postpone**, explicitly, not silently. This Bible records the standing decision (desktop-first, no mobile/tablet workspace) as intentional, not forgotten — the one thing worth adding beyond restating prior audits is a **product-level acknowledgment gap**: no user-facing messaging exists today telling a reviewer on a narrow viewport that the tool isn't designed for their screen size (F-1's original finding, never addressed) — this is a small, cheap, honest addition (a one-line "RAWRS is designed for desktop screens" notice below a viewport threshold) worth bundling into whatever milestone eventually touches this area, without designing full responsive layouts now.

---

## §30. Large Document Mode

**What exists today (DECIDED, R-1.0's complete design, not reopened here):** R-1.0 produced a full architecture — page-indexed PDF overlays, memoized top-level selectors, debounced nav-tree search (all zero-new-dependency), and exactly one new virtualization dependency scoped narrowly to `SemanticNavTree`'s "By Type" lists, sequenced *after* a mandatory benchmark against a genuinely large synthetic document. R-1.0 explicitly rejected virtualizing Special-View grids (Images/Tables) without benchmark evidence, and explicitly rejected building a custom PDF page-cache (confirmed via Context7 that `react-pdf`/`pdfjs-dist` already cache correctly).

**What Stitch proposes:** nothing — none of the three explorations engage with document scale at all; every captured screen shows a short document (a handful of pages).

**Verdict:** **Keep** R-1.0's design in full, restated here as binding, not redesigned. The only addition this Bible makes: §4's "Tables/Images in this document" secondary-rail idea and §14's Remediation Layers toggle should both be designed *against* R-1.0's planned page-indexed overlay structure from the start, not layered on top of the current unindexed structure and re-migrated later — a sequencing note for whoever implements these, not a change to R-1.0's own plan.

---

## §31. Focus Mode

**What exists today (DECIDED, shipped, F-4.3):** collapses Nav+Rail via imperative panel refs, persisted via `localStorage` (F-4.3), toggle button in the top bar, `aria-pressed`.

**What Stitch proposes:** V1/V2 both surface a "Focus Mode" toggle button in the same top-bar location — independent convergent validation of the shipped placement, not a new idea.

**Verdict:** **Keep**, unchanged. F-3.1 considered and correctly declined a global keyboard shortcut for Focus Mode (already one click away in a fixed, discoverable location) — this Bible does not reopen that call.

---

## §32. Empty States

**What exists today (DECIDED, shipped, F-5.0 confirmed):** every panel/grid writes its own independently-authored empty message (F-5.0's audit found ~6 near-identical "no cross-source corrections proposed for X" literal strings, plus distinct wording elsewhere) — functional, but not unified.

**What Stitch proposes:** no empty states are visible in any captured screenshot (all show populated data).

**Verdict:** **Merge** the ~6 duplicated `CorrectionHistoryList` empty-message literals into one shared default (F-5.0 already named this as a low-priority cleanup item — restated as binding here, still low-priority, bundle it opportunistically rather than as a dedicated milestone). Beyond that specific cleanup, empty states should follow one shared visual pattern (icon from §25's Material Symbols set, used functionally not decoratively, one line of plain-language explanation, and — where relevant — a direct action, e.g., "No footnotes detected" needs no action, but "No documents yet" on `/` should link straight to upload). **Invent** this as a documented pattern, not a new component (the app is small enough that a shared `<EmptyState>` component is not yet justified per YAGNI — F-5.0 already reached this same conclusion for loading states; apply consistently rather than building a component prematurely).

---

## §33. Loading States

**What exists today (DECIDED, shipped, F-5.0 confirmed):** no shared `<Spinner>`/`<Skeleton>` exists; every component authors its own (`<p>Loading…</p>` in 3 places, one hand-rolled `animate-spin` SVG in `DocxPreview`, one `animate-pulse` text in `PipelineView`). F-5.0 explicitly judged this **Already acceptable** — not urgent, app is small enough that a shared component isn't yet justified.

**What Stitch proposes:** V3's Dashboard shows an in-progress row with a spinning-icon status indicator and live percentage text ("45%... Extracting semantic structure...") — a good precedent for *stage-labeled* progress, not just a generic spinner.

**Verdict:** **Keep** F-5.0's verdict (no shared component needed yet). **Improve**: adopt the stage-labeled progress pattern (spinner + specific current-stage text, e.g., "Extracting semantic structure…") for the one place RAWRS already has multi-stage async work worth narrating — document processing itself (`PipelineView`'s existing "Running…" state could name the actual current pipeline stage, which the backend's `last_completed_stage` field, confirmed to exist per `Job` model, already provides — no new backend capability, a rendering improvement only).

---

## §34. Error States

**What exists today (DECIDED, F-1/F-5.0's standing, unaddressed gap):** inline `role="alert"` messages exist for upload failures and job-failed states; **zero route-level `error.tsx` exists anywhere**, and zero custom error-boundary class components exist in the whole repo (F-5.0's independent, exhaustive re-verification confirmed this is still true, six milestones after F-1 first flagged it).

**What Stitch proposes:** no error states are visible in any captured screenshot.

**Verdict:** **Invent** (a gap, not a novel idea — restating F-5.0's own top recommendation as formally binding in this Bible, since it has now been deferred long enough to deserve constitutional-level insistence rather than another audit footnote). A single `app/error.tsx` following the standard Next.js App Router convention, wired to whatever error-reporting the project already has (none currently — flag as a genuinely open question whether any error telemetry should accompany this, or whether a plain user-facing message suffices for a local-first, no-cloud tool). **This is the single most overdue item in this entire Bible** — small, cheap, zero design ambiguity, and it has waited through F-2.1, F-2.2, F-3.1, F-3.2, F-4.1 through F-4.5, and F-5.0 without being picked up.

---

## §35. Export Experience

**What exists today (DECIDED, shipped, F-1 confirmed):** download buttons for markdown/docx/report exist; no unified export UI (no format selection, no batch export, no export history — F-1 item 30, "Partially Complete," never subsequently addressed).

**What Stitch proposes:** V2's Validation Center header shows a persistent "Export Accessibility Report" button alongside the running compliance score (§10) — a good, minimal pattern: export is reachable from the orientation surface, not buried in a separate menu.

**Verdict:** **Improve**, using the V2 pattern as the concrete shape: consolidate the existing download actions into one visible export affordance in the workspace header (not a separate top-level "Exports" page, per §3's IA rejection), showing format options (Markdown/DOCX/Report) inline rather than as three separate unlabeled buttons scattered across panels. **Engineering constraint, explicit:** this must reuse the `document_version` staleness pattern already proven correct elsewhere in the app (F-4.2/F-4.3's sync work) — an export action must either block on or clearly warn about an in-flight/stale version, exactly as the Markdown/DOCX preview panes already do. No backend dependency beyond what's already exposed (the download endpoints already exist per F-1's own confirmation).

---

## §36. AI Integration

**What exists today (DECIDED, shipped):** per-object AI suggestions (alt-text generation, table structure detection, evidence-signal confidence scoring), all routed through the existing accept/reject/edit `CorrectionRecord` lifecycle — no auto-apply anywhere (Product Principle 2, already true today, not a new constraint).

**What Stitch proposes:** "Auto-tag Chart Data" one-click apply button (V2 landing-page product illustration), "Auto-Gen" button on the Table Summary field (V2 Table Workspace) — both frame AI action as a single, low-visibility click rather than a reviewable proposal.

**Verdict:**
| Item | Verdict | Why |
|---|---|---|
| One-click "Auto-tag"/"Auto-Gen" *button label* pattern (i.e., a clearly-labeled "generate a suggestion" action, still requiring a separate accept) | **Improve** | Fine as a *trigger* for an AI suggestion, as long as it produces a reviewable proposal, not an applied change — must not become an auto-apply shortcut (Anti-Pattern 3). |
| Any framing implying the AI action *is* the final save (V2's landing-page copy reads ambiguously close to this) | **Reject** | Directly violates Product Principle 2. Any implementation must make the two-step propose→accept structure visually unambiguous, regardless of how casually a marketing illustration renders it. |
| Repair Action Plan (§9) as the AI-integration pattern for structural repairs specifically | **Keep as specified in §9** | Cross-referenced, not restated. |

---

## §37. Accessibility Standards

**What exists today (DECIDED, F-2.1/F-2.2 shipped, F-5.0 re-verified):** 6 `jest-axe` automated tests (of ~39 originally-audited areas), one completed manual keyboard/DOM-accessibility-tree pass (F-2.2, via Chrome DevTools Protocol, explicitly disclosed as not a real screen reader), full ARIA-tabs coverage on all 4 tab-bar surfaces, real computed focus-visible rings. F-5.0's own re-audit found the test-coverage-to-surface-area ratio **shrinking** as new surfaces ship without matching new tests (F-4.5's three new special views got zero new a11y tests).

**Standard, binding:** WCAG 2.2 AA minimum for RAWRS's own interface (restated from `PRODUCT.md`, binding here too). Every new SPECIFIED item in this Bible (Repair Action Plan, source-strip Peek, Command Palette, Remediation Layers, Screen Reader Announcement generalization) must ship with: correct semantic roles, full keyboard operability using §21's consolidated shortcut table, and — where it's a list/tab pattern — reuse of `useArrowKeyTabs`/`useListReviewKeyboard` rather than new ad hoc handling (Product Principle 6). **Invent**: a standing rule that every milestone touching a new user-facing surface adds at least one `jest-axe` test for it, closing F-5.0's shrinking-ratio finding going forward rather than only naming it as a gap once more.

---

## §38. Performance Standards

**What exists today (DECIDED, standing gap across F-1/F-4.2/F-5.0/R-1.0):** no performance baseline has ever been measured — not bundle size, not Lighthouse, not a real large-document benchmark. R-1.0 produced a complete benchmark plan (time-to-first-paint, nav-tree time-to-interactive, page-turn P50/P95 latency, search responsiveness, memory) that has never been executed.

**Standard, binding:** no SPECIFIED item in this Bible that plausibly affects render cost at scale (Triple Compare's 3rd pane, Remediation Layers filtering, source-strip Peek panels, Command Palette's search index) ships without being measured against R-1.0's benchmark plan first — this closes the gap named four separate times across this project's audits by making it a hard gate on this Bible's own recommendations, not a fifth restatement.

---

## §39. Design Tokens

Formal token set adopted from V3 (`RAWRS Sentinel`), reconciled against RAWRS's shipped token *names* (values to be verified against actual `globals.css` during implementation, not assumed — see §40):

```yaml
spacing: { unit: 4px, xs: 4px, sm: 8px, md: 16px, lg: 24px, xl: 32px, sidebar_width: 260px, inspector_width: 320px, header_height: 64px }
radius: { sm: 2px, DEFAULT: 4px, md: 6px, lg: 8px, xl: 12px, full: 9999px }
typography:
  display-lg: { family: Inter, size: 48px, weight: 700, lineHeight: 56px, tracking: -0.02em }   # reserved contexts only, per §24
  heading-md: { family: Inter, size: 24px, weight: 600, lineHeight: 32px, tracking: -0.01em }
  body-base:  { family: Inter, size: 16px, weight: 400, lineHeight: 24px }
  body-sm:    { family: Inter, size: 14px, weight: 400, lineHeight: 20px }
  label-caps: { family: Inter, size: 12px, weight: 600, lineHeight: 16px, tracking: 0.05em }
  code-mono:  { family: JetBrains Mono, size: 13px, weight: 450, lineHeight: 20px }
color:
  surface: { dim: base-canvas, container-lowest, container-low, container, container-high, container-highest }  # 5-tier, reconcile against shipped surface-* tokens
  semantic: { primary: indigo, secondary: teal, tertiary: amber, error: coral }  # reconcile against shipped accent/success/warning/danger
  syntax: { tag: cyan, attr: amber, val: lavender }  # scoped exclusively to Semantic AST rendering (§7, §26) — never general UI
icons: Material Symbols Outlined, 20px, stroke-based, fill:0 default / fill:1 active
```

**This supersedes maintaining a separate `DESIGN.md`** — per the plan, this Bible is the single source of truth for both strategic (`PRODUCT.md`, kept) and visual (formerly `DESIGN.md`) context.

---

## §40. Engineering Constraints

*(Consolidated summary — every major SPECIFIED item's constraint, cross-referenced to its section rather than restated in full.)*

| Item | Section | Backend dependency? | Complexity | Risk |
|---|---|---|---|---|
| Source-strip / Peek panel | §9 | None | Medium | Low — reuses existing `PdfViewportContext` state |
| Repair Action Plan | §9 | **Yes** — backend must expose the specific DOM transformations a repair performs, not just accept/reject the whole correction | Medium (frontend) + Medium (backend) | Medium — new data shape needed |
| AI Confidence slider (Validation) | §10 | None — confidence already exists per-issue | Low | Low |
| Running score + Export button (Validation header) | §10 | None — readiness score already computed | Low | Low |
| Triple Compare (3-way split) | §7 | None | Medium — one more `PanelGroup` nesting level | Low |
| Cross-pane synchronized highlight | §7 | None — `SelectionContext` already the shared source of truth | Low-Medium | Low |
| Remediation Layers toggle | §14 | None | Low-Medium | Low |
| Command Palette | §20 | None | Medium — key-precedence rule needed vs. existing hooks | Medium |
| Screen Reader Announcement (generalized) | §19 | None — derivable from existing per-object data | Low | Low |
| `currentIndex`/roving-focus for Validation/Image/Table grids | §21 | None | Medium — per-surface, not shared automatically | Medium |
| `error.tsx` route boundary | §34 | None | Trivial | Low |
| Export consolidation | §35 | None — endpoints already exist | Low-Medium | Low — must preserve existing version-staleness guard |
| Large Document Mode | §30 | None (frontend items); confirm PDF range-request support (R-1.0's own open question) | Per R-1.0 | Per R-1.0 |

---

## §41. Implementation Roadmap

Ranked by ROI / Risk / Complexity / Impact (full ranking table in the Final Output section below — this section states sequencing logic only):

1. **`error.tsx`** (§34) — trivial, zero ambiguity, highest ROI-to-effort ratio in the whole Bible, and the most overdue item in the project.
2. **Context-preserving editing fix** (§9's source-strip/Peek) — highest reviewer-productivity ROI with no backend dependency and no open design question left.
3. **Keyboard-coverage completion** (§21's `currentIndex` prerequisite) — closes a named, honest, long-standing gap; no backend dependency.
4. **Validation Center upgrades** (§10's AI Confidence slider + running score) — low complexity, no backend dependency, direct Journey Stage 2 win.
5. **Triple Compare + cross-pane highlight** (§7) — the single biggest Journey Stage 4 (Compare) win; needs the benchmark gate (§38) before shipping if document size is a factor.
6. **Large Document Mode** (§30, per R-1.0's own sequencing — benchmark first).
7. **Repair Action Plan** (§9) and **Screen Reader Announcement generalization** (§19) — both real wins, both gated on confirming/adding backend data shape first (§40).
8. **Command Palette** (§20) — valuable but not blocking any other item; can proceed independently once the keyboard-precedence question is settled.
9. **Export consolidation** (§35), **Empty/Loading-state cleanup** (§32/§33) — real but narrower-impact, opportunistic.
10. **Postponed, needs a product decision first, not an engineering one**: Settings/Profile (§3), light/dark dual-theme scope (§26), responsive-viewport messaging (§29).

---

## §42. Future-Proofing for Planned Backend Capabilities

*(New section, per amendment — capabilities confirmed planned-but-not-yet-built via `TASKS.md`/`KNOWN_LIMITATIONS.md`, not speculative.)*

| Planned backend capability | Current status | Design obligation now |
|---|---|---|
| `CorrectionTelemetryEvent` exposure via API (M-4.4: collected server-side, never surfaced) | Built, not exposed | The Bible's Review Queue (§13) and Validation (§10) header patterns should reserve visual space/affordance for a future "History"/"Activity" surface without redesigning around it today — don't build UI for data that doesn't exist yet, but don't design this session's header layouts so tightly that a future history affordance has nowhere to go. |
| FEATURE_014 cross-source verification comparison panel (design complete, unimplemented per memory) | Designed, not built | §7's Triple Compare and §12's Evidence Visualization are the natural host surfaces for this once built — this Bible's design of both should be read as already accommodating a future third comparison source (Mathpix vs. RAWRS-native), not just Source/AST/Output. |
| Real-time push sync (SSE/WebSocket, vs. today's poll-based `document_version` watch) | Backend-blocked, R-1.0/F-4.2 named | Every SPECIFIED item that displays "current state" (running score, progress bar, export staleness guard) should read from `document_version` as the single reactive trigger it already is — so a future push-based update requires no UI redesign, only a faster trigger for the same reactive pattern. |
| Equation remediation, multi-column reconstruction, cross-page paragraph stitching, span-level text model | Not started (`KNOWN_LIMITATIONS.md`) | None of these are designed in this Bible — correctly so, no UI should be speculatively built for capabilities with no committed backend design yet (YAGNI). The one obligation now: §27's Component Library pattern (shared Inspector tab shell, shared detail-panel shape) is *already* generic enough that a future 7th object type (e.g., "Equation") slots into the existing `ObjectInspectorFrame`/Special-View pattern without inventing a new one — confirmed by design, not by accident, since every current object type already proves the pattern generalizes. |

---

## §43. Measurable Success Criteria

*(New section, per amendment — concrete numbers, not vague aspiration.)*

| Criterion | Target | How measured |
|---|---|---|
| WCAG conformance of RAWRS's own interface | 2.2 AA, zero known violations on all reviewed screens | `jest-axe` (expand coverage per §37) + one real screen-reader pass (NVDA/JAWS — never yet performed per F-2.2's own disclosure; a standing, named gap this Bible does not close by itself) |
| Keyboard shortcut coverage | 100% of list-review surfaces (Validation, Image/Table/Heading grids, Reviewer Workspace) share the §21 consolidated table | Manual audit per surface at implementation time |
| Large Document Mode | Meets R-1.0's own benchmark thresholds (not restated here — R-1.0 is the authority) | R-1.0's benchmark plan, executed before shipping any virtualization work |
| `error.tsx` coverage | 1 route-level boundary exists; a forced render exception anywhere shows a recoverable error, not a blank page | Manual test: throw in a component, confirm boundary catches it |
| Reviewer-facing latency | Search-input responsiveness stays under ~300ms perceived lag after debounce (§20 Command Palette, §10 nav search) | Manual timing during implementation; formal Lighthouse/DevTools measurement once §38's benchmark gate is executed |
| Accessibility test-to-surface ratio | Does not shrink again — every milestone adding a new user-facing surface adds ≥1 corresponding test | Tracked per-milestone in `PHASE_STATUS.md`, per §37 |
| Context-preserving editing | Zero object types where the bulk-grid path drops PDF/Markdown context without an available Peek/source-strip escape hatch (§9) | Manual audit across all 6 object types once §9 ships |

---

## §44. Implementation Contract (Preserved)

This Bible does not change the execution contract already governing this project's work, and restates it here so it travels with the permanent design record rather than living only in ticket text:

> Implement **only one milestone at a time**. Every milestone: **Plan → Implement → Test → Benchmark → Verify → Update documentation → Wait for approval.** No milestone continues until the previous one is verified. Report remaining technical debt honestly. Never claim verification that wasn't performed.

Concretely, per §41's roadmap: `error.tsx` is milestone 1 (if and when implementation resumes), and it alone must clear this full contract — plan, implement, `tsc`/build/test verification, a brief live-browser confirmation that a thrown error is actually caught, documentation update (`PHASE_STATUS.md`/`TASKS.md`), and explicit wait-for-approval — before milestone 2 begins. This Bible is a design specification, not a green light to implement; nothing in it authorizes skipping this gate for any item, however small it looks in §41's ranking.

---

## §45. Screen-by-Screen Review

Every screen named in the mission, verdict cross-referenced to the section that justifies it (no verdict is asserted without a home section above):

| Screen | Verdict | Section |
|---|---|---|
| Landing (marketing/hero framing) | **Reject** | §16 |
| Landing (`/` as upload utility, real shipped page) | **Keep** | §3, §5 Stage 0 |
| Authentication | **Reject** — no-op, confirmed intentional | §1 Principle 3, §3 |
| Dashboard (SaaS "System Overview") | **Reject** | §3, §1 Anti-Pattern 2 |
| Project View (multi-document/batch concept) | **Reject** | §3, §1 Principle 3 |
| Document Workspace | **Keep** (architecture), **Improve** (§9 context-preserving fix, §7 Triple Compare) | §8, §9, §7 |
| Reviewer Workspace | **Keep**, extend its keyboard model outward (§21) | §13, §21 |
| Validation Center | **Keep** IA, **Invent** (AI Confidence slider, running score) | §10 |
| Accessibility Center (as a separate screen) | **Reject** — accessibility is distributed by design, not a mode | §17 |
| Tables | **Keep** grid+detail pattern, **Improve** via §9's Peek fix, **Invent** Repair Action Plan | §9 |
| Images | Same as Tables | §9 |
| Headings | Same as Tables (lower urgency — F-4.2's own finding that heading context-loss is lower-stakes) | §9 |
| Lists | Same as Tables, applied consistently post-F-4.5 | §9 |
| Footnotes | Same as Tables; **Keep** the existing Screen Reader Announcement precedent, **Invent** its generalization elsewhere | §9, §19 |
| Callouts | Same as Tables | §9 |
| Reading Order | **Keep** reorder mechanism, **Improve** via source-strip (highest-value single application in this Bible) | §9, §18 |
| Metadata | **Keep** — no Stitch or audit evidence argues for change; out of scope for redesign | (unchanged) |
| Reports | **Improve** — fold into consolidated Export affordance rather than a separate destination | §35 |
| Export | **Improve** — consolidate, reuse version-staleness guard | §35 |
| Settings | **Postpone** — needs a product decision on scope first | §3, §41 |
| Profile | **Postpone** — same reasoning; also touches the rejected multi-user framing (§1 Principle 3) if designed as a real account surface rather than a local preference panel | §3 |

---

## FINAL OUTPUTS

### 1. RAWRS Design Bible v1.0
Complete, above (§0-§45). `PRODUCT.md` written and confirmed as this Bible's companion strategic document; no separate `DESIGN.md` maintained (§39 supersedes it).

### 2. Overall UX Score

**7.5 / 10.** Grounded, not vibes-based: the shipped architecture (Bible §8, DECIDED across 4 prior audits) is genuinely strong — a rare case where the underlying panel/sync/keyboard infrastructure is sound enough to extend rather than replace. Points held back by: zero performance baseline ever measured (§38, standing since F-1), the context-preserving-editing inconsistency now resolved *in design* (§9) but not yet *in code*, accessibility test coverage shrinking relative to surface area (§37), and the still-missing `error.tsx` (§34) — all fixable, none architectural, which is exactly why the score is a 7.5 (strong foundation, real but bounded gaps) rather than lower.

### 3. Remaining Weaknesses
1. `error.tsx` still doesn't exist — the single most avoidable weakness in the whole review (§34).
2. Context-preserving editing is inconsistent across object types today — designed away in §9, not yet built.
3. No performance baseline exists anywhere, so every "Large Document Mode" claim (Bible's own §30 included) is reasoned, not measured, until R-1.0's benchmark actually runs.
4. Keyboard coverage stops at `ReviewerWorkspace` — every other list-review surface is mouse-only (§21).
5. Accessibility test coverage is shrinking relative to shipped surface area (§37).
6. Three separate, materially different Stitch design explorations exist with no single one fully authoritative until this Bible — resolved now, but the underlying cause (design exploration happening disconnected from the shipped codebase) is worth naming so it doesn't recur.

### 4. Complete Redesign Recommendations
None. No screen or subsystem in this review warrants a full redesign — every **Reject** verdict above is a rejection of a *proposed* (Stitch) concept never shipped, not a redesign of something real RAWRS already has. The closest thing to a redesign is §9's context-preserving-editing resolution, and even that is framed as an **Improve** (a new affordance added to an existing, architecturally-sound pattern), not a **Replace**.

### 5. Component Inventory
See §27 in full. Summary: 4 shipped components/hooks justified and kept (`ObjectInspectorFrame`, `CorrectionHistoryList`, `useArrowKeyTabs`, `useListReviewKeyboard`), 6 new components specified with mandatory justification (Repair Action Plan, Source-strip/Peek, generalized Screen Reader Announcement, Command Palette, Remediation Layers toggle, AI Confidence slider), 3 proposed-but-rejected components with no surviving justification (vanity-metric Dashboard cards, generic multi-file Objects grid, ceremonial "Mode Active" badge).

### 6. Implementation Roadmap, Ranked

| Rank | Item | ROI | Risk | Complexity | Impact |
|---|---|---|---|---|---|
| 1 | `error.tsx` (§34) | Very High | Very Low | Trivial | Medium (prevents worst-case blank-page failures) |
| 2 | Context-preserving editing / source-strip (§9) | Very High | Low | Medium | High (Journey Stage 3-4, daily, every object type) |
| 3 | Keyboard-coverage completion (§21) | High | Medium | Medium | High (daily, every list-review surface) |
| 4 | Validation Center AI Confidence + running score (§10) | High | Low | Low | Medium |
| 5 | Triple Compare + cross-pane highlight (§7) | High | Low | Medium | High (Journey Stage 4) |
| 6 | Large Document Mode (§30, per R-1.0) | High (once benchmarked) | Medium | Medium | High for large documents specifically |
| 7 | Repair Action Plan (§9) | Medium-High | Medium (backend dep) | Medium | High (auditability + trust) |
| 8 | Screen Reader Announcement generalization (§19) | Medium | Low | Low | Medium-High (verification stage) |
| 9 | Command Palette (§20) | Medium | Medium | Medium | Medium (expert-user delight, not a blocker) |
| 10 | Export consolidation, empty/loading-state cleanup (§32-35) | Low-Medium | Low | Low | Low-Medium |

### 7. Everything That Should Be Deleted
- Nothing currently shipped. Every deletion candidate in this review is a *proposed, unbuilt* Stitch concept: the SaaS Dashboard, the marketing landing page, Sign In/Pro Plan/Enterprise nav, the generic multi-file Objects grid, the ceremonial "Systematic Audit Mode Active" badge. None of these exist in code today — "delete" here means "do not build," not "remove existing code."
- The one true cleanup item: 6 duplicated `CorrectionHistoryList` empty-message string literals (§32) — merge into one shared default.

### 8. Everything That Should Be Redesigned
- Nothing rises to full redesign (see Final Output 4). The closest candidates are all framed as **Improve**, not **Replace**, throughout this Bible: §9's context-preserving editing, §10's Validation Center header, §35's Export consolidation.

### 9. Everything That Should Remain Exactly As It Is
`WorkspaceShell`'s 3-zone architecture (§8), `ObjectInspectorFrame`'s shared tab shell (§11, §27), `useArrowKeyTabs`/`useListReviewKeyboard` (§21, §27), `SelectionContext`/`PdfViewportContext`/`MarkdownViewportContext` (§7), `CorrectionHistoryList` (§12, §27), Focus Mode (§31), the Special-View/Rail hybrid model itself (§0.3, F-4.4 DECIDED), Markdown/DOCX panes' lazy-mount behavior (§15-16), Metadata screen (§45).

### 10. Everything That Should Be Postponed Until Backend Completion
Repair Action Plan's specific DOM-transformation data shape (§40 — needs a small backend addition), `CorrectionTelemetryEvent`/History surface (§42 — built, not exposed), FEATURE_014 cross-source comparison panel (§42 — designed, not built), real-time push sync (§42 — backend-blocked), Settings/Profile scope (§3, §41 — needs a product decision, not backend work, but genuinely not actionable yet), equation/multi-column/cross-page/span-level remediation UI (§42 — no committed backend design exists yet, correctly out of scope).

---

**End of RAWRS Design Bible v1.0.** Per the mission's Execution Contract (§44): no implementation begins from this document alone. The next step is explicit approval to begin milestone 1 (`error.tsx`), which then runs its own full plan → implement → test → benchmark → verify → document → wait-for-approval cycle before milestone 2 is considered.


