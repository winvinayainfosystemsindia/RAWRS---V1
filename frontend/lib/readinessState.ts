import type { AccessibilityReport } from "@/lib/api";

export type ReadinessLabel = "Validating" | "Validation unavailable" | "Export Ready" | "Needs Review" | "Blocked";

export interface ReadinessState {
  label: ReadinessLabel;
  detail: string;
  score: number | null;
}

// Names the backend's verdict; never decides it. export_ready is the only
// readiness authority. The blocker split only reads each blocking evaluation's
// outcome: a FAIL must be fixed (Blocked), MANUAL_REVIEW_REQUIRED needs a
// human decision (Needs Review).
export function readinessState(report: AccessibilityReport | null, reportFailed: boolean): ReadinessState {
  if (!report) {
    return reportFailed
      ? { label: "Validation unavailable", detail: "The accessibility report could not be loaded.", score: null }
      : { label: "Validating", detail: "Loading the accessibility report.", score: null };
  }
  const score = report.overall_score;
  if (report.export_ready) return { label: "Export Ready", detail: "No blocking failures.", score };

  // Mirrors src/accessibility/scoring.py _evaluation_label.
  const blockers = new Set(report.blocking_failures);
  const failing = report.evaluations.filter(
    (e) => e.outcome === "fail" && blockers.has(e.object_id ? `${e.rule_id}:${e.object_id}` : e.rule_id)
  ).length;
  const review = report.blocking_failures.length - failing;
  const parts = [failing && `${failing} must be fixed`, review && `${review} need review`].filter(Boolean);
  return {
    label: failing > 0 ? "Blocked" : "Needs Review",
    detail: `${report.blocking_failures.length} blocking: ${parts.join(", ")}.`,
    score,
  };
}
