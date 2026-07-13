import { render } from "@testing-library/react";
import { axe } from "jest-axe";
import { ValidationIssueTable } from "@/components/ValidationIssueTable";

// Validation Center (Phase F-2.1 minimum scope). jobId/onIssueUpdated are
// optional (component's own docstring: "still works read-only"), so this
// exercises the real component with no API mocking needed.
describe("Validation Center (ValidationIssueTable) accessibility", () => {
  it("has no automatically detectable accessibility violations (empty state)", async () => {
    const { container } = render(<ValidationIssueTable issues={[]} />);

    expect(await axe(container)).toHaveNoViolations();
  });
});
