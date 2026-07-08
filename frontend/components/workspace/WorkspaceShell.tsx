"use client";

import { useState, type ReactNode } from "react";
import type { JobStatus } from "@/lib/api";
import { JobStatusBadge } from "@/components/Badge";
import { ThemeToggle } from "@/components/ThemeToggle";

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

const PANE_HEIGHT = "h-[640px]";

type CenterMode = "split" | "pdf" | "markdown" | "docx";

const CENTER_MODES: { id: CenterMode; label: string }[] = [
  { id: "split", label: "PDF + Markdown" },
  { id: "pdf", label: "PDF" },
  { id: "markdown", label: "Markdown" },
  { id: "docx", label: "DOCX Preview" },
];

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
  const [centerMode, setCenterMode] = useState<CenterMode>("split");
  const [bottomOpen, setBottomOpen] = useState(false);

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
          <ThemeToggle />
        </div>
      </div>

      {/* View switcher — only meaningful in document mode, but shown
          consistently so switching back from a special view is obvious. */}
      {mode === "document" && (
        <div className="flex items-center gap-1 border-b border-border bg-surface-panel px-2 py-1.5">
          {CENTER_MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => setCenterMode(m.id)}
              className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
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

      {/* Body */}
      <div className={`flex ${PANE_HEIGHT} min-h-0`}>
        <div className="w-64 shrink-0 overflow-y-auto border-r border-border bg-surface-panel">
          {nav}
        </div>

        {mode === "special" ? (
          <div className="min-w-0 flex-1 overflow-auto bg-surface-canvas p-4">{specialView}</div>
        ) : (
          <>
            {(centerMode === "split" || centerMode === "pdf") && (
              <div
                className={`min-w-0 overflow-auto border-r border-border bg-surface-canvas ${
                  centerMode === "split" ? "flex-1" : "flex-[2]"
                }`}
              >
                {centerViews.pdf}
              </div>
            )}
            {(centerMode === "split" || centerMode === "markdown") && (
              <div
                className={`min-w-0 overflow-auto border-r border-border bg-surface-canvas ${
                  centerMode === "split" ? "flex-1" : "flex-[2]"
                }`}
              >
                {centerViews.markdown}
              </div>
            )}
            {centerMode === "docx" && (
              <div className="min-w-0 flex-[2] overflow-auto border-r border-border bg-surface-canvas p-4">
                {centerViews.docx}
              </div>
            )}
            <div className="min-w-0 flex-1 overflow-auto bg-surface-canvas">{rightRail}</div>
          </>
        )}
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
