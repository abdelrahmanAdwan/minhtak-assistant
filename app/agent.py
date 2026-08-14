"""The tool-calling loop.

    user text
        -> Gemini (given the declarations) decides: answer, or call tools
        -> we execute each call and feed every result back in one turn
        -> Gemini decides again (another tool, or the final answer)
        -> repeat until it returns text, or MAX_AGENT_STEPS is hit

Tool SELECTION belongs to the model (`mode = AUTO`); this module executes what
it picks, records the turns into the session history, and collects a TRACE so
the UI can show which tools ran and why an answer says what it says.

Running out of steps raises rather than returning a guess: an assistant that
invents an answer after failing to use its tools is worse than one that admits
it could not finish.
"""

from __future__ import annotations

from typing import Any

from . import config
from .errors import AgentStalled, BadRequest
from .gemini import chat_step
from .sessions import Session
from .tools import declarations_for, run_tool

# What the UI renders under "الأدوات المستخدمة".
TraceEntry = dict[str, Any]


def _summarize(result: dict[str, Any]) -> str:
    """A one-line, human-readable summary of a tool result for the trace.

    The full payload stays inside the model's context; the user gets the gist,
    which is what makes the trace readable rather than a JSON dump.
    """
    if not isinstance(result, dict):
        return str(result)[:160]
    if "error" in result:
        return f"خطأ: {result['error']}"[:200]
    if "match_count" in result:
        return f"{result['match_count']} من {result.get('total_in_catalogue', '?')} في الكتالوج"
    if "results" in result and "query" in result:
        return f"{result.get('result_count', 0)} نتيجة ويب"
    if "result_count" in result:
        return f"{result['result_count']} منحة مطابقة"
    if "passages" in result:
        count = len(result["passages"])
        return f"{count} مقطع من الملف" if count else "لا مقاطع مطابقة"
    if "result" in result:
        return f"= {result['result']}"
    if "temperature_c" in result:
        return f"{result.get('city', '')} — {result['temperature_c']}°C"
    if "name" in result:
        return str(result["name"])[:120]
    return "تم"


def run_turn(session: Session, message: str) -> tuple[str, list[TraceEntry]]:
    """Run one user turn to a final text answer, mutating `session.history`."""
    text = (message or "").strip()
    if not text:
        raise BadRequest("empty message", user_message="اكتب رسالة أولًا.")
    if len(text) > config.MAX_MESSAGE_CHARS:
        raise BadRequest(
            "message too long",
            user_message=f"الرسالة طويلة جدًا (الحد {config.MAX_MESSAGE_CHARS} حرف).")

    contents = session.trimmed_history()
    contents.append({"role": "user", "parts": [{"text": text}]})
    declarations = declarations_for(session.corpus)
    trace: list[TraceEntry] = []

    for _ in range(config.MAX_AGENT_STEPS):
        candidate = chat_step(contents, declarations)
        parts = (candidate.get("content") or {}).get("parts") or []
        calls = [part["functionCall"] for part in parts if "functionCall" in part]

        if not calls:
            answer = "".join(p.get("text", "") for p in parts if "text" in p).strip()
            if not answer:
                # No tool call and no text: nothing to record, and echoing an
                # empty bubble would look like the app broke silently.
                raise AgentStalled("model returned neither text nor a tool call")
            contents.append({"role": "model", "parts": parts})
            session.history = contents
            session.message_count += 1
            return answer, trace

        # The model asked for tools. Record its request turn...
        contents.append({"role": "model", "parts": parts})

        # ...run every call, then feed all results back in ONE user turn.
        responses: list[dict[str, Any]] = []
        for call in calls:
            name = call.get("name", "")
            args = call.get("args", {}) or {}
            result = run_tool(name, args, session.corpus)
            trace.append({
                "tool": name,
                "args": args,
                "ok": not (isinstance(result, dict) and "error" in result),
                "summary": _summarize(result),
            })
            responses.append({
                "functionResponse": {
                    "name": name,
                    "response": result if isinstance(result, dict) else {"result": result},
                }
            })
        contents.append({"role": "user", "parts": responses})

    raise AgentStalled(f"no answer within {config.MAX_AGENT_STEPS} tool steps")
