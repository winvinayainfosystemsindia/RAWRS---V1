// FE-1-001 — shared inspector layout classes.
//
// The single scroll region lives in WorkspaceShell's `mode === "special"`
// pane (one container for every panel, current and future). Panels never
// declare their own scrolling; they only opt their toolbar into staying
// visible while that container scrolls.

/**
 * Pins a panel's toolbar/filter row to the top of the shared scroll
 * container.
 *
 * The negative offsets are load-bearing, not cosmetic. The scroll container
 * carries `p-4`, so a plain `sticky top-0` would pin the bar 1rem down and
 * let list rows show through the gap above it. `-top-4` cancels that inset
 * and `-mx-4 px-4` lets the bar's background span the container's full
 * width, so nothing peeks past its edges while scrolling underneath.
 *
 * Exported as one constant rather than repeated per panel: the offsets are
 * coupled to the container's padding, and duplicating them would mean N
 * places to fix if that padding ever changes.
 */
export const INSPECTOR_TOOLBAR =
  "sticky -top-4 z-10 -mx-4 bg-surface-canvas px-4 pb-2 pt-4";
