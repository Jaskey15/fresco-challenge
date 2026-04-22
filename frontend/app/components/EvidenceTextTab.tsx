"use client";

import type { SetLocation } from "@/lib/types";

type Props = { location: SetLocation | null; filename: string };

export function EvidenceTextTab({ location, filename }: Props) {
  if (!location) {
    return (
      <div className="text-[11px] text-ink-dim font-mono p-3">
        Select a set to view its source lines.
      </div>
    );
  }
  return (
    <div className="p-3 text-[11px] font-mono text-ink-dim">
      <div className="uppercase tracking-[0.25em] mb-2">
        {filename} · page {location.page} · lines {location.line_range[0]}–{location.line_range[1]}
      </div>
      <div className="opacity-70">
        The primary evidence pane renders the PDF page with a highlight overlay. This tab is a
        placeholder for the pdftotext line view, which will stream in a future iteration.
      </div>
    </div>
  );
}
