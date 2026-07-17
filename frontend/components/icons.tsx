// Phase R-3: functional, outline-style icon set — the visual language Design
// Bible §25 specifies (Material Symbols Outlined: stroke-based, 20px,
// minimal). Hand-authored inline SVG rather than wiring up the literal
// Google Material Symbols font: that font renders via ligature substitution
// (the English word "search" must render as a glyph before the font loads),
// which risks a flash of literal icon-name text on a cold load — a real,
// documented rough edge, not a hypothetical one. Inline SVG is what every
// icon already in this codebase uses (ThemeToggle, the chevron toggles),
// so this is the existing pattern extended, not a new one, and needs no
// new dependency (no font fetch, no npm package).
//
// Every icon here is `aria-hidden` and paired with visible text wherever
// it's used — decorative reinforcement of an already-accessible label, not
// a substitute for one. None are used standalone as the only content of an
// interactive element.
"use client";

import type { ReactNode } from "react";

type IconProps = { className?: string };

function Stroke({ children, className = "h-4 w-4" }: { children: ReactNode; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {children}
    </svg>
  );
}

export function IconValidation(props: IconProps) {
  return (
    <Stroke {...props}>
      <path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" />
      <polyline points="9 12 11 14 15 10" />
    </Stroke>
  );
}

export function IconImage(props: IconProps) {
  return (
    <Stroke {...props}>
      <rect x="3" y="4" width="18" height="14" rx="2" />
      <circle cx="8.5" cy="9.5" r="1.4" />
      <polyline points="3 16 9 11 13 14 17 10 21 14" />
    </Stroke>
  );
}

export function IconTable(props: IconProps) {
  return (
    <Stroke {...props}>
      <rect x="3" y="4" width="18" height="16" rx="1" />
      <line x1="3" y1="10" x2="21" y2="10" />
      <line x1="9" y1="4" x2="9" y2="20" />
      <line x1="15" y1="4" x2="15" y2="20" />
    </Stroke>
  );
}

export function IconHeading(props: IconProps) {
  return (
    <Stroke {...props}>
      <line x1="4" y1="4" x2="4" y2="20" />
      <line x1="16" y1="4" x2="16" y2="20" />
      <line x1="4" y1="12" x2="16" y2="12" />
    </Stroke>
  );
}

export function IconFootnote(props: IconProps) {
  return (
    <Stroke {...props}>
      <line x1="12" y1="4" x2="12" y2="14" />
      <line x1="6" y1="7" x2="18" y2="11" />
      <line x1="18" y1="7" x2="6" y2="11" />
    </Stroke>
  );
}

export function IconList(props: IconProps) {
  return (
    <Stroke {...props}>
      <circle cx="4.5" cy="6" r="1" fill="currentColor" stroke="none" />
      <line x1="8" y1="6" x2="20" y2="6" />
      <circle cx="4.5" cy="12" r="1" fill="currentColor" stroke="none" />
      <line x1="8" y1="12" x2="20" y2="12" />
      <circle cx="4.5" cy="18" r="1" fill="currentColor" stroke="none" />
      <line x1="8" y1="18" x2="20" y2="18" />
    </Stroke>
  );
}

export function IconCallout(props: IconProps) {
  return (
    <Stroke {...props}>
      <path d="M4 5h16v10H8l-4 4V5z" />
      <line x1="12" y1="8" x2="12" y2="11.5" />
      <circle cx="12" cy="13.6" r="0.6" fill="currentColor" stroke="none" />
    </Stroke>
  );
}

export function IconMetadata(props: IconProps) {
  return (
    <Stroke {...props}>
      <path d="M12 3h6a2 2 0 0 1 2 2v6l-9 9-8-8 9-9z" />
      <circle cx="15" cy="8" r="1.2" fill="currentColor" stroke="none" />
    </Stroke>
  );
}

export function IconOcr(props: IconProps) {
  return (
    <Stroke {...props}>
      <path d="M4 8V6a1 1 0 0 1 1-1h2" />
      <path d="M17 5h2a1 1 0 0 1 1 1v2" />
      <path d="M4 16v2a1 1 0 0 0 1 1h2" />
      <path d="M20 16v2a1 1 0 0 1-1 1h-2" />
      <line x1="6" y1="12" x2="18" y2="12" />
    </Stroke>
  );
}

export function IconReadingOrder(props: IconProps) {
  return (
    <Stroke {...props}>
      <circle cx="5" cy="12" r="1.5" />
      <circle cx="12" cy="12" r="1.5" />
      <circle cx="19" cy="12" r="1.5" />
      <line x1="7.2" y1="12" x2="10" y2="12" />
      <line x1="14" y1="12" x2="16.8" y2="12" />
    </Stroke>
  );
}

export function IconPageLabel(props: IconProps) {
  return (
    <Stroke {...props}>
      <path d="M7 4h10a1 1 0 0 1 1 1v15l-6-4-6 4V5a1 1 0 0 1 1-1z" />
    </Stroke>
  );
}

export function IconCorrections(props: IconProps) {
  return (
    <Stroke {...props}>
      <path d="M4 20l4-1 11-11a2 2 0 0 0-3-3L5 16l-1 4z" />
      <line x1="13" y1="6" x2="17" y2="10" />
    </Stroke>
  );
}

export function IconReadiness(props: IconProps) {
  return (
    <Stroke {...props}>
      <circle cx="12" cy="12" r="8" />
      <polyline points="8.5 12 11 14.5 15.5 9.5" />
    </Stroke>
  );
}

export function IconSearch(props: IconProps) {
  return (
    <Stroke {...props}>
      <circle cx="10" cy="10" r="6" />
      <line x1="15" y1="15" x2="20" y2="20" />
    </Stroke>
  );
}

export function IconExport(props: IconProps) {
  return (
    <Stroke {...props}>
      <path d="M12 4v11" />
      <polyline points="7 11 12 16 17 11" />
      <line x1="4" y1="19" x2="20" y2="19" />
    </Stroke>
  );
}

export function IconFocus(props: IconProps) {
  return (
    <Stroke {...props}>
      <path d="M4 9V5a1 1 0 0 1 1-1h4" />
      <path d="M15 4h4a1 1 0 0 1 1 1v4" />
      <path d="M20 15v4a1 1 0 0 1-1 1h-4" />
      <path d="M9 20H5a1 1 0 0 1-1-1v-4" />
    </Stroke>
  );
}

export function IconCheckCircle(props: IconProps) {
  return (
    <Stroke {...props}>
      <circle cx="12" cy="12" r="9" />
      <polyline points="8 12.5 10.5 15 16 9" />
    </Stroke>
  );
}

export function IconWarningTriangle(props: IconProps) {
  return (
    <Stroke {...props}>
      <path d="M12 4l9 15H3z" />
      <line x1="12" y1="9.5" x2="12" y2="14" />
      <circle cx="12" cy="16.7" r="0.6" fill="currentColor" stroke="none" />
    </Stroke>
  );
}

// Shared disclosure chevron — Phase R-3: consolidates the two
// hand-duplicated inline chevron SVGs (WorkspaceShell's bottom-panel
// toggle, DocumentWorkspace's Overview toggle) into one component so a
// future change to the disclosure affordance only has one place to edit.
// Kept pixel-identical to the markup it replaces (same viewBox/path/stroke)
// so consolidating it is a pure refactor, not a visual change.
export function ChevronDownIcon({ open, className = "h-3 w-3" }: { open: boolean; className?: string }) {
  return (
    <svg
      className={`transition-transform ${open ? "rotate-180" : ""} ${className}`}
      viewBox="0 0 12 12"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M2.5 4.5 6 8l3.5-3.5" />
    </svg>
  );
}
