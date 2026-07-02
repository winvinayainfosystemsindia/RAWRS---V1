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
      className="flex items-center gap-0.5 border-b border-gray-200 overflow-x-auto"
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
            className={`shrink-0 px-4 py-2.5 text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 transition-colors rounded-t-sm ${
              isActive
                ? "border-b-2 border-blue-600 text-blue-700 bg-white"
                : "border-b-2 border-transparent text-gray-500 hover:text-gray-800"
            }`}
          >
            {tab.label}
          </button>
        );
      })}

      {/* Separator */}
      <div className="mx-2 h-5 w-px bg-gray-200 shrink-0" aria-hidden="true" />

      {/* Coming-soon tabs — not interactive */}
      {SOON_TABS.map((tab) => (
        <span
          key={tab.id}
          className="shrink-0 flex items-center gap-1.5 px-4 py-2.5 text-sm text-gray-300 cursor-default select-none"
          title="Coming soon"
        >
          {tab.label}
          <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-[9px] font-semibold text-gray-400 uppercase tracking-wider">
            soon
          </span>
        </span>
      ))}
    </div>
  );
}

// ─── Markdown editor tab ──────────────────────────────────────────────────────

interface MarkdownTabProps {
  generatedMarkdown: string;
  editedMarkdown: string;
  editorKey: number;
  hasUnsavedChanges: boolean;
  onEdit: (value: string) => void;
  onSave: () => void;
  onReset: () => void;
}

function MarkdownTab({
  generatedMarkdown,
  editedMarkdown,
  editorKey,
  hasUnsavedChanges,
  onEdit,
  onSave,
  onReset,
}: MarkdownTabProps) {
  return (
    <div className="flex flex-col gap-2 h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          {hasUnsavedChanges ? (
            <span className="flex items-center gap-1.5 text-xs font-medium text-amber-700">
              <span className="inline-block h-2 w-2 rounded-full bg-amber-500" aria-hidden="true" />
              Unsaved Changes
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-xs text-green-700">
              <svg className="h-3.5 w-3.5" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M2 7l3.5 3.5 6.5-7" />
              </svg>
              Up to date
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onReset}
            disabled={!hasUnsavedChanges}
            className="rounded px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            Reset to Generated
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={!hasUnsavedChanges}
            className={`rounded px-3 py-1.5 text-xs font-semibold focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 transition-colors ${
              hasUnsavedChanges
                ? "bg-blue-600 text-white hover:bg-blue-700"
                : "bg-gray-100 text-gray-400 cursor-not-allowed"
            }`}
          >
            Save
          </button>
        </div>
      </div>

      {/* Note about backend save */}
      {hasUnsavedChanges && (
        <p className="text-[11px] text-gray-400">
          Save stores your edits locally in this session. Download to persist them.{" "}
          <span className="font-mono text-gray-400">TODO: backend /api/documents/{"{id}"}/markdown PATCH endpoint</span>
        </p>
      )}

      {/* Editor — fixed height with internal scroll, matching the
          Accessible DOCX Preview's scroll affordance (DocxPreview.tsx)
          instead of growing the page with the document's length. */}
      <div style={{ height: "600px" }}>
        <MarkdownEditor
          key={editorKey}
          initialContent={generatedMarkdown}
          onChange={onEdit}
        />
      </div>
    </div>
  );
}

// ─── Raw Mathpix tab ──────────────────────────────────────────────────────────

function RawMathpixTab() {
  return (
    <div className="rounded-lg border border-violet-100 bg-white">
      <div className="border-b border-violet-100 bg-violet-50 px-4 py-3">
        <p className="text-xs font-semibold text-violet-800">Not available in Phase 1</p>
      </div>
      <div className="p-6 space-y-4">
        <p className="text-sm text-gray-700">
          The original Mathpix Markdown is not preserved by the Phase 1 pipeline. This tab will show
          the source Mathpix output for side-by-side comparison once Phase 2 input handling is implemented.
        </p>
        <div className="rounded-md border border-gray-200 bg-gray-50 px-4 py-3 font-mono text-xs text-gray-500 space-y-1">
          <p className="text-gray-400 font-semibold">TODO — Phase 2</p>
          <p>Store Mathpix markdown at job creation time.</p>
          <p>Expose via <span className="text-violet-600">GET /api/documents/{"{id}"}/source-markdown</span></p>
          <p>Render read-only here using the same editor (readOnly=true).</p>
          <p>Add diff highlighting if the two markdown streams differ (unified diff view).</p>
        </div>
        <p className="text-xs text-gray-400">
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
  editedMarkdown: string;
  hasUnsavedChanges: boolean;
}

function DownloadControls({ job, editedMarkdown, hasUnsavedChanges }: DownloadControlsProps) {
  function downloadEditedMarkdown() {
    const blob = new Blob([editedMarkdown], { type: "text/markdown; charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = job.filename.replace(/\.[^.]+$/, ".md");
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  const buttons: {
    label: string;
    onClick?: () => void;
    href?: string;
    available: boolean;
    note?: string;
  }[] = [
    {
      label: "Accessible DOCX",
      href: job.docx_available ? api.downloadUrl(job.job_id, "docx") : undefined,
      available: job.docx_available,
    },
    {
      label: "Accessible Markdown",
      onClick: downloadEditedMarkdown,
      available: job.markdown_available,
      note: hasUnsavedChanges ? "includes your edits" : undefined,
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
    <div className="border-t border-gray-100 pt-4 mt-4">
      {/* Save status */}
      <div className="flex items-center gap-2 mb-3">
        {hasUnsavedChanges ? (
          <span className="flex items-center gap-1.5 text-xs text-amber-700">
            <span className="inline-block h-2 w-2 rounded-full bg-amber-500" aria-hidden="true" />
            Unsaved changes — Markdown download will include your edits
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-xs text-gray-500">
            <svg className="h-3.5 w-3.5 text-green-600" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M2 7l3.5 3.5 6.5-7" />
            </svg>
            No unsaved changes
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {buttons.map((btn) =>
          btn.available ? (
            btn.href ? (
              <a
                key={btn.label}
                href={btn.href}
                download
                className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 py-2 text-xs font-semibold text-gray-800 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                <svg className="h-3.5 w-3.5 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
                </svg>
                {btn.label}
                {btn.note && <span className="text-amber-600 font-normal">({btn.note})</span>}
              </a>
            ) : (
              <button
                key={btn.label}
                type="button"
                onClick={btn.onClick}
                className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 py-2 text-xs font-semibold text-gray-800 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                <svg className="h-3.5 w-3.5 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
                </svg>
                {btn.label}
                {btn.note && <span className="text-amber-600 font-normal">({btn.note})</span>}
              </button>
            )
          ) : (
            <span
              key={btn.label}
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-100 bg-gray-50 px-3 py-2 text-xs text-gray-400 cursor-default"
            >
              {btn.label}
              <span className="text-gray-300">—</span>
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
  const [editedMarkdown, setEditedMarkdown] = useState(generatedMarkdown);
  const [savedMarkdown, setSavedMarkdown] = useState(generatedMarkdown);
  // editorKey change forces MarkdownEditor to remount with fresh content.
  const [editorKey, setEditorKey] = useState(0);

  const hasUnsavedChanges = editedMarkdown !== savedMarkdown;

  function handleSave() {
    setSavedMarkdown(editedMarkdown);
  }

  function handleReset() {
    setEditedMarkdown(generatedMarkdown);
    setSavedMarkdown(generatedMarkdown);
    setEditorKey((k) => k + 1);
  }

  return (
    <section aria-labelledby="workspace-heading" className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      {/* Section header */}
      <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
        <h2 id="workspace-heading" className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
          Output Workspace
        </h2>
        {!job.markdown_available && !job.docx_available && (
          <span className="text-xs text-gray-400">No outputs generated</span>
        )}
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
              editedMarkdown={editedMarkdown}
              editorKey={editorKey}
              hasUnsavedChanges={hasUnsavedChanges}
              onEdit={setEditedMarkdown}
              onSave={handleSave}
              onReset={handleReset}
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
            <DocxPreview jobId={job.job_id} available={job.docx_available} />
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
        <DownloadControls
          job={job}
          editedMarkdown={editedMarkdown}
          hasUnsavedChanges={hasUnsavedChanges}
        />
      </div>
    </section>
  );
}
