# RAWRS Frontend Accessibility Testing

Phase F-2.1's deliverable: an automated accessibility testing foundation for RAWRS's own frontend, so a WCAG regression can no longer ship unnoticed (see `FRONTEND_COMPLETION_AUDIT_2026-07-13.md` item 34 — until this phase, RAWRS had zero automated accessibility testing and zero frontend test files of any kind).

Phase F-2.2 (below, "Manual validation findings") followed up with the manual keyboard/screen-reader-proxy pass this doc's own "Known scope limits" section had flagged as the recommended next step.

## Manual validation findings (Phase F-2.2)

`jest-axe` checks the static DOM tree — it cannot evaluate real tab order, focus visibility in practice, keyboard traps, or whether the page structure makes sense to someone navigating by heading or landmark. Phase F-2.2 validated those specifically, against a **live, running instance** of RAWRS (both the FastAPI backend and Next.js frontend dev servers, started for this session and stopped afterward) with real, already-processed documents.

**Disclosed limitation, per this milestone's own instruction:** no actual screen reader (NVDA, JAWS, Windows Narrator, VoiceOver) was executed with its audio/braille output interpreted — this CLI environment has no way to run one and listen to it. Instead, Chrome DevTools Protocol's accessibility tree (`take_snapshot`/`evaluate_script` via a live browser) was used as the most rigorous available proxy: this is the same underlying accessibility-tree data a real screen reader consumes via the OS's platform accessibility API (MSAA/UIA on Windows, AX API on macOS), so it verifies accessible names, roles, landmark structure, and focus state accurately — but it does not verify that the *spoken experience* of a real AT reads naturally, only that the underlying tree is correct. Treat these findings as "verified against the accessibility tree a screen reader would use," not as "verified with a real screen reader."

### Confirmed working (no fix needed)

- Skip-to-content link: correctly `sr-only` by default, reveals on keyboard focus, first tab stop, navigates to `#main-content`. Textbook-correct implementation.
- Landing page: proper heading hierarchy (one H1, four H2s, no level skips), real semantic landmarks (`<header>`/`<nav>`/`<main>`/`<footer>`, not just ARIA roles), and Recent Documents links have correct, well-formed accessible names + descriptions.
- Keyboard focus visibility: verified via `:focus-visible` match + real computed `box-shadow` (an accent-colored 2px ring) on the theme-toggle button — Tailwind's `focus-visible:ring-2` pattern is genuinely applying, not just present in source.
- Tab order through the initial toolbar (skip link → logo → nav link → theme toggle) is logical; no keyboard trap observed in this sequence.
- The `OutputWorkspace` tab bar (Review Queue / Accessible Markdown / Accessible DOCX Preview / Raw Mathpix Markdown) has a **fully correct ARIA tabs pattern already built** — `role="tablist"`/`role="tab"`/`aria-selected`/`aria-controls` on the buttons, matching `role="tabpanel"`/`aria-labelledby` on the panels. It just isn't the default-visible surface (see below).

### Issues found and fixed this milestone

1. **Zero heading elements anywhere on the Document Workspace.** The single most content-rich, most-used page in the app (`/documents/[id]`) had no `h1`–`h6` at all — confirmed by querying the live DOM, not assumed. A screen-reader user's "jump to next heading" navigation (one of the most common AT techniques) had nothing to land on. **Fixed:** added a visually-hidden `<h1>{job.filename}</h1>` in `frontend/app/documents/[id]/DocumentWorkspace.tsx` — the same "exactly one H1 per page" pattern `app/page.tsx` already had correctly. No visual change (the filename is already shown in `WorkspaceShell`'s own toolbar).
2. **Static, generic `<title>` on every document page.** `document.title` never changed per document — every workspace page shared the app's generic title, so a screen reader announcing the page on navigation (and a sighted user's browser tab/history) couldn't distinguish one document from another. **Fixed:** a `useEffect` in the same file sets `document.title` to `"{filename} — RAWRS"` once the job loads.

### Issues found, not fixed this milestone (backlog — out of scope for "minimal fix, no redesign")

- **`WorkspaceShell`'s center-view switcher and `SemanticNavTree`'s mode buttons (Outline/By Type/Pending/Issues/Search/Bookmarks) are plain buttons, not an ARIA tabs/tablist pattern** — unlike the properly-built `OutputWorkspace` tab bar above. A screen-reader user gets no signal that these form a mutually-exclusive view-switcher group or which one is active, beyond visual styling. Retrofitting the same pattern `OutputWorkspace` already uses is the right fix, but touches multiple components — out of scope for this milestone's "fix only what directly blocks, do not redesign."
- **Internal panel structure still has no heading hierarchy below the new page-level H1** — panel titles ("Outline," section labels in the inspector rail, etc.) are still styled `<div>`/`<span>` text, not real `<h2>`/`<h3>` elements. Adding the outer H1 fixed "the page has no heading at all"; it did not fix "the page's internal structure is heading-navigable," which would require touching `SemanticNavTree`, `ContextInspectorRail`, and `BottomPanel` — a larger change, deferred.
- **Keyboard shortcuts (Reviewer Workspace's 9-shortcut set) and Validation/Corrections/Image workspace interaction states were not re-verified live this session** — relied on the existing static code review (the shortcut implementation's `isTypingTarget()` guard, on-screen legend) from when that code was written, plus the Phase F-2.1 empty-state `jest-axe` coverage. A full live keyboard walkthrough of those three areas with populated data remains open.
- **No dialogs/modals exist anywhere in the codebase** (confirmed during the Phase F-1 audit) — so Escape-key/dialog-focus-trap behavior has nothing to verify against. Noted here so it isn't mistaken for an unverified gap; it's a non-applicable check.

## What this is — and isn't

`jest-axe` runs the same automated ruleset [axe-core](https://github.com/dequelabs/axe-core) uses (missing labels, invalid ARIA, contrast issues it can detect statically, landmark/heading structure problems, etc.) against a rendered component's DOM. **It is not a substitute for manual testing.** Axe-core's own documentation states it catches roughly 30-50% of WCAG issues automatically — things like "does this interaction make sense to a screen reader user," "is the reading order logical," or most color-contrast-in-context cases still need a human, ideally with a real screen reader (NVDA, JAWS, Windows Narrator, VoiceOver). Treat a clean `jest-axe` run as "no *automatically detectable* violations," not as "WCAG compliant."

## How to run it

```bash
cd frontend
npm test
```

This runs every `*.test.ts(x)` file under `frontend/__tests__/` (and anywhere else Jest's default discovery finds one) via `jest.config.js`. No backend needs to be running — every accessibility test renders a component directly with React Testing Library and mocked/minimal data, it does not exercise a live app.

## What's covered today (Phase F-2.1 minimum scope)

Six tests, one per area named in the Frontend Completion Audit's minimum scope, all in `frontend/__tests__/a11y/`:

| Area | Test file | Component under test | State tested |
|---|---|---|---|
| Landing / Upload | `landing-upload.a11y.test.tsx` | `app/page.tsx` (`UploadPage`) | Real render, `next/navigation` mocked, `api.listDocuments` stubbed to return `[]` |
| Document Workspace | `document-workspace.a11y.test.tsx` | `components/workspace/WorkspaceShell.tsx` | Shell chrome only — PDF/Markdown/DOCX panes are stub `<div>`s (the shell takes them as props; this isolates the shell's own accessibility from PDF-rendering concerns) |
| Reviewer Workspace | `reviewer-workspace.a11y.test.tsx` | `components/ReviewerWorkspace.tsx` | Empty state (no corrections loaded) — real `DocumentDataProvider`/`SelectionProvider`/`PdfViewportProvider`, no mocking needed since none of them fetch internally |
| Image Workspace | `image-workspace.a11y.test.tsx` | `components/ImageGrid.tsx` | Empty state (`images={[]}`) |
| Validation Center | `validation-center.a11y.test.tsx` | `components/ValidationIssueTable.tsx` | Empty state (`issues={[]}`), read-only mode (no `jobId`) |
| Corrections Center | `corrections-center.a11y.test.tsx` | `components/CorrectionsPanel.tsx` | Empty state (`corrections={[]}`) |

**Current result: 6/6 passing, 0 violations.** This is a real, honest baseline for the states tested — see "Known scope limits" below for what it does *not* yet cover.

## Known scope limits (deliberate, not hidden)

- **Empty-state only.** Every test above renders its component with no data (or minimal stub data). Populated states — a real `CorrectionItem`, a real `ImageItem` with an alt-text review flow, a real `ValidationIssue` row — are not yet covered. Interactive elements that only render when data is present (per-row buttons, filter chips with real counts, the Reviewer Workspace's proposal card) haven't been axed yet.
- **No keyboard-interaction testing.** `jest-axe` checks the static DOM tree, not focus order, tab sequence, or keyboard-trap behavior. The Reviewer Workspace's 9 keyboard shortcuts (see Frontend Completion Audit item 23) are untested by this suite.
- **No manual screen-reader pass.** Per the ticket for this milestone, a live keyboard-only walkthrough of the Reviewer Workspace and Document Workspace was in scope "if practical" — it was **not performed this session** (would require starting the backend + frontend dev servers and a live browser session; deferred given this session's scope). This remains open and should be the next concrete step before claiming any real accessibility confidence beyond the automated baseline above.
- **Six components, not thirty-nine.** This phase covered the ticket's named minimum scope only. The other ~30 frontend areas in the Completion Audit (Lists/Callouts/Footnotes workspaces, Page Label Manager, Reading Order, etc.) have no accessibility test yet.

## How to add a new accessibility test

Follow the existing pattern — render the component (with real providers where they're simple/synchronous, mocked API calls where they'd hit a network boundary), then assert `toHaveNoViolations()`:

```tsx
import { render } from "@testing-library/react";
import { axe } from "jest-axe";
import { YourComponent } from "@/components/YourComponent";

describe("Your Area accessibility", () => {
  it("has no automatically detectable accessibility violations", async () => {
    const { container } = render(<YourComponent {...minimalProps} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
```

Notes from setting up the first six:
- `WorkspaceShell` needs `ThemeProvider` (it renders `ThemeToggle`, which reads theme context).
- `ReviewerWorkspace` needs `PdfViewportProvider` + `SelectionProvider` + `DocumentDataProvider` wrapping it (all three are plain, synchronous local state — no mocking needed, just wrap with the real providers).
- If a component imports `next/navigation`, mock it: `jest.mock("next/navigation", () => ({ useRouter: () => ({ push: jest.fn() }) }))`.
- If a component calls `@/lib/api` at mount/render time, don't `jest.mock("@/lib/api", factory)` — that path-alias form failed to resolve reliably under `next/jest`'s module mapping in this setup. Import the real `api` object and `jest.spyOn(api, "methodName").mockResolvedValue(...)` instead (see `landing-upload.a11y.test.tsx`).
- `window.matchMedia` and any other jsdom-missing browser API should be polyfilled once in `jest.setup.ts`, not per test file (see the existing `matchMedia` stub there).

## Configuration reference

- `frontend/jest.config.js` — uses `next/jest`'s `createJestConfig()`, which reads this app's own `next.config.ts`/`tsconfig.json` (including the `@/*` path alias) so no hand-rolled SWC/Babel transform config is needed.
- `frontend/jest.setup.ts` — loaded via `setupFilesAfterEnv`; extends `expect` with `jest-axe`'s matcher (via `jest-axe/extend-expect`, which supplies both the runtime matcher and its TypeScript types in one import) and polyfills `window.matchMedia`.
- `frontend/next.config.ts` — `transpilePackages: ["react-resizable-panels"]`. This isn't just a build setting: `next/jest` derives its Jest `transformIgnorePatterns` from this list, so it's also what lets `WorkspaceShell` (which uses `react-resizable-panels`, an ESM-only package) render inside Jest at all. There is no way to override `transformIgnorePatterns` directly in `jest.config.js` when using `next/jest` — it always recomputes the pattern from `transpilePackages`.

## Recommended next step

Run the deferred manual keyboard-only + screen-reader pass on the Reviewer Workspace and Document Workspace (the two richest, most-used surfaces) before extending automated coverage further — it's likely to surface real issues the automated ruleset structurally cannot catch (focus order, keyboard traps, meaningful reading order), and those findings should shape which components get the *next* six accessibility tests.
