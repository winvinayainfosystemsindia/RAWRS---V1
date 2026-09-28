"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type ChecklistItem, type ChecklistReport, type ChecklistStatus } from "@/lib/api";

// The two remediation checklists (docs/Checklist for Document Remediation1.docx
// and docs/ChecklistBeforeSubmittingDoc.xlsx), ticked by the backend against
// the DOCX a reader would download right now. The reviewer's job here is to
// oversee: everything automated is already decided, so failures come first and
// passes are folded away.

const STATUS_LABEL: Record<ChecklistStatus, string> = {
  fail: "Fail",
  warn: "Check",
  manual: "Manual",
  pass: "Pass",
  not_applicable: "N/A",
};

const STATUS_CLASS: Record<ChecklistStatus, string> = {
  fail: "bg-danger/10 text-danger",
  warn: "bg-warning/10 text-warning",
  manual: "bg-accent/10 text-accent",
  pass: "bg-success/10 text-success",
  not_applicable: "bg-surface-elevated text-text-secondary",
};

const SOURCE_LABEL: Record<ChecklistItem["source"], string> = {
  remediation_docx: "Checklist for Document Remediation",
  submission_xlsx: "Checklist before submitting",
};

const ATTENTION: ChecklistStatus[] = ["fail", "warn", "manual"];

function StatusBadge({ status }: { status: ChecklistStatus }) {
  return (
    <span className={`inline-block shrink-0 rounded px-2 py-0.5 text-xs font-semibold ${STATUS_CLASS[status]}`}>
      {STATUS_LABEL[status]}
    </span>
  );
}

function ItemRow({ item }: { item: ChecklistItem }) {
  return (
    <li className="flex items-start gap-3 px-3 py-2">
      <StatusBadge status={item.status} />
      <div className="min-w-0">
        <p className="text-sm text-text-primary">{item.requirement}</p>
        {item.evidence && <p className="mt-0.5 break-words text-xs text-text-secondary">{item.evidence}</p>}
      </div>
    </li>
  );
}

export function ChecklistAuditPanel({ jobId }: { jobId: string }) {
  const [report, setReport] = useState<ChecklistReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [runCount, setRunCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .getChecklist(jobId)
      .then((result) => {
        if (cancelled) return;
        setReport(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not audit the document.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, runCount]);

  const handleRerun = useCallback(() => {
    setIsLoading(true);
    setRunCount((count) => count + 1);
  }, []);

  const { attention, settled } = useMemo(() => {
    const results = report?.results ?? [];
    return {
      attention: results
        .filter((r) => ATTENTION.includes(r.status))
        .sort((a, b) => ATTENTION.indexOf(a.status) - ATTENTION.indexOf(b.status)),
      settled: results.filter((r) => !ATTENTION.includes(r.status)),
    };
  }, [report]);

  return (
    <section aria-labelledby="checklist-heading" className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="checklist-heading" className="text-base font-semibold text-text-primary">
          Remediation checklist
        </h2>
        {report && (
          <span
            className={`rounded px-2.5 py-1 text-xs font-semibold ${
              report.passed ? "bg-success/10 text-success" : "bg-danger/10 text-danger"
            }`}
          >
            {report.passed ? "All automated checks pass" : `${report.summary.fail} failing`}
          </span>
        )}
        <button
          type="button"
          onClick={handleRerun}
          disabled={isLoading}
          className="ml-auto rounded border border-border px-3 py-1 text-xs font-medium text-text-primary hover:bg-surface-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
        >
          {isLoading ? "Auditing…" : "Re-run audit"}
        </button>
      </div>

      {error && (
        <p role="alert" className="rounded border border-danger/30 bg-danger/5 p-3 text-sm text-danger">
          {error}
        </p>
      )}

      {report && (
        <>
          <p className="text-xs text-text-secondary" aria-live="polite">
            {report.summary.pass} pass · {report.summary.fail} fail · {report.summary.warn} to check ·{" "}
            {report.summary.manual} manual · {report.summary.not_applicable} not applicable
          </p>

          {attention.length > 0 ? (
            <ul aria-label="Checklist items needing attention" className="divide-y divide-border rounded-lg border border-border bg-surface-panel">
              {attention.map((item) => (
                <ItemRow key={item.item_id} item={item} />
              ))}
            </ul>
          ) : (
            <p className="text-sm text-success">Nothing needs attention.</p>
          )}

          <details className="rounded-lg border border-border bg-surface-panel">
            <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-text-primary">
              {settled.length} settled items
            </summary>
            {(["remediation_docx", "submission_xlsx"] as const).map((source) => {
              const items = settled.filter((r) => r.source === source);
              if (items.length === 0) return null;
              return (
                <div key={source} className="border-t border-border">
                  <h3 className="px-3 pt-2 text-xs font-semibold text-text-secondary">{SOURCE_LABEL[source]}</h3>
                  <ul className="divide-y divide-border">
                    {items.map((item) => (
                      <ItemRow key={item.item_id} item={item} />
                    ))}
                  </ul>
                </div>
              );
            })}
          </details>
        </>
      )}
    </section>
  );
}
