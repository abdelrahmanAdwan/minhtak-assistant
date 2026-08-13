"""The assistant's toolbox: declarations (what the model sees) + dispatch.

Five tools. Four are stateless; the fifth searches the CURRENT session's
uploaded documents, which is why dispatch takes the session's corpus.

Two design rules worth stating:

1. **The document tool is declared only when a document exists.** Advertising a
   tool the session cannot serve invites the model to call it and then explain
   an error to the user -- a self-inflicted failure.
2. **A tool never raises into the agent loop.** Every failure comes back as
   `{"error": ...}` so the model can recover in-conversation (retry with a
   different city, tell the user the catalogue is down) instead of the whole
   request 500-ing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from . import minhtak
from .calculator import CalculatorError, calculate
from .errors import AssistantError
from .rag import DocumentCorpus
from .weather import WeatherError, get_weather

# --------------------------------------------------------------------------- #
# Declarations -- the OpenAPI-subset schemas Gemini uses to pick + fill a tool
# --------------------------------------------------------------------------- #
SCHOLARSHIP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_scholarships",
        "description": (
            "Search the live منحتك catalogue of fully-funded Master's "
            "scholarships for MENA students and return ranked matches. Use this "
            "whenever the user asks which scholarships fit them, or to find "
            "scholarships by nationality/field. Returns a match score, funding "
            "certainty, host country, deadline and a verified reason for each."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "nationality": {
                    "type": "STRING",
                    "description": "ISO 3166-1 alpha-2 country code, e.g. 'EG', 'PS', 'JO'.",
                },
                "field": {
                    "type": "STRING",
                    "description": (
                        "Canonical field code, e.g. 'electrical-eng', 'cs', 'ai', "
                        "'public-health'. Omit if the user did not state a field."
                    ),
                },
                "gpa": {"type": "NUMBER",
                        "description": "The student's GPA value, e.g. 3.4. Omit if unknown."},
                "gpa_system": {
                    "type": "STRING",
                    "description": (
                        "The GPA scale, e.g. 'US-4.0', 'DE-1to5', 'UK-percent', "
                        "'MENA-pct'. Required if gpa is given."
                    ),
                },
                "goals": {"type": "STRING",
                          "description": "The student's career goals in their own words (optional)."},
                "include_competitive": {
                    "type": "BOOLEAN",
                    "description": "Also return competitive (funding-not-guaranteed) awards.",
                },
                "top_n": {"type": "INTEGER",
                          "description": "How many matches to return per tier (1-10, default 5)."},
            },
            "required": ["nationality"],
        },
    },
    {
        "name": "get_scholarship_details",
        "description": (
            "Get the full verified details of ONE scholarship by its id: funding "
            "breakdown (USD amounts), all deadlines with days remaining, host "
            "city/university, language requirements and the official application "
            "link. Use after search_scholarships when the user asks about a "
            "specific award's money, deadline or where to apply."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "scholarship_id": {"type": "INTEGER",
                                   "description": "The scholarship_id from a search result."},
            },
            "required": ["scholarship_id"],
        },
    },
    {
        "name": "get_weather",
        "description": (
            "Get the current weather and conditions for a city — useful when a "
            "student wants to know the climate of a study destination (e.g. "
            "Berlin, Budapest, Abu Dhabi) before accepting an offer."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {
                    "type": "STRING",
                    "description": (
                        "City name in ENGLISH (the geocoder is English), e.g. "
                        "'Cologne' not 'كولونيا', 'Berlin', 'Abu Dhabi'."
                    ),
                }
            },
            "required": ["city"],
        },
    },
    {
        "name": "calculate",
        "description": (
            "Evaluate an arithmetic expression (only numbers and + - * / // % ** "
            "and parentheses). Use for grounded budget math, e.g. a monthly "
            "stipend minus rent, or a funding gap. Never use it for dates."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "expression": {"type": "STRING",
                               "description": "The arithmetic to evaluate, e.g. '1133.26 - 850'."},
            },
            "required": ["expression"],
        },
    },
]

DOCUMENT_TOOL: dict[str, Any] = {
    "name": "search_uploaded_documents",
    "description": (
        "Search the documents the user uploaded in THIS conversation (e.g. their "
        "CV, a scholarship call, an acceptance letter) and return the most "
        "relevant passages with their source file. Use this for ANY question "
        "about 'my CV', 'the file', 'the attached document', or to read the "
        "student's own background before recommending scholarships. Answer only "
        "from the passages returned; if they do not contain the answer, say so."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {
                "type": "STRING",
                "description": (
                    "What to look for, phrased as the user would, e.g. "
                    "'work experience', 'المعدل التراكمي', 'graduation year'."
                ),
            }
        },
        "required": ["query"],
    },
}


def declarations_for(corpus: Optional[DocumentCorpus]) -> list[dict[str, Any]]:
    """The tool list this session should advertise (see rule 1 in the module
    docstring)."""
    tools = list(SCHOLARSHIP_TOOLS)
    if corpus is not None and not corpus.is_empty:
        tools.append(DOCUMENT_TOOL)
    return tools


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #
def _tool_search(args: dict[str, Any]) -> dict[str, Any]:
    result = minhtak.search_scholarships(
        nationality=args["nationality"],
        field=args.get("field"),
        gpa=args.get("gpa"),
        gpa_system=args.get("gpa_system"),
        goals=args.get("goals"),
        include_competitive=bool(args.get("include_competitive", False)),
        top_n=int(args.get("top_n", 5)),
    )
    for tier in ("guaranteed", "competitive"):
        for match in result[tier]:
            match["days_until_deadline"] = _days_until(match.get("deadline_utc"))
    result["result_count"] = len(result["guaranteed"]) + len(result["competitive"])
    return result


def _tool_details(args: dict[str, Any]) -> dict[str, Any]:
    data = minhtak.scholarship_details(int(args["scholarship_id"]))
    for deadline in data.get("deadlines", []):
        deadline["days_until_deadline"] = _days_until(deadline.get("deadline_utc"))
    return data


def _tool_weather(args: dict[str, Any]) -> dict[str, Any]:
    return get_weather(args["city"])


def _tool_calculate(args: dict[str, Any]) -> dict[str, Any]:
    return calculate(args["expression"])


def _tool_documents(args: dict[str, Any], corpus: Optional[DocumentCorpus]
                    ) -> dict[str, Any]:
    if corpus is None or corpus.is_empty:
        return {"error": "no document has been uploaded in this conversation"}
    hits = corpus.retrieve(str(args.get("query", "")))
    if not hits:
        return {"passages": [], "note": "no relevant passage found in the documents"}
    return {
        "passages": [
            {"rank": index, "source": hit.source,
             "similarity": round(hit.score, 4), "text": hit.text}
            for index, hit in enumerate(hits, start=1)
        ],
        "documents": [doc["filename"] for doc in corpus.documents],
    }


_DISPATCH: dict[str, Callable[..., dict[str, Any]]] = {
    "search_scholarships": _tool_search,
    "get_scholarship_details": _tool_details,
    "get_weather": _tool_weather,
    "calculate": _tool_calculate,
}

# Exceptions translated into a clean {"error": ...} the model can react to.
_KNOWN_ERRORS = (minhtak.MinhtakError, WeatherError, CalculatorError,
                 AssistantError, KeyError, ValueError, TypeError)


def run_tool(name: str, args: dict[str, Any],
             corpus: Optional[DocumentCorpus] = None) -> dict[str, Any]:
    """Execute tool `name`; never raise into the agent loop."""
    try:
        if name == "search_uploaded_documents":
            return _tool_documents(args or {}, corpus)
        handler = _DISPATCH.get(name)
        if handler is None:
            return {"error": f"unknown tool {name!r}"}
        return handler(args or {})
    except _KNOWN_ERRORS as exc:
        return {"error": str(exc) or exc.__class__.__name__}


def _days_until(deadline_utc: str | None) -> int | None:
    """Whole days from now (UTC) until an ISO-8601 deadline; None if absent."""
    if not deadline_utc:
        return None
    try:
        moment = datetime.fromisoformat(deadline_utc.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (moment - datetime.now(timezone.utc)).days
