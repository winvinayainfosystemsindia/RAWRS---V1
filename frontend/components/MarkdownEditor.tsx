"use client";

import { useEffect, useRef } from "react";
import { EditorView, basicSetup } from "codemirror";
import { EditorState } from "@codemirror/state";
import { markdown } from "@codemirror/lang-markdown";

interface Props {
  initialContent: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  className?: string;
}

// The RAWRS editor theme — tightly integrated with the enterprise
// design system (slate/gray palette, monospace, no rounded corners
// inside the editor chrome itself).
const rawrsTheme = EditorView.theme({
  "&": {
    height: "100%",
    fontSize: "13px",
    backgroundColor: "#fff",
  },
  ".cm-editor": { height: "100%" },
  ".cm-scroller": {
    overflow: "auto",
    fontFamily:
      "ui-monospace, 'SF Mono', SFMono-Regular, Menlo, Consolas, monospace",
    lineHeight: "1.6",
  },
  ".cm-content": { padding: "8px 0" },
  ".cm-gutters": {
    backgroundColor: "#f8fafc",
    borderRight: "1px solid #e2e8f0",
    color: "#94a3b8",
    userSelect: "none",
  },
  ".cm-lineNumbers .cm-gutterElement": { padding: "0 8px 0 12px", minWidth: "3em" },
  ".cm-activeLine": { backgroundColor: "#f1f5f9" },
  ".cm-activeLineGutter": { backgroundColor: "#e2e8f0" },
  ".cm-selectionBackground": { backgroundColor: "#bfdbfe !important" },
  ".cm-focused .cm-selectionBackground": { backgroundColor: "#93c5fd !important" },
  ".cm-cursor": { borderLeftColor: "#1e40af" },
  "&.cm-focused": { outline: "none" },
  ".cm-searchMatch": { backgroundColor: "#fef9c3", outline: "1px solid #fbbf24" },
  ".cm-searchMatch.cm-searchMatch-selected": { backgroundColor: "#fde68a" },
});

export function MarkdownEditor({ initialContent, onChange, readOnly, className }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    if (!containerRef.current) return;

    const extensions = [
      basicSetup,
      markdown(),
      EditorView.lineWrapping,
      rawrsTheme,
    ];

    if (readOnly) {
      extensions.push(EditorState.readOnly.of(true));
    } else {
      extensions.push(
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            onChangeRef.current?.(update.state.doc.toString());
          }
        })
      );
    }

    const view = new EditorView({
      state: EditorState.create({ doc: initialContent, extensions }),
      parent: containerRef.current,
    });

    return () => view.destroy();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  // Intentionally no deps: the editor owns its state after init.
  // External resets use key prop to remount this component.

  return (
    <div
      ref={containerRef}
      className={`h-full overflow-hidden rounded-md border border-gray-200 ${className ?? ""}`}
    />
  );
}
