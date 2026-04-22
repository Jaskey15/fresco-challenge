"use client";

import { useEffect, useMemo, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import type { BBox, SetLocation } from "@/lib/types";

// Serve pdfjs worker from the same version as pdfjs-dist
pdfjs.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.mjs`;

type Props = {
  pdfUrl: string;             // `${API}/pdf/${sessionId}`
  location: SetLocation | null;
  continued: SetLocation[];
};

type PageDims = { width: number; height: number };

export function EvidencePane({ pdfUrl, location, continued }: Props) {
  const pageNum = location?.page ?? 1;
  const [dims, setDims] = useState<PageDims | null>(null);
  const [renderedWidth, setRenderedWidth] = useState(0);

  // Reset dims when navigating to a different PDF page
  useEffect(() => {
    setDims(null);
  }, [pageNum]);

  const bboxes = useMemo(() => {
    const out: Array<{ page: number; bbox: BBox }> = [];
    if (location?.bbox) out.push({ page: location.page, bbox: location.bbox });
    for (const c of continued) if (c.bbox) out.push({ page: c.page, bbox: c.bbox });
    return out.filter((b) => b.page === pageNum);
  }, [location, continued, pageNum]);

  const scale = useMemo(() => {
    if (!dims || !renderedWidth) return 1;
    return renderedWidth / dims.width;
  }, [dims, renderedWidth]);

  return (
    <div className="relative" ref={(el) => setRenderedWidth(el?.clientWidth ?? 0)}>
      <Document
        file={pdfUrl}
        loading={<div className="text-[11px] text-ink-dim font-mono">loading PDF…</div>}
        error={<div className="text-[11px] text-red-300 font-mono">PDF failed to load.</div>}
      >
        <Page
          pageNumber={pageNum}
          width={renderedWidth || undefined}
          onLoadSuccess={(p) => setDims({ width: p.width, height: p.height })}
          renderAnnotationLayer={false}
          renderTextLayer={false}
        />
      </Document>

      {dims &&
        bboxes.map(({ bbox }, i) => {
          const [x0, top, x1, bottom] = bbox;
          return (
            <div
              key={i}
              aria-hidden
              className="pointer-events-none absolute border-2 border-cyan/80 bg-cyan/10 rounded-sm"
              style={{
                left: x0 * scale,
                top: top * scale,
                width: (x1 - x0) * scale,
                height: (bottom - top) * scale,
              }}
            />
          );
        })}
    </div>
  );
}
