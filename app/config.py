"""Runtime configuration, loaded from the environment (.env supported).

Nothing secret is hard-coded. Every limit that protects the server from a
hostile or careless client lives here, so the production posture can be read
in one screen instead of being hunted through the code.
"""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is optional -- real env vars work without it
    pass

# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
GEMINI_API_KEY: str | None = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_BASE: str = "https://generativelanguage.googleapis.com/v1beta/models"

EMBEDDING_MODEL: str = "gemini-embedding-001"
EMBEDDING_DIM: int = 768

# --------------------------------------------------------------------------- #
# External services (no keys required)
# --------------------------------------------------------------------------- #
# The live منحتك catalogue -- the scholarship tools call this public API.
MINHTAK_API_BASE: str = os.environ.get(
    "MINHTAK_API_BASE", "https://minhtak-api.fly.dev"
).rstrip("/")

# Open-Meteo, free and key-less (the weather tool).
GEOCODE_BASE: str = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_BASE: str = "https://api.open-meteo.com/v1/forecast"

REQUEST_TIMEOUT: float = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "60"))

# --------------------------------------------------------------------------- #
# Agent limits
# --------------------------------------------------------------------------- #
# Safety valve: a misbehaving loop can never call tools forever.
MAX_AGENT_STEPS: int = int(os.environ.get("MAX_AGENT_STEPS", "8"))
MAX_MESSAGE_CHARS: int = int(os.environ.get("MAX_MESSAGE_CHARS", "4000"))

# Trim the model-facing history so a long conversation cannot grow the prompt
# without bound. The BROWSER keeps the full transcript; only what the model
# needs to stay coherent is replayed.
MAX_HISTORY_TURNS: int = int(os.environ.get("MAX_HISTORY_TURNS", "24"))

# --------------------------------------------------------------------------- #
# Upload + RAG limits
# --------------------------------------------------------------------------- #
MAX_UPLOAD_BYTES: int = int(os.environ.get("MAX_UPLOAD_BYTES", str(8 * 1024 * 1024)))
MAX_PDF_PAGES: int = int(os.environ.get("MAX_PDF_PAGES", "60"))
MAX_DOCS_PER_SESSION: int = int(os.environ.get("MAX_DOCS_PER_SESSION", "5"))
MAX_CHUNKS_PER_SESSION: int = int(os.environ.get("MAX_CHUNKS_PER_SESSION", "400"))
RAG_TOP_K: int = int(os.environ.get("RAG_TOP_K", "4"))

# --------------------------------------------------------------------------- #
# Sessions (in-memory -- see app/sessions.py for why nothing is persisted)
# --------------------------------------------------------------------------- #
SESSION_TTL_SECONDS: int = int(os.environ.get("SESSION_TTL_SECONDS", str(60 * 60)))
MAX_SESSIONS: int = int(os.environ.get("MAX_SESSIONS", "300"))

ALLOWED_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]
