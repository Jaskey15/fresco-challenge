"""FastAPI app — health + extract (SSE) + pdf serving."""

from __future__ import annotations

import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from hardware_sets_api.session import store
from hardware_sets_api.sse import heartbeat_merge, stream_extract

MAX_PDF_BYTES = 25 * 1024 * 1024  # 25 MB


def _allowed_origins() -> list[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(title="hardware-sets API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/extract")
async def extract(file: UploadFile = File(...)) -> StreamingResponse:
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="empty upload")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="pdf exceeds 25 MB")

    filename = file.filename or "upload.pdf"
    session_id = store.put(pdf_bytes, filename)

    async def gen():
        async for chunk in heartbeat_merge(
            stream_extract(pdf_bytes, filename, session_id)
        ):
            yield chunk

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/pdf/{session_id}")
def pdf(session_id: str) -> Response:
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="session expired or not found")
    return Response(
        content=entry.pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{entry.filename}"',
            "Cache-Control": "private, max-age=300",
        },
    )
