"use client";

import { useEffect } from "react";
import { api } from "@/lib/api";

/** Seconds of no input after which time stops counting (src/metrics/automation.py). */
export const STRICT_IDLE_SECONDS = 60;
export const LOOSE_IDLE_SECONDS = 300;
/** Flush often enough that one delta never reaches the backend's 300 s cap. */
export const FLUSH_EVERY_SECONDS = 60;

const INPUT_EVENTS = ["pointerdown", "pointermove", "keydown", "wheel", "scroll"] as const;

/**
 * Counts active review time for one document, with no UI and nothing stored in
 * the browser. A second counts only while the tab is visible: towards "strict"
 * if there was input in the last 60 s, towards "loose" within 300 s (people
 * read without touching anything). Totals go only to this RAWRS backend.
 */
export function useReviewTimer(jobId: string, enabled = true): void {
  useEffect(() => {
    if (!enabled) return;
    let lastInput = Date.now();
    let strict = 0;
    let loose = 0;
    let sinceFlush = 0;

    const flush = () => {
      if (loose > 0 || strict > 0) api.postReviewTime(jobId, strict, loose);
      strict = 0;
      loose = 0;
      sinceFlush = 0;
    };
    const onInput = () => {
      lastInput = Date.now();
    };
    const onVisibility = () => {
      if (document.visibilityState === "hidden") flush();
    };
    const tick = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      const idle = (Date.now() - lastInput) / 1000;
      if (idle <= STRICT_IDLE_SECONDS) strict += 1;
      if (idle <= LOOSE_IDLE_SECONDS) loose += 1;
      sinceFlush += 1;
      if (sinceFlush >= FLUSH_EVERY_SECONDS) flush();
    }, 1000);

    INPUT_EVENTS.forEach((name) => window.addEventListener(name, onInput, { passive: true, capture: true }));
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", flush);
    return () => {
      window.clearInterval(tick);
      INPUT_EVENTS.forEach((name) => window.removeEventListener(name, onInput, { capture: true }));
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", flush);
      flush();
    };
  }, [jobId, enabled]);
}
