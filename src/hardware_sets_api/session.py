"""In-memory PDF session cache with TTL (spec §3).

Not persistent: we accept that a pod restart drops active sessions. Keys
are UUID4 hex. Eviction is lazy on every `get` / `put` call — no background
task so the module stays safe to import in any context.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

DEFAULT_TTL_SECONDS = 600  # 10 minutes


@dataclass
class SessionEntry:
    pdf_bytes: bytes
    filename: str
    expires_at: float


class SessionStore:
    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, SessionEntry] = {}

    def _evict_expired(self, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        dead = [sid for sid, e in self._store.items() if e.expires_at <= now]
        for sid in dead:
            self._store.pop(sid, None)

    def put(self, pdf_bytes: bytes, filename: str) -> str:
        self._evict_expired()
        sid = uuid.uuid4().hex
        self._store[sid] = SessionEntry(
            pdf_bytes=pdf_bytes,
            filename=filename,
            expires_at=time.time() + self._ttl,
        )
        return sid

    def get(self, session_id: str) -> SessionEntry | None:
        self._evict_expired()
        return self._store.get(session_id)


# Module-level singleton — one FastAPI process, one store.
store = SessionStore()
