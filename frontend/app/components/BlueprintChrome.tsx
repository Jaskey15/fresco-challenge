"use client";

import React from "react";

type Props = {
  title?: string;       // shown in the top strip after "DWG·"
  rev?: string;         // "A", "B", ...
  sheet?: string;       // "1·1"
  children: React.ReactNode;
};

export function BlueprintChrome({ title = "01", rev = "A", sheet = "1·1", children }: Props) {
  return (
    <div className="relative min-h-screen">
      {/* top strip */}
      <div className="fixed top-0 left-0 right-0 z-20 h-8 px-4 flex items-center justify-between text-[10px] tracking-[0.25em] uppercase text-ink-dim border-b border-cyan-dim bg-paper/80 backdrop-blur">
        <div className="flex items-center gap-3">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-cyan animate-pulse" />
          <span>HARDWARE·SETS</span>
          <span>DWG·{title}</span>
          <span>REV·{rev}</span>
          <span>SHT·{sheet}</span>
        </div>
        <span>SCALE 1:1</span>
      </div>

      {/* corner crosshairs */}
      <Crosshair className="top-8 left-0" />
      <Crosshair className="top-8 right-0" />
      <Crosshair className="bottom-8 left-0" />
      <Crosshair className="bottom-8 right-0" />

      {/* body */}
      <main className="pt-8 pb-8 min-h-screen">{children}</main>

      {/* bottom strip */}
      <div className="fixed bottom-0 left-0 right-0 z-20 h-8 px-4 flex items-center justify-between text-[10px] tracking-[0.25em] uppercase text-ink-dim border-t border-cyan-dim bg-paper/80 backdrop-blur">
        <span>FRESCO · DIV·08 · HARDWARE SCHEDULES</span>
        <span>{new Date().toISOString().slice(0, 10)}</span>
      </div>
    </div>
  );
}

function Crosshair({ className = "" }: { className?: string }) {
  return (
    <div className={`pointer-events-none absolute ${className}`} aria-hidden="true">
      <div className="relative w-6 h-6">
        <div className="absolute top-1/2 left-0 w-full h-px bg-cyan-dim" />
        <div className="absolute top-0 left-1/2 w-px h-full bg-cyan-dim" />
      </div>
    </div>
  );
}
