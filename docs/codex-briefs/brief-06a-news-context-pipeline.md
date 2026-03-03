# Brief 06A — News Context Pipeline for Trading Team Committee

**Priority:** HIGH — Committee is blind to macro/geopolitical events
**LLM cost impact:** ZERO additional LLM calls
**API cost:** $0 (Polygon News API included in Stocks Starter plan)
**Estimated build time:** 2–3 hours
**Agent target:** Codex / Sonnet (implementation)

---

## Problem

The Trading Team committee evaluates signals using technicals, bias factors, Twitter sentiment, whale volume, and playbook rules. But it has **zero awareness of breaking news or macro events**. When the U.S. starts a war with Iran and oil spikes 8%, the committee has no idea why energy tickers are moving. It evaluates BOIL, XLE, or defense stocks in a vacuum.

A human trader would never take a trade without knowing what is driving the market today. The committee must have the same context.

## Design Principle: Zero Additional LLM Calls

The 4 committee agents (TORO, URSA, TECHNICALS, PIVOT) are already LLM calls. They are smart enough to interpret raw headlines. **We do NOT add a separate LLM summarization step.** We fetch structured news data from the Polygon API, format it as a readable text block, and inject it into the context that all 4 agents already receive. The agents interpret the news as part of their existing analysis. Total additional LLM cost: $0.00.

---

## Architecture

```
Signal triggers committee run
  → committee_context.py calls fetch_news_context()
     → Check file cache: news_cache/market.json (30 min TTL)
       → HIT: use cached data
       → MISS: GET https://api.polygon.io/v2/reference/news (market-wide, limit 10, last 6h)
               → Cache to file → return
     → Check file cache: news_cache/ticker_{TICKER}.json (30 min TTL)
       → HIT: use cached data
       → MISS: GET https://api.polygon.io/v2/reference/news?ticker={TICKER} (limit 5, last 24h)
               → Cache to file → return
  → format_news_context() renders text block
  → Injected into format_signal_context() output
  → All 4 agents see it in their user message
```

No cron jobs. No background processes. News is fetched on-demand during committee runs, cached to prevent redundant API calls.

---

## New File: `committee_news.py`

**Location:** `/opt/openclaw/workspace/scripts/committee_news.py`
**Also committed to:** `backend/discord_bridge/committee_news.py` (repo source of truth)

```python
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
```

---

## Modified File: `committee_context.py`

### Change 1: Import committee_news

**FIND this exact line near top of file:**
```python
_log = logging.getLogger("committee_context")
```

**REPLACE with:**
```python
_log = logging.getLogger("committee_context")

# News context (Brief 06A)
try:
    from committee_news import fetch_news_context, format_news_context
    _HAS_NEWS = True
except ImportError:
    _HAS_NEWS = False
    _log.warning("committee_news not available — news context disabled")
```

### Change 2: Add Polygon API key helper

**FIND this exact line (the bias challenge function):**
```python
def get_bias_challenge_context(signal: dict, context: dict) -> str:
```

**INSERT BEFORE that line:**
```python
def _get_polygon_api_key() -> str | None:
    """Get Polygon API key from environment or OpenClaw config."""
    import os
    key = os.environ.get("POLYGON_API_KEY", "")
    if not key:
        try:
            cfg_path = Path("/home/openclaw/.openclaw/openclaw.json")
            if cfg_path.exists():
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                key = (cfg.get("env") or {}).get("POLYGON_API_KEY", "")
        except Exception:
            pass
    return key or None


```

### Change 3: Inject news into format_signal_context()

**FIND these exact lines inside `format_signal_context()`:**
```python
    # Inject Twitter sentiment context
    ticker = signal.get("ticker")
    twitter_ctx = _get_twitter_sentiment_context(ticker=ticker)
```

**INSERT BEFORE those 3 lines:**
```python
    # Inject market news context (Brief 06A)
    if _HAS_NEWS:
        _polygon_key = _get_polygon_api_key()
        if _polygon_key:
            try:
                news_data = fetch_news_context(api_key=_polygon_key, ticker=signal.get("ticker"))
                news_text = format_news_context(news_data)
                if news_text:
                    sections.append(news_text)
            except Exception as e:
                _log.warning("News context injection failed: %s", e)

```

---

## Modified: OpenClaw Config

**File:** `/home/openclaw/.openclaw/openclaw.json`

Add `POLYGON_API_KEY` to the `env` section, after `BRAVE_API_KEY`:

```json
"POLYGON_API_KEY": "<Nick provides this from polygon.io/dashboard>"
```

---

## Context Block Example

What agents will see when evaluating a signal during a geopolitical crisis:

```
## MARKET NEWS (latest 12 min ago)
- US launches strikes on Iranian nuclear facilities, oil surges 8% (Reuters) [CL, USO, XLE]
  The United States launched military strikes against Iranian nuclear sites early Sunday...
- Defense stocks rally as geopolitical tensions escalate (CNBC) [LMT, RTX, NOC, GD]
  Lockheed Martin and Raytheon shares surged in pre-market trading...
- Airlines plunge on fuel cost fears amid Iran conflict (Bloomberg) [DAL, UAL, LUV, AAL]
  Major airline stocks fell sharply as investors priced in higher jet fuel costs...
- Gold hits record high as investors flee to safety (MarketWatch) [GLD, GC]
  Spot gold surged past $2,800 per ounce...
- Treasury yields drop as flight-to-quality trade accelerates (WSJ) [TLT, IEF]
  The 10-year Treasury yield fell 15 basis points...

### NEWS SPECIFIC TO BOIL
- Natural gas futures spike 12% on Iran supply disruption fears (Reuters)
  Natural gas prices jumped as traders assessed the potential impact...
```

---

## Verification Steps

1. Add Polygon API key to OpenClaw config (edit openclaw.json on VPS)
2. Deploy committee_news.py to `/opt/openclaw/workspace/scripts/`
3. Test Polygon API directly: `curl "https://api.polygon.io/v2/reference/news?limit=3&apiKey=KEY"`
4. Test module standalone: `python3 -c "from committee_news import ..."`
5. Test integrated: wait for signal or manual trigger, check Discord embed
6. Verify cache: second run within 30 min should log "Using cached market news"

---

## Files Changed Summary

| File | Action | Lines |
|------|--------|-------|
| `scripts/committee_news.py` | **NEW** | ~160 |
| `scripts/committee_context.py` | MODIFY | ~25 added |
| `openclaw.json` | MODIFY | 1 line |

---

## What This Does NOT Do

- No LLM summarization of news (agents interpret raw headlines themselves)
- No cron job (news fetched on-demand during committee runs only)
- No Pivot interactive news (Pivot already has Brave search for conversation)
- No position sync fix (separate issue, Brief 06B)
- No sentiment scoring (raw titles + summaries only)

## Dependencies

- Polygon.io Stocks Starter subscription (Nick already has this)
- Polygon API key (Nick adds to OpenClaw config)
- No new Python packages (uses stdlib `urllib.request` + `json`)
