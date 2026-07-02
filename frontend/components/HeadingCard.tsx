"use client";

import { type HeadingItem } from "@/lib/api";

interface Props {
  heading: HeadingItem;
  isSelected: boolean;
  onSelect: () => void;
}

function statusLabel(status: HeadingItem["review_status"]): string {
  switch (status) {
    case "detected": return "Detected";
    case "approved": return "Approved";
    case "level_changed": return "Level changed";
    case "rejected": return "Rejected";
  }
}

function statusColor(status: HeadingItem["review_status"]): string {
  switch (status) {
    case "detected": return "bg-yellow-100 text-yellow-800";
    case "approved": return "bg-green-100 text-green-800";
    case "level_changed": return "bg-blue-100 text-blue-800";
    case "rejected": return "bg-red-100 text-red-800";
  }
}

function levelBadge(level: number): string {
  return `H${level}`;
}

function levelColor(level: number): string {
  switch (level) {
    case 1: return "bg-purple-100 text-purple-900 font-bold";
    case 2: return "bg-indigo-100 text-indigo-900 font-semibold";
    case 3: return "bg-blue-100 text-blue-900";
    default: return "bg-gray-100 text-gray-700";
  }
}

export function HeadingCard({ heading, isSelected, onSelect }: Props) {
  return (
    <li
      className={`rounded-lg border p-3 cursor-pointer transition-colors ${
        isSelected
          ? "border-blue-500 bg-blue-50"
          : "border-gray-200 hover:border-gray-300 bg-white"
      }`}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`shrink-0 inline-flex items-center rounded px-2 py-0.5 text-xs font-mono ${levelColor(heading.level)}`}
          >
            {levelBadge(heading.level)}
          </span>
          <p className="text-sm font-medium text-gray-900 truncate">{heading.text}</p>
        </div>
        <span
          className={`shrink-0 inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${statusColor(heading.review_status)}`}
        >
          {statusLabel(heading.review_status)}
        </span>
      </div>
      <p className="text-xs text-gray-500">Page {heading.page_number}</p>
      {heading.reviewer_note && (
        <p className="mt-1 text-xs text-gray-500 italic truncate">{heading.reviewer_note}</p>
      )}
    </li>
  );
}
