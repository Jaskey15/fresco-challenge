// frontend/src/components/DetailTable.tsx
import type { Component, HardwareSet } from "../types";

interface Props {
  set: HardwareSet;
}

const COLUMNS: Array<{ key: keyof Component; label: string }> = [
  { key: "qty", label: "QTY" },
  { key: "description", label: "DESCRIPTION" },
  { key: "catalog_number", label: "CATALOG #" },
  { key: "mfr", label: "MFR" },
  { key: "finish", label: "FINISH" },
  { key: "notes", label: "NOTES" },
];

function CellValue({ value }: { value: string | number | null }) {
  if (value === null || value === undefined) {
    return <span className="text-gray-300">—</span>;
  }
  return <>{String(value)}</>;
}

export default function DetailTable({ set }: Props) {
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
              {set.components.map((comp, i) => (
                <tr key={i} className="border-b border-gray-100">
                  {COLUMNS.map((col) => (
                    <td key={col.key} className="px-3 py-2 text-gray-700">
                      <CellValue value={(comp[col.key] as string | number | null) ?? null} />
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
        <span className="text-[10px] text-gray-300">
          📍 Page {set.location.page}, Lines {set.location.line_range[0]}–
          {set.location.line_range[1]}
        </span>
      </div>
    </div>
  );
}
