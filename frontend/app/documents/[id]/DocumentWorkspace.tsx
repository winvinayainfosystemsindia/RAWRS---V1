"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { DocumentProvider } from "@/lib/store/DocumentProvider";
import {
  useDocumentData,
  useDocumentDispatch,
  selectHeadings,
  selectTables,
  selectImages,
  selectFootnotes,
  selectLists,
  selectCallouts,
  selectCorrections,
  selectPageLabels,
  selectReadingOrder,
  listKey,
  calloutKey,
} from "@/lib/store/DocumentDataContext";
import { useMarkdownViewport } from "@/lib/store/MarkdownViewportContext";
import { useSelection } from "@/lib/store/SelectionContext";
import type { PdfObjectOverlay } from "@/components/PdfViewer";
import { usePdfViewport } from "@/lib/store/PdfViewportContext";
import { useElapsedSeconds } from "@/lib/store/useElapsedSeconds";
import { PipelineView } from "@/components/PipelineView";
import { ResultsDashboard } from "@/components/ResultsDashboard";
import { OutputWorkspace } from "@/components/OutputWorkspace";
import { MarkdownEditor } from "@/components/MarkdownEditor";
import { DocxPreview } from "@/components/DocxPreview";
import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { SemanticNavTree, type NavSection } from "@/components/workspace/SemanticNavTree";
import { NavChips } from "@/components/workspace/NavChips";
import { ContextInspectorRail } from "@/components/workspace/ContextInspectorRail";
import { BottomPanel } from "@/components/workspace/BottomPanel";
import { ValidationIssueTable } from "@/components/ValidationIssueTable";
import { ImageGrid } from "@/components/ImageGrid";
import { TableGrid } from "@/components/TableGrid";
import { HeadingGrid } from "@/components/HeadingGrid";
import { FootnoteTable } from "@/components/FootnoteTable";
import { ListPanel } from "@/components/ListPanel";
import { CalloutPanel } from "@/components/CalloutPanel";
import { MetadataPanel } from "@/components/MetadataPanel";
import { OcrPageTable } from "@/components/OcrPageTable";
import { ReadingOrderPanel } from "@/components/ReadingOrderPanel";
import { PageLabelManagerPanel } from "@/components/PageLabelManagerPanel";
import { CorrectionsPanel } from "@/components/CorrectionsPanel";
import { ReadinessPanel } from "@/components/ReadinessPanel";
import { ChevronDownIcon } from "@/components/icons";

// Naive positional line diff for the "flash changed lines" signal after a
// live document_version regen — not a real LCS diff (would misreport a
// single inserted line as N changed lines), but good enough to draw the
// reviewer's eye toward what moved. Skips flashing entirely on a
// large-scale rewrite, where line-by-line highlighting isn't useful signal.
function computeChangedLines(oldText: string, newText: string, maxFlash = 80): number[] {
  if (!oldText || oldText === newText) return [];
  const oldLines = oldText.split("\n");
  const newLines = newText.split("\n");
  const changed: number[] = [];
  const max = Math.max(oldLines.length, newLines.length);
  for (let i = 0; i < max; i++) {
    if (oldLines[i] !== newLines[i]) changed.push(i + 1);
    if (changed.length > maxFlash) return [];
  }
  return changed;
}

// pdfjs-dist touches browser-only globals (DOMMatrix, etc.) that don't
// exist during Next.js's SSR pass of client components — load it
// client-only.
const PdfViewer = dynamic(() => import("@/components/PdfViewer").then((m) => m.PdfViewer), {
  ssr: false,
  loading: () => <p className="p-4 text-sm text-text-secondary">Loading PDF Inspector…</p>,
});

export function DocumentWorkspace({ jobId }: { jobId: string }) {
  return (
    <DocumentProvider jobId={jobId}>
      <DocumentWorkspaceContent jobId={jobId} />
    </DocumentProvider>
  );
}

function DocumentWorkspaceContent({ jobId }: { jobId: string }) {
  const state = useDocumentData();
  const dispatch = useDocumentDispatch();
  const { jumpTarget: mdJumpTarget, jumpToLine } = useMarkdownViewport();
  const { selection, select } = useSelection();
  const { pageNumber } = usePdfViewport();
  const [activeSpecialView, setActiveSpecialView] = useState("");
  const [overviewOpen, setOverviewOpen] = useState(false);
  // Bumped by WorkspaceShell's toolbar Search button; SemanticNavTree
  // watches this to switch itself into Search mode (see focusSignal).
  const [searchNonce, setSearchNonce] = useState(0);
  const elapsed = useElapsedSeconds(state.job);

  // Diff against the markdown from before this render's update, so a live
  // document_version regen can flash exactly what changed. The ref updates
  // in an effect (after commit) so this render's diff still sees the old
  // value — see computeChangedLines above.
  const prevMarkdownRef = useRef(state.markdown);
  const markdownFlashLines = useMemo(
    () => computeChangedLines(prevMarkdownRef.current, state.markdown),
    [state.markdown]
  );
  useEffect(() => {
    prevMarkdownRef.current = state.markdown;
  }, [state.markdown]);

  // Every hook must run unconditionally on every render, so this stays
  // above the notFound/loading early returns below — selectors here only
  // read always-present dictionary fields off `state`, never `state.job`,
  // so they're safe to compute before job is known to exist.
  const pdfOverlays = useMemo((): PdfObjectOverlay[] => {
    const out: PdfObjectOverlay[] = [];
    for (const h of selectHeadings(state)) {
      if (h.bbox) out.push({ objectType: "heading", objectId: h.document_order, pageNumber: h.page_number, bbox: h.bbox, sourceLine: h.source_line, label: h.text || `H${h.level}` });
    }
    for (const t of selectTables(state)) {
      if (t.bbox) out.push({ objectType: "table", objectId: t.table_id, pageNumber: t.page_number, bbox: t.bbox, sourceLine: t.source_line ?? null, label: t.caption || "Table" });
    }
    for (const img of selectImages(state)) {
      if (img.bbox) out.push({ objectType: "image", objectId: img.image_id, pageNumber: img.page_number, bbox: img.bbox, label: img.figure?.caption || img.figure?.alt_text || "Figure" });
    }
    for (const l of selectLists(state)) {
      if (l.bbox) out.push({ objectType: "list", objectId: listKey(l), pageNumber: l.page_number, bbox: l.bbox, sourceLine: l.source_line ?? null, label: l.items[0]?.text || "List" });
    }
    for (const c of selectCallouts(state)) {
      if (c.bbox) out.push({ objectType: "callout", objectId: calloutKey(c), pageNumber: c.page_number ?? 1, bbox: c.bbox, sourceLine: c.source_line ?? null, label: c.label });
    }
    return out;
  }, [state]);

  const { job, notFound } = state;

  // Phase F-2.2: every page needs its own <title> — screen readers announce
  // it on navigation, and every document workspace previously shared the
  // app's generic title, making tabs/history indistinguishable by name.
  useEffect(() => {
    if (job) document.title = `${job.filename} — RAWRS`;
  }, [job]);

  if (notFound) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-danger" role="alert">
          No document found for this ID. It may have been processed before the API was last restarted.
        </p>
        <Link href="/" className="text-sm font-medium text-accent hover:underline">
          &larr; Upload a document
        </Link>
      </div>
    );
  }

  if (!job) {
    return <p role="status" className="text-sm text-text-secondary">Loading document…</p>;
  }

  const isActive = job.status === "queued" || job.status === "processing";
  const isDone = job.status === "complete" || job.status === "failed";

  const tables = selectTables(state);
  const headings = selectHeadings(state);
  const images = selectImages(state);
  const footnotes = selectFootnotes(state);
  const lists = selectLists(state);
  const callouts = selectCallouts(state);
  const corrections = selectCorrections(state);
  const pageLabels = selectPageLabels(state);
  const readingOrder = selectReadingOrder(state);

  const pendingCorrections = corrections.filter((c) =>
    ["proposed", "pending_review"].includes(c.status)
  ).length;
  const unreviewedReadingOrder = readingOrder.filter(
    (p) => p.reading_order_status === "unreviewed"
  ).length;
  const labelConflicts = pageLabels.filter((p) => p.label_conflict).length;

  function handlePdfOverlayClick(overlay: PdfObjectOverlay) {
    select(overlay.objectType, overlay.objectId);
    setActiveSpecialView("");
    if (overlay.sourceLine != null) jumpToLine(overlay.sourceLine);
  }

  function handleCorrectionJump(correction: { correction_id: string }) {
    select("correction", correction.correction_id);
    setActiveSpecialView("");
  }

  const specialViews: NavSection[] = [
    { id: "validation", label: "Validation", count: state.validationIssues.length },
    { id: "images", label: "Images", count: images.length },
    { id: "tables", label: "Tables", count: tables.length },
    { id: "headings", label: "Headings", count: headings.length },
    { id: "footnotes", label: "Footnotes", count: footnotes.length },
    { id: "lists", label: "Lists", count: lists.length },
    { id: "callouts", label: "Callouts", count: callouts.length },
    { id: "metadata", label: "Metadata" },
    { id: "ocr", label: "OCR Pages" },
    {
      id: "reading-order",
      label: "Reading Order",
      count: readingOrder.length,
      urgentCount: unreviewedReadingOrder,
    },
    { id: "page-labels", label: "Page Labels", count: pageLabels.length, urgentCount: labelConflicts },
    { id: "corrections", label: "Corrections", count: corrections.length, urgentCount: pendingCorrections },
    { id: "readiness", label: "Accessibility Readiness" },
  ];

  function renderSpecialView() {
    switch (activeSpecialView) {
      case "validation":
        return (
          <ValidationIssueTable
            issues={state.validationIssues}
            jobId={jobId}
            onIssueUpdated={(issue) => dispatch({ type: "UPDATE_VALIDATION_ISSUE", issue })}
            readiness={state.readiness}
          />
        );
      case "images":
        return (
          <ImageGrid
            images={images}
            jobId={jobId}
            aiStatus={state.aiStatus}
            onImagesUpdated={(updated) => dispatch({ type: "REPLACE_IMAGES", images: updated })}
          />
        );
      case "tables":
        return (
          <TableGrid
            tables={tables}
            jobId={jobId}
            aiStatus={state.aiStatus}
            onTablesUpdated={(updated) => dispatch({ type: "REPLACE_TABLES", tables: updated })}
          />
        );
      case "headings":
        return (
          <HeadingGrid
            headings={headings}
            jobId={jobId}
            onHeadingsUpdated={(updated) => dispatch({ type: "REPLACE_HEADINGS", headings: updated })}
          />
        );
      case "footnotes":
        return (
          <FootnoteTable
            footnotes={footnotes}
            jobId={jobId}
            onFootnotesUpdated={(updated) => dispatch({ type: "REPLACE_FOOTNOTES", footnotes: updated })}
          />
        );
      case "lists":
        return <ListPanel lists={lists} jobId={jobId} />;
      case "callouts":
        return <CalloutPanel callouts={callouts} jobId={jobId} />;
      case "metadata":
        return state.metadata ? (
          <MetadataPanel
            metadata={state.metadata}
            jobId={jobId}
            onUpdated={(updated) => dispatch({ type: "UPDATE_METADATA", metadata: updated })}
          />
        ) : (
          <p className="text-sm text-text-secondary">Metadata not available.</p>
        );
      case "ocr":
        return <OcrPageTable pages={state.pages} />;
      case "reading-order":
        return (
          <ReadingOrderPanel
            pages={readingOrder}
            jobId={jobId}
            onPagesUpdated={(updated) => dispatch({ type: "REPLACE_READING_ORDER", pages: updated })}
          />
        );
      case "page-labels":
        return (
          <PageLabelManagerPanel
            jobId={jobId}
            pages={pageLabels}
            sections={state.pageLabelSections}
            onUpdated={(updated) =>
              dispatch({ type: "UPDATE_PAGE_LABELS", pages: updated.pages, sections: updated.sections })
            }
          />
        );
      case "corrections":
        return (
          <CorrectionsPanel
            corrections={corrections}
            jobId={jobId}
            onCorrectionsUpdated={(updated) => dispatch({ type: "REPLACE_CORRECTIONS", corrections: updated })}
            onCorrectionClick={handleCorrectionJump}
          />
        );
      case "readiness":
        return <ReadinessPanel readiness={state.readiness} onSelectCategory={setActiveSpecialView} />;
      default:
        return null;
    }
  }

  return (
    <div className="space-y-4">
      {/* Phase F-2.2: this workspace had zero heading elements of any level
          (confirmed via live accessibility-tree inspection) — screen
          reader "jump to next heading" navigation had nothing to land on.
          Visually hidden since the filename is already shown in
          WorkspaceShell's own toolbar; this exists purely so the page has
          the one H1 every page needs, same as app/page.tsx already has. */}
      <h1 className="sr-only">{job.filename}</h1>
      {/* Error banner */}
      {job.status === "failed" && (
        <div role="alert" className="rounded-lg border border-danger/30 bg-danger/10 p-4">
          <p className="text-sm font-semibold text-danger">
            Processing failed{job.failed_stage ? ` at stage "${job.failed_stage}"` : ""}.
          </p>
          {job.error_message && <p className="mt-1 text-sm text-danger/90">{job.error_message}</p>}
        </div>
      )}

      {/* Processing status */}
      {isActive && (
        <div role="status" className="rounded-lg border border-accent/30 bg-accent/10 p-4">
          <p className="text-sm font-medium text-text-primary">
            {job.status === "queued"
              ? "Queued — waiting to start…"
              : "Verification pipeline is running. This page updates automatically."}
          </p>
          <p className="mt-1 text-xs text-text-secondary">
            Scanned PDFs that require OCR may take several minutes per page.
          </p>
        </div>
      )}

      {/* Overview — collapsed by default once processing completes. The
          document is the product; pipeline/stat cards are a glance, not
          the default view. */}
      {isDone && (
        <div className="rounded-lg border border-border bg-surface-panel">
          <button
            type="button"
            onClick={() => setOverviewOpen((v) => !v)}
            aria-expanded={overviewOpen}
            className="flex w-full items-center justify-between px-4 py-2 text-xs font-semibold uppercase tracking-wider text-text-secondary hover:text-text-primary"
          >
            <span>Overview</span>
            <ChevronDownIcon open={overviewOpen} />
          </button>
          {overviewOpen && (
            <div className="space-y-6 border-t border-border p-4">
              <ResultsDashboard
                job={job}
                issues={state.validationIssues}
                images={images}
                footnotes={footnotes}
                pages={state.pages}
                tables={tables}
              />
              <OutputWorkspace job={job} generatedMarkdown={state.markdown} />
              {/* Phase R-2 M4: internal pipeline-stage detail demoted below
                  the reviewer-relevant sections above and behind its own
                  disclosure — it answers "did the pipeline run", not "what
                  should I do first", so it no longer leads the panel.
                  Same native <details> pattern already used elsewhere
                  (Export menu, validation category accordions). */}
              <details className="rounded-lg border border-border">
                <summary className="cursor-pointer select-none px-4 py-2 text-xs font-semibold uppercase tracking-wider text-text-secondary hover:text-text-primary">
                  Processing Log
                </summary>
                <div className="border-t border-border p-4">
                  <PipelineView status={job.status} elapsed={elapsed} />
                </div>
              </details>
            </div>
          )}
        </div>
      )}
      {isActive && (
        <div className="w-full lg:w-64">
          <PipelineView status={job.status} elapsed={elapsed} />
        </div>
      )}

      {isDone && (
        <WorkspaceShell
          filename={job.filename}
          status={job.status}
          documentVersion={job.document_version}
          elapsedSeconds={elapsed}
          durationSeconds={job.duration_seconds}
          mode={activeSpecialView ? "special" : "document"}
          currentPage={pageNumber}
          readinessScore={state.readiness?.overall_score ?? null}
          readinessReady={state.readiness?.ready}
          onOpenSearch={() => {
            setActiveSpecialView("");
            setSearchNonce((n) => n + 1);
          }}
          jobId={jobId}
          docxAvailable={job.docx_available}
          markdownAvailable={job.markdown_available}
          reportAvailable={job.report_available}
          docxStale={job.docx_generated_at_version !== null && job.docx_generated_at_version !== job.document_version}
          markdownStale={
            job.markdown_generated_at_version !== null && job.markdown_generated_at_version !== job.document_version
          }
          quickNav={
            <NavChips
              sections={specialViews}
              activeSpecialView={activeSpecialView || null}
              onSelect={setActiveSpecialView}
            />
          }
          nav={
            <SemanticNavTree
              specialViews={specialViews}
              activeSpecialView={activeSpecialView || null}
              onSelectSpecialView={setActiveSpecialView}
              focusSignal={searchNonce}
            />
          }
          centerViews={{
            pdf: (
              <PdfViewer
                jobId={jobId}
                overlays={pdfOverlays}
                selectedOverlayId={selection?.objectId ?? null}
                onOverlayClick={handlePdfOverlayClick}
                readingOrderBlocks={readingOrder.flatMap((p) => p.blocks)}
              />
            ),
            markdown: (
              <div className="h-full p-4">
                <MarkdownEditor
                  key={`md-${job.document_version ?? 0}`}
                  initialContent={state.markdown}
                  readOnly
                  scrollToLine={mdJumpTarget?.line ?? null}
                  scrollNonce={mdJumpTarget?.nonce}
                  flashLines={markdownFlashLines}
                />
              </div>
            ),
            docx: (
              <DocxPreview
                jobId={jobId}
                available={job.docx_available}
                documentVersion={job.document_version}
              />
            ),
          }}
          rightRail={
            <ContextInspectorRail
              jobId={jobId}
              aiStatus={state.aiStatus}
              onOpenValidation={() => setActiveSpecialView("validation")}
            />
          }
          specialView={renderSpecialView()}
          bottomPanel={<BottomPanel job={job} issues={state.validationIssues} jobId={jobId} />}
        />
      )}
    </div>
  );
}
