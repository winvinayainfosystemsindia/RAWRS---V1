"use client";

import { useState } from "react";
import { api, type BlockItem, type PageReadingOrder } from "@/lib/api";

interface Props {
  pages: PageReadingOrder[];
  jobId: string;
  onPagesUpdated: (updated: PageReadingOrder[]) => void;
}

function statusLabel(status: PageReadingOrder["reading_order_status"]): string {
  if (status === "unreviewed") return "Needs review";
  if (status === "approved") return "Approved";
  return "Corrected";
}

function statusClasses(status: PageReadingOrder["reading_order_status"]): string {
  if (status === "unreviewed") return "bg-warning/15 text-warning";
  if (status === "approved") return "bg-success/15 text-success";
  return "bg-accent/15 text-accent";
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

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${statusClasses(page.reading_order_status)}`}
          >
            {statusLabel(page.reading_order_status)}
          </span>
          <span className="text-xs text-text-secondary">
            {blocks.length} block{blocks.length !== 1 ? "s" : ""}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {isDirty && (
            <button
              type="button"
              onClick={() => setBlocks([...page.blocks])}
              disabled={saving}
              className="rounded px-2.5 py-1.5 text-xs text-text-secondary hover:bg-hover-row disabled:opacity-40"
            >
              Reset
            </button>
          )}
          {isDirty ? (
            <button
              type="button"
              onClick={handleSaveOrder}
              disabled={saving}
              className="rounded bg-accent px-3 py-1.5 text-xs font-semibold text-accent-contrast hover:opacity-90 disabled:opacity-40"
            >
              {saving ? "Saving…" : "Save order"}
            </button>
          ) : (
            <button
              type="button"
              onClick={handleApprove}
              disabled={saving || page.reading_order_status === "approved"}
              className="rounded bg-success px-3 py-1.5 text-xs font-semibold text-accent-contrast hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {saving
                ? "Saving…"
                : page.reading_order_status === "approved"
                  ? "Approved ✓"
                  : "Approve order"}
            </button>
          )}
        </div>
      </div>

      {error && (
        <p className="rounded border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <p className="rounded border border-border bg-surface-panel px-3 py-2 text-xs text-text-secondary">
        Screen readers traverse this page in the order shown. Use ↑ ↓ to correct sequences where
        multi-column layout caused blocks to interleave.
      </p>

      {blocks.length === 0 ? (
        <p className="py-2 text-sm text-text-secondary">No text blocks found on this page.</p>
      ) : (
        <ol className="space-y-1.5">
          {blocks.map((block, idx) => (
            <li
              key={block.block_order}
              className="flex items-start gap-2 rounded border border-border bg-surface-panel p-2.5"
            >
              <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-elevated font-mono text-[11px] font-semibold text-text-secondary">
                {idx + 1}
              </span>
              <p className="min-w-0 flex-1 break-words text-xs leading-snug text-text-primary">
                {block.text.length > 140 ? block.text.slice(0, 140) + "…" : block.text}
              </p>
              <div className="flex shrink-0 flex-col gap-0.5">
                <button
                  type="button"
                  aria-label={`Move block ${idx + 1} up`}
                  onClick={() => moveBlock(idx, idx - 1)}
                  disabled={idx === 0}
                  className="rounded p-0.5 text-text-secondary hover:bg-hover-row hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-30"
                >
                  <svg
                    className="h-3.5 w-3.5"
                    viewBox="0 0 12 12"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M6 9.5V2.5M2.5 6 6 2.5 9.5 6" />
                  </svg>
                </button>
                <button
                  type="button"
                  aria-label={`Move block ${idx + 1} down`}
                  onClick={() => moveBlock(idx, idx + 1)}
                  disabled={idx === blocks.length - 1}
                  className="rounded p-0.5 text-text-secondary hover:bg-hover-row hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-30"
                >
                  <svg
                    className="h-3.5 w-3.5"
                    viewBox="0 0 12 12"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
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
    pages.length > 0 ? pages[0].page_number : null,
  );

  const selectedPage = pages.find((p) => p.page_number === selectedPageNum) ?? null;

  function handleUpdated(updated: PageReadingOrder) {
    onPagesUpdated(pages.map((p) => (p.page_number === updated.page_number ? updated : p)));
  }

  if (pages.length === 0) {
    return (
      <p className="py-4 text-sm text-text-secondary">No reading order anomalies detected.</p>
    );
  }

  const unreviewedCount = pages.filter((p) => p.reading_order_status === "unreviewed").length;
  const approvedCount = pages.filter((p) => p.reading_order_status === "approved").length;
  const correctedCount = pages.filter((p) => p.reading_order_status === "corrected").length;

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-3 text-xs text-text-secondary">
        <span>
          {pages.length} page{pages.length !== 1 ? "s" : ""} flagged
        </span>
        {unreviewedCount > 0 && (
          <span className="text-warning">{unreviewedCount} awaiting review</span>
        )}
        {approvedCount > 0 && <span className="text-success">{approvedCount} approved</span>}
        {correctedCount > 0 && <span className="text-accent">{correctedCount} corrected</span>}
      </div>

      <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
        <ul className="flex w-full shrink-0 flex-col gap-1 lg:w-36">
          {pages.map((page) => (
            <li key={page.page_number}>
              <button
                type="button"
                onClick={() => setSelectedPageNum(page.page_number)}
                className={`w-full rounded border px-3 py-2 text-left text-sm transition-colors ${
                  page.page_number === selectedPageNum
                    ? "border-accent bg-accent/10 text-text-primary"
                    : "border-border bg-surface-panel text-text-secondary hover:border-border-strong hover:text-text-primary"
                }`}
              >
                <span className="block font-medium">Page {page.page_number}</span>
                <span
                  className={`mt-0.5 inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium ${statusClasses(page.reading_order_status)}`}
                >
                  {statusLabel(page.reading_order_status)}
                </span>
              </button>
            </li>
          ))}
        </ul>

        {selectedPage && (
          <div className="min-w-0 flex-1 rounded border border-border bg-surface-canvas p-4">
            <h3 className="mb-3 text-sm font-semibold text-text-primary">
              Page {selectedPage.page_number} — Reading Order
            </h3>
            <PageOrderPanel page={selectedPage} jobId={jobId} onUpdated={handleUpdated} />
          </div>
        )}
      </div>
    </div>
  );
}
