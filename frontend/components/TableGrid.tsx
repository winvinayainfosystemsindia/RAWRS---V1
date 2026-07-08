"use client";

import { useState } from "react";
import { api, type AiStatus, type TableItem } from "@/lib/api";
import { TableCard } from "./TableCard";
import { TableDetailPanel } from "./TableDetailPanel";

interface Props {
  tables: TableItem[];
  jobId: string;
  aiStatus: AiStatus | null;
  onTablesUpdated: (updated: TableItem[]) => void;
}

export function TableGrid({ tables, jobId, aiStatus, onTablesUpdated }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  function handleActionComplete(updated: TableItem) {
    onTablesUpdated(tables.map((t) => (t.table_id === updated.table_id ? updated : t)));
  }

  function handleDelete(deletedId: string) {
    onTablesUpdated(tables.filter((t) => t.table_id !== deletedId));
    if (selectedId === deletedId) setSelectedId(null);
  }

  async function handleCreate() {
    setCreating(true);
    setCreateError(null);
    try {
      const created = await api.createTable(jobId, {});
      onTablesUpdated([...tables, created]);
      setSelectedId(created.table_id);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreating(false);
    }
  }

  const selectedTable = selectedId
    ? tables.find((t) => t.table_id === selectedId) ?? null
    : null;

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-600">
          {tables.length === 0
            ? "No tables detected automatically."
            : `${tables.length} table${tables.length === 1 ? "" : "s"} found.`}
        </p>
        <button
          type="button"
          onClick={handleCreate}
          disabled={creating}
          className="rounded bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {creating ? "Creating…" : "+ Add Table"}
        </button>
      </div>

      {createError && <p className="text-xs text-red-600">{createError}</p>}

      {tables.length === 0 && (
        <div className="rounded-lg border border-dashed border-gray-300 p-6 text-center">
          <p className="text-sm text-gray-500 mb-1">
            No tables were detected in this document.
          </p>
          <p className="text-xs text-gray-400">
            Tables with visible borders are detected automatically.
            Use "+ Add Table" to manually define a table.
          </p>
        </div>
      )}

      {tables.length > 0 && (
        <div className="flex flex-col gap-4">
          {/* Table list */}
          <div className={selectedTable ? "w-full max-h-64 overflow-y-auto" : "w-full"}>
            <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {tables.map((table) => (
                <TableCard
                  key={table.table_id}
                  table={table}
                  isSelected={selectedId === table.table_id}
                  onSelect={() =>
                    setSelectedId((prev) =>
                      prev === table.table_id ? null : table.table_id
                    )
                  }
                />
              ))}
            </ul>
          </div>

          {/* Detail panel */}
          {selectedTable && (
            <div className="w-full">
              <TableDetailPanel
                key={selectedTable.table_id}
                table={selectedTable}
                jobId={jobId}
                aiStatus={aiStatus}
                onClose={() => setSelectedId(null)}
                onActionComplete={handleActionComplete}
                onDelete={handleDelete}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
