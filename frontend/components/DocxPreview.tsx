"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

// What the Word file looks like. Two sources:
//  - the DOCX a reader would download right now (saved edits included), or
//  - `markdown`: an unsaved draft from the Markdown editor, rendered by the
//    backend's preview endpoint, so the reviewer sees the Word output of their
//    edit before saving it.
// A re-render keeps the previous page on screen with an "Updating" note, so
// typing never flashes the preview away.

type Rendered = { html: string; warnings: string[] };

interface Props {
  jobId: string;
  available: boolean;
  // Any change to document_version means the backend will build a fresh
  // DOCX, so the preview re-renders.
  documentVersion?: number | null;
  // An unsaved Markdown draft to preview instead of the saved DOCX.
  markdown?: string | null;
  // Bumped by the caller after saving or discarding edits.
  refreshKey?: number;
}

// Long enough that a burst of typing costs one render, short enough to feel live.
const DRAFT_DEBOUNCE_MS = 700;

const STYLE_MAP = [
  "p[style-name='Heading 1'] => h1:fresh",
  "p[style-name='Heading 2'] => h2:fresh",
  "p[style-name='Heading 3'] => h3:fresh",
  "p[style-name='Heading 4'] => h4:fresh",
  "p[style-name='Heading 5'] => h5:fresh",
  "p[style-name='Heading 6'] => h6:fresh",
  "p[style-name='Caption'] => p.docx-caption:fresh",
  "p[style-name='TOC Heading'] => p.docx-toc-heading:fresh",
];

async function toHtml(arrayBuffer: ArrayBuffer): Promise<Rendered> {
  const mammoth = await import("mammoth"); // keeps mammoth out of the SSR bundle
  const result = await mammoth.convertToHtml({ arrayBuffer }, { styleMap: STYLE_MAP });
  return {
    html: result.value,
    warnings: result.messages.filter((m) => m.type === "warning").map((m) => m.message),
  };
}

export function DocxPreview({ jobId, available, documentVersion, markdown, refreshKey }: Props) {
  const [rendered, setRendered] = useState<Rendered | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isUpdating, setIsUpdating] = useState(false);
  const isDraft = markdown != null;

  useEffect(() => {
    if (!available) return;
    const controller = new AbortController();
    const delay = isDraft ? DRAFT_DEBOUNCE_MS : 0;

    const timer = setTimeout(async () => {
      setIsUpdating(true);
      try {
        const buffer = isDraft
          ? await api.previewDocx(jobId, markdown!, controller.signal)
          : await fetch(api.downloadUrl(jobId, "docx"), { signal: controller.signal }).then((r) => {
              if (!r.ok) throw new Error(`HTTP ${r.status}`);
              return r.arrayBuffer();
            });
        const next = await toHtml(buffer);
        if (controller.signal.aborted) return;
        setRendered(next);
        setError(null);
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        if (!controller.signal.aborted) setIsUpdating(false);
      }
    }, delay);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [jobId, available, documentVersion, refreshKey, isDraft, markdown]);

  if (!available) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <p className="text-sm text-text-secondary">DOCX was not generated for this document.</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-border bg-surface-panel px-3 py-1.5 text-xs">
        <span className="font-medium text-text-primary">Word output</span>
        {isDraft ? (
          <span className="rounded bg-warning/15 px-1.5 py-0.5 font-medium text-warning">Preview of unsaved edits</span>
        ) : (
          <span className="text-text-secondary">as it will download</span>
        )}
        <span aria-live="polite" className="ml-auto text-text-secondary">
          {isUpdating ? "Updating…" : ""}
        </span>
        <a
          href={api.downloadUrl(jobId, "docx")}
          download
          className="rounded px-2 py-0.5 font-medium text-text-secondary hover:bg-hover-row hover:text-text-primary"
        >
          Download
        </a>
      </div>

      {error && (
        <p role="alert" className="shrink-0 border-b border-warning/40 bg-warning/10 px-3 py-1.5 text-xs text-warning">
          Preview could not be rendered ({error}). The download still has the latest saved version.
        </p>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto bg-surface-canvas p-3 sm:p-6">
        {rendered ? (
          <>
            {/* A literal paper page (Times New Roman, white) regardless of app
                theme - it shows the Word document, not app chrome. */}
            <article
              aria-label="Word output preview"
              className={`docx-preview mx-auto max-w-[8.5in] bg-white px-[clamp(1rem,8%,1in)] py-[clamp(1rem,6%,0.9in)] shadow-lg ring-1 ring-black/5 transition-opacity ${
                isUpdating ? "opacity-70" : ""
              }`}
              // Mammoth escapes document text; the HTML is only its own tags.
              dangerouslySetInnerHTML={{ __html: rendered.html }}
            />
            {rendered.warnings.length > 0 && (
              <details className="mx-auto mt-3 max-w-[8.5in] text-xs text-text-secondary">
                <summary className="cursor-pointer">
                  {rendered.warnings.length} preview note{rendered.warnings.length === 1 ? "" : "s"} (Word features
                  the browser draws approximately)
                </summary>
                <ul className="mt-1 list-inside list-disc">
                  {rendered.warnings.slice(0, 5).map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </details>
            )}
          </>
        ) : (
          !error && (
            <p role="status" className="p-6 text-center text-sm text-text-secondary">
              Rendering the Word output…
            </p>
          )
        )}
      </div>
    </div>
  );
}
