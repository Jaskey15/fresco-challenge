from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from pathlib import Path
from queue import Queue
from threading import Thread

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse

from hardware_sets_api import session
from hardware_sets_api.pipeline import run_pipeline
from hardware_sets_api.samples import SAMPLE_BY_ID, SAMPLES

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.get("/samples")
def list_samples():
    return [{"id": s.id, "name": s.name, "label": s.label} for s in SAMPLES]


@router.get("/pdf/{session_id}")
def get_pdf(session_id: str):
    result = session.get(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Session expired or not found")
    pdf_bytes, filename = result
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


def _stream_extraction(
    pdf_path: Path,
    cleanup: bool = False,
    session_id: str | None = None,
):
    queue: Queue = Queue()

    def on_progress(event: dict):
        queue.put(("progress", event))

    def run():
        try:
            result = run_pipeline(pdf_path, on_progress)
            if session_id:
                result["session_id"] = session_id
            queue.put(("result", result))
        except Exception as e:
            log.exception("Pipeline failed for %s", pdf_path.name)
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
    session_id = session.put(content, file.filename or "upload.pdf")

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(content)
    tmp.close()

    return _stream_extraction(Path(tmp.name), cleanup=True, session_id=session_id)


@router.post("/extract/sample/{sample_id}")
def extract_sample(sample_id: str):
    sample = SAMPLE_BY_ID.get(sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail=f"Sample '{sample_id}' not found")
    if not sample.path.is_file():
        raise HTTPException(status_code=500, detail=f"Sample file missing: {sample.filename}")

    pdf_bytes = sample.path.read_bytes()
    session_id = session.put(pdf_bytes, sample.filename)

    return _stream_extraction(sample.path, cleanup=False, session_id=session_id)
