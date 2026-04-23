import { useCallback, useEffect, useRef, useState } from "react";
import type { Sample } from "../types";

interface Props {
  onFileSelect: (file: File) => void;
  onSampleSelect: (sampleId: string) => void;
}

export default function UploadView({ onFileSelect, onSampleSelect }: Props) {
  const [samples, setSamples] = useState<Sample[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch("/api/samples")
      .then((r) => r.json())
      .then(setSamples)
      .catch(() => {});
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file?.type === "application/pdf") onFileSelect(file);
    },
    [onFileSelect],
  );

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) onFileSelect(file);
    },
    [onFileSelect],
  );

  return (
    <div className="min-h-screen bg-backdrop flex items-center justify-center p-8">
      <div className="max-w-2xl w-full">
        <h1 className="text-3xl font-heading font-bold text-primary text-center mb-2 tracking-[0.02em]">
          Hardware Sets Extractor
        </h1>
        <p className="text-muted text-center mb-8">
          Upload a Division 08 specbook PDF to extract hardware sets
        </p>

        {/* Dropzone */}
        <div
          className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
            dragOver
              ? "border-accent bg-accent-subtle"
              : "border-border hover:border-accent/40 bg-surface"
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
        >
          <div className="text-4xl mb-3">📄</div>
          <p className="text-primary font-medium">
            Drop a PDF here or click to browse
          </p>
          <p className="text-muted text-sm mt-1">Division 08 specbook only</p>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={handleFileChange}
          />
        </div>

        {/* Sample cards */}
        {samples.length > 0 && (
          <div className="mt-8">
            <p className="text-sm text-muted mb-3 text-center">
              Or try a sample specbook:
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {samples.map((s) => (
                <button
                  key={s.id}
                  onClick={() => onSampleSelect(s.id)}
                  className="bg-surface border border-border rounded-lg p-4 text-left hover:border-accent hover:bg-elevated transition-colors"
                >
                  <div className="font-medium text-primary text-sm">
                    {s.name}
                  </div>
                  <div className="text-muted text-xs mt-1">{s.label}</div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
