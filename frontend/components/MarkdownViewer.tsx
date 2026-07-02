"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";

export function MarkdownViewer({ content }: { content: string }) {
  const [mode, setMode] = useState<"rendered" | "raw">("rendered");

  return (
    <div>
      <div className="mb-3 flex gap-2" role="group" aria-label="Markdown view mode">
        <ToggleButton active={mode === "rendered"} onClick={() => setMode("rendered")}>
          Rendered
        </ToggleButton>
        <ToggleButton active={mode === "raw"} onClick={() => setMode("raw")}>
          Raw markdown
        </ToggleButton>
      </div>
      <div className="max-h-[70vh] overflow-y-auto rounded-lg border border-gray-200 p-5">
        {mode === "rendered" ? (
          <article className="markdown-body">
            <ReactMarkdown>{content}</ReactMarkdown>
          </article>
        ) : (
          <pre className="whitespace-pre-wrap break-words font-mono text-xs text-gray-800">{content}</pre>
        )}
      </div>
    </div>
  );
}

function ToggleButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`rounded-md px-3 py-1.5 text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
        active ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"
      }`}
    >
      {children}
    </button>
  );
}
