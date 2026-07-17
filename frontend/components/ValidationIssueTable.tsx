"use client";

import { useMemo, useState } from "react";
import { api, type ReadinessReport, type Severity, type ValidationIssue } from "@/lib/api";
import { SeverityBadge } from "./Badge";
import { useArrowKeyTabs } from "@/lib/hooks/useArrowKeyTabs";
import { IconCheckCircle, IconWarningTriangle } from "@/components/icons";
import { categoryOf, sortCategories } from "@/lib/validationCategories";

interface Props {
  issues: ValidationIssue[];
  onJump?: (pageNumber: number) => void;
  // Both optional so ValidationIssueTable still works read-only (e.g. a
  // summary embed) wherever a caller doesn't wire up persistence.
  jobId?: string;
  onIssueUpdated?: (issue: ValidationIssue) => void;
  // Optional — when supplied, renders a one-line running score so a
  // reviewer can gauge document health without opening a separate
  // dashboard (Design Bible §10; reuses GET /readiness, already fetched
  // into DocumentDataContext — no new backend capability).
  readiness?: ReadinessReport | null;
}

const SEVERITY_TABS: { id: Severity | "all"; label: string }[] = [
  { id: "all", label: "All" },
  { id: "error", label: "Errors" },
  { id: "warning", label: "Warnings" },
  { id: "info", label: "Info" },
];
const SEVERITY_TAB_IDS = SEVERITY_TABS.map((t) => t.id);

export function ValidationIssueTable({ issues, onJump, jobId, onIssueUpdated, readiness }: Props) {
  const [severityFilter, setSeverityFilter] = useState<Severity | "all">("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [showIgnored, setShowIgnored] = useState(false);
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());

  async function setStatus(issue: ValidationIssue, action: "ignore" | "defer" | "reopen") {
    if (!jobId) return;
    setPendingIds((prev) => new Set(prev).add(issue.issue_id));
    try {
      const updated = await api.reviewValidationIssue(jobId, issue.issue_id, { action });
      onIssueUpdated?.(updated);
    } finally {
      setPendingIds((prev) => {
        const next = new Set(prev);
        next.delete(issue.issue_id);
        return next;
      });
    }
  }

  function toggleIgnore(issue: ValidationIssue) {
    setStatus(issue, issue.status === "ignored" ? "reopen" : "ignore");
  }

  function toggleDefer(issue: ValidationIssue) {
    setStatus(issue, issue.status === "deferred" ? "reopen" : "defer");
  }

  const categories = useMemo(() => {
    const set = new Set(issues.map((issue) => categoryOf(issue.rule_id)));
    return sortCategories(Array.from(set));
  }, [issues]);

  const ignoredCount = issues.filter((i) => i.status === "ignored").length;

  const severityCounts = useMemo(() => {
    const counts: Record<Severity, number> = { error: 0, warning: 0, info: 0 };
    for (const issue of issues) counts[issue.severity]++;
    return counts;
  }, [issues]);

  // Phase R-1.1 — a genuine tabs case (swaps which issues are visible),
  // not a filter-checkbox case, so this reuses the shared ARIA-tabs hook
  // (F-3.2) instead of the plain <select> it replaces.
  const severityTabs = useArrowKeyTabs({
    ids: SEVERITY_TAB_IDS,
    active: severityFilter,
    onChange: setSeverityFilter,
  });

  const filtered = issues.filter((issue) => {
    if (!showIgnored && issue.status === "ignored") return false;
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

  const readinessBanner = readiness && (
    <div className="mb-3 flex items-center gap-3">
      <span
        className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-sm font-semibold ${
          readiness.ready ? "bg-success/10 text-success" : "bg-warning/10 text-warning"
        }`}
      >
        {readiness.ready ? (
          <IconCheckCircle className="h-4 w-4 shrink-0" />
        ) : (
          <IconWarningTriangle className="h-4 w-4 shrink-0" />
        )}
        {readiness.ready ? "Export Ready" : "Not Yet Ready"}
      </span>
      <span className="text-sm text-text-secondary">Score {Math.round(readiness.overall_score * 100)}%</span>
    </div>
  );

  if (issues.length === 0) {
    return (
      <div>
        {readinessBanner}
        <p className="text-sm text-text-secondary">No validation issues were found for this document.</p>
      </div>
    );
  }

  return (
    <div>
      {readinessBanner}

      <div
        role="tablist"
        aria-label="Filter by severity"
        ref={severityTabs.tablistRef as React.RefObject<HTMLDivElement>}
        className="mb-3 flex items-center gap-1"
      >
        {SEVERITY_TABS.map((tab) => (
          <button
            key={tab.id}
            {...severityTabs.getTabProps(tab.id)}
            className={`rounded px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
              severityFilter === tab.id
                ? "bg-accent text-accent-contrast"
                : "text-text-secondary hover:bg-hover-row hover:text-text-primary"
            }`}
          >
            {tab.label}
            {tab.id !== "all" && (
              <span className="ml-1.5 font-mono text-[10px] opacity-80">{severityCounts[tab.id]}</span>
            )}
          </button>
        ))}
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3">
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
                const isIgnored = issue.status === "ignored";
                const isDeferredIssue = issue.status === "deferred";
                const isPending = pendingIds.has(issue.issue_id);
                return (
                  <li
                    key={issue.issue_id || `${issue.rule_id}-${issue.page_number}-${index}`}
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
                        {jobId && (
                          <>
                            <button
                              type="button"
                              onClick={() => toggleDefer(issue)}
                              disabled={isPending}
                              className={`rounded border px-2 py-0.5 text-xs font-medium transition-colors disabled:opacity-40 ${
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
                              disabled={isPending}
                              className="rounded border border-border px-2 py-0.5 text-xs font-medium text-text-secondary transition-colors hover:bg-hover-row disabled:opacity-40"
                            >
                              {isIgnored ? "Unignore" : "Ignore"}
                            </button>
                          </>
                        )}
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

      {ignoredCount > 0 && (
        <button
          type="button"
          onClick={() => setShowIgnored((v) => !v)}
          className="mt-2 text-xs text-text-secondary hover:text-text-primary"
        >
          {showIgnored ? "Hide" : "Show"} {ignoredCount} ignored issue{ignoredCount !== 1 ? "s" : ""}
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
        className="rounded border border-border bg-surface-canvas px-2 py-1 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
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
