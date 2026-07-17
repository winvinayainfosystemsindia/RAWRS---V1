import { render } from "@testing-library/react";
import { axe } from "jest-axe";
import { ContextInspectorRail } from "@/components/workspace/ContextInspectorRail";
import { DocumentDataProvider } from "@/lib/store/DocumentDataContext";
import { SelectionProvider } from "@/lib/store/SelectionContext";
import { PdfViewportProvider } from "@/lib/store/PdfViewportContext";

// Phase R-4 M3 — ContextInspectorRail's no-selection fallback (the
// severity-count summary + "Open Validation Center" button, Phase R-2 M5)
// had never had a dedicated accessibility test; it's a real, new surface,
// not a duplicate of the Validation Center's own tests, since it renders
// a different, consolidated summary rather than the full issue table.
// Same provider-wrapping pattern as reviewer-workspace.a11y.test.tsx —
// all three providers are plain synchronous local state, safe to use
// unmodified rather than mocked.
describe("Context Inspector Rail accessibility", () => {
  it("has no automatically detectable accessibility violations (no selection, empty validation)", async () => {
    const { container } = render(
      <PdfViewportProvider>
        <SelectionProvider>
          <DocumentDataProvider>
            <ContextInspectorRail jobId="test-job" aiStatus={null} onOpenValidation={() => {}} />
          </DocumentDataProvider>
        </SelectionProvider>
      </PdfViewportProvider>
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
