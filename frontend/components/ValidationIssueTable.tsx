"use client";

import { useMemo, useState } from "react";
import type { Severity, ValidationIssue } from "@/lib/api";
import { SeverityBadge } from "./Badge";

const RULE_CATEGORY_LABELS: Record<string, string> = {
  DOC: "Document",
  HEADING: "Heading",
  PAGE: "Page",
  META: "Metadata",
  IMAGE: "Image",
  NOTE: "Footnote/Endnote",
  OCR: "OCR",
  TABLE: "Table",
  LIST: "List",
  CALLOUT: "Callout",
};

// PAGE_003 (reading-order anomalies) is split out from the generic
// "Page" category (page markers/sequencing, PAGE_001/002) since
// reading-order review is its own required workflow. Any *_VERIFY_*
// rule id (HEADING_VERIFY_004, LIST_VERIFY_002, ...) is cross-source
// Mathpix-vs-PDF verification output, grouped separately from the
// same object type's Phase-1 structural findings per the stitch
// validation-report reference.
function categoryOf(ruleId: string): string {
  if (ruleId === "PAGE_003") return "Reading order";
  if (ruleId.includes("_VERIFY_")) return "Cross-Source Verification";
  const prefix = ruleId.split("_")[0];
  return RULE_CATEGORY_LABELS[prefix] ?? prefix;
}

// Canonical display order — cross-source verification and structural
// document-level issues surface first, per-object categories follow.
const CATEGORY_ORDER = [
  "Cross-Source Verification",
  "Document",
  "Metadata",
  "Reading order",
  "Page",
  "Heading",
  "Image",
  "Table",
  "List",
  "Callout",
  "Footnote/Endnote",
  "OCR",
];

function sortCategories(categories: string[]): string[] {
  return [...categories].sort((a, b) => {
    const ai = CATEGORY_ORDER.indexOf(a);
    const bi = CATEGORY_ORDER.indexOf(b);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return a.localeCompare(b);
  });
}

function issueKey(issue: ValidationIssue): string {
  return `${issue.rule_id}:${issue.page_number}`;
}

export function ValidationIssueTable({ issues, onJump }: { issues: ValidationIssue[]; onJump?: (pageNumber: number) => void }) {
  const [severityFilter, setSeverityFilter] = useState<Severity | "all">("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [ignored, setIgnored] = useState<Set<string>>(new Set());
  const [deferred, setDeferred] = useState<Set<string>>(new Set());
  const [showIgnored, setShowIgnored] = useState(false);

  function toggleIgnore(issue: ValidationIssue) {
    const k = issueKey(issue);
    setIgnored((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k); else next.add(k);
      return next;
    });
  }

  function toggleDefer(issue: ValidationIssue) {
    const k = issueKey(issue);
    setDeferred((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k); else next.add(k);
      return next;
    });
  }

  const categories = useMemo(() => {
    const set = new Set(issues.map((issue) => categoryOf(issue.rule_id)));
    return sortCategories(Array.from(set));
  }, [issues]);

  const filtered = issues.filter((issue) => {
    if (!showIgnored && ignored.has(issueKey(issue))) return false;
    if (severityFilter !== "all" && issue.severity !== severityFilter) return false;
    if (categoryFilter !== "all" && categoryOf(issue.rule_id) !== categoryFilter) return false;
    return true;
  });

  const grouped = useMemo(() => {
    const byCategory = new Map<string, ValidationIssue[]>();
    for (const issue of filtered) {
      const cat = categoryOf(issue.rule_id);
      const list = byCategory.get(cat) ?? [];
      list.push(issue);
      byCategory.set(cat, list);
    }
    return sortCategories(Array.from(byCategory.keys())).map((cat) => ({
      category: cat,
      issues: byCategory.get(cat)!,
    }));
  }, [filtered]);

  if (issues.length === 0) {
    return <p className="text-sm text-text-secondary">No validation issues were found for this document.</p>;
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
        <span className="text-sm text-text-secondary">
          {filtered.length} of {issues.length} issue{issues.length === 1 ? "" : "s"}
        </span>
      </div>

      {filtered.length === 0 && (
        <p className="rounded-lg border border-border p-4 text-sm text-text-secondary">
          No issues match the current filters.
        </p>
      )}

      <div className="space-y-3">
        {grouped.map(({ category, issues: categoryIssues }) => (
          <details key={category} className="rounded-lg border border-border bg-surface-panel" open>
            <summary className="cursor-pointer select-none px-4 py-2.5 text-sm font-semibold text-text-primary">
              {category}{" "}
              <span className="font-mono text-xs font-normal text-text-secondary">
                ({categoryIssues.length})
              </span>
            </summary>
            <ul className="divide-y divide-border border-t border-border">
              {categoryIssues.map((issue, index) => {
                const k = issueKey(issue);
                const isIgnored = ignored.has(k);
                const isDeferredIssue = deferred.has(k);
                return (
                  <li
                    key={`${issue.rule_id}-${issue.page_number}-${index}`}
                    className={`p-4 ${isIgnored ? "opacity-50" : ""}`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <SeverityBadge severity={issue.severity} />
                      <span className="font-mono text-xs text-text-secondary">{issue.rule_id}</span>
                      {issue.page_number !== null && (
                        <span className="text-xs text-text-secondary">Page {issue.page_number}</span>
                      )}
                      {isDeferredIssue && (
                        <span className="rounded bg-warning/15 px-1.5 py-0.5 text-[10px] font-medium text-warning">
                          Review later
                        </span>
                      )}
                      {isIgnored && (
                        <span className="rounded bg-surface-elevated px-1.5 py-0.5 text-[10px] font-medium text-text-secondary">
                          Ignored
                        </span>
                      )}
                      <div className="ml-auto flex items-center gap-1">
                        {onJump && issue.page_number !== null && !isIgnored && (
                          <button
                            type="button"
                            onClick={() => onJump(issue.page_number!)}
                            className="rounded border border-border px-2 py-0.5 text-xs font-medium text-accent hover:bg-hover-row"
                          >
                            Fix
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => toggleDefer(issue)}
                          className={`rounded border px-2 py-0.5 text-xs font-medium transition-colors ${
                            isDeferredIssue
                              ? "border-warning/40 text-warning hover:bg-warning/10"
                              : "border-border text-text-secondary hover:bg-hover-row"
                          }`}
                        >
                          {isDeferredIssue ? "Undefer" : "Review later"}
                        </button>
                        <button
                          type="button"
                          onClick={() => toggleIgnore(issue)}
                          className={`rounded border px-2 py-0.5 text-xs font-medium transition-colors ${
                            isIgnored
                              ? "border-border text-text-secondary hover:bg-hover-row"
                              : "border-border text-text-secondary hover:bg-hover-row"
                          }`}
                        >
                          {isIgnored ? "Unignore" : "Ignore"}
                        </button>
                      </div>
                    </div>
                    <p className="mt-2 text-sm text-text-primary">{issue.message}</p>
                    {issue.suggested_action && (
                      <p className="mt-1 text-sm text-text-secondary">
                        <span className="font-medium">Suggested action: </span>
                        {issue.suggested_action}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          </details>
        ))}
      </div>

      {ignored.size > 0 && (
        <button
          type="button"
          onClick={() => setShowIgnored((v) => !v)}
          className="mt-2 text-xs text-text-secondary hover:text-text-primary"
        >
          {showIgnored ? "Hide" : "Show"} {ignored.size} ignored issue{ignored.size !== 1 ? "s" : ""}
        </button>
      )}
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
    <label className="flex items-center gap-2 text-sm text-text-secondary">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-border bg-surface-canvas px-2 py-1 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
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
