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
}

export function DocxPreview({ jobId, available }: Props) {
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
  }, [jobId, available]);

  if (!available) {
    return (
      <div className="flex items-center justify-center h-64 rounded-lg border border-gray-200 bg-gray-50">
        <p className="text-sm text-gray-500">DOCX was not generated for this document.</p>
      </div>
    );
  }

  if (state.kind === "idle" || state.kind === "loading") {
    return (
      <div className="flex items-center justify-center h-64 rounded-lg border border-gray-200 bg-gray-50">
        <div className="flex items-center gap-2.5 text-sm text-gray-500">
          <svg className="h-4 w-4 animate-spin text-blue-600" viewBox="0 0 24 24" fill="none" aria-hidden="true">
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
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-center space-y-3">
        <p className="text-sm font-medium text-amber-900">
          Browser preview unavailable: {state.message}
        </p>
        <p className="text-xs text-amber-700">
          The DOCX was generated successfully. Use the download button below to open it in Word or LibreOffice.
        </p>
        <a
          href={api.downloadUrl(jobId, "docx")}
          download
          className="inline-flex items-center gap-1.5 rounded-md bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800"
        >
          Download to View
        </a>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {state.warnings.length > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2">
          <p className="text-xs font-medium text-amber-800">
            {state.warnings.length} conversion note{state.warnings.length === 1 ? "" : "s"}
            {" "}(native OOXML features may render approximately):
          </p>
          <ul className="mt-1 space-y-0.5 text-xs text-amber-700 list-disc list-inside">
            {state.warnings.slice(0, 5).map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="overflow-y-auto rounded-lg border border-gray-200 bg-white p-8 docx-preview" style={{ maxHeight: "600px" }}>
        {/* biome-ignore lint: */}
        <div dangerouslySetInnerHTML={{ __html: state.html }} />
      </div>
    </div>
  );
}
