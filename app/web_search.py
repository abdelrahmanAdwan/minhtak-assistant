"""Web-search tool — real results from DuckDuckGo (free, no API key).

Gives the assistant a general-purpose search engine for questions that fall
OUTSIDE the منحتك catalogue: a university's ranking, a country's visa page, a
language-exam date, "what is a Schengen visa", and so on. It complements — it
does not replace — the منحتك tools: verified scholarship facts (amounts,
deadlines, links) still come only from search_scholarships / browse_catalogue /
get_scholarship_details, never from the open web.

Two DuckDuckGo surfaces are used, both keyless:

  * the Instant Answer API (JSON) — a direct abstract/definition when DDG has
    one (e.g. "capital of Germany");
  * the HTML endpoint — the organic result list (title, url, snippet), parsed
    with the standard library (no scraping SDK, no bs4).

Anything unreachable degrades to a typed WebSearchError, which the tool layer
turns into a structured `{"error": ...}` — never a fabricated result.
"""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from .config import (
    DDG_HTML_BASE,
    DDG_INSTANT_BASE,
    REQUEST_TIMEOUT,
    WEB_SEARCH_MAX_RESULTS,
)

# DuckDuckGo serves an empty/challenge page to clients with no browser-like
# User-Agent, so we send a realistic one. This is a normal, unauthenticated
# search request — no key, no login, nothing account-bound.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

_RESULT_LINK = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.S
)
_RESULT_SNIPPET = re.compile(
    r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', re.S
)


class WebSearchError(Exception):
    """DuckDuckGo was unreachable or returned an unusable response."""


def web_search(query: str, max_results: int = WEB_SEARCH_MAX_RESULTS) -> dict[str, Any]:
    """Search the web via DuckDuckGo and return an instant answer (if any) plus
    the top organic results. Raises WebSearchError on a transport failure."""
    cleaned = (query or "").strip()
    if not cleaned:
        raise WebSearchError("no search query was provided")
    limit = max(1, min(int(max_results or WEB_SEARCH_MAX_RESULTS), 10))

    instant = _instant_answer(cleaned)
    results = _organic_results(cleaned, limit)

    if not results and not instant:
        return {
            "query": cleaned,
            "instant_answer": None,
            "results": [],
            "result_count": 0,
            "note": "DuckDuckGo returned no results for this query.",
        }
    return {
        "query": cleaned,
        "instant_answer": instant,
        "results": results,
        "result_count": len(results),
    }


def _instant_answer(query: str) -> dict[str, Any] | None:
    """DuckDuckGo Instant Answer API — a direct abstract/definition when one
    exists. Returns None (not an error) when DDG has no instant answer."""
    try:
        resp = httpx.get(
            DDG_INSTANT_BASE,
            params={
                "q": query,
                "format": "json",
                "no_html": 1,
                "no_redirect": 1,
                "skip_disambig": 1,
            },
            headers=_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        raise WebSearchError(f"DuckDuckGo instant-answer unreachable: {exc}") from exc
    except ValueError:
        return None  # a non-JSON body here is not fatal — organic search still runs

    text = (data.get("AbstractText") or data.get("Answer") or "").strip()
    if not text:
        return None
    return {
        "heading": (data.get("Heading") or "").strip() or None,
        "text": text,
        "source": (data.get("AbstractSource") or "").strip() or None,
        "url": (data.get("AbstractURL") or "").strip() or None,
    }


def _organic_results(query: str, limit: int) -> list[dict[str, Any]]:
    """The DuckDuckGo HTML result list, parsed into (title, url, snippet)."""
    try:
        resp = httpx.post(
            DDG_HTML_BASE,
            data={"q": query, "kl": "wt-wt"},
            headers=_HEADERS,
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()
        body = resp.text
    except httpx.HTTPError as exc:
        raise WebSearchError(f"DuckDuckGo search unreachable: {exc}") from exc

    links = _RESULT_LINK.findall(body)
    snippets = _RESULT_SNIPPET.findall(body)

    results: list[dict[str, Any]] = []
    for index, (href, title_html) in enumerate(links[:limit]):
        snippet = _strip(snippets[index]) if index < len(snippets) else ""
        results.append(
            {
                "title": _strip(title_html),
                "url": _clean_url(href),
                "snippet": snippet,
            }
        )
    return results


def _clean_url(href: str) -> str:
    """DDG wraps result links as //duckduckgo.com/l/?uddg=<encoded-target>.
    Unwrap it so the assistant (and the user) get the real destination URL."""
    if href.startswith("//"):
        href = "https:" + href
    if "duckduckgo.com/l/" in href:
        params = parse_qs(urlparse(href).query)
        target = params.get("uddg")
        if target:
            return unquote(target[0])
    return href


def _strip(fragment: str) -> str:
    """HTML fragment -> clean text (drop tags, unescape entities)."""
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()
