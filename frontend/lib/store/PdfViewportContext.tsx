"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
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
  setPageNumber: (page: number) => void;
  setZoom: (zoom: number) => void;
  jumpToObject: (pageNumber: number, bbox: BoundingBox | null) => void;
}

const PdfViewportContext = createContext<PdfViewportContextValue | null>(null);

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3;

export function PdfViewportProvider({ children }: { children: ReactNode }) {
  const [pageNumber, setPageNumber] = useState(1);
  const [zoom, setZoomState] = useState(1);
  const [jumpTarget, setJumpTarget] = useState<JumpTarget | null>(null);

  const value = useMemo<PdfViewportContextValue>(
    () => ({
      pageNumber,
      zoom,
      jumpTarget,
      setPageNumber,
      setZoom: (next) => setZoomState(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, next))),
      jumpToObject: (page, bbox) => {
        setPageNumber(page);
        setJumpTarget((prev) => ({ pageNumber: page, bbox, nonce: (prev?.nonce ?? 0) + 1 }));
      },
    }),
    [pageNumber, zoom, jumpTarget]
  );

  return <PdfViewportContext.Provider value={value}>{children}</PdfViewportContext.Provider>;
}

export function usePdfViewport(): PdfViewportContextValue {
  const ctx = useContext(PdfViewportContext);
  if (!ctx) throw new Error("usePdfViewport must be used within PdfViewportProvider");
  return ctx;
}
