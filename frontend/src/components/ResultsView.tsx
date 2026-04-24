import { useState } from "react";
import type { ExtractionResult } from "../types";
import PdfViewer from "./PdfViewer";
import SetGrid from "./SetGrid";
import DetailTable from "./DetailTable";

interface Props {
  result: ExtractionResult;
  onReset: () => void;
}

export default function ResultsView({ result, onReset }: Props) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [edits, setEdits] = useState<
    Record<number, Record<number, Record<string, string>>>
  >({});
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
      <div className="min-h-screen bg-backdrop flex items-center justify-center p-8">
        <div className="text-center">
          <h2 className="text-xl font-heading font-semibold text-primary mb-2">
            No Hardware Sets Found
          </h2>
          <p className="text-muted text-sm mb-6">
            The document was scanned but no hardware sets were detected.
          </p>
          <button
            onClick={onReset}
            className="px-4 py-2 bg-accent text-backdrop rounded-lg text-sm font-heading hover:bg-accent/90 transition-colors"
          >
            Try Another Document
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-backdrop">
      {/* Top bar */}
      <div className="h-12 px-4 border-b border-border bg-surface flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={onReset}
            className="text-xs text-dim hover:text-muted transition-colors"
          >
            &larr; Back
          </button>
          <span className="text-sm font-heading font-semibold text-primary">
            {result.source_pdf}
          </span>
          <span className="text-[11px] font-heading text-accent bg-accent-subtle px-2 py-0.5 rounded">
            {sets.length} sets &middot; {result.diagnostics.pages_with_sets} pages
          </span>
        </div>
        <button
          onClick={handleDownload}
          className="text-xs px-3 py-1.5 rounded bg-accent text-backdrop font-heading font-semibold hover:bg-accent/90 transition-colors"
        >
          Download JSON
        </button>
      </div>

      {/* Two-panel layout */}
      <div className="flex-1 flex min-h-0">
        {/* Left: PDF Viewer (~35%) */}
        <div className="w-[35%] min-w-[280px] border-r border-border">
          <PdfViewer
            sessionId={result.session_id}
            setNumber={activeSet.set_number}
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

        </div>
      </div>
    </div>
  );
}
