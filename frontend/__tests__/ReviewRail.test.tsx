import { useEffect } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { ReviewRail } from "@/components/workspace/ReviewRail";
import { ToastProvider, useToast } from "@/components/Toast";
import { statusTabMatches, isResolved } from "@/lib/correctionFilters";
import type { CorrectionItem } from "@/lib/api";
import { DocumentDataProvider, useDocumentDispatch } from "@/lib/store/DocumentDataContext";
import { SelectionProvider, useSelection } from "@/lib/store/SelectionContext";
import { PdfViewportProvider } from "@/lib/store/PdfViewportContext";
import { ReviewQueueProvider, useReviewQueue } from "@/lib/store/ReviewQueueContext";

const queued = {
  correction_id: "q1", object_type: "heading", object_id: "h-9", field: "level_mismatch", problem: "p", current_value: "3",
  suggested_value: "2", reason: "r", confidence: 0.9, evidence: [], status: "proposed", created_at: "2026-09-16T00:00:00Z",
  reviewed_at: null, reviewer_notes: null, rule_id: "HEADING_VERIFY_003", severity: "warning", page_number: 1, reason_code: "X",
} as CorrectionItem;

function Drivers() {
  const { select, selection } = useSelection();
  const dispatch = useDocumentDispatch();
  useEffect(() => dispatch({ type: "REPLACE_CORRECTIONS", corrections: [queued] }), [dispatch]);
  const { focusQueue } = useReviewQueue();
  return (
    <>
      <button onClick={() => select("heading", 1)}>pick heading</button>
      <button onClick={() => select("correction", "c1")}>pick correction</button>
      <button onClick={() => focusQueue()}>fix next</button>
      <output>{selection ? `${selection.objectType}:${selection.objectId}` : "none"}</output>
    </>
  );
}

function renderRail() {
  return render(
    <PdfViewportProvider>
      <SelectionProvider>
        <DocumentDataProvider>
          <ReviewQueueProvider>
            <ToastProvider>
              <Drivers />
              <ReviewRail jobId="job-1" aiStatus={null} pendingCount={3} />
            </ToastProvider>
          </ReviewQueueProvider>
        </DocumentDataProvider>
      </SelectionProvider>
    </PdfViewportProvider>
  );
}

const selected = () => screen.getByRole("tab", { selected: true }).textContent;

describe("ReviewRail", () => {
  beforeEach(() => window.localStorage.clear());

  it("opens on the queue, moves to the Inspector for an object, and back for Fix Next", () => {
    renderRail();
    expect(selected()).toMatch(/^Review/);

    fireEvent.click(screen.getByText("pick correction"));
    expect(selected()).toMatch(/^Review/); // the queue's own selections keep the queue

    fireEvent.click(screen.getByText("pick heading"));
    expect(selected()).toBe("Inspector");
    // The mounted queue must not snatch the selection back to its current item.
    expect(screen.getByRole("status")).toHaveTextContent("heading:1");

    fireEvent.click(screen.getByText("fix next"));
    expect(selected()).toMatch(/^Review/);
  });
});

describe("reverted corrections", () => {
  const reverted = { status: "reverted" } as CorrectionItem;

  it("are pending, because the backend still needs a decision on them", () => {
    expect(statusTabMatches(reverted, "pending")).toBe(true);
    expect(statusTabMatches(reverted, "ignored")).toBe(false);
    expect(isResolved(reverted)).toBe(false);
  });
});

describe("Toast", () => {
  function Fire() {
    const { toast } = useToast();
    return (
      <>
        <button onClick={() => toast("Accepted 2", { label: "Undo all", onClick: () => {} })}>with undo</button>
        <button onClick={() => toast("Saved")}>plain</button>
      </>
    );
  }

  it("keeps an Undo toast until it is used, but times out plain ones", () => {
    jest.useFakeTimers();
    render(<ToastProvider><Fire /></ToastProvider>);
    fireEvent.click(screen.getByText("with undo"));
    fireEvent.click(screen.getByText("plain"));

    act(() => jest.advanceTimersByTime(60_000));

    expect(screen.getByRole("button", { name: "Undo all" })).toBeInTheDocument();
    expect(screen.queryByText("Saved")).toBeNull();
    jest.useRealTimers();
  });
});
