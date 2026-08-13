# Architecture

## The decision that shaped everything: RAG as a tool

The obvious way to combine a chatbot, an agent and a RAG pipeline is to put three modes
behind three buttons. That was rejected, because it pushes the routing decision onto the
user: *"is this a catalogue question or a document question?"* — a question the user
should not have to answer, and often cannot.

Instead, retrieval over the uploaded PDF is registered as **one more function
declaration**, alongside the catalogue search, the weather lookup and the calculator. The
model routes. The consequences are worth stating because they are the reason the app is
one thing rather than three:

- **One conversation history.** "Which of those two scholarships fits my CV better?"
  requires the catalogue results *and* the document in the same context. Separate modes
  cannot answer it at all.
- **One set of grounding rules.** The system instruction forbids inventing scholarship
  facts and requires document answers to come from retrieved passages. Those rules live in
  one place instead of being re-stated per mode.
- **Chaining falls out for free.** The model can search the catalogue, read the CV, then
  call the calculator on the numbers it found — without any orchestration code written for
  that specific path.

## Request flow

```
Browser (static/app.js)
   │  POST /api/chat  { message, session_id }
   ▼
FastAPI (app/main.py)
   │  resolve session  ──────────────>  app/sessions.py   (history + RAG index, in RAM)
   ▼
Agent loop (app/agent.py)                     ┌─ declarations_for(corpus)
   │  chat_step(contents, declarations) ──────┤   (the document tool appears only
   │                                          └─   when a document exists)
   ├── model returns text ───────────────────────────────────> reply
   └── model returns functionCall(s)
         │  run_tool(...)  (app/tools.py — never raises into the loop)
         │     ├─ search_scholarships / get_scholarship_details → minhtak-api.fly.dev
         │     ├─ search_uploaded_documents → app/rag.py → app/store.py (cosine)
         │     ├─ get_weather → Open-Meteo
         │     └─ calculate → app/calculator.py (AST walk)
         │  all results appended in ONE user turn
         └──> loop (max MAX_AGENT_STEPS = 8)
```

## The RAG path

```
PDF bytes
  → app/pdf.py       extract text (pypdf, page-capped)
  → app/pdf.py       chunk: ~900 chars, 150-char overlap, word-aligned
  → app/gemini.py    embed each chunk (gemini-embedding-001, 768-dim,
                     taskType=RETRIEVAL_DOCUMENT)
  → app/store.py     append to the session's in-memory matrix

question
  → app/gemini.py    embed (taskType=RETRIEVAL_QUERY — a different vector for the
                     same text, tuned to the retrieval role)
  → app/store.py     cosine top-k (k=4)
  → returned to the AGENT as a tool result, with source file and similarity
```

The retrieval step does **not** generate the answer. The passages go back to the same
model that is running the conversation, which is what keeps one voice and one history
instead of a second chatbot bolted on beside the first.

## Error handling

Failures are separated by *who* can act on them:

| Layer | Behaviour | Why |
|---|---|---|
| Tool | Returns `{"error": ...}` to the **model** | The model can recover in-conversation: retry a city name, tell the user the catalogue is unreachable |
| Endpoint | Raises a typed `AssistantError` → HTTP status + Arabic message | The client renders it as a banner; no stack trace reaches the browser |
| Agent loop | Raises `AgentStalled` at the step ceiling | Better to admit failure than to answer without the tools |
| Unexpected | Caught by one handler → 500 + generic message, detail to the log | An exception must never leak internals into a chat bubble |

## State and its bounds

| State | Lives in | Bound |
|---|---|---|
| Model-facing history | Server session (RAM) | `MAX_HISTORY_TURNS`, trimmed at a user-turn boundary so a `functionCall` is never split from its `functionResponse` |
| Document vectors | Server session (RAM) | `MAX_DOCS_PER_SESSION`, `MAX_CHUNKS_PER_SESSION` |
| Sessions | Process-global dict | `SESSION_TTL_SECONDS` idle expiry, `MAX_SESSIONS` oldest-first eviction |
| Visible transcript | The user's browser | last 60 messages in `localStorage` |

Because the server's half is in RAM and the browser's half is not, the two can disagree
after a restart. The app detects this (`new_session` in the chat response) and **says so**
— a note in the thread telling the user the previous session expired and asking them to
re-upload — instead of quietly behaving as if it forgot.

## Deployment

One container on Fly.io (`fra`) serving both the API and the client, so there is a single
origin and no CORS configuration. **One machine, one worker** — sessions are in process
memory, and Fly's default HA pair would round-robin users between servers that cannot see
each other's conversations.

The path to horizontal scale, if it were needed: sessions and history into Redis, vectors
into a real vector store (pgvector — the parent platform already runs it), then raise the
machine count. Nothing in the module boundaries prevents that; `app/sessions.py` and
`app/store.py` are the only two files that would change.
