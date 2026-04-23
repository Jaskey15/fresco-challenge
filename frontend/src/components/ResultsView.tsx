import { useState } from "react";
import type { ExtractionResult } from "../types";
import PdfViewer from "./PdfViewer";
import SetGrid from "./SetGrid";
import DetailTable from "./DetailTable";
import JsonViewer from "./JsonViewer";

interface Props {
  result: ExtractionResult;
  onReset: () => void;
}

export default function ResultsView({ result, onReset }: Props) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [edits, setEdits] = useState<
    Record<number, Record<number, Record<string, string>>>
  >({});
  const [showJson, setShowJson] = useState(false);

  const sets = result.hardware_sets;
  const activeSet = sets[activeIndex];

  const editCount = Object.values(edits[activeIndex] ?? {}).reduce(
    (sum, fields) => sum + Object.keys(fields).length,
    0,
  );

  const handleCellEdit = (compIndex: number, field: string, value: string) => {
    setEdits((prev) => ({
      ...prev,
      [activeIndex]: {
        ...prev[activeIndex],
        [compIndex]: {
          ...(prev[activeIndex]?.[compIndex] ?? {}),
          [field]: value,
        },
      },
    }));
  };

  const handleReset = () => {
    setEdits((prev) => {
      const next = { ...prev };
      delete next[activeIndex];
      return next;
    });
  };

  const handleDownload = () => {
    const editedSets = result.hardware_sets.map((set, setIdx) => {
      const setEdits = edits[setIdx];
      if (!setEdits) return set;
      return {
        ...set,
        components: set.components.map((comp, compIdx) => {
          const compEdits = setEdits[compIdx];
          if (!compEdits) return comp;
          return { ...comp, ...compEdits };
        }),
      };
    });

    const output = {
      source_pdf: result.source_pdf,
      hardware_sets: editedSets,
      diagnostics: result.diagnostics,
    };

    const blob = new Blob([JSON.stringify(output, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = result.source_pdf.replace(/\.pdf$/i, "_hardware_sets.json");
    a.click();
    URL.revokeObjectURL(url);
  };

  if (sets.length === 0) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-8">
        <div className="text-center">
          <h2 className="text-xl font-semibold text-gray-900 mb-2">
            No Hardware Sets Found
          </h2>
          <p className="text-gray-500 text-sm mb-6">
            The document was scanned but no hardware sets were detected.
          </p>
          <button
            onClick={onReset}
            className="px-4 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-800"
          >
            Try Another Document
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Top bar */}
      <div className="h-12 px-4 border-b border-gray-200 bg-white flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={onReset}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            &larr; Back
          </button>
          <span className="text-sm font-semibold text-gray-800">
            {result.source_pdf}
          </span>
          <span className="text-xs text-green-600 font-medium">
            {sets.length} sets extracted
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowJson((s) => !s)}
            className={`text-xs px-2 py-1 rounded border ${
              showJson
                ? "bg-blue-50 border-blue-300 text-blue-700"
                : "border-gray-200 text-gray-500 hover:border-gray-300"
            }`}
          >
            {showJson ? "Hide JSON" : "Show JSON"}
          </button>
          <button
            onClick={handleDownload}
            className="text-xs px-2 py-1 rounded border border-gray-200 text-gray-500 hover:border-gray-300"
          >
            Download JSON
          </button>
          <span className="text-xs text-gray-400 ml-2">
            {result.diagnostics.pages_with_sets} pages &middot;{" "}
            {result.diagnostics.llm_calls} LLM call
            {result.diagnostics.llm_calls !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {/* Two-panel layout */}
      <div className="flex-1 flex min-h-0">
        {/* Left: PDF Viewer (~35%) */}
        <div className="w-[35%] min-w-[280px] border-r border-gray-200">
          <PdfViewer
            sessionId={result.session_id}
            location={activeSet.location}
            continuedOn={activeSet.continued_on}
            pageLayouts={result.page_layouts}
          />
        </div>

        {/* Right: SetGrid + DetailTable (~65%) */}
        <div className="flex-1 min-w-0 flex flex-col">
          <SetGrid
            sets={sets}
            activeIndex={activeIndex}
            onSelect={setActiveIndex}
          />
          <DetailTable
            set={activeSet}
            edits={edits[activeIndex] ?? {}}
            editCount={editCount}
            onCellEdit={handleCellEdit}
            onReset={handleReset}
          />
          {showJson && (
            <JsonViewer set={activeSet} edits={edits[activeIndex] ?? {}} />
          )}
        </div>
      </div>
    </div>
  );
}
