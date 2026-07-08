"use client";

import { useState } from "react";
import type { ListItem } from "@/lib/api";
import { Badge } from "./Badge";
import { ObjectInspectorFrame } from "./workspace/ObjectInspectorFrame";
import { CorrectionHistoryList } from "./CorrectionHistoryList";
import { useObjectInspectorContext } from "@/lib/store/useObjectInspectorContext";
import { useDocumentDispatch } from "@/lib/store/DocumentDataContext";
import { listKey } from "@/lib/store/DocumentDataContext";

interface Props {
  lists: ListItem[];
  jobId: string;
}

export function ListDetailPanel({ list, jobId }: { list: ListItem; jobId: string }) {
  const { corrections, documentVersion } = useObjectInspectorContext("list", list.id, list.page_number);
  const dispatch = useDocumentDispatch();

  const header = (
    <div className="flex items-center gap-2">
      <Badge tone={list.list_type === "numbered" ? "info" : "neutral"}>
        {list.list_type === "numbered" ? "Numbered" : "Bullet"}
      </Badge>
      <span className="text-xs text-text-secondary">Page {list.page_number}</span>
    </div>
  );

  return (
    <ObjectInspectorFrame
      header={header}
      metadata={
        <ul className="space-y-1 text-sm text-text-primary">
          {list.items.map((item, itemIdx) => (
            <li key={itemIdx} style={{ paddingLeft: `${item.level}rem` }}>
              {list.list_type === "numbered" ? `${itemIdx + 1}.` : "•"} {item.text}
            </li>
          ))}
        </ul>
      }
      correctionHistory={
        <CorrectionHistoryList
          corrections={corrections}
          jobId={jobId}
          onUpdated={(updated) => dispatch({ type: "UPDATE_CORRECTION", correction: updated })}
          emptyMessage="No cross-source corrections proposed for this list."
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

export function ListPanel({ lists, jobId }: Props) {
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  if (lists.length === 0) {
    return <p className="text-sm text-text-secondary">No lists were detected in this document.</p>;
  }

  const selected = lists.find((l) => listKey(l) === selectedKey) ?? null;

  return (
    <div className="flex flex-col gap-4">
      <div className={`w-full ${selected ? "max-h-64 overflow-y-auto" : ""}`}>
        <p className="mb-2 text-xs text-text-secondary">{lists.length} list{lists.length !== 1 ? "s" : ""}</p>
        <ul className="space-y-2">
          {lists.map((list) => {
            const key = listKey(list);
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
                  <Badge tone={list.list_type === "numbered" ? "info" : "neutral"}>
                    {list.list_type === "numbered" ? "Numbered" : "Bullet"}
                  </Badge>
                  <span className="text-xs text-text-secondary">Page {list.page_number}</span>
                </div>
                <p className="line-clamp-2 text-xs text-text-primary">
                  {list.items.map((i) => i.text).join(" · ")}
                </p>
              </li>
            );
          })}
        </ul>
      </div>

      {selected && (
        <div className="flex-1 min-w-0">
          <ListDetailPanel list={selected} jobId={jobId} />
        </div>
      )}
    </div>
  );
}
