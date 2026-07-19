"""Theme scoring layer.

Aggregates per-ticker metrics into theme-level scores.
This is V1 - intentionally simple. We iterate on weights and components after
seeing the dashboard with real data.

Score components (each 0-100):
- breadth: % of basket above 20DMA, 50DMA
- leadership: % making 20D highs, % above 200DMA
- momentum: average 5D and 20D returns vs benchmark
- acceleration: 5D delta in breadth (theme getting stronger or weaker?)
- extension penalty: average ATR extension, capped (hot themes get docked)

Final score is a weighted blend, with a status label and a 1D delta.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from . import db, settings as settings_mod


# Themes excluded from scoring (benchmarks, broad ETF sleeves, scan-only universe)
EXCLUDED_THEMES = {"Benchmark", "Scan Only"}


def _safe_pct(series: pd.Series) -> float:
    """Mean of a 0/1 series as percentage, NaN-safe."""
    s = series.dropna()
    if len(s) == 0:
        return 0.0
    return float(s.mean()) * 100


def _scale_to_100(value: float, low: float, high: float) -> float:
    """Linearly map `value` from [low, high] to [0, 100], clamped."""
    if high == low:
        return 50.0
    pct = (value - low) / (high - low) * 100
    return max(0.0, min(100.0, pct))


def compute_theme_scores(as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    """Compute one row per theme for the latest date (or as_of).

    Returns columns:
      theme, n_names, score, status, breadth, leadership, momentum, accel, extension,
      pct_above_20ma, pct_above_50ma, pct_new_high_20d, avg_ret_5d, avg_ret_20d,
      avg_atr_ext_50ma, avg_rs_qqq_20d, score_1d_delta
    """
    with db.connect(read_only=True) as conn:
        latest_date = conn.execute("SELECT MAX(date) FROM metrics").fetchone()[0]
        if as_of is None:
            as_of = latest_date

        # Pull latest + 1-day-prior metrics joined with universe
        df = conn.execute("""
            SELECT u.theme, u.ticker, u.liquidity_tier,
                   m.date, m.ret_5d, m.ret_20d,
                   m.above_ma20, m.above_ma50, m.above_ma200,
                   m.new_high_20d, m.new_high_52w,
                   m.atr_ext_50ma, m.rs_qqq_20d, m.rs_rsp_20d,
                   m.dist_ma50_pct, m.vol_ratio
            FROM metrics m
            JOIN universe u ON u.ticker = m.ticker
            WHERE m.date IN (
                SELECT DISTINCT date FROM metrics
                WHERE date <= ?
                ORDER BY date DESC LIMIT 6
            )
        """, [as_of]).df()

    if df.empty:
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"])
    today = df["date"].max()
    yesterday_dates = sorted(df["date"].unique(), reverse=True)
    prior = yesterday_dates[1] if len(yesterday_dates) > 1 else today

    rows = []
    for date_val in [today, prior]:
        sub = df[df["date"] == date_val]
        for theme, group in sub.groupby("theme"):
            if theme in EXCLUDED_THEMES:
                continue
            n = len(group)
            if n < 3:
                continue

            pct_above_20 = _safe_pct(group["above_ma20"])
            pct_above_50 = _safe_pct(group["above_ma50"])
            pct_above_200 = _safe_pct(group["above_ma200"])
            pct_new_high_20 = _safe_pct(group["new_high_20d"])
            pct_new_high_52w = _safe_pct(group["new_high_52w"])

            avg_ret_5d = float(group["ret_5d"].mean(skipna=True) or 0)
            avg_ret_20d = float(group["ret_20d"].mean(skipna=True) or 0)
            avg_atr_ext = float(group["atr_ext_50ma"].mean(skipna=True) or 0)
            avg_rs_qqq = float(group["rs_qqq_20d"].mean(skipna=True) or 0)

            # Sub-scores (each 0-100)
            breadth = (pct_above_20 + pct_above_50) / 2
            leadership = (pct_new_high_20 * 0.6 + pct_above_200 * 0.4)
            # Momentum: 20D return vs typical range (-10% to +15%)
            momentum = _scale_to_100(avg_ret_20d, -0.10, 0.15)
            # Extension penalty: hot if avg ATR ext > 5
            extension_raw = max(0, min(avg_atr_ext, 15))
            # Final score: weighted blend
            score = (
                0.30 * breadth +
                0.25 * leadership +
                0.30 * momentum +
                0.15 * (50 + avg_rs_qqq * 500)  # RS centered at 50, ±50% range
            )
            score = max(0, min(100, score))

            rows.append({
                "date": date_val,
                "theme": theme,
                "n_names": n,
                "score": round(score, 1),
                "breadth": round(breadth, 1),
                "leadership": round(leadership, 1),
                "momentum": round(momentum, 1),
                "extension_raw": round(extension_raw, 2),
                "pct_above_20ma": round(pct_above_20, 1),
                "pct_above_50ma": round(pct_above_50, 1),
                "pct_above_200ma": round(pct_above_200, 1),
                "pct_new_high_20d": round(pct_new_high_20, 1),
                "pct_new_high_52w": round(pct_new_high_52w, 1),
                "avg_ret_5d": round(avg_ret_5d, 4),
                "avg_ret_20d": round(avg_ret_20d, 4),
                "avg_atr_ext_50ma": round(avg_atr_ext, 2),
                "avg_rs_qqq_20d": round(avg_rs_qqq, 4),
            })

    if not rows:
        return pd.DataFrame()

    all_scores = pd.DataFrame(rows)
    today_scores = all_scores[all_scores["date"] == today].copy()
    prior_scores = all_scores[all_scores["date"] == prior].set_index("theme")["score"]

    today_scores["score_1d_delta"] = today_scores["theme"].map(
        lambda t: round(today_scores[today_scores["theme"] == t]["score"].iloc[0] -
                       prior_scores.get(t, today_scores[today_scores["theme"] == t]["score"].iloc[0]), 2)
    )

    # Status labels
    def label(row):
        s = row["score"]
        d = row["score_1d_delta"]
        ext = row["extension_raw"]
        if s >= 75 and ext > 6:
            return "STRONG / HOT"
        if s >= 75:
            return "DOMINANT"
        if s >= 60 and d > 2:
            return "EMERGING"
        if s >= 60:
            return "STRONG"
        if s <= 35 and d < -2:
            return "FADING"
        if s <= 35:
            return "WEAK"
        if d > 3:
            return "IMPROVING"
        if d < -3:
            return "DETERIORATING"
        return "NEUTRAL"

    today_scores["status"] = today_scores.apply(label, axis=1)
    today_scores = today_scores.sort_values("score", ascending=False).reset_index(drop=True)
    today_scores["rank"] = today_scores.index + 1

    return today_scores


def get_theme_constituents(theme: str, limit: int = 50) -> pd.DataFrame:
    """Get latest metrics for all tickers in a theme, sorted by 5D return."""
    with db.connect(read_only=True) as conn:
        latest_date = conn.execute("SELECT MAX(date) FROM metrics").fetchone()[0]
        df = conn.execute("""
            SELECT u.ticker, u.name, u.subtheme, u.liquidity_tier,
                   m.ret_1d, m.ret_5d, m.ret_20d,
                   m.dist_ma20_pct, m.dist_ma50_pct,
                   m.above_ma20, m.above_ma50, m.above_ma200,
                   m.atr_ext_50ma, m.vol_ratio,
                   m.new_high_20d, m.new_high_52w,
                   m.rs_qqq_20d
            FROM metrics m
            JOIN universe u ON u.ticker = m.ticker
            WHERE u.theme = ? AND m.date = ?
            ORDER BY m.ret_5d DESC NULLS LAST
            LIMIT ?
        """, [theme, latest_date, limit]).df()
    return df


def get_extension_lists() -> dict:
    """Return three lists: too_hot, clean_momentum, fading."""
    cfg = settings_mod.load()
    too_hot_threshold = cfg["extension"]["too_hot_atr_threshold"]
    cm_atr_min = cfg["extension"]["clean_momentum_atr_min"]
    cm_atr_max = cfg["extension"]["clean_momentum_atr_max"]
    cm_min_vol = cfg["extension"]["clean_momentum_min_vol_ratio"]
    cm_min_ret_5d = cfg["extension"]["clean_momentum_min_ret_5d"]

    with db.connect(read_only=True) as conn:
        latest_date = conn.execute("SELECT MAX(date) FROM metrics").fetchone()[0]
        df = conn.execute("""
            SELECT u.ticker, u.name, u.theme, u.subtheme, u.liquidity_tier,
                   m.ret_1d, m.ret_5d, m.ret_20d,
                   m.dist_ma50_pct, m.atr_ext_50ma, m.vol_ratio,
                   m.above_ma20, m.above_ma50,
                   m.new_high_20d, m.new_high_52w,
                   m.rs_qqq_20d
            FROM metrics m
            JOIN universe u ON u.ticker = m.ticker
            WHERE m.date = ? AND u.liquidity_tier IN ('Core', 'Active')
                AND m.atr_ext_50ma IS NOT NULL
        """, [latest_date]).df()

    if df.empty:
        return {"too_hot": [], "clean_momentum": [], "fading": []}

    # Too hot: ≥ N ATRs above 50DMA (configurable)
    too_hot = df[df["atr_ext_50ma"] >= too_hot_threshold].sort_values(
        "atr_ext_50ma", ascending=False
    ).head(20)

    # Clean momentum: above both MAs, positive 5D, ATR ext in configured range, vol > min
    clean = df[
        (df["above_ma20"] == 1) &
        (df["above_ma50"] == 1) &
        (df["ret_5d"] > cm_min_ret_5d) &
        (df["atr_ext_50ma"].between(cm_atr_min, cm_atr_max)) &
        (df["vol_ratio"] > cm_min_vol)
    ].sort_values("rs_qqq_20d", ascending=False).head(25)

    # Fading: lost 20DMA, was extended recently
    fading = df[
        (df["above_ma20"] == 0) &
        (df["ret_5d"] < -0.03)
    ].sort_values("ret_5d").head(20)

    return {
        "too_hot": too_hot.to_dict("records"),
        "clean_momentum": clean.to_dict("records"),
        "fading": fading.to_dict("records"),
        "_thresholds": {
            "too_hot_atr": too_hot_threshold,
            "clean_atr_min": cm_atr_min,
            "clean_atr_max": cm_atr_max,
            "clean_min_vol": cm_min_vol,
            "clean_min_ret_5d": cm_min_ret_5d,
        }
    }


def get_regime_read() -> dict:
    """Top-level regime read using benchmark and breadth data."""
    cfg = settings_mod.load()
    big_move = cfg["breadth"]["big_move_threshold"]

    with db.connect(read_only=True) as conn:
        latest = conn.execute("SELECT MAX(date) FROM metrics").fetchone()[0]
        bench = conn.execute("""
            SELECT u.ticker, u.subtheme, m.ret_1d, m.ret_5d, m.ret_20d,
                   m.dist_ma20_pct, m.dist_ma50_pct, m.atr_ext_50ma,
                   m.above_ma20, m.above_ma50, m.above_ma200
            FROM metrics m JOIN universe u ON u.ticker = m.ticker
            WHERE m.date = ? AND u.theme = 'Benchmark'
            ORDER BY u.ticker
        """, [latest]).df()

        # Universe-wide breadth (excluding benchmarks and scan-only names)
        # Use parameterized big_move threshold
        breadth = conn.execute(f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN m.above_ma20 = 1 THEN 1 ELSE 0 END) AS above_20,
                SUM(CASE WHEN m.above_ma50 = 1 THEN 1 ELSE 0 END) AS above_50,
                SUM(CASE WHEN m.above_ma200 = 1 THEN 1 ELSE 0 END) AS above_200,
                SUM(CASE WHEN m.new_high_20d = 1 THEN 1 ELSE 0 END) AS new_high_20d,
                SUM(CASE WHEN m.new_high_52w = 1 THEN 1 ELSE 0 END) AS new_high_52w,
                SUM(CASE WHEN m.ret_1d > {big_move} THEN 1 ELSE 0 END) AS up_big,
                SUM(CASE WHEN m.ret_1d < -{big_move} THEN 1 ELSE 0 END) AS down_big
            FROM metrics m JOIN universe u ON u.ticker = m.ticker
            WHERE m.date = ? AND u.theme NOT IN ('Benchmark', 'Scan Only')
        """, [latest]).df().iloc[0].to_dict()

    return {
        "as_of": str(latest),
        "benchmarks": bench.to_dict("records"),
        "breadth": breadth,
        "thresholds": {
            "big_move_pct": big_move * 100,
        },
    }


def _ratio_perf(df: pd.DataFrame, num: str, den: str) -> dict:
    """Compute pair performance: ratio of two tickers' total return over 1/5/20 days.

    Positive value means num is outperforming den.
    """
    n = df[df["ticker"] == num]
    d = df[df["ticker"] == den]
    if n.empty or d.empty:
        return {"num": num, "den": den, "label": f"{num} / {den}",
                "ret_1d": None, "ret_5d": None, "ret_20d": None}
    nrow = n.iloc[0]
    drow = d.iloc[0]

    def diff(a, b):
        if a is None or b is None or pd.isna(a) or pd.isna(b):
            return None
        return float(a) - float(b)

    return {
        "num": num,
        "den": den,
        "label": f"{num} / {den}",
        "ret_1d": diff(nrow.get("ret_1d"), drow.get("ret_1d")),
        "ret_5d": diff(nrow.get("ret_5d"), drow.get("ret_5d")),
        "ret_20d": diff(nrow.get("ret_20d"), drow.get("ret_20d")),
        "num_dist_50ma": nrow.get("dist_ma50_pct"),
        "den_dist_50ma": drow.get("dist_ma50_pct"),
    }


def get_etf_pulse() -> dict:
    """Cross-asset ETF rotation read.

    Returns three groups:
      - style_rotation: small/large, equal/cap weight, growth/value
      - risk_pulse: junk/duration, USD, gold/SPY, VIX
      - sector_rotation: 11 sector ETFs ranked by 5D and 20D performance
    """
    with db.connect(read_only=True) as conn:
        latest = conn.execute("SELECT MAX(date) FROM metrics").fetchone()[0]
        df = conn.execute("""
            SELECT u.ticker, u.subtheme, m.ret_1d, m.ret_5d, m.ret_20d,
                   m.dist_ma20_pct, m.dist_ma50_pct, m.atr_ext_50ma,
                   m.above_ma50, m.above_ma200, m.vol_ratio
            FROM metrics m JOIN universe u ON u.ticker = m.ticker
            WHERE m.date = ?
        """, [latest]).df()

    # Style rotation pairs
    style_pairs = [
        ("IWM", "SPY"),    # small vs large
        ("RSP", "SPY"),    # equal weight vs cap weight (narrowness signal)
        ("QQQ", "SPY"),    # growth-heavy vs broad
        ("IWF", "IWD"),    # explicit growth vs value
        ("EEM", "SPY"),    # emerging vs US
    ]
    style_rotation = [_ratio_perf(df, n, d) for n, d in style_pairs]

    # Risk-on / risk-off pulse
    risk_pulse = []
    risk_pairs = [
        ("HYG", "TLT", "junk vs duration"),     # high yield over treasuries = risk-on
        ("GLD", "SPY", "gold vs equities"),     # gold over SPY = risk-off
        ("UUP", None, "USD strength"),          # standalone
        ("UVXY", None, "VIX"),                  # standalone
        ("TLT", None, "long bonds"),            # standalone
    ]
    for spec in risk_pairs:
        if spec[1] is None:
            sub = df[df["ticker"] == spec[0]]
            if sub.empty:
                continue
            row = sub.iloc[0]
            risk_pulse.append({
                "num": spec[0],
                "den": None,
                "label": spec[0],
                "context": spec[2],
                "ret_1d": float(row["ret_1d"]) if pd.notna(row["ret_1d"]) else None,
                "ret_5d": float(row["ret_5d"]) if pd.notna(row["ret_5d"]) else None,
                "ret_20d": float(row["ret_20d"]) if pd.notna(row["ret_20d"]) else None,
                "dist_50ma": float(row["dist_ma50_pct"]) if pd.notna(row["dist_ma50_pct"]) else None,
            })
        else:
            r = _ratio_perf(df, spec[0], spec[1])
            r["context"] = spec[2]
            risk_pulse.append(r)

    # Sector rotation - 11 sector ETFs
    sector_etfs = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLC", "XLRE"]
    spy_row = df[df["ticker"] == "SPY"]
    spy_5d = float(spy_row.iloc[0]["ret_5d"]) if not spy_row.empty and pd.notna(spy_row.iloc[0]["ret_5d"]) else 0.0
    spy_20d = float(spy_row.iloc[0]["ret_20d"]) if not spy_row.empty and pd.notna(spy_row.iloc[0]["ret_20d"]) else 0.0

    sector_data = []
    sector_labels = {
        "XLK": "Technology", "XLF": "Financials", "XLE": "Energy",
        "XLV": "Healthcare", "XLY": "Discretionary", "XLP": "Staples",
        "XLI": "Industrials", "XLU": "Utilities", "XLB": "Materials",
        "XLC": "Comm Services", "XLRE": "Real Estate",
    }
    for tk in sector_etfs:
        sub = df[df["ticker"] == tk]
        if sub.empty:
            continue
        row = sub.iloc[0]
        ret_5d = float(row["ret_5d"]) if pd.notna(row["ret_5d"]) else None
        ret_20d = float(row["ret_20d"]) if pd.notna(row["ret_20d"]) else None
        sector_data.append({
            "ticker": tk,
            "label": sector_labels.get(tk, tk),
            "ret_1d": float(row["ret_1d"]) if pd.notna(row["ret_1d"]) else None,
            "ret_5d": ret_5d,
            "ret_20d": ret_20d,
            "rs_spy_5d": (ret_5d - spy_5d) if ret_5d is not None else None,
            "rs_spy_20d": (ret_20d - spy_20d) if ret_20d is not None else None,
            "dist_50ma": float(row["dist_ma50_pct"]) if pd.notna(row["dist_ma50_pct"]) else None,
            "above_50": int(row["above_ma50"]) if pd.notna(row["above_ma50"]) else None,
        })

    # Sort by 20D RS vs SPY (clearest "leading vs lagging" signal)
    sector_data.sort(key=lambda x: x["rs_spy_20d"] or -999, reverse=True)

    return {
        "as_of": str(latest),
        "style_rotation": style_rotation,
        "risk_pulse": risk_pulse,
        "sector_rotation": sector_data,
    }


def get_vol_regime() -> dict:
    """Composite volatility regime read.

    Combines:
      - VXX level (short-term VIX futures proxy) and its 60-day percentile
      - VXX/VXZ ratio (term structure: > 1.0 backwardation = stress, < 1.0 contango = calm)
      - CBOE equity P/C ratio (latest + 10D SMA, sentiment label)
      - CBOE index P/C ratio (latest + 10D SMA, hedging activity)
      - Composite vol regime label
    """
    out = {
        "vxx_level": None,
        "vxx_pct_rank_60d": None,
        "vxx_5d_chg": None,
        "vxz_level": None,
        "vxx_vxz_ratio": None,
        "term_structure": None,        # "contango" | "backwardation" | "flat"
        "term_structure_5d_chg": None,
        "equity_pc": None,
        "equity_pc_10dma": None,
        "equity_pc_sentiment": None,   # "greedy" | "neutral" | "fearful" | "capitulation"
        "index_pc": None,
        "index_pc_10dma": None,
        "regime_label": None,          # composite
        "regime_color": None,          # for UI heat
        "pc_as_of": None,
    }

    # 1. VXX / VXZ from prices (we may not have metrics computed yet if these
    # are brand-new tickers, so go straight to prices)
    with db.connect(read_only=True) as conn:
        # Pull last 70 days of VXX and VXZ closes for percentile and ratio history
        vxx = conn.execute("""
            SELECT date, close FROM prices WHERE ticker = 'VXX'
            ORDER BY date DESC LIMIT 70
        """).df()
        vxz = conn.execute("""
            SELECT date, close FROM prices WHERE ticker = 'VXZ'
            ORDER BY date DESC LIMIT 70
        """).df()

    if not vxx.empty:
        vxx = vxx.sort_values("date").reset_index(drop=True)
        latest_vxx = float(vxx["close"].iloc[-1])
        out["vxx_level"] = latest_vxx
        # 60-day percentile rank (where does current sit in 60D distribution)
        vxx_60 = vxx["close"].tail(60)
        if len(vxx_60) >= 30:
            pct = (vxx_60 <= latest_vxx).mean() * 100
            out["vxx_pct_rank_60d"] = float(pct)
        if len(vxx) >= 6:
            prior = float(vxx["close"].iloc[-6])
            out["vxx_5d_chg"] = (latest_vxx / prior - 1.0) if prior else None

    if not vxz.empty and not vxx.empty:
        vxz = vxz.sort_values("date").reset_index(drop=True)
        latest_vxz = float(vxz["close"].iloc[-1])
        out["vxz_level"] = latest_vxz
        ratio = out["vxx_level"] / latest_vxz if latest_vxz else None
        out["vxx_vxz_ratio"] = ratio
        # Term structure label: VXX/VXZ < 1 means short-term vol cheaper than mid-term
        # = contango (calm). > 1 = backwardation (stress).
        if ratio is not None:
            if ratio >= 1.03:
                out["term_structure"] = "backwardation"
            elif ratio <= 0.97:
                out["term_structure"] = "contango"
            else:
                out["term_structure"] = "flat"
        # 5D ratio change to see if structure is shifting
        if len(vxx) >= 6 and len(vxz) >= 6:
            prior_vxx = float(vxx["close"].iloc[-6])
            prior_vxz = float(vxz["close"].iloc[-6])
            prior_ratio = prior_vxx / prior_vxz if prior_vxz else None
            if prior_ratio:
                out["term_structure_5d_chg"] = ratio - prior_ratio

    # 2. CBOE P/C ratios
    with db.connect(read_only=True) as conn:
        try:
            pc_df = conn.execute("""
                SELECT series, date, pc_ratio FROM cboe_pc
                WHERE date >= (SELECT MAX(date) - INTERVAL 30 DAY FROM cboe_pc)
                ORDER BY series, date
            """).df()
        except Exception:
            pc_df = pd.DataFrame()  # cboe_pc table missing or empty

    if not pc_df.empty:
        latest_pc_date = pc_df["date"].max()
        out["pc_as_of"] = str(latest_pc_date)

        for series_name, key_prefix in [("equity", "equity"), ("index", "index")]:
            sub = pc_df[pc_df["series"] == series_name].sort_values("date")
            if sub.empty:
                continue
            latest_val = float(sub["pc_ratio"].iloc[-1])
            ma10 = float(sub["pc_ratio"].tail(10).mean())
            out[f"{key_prefix}_pc"] = latest_val
            out[f"{key_prefix}_pc_10dma"] = ma10

            # Sentiment label only for equity P/C (the conventional sentiment gauge)
            if series_name == "equity":
                if latest_val < 0.55:
                    out["equity_pc_sentiment"] = "greedy"
                elif latest_val < 0.70:
                    out["equity_pc_sentiment"] = "neutral"
                elif latest_val < 1.0:
                    out["equity_pc_sentiment"] = "cautious"
                elif latest_val < 1.3:
                    out["equity_pc_sentiment"] = "fearful"
                else:
                    out["equity_pc_sentiment"] = "capitulation"

    # 3. Composite regime label
    # Logic: combine VXX percentile + term structure + equity P/C
    label = "NEUTRAL"
    color = "h-neu"
    vxx_pct = out["vxx_pct_rank_60d"]
    term = out["term_structure"]
    sentiment = out["equity_pc_sentiment"]

    if vxx_pct is not None:
        if vxx_pct <= 25 and term == "contango":
            label = "CALM"
            color = "h-pos-2"
            if sentiment in ("greedy",):
                label = "CALM / COMPLACENT"
                color = "h-pos-1"
        elif vxx_pct >= 75 and term == "backwardation":
            label = "STRESS"
            color = "h-neg-3"
        elif vxx_pct >= 60 or term == "backwardation":
            label = "ELEVATED"
            color = "h-neg-1"
        elif vxx_pct <= 35:
            label = "QUIET"
            color = "h-pos-1"

    out["regime_label"] = label
    out["regime_color"] = color

    return out


def get_theme_rotation(lookback_days: int = 5) -> dict:
    """Compute theme score deltas over `lookback_days` to find biggest climbers/fallers.

    For each theme, computes its score today and `lookback_days` ago, then ranks
    by absolute change.
    """
    with db.connect(read_only=True) as conn:
        # Get the trading dates we need: latest + N back
        dates = conn.execute("""
            SELECT DISTINCT date FROM metrics
            ORDER BY date DESC LIMIT ?
        """, [lookback_days + 1]).fetchall()

    if len(dates) < 2:
        return {"climbers": [], "fallers": [], "lookback_days": lookback_days}

    today_date = dates[0][0]
    past_date = dates[-1][0]

    today_scores = compute_theme_scores(as_of=pd.Timestamp(today_date))
    past_scores = compute_theme_scores(as_of=pd.Timestamp(past_date))

    if today_scores.empty or past_scores.empty:
        return {"climbers": [], "fallers": [], "lookback_days": lookback_days}

    # Build a comparison dataframe
    today_idx = today_scores.set_index("theme")[["score", "rank", "status"]]
    past_idx = past_scores.set_index("theme")[["score", "rank"]]
    past_idx.columns = ["score_then", "rank_then"]

    merged = today_idx.join(past_idx, how="left").reset_index()
    merged["score_delta"] = merged["score"] - merged["score_then"]
    merged["rank_delta"] = merged["rank_then"] - merged["rank"]  # positive = moved up
    merged = merged.dropna(subset=["score_delta"])

    climbers = merged.sort_values("score_delta", ascending=False).head(5).to_dict("records")
    fallers = merged.sort_values("score_delta", ascending=True).head(5).to_dict("records")

    return {
        "as_of": str(today_date),
        "from_date": str(past_date),
        "lookback_days": lookback_days,
        "climbers": climbers,
        "fallers": fallers,
    }


# ============================================================
# BREADTH TIME SERIES
# ============================================================

ALLOWED_LOOKBACK_DAYS = {
    "1M": 22,
    "3M": 63,
    "6M": 126,
    "1Y": 252,
}


def get_breadth_series(
    lookback: str = "3M",
    theme: str | None = None,
    tiers: tuple = ("Core", "Active"),
) -> dict:
    """Compute daily breadth time series for charting.

    Returns three series, each as parallel lists of dates and values:

    1. participation: % above 20DMA / 50DMA / 200DMA, per day
    2. impulse: daily advancers/decliners + new 20D highs/lows + big-move counts
    3. ad_line: cumulative advancers-minus-decliners alongside SPY close (rescaled)

    Args:
        lookback: one of "1M", "3M", "6M", "1Y"
        theme: optional theme name to filter the universe; None = all themes ex-benchmark
        tiers: tuple of liquidity tiers to include (default Core+Active)
    """
    days = ALLOWED_LOOKBACK_DAYS.get(lookback, 63)
    # For A/D line we always want at least 6 months of context for the SPY comparison
    ad_days = max(days, ALLOWED_LOOKBACK_DAYS["6M"])

    # The big-move threshold from user settings
    cfg = settings_mod.load()
    big_move = cfg["breadth"]["big_move_threshold"]

    # Build universe filter
    tier_list = list(tiers) if tiers else ["Core", "Active", "Watch"]
    tier_placeholders = ",".join(["?"] * len(tier_list))

    theme_filter = ""
    params_base: list = []
    if theme and theme != "All":
        theme_filter = " AND u.theme = ?"
        params_base.append(theme)
    else:
        theme_filter = " AND u.theme NOT IN ('Benchmark', 'Scan Only')"

    with db.connect(read_only=True) as conn:
        latest = conn.execute("SELECT MAX(date) FROM metrics").fetchone()[0]
        if latest is None:
            return _empty_breadth_payload(lookback, theme)

        # Long lookback for A/D line, then we'll trim Charts 1 & 2 to `days`
        df = conn.execute(f"""
            SELECT m.date,
                   m.above_ma20, m.above_ma50, m.above_ma200,
                   m.ret_1d, m.new_high_20d, m.new_high_52w
            FROM metrics m
            JOIN universe u ON u.ticker = m.ticker
            WHERE m.date >= (SELECT MAX(date) - INTERVAL {ad_days} DAY FROM metrics)
                  AND u.liquidity_tier IN ({tier_placeholders})
                  {theme_filter}
        """, tier_list + params_base).df()

        # SPY closes for the A/D vs SPY chart
        spy = conn.execute(f"""
            SELECT date, close
            FROM prices
            WHERE ticker = 'SPY'
              AND date >= (SELECT MAX(date) - INTERVAL {ad_days} DAY FROM prices)
            ORDER BY date
        """).df()

    if df.empty:
        return _empty_breadth_payload(lookback, theme)

    df["date"] = pd.to_datetime(df["date"])

    # Aggregate per-day
    grouped = df.groupby("date").agg(
        total=("above_ma20", "count"),
        above_20=("above_ma20", lambda s: int(s.fillna(0).sum())),
        above_50=("above_ma50", lambda s: int(s.fillna(0).sum())),
        above_200=("above_ma200", lambda s: int(s.fillna(0).sum())),
        advancers=("ret_1d", lambda s: int((s > 0).sum())),
        decliners=("ret_1d", lambda s: int((s < 0).sum())),
        new_high_20=("new_high_20d", lambda s: int(s.fillna(0).sum())),
        new_high_52w=("new_high_52w", lambda s: int(s.fillna(0).sum())),
        up_big=("ret_1d", lambda s: int((s > big_move).sum())),
        down_big=("ret_1d", lambda s: int((s < -big_move).sum())),
    ).reset_index()
    grouped = grouped.sort_values("date").reset_index(drop=True)

    # Derived breadth percentages
    grouped["pct_above_20"] = (grouped["above_20"] / grouped["total"] * 100).round(2)
    grouped["pct_above_50"] = (grouped["above_50"] / grouped["total"] * 100).round(2)
    grouped["pct_above_200"] = (grouped["above_200"] / grouped["total"] * 100).round(2)
    grouped["adv_minus_dec"] = grouped["advancers"] - grouped["decliners"]
    grouped["nh_minus_nl"] = grouped["new_high_20"] - (grouped["total"] - grouped["above_20"])
    # The "new lows" proxy: names below their 20DMA AND making fresh lows is more nuanced;
    # for simplicity use names not above 20DMA as a soft "downside participation" proxy.
    # In practice for a daily impulse chart, NH20 alone tells the more useful story.

    grouped["cum_ad"] = grouped["adv_minus_dec"].cumsum()

    # Build participation series, trimmed to the user's lookback window
    short_df = grouped.tail(days).copy()

    participation = {
        "dates": [d.strftime("%Y-%m-%d") for d in short_df["date"]],
        "pct_above_20": short_df["pct_above_20"].tolist(),
        "pct_above_50": short_df["pct_above_50"].tolist(),
        "pct_above_200": short_df["pct_above_200"].tolist(),
        "total_names": int(short_df["total"].iloc[-1]) if not short_df.empty else 0,
    }

    impulse_days = min(days, 60)
    imp_df = grouped.tail(impulse_days).copy()
    impulse = {
        "dates": [d.strftime("%Y-%m-%d") for d in imp_df["date"]],
        "adv_minus_dec": imp_df["adv_minus_dec"].tolist(),
        "new_high_20d": imp_df["new_high_20"].tolist(),
        "new_high_52w": imp_df["new_high_52w"].tolist(),
        "up_big": imp_df["up_big"].tolist(),
        "down_big": imp_df["down_big"].tolist(),
        "big_move_pct": big_move * 100,
    }

    # A/D vs SPY: always use the longer window
    spy_aligned = pd.DataFrame()
    if not spy.empty:
        spy["date"] = pd.to_datetime(spy["date"])
        spy_aligned = spy.set_index("date").reindex(grouped["date"]).reset_index()
        spy_aligned["close"] = spy_aligned["close"].ffill()

    ad_line = {
        "dates": [d.strftime("%Y-%m-%d") for d in grouped["date"]],
        "cumulative_ad": [int(v) for v in grouped["cum_ad"].tolist()],
        "spy_close": (
            [None if pd.isna(c) else round(float(c), 2) for c in spy_aligned["close"]]
            if not spy_aligned.empty else []
        ),
    }

    return {
        "as_of": latest.strftime("%Y-%m-%d") if hasattr(latest, "strftime") else str(latest),
        "lookback": lookback,
        "theme": theme or "All",
        "tiers": tier_list,
        "participation": participation,
        "impulse": impulse,
        "ad_line": ad_line,
    }


def _empty_breadth_payload(lookback: str, theme: str | None) -> dict:
    return {
        "as_of": None,
        "lookback": lookback,
        "theme": theme or "All",
        "tiers": [],
        "participation": {"dates": [], "pct_above_20": [], "pct_above_50": [], "pct_above_200": [], "total_names": 0},
        "impulse": {"dates": [], "adv_minus_dec": [], "new_high_20d": [], "new_high_52w": [], "up_big": [], "down_big": [], "big_move_pct": 4.0},
        "ad_line": {"dates": [], "cumulative_ad": [], "spy_close": []},
    }


# ============================================================
# MOMENTUM SCANNER
# ============================================================

# Window definitions (trading days)
MOMENTUM_WINDOWS = {
    "1W": {"avg_window": 5,   "min_window": 5,   "label": "1W"},
    "1M": {"avg_window": 25,  "min_window": 21,  "label": "1M"},
    "3M": {"avg_window": 66,  "min_window": 67,  "label": "3M"},
    "6M": {"avg_window": 126, "min_window": 126, "label": "6M"},
}


def get_momentum_scan(
    min_dollar_vol: float = 100_000_000.0,
    above_mas: tuple = (20, 50),
    tiers: tuple = ("Core", "Active"),
    exclude_benchmark: bool = True,
    top_n: int = 25,
) -> dict:
    """Compute four momentum-ranked top-N lists (1W / 1M / 3M / 6M).

    For each ticker we compute:
      - relative momentum: close / avg(close, window) - 1.0       (c/avgc style)
      - absolute momentum: (close - min(close, window)) / min(close, window) * 100
      - ret_1d: most recent single-day return (a noise check for the 1W list,
        so a 5-day move that is really one earnings gap is visible)

    Filters applied universe-wide before ranking:
      - Tier in `tiers`
      - Theme != Benchmark if `exclude_benchmark`
      - 20-day average dollar volume >= min_dollar_vol
      - Close above each MA in `above_mas` (AND filter)

    Returns dict with keys: "1W", "1M", "3M", "6M", each holding the ranked list.
    """
    # Pull last 140 days of prices for all eligible tickers in one query.
    # 140 = a bit of cushion past the 126-day window.
    tier_list = list(tiers) if tiers else ["Core", "Active", "Watch"]
    tier_placeholders = ",".join(["?"] * len(tier_list))

    theme_clause = " AND u.theme != 'Benchmark'" if exclude_benchmark else ""

    with db.connect(read_only=True) as conn:
        latest = conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]
        if latest is None:
            return _empty_momentum_payload(min_dollar_vol, above_mas, tiers, top_n)

        # Get the last 140 trading days' prices for our universe
        prices = conn.execute(f"""
            SELECT p.ticker, p.date, p.close, p.volume,
                   u.name, u.theme, u.subtheme, u.liquidity_tier
            FROM prices p
            JOIN universe u ON u.ticker = p.ticker
            WHERE p.date >= (SELECT MAX(date) - INTERVAL 200 DAY FROM prices)
              AND u.liquidity_tier IN ({tier_placeholders})
              {theme_clause}
            ORDER BY p.ticker, p.date
        """, tier_list).df()

        # Latest metrics for MA filter and additional context columns
        metrics_latest = conn.execute("""
            SELECT m.ticker, m.date,
                   m.above_ma10, m.above_ma20, m.above_ma50, m.above_ma200,
                   m.dist_ma20_pct, m.dist_ma50_pct,
                   m.atr_ext_50ma, m.vol_ratio,
                   m.new_high_20d, m.new_high_52w
            FROM metrics m
            WHERE m.date = (SELECT MAX(date) FROM metrics)
        """).df()

    if prices.empty:
        return _empty_momentum_payload(min_dollar_vol, above_mas, tiers, top_n)

    prices["date"] = pd.to_datetime(prices["date"])
    prices["dollar_vol"] = prices["close"] * prices["volume"]

    # Compute per-ticker momentum metrics from the last 140 trading days
    records = []
    for ticker, sub in prices.groupby("ticker"):
        sub = sub.sort_values("date")
        if len(sub) < 30:
            continue  # not enough history

        close = sub["close"].iloc[-1]
        # 20-day average dollar volume (filter input)
        dollar_vol_20d = float(sub["dollar_vol"].tail(20).mean())

        # Most recent single-day return: noise check for the weekly list
        ret_1d = None
        if len(sub) >= 2:
            prev_close = float(sub["close"].iloc[-2])
            if prev_close:
                ret_1d = (float(close) / prev_close - 1.0)

        row = {
            "ticker": ticker,
            "name": sub["name"].iloc[-1],
            "theme": sub["theme"].iloc[-1],
            "subtheme": sub["subtheme"].iloc[-1],
            "liquidity_tier": sub["liquidity_tier"].iloc[-1],
            "close": float(close),
            "dollar_vol_20d": dollar_vol_20d,
            "ret_1d": ret_1d,
        }

        for win_key, win in MOMENTUM_WINDOWS.items():
            avg_w = win["avg_window"]
            min_w = win["min_window"]

            if len(sub) >= avg_w:
                avg_close = float(sub["close"].tail(avg_w).mean())
                row[f"mom_{win_key}_rel"] = (close / avg_close - 1.0) if avg_close else None
            else:
                row[f"mom_{win_key}_rel"] = None

            if len(sub) >= min_w:
                min_close = float(sub["close"].tail(min_w).min())
                row[f"mom_{win_key}_abs"] = (
                    ((close - min_close) / min_close) * 100 if min_close else None
                )
            else:
                row[f"mom_{win_key}_abs"] = None

        records.append(row)

    if not records:
        return _empty_momentum_payload(min_dollar_vol, above_mas, tiers, top_n)

    df = pd.DataFrame(records)

    # Merge in MA filter info and context columns
    df = df.merge(
        metrics_latest.drop(columns=["date"], errors="ignore"),
        on="ticker", how="left"
    )

    # Apply filters
    mask = pd.Series(True, index=df.index)

    # Dollar volume
    mask &= df["dollar_vol_20d"] >= min_dollar_vol

    # MA filter: must be above ALL selected MAs
    for ma in above_mas:
        col = f"above_ma{ma}"
        if col in df.columns:
            mask &= df[col].fillna(0).astype(int) == 1

    filtered = df[mask].copy()

    # Four ranked lists, sorted by ABSOLUTE momentum per window
    results = {}
    for win_key in ("1W", "1M", "3M", "6M"):
        sort_col = f"mom_{win_key}_abs"
        if sort_col not in filtered.columns:
            results[win_key] = []
            continue
        sub = filtered.dropna(subset=[sort_col]).sort_values(
            sort_col, ascending=False
        ).head(top_n).copy()
        sub["rank"] = range(1, len(sub) + 1)
        # Round display-ready values for the JSON payload
        for col in [
            "mom_1W_rel", "mom_1M_rel", "mom_3M_rel", "mom_6M_rel",
            "mom_1W_abs", "mom_1M_abs", "mom_3M_abs", "mom_6M_abs",
            "ret_1d",
            "dist_ma20_pct", "dist_ma50_pct", "atr_ext_50ma", "vol_ratio",
        ]:
            if col in sub.columns:
                sub[col] = sub[col].apply(
                    lambda v: round(float(v), 4) if v is not None and pd.notna(v) else None
                )
        results[win_key] = sub.to_dict("records")

    return {
        "as_of": str(latest),
        "filters": {
            "min_dollar_vol": min_dollar_vol,
            "above_mas": list(above_mas),
            "tiers": tier_list,
            "exclude_benchmark": exclude_benchmark,
            "top_n": top_n,
        },
        "universe_size_after_filter": int(mask.sum()),
        "universe_size_before_filter": int(len(df)),
        "by_window": results,
    }


def _empty_momentum_payload(min_dollar_vol, above_mas, tiers, top_n) -> dict:
    return {
        "as_of": None,
        "filters": {
            "min_dollar_vol": min_dollar_vol,
            "above_mas": list(above_mas),
            "tiers": list(tiers),
            "top_n": top_n,
        },
        "universe_size_after_filter": 0,
        "universe_size_before_filter": 0,
        "by_window": {"1W": [], "1M": [], "3M": [], "6M": []},
    }


# ============================================================
# INTRADAY LIVE OVERLAY
# ============================================================

def get_live_overlay() -> dict:
    """Fetch a live market snapshot and overlay it on stored daily metrics.

    The structural analysis (theme scores, breadth, momentum rankings) stays
    anchored to the last completed daily close. This function adds a live price
    layer on top: for every ticker it returns the current price (15-min delayed
    on the Starter plan) and recomputes price-relative measures against the
    daily moving averages stored from the last close.

    Returns a dict keyed by ticker, each value holding:
      last_price, change_pct, day_high, day_low, day_volume,
      prev_close, vs_ma20, vs_ma50, vs_ma200 (live distance from each MA),
      live_atr_ext (live ATR extension from 50DMA),
      crossed (list of MAs crossed today: e.g. ['ma50'] if price moved above/below)
    plus top-level metadata: as_of_daily, snapshot_age_min, ticker_count, market_status.
    """
    from . import polygon_client

    # Pull the snapshot from Polygon
    snap = polygon_client.fetch_full_market_snapshot()

    out = {
        "as_of_daily": None,
        "snapshot_age_min": None,
        "ticker_count": 0,
        "market_status": "unknown",
        "by_ticker": {},
    }

    if snap.empty:
        return out

    # Compute snapshot age from the most recent updated timestamp (nanoseconds)
    import time as _time
    latest_update_ns = snap["updated_ms"].dropna().max() if "updated_ms" in snap.columns else None
    if latest_update_ns:
        age_sec = (_time.time() * 1e9 - float(latest_update_ns)) / 1e9
        out["snapshot_age_min"] = round(age_sec / 60.0, 1)
        # Rough market status read from snapshot freshness
        if age_sec < 20 * 60:
            out["market_status"] = "open"      # data is fresh, market likely open
        else:
            out["market_status"] = "closed"    # stale data, market likely closed

    # Pull the latest daily metrics for the MA reference levels.
    # MA columns are ma_20/ma_50/ma_200; the close price lives in `prices`.
    with db.connect(read_only=True) as conn:
        latest = conn.execute("SELECT MAX(date) FROM metrics").fetchone()[0]
        if latest is None:
            return out
        out["as_of_daily"] = str(latest)

        daily = conn.execute("""
            SELECT m.ticker,
                   p.close AS daily_close,
                   m.ma_20  AS ma20,
                   m.ma_50  AS ma50,
                   m.ma_200 AS ma200,
                   m.atr_14,
                   m.above_ma20, m.above_ma50, m.above_ma200
            FROM metrics m
            JOIN prices p ON p.ticker = m.ticker AND p.date = m.date
            WHERE m.date = (SELECT MAX(date) FROM metrics)
        """).df()

    if daily.empty:
        return out

    # Index daily metrics by ticker for fast lookup
    daily_by_ticker = {r["ticker"]: r for _, r in daily.iterrows()}

    by_ticker = {}
    for _, s in snap.iterrows():
        ticker = s["ticker"]
        d = daily_by_ticker.get(ticker)
        if d is None:
            continue  # snapshot ticker not in our universe
        last_price = s["last_price"]
        if last_price is None or pd.isna(last_price):
            continue

        ma20 = d["ma20"]
        ma50 = d["ma50"]
        ma200 = d["ma200"]
        atr = d["atr_14"]

        def _vs(ma):
            if ma is None or pd.isna(ma) or ma == 0:
                return None
            return round((last_price / ma - 1.0) * 100, 2)

        # Detect intraday MA crosses: was below at daily close, now above (or vice versa)
        crossed = []
        for ma_name, ma_val, was_above in [
            ("ma20", ma20, d["above_ma20"]),
            ("ma50", ma50, d["above_ma50"]),
            ("ma200", ma200, d["above_ma200"]),
        ]:
            if ma_val is None or pd.isna(ma_val):
                continue
            now_above = last_price > ma_val
            if bool(was_above) != bool(now_above):
                crossed.append({
                    "ma": ma_name,
                    "direction": "above" if now_above else "below",
                })

        live_atr_ext = None
        if atr and not pd.isna(atr) and atr != 0 and ma50 and not pd.isna(ma50):
            live_atr_ext = round((last_price - ma50) / atr, 2)

        by_ticker[ticker] = {
            "last_price": round(float(last_price), 2),
            "change_pct": round(float(s["change_pct"]), 4) if s["change_pct"] is not None and not pd.isna(s["change_pct"]) else None,
            "day_high": round(float(s["day_high"]), 2) if s["day_high"] and not pd.isna(s["day_high"]) else None,
            "day_low": round(float(s["day_low"]), 2) if s["day_low"] and not pd.isna(s["day_low"]) else None,
            "day_volume": int(s["day_volume"]) if s["day_volume"] and not pd.isna(s["day_volume"]) else None,
            "prev_close": round(float(s["prev_close"]), 2) if s["prev_close"] and not pd.isna(s["prev_close"]) else None,
            "daily_close": round(float(d["daily_close"]), 2) if d["daily_close"] and not pd.isna(d["daily_close"]) else None,
            "vs_ma20": _vs(ma20),
            "vs_ma50": _vs(ma50),
            "vs_ma200": _vs(ma200),
            "live_atr_ext": live_atr_ext,
            "crossed": crossed,
        }

    out["by_ticker"] = by_ticker
    out["ticker_count"] = len(by_ticker)
    return out
