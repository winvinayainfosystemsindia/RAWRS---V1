"use client";

import { useMemo, useState } from "react";
import type { Severity, ValidationIssue } from "@/lib/api";
import { SeverityBadge } from "./Badge";

const RULE_CATEGORY_LABELS: Record<string, string> = {
  DOC: "Document",
  HEADING: "Heading",
  PAGE: "Page",
  IMAGE: "Image",
  NOTE: "Footnote/Endnote",
  OCR: "OCR",
};

// PAGE_003 (reading-order anomalies) is split out from the generic
// "Page" category (page markers/sequencing, PAGE_001/002) since
// reading-order review is its own required workflow.
function categoryOf(ruleId: string): string {
  if (ruleId === "PAGE_003") return "Reading order";
  const prefix = ruleId.split("_")[0];
  return RULE_CATEGORY_LABELS[prefix] ?? prefix;
}

export function ValidationIssueTable({ issues }: { issues: ValidationIssue[] }) {
  const [severityFilter, setSeverityFilter] = useState<Severity | "all">("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");

  const categories = useMemo(() => {
    const set = new Set(issues.map((issue) => categoryOf(issue.rule_id)));
    return Array.from(set).sort();
  }, [issues]);

  const filtered = issues.filter((issue) => {
    if (severityFilter !== "all" && issue.severity !== severityFilter) return false;
    if (categoryFilter !== "all" && categoryOf(issue.rule_id) !== categoryFilter) return false;
    return true;
  });

  if (issues.length === 0) {
    return <p className="text-sm text-gray-600">No validation issues were found for this document.</p>;
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <FilterSelect
          label="Severity"
          value={severityFilter}
          onChange={(v) => setSeverityFilter(v as Severity | "all")}
          options={[
            { value: "all", label: "All severities" },
            { value: "error", label: "Error" },
            { value: "warning", label: "Warning" },
            { value: "info", label: "Info" },
          ]}
        />
        <FilterSelect
          label="Category"
          value={categoryFilter}
          onChange={setCategoryFilter}
          options={[
            { value: "all", label: "All categories" },
            ...categories.map((c) => ({ value: c, label: c })),
          ]}
        />
        <span className="text-sm text-gray-500">
          {filtered.length} of {issues.length} issue{issues.length === 1 ? "" : "s"}
        </span>
      </div>

      <ul className="divide-y divide-gray-200 rounded-lg border border-gray-200">
        {filtered.map((issue, index) => (
          <li key={`${issue.rule_id}-${issue.page_number}-${index}`} className="p-4">
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge severity={issue.severity} />
              <span className="font-mono text-xs text-gray-500">{issue.rule_id}</span>
              {issue.page_number !== null && (
                <span className="text-xs text-gray-500">Page {issue.page_number}</span>
              )}
            </div>
            <p className="mt-2 text-sm text-gray-900">{issue.message}</p>
            {issue.suggested_action && (
              <p className="mt-1 text-sm text-gray-500">
                <span className="font-medium">Suggested action: </span>
                {issue.suggested_action}
              </p>
            )}
          </li>
        ))}
        {filtered.length === 0 && (
          <li className="p-4 text-sm text-gray-500">No issues match the current filters.</li>
        )}
      </ul>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-gray-700">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-gray-300 bg-white px-2 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}
