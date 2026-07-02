"use client";

import { useEffect, useState } from "react";

interface Stage {
  label: string;
  phase2?: boolean;       // Phase 2 — not yet implemented, always shown as pending
  immediate?: boolean;    // Shown as complete as soon as the pipeline starts
}

const STAGES: Stage[] = [
  { label: "Load Mathpix Markdown",                 immediate: true },
  { label: "Load Source PDF",                        immediate: true },
  { label: "Compare Mathpix Output ↔ Source PDF",   phase2: true },
  { label: "OCR Verification" },
  { label: "Layout Analysis" },
  { label: "Figure Detection" },
  { label: "Heading Verification" },
  { label: "Front Matter Detection" },
  { label: "Footnote Verification" },
  { label: "Accessibility Repairs" },
  { label: "Accessibility Validation" },
  { label: "Generate Accessible Markdown" },
  { label: "Generate Accessible DOCX" },
];

// First backend-run stage index (after immediate + phase2 stages).
const BACKEND_STAGE_START = 3;

type PipelineStatus = "queued" | "processing" | "complete" | "failed";

interface Props {
  status: PipelineStatus;
  elapsed: number;
}

export function PipelineView({ status, elapsed }: Props) {
  // completeThrough: stages [0, completeThrough) are complete (excluding phase2 stages).
  const [completeThrough, setCompleteThrough] = useState(0);

  useEffect(() => {
    if (status === "complete") {
      setCompleteThrough(STAGES.length);
    } else if (status === "processing") {
      // Immediate stages (0,1) start complete; then advance from BACKEND_STAGE_START.
      // Reserve last 2 non-phase2 stages for completion.
      const n = Math.min(
        BACKEND_STAGE_START + Math.floor(elapsed / 4),
        STAGES.length - 2
      );
      setCompleteThrough(n);
    } else if (status === "queued") {
      // Immediate stages are complete even while queued — the files are already loaded.
      setCompleteThrough(2);
    }
    // On "failed": leave counter wherever it was.
  }, [status, elapsed]);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5">
      <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">
        Verification Pipeline
      </h2>
      <ol className="space-y-2" aria-label="Pipeline stages">
        {STAGES.map((stage, i) => {
          if (stage.phase2) {
            // Comparison stage: always shown as Phase 2 — never completes automatically.
            return (
              <li key={stage.label} className="flex items-center gap-3">
                <span
                  aria-hidden="true"
                  className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-dashed border-violet-400 bg-violet-50 text-[9px] font-bold text-violet-500"
                >
                  2
                </span>
                <span className="flex-1 text-sm text-violet-700">{stage.label}</span>
                <span className="shrink-0 rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-semibold text-violet-700">
                  Phase 2
                </span>
              </li>
            );
          }

          const done = i < completeThrough;
          const active = i === completeThrough && (status === "processing" || status === "queued");
          const failed = status === "failed" && !done && i === completeThrough;

          return (
            <li key={stage.label} className="flex items-center gap-3">
              <span
                aria-hidden="true"
                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full transition-colors ${
                  done
                    ? "bg-green-500"
                    : failed
                    ? "bg-red-500 text-white"
                    : active
                    ? "bg-blue-600"
                    : "bg-gray-100"
                }`}
              >
                {done ? (
                  <svg className="h-3 w-3 text-white" viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M2 6l3 3 5-5" />
                  </svg>
                ) : failed ? (
                  <svg className="h-3 w-3 text-white" viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 3l6 6M9 3l-6 6" />
                  </svg>
                ) : active ? (
                  <span className="h-2 w-2 rounded-full bg-white" />
                ) : (
                  <span className="text-[9px] text-gray-400 font-medium">{i + 1}</span>
                )}
              </span>

              <span
                className={`flex-1 text-sm leading-none ${
                  done
                    ? "text-gray-900"
                    : failed
                    ? "text-red-700"
                    : active
                    ? "font-medium text-blue-700"
                    : "text-gray-400"
                }`}
              >
                {stage.label}
              </span>

              {active && status === "processing" && (
                <span className="shrink-0 text-xs font-medium text-blue-500" aria-live="polite">
                  Running<span className="animate-pulse">…</span>
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
