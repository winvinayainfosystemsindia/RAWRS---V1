import { render, screen, within, fireEvent } from "@testing-library/react";
import { ValidationIssueTable } from "@/components/ValidationIssueTable";
import type { ValidationIssue } from "@/lib/api";

// Queue Signal Improvement (Option A) — the actionable queue must not be
// diluted by cross-source _VERIFY_ duplicates. Actionable issues (those with
// a suggested_action) render in the main queue; verification findings render
// collapsed under "Verification Findings". Nothing is dropped.

const issue = (over: Partial<ValidationIssue> & Pick<ValidationIssue, "rule_id" | "severity">): ValidationIssue => ({
  issue_id: over.rule_id + "-id",
  message: `${over.rule_id} message`,
  page_number: 1,
  suggested_action: null,
  status: "open",
  reviewed_at: null,
  ...over,
});

const ACTIONABLE = [
  issue({ rule_id: "TABLE_001", severity: "warning", suggested_action: "Add a caption in the Tables workspace." }),
  issue({ rule_id: "META_001", severity: "info", suggested_action: "Set the document language in the Metadata panel." }),
];
const VERIFICATION = [
  issue({ rule_id: "HEADING_VERIFY_001", severity: "info" }),
  issue({ rule_id: "IMAGE_VERIFY_002", severity: "warning" }),
];

function verificationDetails(): HTMLElement {
  // selector: "summary" disambiguates from the "N verification findings
  // below" banner, which also contains the phrase.
  const summary = screen.getByText(/Verification Findings/i, { selector: "summary" });
  const details = summary.closest("details");
  if (!details) throw new Error("Verification Findings <details> not found");
  return details as HTMLElement;
}

describe("ValidationIssueTable — actionable vs verification partition", () => {
  it("separates actionable issues from cross-source verification findings", () => {
    render(<ValidationIssueTable issues={[...ACTIONABLE, ...VERIFICATION]} />);

    // The two _VERIFY_ findings live inside the collapsed section...
    const details = verificationDetails();
    expect(within(details).getAllByRole("listitem")).toHaveLength(2);
    expect(within(details).getByText("HEADING_VERIFY_001")).toBeInTheDocument();
    expect(within(details).getByText("IMAGE_VERIFY_002")).toBeInTheDocument();

    // ...and the actionable ones do NOT.
    expect(within(details).queryByText("TABLE_001")).toBeNull();
    expect(within(details).queryByText("META_001")).toBeNull();

    // Actionable issues are still present in the queue (just not buried).
    expect(screen.getByText("TABLE_001")).toBeInTheDocument();
    expect(screen.getByText("META_001")).toBeInTheDocument();
  });

  it("shows a 'no action required' cue when only verification findings exist", () => {
    render(<ValidationIssueTable issues={VERIFICATION} />);

    expect(screen.getByText(/No action required/i)).toBeInTheDocument();
    expect(within(verificationDetails()).getAllByRole("listitem")).toHaveLength(2);
  });

  it("does not render a verification section when every issue is actionable", () => {
    render(<ValidationIssueTable issues={ACTIONABLE} />);

    expect(screen.queryByText(/Verification Findings/i)).toBeNull();
    expect(screen.queryByText(/No action required/i)).toBeNull();
    expect(screen.getByText("TABLE_001")).toBeInTheDocument();
  });

  it("keeps severity filtering working across the partition", () => {
    render(<ValidationIssueTable issues={[...ACTIONABLE, ...VERIFICATION]} />);

    fireEvent.click(screen.getByRole("tab", { name: /Info/i }));

    // Info-only view: the info actionable + info verification remain; the
    // warning issues (actionable TABLE_001 and verification IMAGE_VERIFY_002)
    // are filtered out of both partitions.
    expect(screen.getByText("META_001")).toBeInTheDocument();
    expect(within(verificationDetails()).getByText("HEADING_VERIFY_001")).toBeInTheDocument();
    expect(screen.queryByText("TABLE_001")).toBeNull();
    expect(screen.queryByText("IMAGE_VERIFY_002")).toBeNull();
  });
});
