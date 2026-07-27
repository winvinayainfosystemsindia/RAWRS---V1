import { isActionable } from "@/lib/validationCategories";

// Queue Signal Improvement — the actionability invariant.
//
// isActionable keys purely on suggested_action: a finding is a real
// remediation task in this queue iff the validator gave it a concrete
// suggested_action (which also names the workspace that changes output).
// Cross-source *_VERIFY_* findings are emitted with suggested_action=null
// (src/verification/engine.py findings_to_validation_issues) because they
// are already actionable as CorrectionRecords in the Corrections workspace.
//
// The fixtures below mirror the rules actually observed across the 10-doc
// benchmark corpus, with their real suggested_action presence, so this test
// locks the runtime invariant: actionable  <=>  not a _VERIFY_ rule.

const mk = (rule_id: string, suggested_action: string | null) => ({
  suggested_action,
  rule_id,
});

// Structural rules — every one carries a suggested_action at runtime.
const ACTIONABLE_RULES: Array<[string, string]> = [
  ["PAGE_003", "Review this page's content order."],
  ["PAGE_004", "Adjust page label sections so every label is unique."],
  ["HEADING_002", "Confirm the document has a clear title."],
  ["HEADING_004", "Confirm this repeated heading is intentional."],
  ["IMAGE_004", "Review and, if needed, replace the placeholder alt text."],
  ["IMAGE_005", "Inspect the image file for format issues."],
  ["META_001", "Set the document language in the Metadata panel."],
  ["META_002", "Set the document title in the Metadata panel."],
  ["TABLE_001", "Add a descriptive caption in the Tables workspace."],
  ["TABLE_002", "Add a prose summary in the Tables workspace."],
  ["TABLE_004", "Fill in the empty header cell."],
  ["DOC_004", "Confirm the surrounding text still reads correctly."],
];

// Cross-source verification rules — every one has suggested_action=null.
const VERIFY_RULES = [
  "HEADING_VERIFY_001",
  "HEADING_VERIFY_002",
  "HEADING_VERIFY_003",
  "HEADING_VERIFY_004",
  "HEADING_VERIFY_005",
  "IMAGE_VERIFY_002",
  "IMAGE_VERIFY_003",
  "IMAGE_VERIFY_006",
  "IMAGE_VERIFY_007",
  "IMAGE_VERIFY_008",
  "LIST_VERIFY_001",
  "LIST_VERIFY_002",
  "LIST_VERIFY_003",
  "TABLE_VERIFY_002",
  "TABLE_VERIFY_006",
  "TABLE_VERIFY_007",
  "FOOTNOTE_VERIFY_001",
];

describe("isActionable", () => {
  it("returns true exactly when a suggested_action is present", () => {
    expect(isActionable(mk("TABLE_001", "Add a caption."))).toBe(true);
    expect(isActionable(mk("HEADING_VERIFY_001", null))).toBe(false);
    // Empty string is not a real action.
    expect(isActionable(mk("SOMETHING", ""))).toBe(false);
  });

  it("treats every structural (non-_VERIFY_) corpus rule as actionable", () => {
    for (const [rule_id, action] of ACTIONABLE_RULES) {
      expect(isActionable(mk(rule_id, action))).toBe(true);
    }
  });

  it("treats every cross-source _VERIFY_ corpus rule as non-actionable", () => {
    for (const rule_id of VERIFY_RULES) {
      expect(isActionable(mk(rule_id, null))).toBe(false);
    }
  });

  it("holds the corpus invariant: actionable <=> not a _VERIFY_ rule", () => {
    const all = [
      ...ACTIONABLE_RULES.map(([r, a]) => mk(r, a)),
      ...VERIFY_RULES.map((r) => mk(r, null)),
    ];
    for (const issue of all) {
      expect(isActionable(issue)).toBe(!issue.rule_id.includes("_VERIFY_"));
    }
  });
});
