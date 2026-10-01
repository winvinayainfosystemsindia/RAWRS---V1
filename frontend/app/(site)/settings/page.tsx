"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type AiStatus } from "@/lib/api";
import { useTheme } from "@/lib/theme/ThemeProvider";

// Settings (frontend plan item 4). Client component so it can read the live
// theme and poll the backend's AI status. Everything shown is real: the
// theme and backend URL are the client's own state, AI status comes from
// GET /api/ai/status, and the version is the frontend package.json version
// (there is no backend version endpoint to show).

function formatCapabilities(capabilities: string[]): string {
  return capabilities.length > 0 ? capabilities.join(", ") : "none";
}

export default function SettingsPage() {
  const { theme, toggleTheme } = useTheme();
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);
  const [version, setVersion] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    api
      .getAiStatus()
      .then((status) => {
        if (!cancelled) {
          setAiStatus(status);
          setAiError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setAiError(
            err instanceof ApiError
              ? `The backend answered, but the status request failed (${err.status}).`
              : "Could not reach the backend. Is it running?"
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    import("@/package.json")
      .then((pkg) => {
        if (!cancelled) setVersion(pkg.default?.version ?? pkg.version ?? "");
      })
      .catch(() => {
        // Static import would inline the whole package.json (all its
        // dependencies) into the client bundle; the dynamic import keeps it
        // out of the critical path, and failure just means no version shown.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-6">
      <section className="pt-2">
        <h1 className="text-xl font-bold tracking-tight text-text-primary">Settings</h1>
        <p className="mt-1.5 text-sm text-text-secondary">
          Appearance, backend connection and application information.
        </p>
      </section>

      {/* Appearance */}
      <section aria-labelledby="settings-theme-heading" className="rounded-xl border border-border bg-surface-panel p-6">
        <h2 id="settings-theme-heading" className="mb-3 text-sm font-bold text-text-primary">
          Appearance
        </h2>
        <div className="flex items-center justify-between gap-4">
          <p className="text-sm text-text-secondary">
            Current theme: <span className="font-medium text-text-primary">{theme === "dark" ? "Dark" : "Light"}</span>
          </p>
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={`Switch to the ${theme === "dark" ? "light" : "dark"} theme`}
            className="rounded-lg border border-border bg-surface-canvas px-4 py-2 text-sm font-semibold text-text-primary hover:bg-hover-row focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            Switch to {theme === "dark" ? "light" : "dark"}
          </button>
        </div>
      </section>

      {/* Backend connection */}
      <section aria-labelledby="settings-backend-heading" className="rounded-xl border border-border bg-surface-panel p-6">
        <h2 id="settings-backend-heading" className="mb-3 text-sm font-bold text-text-primary">
          Backend
        </h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
          <dt className="text-text-secondary">URL</dt>
          <dd className="break-all font-mono text-text-primary">{api.baseUrl}</dd>
          <dt className="text-text-secondary">AI status</dt>
          <dd>
            {aiStatus === null && !aiError && <span className="text-text-secondary">Checking…</span>}
            {aiError && (
              <span className="text-warning" role="status">
                {aiError}
              </span>
            )}
            {aiStatus !== null && !aiError && aiStatus.available && (
              <span className="text-success" role="status">
                {aiStatus.provider} available · capabilities: {formatCapabilities(aiStatus.capabilities)}
              </span>
            )}
            {aiStatus !== null && !aiError && !aiStatus.available && (
              <span className="text-warning" role="status">
                {aiStatus.provider} unavailable
                {aiStatus.unavailable_reason ? ` — ${aiStatus.unavailable_reason}` : ""}
              </span>
            )}
          </dd>
        </dl>
        <p className="mt-3 text-xs text-text-secondary">
          The backend URL is fixed at build time via <code className="font-mono">NEXT_PUBLIC_API_BASE_URL</code>{" "}
          (<code className="font-mono">frontend/.env.local</code> locally). AI status reflects what the backend
          reported when this page loaded.
        </p>
      </section>

      {/* About */}
      <section aria-labelledby="settings-about-heading" className="rounded-xl border border-border bg-surface-panel p-6">
        <h2 id="settings-about-heading" className="mb-3 text-sm font-bold text-text-primary">
          About
        </h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
          <dt className="text-text-secondary">RAWRS</dt>
          <dd className="text-text-primary">Accessibility Verification &amp; Remediation Engine</dd>
          <dt className="text-text-secondary">Frontend version</dt>
          <dd className="font-mono text-text-primary">{version || "unknown"}</dd>
        </dl>
        <p className="mt-3 text-xs text-text-secondary">
          Turns a PDF — born-digital or scanned — into an accessible, checklist-compliant DOCX and Markdown.
        </p>
      </section>
    </div>
  );
}
