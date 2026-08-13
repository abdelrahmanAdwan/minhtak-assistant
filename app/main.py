"""FastAPI application: JSON API + the static web client, one container.

Endpoints
    POST   /api/session            start a conversation
    GET    /api/session/{id}       what the server still remembers
    DELETE /api/session/{id}       forget everything (documents included)
    POST   /api/chat               one turn -> reply + tool trace
    POST   /api/documents          upload a PDF into the session's RAG index
    GET    /api/health             liveness + live counters

Error contract: every failure is an `AssistantError` subclass carrying an HTTP
status and an Arabic message the client renders as-is. Nothing else escapes --
an unexpected exception becomes a generic 500 with a safe message, and the
detail stays in the server log.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .agent import run_turn
from .errors import AssistantError, BadRequest, UploadRejected
from .sessions import STORE, get_or_create

logger = logging.getLogger("minhtak-assistant")
logging.basicConfig(level=logging.INFO)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="منحتك Assistant",
    description="Chat + tool calling + PDF RAG over the live منحتك catalogue.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Error handling -- one place, so no handler needs a try/except of its own
# --------------------------------------------------------------------------- #
@app.exception_handler(AssistantError)
async def _assistant_error(_: Request, exc: AssistantError) -> JSONResponse:
    logger.warning("%s: %s", exc.__class__.__name__, exc.detail)
    return JSONResponse(
        status_code=exc.status,
        content={"error": exc.__class__.__name__, "message": exc.user_message},
    )


@app.exception_handler(Exception)
async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
    # The detail is logged, never returned: a stack trace in the chat window is
    # both a bad experience and an information leak.
    logger.exception("unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "InternalError",
                 "message": "حدث خطأ غير متوقع. حاول مرة أخرى."},
    )


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class ChatIn(BaseModel):
    message: str = Field(..., description="The user's message.")
    session_id: Optional[str] = Field(None, description="Omit to start fresh.")


class ChatOut(BaseModel):
    session_id: str
    reply: str
    trace: list[dict[str, Any]]
    documents: list[str]
    new_session: bool


# --------------------------------------------------------------------------- #
# Session endpoints
# --------------------------------------------------------------------------- #
@app.post("/api/session")
def start_session() -> dict[str, Any]:
    session = STORE.create()
    return {"session_id": session.id, "ttl_seconds": config.SESSION_TTL_SECONDS}


@app.get("/api/session/{session_id}")
def read_session(session_id: str) -> dict[str, Any]:
    session = STORE.get(session_id)          # raises SessionExpired -> 404
    return {
        "session_id": session.id,
        "message_count": session.message_count,
        "documents": [doc["filename"] for doc in session.corpus.documents],
    }


@app.delete("/api/session/{session_id}")
def end_session(session_id: str) -> dict[str, Any]:
    STORE.drop(session_id)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Chat
# --------------------------------------------------------------------------- #
@app.post("/api/chat", response_model=ChatOut)
def chat(payload: ChatIn) -> ChatOut:
    session, is_new = get_or_create(payload.session_id)
    reply, trace = run_turn(session, payload.message)
    return ChatOut(
        session_id=session.id,
        reply=reply,
        trace=trace,
        documents=[doc["filename"] for doc in session.corpus.documents],
        new_session=is_new and bool(payload.session_id),
    )


# --------------------------------------------------------------------------- #
# Document upload (RAG ingestion)
# --------------------------------------------------------------------------- #
@app.post("/api/documents")
async def upload_document(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
) -> dict[str, Any]:
    filename = (file.filename or "document.pdf").strip()
    if not filename.lower().endswith(".pdf"):
        raise BadRequest("not a pdf", user_message="يُقبل ملف PDF فقط.")

    raw = await file.read()
    if not raw:
        raise UploadRejected("empty upload", user_message="الملف فارغ.")
    if len(raw) > config.MAX_UPLOAD_BYTES:
        raise UploadRejected(
            f"{len(raw)} bytes",
            user_message=(f"حجم الملف يتجاوز "
                          f"{config.MAX_UPLOAD_BYTES // (1024 * 1024)} ميغابايت."))

    session, is_new = get_or_create(session_id)
    summary = session.corpus.ingest(raw, filename)
    return {
        "session_id": session.id,
        "new_session": is_new and bool(session_id),
        "documents": [doc["filename"] for doc in session.corpus.documents],
        **summary,
    }


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "model": config.GEMINI_MODEL,
        "gemini_key_configured": bool(config.GEMINI_API_KEY),
        "catalogue_api": config.MINHTAK_API_BASE,
        "active_sessions": STORE.active,
    }


# --------------------------------------------------------------------------- #
# The web client -- mounted LAST so it never shadows /api/*
# --------------------------------------------------------------------------- #
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
