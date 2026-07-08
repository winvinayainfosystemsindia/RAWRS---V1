"use client";

import { type TableItem } from "@/lib/api";

interface Props {
  table: TableItem;
  isSelected: boolean;
  onSelect: () => void;
}

function statusLabel(status: TableItem["status"]): string {
  switch (status) {
    case "auto_detected": return "Auto-detected";
    case "manually_created": return "Manual";
    case "reviewed": return "Reviewed";
  }
}

function statusColor(status: TableItem["status"]): string {
  switch (status) {
    case "auto_detected": return "bg-warning/10 text-warning";
    case "manually_created": return "bg-accent/10 text-accent";
    case "reviewed": return "bg-success/10 text-success";
  }
}

export function TableCard({ table, isSelected, onSelect }: Props) {
  const missingCaption = !table.caption;
  const missingSummary = !table.summary;
  const missingHeader = !table.rows.some((r) => r.is_header_row);
  const issueCount = [missingCaption, missingSummary, missingHeader].filter(Boolean).length;
  const lowConfidence =
    table.status === "auto_detected" && table.confidence < 0.7;

  return (
    <li
      className={`rounded-lg border p-3 cursor-pointer transition-colors ${
        isSelected
          ? "border-accent bg-accent/10"
          : "border-border hover:border-border-strong bg-surface-elevated"
      }`}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div>
          <p className="text-xs text-text-secondary mb-0.5">Page {table.page_number}</p>
          <p className="text-sm font-medium text-text-primary">
            {table.row_count} rows × {table.col_count} cols
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span
            className={`shrink-0 inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${statusColor(table.status)}`}
          >
            {statusLabel(table.status)}
          </span>
          {lowConfidence && (
            <span className="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium bg-warning/10 text-warning">
              {Math.round(table.confidence * 100)}% confidence
            </span>
          )}
        </div>
      </div>

      {table.caption ? (
        <p className="text-sm text-text-primary italic line-clamp-2 mb-1">{table.caption}</p>
      ) : (
        <p className="text-xs text-text-secondary italic mb-1">No caption</p>
      )}

      {issueCount > 0 && (
        <p className="text-xs text-warning">
          {issueCount} accessibility {issueCount === 1 ? "issue" : "issues"} —{" "}
          {[
            missingCaption && "no caption",
            missingSummary && "no summary",
            missingHeader && "no header row",
          ]
            .filter(Boolean)
            .join(", ")}
        </p>
      )}
    </li>
  );
}
