"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { BlueprintChrome } from "./components/BlueprintChrome";
import { DropZone } from "./components/DropZone";
import { hashPdf } from "@/lib/hashPdf";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Landing() {
  const router = useRouter();
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setUploading(true);
      setError(null);
      try {
        const pdfHash = await hashPdf(file);

        // Push the bytes directly to /extract — backend returns an SSE stream,
        // so we kick off the request on the /extract page via POST + ReadableStream.
        // Here we only stash the file in sessionStorage as a handoff, along with its hash.
        const buffer = await file.arrayBuffer();
        const base64 = btoa(
          String.fromCharCode(...new Uint8Array(buffer)),
        );
        sessionStorage.setItem(
          "pending_pdf",
          JSON.stringify({
            name: file.name,
            hash: pdfHash,
            base64,
          }),
        );
        router.push("/extract");
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e));
        setUploading(false);
      }
    },
    [router],
  );

  return (
    <BlueprintChrome title="01" rev="A" sheet="1·1">
      <div className="min-h-[calc(100vh-4rem)] flex flex-col items-center justify-center px-6 py-16">
        <h1 className="font-serif text-4xl md:text-6xl text-center mb-16 tracking-tight">
          Hardware Sets, <em className="text-cyan">located.</em>
        </h1>

        <DropZone onFile={handleFile} disabled={uploading} />

        {error && (
          <p className="mt-6 text-sm text-red-300 font-mono">{error}</p>
        )}

        {/* v2 samples chip row placeholder — layout slot only */}
        <div className="samples-row mt-12 h-8 opacity-30 text-[10px] tracking-[0.3em] uppercase text-ink-dim">
          {/* intentional blank: sample PDFs land in v2 */}
        </div>

        <p className="mt-16 text-[10px] tracking-[0.3em] uppercase text-ink-dim">
          API · <span className="text-cyan">{API_URL.replace(/^https?:\/\//, "")}</span>
        </p>
      </div>
    </BlueprintChrome>
  );
}
