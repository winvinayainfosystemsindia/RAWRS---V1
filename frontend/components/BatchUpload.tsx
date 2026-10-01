"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { DropZone } from "./DropZone";

// Batch PDF upload (frontend plan item 5). The backend takes one file per
// request, so the queue lives here: files upload strictly one at a time
// (the pipeline itself is the heavy resource), each file shows its own
// state, and cancel stops the queue and aborts the in-flight request.
// Honest limitation, stated in the UI: once a request has reached the
// backend the pipeline may still process that file server-side — cancel
// means "stop queuing and stop tracking", not a server-side kill.

type QueueState = "queued" | "uploading" | "done" | "error" | "cancelled";

interface QueueItem {
  id: number;
  file: File;
  state: QueueState;
  jobId?: string;
  error?: string;
}

const STATE_LABEL: Record<QueueState, string> = {
  queued: "Queued",
  uploading: "Uploading…",
  done: "Uploaded",
  error: "Failed",
  cancelled: "Cancelled",
};

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function BatchUpload() {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  // The run loop reads the latest items through a ref (setItems during an
  // await must not require a re-render to be visible to the loop), and a
  // pump counter (re)starts it after files are added — mount-scoped effect,
  // so adding files mid-run can never abort the in-flight upload via effect
  // cleanup.
  const itemsRef = useRef<QueueItem[]>([]);
  const runningRef = useRef(false);
  const nextIdRef = useRef(1);
  const controllerRef = useRef<AbortController | null>(null);
  const [pump, setPump] = useState(0);

  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

  useEffect(() => {
    if (runningRef.current) return;
    let alive = true;
    runningRef.current = true;

    async function run() {
      while (alive) {
        const next = itemsRef.current.find((q) => q.state === "queued");
        if (!next) break;
        setItems((prev) => prev.map((q) => (q.id === next.id ? { ...q, state: "uploading" } : q)));
        const controller = new AbortController();
        controllerRef.current = controller;
        try {
          const upload = await api.uploadDocument(next.file, undefined, [], true, controller.signal);
          if (!alive) break;
          setItems((prev) =>
            prev.map((q) => (q.id === next.id ? { ...q, state: "done", jobId: upload.job_id } : q))
          );
        } catch (err) {
          if (!alive) break;
          const aborted = controller.signal.aborted;
          setItems((prev) =>
            prev.map((q) =>
              q.id === next.id
                ? {
                    ...q,
                    state: aborted ? "cancelled" : "error",
                    error: aborted
                      ? undefined
                      : err instanceof ApiError
                        ? err.message
                        : "Could not reach the RAWRS API.",
                  }
                : q
            )
          );
        } finally {
          controllerRef.current = null;
        }
      }
      runningRef.current = false;
    }

    void run();
    return () => {
      alive = false;
      runningRef.current = false;
      controllerRef.current?.abort();
    };
  }, [pump]);

  function addFiles(files: File[]) {
    const pdfs = files.filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (pdfs.length === 0) {
      setListError("Only PDF files can be queued.");
      return;
    }
    setListError(null);
    const added: QueueItem[] = pdfs.map((file) => ({
      id: nextIdRef.current++,
      file,
      state: "queued",
    }));
    setItems((prev) => [...prev, ...added]);
    setPump((p) => p + 1);
  }

  const isRunning = items.some((q) => q.state === "uploading");
  const hasActive = items.some((q) => q.state === "queued" || q.state === "uploading");

  function cancelQueue() {
    // Abort whatever request is in flight; mark everything still queued as
    // cancelled so the loop has nothing left to pick up.
    controllerRef.current?.abort();
    setItems((prev) =>
      prev.map((q) => (q.state === "queued" ? { ...q, state: "cancelled" } : q))
    );
  }

  function removeItem(id: number) {
    setItems((prev) => prev.filter((q) => q.id !== id || q.state === "uploading"));
  }

  function clearFinished() {
    setItems((prev) => prev.filter((q) => q.state === "queued" || q.state === "uploading"));
  }

  const finishedCount = items.filter((q) => q.state === "done").length;

  return (
    // A div, not a <section>: the upload page wraps this component in its
    // own named region ("Batch Upload"), and a named <section> here would
    // nest a second region with the same name — an axe landmark-unique
    // violation, found by the landing page's a11y test.
    <div>

      {items.length === 0 ? (
        <DropZone accept="application/pdf,.pdf" multiple onFiles={addFiles}>
          <span className="text-sm text-text-secondary">
            <span className="font-medium text-accent">Choose</span> one or many PDFs — they are
            processed one at a time
          </span>
          <span className="text-xs text-text-secondary/70">PDF only · Mathpix packages are per-document</span>
        </DropZone>
      ) : (
        <div className="rounded-lg border border-border bg-surface-panel">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
            <p className="text-xs font-semibold text-text-secondary" aria-live="polite">
              {finishedCount}/{items.length} uploaded · processing one at a time
            </p>
            <div className="flex items-center gap-2">
              {hasActive && (
                <button
                  type="button"
                  onClick={cancelQueue}
                  className="rounded border border-danger/40 px-3 py-1 text-xs font-medium text-danger hover:bg-danger/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                >
                  {isRunning ? "Cancel queue" : "Cancel all"}
                </button>
              )}
              {!hasActive && items.length > 0 && (
                <button
                  type="button"
                  onClick={clearFinished}
                  className="rounded border border-border px-3 py-1 text-xs font-medium text-text-secondary hover:bg-hover-row focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                >
                  Clear list
                </button>
              )}
            </div>
          </div>
          <ul className="divide-y divide-border">
            {items.map((q) => (
              <li key={q.id} className="flex items-center justify-between gap-3 px-4 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-text-primary">{q.file.name}</p>
                  <p className="text-xs text-text-secondary">
                    {formatBytes(q.file.size)}
                    {q.state === "error" && q.error ? ` — ${q.error}` : ""}
                    {q.state === "cancelled" && " — removed from the queue; if the pipeline already received it, it may still finish server-side"}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {q.state === "uploading" && (
                    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-accent border-t-transparent" aria-hidden="true" />
                  )}
                  <span
                    className={`text-xs font-semibold ${
                      q.state === "done"
                        ? "text-success"
                        : q.state === "error"
                          ? "text-danger"
                          : q.state === "cancelled"
                            ? "text-text-secondary"
                            : "text-text-secondary"
                    }`}
                  >
                    {STATE_LABEL[q.state]}
                  </span>
                  {q.jobId && (
                    <Link
                      href={`/documents/${q.jobId}`}
                      className="rounded border border-border px-2 py-0.5 text-xs font-medium text-accent hover:bg-hover-row focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                    >
                      Open →
                    </Link>
                  )}
                  {(q.state === "queued" || q.state === "error" || q.state === "cancelled" || q.state === "done") && (
                    <button
                      type="button"
                      onClick={() => removeItem(q.id)}
                      aria-label={`Remove ${q.file.name} from the list`}
                      className="text-xs text-text-secondary hover:text-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded"
                    >
                      ✕
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
          <div className="border-t border-border px-4 py-2.5">
            <DropZone accept="application/pdf,.pdf" multiple onFiles={addFiles} className="p-3">
              <span className="text-xs text-text-secondary">
                <span className="font-medium text-accent">Add</span> more PDFs to the queue
              </span>
            </DropZone>
          </div>
        </div>
      )}

      {listError && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {listError}
        </p>
      )}
    </div>
  );
}
