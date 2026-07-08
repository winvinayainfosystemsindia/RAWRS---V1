"use client";

import { useState } from "react";
import {
  api,
  type PageLabel,
  type PageLabelSection,
  type PageLabelSectionRequest,
  type PageLabelStatus,
  type PageLabelStyle,
} from "@/lib/api";

interface Props {
  jobId: string;
  pages: PageLabel[];
  sections: PageLabelSection[];
  onUpdated: (updated: { pages: PageLabel[]; sections: PageLabelSection[] }) => void;
}

function statusLabel(status: PageLabelStatus): string {
  switch (status) {
    case "detected": return "Detected";
    case "approved": return "Approved";
    case "overridden": return "Overridden";
  }
}

function statusColor(status: PageLabelStatus): string {
  switch (status) {
    case "detected": return "bg-yellow-100 text-yellow-800";
    case "approved": return "bg-green-100 text-green-800";
    case "overridden": return "bg-blue-100 text-blue-800";
  }
}

const STYLE_OPTIONS: { value: PageLabelStyle; label: string }[] = [
  { value: "arabic", label: "Arabic (1, 2, 3…)" },
  { value: "roman_lower", label: "Roman lower (i, ii, iii…)" },
  { value: "roman_upper", label: "Roman upper (I, II, III…)" },
  { value: "none", label: "None (no label)" },
];

function SectionForm({
  jobId,
  sections,
  onApplied,
}: {
  jobId: string;
  sections: PageLabelSection[];
  onApplied: (result: { pages: PageLabel[]; sections: PageLabelSection[] }) => void;
}) {
  const [startPage, setStartPage] = useState(1);
  const [endPage, setEndPage] = useState(1);
  const [style, setStyle] = useState<PageLabelStyle>("arabic");
  const [startNumber, setStartNumber] = useState(1);
  const [prefix, setPrefix] = useState("");
  const [suffix, setSuffix] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleApply() {
    setSaving(true);
    setError(null);
    try {
      const next: PageLabelSectionRequest[] = [
        ...sections,
        { start_page: startPage, end_page: endPage, style, start_number: startNumber, prefix, suffix },
      ];
      const result = await api.setPageLabelSections(jobId, next);
      onApplied(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to apply section.");
    } finally {
      setSaving(false);
    }
  }

  async function handleRemove(index: number) {
    setSaving(true);
    setError(null);
    try {
      const next = sections.filter((_, i) => i !== index);
      const result = await api.setPageLabelSections(jobId, next);
      onApplied(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove section.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-3">
      <h3 className="text-sm font-semibold text-gray-800">Bulk numbering (add a section)</h3>
      <p className="text-xs text-gray-500">
        Applies to every page in the range. Covers offset (shift start number), restart numbering
        (a new section mid-document), roman numerals, and prefixes/suffixes — all via the fields below.
      </p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <label className="text-xs text-gray-600">
          Start page
          <input
            type="number"
            min={1}
            value={startPage}
            onChange={(e) => setStartPage(Number(e.target.value))}
            className="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm"
          />
        </label>
        <label className="text-xs text-gray-600">
          End page
          <input
            type="number"
            min={1}
            value={endPage}
            onChange={(e) => setEndPage(Number(e.target.value))}
            className="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm"
          />
        </label>
        <label className="text-xs text-gray-600">
          Style
          <select
            value={style}
            onChange={(e) => setStyle(e.target.value as PageLabelStyle)}
            className="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm"
          >
            {STYLE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </label>
        <label className="text-xs text-gray-600">
          Start number
          <input
            type="number"
            value={startNumber}
            onChange={(e) => setStartNumber(Number(e.target.value))}
            className="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm"
          />
        </label>
        <label className="text-xs text-gray-600">
          Prefix
          <input
            type="text"
            value={prefix}
            onChange={(e) => setPrefix(e.target.value)}
            className="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm"
          />
        </label>
        <label className="text-xs text-gray-600">
          Suffix
          <input
            type="text"
            value={suffix}
            onChange={(e) => setSuffix(e.target.value)}
            className="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm"
          />
        </label>
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
      <button
        type="button"
        onClick={handleApply}
        disabled={saving}
        className="rounded px-3 py-1.5 text-xs font-semibold bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
      >
        {saving ? "Applying…" : "Add section"}
      </button>

      {sections.length > 0 && (
        <ul className="mt-2 space-y-1.5">
          {sections.map((s, i) => (
            <li
              key={i}
              className="flex items-center justify-between gap-2 rounded border border-gray-200 px-2.5 py-1.5 text-xs text-gray-700"
            >
              <span>
                Pages {s.start_page}–{s.end_page}: {STYLE_OPTIONS.find((o) => o.value === s.style)?.label}
                {s.start_number !== 1 ? `, starts at ${s.start_number}` : ""}
                {s.prefix ? `, prefix "${s.prefix}"` : ""}
                {s.suffix ? `, suffix "${s.suffix}"` : ""}
              </span>
              <button
                type="button"
                onClick={() => handleRemove(i)}
                disabled={saving}
                className="text-gray-400 hover:text-red-600 disabled:opacity-40"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PageRow({
  jobId,
  page,
  onUpdated,
}: {
  jobId: string;
  page: PageLabel;
  onUpdated: (updated: PageLabel) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(page.page_label ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.overridePageLabel(jobId, page.page_number, value);
      onUpdated(updated);
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function handleReset() {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.resetPageLabel(jobId, page.page_number);
      onUpdated(updated);
      setValue(updated.page_label ?? "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reset failed.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <li className="flex flex-col gap-1.5 rounded-lg border border-gray-200 bg-white p-2.5">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-900">Page {page.page_number}</span>
          <span className="text-xs text-gray-500">
            detected: {page.printed_label ?? "—"}
          </span>
          <span className="text-sm text-gray-800">→ {page.page_label ?? "(none)"}</span>
        </div>
        <div className="flex items-center gap-1.5">
          {page.label_conflict && (
            <span
              title="Multiple conflicting candidates were detected on this page"
              className="inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium bg-red-100 text-red-800"
            >
              Conflict
            </span>
          )}
          {page.label_confidence === null && !page.printed_label && (
            <span className="text-[11px] text-gray-400">no detection</span>
          )}
          <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium ${statusColor(page.page_label_status)}`}>
            {statusLabel(page.page_label_status)}
          </span>
          <button
            type="button"
            onClick={() => setEditing((v) => !v)}
            className="rounded px-2 py-1 text-xs text-gray-600 hover:bg-gray-100"
          >
            {editing ? "Cancel" : "Override"}
          </button>
          {page.page_label_status === "overridden" && (
            <button
              type="button"
              onClick={handleReset}
              disabled={saving}
              className="rounded px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-40"
            >
              Reset
            </button>
          )}
        </div>
      </div>
      {editing && (
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="rounded border border-gray-300 px-2 py-1 text-sm"
            placeholder="New label"
          />
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !value}
            className="rounded px-3 py-1 text-xs font-semibold bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      )}
      {error && <p className="text-xs text-red-600">{error}</p>}
    </li>
  );
}

export function PageLabelManagerPanel({ jobId, pages, sections, onUpdated }: Props) {
  function handleSectionsApplied(result: { pages: PageLabel[]; sections: PageLabelSection[] }) {
    onUpdated(result);
  }

  function handlePageUpdated(updated: PageLabel) {
    onUpdated({
      pages: pages.map((p) => (p.page_number === updated.page_number ? updated : p)),
      sections,
    });
  }

  const conflictCount = pages.filter((p) => p.label_conflict).length;
  const overriddenCount = pages.filter((p) => p.page_label_status === "overridden").length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3 text-xs text-gray-600">
        <span>{pages.length} page{pages.length !== 1 ? "s" : ""}</span>
        {conflictCount > 0 && <span className="text-red-700">{conflictCount} with conflicting detection</span>}
        {overriddenCount > 0 && <span className="text-blue-700">{overriddenCount} manually overridden</span>}
      </div>

      <SectionForm jobId={jobId} sections={sections} onApplied={handleSectionsApplied} />

      <ul className="space-y-1.5">
        {pages.map((page) => (
          <PageRow key={page.page_number} jobId={jobId} page={page} onUpdated={handlePageUpdated} />
        ))}
      </ul>
    </div>
  );
}
