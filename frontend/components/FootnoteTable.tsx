"use client";

import { useState } from "react";
import { api, type FootnoteItem } from "@/lib/api";
import { Badge } from "./Badge";

interface Props {
  footnotes: FootnoteItem[];
  jobId: string;
  onFootnotesUpdated: (updated: FootnoteItem[]) => void;
}

function statusLabel(status: FootnoteItem["review_status"]): string {
  switch (status) {
    case "detected": return "Detected";
    case "approved": return "Approved";
    case "edited": return "Edited";
    case "rejected": return "Rejected";
  }
}

function statusColor(status: FootnoteItem["review_status"]): string {
  switch (status) {
    case "detected": return "bg-yellow-100 text-yellow-800";
    case "approved": return "bg-green-100 text-green-800";
    case "edited": return "bg-blue-100 text-blue-800";
    case "rejected": return "bg-red-100 text-red-800";
  }
}

function noteKey(note: FootnoteItem): string {
  return note.footnote_id ?? `${note.note_type}-${note.number}-${note.anchor_page_number}`;
}

interface DetailProps {
  note: FootnoteItem;
  jobId: string;
  onUpdated: (updated: FootnoteItem) => void;
}

function FootnoteDetailPanel({ note, jobId, onUpdated }: DetailProps) {
  const [body, setBody] = useState(note.body);
  const [reviewerNote, setReviewerNote] = useState(note.reviewer_note ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isDirty = body !== note.body || reviewerNote !== (note.reviewer_note ?? "");
  const canReview = !!note.footnote_id;

  const srAnnouncement =
    note.note_type === "footnote"
      ? `Footnote ${note.number}: ${body}`
      : `Endnote ${note.number}: ${body}`;

  async function call(request: Parameters<typeof api.reviewFootnote>[2]) {
    if (!note.footnote_id) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.reviewFootnote(jobId, note.footnote_id, request);
      onUpdated(updated);
      setBody(updated.body);
      setReviewerNote(updated.reviewer_note ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4 p-1">
      {/* Location */}
      <div className="flex flex-wrap gap-4 text-sm text-gray-600">
        <span>Marker: <span className="font-mono font-medium">{note.marker}</span></span>
        <span>Anchor page: <span className="font-medium">{note.anchor_page_number}</span></span>
        <span>Body page: <span className="font-medium">{note.body_page_number}</span></span>
      </div>

      {/* Body text */}
      <div>
        <label htmlFor="fn-body" className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
          Note Body
        </label>
        <textarea
          id="fn-body"
          rows={4}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm resize-none focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          disabled={saving || note.review_status === "rejected" || !canReview}
        />
      </div>

      {/* SR simulation */}
      <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-3">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">
          Screen Reader Announcement
        </p>
        <p className="text-sm font-mono text-gray-800 leading-relaxed">
          &quot;{srAnnouncement}&quot;
        </p>
        <p className="mt-1 text-xs text-gray-400">
          NVDA/JAWS: <kbd className="rounded bg-gray-200 px-1 py-0.5 text-xs">F</kbd> navigates between footnote references.
          Word renders this as a native <code className="text-xs">w:footnote</code> element.
        </p>
      </div>

      {/* Reviewer note */}
      <div>
        <label htmlFor="fn-reviewer-note" className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
          Reviewer Note <span className="font-normal text-gray-400">(optional)</span>
        </label>
        <input
          id="fn-reviewer-note"
          type="text"
          value={reviewerNote}
          onChange={(e) => setReviewerNote(e.target.value)}
          placeholder="Reason for edit or rejection"
          className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          disabled={saving || !canReview}
        />
      </div>

      {!canReview && (
        <p className="text-xs text-amber-600">
          This note has no stable ID (detected in a document processed before FEATURE_016D). Re-process the document to enable review.
        </p>
      )}

      {error && <p className="text-sm text-red-600" role="alert">{error}</p>}

      {canReview && (
        <div className="flex flex-wrap gap-2">
          {isDirty && (
            <button
              onClick={() => call({ body: body !== note.body ? body : undefined, reviewer_note: reviewerNote || undefined })}
              disabled={saving || !body.trim()}
              className="rounded bg-gray-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save edits"}
            </button>
          )}
          {note.review_status !== "approved" && note.review_status !== "rejected" && (
            <button
              onClick={() => call({ action: "approve", reviewer_note: reviewerNote || undefined })}
              disabled={saving}
              className="rounded bg-green-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-800 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Approve"}
            </button>
          )}
          {note.review_status === "approved" && (
            <button
              onClick={() => call({ action: "approve" })}
              disabled={saving}
              className="rounded bg-green-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-800 disabled:opacity-50"
            >
              Re-approve
            </button>
          )}
          {note.review_status !== "rejected" && (
            <button
              onClick={() => call({ action: "reject", reviewer_note: reviewerNote || undefined })}
              disabled={saving}
              className="rounded border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Mark as false positive"}
            </button>
          )}
          {note.review_status === "rejected" && (
            <button
              onClick={() => call({ action: "approve" })}
              disabled={saving}
              className="rounded border border-green-300 px-3 py-1.5 text-sm font-medium text-green-700 hover:bg-green-50 disabled:opacity-50"
            >
              Restore
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function FootnoteTable({ footnotes, jobId, onFootnotesUpdated }: Props) {
  const [selectedKey, setSelectedKey] = useState<string | null>(
    footnotes.length > 0 ? noteKey(footnotes[0]) : null
  );

  const selectedNote = footnotes.find((n) => noteKey(n) === selectedKey) ?? null;

  function handleUpdated(updated: FootnoteItem) {
    const key = noteKey(updated);
    onFootnotesUpdated(
      footnotes.map((n) => (noteKey(n) === key ? updated : n))
    );
  }

  if (footnotes.length === 0) {
    return (
      <p className="text-sm text-gray-600">
        No footnotes or endnotes were detected in this document.
      </p>
    );
  }

  const pendingCount = footnotes.filter((n) => n.review_status === "detected").length;
  const approvedCount = footnotes.filter((n) => n.review_status === "approved" || n.review_status === "edited").length;

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-3 text-xs text-gray-600">
        <span>{footnotes.length} note{footnotes.length !== 1 ? "s" : ""}</span>
        {pendingCount > 0 && <span className="text-yellow-700">{pendingCount} awaiting review</span>}
        {approvedCount > 0 && <span className="text-green-700">{approvedCount} approved</span>}
      </div>

      <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
        {/* Note list */}
        <div className="w-full lg:w-64 shrink-0">
          <ul className="space-y-2">
            {footnotes.map((note) => {
              const key = noteKey(note);
              const isSelected = key === selectedKey;
              return (
                <li
                  key={key}
                  className={`rounded-lg border p-3 cursor-pointer transition-colors ${
                    isSelected
                      ? "border-blue-500 bg-blue-50"
                      : "border-gray-200 hover:border-gray-300 bg-white"
                  }`}
                  onClick={() => setSelectedKey(key)}
                >
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <Badge tone={note.note_type === "endnote" ? "info" : "neutral"}>
                      {note.note_type === "endnote" ? "Endnote" : "Footnote"} {note.number}
                    </Badge>
                    <span className={`shrink-0 inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${statusColor(note.review_status)}`}>
                      {statusLabel(note.review_status)}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mb-0.5">Marker: <span className="font-mono">{note.marker}</span> · Page {note.anchor_page_number}</p>
                  <p className="text-xs text-gray-700 line-clamp-2">{note.body}</p>
                </li>
              );
            })}
          </ul>
        </div>

        {/* Detail panel */}
        {selectedNote && (
          <div className="flex-1 min-w-0 rounded-lg border border-gray-200 bg-white p-4">
            <div className="mb-3 flex items-center gap-2">
              <Badge tone={selectedNote.note_type === "endnote" ? "info" : "neutral"}>
                {selectedNote.note_type === "endnote" ? "Endnote" : "Footnote"} {selectedNote.number}
              </Badge>
              <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${statusColor(selectedNote.review_status)}`}>
                {statusLabel(selectedNote.review_status)}
              </span>
            </div>
            <FootnoteDetailPanel
              note={selectedNote}
              jobId={jobId}
              onUpdated={handleUpdated}
            />
          </div>
        )}
      </div>
    </div>
  );
}
