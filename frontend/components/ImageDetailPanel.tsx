"use client";

import { useState } from "react";
import { api, type ImageItem, type ReviewAction } from "@/lib/api";
import { AltTextStatusBadge } from "./Badge";

interface Props {
  image: ImageItem;
  jobId: string;
  onClose: () => void;
  onActionComplete: (updated: ImageItem) => void;
}

export function ImageDetailPanel({ image, jobId, onClose, onActionComplete }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editText, setEditText] = useState(image.figure?.alt_text ?? "");

  const figure = image.figure;
  const status = figure?.alt_text_status ?? null;

  async function handleGenerate() {
    setLoading(true);
    setError(null);
    try {
      const updated = await api.generateAltText(jobId, image.image_id);
      onActionComplete(updated);
      setEditText(updated.figure?.alt_text ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleAction(action: ReviewAction, altText?: string) {
    setLoading(true);
    setError(null);
    try {
      const updated = await api.reviewImage(jobId, image.image_id, action, altText);
      onActionComplete(updated);
      setEditText(updated.figure?.alt_text ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setLoading(false);
    }
  }

  const canGenerate =
    !status ||
    status === "pending_review" ||
    status === "rejected" ||
    status === "skipped" ||
    status === "decorative" ||
    status === "complex";

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-gray-900">
            {figure?.label ? `${figure.label}` : `Image — Page ${image.page_number}`}
          </p>
          <p className="text-xs text-gray-500">Page {image.page_number}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 text-sm font-medium"
          aria-label="Close detail panel"
        >
          ✕
        </button>
      </div>

      {/* Preview */}
      {image.url && (
        <div className="flex items-center justify-center rounded-md bg-gray-50 overflow-hidden max-h-64">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={image.url.startsWith("http") ? image.url : `${api.baseUrl}${image.url}`}
            alt={figure?.alt_text ?? `Image from page ${image.page_number}`}
            className="max-h-64 max-w-full object-contain"
          />
        </div>
      )}

      {/* Caption */}
      {figure?.caption && (
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Caption</p>
          <p className="text-sm text-gray-800">{figure.caption}</p>
        </div>
      )}

      {/* Current alt text (editable) */}
      <div>
        <label htmlFor="alt-text-edit" className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
          Alt Text
        </label>
        <AltTextStatusBadge status={status} />
        <textarea
          id="alt-text-edit"
          className="mt-2 w-full rounded border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          rows={3}
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          placeholder="Enter alt text…"
          disabled={loading}
        />
        <div className="mt-1.5 flex gap-2">
          <button
            type="button"
            className="rounded bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50"
            onClick={() => handleAction("approve", editText)}
            disabled={loading || !editText.trim()}
          >
            Approve this text
          </button>
          <button
            type="button"
            className="rounded bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-700 ring-1 ring-gray-300 hover:bg-gray-200 disabled:opacity-50"
            onClick={() => handleAction("edit", editText)}
            disabled={loading || !editText.trim()}
          >
            Save as draft
          </button>
        </div>
      </div>

      {/* AI analysis */}
      {figure?.ai_description && (
        <div className="rounded-md bg-blue-50 p-3 space-y-2">
          <p className="text-xs font-semibold text-blue-900 uppercase tracking-wide">AI Analysis</p>
          <DetailRow label="Description" value={figure.ai_description} />
          <DetailRow label="Purpose" value={figure.ai_purpose} />
          <DetailRow label="Visible Text" value={figure.ai_visible_text} />
          {figure.ai_confidence !== null && (
            <div>
              <p className="text-xs font-medium text-blue-800 mb-0.5">Confidence</p>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-2 rounded-full bg-blue-200 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-blue-600"
                    style={{ width: `${Math.round((figure.ai_confidence ?? 0) * 100)}%` }}
                  />
                </div>
                <span className="text-xs text-blue-700 shrink-0">
                  {Math.round((figure.ai_confidence ?? 0) * 100)}%
                </span>
              </div>
            </div>
          )}
          {figure.ai_warnings.length > 0 && (
            <div>
              <p className="text-xs font-medium text-amber-800 mb-0.5">Warnings</p>
              <ul className="list-disc list-inside space-y-0.5">
                {figure.ai_warnings.map((w, i) => (
                  <li key={i} className="text-xs text-amber-700">{w}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {error && <p className="text-xs text-red-600">{error}</p>}

      {/* Action row */}
      <div className="flex flex-wrap gap-2 border-t pt-3">
        {canGenerate && (
          <button
            type="button"
            className="rounded bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            onClick={handleGenerate}
            disabled={loading}
          >
            {loading ? "Generating…" : figure?.ai_description ? "Re-generate AI Alt Text" : "Generate AI Alt Text"}
          </button>
        )}
        {status === "ai_generated" && (
          <button
            type="button"
            className="rounded bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
            onClick={() => handleAction("reject")}
            disabled={loading}
          >
            Reject
          </button>
        )}
        <button
          type="button"
          className="rounded bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-700 ring-1 ring-gray-300 hover:bg-gray-200 disabled:opacity-50"
          onClick={() => handleAction("mark_decorative")}
          disabled={loading}
        >
          Mark Decorative
        </button>
        <button
          type="button"
          className="rounded bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-700 ring-1 ring-gray-300 hover:bg-gray-200 disabled:opacity-50"
          onClick={() => handleAction("mark_complex")}
          disabled={loading}
        >
          Mark Complex
        </button>
        <button
          type="button"
          className="rounded bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-700 ring-1 ring-gray-300 hover:bg-gray-200 disabled:opacity-50"
          onClick={() => handleAction("skip")}
          disabled={loading}
        >
          Skip
        </button>
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div>
      <p className="text-xs font-medium text-blue-800 mb-0.5">{label}</p>
      <p className="text-xs text-blue-900">{value}</p>
    </div>
  );
}
