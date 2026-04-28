import { useCallback, useRef, useState } from "react";
import type { ExtractionResult, ProgressEvent } from "../types";

interface UseExtractionReturn {
  startUpload: (file: File) => void;
  startSample: (sampleId: string) => void;
  progress: ProgressEvent[];
  result: ExtractionResult | null;
  error: string | null;
  isLoading: boolean;
  reset: () => void;
}

function parseSSE(text: string): Array<{ event: string; data: string }> {
  const events: Array<{ event: string; data: string }> = [];
  let currentEvent = "";
  let currentData = "";

  for (const line of text.split("\n")) {
    if (line.startsWith("event: ")) {
      currentEvent = line.slice(7);
    } else if (line.startsWith("data: ")) {
      currentData = line.slice(6);
    } else if (line === "" && currentEvent) {
      events.push({ event: currentEvent, data: currentData });
      currentEvent = "";
      currentData = "";
    }
  }
  return events;
}

async function streamSSE(
  url: string,
  init: RequestInit,
  onProgress: (event: ProgressEvent) => void,
  onResult: (result: ExtractionResult) => void,
  onError: (message: string) => void,
) {
  const resp = await fetch(url, init);
  if (!resp.ok) {
    const body = await resp.text();
    onError(`Server error: ${resp.status} — ${body}`);
    return;
  }

  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    const events = parseSSE(buffer);
    if (events.length > 0) {
      // Keep only the unparsed tail
      const lastEventEnd = buffer.lastIndexOf("\n\n");
      buffer = lastEventEnd >= 0 ? buffer.slice(lastEventEnd + 2) : "";
    }

    for (const ev of events) {
      try {
        if (ev.event === "progress") {
          onProgress(JSON.parse(ev.data));
        } else if (ev.event === "result") {
          onResult(JSON.parse(ev.data));
        } else if (ev.event === "error") {
          onError(JSON.parse(ev.data).message);
        }
      } catch {
        onError("Received malformed response from server");
        return;
      }
    }
  }
}

export function useExtraction(): UseExtractionReturn {
  const [progress, setProgress] = useState<ProgressEvent[]>([]);
  const [result, setResult] = useState<ExtractionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const run = useCallback((url: string, init: RequestInit) => {
    setProgress([]);
    setResult(null);
    setError(null);
    setIsLoading(true);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    streamSSE(
      url,
      { ...init, signal: controller.signal },
      (event) => setProgress((prev) => [...prev, event]),
      (res) => {
        setResult(res);
        setIsLoading(false);
      },
      (msg) => {
        setError(msg);
        setIsLoading(false);
      },
    ).catch((err) => {
      if (err.name !== "AbortError") {
        setError(err.message);
        setIsLoading(false);
      }
    });
  }, []);

  const startUpload = useCallback(
    (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      run("/api/extract", { method: "POST", body: formData });
    },
    [run],
  );

  const startSample = useCallback(
    (sampleId: string) => {
      run(`/api/extract/sample/${sampleId}`, { method: "POST" });
    },
    [run],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setProgress([]);
    setResult(null);
    setError(null);
    setIsLoading(false);
  }, []);

  return { startUpload, startSample, progress, result, error, isLoading, reset };
}
