// frontend/src/components/ResultsView.tsx (stub — full implementation in Task 10)
import type { ExtractionResult } from "../types";

interface Props {
  result: ExtractionResult;
  onReset: () => void;
}

export default function ResultsView({ result, onReset }: Props) {
  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <button onClick={onReset} className="text-sm text-gray-500 hover:text-gray-700">
        ← Upload another
      </button>
      <pre className="mt-4 text-xs bg-white p-4 rounded-lg border overflow-auto max-h-[80vh]">
        {JSON.stringify(result, null, 2)}
      </pre>
    </div>
  );
}
