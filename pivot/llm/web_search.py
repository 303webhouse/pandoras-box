"""Brave Search integration for Pivot."""
import os
import logging
import httpx

logger = logging.getLogger(__name__)
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")


async def web_search(query: str, count: int = 5) -> str:
    """Search the web via Brave Search API. Returns formatted results."""
    if not BRAVE_API_KEY:
        return "[Web search disabled: no BRAVE_API_KEY]"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": BRAVE_API_KEY,
                },
                params={"q": query, "count": count, "freshness": "pd"},
            )
            if resp.status_code != 200:
                return f"[Search failed: HTTP {resp.status_code}]"
            results = resp.json().get("web", {}).get("results", [])
            if not results:
                return "[No results found]"
            out = []
            for r in results[:count]:
                title = r.get("title", "")
                desc = r.get("description", "")
                out.append(f"- {title}\n  {desc}")
            return "\n".join(out)
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return f"[Search error: {e}]"
