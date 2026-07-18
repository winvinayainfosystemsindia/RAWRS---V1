"use client";

import { useState } from "react";
import { api, type CorrectionItem } from "@/lib/api";
import { Badge } from "./Badge";
import { EvidenceBreakdown } from "./EvidenceBreakdown";
import { parseCorrectionPayload, type CorrectionPreview } from "@/lib/correctionPreview";
import { useToast } from "./Toast";

interface Props {
  corrections: CorrectionItem[];
  jobId: string;
  onUpdated: (updated: CorrectionItem) => void;
  onCorrectionClick?: (correction: CorrectionItem) => void;
  emptyMessage?: string;
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

function statusTone(status: string): "success" | "danger" | "info" | "neutral" | "warning" {
  switch (status) {
    case "accepted":
    case "auto_applied": return "success";
    case "rejected": return "danger";
    case "edited": return "info";
    case "ignored": return "neutral";
    case "reverted": return "warning";
    default: return "warning"; // proposed / pending_review
  }
}

function objectTypeLabel(objectType: string): string {
  return objectType.charAt(0).toUpperCase() + objectType.slice(1);
}

function CorrectionRow({ correction, jobId, onUpdated, onCorrectionClick }: { correction: CorrectionItem; jobId: string; onUpdated: (updated: CorrectionItem) => void; onCorrectionClick?: (c: CorrectionItem) => void }) {
  const [editValue, setEditValue] = useState(correction.suggested_value);
  const [reviewerNotes, setReviewerNotes] = useState(correction.reviewer_notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();

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
      if (action === "accept" || action === "reject") {
        const label = action === "accept" ? "Accepted" : "Rejected";
        toast(`${label}: ${correction.problem}`, {
          label: "Undo",
          onClick: () => {
            api.reviewCorrection(jobId, correction.correction_id, { action: "undo" })
              .then((reverted) => onUpdated(reverted))
              .catch(() => {});
          },
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setSaving(false);
    }
  }

  const isDecided = !["proposed", "pending_review"].includes(correction.status);

  // Phase RW-1: some verifiers (footnotes/headings/lists/tables) encode a
  // structured payload as a JSON string in current_value/suggested_value
  // rather than a plain string — rendered as-is, that was raw JSON shown
  // as "the suggestion" to a reviewer. Prefer the suggested shape (what
  // RAWRS wants to insert) as the card's headline; the current shape
  // (e.g. a footnote's old anchor page) supplies "what was there before"
  // context when both parse. Neither parsing (the common case — image
  // alt text, page-label text, plain corrected strings) falls back to
  // the plain Detected/Suggested fix pair below, unchanged in shape.
  const suggestedPreview: CorrectionPreview | null = parseCorrectionPayload(correction.suggested_value);
  const currentPreview: CorrectionPreview | null = parseCorrectionPayload(correction.current_value);
  const preview = suggestedPreview ?? currentPreview;

  return (
    <div className="rounded-lg border border-border bg-surface-panel p-3 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge tone="neutral">{objectTypeLabel(correction.object_type)}</Badge>
          <Badge tone={statusTone(correction.status)}>{statusLabel(correction.status)}</Badge>
          {correction.confidence !== null && (
            <span className="text-xs text-text-secondary">
              {(correction.confidence * 100).toFixed(0)}%
            </span>
          )}
        </div>
        {onCorrectionClick && (
          <button
            type="button"
            onClick={() => onCorrectionClick(correction)}
            className="shrink-0 rounded border border-border px-2 py-0.5 text-xs font-medium text-accent hover:bg-hover-row"
          >
            Jump →
          </button>
        )}
      </div>

      <div>
        {preview && <p className="text-sm font-semibold text-text-primary">{preview.kind}</p>}
        <p className="text-sm text-text-primary">{correction.problem}</p>
        {correction.page_number !== null && (
          <p className="text-xs text-text-secondary">Detected on page {correction.page_number}</p>
        )}
      </div>

      {preview ? (
        <dl className="space-y-1.5 rounded-lg border border-border bg-surface-canvas p-3">
          {preview.fields.map((f) => (
            <div key={f.label}>
              <dt className="text-xs font-semibold text-text-secondary uppercase tracking-wider">{f.label}</dt>
              <dd className="text-sm text-text-primary break-words">{f.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">Detected</p>
            <p className="text-sm text-text-primary break-words">{correction.current_value || "—"}</p>
          </div>
          <div>
            <p className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">Suggested fix</p>
            <p className="text-sm text-success break-words">{correction.suggested_value || "—"}</p>
          </div>
        </div>
      )}

      {correction.reason && <p className="text-sm text-text-secondary">Reason: {correction.reason}</p>}

      <EvidenceBreakdown evidence={correction.evidence} />

      {!isDecided && (
        <div>
          <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
            Edit suggested value
          </label>
          <input
            type="text"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            className="w-full rounded border border-border bg-surface-canvas px-2 py-1.5 text-sm font-mono text-text-primary focus:border-accent focus:outline-none"
            disabled={saving}
          />
        </div>
      )}

      <div>
        <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
          Reviewer Notes <span className="font-normal text-text-secondary/70">(optional)</span>
        </label>
        <input
          type="text"
          value={reviewerNotes}
          onChange={(e) => setReviewerNotes(e.target.value)}
          className="w-full rounded border border-border bg-surface-canvas px-2 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
          disabled={saving}
        />
      </div>

      {error && <p className="text-sm text-danger" role="alert">{error}</p>}

      <div className="flex flex-wrap gap-2">
        {!isDecided && (
          <>
            <button
              onClick={() => act("accept")}
              disabled={saving}
              className="rounded bg-success px-3 py-1.5 text-sm font-medium text-accent-contrast hover:opacity-90 disabled:opacity-50"
            >
              {saving ? "Working…" : "Accept"}
            </button>
            <button
              onClick={() => act("edit", editValue)}
              disabled={saving || editValue === correction.suggested_value}
              className="rounded bg-accent px-3 py-1.5 text-sm font-medium text-accent-contrast hover:opacity-90 disabled:opacity-50"
            >
              Accept &amp; Edit
            </button>
            <button
              onClick={() => act("reject")}
              disabled={saving}
              className="rounded border border-danger/40 px-3 py-1.5 text-sm font-medium text-danger hover:bg-danger/10 disabled:opacity-50"
            >
              Reject
            </button>
            <button
              onClick={() => act("ignore")}
              disabled={saving}
              className="rounded border border-border px-3 py-1.5 text-sm font-medium text-text-secondary hover:bg-hover-row disabled:opacity-50"
            >
              Ignore
            </button>
            {correction.status !== "pending_review" && (
              <button
                onClick={() => act("needs_review")}
                disabled={saving}
                className="rounded border border-warning/40 px-3 py-1.5 text-sm font-medium text-warning hover:bg-warning/10 disabled:opacity-50"
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
            className="rounded border border-border px-3 py-1.5 text-sm font-medium text-text-primary hover:bg-hover-row disabled:opacity-50"
          >
            {saving ? "Working…" : "Undo"}
          </button>
        )}
      </div>

      {/* Phase RW-1 issue #2: raw/technical fields (rule id, internal
          field name, ids, and the raw current/suggested strings this
          card already parsed into the friendly view above) live behind
          a collapsed-by-default disclosure, placed after the action
          buttons so expanding it never pushes Accept/Reject out of
          reach (issue #6 — long-content ergonomics). Same native
          <details> pattern already used elsewhere (Export menu,
          Overview, Processing Log). */}
      <details className="rounded border border-border">
        <summary className="cursor-pointer select-none px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-text-secondary hover:text-text-primary">
          Developer Details
        </summary>
        <dl className="space-y-2 border-t border-border p-3 text-xs">
          <div>
            <dt className="font-semibold text-text-secondary uppercase tracking-wider">Rule</dt>
            <dd className="font-mono text-text-primary">{correction.rule_id ?? "—"}</dd>
          </div>
          <div>
            <dt className="font-semibold text-text-secondary uppercase tracking-wider">Field</dt>
            <dd className="font-mono text-text-primary">{correction.field}</dd>
          </div>
          <div>
            <dt className="font-semibold text-text-secondary uppercase tracking-wider">Detected value (raw)</dt>
            <dd className="whitespace-pre-wrap break-words font-mono text-text-primary">
              {correction.current_value || "—"}
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-text-secondary uppercase tracking-wider">Suggested value (raw)</dt>
            <dd className="whitespace-pre-wrap break-words font-mono text-text-primary">
              {correction.suggested_value || "—"}
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-text-secondary uppercase tracking-wider">IDs</dt>
            <dd className="font-mono text-text-primary">
              correction: {correction.correction_id} · object: {correction.object_id ?? "—"}
            </dd>
          </div>
        </dl>
      </details>
    </div>
  );
}

// Shared by CorrectionsPanel (all corrections) and ObjectInspectorFrame
// (corrections filtered to one object) — one implementation, never
// diverging, per the approved architecture amendment.
export function CorrectionHistoryList({ corrections, jobId, onUpdated, onCorrectionClick, emptyMessage }: Props) {
  if (corrections.length === 0) {
    return (
      <p className="text-sm text-text-secondary">
        {emptyMessage ?? "No corrections."}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {corrections.map((correction) => (
        <CorrectionRow
          key={correction.correction_id}
          correction={correction}
          jobId={jobId}
          onUpdated={onUpdated}
          onCorrectionClick={onCorrectionClick}
        />
      ))}
    </div>
  );
}
