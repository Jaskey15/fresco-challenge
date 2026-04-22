import type { SseEvent } from "./types";

export type SseHandler = (ev: SseEvent) => void;

/** POST `file` to `${apiUrl}/extract` and parse SSE events until the stream closes. */
export async function streamExtract(
  apiUrl: string,
  file: File,
  onEvent: SseHandler,
  signal?: AbortSignal,
): Promise<void> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${apiUrl}/extract`, {
    method: "POST",
    body: form,
    signal,
    headers: { Accept: "text/event-stream" },
  });

  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    throw new Error(`extract failed: ${res.status} ${text}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const parsed = parseBlock(block);
      if (parsed) onEvent(parsed);
    }
  }
}

function parseBlock(block: string): SseEvent | null {
  if (!block || block.startsWith(":")) return null; // heartbeat
  let event = "message";
  let dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  try {
    const data = JSON.parse(dataLines.join("\n"));
    return { event, data } as SseEvent;
  } catch {
    return null;
  }
}
