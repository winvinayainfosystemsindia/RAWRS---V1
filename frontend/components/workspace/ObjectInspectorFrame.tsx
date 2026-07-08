import type { ReactNode } from "react";

interface ObjectInspectorFrameProps {
  header: ReactNode;
  metadata?: ReactNode;
  evidence?: ReactNode;
  validation?: ReactNode;
  correctionHistory?: ReactNode;
  version?: ReactNode;
  actions?: ReactNode;
}

function Section({ label, children }: { label: string; children?: ReactNode }) {
  if (!children) return null;
  return (
    <div>
      <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-text-secondary">{label}</p>
      {children}
    </div>
  );
}

// Every per-type detail panel (Heading, Table, Image, Footnote, List,
// Callout) renders inside this frame with sections in this fixed order —
// the seam a fully generic Semantic Object Inspector slots into later
// without a rewrite.
export function ObjectInspectorFrame({
  header,
  metadata,
  evidence,
  validation,
  correctionHistory,
  version,
  actions,
}: ObjectInspectorFrameProps) {
  return (
    <div className="rounded-lg border border-border bg-surface-panel p-4 space-y-4">
      {header}
      <Section label="Metadata">{metadata}</Section>
      <Section label="Evidence">{evidence}</Section>
      <Section label="Validation">{validation}</Section>
      <Section label="Correction History">{correctionHistory}</Section>
      <Section label="Version">{version}</Section>
      {actions && <div className="flex flex-wrap gap-2 border-t border-border pt-3">{actions}</div>}
    </div>
  );
}
