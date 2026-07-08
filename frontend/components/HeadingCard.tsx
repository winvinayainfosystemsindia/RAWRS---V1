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
    case "detected": return "bg-warning/10 text-warning";
    case "approved": return "bg-success/10 text-success";
    case "level_changed": return "bg-accent/10 text-accent";
    case "rejected": return "bg-danger/10 text-danger";
  }
}

function levelBadge(level: number): string {
  return `H${level}`;
}

function levelColor(level: number): string {
  switch (level) {
    case 1: return "bg-accent/10 text-accent font-bold";
    case 2: return "bg-accent/10 text-accent font-semibold";
    case 3: return "bg-accent/10 text-accent";
    default: return "bg-hover-row text-text-secondary";
  }
}

export function HeadingCard({ heading, isSelected, onSelect }: Props) {
  return (
    <li
      className={`rounded-lg border p-3 cursor-pointer transition-colors ${
        isSelected
          ? "border-accent bg-accent/10"
          : "border-border hover:border-border-strong bg-surface-elevated"
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
          <p className="text-sm font-medium text-text-primary truncate">{heading.text}</p>
        </div>
        <span
          className={`shrink-0 inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${statusColor(heading.review_status)}`}
        >
          {statusLabel(heading.review_status)}
        </span>
      </div>
      <p className="text-xs text-text-secondary">Page {heading.page_number}</p>
      {heading.reviewer_note && (
        <p className="mt-1 text-xs text-text-secondary italic truncate">{heading.reviewer_note}</p>
      )}
    </li>
  );
}
