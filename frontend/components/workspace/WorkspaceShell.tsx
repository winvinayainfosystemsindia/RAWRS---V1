"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Panel, PanelGroup, PanelResizeHandle, type ImperativePanelHandle } from "react-resizable-panels";
import { api, type JobStatus } from "@/lib/api";
import { JobStatusBadge } from "@/components/Badge";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useArrowKeyTabs } from "@/lib/hooks/useArrowKeyTabs";
import {
  IconSearch,
  IconExport,
  IconFocus,
  IconCheckCircle,
  IconWarningTriangle,
  ChevronDownIcon,
} from "@/components/icons";

interface CenterViews {
  pdf: ReactNode;
  markdown: ReactNode;
  docx: ReactNode;
}

interface WorkspaceShellProps {
  filename: string;
  status: JobStatus;
  documentVersion: number | null;
  elapsedSeconds: number;
  durationSeconds: number | null;
  nav: ReactNode;
  // "document" = the default editing surface (PDF + Markdown + Context
  // Inspector, driven by object selection). "special" = a whole-document
  // workspace (Images gallery, Page Labels, Reading Order, ...) that takes
  // over the full center+right width, same as the rest of the app's
  // dedicated editors.
  mode: "document" | "special";
  centerViews: CenterViews;
  rightRail: ReactNode;
  specialView: ReactNode;
  bottomPanel: ReactNode;
  // Global Reviewer Toolbar additions (Phase R-1.1) — all optional, all
  // caller-supplied data/callbacks so this component stays a pure
  // presentational shell (no context hooks here — see the a11y test,
  // which renders this with no PdfViewportContext/DocumentDataContext).
  currentPage?: number | null;
  readinessScore?: number | null;
  // Optional, primitive (not the full ReadinessReport type) — keeps this
  // component decoupled from DocumentDataContext's data shape, same
  // reasoning as every other prop here.
  readinessReady?: boolean;
  onOpenSearch?: () => void;
  jobId?: string;
  docxAvailable?: boolean;
  markdownAvailable?: boolean;
  reportAvailable?: boolean;
  docxStale?: boolean;
  markdownStale?: boolean;
  // Phase R-2 M2 — rendered after the toolbar row, before the center-view
  // tabs. Exists so a caller's quick-jump chips sit after the toolbar in
  // DOM/tab order (keyboard users reach Search/Export/Focus Mode without
  // tabbing through every chip first) while staying visually adjacent to
  // it. Optional, plain ReactNode slot — same pattern as `nav`/`rightRail`.
  quickNav?: ReactNode;
}

// ponytail: estimate of surrounding chrome (site header, footer, page
// padding, WorkspaceShell's own top bar + view switcher) — fills the
// viewport rather than the old fixed h-[640px]; retune if that chrome grows.
const PANE_HEIGHT = "h-[calc(100vh-15rem)] min-h-[480px]";

const RESIZE_HANDLE =
  "w-1 shrink-0 bg-border transition-colors hover:bg-accent focus-visible:bg-accent focus-visible:outline-none data-[resize-handle-state=drag]:bg-accent";

type CenterMode = "split-pdf-md" | "split-pdf-docx" | "split-md-docx" | "pdf" | "markdown" | "docx";

const CENTER_MODES: { id: CenterMode; label: string }[] = [
  { id: "split-pdf-md", label: "PDF + Markdown" },
  { id: "split-pdf-docx", label: "PDF + DOCX" },
  { id: "split-md-docx", label: "Markdown + DOCX" },
  { id: "pdf", label: "PDF" },
  { id: "markdown", label: "Markdown" },
  { id: "docx", label: "DOCX Preview" },
];
const CENTER_MODE_IDS = CENTER_MODES.map((m) => m.id);

// ponytail: every split preset reuses the same nested-PanelGroup shape,
// just with a different pair of centerViews keys — cheaper than a branch
// per preset.
const SPLIT_PAIRS: Partial<Record<CenterMode, [keyof CenterViews, keyof CenterViews]>> = {
  "split-pdf-md": ["pdf", "markdown"],
  "split-pdf-docx": ["pdf", "docx"],
  "split-md-docx": ["markdown", "docx"],
};

// Layout-preference persistence (Phase F-4.3) — same lazy-init-read +
// effect-write localStorage pattern as ThemeProvider.tsx. A reviewer's
// preferred split/focus/bottom-panel state is a screen-setup preference,
// not document data, so one global key set (not per-document) is correct.
const CENTER_MODE_KEY = "rawrs-workspace-center-mode";
const FOCUS_MODE_KEY = "rawrs-workspace-focus-mode";
const BOTTOM_OPEN_KEY = "rawrs-workspace-bottom-open";

function getInitialCenterMode(): CenterMode {
  if (typeof window === "undefined") return "split-pdf-md";
  const stored = window.localStorage.getItem(CENTER_MODE_KEY);
  return (CENTER_MODE_IDS as string[]).includes(stored ?? "") ? (stored as CenterMode) : "split-pdf-md";
}

function getInitialFlag(key: string): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(key) === "true";
}

// ponytail: native <details>/<summary> instead of a hand-rolled dropdown —
// no portal, no click-outside handler, no z-index management to get wrong.
function ExportMenu({
  jobId,
  docxAvailable,
  markdownAvailable,
  reportAvailable,
  docxStale,
  markdownStale,
}: {
  jobId: string;
  docxAvailable: boolean;
  markdownAvailable: boolean;
  reportAvailable: boolean;
  docxStale: boolean;
  markdownStale: boolean;
}) {
  return (
    <details className="relative">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium text-text-secondary transition-colors hover:bg-hover-row hover:text-text-primary">
        <IconExport className="h-3.5 w-3.5" />
        Export
      </summary>
      <div className="absolute right-0 z-10 mt-1 w-56 rounded border border-border bg-surface-panel py-1 shadow-lg">
        {docxAvailable && (
          <a
            href={api.downloadUrl(jobId, "docx")}
            download
            className="block px-3 py-1.5 text-xs text-text-primary hover:bg-hover-row"
          >
            Accessible DOCX{docxStale ? " (stale)" : ""}
          </a>
        )}
        {markdownAvailable && (
          <a
            href={api.downloadUrl(jobId, "markdown")}
            download
            className="block px-3 py-1.5 text-xs text-text-primary hover:bg-hover-row"
          >
            Accessible Markdown{markdownStale ? " (stale)" : ""}
          </a>
        )}
        {reportAvailable && (
          <a
            href={api.downloadUrl(jobId, "report")}
            download
            className="block px-3 py-1.5 text-xs text-text-primary hover:bg-hover-row"
          >
            Validation Report
          </a>
        )}
      </div>
    </details>
  );
}

export function WorkspaceShell({
  filename,
  status,
  documentVersion,
  elapsedSeconds,
  durationSeconds,
  nav,
  mode,
  centerViews,
  rightRail,
  specialView,
  bottomPanel,
  currentPage,
  readinessScore,
  readinessReady,
  onOpenSearch,
  jobId,
  docxAvailable,
  markdownAvailable,
  reportAvailable,
  docxStale,
  markdownStale,
  quickNav,
}: WorkspaceShellProps) {
  const isActive = status === "queued" || status === "processing";
  const [centerMode, setCenterMode] = useState<CenterMode>(getInitialCenterMode);
  const [bottomOpen, setBottomOpen] = useState(() => getInitialFlag(BOTTOM_OPEN_KEY));
  const [focusMode, setFocusMode] = useState(() => getInitialFlag(FOCUS_MODE_KEY));
  const navPanelRef = useRef<ImperativePanelHandle>(null);
  const railPanelRef = useRef<ImperativePanelHandle>(null);
  const splitPair = SPLIT_PAIRS[centerMode];
  // Phase F-3.2 — shared ARIA-tabs keyboard model (arrow keys move focus
  // + selection together, Home/End jump to first/last).
  const centerTabs = useArrowKeyTabs({ ids: CENTER_MODE_IDS, active: centerMode, onChange: setCenterMode });

  useEffect(() => window.localStorage.setItem(CENTER_MODE_KEY, centerMode), [centerMode]);
  useEffect(() => window.localStorage.setItem(FOCUS_MODE_KEY, String(focusMode)), [focusMode]);
  useEffect(() => window.localStorage.setItem(BOTTOM_OPEN_KEY, String(bottomOpen)), [bottomOpen]);

  // Re-apply a persisted Focus Mode on mount — react-resizable-panels'
  // autoSaveId already restores each panel's last saved size (including a
  // collapsed 0%), but calling collapse() here too is a harmless no-op if
  // it already restored collapsed, and a correct fix if it didn't.
  useEffect(() => {
    if (focusMode) {
      navPanelRef.current?.collapse();
      railPanelRef.current?.collapse();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggleFocusMode() {
    const next = !focusMode;
    setFocusMode(next);
    if (next) {
      navPanelRef.current?.collapse();
      railPanelRef.current?.collapse();
    } else {
      navPanelRef.current?.expand();
      railPanelRef.current?.expand();
    }
  }

  return (
    <div className="flex flex-col rounded border border-border bg-surface-canvas overflow-hidden">
      {/* Top bar — Phase R-2 M3: primary orientation info (filename,
          status, readiness score) grouped on the left with the filename,
          since these three answer "what is this document / how healthy is
          it" (Journey Stage 1). Everything on the right is secondary
          action/metadata (page position, export, view options) and keeps
          its original small/muted styling unchanged. */}
      <div className="flex items-center justify-between gap-4 border-b border-border bg-surface-panel px-4 py-2.5">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <span className="break-all text-sm font-semibold text-text-primary">{filename}</span>
          <JobStatusBadge status={status} />
          {readinessScore !== null && readinessScore !== undefined && (
            <span
              title="Accessibility readiness score"
              className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-sm font-semibold ${
                readinessReady ? "bg-success/10 text-success" : "bg-warning/10 text-warning"
              }`}
            >
              {readinessReady ? (
                <IconCheckCircle className="h-4 w-4 shrink-0" />
              ) : (
                <IconWarningTriangle className="h-4 w-4 shrink-0" />
              )}
              Score {Math.round(readinessScore * 100)}%
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-4">
          {/* Position/version readout — grouped tightly since both are
              passive status, not actions. */}
          {(mode === "document" && currentPage != null) || documentVersion !== null ? (
            <div className="flex items-center gap-2">
              {mode === "document" && currentPage != null && (
                <span className="font-mono text-xs text-text-secondary">Page {currentPage}</span>
              )}
              {documentVersion !== null && (
                <span className="rounded border border-border px-2 py-0.5 font-mono text-xs text-text-secondary">
                  Document v{documentVersion}
                </span>
              )}
            </div>
          ) : null}
          {/* Action cluster — grouped tightly since these are the toolbar's
              actual controls, distinct from the passive readout above. */}
          <div className="flex items-center gap-1.5">
            {onOpenSearch && (
              <button
                type="button"
                onClick={onOpenSearch}
                className="inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium text-text-secondary transition-colors hover:bg-hover-row hover:text-text-primary"
              >
                <IconSearch className="h-3.5 w-3.5" />
                Search
              </button>
            )}
            {jobId && (docxAvailable || markdownAvailable || reportAvailable) && (
              <ExportMenu
                jobId={jobId}
                docxAvailable={!!docxAvailable}
                markdownAvailable={!!markdownAvailable}
                reportAvailable={!!reportAvailable}
                docxStale={!!docxStale}
                markdownStale={!!markdownStale}
              />
            )}
            {mode === "document" && (
              <button
                type="button"
                onClick={toggleFocusMode}
                aria-pressed={focusMode}
                className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                  focusMode
                    ? "bg-accent text-accent-contrast"
                    : "text-text-secondary hover:bg-hover-row hover:text-text-primary"
                }`}
              >
                <IconFocus className="h-3.5 w-3.5" />
                Focus Mode
              </button>
            )}
            <ThemeToggle />
          </div>
        </div>
      </div>

      {/* Phase R-2 M2 — quick-jump chips render here, after the toolbar row
          above, so they come after Search/Export/Focus Mode/Theme in
          DOM/tab order. A keyboard user reaches the toolbar's action
          controls without tabbing through every chip first. */}
      {quickNav && (
        <div className="border-b border-border bg-surface-panel px-2 py-1.5">{quickNav}</div>
      )}

      {/* View switcher — only meaningful in document mode, but shown
          consistently so switching back from a special view is obvious. */}
      {mode === "document" && (
        <div
          role="tablist"
          aria-label="Center view"
          ref={centerTabs.tablistRef as React.RefObject<HTMLDivElement>}
          className="flex items-center gap-1 border-b border-border bg-surface-panel px-2 py-1.5"
        >
          {CENTER_MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              {...centerTabs.getTabProps(m.id)}
              className={`rounded px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                centerMode === m.id
                  ? "bg-accent text-accent-contrast"
                  : "text-text-secondary hover:bg-hover-row hover:text-text-primary"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      )}

      {/* Body — nav/center/rail are resizable panels (react-resizable-panels)
          so the reader can trade Outline/PDF/Markdown/Inspector width for
          whatever the current task needs; defaults approximate the
          Outline≈PDF≈Markdown 22/39/39 split with the Context Inspector
          rail folded in as a fourth, narrower pane. */}
      <div className={`flex ${PANE_HEIGHT} min-h-0`}>
        {/* Phase R-4 M2 — every Panel below carries a stable id/order.
            react-resizable-panels' own README: "id and order props ...
            aren't necessary for static layouts. When panels are
            conditionally rendered though, it's best to supply these
            values" — real guidance, not a stylistic nit. The rail Panel
            is genuinely conditional (mode === "document" only), and the
            center slot mounts one of three different Panel elements
            depending on mode/centerMode. Without ids, this autoSaveId
            group's persisted layout has no stable key to reconcile
            against when the panel set changes across a mode switch,
            which is exactly the "layout/sizing problems" scenario the
            README names. */}
        <PanelGroup autoSaveId="rawrs-workspace-shell" direction="horizontal" className="flex-1">
          <Panel
            id="nav"
            order={1}
            ref={navPanelRef}
            defaultSize={18}
            minSize={12}
            // Nav is an outline tree, not primary work surface — cap so a
            // drag can't let it swallow the center/rail panes. Exempt from
            // this while collapsed (collapsedSize={0} is a distinct state).
            maxSize={40}
            collapsible
            collapsedSize={0}
            className="overflow-y-auto border-r border-border bg-surface-panel"
          >
            {nav}
          </Panel>
          <PanelResizeHandle className={RESIZE_HANDLE} />

          {mode === "special" ? (
            // Sole content pane besides nav in this mode — no sibling to
            // protect from being swallowed, so no maxSize needed. Same
            // id/order as the other two center-slot branches below: exactly
            // one of the three is ever mounted, occupying the same logical
            // slot, so it needs the same stable identity, not three.
            <Panel id="center" order={2} minSize={30} className="overflow-auto bg-surface-canvas p-4">
              {specialView}
            </Panel>
          ) : splitPair ? (
            <Panel id="center" order={2} minSize={40} className="flex overflow-hidden">
              <PanelGroup autoSaveId="rawrs-workspace-center-split" direction="horizontal">
                <Panel
                  id="center-a"
                  order={1}
                  defaultSize={50}
                  minSize={20}
                  // Complement of the sibling's minSize=20, so neither side
                  // can be dragged past the other's usability floor.
                  maxSize={80}
                  className={`overflow-auto border-r border-border bg-surface-canvas ${
                    splitPair[0] === "docx" ? "p-4" : ""
                  }`}
                >
                  {centerViews[splitPair[0]]}
                </Panel>
                <PanelResizeHandle className={RESIZE_HANDLE} />
                <Panel
                  id="center-b"
                  order={2}
                  defaultSize={50}
                  minSize={20}
                  maxSize={80}
                  className={`overflow-auto bg-surface-canvas ${splitPair[1] === "docx" ? "p-4" : ""}`}
                >
                  {centerViews[splitPair[1]]}
                </Panel>
              </PanelGroup>
            </Panel>
          ) : (
            // No maxSize here deliberately: Focus Mode's whole point is
            // letting this pane approach 100% once nav/rail collapse to 0 —
            // a cap here would fight that, not just resize dragging.
            <Panel
              id="center"
              order={2}
              defaultSize={68}
              minSize={30}
              className={`overflow-auto bg-surface-canvas ${centerMode === "docx" ? "p-4" : ""}`}
            >
              {centerViews[centerMode as keyof CenterViews]}
            </Panel>
          )}

          {mode === "document" && (
            <>
              <PanelResizeHandle className={RESIZE_HANDLE} />
              <Panel
                id="rail"
                order={3}
                ref={railPanelRef}
                defaultSize={14}
                minSize={10}
                // Inspector tabs/detail panels don't need more than this to
                // stay usable; caps the same accidental-swallow risk as nav.
                maxSize={40}
                collapsible
                collapsedSize={0}
                className="overflow-auto border-l border-border bg-surface-canvas"
              >
                {rightRail}
              </Panel>
            </>
          )}
        </PanelGroup>
      </div>

      {/* Collapsible bottom panel */}
      <div className="flex shrink-0 flex-col border-t border-border bg-surface-panel">
        <button
          type="button"
          onClick={() => setBottomOpen((v) => !v)}
          aria-expanded={bottomOpen}
          className="flex items-center justify-between px-4 py-1 text-xs text-text-secondary hover:text-text-primary"
        >
          <span className="flex items-center gap-2">
            <ChevronDownIcon open={bottomOpen} />
            <span aria-live="polite">
              {isActive
                ? `Elapsed: ${elapsedSeconds}s`
                : durationSeconds !== null
                  ? `Completed in ${durationSeconds.toFixed(1)}s`
                  : ""}
            </span>
          </span>
          {documentVersion !== null && <span>v{documentVersion}</span>}
        </button>
        {bottomOpen && <div className="border-t border-border">{bottomPanel}</div>}
      </div>
    </div>
  );
}
