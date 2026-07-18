"use client";

import { useCallback, useMemo, useState, createContext, useContext, useRef, type ReactNode } from "react";

interface ToastItem {
  id: number;
  message: string;
  action?: { label: string; onClick: () => void };
}

interface ToastContextValue {
  toast: (message: string, action?: ToastItem["action"]) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const DURATION_MS = 6000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(0);

  const dismiss = useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback((message: string, action?: ToastItem["action"]) => {
    const id = ++nextId.current;
    setItems((prev) => [...prev, { id, message, action }]);
    setTimeout(() => dismiss(id), DURATION_MS);
  }, [dismiss]);

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 flex-col items-center gap-2"
      >
        {items.map((item) => (
          <div
            key={item.id}
            className="pointer-events-auto flex items-center gap-3 rounded-lg border border-border bg-surface-panel px-4 py-2.5 text-sm text-text-primary shadow-lg"
          >
            <span>{item.message}</span>
            {item.action && (
              <button
                type="button"
                onClick={() => {
                  item.action!.onClick();
                  dismiss(item.id);
                }}
                className="shrink-0 font-semibold text-accent hover:underline"
              >
                {item.action.label}
              </button>
            )}
            <button
              type="button"
              onClick={() => dismiss(item.id)}
              className="ml-1 shrink-0 text-text-secondary hover:text-text-primary"
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
