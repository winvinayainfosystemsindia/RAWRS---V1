"use client";

import { useState } from "react";
import { api, type ImageItem, type ReviewAction } from "@/lib/api";

interface Props {
  jobId: string;
  selectedIds: string[];
  onClearSelection: () => void;
  onActionComplete: (updated: ImageItem[]) => void;
}

export function BulkActions({ jobId, selectedIds, onClearSelection, onActionComplete }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (selectedIds.length === 0) return null;

  async function handleBulk(action: ReviewAction) {
    setLoading(true);
    setError(null);
    try {
      const response = await api.bulkReviewImages(jobId, selectedIds, action);
      onActionComplete(response.images);
      onClearSelection();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk action failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2">
      <span className="text-sm font-medium text-blue-900">
        {selectedIds.length} selected
      </span>
      <div className="flex flex-wrap gap-2">
        <BulkButton onClick={() => handleBulk("approve")} loading={loading} variant="success">
          Approve All
        </BulkButton>
        <BulkButton onClick={() => handleBulk("mark_decorative")} loading={loading} variant="neutral">
          Mark All Decorative
        </BulkButton>
        <BulkButton onClick={() => handleBulk("reject")} loading={loading} variant="danger">
          Reject All
        </BulkButton>
        <BulkButton onClick={() => handleBulk("skip")} loading={loading} variant="neutral">
          Skip All
        </BulkButton>
        <button
          type="button"
          className="text-xs text-blue-600 hover:underline"
          onClick={onClearSelection}
        >
          Clear
        </button>
      </div>
      {error && <p className="w-full text-xs text-red-600">{error}</p>}
    </div>
  );
}

function BulkButton({
  onClick,
  loading,
  variant,
  children,
}: {
  onClick: () => void;
  loading: boolean;
  variant: "success" | "danger" | "neutral";
  children: React.ReactNode;
}) {
  const base =
    "inline-flex items-center rounded px-2.5 py-1 text-xs font-medium transition-opacity disabled:opacity-50";
  const styles: Record<string, string> = {
    success: "bg-green-600 text-white hover:bg-green-700",
    danger: "bg-red-600 text-white hover:bg-red-700",
    neutral: "bg-white text-gray-700 ring-1 ring-gray-300 hover:bg-gray-50",
  };
  return (
    <button
      type="button"
      className={`${base} ${styles[variant]}`}
      onClick={onClick}
      disabled={loading}
    >
      {loading ? "…" : children}
    </button>
  );
}
