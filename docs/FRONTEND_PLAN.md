# Frontend completion plan

Decided 2026-10-01: **complete the existing Next.js frontend**, not rebuild it. Start after the usage limit resets (2026-10-02 19:31 IST). Items run cheapest first; each is its own commit, with typecheck + Jest + production build + a browser check of the running app.

## Already exists (do not rebuild)

Upload with a polling recent-documents list (`app/(site)/page.tsx`); workspace with PDF / Markdown / DOCX panes; nav tree, review rail, panels for headings, images, tables, notes, lists, callouts, corrections, reading order, page labels, metadata, validation, readiness, checklist audit (`ChecklistAuditPanel`), downloads (`OutputWorkspace`); theme toggle; 6 Jest test files.

## Backend already available

`GET/PATCH /documents/{id}/equations`, `GET /documents`, `GET /ai/status`, `GET /documents/{id}/checklist`, corrections endpoints. **Missing:** document delete / re-run endpoints (`document_store.delete_document` exists), and any authentication.

## Plan

| # | Item | Backend change | Files to start from |
|---|---|---|---|
| 1 | `EQUATION_001` shows under the right category/filter in the validation queue | none | `lib/validationCategories.ts` |
| 2 | **Equations panel**: list, flagged-only filter, edit LaTeX / number / description, flag reasons, undo via corrections history, nav entry, Jest test. LaTeX + Unicode text, no new library | none | `lib/api.ts`, new `components/EquationsPanel.tsx`, `SemanticNavTree.tsx`, `ActivityBar.tsx`, `DocumentWorkspace.tsx` |
| 3 | **Export center** tab: readiness + checklist audit (incl. `DR-EQ`) + all downloads in one place | none | `ReadinessPanel`, `ChecklistAuditPanel`, `OutputWorkspace` |
| 4 | **Settings page**: theme, AI status, backend URL, version | none | `GET /ai/status`, `ThemeProvider` |
| 5 | **Batch PDF upload**: many files, per-file progress/errors, cancel (frontend queues; backend takes one file per request) | none | `app/(site)/page.tsx` |
| 6 | **Documents dashboard** `/documents`: search, sort, status filters, counts | none | `RecentDocuments` in `app/(site)/page.tsx` |
| 7 | **Delete and re-run** a document, with confirm dialogs | new `DELETE` + re-run endpoints; data-loss risk | `src/api/routes.py`, `document_store.py` |
| 8a | **Login via Cloudflare Access identity** ("signed in as …", edits attributed). The identity header is **unverified** | small | `src/api/routes.py`, `lib/api.ts` |
| 8b | **Own accounts**: login page, sessions, guards, roles, ownership | a whole auth system | — |

**Before 8:** the company must say which identity provider and how many reviewers (`docs/STATUS_REPORT_2026-09-30.md` §7, Q8). Concurrent editing of one document is still unhandled and matters most once there are users.

## Working rules for the session

- Run tests in batches; frontend: `npx tsc --noEmit`, `npx jest --ci`, `npm run build`. Backend tests are slow — never run two pytest processes at once.
- Verify each screen in the browser (chrome-devtools MCP) against the running backend on 8001 and frontend on 3000; open `http://localhost:3000`, not `127.0.0.1`.
- Tooling traps: the Bash tool mangles backslashes and apostrophes in heredocs — use the Write/Edit tools for files containing LaTeX or quotes. GateGuard denies the **first** Write/Edit of each file; send a tiny stub Write first, then the real one.
- Commit per item and push (standing rule: commit means push).
- CI is red on 5 known tests in `tests/test_pipeline.py`; do not hide or "fix" them as part of frontend work.
