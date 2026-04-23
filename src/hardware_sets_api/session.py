from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

_TTL = 1800  # 30 minutes


@dataclass
class _Entry:
    pdf_bytes: bytes
    filename: str
    expires_at: float


_store: dict[str, _Entry] = {}


def _evict() -> None:
    now = time.monotonic()
    expired = [k for k, v in _store.items() if v.expires_at < now]
    for k in expired:
        del _store[k]


def put(pdf_bytes: bytes, filename: str) -> str:
    _evict()
    session_id = uuid.uuid4().hex
    _store[session_id] = _Entry(
        pdf_bytes=pdf_bytes,
        filename=filename,
        expires_at=time.monotonic() + _TTL,
    )
    return session_id


def get(session_id: str) -> tuple[bytes, str] | None:
    _evict()
    entry = _store.get(session_id)
    if entry is None:
        return None
    entry.expires_at = time.monotonic() + _TTL
    return (entry.pdf_bytes, entry.filename)
