# Frontend UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI + Vite/React frontend that uploads specbook PDFs, streams extraction progress, and displays results in a three-panel review interface with inline editing.

**Architecture:** FastAPI wraps the existing Python pipeline (filter → layout → extract) and exposes it via SSE-streamed endpoints. A Vite/React SPA consumes the API. In production, FastAPI serves the built React app as static files — single service, single deploy.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Vite, React 19, TypeScript, Tailwind CSS v4.

**Spec:** `docs/superpowers/specs/2026-04-22-frontend-ui-design.md`

---

## File Map

### Backend (new files in `src/hardware_sets_api/`)

| File | Responsibility |
|---|---|
| `__init__.py` | Package marker |
| `app.py` | FastAPI app, CORS, static mount, catch-all fallback |
| `pipeline.py` | Wraps existing pipeline modules; yields progress events via callback |
| `routes.py` | API endpoints: extract (upload + SSE), samples list, sample extract |
| `samples.py` | Demo sample registry: metadata + file paths |

### Frontend (new files in `frontend/`)

| File | Responsibility |
|---|---|
| `index.html` | Vite entry HTML |
| `vite.config.ts` | Vite config: React plugin, Tailwind plugin, dev proxy |
| `package.json` | Node deps |
| `tsconfig.json` | TypeScript config |
| `src/main.tsx` | React entry point |
| `src/index.css` | Tailwind import + custom properties |
| `src/App.tsx` | Top-level state machine: upload → processing → results |
| `src/types.ts` | TypeScript types mirroring Python dataclasses |
| `src/hooks/useExtraction.ts` | SSE connection, progress tracking, result state |
| `src/components/UploadView.tsx` | Dropzone + sample cards |
| `src/components/ProcessingView.tsx` | Two-phase progress indicator |
| `src/components/ResultsView.tsx` | Three-panel layout shell |
| `src/components/SetSidebar.tsx` | Scrollable set list with search |
| `src/components/SourcePanel.tsx` | PDF text lines with green highlight |
| `src/components/DetailTable.tsx` | Editable component table |
| `src/components/JsonViewer.tsx` | Inline JSON viewer toggle |

### Config / Deploy

| File | Responsibility |
|---|---|
| `pyproject.toml` | Add FastAPI + uvicorn deps |
| `demo_samples/` | 2–3 committed sample PDFs for the demo |
| `Dockerfile` | Single-service build: install Python + build frontend + serve |

### Tests

| File | Responsibility |
|---|---|
| `tests/test_pipeline_runner.py` | Pipeline runner with mocked filter/extract |
| `tests/test_api.py` | FastAPI route tests with TestClient |

---

## Task 1: Pipeline Runner Module

Extract the orchestration logic from `cli.py` into a reusable function that the API can call with a progress callback.

**Files:**
- Create: `src/hardware_sets_api/__init__.py`
- Create: `src/hardware_sets_api/pipeline.py`
- Create: `tests/test_pipeline_runner.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_pipeline_runner.py
"""Tests for the API pipeline runner."""
from pathlib import Path
from unittest.mock import MagicMock, patch

from hardware_sets.types import (
    HardwareSet, SetLocation, Component, ScheduleRegion, PageLayout, NumberedLine,
)
from hardware_sets_api.pipeline import run_pipeline


def _fake_region():
    return ScheduleRegion(start_page=3, end_page=4, start_marker="group_or_set", end_marker="eof")


def _fake_layout(page: int):
    return PageLayout(page_number=page, lines=[
        NumberedLine(number=1, text="HARDWARE GROUP NO. 1"),
        NumberedLine(number=2, text="3 EA  HINGE  626  IVE"),
    ])


def _fake_set():
    return HardwareSet(
        set_number="1",
        description="ENTRANCE DOORS",
        location=SetLocation(page=3, line_range=(1, 2)),
        components=[Component(qty=3, description="Hinge", catalog_number=None, mfr="IVE", finish="626", notes=None)],
    )


@patch("hardware_sets_api.pipeline.extract_mod")
@patch("hardware_sets_api.pipeline.layout_mod")
@patch("hardware_sets_api.pipeline.filter_mod")
@patch("hardware_sets_api.pipeline.PdfReader")
def test_run_pipeline_emits_progress_and_result(mock_reader, mock_filter, mock_layout, mock_extract):
    mock_reader.return_value.pages = [None] * 5  # 5 pages
    mock_filter.find_schedule_regions.return_value = [_fake_region()]
    mock_layout.extract_layout.side_effect = lambda path, p: _fake_layout(p)
    mock_extract.extract_sets.return_value = [_fake_set()]

    progress_events = []
    result = run_pipeline(Path("test.pdf"), on_progress=progress_events.append)

    assert any(e["phase"] == "filter" for e in progress_events)
    assert any(e["phase"] == "extract" for e in progress_events)
    assert result["source_pdf"] == "test.pdf"
    assert len(result["hardware_sets"]) == 1
    assert "3" in result["page_layouts"]
    assert "4" in result["page_layouts"]
    assert result["page_layouts"]["3"][0]["text"] == "HARDWARE GROUP NO. 1"


@patch("hardware_sets_api.pipeline.filter_mod")
@patch("hardware_sets_api.pipeline.PdfReader")
def test_run_pipeline_no_regions(mock_reader, mock_filter):
    mock_reader.return_value.pages = [None] * 3
    mock_filter.find_schedule_regions.return_value = []

    result = run_pipeline(Path("empty.pdf"), on_progress=lambda e: None)

    assert result["hardware_sets"] == []
    assert result["diagnostics"]["regions_found"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pipeline_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hardware_sets_api'`

- [ ] **Step 3: Create the package and pipeline module**

```python
# src/hardware_sets_api/__init__.py
```

```python
# src/hardware_sets_api/pipeline.py
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Callable

from pypdf import PdfReader

from hardware_sets import filter as filter_mod
from hardware_sets import layout as layout_mod
from hardware_sets import extract as extract_mod
from hardware_sets.types import HardwareSet


def run_pipeline(
    pdf_path: Path,
    on_progress: Callable[[dict], None],
) -> dict:
    total_pages = len(PdfReader(str(pdf_path)).pages)
    on_progress({"phase": "filter", "message": f"Scanning {total_pages} pages..."})

    regions = filter_mod.find_schedule_regions(pdf_path)
    if not regions:
        on_progress({"phase": "filter", "message": "No schedule regions found"})
        return {
            "source_pdf": pdf_path.name,
            "hardware_sets": [],
            "page_layouts": {},
            "diagnostics": {
                "pages_scanned": total_pages,
                "regions_found": 0,
                "pages_with_sets": 0,
                "llm_calls": 0,
                "warnings": ["no_schedule_found"],
            },
        }

    on_progress({
        "phase": "filter",
        "message": f"Found {len(regions)} region(s)",
    })

    all_sets: list[HardwareSet] = []
    all_layouts: dict[str, list[dict]] = {}
    warnings: list[str] = []
    llm_calls = 0

    for i, region in enumerate(regions, start=1):
        on_progress({
            "phase": "extract",
            "message": f"Extracting sets from region {i}/{len(regions)}...",
        })

        layouts = [
            layout_mod.extract_layout(pdf_path, p)
            for p in range(region.start_page, region.end_page + 1)
        ]

        for lay in layouts:
            all_layouts[str(lay.page_number)] = [
                {"number": line.number, "text": line.text}
                for line in lay.lines
            ]

        try:
            sets = extract_mod.extract_sets(region, layouts)
            llm_calls += 1
            all_sets.extend(sets)
        except extract_mod.ExtractionError as e:
            warnings.append(f"region {region.start_page}-{region.end_page}: {e}")

    return {
        "source_pdf": pdf_path.name,
        "hardware_sets": [asdict(s) for s in all_sets],
        "page_layouts": all_layouts,
        "diagnostics": {
            "pages_scanned": total_pages,
            "regions_found": len(regions),
            "pages_with_sets": sum(r.end_page - r.start_page + 1 for r in regions),
            "llm_calls": llm_calls,
            "warnings": warnings,
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pipeline_runner.py -v`
Expected: PASS — both tests green

- [ ] **Step 5: Commit**

```bash
git add src/hardware_sets_api/__init__.py src/hardware_sets_api/pipeline.py tests/test_pipeline_runner.py
git commit -m "feat(api): add pipeline runner module"
```

---

## Task 2: FastAPI App + Samples Registry + Dependencies

Scaffold the FastAPI app, add deps to pyproject.toml, create the demo samples registry.

**Files:**
- Modify: `pyproject.toml`
- Create: `src/hardware_sets_api/app.py`
- Create: `src/hardware_sets_api/samples.py`
- Create: `demo_samples/` (copy 2–3 PDFs from `samples/`)

- [ ] **Step 1: Update pyproject.toml with API dependencies**

Add `fastapi`, `uvicorn`, and `python-multipart` to the main dependencies:

```toml
dependencies = [
    "anthropic>=0.40.0",
    "pdfplumber>=0.11",
    "pypdf>=5.0",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "python-multipart>=0.0.12",
]
```

Run: `pip install -e ".[dev]"` to install the new deps.

- [ ] **Step 2: Copy 2–3 sample PDFs into `demo_samples/`**

Pick representative samples that cover different formats and are reasonable in file size:

```bash
mkdir -p demo_samples
cp samples/81-85_bridgeport.pdf demo_samples/bridgeport.pdf
cp samples/morris_bank_08.pdf demo_samples/morris_bank.pdf
cp samples/roselle_public_library_08.pdf demo_samples/roselle_library.pdf
```

These choices cover list format (Bridgeport), tabular schedule (Morris Bank), and a mid-size doc (Roselle). Verify the pipeline runs on each:

```bash
python -m hardware_sets demo_samples/bridgeport.pdf --quiet -o /dev/null && echo "bridgeport OK"
python -m hardware_sets demo_samples/morris_bank.pdf --quiet -o /dev/null && echo "morris_bank OK"
python -m hardware_sets demo_samples/roselle_library.pdf --quiet -o /dev/null && echo "roselle OK"
```

If any sample is too large (>5 MB) or fails, substitute another from `samples/`.

- [ ] **Step 3: Create samples registry**

```python
# src/hardware_sets_api/samples.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent.parent.parent / "demo_samples"


@dataclass
class SampleSpec:
    id: str
    name: str
    label: str
    filename: str

    @property
    def path(self) -> Path:
        return DEMO_DIR / self.filename


SAMPLES: list[SampleSpec] = [
    SampleSpec(id="bridgeport", name="Bridgeport Specs", label="List format", filename="bridgeport.pdf"),
    SampleSpec(id="morris-bank", name="Morris Bank", label="Tabular schedule", filename="morris_bank.pdf"),
    SampleSpec(id="roselle-library", name="Roselle Public Library", label="Mixed format", filename="roselle_library.pdf"),
]

SAMPLE_BY_ID: dict[str, SampleSpec] = {s.id: s for s in SAMPLES}
```

- [ ] **Step 4: Create FastAPI app scaffold**

```python
# src/hardware_sets_api/app.py
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from hardware_sets_api.routes import router

app = FastAPI(title="Hardware Sets Extractor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Static file serving for production (frontend/dist/).
# Mount AFTER API routes so /api/* takes priority.
_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="static")
```

Note: `routes.py` doesn't exist yet — create a stub so the import doesn't fail:

```python
# src/hardware_sets_api/routes.py (stub — full implementation in Task 3)
from fastapi import APIRouter

router = APIRouter()
```

- [ ] **Step 5: Verify the app starts**

```bash
uvicorn hardware_sets_api.app:app --port 8000 &
curl -s http://localhost:8000/docs | head -5
# Should return the FastAPI Swagger HTML
kill %1
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/hardware_sets_api/app.py src/hardware_sets_api/samples.py src/hardware_sets_api/routes.py demo_samples/
git commit -m "feat(api): scaffold FastAPI app with samples registry"
```

---

## Task 3: API Routes with SSE Streaming

Implement the extraction endpoints: file upload with SSE progress, samples list, sample extraction.

**Files:**
- Modify: `src/hardware_sets_api/routes.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write API route tests**

```python
# tests/test_api.py
"""Tests for the API endpoints."""
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from hardware_sets_api.app import app

client = TestClient(app)


def test_get_samples():
    resp = client.get("/api/samples")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2
    assert all("id" in s and "name" in s and "label" in s for s in data)


@patch("hardware_sets_api.routes.run_pipeline")
def test_extract_sample_streams_sse(mock_pipeline):
    mock_pipeline.side_effect = lambda path, on_progress: (
        on_progress({"phase": "filter", "message": "Scanning 5 pages..."}),
        {
            "source_pdf": "test.pdf",
            "hardware_sets": [],
            "page_layouts": {},
            "diagnostics": {"pages_scanned": 5, "regions_found": 0, "pages_with_sets": 0, "llm_calls": 0, "warnings": []},
        },
    )[-1]

    resp = client.post("/api/extract/sample/bridgeport")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    body = resp.text
    assert "event: progress" in body
    assert "event: result" in body


def test_extract_sample_not_found():
    resp = client.post("/api/extract/sample/nonexistent")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api.py -v`
Expected: FAIL — routes not implemented

- [ ] **Step 3: Implement routes**

```python
# src/hardware_sets_api/routes.py
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from queue import Queue
from threading import Thread

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from hardware_sets_api.pipeline import run_pipeline
from hardware_sets_api.samples import SAMPLE_BY_ID, SAMPLES

router = APIRouter(prefix="/api")


@router.get("/samples")
def list_samples():
    return [{"id": s.id, "name": s.name, "label": s.label} for s in SAMPLES]


def _stream_extraction(pdf_path: Path, cleanup: bool = False):
    queue: Queue = Queue()

    def on_progress(event: dict):
        queue.put(("progress", event))

    def run():
        try:
            result = run_pipeline(pdf_path, on_progress)
            queue.put(("result", result))
        except Exception as e:
            queue.put(("error", {"message": str(e)}))
        finally:
            if cleanup:
                pdf_path.unlink(missing_ok=True)

    thread = Thread(target=run, daemon=True)
    thread.start()

    async def generate():
        while True:
            event_type, data = await asyncio.to_thread(queue.get)
            yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
            if event_type in ("result", "error"):
                break

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/extract")
async def extract_upload(file: UploadFile):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    content = await file.read()
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(content)
    tmp.close()

    return _stream_extraction(Path(tmp.name), cleanup=True)


@router.post("/extract/sample/{sample_id}")
def extract_sample(sample_id: str):
    sample = SAMPLE_BY_ID.get(sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail=f"Sample '{sample_id}' not found")
    if not sample.path.is_file():
        raise HTTPException(status_code=500, detail=f"Sample file missing: {sample.filename}")

    return _stream_extraction(sample.path, cleanup=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api.py -v`
Expected: PASS — all three tests green

- [ ] **Step 5: Manual smoke test with a real PDF**

```bash
uvicorn hardware_sets_api.app:app --port 8000 &
curl -N -X POST http://localhost:8000/api/extract/sample/bridgeport
# Should see SSE events streaming: event: progress, then event: result
kill %1
```

- [ ] **Step 6: Commit**

```bash
git add src/hardware_sets_api/routes.py tests/test_api.py
git commit -m "feat(api): add extraction routes with SSE streaming"
```

---

## Task 4: Frontend Scaffold

Set up Vite + React + TypeScript + Tailwind CSS v4 with a dev proxy to the FastAPI backend.

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/index.css`
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: Initialize the frontend project**

```bash
cd frontend
npm init -y
npm install react react-dom
npm install -D typescript @types/react @types/react-dom vite @vitejs/plugin-react tailwindcss @tailwindcss/vite
```

- [ ] **Step 2: Create `package.json` scripts** (edit the generated one)

Add to `frontend/package.json`:
```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  }
}
```

- [ ] **Step 3: Create config files**

```typescript
// frontend/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
```

```json
// frontend/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "outDir": "dist",
    "rootDir": "src",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Create entry files**

```html
<!-- frontend/index.html -->
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Hardware Sets Extractor</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

```css
/* frontend/src/index.css */
@import "tailwindcss";
```

```tsx
// frontend/src/main.tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

```tsx
// frontend/src/App.tsx
export default function App() {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <h1 className="text-2xl font-bold text-gray-800">Hardware Sets Extractor</h1>
    </div>
  );
}
```

- [ ] **Step 5: Verify the dev server starts**

```bash
cd frontend && npm run dev
# Open http://localhost:5173 — should show "Hardware Sets Extractor" with Tailwind styling
```

- [ ] **Step 6: Verify the build works**

```bash
cd frontend && npm run build
ls dist/  # Should contain index.html and assets/
```

- [ ] **Step 7: Clean up old frontend artifacts**

Remove the stale `.next` directory and `tsconfig.tsbuildinfo` from a previous Next.js experiment:

```bash
rm -rf frontend/.next frontend/tsconfig.tsbuildinfo frontend/node_modules
```

Then reinstall: `cd frontend && npm install`

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/index.html frontend/vite.config.ts frontend/tsconfig.json frontend/src/
git commit -m "feat(frontend): scaffold Vite + React + TypeScript + Tailwind"
```

---

## Task 5: TypeScript Types + useExtraction Hook

Define the shared types and the SSE hook that drives the upload → processing → results flow.

**Files:**
- Create: `frontend/src/types.ts`
- Create: `frontend/src/hooks/useExtraction.ts`

- [ ] **Step 1: Create TypeScript types**

```typescript
// frontend/src/types.ts
export interface NumberedLine {
  number: number;
  text: string;
}

export interface SetLocation {
  page: number;
  line_range: [number, number];
}

export interface Component {
  qty: number | null;
  description: string | null;
  catalog_number: string | null;
  mfr: string | null;
  finish: string | null;
  notes: string | null;
  confidence?: Record<string, number>;
}

export interface HardwareSet {
  set_number: string;
  description: string | null;
  location: SetLocation;
  components: Component[];
  continued_on: SetLocation[];
  is_not_used: boolean;
  confidence: number;
  notes: string | null;
}

export interface ExtractionResult {
  source_pdf: string;
  hardware_sets: HardwareSet[];
  page_layouts: Record<string, NumberedLine[]>;
  diagnostics: {
    pages_scanned: number;
    regions_found: number;
    pages_with_sets: number;
    llm_calls: number;
    warnings: string[];
  };
}

export interface ProgressEvent {
  phase: "filter" | "extract";
  message: string;
}

export interface Sample {
  id: string;
  name: string;
  label: string;
}
```

- [ ] **Step 2: Create the useExtraction hook**

This hook handles SSE streaming from both the file upload and sample extraction endpoints. It parses the `fetch` response body as a stream of SSE events.

```typescript
// frontend/src/hooks/useExtraction.ts
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
      if (ev.event === "progress") {
        onProgress(JSON.parse(ev.data));
      } else if (ev.event === "result") {
        onResult(JSON.parse(ev.data));
      } else if (ev.event === "error") {
        onError(JSON.parse(ev.data).message);
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
```

- [ ] **Step 3: Verify types compile**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types.ts frontend/src/hooks/useExtraction.ts
git commit -m "feat(frontend): add TypeScript types and useExtraction SSE hook"
```

---

## Task 6: UploadView + ProcessingView

The landing page with dropzone + sample cards, and the loading indicator that shows pipeline progress.

**Files:**
- Create: `frontend/src/components/UploadView.tsx`
- Create: `frontend/src/components/ProcessingView.tsx`

- [ ] **Step 1: Create UploadView**

```tsx
// frontend/src/components/UploadView.tsx
import { useCallback, useEffect, useRef, useState } from "react";
import type { Sample } from "../types";

interface Props {
  onFileSelect: (file: File) => void;
  onSampleSelect: (sampleId: string) => void;
}

export default function UploadView({ onFileSelect, onSampleSelect }: Props) {
  const [samples, setSamples] = useState<Sample[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch("/api/samples")
      .then((r) => r.json())
      .then(setSamples)
      .catch(() => {});
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file?.type === "application/pdf") onFileSelect(file);
    },
    [onFileSelect],
  );

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) onFileSelect(file);
    },
    [onFileSelect],
  );

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-8">
      <div className="max-w-2xl w-full">
        <h1 className="text-3xl font-bold text-gray-900 text-center mb-2">
          Hardware Sets Extractor
        </h1>
        <p className="text-gray-500 text-center mb-8">
          Upload a Division 08 specbook PDF to extract hardware sets
        </p>

        {/* Dropzone */}
        <div
          className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
            dragOver
              ? "border-green-500 bg-green-50"
              : "border-gray-300 hover:border-gray-400 bg-white"
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
        >
          <div className="text-4xl mb-3">📄</div>
          <p className="text-gray-700 font-medium">
            Drop a PDF here or click to browse
          </p>
          <p className="text-gray-400 text-sm mt-1">Division 08 specbook only</p>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={handleFileChange}
          />
        </div>

        {/* Sample cards */}
        {samples.length > 0 && (
          <div className="mt-8">
            <p className="text-sm text-gray-500 mb-3 text-center">
              Or try a sample specbook:
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {samples.map((s) => (
                <button
                  key={s.id}
                  onClick={() => onSampleSelect(s.id)}
                  className="bg-white border border-gray-200 rounded-lg p-4 text-left hover:border-green-400 hover:bg-green-50 transition-colors"
                >
                  <div className="font-medium text-gray-800 text-sm">
                    {s.name}
                  </div>
                  <div className="text-gray-400 text-xs mt-1">{s.label}</div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create ProcessingView**

```tsx
// frontend/src/components/ProcessingView.tsx
import type { ProgressEvent } from "../types";

interface Props {
  progress: ProgressEvent[];
  error: string | null;
  onReset: () => void;
}

export default function ProcessingView({ progress, error, onReset }: Props) {
  const latest = progress[progress.length - 1];

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-8">
        <div className="max-w-md text-center">
          <div className="text-4xl mb-4">⚠️</div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">
            Extraction Failed
          </h2>
          <p className="text-gray-500 text-sm mb-6">{error}</p>
          <button
            onClick={onReset}
            className="px-4 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-800"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-8">
      <div className="max-w-md text-center">
        {/* Spinner */}
        <div className="mb-6 flex justify-center">
          <div className="w-10 h-10 border-3 border-gray-200 border-t-green-500 rounded-full animate-spin" />
        </div>

        <h2 className="text-xl font-semibold text-gray-900 mb-2">
          {latest?.phase === "extract"
            ? "Extracting Hardware Sets"
            : "Scanning Document"}
        </h2>

        <p className="text-gray-500 text-sm">
          {latest?.message ?? "Starting..."}
        </p>

        {/* Progress log */}
        {progress.length > 1 && (
          <div className="mt-6 text-left bg-white rounded-lg border border-gray-200 p-3 max-h-40 overflow-y-auto">
            {progress.map((p, i) => (
              <div key={i} className="text-xs text-gray-400 py-0.5">
                <span className="text-gray-300 mr-2">
                  {p.phase === "filter" ? "🔍" : "⚙️"}
                </span>
                {p.message}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/UploadView.tsx frontend/src/components/ProcessingView.tsx
git commit -m "feat(frontend): add UploadView and ProcessingView components"
```

---

## Task 7: App State Machine

Wire App.tsx to manage the upload → processing → results flow using the useExtraction hook.

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Implement App with view state machine**

```tsx
// frontend/src/App.tsx
import { useExtraction } from "./hooks/useExtraction";
import UploadView from "./components/UploadView";
import ProcessingView from "./components/ProcessingView";
import ResultsView from "./components/ResultsView";

export default function App() {
  const { startUpload, startSample, progress, result, error, isLoading, reset } =
    useExtraction();

  // View state derived from hook state
  if (result) {
    return <ResultsView result={result} onReset={reset} />;
  }

  if (isLoading || error) {
    return <ProcessingView progress={progress} error={error} onReset={reset} />;
  }

  return <UploadView onFileSelect={startUpload} onSampleSelect={startSample} />;
}
```

Note: `ResultsView` doesn't exist yet. Create a stub:

```tsx
// frontend/src/components/ResultsView.tsx (stub — full implementation in Task 10)
import type { ExtractionResult } from "../types";

interface Props {
  result: ExtractionResult;
  onReset: () => void;
}

export default function ResultsView({ result, onReset }: Props) {
  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <button onClick={onReset} className="text-sm text-gray-500 hover:text-gray-700">
        ← Upload another
      </button>
      <pre className="mt-4 text-xs bg-white p-4 rounded-lg border overflow-auto max-h-[80vh]">
        {JSON.stringify(result, null, 2)}
      </pre>
    </div>
  );
}
```

- [ ] **Step 2: Verify in browser**

Start both servers:
```bash
# Terminal 1
uvicorn hardware_sets_api.app:app --port 8000

# Terminal 2
cd frontend && npm run dev
```

Open http://localhost:5173. Test:
1. Sample cards appear and clicking one starts extraction
2. Progress messages display during processing
3. Result JSON appears when extraction completes
4. "Upload another" button returns to upload view

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/ResultsView.tsx
git commit -m "feat(frontend): wire App state machine (upload → processing → results)"
```

---

## Task 8: SetSidebar

The collapsible sidebar with search, scrollable set list, and active set highlighting.

**Files:**
- Create: `frontend/src/components/SetSidebar.tsx`

- [ ] **Step 1: Create SetSidebar**

```tsx
// frontend/src/components/SetSidebar.tsx
import { useMemo, useState } from "react";
import type { HardwareSet } from "../types";

interface Props {
  sets: HardwareSet[];
  activeIndex: number;
  onSelect: (index: number) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export default function SetSidebar({
  sets,
  activeIndex,
  onSelect,
  collapsed,
  onToggleCollapse,
}: Props) {
  const [filter, setFilter] = useState("");

  const filtered = useMemo(() => {
    if (!filter) return sets.map((s, i) => ({ set: s, index: i }));
    const q = filter.toLowerCase();
    return sets
      .map((s, i) => ({ set: s, index: i }))
      .filter(
        ({ set }) =>
          set.set_number.toLowerCase().includes(q) ||
          (set.description?.toLowerCase().includes(q) ?? false),
      );
  }, [sets, filter]);

  if (collapsed) {
    return (
      <div className="w-10 bg-gray-50 border-r border-gray-200 flex flex-col items-center pt-3">
        <button
          onClick={onToggleCollapse}
          className="text-gray-400 hover:text-gray-600 text-xs"
          title="Expand sidebar"
        >
          ▶
        </button>
      </div>
    );
  }

  return (
    <div className="w-[160px] min-w-[160px] bg-gray-50 border-r border-gray-200 flex flex-col">
      {/* Header */}
      <div className="px-3 pt-3 pb-2 flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
          {sets.length} Sets
        </span>
        <button
          onClick={onToggleCollapse}
          className="text-gray-400 hover:text-gray-600 text-xs"
          title="Collapse sidebar"
        >
          ◀
        </button>
      </div>

      {/* Search */}
      <div className="px-3 pb-2">
        <input
          type="text"
          placeholder="Filter..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="w-full text-xs px-2 py-1.5 border border-gray-200 rounded bg-white placeholder:text-gray-300 focus:outline-none focus:border-green-400"
        />
      </div>

      {/* Set list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-1">
        {filtered.map(({ set, index }) => {
          const isActive = index === activeIndex;
          return (
            <button
              key={index}
              onClick={() => onSelect(index)}
              className={`w-full text-left px-2 py-2 rounded-md text-xs transition-colors ${
                isActive
                  ? "bg-green-500 text-white"
                  : set.is_not_used
                    ? "bg-white border border-gray-100 text-gray-400 hover:border-gray-300"
                    : "bg-white border border-gray-100 text-gray-700 hover:border-gray-300"
              }`}
            >
              <div className="font-semibold">
                {set.set_number}
                <span className={`font-normal ml-1 ${isActive ? "opacity-80" : "text-gray-400"}`}>
                  {set.description
                    ? set.description.length > 12
                      ? set.description.slice(0, 12) + "…"
                      : set.description
                    : set.is_not_used
                      ? "NOT USED"
                      : ""}
                </span>
              </div>
              <div className={`mt-0.5 ${isActive ? "opacity-70" : "text-gray-400"}`}>
                {set.components.length} comp · pg {set.location.page}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/SetSidebar.tsx
git commit -m "feat(frontend): add SetSidebar component"
```

---

## Task 9: SourcePanel

PDF text lines with line-number gutter and green highlight for the selected set's line range.

**Files:**
- Create: `frontend/src/components/SourcePanel.tsx`

- [ ] **Step 1: Create SourcePanel**

```tsx
// frontend/src/components/SourcePanel.tsx
import { useMemo } from "react";
import type { HardwareSet, NumberedLine } from "../types";

interface Props {
  set: HardwareSet;
  pageLayouts: Record<string, NumberedLine[]>;
}

export default function SourcePanel({ set, pageLayouts }: Props) {
  const pages = useMemo(() => {
    const result: Array<{
      pageNumber: number;
      lines: NumberedLine[];
      highlightRange: [number, number];
    }> = [];

    // Primary location
    const primaryLines = pageLayouts[String(set.location.page)];
    if (primaryLines) {
      result.push({
        pageNumber: set.location.page,
        lines: primaryLines,
        highlightRange: set.location.line_range,
      });
    }

    // Continued-on pages
    for (const cont of set.continued_on) {
      const contLines = pageLayouts[String(cont.page)];
      if (contLines) {
        result.push({
          pageNumber: cont.page,
          lines: contLines,
          highlightRange: cont.line_range,
        });
      }
    }

    return result;
  }, [set, pageLayouts]);

  if (pages.length === 0) {
    return (
      <div className="flex-1 bg-white border-r border-gray-200 flex items-center justify-center text-gray-400 text-sm">
        No source data available
      </div>
    );
  }

  return (
    <div className="flex-1 min-w-0 bg-white border-r border-gray-200 flex flex-col">
      {pages.map((page, pageIdx) => (
        <div key={pageIdx} className="flex flex-col flex-1 min-h-0">
          {/* Page header */}
          <div className="px-3 py-2 border-b border-gray-100 flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-500">
              📄 Page {page.pageNumber}
            </span>
            {pages.length > 1 && (
              <span className="text-[10px] text-gray-400">
                {pageIdx === 0 ? "primary" : "continued"}
              </span>
            )}
          </div>

          {/* Lines */}
          <div className="flex-1 overflow-y-auto p-2 font-mono text-[11px] leading-[1.8]">
            {page.lines.map((line) => {
              const inRange =
                line.number >= page.highlightRange[0] &&
                line.number <= page.highlightRange[1];
              return (
                <div
                  key={line.number}
                  className={`flex ${
                    inRange
                      ? "bg-green-50 border-l-2 border-green-500 -ml-[2px] pl-[2px] text-gray-900"
                      : "text-gray-400"
                  }`}
                >
                  <span
                    className={`w-7 text-right mr-2 select-none shrink-0 ${
                      inRange ? "text-green-600 font-semibold" : "text-gray-300"
                    }`}
                  >
                    {line.number}
                  </span>
                  <span className="whitespace-pre overflow-x-auto">{line.text}</span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/SourcePanel.tsx
git commit -m "feat(frontend): add SourcePanel with line highlighting"
```

---

## Task 10: DetailTable (Read-Only) + ResultsView Shell

The component table showing structured extraction results, and the three-panel layout that wires sidebar + source + table together.

**Files:**
- Create: `frontend/src/components/DetailTable.tsx`
- Modify: `frontend/src/components/ResultsView.tsx`

- [ ] **Step 1: Create DetailTable (read-only version)**

```tsx
// frontend/src/components/DetailTable.tsx
import type { Component, HardwareSet } from "../types";

interface Props {
  set: HardwareSet;
}

const COLUMNS: Array<{ key: keyof Component; label: string }> = [
  { key: "qty", label: "QTY" },
  { key: "description", label: "DESCRIPTION" },
  { key: "catalog_number", label: "CATALOG #" },
  { key: "mfr", label: "MFR" },
  { key: "finish", label: "FINISH" },
  { key: "notes", label: "NOTES" },
];

function CellValue({ value }: { value: string | number | null }) {
  if (value === null || value === undefined) {
    return <span className="text-gray-300">—</span>;
  }
  return <>{String(value)}</>;
}

export default function DetailTable({ set }: Props) {
  return (
    <div className="flex-1 min-w-0 flex flex-col bg-white">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 flex items-start justify-between">
        <div>
          <h2 className="text-base font-bold text-gray-900">
            <span className="text-green-500 mr-1">●</span>
            Hardware Set {set.set_number}
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">
            {set.description && <span>{set.description} · </span>}
            {set.components.length} components · Page {set.location.page}, Lines{" "}
            {set.location.line_range[0]}–{set.location.line_range[1]}
          </p>
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto px-4 py-2">
        {set.is_not_used ? (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            This set is marked as NOT USED
          </div>
        ) : (
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b-2 border-gray-200">
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    className="text-left px-3 py-2 text-[10px] font-semibold text-gray-400 uppercase tracking-wider"
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {set.components.map((comp, i) => (
                <tr key={i} className="border-b border-gray-100">
                  {COLUMNS.map((col) => (
                    <td key={col.key} className="px-3 py-2 text-gray-700">
                      <CellValue value={comp[col.key] ?? null} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Bottom bar */}
      <div className="px-4 py-2 border-t border-gray-100 flex items-center justify-between bg-gray-50">
        <span className="text-[10px] text-gray-400">
          Click any cell to edit · Tab to advance · Esc to cancel
        </span>
        <span className="text-[10px] text-gray-300">
          📍 Page {set.location.page}, Lines {set.location.line_range[0]}–
          {set.location.line_range[1]}
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Implement the full ResultsView three-panel layout**

Replace the stub with the real implementation:

```tsx
// frontend/src/components/ResultsView.tsx
import { useState } from "react";
import type { ExtractionResult } from "../types";
import SetSidebar from "./SetSidebar";
import SourcePanel from "./SourcePanel";
import DetailTable from "./DetailTable";

interface Props {
  result: ExtractionResult;
  onReset: () => void;
}

export default function ResultsView({ result, onReset }: Props) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const sets = result.hardware_sets;
  const activeSet = sets[activeIndex];

  if (sets.length === 0) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-8">
        <div className="text-center">
          <div className="text-4xl mb-4">🔍</div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">
            No Hardware Sets Found
          </h2>
          <p className="text-gray-500 text-sm mb-6">
            The document was scanned but no hardware sets were detected.
          </p>
          <button
            onClick={onReset}
            className="px-4 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-800"
          >
            Try Another Document
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Top bar */}
      <div className="h-12 px-4 border-b border-gray-200 bg-white flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={onReset}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            ← Back
          </button>
          <span className="text-sm font-semibold text-gray-800">
            {result.source_pdf}
          </span>
          <span className="text-xs text-green-600 font-medium">
            ✓ {sets.length} sets extracted
          </span>
        </div>
        <div className="text-xs text-gray-400">
          {result.diagnostics.pages_with_sets} pages ·{" "}
          {result.diagnostics.llm_calls} LLM call
          {result.diagnostics.llm_calls !== 1 ? "s" : ""}
        </div>
      </div>

      {/* Three-panel layout */}
      <div className="flex-1 flex min-h-0">
        <SetSidebar
          sets={sets}
          activeIndex={activeIndex}
          onSelect={setActiveIndex}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
        />
        <SourcePanel set={activeSet} pageLayouts={result.page_layouts} />
        <DetailTable set={activeSet} />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify in browser**

Start both servers and run a sample extraction end-to-end:
1. Click a sample card
2. Watch the processing progress
3. Results should show the three-panel layout
4. Click sets in the sidebar — source highlight and table should update
5. NOT USED sets should show the placeholder message
6. Test the sidebar filter
7. Test sidebar collapse/expand

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/DetailTable.tsx frontend/src/components/ResultsView.tsx
git commit -m "feat(frontend): add DetailTable and three-panel ResultsView"
```

---

## Task 11: Inline Editing + Edit Tracking

Add click-to-edit functionality to table cells, with yellow highlights for edited cells and a reset button.

**Files:**
- Modify: `frontend/src/components/DetailTable.tsx`
- Modify: `frontend/src/components/ResultsView.tsx`

- [ ] **Step 1: Add edit state to ResultsView**

The edit state is a nested record: `{ [setIndex]: { [componentIndex]: { [field]: value } } }`. ResultsView owns this state and passes it down.

Update `ResultsView.tsx` to manage edits:

```tsx
// Add to ResultsView's state:
const [edits, setEdits] = useState<Record<number, Record<number, Record<string, string>>>>({});

const editCount = Object.values(edits[activeIndex] ?? {}).reduce(
  (sum, fields) => sum + Object.keys(fields).length,
  0,
);

const handleCellEdit = (compIndex: number, field: string, value: string) => {
  setEdits((prev) => ({
    ...prev,
    [activeIndex]: {
      ...prev[activeIndex],
      [compIndex]: {
        ...(prev[activeIndex]?.[compIndex] ?? {}),
        [field]: value,
      },
    },
  }));
};

const handleReset = () => {
  setEdits((prev) => {
    const next = { ...prev };
    delete next[activeIndex];
    return next;
  });
};
```

Pass to DetailTable:
```tsx
<DetailTable
  set={activeSet}
  edits={edits[activeIndex] ?? {}}
  editCount={editCount}
  onCellEdit={handleCellEdit}
  onReset={handleReset}
/>
```

- [ ] **Step 2: Update DetailTable props and add inline editing**

The full updated `DetailTable.tsx`:

```tsx
// frontend/src/components/DetailTable.tsx
import { useCallback, useEffect, useRef, useState } from "react";
import type { Component, HardwareSet } from "../types";

interface Props {
  set: HardwareSet;
  edits: Record<number, Record<string, string>>;
  editCount: number;
  onCellEdit: (compIndex: number, field: string, value: string) => void;
  onReset: () => void;
}

const COLUMNS: Array<{ key: keyof Component; label: string }> = [
  { key: "qty", label: "QTY" },
  { key: "description", label: "DESCRIPTION" },
  { key: "catalog_number", label: "CATALOG #" },
  { key: "mfr", label: "MFR" },
  { key: "finish", label: "FINISH" },
  { key: "notes", label: "NOTES" },
];

interface EditableCellProps {
  value: string | number | null;
  isEdited: boolean;
  onCommit: (value: string) => void;
}

function EditableCell({ value, isEdited, onCommit }: EditableCellProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const displayValue = value === null || value === undefined ? "" : String(value);

  const startEdit = useCallback(() => {
    setDraft(displayValue);
    setEditing(true);
  }, [displayValue]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const commit = useCallback(() => {
    setEditing(false);
    if (draft !== displayValue) {
      onCommit(draft);
    }
  }, [draft, displayValue, onCommit]);

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === "Tab") {
            e.preventDefault();
            commit();
          } else if (e.key === "Escape") {
            setEditing(false);
          }
        }}
        className="w-full px-1.5 py-0.5 text-sm border-2 border-blue-500 rounded outline-none bg-white shadow-[0_0_0_3px_rgba(59,130,246,0.1)]"
      />
    );
  }

  return (
    <div
      onClick={startEdit}
      className={`cursor-pointer px-1.5 py-0.5 rounded min-h-[24px] ${
        isEdited
          ? "bg-amber-50 border border-amber-300"
          : "hover:bg-gray-50"
      }`}
    >
      {displayValue || <span className="text-gray-300">—</span>}
    </div>
  );
}

export default function DetailTable({ set, edits, editCount, onCellEdit, onReset }: Props) {
  const getDisplayValue = (compIndex: number, field: string, original: string | number | null) => {
    const edited = edits[compIndex]?.[field];
    return edited !== undefined ? edited : original;
  };

  const isEdited = (compIndex: number, field: string) => {
    return edits[compIndex]?.[field] !== undefined;
  };

  return (
    <div className="flex-[1.6] min-w-0 flex flex-col bg-white">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 flex items-start justify-between">
        <div>
          <h2 className="text-base font-bold text-gray-900">
            <span className="text-green-500 mr-1">●</span>
            Hardware Set {set.set_number}
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">
            {set.description && <span>{set.description} · </span>}
            {set.components.length} components · Page {set.location.page}, Lines{" "}
            {set.location.line_range[0]}–{set.location.line_range[1]}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {editCount > 0 && (
            <span className="text-[10px] px-2 py-1 bg-amber-50 border border-amber-300 rounded text-amber-700">
              {editCount} edited
            </span>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto px-4 py-2">
        {set.is_not_used ? (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            This set is marked as NOT USED
          </div>
        ) : (
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b-2 border-gray-200">
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    className="text-left px-3 py-2 text-[10px] font-semibold text-gray-400 uppercase tracking-wider"
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {set.components.map((comp, compIdx) => (
                <tr key={compIdx} className="border-b border-gray-100">
                  {COLUMNS.map((col) => (
                    <td key={col.key} className="px-2 py-1.5">
                      <EditableCell
                        value={getDisplayValue(compIdx, col.key, comp[col.key] ?? null)}
                        isEdited={isEdited(compIdx, col.key)}
                        onCommit={(val) => onCellEdit(compIdx, col.key, val)}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Bottom bar */}
      <div className="px-4 py-2 border-t border-gray-100 flex items-center justify-between bg-gray-50">
        <span className="text-[10px] text-gray-400">
          Click any cell to edit · Tab to advance · Esc to cancel
        </span>
        <div className="flex items-center gap-2">
          {editCount > 0 && (
            <button
              onClick={onReset}
              className="text-[10px] px-3 py-1 border border-gray-300 rounded text-gray-500 hover:bg-gray-100"
            >
              Reset
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify in browser**

1. Click a cell — should show blue input border
2. Type a new value and press Enter or Tab — cell should commit and show yellow highlight
3. Press Esc — should cancel edit
4. "N edited" badge should appear in the header
5. Click Reset — all yellow highlights should clear

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/DetailTable.tsx frontend/src/components/ResultsView.tsx
git commit -m "feat(frontend): add inline editing with edit tracking"
```

---

## Task 12: JSON Viewer + JSON Download

Inline JSON viewer toggle and per-document JSON download that reflects edits.

**Files:**
- Create: `frontend/src/components/JsonViewer.tsx`
- Modify: `frontend/src/components/ResultsView.tsx`
- Modify: `frontend/src/components/DetailTable.tsx`

- [ ] **Step 1: Create JsonViewer**

```tsx
// frontend/src/components/JsonViewer.tsx
import type { HardwareSet } from "../types";

interface Props {
  set: HardwareSet;
  edits: Record<number, Record<string, string>>;
}

export default function JsonViewer({ set, edits }: Props) {
  const edited = {
    ...set,
    components: set.components.map((comp, i) => {
      const compEdits = edits[i];
      if (!compEdits) return comp;
      return { ...comp, ...compEdits };
    }),
  };

  return (
    <div className="border-t border-gray-200 bg-gray-50 max-h-64 overflow-auto">
      <pre className="p-3 text-[11px] text-gray-600 font-mono leading-relaxed">
        {JSON.stringify(edited, null, 2)}
      </pre>
    </div>
  );
}
```

- [ ] **Step 2: Add JSON download helper and viewer toggle to ResultsView**

Add to `ResultsView.tsx`:

```tsx
// New state
const [showJson, setShowJson] = useState(false);

// Download function — builds the full result with edits applied
const handleDownload = () => {
  const editedSets = result.hardware_sets.map((set, setIdx) => {
    const setEdits = edits[setIdx];
    if (!setEdits) return set;
    return {
      ...set,
      components: set.components.map((comp, compIdx) => {
        const compEdits = setEdits[compIdx];
        if (!compEdits) return comp;
        return { ...comp, ...compEdits };
      }),
    };
  });

  const output = {
    source_pdf: result.source_pdf,
    hardware_sets: editedSets,
    diagnostics: result.diagnostics,
  };

  const blob = new Blob([JSON.stringify(output, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = result.source_pdf.replace(/\.pdf$/i, "_hardware_sets.json");
  a.click();
  URL.revokeObjectURL(url);
};
```

Add download + JSON viewer buttons to the top bar:

```tsx
<div className="flex items-center gap-2">
  <button
    onClick={() => setShowJson((s) => !s)}
    className={`text-xs px-2 py-1 rounded border ${
      showJson
        ? "bg-blue-50 border-blue-300 text-blue-700"
        : "border-gray-200 text-gray-500 hover:border-gray-300"
    }`}
  >
    {showJson ? "Hide JSON" : "Show JSON"}
  </button>
  <button
    onClick={handleDownload}
    className="text-xs px-2 py-1 rounded border border-gray-200 text-gray-500 hover:border-gray-300"
  >
    ⬇ Download JSON
  </button>
</div>
```

Pass `showJson` state to DetailTable or render JsonViewer conditionally inside the detail column:

```tsx
{/* Inside the right panel area, after DetailTable */}
{showJson && (
  <JsonViewer set={activeSet} edits={edits[activeIndex] ?? {}} />
)}
```

The cleanest approach is to make the right column a wrapper div that stacks DetailTable and JsonViewer:

```tsx
<div className="flex-[1.6] min-w-0 flex flex-col">
  <DetailTable
    set={activeSet}
    edits={edits[activeIndex] ?? {}}
    editCount={editCount}
    onCellEdit={handleCellEdit}
    onReset={handleReset}
  />
  {showJson && (
    <JsonViewer set={activeSet} edits={edits[activeIndex] ?? {}} />
  )}
</div>
```

- [ ] **Step 3: Verify in browser**

1. Toggle "Show JSON" — JSON panel should appear below the table
2. Navigate between sets — JSON should update
3. Edit a cell — JSON should reflect the change
4. Click "Download JSON" — should download a `.json` file
5. Open the downloaded file — should contain all sets with edits applied

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/JsonViewer.tsx frontend/src/components/ResultsView.tsx
git commit -m "feat(frontend): add JSON viewer and download"
```

---

## Task 13: Deployment — Dockerfile + Static Serving

Create a Dockerfile that builds the frontend and runs the FastAPI app as a single service.

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Create `.dockerignore`**

```
# .dockerignore
.git
.claude
.superpowers
__pycache__
*.egg-info
node_modules
frontend/node_modules
frontend/.next
out/
logs/
docs/
*.pyc
.env
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
# Dockerfile
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

# System dep: pdftotext (from poppler-utils)
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils && rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir .

# Demo samples
COPY demo_samples/ demo_samples/

# Built frontend
COPY --from=frontend-build /app/frontend/dist frontend/dist

EXPOSE 8000

CMD ["uvicorn", "hardware_sets_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Verify Docker build**

```bash
docker build -t hardware-sets .
docker run --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY -p 8000:8000 hardware-sets
# Open http://localhost:8000 — should serve the frontend
# Click a sample — should run extraction and show results
```

- [ ] **Step 4: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat: add Dockerfile for single-service deployment"
```

---

## Post-Implementation Checklist

After all tasks are complete, verify end-to-end:

- [ ] Run `python -m pytest` — all backend tests pass
- [ ] Run `cd frontend && npm run build` — frontend builds cleanly
- [ ] Start both servers (`uvicorn` + `npm run dev`) and test the full flow:
  - Upload a PDF via dropzone
  - Click a sample card
  - Watch progress streaming
  - Navigate sets in sidebar
  - Verify source highlighting matches location data
  - Edit cells, confirm yellow highlight and badge
  - Toggle JSON viewer, verify edits appear
  - Download JSON, verify it includes edits
  - Test sidebar filter and collapse
  - Test error state (upload a non-PDF)
  - Test "no sets found" state
- [ ] Docker build and run succeeds
- [ ] Update `README.md` with setup and run instructions
