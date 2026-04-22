import type { ProgressEvent } from "../types";

interface Props {
  progress: ProgressEvent[];
  error: string | null;
  onReset: () => void;
}

export default function ProcessingView({ progress, error, onReset }: Props) {
  const latest = progress[progress.length - 1];

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-8">
        <div className="max-w-md text-center">
          <div className="text-4xl mb-4">⚠️</div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">
            Extraction Failed
          </h2>
          <p className="text-gray-500 text-sm mb-6">{error}</p>
          <button
            onClick={onReset}
            className="px-4 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-800"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-8">
      <div className="max-w-md text-center">
        {/* Spinner */}
        <div className="mb-6 flex justify-center">
          <div className="w-10 h-10 border-3 border-gray-200 border-t-green-500 rounded-full animate-spin" />
        </div>

        <h2 className="text-xl font-semibold text-gray-900 mb-2">
          {latest?.phase === "extract"
            ? "Extracting Hardware Sets"
            : "Scanning Document"}
        </h2>

        <p className="text-gray-500 text-sm">
          {latest?.message ?? "Starting..."}
        </p>

        {/* Progress log */}
        {progress.length > 1 && (
          <div className="mt-6 text-left bg-white rounded-lg border border-gray-200 p-3 max-h-40 overflow-y-auto">
            {progress.map((p, i) => (
              <div key={i} className="text-xs text-gray-400 py-0.5">
                <span className="text-gray-300 mr-2">
                  {p.phase === "filter" ? "🔍" : "⚙️"}
                </span>
                {p.message}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
