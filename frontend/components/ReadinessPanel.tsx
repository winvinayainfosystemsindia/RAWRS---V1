"use client";

import type { ReadinessReport } from "@/lib/api";
import { KNOWN_READINESS_CATEGORIES, DEFERRED_READINESS_CATEGORIES } from "@/lib/validationCategories";
import { IconCheckCircle, IconWarningTriangle, IconValidation } from "@/components/icons";

interface Props {
  readiness: ReadinessReport | null;
  // Phase RW-1 issue #3 — lets a reviewer jump straight from a failed
  // category to the special view that fixes it, reusing the exact same
  // setActiveSpecialView mechanism every other navigation path in the
  // app already calls (DocumentWorkspace.tsx). Optional so this panel
  // still renders standalone (e.g. tests) without it.
  onSelectCategory?: (specialViewId: string) => void;
}

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

/**
 * Merges the backend's real per-run category counts (GET /readiness —
 * only ever contains an entry for a rule prefix that actually fired,
 * see src/validation/readiness.py compute_readiness) against the fixed
 * set of categories RAWRS's validator can possibly report on. A known
 * category absent from the report has zero issues this run — a real,
 * backend-truthful "Passed", not a fabricated one. Nothing here invents
 * a score for a category the validator has no rule prefix for at all;
 * see DEFERRED_READINESS_CATEGORIES for those, rendered separately.
 */
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

    return {
      prefix: known.prefix,
      label: real?.label ?? known.label,
      specialViewId: known.specialViewId,
      status,
      errorCount,
      warningCount,
      infoCount,
    };
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

function CategoryCard({ row, onSelectCategory }: { row: CategoryRow; onSelectCategory?: (id: string) => void }) {
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

/**
 * The Accessibility Center — a reviewer's primary document-health
 * overview. Everything on this screen is derived from GET /readiness's
 * real category counts (src/validation/readiness.py); nothing is
 * hardcoded. Categories with no backend rule coverage yet (Reading
 * Order as its own score, Navigation, Language) are named explicitly as
 * deferred, not silently omitted or fabricated — see
 * DEFERRED_READINESS_CATEGORIES and issue #7's WCAG-foundation intent:
 * this UI is built to keep working, unchanged, once a future
 * Accessibility Rules Engine fills those categories in with real data.
 */
export function ReadinessPanel({ readiness, onSelectCategory }: Props) {
  if (!readiness) {
    return <p className="text-sm text-text-secondary">Readiness data not available.</p>;
  }

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
      {/* Overall score + export readiness — the primary health signal. */}
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

      {/* Critical / Warnings / Passed / Manual review — real aggregate
          counts from the category rows above, not separate data. */}
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

      {/* Per-category WCAG-style breakdown. */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-secondary">
          Category Breakdown
        </p>
        <ul className="space-y-2">
          {rows.map((row) => (
            <CategoryCard key={row.prefix} row={row} onSelectCategory={onSelectCategory} />
          ))}
        </ul>
      </div>

      {/* Named, honest placeholder for a future Accessibility Rules
          Engine — not a fabricated score for these categories. */}
      <div className="rounded-lg border border-dashed border-border-strong bg-surface-elevated p-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
          Awaiting Accessibility Rules Engine
        </p>
        <p className="mt-1 text-xs text-text-secondary">
          {DEFERRED_READINESS_CATEGORIES.join(", ")} — no automated check exists for these yet; not scored above.
        </p>
      </div>
    </div>
  );
}
