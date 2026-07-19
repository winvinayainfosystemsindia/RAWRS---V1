"use client";

import { useRef, useState } from "react";
import { type CorrectionItem, type CorrectionAction } from "@/lib/api";
import { Badge } from "./Badge";
import { EvidenceBreakdown } from "./EvidenceBreakdown";
import { parseCorrectionPayload, type CorrectionPreview } from "@/lib/correctionPreview";
import { useReviewAction } from "@/lib/hooks/useReviewAction";

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

const OBJECT_TYPE_TONE: Record<string, "info" | "warning" | "success" | "danger" | "neutral"> = {
  heading: "info",
  image: "warning",
  table: "success",
  footnote: "neutral",
  reading_order: "danger",
  metadata: "neutral",
};

function confidenceLabel(confidence: number): { text: string; tone: string } {
  if (confidence >= 0.95) return { text: "Very High", tone: "text-success" };
  if (confidence >= 0.80) return { text: "High", tone: "text-success" };
  if (confidence >= 0.60) return { text: "Moderate", tone: "text-warning" };
  if (confidence >= 0.40) return { text: "Requires Review", tone: "text-warning" };
  return { text: "Low Confidence", tone: "text-danger" };
}

const ACCESSIBILITY_IMPACT: Record<string, string> = {
  heading: "Screen reader users rely on heading hierarchy to navigate document structure.",
  image: "Users of assistive technology receive no meaningful information without alternative text.",
  table: "Tables without proper structure become incomprehensible to assistive technology users.",
  footnote: "Footnote references must be navigable for non-visual readers.",
  reading_order: "Content delivered out of order confuses assistive technology users.",
  metadata: "Document metadata helps assistive technology orient users within the document.",
  list: "List structure lets assistive technology announce item count and position; without it, items read as loose prose.",
  callout: "Callouts and asides need semantic grouping so assistive technology can convey their distinct role.",
  paragraph: "Correct text structure keeps reading order and flow intelligible to non-visual readers.",
  caption: "Captions must be programmatically tied to their figure or table to be reachable by assistive technology.",
  front_matter: "Front-matter structure orients assistive-technology users at the start of the document.",
};

// Every object type explains why it matters — no silent fallback (P2-8). A
// type without a specific line still gets an honest generic one rather than
// rendering nothing.
const GENERIC_IMPACT =
  "Correcting this improves how assistive technology interprets the document's structure and content.";

function editFieldWarning(value: string, objectType: string): string | null {
  if (!value.trim()) return "Empty value — this will not resolve the accessibility issue.";
  if (objectType === "image" && value.trim().length < 10) return "Very short — consider whether this provides meaningful context.";
  if (/^(image|photo|picture|figure|table|heading)$/i.test(value.trim())) return "Placeholder text detected — describe the actual content.";
  return null;
}

function CorrectionRow({ correction, jobId, onUpdated, onCorrectionClick }: { correction: CorrectionItem; jobId: string; onUpdated: (updated: CorrectionItem) => void; onCorrectionClick?: (c: CorrectionItem) => void }) {
  const [editValue, setEditValue] = useState(correction.suggested_value);
  const [reviewerNotes, setReviewerNotes] = useState(correction.reviewer_notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const editRef = useRef<HTMLInputElement>(null);
  const { review } = useReviewAction(jobId);

  // Thin wrapper over the shared review pipeline: the hook owns the API call,
  // toast + undo, error toast, and the post-action score refresh — this only
  // adds the card's local saving/inline-error UI. Keyboard path
  // (ReviewerWorkspace) uses the same hook, so the two can't drift (P1-5).
  async function act(action: CorrectionAction, proposedValue?: string) {
    setSaving(true);
    setError(null);
    try {
      await review(correction, action, { proposedValue, reviewerNotes, onUpdated });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setSaving(false);
    }
  }

  const isDecided = !["proposed", "pending_review"].includes(correction.status);
  const suggestedPreview: CorrectionPreview | null = parseCorrectionPayload(correction.suggested_value);
  const currentPreview: CorrectionPreview | null = parseCorrectionPayload(correction.current_value);
  const preview = suggestedPreview ?? currentPreview;
  const conf = correction.confidence !== null ? confidenceLabel(correction.confidence) : null;
  const impact = ACCESSIBILITY_IMPACT[correction.object_type] ?? GENERIC_IMPACT;
  const warning = editFieldWarning(editValue, correction.object_type);

  return (
    <div className="rounded-lg border border-border bg-surface-panel p-4 space-y-3">
      {/* Row 1: Type + Location + Status + Jump */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge tone={OBJECT_TYPE_TONE[correction.object_type] ?? "neutral"}>{objectTypeLabel(correction.object_type)}</Badge>
          {correction.page_number !== null && (
            <span className="text-xs text-text-secondary">Page {correction.page_number}</span>
          )}
          <Badge tone={statusTone(correction.status)}>{statusLabel(correction.status)}</Badge>
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

      {/* Row 2: Problem headline — the primary focal point */}
      <div>
        {preview && <p className="text-xs font-medium text-text-secondary">{preview.kind}</p>}
        <p className="text-sm font-semibold text-text-primary leading-snug">{correction.problem}</p>
      </div>

      {/* Row 3: Accessibility Impact — why this matters */}
      {impact && (
        <p className="text-xs text-text-secondary italic">{impact}</p>
      )}

      {/* Row 4: Recommended Fix / Current vs Suggested */}
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
            <p className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">Current</p>
            <p className="text-sm text-text-primary break-words">{correction.current_value || "—"}</p>
          </div>
          <div>
            <p className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">Recommended Fix</p>
            <p className="text-sm text-success break-words">{correction.suggested_value || "—"}</p>
          </div>
        </div>
      )}

      {/* Row 5: Confidence + Detection Reason */}
      <div className="flex items-baseline gap-3 text-xs">
        {conf && (
          <span className={`font-medium ${conf.tone}`}>{conf.text} confidence</span>
        )}
        {correction.reason && (
          <span className="text-text-secondary">{correction.reason}</span>
        )}
      </div>

      {/* Row 6: Evidence */}
      <EvidenceBreakdown evidence={correction.evidence} />

      {/* Row 7: Edit field with live validation */}
      {!isDecided && (
        <div>
          <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
            Edit value
          </label>
          <input
            ref={editRef}
            type="text"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            className="w-full rounded border border-border bg-surface-canvas px-2 py-1.5 text-sm font-mono text-text-primary focus:border-accent focus:outline-none"
            disabled={saving}
          />
          {warning && (
            <p className="mt-1 text-xs text-warning">{warning}</p>
          )}
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

      {/* Row 8: Actions */}
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
              onClick={() => {
                act("edit", editValue);
                editRef.current?.focus();
                editRef.current?.select();
              }}
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

      {/* Technical details — collapsed by default */}
      <details className="rounded border border-border">
        <summary className="cursor-pointer select-none px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-text-secondary hover:text-text-primary">
          Technical Details
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
