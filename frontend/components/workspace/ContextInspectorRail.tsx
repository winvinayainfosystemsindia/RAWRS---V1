"use client";

import type { AiStatus } from "@/lib/api";
import { useDocumentData, useDocumentDispatch, footnoteKey, listKey, calloutKey } from "@/lib/store/DocumentDataContext";
import { useSelection } from "@/lib/store/SelectionContext";
import { usePdfViewport } from "@/lib/store/PdfViewportContext";
import { ValidationIssueTable } from "@/components/ValidationIssueTable";
import { HeadingDetailPanel } from "@/components/HeadingDetailPanel";
import { TableDetailPanel } from "@/components/TableDetailPanel";
import { ImageDetailPanel } from "@/components/ImageDetailPanel";
import { FootnoteDetailPanel } from "@/components/FootnoteTable";
import { ListDetailPanel } from "@/components/ListPanel";
import { CalloutDetailPanel } from "@/components/CalloutPanel";
import { CorrectionHistoryList } from "@/components/CorrectionHistoryList";

// The right rail, always the same across every nav mode and every object
// type — this is the "Context Inspector" the workflow redesign centers on.
// Whatever is selected (nav tree click, PDF overlay click, correction card,
// search result) renders here via the single normalized store, replacing
// the old nav-category-driven detail pane.
export function ContextInspectorRail({ jobId, aiStatus }: { jobId: string; aiStatus: AiStatus | null }) {
  const { selection, clearSelection } = useSelection();
  const state = useDocumentData();
  const dispatch = useDocumentDispatch();
  const { jumpToObject } = usePdfViewport();

  if (!selection) {
    return (
      <div className="p-4">
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-text-secondary">
          Validation Issues
        </p>
        <ValidationIssueTable
          issues={state.validationIssues}
          onJump={(page) => jumpToObject(page, null)}
          jobId={jobId}
          onIssueUpdated={(issue) => dispatch({ type: "UPDATE_VALIDATION_ISSUE", issue })}
        />
      </div>
    );
  }

  const { objectType, objectId } = selection;

  switch (objectType) {
    case "heading": {
      const heading = state.headingsById[objectId as number];
      if (!heading) break;
      return (
        <div className="p-4">
          <HeadingDetailPanel
            heading={heading}
            jobId={jobId}
            onUpdated={(updated) => dispatch({ type: "UPDATE_HEADING", heading: updated })}
          />
        </div>
      );
    }
    case "table": {
      const table = state.tablesById[objectId as string];
      if (!table) break;
      return (
        <div className="p-4">
          <TableDetailPanel
            table={table}
            jobId={jobId}
            aiStatus={aiStatus}
            onClose={clearSelection}
            onActionComplete={(updated) => dispatch({ type: "UPDATE_TABLE", table: updated })}
            onDelete={(tableId) => dispatch({ type: "REMOVE_TABLE", tableId })}
          />
        </div>
      );
    }
    case "image": {
      const image = state.imagesById[objectId as string];
      if (!image) break;
      return (
        <div className="p-4">
          <ImageDetailPanel
            image={image}
            jobId={jobId}
            aiStatus={aiStatus}
            onClose={clearSelection}
            onActionComplete={(updated) => dispatch({ type: "UPDATE_IMAGE", image: updated })}
          />
        </div>
      );
    }
    case "footnote": {
      const note = Object.values(state.footnotesById).find((n) => footnoteKey(n) === objectId);
      if (!note) break;
      return (
        <div className="p-4">
          <FootnoteDetailPanel
            note={note}
            jobId={jobId}
            onUpdated={(updated) => dispatch({ type: "UPDATE_FOOTNOTE", footnote: updated })}
          />
        </div>
      );
    }
    case "list": {
      const list = Object.values(state.listsById).find((l) => listKey(l) === objectId);
      if (!list) break;
      return (
        <div className="p-4">
          <ListDetailPanel list={list} jobId={jobId} />
        </div>
      );
    }
    case "callout": {
      const callout = Object.values(state.calloutsById).find((c) => calloutKey(c) === objectId);
      if (!callout) break;
      return (
        <div className="p-4">
          <CalloutDetailPanel callout={callout} jobId={jobId} />
        </div>
      );
    }
    case "correction": {
      const correction = state.correctionsById[objectId as string];
      if (!correction) break;
      return (
        <div className="p-4">
          <CorrectionHistoryList
            corrections={[correction]}
            jobId={jobId}
            onUpdated={(updated) => dispatch({ type: "UPDATE_CORRECTION", correction: updated })}
          />
        </div>
      );
    }
    default:
      break;
  }

  return (
    <div className="p-4">
      <p className="text-sm text-text-secondary">
        This item has its own dedicated panel — open it from the nav tree above.
      </p>
    </div>
  );
}
