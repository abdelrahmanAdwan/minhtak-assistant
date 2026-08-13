"""In-memory conversation sessions with a TTL.

Why nothing is persisted: a session holds a student's uploaded CV and their
conversation about it. Writing that to disk would make this app a custodian of
personal data, which is a much heavier promise than a portfolio assistant
should make. So the corpus and the model-facing history live in RAM, expire on
idle, and disappear on restart.

The BROWSER keeps its own copy of the visible transcript, so a restart costs
the model's memory of the conversation -- not the user's. When that happens the
UI says so plainly instead of pretending the assistant forgot.

Two bounds keep a small machine safe: `SESSION_TTL_SECONDS` (idle expiry) and
`MAX_SESSIONS` (oldest-first eviction).
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from . import config
from .errors import SessionExpired
from .rag import DocumentCorpus


@dataclass
class Session:
    id: str
    created_at: float
    last_seen: float
    # The Gemini `contents` list: user turns, model turns, and tool results.
    history: list[dict[str, Any]] = field(default_factory=list)
    corpus: DocumentCorpus = field(default_factory=DocumentCorpus)
    message_count: int = 0

    def touch(self) -> None:
        self.last_seen = time.time()

    def trimmed_history(self) -> list[dict[str, Any]]:
        """Keep the tail of the conversation the model needs to stay coherent.

        Trimming happens at a USER turn boundary: cutting between a model's
        functionCall and its functionResponse would hand Gemini an invalid
        conversation, which fails as a confusing 400 rather than a clean
        truncation.
        """
        limit = config.MAX_HISTORY_TURNS
        if len(self.history) <= limit:
            return list(self.history)
        tail = self.history[-limit:]
        for index, entry in enumerate(tail):
            if entry.get("role") == "user" and any(
                    "text" in part for part in entry.get("parts", [])):
                return tail[index:]
        return []


class SessionStore:
    """Thread-safe because uvicorn runs request handlers in a worker pool."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self) -> Session:
        now = time.time()
        session = Session(id=uuid.uuid4().hex, created_at=now, last_seen=now)
        with self._lock:
            self._evict_locked()
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session:
        """Fetch a live session or raise `SessionExpired` -- callers must not
        silently invent a new one, or a user would lose their uploaded document
        without ever being told."""
        with self._lock:
            session = self._sessions.get(session_id or "")
            if session is None or self._is_expired(session):
                self._sessions.pop(session_id or "", None)
                raise SessionExpired(f"session {session_id!r} is not active")
            session.touch()
            return session

    def drop(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    @property
    def active(self) -> int:
        with self._lock:
            self._sweep_locked()
            return len(self._sessions)

    # -- internals ---------------------------------------------------------- #
    @staticmethod
    def _is_expired(session: Session) -> bool:
        return time.time() - session.last_seen > config.SESSION_TTL_SECONDS

    def _sweep_locked(self) -> None:
        for key in [k for k, s in self._sessions.items() if self._is_expired(s)]:
            self._sessions.pop(key, None)

    def _evict_locked(self) -> None:
        self._sweep_locked()
        while len(self._sessions) >= config.MAX_SESSIONS:
            oldest = min(self._sessions.values(), key=lambda s: s.last_seen)
            self._sessions.pop(oldest.id, None)


STORE = SessionStore()


def get_or_create(session_id: Optional[str]) -> tuple[Session, bool]:
    """Resolve a session id, creating one if it is missing or expired.

    Returns `(session, is_new)` so the caller can tell the user honestly that a
    fresh conversation was started.
    """
    if session_id:
        try:
            return STORE.get(session_id), False
        except SessionExpired:
            pass
    return STORE.create(), True
