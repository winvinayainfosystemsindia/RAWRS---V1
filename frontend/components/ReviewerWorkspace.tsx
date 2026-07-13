"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type CorrectionItem } from "@/lib/api";
import { STATUS_TABS, isResolved, statusTabMatches, type StatusTab } from "@/lib/correctionFilters";
import { useDocumentData, useDocumentDispatch, selectCorrections } from "@/lib/store/DocumentDataContext";
import { useSelection } from "@/lib/store/SelectionContext";
import { usePdfViewport } from "@/lib/store/PdfViewportContext";
import { CorrectionHistoryList } from "@/components/CorrectionHistoryList";

type SortKey = "document_order" | "confidence" | "page_number";

const SORT_OPTIONS: { id: SortKey; label: string }[] = [
  { id: "document_order", label: "Document Order" },
  { id: "confidence", label: "Confidence" },
  { id: "page_number", label: "Page Number" },
];

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
  const corrections = selectCorrections(state);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const [statusTab, setStatusTab] = useState<StatusTab>("pending");
  const [assetType, setAssetType] = useState<string>(ANY);
  const [severity, setSeverity] = useState<string>(ANY);
  const [ruleId, setRuleId] = useState<string>(ANY);
  const [minConfidence, setMinConfidence] = useState<string>("");
  const [pageFilter, setPageFilter] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const [sortKey, setSortKey] = useState<SortKey>("document_order");
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
      if (sortKey === "confidence") return (b.confidence ?? -1) - (a.confidence ?? -1);
      if (sortKey === "page_number") return (a.page_number ?? Infinity) - (b.page_number ?? Infinity);
      // document_order: corrections are appended in the order each
      // verifier generated them during the pipeline run, which created_at
      // (microsecond resolution) preserves — no separate ordinal exists.
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

  const totalCount = corrections.length;
  const reviewedCount = corrections.filter(isResolved).length;

  function handleUpdated(updated: CorrectionItem) {
    dispatch({ type: "UPDATE_CORRECTION", correction: updated });
  }

  function resetToFirst() {
    setIndex(0);
  }

  // Keyboard-first review actions call the same generic Corrections API
  // CorrectionRow's own buttons call — one endpoint, two triggers (mouse,
  // keyboard), not a second business-logic path.
  const runAction = useCallback(
    async (action: "accept" | "reject" | "ignore" | "undo") => {
      if (!current) return;
      const updated = await api.reviewCorrection(jobId, current.correction_id, { action });
      dispatch({ type: "UPDATE_CORRECTION", correction: updated });
    },
    [current, jobId, dispatch]
  );

  // M-4.3 (Proposal Review Experience) — keyboard-first review. Ignored
  // while focus is inside a text input/textarea/select (search box, the
  // Proposal Card's edit-value/reviewer-notes fields) so shortcut letters
  // don't fight with normal typing. See the on-screen legend below for the
  // full, documented list.
  useEffect(() => {
    function isTypingTarget(el: EventTarget | null): boolean {
      const tag = (el as HTMLElement | null)?.tagName;
      return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
    }

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "/" && !isTypingTarget(e.target)) {
        e.preventDefault();
        searchInputRef.current?.focus();
        return;
      }
      if (isTypingTarget(e.target)) return;

      switch (e.key) {
        case "ArrowRight":
        case "n":
          setIndex(Math.min(filtered.length - 1, clampedIndex + 1));
          break;
        case "ArrowLeft":
        case "p":
          setIndex(Math.max(0, clampedIndex - 1));
          break;
        case "a":
          runAction("accept");
          break;
        case "r":
          runAction("reject");
          break;
        case "i":
          runAction("ignore");
          break;
        case "u":
          runAction("undo");
          break;
        case "e":
          // Open Inspector: re-affirms the sync to the right-rail
          // Inspector — meaningful if the reviewer navigated it away.
          if (current) select("correction", current.correction_id);
          break;
        case "j":
          // Jump to PDF: jumpToObject's nonce always bumps (see
          // PdfViewportContext.tsx), so re-jumping to the same page still
          // re-triggers the PDF pane's scroll/highlight.
          if (current?.page_number !== null && current) jumpToObject(current.page_number, null);
          break;
        default:
          break;
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [current, clampedIndex, filtered.length, select, jumpToObject, runAction]);

  if (corrections.length === 0) {
    return (
      <p className="text-sm text-text-secondary">
        No cross-source corrections were proposed for this document.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Progress */}
      <div className="flex items-center justify-between text-xs text-text-secondary">
        <span>
          {reviewedCount} / {totalCount} reviewed
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
