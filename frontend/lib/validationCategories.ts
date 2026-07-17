// Shared category registry — extracted from ValidationIssueTable.tsx
// (Phase RW-1) so the Accessibility Center (ReadinessPanel.tsx) can reuse
// the exact same rule-id -> category mapping instead of re-deriving its
// own, drifting, second copy. ValidationIssueTable.tsx's own behavior is
// unchanged by this extraction — same map, same order, same function.

export const RULE_CATEGORY_LABELS: Record<string, string> = {
  DOC: "Document",
  HEADING: "Heading",
  PAGE: "Page",
  META: "Metadata",
  IMAGE: "Image",
  NOTE: "Footnote/Endnote",
  OCR: "OCR",
  TABLE: "Table",
  LIST: "List",
  CALLOUT: "Callout",
};

// PAGE_003 (reading-order anomalies) is split out from the generic
// "Page" category (page markers/sequencing, PAGE_001/002) since
// reading-order review is its own required workflow. Any *_VERIFY_*
// rule id (HEADING_VERIFY_004, LIST_VERIFY_002, ...) is cross-source
// Mathpix-vs-PDF verification output, grouped separately from the
// same object type's Phase-1 structural findings per the stitch
// validation-report reference.
export function categoryOf(ruleId: string): string {
  if (ruleId === "PAGE_003") return "Reading order";
  if (ruleId.includes("_VERIFY_")) return "Cross-Source Verification";
  const prefix = ruleId.split("_")[0];
  return RULE_CATEGORY_LABELS[prefix] ?? prefix;
}

// Canonical display order — cross-source verification and structural
// document-level issues surface first, per-object categories follow.
export const CATEGORY_ORDER = [
  "Cross-Source Verification",
  "Document",
  "Metadata",
  "Reading order",
  "Page",
  "Heading",
  "Image",
  "Table",
  "List",
  "Callout",
  "Footnote/Endnote",
  "OCR",
];

export function sortCategories(categories: string[]): string[] {
  return [...categories].sort((a, b) => {
    const ai = CATEGORY_ORDER.indexOf(a);
    const bi = CATEGORY_ORDER.indexOf(b);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return a.localeCompare(b);
  });
}

// The Accessibility Center (ReadinessPanel.tsx) needs to know which
// categories RAWRS's validator can *possibly* report on, so a category
// with zero issues (never appears in GET /readiness's category list —
// see src/validation/readiness.py's compute_readiness, which only
// creates an entry for a prefix that actually fired) can be shown as a
// real "Passed" state rather than silently omitted, while a category
// the validator has no rule prefix for at all is shown honestly as
// "not yet assessed", never a fake pass. Mirrors the backend's own
// fixed prefix set (src/validation/readiness.py _CATEGORY_LABELS) —
// not invented here.
export interface KnownCategory {
  /** Matches ReadinessCategoryDetail.category from the backend (the raw prefix). */
  prefix: string;
  label: string;
  /** DocumentWorkspace.tsx specialView id this category can jump to, if any. */
  specialViewId?: string;
}

export const KNOWN_READINESS_CATEGORIES: KnownCategory[] = [
  { prefix: "IMAGE", label: "Images", specialViewId: "images" },
  { prefix: "TABLE", label: "Tables", specialViewId: "tables" },
  { prefix: "HEADING", label: "Headings", specialViewId: "headings" },
  { prefix: "LIST", label: "Lists", specialViewId: "lists" },
  { prefix: "NOTE", label: "Footnotes", specialViewId: "footnotes" },
  { prefix: "META", label: "Metadata", specialViewId: "metadata" },
  { prefix: "PAGE", label: "Page Structure", specialViewId: "page-labels" },
  { prefix: "OCR", label: "OCR Quality", specialViewId: "ocr" },
  { prefix: "DOC", label: "Document Structure" },
];

// Named, on the record, per the mission's WCAG Foundation requirement —
// categories a future Accessibility Rules Engine would need to cover
// with their own dedicated score. "Reading Order" issues are real data
// today (rule_id PAGE_003) but src/validation/readiness.py's
// compute_readiness lumps them into the generic PAGE bucket rather than
// breaking them out, so a separately-honest reading-order score can't
// yet be computed from GET /readiness. "Navigation" and "Language" have
// no backend rule prefix at all yet. All three render as an explicit
// "not yet assessed" note in the Accessibility Center, never a
// fabricated score.
export const DEFERRED_READINESS_CATEGORIES = ["Reading Order", "Navigation", "Language"];
