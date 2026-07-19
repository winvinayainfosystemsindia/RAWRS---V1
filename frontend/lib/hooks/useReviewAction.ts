"use client";

import { useCallback } from "react";
import { api, type CorrectionItem, type CorrectionAction } from "@/lib/api";
import { useDocumentDispatch } from "@/lib/store/DocumentDataContext";
import { useToast } from "@/components/Toast";

// The single review-action pipeline. Both the card buttons
// (CorrectionHistoryList) and the keyboard-first queue (ReviewerWorkspace)
// route every accept/reject/edit/ignore/needs_review/undo through this hook,
// so they can never drift on undo, error handling, notifications, or the
// post-action intelligence refresh — that divergence was exactly the audit's
// P1-5 finding (keyboard path silently bypassed the toast + error handling).
//
// After any mutating action, the readiness score / accessibility report /
// category totals are re-fetched (P0-1): the review response only carries the
// updated correction, not the document-wide score, and the score is computed
// server-side over every correction. This is event-driven off the action —
// no new polling loop — so the number moves the moment the reviewer acts
// instead of staying frozen until reload.

interface ReviewOptions {
  proposedValue?: string;
  reviewerNotes?: string;
  // Suppress the toast (bulk review shows its own single summary toast).
  silent?: boolean;
  // Suppress the intelligence refetch (bulk review refreshes once at the end
  // rather than once per item).
  skipRefresh?: boolean;
  // Optional caller side-channel, fired on the action result AND on undo.
  // Every current caller uses this only to mirror the correction into the
  // store — which this hook already does — so it's redundant for them, but
  // kept so a caller with local state stays correct and behaviour is
  // identical to before centralization.
  onUpdated?: (c: CorrectionItem) => void;
}

const ACTION_LABEL: Partial<Record<CorrectionAction, string>> = {
  accept: "Accepted",
  reject: "Rejected",
  edit: "Edited",
  ignore: "Ignored",
};

export function useReviewAction(jobId: string) {
  const dispatch = useDocumentDispatch();
  const { toast } = useToast();

  // Re-pull the document-wide intelligence after a mutation. Both GETs are
  // idempotent; failures degrade to leaving the current values in place
  // (never blanking a real score to null on a transient blip).
  const refreshIntelligence = useCallback(async () => {
    const [readiness, report] = await Promise.all([
      api.getReadiness(jobId).then((r) => r).catch(() => undefined),
      api.getAccessibilityReport(jobId).then((r) => r).catch(() => undefined),
    ]);
    if (readiness !== undefined) dispatch({ type: "SET_READINESS", readiness });
    if (report !== undefined) dispatch({ type: "SET_ACCESSIBILITY_REPORT", report });
  }, [jobId, dispatch]);

  // Runs one action end to end. Returns the updated correction, or throws so
  // a caller that wants inline error UI (the card) can still catch it — the
  // toast fires regardless so the keyboard path is never silent.
  const review = useCallback(
    async (
      correction: CorrectionItem,
      action: CorrectionAction,
      opts: ReviewOptions = {}
    ): Promise<CorrectionItem> => {
      try {
        const updated = await api.reviewCorrection(jobId, correction.correction_id, {
          action,
          proposed_value: opts.proposedValue,
          reviewer_notes: opts.reviewerNotes || undefined,
        });
        dispatch({ type: "UPDATE_CORRECTION", correction: updated });
        opts.onUpdated?.(updated);

        if (!opts.skipRefresh) void refreshIntelligence();

        const label = ACTION_LABEL[action];
        if (label && !opts.silent) {
          const undoable = action === "accept" || action === "reject" || action === "edit";
          toast(`${label}: ${correction.problem}`, undoable ? {
            label: "Undo",
            onClick: () => {
              api.reviewCorrection(jobId, correction.correction_id, { action: "undo" })
                .then((reverted) => {
                  dispatch({ type: "UPDATE_CORRECTION", correction: reverted });
                  opts.onUpdated?.(reverted);
                  void refreshIntelligence();
                })
                .catch(() => toast("Undo failed — please retry"));
            },
          } : undefined);
        }
        return updated;
      } catch (err) {
        toast(`${ACTION_LABEL[action] ?? "Action"} failed: ${err instanceof Error ? err.message : "please retry"}`);
        throw err;
      }
    },
    [jobId, dispatch, toast, refreshIntelligence]
  );

  return { review, refreshIntelligence };
}
