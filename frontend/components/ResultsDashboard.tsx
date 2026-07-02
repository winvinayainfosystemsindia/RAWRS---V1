"use client";

import type { FootnoteItem, ImageItem, JobSummary, PageOcrInfo, TableItem, ValidationIssue } from "@/lib/api";
import { SeverityBadge } from "@/components/Badge";
import { ChecklistPanel } from "@/components/ChecklistPanel";

// ─── VERIFICATION SUMMARY section ────────────────────────────────────────────

interface SummaryRow {
  label: string;
  value: string | number;
  source: "backend" | "todo";
}

function VerificationSummarySection({ job }: { job: JobSummary }) {
  const rows: SummaryRow[] = [
    {
      label: "Headings Verified",
      value: job.heading_count !== null ? job.heading_count : "—",
      source: job.heading_count !== null ? "backend" : "todo",
    },
    {
      label: "Footnotes Verified",
      value: job.footnote_count !== null ? job.footnote_count : "—",
      source: job.footnote_count !== null ? "backend" : "todo",
    },
    {
      label: "Figures Verified",
      value: job.image_count !== null ? job.image_count : "—",
      source: job.image_count !== null ? "backend" : "todo",
    },
    {
      label: "Captions Verified",
      value: "TODO",
      source: "todo",
    },
    {
      label: "Page Labels Verified",
      value: "TODO",
      source: "todo",
    },
    {
      label: "Mismatches Detected",
      value: "TODO",
      source: "todo",
    },
  ];

  return (
    <section aria-labelledby="verification-summary-heading">
      <div className="flex items-center gap-2 mb-3">
        <span
          className="flex h-5 w-5 items-center justify-center rounded-full border-2 border-dashed border-violet-400"
          aria-hidden="true"
        >
          <svg className="h-2.5 w-2.5 text-violet-500" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M1 5h3m5 0h-3m0 0V2m0 3v3" />
          </svg>
        </span>
        <h2 id="verification-summary-heading" className="text-sm font-bold text-gray-900 uppercase tracking-wide">
          Verification Summary
        </h2>
        <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-semibold text-violet-700">
          Mathpix ↔ PDF Comparison
        </span>
      </div>

      <div className="rounded-lg border border-violet-100 bg-white overflow-hidden">
        <div className="border-b border-violet-100 bg-violet-50 px-4 py-2">
          <p className="text-xs text-violet-700">
            <span className="font-semibold">Phase 2:</span> Direct Mathpix-to-PDF comparison is not yet implemented.
            Counts below reflect Phase 1 pipeline detection only — not cross-source verification.
          </p>
        </div>
        <dl className="divide-y divide-gray-100">
          {rows.map((row) => (
            <div key={row.label} className="flex items-center justify-between px-4 py-3">
              <dt className="text-sm text-gray-700">{row.label}</dt>
              <dd className="flex items-center gap-2">
                {row.source === "backend" ? (
                  <span className="text-sm font-semibold tabular-nums text-gray-900">{row.value}</span>
                ) : (
                  <span className="rounded bg-violet-50 px-2 py-0.5 font-mono text-xs text-violet-600 border border-violet-200">
                    TODO — Phase 2
                  </span>
                )}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

// ─── VERIFIED section ─────────────────────────────────────────────────────────

interface VerifiedMetric {
  label: string;
  value: string | number;
  available: boolean;
}

function VerifiedSection({ job, pages, tables }: { job: JobSummary; pages: PageOcrInfo[]; tables: TableItem[] }) {
  const directPages = pages.filter((p) => p.extraction_method === "direct_text_extraction").length;
  const ocrPages = pages.filter((p) => p.extraction_method && p.extraction_method !== "direct_text_extraction").length;
  const pagesWithLabel = pages.filter((p) => p.printed_label !== null).length;

  const metrics: VerifiedMetric[] = [
    {
      label: "Pages Verified",
      value: job.page_count ?? "—",
      available: job.page_count !== null,
    },
    {
      label: "Direct Text",
      value: pages.length > 0 ? directPages : "—",
      available: pages.length > 0,
    },
    {
      label: "OCR Pages",
      value: pages.length > 0 ? ocrPages : "—",
      available: pages.length > 0,
    },
    {
      label: "Headings Verified",
      value: job.heading_count ?? "—",
      available: job.heading_count !== null,
    },
    {
      label: "Figures Detected",
      value: job.image_count ?? "—",
      available: job.image_count !== null,
    },
    {
      label: "Footnotes Verified",
      value: job.footnote_count ?? "—",
      available: job.footnote_count !== null,
    },
    {
      label: "Tables Detected",
      value: tables.length,
      available: true,
    },
    {
      label: "Page Labels",
      value: pages.length > 0 ? `${pagesWithLabel} of ${pages.length}` : "—",
      available: pages.length > 0 && pagesWithLabel > 0,
    },
  ];

  return (
    <section aria-labelledby="verified-heading">
      <div className="flex items-center gap-2 mb-3">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-green-500 text-white" aria-hidden="true">
          <svg className="h-3 w-3" viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 6l3 3 5-5" />
          </svg>
        </span>
        <h2 id="verified-heading" className="text-sm font-bold text-gray-900 uppercase tracking-wide">
          Verified
        </h2>
      </div>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {metrics.map((m) => (
          <div
            key={m.label}
            className={`rounded-lg border p-3 ${
              m.available ? "border-green-200 bg-green-50" : "border-gray-100 bg-gray-50"
            }`}
          >
            <dt className={`text-xs ${m.available ? "text-green-700" : "text-gray-400"}`}>{m.label}</dt>
            <dd
              className={`mt-1 text-xl font-bold tabular-nums ${
                m.available ? "text-green-900" : "text-gray-400"
              }`}
            >
              {m.available ? m.value : <span className="text-xs font-normal italic">{m.value}</span>}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

// ─── AUTOMATIC REPAIRS section ────────────────────────────────────────────────

interface RepairItem {
  label: string;
  value: string;
  available: boolean;
}

function AutomaticRepairsSection({
  job,
  footnotes,
  images,
  pages,
}: {
  job: JobSummary;
  footnotes: FootnoteItem[];
  images: ImageItem[];
  pages: PageOcrInfo[];
}) {
  const successfulImages = images.filter((img) => !img.extraction_failed).length;
  const pagesWithLabel = pages.filter((p) => p.printed_label !== null).length;

  const repairs: RepairItem[] = [
    {
      label: "Native Word Footnotes Created",
      value:
        job.footnote_count === null
          ? "Not Available"
          : job.footnote_count === 0
          ? "None detected"
          : `${job.footnote_count} footnote${job.footnote_count === 1 ? "" : "s"}`,
      available: job.footnote_count !== null && job.footnote_count > 0,
    },
    {
      label: "Heading Structure Applied",
      value:
        job.heading_count === null
          ? "Not Available"
          : job.heading_count === 0
          ? "No headings detected"
          : `${job.heading_count} heading${job.heading_count === 1 ? "" : "s"}`,
      available: job.heading_count !== null && job.heading_count > 0,
    },
    {
      label: "Figures Embedded",
      value:
        images.length === 0
          ? "None detected"
          : `${successfulImages} of ${images.length} figure${images.length === 1 ? "" : "s"}`,
      available: successfulImages > 0,
    },
    {
      label: "Accessibility Metadata Added",
      value: job.docx_available ? "Yes — font, style, and document properties" : "Not Available",
      available: job.docx_available,
    },
    {
      label: "Front Matter Normalized",
      value: job.has_front_matter ? "Yes — title and authors extracted" : "Not detected",
      available: job.has_front_matter,
    },
    {
      label: "Wrapped Headings Merged",
      value: "Not Available",
      available: false,
    },
    {
      label: "Running Headers Removed",
      value: "Not Available",
      available: false,
    },
    {
      label: "Printed Page Labels Preserved",
      value: pagesWithLabel > 0
        ? `${pagesWithLabel} page${pagesWithLabel === 1 ? "" : "s"} with labels preserved`
        : "None detected",
      available: pagesWithLabel > 0,
    },
  ];

  const activeRepairs = repairs.filter((r) => r.available);
  const unavailableRepairs = repairs.filter((r) => !r.available);

  return (
    <section aria-labelledby="repairs-heading">
      <div className="flex items-center gap-2 mb-3">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-white" aria-hidden="true">
          <svg className="h-3 w-3" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true">
            <path d="M9 2L3 8l2 2 6-6-2-2zm-5 7l-1.5 1.5L1 9l1-1 2 1z" />
          </svg>
        </span>
        <h2 id="repairs-heading" className="text-sm font-bold text-gray-900 uppercase tracking-wide">
          Automatic Repairs
        </h2>
      </div>

      {activeRepairs.length === 0 && unavailableRepairs.length === repairs.length ? (
        <p className="text-sm text-gray-500">No automatic repairs were applied to this document.</p>
      ) : (
        <div className="rounded-lg border border-gray-200 bg-white divide-y divide-gray-100">
          {activeRepairs.map((r) => (
            <div key={r.label} className="flex items-center justify-between gap-4 px-4 py-3">
              <div className="flex items-center gap-2.5">
                <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-blue-100" aria-hidden="true">
                  <svg className="h-2.5 w-2.5 text-blue-600" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1.5 5l2.5 2.5 4.5-4.5" />
                  </svg>
                </span>
                <span className="text-sm text-gray-900">{r.label}</span>
              </div>
              <span className="text-xs text-blue-700 font-medium shrink-0">{r.value}</span>
            </div>
          ))}
          {unavailableRepairs.map((r) => (
            <div key={r.label} className="flex items-center justify-between gap-4 px-4 py-2.5">
              <span className="text-sm text-gray-400">{r.label}</span>
              <span className="text-xs text-gray-400 italic shrink-0">Not Available</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

// ─── MANUAL REVIEW section ────────────────────────────────────────────────────

function ManualReviewSection({
  issues,
  images,
}: {
  issues: ValidationIssue[];
  images: ImageItem[];
}) {
  const reviewIssues = issues.filter((i) => i.severity === "error" || i.severity === "warning");
  const missingAltText = images.filter(
    (img) => !img.extraction_failed && img.figure && img.figure.alt_text === null
  );

  const hasItems = reviewIssues.length > 0 || missingAltText.length > 0;

  return (
    <section aria-labelledby="review-heading">
      <div className="flex items-center gap-2 mb-3">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-amber-500 text-white" aria-hidden="true">
          <svg className="h-3 w-3" viewBox="0 0 12 12" fill="currentColor">
            <path d="M6 1L1 11h10L6 1zm0 3v3m0 2v1" stroke="white" strokeWidth="1" fill="none" strokeLinecap="round" />
          </svg>
        </span>
        <h2 id="review-heading" className="text-sm font-bold text-gray-900 uppercase tracking-wide">
          Manual Review Required
          {hasItems && (
            <span className="ml-2 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-amber-100 px-1.5 text-[11px] font-semibold text-amber-800">
              {reviewIssues.length + missingAltText.length}
            </span>
          )}
        </h2>
      </div>

      {!hasItems ? (
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3">
          <p className="text-sm text-green-800 font-medium">No manual review items identified.</p>
        </div>
      ) : (
        <ul className="space-y-2" aria-label="Manual review items">
          {missingAltText.map((img) => (
            <li
              key={img.image_id}
              className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3"
            >
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium bg-amber-100 text-amber-800 ring-1 ring-inset ring-amber-300">
                  WARNING
                </span>
                <span className="text-xs text-gray-500 font-mono">IMAGE_ALT</span>
                {img.page_number && (
                  <span className="text-xs text-gray-500">Page {img.page_number}</span>
                )}
              </div>
              <p className="text-sm text-gray-900">Missing alt text for figure on page {img.page_number}.</p>
              <p className="mt-1 text-xs text-gray-600">
                <span className="font-medium">Suggested action: </span>
                Add descriptive alt text via a future Review Workspace or manual DOCX edit.
              </p>
            </li>
          ))}

          {reviewIssues.map((issue, idx) => (
            <li
              key={`${issue.rule_id}-${idx}`}
              className={`rounded-lg border px-4 py-3 ${
                issue.severity === "error"
                  ? "border-red-200 bg-red-50"
                  : "border-amber-200 bg-amber-50"
              }`}
            >
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <SeverityBadge severity={issue.severity} />
                <span className="text-xs text-gray-500 font-mono">{issue.rule_id}</span>
                {issue.page_number !== null && (
                  <span className="text-xs text-gray-500">Page {issue.page_number}</span>
                )}
              </div>
              <p className="text-sm text-gray-900">{issue.message}</p>
              {issue.suggested_action && (
                <p className="mt-1 text-xs text-gray-600">
                  <span className="font-medium">Suggested action: </span>
                  {issue.suggested_action}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ─── Composed Dashboard ───────────────────────────────────────────────────────

export interface ResultsDashboardProps {
  job: JobSummary;
  issues: ValidationIssue[];
  images: ImageItem[];
  footnotes: FootnoteItem[];
  pages: PageOcrInfo[];
  tables: TableItem[];
}

export function ResultsDashboard({ job, issues, images, footnotes, pages, tables }: ResultsDashboardProps) {
  return (
    <div className="space-y-8">
      <VerificationSummarySection job={job} />
      <VerifiedSection job={job} pages={pages} tables={tables} />
      <AutomaticRepairsSection job={job} footnotes={footnotes} images={images} pages={pages} />
      <ManualReviewSection issues={issues} images={images} />
      <ChecklistPanel job={job} issues={issues} images={images} footnotes={footnotes} pages={pages} tables={tables} />
    </div>
  );
}
