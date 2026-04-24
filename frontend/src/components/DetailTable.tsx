// frontend/src/components/DetailTable.tsx
import { useCallback, useEffect, useRef, useState } from "react";
import type { Component, WorkingComponent } from "../types";
import type { HardwareSet } from "../types";

interface Props {
  set: HardwareSet;
  components: WorkingComponent[];
  editCount: number;
  onCellEdit: (compIndex: number, field: string, value: string) => void;
  onDelete: (compIndex: number) => void;
  onAdd: () => void;
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

const COL_STYLES: Record<string, string> = {
  qty: "text-muted",
  description: "text-primary text-[13px]",
  catalog_number: "font-heading text-secondary",
  mfr: "text-muted",
  finish: "text-muted",
  notes: "text-muted text-xs",
};

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
        className="w-full px-1.5 py-0.5 text-sm border-2 border-accent rounded outline-none bg-elevated text-primary shadow-[0_0_0_3px_rgba(212,149,106,0.1)]"
      />
    );
  }

  return (
    <div
      onClick={startEdit}
      className={`cursor-pointer px-1.5 py-0.5 rounded min-h-[24px] ${
        isEdited
          ? "bg-accent-subtle border border-accent/30"
          : "hover:bg-surface"
      }`}
    >
      {displayValue || <span className="text-dim">—</span>}
    </div>
  );
}

function getComponentLabel(comp: WorkingComponent): string {
  if (comp.description) return comp.description;
  if (comp.catalog_number) return comp.catalog_number;
  return "this component";
}

interface ConfirmStripProps {
  label: string;
  onConfirm: () => void;
  onCancel: () => void;
}

function ConfirmStrip({ label, onConfirm, onCancel }: ConfirmStripProps) {
  return (
    <td colSpan={COLUMNS.length + 1} className="p-0">
      <div className="flex items-center gap-2 px-3 py-2 bg-error-subtle border border-error/20 rounded mx-1 my-0.5">
        <span className="text-[12px] text-primary flex-1">
          Remove &ldquo;{label}&rdquo;?
        </span>
        <button
          onClick={onConfirm}
          className="text-[10px] px-3 py-1 bg-error text-white rounded font-heading font-medium hover:bg-error/90 transition-colors"
        >
          Remove
        </button>
        <button
          onClick={onCancel}
          className="text-[10px] px-3 py-1 border border-border rounded text-muted font-heading hover:bg-elevated transition-colors"
        >
          Cancel
        </button>
      </div>
    </td>
  );
}

export default function DetailTable({
  set,
  components,
  editCount,
  onCellEdit,
  onDelete,
  onAdd,
  onReset,
}: Props) {
  const [confirmingIndex, setConfirmingIndex] = useState<number | null>(null);

  const isEdited = (comp: WorkingComponent, field: keyof Component) => {
    if (comp._sourceIndex === null) return true;
    const orig = set.components[comp._sourceIndex];
    return String(comp[field] ?? "") !== String(orig[field] ?? "");
  };

  return (
    <div className="flex-1 min-w-0 flex flex-col bg-backdrop">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border flex items-start justify-between">
        <div>
          <h2 className="text-[17px] font-heading font-bold text-primary tracking-[0.02em]">
            <span className="inline-block w-2 h-2 bg-accent rounded-[2px] shadow-[0_0_6px_rgba(212,149,106,0.3)] mr-2 align-middle" />
            Hardware Set {set.set_number}
          </h2>
          <p className="text-[13px] text-muted mt-0.5">
            {set.description && <span>{set.description} · </span>}
            {components.length} components · Page {set.location.page}, Lines{" "}
            {set.location.line_range[0]}–{set.location.line_range[1]}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {editCount > 0 && (
            <span className="text-[10px] px-2 py-1 bg-accent-subtle border border-accent/30 rounded text-accent font-heading">
              {editCount} edited
            </span>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto px-4 py-2">
        {set.is_not_used ? (
          <div className="flex items-center justify-center h-full text-muted text-sm">
            This set is marked as NOT USED
          </div>
        ) : (
          <>
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-border">
                  {COLUMNS.map((col) => (
                    <th
                      key={col.key}
                      className="text-left px-3 py-2 text-[10px] font-heading font-semibold text-accent uppercase tracking-widest"
                    >
                      {col.label}
                    </th>
                  ))}
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {components.map((comp, compIdx) =>
                  confirmingIndex === compIdx ? (
                    <tr key={compIdx} className="border-b border-surface">
                      <ConfirmStrip
                        label={getComponentLabel(comp)}
                        onConfirm={() => {
                          onDelete(compIdx);
                          setConfirmingIndex(null);
                        }}
                        onCancel={() => setConfirmingIndex(null)}
                      />
                    </tr>
                  ) : (
                    <tr key={compIdx} className="group border-b border-surface">
                      {COLUMNS.map((col) => (
                        <td key={col.key} className={`px-2 py-1.5 ${COL_STYLES[col.key] ?? ""}`}>
                          <EditableCell
                            value={(comp[col.key] as string | number | null) ?? null}
                            isEdited={isEdited(comp, col.key)}
                            onCommit={(val) => onCellEdit(compIdx, col.key, val)}
                          />
                        </td>
                      ))}
                      <td className="px-1 py-1.5 w-8">
                        <button
                          onClick={() => setConfirmingIndex(compIdx)}
                          className="w-6 h-6 flex items-center justify-center rounded text-dim opacity-0 group-hover:opacity-100 hover:!bg-error-subtle hover:!text-error transition-all text-sm"
                        >
                          ×
                        </button>
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
            <button
              onClick={onAdd}
              className="w-full mt-1 py-2 flex items-center justify-center gap-1.5 text-[11px] font-heading text-dim border border-dashed border-border rounded hover:text-accent hover:border-accent/50 transition-colors"
            >
              <span className="text-sm">+</span> Add component
            </button>
          </>
        )}
      </div>

    </div>
  );
}
