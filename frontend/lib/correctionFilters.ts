import { type CorrectionItem } from "@/lib/api";

// Extracted from CorrectionsPanel.tsx (M-4.1) so ReviewerWorkspace shares
// the exact same status-grouping logic rather than a second copy — one
// implementation, never diverging, same reasoning as CorrectionHistoryList
// and EvidenceBreakdown already follow.
export type StatusTab = "pending" | "accepted" | "rejected" | "ignored" | "all";

export const STATUS_TABS: { id: StatusTab; label: string }[] = [
  { id: "pending", label: "Pending" },
  { id: "accepted", label: "Accepted" },
  { id: "rejected", label: "Rejected" },
  { id: "ignored", label: "Ignored" },
  { id: "all", label: "All" },
];

export function statusTabMatches(c: CorrectionItem, tab: StatusTab): boolean {
  if (tab === "all") return true;
  if (tab === "pending") return ["proposed", "pending_review"].includes(c.status);
  if (tab === "accepted") return ["accepted", "auto_applied", "edited"].includes(c.status);
  if (tab === "rejected") return c.status === "rejected";
  if (tab === "ignored") return ["ignored", "reverted"].includes(c.status);
  return false;
}

export function isResolved(c: CorrectionItem): boolean {
  return !["proposed", "pending_review"].includes(c.status);
}
