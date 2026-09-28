import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { ChecklistAuditPanel } from "@/components/ChecklistAuditPanel";
import { api, type ChecklistItem, type ChecklistReport } from "@/lib/api";

const item = (id: string, status: ChecklistItem["status"], requirement: string): ChecklistItem => ({
  item_id: id,
  source: id.startsWith("SUB") ? "submission_xlsx" : "remediation_docx",
  section: "General Formatting",
  requirement,
  status,
  evidence: `${requirement} evidence`,
  count: 0,
});

const report = (results: ChecklistItem[]): ChecklistReport => ({
  docx_path: "out.docx",
  passed: !results.some((r) => r.status === "fail"),
  summary: {
    pass: results.filter((r) => r.status === "pass").length,
    fail: results.filter((r) => r.status === "fail").length,
    warn: results.filter((r) => r.status === "warn").length,
    manual: results.filter((r) => r.status === "manual").length,
    not_applicable: results.filter((r) => r.status === "not_applicable").length,
  },
  results,
});

afterEach(() => jest.restoreAllMocks());

test("failures lead, settled items are folded away", async () => {
  jest.spyOn(api, "getChecklist").mockResolvedValue(
    report([
      item("DR-02", "pass", "Normal text is Times New Roman 12 pt"),
      item("SUB-KEYBOARD", "manual", "Keyboard-only navigation"),
      item("DR-ALT", "fail", "Alt text for all images"),
    ])
  );
  const { container } = render(<ChecklistAuditPanel jobId="job1" />);

  const attention = await screen.findByRole("list", { name: "Checklist items needing attention" });
  const rows = within(attention).getAllByRole("listitem");
  expect(rows.map((row) => row.textContent)).toEqual([
    expect.stringContaining("Alt text for all images"),
    expect.stringContaining("Keyboard-only navigation"),
  ]);
  expect(screen.getByText("1 failing")).toBeInTheDocument();
  expect(screen.getByText("1 settled items")).toBeInTheDocument();
  expect(await axe(container)).toHaveNoViolations();
});

test("a clean document says so, and the audit can be re-run", async () => {
  const spy = jest
    .spyOn(api, "getChecklist")
    .mockResolvedValue(report([item("DR-02", "pass", "Normal text is Times New Roman 12 pt")]));
  render(<ChecklistAuditPanel jobId="job1" />);

  expect(await screen.findByText("All automated checks pass")).toBeInTheDocument();
  expect(screen.getByText("Nothing needs attention.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Re-run audit" }));
  await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
});

test("an audit error is announced", async () => {
  jest.spyOn(api, "getChecklist").mockRejectedValue(new Error("This document has no DOCX to audit."));
  render(<ChecklistAuditPanel jobId="job1" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("This document has no DOCX to audit.");
});
