"use client";

import { useState } from "react";
import { api, type AiStatus, type ImageItem, type ReviewAction } from "@/lib/api";
import { AiUnavailableBadge, AltTextStatusBadge } from "./Badge";
import { ObjectInspectorFrame } from "./workspace/ObjectInspectorFrame";
import { CorrectionHistoryList } from "./CorrectionHistoryList";
import { useObjectInspectorContext } from "@/lib/store/useObjectInspectorContext";
import { useDocumentDispatch } from "@/lib/store/DocumentDataContext";

interface Props {
  image: ImageItem;
  jobId: string;
  aiStatus: AiStatus | null;
  onClose: () => void;
  onActionComplete: (updated: ImageItem) => void;
}

export function ImageDetailPanel({ image, jobId, aiStatus, onClose, onActionComplete }: Props) {
  const { corrections, documentVersion } = useObjectInspectorContext("figure", image.image_id, image.page_number);
  const dispatch = useDocumentDispatch();
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

  const header = (
    <div className="flex items-start justify-between gap-2">
      <div>
        <p className="text-sm font-semibold text-text-primary">
          {figure?.label ? `${figure.label}` : `Image — Page ${image.page_number}`}
        </p>
        <p className="text-xs text-text-secondary">Page {image.page_number}</p>
      </div>
      <button
        type="button"
        onClick={onClose}
        className="text-text-secondary hover:text-text-primary text-sm font-medium"
        aria-label="Close detail panel"
      >
        ✕
      </button>
    </div>
  );

  return (
    <ObjectInspectorFrame
      header={header}
      metadata={
        <div className="space-y-4">
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
      {error && <p className="text-xs text-danger">{error}</p>}
        </div>
      }
      correctionHistory={
        <CorrectionHistoryList
          corrections={corrections}
          jobId={jobId}
          onUpdated={(updated) => dispatch({ type: "UPDATE_CORRECTION", correction: updated })}
          emptyMessage="No cross-source corrections proposed for this figure."
        />
      }
      version={
        documentVersion !== null ? (
          <p className="text-sm text-text-secondary">As of Document v{documentVersion}</p>
        ) : undefined
      }
      actions={
        <>
          {canGenerate && aiStatus && !aiStatus.available && (
            <AiUnavailableBadge reason={aiStatus.unavailable_reason} />
          )}
          {canGenerate && (!aiStatus || aiStatus.available) && (
            <button
              type="button"
              className="rounded bg-accent px-3 py-1.5 text-xs font-medium text-accent-contrast hover:opacity-90 disabled:opacity-50"
              onClick={handleGenerate}
              disabled={loading}
            >
              {loading ? "Generating…" : figure?.ai_description ? "Re-generate AI Alt Text" : "Generate AI Alt Text"}
            </button>
          )}
          {status === "ai_generated" && (
            <button
              type="button"
              className="rounded border border-danger/40 px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger/10 disabled:opacity-50"
              onClick={() => handleAction("reject")}
              disabled={loading}
            >
              Reject
            </button>
          )}
          <button
            type="button"
            className="rounded border border-border px-3 py-1.5 text-xs font-medium text-text-secondary hover:bg-hover-row disabled:opacity-50"
            onClick={() => handleAction("mark_decorative")}
            disabled={loading}
          >
            Mark Decorative
          </button>
          <button
            type="button"
            className="rounded border border-border px-3 py-1.5 text-xs font-medium text-text-secondary hover:bg-hover-row disabled:opacity-50"
            onClick={() => handleAction("mark_complex")}
            disabled={loading}
          >
            Mark Complex
          </button>
          <button
            type="button"
            className="rounded border border-border px-3 py-1.5 text-xs font-medium text-text-secondary hover:bg-hover-row disabled:opacity-50"
            onClick={() => handleAction("skip")}
            disabled={loading}
          >
            Skip
          </button>
        </>
      }
    />
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
