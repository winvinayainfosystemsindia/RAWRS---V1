"use client";

import { useState } from "react";
import { api, type EquationItem, type EquationEditRequest } from "@/lib/api";
import { Badge } from "./Badge";
import { ObjectInspectorFrame } from "./workspace/ObjectInspectorFrame";
import { CorrectionHistoryList } from "./CorrectionHistoryList";
import { useObjectInspectorContext } from "@/lib/store/useObjectInspectorContext";
import { useDocumentDispatch } from "@/lib/store/DocumentDataContext";

// The equations workspace (frontend plan item 2). The backend parses maths
// into Equation objects, converts them to native Word equations, and marks
// the ones it was not confident about as `flagged` (EQUATION_001 in the
// validation queue). This panel is where the reviewer works them off:
// compare the LaTeX with the PDF, correct it, and see the edit history —
// every edit lands in the generic corrections ledger, so one Undo reverts
// the whole edit (PATCH wraps all changed fields in one transaction).

const STATUS_BADGE: Record<EquationItem["status"], { label: string; tone: "success" | "danger" | "neutral" }> = {
  converted: { label: "Converted", tone: "success" },
  flagged: { label: "Flagged", tone: "danger" },
  plain: { label: "Plain text", tone: "neutral" },
};

function EquationStatusBadge({ status }: { status: EquationItem["status"] }) {
  const { label, tone } = STATUS_BADGE[status];
  return <Badge tone={tone}>{label}</Badge>;
}

function FlagReasons({ reasons }: { reasons: string[] }) {
  if (reasons.length === 0) return null;
  return (
    <div className="rounded border border-danger/30 bg-danger/5 p-2">
      <p className="text-xs font-semibold text-danger">Why it was flagged</p>
      <ul className="mt-1 list-inside list-disc space-y-0.5">
        {reasons.map((reason) => (
          <li key={reason} className="text-xs text-danger/90">
            {reason}
          </li>
        ))}
      </ul>
    </div>
  );
}

function EquationDetailPanel({ equation, jobId }: { equation: EquationItem; jobId: string }) {
  const { corrections, documentVersion } = useObjectInspectorContext("equation", equation.equation_id, equation.page_number);
  const dispatch = useDocumentDispatch();

  const [latex, setLatex] = useState(equation.latex);
  const [number, setNumber] = useState(equation.number ?? "");
  const [description, setDescription] = useState(equation.description ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirty =
    latex !== equation.latex ||
    number !== (equation.number ?? "") ||
    description !== (equation.description ?? "");

  async function handleSave() {
    if (!dirty || saving) return;
    setSaving(true);
    setError(null);
    // Send only the fields that changed; an emptied number/description must
    // still go through as "" (the backend treats that as a clear), so the
    // dirty check — not a null check — decides what is sent.
    const body: EquationEditRequest = {};
    if (latex !== equation.latex) body.latex = latex;
    if (number !== (equation.number ?? "")) body.number = number;
    if (description !== (equation.description ?? "")) body.description = description;
    try {
      const updated = await api.editEquation(jobId, equation.equation_id, body);
      dispatch({ type: "UPDATE_EQUATION", equation: updated });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the equation.");
    } finally {
      setSaving(false);
    }
  }

  const header = (
    <div className="flex items-center gap-2">
      <EquationStatusBadge status={equation.status} />
      <span className="text-xs text-text-secondary">
        Page {equation.page_number} · {equation.display ? "Display" : "Inline"}
        {equation.number ? ` · (${equation.number})` : ""}
      </span>
    </div>
  );

  return (
    <ObjectInspectorFrame
      header={header}
      metadata={
        <div className="space-y-3">
          <div>
            <label
              htmlFor="equation-latex"
              className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-secondary"
            >
              LaTeX
            </label>
            <textarea
              id="equation-latex"
              value={latex}
              onChange={(e) => setLatex(e.target.value)}
              rows={3}
              spellCheck={false}
              className="w-full rounded border border-border bg-surface-canvas px-2 py-1.5 font-mono text-sm text-text-primary focus:border-accent focus:outline-none"
              disabled={saving}
            />
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label
                htmlFor="equation-number"
                className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-secondary"
              >
                Number
              </label>
              <input
                id="equation-number"
                type="text"
                value={number}
                onChange={(e) => setNumber(e.target.value)}
                placeholder="(none)"
                className="w-full rounded border border-border bg-surface-canvas px-2 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
                disabled={saving}
              />
            </div>
            <div>
              <label
                htmlFor="equation-description"
                className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-secondary"
              >
                Description
              </label>
              <input
                id="equation-description"
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="(none)"
                className="w-full rounded border border-border bg-surface-canvas px-2 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
                disabled={saving}
              />
            </div>
          </div>

          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-text-secondary">
              Unicode rendering
            </p>
            <p className="rounded border border-border bg-surface-canvas px-2 py-1.5 text-sm text-text-primary">
              {equation.text || "—"}
            </p>
          </div>

          <FlagReasons reasons={equation.flag_reasons} />

          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}

          <button
            type="button"
            onClick={handleSave}
            disabled={!dirty || saving || !latex.trim()}
            className="rounded bg-accent px-3 py-1.5 text-sm font-medium text-accent-contrast hover:opacity-90 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            {saving ? "Saving…" : "Save equation"}
          </button>
          {!latex.trim() && (
            <p className="text-xs text-text-secondary">LaTeX must not be blank — deleting an equation is not an edit.</p>
          )}
        </div>
      }
      correctionHistory={
        <CorrectionHistoryList
          corrections={corrections}
          jobId={jobId}
          onUpdated={(updated) => dispatch({ type: "UPDATE_CORRECTION", correction: updated })}
          emptyMessage="No edits yet. Save a change and it appears here — undoing it reverts the whole edit."
        />
      }
      version={
        documentVersion !== null ? (
          <p className="text-sm text-text-secondary">As of Document v{documentVersion}</p>
        ) : undefined
      }
    />
  );
}

type FilterMode = "all" | "flagged";

export function EquationsPanel({ equations, jobId }: { equations: EquationItem[]; jobId: string }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterMode>("all");

  if (equations.length === 0) {
    return <p className="text-sm text-text-secondary">No equations were detected in this document.</p>;
  }

  const flaggedCount = equations.filter((e) => e.status === "flagged").length;
  const visible = filter === "flagged" ? equations.filter((e) => e.status === "flagged") : equations;
  const selected = equations.find((e) => e.equation_id === selectedId) ?? null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-text-secondary">
          {equations.length} equation{equations.length !== 1 ? "s" : ""} · {flaggedCount} flagged
        </p>
        <div className="flex items-center gap-0.5 rounded-md border border-border bg-surface-canvas p-0.5" role="group" aria-label="Equation filter">
          <button
            type="button"
            onClick={() => setFilter("all")}
            aria-pressed={filter === "all"}
            className={`rounded px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
              filter === "all" ? "bg-accent text-accent-contrast" : "text-text-secondary hover:bg-hover-row hover:text-text-primary"
            }`}
          >
            All
          </button>
          <button
            type="button"
            onClick={() => setFilter("flagged")}
            aria-pressed={filter === "flagged"}
            disabled={flaggedCount === 0}
            className={`rounded px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50 ${
              filter === "flagged" ? "bg-accent text-accent-contrast" : "text-text-secondary hover:bg-hover-row hover:text-text-primary"
            }`}
          >
            Flagged only
          </button>
        </div>
      </div>

      <div className={`w-full ${selected ? "max-h-64 overflow-y-auto" : ""}`}>
        {visible.length === 0 ? (
          <p className="text-sm text-text-secondary">
            {filter === "flagged" ? "Nothing is flagged — every equation converted cleanly." : "No equations."}
          </p>
        ) : (
          <ul className="space-y-2">
            {visible.map((eq) => {
              const isSelected = eq.equation_id === selectedId;
              return (
                <li key={eq.equation_id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId((prev) => (prev === eq.equation_id ? null : eq.equation_id))}
                    aria-pressed={isSelected}
                    className={`w-full cursor-pointer rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                      isSelected ? "border-accent bg-hover-row" : "border-border bg-surface-panel hover:border-border-strong"
                    }`}
                  >
                    <div className="mb-1 flex items-center gap-2">
                      <EquationStatusBadge status={eq.status} />
                      <span className="text-xs text-text-secondary">
                        Page {eq.page_number} · {eq.display ? "Display" : "Inline"}
                      </span>
                    </div>
                    <p className="line-clamp-2 break-words font-mono text-xs text-text-primary">
                      {eq.number ? `(${eq.number}) ` : ""}
                      {eq.latex}
                    </p>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {selected && (
        <div className="min-w-0 flex-1">
          <EquationDetailPanel equation={selected} jobId={jobId} />
        </div>
      )}
    </div>
  );
}
