"use client";

// VS Code-style activity bar: one icon per workspace down the left edge of the
// window. It replaces the two rows of quick-jump chips that sat above the
// document and cost ~90px of height on every screen; the same `specialViews`
// array and the same `onSelect` callback drive it, so nothing about which
// workspaces exist or how they open has changed - only where they live.
import type { ComponentType } from "react";
import type { NavSection } from "@/components/workspace/SemanticNavTree";
import {
  IconCallout,
  IconCorrections,
  IconDocument,
  IconEquation,
  IconFootnote,
  IconHeading,
  IconImage,
  IconList,
  IconMetadata,
  IconOcr,
  IconOverview,
  IconPageLabel,
  IconReadiness,
  IconReadingOrder,
  IconTable,
  IconValidation,
} from "@/components/icons";

const SECTION_ICONS: Record<string, ComponentType<{ className?: string }>> = {
  overview: IconOverview,
  validation: IconValidation,
  images: IconImage,
  tables: IconTable,
  headings: IconHeading,
  footnotes: IconFootnote,
  lists: IconList,
  callouts: IconCallout,
  equations: IconEquation,
  metadata: IconMetadata,
  ocr: IconOcr,
  "reading-order": IconReadingOrder,
  "page-labels": IconPageLabel,
  corrections: IconCorrections,
  readiness: IconReadiness,
};

type Props = {
  sections: NavSection[];
  activeSpecialView: string | null;
  onSelect: (id: string) => void;
};

export function ActivityBar({ sections, activeSpecialView, onSelect }: Props) {
  return (
    <nav
      aria-label="Workspaces"
      className="flex w-12 shrink-0 flex-col items-center gap-0.5 overflow-y-auto border-r border-border bg-surface-panel py-1.5"
    >
      <ActivityButton
        label="Document"
        Icon={IconDocument}
        isActive={!activeSpecialView}
        onClick={() => onSelect("")}
      />
      <div className="my-1 h-px w-6 bg-border" aria-hidden="true" />
      {sections.map((section) => (
        <ActivityButton
          key={section.id}
          label={section.label}
          Icon={SECTION_ICONS[section.id] ?? IconDocument}
          count={section.count}
          urgentCount={section.urgentCount}
          isActive={activeSpecialView === section.id}
          onClick={() => onSelect(section.id)}
        />
      ))}
    </nav>
  );
}

function ActivityButton({
  label,
  Icon,
  count,
  urgentCount,
  isActive,
  onClick,
}: {
  label: string;
  Icon: ComponentType<{ className?: string }>;
  count?: number;
  urgentCount?: number;
  isActive: boolean;
  onClick: () => void;
}) {
  const badge = urgentCount ? urgentCount : undefined;
  const spoken = [label, urgentCount ? `${urgentCount} need attention` : count != null ? `${count}` : ""]
    .filter(Boolean)
    .join(", ");
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={isActive}
      aria-label={spoken}
      title={spoken}
      className={`group relative flex h-10 w-10 items-center justify-center rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
        isActive
          ? "bg-accent/15 text-text-primary"
          : "text-text-secondary hover:bg-hover-row hover:text-text-primary"
      }`}
    >
      {/* The active item's accent rail, as in VS Code. */}
      <span
        aria-hidden="true"
        className={`absolute -left-1 top-2 bottom-2 w-0.5 rounded-full ${isActive ? "bg-accent" : "bg-transparent"}`}
      />
      <Icon className="h-5 w-5" />
      {badge != null && (
        <span
          aria-hidden="true"
          className="absolute -right-0.5 -top-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 font-mono text-[9px] font-semibold leading-none text-white"
        >
          {badge > 99 ? "99+" : badge}
        </span>
      )}
    </button>
  );
}
