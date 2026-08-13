# Single container: the FastAPI app serves both the JSON API and the web client,
# so the whole assistant is one deploy and one origin (no CORS to configure).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY static/ ./static/

EXPOSE 8080

# ONE worker on purpose: sessions and the RAG index live in THIS process's
# memory (see app/sessions.py), so a second worker would answer half the
# requests from a session it cannot see. The same reasoning caps the app at one
# MACHINE (`fly scale count 1`) — Fly's default 2-machine HA pair round-robins
# requests, which would look to users like the assistant randomly forgetting
# their upload. Horizontal scaling needs a shared session store (Redis); that
# trade-off is documented in the README rather than hidden here.
# --proxy-headers so Fly's edge IP does not replace the real client IP in logs.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", \
     "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
