"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

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

  const value = useMemo<SelectionContextValue>(
    () => ({
      selection,
      select: (objectType, objectId) => setSelection({ objectType, objectId }),
      clearSelection: () => setSelection(null),
    }),
    [selection]
  );

  return <SelectionContext.Provider value={value}>{children}</SelectionContext.Provider>;
}

export function useSelection(): SelectionContextValue {
  const ctx = useContext(SelectionContext);
  if (!ctx) throw new Error("useSelection must be used within SelectionProvider");
  return ctx;
}
