# BRIEF: Hermes Flash — Pivot Intelligence Layer
## Priority: P0.5 | System: VPS (188.245.250.2) at /opt/openclaw
## Date: 2026-03-31
## Depends on: Brief 1 (Hermes Flash Core) deployed on Railway

---

## CONTEXT FOR CLAUDE CODE

This is the "brain" layer of Hermes Flash. Brief 1 handles detection (TradingView spots a velocity breach) and plumbing (Railway receives it, stores it, triggers the VPS). This brief handles the **intelligence**: when Pivot gets triggered, it scrapes Twitter/X for breaking context, runs an LLM analysis to identify the catalyst, and pushes the result back to Supabase so the Agora banner can display WHY the market just moved.

**The real-time chain:**
TV alert → Railway webhook → Railway pings VPS trigger endpoint → **THIS BRIEF STARTS HERE** → VPS scrapes Twitter every 2 min for 15 min → each batch goes through Haiku → best analysis is pushed to `catalyst_events` table → Agora banner updates from "Pivot analyzing..." to the actual headline

**VPS environment:**
- Server: `188.245.250.2`
- App location: `/opt/openclaw`
- Existing framework: FastAPI (Pivot II / OpenClaw)
- Python environment: whatever is already running the committee pipeline
- LLM: Direct Anthropic API (Haiku for analysis). **NOT** OpenRouter, **NOT** Gemini.
- Cron: existing cron runs every 3 min, 13:00–20:00 UTC weekdays for committee pipeline

**PREREQUISITE: Twitter/X Scraper Status**
Before building, check the current state of the Twitter scraper on this VPS:
- Look for existing scrape scripts in `/opt/openclaw` (grep for "twitter", "tweet", "scrape", "nitter", "x.com")
- Check if there's a working scraper that just needs to be wired up, or if we need to build one from scratch
- If no scraper exists, this brief includes a fallback architecture using RSS feeds + web scraping of news sites

---

## STEP 1: Hermes Trigger Endpoint

Replace the stub from Brief 1 with the full implementation. This endpoint receives the trigger from Railway and kicks off the scrape burst.

**File:** `/opt/openclaw/hermes_trigger.py`

```python
# === HERMES FLASH — Pivot Intelligence Layer ===
# Receives velocity breach triggers from Railway.
# Launches a timed scrape burst, analyzes results via Haiku,
# and pushes catalyst intelligence back to Supabase.

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks

logger = logging.getLogger("hermes_pivot")
router = APIRouter()

# === CONFIG ===
HERMES_API_KEY = os.environ.get("HERMES_API_KEY", "REPLACE_WITH_SHARED_SECRET")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")  # Already set for committee pipeline
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")  # Service key for direct DB writes

# Track active scrape bursts to prevent overlapping
active_bursts = {}


@router.post("/api/hermes/trigger")
async def hermes_trigger(request: Request, background_tasks: BackgroundTasks):
    """
    Receives trigger from Railway when a velocity breach is detected.
    Launches a background scrape burst — returns immediately so Railway doesn't timeout.
    """
    # Auth check
    api_key = request.headers.get("X-API-Key")
    if api_key != HERMES_API_KEY:
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

    logger.info(f"HERMES TRIGGER: {trigger_ticker} {direction} {velocity_pct}% | Tier {tier} | Event {event_id}")

    # Prevent duplicate bursts for same event
    if event_id in active_bursts:
        logger.info(f"HERMES: Burst already active for event {event_id}, skipping")
        return {"status": "already_active", "event_id": event_id}

    # Launch scrape burst in background
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
        scrape_duration=scrape_duration
    )

    return {"status": "burst_launched", "event_id": event_id}


# === SCRAPE BURST ENGINE ===

async def run_scrape_burst(
    event_id: str,
    tier: int,
    trigger_ticker: str,
    velocity_pct: float,
    direction: str,
    search_terms: list,
    scrape_interval: int = 120,
    scrape_duration: int = 15
):
    """
    Runs the full scrape burst cycle:
    1. Scrape every scrape_interval seconds for scrape_duration minutes
    2. After each scrape pass, accumulate results
    3. After final pass (or early if high-confidence result found), run LLM analysis
    4. Push results to Supabase catalyst_events table
    """
    try:
        total_passes = scrape_duration * 60 // scrape_interval  # e.g., 15 min / 2 min = 7-8 passes
        all_scraped_content = []
        best_analysis = None

        logger.info(f"HERMES BURST START: {total_passes} passes, {scrape_interval}s intervals for event {event_id}")

        for pass_num in range(1, total_passes + 1):
            logger.info(f"HERMES BURST pass {pass_num}/{total_passes} for {trigger_ticker}")

            # Scrape
            scraped = await scrape_sources(search_terms, tier)
            if scraped:
                all_scraped_content.extend(scraped)

            # Run LLM analysis after pass 2 (have some data) and on final pass
            # Also run on pass 1 if Tier 2 (urgent — correlated event)
            should_analyze = (
                pass_num == total_passes or  # Final pass — always analyze
                (pass_num >= 2 and len(all_scraped_content) >= 5) or  # Enough data accumulated
                (tier >= 2 and pass_num == 1 and len(all_scraped_content) >= 2)  # Tier 2 urgent — analyze ASAP
            )

            if should_analyze and all_scraped_content:
                analysis = await analyze_with_haiku(
                    scraped_content=all_scraped_content,
                    trigger_ticker=trigger_ticker,
                    velocity_pct=velocity_pct,
                    direction=direction,
                    tier=tier
                )
                if analysis:
                    best_analysis = analysis
                    # Push intermediate result to Supabase so Agora can show progress
                    await push_to_supabase(event_id, analysis)
                    logger.info(f"HERMES ANALYSIS (pass {pass_num}): {analysis.get('headline_summary', 'N/A')}")

                    # If high confidence, we can stop early — no need to keep scraping
                    if analysis.get("confidence", 0) >= 0.85 and pass_num >= 2:
                        logger.info(f"HERMES: High confidence ({analysis['confidence']}) — ending burst early")
                        break

            # Wait for next pass (skip wait on final pass)
            if pass_num < total_passes:
                await asyncio.sleep(scrape_interval)

        # Final analysis if we haven't pushed one yet
        if not best_analysis and all_scraped_content:
            analysis = await analyze_with_haiku(
                scraped_content=all_scraped_content,
                trigger_ticker=trigger_ticker,
                velocity_pct=velocity_pct,
                direction=direction,
                tier=tier
            )
            if analysis:
                await push_to_supabase(event_id, analysis)

        # If NO content was scraped at all, push a "no intel" result
        if not all_scraped_content:
            await push_to_supabase(event_id, {
                "headline_summary": f"{trigger_ticker} velocity breach detected — no headline catalyst found via scrape",
                "catalyst_category": "unknown",
                "confidence": 0.0,
                "full_analysis": "Pivot scrape burst returned no relevant content. Move may be technical/flow-driven rather than headline-driven."
            })

        logger.info(f"HERMES BURST COMPLETE for event {event_id}")

    except Exception as e:
        logger.error(f"HERMES BURST ERROR for event {event_id}: {e}", exc_info=True)
        # Push error status so the UI doesn't hang on "Pivot analyzing..."
        await push_to_supabase(event_id, {
            "headline_summary": "Pivot analysis failed — check VPS logs",
            "catalyst_category": "error",
            "confidence": 0.0,
            "full_analysis": str(e)
        })
    finally:
        active_bursts.pop(event_id, None)


# === SCRAPING LAYER ===
# This section contains multiple scrape strategies.
# CC: Check what's already available on this VPS and use the best option.
# Priority: 1) Existing Twitter scraper  2) Nitter instances  3) RSS + news scrape fallback

async def scrape_sources(search_terms: list, tier: int) -> list:
    """
    Master scrape function. Tries available sources in priority order.
    Returns a list of dicts: [{"source": str, "text": str, "author": str, "timestamp": str, "url": str}, ...]
    """
    results = []

    # Strategy 1: Twitter/X scrape (if available)
    twitter_results = await scrape_twitter(search_terms)
    if twitter_results:
        results.extend(twitter_results)

    # Strategy 2: RSS feeds from major financial news outlets
    rss_results = await scrape_rss_feeds(search_terms)
    if rss_results:
        results.extend(rss_results)

    # Strategy 3: Direct news site scrape (for Tier 2 — broader search)
    if tier >= 2:
        news_results = await scrape_news_sites(search_terms)
        if news_results:
            results.extend(news_results)

    # Deduplicate by content similarity (rough — first 80 chars)
    seen = set()
    deduped = []
    for r in results:
        key = r.get("text", "")[:80].lower().strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(r)

    return deduped


async def scrape_twitter(search_terms: list) -> list:
    """
    Twitter/X scrape via whatever method is available on this VPS.

    CC: CHECK FIRST what exists. Look for:
    - Existing scraper scripts (grep -r "twitter\|tweet\|nitter\|x.com" /opt/openclaw/)
    - snscrape, twscrape, ntscraper, or similar libraries installed (pip list | grep -i twit)
    - Nitter instances that may still be running
    - Any API keys or auth tokens for Twitter/X

    If a working scraper exists, wire it in here.
    If nothing exists, implement one of these options (in preference order):

    Option A: ntscraper (Nitter-based, no auth needed)
        pip install ntscraper
        from ntscraper import Nitter
        nitter = Nitter()
        tweets = nitter.get_tweets(search_term, mode='term', number=20)

    Option B: twscrape (needs Twitter accounts but works well)
        pip install twscrape
        Requires account pool setup — more complex but more reliable

    Option C: Direct Nitter instance scrape
        Hit a public Nitter instance URL with httpx and parse HTML
        Many instances are unreliable — use multiple with fallback

    Option D: Skip Twitter entirely and rely on RSS + news scrape
        This is the fallback if nothing else works. Still valuable —
        just 5-15 min slower than Twitter for breaking news.
    """
    results = []
    try:
        # === CC: IMPLEMENT BEST AVAILABLE OPTION HERE ===
        # Example structure for whatever method is used:
        #
        # For each search term (limit to top 3-4 most specific terms to avoid rate limits):
        #   query = search_terms[:4]
        #   for term in query:
        #       tweets = <scrape method>(term, count=15, recent=True)
        #       for tweet in tweets:
        #           results.append({
        #               "source": "twitter",
        #               "text": tweet.text,
        #               "author": tweet.username or tweet.user.username,
        #               "timestamp": str(tweet.created_at or tweet.date),
        #               "url": tweet.url or f"https://x.com/{tweet.username}/status/{tweet.id}",
        #               "engagement": getattr(tweet, 'likes', 0) + getattr(tweet, 'retweets', 0)
        #           })
        #
        # Sort by engagement (highest first) — the most-engaged tweets
        # in the last few minutes are most likely to explain the move.
        # Return top 30 results across all search terms.

        pass  # CC implements

    except Exception as e:
        logger.warning(f"HERMES Twitter scrape failed: {e}")

    return results


async def scrape_rss_feeds(search_terms: list) -> list:
    """
    Poll RSS feeds from major financial news outlets.
    Look for items published in the last 15 minutes that match search terms.
    """
    results = []

    rss_feeds = [
        {"name": "Reuters Business", "url": "https://feeds.reuters.com/reuters/businessNews"},
        {"name": "Reuters Markets", "url": "https://feeds.reuters.com/reuters/marketsNews"},
        {"name": "CNBC Top News", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"},
        {"name": "CNBC World", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362"},
        {"name": "Bloomberg Markets", "url": "https://feeds.bloomberg.com/markets/news.rss"},
        {"name": "AP News", "url": "https://rsshub.app/apnews/topics/business"},
        {"name": "MarketWatch", "url": "https://feeds.marketwatch.com/marketwatch/topstories"},
        {"name": "WSJ Markets", "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"},
        {"name": "FT Markets", "url": "https://www.ft.com/markets?format=rss"},
        {"name": "ZeroHedge", "url": "https://feeds.feedburner.com/zerohedge/feed"},
    ]

    # Build regex pattern from search terms for matching
    # Escape special regex chars and join with OR
    term_pattern = "|".join(re.escape(t.lower()) for t in search_terms if len(t) > 2)

    async with httpx.AsyncClient(timeout=10.0) as client:
        for feed in rss_feeds:
            try:
                resp = await client.get(feed["url"], follow_redirects=True)
                if resp.status_code != 200:
                    continue

                # Simple XML parsing — extract <item> blocks
                # Using regex rather than xml.etree for speed and to handle malformed feeds
                items = re.findall(
                    r'<item[^>]*>(.*?)</item>',
                    resp.text,
                    re.DOTALL | re.IGNORECASE
                )

                for item_xml in items[:10]:  # Check last 10 items per feed
                    title = extract_xml_field(item_xml, "title")
                    description = extract_xml_field(item_xml, "description")
                    link = extract_xml_field(item_xml, "link")
                    pub_date = extract_xml_field(item_xml, "pubDate")

                    # Check if item is recent (within last 20 minutes)
                    if pub_date and not is_recent(pub_date, minutes=20):
                        continue

                    # Check if item matches any search terms
                    combined_text = f"{title} {description}".lower()
                    if term_pattern and re.search(term_pattern, combined_text):
                        results.append({
                            "source": f"rss:{feed['name']}",
                            "text": f"{title}. {description[:300]}",
                            "author": feed["name"],
                            "timestamp": pub_date or "",
                            "url": link or ""
                        })

            except Exception as e:
                logger.debug(f"HERMES RSS feed {feed['name']} error: {e}")
                continue

    return results


async def scrape_news_sites(search_terms: list) -> list:
    """
    Direct scrape of financial news sites for Tier 2 events.
    Hits front pages of key sites and looks for breaking headlines matching terms.
    Only used for correlated/high-tier events to avoid excessive scraping.
    """
    results = []

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
                    "User-Agent": "Mozilla/5.0 (compatible; PandorasBox/1.0; +https://pandoras-box.dev)"
                })
                if resp.status_code != 200:
                    continue

                # Extract text content, find headlines matching search terms
                # Very rough: pull all text, search for term matches in surrounding context
                text = resp.text
                # Strip HTML tags for rough text extraction
                clean = re.sub(r'<[^>]+>', ' ', text)
                clean = re.sub(r'\s+', ' ', clean)

                # Find sentences/phrases containing search terms
                if term_pattern:
                    matches = re.finditer(term_pattern, clean.lower())
                    for match in list(matches)[:3]:  # Max 3 matches per site
                        start = max(0, match.start() - 100)
                        end = min(len(clean), match.end() + 200)
                        snippet = clean[start:end].strip()
                        results.append({
                            "source": f"web:{url.split('/')[2]}",
                            "text": snippet,
                            "author": url.split('/')[2],
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "url": url
                        })

            except Exception as e:
                logger.debug(f"HERMES news scrape {url} error: {e}")
                continue

    return results


# === XML/RSS HELPERS ===

def extract_xml_field(xml_str: str, field: str) -> str:
    """Extract text content from an XML field."""
    match = re.search(
        rf'<{field}[^>]*>(.*?)</{field}>',
        xml_str,
        re.DOTALL | re.IGNORECASE
    )
    if match:
        content = match.group(1).strip()
        # Handle CDATA blocks
        cdata_match = re.search(r'<!\[CDATA\[(.*?)\]\]>', content, re.DOTALL)
        if cdata_match:
            content = cdata_match.group(1)
        # Strip HTML tags from content
        content = re.sub(r'<[^>]+>', '', content)
        return content.strip()
    return ""


def is_recent(pub_date_str: str, minutes: int = 20) -> bool:
    """Check if an RSS pubDate is within the last N minutes."""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(pub_date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return dt >= cutoff
    except Exception:
        return True  # If we can't parse the date, include it (err on side of inclusion)


# === LLM ANALYSIS ===

async def analyze_with_haiku(
    scraped_content: list,
    trigger_ticker: str,
    velocity_pct: float,
    direction: str,
    tier: int
) -> Optional[dict]:
    """
    Feed scraped content into Claude Haiku for catalyst identification.
    Returns structured analysis with headline summary and category.
    """
    if not ANTHROPIC_API_KEY:
        logger.error("HERMES: No ANTHROPIC_API_KEY set — cannot run analysis")
        return None

    # Build the scraped content digest for the prompt
    # Sort by engagement (Twitter) or recency, take top 25 items
    sorted_content = sorted(
        scraped_content,
        key=lambda x: x.get("engagement", 0),
        reverse=True
    )[:25]

    content_digest = "\n\n".join([
        f"[{item['source']}] {item.get('author', 'Unknown')} ({item.get('timestamp', 'recent')}):\n{item['text'][:400]}"
        for item in sorted_content
    ])

    direction_word = "rallying" if direction == "up" else "selling off"
    sign = "+" if direction == "up" else ""

    prompt = f"""You are a real-time market intelligence analyst. A velocity breach was just detected:

**{trigger_ticker} moved {sign}{velocity_pct}% in ~30 minutes ({direction_word})**
{"This is a CORRELATED event — multiple related tickers moved simultaneously." if tier >= 2 else "This is a single-ticker event."}

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
- If nothing in the content explains the move, say so and set category to "unknown" with confidence < 0.3
- "thesis_impact" is critical — Nick holds bearish positions and needs to know if this changes anything
- The headline_summary will be displayed on a trading dashboard — make it precise, not clickbait"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}]
                }
            )

            if resp.status_code != 200:
                logger.error(f"HERMES Haiku API error: {resp.status_code} {resp.text[:200]}")
                return None

            data = resp.json()
            response_text = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    response_text += block.get("text", "")

            # Parse JSON response
            # Strip any markdown backticks if Haiku wraps it
            clean = response_text.strip()
            clean = re.sub(r'^```json\s*', '', clean)
            clean = re.sub(r'\s*```$', '', clean)

            analysis = json.loads(clean)

            # Validate required fields
            if "headline_summary" not in analysis or "catalyst_category" not in analysis:
                logger.warning(f"HERMES: Haiku response missing required fields: {clean[:200]}")
                return None

            return analysis

    except json.JSONDecodeError as e:
        logger.error(f"HERMES: Failed to parse Haiku response as JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"HERMES Haiku analysis error: {e}", exc_info=True)
        return None


# === SUPABASE PUSH ===

async def push_to_supabase(event_id: str, analysis: dict):
    """
    Update the catalyst_events row with Pivot's analysis.
    This is what makes the Agora banner update from 'Pivot analyzing...' to the real headline.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("HERMES: Supabase credentials not set — cannot push results")
        return

    update_payload = {
        "headline_summary": analysis.get("headline_summary", ""),
        "catalyst_category": analysis.get("catalyst_category", "unknown"),
        "pivot_analysis": json.dumps({
            "full_analysis": analysis.get("full_analysis", ""),
            "confidence": analysis.get("confidence", 0),
            "key_sources": analysis.get("key_sources", []),
            "thesis_impact": analysis.get("thesis_impact", ""),
            "analyzed_at": datetime.now(timezone.utc).isoformat()
        }),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/catalyst_events?id=eq.{event_id}",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal"
                },
                json=update_payload
            )
            if resp.status_code not in [200, 204]:
                logger.error(f"HERMES Supabase update failed: {resp.status_code} {resp.text[:200]}")
            else:
                logger.info(f"HERMES: Pushed analysis to Supabase for event {event_id}: {analysis.get('headline_summary', '')[:80]}")

    except Exception as e:
        logger.error(f"HERMES Supabase push error: {e}")


# === ROUTER REGISTRATION ===
# CC: Add this router to the existing FastAPI app in /opt/openclaw
# Find where other routers are included (e.g., app.include_router(...))
# and add:
#
#   from hermes_trigger import router as hermes_router
#   app.include_router(hermes_router)
#
# If the VPS app uses a different structure (e.g., single file),
# merge these routes into the existing file.
```

---

## STEP 2: Environment Variables on VPS

These should already be set for the committee pipeline, but verify:

```bash
# Check existing env vars
echo $ANTHROPIC_API_KEY  # Should be set
echo $SUPABASE_URL       # Should be set
echo $SUPABASE_SERVICE_KEY  # May need to add — different from anon key

# Add HERMES_API_KEY — must match the value set in Railway's system_config
export HERMES_API_KEY="REPLACE_WITH_SHARED_SECRET"
```

Add `HERMES_API_KEY` to whatever env management the VPS uses (`.env` file, systemd service file, etc.) so it persists across restarts.

---

## STEP 3: Firewall / Port Verification

The VPS needs to accept incoming HTTP from Railway on whatever port the FastAPI app runs on. Check:

```bash
# What port is the FastAPI app listening on?
ss -tlnp | grep python

# If the app runs on e.g., port 8000, verify Railway can reach it:
# From Railway (or any external machine):
# curl -X POST http://188.245.250.2:8000/api/hermes/trigger -H "X-API-Key: test" -d '{"event_id":"test"}'

# If the port is firewalled, open it:
# ufw allow 8000/tcp  (or whatever port)
```

**Important:** The trigger URL in Brief 1's system_config (`vps_trigger_url`) must match the actual port. Default in Brief 1 is `http://188.245.250.2:8000/api/hermes/trigger` — update if the port differs.

---

## STEP 4: Agora Frontend Update — Pivot Analysis Display

Brief 1 already created the banner with the "Pivot analyzing..." placeholder. The frontend polling in Brief 1 (`fetchHermesAlerts()`) already checks for `pivot_analysis` updates and calls `updateHermesPivotAnalysis()`. No new frontend code is needed here.

However, enhance the detail panel to show the full Pivot analysis when expanded:

**Find/replace in `app.js` — locate the `updateHermesPivotAnalysis` function from Brief 1 and replace with:**

```javascript
function updateHermesPivotAnalysis(analysisJson, category) {
    // Parse the pivot_analysis JSON if it's a string
    let analysis = analysisJson;
    if (typeof analysisJson === 'string') {
        try { analysis = JSON.parse(analysisJson); } catch(e) { analysis = { full_analysis: analysisJson }; }
    }

    const headline = analysis.headline_summary || analysis.full_analysis || analysisJson;
    const confidence = analysis.confidence || 0;
    const thesisImpact = analysis.thesis_impact || '';
    const sources = analysis.key_sources || [];

    // Update banner intel line
    const intelEl = document.getElementById('hermes-intel');
    intelEl.textContent = typeof headline === 'string' ? headline.substring(0, 120) : 'Analysis received';
    intelEl.style.fontStyle = 'normal';

    // Update detail panel
    const pivotPanel = document.getElementById('hermes-pivot-analysis');
    const categoryBadge = category ? `<span class="hermes-category-badge">[${category.toUpperCase()}]</span>` : '';
    const confidenceBar = `<span class="hermes-confidence" style="opacity: ${0.4 + confidence * 0.6}">${Math.round(confidence * 100)}% confidence</span>`;
    const thesisLine = thesisImpact ? `<div class="hermes-thesis-impact"><strong>Thesis Impact:</strong> ${thesisImpact}</div>` : '';
    const sourcesLine = sources.length ? `<div class="hermes-sources">Sources: ${sources.join(', ')}</div>` : '';

    pivotPanel.innerHTML = `
        <div class="hermes-analysis-header">${categoryBadge} ${confidenceBar}</div>
        <div class="hermes-analysis-body">${analysis.full_analysis || ''}</div>
        ${thesisLine}
        ${sourcesLine}
    `;
}
```

**Additional CSS (add to stylesheet after Brief 1's Hermes styles):**

```css
.hermes-category-badge {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
    margin-right: 6px;
}
/* Category-specific colors */
.hermes-category-badge:has(+ .hermes-confidence) { background: rgba(255,255,255,0.1); }

.hermes-confidence {
    font-size: 11px;
    font-family: 'IBM Plex Mono', monospace;
}

.hermes-analysis-body {
    margin: 6px 0;
    font-size: 12px;
    line-height: 1.5;
    color: rgba(255,255,255,0.85);
}

.hermes-thesis-impact {
    margin-top: 6px;
    padding: 4px 8px;
    background: rgba(255, 152, 0, 0.1);
    border-left: 2px solid rgba(255, 152, 0, 0.5);
    font-size: 12px;
    color: #ff9800;
}

.hermes-sources {
    margin-top: 4px;
    font-size: 10px;
    opacity: 0.5;
}
```

---

## STEP 5: Integration Test Checklist

After deployment, test the full chain end-to-end:

1. **Simulate a TV webhook** — from any machine, POST to Railway:
```bash
curl -X POST https://pandoras-box-production.up.railway.app/api/webhook/hermes \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "SPY",
    "velocity_pct": 1.5,
    "direction": "up",
    "threshold": 1.0,
    "timeframe_min": 30,
    "source": "tradingview",
    "alert_type": "hermes_flash"
  }'
```

2. **Verify Railway creates the event** — check `catalyst_events` table in Supabase for the new row

3. **Verify VPS received the trigger** — check VPS logs for "HERMES TRIGGER received" message

4. **Verify scrape burst runs** — check VPS logs for "HERMES BURST pass 1/7" messages

5. **Verify Haiku analysis runs** — check VPS logs for "HERMES ANALYSIS" with headline

6. **Verify Supabase updated** — check the `catalyst_events` row now has `headline_summary` and `pivot_analysis` populated

7. **Verify Agora displays it** — open the dashboard, confirm the Hermes Flash banner shows the alert and updates from "Pivot analyzing..." to the actual headline

---

## NOTES FOR CC

- The Twitter scraper section is intentionally flexible. Check what exists on the VPS first. If there's a working scraper, wire it in. If not, the RSS feed scraper alone is still valuable — it just runs 5-15 min behind Twitter. The architecture is the same either way.
- RSS feeds may have rate limits or change URLs. The feed list is a starting point — test each one during build and remove any that are dead.
- The `is_recent()` function uses Python's `email.utils.parsedate_to_datetime` which handles RFC 2822 date formats (standard for RSS). If a feed uses a non-standard format, add a fallback parser.
- Haiku model string: `claude-haiku-4-5-20251001` — this is the correct current model identifier for the direct Anthropic API.
- The `thesis_impact` field in the Haiku prompt is what makes this specifically useful for Nick rather than generic. It forces Haiku to evaluate every catalyst against the bearish Iran/Hormuz/credit thesis.
- `active_bursts` dict prevents a second trigger for the same event from launching a duplicate scrape cycle. This handles the case where Railway retries the trigger due to a timeout.
- The early-exit logic (confidence >= 0.85 after pass 2) saves LLM tokens when the catalyst is obvious. For ambiguous situations, the full 15-minute burst runs to accumulate more signal.
- Supabase writes use the service key (not anon key) because this is server-to-server. The anon key's RLS policies might block writes from the VPS IP.
