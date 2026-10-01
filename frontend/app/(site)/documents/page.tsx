"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, type JobSummary } from "@/lib/api";
import { JobStatusBadge } from "@/components/Badge";

// Documents dashboard (frontend plan item 6): every processed document with
// its counts and a link into its workspace. Replaces the polling
// recent-documents list that used to live under the upload form — that page
// is about starting work, this one is about finding it again. Same polling
// pattern as the old list (and DocumentWorkspace): poll every 3s while any
// job is queued/processing so counts fill in live, then stop.

type StatusFilter = "all" | "queued" | "processing" | "complete" | "failed";
type SortKey = "newest" | "oldest" | "name";

const STATUS_FILTERS: { id: StatusFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "queued", label: "Queued" },
  { id: "processing", label: "Processing" },
  { id: "complete", label: "Complete" },
  { id: "failed", label: "Failed" },
];

const SORTS: { id: SortKey; label: string }[] = [
  { id: "newest", label: "Newest first" },
  { id: "oldest", label: "Oldest first" },
  { id: "name", label: "Name (A–Z)" },
];

const POLL_INTERVAL_MS = 3000;

// Live extracted-object counts for a job still processing — these fields
// update as the poll re-fetches the list, before the job reaches a terminal
// status (moved from the upload page's RecentDocuments).
function ExtractedCounts({ job }: { job: JobSummary }) {
  const parts: string[] = [];
  if (job.heading_count !== null) parts.push(`${job.heading_count} headings`);
  if (job.image_count !== null) parts.push(`${job.image_count} images`);
  if (job.footnote_count !== null) parts.push(`${job.footnote_count} notes`);
  if (parts.length === 0) return null;
  return <span className="text-text-secondary/70">{parts.join(" · ")}</span>;
}

function DocumentRow({ job }: { job: JobSummary }) {
  return (
    <li>
      <Link
        href={`/documents/${job.job_id}`}
        className="flex items-center justify-between gap-4 p-4 hover:bg-hover-row focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent"
        title={`${job.filename} — uploaded ${new Date(job.created_at).toLocaleString()}`}
      >
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-text-primary">{job.filename}</p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-text-secondary">
            {job.page_count !== null && <span>{job.page_count} pages</span>}
            {job.image_count !== null && <span>{job.image_count} images</span>}
            {job.heading_count !== null && <span>{job.heading_count} headings</span>}
            {(job.status === "queued" || job.status === "processing") && <ExtractedCounts job={job} />}
            {job.error_count !== null && job.error_count > 0 && (
              <span className="text-danger">{job.error_count} error{job.error_count === 1 ? "" : "s"}</span>
            )}
            {job.duration_seconds !== null && <span>{job.duration_seconds.toFixed(1)}s</span>}
          </p>
        </div>
        <span className="flex shrink-0 items-center gap-3">
          <time dateTime={job.created_at} className="hidden text-xs text-text-secondary sm:block">
            {new Date(job.created_at).toLocaleDateString()}
          </time>
          <JobStatusBadge status={job.status} />
        </span>
      </Link>
    </li>
  );
}

export default function DocumentsDashboard() {
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("newest");

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const list = await api.listDocuments();
        if (cancelled) return;
        setJobs(list);
        setLoadError(null);
        if (list.some((j) => j.status === "queued" || j.status === "processing")) {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch {
        if (!cancelled) {
          // First load failed: say so. A later failure after a successful
          // load keeps showing the last good list — a transient blip should
          // not blank the dashboard.
          setJobs((prev) => {
            if (prev === null) setLoadError("Could not reach the RAWRS API. Confirm the backend is running.");
            return prev;
          });
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      }
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  const visible = useMemo(() => {
    const list = jobs ?? [];
    const q = query.trim().toLowerCase();
    const filtered = list.filter((job) => {
      if (statusFilter !== "all" && job.status !== statusFilter) return false;
      if (q && !job.filename.toLowerCase().includes(q)) return false;
      return true;
    });
    return filtered.sort((a, b) => {
      if (sort === "name") return a.filename.localeCompare(b.filename);
      const aTime = new Date(a.created_at).getTime();
      const bTime = new Date(b.created_at).getTime();
      return sort === "newest" ? bTime - aTime : aTime - bTime;
    });
  }, [jobs, statusFilter, query, sort]);

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-end justify-between gap-3 pt-2">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-text-primary">Documents</h1>
          <p className="mt-1.5 text-sm text-text-secondary">
            Every processed document. Open one to review and export it.
          </p>
        </div>
        <Link
          href="/"
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-contrast hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          + New document
        </Link>
      </section>

      {/* Filters */}
      <section aria-labelledby="documents-filter-heading" className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-surface-panel px-4 py-3">
        <h2 id="documents-filter-heading" className="sr-only">
          Filter and sort documents
        </h2>
        <div className="flex items-center gap-0.5 rounded-md border border-border bg-surface-canvas p-0.5" role="group" aria-label="Filter by status">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => setStatusFilter(f.id)}
              aria-pressed={statusFilter === f.id}
              className={`rounded px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                statusFilter === f.id
                  ? "bg-accent text-accent-contrast"
                  : "text-text-secondary hover:bg-hover-row hover:text-text-primary"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by filename…"
          aria-label="Search documents by filename"
          className="min-w-0 flex-1 rounded border border-border bg-surface-canvas px-3 py-1.5 text-sm text-text-primary placeholder:text-text-secondary/60 focus:border-accent focus:outline-none sm:max-w-xs"
        />
        <label className="flex items-center gap-2 text-xs text-text-secondary">
          Sort
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            className="rounded border border-border bg-surface-canvas px-2 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
          >
            {SORTS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
      </section>

      {loadError && (
        <p role="alert" className="rounded border border-danger/30 bg-danger/5 p-3 text-sm text-danger">
          {loadError}
        </p>
      )}

      {/* List */}
      <section aria-labelledby="documents-list-heading">
        <h2 id="documents-list-heading" className="sr-only">
          Document list
        </h2>
        {jobs === null && !loadError && (
          <p role="status" className="text-sm text-text-secondary">
            Loading…
          </p>
        )}
        {jobs !== null && visible.length === 0 && (
          <p className="text-sm text-text-secondary">
            {jobs.length === 0
              ? "No documents have been processed yet. Upload a PDF to get started."
              : "No documents match the current filters."}
          </p>
        )}
        {visible.length > 0 && (
          <ul className="divide-y divide-border rounded-lg border border-border bg-surface-panel">
            {visible.map((job) => (
              <DocumentRow key={job.job_id} job={job} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
