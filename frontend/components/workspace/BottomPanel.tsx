"use client";

import { useState } from "react";
import type { JobSummary, ValidationIssue } from "@/lib/api";

type BottomTab = "validation" | "export" | "console";

export function BottomPanel({ job, issues }: { job: JobSummary; issues: ValidationIssue[] }) {
  const [tab, setTab] = useState<BottomTab>("validation");
  const errorCount = issues.filter((i) => i.severity === "error").length;
  const warningCount = issues.filter((i) => i.severity === "warning").length;

  const markdownStale =
    job.markdown_generated_at_version !== null && job.markdown_generated_at_version !== job.document_version;
  const docxStale =
    job.docx_generated_at_version !== null && job.docx_generated_at_version !== job.document_version;

  return (
    <div className="flex h-40 flex-col">
      <div className="flex items-center gap-1 border-b border-border px-2 py-1">
        {([
          ["validation", "Validation"],
          ["export", "Export"],
          ["console", "Console"],
        ] as [BottomTab, string][]).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`rounded px-2 py-1 text-xs font-medium ${
              tab === id ? "bg-accent text-accent-contrast" : "text-text-secondary hover:bg-hover-row"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-auto p-3 font-mono text-xs text-text-secondary">
        {tab === "validation" && (
          <p>
            {issues.length === 0
              ? "No validation issues."
              : `${issues.length} issue${issues.length === 1 ? "" : "s"} — ${errorCount} error${errorCount === 1 ? "" : "s"}, ${warningCount} warning${warningCount === 1 ? "" : "s"}. Open the Validation workspace from the nav to review.`}
          </p>
        )}
        {tab === "export" && (
          <div className="space-y-1">
            <p>Document v{job.document_version ?? 0}</p>
            <p className={markdownStale ? "text-warning" : ""}>
              Markdown: {job.markdown_available ? (markdownStale ? `stale (generated at v${job.markdown_generated_at_version})` : "up to date") : "not generated"}
            </p>
            <p className={docxStale ? "text-warning" : ""}>
              DOCX: {job.docx_available ? (docxStale ? `stale (generated at v${job.docx_generated_at_version})` : "up to date") : "not generated"}
            </p>
          </div>
        )}
        {tab === "console" && (
          <p className="text-text-secondary/70">
            No backend log-stream endpoint exists yet — this tab is reserved for a future
            processing console, not fabricated output.
          </p>
        )}
      </div>
    </div>
  );
}
