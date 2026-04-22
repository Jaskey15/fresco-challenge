// frontend/src/components/SetSidebar.tsx
import { useMemo, useState } from "react";
import type { HardwareSet } from "../types";

interface Props {
  sets: HardwareSet[];
  activeIndex: number;
  onSelect: (index: number) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export default function SetSidebar({
  sets,
  activeIndex,
  onSelect,
  collapsed,
  onToggleCollapse,
}: Props) {
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

  if (collapsed) {
    return (
      <div className="w-10 bg-gray-50 border-r border-gray-200 flex flex-col items-center pt-3">
        <button
          onClick={onToggleCollapse}
          className="text-gray-400 hover:text-gray-600 text-xs"
          title="Expand sidebar"
        >
          ▶
        </button>
      </div>
    );
  }

  return (
    <div className="w-[160px] min-w-[160px] bg-gray-50 border-r border-gray-200 flex flex-col">
      {/* Header */}
      <div className="px-3 pt-3 pb-2 flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
          {sets.length} Sets
        </span>
        <button
          onClick={onToggleCollapse}
          className="text-gray-400 hover:text-gray-600 text-xs"
          title="Collapse sidebar"
        >
          ◀
        </button>
      </div>

      {/* Search */}
      <div className="px-3 pb-2">
        <input
          type="text"
          placeholder="Filter..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="w-full text-xs px-2 py-1.5 border border-gray-200 rounded bg-white placeholder:text-gray-300 focus:outline-none focus:border-green-400"
        />
      </div>

      {/* Set list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-1">
        {filtered.map(({ set, index }) => {
          const isActive = index === activeIndex;
          return (
            <button
              key={index}
              onClick={() => onSelect(index)}
              className={`w-full text-left px-2 py-2 rounded-md text-xs transition-colors ${
                isActive
                  ? "bg-green-500 text-white"
                  : set.is_not_used
                    ? "bg-white border border-gray-100 text-gray-400 hover:border-gray-300"
                    : "bg-white border border-gray-100 text-gray-700 hover:border-gray-300"
              }`}
            >
              <div className="font-semibold">
                {set.set_number}
                <span className={`font-normal ml-1 ${isActive ? "opacity-80" : "text-gray-400"}`}>
                  {set.description
                    ? set.description.length > 12
                      ? set.description.slice(0, 12) + "…"
                      : set.description
                    : set.is_not_used
                      ? "NOT USED"
                      : ""}
                </span>
              </div>
              <div className={`mt-0.5 ${isActive ? "opacity-70" : "text-gray-400"}`}>
                {set.components.length} comp · pg {set.location.page}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
