#!/usr/bin/env python3
"""
Hermes Flash — Pivot Intelligence Layer (VPS)

Receives velocity breach triggers from Railway, launches a timed scrape burst
(Twitter via bird CLI + RSS feeds), feeds content into Haiku for catalyst
identification, and pushes results back to Railway via POST /api/hermes/analysis.

Deploy: SCP to /opt/openclaw/workspace/scripts/hermes_trigger.py
Run:    systemd service (hermes-trigger.service) — standalone FastAPI on port 8000
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
import uvicorn

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("hermes_pivot")


# ── Config ───────────────────────────────────────────────────────────────────

def _load_openclaw_env() -> dict:
    config_path = "/home/openclaw/.openclaw/openclaw.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        env = data.get("env")
        return env if isinstance(env, dict) else {}
    except Exception:
        return {}


_CONFIG_ENV = _load_openclaw_env()

HERMES_API_KEY = (
    os.environ.get("HERMES_API_KEY")
    or _CONFIG_ENV.get("HERMES_API_KEY")
    or ""
)
ANTHROPIC_API_KEY = (
    os.environ.get("ANTHROPIC_API_KEY")
    or _CONFIG_ENV.get("ANTHROPIC_API_KEY")
    or ""
)
PANDORA_API_URL = (
    os.environ.get("PANDORA_API_URL")
    or _CONFIG_ENV.get("PANDORA_API_URL")
    or "https://pandoras-box-production.up.railway.app/api"
).rstrip("/")
PIVOT_API_KEY = (
    os.environ.get("PIVOT_API_KEY")
    or _CONFIG_ENV.get("PIVOT_API_KEY")
    or ""
)

# Bird CLI for Twitter scraping (same as pivot2_twitter.py)
BIRD_BIN = os.path.expanduser("~/.local/bin/bird")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN") or _CONFIG_ENV.get("AUTH_TOKEN", "")
CT0 = os.environ.get("CT0") or _CONFIG_ENV.get("CT0", "")

# Track active scrape bursts to prevent overlapping
active_bursts: dict[str, bool] = {}

# ── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(title="Hermes Trigger", docs_url=None, redoc_url=None)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "hermes-trigger"}


@app.post("/api/hermes/trigger")
async def hermes_trigger(request: Request, background_tasks: BackgroundTasks):
    """
    Receives trigger from Railway when a velocity breach is detected.
    Launches a background scrape burst — returns immediately.
    """
    api_key = request.headers.get("X-API-Key")
    if not HERMES_API_KEY or api_key != HERMES_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    payload = await request.json()
    event_id = payload.get("event_id")
    tier = payload.get("tier", 1)
    trigger_ticker = payload.get("trigger_ticker", "UNKNOWN")
    velocity_pct = payload.get("velocity_pct", 0)
    direction = payload.get("direction", "unknown")
    search_terms = payload.get("search_terms", [])
    scrape_interval = payload.get("scrape_interval_seconds", 120)
    scrape_duration = payload.get("scrape_duration_minutes", 15)

    logger.info("HERMES TRIGGER: %s %s %.1f%% | Tier %d | Event %s",
                trigger_ticker, direction, velocity_pct, tier, event_id)

    if event_id in active_bursts:
        logger.info("HERMES: Burst already active for event %s, skipping", event_id)
        return {"status": "already_active", "event_id": event_id}

    active_bursts[event_id] = True
    background_tasks.add_task(
        run_scrape_burst,
        event_id=event_id,
        tier=tier,
        trigger_ticker=trigger_ticker,
        velocity_pct=velocity_pct,
        direction=direction,
        search_terms=search_terms,
        scrape_interval=scrape_interval,
        scrape_duration=scrape_duration,
    )

    return {"status": "burst_launched", "event_id": event_id}


# ── Scrape Burst Engine ──────────────────────────────────────────────────────

async def run_scrape_burst(
    event_id: str,
    tier: int,
    trigger_ticker: str,
    velocity_pct: float,
    direction: str,
    search_terms: list,
    scrape_interval: int = 120,
    scrape_duration: int = 15,
):
    """
    Runs the full scrape burst cycle:
    1. Scrape every scrape_interval seconds for scrape_duration minutes
    2. After each pass, accumulate results
    3. After pass 2+ (or pass 1 for Tier 2), run LLM analysis
    4. Push results back to Railway via POST /api/hermes/analysis
    """
    try:
        total_passes = max(1, scrape_duration * 60 // scrape_interval)
        all_scraped_content: list[dict] = []
        best_analysis: Optional[dict] = None

        logger.info("HERMES BURST START: %d passes, %ds intervals for event %s",
                     total_passes, scrape_interval, event_id)

        for pass_num in range(1, total_passes + 1):
            logger.info("HERMES BURST pass %d/%d for %s",
                         pass_num, total_passes, trigger_ticker)

            scraped = await scrape_sources(search_terms, tier)
            if scraped:
                all_scraped_content.extend(scraped)

            should_analyze = (
                pass_num == total_passes
                or (pass_num >= 2 and len(all_scraped_content) >= 5)
                or (tier >= 2 and pass_num == 1 and len(all_scraped_content) >= 2)
            )

            if should_analyze and all_scraped_content:
                analysis = await analyze_with_haiku(
                    scraped_content=all_scraped_content,
                    trigger_ticker=trigger_ticker,
                    velocity_pct=velocity_pct,
                    direction=direction,
                    tier=tier,
                )
                if analysis:
                    best_analysis = analysis
                    await push_to_railway(event_id, analysis)
                    logger.info("HERMES ANALYSIS (pass %d): %s",
                                 pass_num, analysis.get("headline_summary", "N/A"))

                    if analysis.get("confidence", 0) >= 0.85 and pass_num >= 2:
                        logger.info("HERMES: High confidence (%.2f) — ending burst early",
                                     analysis["confidence"])
                        break

            if pass_num < total_passes:
                await asyncio.sleep(scrape_interval)

        if not best_analysis and all_scraped_content:
            analysis = await analyze_with_haiku(
                scraped_content=all_scraped_content,
                trigger_ticker=trigger_ticker,
                velocity_pct=velocity_pct,
                direction=direction,
                tier=tier,
            )
            if analysis:
                await push_to_railway(event_id, analysis)

        if not all_scraped_content:
            await push_to_railway(event_id, {
                "headline_summary": f"{trigger_ticker} velocity breach — no headline catalyst found via scrape",
                "catalyst_category": "unknown",
                "confidence": 0.0,
                "full_analysis": "Pivot scrape burst returned no relevant content. Move may be technical/flow-driven.",
            })

        logger.info("HERMES BURST COMPLETE for event %s", event_id)

    except Exception as e:
        logger.error("HERMES BURST ERROR for event %s: %s", event_id, e, exc_info=True)
        await push_to_railway(event_id, {
            "headline_summary": "Pivot analysis failed — check VPS logs",
            "catalyst_category": "error",
            "confidence": 0.0,
            "full_analysis": str(e),
        })
    finally:
        active_bursts.pop(event_id, None)


# ── Scraping Layer ───────────────────────────────────────────────────────────

async def scrape_sources(search_terms: list, tier: int) -> list[dict]:
    """Master scrape: Twitter (bird CLI) + RSS feeds + news sites for Tier 2."""
    results: list[dict] = []

    twitter_results = await scrape_twitter(search_terms)
    if twitter_results:
        results.extend(twitter_results)

    rss_results = await scrape_rss_feeds(search_terms)
    if rss_results:
        results.extend(rss_results)

    if tier >= 2:
        news_results = await scrape_news_sites(search_terms)
        if news_results:
            results.extend(news_results)

    # Deduplicate by first 80 chars
    seen: set[str] = set()
    deduped: list[dict] = []
    for r in results:
        key = r.get("text", "")[:80].lower().strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(r)

    return deduped


async def scrape_twitter(search_terms: list) -> list[dict]:
    """
    Twitter/X scrape via bird CLI (same tool used by pivot2_twitter.py).
    Searches for recent tweets matching search terms from high-signal accounts.
    """
    results: list[dict] = []
    if not os.path.isfile(BIRD_BIN):
        logger.warning("HERMES: bird binary not found at %s — skipping Twitter", BIRD_BIN)
        return results

    env = os.environ.copy()
    env["AUTH_TOKEN"] = AUTH_TOKEN
    env["CT0"] = CT0

    if not AUTH_TOKEN or not CT0:
        logger.warning("HERMES: AUTH_TOKEN/CT0 not set — skipping Twitter")
        return results

    # Fetch home timeline (catches most breaking content)
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            [BIRD_BIN, "--plain", "home", "-n", "100", "--json"],
            capture_output=True, text=True, timeout=30, env=env,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            tweets = json.loads(proc.stdout)
            term_pattern = "|".join(re.escape(t.lower()) for t in search_terms if len(t) > 2)
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=20)

            for t in tweets:
                text = t.get("text") or t.get("fullText") or ""
                if not text:
                    continue
                # Filter by recency
                raw_ts = t.get("timestamp") or t.get("createdAt") or ""
                ts = _parse_tweet_ts(raw_ts)
                if ts and ts < cutoff:
                    continue
                # Filter by search term match
                if term_pattern and not re.search(term_pattern, text.lower()):
                    continue
                author = (t.get("author") or {}).get("username", "unknown")
                engagement = (t.get("likes") or 0) + (t.get("retweets") or 0)
                results.append({
                    "source": "twitter",
                    "text": text[:500],
                    "author": f"@{author}",
                    "timestamp": raw_ts,
                    "url": f"https://x.com/{author}",
                    "engagement": engagement,
                })
    except Exception as e:
        logger.warning("HERMES Twitter home timeline error: %s", e)

    # Also search for specific high-signal terms (top 3)
    for term in search_terms[:3]:
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                [BIRD_BIN, "--plain", "search", term, "-n", "15", "--json"],
                capture_output=True, text=True, timeout=20, env=env,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                tweets = json.loads(proc.stdout)
                for t in tweets:
                    text = t.get("text") or t.get("fullText") or ""
                    if not text:
                        continue
                    author = (t.get("author") or {}).get("username", "unknown")
                    engagement = (t.get("likes") or 0) + (t.get("retweets") or 0)
                    results.append({
                        "source": "twitter",
                        "text": text[:500],
                        "author": f"@{author}",
                        "timestamp": (t.get("timestamp") or t.get("createdAt") or ""),
                        "url": f"https://x.com/{author}",
                        "engagement": engagement,
                    })
        except Exception as e:
            logger.debug("HERMES Twitter search '%s' error: %s", term, e)

    # Sort by engagement, return top 30
    results.sort(key=lambda x: x.get("engagement", 0), reverse=True)
    return results[:30]


def _parse_tweet_ts(raw_ts: str) -> Optional[datetime]:
    for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw_ts, fmt)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
    except Exception:
        return None


async def scrape_rss_feeds(search_terms: list) -> list[dict]:
    """Poll RSS feeds from major financial news outlets for recent matching items."""
    results: list[dict] = []

    rss_feeds = [
        {"name": "Reuters Business", "url": "https://feeds.reuters.com/reuters/businessNews"},
        {"name": "Reuters Markets", "url": "https://feeds.reuters.com/reuters/marketsNews"},
        {"name": "CNBC Top News", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"},
        {"name": "CNBC World", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362"},
        {"name": "AP News", "url": "https://rsshub.app/apnews/topics/business"},
        {"name": "MarketWatch", "url": "https://feeds.marketwatch.com/marketwatch/topstories"},
        {"name": "WSJ Markets", "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"},
        {"name": "ZeroHedge", "url": "https://feeds.feedburner.com/zerohedge/feed"},
    ]

    term_pattern = "|".join(re.escape(t.lower()) for t in search_terms if len(t) > 2)

    async with httpx.AsyncClient(timeout=10.0) as client:
        for feed in rss_feeds:
            try:
                resp = await client.get(feed["url"], follow_redirects=True)
                if resp.status_code != 200:
                    continue

                items = re.findall(
                    r'<item[^>]*>(.*?)</item>',
                    resp.text,
                    re.DOTALL | re.IGNORECASE,
                )

                for item_xml in items[:10]:
                    title = _extract_xml_field(item_xml, "title")
                    description = _extract_xml_field(item_xml, "description")
                    link = _extract_xml_field(item_xml, "link")
                    pub_date = _extract_xml_field(item_xml, "pubDate")

                    if pub_date and not _is_recent(pub_date, minutes=20):
                        continue

                    combined_text = f"{title} {description}".lower()
                    if term_pattern and re.search(term_pattern, combined_text):
                        results.append({
                            "source": f"rss:{feed['name']}",
                            "text": f"{title}. {description[:300]}",
                            "author": feed["name"],
                            "timestamp": pub_date or "",
                            "url": link or "",
                        })

            except Exception as e:
                logger.debug("HERMES RSS feed %s error: %s", feed["name"], e)
                continue

    return results


async def scrape_news_sites(search_terms: list) -> list[dict]:
    """Direct scrape of financial news sites for Tier 2 events."""
    results: list[dict] = []

    news_urls = [
        "https://www.cnbc.com/world/?region=world",
        "https://www.reuters.com/markets/",
        "https://finance.yahoo.com/",
    ]

    term_pattern = "|".join(re.escape(t.lower()) for t in search_terms if len(t) > 2)

    async with httpx.AsyncClient(timeout=10.0) as client:
        for url in news_urls:
            try:
                resp = await client.get(url, follow_redirects=True, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; PandorasBox/1.0)"
                })
                if resp.status_code != 200:
                    continue

                clean = re.sub(r'<[^>]+>', ' ', resp.text)
                clean = re.sub(r'\s+', ' ', clean)

                if term_pattern:
                    matches = re.finditer(term_pattern, clean.lower())
                    for match in list(matches)[:3]:
                        start = max(0, match.start() - 100)
                        end = min(len(clean), match.end() + 200)
                        snippet = clean[start:end].strip()
                        results.append({
                            "source": f"web:{url.split('/')[2]}",
                            "text": snippet,
                            "author": url.split('/')[2],
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "url": url,
                        })

            except Exception as e:
                logger.debug("HERMES news scrape %s error: %s", url, e)
                continue

    return results


# ── XML/RSS Helpers ──────────────────────────────────────────────────────────

def _extract_xml_field(xml_str: str, field: str) -> str:
    match = re.search(
        rf'<{field}[^>]*>(.*?)</{field}>',
        xml_str,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        content = match.group(1).strip()
        cdata_match = re.search(r'<!\[CDATA\[(.*?)\]\]>', content, re.DOTALL)
        if cdata_match:
            content = cdata_match.group(1)
        content = re.sub(r'<[^>]+>', '', content)
        return content.strip()
    return ""


def _is_recent(pub_date_str: str, minutes: int = 20) -> bool:
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(pub_date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return dt >= cutoff
    except Exception:
        return True  # If we can't parse the date, include it


# ── LLM Analysis ─────────────────────────────────────────────────────────────

async def analyze_with_haiku(
    scraped_content: list[dict],
    trigger_ticker: str,
    velocity_pct: float,
    direction: str,
    tier: int,
) -> Optional[dict]:
    """Feed scraped content into Haiku for catalyst identification."""
    if not ANTHROPIC_API_KEY:
        logger.error("HERMES: No ANTHROPIC_API_KEY — cannot run analysis")
        return None

    sorted_content = sorted(
        scraped_content,
        key=lambda x: x.get("engagement", 0),
        reverse=True,
    )[:25]

    content_digest = "\n\n".join([
        f"[{item['source']}] {item.get('author', 'Unknown')} ({item.get('timestamp', 'recent')}):\n{item['text'][:400]}"
        for item in sorted_content
    ])

    direction_word = "rallying" if direction == "up" else "selling off"
    sign = "+" if direction == "up" else ""
    correlated_note = (
        "This is a CORRELATED event — multiple related tickers moved simultaneously."
        if tier >= 2 else "This is a single-ticker event."
    )

    prompt = f"""You are a real-time market intelligence analyst. A velocity breach was just detected:

**{trigger_ticker} moved {sign}{velocity_pct}% in ~30 minutes ({direction_word})**
{correlated_note}

Below is scraped content from Twitter and news sources captured in the minutes following this move. Your job is to identify the most likely catalyst.

=== SCRAPED CONTENT ===
{content_digest}
=== END CONTENT ===

Respond in this exact JSON format (no markdown, no backticks, just raw JSON):
{{
    "headline_summary": "One sentence (max 120 chars) describing the catalyst — this appears in a dashboard banner, be concise and specific",
    "catalyst_category": "one of: geopolitical, credit_event, fed_macro, earnings, technical_flow, sector_rotation, unknown",
    "confidence": 0.0 to 1.0,
    "full_analysis": "2-3 sentence explanation of what happened and why it moved the market",
    "key_sources": ["list of 1-3 most credible sources that confirm the catalyst"],
    "thesis_impact": "One sentence: how does this affect the bearish Iran/Hormuz/credit thesis? Is this noise or signal?"
}}

Rules:
- If the content clearly explains the move, confidence should be 0.7+
- If content is mixed/conflicting, confidence should be 0.3-0.6
- If nothing explains the move, say so and set category to "unknown" with confidence < 0.3
- "thesis_impact" is critical — Nick holds bearish positions and needs to know if this changes anything
- The headline_summary will be displayed on a trading dashboard — make it precise, not clickbait"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )

            if resp.status_code != 200:
                logger.error("HERMES Haiku API error: %d %s", resp.status_code, resp.text[:200])
                return None

            data = resp.json()
            response_text = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    response_text += block.get("text", "")

            clean = response_text.strip()
            clean = re.sub(r'^```json\s*', '', clean)
            clean = re.sub(r'\s*```$', '', clean)

            analysis = json.loads(clean)

            if "headline_summary" not in analysis or "catalyst_category" not in analysis:
                logger.warning("HERMES: Haiku response missing required fields: %s", clean[:200])
                return None

            return analysis

    except json.JSONDecodeError as e:
        logger.error("HERMES: Failed to parse Haiku response as JSON: %s", e)
        return None
    except Exception as e:
        logger.error("HERMES Haiku analysis error: %s", e, exc_info=True)
        return None


# ── Push to Railway (NOT Supabase) ───────────────────────────────────────────

async def push_to_railway(event_id: str, analysis: dict):
    """
    Push Pivot analysis back to Railway app, which writes to Postgres.
    Uses POST /api/hermes/analysis — same auth pattern as committee bridge.
    """
    if not PANDORA_API_URL or not PIVOT_API_KEY:
        logger.error("HERMES: PANDORA_API_URL or PIVOT_API_KEY not set — cannot push results")
        return

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{PANDORA_API_URL}/hermes/analysis",
                headers={
                    "X-API-Key": PIVOT_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "event_id": event_id,
                    "analysis": analysis,
                },
            )
            if resp.status_code not in [200, 201]:
                logger.error("HERMES push to Railway failed: %d %s",
                             resp.status_code, resp.text[:200])
            else:
                logger.info("HERMES: Pushed analysis to Railway for event %s: %s",
                            event_id, analysis.get("headline_summary", "")[:80])

    except Exception as e:
        logger.error("HERMES Railway push error: %s", e)


# ── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
