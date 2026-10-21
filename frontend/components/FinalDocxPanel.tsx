"use client";

import { useEffect, useState, type ChangeEvent } from "react";
import { api, type ChecklistChange, type FinalDocxReview } from "@/lib/api";

// The learning loop's last step (docs/LEARNING_LOOP.md): the remediator
// uploads the DOCX they finished in Word, and the backend reports what they
// changed relative to RAWRS's export and how the checklist moved. Nothing here
// changes the document; it is what RAWRS learns from.

const MAX_EDITS_SHOWN = 200; // ponytail: plain cap; paginate if real reviews exceed it

function categoryLabel(category: string): string {
  const words = category.toLowerCase().replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function percent(share: number | null): string {
  return share === null ? "—" : `${Math.round(share * 100)}%`;
}

function ChangeList({ label, items, tone }: { label: string; items: ChecklistChange[]; tone: "success" | "danger" }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className={`text-xs font-semibold ${tone === "success" ? "text-success" : "text-danger"}`}>{label}</h3>
      <ul aria-label={label} className="mt-1 space-y-1">
        {items.map((item) => (
          <li key={item.item_id} className="text-sm text-text-primary">
            {item.requirement}{" "}
            <span className="text-xs text-text-secondary">
              ({item.before} → {item.after})
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ReviewSummary({ review }: { review: FinalDocxReview }) {
  const { summary, edits } = review.diff;
  const categories = Object.entries(summary.by_category);
  return (
    <div className="space-y-4">
      <p className="text-sm text-text-primary" aria-live="polite">
        <strong>{percent(summary.kept_share)}</strong> of RAWRS&apos;s content was kept unchanged ·{" "}
        <strong>{summary.edits}</strong> {summary.edits === 1 ? "edit" : "edits"} in{" "}
        <span className="text-text-secondary">{review.final_filename}</span>
      </p>
      <p className="text-xs text-text-secondary">
        {review.baseline === "downloaded_copy"
          ? "Compared with the DOCX downloaded from RAWRS."
          : "No download was recorded, so this was compared with RAWRS's current export."}
      </p>

      {categories.length > 0 && (
        <ul aria-label="Edits by kind" className="flex flex-wrap gap-2">
          {categories.map(([category, count]) => (
            <li key={category} className="rounded bg-surface-elevated px-2 py-1 text-xs text-text-primary">
              {categoryLabel(category)} <span className="font-semibold">{count}</span>
            </li>
          ))}
        </ul>
      )}

      {review.checklist && (
        <div className="space-y-2">
          <ChangeList label="Checklist items the remediator fixed" items={review.checklist.fixed_by_remediator} tone="success" />
          <ChangeList label="Checklist items that regressed" items={review.checklist.regressed_by_remediator} tone="danger" />
        </div>
      )}

      {edits.length > 0 && (
        <details className="rounded-lg border border-border">
          <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-text-primary">
            Every edit ({edits.length})
          </summary>
          <ol className="divide-y divide-border border-t border-border">
            {edits.slice(0, MAX_EDITS_SHOWN).map((edit, index) => (
              <li key={index} className="px-3 py-2 text-sm">
                <span className="text-xs font-semibold text-text-secondary">{categoryLabel(edit.category)}</span>
                <p className="mt-0.5 break-words text-text-primary">
                  {edit.before && <del className="text-danger">{edit.before}</del>}
                  {edit.before && edit.after && " → "}
                  {edit.after && <ins className="text-success no-underline">{edit.after}</ins>}
                </p>
              </li>
            ))}
          </ol>
          {edits.length > MAX_EDITS_SHOWN && (
            <p className="border-t border-border px-3 py-2 text-xs text-text-secondary">
              Showing the first {MAX_EDITS_SHOWN}; the full list is in the learning dataset.
            </p>
          )}
        </details>
      )}
    </div>
  );
}

export function FinalDocxPanel({ jobId }: { jobId: string }) {
  const [review, setReview] = useState<FinalDocxReview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getFinalDocxReview(jobId)
      .then((result) => {
        if (!cancelled) setReview(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load the comparison.");
      });
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setIsBusy(true);
    setError(null);
    try {
      setReview(await api.uploadFinalDocx(jobId, file));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not compare the document.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleForget() {
    setIsBusy(true);
    setError(null);
    try {
      await api.deleteFinalDocxReview(jobId);
      setReview(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove the comparison.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <section aria-labelledby="final-docx-heading" className="space-y-3 rounded-xl border border-border bg-surface-panel p-5">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="final-docx-heading" className="text-base font-semibold text-text-primary">
          Finished in Word
        </h2>
        <label className="ml-auto cursor-pointer rounded border border-border px-3 py-1 text-xs font-medium text-text-primary focus-within:ring-2 focus-within:ring-accent hover:bg-surface-elevated">
          {isBusy ? "Comparing…" : review ? "Upload a newer version" : "Upload finished DOCX"}
          <input
            type="file"
            accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            className="sr-only"
            onChange={handleFile}
            disabled={isBusy}
          />
        </label>
        {review && (
          <button
            type="button"
            onClick={handleForget}
            disabled={isBusy}
            className="rounded px-2 py-1 text-xs text-text-secondary hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
          >
            Forget this comparison
          </button>
        )}
      </div>
      <p className="text-xs text-text-secondary">
        After finishing the document in Word, upload it here. RAWRS compares it with its own export and learns from
        what was changed — the document itself is not altered.
      </p>

      {error && (
        <p role="alert" className="rounded border border-danger/30 bg-danger/5 p-3 text-sm text-danger">
          {error}
        </p>
      )}

      {review && <ReviewSummary review={review} />}
    </section>
  );
}
