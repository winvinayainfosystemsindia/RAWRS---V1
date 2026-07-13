import { render } from "@testing-library/react";
import { axe } from "jest-axe";
import { ImageGrid } from "@/components/ImageGrid";

// Image Workspace (Phase F-2.1 minimum scope). ImageGrid takes plain props,
// no context needed. Empty-state baseline — exercises the filter toolbar
// and empty message; per-image card interaction states are a follow-up
// (see docs/ACCESSIBILITY_TESTING.md backlog).
describe("Image Workspace (ImageGrid) accessibility", () => {
  it("has no automatically detectable accessibility violations (empty state)", async () => {
    const { container } = render(
      <ImageGrid images={[]} jobId="test-job" aiStatus={null} onImagesUpdated={() => {}} />
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
