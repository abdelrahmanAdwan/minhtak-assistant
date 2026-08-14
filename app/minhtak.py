"""Client for the live منحتك (minhtak) scholarship API.

Two capabilities the agent uses as tools:
  * search  -> POST /api/v1/recommendations (ranked matches for a profile)
  * details -> GET  /api/v1/scholarships/{id} (funding, deadline, official link)

The API is the SAME contract the production منحتك website talks to. Every
number it returns is verified data with a `last_verified_at` signature — this
client never fabricates or transforms it (currency/GPA math lives server-side).
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import MINHTAK_API_BASE, REQUEST_TIMEOUT


class MinhtakError(Exception):
    """The منحتك API was unreachable or returned an error the tool can't use."""


def _get(path: str, **kwargs: Any) -> Any:
    try:
        resp = httpx.get(
            f"{MINHTAK_API_BASE}{path}", timeout=REQUEST_TIMEOUT, **kwargs
        )
    except httpx.HTTPError as exc:
        raise MinhtakError(f"could not reach the منحتك API: {exc}") from exc
    return _json_or_raise(resp)


def _post(path: str, payload: dict[str, Any]) -> Any:
    try:
        resp = httpx.post(
            f"{MINHTAK_API_BASE}{path}", json=payload, timeout=REQUEST_TIMEOUT
        )
    except httpx.HTTPError as exc:
        raise MinhtakError(f"could not reach the منحتك API: {exc}") from exc
    return _json_or_raise(resp)


def _json_or_raise(resp: httpx.Response) -> Any:
    if resp.status_code >= 400:
        # Surface the API's own (often Arabic) error detail, not a stack trace.
        detail = ""
        try:
            detail = resp.json().get("detail", "")
        except ValueError:
            detail = resp.text[:200]
        raise MinhtakError(f"منحتك API returned {resp.status_code}: {detail}")
    try:
        return resp.json()
    except ValueError as exc:
        raise MinhtakError("منحتك API returned a non-JSON response") from exc


def search_scholarships(
    nationality: str,
    field: str | None = None,
    gpa: float | str | None = None,
    gpa_system: str | None = None,
    goals: str | None = None,
    include_competitive: bool = False,
    top_n: int = 5,
) -> dict[str, Any]:
    """Return ranked scholarship matches (guaranteed + optional competitive)."""
    payload: dict[str, Any] = {
        "nationality": nationality.upper(),
        "include_competitive": include_competitive,
        "top_n": max(1, min(int(top_n), 10)),
    }
    if field:
        payload["field"] = field
    if gpa is not None:
        payload["gpa"] = gpa
    if gpa_system:
        payload["gpa_system"] = gpa_system
    if goals:
        payload["goals"] = goals

    data = _post("/api/v1/recommendations", payload)
    return {
        "guaranteed": [_slim_match(m) for m in data.get("ranked", [])],
        "competitive": [_slim_match(m) for m in data.get("ranked_competitive", [])],
        "competitive_disclosure": data.get("competitive_disclosure"),
    }


def browse_catalogue(
    name: str | None = None,
    country_code: str | None = None,
    certainty: str | None = None,
) -> dict[str, Any]:
    """List/look up scholarships in the catalogue WITHOUT a student profile.

    This is the name-lookup path the ranked search does not cover: "is Chevening
    in your catalogue?", "what UK scholarships do you have?". Backed by
    GET /api/v1/catalogue (every active record: id, name, country, certainty,
    nearest deadline). Filtering is done here over the full list so a name match
    can never be hidden by a profile's ranking or the guaranteed-only default.
    """
    data = _get("/api/v1/catalogue")
    records = data.get("records", []) if isinstance(data, dict) else []

    needle = (name or "").strip().casefold()
    want_country = (country_code or "").strip().upper()
    want_certainty = (certainty or "").strip().casefold()

    matches = []
    for record in records:
        record_name = (record.get("name") or "")
        if needle and needle not in record_name.casefold():
            continue
        if want_country and (record.get("country_code") or "").upper() != want_country:
            continue
        if want_certainty and (record.get("funding_certainty") or "").casefold() != want_certainty:
            continue
        matches.append({
            "scholarship_id": record.get("id"),
            "name": record_name,
            "country_code": record.get("country_code"),
            "funding_certainty": record.get("funding_certainty"),
            "nearest_deadline_utc": record.get("nearest_deadline_utc"),
        })

    return {
        "total_in_catalogue": len(records),
        "match_count": len(matches),
        "matches": matches,
        "note": (
            "These are ALL active scholarships matching the filter, including "
            "'competitive' (funding-not-guaranteed) awards. Absence here means "
            "the catalogue truly does not contain it."
        ),
    }


def scholarship_details(scholarship_id: int) -> dict[str, Any]:
    """Full trust surface for one scholarship: funding, deadlines, official URL."""
    data = _get(f"/api/v1/scholarships/{int(scholarship_id)}")
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "provider": data.get("provider"),
        "university": data.get("university"),
        "country_code": data.get("country_code"),
        "city": data.get("city"),
        "funding_certainty": data.get("funding_certainty"),
        "duration_months": data.get("duration_months"),
        "funding": [
            {
                "component": f.get("component"),
                "period": f.get("period"),
                "amount_usd": f.get("amount_usd"),
                "original_amount": f.get("original_amount"),
                "original_currency": f.get("original_currency"),
                "is_full_coverage": f.get("is_full_coverage"),
            }
            for f in data.get("funding", [])
        ],
        "deadlines": [
            {
                "nationality_group": d.get("nationality_group"),
                "intake_year": d.get("intake_year"),
                "deadline_utc": d.get("deadline_utc"),
                "deadline_timezone": d.get("deadline_timezone"),
            }
            for d in data.get("deadlines", [])
        ],
        "language_requirements": data.get("language_requirements", []),
        "official_url": data.get("official_url"),
        "last_verified_at": data.get("last_verified_at"),
        "last_seen_unchanged_at": data.get("last_seen_unchanged_at"),
    }


def stats() -> dict[str, Any]:
    """Live catalogue counters (used by the demo header, not by the agent)."""
    return _get("/api/v1/stats")


def _slim_match(m: dict[str, Any]) -> dict[str, Any]:
    """Trim a recommendation to what the model needs to reason and cite.

    Includes the engine's own Arabic `summary` (the transparent "why") so the
    agent can quote a verified explanation instead of inventing one.
    """
    explanation = m.get("explanation") or {}
    summary = (explanation.get("summary") or {}).get("text")
    return {
        "scholarship_id": m.get("scholarship_id"),
        "name": m.get("name"),
        "country_code": m.get("country_code"),
        "funding_certainty": m.get("funding_certainty"),
        "match_percent": round(float(m.get("final", 0.0)) * 100),
        "qualification_percent": round(float(m.get("q", 0.0)) * 100),
        "preference_percent": round(float(m.get("p", 0.0)) * 100),
        "deadline_utc": m.get("deadline_utc"),
        "why_summary": summary,
    }
