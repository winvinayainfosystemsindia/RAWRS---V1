"use client";

import { useState } from "react";
import { api, type JobSummary } from "@/lib/api";
import { MarkdownEditor } from "@/components/MarkdownEditor";
import { DocxPreview } from "@/components/DocxPreview";

// ─── Tab definitions ──────────────────────────────────────────────────────────

type TabId = "markdown" | "docx" | "raw";
type SoonId = "diff" | "review" | "ai";

const ACTIVE_TABS: { id: TabId; label: string }[] = [
  { id: "markdown", label: "Accessible Markdown" },
  { id: "docx",     label: "Accessible DOCX Preview" },
  { id: "raw",      label: "Raw Mathpix Markdown" },
];

const SOON_TABS: { id: SoonId; label: string }[] = [
  { id: "diff",   label: "Accessibility Diff" },
  { id: "review", label: "Review Queue" },
  { id: "ai",     label: "AI Suggestions" },
];

// ─── Tab bar ──────────────────────────────────────────────────────────────────

function WorkspaceTabBar({
  active,
  onSelect,
}: {
  active: TabId;
  onSelect: (id: TabId) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="Output workspace"
      className="flex items-center gap-0.5 border-b border-border overflow-x-auto"
    >
      {/* Active tabs */}
      {ACTIVE_TABS.map((tab) => {
        const isActive = tab.id === active;
        return (
          <button
            key={tab.id}
            role="tab"
            id={`ws-tab-${tab.id}`}
            aria-selected={isActive}
            aria-controls={`ws-panel-${tab.id}`}
            onClick={() => onSelect(tab.id)}
            className={`shrink-0 px-4 py-2.5 text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-accent transition-colors rounded-t-sm ${
              isActive
                ? "border-b-2 border-accent text-accent bg-surface-canvas"
                : "border-b-2 border-transparent text-text-secondary hover:text-text-primary"
            }`}
          >
            {tab.label}
          </button>
        );
      })}

      {/* Separator */}
      <div className="mx-2 h-5 w-px bg-border shrink-0" aria-hidden="true" />

      {/* Coming-soon tabs — not interactive */}
      {SOON_TABS.map((tab) => (
        <span
          key={tab.id}
          className="shrink-0 flex items-center gap-1.5 px-4 py-2.5 text-sm text-text-secondary/50 cursor-default select-none"
          title="Coming soon"
        >
          {tab.label}
          <span className="rounded-full bg-surface-elevated px-1.5 py-0.5 text-[9px] font-semibold text-text-secondary/70 uppercase tracking-wider">
            soon
          </span>
        </span>
      ))}
    </div>
  );
}

// ─── Version staleness note ───────────────────────────────────────────────────

function GeneratedAtVersionNote({
  generatedAtVersion,
  currentVersion,
}: {
  generatedAtVersion: number | null;
  currentVersion: number | null;
}) {
  if (generatedAtVersion === null || currentVersion === null) return null;

  const isStale = generatedAtVersion !== currentVersion;

  return (
    <p className={`text-xs ${isStale ? "text-warning" : "text-text-secondary"}`}>
      Generated from Document v{generatedAtVersion}
      {isStale && ` — Document is now v${currentVersion}. Re-run export to include the latest reviewer changes.`}
    </p>
  );
}

// ─── Markdown tab — read-only projection of the generated output ─────────────
// Editable markdown was removed: edits only lasted the browser session and
// were never persisted server-side. Exports are read-only projections of the
// canonical Document; authoring corrections happens through the Corrections
// workflow, not by hand-editing a generated artifact.

interface MarkdownTabProps {
  generatedMarkdown: string;
  generatedAtVersion: number | null;
  currentVersion: number | null;
}

function MarkdownTab({ generatedMarkdown, generatedAtVersion, currentVersion }: MarkdownTabProps) {
  return (
    <div className="flex flex-col gap-2 h-full">
      <GeneratedAtVersionNote generatedAtVersion={generatedAtVersion} currentVersion={currentVersion} />
      <div style={{ height: "600px" }}>
        <MarkdownEditor initialContent={generatedMarkdown} readOnly />
      </div>
    </div>
  );
}

// ─── Raw Mathpix tab ──────────────────────────────────────────────────────────

function RawMathpixTab() {
  return (
    <div className="rounded-lg border border-accent/20 bg-surface-panel">
      <div className="border-b border-accent/20 bg-accent/10 px-4 py-3">
        <p className="text-xs font-semibold text-accent">Not available in Phase 1</p>
      </div>
      <div className="p-6 space-y-4">
        <p className="text-sm text-text-primary">
          The original Mathpix Markdown is not preserved by the Phase 1 pipeline. This tab will show
          the source Mathpix output for side-by-side comparison once Phase 2 input handling is implemented.
        </p>
        <div className="rounded-md border border-border bg-surface-canvas px-4 py-3 font-mono text-xs text-text-secondary space-y-1">
          <p className="text-text-secondary/70 font-semibold">TODO — Phase 2</p>
          <p>Store Mathpix markdown at job creation time.</p>
          <p>Expose via <span className="text-accent">GET /api/documents/{"{id}"}/source-markdown</span></p>
          <p>Render read-only here using the same editor (readOnly=true).</p>
          <p>Add diff highlighting if the two markdown streams differ (unified diff view).</p>
        </div>
        <p className="text-xs text-text-secondary/70">
          Side-by-side diff is deferred rather than implemented poorly.
          A diff library will be evaluated when Phase 2 input is available.
        </p>
      </div>
    </div>
  );
}

// ─── Download controls ────────────────────────────────────────────────────────

interface DownloadControlsProps {
  job: JobSummary;
}

function DownloadControls({ job }: DownloadControlsProps) {
  const buttons: {
    label: string;
    href?: string;
    available: boolean;
    note?: string;
  }[] = [
    {
      label: "Accessible DOCX",
      href: job.docx_available ? api.downloadUrl(job.job_id, "docx") : undefined,
      available: job.docx_available,
      note: job.docx_generated_at_version !== null && job.docx_generated_at_version !== job.document_version
        ? "stale"
        : undefined,
    },
    {
      label: "Accessible Markdown",
      href: job.markdown_available ? api.downloadUrl(job.job_id, "markdown") : undefined,
      available: job.markdown_available,
      note: job.markdown_generated_at_version !== null && job.markdown_generated_at_version !== job.document_version
        ? "stale"
        : undefined,
    },
    {
      label: "Accessibility Report",
      available: false,
    },
    {
      label: "Validation Report",
      href: job.report_available ? api.downloadUrl(job.job_id, "report") : undefined,
      available: job.report_available,
    },
  ];

  return (
    <div className="border-t border-border pt-4 mt-4">
      <div className="flex flex-wrap gap-2">
        {buttons.map((btn) =>
          btn.available ? (
            <a
              key={btn.label}
              href={btn.href}
              download
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface-canvas px-3 py-2 text-xs font-semibold text-text-primary hover:bg-hover-row focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              <svg className="h-3.5 w-3.5 text-text-secondary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
              </svg>
              {btn.label}
              {btn.note && <span className="text-warning font-normal">({btn.note} — Document v{job.document_version})</span>}
            </a>
          ) : (
            <span
              key={btn.label}
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface-panel px-3 py-2 text-xs text-text-secondary/60 cursor-default"
            >
              {btn.label}
              <span className="text-text-secondary/40">—</span>
              <span className="italic">Not available</span>
            </span>
          )
        )}
      </div>
    </div>
  );
}

// ─── Composed workspace ───────────────────────────────────────────────────────

interface OutputWorkspaceProps {
  job: JobSummary;
  generatedMarkdown: string;
}

export function OutputWorkspace({ job, generatedMarkdown }: OutputWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<TabId>("markdown");

  return (
    <section aria-labelledby="workspace-heading" className="rounded-xl border border-border bg-surface-panel overflow-hidden">
      {/* Section header */}
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <h2 id="workspace-heading" className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          Output Workspace
        </h2>
        <div className="flex items-center gap-3">
          {job.document_version !== null && (
            <span className="rounded border border-border px-2 py-0.5 font-mono text-xs text-text-secondary">
              Document v{job.document_version}
            </span>
          )}
          {!job.markdown_available && !job.docx_available && (
            <span className="text-xs text-text-secondary/70">No outputs generated</span>
          )}
        </div>
      </div>

      {/* Tab bar */}
      <div className="px-2 pt-1">
        <WorkspaceTabBar active={activeTab} onSelect={setActiveTab} />
      </div>

      {/* Tab panels */}
      <div className="p-5">
        <div
          role="tabpanel"
          id="ws-panel-markdown"
          aria-labelledby="ws-tab-markdown"
          hidden={activeTab !== "markdown"}
        >
          {activeTab === "markdown" && (
            <MarkdownTab
              generatedMarkdown={generatedMarkdown}
              generatedAtVersion={job.markdown_generated_at_version}
              currentVersion={job.document_version}
            />
          )}
        </div>

        <div
          role="tabpanel"
          id="ws-panel-docx"
          aria-labelledby="ws-tab-docx"
          hidden={activeTab !== "docx"}
        >
          {activeTab === "docx" && (
            <div className="space-y-2">
              <GeneratedAtVersionNote
                generatedAtVersion={job.docx_generated_at_version}
                currentVersion={job.document_version}
              />
              <DocxPreview jobId={job.job_id} available={job.docx_available} />
            </div>
          )}
        </div>

        <div
          role="tabpanel"
          id="ws-panel-raw"
          aria-labelledby="ws-tab-raw"
          hidden={activeTab !== "raw"}
        >
          {activeTab === "raw" && <RawMathpixTab />}
        </div>

        {/* Downloads always visible at the bottom */}
        <DownloadControls job={job} />
      </div>
    </section>
  );
}
