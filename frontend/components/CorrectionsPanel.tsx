"use client";

import { useState } from "react";
import { type CorrectionItem } from "@/lib/api";
import { CorrectionHistoryList } from "./CorrectionHistoryList";

type StatusTab = "pending" | "accepted" | "rejected" | "ignored" | "all";

const TABS: { id: StatusTab; label: string }[] = [
  { id: "pending", label: "Pending" },
  { id: "accepted", label: "Accepted" },
  { id: "rejected", label: "Rejected" },
  { id: "ignored", label: "Ignored" },
  { id: "all", label: "All" },
];

function tabMatches(c: CorrectionItem, tab: StatusTab): boolean {
  if (tab === "all") return true;
  if (tab === "pending") return ["proposed", "pending_review"].includes(c.status);
  if (tab === "accepted") return ["accepted", "auto_applied", "edited"].includes(c.status);
  if (tab === "rejected") return c.status === "rejected";
  if (tab === "ignored") return ["ignored", "reverted"].includes(c.status);
  return false;
}

interface Props {
  corrections: CorrectionItem[];
  jobId: string;
  onCorrectionsUpdated: (updated: CorrectionItem[]) => void;
  onCorrectionClick?: (correction: CorrectionItem) => void;
}

export function CorrectionsPanel({
  corrections,
  jobId,
  onCorrectionsUpdated,
  onCorrectionClick,
}: Props) {
  const [activeTab, setActiveTab] = useState<StatusTab>("pending");

  function handleUpdated(updated: CorrectionItem) {
    onCorrectionsUpdated(
      corrections.map((c) => (c.correction_id === updated.correction_id ? updated : c)),
    );
  }

  if (corrections.length === 0) {
    return (
      <p className="text-sm text-text-secondary">
        No cross-source corrections were proposed for this document.
      </p>
    );
  }

  const tabCounts: Record<StatusTab, number> = {
    pending: corrections.filter((c) => tabMatches(c, "pending")).length,
    accepted: corrections.filter((c) => tabMatches(c, "accepted")).length,
    rejected: corrections.filter((c) => tabMatches(c, "rejected")).length,
    ignored: corrections.filter((c) => tabMatches(c, "ignored")).length,
    all: corrections.length,
  };

  const visible = corrections.filter((c) => tabMatches(c, activeTab));

  return (
    <div className="flex flex-col gap-4">
      {/* PR-style status tabs */}
      <div className="flex items-center rounded-lg border border-border bg-surface-panel p-1">
        {TABS.map((tab) => {
          const count = tabCounts[tab.id];
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                isActive
                  ? "bg-surface-elevated text-text-primary"
                  : "text-text-secondary hover:text-text-primary"
              }`}
            >
              {tab.label}
              {count > 0 && (
                <span
                  className={`inline-flex h-4 min-w-4 items-center justify-center rounded-full px-1 font-mono text-[10px] ${
                    isActive && tab.id === "pending"
                      ? "bg-warning/20 text-warning"
                      : "bg-surface-canvas text-text-secondary"
                  }`}
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {visible.length === 0 ? (
        <p className="rounded-lg border border-border p-4 text-sm text-text-secondary">
          No {activeTab === "all" ? "" : activeTab} corrections.
        </p>
      ) : (
        <CorrectionHistoryList
          corrections={visible}
          jobId={jobId}
          onUpdated={handleUpdated}
          onCorrectionClick={onCorrectionClick}
        />
      )}
    </div>
  );
}
