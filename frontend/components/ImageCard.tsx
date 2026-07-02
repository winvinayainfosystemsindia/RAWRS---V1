"use client";

import { useState } from "react";
import { api, type ImageItem, type ReviewAction } from "@/lib/api";
import { AltTextStatusBadge } from "./Badge";

function resolveImageUrl(url: string, baseUrl: string): string {
  return url.startsWith("http") ? url : `${baseUrl}${url}`;
}

interface Props {
  image: ImageItem;
  jobId: string;
  isSelected: boolean;
  onSelect: () => void;
  onActionComplete: (updated: ImageItem) => void;
  isChecked: boolean;
  onCheckedChange: (checked: boolean) => void;
}

export function ImageCard({
  image,
  jobId,
  isSelected,
  onSelect,
  onActionComplete,
  isChecked,
  onCheckedChange,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const status = image.figure?.alt_text_status ?? null;

  async function handleGenerate(e: React.MouseEvent) {
    e.stopPropagation();
    setLoading(true);
    setError(null);
    try {
      const updated = await api.generateAltText(jobId, image.image_id);
      onActionComplete(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleAction(e: React.MouseEvent, action: ReviewAction, altText?: string) {
    e.stopPropagation();
    setLoading(true);
    setError(null);
    try {
      const updated = await api.reviewImage(jobId, image.image_id, action, altText);
      onActionComplete(updated);
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

  const canApprove = status === "ai_generated";
  const canReject = status === "ai_generated";
  const canRegenerate = status === "approved" || status === "rejected";

  return (
    <li
      className={`rounded-lg border p-3 cursor-pointer transition-colors ${
        isSelected
          ? "border-blue-500 bg-blue-50"
          : "border-gray-200 hover:border-gray-300 bg-white"
      }`}
      onClick={onSelect}
    >
      {/* Checkbox + preview */}
      <div className="flex items-start gap-2 mb-2">
        <input
          type="checkbox"
          checked={isChecked}
          onChange={(e) => {
            e.stopPropagation();
            onCheckedChange(e.target.checked);
          }}
          className="mt-1 shrink-0"
          aria-label={`Select image on page ${image.page_number}`}
        />
        <div className="flex-1 flex aspect-[4/3] items-center justify-center overflow-hidden rounded-md bg-gray-50">
          {image.url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={resolveImageUrl(image.url, api.baseUrl)}
              alt={image.figure?.alt_text ?? `Image extracted from page ${image.page_number}`}
              className="max-h-full max-w-full object-contain"
            />
          ) : (
            <span className="text-xs text-gray-400">Extraction failed</span>
          )}
        </div>
      </div>

      {/* Metadata */}
      <div className="space-y-1 mb-2">
        <p className="text-xs text-gray-500">Page {image.page_number}</p>
        {image.figure?.caption && (
          <p className="text-sm font-medium text-gray-900 line-clamp-2">{image.figure.caption}</p>
        )}
        <AltTextStatusBadge status={status} />
      </div>

      {/* Error */}
      {error && (
        <p className="text-xs text-red-600 mb-2">{error}</p>
      )}

      {/* Action buttons */}
      {!image.extraction_failed && (
        <div className="flex flex-wrap gap-1.5">
          {canGenerate && (
            <ActionButton onClick={handleGenerate} loading={loading} variant="primary">
              Generate AI Alt Text
            </ActionButton>
          )}
          {canApprove && (
            <ActionButton
              onClick={(e) => handleAction(e, "approve", image.figure?.ai_description ?? undefined)}
              loading={loading}
              variant="success"
            >
              Approve
            </ActionButton>
          )}
          {canReject && (
            <ActionButton onClick={(e) => handleAction(e, "reject")} loading={loading} variant="danger">
              Reject
            </ActionButton>
          )}
          {canRegenerate && (
            <ActionButton onClick={handleGenerate} loading={loading} variant="primary">
              Re-generate
            </ActionButton>
          )}
          {status !== "decorative" && (
            <ActionButton onClick={(e) => handleAction(e, "mark_decorative")} loading={loading} variant="neutral">
              Decorative
            </ActionButton>
          )}
          {status !== "skipped" && status !== "approved" && status !== "decorative" && (
            <ActionButton onClick={(e) => handleAction(e, "skip")} loading={loading} variant="neutral">
              Skip
            </ActionButton>
          )}
        </div>
      )}
    </li>
  );
}

function ActionButton({
  onClick,
  loading,
  variant,
  children,
}: {
  onClick: (e: React.MouseEvent) => void;
  loading: boolean;
  variant: "primary" | "success" | "danger" | "neutral";
  children: React.ReactNode;
}) {
  const base =
    "inline-flex items-center rounded px-2 py-1 text-xs font-medium transition-opacity disabled:opacity-50";
  const styles: Record<string, string> = {
    primary: "bg-blue-600 text-white hover:bg-blue-700",
    success: "bg-green-600 text-white hover:bg-green-700",
    danger: "bg-red-600 text-white hover:bg-red-700",
    neutral: "bg-gray-100 text-gray-700 ring-1 ring-gray-300 hover:bg-gray-200",
  };
  return (
    <button
      type="button"
      className={`${base} ${styles[variant]}`}
      onClick={onClick}
      disabled={loading}
    >
      {loading ? "…" : children}
    </button>
  );
}
