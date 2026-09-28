"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { MarkdownEditor } from "@/components/MarkdownEditor";

// The editable Markdown pane. The reviewer types; the DOCX pane beside it
// previews the draft live (the caller passes `onDraftChange` through to
// DocxPreview). Saving makes the edit the deliverable - both downloads are
// then built from it - and "Discard edits" returns to the generated text.

type Props = {
  jobId: string;
  // The Markdown the server currently serves (the saved edit, when one exists).
  content: string;
  documentVersion: number | null;
  scrollToLine?: number | null;
  scrollNonce?: number;
  flashLines?: number[];
  onDraftChange: (draft: string | null) => void;
  // Called with the new server content after a save or a discard.
  onContentReplaced: (content: string) => void;
};

type EditState = { edited: boolean; editedAtVersion: number | null };

// A discard click arms the button; this long without a second click disarms it.
const DISCARD_CONFIRM_MS = 4000;

export function MarkdownEditPane({
  jobId,
  content,
  documentVersion,
  scrollToLine,
  scrollNonce,
  flashLines,
  onDraftChange,
  onContentReplaced,
}: Props) {
  const [draft, setDraft] = useState<string | null>(null);
  const [edit, setEdit] = useState<EditState>({ edited: false, editedAtVersion: null });
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDiscardArmed, setIsDiscardArmed] = useState(false);
  const [editorNonce, setEditorNonce] = useState(0);
  // New server content (the Markdown finished loading, or an accepted
  // correction regenerated it) reloads the editor - unless the reviewer is
  // mid-edit, whose unsaved typing always wins. Derived during render, the
  // React-documented way to reset state from a changed prop.
  const [seenContent, setSeenContent] = useState(content);
  if (content !== seenContent) {
    setSeenContent(content);
    if (draft === null) setEditorNonce((n) => n + 1);
  }

  useEffect(() => {
    let cancelled = false;
    api
      .getMarkdown(jobId)
      .then((r) => {
        if (!cancelled) setEdit({ edited: !!r.edited, editedAtVersion: r.edited_at_version ?? null });
      })
      .catch(() => undefined); // the provider already reports load failures
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  useEffect(() => {
    if (!isDiscardArmed) return;
    const timer = setTimeout(() => setIsDiscardArmed(false), DISCARD_CONFIRM_MS);
    return () => clearTimeout(timer);
  }, [isDiscardArmed]);

  function updateDraft(next: string | null) {
    setDraft(next);
    onDraftChange(next);
  }

  function handleChange(value: string) {
    updateDraft(value === content ? null : value);
  }

  async function handleSave() {
    if (draft === null || isBusy) return;
    setIsBusy(true);
    setError(null);
    try {
      const saved = await api.saveMarkdown(jobId, draft);
      setEdit({ edited: true, editedAtVersion: saved.edited_at_version ?? null });
      setSeenContent(saved.content); // the editor already shows it; no reload
      onContentReplaced(saved.content);
      updateDraft(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setIsBusy(false);
    }
  }

  function handleRevertDraft() {
    updateDraft(null);
    setEditorNonce((n) => n + 1);
  }

  async function handleDiscard() {
    if (!isDiscardArmed) {
      setIsDiscardArmed(true);
      return;
    }
    setIsDiscardArmed(false);
    setIsBusy(true);
    setError(null);
    try {
      const restored = await api.discardMarkdownEdits(jobId);
      setEdit({ edited: false, editedAtVersion: null });
      onContentReplaced(restored.content);
      updateDraft(null);
      setEditorNonce((n) => n + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not discard the edits.");
    } finally {
      setIsBusy(false);
    }
  }

  const isStale =
    edit.edited && edit.editedAtVersion !== null && documentVersion !== null && edit.editedAtVersion !== documentVersion;

  const status =
    draft !== null ? (
      <span className="rounded bg-warning/15 px-1.5 py-0.5 text-[11px] font-medium text-warning">Unsaved changes</span>
    ) : edit.edited ? (
      <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[11px] font-medium text-text-primary">Edited · saved</span>
    ) : (
      <span className="text-[11px] text-text-secondary">Generated</span>
    );

  const button =
    "rounded px-2 py-0.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-40";

  return (
    <div className="flex h-full flex-col gap-2 p-3">
      {isStale && (
        <p role="status" className="shrink-0 rounded border border-warning/40 bg-warning/10 px-3 py-1.5 text-xs text-warning">
          Corrections were accepted after these edits were saved; the edited text does not include them. Discard edits to
          get the regenerated Markdown.
        </p>
      )}
      {error && (
        <p role="alert" className="shrink-0 rounded border border-danger/30 bg-danger/10 px-3 py-1.5 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="min-h-0 flex-1">
        <MarkdownEditor
          key={`md-edit-${editorNonce}`}
          initialContent={content}
          onChange={handleChange}
          onSave={() => void handleSave()}
          scrollToLine={scrollToLine}
          scrollNonce={scrollNonce}
          flashLines={flashLines}
          toolbar={
            <>
              {status}
              <button
                type="button"
                onClick={() => void handleSave()}
                disabled={draft === null || isBusy}
                title="Save (Ctrl+S) - the saved Markdown is what both downloads are built from"
                className={`${button} bg-accent text-accent-contrast hover:opacity-90`}
              >
                {isBusy && draft !== null ? "Saving…" : "Save"}
              </button>
              {draft !== null && (
                <button type="button" onClick={handleRevertDraft} className={`${button} text-text-secondary hover:bg-hover-row hover:text-text-primary`}>
                  Revert
                </button>
              )}
              {draft === null && edit.edited && (
                <button
                  type="button"
                  onClick={() => void handleDiscard()}
                  disabled={isBusy}
                  className={`${button} ${isDiscardArmed ? "bg-danger text-white" : "text-danger hover:bg-danger/10"}`}
                >
                  {isDiscardArmed ? "Click again to discard" : "Discard edits"}
                </button>
              )}
            </>
          }
        />
      </div>
    </div>
  );
}
