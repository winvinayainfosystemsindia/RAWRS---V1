import { render } from "@testing-library/react";
import { axe } from "jest-axe";
import { CorrectionsPanel } from "@/components/CorrectionsPanel";

// Corrections Center (Phase F-2.1 minimum scope). Pure-props component,
// no context needed.
describe("Corrections Center (CorrectionsPanel) accessibility", () => {
  it("has no automatically detectable accessibility violations (empty state)", async () => {
    const { container } = render(
      <CorrectionsPanel corrections={[]} jobId="test-job" onCorrectionsUpdated={() => {}} />
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
