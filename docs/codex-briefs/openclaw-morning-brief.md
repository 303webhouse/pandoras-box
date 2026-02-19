# Codex Brief: Port Morning & EOD Briefs to OpenClaw (Step 2 — Migration Spike)

**Date:** February 19, 2026
**Priority:** High
**Scope:** Two OpenClaw cron flows (morning + EOD) — zero changes to existing Pivot bot
**Estimated effort:** ~45 min agent time

---

## Context

OpenClaw is now running on the VPS as `openclaw.service` alongside the existing Pivot bot. Personality files are populated. This step ports the **morning brief** and **EOD brief** — daily market analyses posted to Discord — as the first real proof-of-concept of OpenClaw doing actual trading work.

**The existing Pivot bot continues to post its briefs to its own channels. This creates parallel briefs in #pivot-ii for side-by-side comparison.**

---

## Key Design Change: Two-Step UW Data Flow

The current Pivot bot generates briefs without Unusual Whales visual data because it can't request it from Nick. **Pivot II fixes this** with a two-step flow:

1. **Prep ping** — Pivot II posts a message asking Nick to drop UW screenshots (Market Tide, Dark Pool levels, notable flow)
2. **Brief generation** — After a wait window, Pivot II collects any screenshots Nick posted, adds them to the composite data as image context, and generates the full brief

If Nick doesn't respond within the wait window, the brief fires anyway and notes the UW data gap. This way the brief is never blocked, but is richer when Nick engages.

---

## Schedule (All Times Eastern)

### Morning Brief
| Step | Time ET | Time MT | What happens |
|------|---------|---------|-------------|
| Prep ping | 9:15 AM | 7:15 AM | Pivot II asks Nick for UW screenshots in #pivot-ii |
| Brief generation | 9:45 AM | 7:45 AM | Brief fires with composite + any UW data Nick posted |

Rationale: 15 minutes after market open lets the opening rotation settle. Nick gets the ping when he wakes (~7:15 MT), has 30 min to drop screenshots, and gets the brief at 7:45 MT.

### EOD Brief
| Step | Time ET | Time MT | What happens |
|------|---------|---------|-------------|
| Prep ping | 4:15 PM | 2:15 PM | Pivot II asks Nick for EOD UW screenshots in #pivot-ii |
| Brief generation | 4:30 PM | 2:30 PM | Brief fires with composite + convergence + any UW data |

---

## How the Current Briefs Work

### Morning Brief (current Pivot — `/opt/pivot/scheduler/cron_runner.py` line 245)

```
1. GET /bias/composite from Railway API → JSON with all factor scores, bias level, stale/active factors
2. Wrap JSON in prompt template
3. Send to Claude Sonnet 4.6 via OpenRouter
4. Post response to Discord
```

### EOD Brief (current Pivot — same file, line 254)

```
1. GET /bias/composite from Railway API
2. GET /analytics/convergence-stats?days=1&min_sources=2
3. GET /analytics/uw-snapshots?days=1
4. Compute factor health (fresh vs stale counts)
5. Wrap all data in prompt template
6. Send to Claude Sonnet 4.6 via OpenRouter
7. Post response to Discord
```

### Railway API Details

- **Base URL:** `https://pandoras-box-production.up.railway.app/api`
- **Auth:** `Authorization: Bearer rLl-7i2GqGjie5in9iHIlVtqlP5zpY7D5E6-8tzlNSk`
- **Endpoints used:**
  - `GET /bias/composite` — factor scores, bias level, active/stale factors
  - `GET /analytics/convergence-stats?days=1&min_sources=2` — signal convergence (EOD only)
  - `GET /analytics/uw-snapshots?days=1` — UW snapshot data (EOD only)

---

## What to Build in OpenClaw

### 1. Morning Brief — Prep Ping (Cron #1)

**Schedule:** `15 9 * * 1-5` (9:15 AM ET, Mon-Fri)
**Channel:** 1474135100521451813 (#pivot-ii)

Pivot II posts a message like:

```
☀️ Morning brief in 30 minutes. Drop any of these in this channel and I'll include them in the analysis:

📊 UW Market Tide screenshot
🏊 UW Dark Pool levels
🔥 Any notable overnight flow or unusual activity

No screenshots? No problem — I'll generate the brief with available data at 9:45 AM ET.
```

This is a simple scheduled Discord message — no skill needed, just a cron that posts static text.

### 2. Morning Brief — Generation (Cron #2)

**Schedule:** `45 9 * * 1-5` (9:45 AM ET, Mon-Fri)
**Channel:** 1474135100521451813 (#pivot-ii)

This cron triggers a skill that:

1. **Fetches composite data** from Railway API (`GET /bias/composite`)
2. **Checks for recent images** in #pivot-ii posted by Nick in the last 30 minutes (between 9:15 and 9:45 AM ET). OpenClaw should be able to read recent channel messages and identify image attachments.
3. **Builds the prompt** with composite JSON + any UW screenshots as image context
4. **Sends to LLM** (Claude Sonnet 4.6 via OpenRouter) with both text and image inputs
5. **Posts the brief** to #pivot-ii

**Morning brief prompt template:**

```
Generate the morning brief. Follow the format from your identity/personality context.

ONE-LINE bias summary first. Then:
- Overnight developments (2-3 bullets, concise)
- Factor snapshot (all factors with scores and one-line reads)
- DEFCON status (Green/Yellow/Orange/Red + any active triggers)
- Open positions across all 3 accounts if data available
- Breakout account status (balance, HWM, room to floors)
- Key catalysts today (from economic/earnings calendars)
- Trading implications (1-2 sentences, account-specific)

If UW screenshots were provided, include:
- Market Tide read (bullish/bearish/neutral flow)
- Dark Pool positioning
- Notable unusual activity

If any factor data is stale or missing, flag it.
If any factor conflicts exist, highlight them.
If no UW data was provided, note: "⚠️ No UW visual data provided — flow analysis unavailable."

DATA:
{composite_json}
```

If screenshots are present, they should be passed as image content alongside the text prompt (Claude Sonnet 4.6 supports vision).

### 3. EOD Brief — Prep Ping (Cron #3)

**Schedule:** `15 16 * * 1-5` (4:15 PM ET, Mon-Fri)
**Channel:** 1474135100521451813 (#pivot-ii)

```
🌙 EOD brief in 15 minutes. If you have these, drop them here:

📊 UW Market Tide (end of day)
🏊 UW Dark Pool levels (closing)
📈 GEX levels if notable
🔥 Any flow that stood out today

Brief fires at 4:30 PM ET regardless.
```

### 4. EOD Brief — Generation (Cron #4)

**Schedule:** `30 16 * * 1-5` (4:30 PM ET, Mon-Fri)
**Channel:** 1474135100521451813 (#pivot-ii)

Same pattern as morning but with more data sources:

1. **Fetch composite data** (`GET /bias/composite`)
2. **Fetch convergence stats** (`GET /analytics/convergence-stats?days=1&min_sources=2`)
3. **Fetch UW snapshots** (`GET /analytics/uw-snapshots?days=1`)
4. **Check for recent images** in #pivot-ii from Nick (last 15 min)
5. **Compute factor health** — count active vs stale factors from composite
6. **Build prompt** with all data + screenshots
7. **Post brief** to #pivot-ii

**EOD brief prompt template:**

```
Generate the EOD summary. Follow the format from your identity/personality context.

Lead with the day's verdict: did the bias call play out?
- Factor Health line: fresh/total fresh (stale count and names)
- If stale_count > 5: "⚠️ Low data confidence — factors stale. Composite bias may be unreliable."
- Signal Convergence section (last 24h):
  - "🎯 CONVERGENCE: {ticker} {direction} — confirmed by {source1}, {source2}"
  - 2 sources = MODERATE, 3+ = HIGH
  - If none: "No signal convergence detected today."
- UW Flow Intelligence from screenshots if provided:
  - Market Tide read, Dark Pool positioning, GEX analysis
  - If no screenshots: "📊 UW visual data not provided — flow analysis based on API data only."
- Factor changes during session (what moved, what didn't)
- DEFCON events today
- Notable flow activity
- P&L across accounts if data available
- Breakout account end-of-day status
- Lessons or patterns worth noting
- Setup for tomorrow (overnight bias lean)

DATA:
{eod_payload_json}
```

### 5. Store API Credentials

Store the Railway API key in OpenClaw's config (NOT hardcoded in skills):

```bash
su - openclaw
openclaw config set env.PANDORA_API_URL "https://pandoras-box-production.up.railway.app/api"
openclaw config set env.PIVOT_API_KEY "rLl-7i2GqGjie5in9iHIlVtqlP5zpY7D5E6-8tzlNSk"
```

Or add to the systemd service file environment:

```ini
Environment=PANDORA_API_URL=https://pandoras-box-production.up.railway.app/api
Environment=PIVOT_API_KEY=rLl-7i2GqGjie5in9iHIlVtqlP5zpY7D5E6-8tzlNSk
```

Use whichever method OpenClaw's docs recommend.

---

## Testing

### Step 1: Test prep ping manually

Trigger the prep ping cron manually. Verify it posts the UW data request message to #pivot-ii.

### Step 2: Drop a test screenshot

Post any image to #pivot-ii after the prep ping.

### Step 3: Trigger morning brief manually

Run the morning brief skill/cron. Verify:
1. It fetches composite data from Railway API
2. It picks up the screenshot you posted
3. It generates a brief that references the image content
4. Brief posts to #pivot-ii with correct factor data AND UW analysis

### Step 4: Test without screenshots

Trigger the brief again WITHOUT posting any images. Verify it still generates but includes the "⚠️ No UW visual data provided" note.

### Step 5: Test EOD brief

Same as above but trigger the EOD flow. Verify it pulls convergence + UW snapshot data in addition to composite.

### Step 6: Let cron fire naturally

After manual tests pass, let the next trading morning crons fire on schedule and verify end-to-end.

---

## Image Handling Notes

OpenClaw with Claude Sonnet 4.6 supports vision (image analysis). The key challenge is:

1. **Reading recent channel messages** — OpenClaw's Discord plugin should support reading message history. Look for a way to fetch recent messages from a channel and filter for image attachments.
2. **Passing images to LLM** — The images need to be included in the LLM prompt as image content (base64 or URL). OpenClaw should support multi-modal prompts since it uses Claude.
3. **Filtering by time window** — Only collect images posted AFTER the prep ping and BEFORE the brief generation time. Don't pick up old screenshots from yesterday.
4. **Filtering by author** — Only collect images from Nick (the server owner), not from Pivot II's own messages.

If OpenClaw doesn't natively support reading channel history + passing images to LLM in a skill, the fallback is a helper script that uses the Discord API to fetch recent messages with attachments.

---

## Definition of Done

- [ ] Prep ping cron posts UW data request to #pivot-ii at 9:15 AM ET, Mon-Fri
- [ ] Morning brief skill fetches Railway composite, collects any UW screenshots from channel, generates brief with both
- [ ] Morning brief cron fires at 9:45 AM ET and posts to #pivot-ii
- [ ] Brief correctly includes UW analysis when screenshots are provided
- [ ] Brief correctly notes UW gap when no screenshots are provided
- [ ] EOD prep ping posts at 4:15 PM ET
- [ ] EOD brief fires at 4:30 PM ET with composite + convergence + UW data
- [ ] API credentials stored securely (not hardcoded)
- [ ] Existing Pivot bot services unaffected

---

## What This Does NOT Include

- No other cron jobs (heartbeat, anomaly, collectors)
- No UW flow parsing beyond screenshot analysis
- No TradingView webhook handling
- No changes to existing Pivot bot or its channels
- No shutdown of existing briefs (both bots run in parallel)

---

## Reference Files on VPS

| File | What's in it |
|------|-------------|
| `/opt/pivot/scheduler/cron_runner.py` (line 245) | Current morning_brief() function |
| `/opt/pivot/scheduler/cron_runner.py` (line 254) | Current eod_brief() function |
| `/opt/pivot/llm/prompts.py` (line 284) | build_morning_brief_prompt() |
| `/opt/pivot/llm/prompts.py` (line 302) | build_eod_prompt() |
| `/opt/pivot/collectors/base_collector.py` | get_json() helper with retry logic |
| `/opt/pivot/.env` | PANDORA_API_URL and PIVOT_API_KEY |
| `/opt/openclaw/workspace/IDENTITY.md` | Pivot II personality |
| `/opt/openclaw/workspace/SOUL.md` | Pivot II behavioral rules |

---

## Files Changed

- OpenClaw skills directory (NEW — morning-brief skill, EOD-brief skill)
- OpenClaw cron configuration (NEW — 4 cron entries)
- OpenClaw env/config (NEW — API credentials)
- Possibly `/opt/openclaw/workspace/scripts/` (NEW — helper scripts if needed)
- Possibly `/etc/systemd/system/openclaw.service` (if adding env vars)

**Zero files changed in /opt/pivot/**
