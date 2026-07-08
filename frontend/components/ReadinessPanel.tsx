"use client";

import type { ReadinessReport } from "@/lib/api";

interface Props {
  readiness: ReadinessReport | null;
}

/**
 * Renders whatever GET /documents/{id}/readiness reports — no hardcoded
 * rule_id -> category mapping here. Every current and future verifier's
 * findings count toward this automatically (see
 * src/validation/readiness.py); this component never needs an edit when
 * a new rule or asset type is added, unlike ChecklistPanel.tsx's
 * hand-written per-rule byRule() lists (kept as-is, a separate,
 * pre-existing surface — see docs/DECISIONS_LOG.md for the migration
 * plan).
 */
export function ReadinessPanel({ readiness }: Props) {
  if (!readiness) {
    return <p className="text-sm text-text-secondary">Readiness data not available.</p>;
  }

  if (readiness.categories.length === 0) {
    return (
      <p className="text-sm text-text-secondary">
        No validation issues recorded — nothing to report a readiness breakdown for yet.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <span
          className={`inline-flex items-center rounded px-2.5 py-1 text-sm font-semibold ${
            readiness.ready ? "bg-success/10 text-success" : "bg-warning/10 text-warning"
          }`}
        >
          {readiness.ready ? "Export Ready" : "Not Yet Ready"}
        </span>
        <span className="text-sm text-text-secondary">
          {Math.round(readiness.overall_score * 100)}% of categories ready
        </span>
      </div>

      <ul className="divide-y divide-border rounded-lg border border-border bg-surface-elevated">
        {readiness.categories.map((category) => (
          <li key={category.category} className="flex items-center justify-between gap-4 px-4 py-3">
            <div>
              <p className="text-sm font-medium text-text-primary">{category.label}</p>
              <p className="text-xs text-text-secondary">
                {category.error_count > 0 && <span className="text-danger">{category.error_count} error(s) </span>}
                {category.warning_count > 0 && <span className="text-warning">{category.warning_count} warning(s) </span>}
                {category.info_count > 0 && <span className="text-text-secondary">{category.info_count} info</span>}
                {category.error_count === 0 && category.warning_count === 0 && category.info_count === 0 && "No issues"}
              </p>
            </div>
            <span
              className={`shrink-0 inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${
                category.ready ? "bg-success/10 text-success" : "bg-warning/10 text-warning"
              }`}
            >
              {category.ready ? "Ready" : "Needs review"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
