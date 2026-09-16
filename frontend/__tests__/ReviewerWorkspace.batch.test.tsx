import { useEffect, type ReactNode } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { ReviewerWorkspace } from "@/components/ReviewerWorkspace";
import { api, type CorrectionItem } from "@/lib/api";
import { DocumentDataProvider, useDocumentDispatch } from "@/lib/store/DocumentDataContext";
import { SelectionProvider } from "@/lib/store/SelectionContext";
import { PdfViewportProvider } from "@/lib/store/PdfViewportContext";
import { ReviewQueueProvider } from "@/lib/store/ReviewQueueContext";
import { ToastProvider } from "@/components/Toast";

// Batch review must follow cause, never confidence: every item below is 0.99.
const item = (id: string, over: Partial<CorrectionItem> = {}): CorrectionItem => ({
  correction_id: id,
  object_type: "heading",
  object_id: `h-${id}`,
  field: "level_mismatch",
  problem: `Level mismatch ${id}`,
  current_value: "3",
  suggested_value: "2",
  reason: "Heading level disagrees with PDF typography.",
  confidence: 0.99,
  evidence: [],
  status: "proposed",
  created_at: `2026-09-16T00:00:0${id.length}Z`,
  reviewed_at: null,
  reviewer_notes: null,
  rule_id: "HEADING_VERIFY_003",
  severity: "warning",
  page_number: 1,
  reason_code: "HEADING_LEVEL_MISMATCH",
  ...over,
});

function Seed({ corrections, children }: { corrections: CorrectionItem[]; children: ReactNode }) {
  const dispatch = useDocumentDispatch();
  useEffect(() => {
    dispatch({ type: "REPLACE_CORRECTIONS", corrections });
  }, [dispatch, corrections]);
  return <>{children}</>;
}

function renderQueue(corrections: CorrectionItem[]) {
  return render(
    <PdfViewportProvider>
      <SelectionProvider>
        <DocumentDataProvider>
          <ReviewQueueProvider>
            <ToastProvider>
              <Seed corrections={corrections}>
                <ReviewerWorkspace jobId="job-1" />
              </Seed>
            </ToastProvider>
          </ReviewQueueProvider>
        </DocumentDataProvider>
      </SelectionProvider>
    </PdfViewportProvider>
  );
}

beforeEach(() => {
  window.localStorage.clear();
  jest.spyOn(api, "getAccessibilityReport").mockResolvedValue(undefined as never);
});

afterEach(() => jest.restoreAllMocks());

describe("ReviewerWorkspace batch review", () => {
  it("offers no batch accept when the pending view mixes causes, however confident", () => {
    renderQueue([
      item("a"),
      item("b", { field: "text_correction", rule_id: "HEADING_VERIFY_004", reason_code: "HEADING_TEXT_OCR_ERROR" }),
    ]);

    expect(screen.queryByRole("button", { name: /Accept all/i })).toBeNull();
    expect(screen.getByText(/filter by Rule/i)).toBeInTheDocument();
  });

  it("accepts one cause as a single request", async () => {
    const bulk = jest
      .spyOn(api, "bulkReviewCorrections")
      .mockResolvedValue({ corrections: [item("a", { status: "accepted" }), item("b", { status: "accepted" })] });
    renderQueue([item("a"), item("b")]);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Accept all 2 HEADING_VERIFY_003 corrections in view" }));
    });

    expect(bulk).toHaveBeenCalledTimes(1);
    expect(bulk).toHaveBeenCalledWith("job-1", ["a", "b"], "accept");
    expect(await screen.findByText("Accepted 2 HEADING_VERIFY_003 corrections")).toBeInTheDocument();
  });

  it("reports a refused batch as nothing changed, never as accepted", async () => {
    jest.spyOn(api, "bulkReviewCorrections").mockRejectedValue(new Error("failed on correction b; nothing was changed."));
    renderQueue([item("a"), item("b")]);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Accept all 2/ }));
    });

    expect(await screen.findByText(/Nothing changed/)).toBeInTheDocument();
    expect(screen.queryByText(/^Accepted 2/)).toBeNull();
    expect(screen.getByRole("button", { name: /Accept all 2/ })).toBeInTheDocument();
  });

  it("puts the proposal above collapsed filters, and still reaches them by keyboard", () => {
    renderQueue([item("a"), item("b")]);
    const details = screen.getByText("Filters & sort").closest("details")!;
    const card = screen.getByText("Level mismatch a");

    expect(details.open).toBe(false);
    expect(card.compareDocumentPosition(details) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    fireEvent.keyDown(window, { key: "/" });
    expect(details.open).toBe(true);
    expect(screen.getByLabelText("Search corrections")).toHaveFocus();

    fireEvent.change(screen.getByLabelText("Search corrections"), { target: { value: "mismatch" } });
    expect(details.querySelector("summary")).toHaveTextContent("1 active");
  });
});
