"use client";

import { useState } from "react";
import { api, type BlockItem, type PageReadingOrder } from "@/lib/api";

interface Props {
  pages: PageReadingOrder[];
  jobId: string;
  onPagesUpdated: (updated: PageReadingOrder[]) => void;
}

function statusLabel(status: PageReadingOrder["reading_order_status"]): string {
  switch (status) {
    case "unreviewed": return "Needs review";
    case "approved":   return "Approved";
    case "corrected":  return "Corrected";
  }
}

function statusColor(status: PageReadingOrder["reading_order_status"]): string {
  switch (status) {
    case "unreviewed": return "bg-yellow-100 text-yellow-800";
    case "approved":   return "bg-green-100 text-green-800";
    case "corrected":  return "bg-blue-100 text-blue-800";
  }
}

interface PagePanelProps {
  page: PageReadingOrder;
  jobId: string;
  onUpdated: (updated: PageReadingOrder) => void;
}

function PageOrderPanel({ page, jobId, onUpdated }: PagePanelProps) {
  const [blocks, setBlocks] = useState<BlockItem[]>([...page.blocks]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isDirty = blocks.some((b, i) => b.block_order !== page.blocks[i]?.block_order);

  function moveBlock(fromIdx: number, toIdx: number) {
    if (toIdx < 0 || toIdx >= blocks.length) return;
    const next = [...blocks];
    const [moved] = next.splice(fromIdx, 1);
    next.splice(toIdx, 0, moved);
    setBlocks(next);
  }

  async function handleApprove() {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateReadingOrder(jobId, page.page_number, { action: "approve" });
      onUpdated(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveOrder() {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateReadingOrder(jobId, page.page_number, {
        action: "reorder",
        block_sequence: blocks.map((b) => b.block_order),
      });
      onUpdated(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  function handleReset() {
    setBlocks([...page.blocks]);
  }

  return (
    <div className="space-y-3">
      {/* Status + controls */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${statusColor(page.reading_order_status)}`}>
            {statusLabel(page.reading_order_status)}
          </span>
          <span className="text-xs text-gray-500">{blocks.length} block{blocks.length !== 1 ? "s" : ""} on this page</span>
        </div>
        <div className="flex items-center gap-2">
          {isDirty && (
            <button
              type="button"
              onClick={handleReset}
              disabled={saving}
              className="rounded px-2.5 py-1.5 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              Reset
            </button>
          )}
          {isDirty ? (
            <button
              type="button"
              onClick={handleSaveOrder}
              disabled={saving}
              className="rounded px-3 py-1.5 text-xs font-semibold bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              {saving ? "Saving…" : "Save order"}
            </button>
          ) : (
            <button
              type="button"
              onClick={handleApprove}
              disabled={saving || page.reading_order_status === "approved"}
              className="rounded px-3 py-1.5 text-xs font-semibold bg-green-600 text-white hover:bg-green-700 disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-green-500"
            >
              {saving ? "Saving…" : page.reading_order_status === "approved" ? "Approved" : "Approve order"}
            </button>
          )}
        </div>
      </div>

      {error && (
        <p className="text-xs text-red-600 rounded border border-red-200 bg-red-50 px-3 py-2">
          {error}
        </p>
      )}

      {/* Screen reader simulation note */}
      <p className="text-xs text-gray-500 bg-gray-50 rounded px-3 py-2 border border-gray-100">
        Screen readers traverse this page&rsquo;s text in the order shown below. Use the arrows to correct the sequence if two-column or multi-region layout caused PyMuPDF to interleave the blocks.
      </p>

      {/* Block list */}
      {blocks.length === 0 ? (
        <p className="text-sm text-gray-500 py-2">No text blocks found on this page.</p>
      ) : (
        <ol className="space-y-1.5">
          {blocks.map((block, idx) => (
            <li
              key={block.block_order}
              className="flex items-start gap-2 rounded-lg border border-gray-200 bg-white p-2.5"
            >
              {/* Position number */}
              <span className="shrink-0 inline-flex items-center justify-center w-6 h-6 rounded-full bg-gray-100 text-[11px] font-semibold text-gray-600 mt-0.5">
                {idx + 1}
              </span>

              {/* Block text */}
              <p className="flex-1 min-w-0 text-xs text-gray-800 break-words leading-snug">
                {block.text.length > 120 ? block.text.slice(0, 120) + "…" : block.text}
              </p>

              {/* Move controls */}
              <div className="shrink-0 flex flex-col gap-0.5">
                <button
                  type="button"
                  aria-label={`Move block ${idx + 1} up`}
                  onClick={() => moveBlock(idx, idx - 1)}
                  disabled={idx === 0}
                  className="rounded p-0.5 text-gray-400 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-1 focus-visible:ring-blue-500"
                >
                  <svg className="h-3.5 w-3.5" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M6 9.5V2.5M2.5 6 6 2.5 9.5 6" />
                  </svg>
                </button>
                <button
                  type="button"
                  aria-label={`Move block ${idx + 1} down`}
                  onClick={() => moveBlock(idx, idx + 1)}
                  disabled={idx === blocks.length - 1}
                  className="rounded p-0.5 text-gray-400 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-1 focus-visible:ring-blue-500"
                >
                  <svg className="h-3.5 w-3.5" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M6 2.5v7M9.5 6 6 9.5 2.5 6" />
                  </svg>
                </button>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export function ReadingOrderPanel({ pages, jobId, onPagesUpdated }: Props) {
  const [selectedPageNum, setSelectedPageNum] = useState<number | null>(
    pages.length > 0 ? pages[0].page_number : null
  );

  const selectedPage = pages.find((p) => p.page_number === selectedPageNum) ?? null;

  function handleUpdated(updated: PageReadingOrder) {
    onPagesUpdated(pages.map((p) => (p.page_number === updated.page_number ? updated : p)));
  }

  if (pages.length === 0) {
    return (
      <p className="text-sm text-gray-500 py-4">
        No reading order anomalies detected. PAGE_003 validation issues trigger this workspace.
      </p>
    );
  }

  const unreviewedCount = pages.filter((p) => p.reading_order_status === "unreviewed").length;
  const approvedCount = pages.filter((p) => p.reading_order_status === "approved").length;
  const correctedCount = pages.filter((p) => p.reading_order_status === "corrected").length;

  return (
    <div>
      {/* Summary bar */}
      <div className="mb-3 flex flex-wrap gap-3 text-xs text-gray-600">
        <span>{pages.length} page{pages.length !== 1 ? "s" : ""} flagged</span>
        {unreviewedCount > 0 && <span className="text-yellow-700">{unreviewedCount} awaiting review</span>}
        {approvedCount > 0 && <span className="text-green-700">{approvedCount} approved</span>}
        {correctedCount > 0 && <span className="text-blue-700">{correctedCount} corrected</span>}
      </div>

      <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
        {/* Page list */}
        <div className="w-full lg:w-40 shrink-0">
          <ul className="space-y-1.5">
            {pages.map((page) => (
              <li key={page.page_number}>
                <button
                  type="button"
                  onClick={() => setSelectedPageNum(page.page_number)}
                  className={`w-full text-left rounded-lg border px-3 py-2.5 text-sm transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                    page.page_number === selectedPageNum
                      ? "border-blue-500 bg-blue-50"
                      : "border-gray-200 hover:border-gray-300 bg-white"
                  }`}
                >
                  <span className="font-medium text-gray-900 block">Page {page.page_number}</span>
                  <span className={`mt-1 inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium ${statusColor(page.reading_order_status)}`}>
                    {statusLabel(page.reading_order_status)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        {/* Detail panel */}
        {selectedPage && (
          <div className="flex-1 min-w-0 rounded-lg border border-gray-200 bg-white p-4">
            <h3 className="text-sm font-semibold text-gray-800 mb-3">
              Page {selectedPage.page_number} — Reading Order
            </h3>
            <PageOrderPanel
              page={selectedPage}
              jobId={jobId}
              onUpdated={handleUpdated}
            />
          </div>
        )}
      </div>
    </div>
  );
}
