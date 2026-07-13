"use client";

import { useRef, type KeyboardEvent, type RefObject } from "react";

export interface ArrowKeyTabsOptions<T extends string> {
  ids: readonly T[];
  active: T;
  onChange: (id: T) => void;
  /** Default "horizontal" (Left/Right). Use "vertical" for Up/Down. */
  orientation?: "horizontal" | "vertical";
}

export interface TabProps<T extends string> {
  role: "tab";
  "aria-selected": boolean;
  tabIndex: number;
  "data-tab-id": T;
  onClick: () => void;
  onKeyDown: (e: KeyboardEvent) => void;
}

export interface ArrowKeyTabsResult<T extends string> {
  tablistRef: RefObject<HTMLElement | null>;
  getTabProps: (id: T) => TabProps<T>;
}

// WAI-ARIA APG "Tabs" keyboard pattern (roving tabindex + automatic
// activation — arrow keys move focus and selection together, the
// simpler and by far more common of the APG's two activation models).
// One shared implementation for every mutually-exclusive CONTENT-
// SWITCHING widget in RAWRS (Phase F-3.2): selecting an option swaps
// which panel/content is visible. Deliberately NOT used for filter/
// status toggles (e.g. Corrections status tabs, Image Workspace's
// Missing Alt/Accepted/... filters) — those narrow one persistent list
// rather than switch panels, so role="tab" would misrepresent them to
// assistive tech (a screen reader announcing "tab 2 of 5" for what is
// actually a filter checkbox is a real regression, not an improvement).
export function useArrowKeyTabs<T extends string>({
  ids,
  active,
  onChange,
  orientation = "horizontal",
}: ArrowKeyTabsOptions<T>): ArrowKeyTabsResult<T> {
  const tablistRef = useRef<HTMLElement | null>(null);

  function focusTab(id: T): void {
    const el = tablistRef.current?.querySelector<HTMLElement>(`[data-tab-id="${id}"]`);
    el?.focus();
  }

  function handleKeyDown(e: KeyboardEvent): void {
    const idx = ids.indexOf(active);
    const nextKey = orientation === "vertical" ? "ArrowDown" : "ArrowRight";
    const prevKey = orientation === "vertical" ? "ArrowUp" : "ArrowLeft";

    let nextIdx: number | null = null;
    if (e.key === nextKey) nextIdx = (idx + 1) % ids.length;
    else if (e.key === prevKey) nextIdx = (idx - 1 + ids.length) % ids.length;
    else if (e.key === "Home") nextIdx = 0;
    else if (e.key === "End") nextIdx = ids.length - 1;
    if (nextIdx === null) return;

    e.preventDefault();
    const nextId = ids[nextIdx];
    onChange(nextId);
    // Focus follows selection only after the re-render moves tabIndex=0
    // onto the new tab — rAF, not a synchronous call, so the DOM node
    // being focused actually exists with the updated tabIndex by then.
    requestAnimationFrame(() => focusTab(nextId));
  }

  function getTabProps(id: T): TabProps<T> {
    return {
      role: "tab",
      "aria-selected": id === active,
      tabIndex: id === active ? 0 : -1,
      "data-tab-id": id,
      onClick: () => onChange(id),
      onKeyDown: handleKeyDown,
    };
  }

  return { tablistRef, getTabProps };
}
