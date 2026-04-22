"use client";

import { useState } from "react";
import type { Correction, HardwareSet } from "@/lib/types";
import { buildExport } from "@/lib/corrections";

type Props = {
  sourceFilename: string;
  sets: HardwareSet[];
  applied: Record<number, HardwareSet>;
  deletedSets: Set<string>;
  corrections: Correction[];
};

export function ExportMenu({ sourceFilename, sets, applied, deletedSets, corrections }: Props) {
  const [copied, setCopied] = useState(false);

  const resolved = sets
    .map((s, i) => applied[i] ?? s)
    .filter((s) => !deletedSets.has(s.set_number));

  const payload = buildExport({
    sourceFilename,
    appliedSets: resolved,
    corrections,
    extractedAt: new Date().toISOString(),
  });

  const download = () => {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${sourceFilename.replace(/\.pdf$/i, "")}.hardware-sets.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const copy = async () => {
    await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={download}
        disabled={!sets.length}
        className="text-[10px] uppercase tracking-[0.3em] font-mono text-paper bg-cyan px-3 py-1 rounded-sm disabled:opacity-40"
      >
        DOWNLOAD JSON
      </button>
      <button
        onClick={copy}
        disabled={!sets.length}
        className="text-[10px] uppercase tracking-[0.3em] font-mono text-cyan border border-cyan-dim px-3 py-1 rounded-sm hover:bg-cyan/10 disabled:opacity-40"
      >
        {copied ? "COPIED ✓" : "COPY"}
      </button>
    </div>
  );
}
