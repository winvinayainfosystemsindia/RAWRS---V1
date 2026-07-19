import { useState, useCallback } from "react";

// ponytail: localStorage wrapper. No framework, no external dep.
// Ceiling: no cross-tab sync; add BroadcastChannel if needed.
export function usePersistedState<T>(key: string, defaultValue: T): [T, (v: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => {
    if (typeof window === "undefined") return defaultValue;
    try {
      const stored = localStorage.getItem(key);
      return stored !== null ? JSON.parse(stored) : defaultValue;
    } catch {
      return defaultValue;
    }
  });

  const setPersisted = useCallback(
    (next: T | ((prev: T) => T)) => {
      setValue((prev) => {
        const resolved = typeof next === "function" ? (next as (p: T) => T)(prev) : next;
        try {
          localStorage.setItem(key, JSON.stringify(resolved));
        } catch { /* quota exceeded — degrade gracefully */ }
        return resolved;
      });
    },
    [key]
  );

  return [value, setPersisted];
}
