# Codex Brief: Port Morning Brief to OpenClaw (Step 2 — Migration Spike)

**Date:** February 19, 2026
**Priority:** High
**Scope:** One OpenClaw cron job + skill — zero changes to existing Pivot bot
**Estimated effort:** ~30 min agent time

---

## Context

OpenClaw is now running on the VPS as `openclaw.service` alongside the existing Pivot bot. Personality files are populated. This step ports the **morning brief** — a daily market analysis posted to Discord before market open — as the first real proof-of-concept of OpenClaw doing actual trading work.

**The existing Pivot bot continues to post its morning brief to its own channels. This creates a parallel brief in #pivot-ii for side-by-side comparison.**

---

## How the Current Morning Brief Works

The flow is simple (see `/opt/pivot/scheduler/cron_runner.py` line 245):

```
1. Cron fires at 6:45 AM ET, Mon-Fri
2. GET /bias/composite from Railway API → returns JSON with all factor scores, bias level, stale/active factors
3. Wrap the JSON in a prompt template (see build_morning_brief_prompt in prompts.py)
4. Send prompt to Claude Sonnet 4.6 via OpenRouter
5. Post the LLM response to Discord #briefs channel
```

### Railway API Details

- **URL:** `https://pandoras-box-production.up.railway.app/api/bias/composite`
- **Auth:** `Authorization: Bearer rLl-7i2GqGjie5in9iHIlVtqlP5zpY7D5E6-8tzlNSk`
- **Method:** GET
- **Returns:** JSON with composite_score, bias_level, factors (each with score, signal, detail, timestamp, raw_data), active_factors, stale_factors

### The Prompt Template

The morning brief prompt (from `/opt/pivot/llm/prompts.py` line 284) tells the LLM to generate:

```
ONE-LINE bias summary first. Then:
- Overnight developments (2-3 bullets, concise)
- Factor snapshot (all factors with scores and one-line reads)
- DEFCON status (Green/Yellow/Orange/Red + any active triggers)
- Open positions across all 3 accounts if data available
- Breakout account status (balance, HWM, room to floors)
- Key catalysts today (from economic/earnings calendars)
- Trading implications (1-2 sentences, account-specific)

If any factor data is stale or missing, flag it.
If any factor conflicts exist, highlight them.
```

The prompt is prepended with the system prompt from PIVOT_SYSTEM_PROMPT in prompts.py, which contains Pivot's full personality, trading rules, and behavioral instructions. For Pivot II, this context is already in the OpenClaw identity files (SOUL.md, IDENTITY.md, etc.).

---

## What to Build in OpenClaw

### 1. Create a Morning Brief Skill

OpenClaw skills are the mechanism for custom functionality. Create a skill that:

1. Makes an HTTP GET request to the Railway API composite endpoint
2. Formats the response into the morning brief prompt
3. Returns the prompt so OpenClaw's LLM generates the brief
4. Posts the result to the #pivot-ii Discord channel

**Refer to OpenClaw's skill creation docs:** https://docs.openclaw.ai/tools/clawhub (or local `openclaw skill create` CLI).

The skill should be named something like `morning-brief` or `market-brief`.

**The prompt template to use (adapt to OpenClaw's skill format):**

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

If any factor data is stale or missing, flag it.
If any factor conflicts exist, highlight them.

DATA:
{composite_json}
```

### 2. Set Up the Cron Job

Use OpenClaw's native cron system (https://docs.openclaw.ai/automation/cron-jobs):

```bash
su - openclaw

# Add morning brief cron — 6:45 AM ET, Monday-Friday
openclaw cron add \
  --name "morning-brief" \
  --schedule "45 6 * * 1-5" \
  --timezone "America/New_York" \
  --channel "1474135100521451813" \
  --command "Run the morning brief skill"
```

The exact syntax may differ — check `openclaw cron --help` for the correct flags. The key parameters:
- **Schedule:** `45 6 * * 1-5` (6:45 AM, Mon-Fri)
- **Timezone:** America/New_York (ET)
- **Channel:** 1474135100521451813 (#pivot-ii)

### 3. Handle the API Call

The skill needs to make an authenticated HTTP request. How this works depends on OpenClaw's skill framework:

**Option A — If OpenClaw skills support HTTP natively:**
Use whatever built-in HTTP/fetch tool OpenClaw provides. Pass the URL and auth header.

**Option B — If skills need a helper script:**
Create a small script at `/opt/openclaw/workspace/scripts/fetch-composite.sh`:

```bash
#!/bin/bash
curl -s \
  -H "Authorization: Bearer rLl-7i2GqGjie5in9iHIlVtqlP5zpY7D5E6-8tzlNSk" \
  "https://pandoras-box-production.up.railway.app/api/bias/composite"
```

Make it executable: `chmod +x /opt/openclaw/workspace/scripts/fetch-composite.sh`

The skill invokes this script and pipes the output into the prompt template.

**Option C — If OpenClaw supports webhook-triggered skills:**
Set up a webhook route that the existing `pivot-collector` could hit, but this adds coupling we don't want yet. Prefer Option A or B.

### 4. Store API Credentials

The Railway API key should NOT be hardcoded in skill files. Store it in OpenClaw's config/env:

```bash
su - openclaw
openclaw config set env.PANDORA_API_URL "https://pandoras-box-production.up.railway.app/api"
openclaw config set env.PIVOT_API_KEY "rLl-7i2GqGjie5in9iHIlVtqlP5zpY7D5E6-8tzlNSk"
```

Or add to the openclaw user's environment in the systemd service file:

```ini
Environment=PANDORA_API_URL=https://pandoras-box-production.up.railway.app/api
Environment=PIVOT_API_KEY=rLl-7i2GqGjie5in9iHIlVtqlP5zpY7D5E6-8tzlNSk
```

Use whichever method OpenClaw's docs recommend for persistent env vars.

---

## Testing

### Manual trigger first

Before relying on cron, trigger the brief manually:

```bash
su - openclaw
openclaw cron run morning-brief
```

Or invoke the skill directly (whatever OpenClaw's CLI supports). Verify:

1. It fetches data from the Railway API (non-empty JSON response)
2. It generates a brief that includes factor scores, bias level, stale factor warnings
3. It posts to #pivot-ii channel in Discord
4. The formatting and content quality is comparable to current Pivot's morning brief

### Then wait for cron

After manual test passes, let the cron fire naturally the next trading morning (6:45 AM ET). Verify it posts without manual intervention.

---

## Comparison Test

Once both briefs are posting (current Pivot to its channel, Pivot II to #pivot-ii), Nick will compare them side by side to evaluate:

- Does Pivot II's brief contain the same information?
- Is the analysis quality comparable?
- Does it correctly flag stale factors?
- Does it correctly identify the bias level?
- Does the personality feel like Pivot?

This comparison determines whether to continue the migration.

---

## Definition of Done

- [ ] OpenClaw skill created for morning brief (fetches Railway API, formats prompt, returns analysis)
- [ ] API credentials stored securely in OpenClaw config (not hardcoded in skill files)
- [ ] Cron job configured: 6:45 AM ET, Mon-Fri, posts to #pivot-ii
- [ ] Manual trigger tested successfully — brief appears in #pivot-ii with correct content
- [ ] Existing Pivot bot services unaffected (pivot-bot, pivot-collector still active)

---

## What This Does NOT Include

- No EOD brief (port that after morning brief is validated)
- No other cron jobs (heartbeat, anomaly, collectors)
- No UW flow parsing
- No TradingView webhook handling
- No changes to existing Pivot bot or its channels
- No shutdown of existing morning brief (both run in parallel)

---

## Reference Files on VPS

| File | What's in it |
|------|-------------|
| `/opt/pivot/scheduler/cron_runner.py` (line 245) | Current morning_brief() function |
| `/opt/pivot/llm/prompts.py` (line 284) | build_morning_brief_prompt() template |
| `/opt/pivot/collectors/base_collector.py` | get_json() helper with retry logic |
| `/opt/pivot/.env` | PANDORA_API_URL and PIVOT_API_KEY values |
| `/opt/openclaw/workspace/IDENTITY.md` | Pivot II personality (replaces PIVOT_SYSTEM_PROMPT) |
| `/opt/openclaw/workspace/SOUL.md` | Pivot II behavioral rules |

---

## Files Changed

- `/opt/openclaw/workspace/skills/morning-brief/` (NEW — or wherever OpenClaw stores skills)
- OpenClaw cron configuration (NEW entry)
- OpenClaw env/config (NEW — API credentials)
- Possibly `/etc/systemd/system/openclaw.service` (if adding env vars there)

**Zero files changed in /opt/pivot/**
