"use client";

import { useState } from "react";
import { api, type CorrectionItem } from "@/lib/api";
import { Badge } from "./Badge";

interface Props {
  corrections: CorrectionItem[];
  jobId: string;
  onCorrectionsUpdated: (updated: CorrectionItem[]) => void;
}

function statusLabel(status: string): string {
  switch (status) {
    case "proposed": return "Proposed";
    case "auto_applied": return "Auto-applied";
    case "accepted": return "Accepted";
    case "rejected": return "Rejected";
    case "edited": return "Edited";
    case "ignored": return "Ignored";
    case "pending_review": return "Needs Review";
    case "reverted": return "Reverted";
    default: return status;
  }
}

function statusColor(status: string): string {
  switch (status) {
    case "accepted":
    case "auto_applied": return "bg-green-100 text-green-800";
    case "rejected": return "bg-red-100 text-red-800";
    case "edited": return "bg-blue-100 text-blue-800";
    case "ignored": return "bg-gray-100 text-gray-600";
    case "pending_review": return "bg-yellow-100 text-yellow-800";
    case "reverted": return "bg-orange-100 text-orange-800";
    default: return "bg-yellow-100 text-yellow-800"; // proposed
  }
}

/** Every object type this panel shows a correction for — headings, lists,
 * figures, and any future asset type registered with the verification
 * engine — shares this exact same reviewer surface. No per-type panel is
 * added here again. */
function objectTypeLabel(objectType: string): string {
  return objectType.charAt(0).toUpperCase() + objectType.slice(1);
}

interface DetailProps {
  correction: CorrectionItem;
  jobId: string;
  onUpdated: (updated: CorrectionItem) => void;
}

function CorrectionDetailPanel({ correction, jobId, onUpdated }: DetailProps) {
  const [editValue, setEditValue] = useState(correction.suggested_value);
  const [reviewerNotes, setReviewerNotes] = useState(correction.reviewer_notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function act(action: Parameters<typeof api.reviewCorrection>[2]["action"], proposedValue?: string) {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.reviewCorrection(jobId, correction.correction_id, {
        action,
        proposed_value: proposedValue,
        reviewer_notes: reviewerNotes || undefined,
      });
      onUpdated(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setSaving(false);
    }
  }

  const isDecided = !["proposed", "pending_review"].includes(correction.status);

  return (
    <div className="space-y-4 p-1">
      {/* Problem / current / suggested */}
      <div>
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Problem</p>
        <p className="text-sm text-gray-800">{correction.problem}</p>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Current</p>
          <p className="text-sm font-mono text-gray-700 break-words">{correction.current_value || "—"}</p>
        </div>
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Suggested</p>
          <p className="text-sm font-mono text-green-700 break-words">{correction.suggested_value || "—"}</p>
        </div>
      </div>

      {/* Reason / confidence */}
      <div className="flex flex-wrap items-center gap-3 text-sm text-gray-600">
        {correction.reason && <span>Reason: {correction.reason}</span>}
        {correction.confidence !== null && (
          <span>Confidence: {(correction.confidence * 100).toFixed(0)}%</span>
        )}
      </div>

      {/* Evidence breakdown */}
      {correction.evidence.length > 0 && (
        <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-3">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Evidence</p>
          <ul className="space-y-0.5 text-sm text-gray-700">
            {correction.evidence.map((item, i) => (
              <li key={i}>
                <span className="font-medium">{item.signal}:</span> {item.detail}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Edit field — only meaningful when accepting an edited value */}
      {!isDecided && (
        <div>
          <label htmlFor="correction-edit-value" className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
            Edit suggested value
          </label>
          <input
            id="correction-edit-value"
            type="text"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm font-mono focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            disabled={saving}
          />
        </div>
      )}

      <div>
        <label htmlFor="correction-reviewer-notes" className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
          Reviewer Notes <span className="font-normal text-gray-400">(optional)</span>
        </label>
        <input
          id="correction-reviewer-notes"
          type="text"
          value={reviewerNotes}
          onChange={(e) => setReviewerNotes(e.target.value)}
          className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          disabled={saving}
        />
      </div>

      {error && <p className="text-sm text-red-600" role="alert">{error}</p>}

      {/* Standardized reviewer actions: Accept / Reject / Edit / Ignore / Needs Review / Undo */}
      <div className="flex flex-wrap gap-2">
        {!isDecided && (
          <>
            <button
              onClick={() => act("accept")}
              disabled={saving}
              className="rounded bg-green-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-800 disabled:opacity-50"
            >
              {saving ? "Working…" : "Accept"}
            </button>
            <button
              onClick={() => act("edit", editValue)}
              disabled={saving || editValue === correction.suggested_value}
              className="rounded bg-blue-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-50"
            >
              Accept with edit
            </button>
            <button
              onClick={() => act("reject")}
              disabled={saving}
              className="rounded border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
            >
              Reject
            </button>
            <button
              onClick={() => act("ignore")}
              disabled={saving}
              className="rounded border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50"
            >
              Ignore
            </button>
            {correction.status !== "pending_review" && (
              <button
                onClick={() => act("needs_review")}
                disabled={saving}
                className="rounded border border-yellow-300 px-3 py-1.5 text-sm font-medium text-yellow-700 hover:bg-yellow-50 disabled:opacity-50"
              >
                Needs Review
              </button>
            )}
          </>
        )}
        {isDecided && (
          <button
            onClick={() => act("undo")}
            disabled={saving}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {saving ? "Working…" : "Undo"}
          </button>
        )}
      </div>
    </div>
  );
}

export function CorrectionsPanel({ corrections, jobId, onCorrectionsUpdated }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(
    corrections.length > 0 ? corrections[0].correction_id : null
  );

  const selected = corrections.find((c) => c.correction_id === selectedId) ?? null;

  function handleUpdated(updated: CorrectionItem) {
    onCorrectionsUpdated(
      corrections.map((c) => (c.correction_id === updated.correction_id ? updated : c))
    );
  }

  if (corrections.length === 0) {
    return (
      <p className="text-sm text-gray-600">
        No cross-source corrections were proposed for this document — either no Mathpix package
        was supplied, or every verified object already matched the PDF.
      </p>
    );
  }

  const pendingCount = corrections.filter((c) => ["proposed", "pending_review"].includes(c.status)).length;
  const decidedCount = corrections.length - pendingCount;

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-3 text-xs text-gray-600">
        <span>{corrections.length} correction{corrections.length !== 1 ? "s" : ""}</span>
        {pendingCount > 0 && <span className="text-yellow-700">{pendingCount} awaiting review</span>}
        {decidedCount > 0 && <span className="text-green-700">{decidedCount} decided</span>}
      </div>

      <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
        {/* Correction list */}
        <div className="w-full lg:w-72 shrink-0">
          <ul className="space-y-2">
            {corrections.map((correction) => {
              const isSelected = correction.correction_id === selectedId;
              return (
                <li
                  key={correction.correction_id}
                  className={`rounded-lg border p-3 cursor-pointer transition-colors ${
                    isSelected ? "border-blue-500 bg-blue-50" : "border-gray-200 hover:border-gray-300 bg-white"
                  }`}
                  onClick={() => setSelectedId(correction.correction_id)}
                >
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <Badge tone="neutral">{objectTypeLabel(correction.object_type)}</Badge>
                    <span className={`shrink-0 inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${statusColor(correction.status)}`}>
                      {statusLabel(correction.status)}
                    </span>
                  </div>
                  <p className="text-xs text-gray-700 line-clamp-2">{correction.problem}</p>
                </li>
              );
            })}
          </ul>
        </div>

        {/* Detail panel */}
        {selected && (
          <div className="flex-1 min-w-0 rounded-lg border border-gray-200 bg-white p-4">
            <div className="mb-3 flex items-center gap-2">
              <Badge tone="neutral">{objectTypeLabel(selected.object_type)}</Badge>
              <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${statusColor(selected.status)}`}>
                {statusLabel(selected.status)}
              </span>
            </div>
            <CorrectionDetailPanel correction={selected} jobId={jobId} onUpdated={handleUpdated} />
          </div>
        )}
      </div>
    </div>
  );
}
