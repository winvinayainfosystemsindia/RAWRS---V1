import { readinessState } from "@/lib/readinessState";
import type { AccessibilityReport, AccessibilityRuleEvaluation } from "@/lib/api";

const ev = (rule_id: string, outcome: AccessibilityRuleEvaluation["outcome"], object_id: string | null = null) =>
  ({ rule_id, outcome, object_id }) as AccessibilityRuleEvaluation;

const report = (blocking_failures: string[], evaluations: AccessibilityRuleEvaluation[]) =>
  ({ overall_score: 0.92, export_ready: blocking_failures.length === 0, blocking_failures, evaluations }) as AccessibilityReport;

describe("readinessState", () => {
  it("says Validating until the report arrives, and admits a failed load", () => {
    expect(readinessState(null, false).label).toBe("Validating");
    expect(readinessState(null, true).label).toBe("Validation unavailable");
  });

  it("trusts export_ready and nothing else for Export Ready", () => {
    expect(readinessState(report([], [ev("HEADING_001", "fail", "h1")]), false).label).toBe("Export Ready");
  });

  it("calls review-only blockers Needs Review", () => {
    const s = readinessState(report(["REVIEW_001"], [ev("REVIEW_001", "manual_review_required")]), false);
    expect(s).toEqual({ label: "Needs Review", detail: "1 blocking: 1 need review.", score: 0.92 });
  });

  it("calls any failing blocker Blocked", () => {
    const s = readinessState(
      report(["HEADING_001:h1", "REVIEW_001"], [
        ev("HEADING_001", "fail", "h1"),
        ev("HEADING_001", "fail", "h2"), // non-blocking fail: not counted
        ev("REVIEW_001", "manual_review_required"),
      ]),
      false
    );
    expect(s.label).toBe("Blocked");
    expect(s.detail).toBe("2 blocking: 1 must be fixed, 1 need review.");
  });
});
