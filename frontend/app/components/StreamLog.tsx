"use client";

import { useEffect, useRef } from "react";

export type StreamLine = { t: number; text: string; kind: "info" | "warn" | "error" | "done" };

export function StreamLog({ lines }: { lines: StreamLine[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [lines.length]);

  const color = (k: StreamLine["kind"]) =>
    k === "error" ? "text-red-300" : k === "warn" ? "text-amber-300" : k === "done" ? "text-cyan" : "text-ink-dim";

  return (
    <div
      ref={ref}
      className="font-mono text-[11px] tracking-wide h-40 overflow-y-auto border border-cyan-dim rounded-sm p-3 bg-paper2/40"
    >
      {lines.map((l, i) => (
        <div key={i} className={color(l.kind)}>
          <span className="text-ink-dim/60 mr-2">
            {new Date(l.t).toISOString().slice(11, 19)}
          </span>
          {l.text}
        </div>
      ))}
    </div>
  );
}
