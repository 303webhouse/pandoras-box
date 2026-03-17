# Brief 5B: Nemesis — Countertrend Lane + WRR Scanner

**Target Agent:** Claude Code (VSCode)
**Phase:** 5 — Nemesis
**Depends On:** Brief 5A (STRC) is independent, but 5B should run after 5A
**Build Plan:** `docs/build-plans/phase-5-countertrend-lane.md`
**Strategy Doc:** `docs/approved-strategies/wrr-buy-model.md`
**Olympus Approved:** March 16, 2026
**Titans Approved:** March 17, 2026

---

## What This Does

Adds a `lane` field to the signal pipeline. All existing signals are implicitly `lane: "trend"` (bias-aligned). A new countertrend lane allows whitelisted strategies to bypass the bias penalty under strict conditions: bias must be at an extreme, score must reach 90+, and positions are half-sized with accelerated expiry.

The first countertrend strategy is the **WRR Buy Model** (Linda Raschke) — a server-side scanner that fires once daily after market close.

---

## Step 1: Add `lane` Field to Signal Pipeline

### 1A. Add countertrend constants

**File:** `backend/signals/pipeline.py`

**Find this block near the top:**
```python
COMMITTEE_SCORE_THRESHOLD = 75.0  # Minimum score_v2 to trigger committee
```

**Replace with:**
```python
COMMITTEE_SCORE_THRESHOLD = 75.0  # Minimum score_v2 to trigger committee
COUNTERTREND_COMMITTEE_THRESHOLD = 90.0  # Countertrend signals need higher score
COUNTERTREND_WHITELIST = ["WRR"]  # Strategies allowed to use countertrend lane
COUNTERTREND_BIAS_EXTREME_LOW = 25  # Bias must be <= this for countertrend longs
COUNTERTREND_BIAS_EXTREME_HIGH = 75  # Bias must be >= this for countertrend shorts
```

### 1B. Modify `_maybe_flag_for_committee()` for lane-aware threshold

**File:** `backend/signals/pipeline.py`

**Find:**
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
    lane = signal_data.get("lane", "trend")
    threshold = COUNTERTREND_COMMITTEE_THRESHOLD if lane == "countertrend" else COMMITTEE_SCORE_THRESHOLD
    if score < threshold:
        return
```

### 1C. Modify `calculate_expiry()` for countertrend accelerated expiry

**File:** `backend/signals/pipeline.py`

**Find the start of `calculate_expiry()`:**
```python
def calculate_expiry(signal_data: Dict[str, Any]) -> Optional[datetime]:
    """
    Calculate signal expiry based on timeframe and asset class.
    Returns None for signals that shouldn't auto-expire.
    """
    timeframe = (signal_data.get("timeframe") or "1H").upper()
```

**Replace with:**
```python
def calculate_expiry(signal_data: Dict[str, Any]) -> Optional[datetime]:
    """
    Calculate signal expiry based on timeframe and asset class.
    Returns None for signals that shouldn't auto-expire.
    Countertrend lane signals get accelerated 36-hour expiry regardless of timeframe.
    """
    # Countertrend signals always get accelerated expiry
    if signal_data.get("lane") == "countertrend":
        return datetime.utcnow() + timedelta(hours=36)

    timeframe = (signal_data.get("timeframe") or "1H").upper()
```

### 1D. Add countertrend bias-extreme gate to `apply_scoring()`

**File:** `backend/signals/pipeline.py`

This is the critical change. Countertrend signals that arrive when bias is NOT at an extreme should be rejected before scoring.

**Find the start of `apply_scoring()`:**
```python
async def apply_scoring(signal_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply Trade Ideas Scorer to a signal.

    Extracted from tradingview.py.apply_signal_scoring() for shared use.
    Includes composite bias lookup, contrarian qualification, and sector rotation.
    """
    try:
        # Get composite bias score
        composite_score = None
        try:
            from bias_engine.composite import get_cached_composite
            cached = await get_cached_composite()
            if cached:
                composite_score = cached.composite_score
        except Exception as comp_err:
            logger.warning(f"Composite bias unavailable: {comp_err}")
```

**Replace with:**
```python
async def apply_scoring(signal_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply Trade Ideas Scorer to a signal.

    Extracted from tradingview.py.apply_signal_scoring() for shared use.
    Includes composite bias lookup, contrarian qualification, and sector rotation.
    Countertrend lane signals are rejected if bias is not at an extreme.
    """
    try:
        # Get composite bias score
        composite_score = None
        try:
            from bias_engine.composite import get_cached_composite
            cached = await get_cached_composite()
            if cached:
                composite_score = cached.composite_score
        except Exception as comp_err:
            logger.warning(f"Composite bias unavailable: {comp_err}")

        # Countertrend lane gate: reject if bias not at extreme
        lane = signal_data.get("lane", "trend")
        if lane == "countertrend" and composite_score is not None:
            direction = (signal_data.get("direction") or "").upper()
            strategy = signal_data.get("strategy", "")

            # Whitelist check
            if strategy not in COUNTERTREND_WHITELIST:
                logger.warning(f"Countertrend signal rejected: {strategy} not in whitelist")
                signal_data["status"] = "REJECTED"
                signal_data["rejection_reason"] = f"Strategy '{strategy}' not in COUNTERTREND_WHITELIST"
                signal_data["score"] = 0
                return signal_data

            # Bias extreme check
            bias_extreme_ok = False
            if direction in ("LONG", "BUY") and composite_score <= COUNTERTREND_BIAS_EXTREME_LOW:
                bias_extreme_ok = True
            elif direction in ("SHORT", "SELL") and composite_score >= COUNTERTREND_BIAS_EXTREME_HIGH:
                bias_extreme_ok = True

            if not bias_extreme_ok:
                logger.info(
                    f"Countertrend signal rejected: {signal_data.get('ticker')} "
                    f"({direction}) — bias {composite_score} not at extreme "
                    f"(need <={COUNTERTREND_BIAS_EXTREME_LOW} for longs, >={COUNTERTREND_BIAS_EXTREME_HIGH} for shorts)"
                )
                signal_data["status"] = "REJECTED"
                signal_data["rejection_reason"] = f"Bias {composite_score} not at extreme for countertrend {direction}"
                signal_data["score"] = 0
                return signal_data

            # Set half-size modifier
            signal_data["position_size_modifier"] = 0.5
            logger.info(f"\u21ba Countertrend signal accepted: {signal_data.get('ticker')} ({direction}, bias={composite_score})")
```

**Important:** This new block goes right after the composite_score retrieval, BEFORE the existing `# Build bias data` section. The existing code continues unchanged after this block.

### 1E. Ensure rejected countertrend signals don't persist

**File:** `backend/signals/pipeline.py`

**Find in `process_signal_unified()`:**
```python
    # 3. Score signal
    if not skip_scoring:
        signal_data = await apply_scoring(signal_data)

    # 4. Persist to PostgreSQL
```

**Replace with:**
```python
    # 3. Score signal
    if not skip_scoring:
        signal_data = await apply_scoring(signal_data)

    # 3b. Bail out if countertrend signal was rejected at bias gate
    if signal_data.get("status") == "REJECTED":
        logger.info(f"Signal rejected (not persisted): {signal_data.get('ticker')} — {signal_data.get('rejection_reason')}")
        return signal_data

    # 4. Persist to PostgreSQL
```

---

## Step 2: WRR Buy Model Scanner

### 2A. Create `backend/strategies/wrr_buy_model.py` (NEW FILE)

```python
"""
WRR Buy Model Scanner (Linda Raschke)

Countertrend mean-reversion scanner. Runs daily after market close.
Looks for oversold snap-back setups when the bias engine is at an extreme.

Data source: Polygon.io (primary), yfinance (fallback).
Pipeline: signals routed with lane="countertrend" through process_signal_unified().

See: docs/approved-strategies/wrr-buy-model.md
"""
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")


def _generate_signal_id(ticker: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"WRR_{ticker}_{ts}"


async def _fetch_daily_bars_polygon(ticker: str, days: int = 30) -> Optional[List[Dict]]:
    """Fetch daily bars from Polygon.io."""
    if not POLYGON_API_KEY:
        return None
    try:
        import httpx
        from datetime import timedelta
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=days + 5)  # buffer for weekends
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params={"apiKey": POLYGON_API_KEY, "adjusted": "true", "sort": "asc"})
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                return results  # Each: {"o", "h", "l", "c", "v", "t", "vw", "n"}
    except Exception as e:
        logger.warning(f"Polygon bars failed for {ticker}: {e}")
    return None


async def _fetch_daily_bars_yfinance(ticker: str, days: int = 30) -> Optional[List[Dict]]:
    """yfinance fallback for daily bars."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period=f"{days}d")
        if hist.empty:
            return None
        bars = []
        for idx, row in hist.iterrows():
            bars.append({
                "o": row["Open"],
                "h": row["High"],
                "l": row["Low"],
                "c": row["Close"],
                "v": row["Volume"],
                "t": int(idx.timestamp() * 1000),
            })
        return bars
    except Exception as e:
        logger.warning(f"yfinance fallback failed for {ticker}: {e}")
        return None


async def _fetch_daily_bars(ticker: str, days: int = 30) -> Optional[List[Dict]]:
    """Polygon first, yfinance fallback."""
    bars = await _fetch_daily_bars_polygon(ticker, days)
    if bars:
        return bars
    return await _fetch_daily_bars_yfinance(ticker, days)


def _compute_rsi(closes: List[float], period: int = 3) -> Optional[float]:
    """Compute RSI for a list of close prices."""
    if len(closes) < period + 1:
        return None
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    recent = changes[-period:]
    gains = [c for c in recent if c > 0]
    losses = [-c for c in recent if c < 0]
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0.001
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _count_consecutive_down_days(bars: List[Dict]) -> int:
    """Count how many consecutive days price closed lower."""
    count = 0
    for i in range(len(bars) - 1, 0, -1):
        if bars[i]["c"] < bars[i - 1]["c"]:
            count += 1
        else:
            break
    return count


def _count_consecutive_up_days(bars: List[Dict]) -> int:
    """Count how many consecutive days price closed higher."""
    count = 0
    for i in range(len(bars) - 1, 0, -1):
        if bars[i]["c"] > bars[i - 1]["c"]:
            count += 1
        else:
            break
    return count


def _is_reversal_candle_bullish(bar: Dict) -> bool:
    """Check for bullish reversal: engulfing, hammer, or doji with long lower wick."""
    o, h, l, c = bar["o"], bar["h"], bar["l"], bar["c"]
    body = abs(c - o)
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)
    total_range = h - l
    if total_range == 0:
        return False
    # Hammer: lower wick > 2x body, body in upper third
    if lower_wick > 2 * body and body > 0 and upper_wick < body:
        return True
    # Bullish engulfing proxy: close > open and body > 60% of range
    if c > o and body > 0.6 * total_range:
        return True
    # Doji with long lower wick
    if body < 0.1 * total_range and lower_wick > 2 * body:
        return True
    return False


def _is_reversal_candle_bearish(bar: Dict) -> bool:
    """Check for bearish reversal: shooting star, bearish engulfing."""
    o, h, l, c = bar["o"], bar["h"], bar["l"], bar["c"]
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    total_range = h - l
    if total_range == 0:
        return False
    if upper_wick > 2 * body and body > 0 and lower_wick < body:
        return True
    if c < o and body > 0.6 * total_range:
        return True
    if body < 0.1 * total_range and upper_wick > 2 * body:
        return True
    return False


def _compute_atr(bars: List[Dict], period: int = 14) -> Optional[float]:
    """Simple ATR calculation."""
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["h"], bars[i]["l"], bars[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[-period:]) / period


def _compute_roc(closes: List[float], period: int = 10) -> Optional[float]:
    """Rate of Change as percentage."""
    if len(closes) < period + 1:
        return None
    prev = closes[-(period + 1)]
    curr = closes[-1]
    if prev == 0:
        return None
    return ((curr - prev) / prev) * 100


async def scan_wrr_signals(tickers: List[str]) -> List[Dict[str, Any]]:
    """
    Scan a list of tickers for WRR Buy/Sell Model setups.
    Returns a list of signal_data dicts ready for process_signal_unified().
    """
    signals = []

    for ticker in tickers:
        try:
            bars = await _fetch_daily_bars(ticker, days=30)
            if not bars or len(bars) < 21:
                continue

            closes = [b["c"] for b in bars]
            volumes = [b["v"] for b in bars]
            latest = bars[-1]

            rsi3 = _compute_rsi(closes, period=3)
            atr = _compute_atr(bars, period=14)
            roc10 = _compute_roc(closes, period=10)
            avg_vol_20 = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else None

            if rsi3 is None or atr is None or roc10 is None or avg_vol_20 is None:
                continue

            current_vol = latest["v"]
            vol_ratio = current_vol / avg_vol_20 if avg_vol_20 > 0 else 0

            # 20-day low/high
            low_20 = min(b["l"] for b in bars[-20:])
            high_20 = max(b["h"] for b in bars[-20:])

            # === WRR Long ===
            consec_down = _count_consecutive_down_days(bars)
            is_long_candidate = (
                (consec_down >= 3 or latest["l"] <= low_20) and
                rsi3 <= 15 and
                _is_reversal_candle_bullish(latest) and
                vol_ratio >= 1.5 and
                roc10 < -3.0  # deeply negative ROC
            )

            if is_long_candidate:
                stop = latest["l"] - (0.5 * atr)
                risk = latest["c"] - stop
                tp1 = latest["c"] + (1.5 * risk) if risk > 0 else None

                signals.append({
                    "signal_id": _generate_signal_id(ticker),
                    "ticker": ticker,
                    "strategy": "WRR",
                    "signal_type": "WRR_LONG",
                    "direction": "LONG",
                    "lane": "countertrend",
                    "timeframe": "D",
                    "entry_price": latest["c"],
                    "stop_loss": round(stop, 2),
                    "target_1": round(tp1, 2) if tp1 else None,
                    "position_size_modifier": 0.5,
                    "metadata": {
                        "rsi3": round(rsi3, 2),
                        "roc10": round(roc10, 2),
                        "vol_ratio": round(vol_ratio, 2),
                        "consec_down_days": consec_down,
                        "atr14": round(atr, 2),
                        "reversal_candle": True,
                    },
                })
                logger.info(f"WRR LONG candidate: {ticker} (RSI3={rsi3:.1f}, ROC10={roc10:.1f}, vol={vol_ratio:.1f}x)")

            # === WRR Short ===
            consec_up = _count_consecutive_up_days(bars)
            is_short_candidate = (
                (consec_up >= 3 or latest["h"] >= high_20) and
                rsi3 >= 85 and
                _is_reversal_candle_bearish(latest) and
                vol_ratio >= 1.5 and
                roc10 > 3.0  # deeply positive ROC
            )

            if is_short_candidate:
                stop = latest["h"] + (0.5 * atr)
                risk = stop - latest["c"]
                tp1 = latest["c"] - (1.5 * risk) if risk > 0 else None

                signals.append({
                    "signal_id": _generate_signal_id(ticker),
                    "ticker": ticker,
                    "strategy": "WRR",
                    "signal_type": "WRR_SHORT",
                    "direction": "SHORT",
                    "lane": "countertrend",
                    "timeframe": "D",
                    "entry_price": latest["c"],
                    "stop_loss": round(stop, 2),
                    "target_1": round(tp1, 2) if tp1 else None,
                    "position_size_modifier": 0.5,
                    "metadata": {
                        "rsi3": round(rsi3, 2),
                        "roc10": round(roc10, 2),
                        "vol_ratio": round(vol_ratio, 2),
                        "consec_up_days": consec_up,
                        "atr14": round(atr, 2),
                        "reversal_candle": True,
                    },
                })
                logger.info(f"WRR SHORT candidate: {ticker} (RSI3={rsi3:.1f}, ROC10={roc10:.1f}, vol={vol_ratio:.1f}x)")

        except Exception as e:
            logger.warning(f"WRR scan error for {ticker}: {e}")
            continue

    return signals


async def run_wrr_scan():
    """
    Entry point for scheduled WRR scan. Fetches watchlist, scans, routes signals.
    Called by scheduler after market close (4:15 PM ET).
    """
    from database.postgres_client import get_postgres_client
    from signals.pipeline import process_signal_unified

    logger.info("\u21ba WRR Buy Model scan starting...")

    # Get watchlist tickers from DB
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT ticker FROM watchlist_tickers WHERE active = true")
            tickers = [r["ticker"] for r in rows]
    except Exception as e:
        logger.error(f"Failed to fetch watchlist for WRR scan: {e}")
        return

    if not tickers:
        logger.warning("WRR scan: no active watchlist tickers found")
        return

    logger.info(f"WRR scanning {len(tickers)} tickers...")
    candidates = await scan_wrr_signals(tickers)

    for signal in candidates:
        try:
            result = await process_signal_unified(signal, source="wrr_scanner")
            logger.info(
                f"WRR signal processed: {signal['ticker']} "
                f"({signal['direction']}) — score={result.get('score')}, "
                f"status={result.get('status')}"
            )
        except Exception as e:
            logger.error(f"Failed to process WRR signal for {signal['ticker']}: {e}")

    logger.info(f"\u21ba WRR scan complete. {len(candidates)} candidates found.")
```

### 2B. Schedule the WRR scanner

Find the scheduler (same search as Brief 5A step 1C).

Add:
```python
from strategies.wrr_buy_model import run_wrr_scan
```

Schedule to run Mon-Fri at 4:15 PM ET (after market close):
```python
scheduler.add_job(run_wrr_scan, 'cron', day_of_week='mon-fri', hour=16, minute=15,
                  timezone='America/New_York', id='wrr_daily_scan')
```

---

## Step 3: Frontend — Countertrend Badge in Trade Ideas

### 3A. Find the Trade Ideas rendering

```
grep -n "trade-idea\|tradeIdea\|signal_type\|APIS_CALL\|KODIAK_CALL\|scoreTier" frontend/app.js
```

In the function that renders a trade idea card/row, find where the signal type badge is created (look for `APIS_CALL`, `KODIAK_CALL`, or score tier rendering).

### 3B. Add countertrend badge logic

**After** the existing signal type badge logic, add:

```javascript
// Countertrend lane badge
if (signal.lane === 'countertrend') {
    const ctBadge = document.createElement('span');
    ctBadge.className = 'badge badge-countertrend';
    ctBadge.textContent = '\u21ba COUNTERTREND';
    // Insert after signal type badge (adapt selector to match existing DOM)
    badgeContainer.appendChild(ctBadge);

    // Half-size indicator
    const halfSize = document.createElement('span');
    halfSize.className = 'trade-idea-half-size';
    halfSize.textContent = 'HALF-SIZE';
    // Insert below ticker name (adapt to match existing DOM)
    tickerContainer.appendChild(halfSize);
}
```

**Adapt the selectors** (`badgeContainer`, `tickerContainer`) to match the actual DOM structure. Search for the parent elements where badges and ticker names are rendered.

### 3C. Add countertrend CSS

**In `frontend/styles.css`**, add:

```css
/* ===== Countertrend Lane Badge ===== */
.badge-countertrend {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    background: rgba(245, 158, 11, 0.15);
    color: #f59e0b;
    border: 1px solid rgba(245, 158, 11, 0.3);
}

.trade-idea-half-size {
    display: block;
    font-size: 10px;
    font-weight: 600;
    color: #f59e0b;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 2px;
}
```

---

## Step 4: Add Committee Lane Context

Find where the committee prompt is assembled for signal analysis. Search:
```
grep -rn "committee\|TORO\|URSA\|TECHNICALS\|PIVOT\|analyst" backend/ --include="*.py" -l
```

In the committee prompt construction, check if `signal_data.get("lane") == "countertrend"` and if so, prepend this context to the signal description:

```python
if signal_data.get("lane") == "countertrend":
    lane_context = (
        "\n\n⚠️ COUNTERTREND SIGNAL: This signal is AGAINST the prevailing bias. "
        "The bias engine is at an extreme, which is why this countertrend setup "
        "was allowed through. Evaluate whether the extreme condition justifies "
        "a countertrend entry. Position will be HALF-SIZE with 36-hour expiry.\n"
    )
    # Prepend to signal description in the prompt
```

Adapt to match the existing prompt assembly pattern.

---

## Step 5: Tests

Create `tests/test_countertrend_lane.py`:

```python
"""Tests for countertrend lane gating logic."""
import pytest
from unittest.mock import AsyncMock, patch
from signals.pipeline import apply_scoring, COUNTERTREND_WHITELIST


@pytest.mark.asyncio
async def test_countertrend_rejected_when_bias_not_extreme():
    """Countertrend long should be rejected when bias > 25."""
    signal = {
        "ticker": "AAPL",
        "direction": "LONG",
        "lane": "countertrend",
        "strategy": "WRR",
    }
    with patch("signals.pipeline.get_cached_composite") as mock_comp:
        mock_comp.return_value = AsyncMock(composite_score=50)  # not extreme
        result = await apply_scoring(signal)
        assert result["status"] == "REJECTED"
        assert result["score"] == 0


@pytest.mark.asyncio
async def test_countertrend_accepted_when_bias_extreme():
    """Countertrend long should pass when bias <= 25."""
    signal = {
        "ticker": "AAPL",
        "direction": "LONG",
        "lane": "countertrend",
        "strategy": "WRR",
        "entry_price": 150.0,
        "stop_loss": 148.0,
    }
    with patch("signals.pipeline.get_cached_composite") as mock_comp:
        mock_comp.return_value = AsyncMock(composite_score=20)  # extreme bearish
        # Mock the rest of scoring to avoid full pipeline
        with patch("signals.pipeline.calculate_signal_score", return_value=(85, "COUNTERTREND", {})):
            result = await apply_scoring(signal)
            assert result.get("status") != "REJECTED"
            assert result.get("position_size_modifier") == 0.5


@pytest.mark.asyncio
async def test_countertrend_rejected_when_not_whitelisted():
    """Non-whitelisted strategy should be rejected even at bias extreme."""
    signal = {
        "ticker": "AAPL",
        "direction": "LONG",
        "lane": "countertrend",
        "strategy": "UNKNOWN_STRATEGY",
    }
    with patch("signals.pipeline.get_cached_composite") as mock_comp:
        mock_comp.return_value = AsyncMock(composite_score=15)
        result = await apply_scoring(signal)
        assert result["status"] == "REJECTED"
        assert "not in COUNTERTREND_WHITELIST" in result.get("rejection_reason", "")
```

Run tests with the existing test suite to verify nothing breaks:
```bash
python -m pytest tests/ -v
```

---

## Testing Checklist

1. **Countertrend rejection:** Send a test signal with `lane: countertrend` when bias is 50 — should be rejected, not persisted
2. **Countertrend acceptance:** Send a test signal with `lane: countertrend` when bias is 20 — should score normally with 1.0 multiplier
3. **Whitelist enforcement:** Send a countertrend signal with `strategy: FAKE` — should be rejected
4. **Committee threshold:** Countertrend signal with score 80 should NOT be flagged for committee (needs 90+)
5. **Expiry:** Countertrend signal should get 36-hour expiry regardless of timeframe
6. **Frontend badge:** Trade idea with `lane: countertrend` should show amber badge + HALF-SIZE text
7. **WRR scanner:** Run `run_wrr_scan()` manually — should fetch bars, scan, and produce candidates (or empty list if no setups)
8. **Existing tests pass:** `python -m pytest tests/ -v` — all 217+ existing tests should still pass

## Definition of Done
- [ ] `COUNTERTREND_WHITELIST` and constants added to `pipeline.py`
- [ ] Countertrend bias-extreme gate in `apply_scoring()` rejects non-extreme signals
- [ ] Committee threshold is 90 for countertrend lane
- [ ] Countertrend expiry is 36 hours
- [ ] Rejected signals bail out before DB persist
- [ ] `backend/strategies/wrr_buy_model.py` created and scans via Polygon.io
- [ ] WRR scanner scheduled for 4:15 PM ET weekdays
- [ ] Frontend shows countertrend badge + half-size indicator
- [ ] Committee prompt includes lane context for countertrend signals
- [ ] Tests pass (including new countertrend tests)
- [ ] All 217+ existing tests still pass
