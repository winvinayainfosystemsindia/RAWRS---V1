import { useEffect, type ReactNode } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { ReviewerWorkspace } from "@/components/ReviewerWorkspace";
import { api, type CorrectionItem } from "@/lib/api";
import { DocumentDataProvider, useDocumentDispatch } from "@/lib/store/DocumentDataContext";
import { SelectionProvider } from "@/lib/store/SelectionContext";
import { PdfViewportProvider } from "@/lib/store/PdfViewportContext";
import { ReviewQueueProvider } from "@/lib/store/ReviewQueueContext";
import { ToastProvider } from "@/components/Toast";

// Batch review follows the producer's decision basis and cause, never
// confidence: every item below is 0.99. Items default to judgement.
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
  decision_basis: "judgement",
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

const det = (id: string, over: Partial<CorrectionItem> = {}) => item(id, { decision_basis: "deterministic", ...over });

describe("ReviewerWorkspace batch review", () => {
  it("offers no batch accept when the pending view mixes causes, however confident", () => {
    renderQueue([
      det("a"),
      det("b", { field: "text_correction", rule_id: "HEADING_VERIFY_004", reason_code: "HEADING_TEXT_OCR_ERROR" }),
    ]);

    expect(screen.queryByRole("button", { name: /Accept all/i })).toBeNull();
    expect(screen.getByText(/filter by Rule/i)).toBeInTheDocument();
  });

  it("accepts one cause as a single request", async () => {
    const bulk = jest
      .spyOn(api, "bulkReviewCorrections")
      .mockResolvedValue({ corrections: [det("a", { status: "accepted" }), det("b", { status: "accepted" })] });
    renderQueue([det("a"), det("b")]);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Accept all 2 HEADING_VERIFY_003 safe fixes in view" }));
    });

    expect(bulk).toHaveBeenCalledTimes(1);
    expect(bulk).toHaveBeenCalledWith("job-1", ["a", "b"], "accept");
    expect(await screen.findByText("Accepted 2 HEADING_VERIFY_003 safe fixes")).toBeInTheDocument();
  });

  it("reports a refused batch as nothing changed, never as accepted", async () => {
    jest.spyOn(api, "bulkReviewCorrections").mockRejectedValue(new Error("failed on correction b; nothing was changed."));
    renderQueue([det("a"), det("b")]);

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

  it("offers no batch for judgement corrections of one cause, however confident", () => {
    const bulk = jest.spyOn(api, "bulkReviewCorrections");
    renderQueue([item("a"), item("b"), item("c")]);

    expect(screen.queryByRole("button", { name: /Accept all/i })).toBeNull();
    expect(screen.queryByText(/filter by Rule/i)).toBeNull();
    expect(bulk).not.toHaveBeenCalled();
  });

  it("batches only the deterministic corrections when judgement ones share the cause", async () => {
    const bulk = jest
      .spyOn(api, "bulkReviewCorrections")
      .mockResolvedValue({ corrections: [det("a", { status: "accepted" }), det("c", { status: "accepted" })] });
    renderQueue([det("a"), item("b"), det("c")]);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Accept all 2 HEADING_VERIFY_003 safe fixes in view" }));
    });

    expect(bulk).toHaveBeenCalledWith("job-1", ["a", "c"], "accept");
  });
});

describe("decision basis on the proposal card", () => {
  it("names the basis in words, apart from confidence, and passes axe", async () => {
    const { container, unmount } = renderQueue([item("a", { confidence: 0.99 })]);
    expect(screen.getByText("Review · judgement")).toBeInTheDocument();
    expect(screen.getByText(/Very High confidence/)).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
    unmount();

    const low = renderQueue([det("x", { confidence: 0.3 })]);
    expect(screen.getByText("Safe fix · deterministic")).toBeInTheDocument();
    expect(screen.getByText(/Very Low confidence/)).toBeInTheDocument();
    expect(await axe(low.container)).toHaveNoViolations();
  });
});
