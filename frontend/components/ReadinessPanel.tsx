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
    return <p className="text-sm text-gray-600">Readiness data not available.</p>;
  }

  if (readiness.categories.length === 0) {
    return (
      <p className="text-sm text-gray-600">
        No validation issues recorded — nothing to report a readiness breakdown for yet.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <span
          className={`inline-flex items-center rounded px-2.5 py-1 text-sm font-semibold ${
            readiness.ready ? "bg-green-100 text-green-800" : "bg-yellow-100 text-yellow-800"
          }`}
        >
          {readiness.ready ? "Export Ready" : "Not Yet Ready"}
        </span>
        <span className="text-sm text-gray-600">
          {Math.round(readiness.overall_score * 100)}% of categories ready
        </span>
      </div>

      <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
        {readiness.categories.map((category) => (
          <li key={category.category} className="flex items-center justify-between gap-4 px-4 py-3">
            <div>
              <p className="text-sm font-medium text-gray-800">{category.label}</p>
              <p className="text-xs text-gray-500">
                {category.error_count > 0 && <span className="text-red-600">{category.error_count} error(s) </span>}
                {category.warning_count > 0 && <span className="text-yellow-700">{category.warning_count} warning(s) </span>}
                {category.info_count > 0 && <span className="text-gray-400">{category.info_count} info</span>}
                {category.error_count === 0 && category.warning_count === 0 && category.info_count === 0 && "No issues"}
              </p>
            </div>
            <span
              className={`shrink-0 inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${
                category.ready ? "bg-green-100 text-green-800" : "bg-yellow-100 text-yellow-800"
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
