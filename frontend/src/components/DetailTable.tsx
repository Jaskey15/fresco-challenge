// frontend/src/components/DetailTable.tsx
import { useCallback, useEffect, useRef, useState } from "react";
import type { Component, HardwareSet } from "../types";

interface Props {
  set: HardwareSet;
  edits: Record<number, Record<string, string>>;
  editCount: number;
  onCellEdit: (compIndex: number, field: string, value: string) => void;
  onReset: () => void;
}

const COLUMNS: Array<{ key: keyof Component; label: string }> = [
  { key: "qty", label: "QTY" },
  { key: "description", label: "DESCRIPTION" },
  { key: "catalog_number", label: "CATALOG #" },
  { key: "mfr", label: "MFR" },
  { key: "finish", label: "FINISH" },
  { key: "notes", label: "NOTES" },
];

interface EditableCellProps {
  value: string | number | null;
  isEdited: boolean;
  onCommit: (value: string) => void;
}

function EditableCell({ value, isEdited, onCommit }: EditableCellProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const displayValue = value === null || value === undefined ? "" : String(value);

  const startEdit = useCallback(() => {
    setDraft(displayValue);
    setEditing(true);
  }, [displayValue]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const commit = useCallback(() => {
    setEditing(false);
    if (draft !== displayValue) {
      onCommit(draft);
    }
  }, [draft, displayValue, onCommit]);

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === "Tab") {
            e.preventDefault();
            commit();
          } else if (e.key === "Escape") {
            setEditing(false);
          }
        }}
        className="w-full px-1.5 py-0.5 text-sm border-2 border-blue-500 rounded outline-none bg-white shadow-[0_0_0_3px_rgba(59,130,246,0.1)]"
      />
    );
  }

  return (
    <div
      onClick={startEdit}
      className={`cursor-pointer px-1.5 py-0.5 rounded min-h-[24px] ${
        isEdited
          ? "bg-amber-50 border border-amber-300"
          : "hover:bg-gray-50"
      }`}
    >
      {displayValue || <span className="text-gray-300">—</span>}
    </div>
  );
}

export default function DetailTable({ set, edits, editCount, onCellEdit, onReset }: Props) {
  const getDisplayValue = (compIndex: number, field: string, original: string | number | null) => {
    const edited = edits[compIndex]?.[field];
    return edited !== undefined ? edited : original;
  };

  const isEdited = (compIndex: number, field: string) => {
    return edits[compIndex]?.[field] !== undefined;
  };

  return (
    <div className="flex-1 min-w-0 flex flex-col bg-white">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 flex items-start justify-between">
        <div>
          <h2 className="text-base font-bold text-gray-900">
            <span className="text-green-500 mr-1">●</span>
            Hardware Set {set.set_number}
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">
            {set.description && <span>{set.description} · </span>}
            {set.components.length} components · Page {set.location.page}, Lines{" "}
            {set.location.line_range[0]}–{set.location.line_range[1]}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {editCount > 0 && (
            <span className="text-[10px] px-2 py-1 bg-amber-50 border border-amber-300 rounded text-amber-700">
              {editCount} edited
            </span>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto px-4 py-2">
        {set.is_not_used ? (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            This set is marked as NOT USED
          </div>
        ) : (
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b-2 border-gray-200">
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    className="text-left px-3 py-2 text-[10px] font-semibold text-gray-400 uppercase tracking-wider"
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {set.components.map((comp, compIdx) => (
                <tr key={compIdx} className="border-b border-gray-100">
                  {COLUMNS.map((col) => (
                    <td key={col.key} className="px-2 py-1.5">
                      <EditableCell
                        value={getDisplayValue(compIdx, col.key, (comp[col.key] as string | number | null) ?? null)}
                        isEdited={isEdited(compIdx, col.key)}
                        onCommit={(val) => onCellEdit(compIdx, col.key, val)}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Bottom bar */}
      <div className="px-4 py-2 border-t border-gray-100 flex items-center justify-between bg-gray-50">
        <span className="text-[10px] text-gray-400">
          Click any cell to edit · Tab to advance · Esc to cancel
        </span>
        <div className="flex items-center gap-2">
          {editCount > 0 && (
            <button
              onClick={onReset}
              className="text-[10px] px-3 py-1 border border-gray-300 rounded text-gray-500 hover:bg-gray-100"
            >
              Reset
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
