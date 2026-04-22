# Frontend UI Design — Hardware Sets Extraction

## Overview

A single-page web application for uploading Division 08 specbook PDFs, extracting hardware sets via the existing Python pipeline, and reviewing/editing the structured results. Deployed as a single service: FastAPI serves both the API and the built React SPA as static files.

**Stack:** FastAPI (API + static serving), Vite + React + TypeScript (frontend). Deployed on Railway or Render.

## Upload View

The landing page. Centered layout with two ways to start:

**Dropzone / file picker:** Accepts a single PDF. Drag-and-drop or click to browse. Validates file type client-side (PDF only). On upload, transitions to the processing state.

**Sample specbooks:** 2–3 pre-loaded sample PDFs displayed as clickable cards below the dropzone. Each card shows the specbook name and a brief label (e.g., "22 sets · list format", "8 sets · tabular schedule"). Clicking a sample triggers the same extraction flow as uploading a file — the sample PDFs are bundled server-side and processed identically.

The samples serve the interview demo: the reviewer can see results immediately without needing a specbook on hand, and the variety demonstrates the system handles different formats.

## Processing State

After upload or sample selection, the upload view transitions to a processing indicator. Two phases displayed sequentially, mirroring the actual pipeline stages:

1. **"Scanning pages..."** — the filter phase (fast, local). Shows the total page count once known.
2. **"Extracting sets from region 1/N..."** — the extract phase (LLM call per region). Updates the region counter as each region completes.

No fake progress bar. The text updates reflect real pipeline events streamed from the backend. Typical wall-clock time: 10–30 seconds depending on specbook size.

On completion, transitions to the results view.

## Results View — Three Panel Layout

The main UI after extraction completes. Three panels arranged horizontally:

### Left: Set Sidebar (~130px, collapsible)

- **Header:** total set count (e.g., "22 Sets") and a collapse toggle (◀) that hides the sidebar to give more room to the content panels.
- **Search/filter input:** filters the set list by set number or description as the user types.
- **Set list:** scrollable list of all extracted sets. Each item shows:
  - Set number + truncated description
  - Component count + page number
  - Visual distinction for NOT USED sets (dimmed/faded)
- **Active set** is highlighted (green). Clicking a set updates both the source panel and the detail table.

This handles specbooks with 60+ sets — the list scrolls and the filter narrows it down.

### Center: PDF Source Panel (~33%)

Displays the rendered text of the page(s) containing the selected set, using the same `NumberedLine` format the pipeline already produces. Key behaviors:

- **Line numbers** in a gutter on the left, matching the pipeline's 1-indexed line numbering.
- **Green highlight** on the line range belonging to the selected set (the `location.line_range` from extraction results). Non-highlighted lines are dimmed but visible for context.
- **Page navigation** (◀ ▶) when a set spans multiple pages (`continued_on` locations). The highlight follows to each continuation page.
- The source text is **read-only** — it's the ground truth the user references while reviewing/editing the structured table.

The source panel does NOT render the PDF visually (no embedded PDF viewer). It displays the extracted text lines, which is what the LLM actually sees. This is an intentional choice: it shows the user exactly what the model worked with, making it easier to diagnose extraction errors.

### Right: Component Table (~55%)

The structured extraction results for the selected set, displayed as an editable table.

**Header area:**
- Set number + green dot indicator
- Description, component count, location (page + line range)
- Edit tracking badge (e.g., "2 edited") — appears after any cell is modified
- JSON download button and inline viewer toggle

**Table columns:** QTY, DESCRIPTION, CATALOG #, MFR, FINISH, NOTES — matching the `Component` dataclass fields.

**Inline editing:**
- Click any cell to enter edit mode (blue border + cursor).
- Tab advances to the next cell, Esc cancels.
- Previously edited cells get a yellow background highlight so the user can see what's been changed at a glance.
- Edits are session-only (browser state). No backend persistence.

**Bottom bar:**
- Keyboard shortcut hints ("Click any cell to edit · Tab to advance · Esc to cancel")
- Reset button (reverts all edits for the current set to original extraction values)
- Save Changes button (commits edits to the in-memory state — reflected in JSON export)

**NOT USED sets:** displayed with an empty table body and a "NOT USED" indicator. Still navigable and visible in the sidebar.

## JSON Export

A single download button in the results header area exports the full document result as one JSON file. The format matches the existing CLI output structure:

```json
{
  "source_pdf": "specbook.pdf",
  "hardware_sets": [ ... ],
  "diagnostics": { ... }
}
```

If the user has made inline edits, the exported JSON reflects those changes.

**Inline JSON viewer:** a toggle in the set detail header opens a read-only JSON panel showing the raw JSON for the currently selected set. Useful during the Loom demo for showing the structured output alongside the table. The viewer updates live as the user navigates between sets or makes edits.

## API Design

FastAPI backend with the following endpoints:

### `POST /api/extract`
Accepts a PDF file upload (multipart/form-data). Runs the full pipeline (filter → extract). Returns the extraction result JSON.

Response is streamed as server-sent events (SSE) for progress updates:
```
event: progress
data: {"phase": "filter", "message": "Scanning 12 pages..."}

event: progress
data: {"phase": "extract", "message": "Extracting sets from region 1/2..."}

event: result
data: {"source_pdf": "...", "hardware_sets": [...], "diagnostics": {...}}
```

### `GET /api/samples`
Returns the list of available sample specbooks with metadata:
```json
[
  {"id": "bridgeport", "name": "Bridgeport Specs", "label": "22 sets · list format"},
  {"id": "morris-bank", "name": "Morris Bank", "label": "8 sets · tabular schedule"}
]
```

### `POST /api/extract/sample/{sample_id}`
Same as `/api/extract` but uses a bundled sample PDF instead of an upload. Same SSE progress stream and result format.

### Bundled page layouts

The extraction result includes all page layouts (rendered text lines) for the processed region. No separate endpoint needed — the source panel reads from the already-loaded result. This avoids server-side state and extra round-trips. The data is small (just text lines, typically a few KB per page).

The result shape extends the existing CLI output:
```json
{
  "source_pdf": "specbook.pdf",
  "hardware_sets": [ ... ],
  "page_layouts": {
    "3": [{"number": 1, "text": "HARDWARE GROUP NO. 1"}, ...],
    "4": [{"number": 1, "text": "..."}, ...]
  },
  "diagnostics": { ... }
}
```

### Static file serving
FastAPI mounts the built Vite output (`frontend/dist/`) at `/` as static files, with a catch-all fallback to `index.html` for client-side routing.

## Project Structure

```
src/
  hardware_sets/          # existing pipeline (unchanged)
  hardware_sets_api/      # new FastAPI app
    __init__.py
    app.py                # FastAPI app, static mount, CORS
    routes.py             # API endpoints
    samples.py            # sample PDF registry + metadata
frontend/
  src/
    App.tsx
    components/
      UploadView.tsx      # dropzone + sample cards
      ProcessingView.tsx  # two-phase progress indicator
      ResultsView.tsx     # three-panel layout shell
      SetSidebar.tsx      # set list + search
      SourcePanel.tsx     # PDF text with line highlighting
      DetailTable.tsx     # editable component table
      JsonViewer.tsx      # inline JSON toggle panel
    hooks/
      useExtraction.ts    # SSE connection, progress state, result state
    types.ts              # TypeScript types mirroring Python dataclasses
  index.html
  vite.config.ts
  package.json
  tsconfig.json
```

## Deployment

Single-service deployment:

1. **Build step:** `cd frontend && npm run build` produces `frontend/dist/`.
2. **Runtime:** `uvicorn hardware_sets_api.app:app` serves both the API routes and the static frontend.
3. **Environment:** requires `ANTHROPIC_API_KEY` set on the deployment platform.
4. **Platform:** Railway or Render free tier. Single Dockerfile or buildpack that installs Python deps + builds the frontend.

## Out of Scope

- PDF visual rendering (embedded PDF viewer) — we show extracted text lines, not the rendered PDF
- Multi-document sessions — one PDF at a time
- Edit persistence — session-only, no database
- User authentication — open access
- Model selection — uses the pipeline default (Sonnet)
- Mobile/responsive layout — desktop-focused for the demo
