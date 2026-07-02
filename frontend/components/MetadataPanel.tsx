"use client";

import { useState } from "react";
import { api, type MetadataItem } from "@/lib/api";

interface Props {
  metadata: MetadataItem;
  jobId: string;
  onUpdated: (updated: MetadataItem) => void;
}

export function MetadataPanel({ metadata, jobId, onUpdated }: Props) {
  const [language, setLanguage] = useState(metadata.language ?? "");
  const [title, setTitle] = useState(metadata.title ?? "");
  const [author, setAuthor] = useState(metadata.author ?? "");
  const [subject, setSubject] = useState(metadata.subject ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isDirty =
    language !== (metadata.language ?? "") ||
    title !== (metadata.title ?? "") ||
    author !== (metadata.author ?? "") ||
    subject !== (metadata.subject ?? "");

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const updated = await api.updateMetadata(jobId, {
        language: language || null,
        title: title || null,
        author: author || null,
        subject: subject || null,
      });
      onUpdated(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-5 max-w-lg">
      <div>
        <p className="text-sm text-gray-600 mb-4">
          These properties are written into the DOCX file on export.
          Screen readers announce the title when opening the document,
          and use the language setting to select the correct voice.
        </p>

        {/* Stats row */}
        <div className="flex gap-4 text-sm text-gray-600 mb-5 pb-4 border-b">
          <span><span className="font-medium">{metadata.page_count}</span> pages</span>
          <span><span className="font-medium">{metadata.image_count}</span> images</span>
          <span className="text-gray-400 truncate">{metadata.filename}</span>
        </div>
      </div>

      {/* Language */}
      <div>
        <label htmlFor="meta-language" className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
          Language <span className="font-normal text-gray-400">(WCAG 3.1.1)</span>
        </label>
        <input
          id="meta-language"
          type="text"
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          placeholder="e.g. en-US, en-AU, fr-FR"
          className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          disabled={saving}
        />
        <p className="mt-1 text-xs text-gray-400">
          IETF BCP 47 tag. Screen readers select the correct speech synthesiser voice from this value.
        </p>
      </div>

      {/* Title */}
      <div>
        <label htmlFor="meta-title" className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
          Document Title <span className="font-normal text-gray-400">(WCAG 2.4.2)</span>
        </label>
        <input
          id="meta-title"
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. Annual Report 2024"
          className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          disabled={saving}
        />
        <p className="mt-1 text-xs text-gray-400">
          Screen readers announce this when the document is opened. Distinct from the H1 heading.
        </p>
      </div>

      {/* Author */}
      <div>
        <label htmlFor="meta-author" className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
          Author <span className="font-normal text-gray-400">(optional)</span>
        </label>
        <input
          id="meta-author"
          type="text"
          value={author}
          onChange={(e) => setAuthor(e.target.value)}
          placeholder="e.g. WinVinaya Foundation"
          className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          disabled={saving}
        />
      </div>

      {/* Subject */}
      <div>
        <label htmlFor="meta-subject" className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
          Subject <span className="font-normal text-gray-400">(optional)</span>
        </label>
        <input
          id="meta-subject"
          type="text"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="e.g. Accessibility, Education"
          className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          disabled={saving}
        />
      </div>

      {error && (
        <p className="text-sm text-red-600" role="alert">{error}</p>
      )}

      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving || !isDirty}
          className="rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save metadata"}
        </button>
        {saved && (
          <p className="text-sm text-green-700" role="status">Saved. Will be written to DOCX on next export.</p>
        )}
      </div>
    </div>
  );
}
