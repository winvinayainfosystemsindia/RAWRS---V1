"use client";

import { useMemo, useState } from "react";
import { api, type AiStatus, type ImageItem } from "@/lib/api";
import { ImageCard } from "./ImageCard";
import { ImageDetailPanel } from "./ImageDetailPanel";
import { BulkActions } from "./BulkActions";
import { AiUnavailableBadge } from "./Badge";

interface Props {
  images: ImageItem[];
  jobId: string;
  aiStatus: AiStatus | null;
  onImagesUpdated: (updated: ImageItem[]) => void;
}

// ponytail: threshold picked from typical print-figure DPI, not measured —
// tune if reviewers report false positives/negatives on real documents.
const LOW_RES_THRESHOLD_PX = 150;

type ImageFilter = "all" | "missing" | "needs_review" | "accepted" | "rejected" | "decorative" | "low_res";

const FILTERS: { id: ImageFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "missing", label: "Missing Alt Text" },
  { id: "needs_review", label: "Needs Review" },
  { id: "accepted", label: "Accepted" },
  { id: "rejected", label: "Rejected" },
  { id: "decorative", label: "Decorative" },
  { id: "low_res", label: "Low Resolution" },
];

function isLowRes(image: ImageItem): boolean {
  return (
    image.width !== null &&
    image.height !== null &&
    (image.width < LOW_RES_THRESHOLD_PX || image.height < LOW_RES_THRESHOLD_PX)
  );
}

function matchesFilter(image: ImageItem, filter: ImageFilter): boolean {
  const status = image.figure?.alt_text_status ?? null;
  switch (filter) {
    case "all": return true;
    case "missing": return status === null || status === "pending_review" || status === "skipped";
    case "needs_review": return status === "ai_generated" || status === "complex";
    case "accepted": return status === "approved" || status === "human_reviewed";
    case "rejected": return status === "rejected";
    case "decorative": return status === "decorative";
    case "low_res": return isLowRes(image);
  }
}

// Whole-document AI generation isn't a real backend bulk endpoint — it's a
// client-side loop over the existing per-image generate-alt-text call.
// "Generate Missing" targets never-generated images; "Generate Entire
// Document" additionally re-runs anything not yet human-finalized
// (approved/human_reviewed/decorative are left alone — never overwrite a
// reviewer's decision).
function targetsFor(images: ImageItem[], mode: "missing" | "whole_document"): ImageItem[] {
  return images.filter((img) => {
    if (img.extraction_failed) return false;
    const status = img.figure?.alt_text_status ?? null;
    if (mode === "missing") return status === null || status === "pending_review" || status === "skipped";
    return status !== "approved" && status !== "human_reviewed" && status !== "decorative";
  });
}

function GenerationToolbar({
  images,
  jobId,
  aiStatus,
  onImagesUpdated,
}: {
  images: ImageItem[];
  jobId: string;
  aiStatus: AiStatus | null;
  onImagesUpdated: (updated: ImageItem[]) => void;
}) {
  const [running, setRunning] = useState<{ done: number; total: number } | null>(null);
  const [failedIds, setFailedIds] = useState<string[]>([]);

  async function runBatch(targets: ImageItem[]) {
    if (targets.length === 0) return;
    setRunning({ done: 0, total: targets.length });
    const failures: string[] = [];
    const updatesById = new Map<string, ImageItem>();
    for (const img of targets) {
      try {
        updatesById.set(img.image_id, await api.generateAltText(jobId, img.image_id));
      } catch {
        failures.push(img.image_id);
      }
      setRunning((prev) => (prev ? { ...prev, done: prev.done + 1 } : prev));
    }
    // onImagesUpdated replaces the whole document's image list (REPLACE_IMAGES
    // in DocumentDataContext), so merge into the full set rather than sending
    // just the batch — otherwise every image outside this batch disappears.
    if (updatesById.size > 0) {
      onImagesUpdated(images.map((img) => updatesById.get(img.image_id) ?? img));
    }
    setFailedIds(failures);
    setRunning(null);
  }

  const missingCount = targetsFor(images, "missing").length;
  const wholeDocCount = targetsFor(images, "whole_document").length;
  const aiUnavailable = aiStatus && !aiStatus.available;

  if (aiUnavailable) {
    return (
      <div className="flex items-center gap-2">
        <AiUnavailableBadge reason={aiStatus.unavailable_reason} />
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => runBatch(targetsFor(images, "missing"))}
        disabled={!!running || missingCount === 0}
        className="rounded bg-accent px-3 py-1.5 text-xs font-medium text-accent-contrast hover:opacity-90 disabled:opacity-50"
      >
        Generate Missing ({missingCount})
      </button>
      <button
        type="button"
        onClick={() => runBatch(targetsFor(images, "whole_document"))}
        disabled={!!running || wholeDocCount === 0}
        className="rounded bg-surface-elevated px-3 py-1.5 text-xs font-medium text-text-primary ring-1 ring-border hover:bg-hover-row disabled:opacity-50"
      >
        Generate Entire Document ({wholeDocCount})
      </button>
      {failedIds.length > 0 && !running && (
        <button
          type="button"
          onClick={() => runBatch(images.filter((img) => failedIds.includes(img.image_id)))}
          className="rounded border border-danger/40 px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger/10"
        >
          Retry Failed ({failedIds.length})
        </button>
      )}
      {running && (
        <span className="text-xs text-text-secondary">
          Generating {running.done}/{running.total}…
        </span>
      )}
    </div>
  );
}

export function ImageGrid({ images, jobId, aiStatus, onImagesUpdated }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<ImageFilter>("all");

  const filteredImages = useMemo(
    () => images.filter((img) => matchesFilter(img, filter)),
    [images, filter]
  );

  if (images.length === 0) {
    return <p className="text-sm text-text-secondary">No images were retained from this document.</p>;
  }

  function handleActionComplete(updated: ImageItem) {
    onImagesUpdated(images.map((img) => (img.image_id === updated.image_id ? updated : img)));
    // Keep the detail panel open on the same image (now with fresh data).
  }

  function handleBulkComplete(updatedAll: ImageItem[]) {
    onImagesUpdated(updatedAll);
  }

  function toggleChecked(imageId: string, checked: boolean) {
    setCheckedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(imageId);
      else next.delete(imageId);
      return next;
    });
  }

  const selectedImage = selectedId ? images.find((img) => img.image_id === selectedId) ?? null : null;

  return (
    <div className="space-y-4">
      {/* Doc-wide AI generation — operates on all images matching a rule,
          not just checked ones (see targetsFor above). */}
      <GenerationToolbar
        images={images}
        jobId={jobId}
        aiStatus={aiStatus}
        onImagesUpdated={onImagesUpdated}
      />

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-1.5">
        {FILTERS.map((f) => {
          const count = images.filter((img) => matchesFilter(img, f.id)).length;
          return (
            <button
              key={f.id}
              type="button"
              onClick={() => setFilter(f.id)}
              className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                filter === f.id
                  ? "bg-accent text-accent-contrast"
                  : "bg-surface-elevated text-text-secondary ring-1 ring-border hover:bg-hover-row"
              }`}
            >
              {f.label} ({count})
            </button>
          );
        })}
      </div>

      {/* Bulk action toolbar — only visible when images are checked */}
      <BulkActions
        jobId={jobId}
        selectedIds={Array.from(checkedIds)}
        onClearSelection={() => setCheckedIds(new Set())}
        onActionComplete={handleBulkComplete}
      />

      <div className="flex flex-col gap-4">
        {/* Image grid */}
        <div className={selectedImage ? "w-full max-h-64 overflow-y-auto" : "w-full"}>
          {filteredImages.length === 0 ? (
            <p className="text-sm text-text-secondary py-4">No images match this filter.</p>
          ) : (
          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filteredImages.map((image) => (
              <ImageCard
                key={image.image_id}
                image={image}
                jobId={jobId}
                aiStatus={aiStatus}
                isSelected={selectedId === image.image_id}
                onSelect={() =>
                  setSelectedId((prev) => (prev === image.image_id ? null : image.image_id))
                }
                onActionComplete={handleActionComplete}
                isChecked={checkedIds.has(image.image_id)}
                onCheckedChange={(checked) => toggleChecked(image.image_id, checked)}
              />
            ))}
          </ul>
          )}
        </div>

        {/* Detail panel — shown when an image is selected */}
        {selectedImage && (
          <div className="w-full">
            <ImageDetailPanel
              key={selectedImage.image_id}
              image={selectedImage}
              jobId={jobId}
              aiStatus={aiStatus}
              onClose={() => setSelectedId(null)}
              onActionComplete={handleActionComplete}
            />
          </div>
        )}
      </div>
    </div>
  );
}
