"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type CorrectionItem } from "@/lib/api";
import { STATUS_TABS, isResolved, statusTabMatches, type StatusTab } from "@/lib/correctionFilters";
import { useDocumentData, useDocumentDispatch, selectCorrections } from "@/lib/store/DocumentDataContext";
import { useSelection } from "@/lib/store/SelectionContext";
import { usePdfViewport } from "@/lib/store/PdfViewportContext";
import { CorrectionHistoryList } from "@/components/CorrectionHistoryList";
import { useListReviewKeyboard } from "@/lib/hooks/useListReviewKeyboard";
import { usePersistedState } from "@/lib/hooks/usePersistedState";
import { useReviewAction } from "@/lib/hooks/useReviewAction";
import { useReviewQueue } from "@/lib/store/ReviewQueueContext";
import { useToast } from "@/components/Toast";

type SortKey = "document_order" | "confidence" | "page_number" | "priority";

const SORT_OPTIONS: { id: SortKey; label: string }[] = [
  { id: "priority", label: "Priority" },
  { id: "document_order", label: "Document Order" },
  { id: "confidence", label: "Confidence" },
  { id: "page_number", label: "Page Number" },
];

function priorityScore(c: CorrectionItem): number {
  let score = 0;
  if (c.severity === "error") score += 300;
  else if (c.severity === "warning") score += 200;
  else score += 100;
  score += Math.round((c.confidence ?? 0) * 100);
  return score;
}

const ANY = "__any__";

function matchesSearch(c: CorrectionItem, query: string): boolean {
  if (!query) return true;
  const haystack = `${c.problem} ${c.reason} ${c.current_value} ${c.suggested_value} ${c.rule_id ?? ""}`.toLowerCase();
  return haystack.includes(query.toLowerCase());
}

// The Reviewer Workspace (M-4) — fills the "Review Queue" slot
// OutputWorkspace.tsx previously listed under SOON_TABS. One-item-at-a-time
// triage over the same document.corrections the Corrections bottom panel
// already lists, reusing CorrectionRow (via CorrectionHistoryList) for the
// actual card — no second proposal-card implementation. Selecting the
// current item syncs ContextInspectorRail (existing SelectionContext) and
// jumps the PDF (usePdfViewport — the same call SemanticNavTree/
// ContextInspectorRail already make) to the affected page.
//
// Filter/sort/search all run client-side over the already-fetched
// correction list — per-document volumes measured so far are in the low
// hundreds, not thousands (see Phase M-4 design review), so this is not a
// premature optimization to skip. `filtered` below is the exact seam a
// later virtualized-list pass would wrap, without touching the filter/sort
// logic itself.
export function ReviewerWorkspace({ jobId }: { jobId: string }) {
  const state = useDocumentData();
  const dispatch = useDocumentDispatch();
  const { select } = useSelection();
  const { jumpToObject } = usePdfViewport();
  const { review, refreshIntelligence } = useReviewAction(jobId);
  const { toast } = useToast();
  // Asset-type filter is the shared, persisted queue filter (P1-6/P1-7):
  // category cards in the Accessibility Center set it, and it survives reloads.
  const { objectTypeFilter: assetType, setObjectTypeFilter: setAssetType } = useReviewQueue();
  const corrections = selectCorrections(state);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const [statusTab, setStatusTab] = usePersistedState<StatusTab>("rawrs:rw:statusTab", "pending");
  const [severity, setSeverity] = useState<string>(ANY);
  const [ruleId, setRuleId] = useState<string>(ANY);
  const [minConfidence, setMinConfidence] = useState<string>("");
  const [pageFilter, setPageFilter] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const [sortKey, setSortKey] = usePersistedState<SortKey>("rawrs:rw:sortKey", "priority");
  const [index, setIndex] = useState(0);

  const assetTypeOptions = useMemo(
    () => Array.from(new Set(corrections.map((c) => c.object_type))).sort(),
    [corrections]
  );
  const severityOptions = useMemo(
    () => Array.from(new Set(corrections.map((c) => c.severity).filter((s): s is string => s !== null))).sort(),
    [corrections]
  );
  const ruleIdOptions = useMemo(
    () => Array.from(new Set(corrections.map((c) => c.rule_id).filter((r): r is string => r !== null))).sort(),
    [corrections]
  );

  const filtered = useMemo(() => {
    const minConf = minConfidence.trim() === "" ? null : Number(minConfidence) / 100;
    const page = pageFilter.trim() === "" ? null : Number(pageFilter);

    const result = corrections.filter((c) => {
      if (!statusTabMatches(c, statusTab)) return false;
      if (assetType !== ANY && c.object_type !== assetType) return false;
      if (severity !== ANY && c.severity !== severity) return false;
      if (ruleId !== ANY && c.rule_id !== ruleId) return false;
      if (minConf !== null && (c.confidence === null || c.confidence < minConf)) return false;
      if (page !== null && c.page_number !== page) return false;
      if (!matchesSearch(c, search)) return false;
      return true;
    });

    const sorted = [...result].sort((a, b) => {
      if (sortKey === "priority") return priorityScore(b) - priorityScore(a);
      if (sortKey === "confidence") return (b.confidence ?? -1) - (a.confidence ?? -1);
      if (sortKey === "page_number") return (a.page_number ?? Infinity) - (b.page_number ?? Infinity);
      return a.created_at.localeCompare(b.created_at);
    });

    return sorted;
  }, [corrections, statusTab, assetType, severity, ruleId, minConfidence, pageFilter, search, sortKey]);

  // Derived during render, not clamped via a setState-in-effect: when the
  // filtered set shrinks (a decision moves the current item out of view,
  // or a filter narrows the set), this keeps the pointer valid without an
  // extra render.
  const clampedIndex = Math.min(index, Math.max(0, filtered.length - 1));
  const current = filtered[clampedIndex] ?? null;

  // Sync the rest of the workspace to whichever proposal is currently
  // focused — reuses the existing selection mechanism and the same
  // select()+jumpToObject() pairing SemanticNavTree/ContextInspectorRail
  // already use, rather than a new sync channel.
  useEffect(() => {
    if (!current) return;
    select("correction", current.correction_id);
    if (current.page_number !== null) jumpToObject(current.page_number, null);
  }, [current, select, jumpToObject]);

  // When the shared asset-type filter changes (e.g. a category card in the
  // Accessibility Center set it), land on the first matching item.
  useEffect(() => {
    setIndex(0);
  }, [assetType]);

  const totalCount = corrections.length;
  const reviewedCount = corrections.filter(isResolved).length;
  const acceptedCount = corrections.filter((c) => c.status === "accepted" || c.status === "auto_applied" || c.status === "edited").length;
  const rejectedCount = corrections.filter((c) => c.status === "rejected").length;
  const ignoredCount = corrections.filter((c) => c.status === "ignored").length;

  function handleUpdated(updated: CorrectionItem) {
    dispatch({ type: "UPDATE_CORRECTION", correction: updated });
  }

  function resetToFirst() {
    setIndex(0);
  }

  const runAction = useCallback(
    async (action: "accept" | "reject" | "ignore" | "undo") => {
      if (!current) return;
      // Shared pipeline (P1-5): keyboard actions now get the exact toast +
      // undo + error handling + live-score refresh the buttons get. The
      // shared hook already surfaces failures via toast, so a throw here just
      // stops the auto-advance rather than needing its own UI.
      try {
        await review(current, action);
      } catch {
        /* surfaced by the shared pipeline's toast */
      }
      // ponytail: auto-advance — the resolved item leaves the "pending"
      // filter on next render, so the same clampedIndex naturally points
      // to the next item. No explicit index bump needed.
    },
    [current, review]
  );

  // Bulk review (P2-9): accept every high-confidence pending item in the
  // current view in one action, with a single Undo-all. High confidence =
  // the same ≥0.95 threshold the card labels "Very High" — the items that
  // need the least human judgement. Per-item toast/refresh are suppressed;
  // one summary toast and one score refresh fire at the end.
  const HIGH_CONF = 0.95;
  const [bulkRunning, setBulkRunning] = useState(false);
  const highConfidencePending = useMemo(
    () => filtered.filter((c) => !isResolved(c) && (c.confidence ?? 0) >= HIGH_CONF),
    [filtered]
  );

  async function acceptAllHighConfidence() {
    if (bulkRunning || highConfidencePending.length === 0) return;
    setBulkRunning(true);
    const batch = highConfidencePending;
    let ok = 0;
    for (const c of batch) {
      try {
        await review(c, "accept", { silent: true, skipRefresh: true });
        ok++;
      } catch {
        /* individual failure already toasted by the pipeline */
      }
    }
    await refreshIntelligence();
    setBulkRunning(false);
    toast(`Accepted ${ok} high-confidence correction${ok === 1 ? "" : "s"}`, {
      label: "Undo all",
      onClick: async () => {
        for (const c of batch) {
          try {
            await review(c, "undo", { silent: true, skipRefresh: true });
          } catch {
            /* ignore */
          }
        }
        await refreshIntelligence();
        toast(`Reverted ${batch.length} correction${batch.length === 1 ? "" : "s"}`);
      },
    });
  }

  // M-4.3 (Proposal Review Experience) — keyboard-first review, now built
  // on the shared useListReviewKeyboard hook (Phase F-3.1) so any future
  // workspace extends this exact reference implementation instead of a
  // second, parallel shortcut scheme. Ignored while focus is inside a text
  // input/textarea/select (search box, the Proposal Card's edit-value/
  // reviewer-notes fields) so shortcut letters don't fight with normal
  // typing — see the on-screen legend below for the full, documented list.
  const keyActions = useMemo(
    () => ({
      a: () => runAction("accept"),
      r: () => runAction("reject"),
      i: () => runAction("ignore"),
      u: () => runAction("undo"),
      // Open Inspector: re-affirms the sync to the right-rail Inspector —
      // meaningful if the reviewer navigated it away.
      e: () => current && select("correction", current.correction_id),
      // Jump to PDF: jumpToObject's nonce always bumps (see
      // PdfViewportContext.tsx), so re-jumping to the same page still
      // re-triggers the PDF pane's scroll/highlight.
      j: () => current?.page_number !== null && current && jumpToObject(current.page_number, null),
    }),
    [runAction, current, select, jumpToObject]
  );

  useListReviewKeyboard({
    onNext: () => setIndex(Math.min(filtered.length - 1, clampedIndex + 1)),
    onPrev: () => setIndex(Math.max(0, clampedIndex - 1)),
    onSearch: () => searchInputRef.current?.focus(),
    keyActions,
  });

  const insight = useMemo(() => {
    if (corrections.length < 3) return null;
    const typeCounts = new Map<string, number>();
    for (const c of corrections) {
      typeCounts.set(c.object_type, (typeCounts.get(c.object_type) ?? 0) + 1);
    }
    const dominant = [...typeCounts.entries()].sort((a, b) => b[1] - a[1])[0];
    if (!dominant) return null;
    const pct = Math.round((dominant[1] / corrections.length) * 100);
    if (pct < 40) return null;
    const pending = corrections.filter((c) => !isResolved(c));
    const blockingCount = pending.filter((c) => c.severity === "error").length;
    const parts: string[] = [];
    parts.push(`${pct}% of issues are ${dominant[0]} corrections.`);
    if (blockingCount > 0) parts.push(`${blockingCount} blocking issue${blockingCount === 1 ? "" : "s"} remain.`);
    return parts.join(" ");
  }, [corrections]);

  if (corrections.length === 0) {
    return (
      <p className="text-sm text-text-secondary">
        No cross-source corrections were proposed for this document.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Insight card */}
      {insight && (
        <p className="rounded-lg border border-accent/20 bg-accent/5 px-3 py-2 text-xs text-text-secondary">
          {insight}
        </p>
      )}

      {/* Progress */}
      <div className="flex items-center justify-between text-xs text-text-secondary">
        <span>
          {reviewedCount} / {totalCount} reviewed
          {reviewedCount > 0 && (
            <span className="ml-2 text-text-secondary/70">
              {acceptedCount} accepted · {rejectedCount} rejected · {ignoredCount} ignored
            </span>
          )}
        </span>
        {filtered.length > 0 && (
          <span>
            {clampedIndex + 1} / {filtered.length} in this view
          </span>
        )}
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-elevated">
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${totalCount ? Math.round((reviewedCount / totalCount) * 100) : 0}%` }}
        />
      </div>

      {/* Status tabs */}
      <div className="flex items-center rounded-lg border border-border bg-surface-panel p-1">
        {STATUS_TABS.map((tab) => {
          const count = corrections.filter((c) => statusTabMatches(c, tab.id)).length;
          const isActive = statusTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => {
                setStatusTab(tab.id);
                resetToFirst();
              }}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                isActive
                  ? "bg-surface-elevated text-text-primary"
                  : "text-text-secondary hover:text-text-primary"
              }`}
            >
              {tab.label}
              {count > 0 && (
                <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-surface-canvas px-1 font-mono text-[10px] text-text-secondary">
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Search + sort */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={searchInputRef}
          type="text"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            resetToFirst();
          }}
          placeholder="Search problem, reason, values, rule…"
          aria-label="Search corrections"
          className="min-w-[220px] flex-1 rounded border border-border bg-surface-canvas px-2 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
        />
        <label className="flex items-center gap-1.5 text-xs text-text-secondary">
          Sort
          <select
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
            className="rounded border border-border bg-surface-canvas px-2 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1.5 text-xs text-text-secondary">
          Asset Type
          <select
            value={assetType}
            onChange={(e) => {
              setAssetType(e.target.value);
              resetToFirst();
            }}
            className="rounded border border-border bg-surface-canvas px-2 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
          >
            <option value={ANY}>Any</option>
            {assetTypeOptions.map((t) => (
              <option key={t} value={t}>
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-1.5 text-xs text-text-secondary">
          Severity
          <select
            value={severity}
            onChange={(e) => {
              setSeverity(e.target.value);
              resetToFirst();
            }}
            className="rounded border border-border bg-surface-canvas px-2 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
          >
            <option value={ANY}>Any</option>
            {severityOptions.map((s) => (
              <option key={s} value={s}>
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-1.5 text-xs text-text-secondary">
          Rule
          <select
            value={ruleId}
            onChange={(e) => {
              setRuleId(e.target.value);
              resetToFirst();
            }}
            className="rounded border border-border bg-surface-canvas px-2 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
          >
            <option value={ANY}>Any</option>
            {ruleIdOptions.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-1.5 text-xs text-text-secondary">
          Min Confidence %
          <input
            type="number"
            min={0}
            max={100}
            value={minConfidence}
            onChange={(e) => {
              setMinConfidence(e.target.value);
              resetToFirst();
            }}
            placeholder="e.g. 95"
            className="w-20 rounded border border-border bg-surface-canvas px-2 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
          />
        </label>

        <label className="flex items-center gap-1.5 text-xs text-text-secondary">
          Page
          <input
            type="number"
            min={1}
            value={pageFilter}
            onChange={(e) => {
              setPageFilter(e.target.value);
              resetToFirst();
            }}
            placeholder="e.g. 128"
            className="w-20 rounded border border-border bg-surface-canvas px-2 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
          />
        </label>
      </div>

      {/* Prev / Next */}
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => setIndex(Math.max(0, clampedIndex - 1))}
          disabled={clampedIndex === 0}
          className="rounded border border-border px-3 py-1.5 text-sm font-medium text-text-primary hover:bg-hover-row disabled:opacity-40"
        >
          ← Previous
        </button>
        <button
          type="button"
          onClick={() => setIndex(Math.min(filtered.length - 1, clampedIndex + 1))}
          disabled={clampedIndex >= filtered.length - 1}
          className="rounded border border-border px-3 py-1.5 text-sm font-medium text-text-primary hover:bg-hover-row disabled:opacity-40"
        >
          Next →
        </button>
      </div>

      {/* Bulk review (P2-9) — only offered when there are high-confidence
          items to clear; the reviewer's scarce attention is better spent on
          the ambiguous ones. Every accept is individually undoable via the
          summary toast's Undo-all. */}
      {statusTab === "pending" && highConfidencePending.length > 1 && (
        <button
          type="button"
          onClick={acceptAllHighConfidence}
          disabled={bulkRunning}
          className="rounded-lg border border-success/40 bg-success/5 px-3 py-2 text-sm font-medium text-success hover:bg-success/10 disabled:opacity-50"
        >
          {bulkRunning
            ? "Accepting…"
            : `Accept ${highConfidencePending.length} high-confidence corrections in view`}
        </button>
      )}

      {/* Keyboard shortcuts legend — documented per the shortcuts
          themselves, not just implemented silently. */}
      <p className="text-xs text-text-secondary/70">
        Keyboard: <kbd className="rounded border border-border px-1">n</kbd>/
        <kbd className="rounded border border-border px-1">→</kbd> next ·{" "}
        <kbd className="rounded border border-border px-1">p</kbd>/
        <kbd className="rounded border border-border px-1">←</kbd> previous ·{" "}
        <kbd className="rounded border border-border px-1">a</kbd> accept ·{" "}
        <kbd className="rounded border border-border px-1">r</kbd> reject ·{" "}
        <kbd className="rounded border border-border px-1">i</kbd> ignore ·{" "}
        <kbd className="rounded border border-border px-1">u</kbd> undo ·{" "}
        <kbd className="rounded border border-border px-1">e</kbd> open inspector ·{" "}
        <kbd className="rounded border border-border px-1">j</kbd> jump to PDF ·{" "}
        <kbd className="rounded border border-border px-1">/</kbd> focus search
      </p>

      {/* Current proposal — reuses CorrectionRow via CorrectionHistoryList,
          not a second card implementation. */}
      {current ? (
        <CorrectionHistoryList corrections={[current]} jobId={jobId} onUpdated={handleUpdated} />
      ) : (
        <p className="rounded-lg border border-border p-4 text-sm text-text-secondary">
          No corrections match the current filters.
        </p>
      )}
    </div>
  );
}
