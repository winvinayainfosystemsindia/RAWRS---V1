import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { FinalDocxPanel } from "@/components/FinalDocxPanel";
import InsightsPage from "@/app/(site)/insights/page";
import { api, type FinalDocxReview, type LearningInsights } from "@/lib/api";

const review: FinalDocxReview = {
  job_id: "job1",
  filename: "book.pdf",
  final_filename: "book-final.docx",
  reviewed_at: "2026-10-21T00:00:00+00:00",
  baseline: "downloaded_copy",
  diff: {
    summary: {
      units_exported: 10,
      units_final: 10,
      units_kept: 9,
      kept_share: 0.9,
      edits: 2,
      by_category: { HEADING_LEVEL_CHANGED: 1, ALT_TEXT_WRITTEN: 1 },
    },
    edits: [
      { category: "HEADING_LEVEL_CHANGED", object_type: "heading", before: "H2", after: "H3", position_before: 1, position_after: 1 },
      { category: "ALT_TEXT_WRITTEN", object_type: "figure", before: "", after: "A bar chart.", position_before: 4, position_after: 4 },
    ],
  },
  checklist: {
    exported: { passed: false, summary: { pass: 9, fail: 1, warn: 0, manual: 0, not_applicable: 0 } },
    final: { passed: true, summary: { pass: 10, fail: 0, warn: 0, manual: 0, not_applicable: 0 } },
    fixed_by_remediator: [{ item_id: "DR-ALT", requirement: "Alt text for all images", before: "fail", after: "pass", evidence: "" }],
    regressed_by_remediator: [],
  },
};

afterEach(() => jest.restoreAllMocks());

test("with nothing uploaded, offers the upload", async () => {
  jest.spyOn(api, "getFinalDocxReview").mockResolvedValue(null);
  const { container } = render(<FinalDocxPanel jobId="job1" />);
  expect(await screen.findByText("Upload finished DOCX")).toBeInTheDocument();
  expect(screen.queryByText(/kept unchanged/)).not.toBeInTheDocument();
  expect(await axe(container)).toHaveNoViolations();
});

test("uploading shows what the remediator changed and which checklist items they fixed", async () => {
  jest.spyOn(api, "getFinalDocxReview").mockResolvedValue(null);
  const upload = jest.spyOn(api, "uploadFinalDocx").mockResolvedValue(review);
  const { container } = render(<FinalDocxPanel jobId="job1" />);
  await screen.findByText("Upload finished DOCX");

  const file = new File(["x"], "book-final.docx");
  fireEvent.change(screen.getByLabelText("Upload finished DOCX"), { target: { files: [file] } });

  expect(await screen.findByText("90%")).toBeInTheDocument();
  expect(upload).toHaveBeenCalledWith("job1", file);
  const kinds = screen.getByRole("list", { name: "Edits by kind" });
  expect(within(kinds).getByText(/Heading level changed/)).toBeInTheDocument();
  const fixed = screen.getByRole("list", { name: "Checklist items the remediator fixed" });
  expect(within(fixed).getByText(/Alt text for all images/)).toBeInTheDocument();
  expect(screen.getByText("Every edit (2)")).toBeInTheDocument();
  expect(await axe(container)).toHaveNoViolations();
});

test("an upload the backend refuses is reported, and a stored comparison can be forgotten", async () => {
  jest.spyOn(api, "getFinalDocxReview").mockResolvedValue(review);
  jest.spyOn(api, "uploadFinalDocx").mockRejectedValue(new Error("Only .docx files are accepted."));
  const remove = jest.spyOn(api, "deleteFinalDocxReview").mockResolvedValue();
  render(<FinalDocxPanel jobId="job1" />);
  await screen.findByText("90%");

  fireEvent.change(screen.getByLabelText("Upload a newer version"), { target: { files: [new File(["x"], "x.pdf")] } });
  expect(await screen.findByRole("alert")).toHaveTextContent("Only .docx files are accepted.");

  fireEvent.click(screen.getByRole("button", { name: "Forget this comparison" }));
  await waitFor(() => expect(screen.queryByText("90%")).not.toBeInTheDocument());
  expect(remove).toHaveBeenCalledWith("job1");
});

const insights: LearningInsights = {
  generated_at: "2026-10-21T00:00:00+00:00",
  decisions: {
    rules: [
      {
        object_type: "heading",
        reason_code: "HEADING_LEVEL_MISMATCH",
        counts: { accepted: 40, rejected: 0, edited: 0, auto_undone: 0 },
        documents: 3,
        decided: 40,
        precision: 1,
        precision_low: 0.91,
        precision_high: 1,
        edit_share: 0,
        auto_applied: 0,
        auto_undo_rate: null,
        median_decision_seconds: 4,
        recommendation: "approaching_auto_apply",
        rationale: "Accepted 40 of 40 times.",
      },
    ],
    human_edits: [
      { object_type: "heading", reason_code: "HEADING_LEVEL_MANUAL_EDIT", count: 4, documents: 2, top_changes: [{ from: "2", to: "3", count: 3 }] },
    ],
    totals: { documents: 3, proposals: 40, human_edits: 4 },
  },
  after_export: {
    documents: 1,
    mean_kept_share: 0.9,
    categories: [{ category: "HEADING_LEVEL_CHANGED", object_type: "heading", count: 2, documents: 1, phrase: "changed a heading's level" }],
    word_substitutions: [{ from: "teh", to: "the", count: 1, documents: 1 }],
    checklist_fixed_by_remediators: [],
    checklist_regressed_by_remediators: [],
  },
  priorities: [{ source: "after_export", weight: 2, message: "After export, remediators changed a heading's level 2 times." }],
  reviewed_documents: [{ job_id: "job1", filename: "book.pdf", reviewed_at: null, kept_share: 0.9, edits: 2 }],
};

test("the insights page lays out priorities, rule verdicts and reviewer edits", async () => {
  jest.spyOn(api, "getLearningInsights").mockResolvedValue(insights);
  const { container } = render(<InsightsPage />);

  expect(await screen.findByText("After export, remediators changed a heading's level 2 times.")).toBeInTheDocument();
  expect(screen.getByText("Approaching auto-apply")).toBeInTheDocument();
  expect(screen.getByText(/2 → 3 \(3\)/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "book.pdf" })).toHaveAttribute("href", "/documents/job1");
  expect(screen.getByRole("link", { name: /learning dataset/ })).toHaveAttribute("href", api.learningDatasetUrl());
  expect(await axe(container)).toHaveNoViolations();
});

test("the insights page reports a backend failure", async () => {
  jest.spyOn(api, "getLearningInsights").mockRejectedValue(new Error("Backend unavailable"));
  render(<InsightsPage />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Backend unavailable");
});
