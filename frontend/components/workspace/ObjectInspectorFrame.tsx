"use client";

import { useState, type ReactNode } from "react";
import { useArrowKeyTabs } from "@/lib/hooks/useArrowKeyTabs";

interface ObjectInspectorFrameProps {
  header: ReactNode;
  metadata?: ReactNode;
  evidence?: ReactNode;
  validation?: ReactNode;
  correctionHistory?: ReactNode;
  ai?: ReactNode;
  version?: ReactNode;
  actions?: ReactNode;
}

type TabId = "properties" | "evidence" | "history" | "ai" | "actions";

// Every per-type detail panel (Heading, Table, Image, Footnote, List,
// Callout) renders inside this frame — the seam a fully generic Semantic
// Object Inspector slots into later without a rewrite. Prop names stay
// stable across callers; only panels with AI content (Image, Table) pass
// `ai` — everything else just doesn't get that tab.
export function ObjectInspectorFrame({
  header,
  metadata,
  evidence,
  validation,
  correctionHistory,
  ai,
  version,
  actions,
}: ObjectInspectorFrameProps) {
  type Tab = { id: TabId; label: string; content: ReactNode };
  // Kept as its own statement (not `[...].filter(...)` inline) — chaining
  // .filter() directly onto the literal breaks contextual typing of the
  // `id` literals against TabId, widening them to `string`.
  const allTabs: Tab[] = [
    { id: "properties", label: "Properties", content: metadata },
    {
      id: "evidence",
      label: "Evidence",
      content: (evidence || validation) ? (
        <div className="space-y-4">
          {evidence}
          {validation && (
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-text-secondary">
                Validation
              </p>
              {validation}
            </div>
          )}
        </div>
      ) : undefined,
    },
    { id: "history", label: "History", content: correctionHistory },
    { id: "ai", label: "AI", content: ai },
    { id: "actions", label: "Actions", content: actions },
  ];
  const tabs = allTabs.filter((tab) => tab.content);

  const [activeTab, setActiveTab] = useState<TabId>(tabs[0]?.id ?? "properties");
  const active = tabs.find((tab) => tab.id === activeTab) ?? tabs[0];
  // Phase F-3.2 — shared ARIA-tabs keyboard model. This bar previously
  // used aria-current (a pagination/breadcrumb attribute, not a tabs
  // one) with no role="tab"/"tablist" at all — a real bug, not just a
  // missing enhancement; assistive tech had no way to know this was a
  // tab group.
  const inspectorTabs = useArrowKeyTabs({
    ids: tabs.map((t) => t.id),
    active: active?.id ?? activeTab,
    onChange: setActiveTab,
  });

  return (
    <div className="rounded-lg border border-border bg-surface-panel p-4 space-y-3">
      {header}

      {tabs.length > 0 && (
        <div
          role="tablist"
          aria-label="Object details"
          ref={inspectorTabs.tablistRef as React.RefObject<HTMLDivElement>}
          className="flex flex-wrap gap-1 border-b border-border"
        >
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              {...inspectorTabs.getTabProps(tab.id)}
              id={`inspector-tab-${tab.id}`}
              aria-controls={`inspector-panel-${tab.id}`}
              className={`border-b-2 px-2.5 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                active?.id === tab.id
                  ? "border-accent text-text-primary"
                  : "border-transparent text-text-secondary hover:text-text-primary"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}

      {active && (
        <div
          role="tabpanel"
          id={`inspector-panel-${active.id}`}
          aria-labelledby={`inspector-tab-${active.id}`}
          className="pt-1"
        >
          {active.content}
        </div>
      )}

      {version && <p className="border-t border-border pt-2 text-xs text-text-secondary">{version}</p>}
    </div>
  );
}
