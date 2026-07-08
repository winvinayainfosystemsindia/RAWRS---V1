"use client";

import { useEffect, useRef } from "react";
import { EditorView, basicSetup } from "codemirror";
import { EditorState } from "@codemirror/state";
import { markdown } from "@codemirror/lang-markdown";
import { openSearchPanel } from "@codemirror/search";

interface Props {
  initialContent: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  className?: string;
  scrollToLine?: number | null;
  scrollNonce?: number;
}

// CSS-variable-based theme — responds to light/dark token switching without
// re-mounting the editor.
const rawrsTheme = EditorView.theme({
  "&": {
    height: "100%",
    fontSize: "13px",
    backgroundColor: "var(--surface-canvas)",
  },
  ".cm-editor": { height: "100%" },
  ".cm-scroller": {
    overflow: "auto",
    fontFamily:
      "var(--font-jetbrains-mono, 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace)",
    lineHeight: "1.6",
  },
  ".cm-content": { padding: "8px 0", color: "var(--text-primary)" },
  ".cm-gutters": {
    backgroundColor: "var(--surface-panel)",
    borderRight: "1px solid var(--border-default)",
    color: "var(--text-secondary)",
    userSelect: "none",
  },
  ".cm-lineNumbers .cm-gutterElement": { padding: "0 8px 0 12px", minWidth: "3em" },
  ".cm-activeLine": { backgroundColor: "var(--hover-row)" },
  ".cm-activeLineGutter": { backgroundColor: "var(--hover-row)" },
  ".cm-selectionBackground": {
    backgroundColor: "color-mix(in srgb, var(--accent) 30%, transparent) !important",
  },
  ".cm-focused .cm-selectionBackground": {
    backgroundColor: "color-mix(in srgb, var(--accent) 40%, transparent) !important",
  },
  ".cm-cursor": { borderLeftColor: "var(--accent)" },
  "&.cm-focused": { outline: "none" },
  ".cm-searchMatch": {
    backgroundColor: "color-mix(in srgb, var(--warning) 25%, transparent)",
    outline: "1px solid var(--warning)",
  },
  ".cm-searchMatch.cm-searchMatch-selected": {
    backgroundColor: "color-mix(in srgb, var(--warning) 45%, transparent)",
  },
  ".cm-panels": {
    backgroundColor: "var(--surface-panel)",
    borderTop: "1px solid var(--border-default)",
    color: "var(--text-primary)",
  },
  ".cm-panels input": {
    backgroundColor: "var(--surface-canvas)",
    border: "1px solid var(--border-default)",
    color: "var(--text-primary)",
    borderRadius: "3px",
    padding: "1px 4px",
  },
  ".cm-panels button": { color: "var(--text-secondary)" },
  ".cm-tooltip": {
    backgroundColor: "var(--surface-elevated)",
    border: "1px solid var(--border-strong)",
    color: "var(--text-primary)",
  },
});

export function MarkdownEditor({
  initialContent,
  onChange,
  readOnly,
  className,
  scrollToLine,
  scrollNonce,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    if (!containerRef.current) return;

    const extensions = [basicSetup, markdown(), EditorView.lineWrapping, rawrsTheme];

    if (readOnly) {
      extensions.push(EditorState.readOnly.of(true));
    } else {
      extensions.push(
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            onChangeRef.current?.(update.state.doc.toString());
          }
        }),
      );
    }

    const view = new EditorView({
      state: EditorState.create({ doc: initialContent, extensions }),
      parent: containerRef.current,
    });
    viewRef.current = view;

    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  // Editor owns its state after init; external resets use key prop to remount.

  // Imperative jump-to-line — PDF/Markdown bidirectional sync.
  useEffect(() => {
    const view = viewRef.current;
    if (!view || scrollToLine == null) return;
    const lineNumber = Math.min(Math.max(1, scrollToLine), view.state.doc.lines);
    const pos = view.state.doc.line(lineNumber).from;
    view.dispatch({
      selection: { anchor: pos },
      effects: EditorView.scrollIntoView(pos, { y: "center" }),
    });
  }, [scrollToLine, scrollNonce]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleOpenSearch() {
    if (viewRef.current) openSearchPanel(viewRef.current);
  }

  return (
    <div
      className={`flex h-full flex-col overflow-hidden rounded border border-border ${className ?? ""}`}
    >
      <div className="flex shrink-0 items-center justify-end gap-1 border-b border-border bg-surface-panel px-2 py-1">
        <button
          type="button"
          onClick={handleOpenSearch}
          title="Find / Replace (Ctrl+F)"
          className="rounded px-2 py-0.5 text-xs font-medium text-text-secondary hover:bg-hover-row hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          Find
        </button>
        {readOnly && (
          <span className="ml-2 rounded border border-border px-1.5 py-0.5 font-mono text-[10px] text-text-secondary">
            read-only
          </span>
        )}
      </div>
      <div ref={containerRef} className="min-h-0 flex-1 overflow-hidden" />
    </div>
  );
}
