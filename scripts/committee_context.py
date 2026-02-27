"""
Committee Context Formatters + Bias Challenge + Technical Data + Playbook

Formats the raw context dict from build_market_context() into
readable text blocks for each LLM agent's user message.

Position data removed — no agent gets portfolio information.
Focus: signal details, market regime, circuit breakers, earnings, zone shifts,
Twitter sentiment, lessons from recent reviews, live technical data (yfinance),
playbook rules, and per-agent performance feedback.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import time
from pathlib import Path

_log = logging.getLogger("committee_context")


def format_signal_context(signal: dict, context: dict) -> str:
    """
    Formats signal + market context into a readable text block
    shared by all four agents as the base user message.
    """
    bias = context.get("bias_composite") or {}
    cbs = context.get("circuit_breakers") or []
    earnings = context.get("earnings") or {}
    zone = context.get("zone") or {}

    sections = []

    # ── Signal info ──
    metadata = signal.get("metadata") or {}
    sections.append(
        f"## SIGNAL\n"
        f"Ticker: {signal.get('ticker', 'N/A')}\n"
        f"Direction: {signal.get('direction', 'N/A')}\n"
        f"Alert Type: {signal.get('alert_type', signal.get('signal_type', 'N/A'))}\n"
        f"Score: {signal.get('score', 'N/A')}\n"
        f"Strategy: {metadata.get('strategy', signal.get('strategy', 'N/A'))}\n"
        f"Timeframe: {metadata.get('timeframe', 'N/A')}"
    )

    # ── Market regime ──
    sections.append(
        f"## MARKET REGIME\n"
        f"Bias: {bias.get('bias_level', 'UNKNOWN')}\n"
        f"Composite Score: {bias.get('composite_score', 'N/A')}\n"
        f"Confidence: {bias.get('confidence', 'UNKNOWN')}\n"
        f"DEFCON: {context.get('defcon', 'UNKNOWN')}"
    )

    # ── Circuit breaker alerts ──
    if cbs:
        cb_lines = []
        for cb in cbs:
            cb_lines.append(
                f"- [{cb.get('timestamp', '?')}] "
                f"{cb.get('ticker', '?')} {cb.get('direction', '?')} "
                f"@ ${cb.get('entry_price', '?')} — {cb.get('notes', '')}"
            )
        sections.append(f"## RECENT CIRCUIT BREAKER EVENTS\n" + "\n".join(cb_lines))

    # ── Earnings proximity ──
    if earnings.get("has_earnings"):
        sections.append(
            f"## EARNINGS WARNING\n"
            f"{signal.get('ticker', '?')} has earnings in "
            f"{earnings['days_until']} days ({earnings['date']})"
        )

    # ── Zone context ──
    if zone and zone.get("to_zone"):
        sections.append(
            f"## RECENT ZONE SHIFT\n"
            f"From {zone.get('from_zone', '?')} to {zone.get('to_zone', '?')} "
            f"at {zone.get('timestamp', '?')}"
        )

    # ── Whale context ──
    alert_type = signal.get("alert_type", signal.get("signal_type", ""))
    if alert_type == "whale_flow_confirmed":
        whale_meta = signal.get("metadata") or {}
        sections.append(
            f"## WHALE FLOW CONFIRMATION\n"
            f"Original alert: {whale_meta.get('original_whale_alert', {})}\n"
            f"UW analysis: {whale_meta.get('uw_screenshot_description', 'N/A')}\n"
            f"Confirmation delay: {whale_meta.get('confirmation_delay_seconds', 'N/A')}s"
        )

    # Inject Twitter sentiment context
    ticker = signal.get("ticker")
    twitter_ctx = _get_twitter_sentiment_context(ticker=ticker)
    if twitter_ctx:
        sections.append(twitter_ctx)

    # Inject recent lessons from weekly reviews (if any)
    lessons_text = _get_recent_lessons_context()
    if lessons_text:
        sections.append(lessons_text)

    return "\n\n".join(sections)


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
        sections.append("\n### \u26a0\ufe0f ALERTS:")
        for s in alerts[-3:]:
            sections.append(f"- @{s['username']}: {s.get('summary', 'ALERT')}")

    return "\n".join(sections) if len(sections) > 1 else ""


def _get_recent_lessons_context() -> str:
    """Load recent lessons from lessons_bank.jsonl with 6-week recency cutoff."""
    lessons_path = Path("/opt/openclaw/workspace/data/lessons_bank.jsonl")
    try:
        with open(lessons_path, "r") as f:
            lines = f.readlines()

        cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(weeks=6)
        recent = []

        # Scan last 20 entries for recency-weighted lessons
        for line in lines[-20:]:
            try:
                entry = json.loads(line.strip())
                # Check timestamp if present
                ts_str = entry.get("timestamp", "")
                if ts_str:
                    ts = _dt.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts < cutoff:
                        continue
                recent.append(entry["lesson"])
            except (json.JSONDecodeError, KeyError, ValueError):
                continue

        # Keep last 5 recent lessons (more context than before, but only fresh ones)
        recent = recent[-5:]
        if recent:
            return (
                "\n\n## LESSONS FROM RECENT PERFORMANCE REVIEWS (last 6 weeks)\n"
                + "\n".join(f"- {l}" for l in recent)
                + "\n"
            )
    except FileNotFoundError:
        pass
    return ""


def get_bias_challenge_context(signal: dict, context: dict) -> str:
    """
    Returns additional context to inject into Pivot's user message
    when the signal might trigger Nick's known biases.

    Nick's documented biases:
    1. Extremely bearish on Trump admin / US macro stability
    2. Extremely bullish on AI disruption as a trade thesis

    Pivot should challenge these when they might lead to bad trades.
    """
    challenges = []
    bias = context.get("bias_composite") or {}
    ticker = str(signal.get("ticker") or "").upper()
    direction = str(signal.get("direction") or "").upper()
    regime = str(bias.get("bias_level") or "").upper()

    # Challenge 1: Nick's bearish macro bias
    if direction in ("BEARISH", "SHORT", "SELL") and regime.startswith("TORO"):
        challenges.append(
            "BIAS CHECK: This is a BEARISH signal but the market regime "
            "is actually bullish. Nick has a documented bearish macro bias — "
            "make sure this trade is based on the chart, not on macro anxiety. "
            "Challenge him if the bear case relies on 'the market should be lower' "
            "rather than specific technical evidence."
        )

    # Challenge 2: Nick's AI bullish bias
    AI_TICKERS = {
        "NVDA", "AMD", "SMCI", "MSFT", "GOOGL", "GOOG", "META",
        "AMZN", "PLTR", "ARM", "TSM", "AVGO", "MRVL", "AI", "SNOW",
    }

    if ticker in AI_TICKERS and direction in ("BULLISH", "LONG", "BUY"):
        challenges.append(
            "BIAS CHECK: This is a BULLISH signal on an AI-related ticker. "
            "Nick has a documented bullish bias on AI disruption. "
            "Be extra critical of the bull case — is this actually a good entry "
            "or is Nick just bullish on the sector regardless of timing and price? "
            "Check if IV is elevated from AI hype cycles."
        )

    # Challenge 3: Bearish on AI ticker when he's usually bullish
    if ticker in AI_TICKERS and direction in ("BEARISH", "SHORT", "SELL"):
        challenges.append(
            "NOTE: Nick is typically very bullish on AI tickers, so a bearish "
            "signal here is counter to his usual bias. This might actually be a "
            "higher-quality signal since it's not confirmation bias. Evaluate on merits."
        )

    if challenges:
        return "\n\n## BIAS CHALLENGE NOTES (for Pivot only)\n" + "\n\n".join(challenges)
    return ""


# ── Technical Data Enrichment (yfinance) ─────────────────────

DATA_DIR = Path("/opt/openclaw/workspace/data")
TECH_CACHE_DIR = DATA_DIR / "tech_cache"
TECH_CACHE_TTL_SEC = 600  # 10 minutes


def fetch_technical_snapshot(ticker: str) -> dict:
    """
    Fetch live technical data for a ticker via yfinance.
    Returns dict with EMAs, RSI, MACD, ATR, volume ratio, 52-week range.
    Uses a 10-minute file cache to avoid redundant API calls.
    Returns empty dict on failure (committee runs without tech data).
    """
    if not ticker:
        return {}

    ticker = ticker.upper().strip()

    # Check cache
    cache_file = TECH_CACHE_DIR / f"{ticker}.json"
    try:
        if cache_file.exists():
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            cached_at = cached.get("_cached_at", 0)
            if time.time() - cached_at < TECH_CACHE_TTL_SEC:
                _log.info("Using cached tech data for %s (age %.0fs)", ticker, time.time() - cached_at)
                return cached
    except Exception:
        pass

    try:
        import yfinance as yf
        import numpy as np

        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        if df is None or df.empty or len(df) < 50:
            _log.warning("Insufficient yfinance data for %s (%d rows)", ticker, len(df) if df is not None else 0)
            return {}

        # Flatten MultiIndex columns if present
        if hasattr(df.columns, 'levels') and len(df.columns.levels) > 1:
            df.columns = df.columns.get_level_values(0)

        close = df["Close"].astype(float)
        high = df["High"].astype(float)
        low = df["Low"].astype(float)
        volume = df["Volume"].astype(float)

        price = float(close.iloc[-1])

        # EMAs
        ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
        ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
        ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])

        # EMA slopes (current vs 5 days ago)
        ema20_series = close.ewm(span=20, adjust=False).mean()
        ema50_series = close.ewm(span=50, adjust=False).mean()
        ema200_series = close.ewm(span=200, adjust=False).mean()

        def _slope(series):
            if len(series) < 6:
                return "flat"
            return "rising" if float(series.iloc[-1]) > float(series.iloc[-6]) else "falling"

        ema20_slope = _slope(ema20_series)
        ema50_slope = _slope(ema50_series)
        ema200_slope = _slope(ema200_series)

        # SMAs for CTA Three-Speed System (20/50/120 + 200)
        sma20 = float(close.rolling(20).mean().iloc[-1])
        sma50 = float(close.rolling(50).mean().iloc[-1])
        sma120 = float(close.rolling(min(120, len(close))).mean().iloc[-1])
        sma200 = float(close.rolling(min(200, len(close))).mean().iloc[-1])

        # CTA zone classification based on SMA alignment
        if price > sma20 and sma20 > sma50 and sma50 > sma120:
            cta_zone = "GREEN — max long, all SMAs aligned bullish"
        elif price < sma20 and sma20 < sma50 and sma50 < sma120:
            cta_zone = "RED — CTA capitulation, all SMAs aligned bearish"
        elif price > sma50 and sma50 > sma120:
            cta_zone = "YELLOW — above 50/120 SMA but 20 SMA crossing"
        elif price < sma50 and sma50 < sma120:
            cta_zone = "YELLOW-BEAR — below 50/120 SMA, bearish transition"
        else:
            cta_zone = "GREY — choppy, SMAs not cleanly aligned"

        # RSI 14 (Wilder's EWM method)
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta.clip(upper=0))
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi_series = 100 - (100 / (1 + rs))
        rsi = float(rsi_series.iloc[-1]) if not np.isnan(rsi_series.iloc[-1]) else None

        # MACD (12, 26, 9)
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line

        macd_val = float(macd_line.iloc[-1])
        signal_val = float(signal_line.iloc[-1])
        hist_val = float(histogram.iloc[-1])

        # RSI / MACD divergence detection (last 30 bars)
        rsi_divergence = None
        macd_divergence = None
        try:
            lookback = min(30, len(close) - 1)
            if lookback >= 10:
                price_arr = close.iloc[-lookback:].to_numpy()
                rsi_arr = rsi_series.iloc[-lookback:].to_numpy()
                hist_arr = histogram.iloc[-lookback:].to_numpy()

                def _pivots(arr, w=3):
                    """Find (index, value) of swing highs and lows."""
                    highs, lows = [], []
                    for i in range(w, len(arr) - w):
                        seg = arr[i - w:i + w + 1]
                        if not np.any(np.isnan(seg)):
                            if arr[i] == np.max(seg):
                                highs.append((i, float(arr[i])))
                            if arr[i] == np.min(seg):
                                lows.append((i, float(arr[i])))
                    return highs, lows

                p_hi, p_lo = _pivots(price_arr)
                r_hi, r_lo = _pivots(rsi_arr)
                m_hi, m_lo = _pivots(hist_arr)

                # Bearish RSI: price higher high, RSI lower high
                if len(p_hi) >= 2 and len(r_hi) >= 2:
                    if p_hi[-1][1] > p_hi[-2][1] and r_hi[-1][1] < r_hi[-2][1]:
                        rsi_divergence = "bearish (price higher high, RSI lower high)"
                # Bullish RSI: price lower low, RSI higher low
                if rsi_divergence is None and len(p_lo) >= 2 and len(r_lo) >= 2:
                    if p_lo[-1][1] < p_lo[-2][1] and r_lo[-1][1] > r_lo[-2][1]:
                        rsi_divergence = "bullish (price lower low, RSI higher low)"

                # Bearish MACD: price higher high, histogram lower high
                if len(p_hi) >= 2 and len(m_hi) >= 2:
                    if p_hi[-1][1] > p_hi[-2][1] and m_hi[-1][1] < m_hi[-2][1]:
                        macd_divergence = "bearish (price higher high, histogram lower high)"
                # Bullish MACD: price lower low, histogram higher low
                if macd_divergence is None and len(p_lo) >= 2 and len(m_lo) >= 2:
                    if p_lo[-1][1] < p_lo[-2][1] and m_lo[-1][1] > m_lo[-2][1]:
                        macd_divergence = "bullish (price lower low, histogram higher low)"
        except Exception:
            pass

        # MACD crossover state (7-bar lookback for swing trading context)
        if len(histogram) >= 7:
            recent_hist = [float(histogram.iloc[i]) for i in range(-7, 0)]
            if hist_val > 0 and any(h <= 0 for h in recent_hist):
                macd_cross = "bullish crossover (recent)"
            elif hist_val < 0 and any(h >= 0 for h in recent_hist):
                macd_cross = "bearish crossover (recent)"
            elif hist_val > 0:
                macd_cross = "above signal (bullish)"
            else:
                macd_cross = "below signal (bearish)"
        else:
            macd_cross = "above signal" if hist_val > 0 else "below signal"

        # ATR 14
        tr = np.maximum(
            high - low,
            np.maximum(
                abs(high - close.shift(1)),
                abs(low - close.shift(1))
            )
        )
        atr = float(tr.ewm(alpha=1/14, min_periods=14, adjust=False).mean().iloc[-1])

        # Volume ratio vs 20-day average
        vol_current = float(volume.iloc[-1])
        vol_20d_avg = float(volume.rolling(20).mean().iloc[-1])
        vol_ratio = round(vol_current / vol_20d_avg, 2) if vol_20d_avg > 0 else None

        # Volume trend: up-volume vs down-volume (10-day window)
        price_change = close.diff()
        up_vol = volume.where(price_change > 0, 0).rolling(10).mean()
        down_vol = volume.where(price_change < 0, 0).rolling(10).mean()
        up_vol_avg = float(up_vol.iloc[-1]) if not np.isnan(float(up_vol.iloc[-1])) else 0
        down_vol_avg = float(down_vol.iloc[-1]) if not np.isnan(float(down_vol.iloc[-1])) else 0
        vol_ad_ratio = round(up_vol_avg / down_vol_avg, 2) if down_vol_avg > 0 else None

        # VWAP (5-day rolling — more useful than cumulative annual)
        typical_price = (high + low + close) / 3
        tp_vol = (typical_price * volume).rolling(5).sum()
        vol_5d = volume.rolling(5).sum()
        vwap_5d = round(float((tp_vol / vol_5d).iloc[-1]), 2) if float(vol_5d.iloc[-1]) > 0 else None

        # 52-week high/low
        high_52w = float(high.iloc[-252:].max()) if len(high) >= 252 else float(high.max())
        low_52w = float(low.iloc[-252:].min()) if len(low) >= 252 else float(low.min())
        pct_from_high = round((price - high_52w) / high_52w * 100, 1) if high_52w > 0 else None
        pct_from_low = round((price - low_52w) / low_52w * 100, 1) if low_52w > 0 else None

        # Relative strength vs SPY (20-day return comparison)
        rs_vs_spy = None
        if ticker.upper() != "SPY" and len(close) >= 20:
            try:
                spy_df = yf.download("SPY", period="1mo", interval="1d", progress=False)
                if len(spy_df) >= 20:
                    spy_close = spy_df["Close"]
                    # Handle MultiIndex columns from yfinance
                    if hasattr(spy_close, "columns"):
                        spy_close = spy_close.iloc[:, 0]
                    spy_close = spy_close.astype(float)
                    spy_ret = (float(spy_close.iloc[-1]) / float(spy_close.iloc[-20]) - 1) * 100
                    tick_ret = (price / float(close.iloc[-20]) - 1) * 100
                    rs_vs_spy = round(tick_ret - spy_ret, 2)
            except Exception:
                pass

        # Historical Volatility (20-day annualized) — proxy for IV assessment
        log_returns = np.log(close / close.shift(1)).dropna()
        hv20_series = log_returns.rolling(20).std() * np.sqrt(252) * 100
        hv20_series_clean = hv20_series.dropna()
        if len(hv20_series_clean) >= 20:
            hv20 = float(hv20_series_clean.iloc[-1])
            hv_min = float(hv20_series_clean.min())
            hv_max = float(hv20_series_clean.max())
            hv_percentile = round((hv20 - hv_min) / (hv_max - hv_min) * 100, 0) if hv_max > hv_min else 50
            hv_trend = "rising" if len(hv20_series_clean) > 11 and hv20 > float(hv20_series_clean.iloc[-11]) else "falling"
        else:
            hv20 = None
            hv_percentile = None
            hv_min = None
            hv_max = None
            hv_trend = None

        # Bollinger Bands (20, 2) + squeeze detection
        bb_sma = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = round(float((bb_sma + 2 * bb_std).iloc[-1]), 2)
        bb_lower = round(float((bb_sma - 2 * bb_std).iloc[-1]), 2)
        bb_width = round((bb_upper - bb_lower) / price * 100, 2) if price > 0 else 0
        # Squeeze: current bandwidth below 20th percentile of 90-day bandwidth history
        bb_width_series = ((bb_sma + 2 * bb_std) - (bb_sma - 2 * bb_std)) / close * 100
        bw_90 = bb_width_series.iloc[-90:].dropna()
        bb_squeeze = bool(bb_width < float(bw_90.quantile(0.20))) if len(bw_90) >= 20 else False

        snapshot = {
            "ticker": ticker,
            "price": round(price, 2),
            "ema20": round(ema20, 2),
            "ema50": round(ema50, 2),
            "ema200": round(ema200, 2),
            "ema20_slope": ema20_slope,
            "ema50_slope": ema50_slope,
            "ema200_slope": ema200_slope,
            "price_vs_ema20": "above" if price > ema20 else "below",
            "price_vs_ema50": "above" if price > ema50 else "below",
            "price_vs_ema200": "above" if price > ema200 else "below",
            "sma20": round(sma20, 2),
            "sma50": round(sma50, 2),
            "sma120": round(sma120, 2),
            "sma200": round(sma200, 2),
            "price_vs_sma20": "above" if price > sma20 else "below",
            "price_vs_sma50": "above" if price > sma50 else "below",
            "price_vs_sma120": "above" if price > sma120 else "below",
            "cta_zone": cta_zone,
            "rsi14": round(rsi, 1) if rsi is not None else None,
            "rsi_divergence": rsi_divergence,
            "macd_divergence": macd_divergence,
            "macd": round(macd_val, 4),
            "macd_signal": round(signal_val, 4),
            "macd_histogram": round(hist_val, 4),
            "macd_cross": macd_cross,
            "atr14": round(atr, 2),
            "volume_ratio": vol_ratio,
            "vol_ad_ratio": vol_ad_ratio,
            "vwap_5d": vwap_5d,
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2),
            "pct_from_52w_high": pct_from_high,
            "pct_from_52w_low": pct_from_low,
            "rs_vs_spy": rs_vs_spy,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "bb_width": bb_width,
            "bb_squeeze": bb_squeeze,
            "hv20": round(hv20, 1) if hv20 is not None else None,
            "hv_percentile": int(hv_percentile) if hv_percentile is not None else None,
            "hv_min_1y": round(hv_min, 1) if hv_min is not None else None,
            "hv_max_1y": round(hv_max, 1) if hv_max is not None else None,
            "hv_trend": hv_trend,
            "_cached_at": time.time(),
        }

        # Write cache
        try:
            TECH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        except Exception as e:
            _log.warning("Failed to cache tech data for %s: %s", ticker, e)

        _log.info("Fetched live tech data for %s: price=$%.2f RSI=%.1f", ticker, price, rsi or 0)
        return snapshot

    except ImportError:
        _log.warning("yfinance not installed — skipping technical data enrichment")
        return {}
    except Exception as e:
        _log.warning("Failed to fetch tech data for %s: %s", ticker, e)
        return {}


def format_technical_data(snapshot: dict) -> str:
    """Render technical snapshot dict into a context block for LLM agents."""
    if not snapshot or not snapshot.get("price"):
        return ""

    price = snapshot["price"]
    lines = [f"## TECHNICAL DATA (live — {snapshot.get('ticker', '?')})"]

    # Price + 52-week range
    h52 = snapshot.get("high_52w")
    l52 = snapshot.get("low_52w")
    pct_h = snapshot.get("pct_from_52w_high")
    pct_l = snapshot.get("pct_from_52w_low")
    price_line = f"Price: ${price}"
    if h52 is not None:
        price_line += f" | 52w High: ${h52} ({pct_h:+.1f}%)"
    if l52 is not None:
        price_line += f" | 52w Low: ${l52} ({pct_l:+.1f}%)"
    lines.append(price_line)

    # 5-day VWAP
    vwap = snapshot.get("vwap_5d")
    if vwap is not None:
        vwap_pos = "above" if price > vwap else "below"
        lines.append(f"5d VWAP: ${vwap} (price {vwap_pos})")

    # EMAs
    ema_parts = []
    for period in (20, 50, 200):
        val = snapshot.get(f"ema{period}")
        pos = snapshot.get(f"price_vs_ema{period}", "?")
        slope = snapshot.get(f"ema{period}_slope", "?")
        if val is not None:
            ema_parts.append(f"EMA {period}: ${val} ({pos}, {slope})")
    if ema_parts:
        lines.append(" | ".join(ema_parts))

    # SMAs + CTA Zone
    sma_parts = []
    for period in (20, 50, 120):
        val = snapshot.get(f"sma{period}")
        pos = snapshot.get(f"price_vs_sma{period}", "?")
        if val is not None:
            sma_parts.append(f"SMA {period}: ${val} ({pos})")
    sma200_val = snapshot.get("sma200")
    if sma200_val is not None:
        sma_parts.append(f"SMA 200: ${sma200_val}")
    if sma_parts:
        lines.append(" | ".join(sma_parts))
    cta_zone = snapshot.get("cta_zone")
    if cta_zone:
        lines.append(f"CTA Zone: {cta_zone}")

    # Indicators
    ind_parts = []
    rsi = snapshot.get("rsi14")
    if rsi is not None:
        rsi_label = "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral"
        rsi_str = f"RSI(14): {rsi} [{rsi_label}]"
        rsi_div = snapshot.get("rsi_divergence")
        if rsi_div:
            rsi_str += f" **DIVERGENCE: {rsi_div}**"
        ind_parts.append(rsi_str)

    macd_cross = snapshot.get("macd_cross")
    macd_val = snapshot.get("macd")
    if macd_val is not None and macd_cross:
        hist_val = snapshot.get("macd_histogram")
        hist_str = f" | hist: {hist_val:+.4f}" if hist_val is not None else ""
        macd_str = f"MACD: {macd_val:.4f}{hist_str} — {macd_cross}"
        macd_div = snapshot.get("macd_divergence")
        if macd_div:
            macd_str += f" **DIVERGENCE: {macd_div}**"
        ind_parts.append(macd_str)

    if ind_parts:
        lines.append(" | ".join(ind_parts))

    # ATR + Volume + Volume Trend
    misc_parts = []
    atr = snapshot.get("atr14")
    if atr is not None:
        misc_parts.append(f"ATR(14): ${atr}")
    vol_r = snapshot.get("volume_ratio")
    if vol_r is not None:
        misc_parts.append(f"Volume: {vol_r}x 20d avg")
    vol_ad = snapshot.get("vol_ad_ratio")
    if vol_ad is not None:
        ad_label = "accumulation" if vol_ad > 1.2 else "distribution" if vol_ad < 0.8 else "neutral"
        misc_parts.append(f"Up/Down Vol: {vol_ad} ({ad_label})")
    if misc_parts:
        lines.append(" | ".join(misc_parts))

    # Bollinger Bands
    bb_upper = snapshot.get("bb_upper")
    bb_lower = snapshot.get("bb_lower")
    bb_width = snapshot.get("bb_width")
    if bb_upper is not None and bb_lower is not None:
        bb_str = f"BB(20,2): ${bb_upper} / ${bb_lower} (width: {bb_width}%)"
        if snapshot.get("bb_squeeze"):
            bb_str += " **SQUEEZE — breakout imminent**"
        lines.append(bb_str)

    # Relative Strength vs SPY
    rs = snapshot.get("rs_vs_spy")
    if rs is not None:
        rs_label = "outperforming" if rs > 0 else "underperforming"
        lines.append(f"Relative Strength vs SPY (20d): {rs:+.1f}% ({rs_label})")

    # Volatility regime
    hv = snapshot.get("hv20")
    hv_pct = snapshot.get("hv_percentile")
    if hv is not None and hv_pct is not None:
        hv_min = snapshot.get("hv_min_1y")
        hv_max = snapshot.get("hv_max_1y")
        hv_trend = snapshot.get("hv_trend", "?")
        vol_line = f"HV(20): {hv:.1f}% [percentile: {hv_pct}%]"
        if hv_min is not None and hv_max is not None:
            vol_line += f" | 1Y range: {hv_min:.1f}%-{hv_max:.1f}%"
        vol_line += f" | Trend: {hv_trend}"
        lines.append(vol_line)
        # Regime guidance (HV percentile as IV proxy — HV and IV are highly correlated for swing timeframes)
        if hv_pct < 25:
            lines.append("Vol regime: Low HV — options premium is cheap relative to history. Debit structures (long options, debit spreads) are attractively priced for convex trades.")
        elif hv_pct < 50:
            lines.append("Vol regime: Below-average HV — neutral premium environment. Debit spreads work well here.")
        elif hv_pct < 75:
            lines.append("Vol regime: Elevated HV — options are historically expensive. Use debit SPREADS to reduce vega exposure while maintaining convex payoff. Reduce position size if needed.")
        else:
            lines.append("Vol regime: High HV — premium is very expensive. Use tighter debit spreads (narrower width) or go further OTM to manage cost. Reduce size. Do NOT switch to credit/selling strategies — that's an institutional approach, not retail.")

    return "\n".join(lines)


# ── Economic Calendar ─────────────────────────────────────────

ECON_CALENDAR_FILE = DATA_DIR / "econ_calendar_2026.json"


def fetch_economic_calendar(dte_days: int = 30) -> list[dict]:
    """
    Load upcoming economic events within dte_days from today.
    Reads from a static JSON file of known high-impact events.
    Returns list of {event, date, days_until, impact} dicts.
    """
    try:
        if not ECON_CALENDAR_FILE.exists():
            _log.debug("No economic calendar file found at %s", ECON_CALENDAR_FILE)
            return []

        events = json.loads(ECON_CALENDAR_FILE.read_text(encoding="utf-8"))
        today = _dt.date.today()
        cutoff = today + _dt.timedelta(days=dte_days)

        upcoming = []
        for ev in events:
            try:
                ev_date = _dt.date.fromisoformat(ev["date"])
                if today <= ev_date <= cutoff:
                    upcoming.append({
                        "event": ev["event"],
                        "date": ev["date"],
                        "days_until": (ev_date - today).days,
                        "impact": ev.get("impact", "MEDIUM"),
                    })
            except (KeyError, ValueError):
                continue

        return sorted(upcoming, key=lambda x: x["days_until"])
    except Exception as e:
        _log.warning("Failed to load economic calendar: %s", e)
        return []


def format_economic_calendar(events: list[dict]) -> str:
    """Render upcoming economic events into a context block for LLM agents."""
    if not events:
        return ""

    lines = ["## ECONOMIC CALENDAR (within DTE window)"]
    for ev in events:
        d = _dt.date.fromisoformat(ev["date"])
        date_str = d.strftime("%b %d")
        days = ev["days_until"]
        impact = ev["impact"]
        day_label = "TODAY" if days == 0 else "TOMORROW" if days == 1 else f"{days} days away"
        lines.append(f"- {date_str}: {ev['event']} ({impact}) — {day_label}")

    return "\n".join(lines)


# ── Portfolio Context ─────────────────────────────────────────

def fetch_portfolio_context(api_url: str) -> dict:
    """
    Fetch portfolio balances + active positions from Railway API.
    Returns dict with 'balances' and 'positions' keys, or {} on failure.
    Never raises — committee runs without portfolio data if this fails.
    """
    import urllib.request
    import urllib.error

    base = api_url.rstrip("/")
    result = {}

    # Try v2 unified positions summary first (Brief 10)
    try:
        req = urllib.request.Request(f"{base}/api/v2/positions/summary")
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "position_count" in data:
                result = {"v2_summary": data}
                # Also try to fetch greeks from Polygon.io
                try:
                    greq = urllib.request.Request(f"{base}/api/v2/positions/greeks")
                    with urllib.request.urlopen(greq, timeout=15) as gresp:
                        greeks_data = json.loads(gresp.read().decode("utf-8"))
                        if greeks_data.get("status") == "ok":
                            result["greeks"] = greeks_data
                except Exception as ge:
                    _log.debug("Portfolio greeks unavailable: %s", ge)
                return result
    except Exception as e:
        _log.debug("v2 portfolio summary unavailable, falling back to v1: %s", e)

    # Fallback: Fetch balances
    try:
        req = urllib.request.Request(f"{base}/api/portfolio/balances")
        with urllib.request.urlopen(req, timeout=8) as resp:
            result["balances"] = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        _log.debug("Portfolio balances unavailable: %s", e)

    # Fallback: Fetch active positions
    try:
        req = urllib.request.Request(f"{base}/api/portfolio/positions")
        with urllib.request.urlopen(req, timeout=8) as resp:
            result["positions"] = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        _log.debug("Portfolio positions unavailable: %s", e)

    return result


def format_portfolio_context(portfolio: dict) -> str:
    """Render terse portfolio summary as a context block for LLM agents."""
    if not portfolio:
        return ""

    # v2 unified summary (Brief 10) — uses max_loss for capital at risk
    v2 = portfolio.get("v2_summary")
    if v2:
        lines = ["## PORTFOLIO CONTEXT"]
        bal = v2.get("account_balance", 0)
        lines.append(f"Account: ${bal:,.0f} (Robinhood)")
        count = v2.get("position_count", 0)
        risk = v2.get("capital_at_risk", 0)
        risk_pct = v2.get("capital_at_risk_pct", 0)
        lines.append(f"Open: {count} positions | Capital at risk: ${risk:,.0f} ({risk_pct:.1f}% of account) — sum of max losses")
        for p in (v2.get("positions") or []):
            ticker = p.get("ticker", "?")
            structure = (p.get("structure") or "equity").replace("_", " ")
            strikes = ""
            if p.get("long_strike") or p.get("short_strike"):
                s_parts = [str(int(s)) for s in [p.get("long_strike"), p.get("short_strike")] if s]
                strikes = "/".join(s_parts) + " "
            expiry = str(p["expiry"])[:10] + " " if p.get("expiry") else ""
            qty = p.get("quantity", 1)
            max_loss = p.get("max_loss")
            ml_str = f"max loss ${max_loss:,.0f}" if max_loss else "risk unknown"
            dte = p.get("dte")
            dte_str = f"DTE {dte}" if dte is not None else ""
            lines.append(f"- {ticker} {structure} {strikes}{expiry}({qty} contracts) — {ml_str}, {dte_str}")
        nearest = v2.get("nearest_dte")
        if nearest is not None:
            lines.append(f"Nearest expiry: {nearest} DTE")
        net_dir = v2.get("net_direction", "FLAT")
        bd = v2.get("direction_breakdown", {})
        lines.append(f"Net lean: {net_dir.lower()} ({bd.get('long', 0)} bullish, {bd.get('short', 0)} bearish, {bd.get('mixed', 0)} neutral)")
        # Greeks context (from Polygon.io if available)
        greeks = portfolio.get("greeks")
        if greeks:
            port_g = greeks.get("portfolio", {})
            lines.append(f"Portfolio greeks: delta {port_g.get('net_delta', '?')}, gamma {port_g.get('net_gamma', '?')}, theta {port_g.get('net_theta', '?')}/day, vega {port_g.get('net_vega', '?')}")
            for tk, tg in (greeks.get("tickers") or {}).items():
                if "error" not in tg:
                    lines.append(f"  {tk}: delta {tg.get('net_delta', '?')}, theta {tg.get('net_theta', '?')}/day, underlying ${tg.get('underlying_price', '?')}")

        lines.append("NOTE: Portfolio context is for awareness only. Evaluate this signal on its own setup quality.")
        return "\n".join(lines)

    # Fallback to v1 format
    lines = ["## PORTFOLIO CONTEXT"]

    balances = portfolio.get("balances") or []
    rh = None
    account_balance = None
    for b in balances:
        if (b.get("broker") or "").lower() == "robinhood" or (b.get("account_name") or "").lower() == "robinhood":
            rh = b
            break
    if not rh and balances:
        rh = balances[0]

    if rh:
        account_balance = rh.get("balance")
        buying_power = rh.get("buying_power")
        bal_str = f"Account: ${account_balance:,.0f}" if account_balance else "Account: unknown"
        if buying_power:
            bal_str += f" | Buying power: ${buying_power:,.0f}"
        lines.append(bal_str)

    positions = portfolio.get("positions") or []
    if positions:
        total_cost = 0.0
        pos_parts = []
        for p in positions:
            ticker = p.get("ticker", "?")
            direction = (p.get("direction") or "?").upper()
            spread = p.get("spread_type") or p.get("option_type") or "option"
            cost = float(p.get("cost_basis") or 0)
            total_cost += cost
            pos_parts.append(f"{ticker} {direction} {spread}")
        lines.append(f"Open positions ({len(positions)}): {', '.join(pos_parts[:8])}")
        if len(pos_parts) > 8:
            lines.append(f"  ... and {len(pos_parts) - 8} more")
        if total_cost > 0:
            cap_str = f"Capital at risk: ~${total_cost:,.0f}"
            if account_balance and account_balance > 0:
                pct = (total_cost / account_balance) * 100
                cap_str += f" (~{pct:.1f}% of account)"
            lines.append(cap_str)
    else:
        lines.append("Open positions: none recorded")

    return "\n".join(lines) if len(lines) > 1 else ""


# ── Recent P&L Context ───────────────────────────────────────

def fetch_recent_pnl_context() -> str:
    """
    Load last 5 trade outcomes from outcome_log.jsonl for loss streak tracking.
    Returns formatted context block with results and playbook warnings.
    Returns empty string if no data or on failure.
    """
    outcome_file = DATA_DIR / "outcome_log.jsonl"
    try:
        if not outcome_file.exists():
            return ""

        # Read last 5 entries from JSONL
        entries = []
        with open(outcome_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        if not entries:
            return ""

        # Sort by matched_at descending, take last 5
        entries.sort(key=lambda x: x.get("matched_at", ""), reverse=True)
        recent = entries[:5]

        results = [e.get("result", "UNKNOWN") for e in recent]
        if not results:
            return ""

        lines = ["## RECENT TRADE RESULTS"]
        lines.append(f"Last {len(results)}: {', '.join(results)}")

        # Count consecutive losses from most recent
        consec_losses = 0
        for r in results:
            if r in ("LOSS",):
                consec_losses += 1
            else:
                break

        if consec_losses >= 2:
            lines.append(f"Current streak: {consec_losses} consecutive losses")
            lines.append("PLAYBOOK RULE: After 2 consecutive losses, reduce position size to 50% until a winner lands.")
        elif consec_losses == 1:
            lines.append("Last trade was a loss — one more loss triggers the 50% size reduction rule.")

        return "\n".join(lines)
    except Exception as e:
        _log.debug("P&L context unavailable: %s", e)
        return ""


# ── Agent Feedback Injection ──────────────────────────────────

def _get_agent_feedback_context(agent_name: str) -> str:
    """
    Load per-agent performance feedback (generated weekly by committee_review.py).
    Returns a context block for the specific agent, or empty string.
    """
    feedback_file = DATA_DIR / "agent_feedback.json"
    try:
        if not feedback_file.exists():
            return ""
        data = json.loads(feedback_file.read_text(encoding="utf-8"))
        agent_key = agent_name.lower()
        agent_data = data.get(agent_key)
        if not agent_data:
            return ""

        parts = [f"\n\n## YOUR RECENT PERFORMANCE ({agent_name.upper()})"]
        if agent_data.get("accuracy_summary"):
            parts.append(agent_data["accuracy_summary"])
        if agent_data.get("strengths"):
            parts.append(f"Strengths: {agent_data['strengths']}")
        if agent_data.get("weaknesses"):
            parts.append(f"Weaknesses: {agent_data['weaknesses']}")
        if agent_data.get("directive"):
            parts.append(f"Directive: {agent_data['directive']}")
        return "\n".join(parts)
    except Exception as e:
        _log.warning("Failed to load agent feedback for %s: %s", agent_name, e)
        return ""
