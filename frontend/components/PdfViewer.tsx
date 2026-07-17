"use client";

import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { api, type BlockItem, type BoundingBox } from "@/lib/api";
import { usePdfViewport } from "@/lib/store/PdfViewportContext";
import type { SelectableObjectType } from "@/lib/store/SelectionContext";

pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

const ZOOM_STEP = 0.1;

export type PdfViewerMode = "view" | "region-select";

export interface PdfObjectOverlay {
  objectType: SelectableObjectType;
  objectId: string | number;
  pageNumber: number;
  bbox: BoundingBox;
  sourceLine?: number | null;
  label?: string;
}

interface PdfViewerProps {
  jobId: string;
  mode?: PdfViewerMode;
  overlays?: PdfObjectOverlay[];
  selectedOverlayId?: string | number | null;
  onOverlayClick?: (overlay: PdfObjectOverlay) => void;
  onRegionSelect?: (bbox: BoundingBox, pageNumber: number) => void;
  // Reading-order sequence numbers, drawn as small badges at each block's
  // top-left corner — separate from `overlays` (which highlight a single
  // selectable object's full bbox) since a page can have many blocks and
  // drawing a full box per block would bury the page in outlines.
  readingOrderBlocks?: BlockItem[];
}

export function PdfViewer({
  jobId,
  mode = "view",
  overlays,
  selectedOverlayId,
  onOverlayClick,
  readingOrderBlocks,
}: PdfViewerProps) {
  const { pageNumber, zoom, jumpTarget, setPageNumber, setZoom } = usePdfViewport();
  const [numPages, setNumPages] = useState<number | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const highlightRef = useRef<HTMLDivElement>(null);

  const highlight =
    jumpTarget && jumpTarget.pageNumber === pageNumber && jumpTarget.bbox ? jumpTarget.bbox : null;

  // Same scroll-into-view intent as MarkdownEditor's jump-to-line effect;
  // keyed on jumpTarget's nonce (bumped on every jumpToObject call, even a
  // re-jump to the same target) so it fires every time, not just on change.
  useEffect(() => {
    highlightRef.current?.scrollIntoView({ block: "center", inline: "center" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jumpTarget?.nonce]);

  const pageOverlays = overlays?.filter((o) => o.pageNumber === pageNumber) ?? [];
  const pageOrderBlocks = [...(readingOrderBlocks?.filter((b) => b.page_number === pageNumber) ?? [])].sort(
    (a, b) => (a.corrected_order ?? a.block_order) - (b.corrected_order ?? b.block_order)
  );

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border bg-surface-panel px-2 py-1.5">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setZoom((z) => z - ZOOM_STEP)}
            className="rounded border border-border px-2 py-0.5 text-sm text-text-secondary hover:text-text-primary hover:border-border-strong"
            aria-label="Zoom out"
          >
            −
          </button>
          <span className="w-12 text-center font-mono text-xs text-text-secondary">
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            onClick={() => setZoom((z) => z + ZOOM_STEP)}
            className="rounded border border-border px-2 py-0.5 text-sm text-text-secondary hover:text-text-primary hover:border-border-strong"
            aria-label="Zoom in"
          >
            +
          </button>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setPageNumber(Math.max(1, pageNumber - 1))}
            disabled={pageNumber <= 1}
            className="rounded border border-border px-2 py-0.5 text-sm text-text-secondary hover:text-text-primary hover:border-border-strong disabled:opacity-40"
            aria-label="Previous page"
          >
            ◄
          </button>
          <span className="font-mono text-xs text-text-secondary">
            {pageNumber}/{numPages ?? "…"}
          </span>
          <button
            type="button"
            onClick={() => setPageNumber(Math.min(numPages ?? pageNumber, pageNumber + 1))}
            disabled={numPages !== null && pageNumber >= numPages}
            className="rounded border border-border px-2 py-0.5 text-sm text-text-secondary hover:text-text-primary hover:border-border-strong disabled:opacity-40"
            aria-label="Next page"
          >
            ►
          </button>
        </div>
      </div>

      {/* Page canvas */}
      <div className="flex-1 overflow-auto bg-surface-canvas p-4" data-pdf-mode={mode}>
        {loadError ? (
          <p className="p-4 text-sm text-danger" role="alert">
            {loadError}
          </p>
        ) : (
          <Document
            file={api.sourcePdfUrl(jobId)}
            onLoadSuccess={({ numPages: n }) => setNumPages(n)}
            onLoadError={(err) => {
              // Phase R-2 M7: react-pdf/pdfjs errors are developer-facing
              // (raw status text, internal API URLs) — keep the full detail
              // in the console for diagnostics, show reviewers a plain,
              // actionable message instead.
              console.error("PDF load failed:", err);
              setLoadError("The source PDF isn't available right now. Try re-uploading the document, or continue with the Markdown/DOCX view.");
            }}
            loading={<p className="text-sm text-text-secondary">Loading PDF…</p>}
          >
            <div className="relative inline-block">
              <Page pageNumber={pageNumber} scale={zoom} />

              {/* Clickable semantic overlays — one per document object on this page */}
              {pageOverlays.map((o) => {
                const isSelected = o.objectId === selectedOverlayId;
                return (
                  <button
                    key={`${o.objectType}-${o.objectId}`}
                    type="button"
                    title={o.label ?? o.objectType}
                    onClick={() => onOverlayClick?.(o)}
                    aria-label={`Select ${o.label ?? o.objectType}`}
                    className="absolute cursor-pointer rounded-sm transition-all"
                    style={{
                      left: o.bbox.x0 * zoom,
                      top: o.bbox.y0 * zoom,
                      width: (o.bbox.x1 - o.bbox.x0) * zoom,
                      height: (o.bbox.y1 - o.bbox.y0) * zoom,
                      border: isSelected
                        ? "2px solid var(--accent)"
                        : "1.5px solid transparent",
                      backgroundColor: isSelected
                        ? "color-mix(in srgb, var(--accent) 15%, transparent)"
                        : "transparent",
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) {
                        (e.currentTarget as HTMLElement).style.borderColor = "var(--accent)";
                        (e.currentTarget as HTMLElement).style.backgroundColor =
                          "color-mix(in srgb, var(--accent) 10%, transparent)";
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) {
                        (e.currentTarget as HTMLElement).style.borderColor = "transparent";
                        (e.currentTarget as HTMLElement).style.backgroundColor = "transparent";
                      }
                    }}
                  />
                );
              })}

              {/* Jump-to highlight — rendered on top, pointer-events-none */}
              {highlight && (
                <div
                  ref={highlightRef}
                  className="pointer-events-none absolute border-2 border-accent bg-accent/20"
                  style={{
                    left: highlight.x0 * zoom,
                    top: highlight.y0 * zoom,
                    width: (highlight.x1 - highlight.x0) * zoom,
                    height: (highlight.y1 - highlight.y0) * zoom,
                  }}
                />
              )}

              {/* Reading order sequence badges — decorative, pointer-events-none;
                  the numbered list with reorder controls lives in ReadingOrderPanel. */}
              {pageOrderBlocks.map((block, idx) => (
                <div
                  key={block.block_order}
                  title={block.text.slice(0, 140)}
                  className="pointer-events-none absolute flex h-5 w-5 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-accent bg-accent font-mono text-[10px] font-semibold text-accent-contrast shadow"
                  style={{
                    left: block.bbox_x0 * zoom,
                    top: block.bbox_y0 * zoom,
                  }}
                >
                  {idx + 1}
                </div>
              ))}
            </div>
          </Document>
        )}
      </div>
    </div>
  );
}
