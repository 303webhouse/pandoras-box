# Brief 5C: Wiring Patch — Connect WRR Scanner + STRC Poller to Scheduler

**Target Agent:** Claude Code (VSCode)
**Priority:** URGENT — Phase 5 code exists but is dead (never called)
**Depends On:** Briefs 5A + 5B already deployed

---

## Problem

Three issues from the Brief 5A/5B deploy:

1. **WRR scanner (`wrr_buy_model.py`) is dead code** — the file exists but `run_wrr_scan()` is never imported or scheduled. The daily after-close scan will never fire.
2. **STRC poller (`strc_monitor.py`) is dead code** — `update_strc_cache()` is never imported or scheduled. The Redis cache never gets populated, so the frontend banner will never show data.
3. **Committee threshold for countertrend not applied** — `COUNTERTREND_COMMITTEE_THRESHOLD = 90` is defined in `pipeline.py` but `_maybe_flag_for_committee()` still only checks `COMMITTEE_SCORE_THRESHOLD = 75`. A countertrend signal scoring 80 would incorrectly get flagged for committee.

---

## Fix 1: Register WRR Scanner in Scheduler

**File:** `backend/scheduler/bias_scheduler.py`

### 1A. Add import wrapper function

Find the function `run_health_monitor_job` and ADD this new function **after** it (before `reset_circuit_breaker_scheduled`):

```python
async def run_wrr_scan_job():
    """Run WRR Buy Model countertrend scanner after market close."""
    now = get_eastern_now()
    if not is_trading_day():
        logger.info("WRR scan skipped — not a trading day")
        return
    try:
        from strategies.wrr_buy_model import run_wrr_scan
        logger.info("\u21ba WRR Buy Model scan starting (scheduled)...")
        await run_wrr_scan()
    except Exception as e:
        logger.error(f"WRR scan job error: {e}")
```

### 1B. Register the job in APScheduler

**Find this exact block** in `start_scheduler()` (the APScheduler section):

```python
        # Nightly signal outcome scoring + discovery cleanup (9:00 PM ET)
        scheduler.add_job(
            run_signal_scoring_job,
            CronTrigger(day_of_week='mon-fri', hour=21, minute=0, timezone=ET),
            id='signal_scoring',
            name='Signal Outcome Scoring',
            replace_existing=True
        )
```

**BEFORE that block**, insert:

```python
        # WRR Buy Model countertrend scanner (4:20 PM ET, after market close)
        scheduler.add_job(
            run_wrr_scan_job,
            CronTrigger(day_of_week='mon-fri', hour=16, minute=20, timezone=ET),
            id='wrr_daily_scan',
            name='WRR Buy Model Scanner',
            replace_existing=True
        )

```

### 1C. Add startup log line

Find this line:
```python
        logger.info("\u2705 Signal outcome scoring scheduled for 9:00 PM ET")
```

Before it, add:
```python
        logger.info("\u2705 WRR Buy Model scanner scheduled daily at 4:20 PM ET")
```

---

## Fix 2: Register STRC Poller in Scheduler

**File:** `backend/scheduler/bias_scheduler.py`

### 2A. Add import wrapper function

Add this function right after the `run_wrr_scan_job` function you just added:

```python
async def run_strc_poller_job():
    """Poll STRC price and update Redis cache for circuit breaker banner."""
    try:
        from circuit_breakers.strc_monitor import update_strc_cache
        await update_strc_cache()
    except Exception as e:
        logger.warning(f"STRC poller error: {e}")
```

### 2B. Register the job in APScheduler

**Find this block** in `start_scheduler()`:

```python
        # Composite bias refresh every 15 minutes
        scheduler.add_job(
            refresh_composite_bias,
            'interval',
            minutes=15,
            id='composite_bias_refresh',
            name='Composite Bias Refresh',
            replace_existing=True
        )
```

**AFTER that block**, insert:

```python
        # STRC circuit breaker price poller (every 5 minutes)
        scheduler.add_job(
            run_strc_poller_job,
            'interval',
            minutes=5,
            id='strc_circuit_breaker_poller',
            name='STRC Circuit Breaker Poller',
            replace_existing=True
        )

```

### 2C. Add startup log line

Find this line:
```python
        logger.info("\u2705 Composite bias refresh scheduled every 15 minutes")
```

After it, add:
```python
        logger.info("\u2705 STRC circuit breaker poller scheduled every 5 minutes")
```

---

## Fix 3: Committee Threshold for Countertrend

**File:** `backend/signals/pipeline.py`

The `COUNTERTREND_COMMITTEE_THRESHOLD = 90` constant is already defined but not used in `_maybe_flag_for_committee()`.

**Find this exact code** in `_maybe_flag_for_committee()`:

```python
    # Check score threshold (prefer score_v2, fall back to score)
    score = signal_data.get("score_v2") or signal_data.get("score") or 0
    if score < COMMITTEE_SCORE_THRESHOLD:
        return
```

**Replace with:**

```python
    # Check score threshold (prefer score_v2, fall back to score)
    score = signal_data.get("score_v2") or signal_data.get("score") or 0
    is_countertrend = signal_data.get("countertrend") or "wrr" in (signal_data.get("strategy") or "").lower()
    threshold = COUNTERTREND_COMMITTEE_THRESHOLD if is_countertrend else COMMITTEE_SCORE_THRESHOLD
    if score < threshold:
        return
```

---

## Testing

1. **Scheduler registration:** After deploy, check Railway logs for:
   - `\u2705 WRR Buy Model scanner scheduled daily at 4:20 PM ET`
   - `\u2705 STRC circuit breaker poller scheduled every 5 minutes`
2. **STRC poller:** Within 5 minutes of deploy, hit `GET /api/crypto/circuit-breakers` — should return STRC price data (not null)
3. **WRR scanner:** Wait for 4:20 PM ET on a weekday, or manually call `run_wrr_scan_job()` to verify it runs
4. **Committee threshold:** A countertrend signal with score 80 should NOT be flagged for committee review
5. **Existing tests:** `python -m pytest tests/ -v` — all should pass

## Definition of Done
- [ ] `run_wrr_scan_job()` registered in APScheduler at 4:20 PM ET Mon-Fri
- [ ] `run_strc_poller_job()` registered in APScheduler every 5 minutes
- [ ] `_maybe_flag_for_committee()` uses 90 threshold for countertrend signals
- [ ] Railway logs confirm both jobs scheduled on deploy
- [ ] `/api/crypto/circuit-breakers` returns data within 5 min of deploy
- [ ] All existing tests pass
