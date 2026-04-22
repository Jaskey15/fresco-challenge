"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { BlueprintChrome } from "../components/BlueprintChrome";
import { StreamLog, type StreamLine } from "../components/StreamLog";
import { streamExtract } from "@/lib/sse";
import type { HardwareSet, SseEvent } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type PendingPdf = { name: string; hash: string; base64: string };

function base64ToFile(b64: string, name: string): File {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return new File([arr], name, { type: "application/pdf" });
}

export default function ExtractPage() {
  const router = useRouter();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [filename, setFilename] = useState<string>("");
  const [sets, setSets] = useState<HardwareSet[]>([]);
  const [selected, setSelected] = useState<number>(0);
  const [log, setLog] = useState<StreamLine[]>([]);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const startedRef = useRef(false);

  const appendLog = useCallback((text: string, kind: StreamLine["kind"] = "info") => {
    setLog((l) => [...l, { t: Date.now(), text, kind }]);
  }, []);

  const handleEvent = useCallback(
    (ev: SseEvent) => {
      switch (ev.event) {
        case "session_started":
          setSessionId(ev.data.session_id);
          setFilename(ev.data.filename);
          appendLog(`session · ${ev.data.session_id.slice(0, 8)} · ${ev.data.filename}`);
          break;
        case "region_found":
          appendLog(`region · pages ${ev.data.page_start}-${ev.data.page_end} · ${ev.data.marker}`);
          break;
        case "extracting":
          appendLog(`extracting · ${ev.data.region_index + 1}/${ev.data.total_regions}`);
          break;
        case "set_extracted":
          setSets((s) => [...s, ev.data]);
          appendLog(`set · ${ev.data.set_number} · ${ev.data.components.length} components`);
          break;
        case "scored":
          setSets((s) =>
            s.map((hw, i) => (i === ev.data.set_index ? { ...hw, confidence: ev.data.confidence } : hw)),
          );
          break;
        case "warning":
          appendLog(ev.data.message, "warn");
          break;
        case "error":
          setErrorCode(ev.data.code);
          setErrorMessage(ev.data.message);
          appendLog(`error · ${ev.data.code} · ${ev.data.message}`, "error");
          break;
        case "done":
          setDone(true);
          appendLog(`done · ${ev.data.total_sets} sets · ${ev.data.llm_calls} llm calls`, "done");
          break;
      }
    },
    [appendLog],
  );

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    const raw = sessionStorage.getItem("pending_pdf");
    if (!raw) {
      router.replace("/");
      return;
    }
    const pending = JSON.parse(raw) as PendingPdf;
    sessionStorage.removeItem("pending_pdf");
    const file = base64ToFile(pending.base64, pending.name);

    streamExtract(API_URL, file, handleEvent).catch((e) => {
      appendLog(String(e), "error");
      setErrorCode("api_error");
      setErrorMessage(String(e));
    });
  }, [handleEvent, router, appendLog]);

  return (
    <BlueprintChrome title="02" rev="A" sheet="1·1">
      <div className="min-h-[calc(100vh-4rem)] grid grid-cols-1 md:grid-cols-[60%_40%] gap-4 px-6 py-10">
        {/* left: sets + log */}
        <div className="flex flex-col gap-4 min-h-0">
          <StreamLog lines={log} />

          <div className="flex-1 grid grid-cols-[240px_1fr] gap-4 min-h-0">
            <aside className="overflow-y-auto border border-cyan-dim rounded-sm bg-paper2/40">
              {sets.map((s, i) => (
                <button
                  key={`${s.set_number}-${s.location.page}`}
                  onClick={() => setSelected(i)}
                  className={`block w-full text-left px-3 py-2 border-b border-cyan-dim/40 font-mono text-xs
                    ${i === selected ? "bg-paper text-cyan" : "text-ink-dim hover:text-ink"}`}
                >
                  <div className="flex items-center justify-between">
                    <span>{s.set_number}</span>
                    <span className="text-[10px]">p.{s.location.page}</span>
                  </div>
                  <div className="text-[10px] truncate opacity-70">{s.description ?? "—"}</div>
                </button>
              ))}
              {!sets.length && !errorCode && (
                <div className="p-3 text-[11px] text-ink-dim font-mono">waiting for sets…</div>
              )}
            </aside>

            <section className="overflow-y-auto border border-cyan-dim rounded-sm bg-paper2/40 p-4">
              {/* SetCard lands in Task 17 */}
              {sets[selected] ? (
                <pre className="font-mono text-[11px] whitespace-pre-wrap">
                  {JSON.stringify(sets[selected], null, 2)}
                </pre>
              ) : (
                <div className="text-[11px] text-ink-dim font-mono">select a set</div>
              )}
            </section>
          </div>
        </div>

        {/* right: evidence pane lands in Task 18 */}
        <aside className="border border-cyan-dim rounded-sm bg-paper2/40 p-4 min-h-[500px]">
          <div className="text-[10px] tracking-[0.3em] uppercase text-ink-dim mb-3">
            Evidence · {sessionId ? sessionId.slice(0, 8) : "…"} · {filename}
          </div>
          <div className="text-xs text-ink-dim font-mono">
            PDF pane lands next.
          </div>
        </aside>

        {done && <div className="hidden" aria-hidden>{/* reserved */}</div>}
        {errorCode && <div className="hidden" aria-hidden>{errorMessage}</div>}
      </div>
    </BlueprintChrome>
  );
}
