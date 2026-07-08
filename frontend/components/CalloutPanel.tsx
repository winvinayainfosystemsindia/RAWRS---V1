"use client";

import { useState } from "react";
import type { CalloutItem } from "@/lib/api";
import { Badge } from "./Badge";
import { ObjectInspectorFrame } from "./workspace/ObjectInspectorFrame";
import { CorrectionHistoryList } from "./CorrectionHistoryList";
import { useObjectInspectorContext } from "@/lib/store/useObjectInspectorContext";
import { useDocumentDispatch, calloutKey } from "@/lib/store/DocumentDataContext";

interface Props {
  callouts: CalloutItem[];
  jobId: string;
}

export function CalloutDetailPanel({ callout, jobId }: { callout: CalloutItem; jobId: string }) {
  const { corrections, documentVersion } = useObjectInspectorContext(
    "callout",
    callout.id,
    callout.page_number
  );
  const dispatch = useDocumentDispatch();

  const header = (
    <div className="flex items-center gap-2">
      <Badge tone="info">{callout.callout_type}</Badge>
      {callout.page_number !== null && (
        <span className="text-xs text-text-secondary">Page {callout.page_number}</span>
      )}
    </div>
  );

  return (
    <ObjectInspectorFrame
      header={header}
      metadata={<p className="text-sm text-text-primary">{callout.label}</p>}
      correctionHistory={
        <CorrectionHistoryList
          corrections={corrections}
          jobId={jobId}
          onUpdated={(updated) => dispatch({ type: "UPDATE_CORRECTION", correction: updated })}
          emptyMessage="No cross-source corrections proposed for this callout."
        />
      }
      version={
        documentVersion !== null ? (
          <p className="text-sm text-text-secondary">As of Document v{documentVersion}</p>
        ) : undefined
      }
    />
  );
}

export function CalloutPanel({ callouts, jobId }: Props) {
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  if (callouts.length === 0) {
    return <p className="text-sm text-text-secondary">No callout boxes were detected in this document.</p>;
  }

  const selected = callouts.find((c) => calloutKey(c) === selectedKey) ?? null;

  return (
    <div className="flex flex-col gap-4">
      <div className={`w-full ${selected ? "max-h-64 overflow-y-auto" : ""}`}>
        <p className="mb-2 text-xs text-text-secondary">{callouts.length} callout{callouts.length !== 1 ? "s" : ""}</p>
        <ul className="space-y-2">
          {callouts.map((callout) => {
            const key = calloutKey(callout);
            const isSelected = key === selectedKey;
            return (
              <li
                key={key}
                onClick={() => setSelectedKey((prev) => (prev === key ? null : key))}
                className={`cursor-pointer rounded-lg border p-3 transition-colors ${
                  isSelected
                    ? "border-accent bg-hover-row"
                    : "border-border hover:border-border-strong bg-surface-panel"
                }`}
              >
                <div className="mb-1 flex items-center gap-2">
                  <Badge tone="info">{callout.callout_type}</Badge>
                  {callout.page_number !== null && (
                    <span className="text-xs text-text-secondary">Page {callout.page_number}</span>
                  )}
                </div>
                <p className="text-xs text-text-primary">{callout.label}</p>
              </li>
            );
          })}
        </ul>
      </div>

      {selected && (
        <div className="flex-1 min-w-0">
          <CalloutDetailPanel callout={selected} jobId={jobId} />
        </div>
      )}
    </div>
  );
}
