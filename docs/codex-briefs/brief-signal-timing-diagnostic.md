# Codex Brief: Signal Timing Diagnostic — "Are We Early, On Time, or Late?"

**Date:** April 9, 2026
**Priority:** HIGH (diagnostic — informs whether signal pipeline needs redesign)
**Scope:** Standalone Python script. No codebase modifications. Read-only against DB + Polygon API.
**Estimated effort:** ~30-45 min agent time
**Output:** JSON report + printed summary table to stdout

---

## Problem

Nick has noticed that the hub's highest-scored signals (score 80-100, the top tier) often seem to fire AFTER a significant portion of the price move has already occurred. If true, this means the system's BEST signals — the ones Nick should be acting on — are lagging indicators rather than actionable setups. The question is not about signal volume but about the reliability and timing of the cream-of-the-crop signals.

We need hard data to answer:
1. What percentage of the total price move has already occurred BEFORE each signal fires?
2. Which signal types (strategies) are consistently early vs. late?
3. Is the system catching continuation setups (by design) or missing entries (a bug)?
4. How much profitable move remains AFTER the signal on average?

---

## What Gets Built

A single standalone diagnostic script: `scripts/signal_timing_diagnostic.py`

**This script does NOT modify anything.** It is a read-only analysis tool.
---

## Part 1: Query Recent Signals

Connect to the Railway Postgres database using the same connection pattern as the rest of the codebase.

### 1A: Database Connection

Use the existing `get_postgres_client()` from `backend/database/postgres_client.py` if running within the project. If running standalone, connect directly:

```python
import asyncpg
import os

DATABASE_URL = os.environ.get("DATABASE_URL")
# If DATABASE_URL is not set, construct from Railway env vars.
# The internal hostname postgres.railway.internal only works from WITHIN Railway.
# For local/external access, use the Railway public database URL from the dashboard.
```

**IMPORTANT:** If you cannot find the public URL, run as a Railway one-off command:
```bash
railway run python scripts/signal_timing_diagnostic.py
```

### 1B: Query signals from the last 5 days

```sql
SELECT signal_id, timestamp, ticker, direction, signal_type, strategy,
       entry_price, source, timeframe, score, created_at
FROM signals
WHERE created_at >= NOW() - INTERVAL '5 days'
  AND entry_price IS NOT NULL AND entry_price > 0 AND ticker IS NOT NULL
  AND CAST(score AS NUMERIC) >= 80
ORDER BY created_at DESC;
```
Store results in a list of dicts. Log the count: `Found {N} signals in last 5 days`.

If the count is 0, also try:
```sql
SELECT COUNT(*) FROM signals;
SELECT MIN(created_at), MAX(created_at) FROM signals;
```
...and report the actual date range of available data. Adjust the interval if signals are older.

### 1C: Also check for signals in flow_events table

Some signals may be stored in `flow_events` instead of (or in addition to) `signals`. Run a discovery query:

```sql
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'flow_events' ORDER BY ordinal_position;
```

If `flow_events` has ticker, timestamp, and price columns, query it too and merge results. If it doesn't exist or has no relevant data, skip it and note that in the output.

### 1D: Check trade_ideas table too

```sql
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'trade_ideas' ORDER BY ordinal_position;
```

Same logic — if it exists and has signal-like data with timestamps and prices, include it.

**The goal is to find ALL signal-like records regardless of which table they landed in.** The pipeline has evolved through multiple phases and signals may be spread across tables.
---

## Part 2: Get Price Context from Polygon.io

For each signal, we need price data BEFORE and AFTER the signal timestamp to measure timing quality.

### 2A: Polygon API Setup

```python
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
# Already in Railway environment. If running locally, check .env or Railway dashboard.
```

### 2B: For each signal, fetch daily bars

Use Polygon Aggregates endpoint:
```
GET https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}?apiKey={key}
```

For each signal: `from_date` = signal timestamp minus 14 calendar days, `to_date` = today or signal + 14 days.

### 2C: Rate limiting

```python
import asyncio
await asyncio.sleep(0.25)  # 4 requests/second max — stay under Polygon Starter limit
```

If you get 429 errors, increase to `sleep(1.0)`.

### 2D: Group by ticker to minimize API calls

```python
from collections import defaultdict
signals_by_ticker = defaultdict(list)
for signal in signals:
    signals_by_ticker[signal['ticker']].append(signal)
# Fetch bars ONCE per ticker using widest date range needed, then match signals against cached bars.
```
---

## Part 3: Calculate Timing Metrics

This is the core analysis. For each signal, answer: **"How much of the move already happened before this signal fired?"**

### 3A: Define the measurement window

```
LOOKBACK_DAYS = 5    # How far back to measure the "move" before the signal
LOOKAHEAD_DAYS = 5   # How far forward to measure remaining opportunity
```

### 3B: For each signal, calculate these metrics

```python
def analyze_signal_timing(signal, daily_bars):
    signal_date = signal['timestamp'].date() if hasattr(signal['timestamp'], 'date') else signal['timestamp']
    signal_price = float(signal['entry_price'])
    direction = signal['direction'].upper()
    is_bullish = direction in ('LONG', 'BUY', 'BULLISH')

    bars_before = [b for b in daily_bars if b['date'] < signal_date][-LOOKBACK_DAYS:]
    bars_after = [b for b in daily_bars if b['date'] > signal_date][:LOOKAHEAD_DAYS]

    if not bars_before or not bars_after:
        return None

    if is_bullish:
        pre_signal_low = min(b['low'] for b in bars_before)
        post_signal_high = max(b['high'] for b in bars_after)
        total_move = post_signal_high - pre_signal_low
        move_before_signal = signal_price - pre_signal_low
        move_after_signal = post_signal_high - signal_price
    else:
        pre_signal_high = max(b['high'] for b in bars_before)
        post_signal_low = min(b['low'] for b in bars_after)
        total_move = pre_signal_high - post_signal_low
        move_before_signal = pre_signal_high - signal_price
        move_after_signal = signal_price - post_signal_low
    if total_move <= 0:
        return None

    pct_move_before = (move_before_signal / total_move) * 100
    pct_move_after = (move_after_signal / total_move) * 100

    if is_bullish:
        max_gain_pct = ((post_signal_high - signal_price) / signal_price) * 100
        max_pain_pct = ((signal_price - min(b['low'] for b in bars_after)) / signal_price) * 100
    else:
        max_gain_pct = ((signal_price - post_signal_low) / signal_price) * 100
        max_pain_pct = ((max(b['high'] for b in bars_after) - signal_price) / signal_price) * 100

    # Classify timing
    if pct_move_before <= 30:
        timing_grade = "EARLY"
    elif pct_move_before <= 60:
        timing_grade = "ON_TIME"
    elif pct_move_before <= 80:
        timing_grade = "LATE"
    else:
        timing_grade = "VERY_LATE"

    actionable = max_gain_pct >= 1.5  # Need 1.5%+ remaining for swing options

    return {
        'signal_id': signal['signal_id'], 'ticker': signal['ticker'],
        'direction': signal['direction'],
        'strategy': signal.get('strategy', signal.get('signal_type', 'unknown')),
        'signal_type': signal.get('signal_type', 'unknown'),
        'source': signal.get('source', 'unknown'),
        'signal_price': signal_price, 'signal_date': str(signal_date),
        'pct_move_before': round(pct_move_before, 1),
        'pct_move_after': round(pct_move_after, 1),
        'max_gain_pct': round(max_gain_pct, 2),
        'max_pain_pct': round(max_pain_pct, 2),
        'timing_grade': timing_grade, 'actionable': actionable,
        'total_move_pct': round((total_move / signal_price) * 100, 2),
    }
```

### 3C: Handle edge cases

- **Crypto tickers**: Polygon may use different formats (`X:BTCUSD`). Map accordingly or skip and note count.
- **ETFs vs stocks**: Both work with same Polygon endpoint.
- **Signals where entry_price is None or 0**: Already filtered in SQL.
- **Weekend/holiday signals**: Handled naturally since Polygon only returns trading days.
- **Very recent signals**: May lack bars_after data. Include but flag as `insufficient_lookahead: true`.
---

## Part 4: Aggregate and Report

### 4A: Summary statistics

```python
from collections import Counter, defaultdict

def generate_report(results):
    total = len(results)
    timing_counts = Counter(r['timing_grade'] for r in results)

    by_strategy = defaultdict(list)
    for r in results:
        by_strategy[r['strategy']].append(r)

    strategy_grades = {}
    for strategy, sigs in by_strategy.items():
        avg_pct_before = sum(s['pct_move_before'] for s in sigs) / len(sigs)
        avg_gain_remaining = sum(s['max_gain_pct'] for s in sigs) / len(sigs)
        actionable_pct = sum(1 for s in sigs if s['actionable']) / len(sigs) * 100
        strategy_grades[strategy] = {
            'count': len(sigs),
            'avg_pct_move_before_signal': round(avg_pct_before, 1),
            'avg_max_gain_after_signal': round(avg_gain_remaining, 2),
            'pct_actionable': round(actionable_pct, 1),
            'timing_distribution': dict(Counter(s['timing_grade'] for s in sigs)),
        }

    return {
        'meta': {'generated_at': datetime.now().isoformat(), 'signals_analyzed': total,
                 'lookback_days': LOOKBACK_DAYS, 'lookahead_days': LOOKAHEAD_DAYS},
        'overall_timing': {
            'distribution': dict(timing_counts),
            'avg_pct_move_before_signal': round(sum(r['pct_move_before'] for r in results) / total, 1),
            'avg_pct_move_after_signal': round(sum(r['pct_move_after'] for r in results) / total, 1),
            'pct_actionable': round(sum(1 for r in results if r['actionable']) / total * 100, 1),
        },
        'by_strategy': strategy_grades,
        'individual_signals': results,
    }
```
### 4B: Print a human-readable summary table

Print a formatted summary to stdout with overall timing breakdown, then a strategy-by-strategy table:

```
============================================================
        SIGNAL TIMING DIAGNOSTIC REPORT
============================================================
OVERALL: Avg % before signal: XX% | Avg % after: XX% | Actionable: XX%
EARLY: XX signals | ON_TIME: XX | LATE: XX | VERY_LATE: XX

BREAKDOWN BY STRATEGY:
Strategy              | Count | Avg% Before | Avg Gain Left | Actionable
---------------------------------------------------------------------------
ScoutSniper           |    23 |       42.1% |         2.8%  |     78%
...
```

### 4C: Save full report to file

```python
import json
report_path = "scripts/output/signal_timing_report.json"
os.makedirs("scripts/output", exist_ok=True)
with open(report_path, 'w') as f:
    json.dump(report, f, indent=2, default=str)
```
---

## Part 5: Diagnostic Answers

After generating the report, print a "DIAGNOSTIC ANSWERS" section that directly answers Nick's questions:

1. **Q1: Are signals late?** If avg_before > 65%: YES, system is confirming not predicting. If 40-65%: MIXED, consistent with continuation strategies. If < 40%: NO, catching setups early.

2. **Q2: Is this by design?** Swing/continuation strategies (ScoutSniper, HolyGrail) are DESIGNED to enter after trend is established. 40-55% before is healthy. But if reversal strategies (TrojanHorse, Phalanx) also show 60%+ before, those are genuinely firing too late.

3. **Q3: Enough move left for options?** If actionable% < 50%: Too many signals lack runway. If 50-70%: Workable. If > 70%: Pipeline generating quality setups.

4. **Q4: Worst offenders?** Sort strategies by avg_pct_move_before descending. Flag any with > 65% as problematic.

---

## Execution Instructions

1. Find the public Railway database URL (not `postgres.railway.internal`)
2. Ensure POLYGON_API_KEY is available in env
3. Run: `python scripts/signal_timing_diagnostic.py` (or `railway run python scripts/signal_timing_diagnostic.py`)
4. Share stdout output with Nick in Claude.ai project chat

---

## Definition of Done

- [ ] Script connects to Railway Postgres and pulls recent signals
- [ ] Script discovers which tables contain signal data (signals, flow_events, trade_ideas)
- [ ] Script fetches daily bars from Polygon for each unique ticker
- [ ] Each signal gets a timing grade (EARLY / ON_TIME / LATE / VERY_LATE)
- [ ] Summary table prints to stdout with strategy-level breakdown
- [ ] Diagnostic answers section prints plain-English verdicts
- [ ] Full JSON report saved to `scripts/output/signal_timing_report.json`
- [ ] Script handles edge cases gracefully
- [ ] Script runs end-to-end without errors

---

## What This Does NOT Include

- No modifications to existing code, database schema, or API endpoints
- No new cron jobs or scheduled tasks
- No frontend changes
- No signal filtering or suppression (diagnostic only — decisions come AFTER we see the data)

---

## After This Brief

Based on the results, the committee will recommend one of three paths:

1. **If signals are EARLY/ON_TIME:** Pipeline is working. Nick's perception may be recency bias.
2. **If signals are LATE but actionable:** Pipeline is designed for continuation plays. Add explicit label to UI showing how much of the move is complete.
3. **If signals are LATE and not actionable:** Pipeline needs structural changes — faster data sources, lower-lag indicators, or a pre-filter suppressing signals where >70% of move is done. Separate brief.