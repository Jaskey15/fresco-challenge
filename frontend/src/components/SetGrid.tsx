import { useMemo, useState } from "react";
import type { HardwareSet } from "../types";

interface Props {
  sets: HardwareSet[];
  activeIndex: number;
  onSelect: (index: number) => void;
}

export default function SetGrid({ sets, activeIndex, onSelect }: Props) {
  const [filter, setFilter] = useState("");

  const filtered = useMemo(() => {
    if (!filter) return sets.map((s, i) => ({ set: s, index: i }));
    const q = filter.toLowerCase();
    return sets
      .map((s, i) => ({ set: s, index: i }))
      .filter(
        ({ set }) =>
          set.set_number.toLowerCase().includes(q) ||
          (set.description?.toLowerCase().includes(q) ?? false),
      );
  }, [sets, filter]);

  return (
    <div className="px-3 py-2 border-b border-border bg-backdrop">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs font-heading font-semibold text-dim uppercase tracking-wide shrink-0">
          {sets.length} Sets
        </span>
        <input
          type="text"
          placeholder="Filter sets..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="flex-1 text-xs px-2 py-1 border border-border rounded bg-surface font-heading text-primary placeholder:text-muted focus:outline-none focus:border-accent transition-colors"
        />
      </div>
      <div className="flex flex-wrap gap-1.5">
        {filtered.map(({ set, index }) => (
          <button
            key={index}
            onClick={() => onSelect(index)}
            className={`px-2.5 py-1 rounded text-xs font-heading font-bold transition-colors ${
              index === activeIndex
                ? "bg-accent text-backdrop shadow-sm"
                : "bg-surface text-dim border border-border hover:bg-elevated"
            }`}
            title={set.description || set.set_number}
          >
            {set.set_number}
          </button>
        ))}
      </div>
    </div>
  );
}
