# RAWRS Frontend

Next.js/React/TypeScript/Tailwind review platform for the RAWRS accessibility remediation pipeline. Talks to the FastAPI backend in `../src/api/` at the URL in `NEXT_PUBLIC_API_BASE_URL` (`.env.local` sets `http://127.0.0.1:8001` for local development; the value is fixed at build time, so a hosted build needs the hosted API URL — see `../docs/DEPLOYMENT.md`).

**Equations:** the backend exposes `GET/PATCH /api/documents/{id}/equations` and raises `EQUATION_001` in the validation queue; the **Equations workspace** (flagged-only filter, LaTeX/number/description editing, correction history with undo) reviews them.

**Upload:** a PDF is required; a Mathpix MMD export is optional; **batch upload** queues many PDFs one at a time. **Dashboard:** `/documents` lists every processed document with counts, search and filters. **Workspace:** VS Code-style, full-width, with PDF, editable Markdown and live DOCX preview side by side; the **Export Center** composes readiness, the checklist audit and downloads. **Settings:** `/settings` shows theme, backend URL, AI status and version. Tests: `npx jest --ci` (15 suites / 45 tests in CI on 2026-10-01), `npx tsc --noEmit`, `npm run build`.

## Getting started

```bash
npm install
npm run dev
```

**Open `http://localhost:3000` — not `http://127.0.0.1:3000` or a LAN IP.** Next.js 16's dev server blocks cross-origin dev requests (including its own hot-reload WebSocket) for any host other than the exact one it printed. Using a different host silently breaks HMR and can make the browser fall back to rapid full-page reloads, wiping in-progress form state (e.g. a file just selected in the upload form). See `next.config.ts`'s `allowedDevOrigins` and `../docs/DECISIONS_LOG.md` Part 24 for the full story.

The backend must be running separately for the app to do anything useful:

```bash
cd .. 
.venv\Scripts\activate       # Windows
uvicorn src.api.main:app --reload
```

## Structure

- `app/` — Next.js App Router pages (`page.tsx` = upload page, `documents/page.tsx` = documents dashboard, `documents/[id]/` = per-document workspace, `settings/page.tsx` = settings)
- `components/` — review panels, grids, detail panels for every reviewable object type (headings, images, tables, lists, callouts, page labels, corrections)
- `components/workspace/` — the `WorkspaceShell` layout: PDF/Markdown/DOCX center-pane switcher, `SemanticNavTree`, `ContextInspectorRail`, `BottomPanel`
- `lib/api.ts` — typed client for the backend's REST API
- `lib/store/` — React context providers (document data, selection, PDF/Markdown viewport sync)
- `lib/theme/` — light/dark theme provider, backing the CSS custom-property tokens in `app/globals.css`

## Theming

Prefer the semantic tokens in `app/globals.css` (`bg-surface-panel`, `text-text-secondary`, `bg-accent`, `text-danger`, etc.) over raw Tailwind palette classes (`gray-*`, `blue-*`, ...) in any new or edited component — the raw classes have no `dark:` handling and will render incorrectly when a user switches themes via `ThemeToggle`.

## Build

```bash
npm run build   # production build — also the fastest way to catch a TypeScript error
npm run start   # serve the production build locally
```

See `../README.md` and `../docs/DOCUMENTATION_MAP.md` for the rest of the project's documentation.
