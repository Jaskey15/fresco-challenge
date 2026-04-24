import { useState, useCallback, useMemo } from "react";
import type { ExtractionResult, Component, WorkingComponent } from "../types";
import PdfViewer from "./PdfViewer";
import SetGrid from "./SetGrid";
import DetailTable from "./DetailTable";

interface Props {
  result: ExtractionResult;
  onReset: () => void;
}

function cloneComponents(components: Component[]): WorkingComponent[] {
  return components.map((c, i) => ({
    ...c,
    _sourceIndex: i,
  }));
}

function makeEmptyComponent(): WorkingComponent {
  return {
    qty: null,
    description: null,
    catalog_number: null,
    mfr: null,
    finish: null,
    notes: null,
    _sourceIndex: null,
  };
}

interface DiffSummary {
  edited: number;
  added: number;
  removed: number;
}

function computeSetDiff(
  original: Component[],
  working: WorkingComponent[],
): DiffSummary {
  const FIELDS: (keyof Component)[] = [
    "qty", "description", "catalog_number", "mfr", "finish", "notes",
  ];

  let edited = 0;
  let added = 0;
  const seenOriginalIndices = new Set<number>();

  for (const wc of working) {
    if (wc._sourceIndex === null) {
      added++;
    } else {
      seenOriginalIndices.add(wc._sourceIndex);
      const orig = original[wc._sourceIndex];
      const changed = FIELDS.some(
        (f) => String(wc[f] ?? "") !== String(orig[f] ?? ""),
      );
      if (changed) edited++;
    }
  }

  const removed = original.length - seenOriginalIndices.size;
  return { edited, added, removed };
}

export default function ResultsView({ result, onReset }: Props) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [workingData, setWorkingData] = useState<
    Record<number, WorkingComponent[]>
  >({});

  const sets = result.hardware_sets;
  const activeSet = sets[activeIndex];

  const activeComponents: WorkingComponent[] =
    workingData[activeIndex] ?? cloneComponents(activeSet.components);

  const handleCellEdit = useCallback(
    (compIndex: number, field: string, value: string) => {
      setWorkingData((prev) => {
        const working = prev[activeIndex]
          ? prev[activeIndex].map((c) => ({ ...c }))
          : cloneComponents(sets[activeIndex].components);
        working[compIndex] = { ...working[compIndex], [field]: value };
        return { ...prev, [activeIndex]: working };
      });
    },
    [activeIndex, sets],
  );

  const handleDelete = useCallback(
    (compIndex: number) => {
      setWorkingData((prev) => {
        const working = prev[activeIndex]
          ? [...prev[activeIndex]]
          : cloneComponents(sets[activeIndex].components);
        working.splice(compIndex, 1);
        return { ...prev, [activeIndex]: working };
      });
    },
    [activeIndex, sets],
  );

  const handleAdd = useCallback(() => {
    setWorkingData((prev) => {
      const working = prev[activeIndex]
        ? [...prev[activeIndex]]
        : cloneComponents(sets[activeIndex].components);
      working.push(makeEmptyComponent());
      return { ...prev, [activeIndex]: working };
    });
  }, [activeIndex, sets]);

  const handleEditReset = useCallback(() => {
    setWorkingData((prev) => {
      const next = { ...prev };
      delete next[activeIndex];
      return next;
    });
  }, [activeIndex]);

  const activeSetDiff = useMemo((): DiffSummary => {
    const working = workingData[activeIndex];
    if (!working) return { edited: 0, added: 0, removed: 0 };
    return computeSetDiff(sets[activeIndex].components, working);
  }, [workingData, activeIndex, sets]);

  const totalDiff = useMemo((): DiffSummary => {
    let edited = 0, added = 0, removed = 0;
    for (const setIdx of Object.keys(workingData).map(Number)) {
      const diff = computeSetDiff(sets[setIdx].components, workingData[setIdx]);
      edited += diff.edited;
      added += diff.added;
      removed += diff.removed;
    }
    return { edited, added, removed };
  }, [workingData, sets]);

  const totalChanges = totalDiff.edited + totalDiff.added + totalDiff.removed;
  const activeChanges =
    activeSetDiff.edited + activeSetDiff.added + activeSetDiff.removed;

  const handleDownload = () => {
    const exportSets = sets.map((set, setIdx) => {
      const working = workingData[setIdx];
      if (!working) return set;
      return {
        ...set,
        components: working.map(({ _sourceIndex, ...comp }) => comp),
      };
    });

    const output = {
      source_pdf: result.source_pdf,
      hardware_sets: exportSets,
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

  const handleDownloadCSV = () => {
    const exportSets = sets.map((set, setIdx) => {
      const working = workingData[setIdx];
      if (!working) return set;
      return {
        ...set,
        components: working.map(({ _sourceIndex, ...comp }) => comp),
      };
    });

    const headers = [
      "set_number",
      "set_description",
      "set_notes",
      "is_not_used",
      "page",
      "qty",
      "description",
      "catalog_number",
      "mfr",
      "finish",
      "notes",
    ];

    const escapeCSV = (val: unknown): string => {
      if (val === null || val === undefined) return "";
      const str = String(val);
      if (str.includes(",") || str.includes('"') || str.includes("\n"))
        return `"${str.replace(/"/g, '""')}"`;
      return str;
    };

    const rows = [headers.join(",")];
    for (const set of exportSets) {
      if (set.components.length === 0) {
        rows.push(
          [
            set.set_number,
            set.description,
            set.notes,
            set.is_not_used,
            set.location.page,
            "",
            "",
            "",
            "",
            "",
            "",
          ]
            .map(escapeCSV)
            .join(",")
        );
      } else {
        for (const comp of set.components) {
          rows.push(
            [
              set.set_number,
              set.description,
              set.notes,
              set.is_not_used,
              set.location.page,
              comp.qty,
              comp.description,
              comp.catalog_number,
              comp.mfr,
              comp.finish,
              comp.notes,
            ]
              .map(escapeCSV)
              .join(",")
          );
        }
      }
    }

    const blob = new Blob([rows.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = result.source_pdf.replace(/\.pdf$/i, "_hardware_sets.csv");
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

  const diffBadgeParts: string[] = [];
  if (totalDiff.edited > 0) diffBadgeParts.push(`${totalDiff.edited} edited`);
  if (totalDiff.added > 0) diffBadgeParts.push(`${totalDiff.added} added`);
  if (totalDiff.removed > 0) diffBadgeParts.push(`${totalDiff.removed} removed`);

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
        <div className="flex items-center gap-2">
          {totalChanges > 0 && (
            <span className="text-[10px] px-2 py-1 bg-accent-subtle border border-accent/30 rounded text-accent font-heading">
              {diffBadgeParts.join(" · ")}
            </span>
          )}
          <button
            onClick={handleDownloadCSV}
            className="text-xs px-3 py-1.5 rounded bg-accent text-backdrop font-heading font-semibold hover:bg-accent/90 transition-colors"
          >
            Download CSV
          </button>
          <button
            onClick={handleDownload}
            className="text-xs px-3 py-1.5 rounded bg-accent text-backdrop font-heading font-semibold hover:bg-accent/90 transition-colors"
          >
            Download JSON
          </button>
        </div>
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
            components={activeComponents}
            editCount={activeChanges}
            onCellEdit={handleCellEdit}
            onDelete={handleDelete}
            onAdd={handleAdd}
            onReset={handleEditReset}
          />
        </div>
      </div>
    </div>
  );
}
