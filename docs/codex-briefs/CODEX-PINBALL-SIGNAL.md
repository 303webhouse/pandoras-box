# Codex Brief: Raschke Pinball Signal Integration

## What Is Pinball?

A mean-reversion signal based on where the market closes relative to its daily range. Close near the high → expect pullback (Pinball Sell). Close near the low → expect bounce (Pinball Buy). It is **supplemental context only** — never a standalone trade recommendation.

## Scope

- New collector: `pivot/collectors/pinball.py`
- Storage: local file `pivot/state/pinball.json` (NOT a bias factor — do NOT use `post_factor`)
- Schedule: runs after market close
- Surfaces in: morning brief, first-hour chat context, EOD brief mention
- Instruments: ES=F, NQ=F (via yfinance, already available)

## Files to Create

### `pivot/collectors/pinball.py`

New file. Follow the same pattern as other collectors (uses `base_collector.get_price_history`).

```python
"""
Raschke Pinball signal detector.

Calculates close_position = (close - low) / (high - low) for ES and NQ.
Stores result in state/pinball.json (NOT a bias factor).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_collector import get_price_history

logger = logging.getLogger(__name__)

STATE_PATH = Path(__file__).resolve().parents[1] / "state" / "pinball.json"

# Thresholds (tunable)
SELL_THRESHOLD = 0.80  # Close in top 20% of range
BUY_THRESHOLD = 0.20   # Close in bottom 20% of range

INSTRUMENTS = {
    "ES": "ES=F",
    "NQ": "NQ=F",
}


def _compute_pinball(ohlc_row: Dict[str, float]) -> Dict[str, Any]:
    """
    Compute pinball signal from a single OHLC bar.
    Returns dict with signal, close_position, and raw OHLC.
    """
    high = ohlc_row["high"]
    low = ohlc_row["low"]
    close = ohlc_row["close"]

    # Avoid division by zero on flat days
    if high == low:
        return {"signal": None, "close_position": 0.5, "ohlc": ohlc_row}

    close_position = (close - low) / (high - low)

    if close_position >= SELL_THRESHOLD:
        signal = "SELL"
    elif close_position <= BUY_THRESHOLD:
        signal = "BUY"
    else:
        signal = None

    return {
        "signal": signal,
        "close_position": round(close_position, 4),
        "ohlc": {
            "open": round(float(ohlc_row.get("open", 0)), 2),
            "high": round(float(high), 2),
            "low": round(float(low), 2),
            "close": round(float(close), 2),
        },
    }


async def collect_pinball() -> Dict[str, Any]:
    """
    Fetch daily OHLC for ES and NQ, compute Pinball signals,
    and save to state/pinball.json.
    
    Returns the full result dict.
    """
    results = {}
    
    for label, ticker in INSTRUMENTS.items():
        try:
            data = await get_price_history(ticker, days=5)
            if data is None or data.empty:
                logger.warning(f"Pinball: no data for {ticker}")
                results[label] = {"signal": None, "error": "no data"}
                continue

            # Get the latest complete daily bar
            latest = data.iloc[-1]
            
            # Ensure we have OHLC columns
            required = {"open", "high", "low", "close"}
            if not required.issubset(set(data.columns)):
                logger.warning(f"Pinball: missing OHLC columns for {ticker}: {list(data.columns)}")
                results[label] = {"signal": None, "error": "missing columns"}
                continue

            ohlc_row = {
                "open": float(latest["open"]),
                "high": float(latest["high"]),
                "low": float(latest["low"]),
                "close": float(latest["close"]),
            }
            
            result = _compute_pinball(ohlc_row)
            results[label] = result
            
            if result["signal"]:
                logger.info(
                    f"Pinball {result['signal']} triggered on {label} "
                    f"(close_position: {result['close_position']})"
                )
            else:
                logger.info(
                    f"Pinball: no signal on {label} "
                    f"(close_position: {result['close_position']})"
                )

        except Exception as exc:
            logger.warning(f"Pinball: failed for {ticker}: {exc}")
            results[label] = {"signal": None, "error": str(exc)}

    # Save to state file
    payload = {
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "computed_at": datetime.utcnow().isoformat(),
        "instruments": results,
    }
    
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info(f"Pinball state saved to {STATE_PATH}")
    except Exception as exc:
        logger.warning(f"Pinball: failed to save state: {exc}")

    return payload


def read_pinball_state() -> Optional[Dict[str, Any]]:
    """
    Read the current Pinball state from disk.
    Returns None if file doesn't exist or is unreadable.
    Used by morning brief, EOD brief, and build_market_context.
    """
    try:
        if STATE_PATH.exists():
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def format_pinball_context(state: Optional[Dict[str, Any]], for_brief: bool = False) -> str:
    """
    Format Pinball state into a human-readable context block.
    
    Args:
        state: Output from read_pinball_state()
        for_brief: If True, return empty string when no signals (briefs skip silent Pinball).
                   If False, always return status (for chat context).
    
    Returns:
        Formatted string for injection into prompts.
    """
    if not state or "instruments" not in state:
        return "" if for_brief else "Pinball Status: unavailable"

    instruments = state["instruments"]
    date = state.get("date", "unknown")
    signals = []

    for label in ["ES", "NQ"]:
        info = instruments.get(label, {})
        signal = info.get("signal")
        close_pos = info.get("close_position")
        
        if signal and close_pos is not None:
            direction = "closed near session high" if signal == "SELL" else "closed near session low"
            signals.append(
                f"{label}: Pinball {signal} triggered (close position: {close_pos:.2f} — {direction})"
            )

    if not signals:
        if for_brief:
            return ""  # Briefs don't mention Pinball if no signal
        return "Pinball Status: no active signals"

    header = "PINBALL STATUS:"
    note = (
        "Note: Pinball is a mean-reversion signal. "
        "Expect potential overnight/early session pullback on SELL triggers, "
        "bounce on BUY triggers. Signal is most relevant in the first hour after open (9:30-10:30 AM ET)."
    )
    
    return f"{header}\n" + "\n".join(signals) + f"\n{note}"
```

**Key design decisions**:
- Uses `state/pinball.json` (same directory as `cooldowns.json`, `bias_shift.json` etc.)
- Does NOT use `post_factor` — Pinball is supplemental context, not a bias engine factor
- `read_pinball_state()` and `format_pinball_context()` are importable by `cron_runner.py` and `bot.py`
- `for_brief=True` returns empty string when no signals (morning brief should stay quiet when there's nothing to report)

## Files to Modify

### 1. `pivot/scheduler/cron_runner.py` — Schedule + inject into briefs

**Add import** at top with other collector imports:

```python
from collectors.pinball import collect_pinball, read_pinball_state, format_pinball_context
```

**Add Pinball collection job** — new async function:

```python
async def run_pinball():
    """Post-close Pinball signal detection."""
    logger.info("Pinball signal detection")
    try:
        result = await collect_pinball()
        instruments = result.get("instruments", {})
        triggered = [k for k, v in instruments.items() if v.get("signal")]
        if triggered:
            logger.info(f"Pinball signals triggered: {triggered}")
    except Exception as exc:
        logger.warning(f"Pinball collection failed: {exc}")
```

**Schedule it** in `start_scheduler()` — add after the `run_sector_strength` line (4:15 PM). Run at 4:20 PM ET so it uses the final daily bar:

```python
scheduler.add_job(run_pinball, CronTrigger(day_of_week="mon-fri", hour=16, minute=20, timezone=TZ))
```

**Modify `morning_brief()`** — inject Pinball context into the data block. After `data_block = json.dumps(composite, indent=2)` and before `prompt = build_morning_brief_prompt(...)`:

```python
        # Pinball context (only included when signals are active)
        pinball_state = read_pinball_state()
        pinball_block = format_pinball_context(pinball_state, for_brief=True)
        if pinball_block:
            data_block = f"{data_block}\n\n{pinball_block}"
```

**Modify `eod_brief()`** — inject Pinball results into the EOD payload. After `payload = {...}` and before `prompt = _repeat_high_stakes_prompt(...)`:

```python
        # Include fresh Pinball computation in EOD
        pinball_state = read_pinball_state()
        if pinball_state:
            payload["pinball"] = pinball_state
            pinball_block = format_pinball_context(pinball_state, for_brief=False)
            if pinball_block:
                payload["pinball_summary"] = pinball_block
```

### 2. `backend/discord_bridge/bot.py` — First-hour chat context

**Add a Pinball reader function** near the top of bot.py. Because bot.py's import path can be tricky on the VPS, use the direct file-based approach:

```python
import json as _json
from pathlib import Path as _Path

_PINBALL_STATE_PATH = _Path(__file__).resolve().parents[1] / "state" / "pinball.json"

def _read_pinball_for_chat() -> str:
    """Read Pinball state and return context string if within first-hour window."""
    now = get_et_now()
    
    # Only inject Pinball context during the first hour: 9:30-10:30 AM ET
    from datetime import time
    if not (time(9, 30) <= now.time() <= time(10, 30)):
        return ""
    
    # Weekday check
    if now.weekday() >= 5:
        return ""

    try:
        if not _PINBALL_STATE_PATH.exists():
            return ""
        state = _json.loads(_PINBALL_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return ""

    if not state or "instruments" not in state:
        return ""

    instruments = state["instruments"]
    signals = []
    for label in ["ES", "NQ"]:
        info = instruments.get(label, {})
        signal = info.get("signal")
        close_pos = info.get("close_position")
        if signal and close_pos is not None:
            direction = "near session high" if signal == "SELL" else "near session low"
            signals.append(f"{label}: Pinball {signal} (close pos {close_pos:.2f} — {direction})")

    if not signals:
        return ""

    return (
        "\n\nPINBALL CONTEXT (first-hour signal — mean reversion):\n"
        + "\n".join(signals)
        + "\nPinball signals are most relevant 9:30-10:30 AM ET. "
        "If a bullish trade aligns with Pinball BUY, that's confirming. "
        "If bullish trade conflicts with Pinball SELL, flag it as conflicting context."
    )
```

**Inject into `build_market_context()`** — at the end of the function, before `return "\n".join(lines)`:

```python
    # Pinball first-hour context (only 9:30-10:30 AM ET)
    pinball_ctx = _read_pinball_for_chat()
    if pinball_ctx:
        lines.append(pinball_ctx)
```

This automatically injects Pinball context into ALL chat interactions during the first hour — including trade evaluations, directional questions, and screenshot analyses — because they all go through `build_market_context()`.

### 3. `pivot/llm/prompts.py` — Update brief prompt instructions

In `build_morning_brief_prompt()`, add a line to the prompt instructions so the LLM knows how to handle Pinball data when it appears. Add after the `"- Key catalysts today..."` line:

```python
        "- Pinball signal status (only if PINBALL STATUS section present in data — "
        "if Pinball Sell triggered, note potential early pullback; "
        "if Pinball Buy triggered, note potential early bounce; "
        "if no Pinball section in data, say nothing about Pinball)\n"
```

In `build_eod_prompt()`, add a line so the EOD brief mentions new Pinball triggers:

```python
        "- Pinball signals (if present in data): note any new triggers as heads-up for tomorrow's first hour\n"
```

## What NOT to Change

- **Bias engine** (`backend/bias_engine/composite.py`) — Pinball is NOT a bias factor, it should never affect the composite score
- **`post_factor()`** — Do not use this for Pinball. It stores to local `state/pinball.json` only.
- **Other collectors** — No changes needed to existing factor collectors
- **Signal pipeline** — Pinball does not generate webhook signals or Discord alerts on its own

## Data Flow Summary

```
4:20 PM ET → cron_runner calls collect_pinball()
           → fetches ES=F, NQ=F daily OHLC via yfinance
           → computes close_position for each
           → writes state/pinball.json

4:30 PM ET → eod_brief() reads state/pinball.json
           → includes in EOD prompt data if signals present
           → LLM mentions as heads-up for tomorrow

10:00 AM ET → morning_brief() reads state/pinball.json  
            → includes in morning brief prompt if signals active
            → LLM calls out expected early-session behavior

9:30-10:30 AM ET → build_market_context() reads state/pinball.json
                  → appends Pinball context to every chat message
                  → LLM uses as confirming/conflicting context for trade signals

After 10:30 AM ET → build_market_context() skips Pinball section
                   → signal expires for chat purposes
```

## `state/pinball.json` Example

```json
{
  "date": "2026-02-19",
  "computed_at": "2026-02-19T21:20:00.123456",
  "instruments": {
    "ES": {
      "signal": "SELL",
      "close_position": 0.87,
      "ohlc": {
        "open": 6040.25,
        "high": 6065.50,
        "low": 6028.00,
        "close": 6060.75
      }
    },
    "NQ": {
      "signal": null,
      "close_position": 0.55,
      "ohlc": {
        "open": 21550.00,
        "high": 21680.00,
        "low": 21490.00,
        "close": 21595.50
      }
    }
  }
}
```

## Testing

1. **Manual run**: SSH to VPS, run `cd /opt/pivot && python -c "import asyncio; from collectors.pinball import collect_pinball; asyncio.run(collect_pinball())"`. Verify `state/pinball.json` gets created with valid data.
2. **Morning brief**: After the next 10:00 AM ET brief, check if Pinball is mentioned (only if a signal was active).
3. **First-hour chat**: During 9:30-10:30 AM ET, ask Pivot about a trade idea. Check if Pinball context appears in the response.
4. **After 10:30 AM**: Same test — Pinball should NOT appear.
5. **No-signal day**: If Pinball doesn't trigger, morning brief should say nothing about it.

## Deployment

```bash
ssh root@188.245.250.2
cd /opt/pivot && git pull origin main
systemctl restart pivot-bot       # picks up bot.py changes
systemctl restart pivot-collector  # picks up cron_runner + pinball collector
journalctl -u pivot-collector -f   # watch for "Pinball signal detection" log at 4:20 PM ET
```

## Definition of Done

- [ ] `pivot/collectors/pinball.py` exists and computes close_position for ES=F and NQ=F
- [ ] `state/pinball.json` gets written after each market close
- [ ] Morning brief includes Pinball context when signals are active, stays silent when not
- [ ] EOD brief mentions new Pinball triggers as tomorrow's heads-up
- [ ] Chat context includes Pinball during 9:30-10:30 AM ET window only
- [ ] Chat context omits Pinball after 10:30 AM ET
- [ ] Pinball does NOT affect the composite bias score
- [ ] No new pip dependencies required
- [ ] Both `pivot-bot` and `pivot-collector` restart cleanly
