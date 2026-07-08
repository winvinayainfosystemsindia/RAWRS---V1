"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type PreviewState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; html: string; warnings: string[] }
  | { kind: "error"; message: string };

interface Props {
  jobId: string;
  available: boolean;
  // Any change to document_version means the backend's on-demand export
  // regen (_needs_export_regen in routes.py) will produce a fresh DOCX —
  // re-run the conversion so this preview never shows stale content.
  documentVersion?: number | null;
}

export function DocxPreview({ jobId, available, documentVersion }: Props) {
  const [state, setState] = useState<PreviewState>({ kind: "idle" });
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (!available) return;
    setState({ kind: "loading" });

    async function load() {
      try {
        const url = api.downloadUrl(jobId, "docx");
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const arrayBuffer = await response.arrayBuffer();

        // Dynamic import keeps mammoth out of the SSR bundle.
        const mammoth = await import("mammoth");
        const result = await mammoth.convertToHtml(
          { arrayBuffer },
          {
            styleMap: [
              "p[style-name='Heading 1'] => h1:fresh",
              "p[style-name='Heading 2'] => h2:fresh",
              "p[style-name='Heading 3'] => h3:fresh",
              "p[style-name='Heading 4'] => h4:fresh",
              "p[style-name='Heading 5'] => h5:fresh",
              "p[style-name='Heading 6'] => h6:fresh",
            ],
          }
        );

        if (!mountedRef.current) return;
        setState({
          kind: "ready",
          html: result.value,
          warnings: result.messages
            .filter((m) => m.type === "warning")
            .map((m) => m.message),
        });
      } catch (err) {
        if (!mountedRef.current) return;
        setState({
          kind: "error",
          message: err instanceof Error ? err.message : "Unknown error",
        });
      }
    }

    load();
  }, [jobId, available, documentVersion]);

  if (!available) {
    return (
      <div className="flex items-center justify-center h-64 rounded-lg border border-border bg-surface-panel">
        <p className="text-sm text-text-secondary">DOCX was not generated for this document.</p>
      </div>
    );
  }

  if (state.kind === "idle" || state.kind === "loading") {
    return (
      <div className="flex items-center justify-center h-64 rounded-lg border border-border bg-surface-panel">
        <div className="flex items-center gap-2.5 text-sm text-text-secondary">
          <svg className="h-4 w-4 animate-spin text-accent" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Converting DOCX for preview…
        </div>
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <div className="rounded-lg border border-warning/40 bg-warning/10 p-6 text-center space-y-3">
        <p className="text-sm font-medium text-warning">
          Browser preview unavailable: {state.message}
        </p>
        <p className="text-xs text-warning/80">
          The DOCX was generated successfully. Use the download button below to open it in Word or LibreOffice.
        </p>
        <a
          href={api.downloadUrl(jobId, "docx")}
          download
          className="inline-flex items-center gap-1.5 rounded-md bg-accent px-4 py-2 text-xs font-semibold text-accent-contrast hover:opacity-90"
        >
          Download to View
        </a>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {state.warnings.length > 0 && (
        <div className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2">
          <p className="text-xs font-medium text-warning">
            {state.warnings.length} conversion note{state.warnings.length === 1 ? "" : "s"}
            {" "}(native OOXML features may render approximately):
          </p>
          <ul className="mt-1 space-y-0.5 text-xs text-warning/80 list-disc list-inside">
            {state.warnings.slice(0, 5).map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      {/* .docx-preview is a deliberate literal paper surface (Times New
          Roman, white bg) regardless of app theme — it previews the actual
          generated Word document, not app chrome. Only the border around it
          follows the app theme. */}
      <div className="overflow-y-auto rounded-lg border border-border bg-white p-8 docx-preview" style={{ maxHeight: "600px" }}>
        {/* biome-ignore lint: */}
        <div dangerouslySetInnerHTML={{ __html: state.html }} />
      </div>
    </div>
  );
}
