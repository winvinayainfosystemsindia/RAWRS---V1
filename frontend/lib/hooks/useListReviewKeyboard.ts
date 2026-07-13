"use client";

import { useEffect } from "react";

function isTypingTarget(el: EventTarget | null): boolean {
  const tag = (el as HTMLElement | null)?.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}

export interface ListReviewKeyboardOptions {
  /** ArrowRight / "n" */
  onNext: () => void;
  /** ArrowLeft / "p" */
  onPrev: () => void;
  /** "/" — omit if the workspace has no search box to focus. */
  onSearch?: () => void;
  /** Single-character key -> handler, e.g. { a: accept, r: reject }. */
  keyActions?: Record<string, () => void>;
}

// Shared keyboard-navigation pattern for a "filtered list, act on the
// current item" workspace — first built for ReviewerWorkspace (M-4.3),
// extracted here (Phase F-3.1) so other workspaces extend the same
// reference implementation instead of a second, parallel shortcut scheme.
// Ignored while focus is inside a text input/textarea/select so shortcut
// letters never fight normal typing.
export function useListReviewKeyboard({ onNext, onPrev, onSearch, keyActions }: ListReviewKeyboardOptions): void {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent): void {
      if (e.key === "/" && onSearch && !isTypingTarget(e.target)) {
        e.preventDefault();
        onSearch();
        return;
      }
      if (isTypingTarget(e.target)) return;

      if (e.key === "ArrowRight" || e.key === "n") {
        onNext();
        return;
      }
      if (e.key === "ArrowLeft" || e.key === "p") {
        onPrev();
        return;
      }
      keyActions?.[e.key]?.();
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onNext, onPrev, onSearch, keyActions]);
}
