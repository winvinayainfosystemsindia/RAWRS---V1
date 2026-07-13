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
      // Bails out (returns the same `prev` reference) when the requested
      // selection is already current — without this, a caller that
      // re-selects the same object on every render (e.g. a queue synced
      // to "whichever item is current") churns `selection`'s identity
      // forever: new object -> new context `value` -> new `select`
      // function identity -> any effect depending on `select` re-fires ->
      // calls `select` again -> infinite render loop ("Maximum update
      // depth exceeded"), caught via live browser verification of M-4.2.
      select: (objectType, objectId) =>
        setSelection((prev) =>
          prev && prev.objectType === objectType && prev.objectId === objectId
            ? prev
            : { objectType, objectId }
        ),
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
