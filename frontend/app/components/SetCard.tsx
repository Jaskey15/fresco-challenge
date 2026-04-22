"use client";

import type { Component, EditableField, HardwareSet } from "@/lib/types";
import { ComponentRow } from "./ComponentRow";

type Props = {
  set: HardwareSet;
  onEditField: (componentIndex: number, field: EditableField, value: string | number | null) => void;
  onAddComponent: () => void;
  onRemoveComponent: (index: number) => void;
  onDeleteSet: () => void;
  isDeleted: boolean;
};

export function SetCard({
  set,
  onEditField,
  onAddComponent,
  onRemoveComponent,
  onDeleteSet,
  isDeleted,
}: Props) {
  return (
    <div className={isDeleted ? "opacity-40" : ""}>
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <div className="font-mono text-[10px] tracking-[0.3em] uppercase text-ink-dim">
            SET · {set.set_number} · p.{set.location.page}
            {set.is_not_used ? " · NOT USED" : ""}
          </div>
          <h2 className="font-serif text-3xl mt-1">
            {set.description ? <em>{set.description}</em> : <span className="text-ink-dim">(untitled)</span>}
          </h2>
        </div>

        <div className="flex items-center gap-2">
          <div className="text-[10px] tracking-[0.3em] uppercase text-ink-dim">
            CONF {set.confidence.toFixed(2)}
          </div>
          <button
            onClick={onDeleteSet}
            className="text-[10px] tracking-[0.2em] uppercase font-mono text-ink-dim hover:text-red-300 border border-cyan-dim/40 px-2 py-1 rounded-sm"
          >
            {isDeleted ? "UNDO DELETE" : "DELETE SET"}
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2 py-1 border-b border-cyan-dim font-mono text-[10px] tracking-[0.25em] uppercase text-ink-dim">
        <span className="w-10">QTY</span>
        <span className="flex-1">DESCRIPTION</span>
        <span className="w-48">CATALOG</span>
        <span className="w-20">MFR</span>
        <span className="w-20">FINISH</span>
        <span className="w-32">NOTES</span>
        <span className="w-12">CONF</span>
        <span className="w-6" />
      </div>

      {set.components.map((c: Component, i: number) => (
        <ComponentRow
          key={i}
          component={c}
          onEdit={(field, value) => onEditField(i, field, value)}
          onRemove={() => onRemoveComponent(i)}
        />
      ))}

      {!set.components.length && (
        <div className="py-3 text-[11px] text-ink-dim font-mono italic">
          {set.is_not_used ? "NOT USED — no components." : "No components emitted."}
        </div>
      )}

      <button
        onClick={onAddComponent}
        className="mt-3 text-[10px] tracking-[0.3em] uppercase font-mono text-cyan border border-cyan-dim/60 px-3 py-1 rounded-sm hover:bg-cyan/10"
      >
        + ADD COMPONENT
      </button>
    </div>
  );
}
