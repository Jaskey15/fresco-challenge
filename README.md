# Fresco Coding Challenge — Hardware Sets

Extract door-hardware sets from Division 08 specbook PDFs into structured JSON with per-set location data (page, line range, and pixel bounding box). Ships as:

1. A Python CLI (`python -m hardware_sets ...`) — the original pipeline.
2. A FastAPI service (`src/hardware_sets_api/`) — wraps the pipeline, streams typed SSE events.
3. A Next.js frontend (`frontend/`) — drag-drop upload, live streaming, inline editing, PDF evidence pane with bbox highlights.

## Live demo

- **Frontend (Vercel):** <!-- fill in after deploy -->
- **API (Fly.io):** <!-- fill in after deploy -->

## Architecture

```
PDF ─┬─→ filter.py    (pick schedule regions)
     │
     ├─→ layout.py    (pdftotext lines + pdfplumber bboxes)
     │
     ├─→ extract.py   (Claude Sonnet 4.6, tool use)
     │
     └─→ resolve.py   (vocab confidence scoring)
                │
                └─→ SSE events → Next.js UI
```

See `docs/superpowers/specs/` for the full designs.

## Run locally

### Backend

Requires Python 3.12 and `poppler` (for `pdftotext`):

```sh
brew install poppler                        # macOS; apt-get install poppler-utils on Debian
python -m venv .venv && source .venv/bin/activate
pip install -e '.[api,dev]'
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn hardware_sets_api.main:app --port 8000
```

### Frontend

Requires Node 20+:

```sh
cd frontend
cp .env.local.example .env.local            # NEXT_PUBLIC_API_URL defaults to http://localhost:8000
npm install
npm run dev
```

Open <http://localhost:3000>, drop any sample PDF (e.g. `samples/div_08_1.pdf`), and watch it stream.

### CLI-only usage

```sh
python -m hardware_sets samples/div_08_1.pdf --out out/div_08_1.json
```

## Deploy

### Backend (Fly.io)

```sh
fly launch --no-deploy --copy-config        # first time: reads fly.toml
fly secrets set ANTHROPIC_API_KEY=sk-ant-...
fly secrets set ALLOWED_ORIGINS=https://<your-vercel-app>.vercel.app
fly deploy
```

### Frontend (Vercel)

```sh
cd frontend
vercel --prod
# Set NEXT_PUBLIC_API_URL=https://<your-fly-app>.fly.dev in Vercel env settings.
```

## Tests

```sh
pytest                                       # Python: filter patterns, resolve scoring, layout bbox clustering
cd frontend && npm test -- --run             # TypeScript: corrections diff builder
cd frontend && npm run typecheck             # tsc --noEmit
cd frontend && npm run build                 # next build
```

## Output schema

Each hardware set emits:

```json
{
  "set_number": "1.1",
  "description": "RECEPTION",
  "location": { "page": 40, "line_range": [12, 26], "bbox": [50, 100, 555, 240] },
  "continued_on": [],
  "is_not_used": false,
  "components": [
    {
      "qty": 1,
      "description": "HINGE",
      "catalog_number": "...",
      "mfr": "IVES",
      "finish": "630",
      "notes": null,
      "confidence": { "mfr": 1.0, "finish": 1.0, "qty": 1.0 }
    }
  ],
  "confidence": 0.95
}
```

`bbox` is `(x0, top, x1, bottom)` in PDF points (top-left origin, increases downward). `null` when the pdfplumber cluster count disagreed with the pdftotext line count on that page — the UI degrades to "scroll to line, no highlight."

## Known caveats

- **mfr short codes** (e.g. `IVE`, `VON`) are project-local — if a specbook uses a code not in `vocab.py`, it flags as low confidence rather than an error. See `resolve.py` docstring.
- **Scanned PDFs** are detected and rejected; OCR is out of scope for v1.
- **Session PDFs** are held in memory for 10 minutes on the API server. A pod restart drops active sessions.
