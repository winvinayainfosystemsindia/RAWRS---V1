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
  selectEquations,
  selectCorrections,
  selectPageLabels,
  selectReadingOrder,
  listKey,
  calloutKey,
} from "@/lib/store/DocumentDataContext";
import { useMarkdownViewport } from "@/lib/store/MarkdownViewportContext";
import { useSelection } from "@/lib/store/SelectionContext";
import { useReviewQueue, ANY_OBJECT_TYPE } from "@/lib/store/ReviewQueueContext";
import type { PdfObjectOverlay } from "@/components/PdfViewer";
import { usePdfViewport } from "@/lib/store/PdfViewportContext";
import { useElapsedSeconds } from "@/lib/store/useElapsedSeconds";
import { PipelineView } from "@/components/PipelineView";
import { ResultsDashboard } from "@/components/ResultsDashboard";
import { OutputWorkspace, DownloadControls } from "@/components/OutputWorkspace";
import { MarkdownEditPane } from "@/components/MarkdownEditPane";
import { DocxPreview } from "@/components/DocxPreview";
import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { readinessState } from "@/lib/readinessState";
import { isPending } from "@/lib/correctionFilters";
import { ReviewRail } from "@/components/workspace/ReviewRail";
import { SemanticNavTree, type NavSection } from "@/components/workspace/SemanticNavTree";
import { ActivityBar } from "@/components/workspace/ActivityBar";
import { BottomPanel } from "@/components/workspace/BottomPanel";
import { ValidationIssueTable } from "@/components/ValidationIssueTable";
import { ImageGrid } from "@/components/ImageGrid";
import { TableGrid } from "@/components/TableGrid";
import { HeadingGrid } from "@/components/HeadingGrid";
import { FootnoteTable } from "@/components/FootnoteTable";
import { ListPanel } from "@/components/ListPanel";
import { CalloutPanel } from "@/components/CalloutPanel";
import { EquationsPanel } from "@/components/EquationsPanel";
import { MetadataPanel } from "@/components/MetadataPanel";
import { OcrPageTable } from "@/components/OcrPageTable";
import { ReadingOrderPanel } from "@/components/ReadingOrderPanel";
import { PageLabelManagerPanel } from "@/components/PageLabelManagerPanel";
import { CorrectionsPanel } from "@/components/CorrectionsPanel";
import { ChecklistAuditPanel } from "@/components/ChecklistAuditPanel";
import { ReadinessPanel } from "@/components/ReadinessPanel";

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
  const { pageNumber, jumpToObject } = usePdfViewport();
  const { focusQueue } = useReviewQueue();
  const [activeSpecialView, setActiveSpecialView] = useState("");
  // Bumped by WorkspaceShell's toolbar Search button; SemanticNavTree
  // watches this to switch itself into Search mode (see focusSignal).
  const [searchNonce, setSearchNonce] = useState(0);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  // The Markdown editor's unsaved draft, which the DOCX pane previews live;
  // docxRefresh re-renders that pane after a save or discard.
  const [markdownDraft, setMarkdownDraft] = useState<string | null>(null);
  const [docxRefresh, setDocxRefresh] = useState(0);
  const shortcutsDialogRef = useRef<HTMLDialogElement>(null);
  const elapsed = useElapsedSeconds(state.job);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "?") setShortcutsOpen((v) => !v);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Drive the native <dialog> from React state: showModal() (not the open
  // attribute) is what engages the top-layer focus trap + Escape handling.
  useEffect(() => {
    const d = shortcutsDialogRef.current;
    if (!d) return;
    if (shortcutsOpen && !d.open) d.showModal();
    else if (!shortcutsOpen && d.open) d.close();
  }, [shortcutsOpen]);

  // Diff against the markdown from before this render's update, so a live
  // document_version regen can flash exactly what changed (React's
  // "adjust state while rendering" pattern; see computeChangedLines above).
  const [prevMarkdown, setPrevMarkdown] = useState(state.markdown);
  const [markdownFlashLines, setMarkdownFlashLines] = useState<number[]>([]);
  if (prevMarkdown !== state.markdown) {
    setPrevMarkdown(state.markdown);
    setMarkdownFlashLines(computeChangedLines(prevMarkdown, state.markdown));
  }

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
      <main id="main-content" className="flex h-dvh flex-col items-center justify-center gap-4 p-6">
        <p className="text-sm text-danger" role="alert">
          No document found for this ID. It may have been processed before the API was last restarted.
        </p>
        <Link href="/" className="text-sm font-medium text-accent hover:underline">
          &larr; Upload a document
        </Link>
      </main>
    );
  }

  if (!job) {
    return (
      <main id="main-content" className="flex h-dvh items-center justify-center">
        <p role="status" className="text-sm text-text-secondary">Loading document…</p>
      </main>
    );
  }

  const isActive = job.status === "queued" || job.status === "processing";
  const isDone = job.status === "complete" || job.status === "failed";

  const tables = selectTables(state);
  const headings = selectHeadings(state);
  const images = selectImages(state);
  const footnotes = selectFootnotes(state);
  const lists = selectLists(state);
  const callouts = selectCallouts(state);
  const equations = selectEquations(state);
  const corrections = selectCorrections(state);
  const pageLabels = selectPageLabels(state);
  const readingOrder = selectReadingOrder(state);

  const pendingCorrections = corrections.filter(isPending).length;
  const flaggedEquations = equations.filter((e) => e.status === "flagged").length;
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

  // The correction object_type each Accessibility-Center special view maps to,
  // for those views whose findings live in the Review Queue. Views not listed
  // here (metadata, reading-order, page-labels, ocr) aren't correction-queue
  // surfaces, so their category cards still open their dedicated workspace.
  const QUEUE_OBJECT_TYPE: Record<string, string> = {
    images: "image",
    tables: "table",
    headings: "heading",
    footnotes: "footnote",
    lists: "list",
    callouts: "callout",
  };

  // Category drill-down (P1-6): if the category's findings are in the Review
  // Queue and there actually are some, filter the queue to that object type
  // and bring it forward — instead of throwing the reviewer into a different
  // full-screen view. Otherwise fall back to the dedicated workspace.
  function handleSelectCategory(specialViewId: string) {
    const objectType = QUEUE_OBJECT_TYPE[specialViewId];
    if (objectType && corrections.some((c) => c.object_type === objectType)) {
      focusQueue(objectType);
    } else {
      setActiveSpecialView(specialViewId);
    }
  }

  const specialViews: NavSection[] = [
    { id: "overview", label: "Overview" },
    { id: "validation", label: "Validation", count: state.validationIssues.length },
    { id: "images", label: "Images", count: images.length },
    { id: "tables", label: "Tables", count: tables.length },
    { id: "headings", label: "Headings", count: headings.length },
    { id: "footnotes", label: "Footnotes", count: footnotes.length },
    { id: "lists", label: "Lists", count: lists.length },
    { id: "callouts", label: "Callouts", count: callouts.length },
    { id: "equations", label: "Equations", count: equations.length, urgentCount: flaggedEquations },
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
    { id: "export-center", label: "Export Center" },
  ];

  function renderSpecialView() {
    switch (activeSpecialView) {
      case "overview":
        return (
          <div className="mx-auto max-w-5xl space-y-6">
            <ResultsDashboard
              job={job!}
              issues={state.validationIssues}
              images={images}
              footnotes={footnotes}
              pages={state.pages}
              tables={tables}
            />
            <OutputWorkspace job={job!} generatedMarkdown={state.markdown} />
            <details className="rounded-lg border border-border">
              <summary className="cursor-pointer select-none px-4 py-2 text-xs font-semibold uppercase tracking-wider text-text-secondary hover:text-text-primary">
                Processing Log
              </summary>
              <div className="border-t border-border p-4">
                <PipelineView status={job!.status} elapsed={elapsed} />
              </div>
            </details>
          </div>
        );
      case "validation":
        return (
          <ValidationIssueTable
            issues={state.validationIssues}
            jobId={jobId}
            onIssueUpdated={(issue) => dispatch({ type: "UPDATE_VALIDATION_ISSUE", issue })}
            onIssueSelect={(issue) => {
              select("validation-issue", issue.issue_id);
              if (issue.page_number !== null) jumpToObject(issue.page_number, null);
            }}
            // Readiness convergence (Commit 1): the banner reads the
            // Accessibility Intelligence Engine (the same source as the
            // header badge and ReadinessPanel), never the frozen
            // ValidationIssue snapshot. compute_readiness/state.readiness is
            // retired in a later commit; mapped to ReadinessReport's shape
            // here (the banner only reads ready + overall_score).
            readiness={
              state.accessibilityReport
                ? {
                    ready: state.accessibilityReport.export_ready,
                    overall_score: state.accessibilityReport.overall_score,
                    categories: [],
                  }
                : null
            }
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
      case "equations":
        return <EquationsPanel equations={equations} jobId={jobId} />;
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
      case "export-center":
        return (
          <div className="space-y-6">
            <ReadinessPanel
              accessibilityReport={state.accessibilityReport}
              onSelectCategory={handleSelectCategory}
              onFixNext={() => {
                // "Fix Next" opens the prioritized Review Queue itself (its
                // default priority sort already surfaces the highest-value item)
                // rather than routing into a category view. Clear the object-type
                // filter so nothing is hidden. (P1-6 — replaces the old
                // hardcoded catMap that dumped unknown categories into Validation.)
                focusQueue(ANY_OBJECT_TYPE);
              }}
            />
            <ChecklistAuditPanel jobId={jobId} />
            <section aria-labelledby="export-center-downloads-heading" className="rounded-xl border border-border bg-surface-panel p-5">
              <h2
                id="export-center-downloads-heading"
                className="text-xs font-semibold uppercase tracking-wider text-text-secondary"
              >
                Downloads
              </h2>
              <DownloadControls job={job!} />
            </section>
          </div>
        );
      default:
        return null;
    }
  }

  const banners = (
    <>
      {job.status === "failed" && (
        <div role="alert" className="shrink-0 border-b border-danger/30 bg-danger/10 px-4 py-2">
          <p className="text-sm font-semibold text-danger">
            Processing failed{job.failed_stage ? ` at stage "${job.failed_stage}"` : ""}.
            {job.error_message && <span className="ml-2 font-normal text-danger/90">{job.error_message}</span>}
          </p>
        </div>
      )}
      {/* Partial-load banner (P0-4) - an errored result slice must never be
          silently rendered as an empty one. */}
      {state.loadErrors.length > 0 && (
        <div
          role="alert"
          className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-warning/40 bg-warning/10 px-4 py-2"
        >
          <p className="text-sm text-warning">
            Some document data could not be loaded ({state.loadErrors.join(", ")}). What you see may be
            incomplete - a section that failed to load is not the same as one with no issues.
          </p>
          <button
            type="button"
            onClick={() => dispatch({ type: "REQUEST_RELOAD" })}
            className="shrink-0 rounded border border-warning/50 px-3 py-1 text-sm font-medium text-warning hover:bg-warning/15"
          >
            Retry
          </button>
        </div>
      )}
    </>
  );

  return (
    <main id="main-content" className="flex h-dvh flex-col overflow-hidden">
      {/* The page's one H1 (screen-reader heading navigation); visually the
          filename is in the workspace title bar. */}
      <h1 className="sr-only">{job.filename}</h1>
      {banners}

      {isActive && (
        <div className="flex min-h-0 flex-1 flex-col">
          <header className="flex h-11 shrink-0 items-center gap-3 border-b border-border bg-surface-panel px-3">
            <Link href="/" className="text-sm font-bold tracking-wide text-text-primary">RAWRS</Link>
            <span className="h-4 w-px bg-border" aria-hidden="true" />
            <span className="truncate text-sm font-medium text-text-primary">{job.filename}</span>
          </header>
          <div className="flex min-h-0 flex-1 items-center justify-center overflow-y-auto p-6">
            <div role="status" className="w-full max-w-md space-y-4 rounded-lg border border-border bg-surface-panel p-6">
              <p className="text-sm font-medium text-text-primary">
                {job.status === "queued"
                  ? "Queued - waiting to start…"
                  : "Remediation is running. This page opens the workspace automatically when it finishes."}
              </p>
              <p className="text-xs text-text-secondary">
                Scanned PDFs need OCR (about 20 seconds a page) and every real figure gets a description
                from the local vision model (about 2-3 minutes each).
              </p>
              <PipelineView status={job.status} elapsed={elapsed} />
            </div>
          </div>
        </div>
      )}

      {isDone && (
        <div className="min-h-0 flex-1">
          <WorkspaceShell
            filename={job.filename}
            status={job.status}
            documentVersion={job.document_version}
            elapsedSeconds={elapsed}
            durationSeconds={job.duration_seconds}
            mode={activeSpecialView ? "special" : "document"}
            currentPage={pageNumber}
            readiness={readinessState(state.accessibilityReport, state.loadErrors.includes("accessibility report"))}
            pendingCount={pendingCorrections}
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
            activityBar={
              <ActivityBar
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
                <MarkdownEditPane
                  jobId={jobId}
                  content={state.markdown}
                  documentVersion={job.document_version}
                  scrollToLine={mdJumpTarget?.line ?? null}
                  scrollNonce={mdJumpTarget?.nonce}
                  flashLines={markdownFlashLines}
                  onDraftChange={setMarkdownDraft}
                  onContentReplaced={(content) => {
                    dispatch({ type: "UPDATE_MARKDOWN", markdown: content });
                    setDocxRefresh((n) => n + 1);
                  }}
                />
              ),
              docx: (
                <DocxPreview
                  jobId={jobId}
                  available={job.docx_available}
                  documentVersion={job.document_version}
                  markdown={markdownDraft}
                  refreshKey={docxRefresh}
                />
              ),
            }}
            rightRail={
              <ReviewRail
                jobId={jobId}
                aiStatus={state.aiStatus}
                pendingCount={pendingCorrections}
                onOpenValidation={() => setActiveSpecialView("validation")}
              />
            }
            specialView={renderSpecialView()}
            bottomPanel={<BottomPanel job={job} issues={state.validationIssues} />}
          />
        </div>
      )}

      {/* Native <dialog> (P2-11): showModal() gives a focus trap, Escape-to-
          close, aria-modal, and focus restoration to the trigger for free —
          all of which the old hand-rolled overlay lacked. onClose keeps React
          state in sync when the browser closes it (Escape or backdrop). */}
      <dialog
        ref={shortcutsDialogRef}
        onClose={() => setShortcutsOpen(false)}
        onClick={(e) => {
          if (e.target === shortcutsDialogRef.current) setShortcutsOpen(false);
        }}
        className="m-auto w-full max-w-md rounded-lg border border-border bg-surface-panel p-5 text-text-primary shadow-xl backdrop:bg-black/40"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-text-primary">Keyboard Shortcuts</h2>
          <button
            type="button"
            onClick={() => setShortcutsOpen(false)}
            className="text-text-secondary hover:text-text-primary"
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          {([
            ["n / →", "Next issue"],
            ["p / ←", "Previous issue"],
            ["a", "Accept current"],
            ["r", "Reject current"],
            ["i", "Ignore current"],
            ["u", "Undo last action"],
            ["e", "Open inspector"],
            ["j", "Jump to PDF"],
            ["/", "Focus search"],
            ["?", "Toggle this overlay"],
          ] as [string, string][]).map(([key, desc]) => (
            <div key={key} className="contents">
              <dt><kbd className="rounded border border-border bg-surface-elevated px-1.5 py-0.5 font-mono text-xs text-text-primary">{key}</kbd></dt>
              <dd className="text-text-secondary">{desc}</dd>
            </div>
          ))}
        </dl>
      </dialog>
    </main>
  );
}
