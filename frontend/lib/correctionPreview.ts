// Phase RW-1: some verifiers (footnotes/headings/lists/tables — confirmed
// via direct grep across src/verification/*.py) encode a structured
// payload as a JSON string into CorrectionItem.current_value/
// suggested_value rather than a plain string, because a single corrected
// value isn't always a scalar (a missing footnote needs a marker +
// insertion point + body, not just one string). Rendered as-is, that raw
// JSON string was the first thing a reviewer saw — this parses it back
// into a small, ordered, friendly field list instead. Detected by key
// shape, not by object_type/field name matching, so it degrades safely
// (returns null -> caller falls back to the plain string) for every
// value that isn't one of these known shapes, rather than breaking if a
// verifier's field names change.

export interface PreviewField {
  label: string;
  value: string;
}

export interface CorrectionPreview {
  /** Short, reviewer-facing headline for this correction shape, e.g. "Missing footnote". */
  kind: string;
  fields: PreviewField[];
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function tryParseJson(raw: string): Record<string, unknown> | null {
  const trimmed = raw.trim();
  if (!trimmed.startsWith("{")) return null;
  try {
    const parsed: unknown = JSON.parse(trimmed);
    return isPlainObject(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function str(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

function humanizeKey(key: string): string {
  return key
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/** Footnote/endnote missing entirely from the Mathpix package (src/verification/footnotes.py _encode_footnote). */
function previewMissingFootnote(data: Record<string, unknown>): CorrectionPreview {
  const fields: PreviewField[] = [];
  if (data.marker != null) fields.push({ label: "Marker", value: str(data.marker) });
  if (data.anchor_text) fields.push({ label: "Insert after", value: `"${str(data.anchor_text)}"` });
  if (data.body) fields.push({ label: "Suggested content", value: str(data.body) });
  return { kind: data.note_type === "endnote" ? "Missing endnote" : "Missing footnote", fields };
}

/** Footnote/endnote anchor page disagreement (src/verification/footnotes.py _encode_anchor). */
function previewFootnoteAnchor(data: Record<string, unknown>): CorrectionPreview {
  const fields: PreviewField[] = [];
  if (data.anchor_page_number != null) {
    fields.push({ label: "Suggested page", value: str(data.anchor_page_number) });
  }
  if (data.anchor_text) fields.push({ label: "Anchor text", value: `"${str(data.anchor_text)}"` });
  return { kind: "Footnote anchor position", fields };
}

/** Heading recovered from the PDF but missing from the Mathpix package (src/verification/headings.py). */
function previewHeading(data: Record<string, unknown>): CorrectionPreview {
  const fields: PreviewField[] = [];
  if (data.level != null) fields.push({ label: "Heading level", value: `H${str(data.level)}` });
  if (data.text) fields.push({ label: "Text", value: str(data.text) });
  if (data.page_number != null) fields.push({ label: "Page", value: str(data.page_number) });
  return { kind: "Missing heading", fields };
}

/** List recovered from the PDF but missing from the Mathpix package (src/verification/lists.py). */
function previewList(data: Record<string, unknown>): CorrectionPreview {
  const fields: PreviewField[] = [];
  const items = Array.isArray(data.items) ? data.items : [];
  if (data.list_type) fields.push({ label: "List type", value: str(data.list_type) });
  fields.push({ label: "Items", value: `${items.length} item${items.length === 1 ? "" : "s"}` });
  const preview = items
    .slice(0, 3)
    .map((item) => (isPlainObject(item) ? str(item.text) : str(item)))
    .filter(Boolean)
    .join("; ");
  if (preview) fields.push({ label: "Preview", value: items.length > 3 ? `${preview}; …` : preview });
  if (data.page_number != null) fields.push({ label: "Page", value: str(data.page_number) });
  return { kind: "Missing list", fields };
}

/**
 * Table repair (src/verification/tables.py) — full row data is
 * deliberately excluded from the friendly preview (too large to
 * summarize meaningfully inline); available in Developer Details.
 */
function previewTable(data: Record<string, unknown>): CorrectionPreview {
  const fields: PreviewField[] = [];
  if (data.caption) fields.push({ label: "Caption", value: str(data.caption) });
  if (data.row_count != null && data.col_count != null) {
    fields.push({ label: "Table size", value: `${str(data.row_count)} rows × ${str(data.col_count)} columns` });
  }
  return { kind: "Table structure repair", fields };
}

/**
 * Attempts to recognize a structured JSON payload in a CorrectionItem's
 * current_value/suggested_value and render it as a short, friendly field
 * list. Returns null when the value is a plain string (the common case
 * for most object types — image alt text, page-label text, metadata
 * fields) so the caller falls back to showing it as-is.
 */
export function parseCorrectionPayload(raw: string): CorrectionPreview | null {
  if (!raw) return null;
  const data = tryParseJson(raw);
  if (!data) return null;

  if ("body" in data && "marker" in data) return previewMissingFootnote(data);
  if ("anchor_page_number" in data && "anchor_text" in data && !("body" in data)) return previewFootnoteAnchor(data);
  if ("level" in data && "text" in data && "page_number" in data) return previewHeading(data);
  if ("list_type" in data && "items" in data) return previewList(data);
  if ("row_count" in data && "col_count" in data) return previewTable(data);

  // Unrecognized structured shape — still real JSON, still shouldn't be
  // dumped raw. Falls back to a generic key/value field list rather than
  // one of the five named shapes above.
  return {
    kind: "Structured suggestion",
    fields: Object.entries(data)
      .filter(([, v]) => typeof v === "string" || typeof v === "number" || typeof v === "boolean")
      .map(([k, v]) => ({ label: humanizeKey(k), value: str(v) })),
  };
}
