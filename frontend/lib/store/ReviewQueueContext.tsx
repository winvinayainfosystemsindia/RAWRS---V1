"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

// Cross-cutting review-queue state, sibling to SelectionContext /
// PdfViewportContext. Exists so the Accessibility Center's category cards can
// drive the Review Queue directly (P1-6): clicking "Review →" on the Images
// category sets objectTypeFilter="image" and bumps focusNonce, and the queue
// (ReviewerWorkspace) + shell (open the bottom panel) react — instead of
// throwing the reviewer into a different full-screen view. Kept deliberately
// small; not a general filter store.

const OBJECT_TYPE_FILTER_KEY = "rawrs:rq:objectType";
export const ANY_OBJECT_TYPE = "__any__";

interface ReviewQueueValue {
  // Object-type the queue is filtered to, or ANY_OBJECT_TYPE. Persisted so a
  // reviewer returns to the same filter (P1-7).
  objectTypeFilter: string;
  setObjectTypeFilter: (t: string) => void;
  // Bumped whenever the queue should be brought forward (bottom panel opened,
  // Review tab selected). Consumers watch the number, not a boolean, so
  // repeated focus requests always re-fire.
  focusNonce: number;
  // Set a filter AND request focus in one call — the category-card action.
  focusQueue: (objectType?: string) => void;
}

const ReviewQueueContext = createContext<ReviewQueueValue | null>(null);

function readInitialFilter(): string {
  if (typeof window === "undefined") return ANY_OBJECT_TYPE;
  return window.localStorage.getItem(OBJECT_TYPE_FILTER_KEY) ?? ANY_OBJECT_TYPE;
}

export function ReviewQueueProvider({ children }: { children: ReactNode }) {
  const [objectTypeFilter, setFilterState] = useState<string>(readInitialFilter);
  const [focusNonce, setFocusNonce] = useState(0);

  const setObjectTypeFilter = useCallback((t: string) => {
    setFilterState(t);
    try {
      window.localStorage.setItem(OBJECT_TYPE_FILTER_KEY, t);
    } catch {
      /* quota / private mode — filter still works for the session */
    }
  }, []);

  const focusQueue = useCallback((objectType?: string) => {
    if (objectType !== undefined) setObjectTypeFilter(objectType);
    setFocusNonce((n) => n + 1);
  }, [setObjectTypeFilter]);

  const value = useMemo(
    () => ({ objectTypeFilter, setObjectTypeFilter, focusNonce, focusQueue }),
    [objectTypeFilter, setObjectTypeFilter, focusNonce, focusQueue]
  );

  return <ReviewQueueContext.Provider value={value}>{children}</ReviewQueueContext.Provider>;
}

export function useReviewQueue(): ReviewQueueValue {
  const ctx = useContext(ReviewQueueContext);
  if (!ctx) throw new Error("useReviewQueue must be used within ReviewQueueProvider");
  return ctx;
}
