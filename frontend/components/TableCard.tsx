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
    case "auto_detected": return "bg-yellow-100 text-yellow-800";
    case "manually_created": return "bg-blue-100 text-blue-800";
    case "reviewed": return "bg-green-100 text-green-800";
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
          ? "border-blue-500 bg-blue-50"
          : "border-gray-200 hover:border-gray-300 bg-white"
      }`}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div>
          <p className="text-xs text-gray-500 mb-0.5">Page {table.page_number}</p>
          <p className="text-sm font-medium text-gray-900">
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
            <span className="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium bg-orange-100 text-orange-800">
              {Math.round(table.confidence * 100)}% confidence
            </span>
          )}
        </div>
      </div>

      {table.caption ? (
        <p className="text-sm text-gray-700 italic line-clamp-2 mb-1">{table.caption}</p>
      ) : (
        <p className="text-xs text-gray-400 italic mb-1">No caption</p>
      )}

      {issueCount > 0 && (
        <p className="text-xs text-amber-600">
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
