// frontend/src/components/SourcePanel.tsx
import { useMemo } from "react";
import type { HardwareSet, NumberedLine } from "../types";

interface Props {
  set: HardwareSet;
  pageLayouts: Record<string, NumberedLine[]>;
}

export default function SourcePanel({ set, pageLayouts }: Props) {
  const pages = useMemo(() => {
    const result: Array<{
      pageNumber: number;
      lines: NumberedLine[];
      highlightRange: [number, number];
    }> = [];

    // Primary location
    const primaryLines = pageLayouts[String(set.location.page)];
    if (primaryLines) {
      result.push({
        pageNumber: set.location.page,
        lines: primaryLines,
        highlightRange: set.location.line_range,
      });
    }

    // Continued-on pages
    for (const cont of set.continued_on) {
      const contLines = pageLayouts[String(cont.page)];
      if (contLines) {
        result.push({
          pageNumber: cont.page,
          lines: contLines,
          highlightRange: cont.line_range,
        });
      }
    }

    return result;
  }, [set, pageLayouts]);

  if (pages.length === 0) {
    return (
      <div className="flex-1 bg-white border-r border-gray-200 flex items-center justify-center text-gray-400 text-sm">
        No source data available
      </div>
    );
  }

  return (
    <div className="flex-1 min-w-0 bg-white border-r border-gray-200 flex flex-col">
      {pages.map((page, pageIdx) => (
        <div key={pageIdx} className="flex flex-col flex-1 min-h-0">
          {/* Page header */}
          <div className="px-3 py-2 border-b border-gray-100 flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-500">
              📄 Page {page.pageNumber}
            </span>
            {pages.length > 1 && (
              <span className="text-[10px] text-gray-400">
                {pageIdx === 0 ? "primary" : "continued"}
              </span>
            )}
          </div>

          {/* Lines */}
          <div className="flex-1 overflow-y-auto p-2 font-mono text-[11px] leading-[1.8]">
            {page.lines.map((line) => {
              const inRange =
                line.number >= page.highlightRange[0] &&
                line.number <= page.highlightRange[1];
              return (
                <div
                  key={line.number}
                  className={`flex ${
                    inRange
                      ? "bg-green-50 border-l-2 border-green-500 -ml-[2px] pl-[2px] text-gray-900"
                      : "text-gray-400"
                  }`}
                >
                  <span
                    className={`w-7 text-right mr-2 select-none shrink-0 ${
                      inRange ? "text-green-600 font-semibold" : "text-gray-300"
                    }`}
                  >
                    {line.number}
                  </span>
                  <span className="whitespace-pre overflow-x-auto">{line.text}</span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
