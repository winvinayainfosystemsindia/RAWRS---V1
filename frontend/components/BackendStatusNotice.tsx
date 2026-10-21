"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, DEMO_JOB_ID } from "@/lib/api";

// The frontend is hosted publicly, but documents are processed by a server
// the project owner runs on their own computer, on request. When that server
// cannot be reached, say so plainly at the top of every page, rather than
// letting each panel fail with a network error.

type Status = "checking" | "online" | "offline";

export function BackendStatusNotice() {
  const [status, setStatus] = useState<Status>("checking");

  const check = useCallback(() => {
    setStatus("checking");
    api.isBackendReachable().then((reachable) => setStatus(reachable ? "online" : "offline"));
  }, []);

  useEffect(() => {
    let cancelled = false;
    api.isBackendReachable().then((reachable) => {
      if (!cancelled) setStatus(reachable ? "online" : "offline");
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "online") return null;
  if (status === "checking") {
    return (
      <p role="status" className="sr-only">
        Checking whether the RAWRS processing service is available…
      </p>
    );
  }

  return (
    <section aria-labelledby="backend-offline-heading" className="border-b border-warning/30 bg-warning/10">
      <div className="mx-auto flex max-w-6xl flex-wrap items-start gap-4 px-6 py-4">
        <div className="min-w-0 flex-1 space-y-1.5">
          <h2 id="backend-offline-heading" className="text-sm font-bold text-text-primary">
            The RAWRS processing service is currently offline
          </h2>
          <p className="text-sm text-text-primary">
            RAWRS processes documents on a private server that the project owner operates on their own computer. That
            server is not running at the moment, so documents cannot be uploaded, processed or opened from this page.
          </p>
          <p className="text-sm text-text-primary">
            To view RAWRS in operation, please contact the project owner and request access. Once your request has been
            approved, the owner will start the server and confirm when the service is available.
          </p>
          <p className="text-sm text-text-primary">
            In the meantime, you can explore a document RAWRS has already processed, in a read-only preview:{" "}
            <Link href={`/documents/${DEMO_JOB_ID}`} className="font-semibold text-accent underline">
              View sample document
            </Link>
          </p>
        </div>
        <button
          type="button"
          onClick={check}
          className="shrink-0 rounded-lg border border-border bg-surface-canvas px-4 py-2 text-sm font-semibold text-text-primary hover:bg-hover-row focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          Check again
        </button>
      </div>
    </section>
  );
}
