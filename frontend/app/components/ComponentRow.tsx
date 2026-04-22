"use client";

import { useState } from "react";
import type { Component, EditableField } from "@/lib/types";
import { ConfidenceBadge } from "./ConfidenceBadge";

type Props = {
  component: Component;
  onEdit: (field: EditableField, value: string | number | null) => void;
  onRemove: () => void;
};

const FIELDS: { key: EditableField; label: string; mono: boolean; width: string }[] = [
  { key: "qty", label: "QTY", mono: true, width: "w-10" },
  { key: "description", label: "DESCRIPTION", mono: false, width: "flex-1" },
  { key: "catalog_number", label: "CATALOG", mono: true, width: "w-48" },
  { key: "mfr", label: "MFR", mono: true, width: "w-20" },
  { key: "finish", label: "FINISH", mono: true, width: "w-20" },
  { key: "notes", label: "NOTES", mono: false, width: "w-32" },
];

export function ComponentRow({ component, onEdit, onRemove }: Props) {
  return (
    <div className="flex items-center gap-2 py-1 border-b border-cyan-dim/30 text-[12px]">
      {FIELDS.map((f) => (
        <EditableCell
          key={f.key}
          value={component[f.key]}
          mono={f.mono}
          widthClass={f.width}
          onCommit={(v) => onEdit(f.key, v)}
        />
      ))}
      <div className="flex items-center gap-1">
        <ConfidenceBadge value={component.confidence.mfr} label="mfr" />
        <ConfidenceBadge value={component.confidence.finish} label="finish" />
        <ConfidenceBadge value={component.confidence.qty} label="qty" />
      </div>
      <button
        onClick={onRemove}
        className="text-ink-dim hover:text-red-300 text-[10px] ml-2 font-mono"
        title="Remove component"
      >
        ✕
      </button>
    </div>
  );
}

function EditableCell({
  value,
  mono,
  widthClass,
  onCommit,
}: {
  value: string | number | null;
  mono: boolean;
  widthClass: string;
  onCommit: (v: string | number | null) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string>(value === null || value === undefined ? "" : String(value));
  const font = mono ? "font-mono" : "font-serif italic";

  const commit = () => {
    const trimmed = draft.trim();
    if (trimmed === "") {
      onCommit(null);
    } else if (/^\d+$/.test(trimmed) && (value === null || typeof value === "number")) {
      onCommit(parseInt(trimmed, 10));
    } else {
      onCommit(trimmed);
    }
    setEditing(false);
  };

  if (editing) {
    return (
      <input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          else if (e.key === "Escape") {
            setDraft(value === null || value === undefined ? "" : String(value));
            setEditing(false);
          }
        }}
        className={`${widthClass} ${font} bg-paper border border-cyan text-ink text-[12px] px-1 py-0.5 rounded-sm`}
      />
    );
  }

  return (
    <button
      onClick={() => {
        setDraft(value === null || value === undefined ? "" : String(value));
        setEditing(true);
      }}
      className={`${widthClass} ${font} text-left px-1 py-0.5 hover:bg-paper2/80 truncate`}
      title="Click to edit"
    >
      {value === null || value === undefined || value === "" ? (
        <span className="text-ink-dim/50">—</span>
      ) : (
        String(value)
      )}
    </button>
  );
}
