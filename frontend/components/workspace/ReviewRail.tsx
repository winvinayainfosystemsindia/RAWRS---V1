"use client";

import { useState } from "react";
import type { AiStatus } from "@/lib/api";
import { ReviewerWorkspace } from "@/components/ReviewerWorkspace";
import { ContextInspectorRail } from "@/components/workspace/ContextInspectorRail";
import { useArrowKeyTabs } from "@/lib/hooks/useArrowKeyTabs";
import { useSelection } from "@/lib/store/SelectionContext";
import { useReviewQueue } from "@/lib/store/ReviewQueueContext";

type RailTab = "review" | "inspector";
const RAIL_TABS: readonly RailTab[] = ["review", "inspector"];

// Phase D — the right rail is where review happens: the Review Queue (one
// proposal at a time, beside the PDF it points at) and the Context Inspector
// for whatever object is selected. Both stay mounted so the queue keeps its
// filters and position; only the visible one takes keyboard shortcuts.
export function ReviewRail({
  jobId,
  aiStatus,
  pendingCount,
  onOpenValidation,
}: {
  jobId: string;
  aiStatus: AiStatus | null;
  pendingCount: number;
  onOpenValidation?: () => void;
}) {
  const { selection } = useSelection();
  const { focusNonce } = useReviewQueue();
  const [tab, setTab] = useState<RailTab>("review");
  const { tablistRef, getTabProps } = useArrowKeyTabs({ ids: RAIL_TABS, active: tab, onChange: setTab });

  // Adjusting state while rendering (not in an effect): a "Review →" / Fix Next
  // request brings the queue forward; selecting a non-correction object (nav
  // tree, PDF overlay, validation issue) brings the Inspector forward. The
  // queue's own correction selections leave the tab alone.
  const [seenNonce, setSeenNonce] = useState(focusNonce);
  if (focusNonce !== seenNonce) {
    setSeenNonce(focusNonce);
    setTab("review");
  }
  const selectionKey = selection ? `${selection.objectType}:${selection.objectId}` : null;
  const [seenSelection, setSeenSelection] = useState(selectionKey);
  if (selectionKey !== seenSelection) {
    setSeenSelection(selectionKey);
    if (selection && selection.objectType !== "correction") setTab("inspector");
  }

  const tabClass = (id: RailTab) =>
    `flex-1 rounded px-2 py-1.5 text-xs font-medium ${
      tab === id ? "bg-surface-elevated text-text-primary" : "text-text-secondary hover:text-text-primary"
    }`;

  return (
    <div className="flex flex-col">
      <div
        role="tablist"
        aria-label="Review rail"
        ref={tablistRef as React.RefObject<HTMLDivElement>}
        className="sticky top-0 z-10 flex gap-1 border-b border-border bg-surface-panel p-1"
      >
        <button type="button" id="rail-tab-review" aria-controls="rail-panel-review" {...getTabProps("review")} className={tabClass("review")}>
          Review
          {pendingCount > 0 && (
            <span className="ml-1.5 rounded-full bg-warning/15 px-1.5 font-mono text-[10px] font-semibold text-warning">
              {pendingCount}
            </span>
          )}
        </button>
        <button type="button" id="rail-tab-inspector" aria-controls="rail-panel-inspector" {...getTabProps("inspector")} className={tabClass("inspector")}>
          Inspector
        </button>
      </div>
      <div role="tabpanel" id="rail-panel-review" aria-labelledby="rail-tab-review" hidden={tab !== "review"} className="p-2">
        <ReviewerWorkspace jobId={jobId} active={tab === "review"} />
      </div>
      <div role="tabpanel" id="rail-panel-inspector" aria-labelledby="rail-tab-inspector" hidden={tab !== "inspector"}>
        <ContextInspectorRail jobId={jobId} aiStatus={aiStatus} onOpenValidation={onOpenValidation} />
      </div>
    </div>
  );
}
