import type { EvidenceSignal } from "@/lib/api";

// Extracted from CorrectionsPanel — one row per signal src/verification/
// evidence.py's EvidenceBundle fused into an overall confidence score; the
// bar is each signal's own score (not its weighted contribution) so a
// reviewer can see at a glance which signals pulled toward the conclusion
// and which were weak or absent. Shared by CorrectionsPanel and
// ObjectInspectorFrame — one implementation, never diverging.
export function EvidenceBreakdown({ evidence }: { evidence: EvidenceSignal[] }) {
  if (evidence.length === 0) return null;

  return (
    <div className="rounded-lg border border-dashed border-border bg-surface-panel p-3">
      <p className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">Evidence</p>
      <ul className="space-y-2">
        {evidence.map((item, i) => (
          <li key={i} className="text-sm text-text-primary">
            <div className="flex items-center gap-2">
              <span className="font-medium shrink-0">{item.name}</span>
              <div
                className="h-1.5 flex-1 min-w-[40px] max-w-[120px] rounded-full bg-surface-elevated overflow-hidden"
                role="img"
                aria-label={`score ${item.score.toFixed(2)} of 1.00`}
              >
                <div
                  className={`h-full rounded-full ${
                    item.score >= 0.7 ? "bg-success" : item.score >= 0.4 ? "bg-warning" : "bg-danger"
                  }`}
                  style={{ width: `${Math.round(item.score * 100)}%` }}
                />
              </div>
              <span className="text-xs text-text-secondary shrink-0">
                {item.score.toFixed(2)} × {item.weight.toFixed(1)} wt
              </span>
            </div>
            <p className="text-text-secondary mt-0.5">{item.note}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
