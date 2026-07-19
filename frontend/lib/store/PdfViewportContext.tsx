"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { BoundingBox } from "@/lib/api";

interface JumpTarget {
  pageNumber: number;
  bbox: BoundingBox | null;
  // Bumped on every jump so effects can fire even when re-jumping to the same page/bbox.
  nonce: number;
}

interface PdfViewportContextValue {
  pageNumber: number;
  zoom: number;
  jumpTarget: JumpTarget | null;
  // Every page the reviewer's viewport has landed on this session (manual
  // paging or a jump). This is the honest basis for "review coverage" =
  // reviewer *attention*, distinct from issue resolution (P2-10): a page can
  // be visited with nothing to fix, or have auto-applied fixes yet never be
  // looked at. Session-scoped; not persisted.
  visitedPages: ReadonlySet<number>;
  setPageNumber: (page: number) => void;
  // Accepts a plain value or a functional updater, same overload shape as
  // React's own setState setter — needed because PdfViewer's zoom
  // buttons compute the next value from the current one
  // (`zoom + ZOOM_STEP`); a plain-value-only setter reads `zoom` from
  // each click handler's render closure, so back-to-back clicks that
  // land before React commits the first update all read the same stale
  // value and only one increment survives (reproduced live: 5 rapid
  // clicks advanced 100% -> 110%, not 150%).
  setZoom: (zoom: number | ((prev: number) => number)) => void;
  jumpToObject: (pageNumber: number, bbox: BoundingBox | null) => void;
}

const PdfViewportContext = createContext<PdfViewportContextValue | null>(null);

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3;

export function PdfViewportProvider({ children }: { children: ReactNode }) {
  const [pageNumber, setPageNumberState] = useState(1);
  const [zoom, setZoomState] = useState(1);
  const [jumpTarget, setJumpTarget] = useState<JumpTarget | null>(null);
  // Seeded with page 1 — that's what the viewer shows on mount.
  const [visitedPages, setVisitedPages] = useState<ReadonlySet<number>>(() => new Set([1]));

  const setPageNumber = useCallback((page: number) => {
    setPageNumberState(page);
    setVisitedPages((prev) => (prev.has(page) ? prev : new Set(prev).add(page)));
  }, []);

  // Stable across renders (empty deps — each only calls a setState setter,
  // which React itself guarantees is stable) so an effect that calls one
  // of these as part of its own dependency array doesn't re-fire just
  // because *this* provider re-rendered for an unrelated state change.
  // jumpToObject's nonce-bump is what should legitimately change on every
  // logical call; the function *reference* itself must not, or any
  // consumer syncing "whichever object is current" into an effect loops
  // forever (caught via live browser verification of M-4.2).
  const setZoom = useCallback((next: number | ((prev: number) => number)) => {
    setZoomState((prev) => {
      const raw = typeof next === "function" ? next(prev) : next;
      return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, raw));
    });
  }, []);
  const jumpToObject = useCallback((page: number, bbox: BoundingBox | null) => {
    setPageNumber(page);
    setJumpTarget((prev) => ({ pageNumber: page, bbox, nonce: (prev?.nonce ?? 0) + 1 }));
  }, [setPageNumber]);

  const value = useMemo<PdfViewportContextValue>(
    () => ({ pageNumber, zoom, jumpTarget, visitedPages, setPageNumber, setZoom, jumpToObject }),
    [pageNumber, zoom, jumpTarget, visitedPages, setPageNumber, setZoom, jumpToObject]
  );

  return <PdfViewportContext.Provider value={value}>{children}</PdfViewportContext.Provider>;
}

export function usePdfViewport(): PdfViewportContextValue {
  const ctx = useContext(PdfViewportContext);
  if (!ctx) throw new Error("usePdfViewport must be used within PdfViewportProvider");
  return ctx;
}
