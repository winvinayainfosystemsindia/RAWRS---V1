import { render } from "@testing-library/react";
import { axe } from "jest-axe";
import { ReviewerWorkspace } from "@/components/ReviewerWorkspace";
import { DocumentDataProvider } from "@/lib/store/DocumentDataContext";
import { SelectionProvider } from "@/lib/store/SelectionContext";
import { PdfViewportProvider } from "@/lib/store/PdfViewportContext";
import { ReviewQueueProvider } from "@/lib/store/ReviewQueueContext";
import { ToastProvider } from "@/components/Toast";

// Reviewer Workspace (Phase F-2.1 minimum scope). DocumentDataProvider/
// SelectionProvider/PdfViewportProvider are all plain, synchronous local
// state (no fetching inside the providers themselves), so the real
// providers are used unmodified rather than mocked. Empty-state baseline
// (no corrections loaded) — exercises the empty message and status-tab
// chrome; the keyboard-shortcut interaction paths are a follow-up.
describe("Reviewer Workspace accessibility", () => {
  it("has no automatically detectable accessibility violations (empty state)", async () => {
    const { container } = render(
      <PdfViewportProvider>
        <SelectionProvider>
          <DocumentDataProvider>
            <ReviewQueueProvider>
              <ToastProvider>
                <ReviewerWorkspace jobId="test-job" />
              </ToastProvider>
            </ReviewQueueProvider>
          </DocumentDataProvider>
        </SelectionProvider>
      </PdfViewportProvider>
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
