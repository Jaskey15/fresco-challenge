// frontend/src/components/JsonViewer.tsx
import type { HardwareSet } from "../types";

interface Props {
  set: HardwareSet;
  edits: Record<number, Record<string, string>>;
}

export default function JsonViewer({ set, edits }: Props) {
  const edited = {
    ...set,
    components: set.components.map((comp, i) => {
      const compEdits = edits[i];
      if (!compEdits) return comp;
      return { ...comp, ...compEdits };
    }),
  };

  return (
    <div className="border-t border-gray-200 bg-gray-50 max-h-64 overflow-auto">
      <pre className="p-3 text-[11px] text-gray-600 font-mono leading-relaxed">
        {JSON.stringify(edited, null, 2)}
      </pre>
    </div>
  );
}
