"use client";

import React, { useCallback, useRef, useState } from "react";

type Props = {
  onFile: (file: File) => void;
  disabled?: boolean;
};

export function DropZone({ onFile, disabled }: Props) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    (file: File | undefined) => {
      if (!file) return;
      if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
        alert("Please drop a PDF.");
        return;
      }
      onFile(file);
    },
    [onFile],
  );

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (disabled) return;
    handleFile(e.dataTransfer.files?.[0]);
  };

  return (
    <div className="relative mx-auto w-full max-w-[860px] px-8">
      {/* dimension callouts top */}
      <div className="flex items-center justify-center gap-3 text-[10px] tracking-[0.3em] uppercase text-ink-dim mb-3">
        <span>↔</span>
        <span>860 PX</span>
        <span>↔</span>
      </div>

      {/* glow halo */}
      <div
        className="absolute inset-8 -z-10 blur-3xl opacity-50"
        style={{
          background:
            "radial-gradient(closest-side, rgba(122,201,255,0.35), transparent 70%)",
        }}
      />

      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`group relative w-full aspect-[1.7/1] border rounded-sm transition-all duration-200
          ${dragging ? "border-cyan bg-paper2/70" : "border-cyan-dim hover:border-cyan hover:-translate-y-0.5"}
          ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
          flex items-center justify-center`}
      >
        <span className="font-serif text-5xl md:text-6xl tracking-tight">
          Drop your <em className="text-cyan">specbook.</em>
        </span>

        <span className="absolute bottom-4 left-1/2 -translate-x-1/2 text-[10px] tracking-[0.3em] uppercase text-ink-dim">
          or click to browse · PDF · up to 25 MB
        </span>
      </button>

      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        onChange={(e) => handleFile(e.target.files?.[0])}
      />

      {/* dimension callouts bottom */}
      <div className="flex items-center justify-center gap-3 text-[10px] tracking-[0.3em] uppercase text-ink-dim mt-3">
        <span>↕</span>
        <span>SCALE 1:1</span>
        <span>↕</span>
      </div>
    </div>
  );
}
