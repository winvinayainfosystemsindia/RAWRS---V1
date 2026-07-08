"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

interface JumpTarget {
  line: number;
  nonce: number;
}

interface MarkdownViewportContextValue {
  jumpTarget: JumpTarget | null;
  jumpToLine: (line: number) => void;
}

const MarkdownViewportContext = createContext<MarkdownViewportContextValue | null>(null);

export function MarkdownViewportProvider({ children }: { children: ReactNode }) {
  const [jumpTarget, setJumpTarget] = useState<JumpTarget | null>(null);

  const value = useMemo<MarkdownViewportContextValue>(
    () => ({
      jumpTarget,
      jumpToLine: (line) => setJumpTarget((prev) => ({ line, nonce: (prev?.nonce ?? 0) + 1 })),
    }),
    [jumpTarget]
  );

  return <MarkdownViewportContext.Provider value={value}>{children}</MarkdownViewportContext.Provider>;
}

export function useMarkdownViewport(): MarkdownViewportContextValue {
  const ctx = useContext(MarkdownViewportContext);
  if (!ctx) throw new Error("useMarkdownViewport must be used within MarkdownViewportProvider");
  return ctx;
}
