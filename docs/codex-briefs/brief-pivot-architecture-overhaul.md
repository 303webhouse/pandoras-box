# Brief: Pivot/OpenClaw Architecture Overhaul

**Target:** Claude Code (VSCode) with ssh-vps tool access
**Goal:** Modernize the committee pipeline, cut API costs ~60%, eliminate dead code, restore the agent feedback loop
**Estimated effort:** 2-3 hours total across 4 tiers
**Pre-work:** `cd C:\trading-hub && git pull origin main` to get the latest trading docs and this brief

---

## CONTEXT: WHAT YOU'RE WORKING WITH

The VPS at 188.245.250.2 runs OpenClaw (renamed Pivot II), which executes the Olympus trading committee on signals from Railway. Key paths:

- **Main pipeline:** `/opt/openclaw/workspace/scripts/pivot2_committee.py`
- **Context builder:** `/opt/openclaw/workspace/scripts/committee_context.py`
- **Agent prompts:** `/opt/openclaw/workspace/scripts/committee_prompts.py`
- **Bridge entry point:** `/opt/openclaw/workspace/scripts/committee_railway_bridge.py`
- **API/parser helpers:** `/opt/openclaw/workspace/scripts/committee_parsers.py`
- **Env file:** `/etc/openclaw/openclaw.env` (read by all scripts)
- **Trading docs (synced from GitHub every 5 min):** `/opt/openclaw/workspace/trading_docs/`
- **Logs:** `/var/log/committee_bridge.log`, `/var/log/trading_docs_sync.log`

**Current model:** `claude-sonnet-4-5-20250929` (line 94 of pivot2_committee.py)
**Current call structure:** 5 sequential calls (TORO → URSA → TECHNICALS → PYTHIA → PIVOT)
**Current daily cap:** 10 auto-runs/day
**Current cron:** `*/3 13-20 * * 1-5` (every 3 min during market hours weekdays)

You access the VPS via the `ssh-vps:exec` tool. Note: the tool has a **1000 character command limit** — for anything longer, write a script to `/tmp/` first via heredoc and then execute it.

---

## TIER 1 — IMMEDIATE FIXES (30 minutes)

### 1.1 — Update committee model to Sonnet 4.6

**File:** `/opt/openclaw/workspace/scripts/pivot2_committee.py`
**Find (line 94):**
```python
COMMITTEE_MODEL = "claude-sonnet-4-5-20250929"
```
**Replace with:**
```python
COMMITTEE_MODEL = "claude-sonnet-4-6"
```

**Verify:** `python3 -c "import sys; sys.path.insert(0,'/opt/openclaw/workspace/scripts'); from pivot2_committee import COMMITTEE_MODEL; print(COMMITTEE_MODEL)"`

### 1.2 — Move GitHub PAT from sync script to env file

**Current state:** `/opt/openclaw/workspace/scripts/sync_trading_docs.sh` has `TOKEN="ghp_..."` hardcoded.

**Steps:**
1. Read the current PAT from the script
2. Append `GITHUB_PAT=<value>` to `/etc/openclaw/openclaw.env` (as root via sudo if needed)
3. Modify the sync script to source the env file:

```bash
#!/bin/bash
source /etc/openclaw/openclaw.env
TOKEN="$GITHUB_PAT"
DEST="/opt/openclaw/workspace/trading_docs"
REPO="303webhouse/pandoras-box"
for f in trading-memory.md open-positions.md macro-economic-data.md; do
  curl -sH "Authorization: token $TOKEN" \
    "https://api.github.com/repos/$REPO/contents/docs/$f?ref=main" \
    | python3 -c "import sys,json,base64; d=json.load(sys.stdin); open('$DEST/$f','w').write(base64.b64decode(d['content']).decode())"
done
echo "Synced at $(date)"
```

**Verify:** Run the sync script manually and confirm files refresh: `/opt/openclaw/workspace/scripts/sync_trading_docs.sh && ls -la /opt/openclaw/workspace/trading_docs/`

### 1.3 — Remove OpenRouter env var (dead config)

**Current:** `/etc/openclaw/openclaw.env` contains `OPENROUTER_API_KEY=...` but it's only referenced in test files (`test_03c_buttons.py`, `test_committee_03b.py`), not the production pipeline.

**Action:**
1. Remove the `OPENROUTER_API_KEY` line from `/etc/openclaw/openclaw.env`
2. Verify no production scripts break: `grep -rn "OPENROUTER_API_KEY" /opt/openclaw/workspace/scripts/ | grep -v test`

**Expected output:** Empty (no production code uses it).

### 1.4 — Diagnose bridge dormancy

**Issue:** No successful committee runs in `/var/log/committee_bridge.log` since March 31, 2026. Either signals aren't qualifying for the queue, or there's a silent failure.

**Investigation steps:**
1. Check the bridge daily count file: `cat /opt/openclaw/workspace/data/bridge_daily_count.json`
2. Check if Railway is returning any signals to the queue:
   ```bash
   source /etc/openclaw/openclaw.env
   curl -sH "X-API-Key: $PIVOT_API_KEY" "$PANDORA_API_URL/api/committee/queue" | python3 -m json.tool | head -50
   ```
3. Check for any errors in the bridge log: `grep -i "error\|exception\|failed" /var/log/committee_bridge.log | tail -20`
4. Check the queue endpoint exists on Railway side. Look for the route in `C:\trading-hub\backend\` — it should be in something like `committee_queue.py` or `routes/committee.py`.

**Likely root causes (in order of probability):**
- The signal threshold for queueing is too high (no signals qualify)
- The queue endpoint was renamed/moved on Railway
- The bridge is hitting the daily cap immediately and exiting (check for stale `bridge_daily_count.json`)

**Fix:** Document what you find in a comment block at the top of `committee_railway_bridge.py` and either lower the threshold, fix the endpoint reference, or reset the daily count.

---

## TIER 2 — ARCHITECTURAL CHANGES (90 minutes)

### 2.1 — Restore the combined analyst call (5 calls → 2 calls)

**Background:** The bridge logs show that on March 19, 2026, there was a "combined analyst agent (TORO + URSA + TECHNICALS)" call that produced a 3081-char response in a single API call. This was reverted by March 31 back to individual calls. The combined approach cuts API cost by ~60%.

**Current structure** (`pivot2_committee.py`, lines 720-950, function `run_committee`):
- 5 sequential calls: TORO, URSA, TECHNICALS, PYTHIA, PIVOT
- Each gets the same `base_context`
- PIVOT gets all four prior responses concatenated

**Target structure:**
- Call 1: COMBINED ANALYST (TORO + URSA + TECHNICALS + PYTHIA in one call)
- Call 2: PIVOT (synthesis with combined output as context)

**Implementation:**

1. **Add a new combined system prompt** to `/opt/openclaw/workspace/scripts/committee_prompts.py`. Append at the end:

```python
COMBINED_ANALYST_SYSTEM_PROMPT = """You are running 4 distinct analyst perspectives on a trading signal in a single response. Output ALL FOUR sections in order, separated exactly as shown.

You will produce:
1. TORO (bull case)
2. URSA (bear case + risks)
3. TECHNICALS (chart structure assessment)
4. PYTHIA (market profile / auction state)

Each analyst has different expertise — do NOT blur them together. TORO finds bullish factors, URSA finds risks, TECHNICALS reads the chart, PYTHIA reads volume profile. They should reach DIFFERENT conclusions if the data supports it.

[INSERT FULL TORO RULES HERE — copy from TORO_SYSTEM_PROMPT, remove the "## OUTPUT FORMAT" section]

[INSERT FULL URSA RULES HERE — copy from URSA_SYSTEM_PROMPT, remove the "## OUTPUT FORMAT" section]

[INSERT FULL TECHNICALS RULES HERE — copy from TECHNICALS_SYSTEM_PROMPT, remove the "## OUTPUT FORMAT" section]

[INSERT FULL PYTHIA RULES HERE — copy from PYTHIA_SYSTEM_PROMPT, remove the "## OUTPUT FORMAT" section]

## REQUIRED OUTPUT FORMAT (follow EXACTLY)

=== TORO ===
ANALYSIS: <3-5 sentence bull case>
CONVICTION: <HIGH|MEDIUM|LOW>

=== URSA ===
ANALYSIS: <3-5 sentence bear case>
CONVICTION: <HIGH|MEDIUM|LOW>

=== TECHNICALS ===
ANALYSIS: <3-5 sentence technical assessment>
CONVICTION: <HIGH|MEDIUM|LOW>

=== PYTHIA ===
STRUCTURE: <auction state>
LEVELS: <key MP levels>
ANALYSIS: <2-3 sentences>
CONVICTION: <HIGH|MEDIUM|LOW>

Each section is independent. Do not summarize across sections — that's PIVOT's job, not yours."""
```

CC: You'll need to actually copy the rule sections from each existing prompt into the placeholders. The total combined prompt will be around 25-30K chars.

2. **Add a parser** for the combined response to `committee_parsers.py`. Append:

```python
def parse_combined_analysts(raw: str) -> dict:
    """Parse a combined TORO+URSA+TECHNICALS+PYTHIA response into 4 dicts."""
    sections = {}
    current = None
    buffer = []
    for line in raw.split("\n"):
        if line.strip() in ("=== TORO ===", "=== URSA ===", "=== TECHNICALS ===", "=== PYTHIA ==="):
            if current:
                sections[current] = "\n".join(buffer).strip()
            current = line.strip().replace("=", "").strip()
            buffer = []
        else:
            buffer.append(line)
    if current:
        sections[current] = "\n".join(buffer).strip()

    return {
        "toro": parse_analyst_response(sections.get("TORO", ""), "TORO"),
        "ursa": parse_analyst_response(sections.get("URSA", ""), "URSA"),
        "technicals": parse_analyst_response(sections.get("TECHNICALS", ""), "TECHNICALS"),
        "pythia": parse_analyst_response(sections.get("PYTHIA", ""), "PYTHIA"),
    }
```

3. **Modify `run_committee` in `pivot2_committee.py`** to use the combined call. Replace the four individual analyst call blocks (TORO, URSA, TECHNICALS, PYTHIA — roughly lines 805-880) with:

```python
# ── COMBINED ANALYSTS (TORO + URSA + TECHNICALS + PYTHIA in one call) ──
log.info("Calling combined analyst agent (TORO + URSA + TECHNICALS + PYTHIA)...")
from committee_prompts import COMBINED_ANALYST_SYSTEM_PROMPT
from committee_parsers import parse_combined_analysts

combined_raw = call_agent(
    system_prompt=COMBINED_ANALYST_SYSTEM_PROMPT,
    user_message=base_context,
    api_key=api_key,
    max_tokens=2500,  # 4 analysts × ~600 tokens each
    temperature=0.3,
    agent_name="ANALYSTS",
    model=COMMITTEE_MODEL,
)

if combined_raw:
    parsed = parse_combined_analysts(combined_raw)
    toro_response = parsed["toro"]
    ursa_response = parsed["ursa"]
    technicals_response = parsed["technicals"]
    pythia_response = parsed["pythia"]
else:
    fallback = {"agent": "?", "analysis": "[ANALYSIS UNAVAILABLE — combined call timed out]", "conviction": "MEDIUM"}
    toro_response = {**fallback, "agent": "TORO"}
    ursa_response = {**fallback, "agent": "URSA"}
    technicals_response = {**fallback, "agent": "TECHNICALS"}
    pythia_response = {**fallback, "agent": "PYTHIA"}
```

4. **Keep the PIVOT call unchanged** — it still gets the four analyst reports concatenated.

5. **Test the combined call** with a real signal. You can manually invoke a committee review by:
```bash
source /etc/openclaw/openclaw.env
cd /opt/openclaw/workspace/scripts
python3 -c "
import os
os.environ.setdefault('ANTHROPIC_API_KEY', '$ANTHROPIC_API_KEY')
from committee_railway_bridge import process_one_signal
# fetch a test signal manually or pull from queue
"
```

**Verification:** After the change, the committee log should show 2 API calls per review instead of 5: `[ANALYSTS] Response received` followed by `[PIVOT] Response received`.

### 2.2 — Personalize trading doc injection per agent

**Background:** Currently `_load_trading_docs()` in `committee_context.py` returns the full 28K of trading docs to every agent. Most agents only need a subset.

**Strategy:**
- **Combined analysts** (TORO/URSA/TECHNICALS/PYTHIA): get positions + don'ts + anti-bias rule (~7K total)
- **PIVOT**: gets the full 28K (memory + positions + macro)

**Implementation in `committee_context.py`:**

Replace the current `_load_trading_docs()` function with two functions:

```python
TRADING_DOCS_DIR = Path("/opt/openclaw/workspace/trading_docs")

def _load_trading_docs_full() -> str:
    """Full context for PIVOT — memory + positions + macro."""
    parts = []
    for fn in ['trading-memory.md', 'open-positions.md', 'macro-economic-data.md']:
        try:
            parts.append((TRADING_DOCS_DIR / fn).read_text())
        except Exception:
            pass
    return "## TRADING CONTEXT\n" + "\n---\n".join(parts) if parts else ""


def _load_trading_docs_lite() -> str:
    """Compressed context for analysts — positions + key rules only."""
    parts = []

    # Always include open positions
    try:
        parts.append((TRADING_DOCS_DIR / "open-positions.md").read_text())
    except Exception:
        pass

    # Extract just the don'ts and anti-bias sections from trading-memory.md
    try:
        memory = (TRADING_DOCS_DIR / "trading-memory.md").read_text()
        # Find the DON'TS section
        if "## 🚫 DON'TS" in memory:
            start = memory.index("## 🚫 DON'TS")
            end = memory.index("---", start) if "---" in memory[start:] else len(memory)
            parts.append(memory[start:end].strip())
        # Find the ANTI-CONFIRMATION BIAS section
        if "## 🔍 ANTI-CONFIRMATION BIAS" in memory:
            start = memory.index("## 🔍 ANTI-CONFIRMATION BIAS")
            end = memory.index("---", start) if "---" in memory[start:] else len(memory)
            parts.append(memory[start:end].strip())
    except Exception:
        pass

    return "## TRADING CONTEXT (compressed)\n" + "\n---\n".join(parts) if parts else ""
```

Then modify `format_signal_context()` to accept an `agent_type` parameter:

```python
def format_signal_context(signal: dict, context: dict, agent_type: str = "analyst") -> str:
    # ... existing code ...

    # Inject trading docs based on agent type
    if agent_type == "pivot":
        td = _load_trading_docs_full()
    else:
        td = _load_trading_docs_lite()
    if td:
        sections.append(td)

    return "\n\n".join(sections)
```

In `pivot2_committee.py`, update the calls:
- For the combined analyst call: `base_context = format_signal_context(signal, context, agent_type="analyst")`
- For the PIVOT call: pivot context already builds on top of base_context, but rebuild it with `agent_type="pivot"`:
  ```python
  pivot_base = format_signal_context(signal, context, agent_type="pivot")
  pivot_context = f"{pivot_base}\n\n## TORO ANALYST REPORT\n..."  # rest unchanged
  ```

**Verification:** Test loader sizes:
```python
python3 -c "
import sys
sys.path.insert(0, '/opt/openclaw/workspace/scripts')
from committee_context import _load_trading_docs_full, _load_trading_docs_lite
print(f'Full: {len(_load_trading_docs_full())} chars')
print(f'Lite: {len(_load_trading_docs_lite())} chars')
"
```
Expected: Full ~28K, Lite ~7K.

### 2.3 — Wire pythia_events DB query into committee context

**Background:** The new `pythia_events` table on Railway Postgres now stores rich Pythia profile events. The committee should pull the last 3-5 events for the signal ticker to give PYTHIA real data to work with.

**Implementation in `committee_context.py`:**

Add a new function:

```python
def fetch_pythia_events(ticker: str, limit: int = 5) -> str:
    """Fetch recent Pythia events for a ticker from Railway Postgres."""
    if not ticker:
        return ""
    try:
        import psycopg2
        DATABASE_URL = os.environ.get("DATABASE_URL", "")
        if not DATABASE_URL:
            return ""
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10, sslmode="require")
        cur = conn.cursor()
        cur.execute("""
            SELECT alert_type, price, va_migration, poor_high, poor_low,
                   volume_quality, ib_high, ib_low, interpretation, timestamp
            FROM pythia_events
            WHERE ticker = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """, (ticker.upper(), limit))
        rows = cur.fetchall()
        conn.close()
        if not rows:
            return ""
        lines = [f"## RECENT PYTHIA EVENTS — {ticker}"]
        for r in rows:
            ts = str(r[9])[:19]
            lines.append(
                f"  {ts} | {r[0]:20s} | ${r[1]} | "
                f"VA-mig: {r[2]} | PH:{r[3]} PL:{r[4]} | vol:{r[5]} | IB:{r[6]}-{r[7]}"
            )
            if r[8]:
                lines.append(f"    >> {r[8][:100]}")
        return "\n".join(lines)
    except Exception as e:
        _log.warning(f"fetch_pythia_events failed: {e}")
        return ""
```

Then in `pivot2_committee.py`, after `format_signal_context()` is called, inject the Pythia events:

```python
# After base_context is built and other context blocks injected:
try:
    from committee_context import fetch_pythia_events
    pythia_events_block = fetch_pythia_events(signal.get("ticker", ""))
    if pythia_events_block:
        base_context = base_context + "\n\n" + pythia_events_block
except Exception as e:
    log.warning("Failed to inject Pythia events: %s", e)
```

**Add DATABASE_URL to env file:**
```bash
echo 'DATABASE_URL=postgresql://postgres:sioMAUjhdgNYWwZMZbkbcSyaAcwdJMty@trolley.proxy.rlwy.net:25012/railway' >> /etc/openclaw/openclaw.env
```

**Verify psycopg2 is installed:** `python3 -c "import psycopg2; print(psycopg2.__version__)"` — if missing, `pip3 install psycopg2-binary`.

### 2.4 — Add Pivot output to Railway API

**Background:** Currently committee reviews go to Discord but Claude.ai can't query historical reviews without scrolling Discord.

**Two parts:**

**A. Railway side** — Add a new endpoint to Pandoras Box backend:

Create `backend/api/committee_history.py`:
```python
from fastapi import APIRouter, Header, HTTPException
from typing import Optional
from backend.database.postgres_client import get_postgres_client

router = APIRouter()

@router.get("/api/committee/history")
def get_committee_history(ticker: Optional[str] = None, limit: int = 20, x_api_key: str = Header(...)):
    if x_api_key != os.environ.get("API_KEY"):
        raise HTTPException(status_code=401, detail="Invalid API key")
    conn = get_postgres_client()
    cur = conn.cursor()
    if ticker:
        cur.execute("""
            SELECT signal_id, ticker, action, conviction, synthesis, invalidation, timestamp
            FROM committee_recommendations
            WHERE ticker = %s
            ORDER BY timestamp DESC LIMIT %s
        """, (ticker.upper(), limit))
    else:
        cur.execute("""
            SELECT signal_id, ticker, action, conviction, synthesis, invalidation, timestamp
            FROM committee_recommendations
            ORDER BY timestamp DESC LIMIT %s
        """, (limit,))
    rows = cur.fetchall()
    return {"recommendations": [dict(zip([d[0] for d in cur.description], r)) for r in rows]}
```

Create the table migration in `backend/database/migrations/`:
```sql
CREATE TABLE IF NOT EXISTS committee_recommendations (
    id SERIAL PRIMARY KEY,
    signal_id VARCHAR(100) UNIQUE NOT NULL,
    ticker VARCHAR(20) NOT NULL,
    action VARCHAR(20),
    conviction VARCHAR(20),
    synthesis TEXT,
    invalidation TEXT,
    structure TEXT,
    levels TEXT,
    size TEXT,
    raw_json JSONB,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_committee_recs_ticker ON committee_recommendations(ticker);
CREATE INDEX IF NOT EXISTS idx_committee_recs_timestamp ON committee_recommendations(timestamp DESC);
```

Wire the new router into `backend/main.py`.

**B. VPS side** — Modify `committee_railway_bridge.py` to POST results to the new endpoint after each committee review:

Find the section that POSTs results back to Railway (look for `urllib.request` or `POST`) and add a call to the new `/api/committee/history` endpoint to store the recommendation. The bridge already POSTs results somewhere — extend that to also write to the history table.

**Verify:** After running a committee review, query the endpoint:
```bash
curl -sH "X-API-Key: rLl-7i2GqGjie5in9iHIlVtqlP5zpY7D5E6-8tzlNSk" \
  "https://pandoras-box-production.up.railway.app/api/committee/history?limit=5" | python3 -m json.tool
```

---

## TIER 3 — CLEANUP & CONSOLIDATION (45 minutes)

### 3.1 — Strip OpenClaw to essentials

**Goal:** Remove dead code and rename the directory to clarify purpose.

**Audit results from the architecture review:**
- `/opt/openclaw/workspace/knowledge/books/` — empty, never populated
- `/opt/openclaw/workspace/knowledge/papers/` — empty, never populated
- `/opt/openclaw/workspace/skills/memory/` — SQLite recall/capture/postmortem, NOT used by committee pipeline
- `/opt/openclaw/workspace/skills/knowledge/` — ingest/query, NOT used by committee pipeline
- `/opt/openclaw/workspace/.openclaw/workspace-state.json` — 70 bytes, vestigial
- `/home/openclaw/.openclaw/memory/main.sqlite` — 78K, never queried by committee

**Action steps:**

1. **Backup first:** `tar -czf /root/openclaw-pre-cleanup-$(date +%Y%m%d).tgz /opt/openclaw/workspace/`

2. **Verify nothing in production references the dead code:**
```bash
grep -rn "skills/memory\|skills/knowledge\|knowledge/books\|knowledge/papers" /opt/openclaw/workspace/scripts/ | grep -v test
```
If empty, proceed. If anything is found, do NOT delete those imports.

3. **Delete dead directories:**
```bash
rm -rf /opt/openclaw/workspace/knowledge/books
rm -rf /opt/openclaw/workspace/knowledge/papers
rm -rf /opt/openclaw/workspace/skills/memory
rm -rf /opt/openclaw/workspace/skills/knowledge
rm -rf /opt/openclaw/workspace/.openclaw
rm -rf /home/openclaw/.openclaw/memory
```

4. **Document what's actually used.** Create `/opt/openclaw/workspace/README.md`:
```markdown
# Pivot II — Trading Committee VPS

This is the VPS deployment of Pivot's automated trading committee.

## Active Components
- `scripts/committee_railway_bridge.py` — Polls Railway every 3 min for queued signals
- `scripts/pivot2_committee.py` — Runs the 2-call committee pipeline (combined analysts + PIVOT)
- `scripts/committee_context.py` — Builds the user message context with trading docs
- `scripts/committee_prompts.py` — System prompts for all agents
- `scripts/committee_parsers.py` — Anthropic API call wrapper + response parsers
- `scripts/sync_trading_docs.sh` — Pulls trading-memory.md, open-positions.md, macro-economic-data.md from GitHub every 5 min
- `trading_docs/` — Synced trading context (read by committee_context)

## Cron Jobs
- `*/5 * * * *` — sync_trading_docs.sh
- `*/3 13-20 * * 1-5` — committee_railway_bridge.py (market hours)

## Data Files
- `data/twitter_signals.jsonl` — Twitter sentiment cache (rotated weekly by cron)
- `data/pending_signals.json` — Bridge state (truncated to 7 days by cron)
- `data/agent_accuracy.json` — Per-agent feedback (updated by feedback loop)

## Environment
- `/etc/openclaw/openclaw.env` — All API keys and config
```

5. **Optional: Rename `openclaw` to `pivot`.** This is risky because all paths in the scripts hardcode `/opt/openclaw/`. Either:
   - Skip the rename (leave the directory name, just update the README), OR
   - Create a symlink: `ln -s /opt/openclaw /opt/pivot` (gives both names without breaking anything)

   Recommend the symlink approach.

### 3.2 — Add file rotation crons

**Issue:** `pending_signals.json` is 687K and growing. `twitter_signals.jsonl` is 455K and growing.

**Create rotation script** `/opt/openclaw/workspace/scripts/rotate_data_files.sh`:
```bash
#!/bin/bash
# Daily rotation of growing data files

DATA_DIR="/opt/openclaw/workspace/data"
LOG="/var/log/data_rotation.log"

# 1. Truncate twitter_signals.jsonl to last 48 hours
TWITTER_FILE="$DATA_DIR/twitter_signals.jsonl"
if [ -f "$TWITTER_FILE" ]; then
    CUTOFF=$(date -u -d '48 hours ago' '+%Y-%m-%dT%H:%M:%S')
    python3 -c "
import json
from pathlib import Path
import datetime as dt
cutoff = dt.datetime.fromisoformat('$CUTOFF').replace(tzinfo=dt.timezone.utc)
keep = []
for line in Path('$TWITTER_FILE').read_text().splitlines():
    try:
        rec = json.loads(line)
        ts = dt.datetime.fromisoformat(rec.get('timestamp', '').replace('Z', '+00:00'))
        if ts >= cutoff:
            keep.append(line)
    except:
        pass
Path('$TWITTER_FILE').write_text('\n'.join(keep) + '\n')
print(f'twitter_signals.jsonl: kept {len(keep)} lines')
" >> $LOG 2>&1
fi

# 2. Truncate pending_signals.json to last 7 days
PENDING_FILE="$DATA_DIR/pending_signals.json"
if [ -f "$PENDING_FILE" ]; then
    python3 -c "
import json
from pathlib import Path
import datetime as dt
cutoff = (dt.datetime.utcnow() - dt.timedelta(days=7)).isoformat()
data = json.loads(Path('$PENDING_FILE').read_text())
if isinstance(data, dict):
    pruned = {k: v for k, v in data.items() if isinstance(v, dict) and v.get('timestamp', '') >= cutoff}
    Path('$PENDING_FILE').write_text(json.dumps(pruned, indent=2))
    print(f'pending_signals.json: kept {len(pruned)} entries')
" >> $LOG 2>&1
fi

echo "Rotation completed at $(date)" >> $LOG
```

**Add cron:**
```bash
(crontab -l 2>/dev/null; echo "0 6 * * * /opt/openclaw/workspace/scripts/rotate_data_files.sh") | crontab -
```

(Runs daily at 6 AM UTC.)

### 3.3 — Caching layer for UW flow and MP levels

**Background:** `build_uw_flow_context()` and `build_mp_levels_context()` are called for every signal, hitting Railway API each time. With multiple signals close together, this is wasteful.

**Implementation:** Use a simple in-memory dict cache with TTL. Add to top of `committee_context.py`:

```python
import time as _time

_uw_flow_cache: dict = {}
_mp_levels_cache: dict = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


def _get_cached(cache: dict, key: str):
    entry = cache.get(key)
    if entry and (_time.time() - entry["ts"]) < _CACHE_TTL_SECONDS:
        return entry["value"]
    return None


def _set_cached(cache: dict, key: str, value):
    cache[key] = {"value": value, "ts": _time.time()}
```

Then wrap the existing `build_uw_flow_context()` and `build_mp_levels_context()` functions to check the cache first. The cache key should be the ticker.

### 3.4 — Reactivate the agent feedback loop

**Background:** `data/agent_accuracy.json` hasn't been updated since February. The feedback loop needs to be re-wired to update accuracy scores when Nick takes/passes on committee recommendations.

**Investigation steps:**
1. Read `data/agent_accuracy.json` to see the structure
2. Find where `_get_agent_feedback_context()` is defined (should be in `committee_context.py` or `pivot2_committee.py`)
3. Find where outcomes are recorded — there's a `committee_outcomes.py` script that handles this
4. Check if `committee_outcomes.py` is currently scheduled in cron — if not, add it

**Create a daily outcome processor cron:**
```bash
(crontab -l 2>/dev/null; echo "30 21 * * 1-5 cd /opt/openclaw/workspace/scripts && python3 committee_outcomes.py >> /var/log/committee_outcomes.log 2>&1") | crontab -
```

(Runs at 9:30 PM ET / 1:30 AM UTC after market close.)

**Verify:** After a few committee runs, `agent_accuracy.json` should update with new outcome data.

---

## TIER 4 — FUTURE ENHANCEMENTS (60 minutes)

### 4.1 — Token budgeting instead of run capping

**Current:** Bridge has a hard cap of 10 runs per day.

**New:** Replace with token budgeting — 50,000 input tokens per hour, 200,000 input tokens per day.

**Implementation in `committee_railway_bridge.py`:**

Add to the top:
```python
TOKEN_BUDGET_HOURLY = 50000
TOKEN_BUDGET_DAILY = 200000
TOKEN_USAGE_FILE = DATA_DIR / "token_usage.json"
```

Add a token tracking function:
```python
def estimate_tokens(text: str) -> int:
    """Rough estimate: 1 token ≈ 4 chars for English."""
    return len(text) // 4

def check_token_budget(estimated_input_tokens: int) -> bool:
    """Returns True if we have budget."""
    now = datetime.utcnow()
    try:
        usage = json.loads(TOKEN_USAGE_FILE.read_text()) if TOKEN_USAGE_FILE.exists() else {}
    except Exception:
        usage = {}

    hour_key = now.strftime("%Y-%m-%dT%H")
    day_key = now.strftime("%Y-%m-%d")

    hour_usage = usage.get(hour_key, 0)
    day_usage = sum(v for k, v in usage.items() if k.startswith(day_key))

    if hour_usage + estimated_input_tokens > TOKEN_BUDGET_HOURLY:
        log.warning(f"Hourly token budget exceeded: {hour_usage}/{TOKEN_BUDGET_HOURLY}")
        return False
    if day_usage + estimated_input_tokens > TOKEN_BUDGET_DAILY:
        log.warning(f"Daily token budget exceeded: {day_usage}/{TOKEN_BUDGET_DAILY}")
        return False
    return True

def record_token_usage(input_tokens: int):
    now = datetime.utcnow()
    hour_key = now.strftime("%Y-%m-%dT%H")
    try:
        usage = json.loads(TOKEN_USAGE_FILE.read_text()) if TOKEN_USAGE_FILE.exists() else {}
    except Exception:
        usage = {}
    usage[hour_key] = usage.get(hour_key, 0) + input_tokens
    # Prune entries older than 7 days
    cutoff = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    usage = {k: v for k, v in usage.items() if k >= cutoff}
    TOKEN_USAGE_FILE.write_text(json.dumps(usage, indent=2))
```

Replace the daily count check (`check_budget(daily)`) with a token budget check. Estimate tokens before calling `run_committee()`, and record actual usage after.

### 4.2 — Audit logging with content hashes

**Implementation:** Add to `pivot2_committee.py` at the start of `run_committee()`:

```python
import hashlib
from pathlib import Path

AUDIT_LOG = Path("/var/log/committee_audit.log")

def _audit_log(signal_id: str, agent: str, system_prompt: str, user_message: str):
    sys_hash = hashlib.sha256(system_prompt.encode()).hexdigest()[:12]
    user_hash = hashlib.sha256(user_message.encode()).hexdigest()[:12]
    line = f"{datetime.utcnow().isoformat()} | {signal_id} | {agent} | sys={sys_hash} | user={user_hash} | sys_chars={len(system_prompt)} | user_chars={len(user_message)}\n"
    try:
        with open(AUDIT_LOG, "a") as f:
            f.write(line)
    except Exception:
        pass
```

Call `_audit_log()` before each `call_agent()` invocation.

### 4.3 — Pre-market scheduled committee runs

**Background:** Currently the bridge only runs when signals queue. Nick's actual workflow includes pre-market analysis at 7:30-9:00 AM ET.

**Implementation:** Create a new script `/opt/openclaw/workspace/scripts/premarket_briefing.py` that:
1. Pulls top 3-5 signals from the last 24 hours from Railway
2. Pulls Nick's open positions from the trading docs
3. Pulls macro headlines from the twitter cache
4. Runs a single PIVOT-only synthesis (no analysts) on the day's setup
5. Posts the result to Discord and the new committee history endpoint

**Cron:** `30 11 * * 1-5` (11:30 UTC = 7:30 AM ET, weekdays)

This is a full feature build — write the brief, but flag that it's optional and can be done in a follow-up session if Tier 1-3 is enough scope for now.

---

## ORDER OF OPERATIONS

**Recommended sequence for CC:**

1. **Tier 1 first** — these are independent fixes, all low risk. Do all four (1.1-1.4) before moving on.
2. **Tier 2 next, in this order:**
   - 2.1 (combined analyst call) — biggest impact, must work before 2.2
   - 2.2 (personalized context) — depends on 2.1 being deployed
   - 2.3 (Pythia events DB query) — independent, can be done in parallel with 2.2
   - 2.4 (Railway history endpoint) — independent, but requires Railway deploy
3. **Verify Tier 1+2 with a real committee run** before proceeding to Tier 3
4. **Tier 3** — cleanup, low risk but do AFTER verifying the new architecture works
5. **Tier 4** — optional, can be deferred to a follow-up session

## ACCEPTANCE CRITERIA

After completing Tier 1+2:
- [ ] Committee model is `claude-sonnet-4-6`
- [ ] GitHub PAT lives in env file, not in script
- [ ] OpenRouter env var removed
- [ ] Bridge dormancy root cause documented
- [ ] Combined analyst call working (2 API calls per review, not 5)
- [ ] Trading docs personalized (analysts get ~7K, PIVOT gets ~28K)
- [ ] `pythia_events` table queried per signal
- [ ] Committee history endpoint deployed to Railway
- [ ] Manual test committee review completes successfully
- [ ] Committee bridge log shows: `[ANALYSTS] Response received` followed by `[PIVOT] Response received`

After completing Tier 3:
- [ ] Dead directories removed
- [ ] README.md created at `/opt/openclaw/workspace/README.md`
- [ ] File rotation cron active
- [ ] UW flow and MP levels caching working
- [ ] Agent feedback cron scheduled

After completing Tier 4 (optional):
- [ ] Token budgeting replaces run capping
- [ ] Audit log writing to `/var/log/committee_audit.log`
- [ ] Pre-market briefing script deployed and scheduled

## ROLLBACK PLAN

If anything breaks:
1. **Tier 1 rollback:** Revert the model line in `pivot2_committee.py`. Restore the original sync script from backup.
2. **Tier 2 rollback:** The combined analyst code is additive — keep the old 5-call code commented out for one week before deleting.
3. **Tier 3 rollback:** Restore from `/root/openclaw-pre-cleanup-*.tgz` backup.

## NOTES FOR CC

- The ssh-vps:exec tool has a 1000 character limit. For long commands, write to `/tmp/script.sh` or `/tmp/patch.py` first via heredoc, then execute.
- Use `python3 -c "..."` for Python one-liners but escape single quotes carefully.
- Always verify syntax after editing Python files: `python3 -c "import py_compile; py_compile.compile('/path/to/file.py', doraise=True); print('OK')"`
- The committee bridge runs every 3 minutes — if you make changes during market hours, your changes will be picked up on the next cron tick automatically.
- All file edits should be tested with a manual import before relying on cron to pick them up.
- After completing each Tier, push a commit to GitHub with format: `pivot: complete brief tier N - <summary>`
