import { useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import type { SetLocation, PageLayout } from "../types";

pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

interface Props {
  sessionId: string;
  location: SetLocation;
  continuedOn: SetLocation[];
  pageLayouts: Record<string, PageLayout>;
}

export default function PdfViewer({
  sessionId,
  location,
  continuedOn,
  pageLayouts,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      setContainerWidth(entries[0].contentRect.width);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const allLocations = useMemo(() => {
    const locs: Array<{
      page: number;
      bbox: [number, number, number, number] | null;
      label: string;
    }> = [];
    locs.push({ page: location.page, bbox: location.bbox, label: "primary" });
    for (const cont of continuedOn) {
      locs.push({ page: cont.page, bbox: cont.bbox, label: "continued" });
    }
    return locs;
  }, [location, continuedOn]);

  const pdfUrl = `/api/pdf/${sessionId}`;

  return (
    <div ref={containerRef} className="h-full overflow-y-auto bg-gray-100">
      <Document
        file={pdfUrl}
        loading={
          <div className="flex items-center justify-center h-full text-sm text-gray-400">
            Loading PDF...
          </div>
        }
        error={
          <div className="flex items-center justify-center h-full text-sm text-red-400 p-4 text-center">
            Session expired — please re-upload the PDF.
          </div>
        }
      >
        {allLocations.map((loc, i) => {
          const layout = pageLayouts[String(loc.page)];
          const scale =
            layout && containerWidth ? containerWidth / layout.page_width : 1;

          return (
            <div key={`${loc.page}-${i}`} className="mb-2">
              <div className="text-[10px] text-gray-400 px-2 py-1 bg-gray-200/50">
                Page {loc.page}
                {allLocations.length > 1 && (
                  <span className="ml-1 text-gray-300">· {loc.label}</span>
                )}
              </div>
              <div className="relative">
                <Page
                  pageNumber={loc.page}
                  width={containerWidth || undefined}
                  renderAnnotationLayer={false}
                  renderTextLayer={false}
                />
                {loc.bbox && layout && (
                  <div
                    className="absolute pointer-events-none border-2 border-green-500/80 bg-green-500/10 rounded-sm"
                    style={{
                      left: loc.bbox[0] * scale,
                      top: loc.bbox[1] * scale,
                      width: (loc.bbox[2] - loc.bbox[0]) * scale,
                      height: (loc.bbox[3] - loc.bbox[1]) * scale,
                    }}
                  />
                )}
              </div>
            </div>
          );
        })}
      </Document>
    </div>
  );
}
