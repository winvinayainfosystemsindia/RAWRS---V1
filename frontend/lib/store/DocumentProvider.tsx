"use client";

import { useEffect, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { DocumentDataProvider, useDocumentDispatch } from "./DocumentDataContext";
import { SelectionProvider } from "./SelectionContext";
import { PdfViewportProvider } from "./PdfViewportContext";
import { MarkdownViewportProvider } from "./MarkdownViewportContext";

const POLL_INTERVAL_MS = 3000;

function DocumentPoller({ jobId }: { jobId: string }) {
  const dispatch = useDocumentDispatch();

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
      if (cancelled) return;
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

    async function poll() {
      try {
        const summary = await api.getDocument(jobId);
        if (cancelled) return;
        dispatch({ type: "SET_JOB", job: summary });

        if (summary.status === "complete" || summary.status === "failed") {
          await loadResults(summary);
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
