"""
Committee News Context (Brief 06A)

Fetches market-wide + ticker-specific news from Polygon.io.
Injected into committee context for all 4 agents.
Zero additional LLM calls — agents interpret raw headlines.
File-based cache (30 min TTL) to avoid redundant API calls.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

_log = logging.getLogger("committee_news")

# —— Constants ——

POLYGON_NEWS_URL = "https://api.polygon.io/v2/reference/news"
NEWS_CACHE_DIR = Path("/opt/openclaw/workspace/data/news_cache")
CACHE_TTL_SEC = 1800  # 30 minutes
MARKET_NEWS_LIMIT = 10
MARKET_NEWS_LOOKBACK_HOURS = 6
TICKER_NEWS_LIMIT = 5
TICKER_NEWS_LOOKBACK_HOURS = 24


# —— File Cache ——

def _read_cache(cache_key: str) -> list[dict] | None:
    """Read cached news from file. Returns None if expired or missing."""
    cache_file = NEWS_CACHE_DIR / f"{cache_key}.json"
    try:
        if not cache_file.exists():
            return None
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        if time.time() - data.get("_cached_at", 0) > CACHE_TTL_SEC:
            return None
        return data.get("articles", [])
    except Exception:
        return None


def _write_cache(cache_key: str, articles: list[dict]):
    """Write news articles to file cache."""
    try:
        NEWS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"_cached_at": time.time(), "articles": articles}
        cache_file = NEWS_CACHE_DIR / f"{cache_key}.json"
        cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as e:
        _log.warning("Failed to cache news for %s: %s", cache_key, e)


# —— Polygon API ——

def _fetch_polygon_news(api_key: str, ticker: str | None = None,
                        limit: int = 10, lookback_hours: int = 6) -> list[dict]:
    """
    Fetch news from Polygon.io REST API.
    Returns list of simplified article dicts.
    Never raises — returns empty list on failure.
    """
    if not api_key:
        _log.warning("No POLYGON_API_KEY configured — skipping news fetch")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {
        "limit": str(limit),
        "order": "desc",
        "sort": "published_utc",
        "published_utc.gte": cutoff_str,
        "apiKey": api_key,
    }
    if ticker:
        params["ticker"] = ticker.upper()

    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{POLYGON_NEWS_URL}?{query_string}"

    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "PandorasBox/1.0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        articles = []
        for item in data.get("results", []):
            articles.append({
                "title": item.get("title", ""),
                "summary": (item.get("description") or "")[:200],
                "publisher": (item.get("publisher") or {}).get("name", ""),
                "published": item.get("published_utc", ""),
                "tickers": item.get("tickers", []),
            })
        _log.info("Fetched %d news articles (ticker=%s)",
                  len(articles), ticker or "market-wide")
        return articles

    except Exception as e:
        _log.warning("Polygon news fetch failed (ticker=%s): %s", ticker, e)
        return []


# —— Public API ——

def fetch_news_context(api_key: str, ticker: str | None = None) -> dict:
    """
    Fetch market-wide + ticker-specific news.
    Returns dict with 'market' and 'ticker' lists of article dicts.
    Uses file cache (30 min TTL) to avoid redundant API calls.
    """
    result = {"market": [], "ticker": []}

    # Market-wide news
    cached = _read_cache("market")
    if cached is not None:
        result["market"] = cached
        _log.info("Using cached market news (%d articles)", len(cached))
    else:
        articles = _fetch_polygon_news(
            api_key, ticker=None,
            limit=MARKET_NEWS_LIMIT,
            lookback_hours=MARKET_NEWS_LOOKBACK_HOURS,
        )
        _write_cache("market", articles)
        result["market"] = articles

    # Ticker-specific news
    if ticker:
        ticker_upper = ticker.upper()
        cache_key = f"ticker_{ticker_upper}"
        cached = _read_cache(cache_key)
        if cached is not None:
            result["ticker"] = cached
            _log.info("Using cached %s news (%d articles)",
                      ticker_upper, len(cached))
        else:
            articles = _fetch_polygon_news(
                api_key, ticker=ticker_upper,
                limit=TICKER_NEWS_LIMIT,
                lookback_hours=TICKER_NEWS_LOOKBACK_HOURS,
            )
            _write_cache(cache_key, articles)
            result["ticker"] = articles

    return result


def format_news_context(news: dict) -> str:
    """
    Render news dict into a context block for LLM agents.
    Returns empty string if no news available.
    """
    market = news.get("market", [])
    ticker_news = news.get("ticker", [])

    if not market and not ticker_news:
        return ""

    sections = ["## MARKET NEWS"]

    if market:
        # Calculate age of freshest article for staleness indicator
        try:
            newest = market[0].get("published", "")
            pub_dt = datetime.fromisoformat(newest.replace("Z", "+00:00"))
            age_min = int((datetime.now(timezone.utc) - pub_dt).total_seconds() / 60)
            sections[0] += f" (latest {age_min} min ago)"
        except Exception:
            pass

        for art in market:
            pub = art.get("publisher", "")
            title = art.get("title", "")
            summary = art.get("summary", "")
            tickers = art.get("tickers", [])
            ticker_str = f" [{', '.join(tickers[:5])}]" if tickers else ""
            line = f"- {title}"
            if pub:
                line += f" ({pub})"
            if ticker_str:
                line += ticker_str
            if summary:
                line += f"\n  {summary}"
            sections.append(line)

    if ticker_news:
        ticker_name = ""
        for art in ticker_news:
            tickers = art.get("tickers", [])
            if tickers:
                ticker_name = tickers[0]
                break
        sections.append(f"\n### NEWS SPECIFIC TO {ticker_name or 'TICKER'}")
        for art in ticker_news:
            pub = art.get("publisher", "")
            title = art.get("title", "")
            summary = art.get("summary", "")
            line = f"- {title}"
            if pub:
                line += f" ({pub})"
            if summary:
                line += f"\n  {summary}"
            sections.append(line)

    return "\n".join(sections)
