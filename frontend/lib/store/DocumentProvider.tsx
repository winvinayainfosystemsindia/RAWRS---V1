"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { DocumentDataProvider, useDocumentDispatch } from "./DocumentDataContext";
import { SelectionProvider } from "./SelectionContext";
import { PdfViewportProvider } from "./PdfViewportContext";
import { MarkdownViewportProvider } from "./MarkdownViewportContext";

const POLL_INTERVAL_MS = 3000;
// ponytail: plain polling, not a websocket/SSE push. Fine at today's
// single-reviewer-per-document scale; switch to a push channel if this
// workspace ever needs many concurrent viewers watching one job.
const VERSION_POLL_INTERVAL_MS = 4000;

function DocumentPoller({ jobId }: { jobId: string }) {
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
      const [validation, images, tables, footnotes, headings, lists, callouts, metadata, pages, readingOrder, pageLabels, corrections, readiness] =
        await Promise.all([
          api.getValidation(jobId).catch(() => ({ issues: [], error_count: 0, warning_count: 0, info_count: 0 })),
          api.getImages(jobId).catch(() => ({ images: [] })),
          api.getTables(jobId).catch(() => ({ tables: [] })),
          api.getFootnotes(jobId).catch(() => ({ footnotes: [] })),
          api.getHeadings(jobId).catch(() => ({ headings: [] })),
          api.getLists(jobId).catch(() => ({ lists: [] })),
          api.getCallouts(jobId).catch(() => ({ callouts: [] })),
          api.getMetadata(jobId).catch(() => null),
          api.getPages(jobId).catch(() => ({ pages: [] })),
          api.getReadingOrder(jobId).catch(() => ({ pages: [] })),
          api.getPageLabels(jobId).catch(() => ({ pages: [], sections: [] })),
          api.getCorrections(jobId).catch(() => ({ corrections: [] })),
          api.getReadiness(jobId).catch(() => null),
        ]);
      const markdown = summary.markdown_available
        ? await api.getMarkdown(jobId).then((r) => r.content).catch(() => "")
        : "";
      const accessibilityReport = await api.getAccessibilityReport(jobId).catch(() => null);
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
          if (summary.markdown_available) {
            const content = await api.getMarkdown(jobId).then((r) => r.content).catch(() => null);
            if (!cancelled && content !== null) {
              dispatch({ type: "UPDATE_MARKDOWN", markdown: content });
            }
          }
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
  }, [jobId, dispatch]);

  return null;
}

export function DocumentProvider({ jobId, children }: { jobId: string; children: ReactNode }) {
  return (
    <DocumentDataProvider>
      <SelectionProvider>
        <PdfViewportProvider>
          <MarkdownViewportProvider>
            <DocumentPoller jobId={jobId} />
            {children}
          </MarkdownViewportProvider>
        </PdfViewportProvider>
      </SelectionProvider>
    </DocumentDataProvider>
  );
}
