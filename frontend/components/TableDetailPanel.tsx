"use client";

import { useState } from "react";
import { api, type AiStatus, type CellUpdate, type TableItem, type TableReviewRequest } from "@/lib/api";
import { AiUnavailableBadge } from "./Badge";
import { ObjectInspectorFrame } from "./workspace/ObjectInspectorFrame";
import { CorrectionHistoryList } from "./CorrectionHistoryList";
import { useObjectInspectorContext } from "@/lib/store/useObjectInspectorContext";
import { useDocumentDispatch } from "@/lib/store/DocumentDataContext";

interface Props {
  table: TableItem;
  jobId: string;
  aiStatus: AiStatus | null;
  onClose: () => void;
  onActionComplete: (updated: TableItem) => void;
  onDelete: (tableId: string) => void;
}

interface SelectedCell {
  rowIdx: number;
  colIdx: number;
}

/** Build the screen reader announcement for a selected cell. */
function buildAnnouncement(table: TableItem, rowIdx: number, colIdx: number): string {
  const row = table.rows[rowIdx];
  if (!row) return "";
  const cell = row.cells[colIdx];
  if (!cell) return "";

  // Collect column header text from all header rows for this column.
  const colHeaders: string[] = [];
  for (const r of table.rows) {
    if (!r.is_header_row) continue;
    const hCell = r.cells[colIdx];
    if (hCell?.text) colHeaders.push(hCell.text);
  }

  // Row header: leftmost header-column cell in this row (if header_col_count > 0).
  let rowHeader = "";
  if (table.header_col_count > 0 && !row.is_header_row) {
    const rhCell = row.cells[0];
    if (rhCell?.text && colIdx > 0) rowHeader = rhCell.text;
  }

  const parts: string[] = [];
  if (colHeaders.length > 0) parts.push(colHeaders.join(" > "));
  if (rowHeader) parts.push(rowHeader);
  parts.push(cell.text || "(empty)");

  return parts.join(" → ");
}

export function TableDetailPanel({ table, jobId, aiStatus, onClose, onActionComplete, onDelete }: Props) {
  const { corrections, documentVersion } = useObjectInspectorContext("table", table.table_id, table.page_number);
  const dispatch = useDocumentDispatch();
  const [caption, setCaption] = useState(table.caption ?? "");
  const [summary, setSummary] = useState(table.summary ?? "");
  const [headerIndices, setHeaderIndices] = useState<Set<number>>(
    new Set(table.rows.flatMap((r, i) => (r.is_header_row ? [i] : [])))
  );
  const [headerColCount, setHeaderColCount] = useState(table.header_col_count ?? 0);
  const [selectedCell, setSelectedCell] = useState<SelectedCell | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [editedCells, setEditedCells] = useState<Map<string, string>>(new Map());
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentTable, setCurrentTable] = useState<TableItem>(table);

  function toggleHeaderRow(rowIdx: number) {
    setHeaderIndices((prev) => {
      const next = new Set(prev);
      if (next.has(rowIdx)) next.delete(rowIdx);
      else next.add(rowIdx);
      return next;
    });
    // Clear screen reader simulation when header structure changes.
    setSelectedCell(null);
  }

  function handleCellClick(rowIdx: number, colIdx: number, e: React.MouseEvent) {
    if (editMode) return;
    e.stopPropagation();
    setSelectedCell((prev) =>
      prev?.rowIdx === rowIdx && prev?.colIdx === colIdx ? null : { rowIdx, colIdx }
    );
  }

  function handleCellEdit(rowIdx: number, colIdx: number, value: string) {
    const key = `${rowIdx}-${colIdx}`;
    setEditedCells((prev) => {
      const next = new Map(prev);
      next.set(key, value);
      return next;
    });
  }

  function getCellDisplayText(cell: { text: string }, rowIdx: number, colIdx: number): string {
    return editedCells.get(`${rowIdx}-${colIdx}`) ?? cell.text;
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const cellUpdates: CellUpdate[] = [];
      for (const [key, text] of editedCells) {
        const [r, c] = key.split("-").map(Number);
        cellUpdates.push({ row_index: r, col_index: c, text });
      }
      const body: TableReviewRequest = {
        caption: caption || null,
        summary: summary || null,
        header_row_indices: Array.from(headerIndices),
        header_col_count: headerColCount,
        cells: cellUpdates.length > 0 ? cellUpdates : null,
      };
      const updated = await api.reviewTable(jobId, currentTable.table_id, body);
      setCurrentTable(updated);
      setEditedCells(new Map());
      onActionComplete(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleAnalyze() {
    setAnalyzing(true);
    setError(null);
    try {
      const updated = await api.analyzeTable(jobId, currentTable.table_id);
      setCurrentTable(updated);
      onActionComplete(updated);
      // Pre-fill caption/summary from AI suggestions if currently empty.
      if (!caption && updated.ai_suggestions?.suggested_caption) {
        setCaption(updated.ai_suggestions.suggested_caption);
      }
      if (!summary && updated.ai_suggestions?.suggested_summary) {
        setSummary(updated.ai_suggestions.suggested_summary);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "AI analysis failed");
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Remove this table? This cannot be undone.")) return;
    setDeleting(true);
    setError(null);
    try {
      await api.deleteTable(jobId, currentTable.table_id);
      onDelete(currentTable.table_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
      setDeleting(false);
    }
  }

  const announcement =
    selectedCell !== null
      ? buildAnnouncement(currentTable, selectedCell.rowIdx, selectedCell.colIdx)
      : null;

  const ai = currentTable.ai_suggestions;

  const header = (
    <div className="flex items-center justify-between">
      <div>
        <h3 className="text-sm font-semibold text-text-primary">
          Table — Page {currentTable.page_number} ({currentTable.row_count}×{currentTable.col_count})
        </h3>
        {currentTable.status === "auto_detected" && currentTable.confidence < 0.7 && (
          <p className="text-xs text-warning mt-0.5">
            Low confidence ({Math.round(currentTable.confidence * 100)}%) — verify structure carefully
          </p>
        )}
      </div>
      <button
        type="button"
        onClick={onClose}
        className="text-text-secondary hover:text-text-primary text-lg leading-none"
        aria-label="Close"
      >
        ×
      </button>
    </div>
  );

  return (
    <ObjectInspectorFrame
      header={header}
      metadata={
        <div className="space-y-4">
      {/* Table preview */}
      <div className="overflow-x-auto rounded border border-border bg-surface-panel max-h-64">
        <table className="text-xs border-collapse w-full">
          <tbody>
            {currentTable.rows.map((row, rowIdx) => (
              <tr
                key={rowIdx}
                className={`transition-colors ${
                  headerIndices.has(rowIdx) ? "bg-accent/10" : ""
                }`}
              >
                {/* Row toggle: click to mark/unmark as header row */}
                <td
                  className="px-1 py-0.5 border border-border text-text-secondary text-center select-none w-6 cursor-pointer hover:bg-accent/10"
                  title={`Click to toggle row ${rowIdx + 1} as header`}
                  onClick={() => toggleHeaderRow(rowIdx)}
                >
                  {headerIndices.has(rowIdx) ? "H" : rowIdx + 1}
                </td>
                {row.cells.map((cell, colIdx) => {
                  const isColHeader = colIdx < headerColCount && !headerIndices.has(rowIdx);
                  const isSelected =
                    selectedCell?.rowIdx === rowIdx && selectedCell?.colIdx === colIdx;
                  const displayText = getCellDisplayText(cell, rowIdx, colIdx);
                  return (
                    <td
                      key={colIdx}
                      onClick={(e) => handleCellClick(rowIdx, colIdx, e)}
                      className={`px-0 py-0 border border-border max-w-[160px] transition-colors ${
                        editMode
                          ? ""
                          : isSelected
                          ? "bg-accent/20 ring-1 ring-accent"
                          : headerIndices.has(rowIdx)
                          ? "font-semibold hover:bg-accent/10"
                          : isColHeader
                          ? "font-semibold text-success bg-success/10 hover:bg-success/20"
                          : "hover:bg-hover-row"
                      }`}
                      title={editMode ? "Edit cell text" : "Click to preview screen reader announcement"}
                    >
                      {editMode ? (
                        <input
                          type="text"
                          value={displayText}
                          onChange={(e) => handleCellEdit(rowIdx, colIdx, e.target.value)}
                          className={`w-full px-2 py-1 bg-transparent focus:bg-surface-elevated focus:outline focus:outline-1 focus:outline-accent ${
                            headerIndices.has(rowIdx) ? "font-semibold" : isColHeader ? "font-semibold text-success" : ""
                          }`}
                          aria-label={`Row ${rowIdx + 1}, Col ${colIdx + 1}`}
                        />
                      ) : (
                        <span className="block px-2 py-1 truncate">
                          {displayText || <span className="text-text-secondary italic">empty</span>}
                        </span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between">
        <p className="text-xs text-text-secondary">
          {editMode
            ? "Edit mode — type in any cell. Click Save to apply."
            : `Click row number to toggle header row (H, accent). Click a data cell to preview screen reader announcement.${headerColCount > 0 ? " Green column = row headers." : ""}`}
        </p>
        <button
          type="button"
          onClick={() => {
            setEditMode((v) => !v);
            setSelectedCell(null);
          }}
          className={`shrink-0 ml-2 rounded px-2 py-0.5 text-xs font-medium ring-1 transition-colors ${
            editMode
              ? "bg-accent/10 text-accent ring-accent/30 hover:bg-accent/20"
              : "bg-surface-panel text-text-secondary ring-border hover:bg-hover-row"
          }`}
        >
          {editMode ? "Done editing" : "Edit cells"}
        </button>
      </div>

      {/* Screen reader simulation */}
      {announcement !== null && (
        <div className="rounded border border-accent/30 bg-accent/10 p-3">
          <p className="text-xs font-semibold text-accent mb-1">Screen reader announcement</p>
          <p className="text-sm text-accent font-mono">{announcement}</p>
          <p className="text-xs text-accent/80 mt-1">
            Row {(selectedCell?.rowIdx ?? 0) + 1}, Col {(selectedCell?.colIdx ?? 0) + 1} —
            NVDA/JAWS would announce this when navigating to this cell
          </p>
        </div>
      )}

      {/* Row header column */}
      <div>
        <label className="block text-xs font-medium text-text-primary mb-1">
          Row headers (stub column)
        </label>
        <select
          value={headerColCount}
          onChange={(e) => {
            setHeaderColCount(Number(e.target.value));
            setSelectedCell(null);
          }}
          className="rounded border border-border px-2 py-1.5 text-sm focus:border-accent focus:outline-none"
        >
          <option value={0}>None — no row header column</option>
          <option value={1}>Column 1 — first column contains row labels</option>
        </select>
      </div>

      {/* Caption */}
      <div>
        <label className="block text-xs font-medium text-text-primary mb-1">
          Caption
        </label>
        <input
          type="text"
          value={caption}
          onChange={(e) => setCaption(e.target.value)}
          placeholder="e.g. Table 1. Summary of results"
          className="w-full rounded border border-border px-2 py-1.5 text-sm focus:border-accent focus:outline-none"
        />
      </div>

      {/* Accessibility summary */}
      <div>
        <label className="block text-xs font-medium text-text-primary mb-1">
          Accessibility summary
          <span className="ml-1 text-text-secondary font-normal">(WCAG H73 — describe complex tables)</span>
        </label>
        <textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          placeholder="Describe what this table shows, for screen reader users."
          rows={3}
          className="w-full rounded border border-border px-2 py-1.5 text-sm focus:border-accent focus:outline-none resize-none"
        />
      </div>

      {/* AI suggestions panel */}
      {ai && (
        <div className="rounded border border-accent/30 bg-accent/10 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-accent">
              AI suggestions ({Math.round(ai.confidence * 100)}% confidence)
              {ai.table_type && (
                <span className="ml-2 font-normal text-accent/80">{ai.table_type}</span>
              )}
            </p>
          </div>
          {ai.suggested_caption && (
            <div>
              <p className="text-xs text-accent font-medium">Suggested caption:</p>
              <p className="text-xs text-accent">{ai.suggested_caption}</p>
              <button
                type="button"
                onClick={() => setCaption(ai.suggested_caption!)}
                className="mt-0.5 text-xs text-accent underline hover:opacity-80"
              >
                Use this caption
              </button>
            </div>
          )}
          {ai.suggested_summary && (
            <div>
              <p className="text-xs text-accent font-medium">Suggested summary:</p>
              <p className="text-xs text-accent">{ai.suggested_summary}</p>
              <button
                type="button"
                onClick={() => setSummary(ai.suggested_summary!)}
                className="mt-0.5 text-xs text-accent underline hover:opacity-80"
              >
                Use this summary
              </button>
            </div>
          )}
          {ai.warnings.length > 0 && (
            <div>
              <p className="text-xs text-accent font-medium">Accessibility warnings:</p>
              <ul className="list-disc list-inside space-y-0.5">
                {ai.warnings.map((w, i) => (
                  <li key={i} className="text-xs text-warning">{w}</li>
                ))}
              </ul>
            </div>
          )}
          {(ai.header_rows_detected > 0 || ai.header_cols_detected > 0) && (
            <p className="text-xs text-accent">
              AI detected: {ai.header_rows_detected} header row(s),{" "}
              {ai.header_cols_detected} row-header col(s)
            </p>
          )}
        </div>
      )}

      {error && <p className="text-xs text-danger">{error}</p>}
        </div>
      }
      correctionHistory={
        <CorrectionHistoryList
          corrections={corrections}
          jobId={jobId}
          onUpdated={(updated) => dispatch({ type: "UPDATE_CORRECTION", correction: updated })}
          emptyMessage="No cross-source corrections proposed for this table."
        />
      }
      version={
        documentVersion !== null ? (
          <p className="text-sm text-text-secondary">As of Document v{documentVersion}</p>
        ) : undefined
      }
      actions={
        <>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || deleting || analyzing}
            className="flex-1 rounded bg-accent px-3 py-1.5 text-xs font-medium text-accent-contrast hover:opacity-90 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
          {aiStatus && !aiStatus.available ? (
            <AiUnavailableBadge reason={aiStatus.unavailable_reason} />
          ) : (
            <button
              type="button"
              onClick={handleAnalyze}
              disabled={saving || deleting || analyzing}
              className="rounded bg-accent px-3 py-1.5 text-xs font-medium text-accent-contrast hover:opacity-90 disabled:opacity-50"
            >
              {analyzing ? "Analyzing…" : "Analyze with AI"}
            </button>
          )}
          <button
            type="button"
            onClick={handleDelete}
            disabled={saving || deleting || analyzing}
            className="rounded border border-danger/40 px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger/10 disabled:opacity-50"
          >
            {deleting ? "Removing…" : "Remove"}
          </button>
        </>
      }
    />
  );
}
