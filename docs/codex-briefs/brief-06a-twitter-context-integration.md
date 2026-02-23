# Brief 06A — Twitter Sentiment Context Integration + Chatbot Skill

**Priority:** HIGH — data is being collected but never consumed  
**Effort:** ~30 min  
**Files modified:** 2 existing, 1 new  
**Deploy:** VPS only (`/opt/openclaw/workspace/`) — no Railway changes  

---

## Problem

`pivot2_twitter.py` runs every 30 minutes during market hours, scores tweets from 30+ accounts via Haiku, and writes results to `data/twitter_signals.jsonl`. But:

1. **Committee context builder ignores it.** `committee_context.py` feeds bias, positions, circuit breakers, and earnings to the Trading Team analysts — but zero Twitter sentiment. The TORO/URSA/Risk/Pivot agents never see what Twitter is saying.
2. **Pivot chatbot has no tool to query it.** When Nick asks "what's Twitter saying?" there's no skill to read the JSONL.
3. **While we're here:** Add `@Citrini7` (Citrini Research — thematic equity / macro, 115K followers) to the tracked accounts list.

---

## Part 1: Inject Twitter sentiment into committee context

**File:** `/opt/openclaw/workspace/scripts/committee_context.py`

### 1A. Add helper function

Insert this function AFTER the existing `_get_recent_lessons_context()` function (after line ~162, before `def get_bias_challenge_context`):

```python
def _get_twitter_sentiment_context(ticker: str | None = None, lookback_hours: int = 2) -> str:
    """Load recent Twitter signals for committee context injection."""
    signals_path = Path("/opt/openclaw/workspace/data/twitter_signals.jsonl")
    try:
        with open(signals_path, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return ""

    import datetime as dt
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=lookback_hours)
    recent = []
    for line in lines[-100:]:  # Only scan last 100 entries for speed
        try:
            entry = json.loads(line.strip())
            ts = dt.datetime.fromisoformat(entry["timestamp"])
            if ts < cutoff:
                continue
            recent.append(entry)
        except (json.JSONDecodeError, KeyError, ValueError):
            continue

    if not recent:
        return ""

    sections = ["\n\n## TWITTER SENTIMENT (last 2 hours)"]

    # Ticker-specific signals first (if we have a ticker)
    if ticker:
        ticker_upper = ticker.upper()
        ticker_hits = [s for s in recent if ticker_upper in [t.upper() for t in s.get("tickers", [])]]
        if ticker_hits:
            sections.append(f"\n### Mentions of {ticker_upper}:")
            for s in ticker_hits[-5:]:
                sections.append(
                    f"- @{s['username']} ({s.get('category','?')}): "
                    f"{s.get('signal','?')} (score: {s.get('score', 0):.1f}) — "
                    f"{s.get('summary', 'no summary')}"
                )

    # Top movers by absolute score
    strong = [s for s in recent if abs(s.get("score", 0)) >= 0.5]
    if strong:
        strong.sort(key=lambda x: abs(x.get("score", 0)), reverse=True)
        sections.append("\n### Strongest signals:")
        for s in strong[:5]:
            sections.append(
                f"- @{s['username']} ({s.get('category','?')}): "
                f"{s.get('signal','?')} (score: {s.get('score', 0):.1f}) — "
                f"{s.get('summary', 'no summary')}"
            )

    # Alert-level items
    alerts = [s for s in recent if s.get("alert")]
    if alerts:
        sections.append("\n### ⚠️ ALERTS:")
        for s in alerts[-3:]:
            sections.append(f"- @{s['username']}: {s.get('summary', 'ALERT')}")

    return "\n".join(sections) if len(sections) > 1 else ""
```

### 1B. Call it in `format_signal_context()`

**Find this exact block** near the end of `format_signal_context()` (around line 136):

```python
    return "\n".join(lines)
```

**Replace with:**

```python
    # Inject Twitter sentiment context
    ticker = signal.get("ticker")
    twitter_ctx = _get_twitter_sentiment_context(ticker=ticker)
    if twitter_ctx:
        lines.append(twitter_ctx)

    # Inject lessons from weekly reviews
    lessons_ctx = _get_recent_lessons_context()
    if lessons_ctx:
        lines.append(lessons_ctx)

    return "\n".join(lines)
```

**IMPORTANT:** Check if `_get_recent_lessons_context()` is already called somewhere else (e.g., in `pivot2_committee.py`). If it's NOT already injected via `format_signal_context`, adding it here is correct. If it IS already called separately in the orchestrator, remove the lessons injection from this block to avoid duplication.

---

## Part 2: Create Pivot chatbot skill for Twitter queries

**New file:** `/opt/openclaw/workspace/skills/twitter/sentiment.py`

Create the directory first: `mkdir -p /opt/openclaw/workspace/skills/twitter`

```python
#!/usr/bin/env python3
"""
sentiment.py — Query recent Twitter sentiment signals
Usage:
  python3 sentiment.py                        # All recent signals
  python3 sentiment.py --ticker SPY           # Filter by ticker
  python3 sentiment.py --category macro       # Filter by category
  python3 sentiment.py --hours 4              # Lookback window
  python3 sentiment.py --strong               # Only |score| >= 0.5
"""
import argparse
import datetime as dt
import json
from pathlib import Path

SIGNAL_LOG = Path("/opt/openclaw/workspace/data/twitter_signals.jsonl")


def load_signals(hours: int = 2, ticker: str | None = None,
                 category: str | None = None, strong_only: bool = False) -> list[dict]:
    if not SIGNAL_LOG.exists():
        return []

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    results = []

    with open(SIGNAL_LOG, "r") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                ts = dt.datetime.fromisoformat(entry["timestamp"])
                if ts < cutoff:
                    continue
                if ticker and ticker.upper() not in [t.upper() for t in entry.get("tickers", [])]:
                    continue
                if category and entry.get("category", "").lower() != category.lower():
                    continue
                if strong_only and abs(entry.get("score", 0)) < 0.5:
                    continue
                results.append(entry)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue

    return results


def format_output(signals: list[dict], hours: int) -> str:
    if not signals:
        return f"No Twitter signals found in the last {hours} hour(s)."

    lines = [f"Twitter sentiment — {len(signals)} signals in last {hours}h:\n"]

    # Group by signal direction
    bullish = [s for s in signals if s.get("score", 0) > 0.2]
    bearish = [s for s in signals if s.get("score", 0) < -0.2]
    neutral = [s for s in signals if -0.2 <= s.get("score", 0) <= 0.2]

    if bullish:
        lines.append(f"BULLISH ({len(bullish)}):")
        for s in sorted(bullish, key=lambda x: x.get("score", 0), reverse=True)[:5]:
            lines.append(f"  @{s['username']} ({s.get('category','')}): {s.get('signal','')} "
                         f"[{s.get('score',0):+.1f}] — {s.get('summary','')}")

    if bearish:
        lines.append(f"\nBEARISH ({len(bearish)}):")
        for s in sorted(bearish, key=lambda x: x.get("score", 0))[:5]:
            lines.append(f"  @{s['username']} ({s.get('category','')}): {s.get('signal','')} "
                         f"[{s.get('score',0):+.1f}] — {s.get('summary','')}")

    if neutral:
        lines.append(f"\nNEUTRAL ({len(neutral)}): {', '.join('@' + s['username'] for s in neutral[:5])}")

    # Ticker summary
    all_tickers: dict[str, list[float]] = {}
    for s in signals:
        for t in s.get("tickers", []):
            all_tickers.setdefault(t.upper(), []).append(s.get("score", 0))
    if all_tickers:
        lines.append("\nTicker mentions:")
        for t, scores in sorted(all_tickers.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
            avg = sum(scores) / len(scores)
            lines.append(f"  {t}: {len(scores)} mentions, avg score {avg:+.2f}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Query Twitter sentiment signals")
    parser.add_argument("--ticker", help="Filter by ticker symbol")
    parser.add_argument("--category", help="Filter by category (flow/macro/policy/tech/strategy/news)")
    parser.add_argument("--hours", type=int, default=2, help="Lookback hours (default: 2)")
    parser.add_argument("--strong", action="store_true", help="Only show strong signals (|score| >= 0.5)")
    args = parser.parse_args()

    signals = load_signals(
        hours=args.hours,
        ticker=args.ticker,
        category=args.category,
        strong_only=args.strong,
    )
    print(format_output(signals, args.hours))


if __name__ == "__main__":
    main()
```

---

## Part 3: Add Citrini Research to tracked accounts

**File:** `/opt/openclaw/workspace/scripts/pivot2_twitter.py`

**Find this exact block** (around line 75):

```python
    # Strategy mentors — highest priority (Nick's primary influences)
    "TheFlowHorse":    {"category": "strategy", "weight": 1.0},  # Ryan Scott / The Stable founder
    "LindaRaschke":    {"category": "strategy", "weight": 1.0},  # Legendary technical trader
```

**Replace with:**

```python
    # Strategy mentors — highest priority (Nick's primary influences)
    "TheFlowHorse":    {"category": "strategy", "weight": 1.0},  # Ryan Scott / The Stable founder
    "LindaRaschke":    {"category": "strategy", "weight": 1.0},  # Legendary technical trader

    # Thematic equity / macro research
    "Citrini7":        {"category": "macro",    "weight": 0.9},  # Citrini Research — megatrend baskets, global macro
```

---

## Verification

After deploying all three changes, run these commands on VPS:

```bash
# 1. Test the new skill directly
python3 /opt/openclaw/workspace/skills/twitter/sentiment.py --hours 24
python3 /opt/openclaw/workspace/skills/twitter/sentiment.py --ticker BTC --hours 24

# 2. Verify Citrini7 is in the accounts list
python3 -c "
import sys; sys.path.insert(0, '/opt/openclaw/workspace/scripts')
from pivot2_twitter import ACCOUNTS
print('Citrini7' in ACCOUNTS, ACCOUNTS.get('Citrini7'))
"

# 3. Verify bird can fetch Citrini tweets
sudo -u openclaw bash -c '
export AUTH_TOKEN=\$(python3 -c "import json; print(json.load(open(\"/home/openclaw/.openclaw/openclaw.json\")).get(\"env\",{}).get(\"AUTH_TOKEN\",\"\"))")
export CT0=\$(python3 -c "import json; print(json.load(open(\"/home/openclaw/.openclaw/openclaw.json\")).get(\"env\",{}).get(\"CT0\",\"\"))")
/home/openclaw/.local/bin/bird --plain user-tweets Citrini7 -n 3 --json 2>&1 | head -20
'

# 4. Dry-run committee context with twitter injection
python3 -c "
import sys; sys.path.insert(0, '/opt/openclaw/workspace/scripts')
from committee_context import format_signal_context
signal = {'ticker': 'BTC', 'direction': 'BEARISH', 'alert_type': 'test', 'score': 75}
context = {'bias_composite': {'bias_level': 'NEUTRAL'}, 'defcon': 3, 'open_positions': {}, 'circuit_breakers': [], 'earnings': {}, 'zone': {}}
result = format_signal_context(signal, context)
# Check if twitter section appears
print('TWITTER SENTIMENT' in result, '— twitter context injected' if 'TWITTER SENTIMENT' in result else '— MISSING, check integration')
"
```

**Expected results:**
- Step 1: Shows formatted Twitter signals with bull/bear grouping
- Step 2: `True {'category': 'macro', 'weight': 0.9}`
- Step 3: Returns JSON array of recent Citrini tweets
- Step 4: `True — twitter context injected`

---

## Post-deploy

1. Append entry to `docs/TRADING_TEAM_LOG.md` per Agent Update Protocol
2. No DEVELOPMENT_STATUS.md change needed (this is a bugfix, not new feature)
3. No systemd restart needed — changes take effect on next committee run and next Pivot message

---

## Known issue (not in scope)

The OpenClaw cron job `pivot2-twitter-sentiment` has 9 consecutive errors ("cron announce delivery failed"). The system crontab is the one actually running the script successfully. The OpenClaw job's `delivery.mode` is set to `"announce"` which is failing. Fix by either:
- Changing delivery mode to `"none"` in `/home/openclaw/.openclaw/cron/jobs.json`
- Or disabling the OpenClaw cron since system crontab handles it

This is cosmetic — the data collection works via system cron regardless.
