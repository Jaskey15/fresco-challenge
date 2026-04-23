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
      <div className="min-h-screen bg-backdrop flex items-center justify-center p-8">
        <div className="max-w-md text-center">
          <div className="text-4xl mb-4">⚠️</div>
          <h2 className="text-xl font-heading font-semibold text-primary mb-2">
            Extraction Failed
          </h2>
          <p className="text-error text-sm mb-6">{error}</p>
          <button
            onClick={onReset}
            className="px-4 py-2 bg-accent text-backdrop rounded-lg text-sm font-heading hover:bg-accent/90 transition-colors"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-backdrop flex items-center justify-center p-8">
      <div className="max-w-md text-center">
        {/* Spinner */}
        <div className="mb-6 flex justify-center">
          <div className="w-10 h-10 border-3 border-border border-t-accent rounded-full animate-spin" />
        </div>

        <h2 className="text-xl font-heading font-semibold text-primary mb-2">
          {latest?.phase === "extract"
            ? "Extracting Hardware Sets"
            : "Scanning Document"}
        </h2>

        <p className="text-secondary text-sm">
          {latest?.message ?? "Starting..."}
        </p>

        {/* Progress log */}
        {progress.length > 1 && (
          <div className="mt-6 text-left bg-surface rounded-lg border border-border p-3 max-h-40 overflow-y-auto">
            {progress.map((p, i) => (
              <div key={i} className="text-xs text-secondary font-heading py-0.5">
                <span className="text-dim mr-2">
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
