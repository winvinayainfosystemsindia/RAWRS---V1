"use client";

import { useState } from "react";
import { api, type HeadingItem } from "@/lib/api";
import { ObjectInspectorFrame } from "./workspace/ObjectInspectorFrame";
import { CorrectionHistoryList } from "./CorrectionHistoryList";
import { useObjectInspectorContext } from "@/lib/store/useObjectInspectorContext";
import { useDocumentDispatch } from "@/lib/store/DocumentDataContext";

interface Props {
  heading: HeadingItem;
  jobId: string;
  onUpdated: (updated: HeadingItem) => void;
}

const LEVEL_LABELS: Record<number, string> = {
  1: "H1 — Document title",
  2: "H2 — Major section",
  3: "H3 — Sub-section",
  4: "H4 — Minor heading",
  5: "H5 — Detail heading",
};

function buildSrAnnouncement(heading: HeadingItem): string {
  return `Heading level ${heading.level}: ${heading.text}`;
}

export function HeadingDetailPanel({ heading, jobId, onUpdated }: Props) {
  const { corrections, documentVersion } = useObjectInspectorContext("heading", null, heading.page_number);
  const dispatch = useDocumentDispatch();
  const [level, setLevel] = useState<number>(heading.level);
  const [text, setText] = useState<string>(heading.text);
  const [note, setNote] = useState<string>(heading.reviewer_note ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isDirty =
    level !== heading.level ||
    text !== heading.text ||
    note !== (heading.reviewer_note ?? "");

  async function handleApprove() {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.reviewHeading(jobId, heading.document_order, {
        level: level !== heading.level ? level : undefined,
        text: text !== heading.text ? text : undefined,
        action: "approve",
        reviewer_note: note || undefined,
      });
      onUpdated(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleReject() {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.reviewHeading(jobId, heading.document_order, {
        action: "reject",
        reviewer_note: note || undefined,
      });
      onUpdated(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveChanges() {
    if (!isDirty) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.reviewHeading(jobId, heading.document_order, {
        level: level !== heading.level ? level : undefined,
        text: text !== heading.text ? text : undefined,
        reviewer_note: note !== (heading.reviewer_note ?? "") ? note : undefined,
      });
      onUpdated(updated);
      setLevel(updated.level);
      setText(updated.text);
      setNote(updated.reviewer_note ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  const srAnnouncement = buildSrAnnouncement({ ...heading, level, text });
  const isRejected = heading.review_status === "rejected";
  const isApproved = heading.review_status === "approved";

  const header = (
    <div>
      <h3 className="text-sm font-semibold text-text-primary">{heading.text || "(untitled heading)"}</h3>
      <p className="text-xs text-text-secondary">Page {heading.page_number} · Document order: {heading.document_order}</p>
    </div>
  );

  return (
    <ObjectInspectorFrame
      header={header}
      metadata={
        <div className="space-y-5">
      {/* Heading level */}
      <div>
        <label htmlFor="heading-level" className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
          Heading Level
        </label>
        <select
          id="heading-level"
          value={level}
          onChange={(e) => setLevel(Number(e.target.value))}
          className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          disabled={saving || isRejected}
        >
          {[1, 2, 3, 4, 5].map((l) => (
            <option key={l} value={l}>{LEVEL_LABELS[l]}</option>
          ))}
        </select>
      </div>

      {/* Heading text */}
      <div>
        <label htmlFor="heading-text" className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
          Heading Text
        </label>
        <input
          id="heading-text"
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          disabled={saving || isRejected}
        />
      </div>

      {/* Screen reader simulation */}
      <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-3">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">
          Screen Reader Announcement
        </p>
        <p
          className="text-sm font-mono text-gray-800 leading-relaxed"
          aria-label="Screen reader announcement preview"
        >
          &quot;{srAnnouncement}&quot;
        </p>
        <p className="mt-1 text-xs text-gray-400">
          NVDA/JAWS navigation: <kbd className="rounded bg-gray-200 px-1 py-0.5 text-xs">H</kbd> cycles through all headings at this level.
        </p>
      </div>

      {/* Reviewer note */}
      <div>
        <label htmlFor="reviewer-note" className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
          Reviewer Note <span className="font-normal text-gray-400">(optional)</span>
        </label>
        <textarea
          id="reviewer-note"
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Reason for level change, rejection, etc."
          className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm resize-none focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          disabled={saving}
        />
      </div>

      {/* Error */}
      {error && (
        <p className="text-sm text-danger" role="alert">{error}</p>
      )}

      {/* Status badge */}
      <div className="border-t border-border pt-3">
        <p className="text-xs text-text-secondary">
          Status:{" "}
          <span className={`font-medium ${
            heading.review_status === "approved" ? "text-success"
            : heading.review_status === "rejected" ? "text-danger"
            : heading.review_status === "level_changed" ? "text-accent"
            : "text-warning"
          }`}>
            {heading.review_status === "detected" && "Awaiting review"}
            {heading.review_status === "approved" && "Approved"}
            {heading.review_status === "level_changed" && "Level corrected"}
            {heading.review_status === "rejected" && "Rejected (false positive)"}
          </span>
        </p>
      </div>
        </div>
      }
      correctionHistory={
        <CorrectionHistoryList
          corrections={corrections}
          jobId={jobId}
          onUpdated={(updated) => dispatch({ type: "UPDATE_CORRECTION", correction: updated })}
          emptyMessage="No cross-source corrections proposed for headings on this page."
        />
      }
      version={
        documentVersion !== null ? (
          <p className="text-sm text-text-secondary">As of Document v{documentVersion}</p>
        ) : undefined
      }
      actions={
        <>
          {isDirty && (
            <button
              onClick={handleSaveChanges}
              disabled={saving || !text.trim()}
              className="rounded bg-text-secondary px-3 py-1.5 text-sm font-medium text-surface-canvas hover:opacity-90 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save changes"}
            </button>
          )}
          {!isApproved && !isRejected && (
            <button
              onClick={handleApprove}
              disabled={saving || !text.trim()}
              className="rounded bg-success px-3 py-1.5 text-sm font-medium text-accent-contrast hover:opacity-90 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Approve"}
            </button>
          )}
          {isApproved && (
            <button
              onClick={handleApprove}
              disabled={saving || !text.trim()}
              className="rounded bg-success px-3 py-1.5 text-sm font-medium text-accent-contrast hover:opacity-90 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Re-approve"}
            </button>
          )}
          {!isRejected && (
            <button
              onClick={handleReject}
              disabled={saving}
              className="rounded border border-danger/40 px-3 py-1.5 text-sm font-medium text-danger hover:bg-danger/10 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Mark as false positive"}
            </button>
          )}
          {isRejected && (
            <button
              onClick={handleApprove}
              disabled={saving}
              className="rounded border border-success/40 px-3 py-1.5 text-sm font-medium text-success hover:bg-success/10 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Restore"}
            </button>
          )}
        </>
      }
    />
  );
}
