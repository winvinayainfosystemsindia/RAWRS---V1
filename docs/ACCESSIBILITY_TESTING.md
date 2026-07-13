# RAWRS Frontend Accessibility Testing

Phase F-2.1's deliverable: an automated accessibility testing foundation for RAWRS's own frontend, so a WCAG regression can no longer ship unnoticed (see `FRONTEND_COMPLETION_AUDIT_2026-07-13.md` item 34 — until this phase, RAWRS had zero automated accessibility testing and zero frontend test files of any kind).

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
