"""Theme scoring layer.

Adapted from Stable Market Board by Ryan Scott (shared within The Stable, 2026).
Math unchanged; data layer swapped Polygon->yfinance and DuckDB->Postgres.

Aggregates per-ticker metrics into theme-level scores. Score components (each 0-100):
- breadth: % of basket above 20DMA, 50DMA
- leadership: % making 20D highs, % above 200DMA
- momentum: 20D returns scaled to a typical range
- extension penalty: average ATR extension (feeds the status label)
Final score is a weighted blend, with a status label and a 1D delta.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from psycopg2.extras import execute_values

import logging

from . import db, settings as settings_mod

logger = logging.getLogger(__name__)

# Themes excluded from scoring (benchmarks, broad ETF sleeves, scan-only universe,
# and the 11 SPDR sector ETFs — Addendum A1).
EXCLUDED_THEMES = {"Benchmark", "Scan Only", "Sector ETF"}


def _scalar(sql: str, params=None):
    df = db.read_df(sql, params)
    if df.empty:
        return None
    return df.iloc[0, 0]


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


# ── R-IV.435(e): THE ANCHOR IS THE NEWEST **COMPLETE** DATE ─────────────────────
#
# WHAT HAPPENED. Theme scores stopped on 2026-09-04 while metrics kept landing through 09-15.
# The newest date in stable_metrics (09-16) held TWO tickers against 677 on every prior date --
# a partial write, and `MAX(date)` made it the anchor. Every theme read a two-ticker universe,
# the basket came back empty, and the nightly stored zero rows while reporting a successful
# pass. A partial date is not a young date: it is an incomplete one, and it must not be able to
# become the thing everything else is measured against.
#
# THE MINIMUM IS DECLARED, NOT INFERRED. A date counts as complete when it carries at least
# ANCHOR_MIN_COVERAGE of the universe. Stated as a fraction of `stable_universe` so it tracks
# the universe rather than a number that goes stale: at 690 tickers the bar is 552, which 677
# clears and 2 does not.
#
# NO SILENT FALLBACK. When no date clears the bar the readers return EMPTY and say so. Falling
# back to MAX(date) would restore exactly the defect this closes.
ANCHOR_MIN_COVERAGE = 0.80
ANCHOR_MIN_TICKERS_FLOOR = 50


def anchor_date(as_of=None):
    """(date, coverage, required) for the newest COMPLETE metrics date, or (None, ...).

    `as_of` bounds the search, so a backfill can ask for the anchor as it stood on a past day.
    """
    universe_n = _scalar("SELECT COUNT(DISTINCT ticker) FROM stable_universe") or 0
    required = max(ANCHOR_MIN_TICKERS_FLOOR, int(universe_n * ANCHOR_MIN_COVERAGE))
    row = db.read_df(
        """
        SELECT date, COUNT(DISTINCT ticker) AS n
        FROM stable_metrics
        WHERE (%s IS NULL OR date <= %s)
        GROUP BY date
        HAVING COUNT(DISTINCT ticker) >= %s
        ORDER BY date DESC
        LIMIT 1
        """,
        [as_of, as_of, required],
    )
    if row is None or row.empty:
        logger.warning("[stable_scoring] no metrics date carries %d of %d universe tickers -- "
                       "NOT anchoring on MAX(date); readers return empty", required, universe_n)
        return None, 0, required
    return row.iloc[0]["date"], int(row.iloc[0]["n"]), required


def compute_theme_scores(as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    """Compute one row per theme for the newest COMPLETE date (or as_of). Math unchanged."""
    latest_date, coverage, required = anchor_date(as_of)
    if latest_date is None:
        return pd.DataFrame()
    if as_of is None:
        as_of = latest_date
    logger.info("[stable_scoring] anchor %s (%d tickers, minimum %d)",
                latest_date, coverage, required)

    df = db.read_df("""
        SELECT u.theme, u.ticker, u.liquidity_tier,
               m.date, m.ret_5d, m.ret_20d,
               m.above_ma20, m.above_ma50, m.above_ma200,
               m.new_high_20d, m.new_high_52w,
               m.atr_ext_50ma, m.rs_qqq_20d, m.rs_rsp_20d,
               m.dist_ma50_pct, m.vol_ratio
        FROM stable_metrics m
        JOIN stable_universe u ON u.ticker = m.ticker
        WHERE m.date IN (
            SELECT DISTINCT date FROM stable_metrics
            WHERE date <= %s
            ORDER BY date DESC LIMIT 6
        )
    """, [as_of])

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

            breadth = (pct_above_20 + pct_above_50) / 2
            leadership = (pct_new_high_20 * 0.6 + pct_above_200 * 0.4)
            momentum = _scale_to_100(avg_ret_20d, -0.10, 0.15)
            extension_raw = max(0, min(avg_atr_ext, 15))
            score = (
                0.30 * breadth +
                0.25 * leadership +
                0.30 * momentum +
                0.15 * (50 + avg_rs_qqq * 500)
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
    """Latest metrics for all tickers in a theme, sorted by 5D return."""
    latest_date, _, _ = anchor_date()
    if latest_date is None:
        return pd.DataFrame()
    return db.read_df("""
        SELECT u.ticker, u.name, u.subtheme, u.liquidity_tier,
               m.ret_1d, m.ret_5d, m.ret_20d,
               m.dist_ma20_pct, m.dist_ma50_pct,
               m.above_ma20, m.above_ma50, m.above_ma200,
               m.atr_ext_50ma, m.vol_ratio,
               m.new_high_20d, m.new_high_52w,
               m.rs_qqq_20d
        FROM stable_metrics m
        JOIN stable_universe u ON u.ticker = m.ticker
        WHERE u.theme = %s AND m.date = %s
        ORDER BY m.ret_5d DESC NULLS LAST
        LIMIT %s
    """, [theme, latest_date, limit])


def get_regime_read() -> dict:
    """Top-level regime read using benchmark and breadth data. Math identical to source."""
    cfg = settings_mod.load()
    big_move = cfg["breadth"]["big_move_threshold"]

    latest, _, _ = anchor_date()
    if latest is None:
        return {"as_of": None, "benchmarks": [], "breadth": {}, "thresholds": {"big_move_pct": big_move * 100}}

    bench = db.read_df("""
        SELECT u.ticker, u.subtheme, m.ret_1d, m.ret_5d, m.ret_20d,
               m.dist_ma20_pct, m.dist_ma50_pct, m.atr_ext_50ma,
               m.above_ma20, m.above_ma50, m.above_ma200
        FROM stable_metrics m JOIN stable_universe u ON u.ticker = m.ticker
        WHERE m.date = %s AND u.theme = 'Benchmark'
        ORDER BY u.ticker
    """, [latest])

    breadth = db.read_df(f"""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN m.above_ma20 = 1 THEN 1 ELSE 0 END) AS above_20,
            SUM(CASE WHEN m.above_ma50 = 1 THEN 1 ELSE 0 END) AS above_50,
            SUM(CASE WHEN m.above_ma200 = 1 THEN 1 ELSE 0 END) AS above_200,
            SUM(CASE WHEN m.new_high_20d = 1 THEN 1 ELSE 0 END) AS new_high_20d,
            SUM(CASE WHEN m.new_high_52w = 1 THEN 1 ELSE 0 END) AS new_high_52w,
            SUM(CASE WHEN m.ret_1d > {big_move} THEN 1 ELSE 0 END) AS up_big,
            SUM(CASE WHEN m.ret_1d < -{big_move} THEN 1 ELSE 0 END) AS down_big
        FROM stable_metrics m JOIN stable_universe u ON u.ticker = m.ticker
        WHERE m.date = %s AND u.theme NOT IN ('Benchmark', 'Scan Only', 'Sector ETF')
    """, [latest]).iloc[0].to_dict()

    return {
        "as_of": str(latest),
        "benchmarks": bench.to_dict("records"),
        "breadth": breadth,
        "thresholds": {"big_move_pct": big_move * 100},
    }


# ── Persistence (Postgres, additive) ─────────────────────────────────────────
_SCORE_COLS = [
    "theme", "date", "anchor", "score", "status", "rank", "score_1d_delta",
    "n_names", "breadth", "leadership", "momentum", "extension_raw",
    "pct_above_20ma", "pct_above_50ma", "pct_above_200ma",
    "pct_new_high_20d", "pct_new_high_52w",
    "avg_ret_5d", "avg_ret_20d", "avg_atr_ext_50ma", "avg_rs_qqq_20d",
    "as_of", "data_age_seconds", "degraded",
]


def store_theme_scores(scores: pd.DataFrame, anchor: str, as_of: datetime | None = None,
                       degraded: bool = False) -> int:
    """Persist compute_theme_scores() output into stable_theme_scores for one anchor."""
    if scores is None or scores.empty:
        return 0
    as_of = as_of or datetime.now(timezone.utc)
    db.init_schema()
    rows = []
    for _, r in scores.iterrows():
        d = pd.to_datetime(r["date"]).date()
        rows.append((
            r["theme"], d, anchor, float(r["score"]), r["status"], int(r["rank"]),
            float(r["score_1d_delta"]), int(r["n_names"]), float(r["breadth"]),
            float(r["leadership"]), float(r["momentum"]), float(r["extension_raw"]),
            float(r["pct_above_20ma"]), float(r["pct_above_50ma"]), float(r["pct_above_200ma"]),
            float(r["pct_new_high_20d"]), float(r["pct_new_high_52w"]),
            float(r["avg_ret_5d"]), float(r["avg_ret_20d"]), float(r["avg_atr_ext_50ma"]),
            float(r["avg_rs_qqq_20d"]), as_of, 0.0, bool(degraded),
        ))
    col_list = ", ".join(_SCORE_COLS)
    # Replace the whole (date, anchor) set so themes that drop out of the basket (e.g.
    # after a retag) don't linger as stale rows / duplicate ranks.
    dates = sorted({pd.to_datetime(r["date"]).date() for _, r in scores.iterrows()})
    with db.connect() as conn:
        with conn.cursor() as cur:
            ph = ",".join(["%s"] * len(dates))
            cur.execute(
                f"DELETE FROM stable_theme_scores WHERE anchor = %s AND date IN ({ph})",
                [anchor] + dates,
            )
            execute_values(
                cur,
                f"INSERT INTO stable_theme_scores ({col_list}) VALUES %s",
                rows, page_size=1000,
            )
    return len(rows)


# ── R-IV.435(e): RECOMPUTE THE DAYS THE PARTIAL ANCHOR COST ────────────────────
#
# Theme scores stopped on 2026-09-04 while metrics kept landing. Those days are computable --
# the metrics are there -- so the nightly fills any COMPLETE date that has no scores instead of
# leaving a hole that only a hand-run script could close. Bounded per pass, oldest first, and it
# writes nothing for a date it cannot compute.
BACKFILL_LOOKBACK_DAYS = 45
BACKFILL_MAX_DATES_PER_PASS = 20


def missing_score_dates(anchor: str = "close", lookback_days: int = BACKFILL_LOOKBACK_DAYS):
    """COMPLETE metrics dates inside the window that carry no stored scores for this anchor."""
    universe_n = _scalar("SELECT COUNT(DISTINCT ticker) FROM stable_universe") or 0
    required = max(ANCHOR_MIN_TICKERS_FLOOR, int(universe_n * ANCHOR_MIN_COVERAGE))
    df = db.read_df(
        """
        SELECT m.date
        FROM (
            SELECT date, COUNT(DISTINCT ticker) AS n
            FROM stable_metrics
            WHERE date >= (SELECT MAX(date) FROM stable_metrics) - %s::int
            GROUP BY date
        ) m
        LEFT JOIN (
            SELECT DISTINCT date FROM stable_theme_scores WHERE anchor = %s
        ) s ON s.date = m.date
        WHERE m.n >= %s AND s.date IS NULL
        ORDER BY m.date
        """,
        [lookback_days, anchor, required],
    )
    return [] if df is None or df.empty else list(df["date"])


def backfill_missing_theme_scores(anchor: str = "close",
                                  lookback_days: int = BACKFILL_LOOKBACK_DAYS,
                                  limit: int = BACKFILL_MAX_DATES_PER_PASS,
                                  degraded: bool = False) -> list:
    """Compute and store scores for each missing COMPLETE date. Returns [(date, rows)]."""
    out = []
    for d in missing_score_dates(anchor, lookback_days)[:limit]:
        scores = compute_theme_scores(as_of=d)
        if scores is None or scores.empty:
            logger.warning("[stable_scoring] backfill: %s has no computable scores", d)
            continue
        out.append((str(d), store_theme_scores(scores, anchor=anchor, degraded=degraded)))
    if out:
        logger.info("[stable_scoring] backfilled %d date(s): %s", len(out), out)
    return out

