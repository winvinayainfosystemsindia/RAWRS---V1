"use client";

import { useMemo, useState } from "react";
import type { JobSummary, ValidationIssue } from "@/lib/api";
import { ReviewerWorkspace } from "@/components/ReviewerWorkspace";
import { useDocumentData, selectCorrections } from "@/lib/store/DocumentDataContext";
import { usePdfViewport } from "@/lib/store/PdfViewportContext";

type BottomTab = "review" | "validation" | "export" | "console";

export function BottomPanel({ job, issues, jobId }: { job: JobSummary; issues: ValidationIssue[]; jobId: string }) {
  const [tab, setTab] = useState<BottomTab>("review");
  const errorCount = issues.filter((i) => i.severity === "error").length;
  const warningCount = issues.filter((i) => i.severity === "warning").length;

  const state = useDocumentData();
  const corrections = selectCorrections(state);
  const { visitedPages } = usePdfViewport();

  // Coverage = reviewer ATTENTION, not issue resolution (P2-10). Pages
  // visited comes from the viewport (the reviewer's eyes landed there);
  // "decided" counts pages where a human acted on a correction, explicitly
  // excluding auto_applied (the machine acted, not the reviewer). A visited
  // page with no issues still counts as covered — coverage and completion
  // are different questions.
  const coverage = useMemo(() => {
    if (!job.page_count) return null;
    const pagesWithIssues = new Set(
      corrections.map((c) => c.page_number).filter((p): p is number => p !== null)
    );
    const humanDecided = (c: (typeof corrections)[number]) =>
      c.reviewed_at !== null && c.status !== "auto_applied";
    const decidedPages = new Set(
      corrections.filter(humanDecided).map((c) => c.page_number).filter((p): p is number => p !== null)
    );
    return {
      pagesVisited: visitedPages.size,
      pagesDecided: decidedPages.size,
      pagesWithIssues: pagesWithIssues.size,
      totalPages: job.page_count,
    };
  }, [corrections, job.page_count, visitedPages]);

  // Recent Activity is now an honest reviewer timeline (P0-3): ordered by
  // reviewed_at (when the human acted), not created_at (pipeline creation
  // time — which was near-identical for every item and made the order
  // meaningless). Only items the reviewer has actually acted on appear.
  const recentActivity = useMemo(() => {
    return corrections
      .filter((c) => c.reviewed_at !== null && c.status !== "auto_applied")
      .sort((a, b) => (b.reviewed_at ?? "").localeCompare(a.reviewed_at ?? ""))
      .slice(0, 8)
      .map((c) => {
        const verb = c.status === "accepted" ? "Accepted"
          : c.status === "rejected" ? "Rejected"
          : c.status === "edited" ? "Edited"
          : c.status === "ignored" ? "Ignored"
          : c.status === "reverted" ? "Reverted" : c.status;
        const type = c.object_type.charAt(0).toUpperCase() + c.object_type.slice(1);
        const page = c.page_number !== null ? ` on page ${c.page_number}` : "";
        return `${verb}: ${type} correction${page}`;
      });
  }, [corrections]);

  const markdownStale =
    job.markdown_generated_at_version !== null && job.markdown_generated_at_version !== job.document_version;
  const docxStale =
    job.docx_generated_at_version !== null && job.docx_generated_at_version !== job.document_version;

  return (
    <div className={`flex flex-col ${tab === "review" ? "h-96" : "h-40"}`}>
      <div className="flex items-center gap-1 border-b border-border px-2 py-1">
        {([
          ["review", "Review Queue"],
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
      <div className={`flex-1 overflow-auto ${tab === "review" ? "" : "p-3 font-mono text-xs text-text-secondary"}`}>
        {tab === "review" && <ReviewerWorkspace jobId={jobId} />}
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
          <div className="space-y-2">
            <p>
              <span className="text-text-primary font-medium">{job.filename}</span>
              {" — "}
              {job.status === "complete"
                ? `Completed in ${job.duration_seconds?.toFixed(1) ?? "?"}s`
                : job.status === "failed"
                  ? `Failed${job.failed_stage ? ` at ${job.failed_stage}` : ""}`
                  : job.status}
            </p>
            {job.page_count !== null && (
              <p>{job.page_count} page{job.page_count === 1 ? "" : "s"} processed</p>
            )}
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
              {job.heading_count !== null && <><dt>Headings</dt><dd>{job.heading_count} detected</dd></>}
              {job.image_count !== null && <><dt>Images</dt><dd>{job.image_count} detected</dd></>}
              {job.footnote_count !== null && <><dt>Footnotes</dt><dd>{job.footnote_count} detected</dd></>}
              {(job.error_count !== null || job.warning_count !== null) && (
                <><dt>Validation</dt><dd>{job.error_count ?? 0} error{job.error_count === 1 ? "" : "s"}, {job.warning_count ?? 0} warning{job.warning_count === 1 ? "" : "s"}</dd></>
              )}
            </dl>
            {job.error_message && (
              <p className="text-danger">{job.error_message}</p>
            )}
            {coverage && (
              <p>
                Review coverage: {coverage.pagesVisited} / {coverage.totalPages} pages visited
                {" · "}
                {coverage.pagesDecided} page{coverage.pagesDecided === 1 ? "" : "s"} with your decisions
                {coverage.pagesWithIssues > 0 && ` · ${coverage.pagesWithIssues} page${coverage.pagesWithIssues === 1 ? "" : "s"} have flagged issues`}
              </p>
            )}
            {recentActivity.length > 0 && (
              <div>
                <p className="text-text-primary font-medium">Recent Activity</p>
                <ul className="mt-1 space-y-0.5">
                  {recentActivity.map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
