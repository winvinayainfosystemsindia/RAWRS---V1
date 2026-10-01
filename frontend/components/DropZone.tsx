"use client";

import { useCallback, useId, useRef, useState } from "react";

// The generic file drop zone, extracted from the upload page so the batch
// uploader (BatchUpload.tsx) composes the same affordance instead of a
// drifting second copy. Behavior is identical to the original inline
// component: drag-over highlight, sr-only input, disabled state.
interface DropZoneProps {
  accept: string;
  multiple?: boolean;
  disabled?: boolean;
  onFiles: (files: File[]) => void;
  children: React.ReactNode;
  className?: string;
}

export function DropZone({ accept, multiple, disabled, onFiles, children, className = "" }: DropZoneProps) {
  const [dragging, setDragging] = useState(false);
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  const pick = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;
      onFiles(Array.from(files));
    },
    [onFiles]
  );

  return (
    <label
      htmlFor={inputId}
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); if (!disabled) pick(e.dataTransfer.files); }}
      className={`flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed p-5 text-center transition-colors focus-within:ring-2 focus-within:ring-accent ${
        dragging ? "border-accent bg-accent/10" : "border-border bg-surface-canvas hover:border-border-strong hover:bg-hover-row"
      } ${disabled ? "pointer-events-none opacity-50" : ""} ${className}`}
    >
      {children}
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={accept}
        multiple={multiple}
        className="sr-only"
        disabled={disabled}
        onChange={(e) => pick(e.target.files)}
      />
    </label>
  );
}
