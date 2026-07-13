"use client";

import { useRef, useState, type ReactNode } from "react";
import { Panel, PanelGroup, PanelResizeHandle, type ImperativePanelHandle } from "react-resizable-panels";
import type { JobStatus } from "@/lib/api";
import { JobStatusBadge } from "@/components/Badge";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useArrowKeyTabs } from "@/lib/hooks/useArrowKeyTabs";

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
}: WorkspaceShellProps) {
  const isActive = status === "queued" || status === "processing";
  const [centerMode, setCenterMode] = useState<CenterMode>("split-pdf-md");
  const [bottomOpen, setBottomOpen] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  const navPanelRef = useRef<ImperativePanelHandle>(null);
  const railPanelRef = useRef<ImperativePanelHandle>(null);
  const splitPair = SPLIT_PAIRS[centerMode];
  // Phase F-3.2 — shared ARIA-tabs keyboard model (arrow keys move focus
  // + selection together, Home/End jump to first/last).
  const centerTabs = useArrowKeyTabs({ ids: CENTER_MODE_IDS, active: centerMode, onChange: setCenterMode });

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
      {/* Top bar */}
      <div className="flex items-center justify-between gap-4 border-b border-border bg-surface-panel px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-3">
          <span className="break-all text-sm font-semibold text-text-primary">{filename}</span>
          <JobStatusBadge status={status} />
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {documentVersion !== null && (
            <span className="rounded border border-border px-2 py-0.5 font-mono text-xs text-text-secondary">
              Document v{documentVersion}
            </span>
          )}
          {mode === "document" && (
            <button
              type="button"
              onClick={toggleFocusMode}
              aria-pressed={focusMode}
              className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                focusMode
                  ? "bg-accent text-accent-contrast"
                  : "text-text-secondary hover:bg-hover-row hover:text-text-primary"
              }`}
            >
              Focus Mode
            </button>
          )}
          <ThemeToggle />
        </div>
      </div>

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
        <PanelGroup direction="horizontal" className="flex-1">
          <Panel
            ref={navPanelRef}
            defaultSize={18}
            minSize={12}
            collapsible
            collapsedSize={0}
            className="overflow-y-auto border-r border-border bg-surface-panel"
          >
            {nav}
          </Panel>
          <PanelResizeHandle className={RESIZE_HANDLE} />

          {mode === "special" ? (
            <Panel minSize={30} className="overflow-auto bg-surface-canvas p-4">
              {specialView}
            </Panel>
          ) : splitPair ? (
            <Panel minSize={40} className="flex overflow-hidden">
              <PanelGroup direction="horizontal">
                <Panel
                  defaultSize={50}
                  minSize={20}
                  className={`overflow-auto border-r border-border bg-surface-canvas ${
                    splitPair[0] === "docx" ? "p-4" : ""
                  }`}
                >
                  {centerViews[splitPair[0]]}
                </Panel>
                <PanelResizeHandle className={RESIZE_HANDLE} />
                <Panel
                  defaultSize={50}
                  minSize={20}
                  className={`overflow-auto bg-surface-canvas ${splitPair[1] === "docx" ? "p-4" : ""}`}
                >
                  {centerViews[splitPair[1]]}
                </Panel>
              </PanelGroup>
            </Panel>
          ) : (
            <Panel
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
                ref={railPanelRef}
                defaultSize={14}
                minSize={10}
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
          className="flex items-center justify-between px-4 py-1 text-xs text-text-secondary hover:text-text-primary"
        >
          <span className="flex items-center gap-2">
            <svg
              className={`h-3 w-3 transition-transform ${bottomOpen ? "rotate-180" : ""}`}
              viewBox="0 0 12 12"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M2.5 4.5 6 8l3.5-3.5" />
            </svg>
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
