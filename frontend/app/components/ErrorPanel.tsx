"use client";

import Link from "next/link";

const COPY: Record<string, { title: string; body: string }> = {
  scanned_pdf: {
    title: "No extractable text",
    body:
      "This PDF looks scanned. The v1 extractor doesn't OCR — we'd need a text-native specbook.",
  },
  no_schedule: {
    title: "Division 08 hardware schedule not detected",
    body:
      "We scanned the whole PDF but didn't find a 08 71 00 door-hardware region. Double-check you uploaded the right file.",
  },
  api_error: {
    title: "Extraction interrupted",
    body:
      "The extraction pipeline hit a recoverable error. Any sets already extracted are preserved below — you can retry or export what you have.",
  },
  parse_error: {
    title: "Couldn't read this PDF",
    body:
      "The file wasn't readable as a valid PDF. Try re-exporting from the source.",
  },
};

export function ErrorPanel({ code, message }: { code: string; message: string }) {
  const { title, body } = COPY[code] ?? { title: "Extraction error", body: message };
  return (
    <div className="mx-auto max-w-xl my-10 border border-cyan-dim rounded-sm bg-paper2/60 p-8">
      <div className="text-[10px] tracking-[0.3em] uppercase text-ink-dim">
        ERROR · {code}
      </div>
      <h2 className="font-serif text-3xl mt-2 mb-3">
        <em>{title}</em>
      </h2>
      <p className="text-[13px] leading-relaxed text-ink-dim mb-2">{body}</p>
      <p className="text-[11px] font-mono text-ink-dim/70 mb-6">{message}</p>
      <Link
        href="/"
        className="text-[10px] tracking-[0.3em] uppercase font-mono text-cyan border border-cyan-dim px-3 py-1 rounded-sm hover:bg-cyan/10"
      >
        UPLOAD ANOTHER
      </Link>
    </div>
  );
}
