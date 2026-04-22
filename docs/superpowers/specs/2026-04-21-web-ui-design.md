# Web UI Design — Hardware Sets

**Date:** 2026-04-21
**Scope:** Web UI that wraps the existing Python extraction pipeline (spec: `2026-04-21-pdf-parsing-design.md`). Frontend-only additions here; the extractor's architecture is covered in that earlier spec.

## 1. Goal

A single-page web application for the Fresco interview challenge that lets a reviewer drag-drop a Division 08 specbook PDF, watch it stream through the existing extraction pipeline with live progress, review extracted hardware sets alongside the source PDF with bounding-box highlighting, correct mistakes inline, and export corrected JSON.

Target audience: the Fresco interview reviewers and a 3–5 minute Loom walkthrough. Not a production SaaS.

## 2. Scope

**In scope for v1:**

- Drag-drop PDF upload (single file).
- Server-sent events streaming of extraction progress and results.
- Results view: sets-first layout with PDF-as-evidence pane (bbox-highlighted).
- Inline editing: edit any component field, delete sets, add/remove components.
- Export: JSON download and copy-to-clipboard, including a `corrections` diff.
- Blueprint-themed visual direction across all screens (see §7).
- localStorage persistence of user edits (single browser).
- Clear empty/error states for scanned PDFs, no-schedule-found, and mid-stream failures.

**Out of scope for v1 (deferred):**

- Pre-loaded sample PDFs with cached results (v2 enhancement; landing page reserves layout space for a sample-chip row).
- OCR for scanned PDFs.
- Auth, multi-user, team features.
- Cross-browser persistence (no database, no accounts).
- Per-document legend-table handling for manufacturer short codes (flagged in extractor spec §4.4).
- Batch upload.

## 3. Architecture

**Frontend:** Next.js 15 + TypeScript, deployed to **Vercel**.

- App Router, Tailwind CSS.
- `react-pdf` (pdf.js wrapper) for page rendering.
- Native `EventSource` for SSE consumption.
- Small custom drag-drop hook — no heavy dropzone dependency.

**Backend:** FastAPI wrapper around the existing Python pipeline, deployed to **Fly.io**.

- Dockerfile bakes in `poppler-utils`, Python 3.12, existing deps.
- Fly chosen over Render because poppler + sustained-runtime SSE is cleaner on a Docker image than on Render's free tier (which sleeps aggressively).
- Two endpoints:
  - `POST /extract` — reads PDF bytes, returns an SSE stream of typed events.
  - `GET /pdf/{session_id}` — serves the just-uploaded PDF back to the browser for rendering. In-memory storage, TTL 10 minutes. Session ID returned in the first SSE event.
- Stateless modulo the in-memory PDF cache.

**Deployment:** two platforms, one README. Frontend env var `NEXT_PUBLIC_API_URL` points at Fly. Backend env vars: `ANTHROPIC_API_KEY`, `ALLOWED_ORIGINS` (for CORS).

This split matches Fresco's own stack ("React + TypeScript on the frontend, Python on the backend" — from their job posting).

## 4. Data model

Declared once in Pydantic on the backend, mirrored as TypeScript types on the frontend (hand-maintained for v1; codegen is premature).

```python
class Location(BaseModel):
    page: int
    line_range: tuple[int, int]                    # 1-indexed pdftotext lines
    bbox: tuple[float, float, float, float]        # x0, y0, x1, y1 in PDF points — NEW

class Component(BaseModel):
    qty: int | None
    description: str | None
    catalog_number: str | None
    mfr: str | None
    finish: str | None
    notes: str | None
    confidence: dict[str, float]                   # per-field: mfr, finish, qty

class HardwareSet(BaseModel):
    set_number: str
    description: str | None
    location: Location
    continued_on: list[Location]
    is_not_used: bool
    components: list[Component]
    confidence: float
```

**Load-bearing addition: `Location.bbox`.** The extractor spec stores only `line_range` today. The evidence pane needs pixel coordinates to overlay a highlight on the rendered PDF, so `layout.py` must cluster pdfplumber word-level bboxes by y-coordinate into line bboxes, attach them to `NumberedLine`, and surface the union bbox for a set's line range as `Location.bbox`. This is the primary backend change — estimated half-day of work.

The existing JSON output schema remains backward-compatible: `Location` gains a new optional field, nothing is removed.

## 5. SSE event protocol

```
event: session_started   data: {"session_id": "abc123"}
event: region_found      data: {"page_start": 15, "page_end": 17, "marker": "Group 1"}
event: extracting        data: {"region_index": 0, "total_regions": 3}
event: set_extracted     data: {<HardwareSet JSON>}
event: scored            data: {"set_index": 5, "confidence": 0.88}
event: warning           data: {"message": "..."}
event: done              data: {"total_sets": 12, "llm_calls": 3, "warnings": []}
event: error             data: {"code": "scanned_pdf|no_schedule|api_error|parse_error", "message": "..."}
```

The frontend appends `set_extracted` events to the sets list incrementally, so a reviewer can start scanning before `done` fires. This is the core "feels alive" demo moment.

## 6. Repository layout & frontend structure

The project becomes a monorepo-style layout:

```
fresco-challenge/
├── src/hardware_sets/              # Existing Python pipeline (unchanged structure)
│   └── ... (filter.py, layout.py, extract.py, resolve.py, cli.py, types.py, vocab.py)
├── src/hardware_sets_api/          # NEW — FastAPI wrapper
│   ├── __init__.py
│   ├── main.py                     # FastAPI app, SSE endpoint
│   └── session.py                  # in-memory PDF cache with TTL
├── Dockerfile                      # NEW — poppler + Python, for Fly.io
├── fly.toml                        # NEW — Fly app config
└── frontend/                       # NEW — Next.js app (deployed to Vercel)
    ├── app/
    ├── lib/
    ├── package.json
    └── next.config.mjs
```

The FastAPI module imports from `src/hardware_sets` — no code duplication.

Frontend tree:

```
frontend/
├── app/
│   ├── page.tsx                    # Landing — Blueprint drop-first (§7)
│   ├── extract/page.tsx            # Live extraction + results (client component)
│   └── components/
│       ├── BlueprintChrome.tsx     # title strip, crosshairs, bottom strip, grid background
│       ├── DropZone.tsx            # drag-drop + file input + dimension callouts
│       ├── StreamLog.tsx           # live SSE event log
│       ├── SetCard.tsx             # one set, editable
│       ├── ComponentRow.tsx        # editable qty/desc/cat/mfr/finish/notes
│       ├── ConfidenceBadge.tsx     # per-field confidence dot + tooltip
│       ├── EvidencePane.tsx        # pdf.js page + overlay bbox (primary tab)
│       ├── EvidenceTextTab.tsx     # pdftotext line view (secondary tab)
│       └── ExportMenu.tsx          # download .json / copy to clipboard
└── lib/
    ├── types.ts                    # shared data model (mirrors Pydantic)
    ├── sse.ts                      # EventSource consumer + typed events
    ├── storage.ts                  # localStorage edit persistence
    └── corrections.ts              # diff builder for export
```

Results-page layout (Layout B from brainstorming):

- **Left column (≈60%):** scrollable sets list on the far left, selected-set editable detail filling the rest.
- **Right column (≈40%):** evidence pane — PDF page with bbox highlight overlay (primary tab), `pdftotext -layout` line view (secondary tab, the "here's what the LLM actually saw" view).

All screens wear the Blueprint chrome from the landing page for visual continuity.

## 7. Visual direction — Blueprint

Committed aesthetic (Direction A from brainstorming):

- **Palette:** deep blueprint navy `#081a34`, cyan accent `#7ac9ff`, cyan-white ink `#e3edff`. No gradients; a subtle noise/grain overlay for paper texture.
- **Typography:** Fraunces (serif display, italic emphasis) for headlines; JetBrains Mono for chrome, dimensions, and technical data.
- **Motifs:** blueprint grid background (16px minor, 80px major), title-block chrome (DWG·01, REV·A, SHT·1·1), corner crosshairs, dimension-line callouts around the drop zone (↔, ↕, SCALE 1:1).
- **Landing page:** drop zone is the hero. Single italic headline above ("Hardware Sets, *located.*"), no marketing paragraph. Drop zone is ~860px wide with its own big italic headline "Drop your *specbook.*", ambient cyan halo glow, hover lift.
- **Results page:** white-on-navy chrome, set tables use monospace for catalog numbers / mfr codes / finish codes; serif for set titles.
- **Motion:** staggered fade-up on initial load; hover lift on interactive elements; pulse on the title-strip status dot.

The full Blueprint landing page mockup is the brainstorming artifact at `.superpowers/brainstorm/.../content/dir-a-blueprint-v2.html`.

## 8. Editing flow

Click any field → inline input appears → blur or Enter commits. Corrections stored in a `Map` keyed by `setNumber.componentIndex.field` with `{ before, after }`. localStorage writes on every mutation, keyed by SHA-256 of the uploaded PDF bytes.

On re-upload of the same PDF (same hash), the landing page offers to restore prior edits.

**Set-level actions:**

- **Delete set** → soft-delete; stays in corrections as `{ type: "delete_set", set_number }`.
- **Add component** → empty row appended, user fills in.
- **Remove component** → soft-delete inside set.

**Export** emits:

```json
{
  "source_pdf": "common_lanes_div_8.pdf",
  "extracted_at": "2026-04-21T19:30:00Z",
  "hardware_sets": [ /* applied: LLM output with user edits merged in */ ],
  "corrections": [ /* list of { set_number, component_index, field, before, after, type } */ ]
}
```

The original extraction is preserved alongside the user's diffs so reviewers can see exactly what a human changed.

## 9. Error handling

Backend emits structured `error` SSE events with one of four codes:

| Code | Trigger | UI state |
|---|---|---|
| `scanned_pdf` | No extractable text | Empty state: "No extractable text — OCR not supported." |
| `no_schedule` | Extractor found no Division 08 region | Empty state: "Division 08 hardware schedule not detected." |
| `api_error` | Claude call failed after one retry | Banner: retry button, partial results preserved |
| `parse_error` | PDF unreadable | Empty state: "Couldn't read this PDF." |

Each empty state keeps the Blueprint chrome and offers an "Upload another" action that returns to the landing page. Mid-stream errors preserve already-extracted sets ("Extraction stopped after set 4. Showing what we have.") with a retry button.

## 10. Testing

Consistent with the existing extractor's manual-QA philosophy (per extractor spec §8). No UI test infrastructure — no Playwright, no component tests, no E2E.

**Two targeted unit tests** for logic with silent-failure modes:

- `tests/test_layout_bbox.py` — `layout.py` line-clustering math. Given hand-crafted word bboxes, asserts cluster count and union rectangles. Catches bbox bugs that would otherwise look like "highlight is drawn in the wrong place" and confuse debugging.
- `frontend/lib/corrections.test.ts` — diff builder output shape for field edit, delete-set, and add-component cases. Catches silent corruption of the export JSON.

**CI-style gates** — all must pass:

- `tsc --noEmit` on the frontend
- `next build` on the frontend
- `pytest` on the backend (existing suites + new `test_layout_bbox`)

**Manual QA** (the primary loop):

1. Happy path: 2–3 sample PDFs extract end-to-end, bbox overlays land on the right rows.
2. Editing: field edits persist across refresh, export includes diffs.
3. Each error state reachable by crafting inputs.
4. Responsive: mobile/tablet viewports — landing page renders, results collapse split to stacked panes.

## 11. Rough effort estimate

| Work | Effort |
|---|---|
| Backend: bbox extraction in `layout.py`, FastAPI wrapper, Dockerfile, Fly deploy | ~1 day |
| Frontend: scaffold + Blueprint landing page + drag-drop upload | ~4 hrs |
| Streaming results + PDF render + bbox overlay | ~1 day |
| Inline editing + localStorage + export | ~4 hrs |
| Polish + error states + README updates + Loom recording | ~4 hrs |

**~3 focused days.** Fits inside a week-long challenge window with iteration room.

## 12. Dependencies added

**Frontend (new):**

- `next` 15, `react` 18, `typescript`, `tailwindcss`
- `react-pdf` (pdf.js wrapper)
- `vitest` (only for the one corrections test)

**Backend (new):**

- `fastapi`
- `uvicorn[standard]`
- No new runtime system deps — poppler already required by existing pipeline.

## 13. Key decisions (why, briefly)

- **Layout B (sets-first) over three-pane workbench:** the set is the content, the PDF is evidence. Three-pane feels cramped on a ~15" laptop and dilutes the editing surface.
- **Bounding-box highlight (C) over text-snippet view (A) or plain page scroll (B):** C is the "money shot" for the Loom — a yellow rectangle visibly snapping around the right rows on the page directly demonstrates the `location` success criterion.
- **SSE streaming over job-queue polling:** for a demo, "feels alive" beats "survives refresh." Reviewer watches the pipeline announce itself without the agent narrating it.
- **Frontend on Vercel, backend on Fly.io:** matches Fresco's actual stack. Keeps the working Python pipeline intact. Two platforms is a one-line README note, not a reviewer minus.
- **Blueprint aesthetic over Fresco-brand-matching:** distinctive creative choice that still respects the domain. Reviewer remembers it.
- **No test infrastructure for UI:** a one-off demo doesn't earn its keep under Playwright/component-test maintenance. Two targeted unit tests for silent-failure logic are the exception.
