import { render } from "@testing-library/react";
import { axe } from "jest-axe";
import { ValidationIssueTable } from "@/components/ValidationIssueTable";
import type { ValidationIssue } from "@/lib/api";

// Validation Center (Phase F-2.1 minimum scope). jobId/onIssueUpdated are
// optional (component's own docstring: "still works read-only"), so this
// exercises the real component with no API mocking needed.
describe("Validation Center (ValidationIssueTable) accessibility", () => {
  it("has no automatically detectable accessibility violations (empty state)", async () => {
    const { container } = render(<ValidationIssueTable issues={[]} />);

    expect(await axe(container)).toHaveNoViolations();
  });

  // Phase R-4 M3 — the empty-state test above never exercised the
  // severity ARIA tabs (Phase R-1.1) or the readiness banner's
  // Check/Warning icon (Phase R-3) — both only render when there's at
  // least one issue and a readiness object, respectively. Real shape,
  // not a mock: matches ValidationIssue/ReadinessReport from lib/api.ts.
  it("has no automatically detectable accessibility violations (populated issues + readiness banner)", async () => {
    const issues: ValidationIssue[] = [
      {
        issue_id: "1",
        severity: "error",
        rule_id: "HEADING_001",
        message: "Heading levels skip from H1 to H3.",
        page_number: 2,
        suggested_action: "Insert an H2 or renumber the heading.",
        status: "open",
        reviewed_at: null,
      },
      {
        issue_id: "2",
        severity: "warning",
        rule_id: "IMAGE_002",
        message: "Figure is missing alt text.",
        page_number: 4,
        suggested_action: null,
        status: "open",
        reviewed_at: null,
      },
    ];

    const { container } = render(
      <ValidationIssueTable
        issues={issues}
        readiness={{ ready: false, overall_score: 0.72, categories: [] }}
      />
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
