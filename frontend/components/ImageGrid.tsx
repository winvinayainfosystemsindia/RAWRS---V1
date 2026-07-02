"use client";

import { useState } from "react";
import { type ImageItem } from "@/lib/api";
import { ImageCard } from "./ImageCard";
import { ImageDetailPanel } from "./ImageDetailPanel";
import { BulkActions } from "./BulkActions";

interface Props {
  images: ImageItem[];
  jobId: string;
  onImagesUpdated: (updated: ImageItem[]) => void;
}

export function ImageGrid({ images, jobId, onImagesUpdated }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());

  if (images.length === 0) {
    return <p className="text-sm text-gray-600">No images were retained from this document.</p>;
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
      {/* Bulk action toolbar — only visible when images are checked */}
      <BulkActions
        jobId={jobId}
        selectedIds={Array.from(checkedIds)}
        onClearSelection={() => setCheckedIds(new Set())}
        onActionComplete={handleBulkComplete}
      />

      <div className="flex gap-4 items-start">
        {/* Image grid */}
        <div className={selectedImage ? "flex-1 min-w-0" : "w-full"}>
          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {images.map((image) => (
              <ImageCard
                key={image.image_id}
                image={image}
                jobId={jobId}
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
        </div>

        {/* Detail panel — shown when an image is selected */}
        {selectedImage && (
          <div className="w-80 shrink-0">
            <ImageDetailPanel
              key={selectedImage.image_id}
              image={selectedImage}
              jobId={jobId}
              onClose={() => setSelectedId(null)}
              onActionComplete={handleActionComplete}
            />
          </div>
        )}
      </div>
    </div>
  );
}
