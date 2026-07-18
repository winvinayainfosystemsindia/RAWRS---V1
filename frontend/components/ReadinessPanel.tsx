"use client";

import { useMemo } from "react";
import type { AccessibilityReport, ReadinessReport } from "@/lib/api";
import { KNOWN_READINESS_CATEGORIES } from "@/lib/validationCategories";
import { IconCheckCircle, IconWarningTriangle, IconValidation } from "@/components/icons";

interface Props {
  readiness: ReadinessReport | null;
  accessibilityReport: AccessibilityReport | null;
  onSelectCategory?: (specialViewId: string) => void;
  onFixNext?: () => void;
}

// --- Engine-powered view (when accessibilityReport is available) -----------

const CATEGORY_SPECIAL_VIEW: Record<string, string> = {
  headings: "headings",
  images: "images",
  tables: "tables",
  metadata: "metadata",
  reading_order: "reading-order",
};

function specialViewFor(category: string): string | undefined {
  return CATEGORY_SPECIAL_VIEW[category.toLowerCase().replace(/\s+/g, "_")];
}

function EngineReadinessPanel({ report, onSelectCategory, onFixNext }: {
  report: AccessibilityReport;
  onSelectCategory?: (id: string) => void;
  onFixNext?: () => void;
}) {
  const scorePercent = Math.round(report.overall_score * 100);
  const failingCount = useMemo(
    () => report.evaluations.filter((ev) => ev.outcome === "FAIL" || ev.outcome === "MANUAL_REVIEW_REQUIRED").length,
    [report.evaluations]
  );

  const coverageByCategory = useMemo(() => {
    const map = new Map<string, { total: number; covered: number }>();
    for (const ev of report.evaluations) {
      const entry = map.get(ev.category) ?? { total: 0, covered: 0 };
      entry.total++;
      if (ev.outcome !== "MANUAL_REVIEW_REQUIRED") entry.covered++;
      map.set(ev.category, entry);
    }
    return map;
  }, [report.evaluations]);

  return (
    <div className="space-y-5">
      {/* Score + Export Ready header */}
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-surface-panel p-4">
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-bold tabular-nums text-text-primary">{scorePercent}%</span>
          <span className="text-sm text-text-secondary">Accessibility Score</span>
        </div>
        <span
          className={`ml-auto inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-sm font-semibold ${
            report.export_ready ? "bg-success/10 text-success" : "bg-danger/10 text-danger"
          }`}
        >
          {report.export_ready ? <IconCheckCircle className="h-4 w-4" /> : <IconWarningTriangle className="h-4 w-4" />}
          {report.export_ready ? "Export Ready" : "Blocked"}
        </span>
      </div>

      {/* Blocking failures */}
      {!report.export_ready && report.blocking_failures.length > 0 && (
        <div className="rounded-lg border border-danger/30 bg-danger/5 p-3">
          <p className="text-xs font-semibold text-danger">Export blocked by:</p>
          <ul className="mt-1.5 space-y-1">
            {report.blocking_failures.map((failure) => (
              <li key={failure} className="flex items-start gap-1.5 text-sm text-danger/90">
                <span className="shrink-0">•</span>
                <span>{failure}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Fix Next CTA */}
      {failingCount > 0 && onFixNext && (
        <button
          type="button"
          onClick={onFixNext}
          className="flex w-full items-center justify-between rounded-lg border border-accent bg-accent/10 px-4 py-3 text-sm font-semibold text-accent transition-colors hover:bg-accent/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <span>Fix Next Issue</span>
          <span className="tabular-nums text-xs font-normal opacity-80">
            {failingCount} remaining
          </span>
        </button>
      )}

      {/* Lost Points — traceable score breakdown */}
      {report.point_ledger.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-semibold text-text-secondary">Lost Points</p>
          <div className="overflow-x-auto rounded-lg border border-border bg-surface-elevated">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-xs text-text-secondary">
                  <th className="px-3 py-1.5 text-left font-medium">Rule</th>
                  <th className="px-3 py-1.5 text-right font-medium">Lost</th>
                  <th className="px-3 py-1.5 text-right font-medium">Score if fixed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {report.point_ledger.map((entry) => {
                  const predicted = report.max_points > 0
                    ? Math.round(((report.max_points - (report.points_lost - entry.points_lost)) / report.max_points) * 100)
                    : 0;
                  return (
                    <tr key={entry.label}>
                      <td className="px-3 py-2 text-text-primary">{entry.label}</td>
                      <td className="px-3 py-2 text-right tabular-nums font-medium text-danger">
                        &minus;{entry.points_lost}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums font-medium text-success">
                        {predicted}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="border-t border-border">
                  <td className="px-3 py-2 text-xs font-semibold text-text-secondary">Total lost</td>
                  <td className="px-3 py-2 text-right tabular-nums text-xs font-semibold text-danger">
                    &minus;{report.points_lost} / {report.max_points}
                  </td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      )}

      {/* Debt tiles */}
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-danger/30 bg-danger/10 p-3">
          <dt className="text-xs text-danger">Critical Debt</dt>
          <dd className="mt-1 text-xl font-bold tabular-nums text-danger">{report.debt.critical_debt_points}</dd>
        </div>
        <div className="rounded-lg border border-warning/30 bg-warning/10 p-3">
          <dt className="text-xs text-warning">Moderate Debt</dt>
          <dd className="mt-1 text-xl font-bold tabular-nums text-warning">{report.debt.moderate_debt_points}</dd>
        </div>
        <div className="rounded-lg border border-accent/30 bg-accent/10 p-3">
          <dt className="text-xs text-accent">Minor Debt</dt>
          <dd className="mt-1 text-xl font-bold tabular-nums text-accent">{report.debt.minor_debt_points}</dd>
        </div>
        <div className="rounded-lg border border-success/30 bg-success/10 p-3">
          <dt className="text-xs text-success">Manual Review</dt>
          <dd className="mt-1 text-xl font-bold tabular-nums text-success">{report.manual_review_count}</dd>
        </div>
      </dl>

      {/* Category scores */}
      <div>
        <p className="mb-2 text-xs font-semibold text-text-secondary">Category Breakdown</p>
        <ul className="space-y-2">
          {report.categories.map((cat) => {
            const catPercent = Math.round(cat.score * 100);
            const specialView = specialViewFor(cat.category);
            const isFailing = cat.points_lost > 0;
            const cov = coverageByCategory.get(cat.category);
            const covPercent = cov && cov.total > 0 ? Math.round((cov.covered / cov.total) * 100) : 100;
            return (
              <li key={cat.category} className="rounded-lg border border-border bg-surface-elevated px-4 py-3">
                <div className="flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-text-primary">{cat.category}</p>
                    <p className="text-xs text-text-secondary">
                      {cat.points_lost > 0 ? `−${cat.points_lost} pts lost` : "No issues"}
                      {cat.manual_review_count > 0 && ` · ${cat.manual_review_count} for review`}
                      {cov && cov.total > 0 && ` · ${cov.covered}/${cov.total} rules covered`}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className={`inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs font-medium ${
                      isFailing ? "bg-danger/10 text-danger" : "bg-success/10 text-success"
                    }`}>
                      {isFailing
                        ? <IconWarningTriangle className="h-3.5 w-3.5" />
                        : <IconCheckCircle className="h-3.5 w-3.5" />}
                      {catPercent}%
                    </span>
                    {specialView && onSelectCategory && isFailing && (
                      <button
                        type="button"
                        onClick={() => onSelectCategory(specialView)}
                        className="rounded border border-border px-2 py-0.5 text-xs font-medium text-accent hover:bg-hover-row"
                      >
                        Review &rarr;
                      </button>
                    )}
                  </div>
                </div>
                <div className="mt-2 h-1.5 rounded-full bg-surface-canvas">
                  <div
                    className={`h-full rounded-full transition-all ${isFailing ? "bg-danger/60" : "bg-success/60"}`}
                    style={{ width: `${catPercent}%` }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      {/* Failing evaluations detail */}
      {failingCount > 0 && (
        <details className="rounded-lg border border-border">
          <summary className="cursor-pointer select-none px-4 py-2.5 text-xs font-semibold text-text-secondary hover:text-text-primary">
            Failing Rules ({failingCount})
          </summary>
          <ul className="divide-y divide-border border-t border-border">
            {report.evaluations
              .filter((ev) => ev.outcome === "FAIL" || ev.outcome === "MANUAL_REVIEW_REQUIRED")
              .map((ev, i) => (
                <li key={`${ev.rule_id}-${ev.object_id ?? i}`} className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                      ev.outcome === "FAIL" ? "bg-danger/10 text-danger" : "bg-accent/10 text-accent"
                    }`}>
                      {ev.outcome === "FAIL" ? "FAIL" : "REVIEW"}
                    </span>
                    <span className="font-mono text-xs text-text-secondary">{ev.rule_id}</span>
                    {ev.page_number != null && (
                      <span className="text-xs text-text-secondary">Page {ev.page_number}</span>
                    )}
                    <span className={`ml-auto rounded px-1.5 py-0.5 text-[10px] font-medium ${
                      ev.confidence_tier === "HIGH" ? "bg-success/10 text-success"
                      : ev.confidence_tier === "MEDIUM" ? "bg-warning/10 text-warning"
                      : "bg-danger/10 text-danger"
                    }`}>
                      {Math.round(ev.confidence * 100)}% {ev.confidence_tier}
                    </span>
                  </div>
                  <p className="mt-1.5 text-sm text-text-primary">{ev.message}</p>
                  {ev.category && (
                    <p className="mt-0.5 text-xs text-text-secondary">Category: {ev.category}</p>
                  )}
                  {ev.evidence.length > 0 && (
                    <div className="mt-2 space-y-1 rounded border border-border bg-surface-canvas p-2">
                      <p className="text-[10px] font-semibold text-text-secondary">Evidence</p>
                      {ev.evidence.map((sig, si) => (
                        <div key={si} className="flex items-baseline gap-2 text-xs">
                          <span className="shrink-0 font-mono text-text-secondary">{sig.name}</span>
                          <span className="text-text-primary">{sig.note}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </li>
              ))}
          </ul>
        </details>
      )}
    </div>
  );
}

// --- Legacy view (fallback when engine report is not available) ------------

type CategoryStatus = "passed" | "warning" | "failed" | "manual_review" | "not_assessed";

interface CategoryRow {
  prefix: string;
  label: string;
  specialViewId?: string;
  status: CategoryStatus;
  errorCount: number;
  warningCount: number;
  infoCount: number;
}

function buildCategoryRows(readiness: ReadinessReport): CategoryRow[] {
  return KNOWN_READINESS_CATEGORIES.map((known) => {
    const real = readiness.categories.find((c) => c.category === known.prefix);
    const errorCount = real?.error_count ?? 0;
    const warningCount = real?.warning_count ?? 0;
    const infoCount = real?.info_count ?? 0;

    let status: CategoryStatus;
    if (errorCount > 0) status = "failed";
    else if (warningCount > 0) status = "warning";
    else if (infoCount > 0) status = "manual_review";
    else status = "passed";

    return { prefix: known.prefix, label: real?.label ?? known.label, specialViewId: known.specialViewId, status, errorCount, warningCount, infoCount };
  });
}

const STATUS_META: Record<CategoryStatus, { label: string; className: string }> = {
  passed: { label: "Passed", className: "bg-success/10 text-success" },
  warning: { label: "Warning", className: "bg-warning/10 text-warning" },
  failed: { label: "Failed", className: "bg-danger/10 text-danger" },
  manual_review: { label: "Manual Review Required", className: "bg-accent/10 text-accent" },
  not_assessed: { label: "Not yet assessed", className: "bg-hover-row text-text-secondary" },
};

function StatusIcon({ status }: { status: CategoryStatus }) {
  const className = "h-4 w-4 shrink-0";
  if (status === "passed") return <IconCheckCircle className={className} />;
  if (status === "manual_review") return <IconValidation className={className} />;
  if (status === "not_assessed") return null;
  return <IconWarningTriangle className={className} />;
}

function LegacyCategoryCard({ row, onSelectCategory }: { row: CategoryRow; onSelectCategory?: (id: string) => void }) {
  const meta = STATUS_META[row.status];
  const issueSummary =
    row.errorCount + row.warningCount + row.infoCount === 0
      ? "No issues found"
      : [
          row.errorCount > 0 && `${row.errorCount} critical`,
          row.warningCount > 0 && `${row.warningCount} warning${row.warningCount === 1 ? "" : "s"}`,
          row.infoCount > 0 && `${row.infoCount} for manual review`,
        ]
          .filter(Boolean)
          .join(", ");

  return (
    <li className="flex items-center justify-between gap-4 rounded-lg border border-border bg-surface-elevated px-4 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium text-text-primary">{row.label}</p>
        <p className="text-xs text-text-secondary">{issueSummary}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <span className={`inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs font-medium ${meta.className}`}>
          <StatusIcon status={row.status} />
          {meta.label}
        </span>
        {row.specialViewId && onSelectCategory && row.status !== "passed" && (
          <button
            type="button"
            onClick={() => onSelectCategory(row.specialViewId!)}
            className="rounded border border-border px-2 py-0.5 text-xs font-medium text-accent hover:bg-hover-row"
          >
            Review &rarr;
          </button>
        )}
      </div>
    </li>
  );
}

function LegacyReadinessPanel({ readiness, onSelectCategory }: {
  readiness: ReadinessReport;
  onSelectCategory?: (id: string) => void;
}) {
  const rows = buildCategoryRows(readiness);
  const totals = rows.reduce(
    (acc, r) => ({
      critical: acc.critical + r.errorCount,
      warnings: acc.warnings + r.warningCount,
      manualReview: acc.manualReview + r.infoCount,
      passed: acc.passed + (r.status === "passed" ? 1 : 0),
    }),
    { critical: 0, warnings: 0, manualReview: 0, passed: 0 }
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-surface-panel p-4">
        <span
          className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-base font-semibold ${
            readiness.ready ? "bg-success/10 text-success" : "bg-warning/10 text-warning"
          }`}
        >
          {readiness.ready ? <IconCheckCircle className="h-5 w-5" /> : <IconWarningTriangle className="h-5 w-5" />}
          {readiness.ready ? "Export Ready" : "Not Yet Ready"}
        </span>
        <span className="text-sm text-text-secondary">
          Overall Accessibility Score:{" "}
          <span className="font-semibold text-text-primary">{Math.round(readiness.overall_score * 100)}%</span>
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-danger/30 bg-danger/10 p-3">
          <dt className="text-xs text-danger">Critical Issues</dt>
          <dd className="mt-1 text-xl font-bold tabular-nums text-danger">{totals.critical}</dd>
        </div>
        <div className="rounded-lg border border-warning/30 bg-warning/10 p-3">
          <dt className="text-xs text-warning">Warnings</dt>
          <dd className="mt-1 text-xl font-bold tabular-nums text-warning">{totals.warnings}</dd>
        </div>
        <div className="rounded-lg border border-success/30 bg-success/10 p-3">
          <dt className="text-xs text-success">Passed Checks</dt>
          <dd className="mt-1 text-xl font-bold tabular-nums text-success">
            {totals.passed} / {rows.length}
          </dd>
        </div>
        <div className="rounded-lg border border-accent/30 bg-accent/10 p-3">
          <dt className="text-xs text-accent">Manual Review</dt>
          <dd className="mt-1 text-xl font-bold tabular-nums text-accent">{totals.manualReview}</dd>
        </div>
      </dl>

      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-secondary">
          Category Breakdown
        </p>
        <ul className="space-y-2">
          {rows.map((row) => (
            <LegacyCategoryCard key={row.prefix} row={row} onSelectCategory={onSelectCategory} />
          ))}
        </ul>
      </div>
    </div>
  );
}

// --- Public component — delegates to engine or legacy view ----------------

export function ReadinessPanel({ readiness, accessibilityReport, onSelectCategory, onFixNext }: Props) {
  if (accessibilityReport) {
    return <EngineReadinessPanel report={accessibilityReport} onSelectCategory={onSelectCategory} onFixNext={onFixNext} />;
  }
  if (readiness) {
    return <LegacyReadinessPanel readiness={readiness} onSelectCategory={onSelectCategory} />;
  }
  return <p className="text-sm text-text-secondary">Readiness data not available.</p>;
}
