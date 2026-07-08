"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, type JobSummary } from "@/lib/api";
import { JobStatusBadge } from "@/components/Badge";

// ─── Utilities ────────────────────────────────────────────────────────────────

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

const RECENT_POLL_INTERVAL_MS = 3000;

// ─── Generic file drop zone ───────────────────────────────────────────────────

interface DropZoneProps {
  accept: string;
  multiple?: boolean;
  disabled?: boolean;
  onFiles: (files: File[]) => void;
  children: React.ReactNode;
  className?: string;
}

function DropZone({ accept, multiple, disabled, onFiles, children, className = "" }: DropZoneProps) {
  const [dragging, setDragging] = useState(false);
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  const pick = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;
      onFiles(Array.from(files));
    },
    [onFiles]
  );

  return (
    <label
      htmlFor={inputId}
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); if (!disabled) pick(e.dataTransfer.files); }}
      className={`flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed p-5 text-center transition-colors focus-within:ring-2 focus-within:ring-accent ${
        dragging ? "border-accent bg-accent/10" : "border-border bg-surface-canvas hover:border-border-strong hover:bg-hover-row"
      } ${disabled ? "pointer-events-none opacity-50" : ""} ${className}`}
    >
      {children}
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={accept}
        multiple={multiple}
        className="sr-only"
        disabled={disabled}
        onChange={(e) => pick(e.target.files)}
      />
    </label>
  );
}

// ─── Stage 1: Mathpix Package ─────────────────────────────────────────────────

interface MathpixState {
  markdownFile: File | null;
  imageFiles: File[];
}

function MathpixPackageZone({
  state,
  onChange,
  disabled,
}: {
  state: MathpixState;
  onChange: (s: MathpixState) => void;
  disabled: boolean;
}) {
  const [mdError, setMdError] = useState<string | null>(null);

  const handleMarkdown = useCallback(
    (files: File[]) => {
      const f = files[0];
      if (!f) return;
      const name = f.name.toLowerCase();
      if (!name.endsWith(".md") && !name.endsWith(".mmd")) {
        setMdError("Only .md or .mmd files are accepted.");
        return;
      }
      setMdError(null);
      onChange({ ...state, markdownFile: f });
    },
    [state, onChange]
  );

  const handleImages = useCallback(
    (files: File[]) => {
      const images = files.filter((f) =>
        /\.(png|jpe?g|gif|webp|svg|tiff?)$/i.test(f.name)
      );
      onChange({ ...state, imageFiles: images });
    },
    [state, onChange]
  );

  const loaded = state.markdownFile !== null;

  return (
    <div className="rounded-xl border-2 border-border bg-surface-panel p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2.5">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-bold text-accent-contrast">
            1
          </span>
          <h2 className="text-sm font-bold text-text-primary">Mathpix Package</h2>
          <span className="rounded-full bg-accent/15 px-2 py-0.5 text-xs font-semibold text-accent">
            Primary Input
          </span>
        </div>
        {loaded ? (
          <span className="flex items-center gap-1.5 text-xs font-semibold text-success">
            <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M3 8l3.5 3.5 6.5-7" />
            </svg>
            Loaded
          </span>
        ) : (
          <span className="text-xs font-medium text-danger">Required</span>
        )}
      </div>

      {/* Markdown file */}
      <div className="mb-4">
        <p className="mb-2 text-xs font-semibold text-text-secondary uppercase tracking-wide">
          Markdown File <span className="text-danger">*</span>
        </p>

        {state.markdownFile ? (
          <div
            className="group flex items-center justify-between gap-2 rounded-lg border border-success/30 bg-success/10 px-4 py-3"
            title={`${state.markdownFile.name} — ${formatBytes(state.markdownFile.size)}`}
          >
            <div className="flex min-w-0 items-center gap-2.5">
              <svg className="h-4 w-4 shrink-0 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
              </svg>
              <span className="truncate text-sm font-medium text-text-primary">{state.markdownFile.name}</span>
              <span className="shrink-0 text-xs text-success">{formatBytes(state.markdownFile.size)}</span>
            </div>
            <button
              type="button"
              onClick={() => onChange({ ...state, markdownFile: null })}
              className="shrink-0 text-xs text-text-secondary opacity-0 transition-opacity hover:text-danger focus:outline-none focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-danger rounded group-hover:opacity-100"
              aria-label="Remove markdown file"
            >
              Remove
            </button>
          </div>
        ) : (
          <>
            <DropZone accept=".md,.mmd" onFiles={handleMarkdown} disabled={disabled}>
              <svg className="h-6 w-6 text-text-secondary/50" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m6.75 12-3-3m0 0-3 3m3-3v6m-1.5-15H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
              </svg>
              <span className="text-sm text-text-secondary">
                <span className="font-medium text-accent">Choose</span> or drop .md / .mmd file
              </span>
            </DropZone>
            {mdError && <p role="alert" className="mt-1.5 text-xs text-danger">{mdError}</p>}
          </>
        )}
      </div>

      {/* Image assets */}
      <div>
        <p className="mb-2 text-xs font-semibold text-text-secondary uppercase tracking-wide">
          Image Assets <span className="text-text-secondary/70 font-normal">(optional)</span>
        </p>

        {state.imageFiles.length > 0 ? (
          <div
            className="group flex items-center justify-between gap-2 rounded-lg border border-success/30 bg-success/10 px-4 py-3"
            title={state.imageFiles.map((f) => f.name).join(", ")}
          >
            <div className="flex min-w-0 items-center gap-2.5">
              <svg className="h-4 w-4 shrink-0 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
              </svg>
              <span className="truncate text-sm font-medium text-text-primary">
                {state.imageFiles.length} image{state.imageFiles.length === 1 ? "" : "s"} loaded
              </span>
            </div>
            <button
              type="button"
              onClick={() => onChange({ ...state, imageFiles: [] })}
              className="shrink-0 text-xs text-text-secondary opacity-0 transition-opacity hover:text-danger focus:outline-none focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-danger rounded group-hover:opacity-100"
              aria-label="Remove image files"
            >
              Remove
            </button>
          </div>
        ) : (
          <DropZone accept="image/*" multiple onFiles={handleImages} disabled={disabled} className="py-4">
            <span className="text-sm text-text-secondary">
              <span className="font-medium text-accent">Choose</span> or drop image files
            </span>
            <span className="text-xs text-text-secondary/70">PNG · JPEG · WebP · SVG</span>
          </DropZone>
        )}
      </div>
    </div>
  );
}

// ─── Stage 2: Source PDF ──────────────────────────────────────────────────────

function SourcePdfZone({
  file,
  onChange,
  disabled,
}: {
  file: File | null;
  onChange: (f: File | null) => void;
  disabled: boolean;
}) {
  const [error, setError] = useState<string | null>(null);

  const handleFiles = useCallback(
    (files: File[]) => {
      const f = files[0];
      if (!f) return;
      if (!f.name.toLowerCase().endsWith(".pdf")) {
        setError("Only PDF files are accepted.");
        return;
      }
      setError(null);
      onChange(f);
    },
    [onChange]
  );

  return (
    <div className="rounded-xl border-2 border-border bg-surface-panel p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-bold text-accent-contrast">
            2
          </span>
          <h2 className="text-sm font-bold text-text-primary">Original Source PDF</h2>
          <span className="rounded-full bg-surface-elevated px-2 py-0.5 text-xs font-semibold text-text-secondary">
            Verification Reference
          </span>
        </div>
        {file ? (
          <span className="flex items-center gap-1.5 text-xs font-semibold text-success">
            <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M3 8l3.5 3.5 6.5-7" />
            </svg>
            Loaded
          </span>
        ) : (
          <span className="text-xs font-medium text-danger">Required</span>
        )}
      </div>

      {/* Purpose note */}
      <div className="mb-4 rounded-lg border border-warning/30 bg-warning/10 px-4 py-3">
        <p className="text-xs font-semibold text-warning mb-1">
          This PDF is NOT the primary text source.
        </p>
        <p className="text-xs text-warning/90">
          Used only for: OCR verification · layout verification · heading verification ·
          figure verification · geometry comparison · accessibility validation
        </p>
      </div>

      {/* Drop zone or loaded state */}
      {file ? (
        <div
          className="group flex items-center justify-between gap-2 rounded-lg border border-success/30 bg-success/10 px-4 py-3"
          title={`${file.name} — ${formatBytes(file.size)}`}
        >
          <div className="flex min-w-0 items-center gap-2.5">
            <svg className="h-4 w-4 shrink-0 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
            <span className="truncate text-sm font-medium text-text-primary">{file.name}</span>
            <span className="shrink-0 text-xs text-success">{formatBytes(file.size)}</span>
          </div>
          <button
            type="button"
            onClick={() => onChange(null)}
            className="shrink-0 text-xs text-text-secondary opacity-0 transition-opacity hover:text-danger focus:outline-none focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-danger rounded group-hover:opacity-100"
            aria-label="Remove PDF file"
          >
            Remove
          </button>
        </div>
      ) : (
        <>
          <DropZone accept="application/pdf,.pdf" onFiles={handleFiles} disabled={disabled}>
            <svg className="h-6 w-6 text-text-secondary/50" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
            </svg>
            <span className="text-sm text-text-secondary">
              <span className="font-medium text-accent">Choose</span> or drop PDF file
            </span>
          </DropZone>
          {error && <p role="alert" className="mt-1.5 text-xs text-danger">{error}</p>}
        </>
      )}
    </div>
  );
}

// ─── Readiness checklist ──────────────────────────────────────────────────────

function ReadinessRow({ label, ready }: { label: string; ready: boolean }) {
  return (
    <li className="flex items-center gap-2.5 text-sm">
      <span
        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
          ready ? "bg-success" : "border border-border bg-surface-canvas"
        }`}
        aria-hidden="true"
      >
        {ready && (
          <svg className="h-3 w-3 text-accent-contrast" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 6l3 3 5-5" />
          </svg>
        )}
      </span>
      <span className={ready ? "text-text-primary" : "text-text-secondary/60"}>{label}</span>
    </li>
  );
}

// ─── Recent documents ─────────────────────────────────────────────────────────

// Live extracted-object counts for a job still processing — these fields
// (heading/image/footnote counts) update as the poll below re-fetches the
// list, before the job reaches a terminal status.
function ExtractedCounts({ job }: { job: JobSummary }) {
  const parts: string[] = [];
  if (job.heading_count !== null) parts.push(`${job.heading_count} headings`);
  if (job.image_count !== null) parts.push(`${job.image_count} images`);
  if (job.footnote_count !== null) parts.push(`${job.footnote_count} notes`);
  if (parts.length === 0) return null;
  return <span className="text-text-secondary/70">{parts.join(" · ")}</span>;
}

function RecentDocuments({ jobs }: { jobs: JobSummary[] | null }) {
  if (jobs === null) return <p className="text-sm text-text-secondary">Loading…</p>;
  if (jobs.length === 0) return <p className="text-sm text-text-secondary">No documents have been processed yet.</p>;
  return (
    <ul className="divide-y divide-border rounded-lg border border-border bg-surface-panel">
      {jobs.map((job) => (
        <li key={job.job_id}>
          <a
            href={`/documents/${job.job_id}`}
            className="flex items-center justify-between gap-4 p-4 hover:bg-hover-row focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent"
            title={`${job.filename} — uploaded ${new Date(job.created_at).toLocaleString()}`}
          >
            <span className="min-w-0 flex-1 truncate text-sm font-medium text-text-primary">{job.filename}</span>
            <span className="flex shrink-0 items-center gap-3 text-xs text-text-secondary">
              {(job.status === "queued" || job.status === "processing") && <ExtractedCounts job={job} />}
              {job.page_count !== null && <span>{job.page_count} pages</span>}
              {job.duration_seconds !== null && <span>{job.duration_seconds.toFixed(1)}s</span>}
              <JobStatusBadge status={job.status} />
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function UploadPage() {
  const router = useRouter();
  const [mathpix, setMathpix] = useState<MathpixState>({ markdownFile: null, imageFiles: [] });
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [recent, setRecent] = useState<JobSummary[] | null>(null);

  // Poll the recent-documents list while any job is still queued/processing,
  // so heading/image/footnote counts and status update live without a
  // manual refresh — same polling pattern as DocumentWorkspace.
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const jobs = await api.listDocuments();
        if (cancelled) return;
        setRecent(jobs);
        const anyActive = jobs.some((j) => j.status === "queued" || j.status === "processing");
        if (anyActive) {
          timer = setTimeout(poll, RECENT_POLL_INTERVAL_MS);
        }
      } catch {
        if (!cancelled) setRecent((prev) => prev ?? []);
      }
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  const mathpixReady = mathpix.markdownFile !== null;
  const pdfReady = pdfFile !== null;
  const canRun = mathpixReady && pdfReady && !isProcessing;

  async function handleRun() {
    const mmdFile = mathpix.markdownFile;
    if (!pdfFile || !mmdFile) return;
    setIsProcessing(true);
    setUploadError(null);
    try {
      const upload = await api.uploadDocument(pdfFile, mmdFile, mathpix.imageFiles, false);
      router.push(`/documents/${upload.job_id}`);
    } catch (err) {
      setIsProcessing(false);
      setUploadError(
        err instanceof ApiError
          ? `Upload failed: ${err.message}`
          : "Could not reach the RAWRS API. Confirm the backend is running on port 8000."
      );
    }
  }

  return (
    <div className="space-y-10">
      {/* Identity */}
      <section className="pt-2 pb-0">
        <h1 className="text-xl font-bold text-text-primary tracking-tight">
          Accessibility Verification &amp; Remediation Engine
        </h1>
        <p className="mt-1.5 text-sm text-text-secondary max-w-2xl">
          Verifies Mathpix output against the original PDF source. Applies deterministic
          accessibility remediation. Generates accessible DOCX and Markdown deliverables.
        </p>
      </section>

      {/* Upload form */}
      <section aria-labelledby="upload-heading">
        <h2 id="upload-heading" className="sr-only">Upload documents</h2>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <MathpixPackageZone state={mathpix} onChange={setMathpix} disabled={isProcessing} />
          <SourcePdfZone file={pdfFile} onChange={setPdfFile} disabled={isProcessing} />
        </div>

        {/* Readiness + Run */}
        <div className="mt-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between rounded-xl border border-border bg-surface-panel px-6 py-4">
          <ul className="flex flex-col gap-2 sm:flex-row sm:gap-6" aria-label="Upload readiness">
            <ReadinessRow label="Mathpix package loaded" ready={mathpixReady} />
            <ReadinessRow label="Source PDF loaded" ready={pdfReady} />
          </ul>

          <div className="flex flex-col items-start sm:items-end gap-1.5">
            <button
              type="button"
              onClick={handleRun}
              disabled={!canRun}
              className={`rounded-lg px-6 py-2.5 text-sm font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                canRun
                  ? "bg-accent text-accent-contrast hover:opacity-90"
                  : "bg-surface-elevated text-text-secondary/60 cursor-not-allowed"
              }`}
            >
              {isProcessing ? "Starting pipeline…" : "Run Verification Pipeline →"}
            </button>
            {!canRun && !isProcessing && (
              <p className="text-xs text-text-secondary/70">Both inputs required to proceed</p>
            )}
          </div>
        </div>

        {uploadError && (
          <p role="alert" className="mt-3 text-sm text-danger">{uploadError}</p>
        )}
      </section>

      {/* Recent documents */}
      <section aria-labelledby="recent-heading">
        <h2 id="recent-heading" className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
          Recent Documents
        </h2>
        <RecentDocuments jobs={recent} />
      </section>
    </div>
  );
}
