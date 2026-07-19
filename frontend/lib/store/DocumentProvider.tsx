"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { DocumentDataProvider, useDocumentData, useDocumentDispatch } from "./DocumentDataContext";
import { SelectionProvider } from "./SelectionContext";
import { PdfViewportProvider } from "./PdfViewportContext";
import { MarkdownViewportProvider } from "./MarkdownViewportContext";
import { ReviewQueueProvider } from "./ReviewQueueContext";
import { ToastProvider } from "@/components/Toast";

const POLL_INTERVAL_MS = 3000;
// ponytail: plain polling, not a websocket/SSE push. Fine at today's
// single-reviewer-per-document scale; switch to a push channel if this
// workspace ever needs many concurrent viewers watching one job.
const VERSION_POLL_INTERVAL_MS = 4000;

// Wraps one labeled result fetch so a failure is recorded (into `errors`)
// instead of silently collapsing to an empty result — a compliance tool must
// never render "backend errored" as "nothing to fix". The fallback still lets
// the rest of the workspace load; the recorded label drives a retryable
// banner (see DocumentWorkspace).
async function tryLoad<T>(label: string, errors: string[], fn: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await fn();
  } catch {
    errors.push(label);
    return fallback;
  }
}

function DocumentPoller({ jobId, reloadNonce }: { jobId: string; reloadNonce: number }) {
  const dispatch = useDocumentDispatch();
  // Tracks the last document_version this tab has loaded outputs for, so
  // the post-completion watcher below only refetches Markdown when the
  // canonical document actually changed (a correction accepted, a table
  // saved, alt text approved, ...) rather than on every poll tick.
  const knownVersionRef = useRef<number | null>(null);

  useEffect(() => {
    api.getAiStatus().then((aiStatus) => dispatch({ type: "SET_AI_STATUS", aiStatus }))
      .catch(() => dispatch({ type: "SET_AI_STATUS", aiStatus: null }));
  }, [dispatch]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function loadResults(summary: Awaited<ReturnType<typeof api.getDocument>>) {
      const errors: string[] = [];
      const [validation, images, tables, footnotes, headings, lists, callouts, metadata, pages, readingOrder, pageLabels, corrections, readiness] =
        await Promise.all([
          tryLoad("validation", errors, () => api.getValidation(jobId), { issues: [], error_count: 0, warning_count: 0, info_count: 0 }),
          tryLoad("images", errors, () => api.getImages(jobId), { images: [] }),
          tryLoad("tables", errors, () => api.getTables(jobId), { tables: [] }),
          tryLoad("footnotes", errors, () => api.getFootnotes(jobId), { footnotes: [] }),
          tryLoad("headings", errors, () => api.getHeadings(jobId), { headings: [] }),
          tryLoad("lists", errors, () => api.getLists(jobId), { lists: [] }),
          tryLoad("callouts", errors, () => api.getCallouts(jobId), { callouts: [] }),
          tryLoad("metadata", errors, () => api.getMetadata(jobId), null),
          tryLoad("OCR pages", errors, () => api.getPages(jobId), { pages: [] }),
          tryLoad("reading order", errors, () => api.getReadingOrder(jobId), { pages: [] }),
          tryLoad("page labels", errors, () => api.getPageLabels(jobId), { pages: [], sections: [] }),
          tryLoad("corrections", errors, () => api.getCorrections(jobId), { corrections: [] }),
          tryLoad("readiness", errors, () => api.getReadiness(jobId), null),
        ]);
      const markdown = summary.markdown_available
        ? await tryLoad("markdown", errors, () => api.getMarkdown(jobId).then((r) => r.content), "")
        : "";
      const accessibilityReport = await tryLoad("accessibility report", errors, () => api.getAccessibilityReport(jobId), null);
      if (cancelled) return;
      knownVersionRef.current = summary.document_version;
      dispatch({ type: "SET_ACCESSIBILITY_REPORT", report: accessibilityReport });
      dispatch({
        type: "LOAD_RESULTS",
        payload: {
          headings: headings.headings,
          tables: tables.tables,
          images: images.images,
          footnotes: footnotes.footnotes,
          lists: lists.lists,
          callouts: callouts.callouts,
          corrections: corrections.corrections,
          pageLabels: pageLabels.pages,
          pageLabelSections: pageLabels.sections,
          readingOrder: readingOrder.pages,
          validationIssues: validation.issues,
          metadata,
          pages: pages.pages,
          readiness,
          markdown,
          loadErrors: errors,
        },
      });
    }

    // Once the pipeline finishes, switch from "wait for completion" polling
    // to "watch for edits" polling — any reviewer action elsewhere (accept a
    // correction, save a table, approve alt text, ...) bumps document_version
    // server-side, and this is the only thing that would tell this tab so
    // Markdown/DOCX previews stop going stale.
    async function watchVersion() {
      try {
        const summary = await api.getDocument(jobId);
        if (cancelled) return;
        dispatch({ type: "SET_JOB", job: summary });

        if (summary.document_version !== knownVersionRef.current) {
          knownVersionRef.current = summary.document_version;
          // The canonical document changed — refresh both the Markdown
          // preview AND the intelligence (score/report), so a reviewer
          // action taken in another tab moves the numbers here too, without
          // a manual refresh. useReviewAction already refreshes the acting
          // tab immediately; this covers cross-tab / out-of-band changes.
          const [content, readiness, report] = await Promise.all([
            summary.markdown_available
              ? api.getMarkdown(jobId).then((r) => r.content).catch(() => null)
              : Promise.resolve(null),
            api.getReadiness(jobId).catch(() => undefined),
            api.getAccessibilityReport(jobId).catch(() => undefined),
          ]);
          if (cancelled) return;
          if (content !== null) dispatch({ type: "UPDATE_MARKDOWN", markdown: content });
          if (readiness !== undefined) dispatch({ type: "SET_READINESS", readiness });
          if (report !== undefined) dispatch({ type: "SET_ACCESSIBILITY_REPORT", report });
        }
      } catch {
        // transient errors just get retried on the next tick
      }
      if (!cancelled) timer = setTimeout(watchVersion, VERSION_POLL_INTERVAL_MS);
    }

    async function poll() {
      try {
        const summary = await api.getDocument(jobId);
        if (cancelled) return;
        dispatch({ type: "SET_JOB", job: summary });

        if (summary.status === "complete" || summary.status === "failed") {
          await loadResults(summary);
          if (!cancelled) timer = setTimeout(watchVersion, VERSION_POLL_INTERVAL_MS);
          return;
        }
        timer = setTimeout(poll, POLL_INTERVAL_MS);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          dispatch({ type: "SET_NOT_FOUND" });
        } else {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      }
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // reloadNonce in deps: a REQUEST_RELOAD (the error banner's Retry) tears
    // down and restarts the whole poll loop, re-running loadResults from
    // scratch — so retry needs no page refresh.
  }, [jobId, dispatch, reloadNonce]);

  return null;
}

// Reads reloadNonce off the data context so REQUEST_RELOAD re-triggers the
// poller effect. Split from DocumentProvider so it sits inside
// DocumentDataProvider (where the hook is valid).
function DocumentPollerHost({ jobId }: { jobId: string }) {
  const { reloadNonce } = useDocumentData();
  return <DocumentPoller jobId={jobId} reloadNonce={reloadNonce} />;
}

export function DocumentProvider({ jobId, children }: { jobId: string; children: ReactNode }) {
  return (
    <DocumentDataProvider>
      <SelectionProvider>
        <PdfViewportProvider>
          <MarkdownViewportProvider>
            <ReviewQueueProvider>
              <ToastProvider>
                <DocumentPollerHost jobId={jobId} />
                {children}
              </ToastProvider>
            </ReviewQueueProvider>
          </MarkdownViewportProvider>
        </PdfViewportProvider>
      </SelectionProvider>
    </DocumentDataProvider>
  );
}
