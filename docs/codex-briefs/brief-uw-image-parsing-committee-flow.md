# Brief — UW Embed Image Parsing (Haiku) + Committee Flow Context

**Priority:** MEDIUM-HIGH — unlocks the highest-value UW data (individual sweeps) and gives the committee flow awareness
**Touches:** VPS files: `uw_watcher.py`, `pivot2_committee.py`, `committee_context.py`
**Estimated time:** 2–3 hours
**Note:** This brief modifies VPS files, not Railway. Changes are deployed via SCP to the VPS, not git push.

---

## Problem Statement

1. **UW Watcher skips the most valuable data.** The Unusual Whales Discord bot sends two types of messages:
   - **Text messages** (ticker updates) — already parsed and flowing to Railway ✅
   - **Image/embed messages** (Highest Volume Contracts charts, large sweep alerts) — currently skipped with `"Skipping embed-only UW message"`. These contain individual high-premium contract data with strikes, expiry, and direction that our text parser can't capture.

2. **The Olympus Committee has zero flow awareness.** `build_market_context()` in `pivot2_committee.py` fetches bias, circuit breakers, earnings, portfolio, and timeframes — but NO options flow data. The committee makes trade decisions blind to what the options market is actually doing.

---

## Part 1 — UW Watcher: Parse Image Messages via Haiku

### File: VPS `/opt/openclaw/workspace/scripts/uw_watcher.py`

#### 1a. Add Anthropic API client setup

At the top of the file, after the existing imports (~line 10), add:

```python
import base64
import httpx

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
```

In the `create_bot()` function, capture the Anthropic API key alongside the existing config:

```python
def create_bot(api_url: str, api_key: str, anthropic_key: str = "") -> discord.Client:
```

And in `main()`, load the Anthropic key:

```python
anthropic_key = pick_env("ANTHROPIC_API_KEY", cfg, env_file)
bot = create_bot(api_url, api_key, anthropic_key)
```

#### 1b. Add image parsing function

Add this function before `create_bot()`:

```python
async def parse_uw_image(image_url: str, anthropic_key: str) -> list[dict] | None:
    """
    Download a UW image/chart and send to Haiku for structured data extraction.
    Returns list of parsed ticker dicts or None if parsing fails.
    
    Cost: ~$0.01-0.02 per image (Haiku vision).
    """
    if not anthropic_key:
        logger.warning("No ANTHROPIC_API_KEY — cannot parse UW images")
        return None

    try:
        # Download image
        async with httpx.AsyncClient(timeout=15.0) as client:
            img_resp = await client.get(image_url)
            if img_resp.status_code != 200:
                logger.warning("Failed to download UW image: HTTP %s", img_resp.status_code)
                return None
            
            image_bytes = img_resp.content
            # Detect media type from content-type header or URL
            content_type = img_resp.headers.get("content-type", "image/png")
            if "jpeg" in content_type or "jpg" in content_type:
                media_type = "image/jpeg"
            elif "gif" in content_type:
                media_type = "image/gif"
            elif "webp" in content_type:
                media_type = "image/webp"
            else:
                media_type = "image/png"
            
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        # Send to Haiku for parsing
        async with httpx.AsyncClient(timeout=30.0) as client:
            haiku_resp = await client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1024,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": image_b64,
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": (
                                        "Extract all options flow data from this Unusual Whales chart/table. "
                                        "Return ONLY a JSON array (no markdown, no backticks) where each element has: "
                                        '{"ticker": "AAPL", "volume": 50000, "premium": 12000000, '
                                        '"direction": "BULLISH" or "BEARISH" or "NEUTRAL", '
                                        '"contract_type": "CALL" or "PUT" or "MIXED", '
                                        '"strike": 150.0 or null, "expiry": "2026-04-17" or null, '
                                        '"notes": "brief description of the flow"}. '
                                        "If the image is not an options flow chart, return an empty array []."
                                    ),
                                },
                            ],
                        }
                    ],
                },
            )

            if haiku_resp.status_code != 200:
                logger.warning("Haiku API error: %s %s", haiku_resp.status_code, haiku_resp.text[:200])
                return None

            haiku_data = haiku_resp.json()
            text = ""
            for block in haiku_data.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")

            # Parse JSON from Haiku response
            text = text.strip()
            # Strip markdown fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            parsed = json.loads(text)
            if isinstance(parsed, list) and len(parsed) > 0:
                logger.info("Haiku parsed %d entries from UW image", len(parsed))
                return parsed
            return None

    except json.JSONDecodeError as e:
        logger.warning("Haiku returned non-JSON: %s", e)
        return None
    except Exception as e:
        logger.error("UW image parsing failed: %s", e)
        return None
```

#### 1c. Replace the skip logic with image parsing

In the `on_message` handler inside `create_bot()`, find the two skip blocks:

**Find:**
```python
        # Skip messages that are just images (Highest Volume Contracts chart)
        if not message.content and message.attachments:
            logger.info("Skipping image-only UW message (Highest Volume Contracts chart)")
            return

        # Skip embed-only messages (Highest Volume Contracts header)
        if not message.content and message.embeds:
            logger.info("Skipping embed-only UW message")
            return
```

**Replace with:**
```python
        # Parse image messages via Haiku (attachments = charts, embeds = sweep alerts)
        if not message.content:
            image_url = None
            
            # Check attachments (usually the "Highest Volume Contracts" chart)
            if message.attachments:
                for att in message.attachments:
                    if att.content_type and att.content_type.startswith("image/"):
                        image_url = att.url
                        break
            
            # Check embeds (may contain image or thumbnail)
            if not image_url and message.embeds:
                for embed in message.embeds:
                    if embed.image and embed.image.url:
                        image_url = embed.image.url
                        break
                    if embed.thumbnail and embed.thumbnail.url:
                        image_url = embed.thumbnail.url
                        break
            
            if not image_url:
                logger.info("UW message with no parseable content or images")
                return
            
            # Parse image via Haiku
            logger.info("Parsing UW image via Haiku: %s", image_url[:80])
            parsed_entries = await parse_uw_image(image_url, anthropic_key)
            
            if not parsed_entries:
                logger.info("No flow data extracted from UW image")
                return
            
            # Convert Haiku output to the same format as text-parsed tickers
            haiku_tickers = []
            for entry in parsed_entries:
                ticker = (entry.get("ticker") or "").upper()
                if not ticker or len(ticker) > 5:
                    continue
                
                direction = (entry.get("direction") or "NEUTRAL").upper()
                premium = entry.get("premium") or 0
                
                haiku_tickers.append({
                    "ticker": ticker,
                    "price": None,
                    "change_pct": None,
                    "volume": entry.get("volume") or 0,
                    "pc_ratio": None,
                    "put_volume": None,
                    "call_volume": None,
                    "total_premium": premium if isinstance(premium, int) else 0,
                    "flow_sentiment": direction if direction in ("BULLISH", "BEARISH") else None,
                    "flow_premium": None,
                    "flow_pct": None,
                })
            
            if haiku_tickers:
                payload = {
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                    "source": "uw_image_haiku",
                    "tickers": haiku_tickers,
                }
                try:
                    resp = requests.post(
                        f"{api_url}/api/uw/ticker-updates",
                        json=payload,
                        headers={"Authorization": f"Bearer {api_key}"},
                        timeout=10,
                    )
                    logger.info(
                        "Posted %d Haiku-parsed tickers from UW image (status=%s)",
                        len(haiku_tickers), resp.status_code,
                    )
                except Exception as e:
                    logger.error("Failed to POST Haiku-parsed UW data: %s", e)
            
            return
```

#### 1d. Update `create_bot()` to capture anthropic_key in closure

The `anthropic_key` variable needs to be accessible inside `on_message`. Update the function signature and make sure the variable is in scope. The simplest approach: store it on the client object.

In `create_bot()`, after `client = discord.Client(intents=intents)`:

```python
    client._anthropic_key = anthropic_key
```

Then in the image parsing call, use `client._anthropic_key` instead of `anthropic_key`. Or use a closure — CC should pick whichever is cleaner.

#### 1e. Update `main()` to pass anthropic_key

**Find:**
```python
    bot = create_bot(api_url, api_key)
```

**Replace with:**
```python
    anthropic_key = pick_env("ANTHROPIC_API_KEY", cfg, env_file)
    if not anthropic_key:
        logger.warning("ANTHROPIC_API_KEY not set — UW image parsing will be disabled")
    bot = create_bot(api_url, api_key, anthropic_key)
```

The `ANTHROPIC_API_KEY` should already be available in the openclaw env (it's used by the committee). If not, it needs to be added to `/etc/openclaw/openclaw.env` or `openclaw.json`.

---

## Part 2 — Committee: Inject Flow Data into Context

### File: VPS `/opt/openclaw/workspace/scripts/pivot2_committee.py`

In `build_market_context()` (~line 619), add a new section after the portfolio fetch (section 6) to fetch flow radar data:

**Find (~line 658, after the portfolio section):**
```python
    # 7. Timeframe sub-scores
```

**Add BEFORE that line:**
```python
    # 6b. Options flow context (from UW Watcher data)
    flow_context = {}
    try:
        flow_raw = http_json(url=f"{base}/api/flow/radar", headers=headers, timeout=15)
        if isinstance(flow_raw, dict):
            flow_context = flow_raw
    except Exception:
        pass
```

Then add `flow_context` to the returned dict. **Find** the `return {` block (~line 687) and add:

```python
        "flow": flow_context,
```

### File: VPS `/opt/openclaw/workspace/scripts/committee_context.py`

In `format_signal_context()`, add a flow section after the portfolio context. Find where portfolio is formatted (search for "PORTFOLIO" or "portfolio" section rendering) and add:

```python
    # ── Options flow context ──
    flow = context.get("flow") or {}
    if flow:
        flow_lines = ["## OPTIONS FLOW (UW Watcher — last update)"]
        
        mp = flow.get("market_pulse", {})
        if mp:
            flow_lines.append(
                f"Market: P/C {mp.get('overall_pc_ratio', '?')} | "
                f"Sentiment: {mp.get('overall_sentiment', '?')} | "
                f"Premium: {mp.get('total_premium_display', '$?')} | "
                f"Tickers: {mp.get('tickers_with_flow', 0)}"
            )

        pf = flow.get("position_flow", [])
        if pf:
            flow_lines.append("Position Flow:")
            for p in pf[:5]:
                flow_lines.append(
                    f"  {p['ticker']} — {p['alignment']} ({p['strength']}) | "
                    f"P/C {p.get('pc_ratio', '?')} | {p.get('premium_display', '')}"
                )

        wu = flow.get("watchlist_unusual", [])
        if wu:
            flow_lines.append("Unusual Activity (watchlist):")
            for w in wu[:5]:
                div_tag = " [DIVERGENCE]" if w.get("divergence") else ""
                flow_lines.append(
                    f"  {w['ticker']} — {w['sentiment']} | "
                    f"P/C {w.get('pc_ratio', '?')} | {w.get('premium_display', '')}"
                    f"{div_tag}"
                )

        sf = flow.get("sector_flow", [])
        if sf:
            flow_lines.append("Sector Rotation:")
            for s in sf[:5]:
                flow_lines.append(
                    f"  {s['etf']} — {s['sentiment']} | "
                    f"P/C {s.get('avg_pc_ratio', '?')} | {s.get('premium_display', '')}"
                )

        if len(flow_lines) > 1:
            sections.append("\n".join(flow_lines))
```

---

## Part 3 — Update Committee Prompts (Flow Awareness Rule)

### File: VPS `/opt/openclaw/workspace/scripts/committee_prompts.py`

Add a flow awareness directive to ALL four agent system prompts. Find each `*_SYSTEM_PROMPT` and add this to their instructions:

**Add to TORO_SYSTEM_PROMPT** (after the existing numbered rules, before the bias scale):
```
6. **Check Options Flow First**: Before analyzing the chart, look at the OPTIONS FLOW section in the context. If there's flow data for this ticker or sector, your analysis MUST reference it. Flow alignment (institutional money confirming the signal direction) significantly increases conviction. Flow divergence (smart money going the opposite direction) is a major red flag even if the chart looks good.
```

**Add to URSA_SYSTEM_PROMPT** (in the risk assessment list):
```
   - Flow conflict: if OPTIONS FLOW data shows institutional money moving opposite to the signal direction, this is a high-conviction counter-signal. Flag it prominently.
   - Sector flow divergence: if the ticker's sector shows heavy put flow while this is a bullish signal (or vice versa), the setup is fighting institutional positioning.
```

**Add to TECHNICALS_SYSTEM_PROMPT** (after the existing technical framework):
```
When OPTIONS FLOW data is available in the context, integrate it into your technical analysis:
- Flow-confirmed breakouts (price breaking a level WITH aligned institutional flow) have significantly higher follow-through rates than chart-only breakouts.
- Flow divergences at key levels (e.g., price at support but put flow accelerating) warn that the level may not hold.
- Use flow data to assess conviction on your entry/exit recommendations.
```

**Add to PIVOT system prompt** (in the synthesis instructions):
```
When OPTIONS FLOW data is present, always include a "Flow Assessment" section in your synthesis:
- Does the options market confirm or challenge this setup?
- Any notable divergences between price action and institutional flow?
- How does sector-level flow context affect the thesis?
If no flow data is available for this ticker, note that as a gap.
```

---

## Deployment

This brief modifies VPS files only. Deploy via SSH:

```bash
# 1. SCP updated files to VPS
scp uw_watcher.py user@188.245.250.2:/opt/openclaw/workspace/scripts/uw_watcher.py
scp pivot2_committee.py user@188.245.250.2:/opt/openclaw/workspace/scripts/pivot2_committee.py
scp committee_context.py user@188.245.250.2:/opt/openclaw/workspace/scripts/committee_context.py
scp committee_prompts.py user@188.245.250.2:/opt/openclaw/workspace/scripts/committee_prompts.py

# 2. Restart UW Watcher
sudo systemctl restart uw-watcher

# 3. Verify
journalctl -u uw-watcher -n 5 --no-pager
```

The committee (Pivot II / OpenClaw) doesn't need a restart — it reads prompts fresh on each run.

---

## Verification Checklist

- [ ] UW Watcher starts without errors after restart
- [ ] On next UW image message: log shows "Parsing UW image via Haiku" instead of "Skipping"
- [ ] Haiku returns valid JSON with ticker/volume/premium data from the image
- [ ] Parsed image data posts to `/api/uw/ticker-updates` with `source: uw_image_haiku`
- [ ] Flow Radar shows additional tickers from image parsing
- [ ] `build_market_context()` includes `flow` key with radar data
- [ ] Committee prompt context includes "## OPTIONS FLOW" section
- [ ] Committee analysis references flow data when available
- [ ] ANTHROPIC_API_KEY is available in the VPS env

---

## Cost Estimate

- Haiku vision: ~$0.01-0.02 per image
- UW sends ~5-10 images per trading session
- **Daily cost: ~$0.05-0.20** — negligible

---

## Known Limitations

1. **Haiku image parsing is best-effort.** Charts with unusual formatting, low resolution, or non-standard layouts may not parse correctly. The function returns `None` on failure and logs a warning — it never blocks the main text parsing flow.
2. **No contract-level detail in the ingestion endpoint.** The current `/api/uw/ticker-updates` endpoint accepts ticker-level data (premium, direction) but not individual contract details (strike, expiry). The Haiku parser extracts this data but it's flattened to fit the existing schema. A future enhancement could add a separate `/api/uw/sweeps` endpoint for contract-level data.
3. **Committee flow context is only as fresh as the last UW update.** During fast-moving markets, the flow data in the committee context may be 15-30 minutes old by the time the committee runs.

---

## Commit (VPS — not git push)

```
feat: UW image parsing via Haiku + committee flow context injection
```
