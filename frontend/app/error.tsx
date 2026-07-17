"use client";

import { useEffect } from "react";
import Link from "next/link";

interface ErrorPageProps {
  error: Error & { digest?: string };
  reset: () => void;
}

// Next.js App Router error-boundary convention — catches any thrown render
// error below this segment. Renders inside app/layout.tsx's existing
// header/main/footer shell (error boundaries only replace their own
// children, not their ancestors), so no page chrome is duplicated here.
//
// Reuses the exact danger-banner pattern already established in
// DocumentWorkspace.tsx's failed-job state (role="alert",
// border-danger/30 bg-danger/10) rather than inventing a new error
// visual language — same reasoning as Phase R-2 M7's PdfViewer message
// rewrite: a reviewer sees a plain, actionable message, never a raw
// message/stack; the full detail goes to the console for diagnostics.
export default function Error({ error, reset }: ErrorPageProps) {
  useEffect(() => {
    console.error("Unhandled application error:", error);
  }, [error]);

  return (
    <div role="alert" className="space-y-3 rounded-lg border border-danger/30 bg-danger/10 p-4">
      <p className="text-sm font-semibold text-danger">Something went wrong.</p>
      <p className="text-sm text-danger/90">
        RAWRS hit an unexpected error rendering this page. Nothing you reviewed has been lost — try
        again, or go back and re-open the document.
      </p>
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={reset}
          className="rounded border border-danger/40 px-3 py-1.5 text-sm font-medium text-danger transition-colors hover:bg-danger/10"
        >
          Try again
        </button>
        <Link href="/" className="text-sm font-medium text-accent hover:underline">
          &larr; Back to upload
        </Link>
      </div>
      {error.digest && <p className="font-mono text-xs text-danger/70">Reference: {error.digest}</p>}
    </div>
  );
}
