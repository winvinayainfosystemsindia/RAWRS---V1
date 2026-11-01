import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { AutomationPanel } from "@/components/AutomationPanel";
import { api, type DocumentMetrics } from "@/lib/api";

const buckets = { auto_decided: 8, pending_human: 2, accepted_unchanged: 0, edited: 0, rejected: 0 };

const metrics: DocumentMetrics = {
  job_id: "job1",
  total_seconds: 41.2,
  stage_seconds: { parse_pdf: 1.2 },
  checks: { pass: 23, fail: 2, warn: 1, manual: 4, not_applicable: 10 },
  snapshot: { headings: buckets },
  live: { headings: buckets },
  review_seconds_strict: 120,
  review_seconds_loose: 300,
  estimate: null,
  rates: {
    decided_without_human: { status: "measured", documents: 1, items: 10, pooled_pct: 80 },
    reviewer_kept_unchanged: { status: "not measured yet", documents: 0, items: 0 },
    human_decisions: 0,
  },
  definitions: {},
};

describe("AutomationPanel", () => {
  afterEach(() => jest.restoreAllMocks());

  it("shows measured (a), unmeasured (b), conservative check counts and both review times", async () => {
    jest.spyOn(api, "getDocumentMetrics").mockResolvedValue(metrics);
    const { container } = render(<AutomationPanel jobId="job1" />);
    expect(await screen.findByText("80% of 10 items")).toBeInTheDocument();
    expect(screen.getByText(/Not measured yet \(0 items\)/)).toBeInTheDocument();
    expect(screen.getByText("23 pass, 2 fail, 5 need a human")).toBeInTheDocument();
    expect(screen.getByText("5 min (strict: 2 min)")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("explains when a document predates metrics", async () => {
    jest.spyOn(api, "getDocumentMetrics").mockResolvedValue(null);
    render(<AutomationPanel jobId="old" />);
    expect(await screen.findByText(/processed before RAWRS recorded them/)).toBeInTheDocument();
  });
});
