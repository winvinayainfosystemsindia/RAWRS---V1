"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type SelectableObjectType =
  | "heading"
  | "table"
  | "image"
  | "footnote"
  | "list"
  | "callout"
  | "correction"
  | "page-label"
  | "reading-order-page"
  | "validation-issue";

export interface Selection {
  objectType: SelectableObjectType;
  objectId: string | number;
}

interface SelectionContextValue {
  selection: Selection | null;
  select: (objectType: SelectableObjectType, objectId: string | number) => void;
  clearSelection: () => void;
}

const SelectionContext = createContext<SelectionContextValue | null>(null);

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [selection, setSelection] = useState<Selection | null>(null);

  // Stable identities: `select` must not change when the selection does.
  // Consumers sync to it in effects (ReviewerWorkspace selects its current
  // item); a new `select` per selection re-fired that effect after every nav
  // click and snatched the selection back. The same-object bail-out still
  // keeps `selection` from churning when the queue re-selects its item.
  const select = useCallback(
    (objectType: SelectableObjectType, objectId: string | number) =>
      setSelection((prev) =>
        prev && prev.objectType === objectType && prev.objectId === objectId ? prev : { objectType, objectId }
      ),
    []
  );
  const clearSelection = useCallback(() => setSelection(null), []);

  const value = useMemo<SelectionContextValue>(
    () => ({ selection, select, clearSelection }),
    [selection, select, clearSelection]
  );

  return <SelectionContext.Provider value={value}>{children}</SelectionContext.Provider>;
}

export function useSelection(): SelectionContextValue {
  const ctx = useContext(SelectionContext);
  if (!ctx) throw new Error("useSelection must be used within SelectionProvider");
  return ctx;
}
