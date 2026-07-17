"use client";

// Quick-jump row rendered above WorkspaceShell (Phase R-1.1 Global
// Navigation Chips). Pure reuse: renders the same `specialViews` array
// DocumentWorkspace.tsx already builds for SemanticNavTree's "Workspaces"
// section and drives the same `onSelectSpecialView` callback — no new
// state, no parallel selection model.
import type { ComponentType } from "react";
import type { NavSection } from "@/components/workspace/SemanticNavTree";
import {
  IconValidation,
  IconImage,
  IconTable,
  IconHeading,
  IconFootnote,
  IconList,
  IconCallout,
  IconMetadata,
  IconOcr,
  IconReadingOrder,
  IconPageLabel,
  IconCorrections,
  IconReadiness,
} from "@/components/icons";

interface NavChipsProps {
  sections: NavSection[];
  activeSpecialView: string | null;
  onSelect: (id: string) => void;
}

// Phase R-3: one icon per specialView id, purely for faster scanning across
// a 13-item row (Bible §25 — icons "used functionally, not decoratively").
// Keyed on the same ids DocumentWorkspace.tsx already assigns; a specialView
// id with no entry here (there shouldn't be one) just renders without an
// icon rather than throwing, so this stays additive, never load-bearing.
const SECTION_ICONS: Record<string, ComponentType<{ className?: string }>> = {
  validation: IconValidation,
  images: IconImage,
  tables: IconTable,
  headings: IconHeading,
  footnotes: IconFootnote,
  lists: IconList,
  callouts: IconCallout,
  metadata: IconMetadata,
  ocr: IconOcr,
  "reading-order": IconReadingOrder,
  "page-labels": IconPageLabel,
  corrections: IconCorrections,
  readiness: IconReadiness,
};

// Phase R-2 M1: no longer owns an "Overview" chip — that duplicated the
// dedicated Overview disclosure in DocumentWorkspace.tsx (same accessible
// name, same overviewOpen state, reached two different ways). Overview
// isn't a specialView (it doesn't run through onSelectSpecialView / render
// inside WorkspaceShell's mode="special"), so it never belonged in a
// component whose whole job is rendering that one array.
export function NavChips({ sections, activeSpecialView, onSelect }: NavChipsProps) {
  return (
    <div role="toolbar" aria-label="Quick jump" className="flex flex-wrap items-center gap-2">
      {sections.map((s) => (
        <Chip
          key={s.id}
          label={s.label}
          count={s.count}
          urgentCount={s.urgentCount}
          isActive={activeSpecialView === s.id}
          onClick={() => onSelect(s.id)}
          Icon={SECTION_ICONS[s.id]}
        />
      ))}
      <Chip label="Bookmarks" disabled Icon={IconPageLabel} />
    </div>
  );
}

function Chip({
  label,
  count,
  urgentCount,
  isActive,
  disabled,
  onClick,
  Icon,
}: {
  label: string;
  count?: number;
  urgentCount?: number;
  isActive?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  Icon?: ComponentType<{ className?: string }>;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      title={disabled ? "Reserved for a future phase" : undefined}
      onClick={onClick}
      aria-pressed={isActive}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
        isActive
          ? "border-accent bg-accent text-accent-contrast"
          : "border-border text-text-secondary hover:border-border-strong hover:bg-hover-row hover:text-text-primary"
      }`}
    >
      {Icon && <Icon className="h-3.5 w-3.5 shrink-0" />}
      {label}
      {!!urgentCount && urgentCount > 0 && (
        <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-danger/20 px-1 font-mono text-[10px] text-danger">
          {urgentCount}
        </span>
      )}
      {typeof count === "number" && !urgentCount && (
        <span
          className={`inline-flex h-4 min-w-4 items-center justify-center rounded-full px-1 font-mono text-[10px] ${
            isActive ? "bg-black/15 text-accent-contrast" : "bg-surface-elevated text-text-secondary"
          }`}
        >
          {count}
        </span>
      )}
    </button>
  );
}
