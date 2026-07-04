"""Provisional (intraday) theme scores from live prices.

Adapted from Stable Market Board by Ryan Scott (shared within The Stable, 2026).
yfinance-only (zero UW calls).

Structural metrics (MAs, ATR extension, 20D/52W highs, 20D returns, RS) stay anchored
to the last completed daily close in stable_metrics — we do NOT recompute those
intraday. We only re-derive the price-relative breadth booleans (above 20/50/200 DMA,
fresh 20D high) and the day return / up-down-3% counts against the live price, then
re-run the identical theme-score blend and store with anchor='provisional'.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from . import db, scoring

logger = logging.getLogger(__name__)


def fetch_live_prices(tickers: list[str]) -> dict[str, float]:
    """Batched current-day price pull (yfinance). Returns {ticker: last_price}."""
    import yfinance as yf
    out: dict[str, float] = {}
    if not tickers:
        return out
    try:
        data = yf.download(tickers, period="1d", interval="1d",
                           auto_adjust=True, group_by="ticker",
                           progress=False, threads=True, actions=False)
    except Exception as e:
        logger.warning("[stable_live] live price pull failed: %s", e)
        return out
    if data is None or data.empty:
        return out
    single = len(tickers) == 1
    for t in tickers:
        try:
            sub = data if single else (data[t] if isinstance(data.columns, pd.MultiIndex)
                                       and t in data.columns.get_level_values(0) else None)
            if sub is None or sub.empty or "Close" not in sub.columns:
                continue
            close = sub["Close"].dropna()
            if not close.empty:
                out[t] = float(close.iloc[-1])
        except Exception:
            continue
    return out


def _latest_close_metrics() -> pd.DataFrame:
    """Per-ticker latest-close structural metrics + last close, joined with universe."""
    return db.read_df("""
        SELECT u.theme, u.ticker, m.date,
               m.ma_20, m.ma_50, m.ma_200, m.high_20d,
               m.ret_5d, m.ret_20d, m.new_high_52w, m.atr_ext_50ma, m.rs_qqq_20d,
               b.c AS last_close
        FROM stable_metrics m
        JOIN stable_universe u ON u.ticker = m.ticker
        JOIN stable_daily_bars b ON b.ticker = m.ticker AND b.date = m.date
        WHERE m.date = (SELECT MAX(date) FROM stable_metrics)
    """)


def compute_provisional_theme_scores(live: dict[str, float]) -> tuple[pd.DataFrame, dict]:
    """Re-derive theme scores against live prices. Returns (scores_df, breadth_counts)."""
    base = _latest_close_metrics()
    if base.empty or not live:
        return pd.DataFrame(), {}

    base = base[base["ticker"].isin(live.keys())].copy()
    if base.empty:
        return pd.DataFrame(), {}
    base["live"] = base["ticker"].map(live)

    # Live-adjusted price-relative signals (structural MAs/highs unchanged)
    base["above_ma20"] = (base["live"] > base["ma_20"]).astype("float").where(base["ma_20"].notna())
    base["above_ma50"] = (base["live"] > base["ma_50"]).astype("float").where(base["ma_50"].notna())
    base["above_ma200"] = (base["live"] > base["ma_200"]).astype("float").where(base["ma_200"].notna())
    base["new_high_20d"] = (base["live"] >= base["high_20d"]).astype("float").where(base["high_20d"].notna())
    base["live_ret_1d"] = base["live"] / base["last_close"] - 1.0

    # Universe-wide up/down-3% counts (breadth impulse), excluding excluded themes
    scan = base[~base["theme"].isin(scoring.EXCLUDED_THEMES)]
    breadth_counts = {
        "total": int(len(scan)),
        "up_3": int((scan["live_ret_1d"] > 0.03).sum()),
        "down_3": int((scan["live_ret_1d"] < -0.03).sum()),
        "pct_above_20ma": round(float(scan["above_ma20"].dropna().mean() * 100), 1) if len(scan) else 0.0,
        "pct_above_200ma": round(float(scan["above_ma200"].dropna().mean() * 100), 1) if len(scan) else 0.0,
    }

    # Prior close scores for the intraday delta
    prior = db.read_df("""
        SELECT theme, score FROM stable_theme_scores
        WHERE anchor = 'close' AND date = (SELECT MAX(date) FROM stable_theme_scores WHERE anchor='close')
    """)
    prior_map = {r["theme"]: r["score"] for _, r in prior.iterrows()} if not prior.empty else {}

    rows = []
    for theme, group in base.groupby("theme"):
        if theme in scoring.EXCLUDED_THEMES or len(group) < 3:
            continue
        pct_above_20 = scoring._safe_pct(group["above_ma20"])
        pct_above_50 = scoring._safe_pct(group["above_ma50"])
        pct_above_200 = scoring._safe_pct(group["above_ma200"])
        pct_new_high_20 = scoring._safe_pct(group["new_high_20d"])
        pct_new_high_52w = scoring._safe_pct((group["new_high_52w"]).astype("float"))

        avg_ret_5d = float(group["ret_5d"].mean(skipna=True) or 0)
        avg_ret_20d = float(group["ret_20d"].mean(skipna=True) or 0)      # structural, from close
        avg_atr_ext = float(group["atr_ext_50ma"].mean(skipna=True) or 0)  # structural
        avg_rs_qqq = float(group["rs_qqq_20d"].mean(skipna=True) or 0)      # structural

        breadth = (pct_above_20 + pct_above_50) / 2
        leadership = (pct_new_high_20 * 0.6 + pct_above_200 * 0.4)
        momentum = scoring._scale_to_100(avg_ret_20d, -0.10, 0.15)
        extension_raw = max(0, min(avg_atr_ext, 15))
        score = (0.30 * breadth + 0.25 * leadership + 0.30 * momentum +
                 0.15 * (50 + avg_rs_qqq * 500))
        score = max(0, min(100, score))
        score_1d_delta = round(score - prior_map.get(theme, score), 2)

        rows.append({
            "date": group["date"].iloc[0], "theme": theme, "n_names": len(group),
            "score": round(score, 1), "breadth": round(breadth, 1),
            "leadership": round(leadership, 1), "momentum": round(momentum, 1),
            "extension_raw": round(extension_raw, 2),
            "pct_above_20ma": round(pct_above_20, 1), "pct_above_50ma": round(pct_above_50, 1),
            "pct_above_200ma": round(pct_above_200, 1), "pct_new_high_20d": round(pct_new_high_20, 1),
            "pct_new_high_52w": round(pct_new_high_52w, 1),
            "avg_ret_5d": round(avg_ret_5d, 4), "avg_ret_20d": round(avg_ret_20d, 4),
            "avg_atr_ext_50ma": round(avg_atr_ext, 2), "avg_rs_qqq_20d": round(avg_rs_qqq, 4),
            "score_1d_delta": score_1d_delta,
        })

    if not rows:
        return pd.DataFrame(), breadth_counts

    def _label(r):
        s, d, ext = r["score"], r["score_1d_delta"], r["extension_raw"]
        if s >= 75 and ext > 6: return "STRONG / HOT"
        if s >= 75: return "DOMINANT"
        if s >= 60 and d > 2: return "EMERGING"
        if s >= 60: return "STRONG"
        if s <= 35 and d < -2: return "FADING"
        if s <= 35: return "WEAK"
        if d > 3: return "IMPROVING"
        if d < -3: return "DETERIORATING"
        return "NEUTRAL"

    out = pd.DataFrame(rows)
    out["status"] = out.apply(_label, axis=1)
    out = out.sort_values("score", ascending=False).reset_index(drop=True)
    out["rank"] = out.index + 1
    return out, breadth_counts


def run_provisional_snapshot(tickers: list[str], degraded_universe: bool = False) -> dict:
    """Pull live prices, recompute provisional theme scores, store anchor='provisional'."""
    live = fetch_live_prices(tickers)
    if not live:
        logger.warning("[stable_live] no live prices — provisional snapshot skipped")
        return {"stored": 0, "live_count": 0, "degraded": True}
    scores, breadth = compute_provisional_theme_scores(live)
    coverage_ok = len(live) >= 0.9 * len([t for t in tickers if t])
    degraded = degraded_universe or not coverage_ok
    stored = scoring.store_theme_scores(scores, anchor="provisional",
                                        as_of=datetime.now(timezone.utc), degraded=degraded)
    logger.info("[stable_live] provisional snapshot: %d live, %d themes stored, up3=%s down3=%s degraded=%s",
                len(live), stored, breadth.get("up_3"), breadth.get("down_3"), degraded)
    return {"stored": stored, "live_count": len(live), "breadth": breadth, "degraded": degraded}
