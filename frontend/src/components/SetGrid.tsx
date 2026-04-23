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
    <div className="px-3 py-2 border-b border-gray-200 bg-white">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide shrink-0">
          {sets.length} Sets
        </span>
        <input
          type="text"
          placeholder="Filter sets..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="flex-1 text-xs px-2 py-1 border border-gray-200 rounded bg-white placeholder:text-gray-300 focus:outline-none focus:border-green-400"
        />
      </div>
      <div className="flex flex-wrap gap-1.5">
        {filtered.map(({ set, index }) => (
          <button
            key={index}
            onClick={() => onSelect(index)}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              index === activeIndex
                ? "bg-green-500 text-white shadow-sm"
                : set.is_not_used
                  ? "bg-gray-100 text-gray-400 hover:bg-gray-200"
                  : "bg-gray-100 text-gray-700 hover:bg-gray-200"
            }`}
            title={set.description || set.set_number}
          >
            {set.confidence < 0.5 && index !== activeIndex && (
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400 mr-1 align-middle" />
            )}
            {set.set_number}
          </button>
        ))}
      </div>
    </div>
  );
}
