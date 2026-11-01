"use client";

import { useEffect, useState } from "react";
import { api, type DocumentMetrics, type MetricsRate } from "@/lib/api";

const BUCKETS = ["auto_decided", "pending_human", "accepted_unchanged", "edited", "rejected"] as const;
const BUCKET_LABELS: Record<(typeof BUCKETS)[number], string> = {
  auto_decided: "Decided by RAWRS",
  pending_human: "Asked a human",
  accepted_unchanged: "Kept by reviewer",
  edited: "Edited",
  rejected: "Rejected",
};

function rateText(rate: MetricsRate): string {
  if (rate.status !== "measured") return `Not measured yet (${rate.items} items)`;
  return `${rate.pooled_pct}% of ${rate.items} items`;
}

function minutes(seconds: number): string {
  return `${Math.ceil(seconds / 60)} min`;
}

/** Automation metrics for one document (src/metrics/automation.py). Measured
 *  figures and the estimate are shown apart and never combined. */
export function AutomationPanel({ jobId }: { jobId: string }) {
  const [metrics, setMetrics] = useState<DocumentMetrics | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.getDocumentMetrics(jobId).then(
      (data) => !cancelled && setMetrics(data),
      (err: unknown) => !cancelled && setError(err instanceof Error ? err.message : "Could not load metrics."),
    );
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  if (metrics === undefined && !error) return null;
  return (
    <section aria-labelledby="automation-heading" className="space-y-3 rounded-xl border border-border bg-surface-panel p-5">
      <h2 id="automation-heading" className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
        Automation
      </h2>
      {error && <p role="alert" className="text-sm text-status-error">{error}</p>}
      {metrics === null && <p className="text-sm text-text-secondary">No metrics: this document was processed before RAWRS recorded them.</p>}
      {metrics && <MetricsBody metrics={metrics} />}
    </section>
  );
}

function MetricsBody({ metrics }: { metrics: DocumentMetrics }) {
  const { rates, checks } = metrics;
  const needsHuman = checks ? (checks.manual ?? 0) + (checks.warn ?? 0) : 0;
  return (
    <div className="space-y-3 text-sm">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
        <dt className="font-medium">Decided without asking a human</dt>
        <dd>{rateText(rates.decided_without_human)}</dd>
        <dt className="font-medium">Reviewer kept unchanged</dt>
        <dd>{rateText(rates.reviewer_kept_unchanged)} ({rates.human_decisions} human decisions)</dd>
        <dt className="font-medium">Checklist (RAWRS&apos;s own audit)</dt>
        <dd>{checks ? `${checks.pass ?? 0} pass, ${checks.fail ?? 0} fail, ${needsHuman} need a human` : "Not recorded"}</dd>
        <dt className="font-medium">Processing time</dt>
        <dd>{Math.ceil(metrics.total_seconds)} s</dd>
        <dt className="font-medium">Active review time</dt>
        <dd>{minutes(metrics.review_seconds_loose)} (strict: {minutes(metrics.review_seconds_strict)})</dd>
      </dl>
      <table className="w-full text-left text-xs">
        <caption className="sr-only">Items by category and outcome, current state</caption>
        <thead>
          <tr>
            <th scope="col">Item</th>
            {BUCKETS.map((b) => <th key={b} scope="col">{BUCKET_LABELS[b]}</th>)}
          </tr>
        </thead>
        <tbody>
          {Object.entries(metrics.live).map(([category, counts]) => (
            <tr key={category}>
              <th scope="row" className="font-normal">{category.replace("_", " ")}</th>
              {BUCKETS.map((b) => <td key={b}>{counts[b] ?? 0}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {metrics.estimate && (
        <p className="text-xs text-text-secondary">
          {String(metrics.estimate.label)}: heading F1 {String(metrics.estimate.heading_f1 ?? "n/a")}. This is an estimate, not a reviewer measurement.
        </p>
      )}
    </div>
  );
}
