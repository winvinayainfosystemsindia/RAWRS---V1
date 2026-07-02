"use client";

import { useState } from "react";
import { api, type HeadingItem } from "@/lib/api";

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

  return (
    <div className="space-y-5 p-1">
      {/* Location */}
      <div>
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Location</p>
        <p className="text-sm text-gray-700">Page {heading.page_number}</p>
        <p className="text-xs text-gray-400 mt-0.5">Document order: {heading.document_order}</p>
      </div>

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
        <p className="text-sm text-red-600" role="alert">{error}</p>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        {isDirty && (
          <button
            onClick={handleSaveChanges}
            disabled={saving || !text.trim()}
            className="rounded bg-gray-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save changes"}
          </button>
        )}
        {!isApproved && !isRejected && (
          <button
            onClick={handleApprove}
            disabled={saving || !text.trim()}
            className="rounded bg-green-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-800 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Approve"}
          </button>
        )}
        {isApproved && (
          <button
            onClick={handleApprove}
            disabled={saving || !text.trim()}
            className="rounded bg-green-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-800 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Re-approve"}
          </button>
        )}
        {!isRejected && (
          <button
            onClick={handleReject}
            disabled={saving}
            className="rounded border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Mark as false positive"}
          </button>
        )}
        {isRejected && (
          <button
            onClick={handleApprove}
            disabled={saving}
            className="rounded border border-green-300 px-3 py-1.5 text-sm font-medium text-green-700 hover:bg-green-50 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Restore"}
          </button>
        )}
      </div>

      {/* Status badge */}
      <div className="border-t pt-3">
        <p className="text-xs text-gray-500">
          Status:{" "}
          <span className={`font-medium ${
            heading.review_status === "approved" ? "text-green-700"
            : heading.review_status === "rejected" ? "text-red-700"
            : heading.review_status === "level_changed" ? "text-blue-700"
            : "text-yellow-700"
          }`}>
            {heading.review_status === "detected" && "Awaiting review"}
            {heading.review_status === "approved" && "Approved"}
            {heading.review_status === "level_changed" && "Level corrected"}
            {heading.review_status === "rejected" && "Rejected (false positive)"}
          </span>
        </p>
      </div>
    </div>
  );
}
