# RAWRS Frontend Completion Audit — 2026-07-13 (Phase F-1)

Point-in-time audit, current as of commit `1571747`. Compares actual frontend code (`frontend/`) against `docs/PHASE1_SCOPE.md`, `docs/RAWRS_PROJECT_CONTEXT.md`, `docs/TASKS.md`, `docs/PAGE_RULES.md`, `docs/HEADING_RULES.md`, `docs/BACKEND_COMPLETION_AUDIT_2026-07-13.md`, and direct inspection of every component under `frontend/components/`. No code was changed to produce this audit.

**On the authoritative sources:** `PHASE1_SCOPE.md` and `RAWRS_PROJECT_CONTEXT.md` both predate the platform layer entirely — the latter literally states "there is no frontend directory," which its own header now flags as stale. Neither document ever describes a multi-user, multi-project, or authenticated product — RAWRS's original vision is a **local-first, single-reviewer workstation**. This matters directly for several items below (Authentication, Dashboard, Project Management): their absence is not automatically a gap against the *original vision*, even though the ticket asks about them as if they might be. `docs/CURRENT_STATE.md` and `docs/ARCHITECTURE_CURRENT.md` (both dated 2026-07-08, pre-Phase-M-3/M-4/M-5) were used as structural references but not trusted where current code disagrees.

---

## 1. Frontend Completion Matrix

| # | Area | Status | Evidence |
|---|---|---|---|
| 1 | Landing Page | 🟡 Needs Polish | `frontend/app/page.tsx` doubles as landing + upload (no separate marketing page — consistent with the local-first single-user vision, not a gap against it). Has real responsive treatment (`sm:`/`lg:` breakpoints). Visual identity is minimal: one heading, one description line. |
| 2 | Authentication | ❌ Missing — **not a gap** | `RAWRS_PROJECT_CONTEXT.md`/`CURRENT_STATE.md` confirm single-developer, local-only, single-user by design. No multi-user concept anywhere in any vision doc. Out of scope, not an oversight. |
| 3 | Dashboard | 🟠 Partially Complete | `RecentDocuments` on `page.tsx` — a flat, live-polling list with status badges (`Badge.tsx`) and extracted-object counts. No per-user views, no sort/filter, no analytics/summary view across documents. |
| 4 | Project Management | ❌ Missing — **not a gap** | No "projects" grouping concept anywhere in the vision or the code. Workflow is one document at a time by design (`RAWRS_PROJECT_CONTEXT.md`'s "Current Development Target": Upload → Process → Markdown → DOCX). |
| 5 | Upload Workflow | ✅ Production Ready | `page.tsx` — dual dropzone (Mathpix package + source PDF), file-type validation, readiness checklist, drag-and-drop, accessible labels (`sr-only`, `aria-label`), inline `role="alert"` errors. |
| 6 | Document Workspace | ✅ Production Ready | `WorkspaceShell.tsx` — persistent PDF/Markdown/DOCX center pane, `SemanticNavTree` left rail, `ContextInspectorRail`/`ObjectInspectorFrame` right rail, collapsible `BottomPanel`, resizable panels (`react-resizable-panels`), Focus Mode. |
| 7 | Reviewer Workspace | ✅ Production Ready | `ReviewerWorkspace.tsx` (Phase M-4, this session) — filters/search/sort, 9 keyboard shortcuts, queue navigation synced to PDF/selection, progress tracking. |
| 8 | Outline Navigation | ✅ Production Ready | `SemanticNavTree.tsx` — Outline / By Type / Pending / Issues / Search modes, plus a "Workspaces" section linking every whole-document editor. |
| 9 | Semantic Object Editing | ✅ Production Ready | `ObjectInspectorFrame.tsx` (tabbed: Properties/Evidence/History/AI/Actions), `ContextInspectorRail.tsx` — driven by object selection, one consistent pattern reused across every asset type. |
| 10 | Image Workspace | ✅ Production Ready | `ImageGrid`/`ImageCard`/`ImageDetailPanel`/`BulkActions` — filters (Missing Alt/Needs Review/Accepted/Rejected/Decorative/Low Res), per-image + whole-document bulk AI generation, full review-state actions. |
| 11 | AI Alt Text Workspace | ✅ Production Ready | Generate/Approve/Reject/Mark Decorative/Mark Complex/Skip/Edit per image; `ImageDetailPanel` shows structured AI output (Description/Purpose/Visible Text/Confidence/Warnings); whole-document bulk generation exists (Phase 1 IDE redesign). |
| 12 | Tables Workspace | ✅ Production Ready | `TableGrid`/`TableCard`/`TableDetailPanel` — caption + WCAG H73 summary editing, header-row toggle, manual table creation for detector misses. |
| 13 | Lists Workspace | 🟡 Needs Polish | `ListPanel.tsx` — a single panel, not the grid+detail-panel pairing Images/Tables/Headings get. Lighter treatment, consistent with lists being a simpler, more recently-added asset type. |
| 14 | Callouts Workspace | 🟡 Needs Polish | `CalloutPanel.tsx` — same single-panel pattern as Lists. Backend itself has no PDF-side callout detector yet (`ARCHITECTURE_CURRENT.md`), so the thinner UI reflects a genuinely thinner backend feature, not a frontend oversight alone. |
| 15 | Footnotes Workspace | 🟡 Needs Polish | `FootnoteTable.tsx` — table view with review states (`FootnoteReviewStatus`, 4 values) wired, but no dedicated detail-panel/grid pairing like Images/Tables. |
| 16 | Page Label Manager | ✅ Production Ready | `PageLabelManagerPanel.tsx` (FEATURE_018) — override/section/detected precedence editing. |
| 17 | Reading Order Workspace | ✅ Production Ready | `ReadingOrderPanel.tsx` + numbered PDF overlay (Phase 1 IDE redesign) — drag-reorder, approve. Matches the deliberately human-only scope (`KNOWN_LIMITATIONS.md`). |
| 18 | Validation Center | 🟡 Needs Polish | `ValidationIssueTable.tsx`, `ChecklistPanel.tsx`, `ReadinessPanel.tsx` — persistent issue triage (ignore/defer/reopen) implemented. Currently surfaces noise from a known **backend** bug (`PAGE_001` false-positives under `AUTO`/`DISABLED` policy, see Backend Audit item 13) — a frontend symptom of an upstream issue, not a frontend defect itself. |
| 19 | Corrections Center | ✅ Production Ready | `CorrectionsPanel.tsx`, `CorrectionHistoryList.tsx`, `ReviewerWorkspace.tsx` — full accept/reject/edit/ignore/undo loop, tested end to end. |
| 20 | Evidence Inspector | ✅ Production Ready | `EvidenceBreakdown.tsx` — per-signal confidence breakdown surfaced directly from the Evidence Engine. |
| 21 | History | 🟠 Partially Complete | `CorrectionHistoryList.tsx` covers per-correction history only. No document-wide activity/audit-log view. M-4.4's `CorrectionTelemetryEvent` data (timestamps, latency, action sequence) is collected server-side but **surfaced nowhere in the frontend** — matches Backend Audit item 18 exactly. |
| 22 | Search | 🟡 Needs Polish | Two independent implementations: a "Search" mode inside `SemanticNavTree`, and a separate free-text filter inside `ReviewerWorkspace` (M-4.1). Neither is a unified, whole-document search. |
| 23 | Keyboard Workflow | 🟠 Partially Complete | Fully built (9-shortcut set: next/prev/accept/reject/ignore/undo/inspect/jump/search) but confirmed (via direct grep across every component) to be **scoped only to `ReviewerWorkspace.tsx`**. Every other workspace — Images, Tables, Headings, Footnotes, Lists, Callouts, the PDF viewer itself — is mouse-only. |
| 24 | Focus Mode | ✅ Production Ready | `WorkspaceShell.tsx` — toggle, `aria-pressed`, collapses nav+rail (Phase 1 IDE redesign). |
| 25 | Split View | ✅ Production Ready | PDF+DOCX / Markdown+DOCX split presets, resizable panels (Phase 1 IDE redesign). |
| 26 | Markdown Preview | ✅ Production Ready | `MarkdownEditor.tsx`. |
| 27 | DOCX Preview | ✅ Production Ready | `DocxPreview.tsx` — live-synced to `document_version` (a real bug from before Phase 1 IDE redesign — silent staleness — since fixed). |
| 28 | PDF Viewer | ✅ Production Ready | `PdfViewer.tsx` — reading-order numbered overlay, jump-to-object sync. |
| 29 | Synchronization | ✅ Production Ready | `PdfViewportContext`/`SelectionContext` (M-4.2) — bidirectional queue↔PDF↔inspector sync. Two real infinite-render-loop bugs were found and fixed via live browser verification (not just unit tests) during M-4.2. |
| 30 | Export Center | 🟠 Partially Complete | Download buttons for markdown/docx/report exist ("Corrections/Export area" per `CURRENT_STATE.md`), but there is no unified export UI — no format selection, no batch export, no export history. |
| 31 | Settings | ❌ Missing | Zero settings component/page anywhere (confirmed by direct search). No user-configurable preference is exposed in the UI at all — page-numbering policy, AI provider choice, theme default, etc. are all either compile-time defaults or per-document reviewer actions, never a persisted app-level setting. |
| 32 | Theme | ✅ Production Ready | `ThemeToggle.tsx` + `ThemeProvider`. Design-token classes (`bg-surface-*`, `text-text-*`, `border-border`) used consistently across every component inspected — no hardcoded colors found. |
| 33 | Responsive Layout | 🟠 Partially Complete | The upload/landing page has real responsive breakpoints. **The Document Workspace itself — where all real remediation work happens — has zero responsive breakpoint classes** (`sm:`/`md:`/`lg:`/`xl:`), confirmed by direct grep across `frontend/components/workspace/`. The core product is desktop-only, and this appears to be an accident of never needing to address it rather than a documented decision. |
| 34 | Accessibility | 🟠 Partially Complete — **the most consequential finding in this audit** | ARIA attributes (`aria-label`/`aria-live`/`role`/`aria-pressed`/`sr-only`) appear in 18 of 36 components (~50%) — real, but partial, uncoordinated coverage. **Zero automated accessibility testing exists** — no `jest-axe`, no `@axe-core`, no Lighthouse CI anywhere in the frontend. **Zero frontend unit/component tests exist at all** (confirmed: no project-owned `.test.tsx`/`.test.ts` file anywhere under `frontend/`, only `node_modules` dependency tests matched). No documented manual screen-reader pass (NVDA/JAWS/Narrator/VoiceOver) exists in any doc reviewed. For a tool whose entire purpose is accessibility remediation, RAWRS's own frontend accessibility has never been formally verified. |
| 35 | Loading States | 🟠 Partially Complete | Ad hoc `<p>Loading…</p>` text in a couple of places (`page.tsx`'s `RecentDocuments`, `PipelineView.tsx`); no skeleton loaders, no shared loading-state component reused elsewhere. |
| 36 | Empty States | 🟡 Needs Polish | Present in several places ("No documents have been processed yet.", "No cross-source corrections were proposed for this document.", "No corrections match the current filters.") but coverage across every grid/panel was not individually verified — likely inconsistent. |
| 37 | Error States | 🟠 Partially Complete | Inline `role="alert"` messages exist for upload failures and form validation. **No Next.js route-level `error.tsx` boundary exists anywhere** (confirmed by direct search) — an unhandled render error in any deep component currently has no graceful fallback; the user would see a blank or broken page. |
| 38 | Animations | ❌ Missing (as a deliberate design element) | Only basic Tailwind `transition-colors`/`transition-opacity` on hover states (39 occurrences across 25 files, all simple micro-interactions). No `framer-motion`, no `@keyframes`, no meaningful motion design. Given `RAWRS_PROJECT_CONTEXT.md`'s own "do not introduce unnecessary frameworks" rule, this reads as correct restraint rather than negligence — but it is a real absence against the ticket's own checklist. |
| 39 | Performance | 🟠 Needs Investigation | No bundle-size analysis, no Lighthouse CI, no React DevTools Profiler pass documented anywhere. `tsc --noEmit`/`next build` are the only checks ever run (this session and per `PHASE_STATUS.md`'s history) — type-correctness, not runtime performance. Mirrors the identical finding in the Backend Audit (item 19) — a project-wide blind spot, not frontend-specific. |

---

## 2. Remaining Frontend Roadmap

**Not a gap — out of scope by the original vision, don't build without a product conversation:**
- Authentication, Project Management (items 2, 4) — RAWRS has never been a multi-user product.

**Real, addressable gaps — no backend work required:**
- Global unified search (item 22) — merge the two existing search implementations into one.
- Keyboard workflow extended beyond Reviewer Workspace (item 23) — the pattern already exists in `ReviewerWorkspace.tsx`; it needs to be generalized/extracted and applied to Images/Tables/Headings/Footnotes.
- Route-level error boundaries (`error.tsx`) (item 37) — a Next.js App Router primitive, not currently used at all.
- Responsive layout for the Document Workspace (item 33) — currently desktop-only by omission, not decision.
- Lists/Callouts/Footnotes workspace parity with Images/Tables (items 13, 14, 15) — extend the existing detail-panel pattern.
- History surface for `CorrectionTelemetryEvent` (item 21) — data already exists server-side (Backend Audit item 18), purely a frontend display task once the backend exposes it via API (small backend + frontend pairing).
- Export Center consolidation (item 30) — unify existing download buttons into one place with format/batch options.
- Settings (item 31) — needs a product decision on what's actually configurable before building.

**Needs backend work first (see Backend Completion Audit for detail):**
- History (item 21) requires the backend to expose `CorrectionTelemetryEvent` via an API endpoint (Backend Audit item 18) before any frontend display work is worthwhile.
- Validation Center noise (item 18) requires the backend `PAGE_001` policy-threading fix (Backend Audit item 13) — no frontend change can fix this on its own.

**Cross-cutting, needs a dedicated pass, not a single ticket:**
- Accessibility (item 34) — audit every component against WCAG 2.2, add automated testing (`jest-axe` minimum), and run at least one real manual screen-reader pass before calling this "done." Given the product's own purpose, this deserves to be prioritized above nearly everything else on this list.
- Performance (item 39) — establish a baseline (Lighthouse, bundle analysis) before deciding whether any optimization work is even needed.

---

## 3. Ranked Implementation Order

1. **Accessibility hardening** (item 34) — highest priority given RAWRS's own purpose; the irony of an accessibility-remediation tool never having verified its own accessibility is the single most important finding in this audit. Start with automated testing (`jest-axe`) + one real screen-reader pass, then fix what it finds.
2. **Route-level error boundaries** (item 37) — small, mechanical, closes a real robustness gap (a single component crash currently has no graceful fallback anywhere in the app).
3. **Keyboard workflow parity** (item 23) — the pattern is proven in `ReviewerWorkspace.tsx`; extending it directly reduces reviewer clicks/context-switching across the whole IDE, which is this project's own stated productivity goal.
4. **Global search unification** (item 22) — two competing implementations is worse than either alone; consolidate.
5. **Lists/Callouts/Footnotes workspace parity** (items 13–15) — brings the three thinner workspaces up to the Images/Tables/Headings standard.
6. **Responsive layout for the Document Workspace** (item 33) — worth doing, but lower urgency than the above since RAWRS is explicitly a desk-based professional tool, not a mobile product.
7. **Export Center consolidation** (item 30) and **History surface** (item 21, paired with its backend prerequisite) — real but narrower-impact items.
8. **Settings** (item 31) — needs a product decision on scope before it's buildable at all; not an engineering-effort question yet.
9. **Performance baseline** (item 39) — establish measurement before optimizing; likely fine as-is given no reported complaints, but currently unverified either way.

---

## 4. UX Issues

- **Keyboard/mouse inconsistency** (item 23): a reviewer who learns the Reviewer Workspace's 9 shortcuts gets no equivalent efficiency anywhere else in the IDE — a jarring, unlearned-elsewhere experience for "professional remediators who use RAWRS for hours every day" (the ticket's own framing).
- **Two search boxes, two behaviors** (item 22): a reviewer reasonably expects one search to behave like the other; right now they don't share an implementation.
- **Desktop-only workspace with no signal that it's desktop-only** (item 33): there is no responsive fallback and no messaging telling a user on a narrow viewport that the tool isn't designed for their screen size — it just silently breaks or clips.
- **Silent failure mode on render errors** (item 37): with no `error.tsx`, a single component throwing during render likely blanks the whole page with no recovery path or error message for the user.
- **Uneven workspace maturity** (items 13–15 vs. 10/12/16/17): a reviewer moving from the polished Images/Tables/Page-Label/Reading-Order workspaces to Lists/Callouts/Footnotes will notice the drop in capability — inconsistent product feel across otherwise-parallel asset types.

---

## 5. Accessibility Issues

- **No automated accessibility testing exists at all** — the single largest finding. Nothing currently prevents a WCAG regression from shipping unnoticed.
- **No documented manual screen-reader verification** (NVDA/JAWS/Narrator/VoiceOver) — the ticket explicitly names all four; none has apparently ever been run against this frontend.
- **ARIA coverage is real but partial and uncoordinated** (~50% of components have some ARIA attribute) — this is evidence of good instincts in the components that have it (`sr-only` labels, `role="alert"`, `aria-pressed`, focus-visible rings were all seen directly in `page.tsx`/`ReviewerWorkspace.tsx`), not evidence of a systematic accessibility pass across the whole app.
- **Keyboard-only users** are well served in the Reviewer Workspace (item 23) but effectively locked out of equivalent efficiency everywhere else — a keyboard-only reviewer cannot navigate Images/Tables/Headings workspaces without a mouse as fluently as a Reviewer-Workspace user can.
- **No documented color-contrast verification** for the theme tokens (item 32) in either light or dark mode — the tokens are used consistently, but consistency isn't the same as WCAG AA contrast compliance, and nothing in the repo confirms the latter.

---

## 6. Production Readiness Assessment

**The frontend is production-ready as a single-reviewer, desktop-based document remediation workstation** for the workflows it was built around: upload → per-document review across 6 registered asset types → export. The Document Workspace, Reviewer Workspace, and every major asset-type workspace except Lists/Callouts/Footnotes are mature, well-integrated, and backed by real bug fixes found through live browser verification (not just unit tests) — genuine engineering rigor, not surface polish.

**It is not production-ready for:**
- Any claim of accessibility compliance for RAWRS's *own* interface (item 34) — this has never been verified, automated, or manually tested, and is the single output most at odds with the product's stated purpose.
- Non-desktop use (item 33) — the core workspace has no responsive behavior.
- Resilience to an unexpected component-level failure (item 37) — no error boundary exists anywhere.
- Any claim about frontend performance (item 39) — no measurement has ever been taken, in either direction.

As with the Backend Audit, none of these are silent — every one is named explicitly here, with the evidence that grounds it.

---

## 7. Recommendation

**Can RAWRS become a production-ready Accessibility Remediation IDE after the remaining items above? Yes — but only after item 34 (Accessibility) specifically, not merely after clearing the whole list.**

The rest of the roadmap (keyboard parity, search unification, workspace parity, error boundaries, responsive layout, export/history/settings) are real, worthwhile, well-scoped engineering tasks that materially improve reviewer productivity and polish — but none of them is disqualifying on its own for calling the product "production ready" in the ordinary sense. Accessibility is different: it is the one item that speaks directly to whether RAWRS can credibly claim to be an *accessibility* remediation tool while its own interface has never been checked against the standard it exists to enforce on other people's documents. Recommend treating item 34 as a gate, not a backlog item — everything else on this list can reasonably proceed in parallel or after.

---

## Devil's Advocate — assumptions, failure modes, and what would prove this wrong

**Assumptions made in this audit:**
- That "production ready" means ready for RAWRS's actual, stated user (a professional remediator at a desk), not a general public web product — this shaped the Responsive Layout and Animations findings toward "real but lower-priority" rather than "blocking."
- That absence of a doc/test file means absence of the underlying practice (e.g., no `error.tsx` file → no error boundary exists). This is a fair inference for Next.js's file-based conventions but does not rule out an as-yet-unfound custom React error-boundary class component elsewhere; a targeted search found none, but a negative search result is weaker evidence than a positive one.
- That the ~50% ARIA-attribute component count is a meaningful proxy for accessibility coverage. It is not a WCAG audit — a component with zero ARIA attributes may still be fully accessible via correct semantic HTML alone, and a component with several ARIA attributes may still fail WCAG elsewhere (contrast, focus order, motion). This number should be read as "partial signal," not as a score.

**How this recommendation could fail:**
- If RAWRS's actual near-term users genuinely need multi-user/concurrent access (contradicting the "single reviewer" framing this audit relied on), then Authentication/Project Management should be reclassified from "not a gap" to "real gap," and the roadmap ordering changes substantially.
- If reviewers already work primarily via keyboard and simply haven't complained, the Keyboard Workflow gap (item 23) may be a bigger live pain point than this audit's ranking suggests — this audit has no usage telemetry to check against (ties directly to Backend Audit item 18, which is also unresolved).
- If the current ARIA coverage, despite being partial, already happens to clear WCAG AA for the flows that matter most, the urgency of item 34 could be lower than stated here — but this cannot be confirmed or ruled out without the automated + manual testing this report recommends, which is exactly the gap being flagged.

**What evidence would change this recommendation:**
- A real `jest-axe` run producing a clean or near-clean report would substantially soften the Accessibility finding.
- A completed manual screen-reader pass (even informally) against the Document Workspace and Reviewer Workspace would either confirm or contradict the "never verified" claim directly.
- Actual reviewer usage data (once Backend Audit item 18's telemetry is surfaced per this audit's own roadmap) would validate or invalidate several UX priority calls made here on inference alone (e.g., how much the keyboard-workflow gap actually costs in practice).
