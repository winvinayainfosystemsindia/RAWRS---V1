"use client";

import { useState } from "react";
import { type HeadingItem } from "@/lib/api";
import { HeadingCard } from "@/components/HeadingCard";
import { HeadingDetailPanel } from "@/components/HeadingDetailPanel";

interface Props {
  headings: HeadingItem[];
  jobId: string;
  onHeadingsUpdated: (updated: HeadingItem[]) => void;
}

export function HeadingGrid({ headings, jobId, onHeadingsUpdated }: Props) {
  const [selectedOrder, setSelectedOrder] = useState<number | null>(
    headings.length > 0 ? headings[0].document_order : null
  );

  const selectedHeading = headings.find((h) => h.document_order === selectedOrder) ?? null;

  function handleUpdated(updated: HeadingItem) {
    onHeadingsUpdated(
      headings.map((h) => (h.document_order === updated.document_order ? updated : h))
    );
  }

  if (headings.length === 0) {
    return (
      <p className="text-sm text-gray-500 py-4">
        No content headings detected in this document.
      </p>
    );
  }

  const pendingCount = headings.filter((h) => h.review_status === "detected").length;
  const approvedCount = headings.filter((h) => h.review_status === "approved" || h.review_status === "level_changed").length;
  const rejectedCount = headings.filter((h) => h.review_status === "rejected").length;

  return (
    <div>
      {/* Summary bar */}
      <div className="mb-3 flex flex-wrap gap-3 text-xs text-gray-600">
        <span>{headings.length} heading{headings.length !== 1 ? "s" : ""}</span>
        {pendingCount > 0 && <span className="text-yellow-700">{pendingCount} awaiting review</span>}
        {approvedCount > 0 && <span className="text-green-700">{approvedCount} approved</span>}
        {rejectedCount > 0 && <span className="text-red-700">{rejectedCount} rejected</span>}
      </div>

      <div className="flex flex-col gap-4">
        {/* Heading list */}
        <div className="w-full max-h-64 overflow-y-auto">
          <ul className="space-y-2">
            {headings.map((heading) => (
              <HeadingCard
                key={heading.document_order}
                heading={heading}
                isSelected={heading.document_order === selectedOrder}
                onSelect={() => setSelectedOrder(heading.document_order)}
              />
            ))}
          </ul>
        </div>

        {/* Detail panel */}
        {selectedHeading && (
          <div className="flex-1 min-w-0">
            <HeadingDetailPanel
              heading={selectedHeading}
              jobId={jobId}
              onUpdated={handleUpdated}
            />
          </div>
        )}
      </div>
    </div>
  );
}
