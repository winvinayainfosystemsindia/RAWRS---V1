"use client";

import { useState } from "react";
import { api, type FootnoteItem } from "@/lib/api";
import { Badge } from "./Badge";
import { ObjectInspectorFrame } from "./workspace/ObjectInspectorFrame";
import { CorrectionHistoryList } from "./CorrectionHistoryList";
import { useObjectInspectorContext } from "@/lib/store/useObjectInspectorContext";
import { useDocumentDispatch } from "@/lib/store/DocumentDataContext";

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
    case "detected": return "bg-warning/10 text-warning";
    case "approved": return "bg-success/10 text-success";
    case "edited": return "bg-accent/10 text-accent";
    case "rejected": return "bg-danger/10 text-danger";
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

export function FootnoteDetailPanel({ note, jobId, onUpdated }: DetailProps) {
  const { corrections, documentVersion } = useObjectInspectorContext(
    "footnote",
    note.footnote_id,
    note.anchor_page_number
  );
  const dispatch = useDocumentDispatch();
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

  const header = (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <Badge tone={note.note_type === "endnote" ? "info" : "neutral"}>
          {note.note_type === "endnote" ? "Endnote" : "Footnote"} {note.number}
        </Badge>
        <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${statusColor(note.review_status)}`}>
          {statusLabel(note.review_status)}
        </span>
      </div>
      <div className="flex flex-wrap gap-4 text-sm text-text-secondary">
        <span>Marker: <span className="font-mono font-medium text-text-primary">{note.marker}</span></span>
        <span>Anchor page: <span className="font-medium text-text-primary">{note.anchor_page_number}</span></span>
        <span>Body page: <span className="font-medium text-text-primary">{note.body_page_number}</span></span>
      </div>
    </div>
  );

  return (
    <ObjectInspectorFrame
      header={header}
      metadata={
        <div className="space-y-4">
      {/* Body text */}
      <div>
        <label htmlFor="fn-body" className="block text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
          Note Body
        </label>
        <textarea
          id="fn-body"
          rows={4}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          className="w-full rounded border border-border px-2 py-1.5 text-sm resize-none focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          disabled={saving || note.review_status === "rejected" || !canReview}
        />
      </div>

      {/* SR simulation */}
      <div className="rounded-lg border border-dashed border-border bg-surface-panel p-3">
        <p className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1.5">
          Screen Reader Announcement
        </p>
        <p className="text-sm font-mono text-text-primary leading-relaxed">
          &quot;{srAnnouncement}&quot;
        </p>
        <p className="mt-1 text-xs text-text-secondary">
          NVDA/JAWS: <kbd className="rounded bg-hover-row px-1 py-0.5 text-xs">F</kbd> navigates between footnote references.
          Word renders this as a native <code className="text-xs">w:footnote</code> element.
        </p>
      </div>

      {/* Reviewer note */}
      <div>
        <label htmlFor="fn-reviewer-note" className="block text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
          Reviewer Note <span className="font-normal text-text-secondary">(optional)</span>
        </label>
        <input
          id="fn-reviewer-note"
          type="text"
          value={reviewerNote}
          onChange={(e) => setReviewerNote(e.target.value)}
          placeholder="Reason for edit or rejection"
          className="w-full rounded border border-border px-2 py-1.5 text-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          disabled={saving || !canReview}
        />
      </div>

      {!canReview && (
        <p className="text-xs text-warning">
          This note has no stable ID (detected in a document processed before FEATURE_016D). Re-process the document to enable review.
        </p>
      )}

      {error && <p className="text-sm text-danger" role="alert">{error}</p>}
        </div>
      }
      correctionHistory={
        <CorrectionHistoryList
          corrections={corrections}
          jobId={jobId}
          onUpdated={(updated) => dispatch({ type: "UPDATE_CORRECTION", correction: updated })}
          emptyMessage="No cross-source corrections proposed for this note."
        />
      }
      version={
        documentVersion !== null ? (
          <p className="text-sm text-text-secondary">As of Document v{documentVersion}</p>
        ) : undefined
      }
      actions={
        canReview ? (
          <>
            {isDirty && (
              <button
                onClick={() => call({ body: body !== note.body ? body : undefined, reviewer_note: reviewerNote || undefined })}
                disabled={saving || !body.trim()}
                className="rounded bg-text-secondary px-3 py-1.5 text-sm font-medium text-surface-canvas hover:opacity-90 disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save edits"}
              </button>
            )}
            {note.review_status !== "approved" && note.review_status !== "rejected" && (
              <button
                onClick={() => call({ action: "approve", reviewer_note: reviewerNote || undefined })}
                disabled={saving}
                className="rounded bg-success px-3 py-1.5 text-sm font-medium text-accent-contrast hover:opacity-90 disabled:opacity-50"
              >
                {saving ? "Saving…" : "Approve"}
              </button>
            )}
            {note.review_status === "approved" && (
              <button
                onClick={() => call({ action: "approve" })}
                disabled={saving}
                className="rounded bg-success px-3 py-1.5 text-sm font-medium text-accent-contrast hover:opacity-90 disabled:opacity-50"
              >
                Re-approve
              </button>
            )}
            {note.review_status !== "rejected" && (
              <button
                onClick={() => call({ action: "reject", reviewer_note: reviewerNote || undefined })}
                disabled={saving}
                className="rounded border border-danger/40 px-3 py-1.5 text-sm font-medium text-danger hover:bg-danger/10 disabled:opacity-50"
              >
                {saving ? "Saving…" : "Mark as false positive"}
              </button>
            )}
            {note.review_status === "rejected" && (
              <button
                onClick={() => call({ action: "approve" })}
                disabled={saving}
                className="rounded border border-success/40 px-3 py-1.5 text-sm font-medium text-success hover:bg-success/10 disabled:opacity-50"
              >
                Restore
              </button>
            )}
          </>
        ) : undefined
      }
    />
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
      <p className="text-sm text-text-secondary">
        No footnotes or endnotes were detected in this document.
      </p>
    );
  }

  const pendingCount = footnotes.filter((n) => n.review_status === "detected").length;
  const approvedCount = footnotes.filter((n) => n.review_status === "approved" || n.review_status === "edited").length;

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-3 text-xs text-text-secondary">
        <span>{footnotes.length} note{footnotes.length !== 1 ? "s" : ""}</span>
        {pendingCount > 0 && <span className="text-warning">{pendingCount} awaiting review</span>}
        {approvedCount > 0 && <span className="text-success">{approvedCount} approved</span>}
      </div>

      <div className="flex flex-col gap-4">
        {/* Note list */}
        <div className="w-full max-h-64 overflow-y-auto">
          <ul className="space-y-2">
            {footnotes.map((note) => {
              const key = noteKey(note);
              const isSelected = key === selectedKey;
              return (
                <li
                  key={key}
                  className={`rounded-lg border p-3 cursor-pointer transition-colors ${
                    isSelected
                      ? "border-accent bg-accent/10"
                      : "border-border hover:border-border-strong bg-surface-elevated"
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
                  <p className="text-xs text-text-secondary mb-0.5">Marker: <span className="font-mono">{note.marker}</span> · Page {note.anchor_page_number}</p>
                  <p className="text-xs text-text-primary line-clamp-2">{note.body}</p>
                </li>
              );
            })}
          </ul>
        </div>

        {/* Detail panel */}
        {selectedNote && (
          <div className="flex-1 min-w-0">
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
