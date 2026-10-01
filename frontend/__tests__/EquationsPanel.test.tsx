import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { EquationsPanel } from "@/components/EquationsPanel";
import { api, type EquationItem } from "@/lib/api";
import { DocumentDataProvider } from "@/lib/store/DocumentDataContext";
import { ToastProvider } from "@/components/Toast";

// The equations workspace (plan item 2). The panel is presentational: it
// takes the equations slice as a prop and pushes edits through
// api.editEquation, mirroring the result into the document store. The API
// module is imported for real and only the network-calling method is
// stubbed via jest.spyOn — the same approach as the a11y suite, because a
// path-alias jest.mock("@/lib/api", ...) failed to resolve reliably under
// next/jest's module mapping.

const flagged: EquationItem = {
  equation_id: "eq-1",
  page_number: 3,
  display: true,
  latex: "x^2 + \\foo{y}",
  latex_source: "mathpix",
  number: "3",
  label: null,
  status: "flagged",
  flag_reasons: ["Unknown command: \\foo"],
  description: null,
  text: "x² + foo(y)",
  before_text: "",
  after_text: "",
  source_line: 42,
  paragraph_id: "p-1",
};

const converted: EquationItem = {
  ...flagged,
  equation_id: "eq-2",
  page_number: 5,
  latex: "E = mc^2",
  number: null,
  status: "converted",
  flag_reasons: [],
  text: "E = mc²",
  source_line: 90,
  paragraph_id: "p-9",
};

function renderPanel(equations: EquationItem[]) {
  return render(
    <DocumentDataProvider>
      <ToastProvider>
        <EquationsPanel equations={equations} jobId="job-1" />
      </ToastProvider>
    </DocumentDataProvider>
  );
}

describe("EquationsPanel", () => {
  it("says so honestly when the document has no equations", () => {
    renderPanel([]);
    expect(screen.getByText(/No equations were detected/i)).toBeInTheDocument();
  });

  it("lists every equation with its status and flagged count", () => {
    renderPanel([flagged, converted]);
    expect(screen.getByText("2 equations · 1 flagged")).toBeInTheDocument();
    expect(screen.getByText(/x\^2 \+ \\foo\{y\}/)).toBeInTheDocument();
    expect(screen.getByText(/E = mc\^2/)).toBeInTheDocument();
  });

  it("filters to flagged equations only, and disables the filter when nothing is flagged", () => {
    const { unmount } = renderPanel([flagged, converted]);
    fireEvent.click(screen.getByRole("button", { name: "Flagged only" }));
    expect(screen.getByText(/x\^2 \+ \\foo\{y\}/)).toBeInTheDocument();
    expect(screen.queryByText(/E = mc\^2/)).toBeNull();
    unmount();

    renderPanel([converted]);
    expect(screen.getByRole("button", { name: "Flagged only" })).toBeDisabled();
  });

  it("opens the detail with the LaTeX, Unicode rendering and the flag reasons", () => {
    renderPanel([flagged, converted]);
    fireEvent.click(screen.getByText(/x\^2 \+ \\foo\{y\}/));

    expect(screen.getByLabelText("LaTeX")).toHaveValue("x^2 + \\foo{y}");
    expect(screen.getByText("x² + foo(y)")).toBeInTheDocument();
    expect(screen.getByText("Why it was flagged")).toBeInTheDocument();
    expect(screen.getByText("Unknown command: \\foo")).toBeInTheDocument();
  });

  it("keeps Save disabled until something changed, and refuses blank LaTeX", () => {
    renderPanel([flagged]);
    fireEvent.click(screen.getByText(/x\^2 \+ \\foo\{y\}/));

    expect(screen.getByRole("button", { name: /Save equation/i })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("LaTeX"), { target: { value: "  " } });
    expect(screen.getByRole("button", { name: /Save equation/i })).toBeDisabled();
    expect(screen.getByText(/LaTeX must not be blank/i)).toBeInTheDocument();
  });

  it("saves changed fields through the API and mirrors the re-derived equation into the store", async () => {
    const edit = jest
      .spyOn(api, "editEquation")
      .mockResolvedValue({ ...flagged, latex: "\\frac{1}{2}", status: "converted", flag_reasons: [] });
    renderPanel([flagged]);
    fireEvent.click(screen.getByText(/x\^2 \+ \\foo\{y\}/));

    fireEvent.change(screen.getByLabelText("LaTeX"), { target: { value: "\\frac{1}{2}" } });
    fireEvent.click(screen.getByRole("button", { name: /Save equation/i }));

    await waitFor(() => {
      expect(edit).toHaveBeenCalledWith("job-1", "eq-1", { latex: "\\frac{1}{2}" });
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
