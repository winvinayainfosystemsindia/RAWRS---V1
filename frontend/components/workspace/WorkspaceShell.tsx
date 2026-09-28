"use client";

import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { Panel, PanelGroup, PanelResizeHandle, type ImperativePanelHandle } from "react-resizable-panels";
import { api, type JobStatus } from "@/lib/api";
import type { ReadinessState } from "@/lib/readinessState";
import { JobStatusBadge } from "@/components/Badge";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useArrowKeyTabs } from "@/lib/hooks/useArrowKeyTabs";
import {
  IconSearch,
  IconExport,
  IconFocus,
  IconFullscreen,
  IconPanelBottom,
  IconPanelSide,
  IconCheckCircle,
  IconWarningTriangle,
} from "@/components/icons";

// The document workspace as an application window, laid out like VS Code:
//
//   ┌ title bar: file · verdict · view switcher · actions ────────────┐
//   │ activity │ outline │        editor panes         │ review rail  │
//   │   bar    │ sidebar │  (PDF / Markdown / DOCX)    │              │
//   │          │         ├─────── bottom panel ────────┤              │
//   └ status bar: verdict · pending · page · version · timing ────────┘
//
// It fills the whole viewport (no site header, no centred column), and
// Fullscreen hands the window to the browser's real fullscreen mode. Every
// piece the old shell had is still here - only where it lives changed.

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
  // "document" = the editing surface (PDF + Markdown + review rail, driven by
  // object selection). "special" = a whole-document workspace (Images,
  // Reading Order, ...) that takes over the editor area.
  mode: "document" | "special";
  centerViews: CenterViews;
  rightRail: ReactNode;
  specialView: ReactNode;
  bottomPanel: ReactNode;
  // Pure presentational shell: everything below is caller-supplied data or
  // callbacks, never context (the a11y test renders it with no providers).
  activityBar?: ReactNode;
  currentPage?: number | null;
  readiness?: ReadinessState | null;
  pendingCount?: number;
  onOpenSearch?: () => void;
  jobId?: string;
  docxAvailable?: boolean;
  markdownAvailable?: boolean;
  reportAvailable?: boolean;
  docxStale?: boolean;
  markdownStale?: boolean;
}

const RESIZE_HANDLE =
  "shrink-0 bg-border transition-colors hover:bg-accent focus-visible:bg-accent focus-visible:outline-none data-[resize-handle-state=drag]:bg-accent";
const RESIZE_HANDLE_V = `w-px ${RESIZE_HANDLE} data-[resize-handle-state=hover]:w-1`;
const RESIZE_HANDLE_H = `h-px ${RESIZE_HANDLE} data-[resize-handle-state=hover]:h-1`;

type CenterMode = "all" | "split-pdf-md" | "split-pdf-docx" | "split-md-docx" | "pdf" | "markdown" | "docx";

const CENTER_MODES: { id: CenterMode; label: string }[] = [
  // Source, the text you edit, and the Word file it becomes - side by side.
  { id: "all", label: "PDF + MD + DOCX" },
  { id: "split-pdf-md", label: "PDF + Markdown" },
  { id: "split-pdf-docx", label: "PDF + DOCX" },
  { id: "split-md-docx", label: "Markdown + DOCX" },
  { id: "pdf", label: "PDF" },
  { id: "markdown", label: "Markdown" },
  { id: "docx", label: "DOCX" },
];
const CENTER_MODE_IDS = CENTER_MODES.map((m) => m.id);

// Every split preset reuses the same nested-PanelGroup shape, just with a
// different pair of centerViews keys.
const SPLIT_PAIRS: Partial<Record<CenterMode, [keyof CenterViews, keyof CenterViews]>> = {
  "split-pdf-md": ["pdf", "markdown"],
  "split-pdf-docx": ["pdf", "docx"],
  "split-md-docx": ["markdown", "docx"],
};

// Layout preferences are a screen setup, not document data: one global key
// set, read lazily, written in effects (same pattern as ThemeProvider).
const CENTER_MODE_KEY = "rawrs-workspace-center-mode";
const FOCUS_MODE_KEY = "rawrs-workspace-focus-mode";
const BOTTOM_OPEN_KEY = "rawrs-workspace-bottom-open";

function readStored<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  if (typeof window === "undefined") return fallback;
  const stored = window.localStorage.getItem(key);
  return (allowed as readonly string[]).includes(stored ?? "") ? (stored as T) : fallback;
}

function readFlag(key: string): boolean {
  return typeof window !== "undefined" && window.localStorage.getItem(key) === "true";
}

const READINESS_TONE: Record<ReadinessState["label"], string> = {
  "Export Ready": "bg-success/15 text-success",
  "Needs Review": "bg-warning/15 text-warning",
  Blocked: "bg-danger/15 text-danger",
  Validating: "bg-accent/15 text-accent",
  "Validation unavailable": "bg-surface-canvas text-text-secondary border border-border",
};

const TOOL_BUTTON =
  "inline-flex h-7 items-center gap-1.5 rounded px-2 text-xs font-medium text-text-secondary transition-colors hover:bg-hover-row hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";
const TOOL_BUTTON_ON = "bg-accent/15 text-text-primary";

// Native <details>/<summary>: no portal, no click-outside handler.
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
      <summary className={`${TOOL_BUTTON} cursor-pointer list-none`}>
        <IconExport className="h-3.5 w-3.5" />
        Export
      </summary>
      <div className="absolute right-0 z-30 mt-1 w-56 rounded border border-border bg-surface-panel py-1 shadow-lg">
        {docxAvailable && (
          <a href={api.downloadUrl(jobId, "docx")} download className="block px-3 py-1.5 text-xs text-text-primary hover:bg-hover-row">
            Accessible DOCX{docxStale ? " (stale)" : ""}
          </a>
        )}
        {markdownAvailable && (
          <a href={api.downloadUrl(jobId, "markdown")} download className="block px-3 py-1.5 text-xs text-text-primary hover:bg-hover-row">
            Accessible Markdown{markdownStale ? " (stale)" : ""}
          </a>
        )}
        {reportAvailable && (
          <a href={api.downloadUrl(jobId, "report")} download className="block px-3 py-1.5 text-xs text-text-primary hover:bg-hover-row">
            Validation Report
          </a>
        )}
      </div>
    </details>
  );
}

// The browser's real fullscreen, on the workspace root - so the OS taskbar and
// browser toolbars go too. Esc (the browser's own binding) leaves it.
function useFullscreen() {
  const rootRef = useRef<HTMLDivElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const sync = () => setIsFullscreen(document.fullscreenElement === rootRef.current);
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);

  function toggle() {
    if (document.fullscreenElement) {
      void document.exitFullscreen();
    } else {
      void rootRef.current?.requestFullscreen?.().catch(() => undefined);
    }
  }

  return { rootRef, isFullscreen, toggle };
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
  activityBar,
  currentPage,
  readiness,
  pendingCount,
  onOpenSearch,
  jobId,
  docxAvailable,
  markdownAvailable,
  reportAvailable,
  docxStale,
  markdownStale,
}: WorkspaceShellProps) {
  const isActive = status === "queued" || status === "processing";
  const [centerMode, setCenterMode] = useState<CenterMode>(() =>
    readStored(CENTER_MODE_KEY, CENTER_MODE_IDS, "all")
  );
  const [bottomOpen, setBottomOpen] = useState(() => readFlag(BOTTOM_OPEN_KEY));
  const [focusMode, setFocusMode] = useState(() => readFlag(FOCUS_MODE_KEY));
  const [navOpen, setNavOpen] = useState(true);
  const [railOpen, setRailOpen] = useState(true);
  const navPanelRef = useRef<ImperativePanelHandle>(null);
  const railPanelRef = useRef<ImperativePanelHandle>(null);
  const bottomPanelRef = useRef<ImperativePanelHandle>(null);
  const { rootRef, isFullscreen, toggle: toggleFullscreen } = useFullscreen();
  const splitPair = SPLIT_PAIRS[centerMode];
  const { tablistRef: centerTablistRef, getTabProps: getCenterTabProps } = useArrowKeyTabs({ ids: CENTER_MODE_IDS, active: centerMode, onChange: setCenterMode });

  useEffect(() => window.localStorage.setItem(CENTER_MODE_KEY, centerMode), [centerMode]);
  useEffect(() => window.localStorage.setItem(FOCUS_MODE_KEY, String(focusMode)), [focusMode]);
  useEffect(() => window.localStorage.setItem(BOTTOM_OPEN_KEY, String(bottomOpen)), [bottomOpen]);

  // Re-apply a persisted Focus Mode on mount (autoSaveId restores sizes too;
  // collapse() here is a no-op if it already did).
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
    for (const panel of [navPanelRef.current, railPanelRef.current]) {
      if (next) panel?.collapse();
      else panel?.expand();
    }
  }

  function togglePanel(ref: React.RefObject<ImperativePanelHandle | null>) {
    const panel = ref.current;
    if (!panel) return;
    if (panel.isCollapsed()) panel.expand();
    else panel.collapse();
  }

  const timing = isActive
    ? `Elapsed ${elapsedSeconds}s`
    : durationSeconds !== null
      ? `Processed in ${durationSeconds.toFixed(1)}s`
      : "";

  const editor =
    mode === "special" ? (
      // One shared scroll container for every whole-document workspace.
      <div className="h-full overflow-y-auto p-5">{specialView}</div>
    ) : centerMode === "all" ? (
      <PanelGroup autoSaveId="rawrs-workspace-center-triple" direction="horizontal">
        {(["pdf", "markdown", "docx"] as const).map((view, index) => (
          <Fragment key={view}>
            {index > 0 && <PanelResizeHandle className={RESIZE_HANDLE_V} />}
            <Panel id={`center-${view}`} order={index + 1} defaultSize={100 / 3} minSize={15} className="overflow-auto bg-surface-canvas">
              {centerViews[view]}
            </Panel>
          </Fragment>
        ))}
      </PanelGroup>
    ) : splitPair ? (
      <PanelGroup autoSaveId="rawrs-workspace-center-split" direction="horizontal">
        <Panel id="center-a" order={1} defaultSize={50} minSize={20} maxSize={80}
          className="overflow-auto bg-surface-canvas">
          {centerViews[splitPair[0]]}
        </Panel>
        <PanelResizeHandle className={RESIZE_HANDLE_V} />
        <Panel id="center-b" order={2} defaultSize={50} minSize={20} maxSize={80}
          className="overflow-auto bg-surface-canvas">
          {centerViews[splitPair[1]]}
        </Panel>
      </PanelGroup>
    ) : (
      <div className="h-full overflow-auto bg-surface-canvas">
        {centerViews[centerMode as keyof CenterViews]}
      </div>
    );

  return (
    <div ref={rootRef} className="flex h-full min-h-[480px] w-full flex-col overflow-hidden bg-surface-canvas text-text-primary">
      {/* ── Title bar ─────────────────────────────────────────────────── */}
      <header className="flex h-11 shrink-0 items-center gap-3 border-b border-border bg-surface-panel pl-3 pr-2">
        <Link
          href="/"
          title="Back to documents"
          className="rounded text-sm font-bold tracking-wide text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          RAWRS
        </Link>
        <span className="h-4 w-px bg-border" aria-hidden="true" />
        <div className="flex min-w-0 items-center gap-2">
          <span title={filename} className="min-w-[8rem] truncate text-sm font-medium text-text-primary">
            {filename}
          </span>
          {status === "complete" && readiness ? (
            <span
              title={readiness.detail}
              className={`inline-flex shrink-0 items-center gap-1 rounded px-2 py-0.5 text-xs font-semibold ${READINESS_TONE[readiness.label]}`}
            >
              {readiness.label === "Export Ready" && <IconCheckCircle className="h-3.5 w-3.5" />}
              {(readiness.label === "Blocked" || readiness.label === "Needs Review") && (
                <IconWarningTriangle className="h-3.5 w-3.5" />
              )}
              {readiness.label}
              <span className="sr-only">. {readiness.detail}</span>
            </span>
          ) : (
            <JobStatusBadge status={status} />
          )}
        </div>

        {/* View switcher - the editor's layouts, centred like VS Code's layout controls. */}
        {mode === "document" ? (
          <div
            role="tablist"
            aria-label="Editor layout"
            ref={centerTablistRef as React.RefObject<HTMLDivElement>}
            className="mx-auto flex shrink-0 items-center gap-0.5 rounded-md border border-border bg-surface-canvas p-0.5"
          >
            {CENTER_MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                {...getCenterTabProps(m.id)}
                className={`rounded px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                  centerMode === m.id
                    ? "bg-accent text-accent-contrast shadow-sm"
                    : "text-text-secondary hover:bg-hover-row hover:text-text-primary"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        ) : (
          <div className="mx-auto" />
        )}

        <div className="flex shrink-0 items-center gap-0.5">
          {onOpenSearch && (
            <button type="button" onClick={onOpenSearch} aria-label="Search" title="Search" className={TOOL_BUTTON}>
              <IconSearch className="h-3.5 w-3.5" />
              <span className="hidden 2xl:inline">Search</span>
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
          <span className="mx-1 h-4 w-px bg-border" aria-hidden="true" />
          <button
            type="button"
            onClick={() => togglePanel(navPanelRef)}
            aria-pressed={navOpen}
            aria-label="Toggle outline sidebar"
            title="Toggle outline sidebar"
            className={`${TOOL_BUTTON} ${navOpen ? "" : "opacity-60"}`}
          >
            <IconPanelSide className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => togglePanel(bottomPanelRef)}
            aria-pressed={bottomOpen}
            aria-label="Toggle validation, export and console panel"
            title="Toggle validation, export and console panel"
            className={`${TOOL_BUTTON} ${bottomOpen ? "" : "opacity-60"}`}
          >
            <IconPanelBottom className="h-4 w-4" />
          </button>
          {mode === "document" && (
            <button
              type="button"
              onClick={() => togglePanel(railPanelRef)}
              aria-pressed={railOpen}
              aria-label="Toggle review rail"
              title="Toggle review rail"
              className={`${TOOL_BUTTON} ${railOpen ? "" : "opacity-60"}`}
            >
              <IconPanelSide right className="h-4 w-4" />
            </button>
          )}
          <span className="mx-1 h-4 w-px bg-border" aria-hidden="true" />
          {mode === "document" && (
            <button
              type="button"
              onClick={toggleFocusMode}
              aria-pressed={focusMode}
              aria-label="Focus mode"
              title="Focus mode: hide the outline and review rail"
              className={`${TOOL_BUTTON} ${focusMode ? TOOL_BUTTON_ON : ""}`}
            >
              <IconFocus className="h-3.5 w-3.5" />
              <span className="hidden 2xl:inline">Focus</span>
            </button>
          )}
          <button
            type="button"
            onClick={toggleFullscreen}
            aria-pressed={isFullscreen}
            aria-label={isFullscreen ? "Exit full screen" : "Full screen"}
            title={isFullscreen ? "Exit full screen (Esc)" : "Full screen"}
            className={`${TOOL_BUTTON} ${isFullscreen ? TOOL_BUTTON_ON : ""}`}
          >
            <IconFullscreen exit={isFullscreen} className="h-3.5 w-3.5" />
            <span className="hidden 2xl:inline">{isFullscreen ? "Exit full screen" : "Full screen"}</span>
          </button>
          <ThemeToggle />
        </div>
      </header>

      {/* ── Body ─────────────────────────────────────────────────────── */}
      <div className="flex min-h-0 flex-1">
        {activityBar}
        <PanelGroup autoSaveId="rawrs-workspace-shell-v3" direction="horizontal" className="min-w-0 flex-1">
          <Panel
            id="nav"
            order={1}
            ref={navPanelRef}
            defaultSize={16}
            minSize={10}
            maxSize={35}
            collapsible
            collapsedSize={0}
            onCollapse={() => setNavOpen(false)}
            onExpand={() => setNavOpen(true)}
            className="overflow-y-auto bg-surface-panel"
          >
            {nav}
          </Panel>
          <PanelResizeHandle className={RESIZE_HANDLE_V} />

          <Panel id="main" order={2} minSize={30} className="min-w-0">
            <PanelGroup autoSaveId="rawrs-workspace-editor-v1" direction="vertical">
              <Panel id="editor" order={1} minSize={30} className="min-h-0 bg-surface-canvas">
                {editor}
              </Panel>
              <PanelResizeHandle className={RESIZE_HANDLE_H} />
              <Panel
                id="bottom"
                order={2}
                ref={bottomPanelRef}
                defaultSize={bottomOpen ? 28 : 0}
                minSize={12}
                maxSize={60}
                collapsible
                collapsedSize={0}
                onCollapse={() => setBottomOpen(false)}
                onExpand={() => setBottomOpen(true)}
                className="overflow-y-auto bg-surface-panel"
              >
                {bottomOpen && bottomPanel}
              </Panel>
            </PanelGroup>
          </Panel>

          {mode === "document" && (
            <>
              <PanelResizeHandle className={RESIZE_HANDLE_V} />
              <Panel
                id="rail"
                order={3}
                ref={railPanelRef}
                defaultSize={26}
                minSize={16}
                maxSize={45}
                collapsible
                collapsedSize={0}
                onCollapse={() => setRailOpen(false)}
                onExpand={() => setRailOpen(true)}
                className="overflow-auto bg-surface-canvas"
              >
                {rightRail}
              </Panel>
            </>
          )}
        </PanelGroup>
      </div>

      {/* ── Status bar ───────────────────────────────────────────────── */}
      <footer
        aria-label="Status"
        className="flex h-7 shrink-0 items-center gap-4 border-t border-border bg-surface-panel px-3 font-mono text-[11px] text-text-secondary"
      >
        <span aria-live="polite" className="flex items-center gap-4">
          {status === "complete" && readiness && (
            <span className={`rounded px-1.5 font-sans font-semibold ${READINESS_TONE[readiness.label]}`}>
              {readiness.label}
              {readiness.score != null && ` · ${Math.round(readiness.score * 100)}%`}
            </span>
          )}
          {pendingCount != null && pendingCount > 0 && <span>{pendingCount} to review</span>}
        </span>
        <span className="ml-auto flex items-center gap-4">
          {mode === "document" && currentPage != null && <span>Page {currentPage}</span>}
          {documentVersion !== null && <span>v{documentVersion}</span>}
          {timing && <span>{timing}</span>}
        </span>
      </footer>
    </div>
  );
}
