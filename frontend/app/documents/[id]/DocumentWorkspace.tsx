"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  api,
  ApiError,
  type CorrectionItem,
  type FootnoteItem,
  type HeadingItem,
  type ImageItem,
  type JobSummary,
  type MetadataItem,
  type PageOcrInfo,
  type PageReadingOrder,
  type ReadinessReport,
  type TableItem,
  type ValidationIssue,
} from "@/lib/api";
import { JobStatusBadge } from "@/components/Badge";
import { PipelineView } from "@/components/PipelineView";
import { ResultsDashboard } from "@/components/ResultsDashboard";
import { OutputWorkspace } from "@/components/OutputWorkspace";
import { Tabs } from "@/components/Tabs";
import { ValidationIssueTable } from "@/components/ValidationIssueTable";
import { ImageGrid } from "@/components/ImageGrid";
import { TableGrid } from "@/components/TableGrid";
import { FootnoteTable } from "@/components/FootnoteTable";
import { HeadingGrid } from "@/components/HeadingGrid";
import { MetadataPanel } from "@/components/MetadataPanel";
import { OcrPageTable } from "@/components/OcrPageTable";
import { ReadingOrderPanel } from "@/components/ReadingOrderPanel";
import { CorrectionsPanel } from "@/components/CorrectionsPanel";
import { ReadinessPanel } from "@/components/ReadinessPanel";

const POLL_INTERVAL_MS = 3000;

interface ResultData {
  issues: ValidationIssue[];
  images: ImageItem[];
  tables: TableItem[];
  footnotes: FootnoteItem[];
  headings: HeadingItem[];
  metadata: MetadataItem | null;
  pages: PageOcrInfo[];
  readingOrder: PageReadingOrder[];
  markdown: string;
  corrections: CorrectionItem[];
  readiness: ReadinessReport | null;
}

export function DocumentWorkspace({ jobId }: { jobId: string }) {
  const [job, setJob] = useState<JobSummary | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [results, setResults] = useState<ResultData | null>(null);
  const elapsedStart = useRef<number>(0);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => { elapsedStart.current = Date.now(); }, []);

  // Elapsed timer — ticks only while queued or processing.
  useEffect(() => {
    if (!job || (job.status !== "queued" && job.status !== "processing")) return;
    const tick = setInterval(() => {
      setElapsed(Math.round((Date.now() - elapsedStart.current) / 1000));
    }, 1000);
    return () => clearInterval(tick);
  }, [job?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  // Polling loop.
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const summary = await api.getDocument(jobId);
        if (cancelled) return;
        setJob(summary);

        if (summary.status === "complete" || summary.status === "failed") {
          await loadResults(summary);
          return;
        }
        timer = setTimeout(poll, POLL_INTERVAL_MS);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      }
    }

    async function loadResults(summary: JobSummary) {
      const [validation, images, tables, footnotes, headings, metadata, pages, readingOrder, corrections, readiness] = await Promise.all([
        api.getValidation(jobId).catch(() => ({ issues: [], error_count: 0, warning_count: 0, info_count: 0 })),
        api.getImages(jobId).catch(() => ({ images: [] })),
        api.getTables(jobId).catch(() => ({ tables: [] })),
        api.getFootnotes(jobId).catch(() => ({ footnotes: [] })),
        api.getHeadings(jobId).catch(() => ({ headings: [] })),
        api.getMetadata(jobId).catch(() => null),
        api.getPages(jobId).catch(() => ({ pages: [] })),
        api.getReadingOrder(jobId).catch(() => ({ pages: [] })),
        api.getCorrections(jobId).catch(() => ({ corrections: [] })),
        api.getReadiness(jobId).catch(() => null),
      ]);
      const markdown = summary.markdown_available
        ? await api.getMarkdown(jobId).then((r) => r.content).catch(() => "")
        : "";
      if (cancelled) return;
      setResults({
        issues: validation.issues,
        images: images.images,
        tables: tables.tables,
        footnotes: footnotes.footnotes,
        headings: headings.headings,
        metadata,
        pages: pages.pages,
        readingOrder: readingOrder.pages,
        markdown,
        corrections: corrections.corrections,
        readiness,
      });
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [jobId]);

  if (notFound) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-red-700" role="alert">
          No document found for this ID. It may have been processed before the API was last restarted.
        </p>
        <Link href="/" className="text-sm font-medium text-blue-700 hover:underline">
          &larr; Upload a document
        </Link>
      </div>
    );
  }

  if (!job) {
    return <p role="status" className="text-sm text-gray-600">Loading document…</p>;
  }

  const isActive = job.status === "queued" || job.status === "processing";
  const isDone = job.status === "complete" || job.status === "failed";

  return (
    <div className="space-y-8">
      {/* Header row */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="break-all text-lg font-bold text-gray-900">{job.filename}</h1>
          <p className="mt-1.5 flex flex-wrap items-center gap-3 text-sm text-gray-500">
            <JobStatusBadge status={job.status} />
            {job.duration_seconds !== null && (
              <span>Completed in {job.duration_seconds.toFixed(1)}s</span>
            )}
            {isActive && (
              <span aria-live="polite">Elapsed: {elapsed}s</span>
            )}
          </p>
        </div>
        <Link href="/" className="shrink-0 text-sm font-medium text-blue-700 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded">
          &larr; New document
        </Link>
      </div>

      {/* Layout: pipeline left, content right — stack on mobile */}
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        {/* Pipeline column — always visible */}
        <div className="w-full lg:w-64 shrink-0">
          <PipelineView status={job.status} elapsed={elapsed} />
        </div>

        {/* Main content column */}
        <div className="flex-1 min-w-0 space-y-8">
          {/* Error banner */}
          {job.status === "failed" && (
            <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4">
              <p className="text-sm font-semibold text-red-900">
                Processing failed{job.failed_stage ? ` at stage "${job.failed_stage}"` : ""}.
              </p>
              {job.error_message && (
                <p className="mt-1 text-sm text-red-700">{job.error_message}</p>
              )}
            </div>
          )}

          {/* Processing status */}
          {isActive && (
            <div role="status" className="rounded-lg border border-blue-200 bg-blue-50 p-4">
              <p className="text-sm font-medium text-blue-900">
                {job.status === "queued"
                  ? "Queued — waiting to start…"
                  : "Verification pipeline is running. This page updates automatically."}
              </p>
              <p className="mt-1 text-xs text-blue-700">
                Scanned PDFs that require OCR may take several minutes per page.
              </p>
            </div>
          )}

          {/* Results Dashboard */}
          {results && isDone && (
            <ResultsDashboard
              job={job}
              issues={results.issues}
              images={results.images}
              footnotes={results.footnotes}
              pages={results.pages}
              tables={results.tables}
            />
          )}

          {/* Output Workspace — editor, DOCX preview, downloads */}
          {results && isDone && (
            <OutputWorkspace job={job} generatedMarkdown={results.markdown} />
          )}

          {/* Detail Tabs */}
          {results && (
            <section aria-labelledby="detail-tabs-heading">
              <h2 id="detail-tabs-heading" className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
                Detail View
              </h2>
              <Tabs
                tabs={[
                  {
                    id: "validation",
                    label: "Validation",
                    badge: results.issues.length > 0 ? <CountBadge n={results.issues.length} /> : undefined,
                    content: <ValidationIssueTable issues={results.issues} />,
                  },
                  {
                    id: "headings",
                    label: "Headings",
                    badge: results.headings.length > 0 ? <CountBadge n={results.headings.length} /> : undefined,
                    content: (
                      <HeadingGrid
                        headings={results.headings}
                        jobId={jobId}
                        onHeadingsUpdated={(updated) =>
                          setResults((prev) => prev ? { ...prev, headings: updated } : prev)
                        }
                      />
                    ),
                  },
                  {
                    id: "images",
                    label: "Figures",
                    badge: results.images.length > 0 ? <CountBadge n={results.images.length} /> : undefined,
                    content: (
                      <ImageGrid
                        images={results.images}
                        jobId={jobId}
                        onImagesUpdated={(updated) =>
                          setResults((prev) => prev ? { ...prev, images: updated } : prev)
                        }
                      />
                    ),
                  },
                  {
                    id: "tables",
                    label: "Tables",
                    badge: results.tables.length > 0 ? <CountBadge n={results.tables.length} /> : undefined,
                    content: (
                      <TableGrid
                        tables={results.tables}
                        jobId={jobId}
                        onTablesUpdated={(updated) =>
                          setResults((prev) => prev ? { ...prev, tables: updated } : prev)
                        }
                      />
                    ),
                  },
                  {
                    id: "footnotes",
                    label: "Footnotes",
                    badge: results.footnotes.length > 0 ? <CountBadge n={results.footnotes.length} /> : undefined,
                    content: (
                      <FootnoteTable
                        footnotes={results.footnotes}
                        jobId={jobId}
                        onFootnotesUpdated={(updated) =>
                          setResults((prev) => prev ? { ...prev, footnotes: updated } : prev)
                        }
                      />
                    ),
                  },
                  {
                    id: "metadata",
                    label: "Metadata",
                    content: results.metadata ? (
                      <MetadataPanel
                        metadata={results.metadata}
                        jobId={jobId}
                        onUpdated={(updated) =>
                          setResults((prev) => prev ? { ...prev, metadata: updated } : prev)
                        }
                      />
                    ) : (
                      <p className="text-sm text-gray-500">Metadata not available.</p>
                    ),
                  },
                  {
                    id: "ocr",
                    label: "OCR Pages",
                    content: <OcrPageTable pages={results.pages} />,
                  },
                  {
                    id: "reading-order",
                    label: "Reading Order",
                    badge: results.readingOrder.filter((p) => p.reading_order_status === "unreviewed").length > 0
                      ? <CountBadge n={results.readingOrder.filter((p) => p.reading_order_status === "unreviewed").length} />
                      : undefined,
                    content: (
                      <ReadingOrderPanel
                        pages={results.readingOrder}
                        jobId={jobId}
                        onPagesUpdated={(updated) =>
                          setResults((prev) => prev ? { ...prev, readingOrder: updated } : prev)
                        }
                      />
                    ),
                  },
                  {
                    id: "corrections",
                    label: "Corrections",
                    badge: results.corrections.filter((c) => ["proposed", "pending_review"].includes(c.status)).length > 0
                      ? <CountBadge n={results.corrections.filter((c) => ["proposed", "pending_review"].includes(c.status)).length} />
                      : undefined,
                    content: (
                      <CorrectionsPanel
                        corrections={results.corrections}
                        jobId={jobId}
                        onCorrectionsUpdated={(updated) =>
                          setResults((prev) => prev ? { ...prev, corrections: updated } : prev)
                        }
                      />
                    ),
                  },
                  {
                    id: "readiness",
                    label: "Accessibility Readiness",
                    content: <ReadinessPanel readiness={results.readiness} />,
                  },
                ]}
              />
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

function CountBadge({ n }: { n: number }) {
  return (
    <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-gray-200 px-1 text-[11px] font-semibold text-gray-700">
      {n}
    </span>
  );
}
