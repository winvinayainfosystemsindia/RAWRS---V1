"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { api, type BlockItem, type BoundingBox } from "@/lib/api";
import { usePdfViewport } from "@/lib/store/PdfViewportContext";
import type { SelectableObjectType } from "@/lib/store/SelectionContext";
import { IconMarkers } from "@/components/icons";
import { orderMarkerRows } from "@/lib/orderMarkers";

pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

const ZOOM_STEP = 0.1;
// Space between a reading-order marker and the text block it numbers.
const ORDER_MARKER_GAP_PX = 3;
const ORDER_MARKERS_KEY = "rawrs-pdf-order-markers";
// Pages either side of the one in view that are actually rendered.
const RENDER_WINDOW = 2;
// US Letter in points, until the first page reports its real size.
const DEFAULT_PAGE_SIZE = { width: 612, height: 792 };
// How far down the viewport a page's top must pass to become "the" page.
const CURRENT_PAGE_LINE = 0.35;

interface PageSize {
  width: number;
  height: number;
}

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
  const [showOrderMarkers, setShowOrderMarkers] = useState(
    () => typeof window !== "undefined" && window.localStorage.getItem(ORDER_MARKERS_KEY) === "true"
  );
  const highlightRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [pageSize, setPageSize] = useState<PageSize | null>(null);
  const [fitWidth, setFitWidth] = useState(0);
  // The page the reader scrolled to - so the page-change effect below does
  // not scroll back to a page the reader is already looking at.
  const scrolledToPage = useRef<number | null>(null);

  // zoom 1 = the page fills the pane's width; the buttons scale from there.
  const scale = ((fitWidth || DEFAULT_PAGE_SIZE.width) / (pageSize ?? DEFAULT_PAGE_SIZE).width) * zoom;

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const measure = () => {
      const cs = getComputedStyle(el);
      setFitWidth(el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const line = el.getBoundingClientRect().top + el.clientHeight * CURRENT_PAGE_LINE;
    let current = 1;
    for (const page of el.querySelectorAll<HTMLElement>("[data-page]")) {
      if (page.getBoundingClientRect().top > line) break;
      current = Number(page.dataset.page);
    }
    if (current !== pageNumber) {
      scrolledToPage.current = current;
      setPageNumber(current);
    }
  }, [pageNumber, setPageNumber]);

  // A page change from anywhere but scrolling (the arrows, a jump to an
  // object) brings that page into view.
  useEffect(() => {
    if (scrolledToPage.current === pageNumber) return;
    const page = scrollRef.current?.querySelector(`[data-page="${pageNumber}"]`);
    if (!page) return; // not laid out yet - retried when numPages arrives
    scrolledToPage.current = pageNumber;
    page.scrollIntoView({ block: "start" });
  }, [pageNumber, numPages]);

  function toggleOrderMarkers() {
    setShowOrderMarkers((shown) => {
      window.localStorage.setItem(ORDER_MARKERS_KEY, String(!shown));
      return !shown;
    });
  }

  const highlight = jumpTarget?.bbox ?? null;

  // Same scroll-into-view intent as MarkdownEditor's jump-to-line effect;
  // keyed on jumpTarget's nonce (bumped on every jumpToObject call, even a
  // re-jump to the same target) so it fires every time, not just on change.
  useEffect(() => {
    highlightRef.current?.scrollIntoView({ block: "center", inline: "center" });
  }, [jumpTarget?.nonce]);

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
          <button
            type="button"
            onClick={() => setZoom(1)}
            title="Fit page to width"
            className="w-12 rounded text-center font-mono text-xs text-text-secondary hover:text-text-primary"
          >
            {Math.round(scale * 100)}%
          </button>
          <button
            type="button"
            onClick={() => setZoom((z) => z + ZOOM_STEP)}
            className="rounded border border-border px-2 py-0.5 text-sm text-text-secondary hover:text-text-primary hover:border-border-strong"
            aria-label="Zoom in"
          >
            +
          </button>
        </div>
        {!!readingOrderBlocks?.length && (
          <button
            type="button"
            onClick={toggleOrderMarkers}
            aria-pressed={showOrderMarkers}
            title="Number each text block in reading order (drawn in the margin)"
            className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs transition-colors ${
              showOrderMarkers
                ? "border-accent bg-accent/15 text-text-primary"
                : "border-border text-text-secondary hover:border-border-strong hover:text-text-primary"
            }`}
          >
            <IconMarkers className="h-3.5 w-3.5" />
            Reading order
          </button>
        )}
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

      {/* Page canvas - every page stacked in one scroll, like the Markdown
          and DOCX panes. Only pages near the one in view are rendered; the
          rest are placeholders of the same size, so a long document stays
          light and the scrollbar is right from the start. */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className={`flex-1 overflow-auto bg-surface-canvas py-4 pr-6 ${showOrderMarkers ? "pl-16" : "pl-6"}`}
        data-pdf-mode={mode}
      >
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
            className="flex flex-col items-center gap-4"
          >
            {Array.from({ length: numPages ?? 0 }, (_, index) => index + 1).map((n) => (
              <PdfPage
                key={n}
                pageNumber={n}
                scale={scale}
                placeholder={pageSize}
                isRendered={Math.abs(n - pageNumber) <= RENDER_WINDOW}
                onFirstLoad={n === 1 ? setPageSize : undefined}
              >
                {overlays
                  ?.filter((o) => o.pageNumber === n)
                  .map((o) => {
                    const isSelected = o.objectId === selectedOverlayId;
                    return (
                      <button
                        key={`${o.objectType}-${o.objectId}`}
                        type="button"
                        title={o.label ?? o.objectType}
                        onClick={() => onOverlayClick?.(o)}
                        aria-label={`Select ${o.label ?? o.objectType}`}
                        className={`absolute cursor-pointer rounded-sm transition-all ${
                          isSelected
                            ? "border-2 border-accent bg-accent/15"
                            : "border-[1.5px] border-transparent hover:border-accent hover:bg-accent/10"
                        }`}
                        style={boxStyle(o.bbox, scale)}
                      />
                    );
                  })}

                {/* Jump-to highlight — rendered on top, pointer-events-none */}
                {highlight && jumpTarget?.pageNumber === n && (
                  <div
                    key={jumpTarget.nonce}
                    ref={highlightRef}
                    className="pdf-highlight-enter pointer-events-none absolute rounded-sm border-2 border-amber-500/70 bg-amber-400/12 shadow-[0_0_8px_2px_rgba(245,158,11,0.15)]"
                    style={boxStyle(highlight, scale)}
                  />
                )}

                {/* Reading-order markers - optional, off by default. They sit in
                    the margin just left of each block, small and translucent, so
                    they never cover a word; the numbered list with reorder
                    controls lives in ReadingOrderPanel. */}
                {showOrderMarkers &&
                  orderMarkerRows(orderBlocksOn(readingOrderBlocks, n), scale).map((row) => (
                    <div
                      key={row.top}
                      aria-hidden="true"
                      className="pointer-events-none absolute flex h-3 items-center justify-end rounded-sm bg-accent/70 px-1 font-mono text-[8px] font-semibold leading-none text-accent-contrast"
                      style={{ right: `calc(100% + ${ORDER_MARKER_GAP_PX}px)`, top: row.top }}
                    >
                      {row.label}
                    </div>
                  ))}
              </PdfPage>
            ))}
          </Document>
        )}
      </div>
    </div>
  );
}

function boxStyle(box: BoundingBox, scale: number) {
  return {
    left: box.x0 * scale,
    top: box.y0 * scale,
    width: (box.x1 - box.x0) * scale,
    height: (box.y1 - box.y0) * scale,
  };
}

function orderBlocksOn(blocks: BlockItem[] | undefined, page: number): BlockItem[] {
  return [...(blocks?.filter((b) => b.page_number === page) ?? [])].sort(
    (a, b) => (a.corrected_order ?? a.block_order) - (b.corrected_order ?? b.block_order)
  );
}

/** One page slot: the rendered page when near the viewport, otherwise an
 *  empty box the size the page will be. */
function PdfPage({
  pageNumber,
  scale,
  placeholder,
  isRendered,
  onFirstLoad,
  children,
}: {
  pageNumber: number;
  scale: number;
  placeholder: PageSize | null;
  isRendered: boolean;
  onFirstLoad?: (size: PageSize) => void;
  children: React.ReactNode;
}) {
  const size = placeholder ?? DEFAULT_PAGE_SIZE;
  return (
    <div
      data-page={pageNumber}
      className="relative shrink-0 bg-white shadow-md"
      style={isRendered ? undefined : { width: size.width * scale, height: size.height * scale }}
    >
      {isRendered && (
        <Page
          pageNumber={pageNumber}
          scale={scale}
          loading={<div style={{ width: size.width * scale, height: size.height * scale }} />}
          onLoadSuccess={(page) => onFirstLoad?.({ width: page.originalWidth, height: page.originalHeight })}
        />
      )}
      {children}
    </div>
  );
}
