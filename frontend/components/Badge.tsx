type Tone = "neutral" | "success" | "warning" | "danger" | "info";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-gray-100 text-gray-700 ring-gray-300 dark:bg-white/10 dark:text-gray-300 dark:ring-white/20",
  success: "bg-green-50 text-green-800 ring-green-300 dark:bg-green-500/15 dark:text-green-300 dark:ring-green-500/30",
  warning: "bg-amber-50 text-amber-800 ring-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:ring-amber-500/30",
  danger: "bg-red-50 text-red-800 ring-red-300 dark:bg-red-500/15 dark:text-red-300 dark:ring-red-500/30",
  info: "bg-blue-50 text-blue-800 ring-blue-300 dark:bg-blue-500/15 dark:text-blue-300 dark:ring-blue-500/30",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: React.ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: "error" | "warning" | "info" }) {
  const tone: Tone = severity === "error" ? "danger" : severity === "warning" ? "warning" : "info";
  return <Badge tone={tone}>{severity.toUpperCase()}</Badge>;
}

export function JobStatusBadge({ status }: { status: "queued" | "processing" | "complete" | "failed" }) {
  const tone: Tone =
    status === "complete" ? "success" : status === "failed" ? "danger" : status === "processing" ? "info" : "neutral";
  const label = status === "complete" ? "Complete" : status === "failed" ? "Failed" : status === "processing" ? "Processing" : "Queued";
  return <Badge tone={tone}>{label}</Badge>;
}

export function ConfidenceBadge({ confidence }: { confidence: "high" | "medium" | "low" | null }) {
  if (!confidence) return <Badge tone="neutral">Not OCR&apos;d</Badge>;
  const tone: Tone = confidence === "high" ? "success" : confidence === "medium" ? "info" : "warning";
  return <Badge tone={tone}>{confidence.toUpperCase()}</Badge>;
}

export function AiUnavailableBadge({ reason }: { reason: string | null }) {
  return (
    <span title={reason ?? undefined} className="inline-flex">
      <Badge tone="warning">AI unavailable{reason ? `: ${reason}` : ""}</Badge>
    </span>
  );
}

import type { AltTextStatus } from "@/lib/api";

export function AltTextStatusBadge({ status }: { status: AltTextStatus | null }) {
  switch (status) {
    case "approved": return <Badge tone="success">Approved</Badge>;
    case "human_reviewed": return <Badge tone="success">Human reviewed</Badge>;
    case "ai_generated": return <Badge tone="info">AI generated — review needed</Badge>;
    case "pending_review": return <Badge tone="warning">Pending review</Badge>;
    case "rejected": return <Badge tone="danger">Rejected</Badge>;
    case "decorative": return <Badge tone="neutral">Decorative</Badge>;
    case "complex": return <Badge tone="warning">Complex — needs long description</Badge>;
    case "skipped": return <Badge tone="neutral">Skipped</Badge>;
    default: return <Badge tone="neutral">No alt text</Badge>;
  }
}
