"""Read-only Stable Engine query layer — backs both the /api/stable/* REST
routes and the hub_get_stable_* MCP tools (Brief 3, 2026-07-15).

Extracted from backend/api/stable.py (which now holds thin route wrappers
for the functions here) so the MCP tool layer never imports api.stable
directly (AEGIS three-layer read-only enforcement) and so the LAZR/Robotics
fix has exactly one place to land instead of two copies drifting apart.

Every function returns the house labeling contract shape: as_of (ISO UTC),
data_age_seconds, anchor ('close'|'provisional'|null), degraded (bool),
flatline (bool, via stable_engine.job_status.feed_flatline) + payload keys.
NOT yet MCP-enveloped -- backend/hub_mcp/stable_envelope.py maps this shape
to the MCP status/staleness_seconds contract one layer up.

DB exceptions are caught here (never propagated raw to a FastMCP client) and
converted to the same degraded/empty shape each function already uses for
"no data yet" -- one fallback representation, not two.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)

# In-process breadth cache, keyed by stable_metrics.metrics_date (Brief 3, Task 3/11).
# Not a wall-clock TTL -- breadth is invariant until the next nightly/provisional job
# writes a new stable_metrics row (confirmed single-worker deployment, Procfile has no
# --workers flag, so in-process is coherent; would need Redis if that ever changes).
_BREADTH_CACHE: dict = {"metrics_date": None, "breadth": None}

# ── R-IV.522(c): WINDOW COMPLETENESS, AND WHAT IT IS FOR ──────────────────────
#
# Every window the regime reads is ROW-BASED: `close.rolling(20)` over a per-ticker
# frame. A symbol missing a session does not lose a day — it silently reaches one
# further back, and by a different amount from its neighbours. Measured at R-IV.517:
# of 685 symbols, the 135 holding the 2026-09-22 bar all windowed back to 2026-08-26,
# while the 550 without it windowed back to anywhere between 2026-04-10 and
# 2026-09-04, some on as few as 12 rows. The regime was comparing symbols whose
# windows spanned different date ranges and saying nothing about it.
#
# Session windows are the real fix and are queued behind money integrity. Until then
# the regime at least STATES the damage: for each window length, how many symbols
# hold every one of the last N exchange sessions. Below scoring's own coverage floor
# the read is DEGRADED — the same 80% that decides whether a date may anchor at all.
#
# Completeness is measured against the EXCHANGE CALENDAR, never against row counts:
# counting rows is the very approximation that hides a gap.
def window_tolerance(n: int) -> int:
    """How many of the last n sessions a symbol may MISS and still count. R-IV.535(c)2.

    `floor(n / 20)`, on every window length, no exclusions: **0** for 1 and 5, **1**
    for 20, **2** for 50, **10** for 200, **12** for 252.

    The asymmetry is the point and it is intended (R-IV.535(c)2). A single missing
    session is a large fraction of a five-session window and a rounding error in a
    252-session one, so a short window reads on **only the symbols that hold every
    one of its sessions** while a long window tolerates the hole. While 2026-09-22
    sits inside the 5-day window that window reads on the 103 symbols that have it,
    and the count and DEGRADED say so rather than averaging the gap away.
    """
    return max(0, int(n) // 20)


REGIME_WINDOWS: tuple = (
    (1, "ret_1d — the big-move counts"),
    (5, "ret_5d"),
    (20, "ret_20d, above_ma20, new_high_20d, new_low_20d"),
    (50, "above_ma50 — the regime label's own input"),
    (200, "above_ma200"),
    (252, "new_high_52w, new_low_52w"),
)

_COMPLETENESS_CACHE: dict = {"metrics_date": None, "windows": None, "lag": None}


def _coverage_floor_pct() -> float:
    """scoring's own anchor-coverage floor, as a percentage. One author for that
    number (conventions #9) -- a second copy here would drift from the one that
    decides whether a date may anchor at all."""
    try:
        from stable_engine.scoring import ANCHOR_MIN_COVERAGE
        return round(ANCHOR_MIN_COVERAGE * 100.0, 1)
    except Exception:
        return 80.0


def _sessions_back(anchor_date, n: int) -> list:
    """The last n exchange sessions ending at anchor_date, oldest first.

    Raises rather than guessing: `market_calendar` fails loudly past its stated
    horizon, and a completeness figure built on a guessed calendar would be worse
    than none — it would read as reassurance.
    """
    from stable_engine.market_calendar import is_trading_day, previous_trading_day

    out = []
    d = anchor_date
    if not is_trading_day(d):
        d = previous_trading_day(d)
    for _ in range(n):
        out.append(d)
        d = previous_trading_day(d)
    return sorted(out)


def completeness_verdict(windows: dict, lag: dict = None):
    """(degraded, reason) from a window-completeness block and the anchor lag.

    A row-based window absorbs a gap by reaching further back, so an incomplete
    window is not an empty one — it is a WRONG one, and the figure it produced looks
    entirely ordinary. Naming which windows, and by how much, is the whole point of
    the flag; a bare `degraded: true` would send a reader looking at the feed age.
    """
    reasons = []
    short = sorted((w for w in (windows or {}).values() if w.get("below_floor")),
                   key=lambda w: w.get("sessions") or 0)
    if short:
        reasons.append(
            ("window completeness below %g%%: " % _coverage_floor_pct()) + ", ".join(
                "%dd at %s%%" % (w.get("sessions"),
                                 "unknown" if w.get("pct") is None else w.get("pct"))
                for w in short))
    behind = (lag or {}).get("sessions_behind")
    if behind:
        reasons.append(
            "the anchor is %d session%s behind: serving %s while %s is complete"
            % (behind, "" if behind == 1 else "s", (lag or {}).get("metrics_date"),
               (lag or {}).get("newest_complete_session")))
    if not reasons:
        return False, None
    return True, "; ".join(reasons)


async def _anchor_lag(conn, metrics_date) -> dict:
    """How far the regime's anchor sits behind the newest session it could have used.

    ONE STEP BEYOND R-IV.522(c) — say if it is unwanted. Measured live on
    2026-09-24: `as_of` was 1.6 hours old, `flatline` false, `degraded` false, and
    the read was serving 2026-09-21 — three sessions back. The nightly had run an
    hour earlier and simply re-published 09-21's numbers, so every staleness signal
    on the envelope said healthy. The only field carrying the truth was
    `metrics_date`, which nothing keys on.

    A row-based window absorbing a gap and an anchor stuck behind one are the same
    fault wearing different clothes: in both cases the figure is computed from the
    wrong days and looks completely ordinary.
    """
    from stable_engine.market_calendar import trading_days_between
    from stable_engine.scoring import ANCHOR_MIN_COVERAGE, ANCHOR_MIN_TICKERS_FLOOR

    universe = await conn.fetchval(
        """SELECT COUNT(DISTINCT u.ticker) FROM stable_universe u
            WHERE u.theme NOT IN ('Benchmark', 'Scan Only', 'Sector ETF')"""
    ) or 0
    required = max(ANCHOR_MIN_TICKERS_FLOOR, int(universe * ANCHOR_MIN_COVERAGE))
    newest = await conn.fetchval(
        """SELECT b.date
             FROM stable_daily_bars b
             JOIN stable_universe u ON u.ticker = b.ticker
            WHERE u.theme NOT IN ('Benchmark', 'Scan Only', 'Sector ETF')
            GROUP BY b.date
           HAVING COUNT(DISTINCT b.ticker) >= $1
            ORDER BY b.date DESC
            LIMIT 1""",
        required,
    )
    if newest is None or metrics_date is None:
        return {"metrics_date": str(metrics_date) if metrics_date else None,
                "newest_complete_session": None, "sessions_behind": None,
                "required_tickers": required, "universe": universe}
    try:
        behind = max(0, trading_days_between(metrics_date, newest))
    except Exception:
        behind = None
    return {
        "metrics_date": str(metrics_date),
        "newest_complete_session": str(newest),
        "sessions_behind": behind,
        "required_tickers": required,
        "universe": universe,
    }


async def _window_completeness(conn, metrics_date) -> dict:
    """{window: {sessions, complete, universe, pct, below_floor}} for each window.

    A symbol's N-window is complete when it holds a bar for EVERY one of the last N
    exchange sessions. Not "N bars": a symbol with N bars spread over N+3 sessions
    has an incomplete window, and that is exactly the case being measured.
    """
    from stable_engine.scoring import ANCHOR_MIN_COVERAGE

    universe = await conn.fetchval(
        """SELECT COUNT(DISTINCT u.ticker) FROM stable_universe u
            WHERE u.theme NOT IN ('Benchmark', 'Scan Only', 'Sector ETF')"""
    ) or 0
    out: dict = {}
    for n, feeds in REGIME_WINDOWS:
        try:
            sessions = _sessions_back(metrics_date, n)
        except Exception as exc:
            out[str(n)] = {"sessions": n, "feeds": feeds, "complete": None,
                           "universe": universe, "pct": None, "below_floor": True,
                           "error": "calendar could not answer: %s" % type(exc).__name__}
            continue
        # R-IV.535(c)2: a symbol counts as complete when it misses at most
        # floor(n/20) of those sessions. `>=` the required count, not `=` n.
        misses_allowed = window_tolerance(n)
        required_sessions = max(1, n - misses_allowed)
        complete = await conn.fetchval(
            """SELECT COUNT(*) FROM (
                   SELECT b.ticker
                     FROM stable_daily_bars b
                     JOIN stable_universe u ON u.ticker = b.ticker
                    WHERE b.date = ANY($1::date[])
                      AND u.theme NOT IN ('Benchmark', 'Scan Only', 'Sector ETF')
                    GROUP BY b.ticker
                   HAVING COUNT(DISTINCT b.date) >= $2
               ) t""",
            sessions, required_sessions,
        ) or 0
        pct = round(100.0 * complete / universe, 1) if universe else None
        out[str(n)] = {
            "sessions": n, "feeds": feeds, "complete": complete, "universe": universe,
            "first_session": str(sessions[0]), "last_session": str(sessions[-1]),
            # Served so a reader never has to work out why a 5-day window is short
            # while a 200-day one is not: the tolerance is the reason, and it is
            # stated rather than inferred.
            "misses_allowed": misses_allowed,
            "sessions_required": required_sessions,
            "pct": pct,
            "below_floor": pct is None or pct < ANCHOR_MIN_COVERAGE * 100.0,
        }
    return out


def _age_seconds(as_of) -> float | None:
    if as_of is None:
        return None
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - as_of).total_seconds())


def _envelope(as_of, anchor, degraded, *, feed=None, **data) -> dict:
    age = _age_seconds(as_of)
    # Flatline: the feed has aged past its SLO -> DEAD, not just stale. Escalates degraded.
    flatline = False
    if feed:
        try:
            from stable_engine.job_status import feed_flatline
            flatline = feed_flatline(feed, age)
        except Exception:
            flatline = False
    return {
        **data,
        "as_of": as_of.isoformat() if as_of else None,
        "data_age_seconds": age,
        "anchor": anchor,
        "degraded": bool(degraded) if degraded is not None else True,
        "flatline": flatline,
    }


async def _latest_snapshot(conn):
    """Return (date, anchor, as_of, degraded) of the most recently written theme snapshot."""
    row = await conn.fetchrow(
        "SELECT date, anchor, as_of, degraded FROM stable_theme_scores ORDER BY as_of DESC NULLS LAST LIMIT 1"
    )
    return row


async def _strip_rows(conn, kinds: tuple) -> tuple[list, object, bool]:
    ph = ",".join(f"${i+1}" for i in range(len(kinds)))
    rows = await conn.fetch(
        f"SELECT symbol, kind, value, day_change, extra, as_of, reason, prior_close FROM stable_live_strip WHERE kind IN ({ph}) ORDER BY symbol",
        *kinds,
    )
    as_of = max((r["as_of"] for r in rows if r["as_of"]), default=None)
    return [dict(r) for r in rows], as_of, len(rows) == 0


async def get_themes() -> dict:
    """Full ranked theme table (score, 1d delta, status, components) for the latest snapshot."""
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            snap = await _latest_snapshot(conn)
            if not snap:
                return _envelope(None, None, True, feed="nightly", themes=[], count=0)
            rows = await conn.fetch(
                """SELECT theme, rank, score, score_1d_delta, status, n_names,
                          breadth, leadership, momentum, extension_raw,
                          pct_above_20ma, pct_above_50ma, pct_above_200ma,
                          pct_new_high_20d, pct_new_high_52w,
                          avg_ret_5d, avg_ret_20d, avg_atr_ext_50ma, avg_rs_qqq_20d
                   FROM stable_theme_scores
                   WHERE date = $1 AND anchor = $2
                   ORDER BY rank""",
                snap["date"], snap["anchor"],
            )
            themes = [dict(r) for r in rows]
            return _envelope(snap["as_of"], snap["anchor"], snap["degraded"], feed="nightly",
                             date=str(snap["date"]), count=len(themes), themes=themes)
    except Exception as e:
        logger.warning("[services.stable] get_themes failed: %s", e)
        return _envelope(None, None, True, feed="nightly", themes=[], count=0)


async def get_regime() -> dict:
    """Regime read: breadth counts + dominant/emerging/fading themes."""
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            snap = await _latest_snapshot(conn)
            latest_metric_date = await conn.fetchval("SELECT MAX(date) FROM stable_metrics")

            breadth = {}
            metrics_date_key = str(latest_metric_date) if latest_metric_date else None
            if metrics_date_key is not None and _BREADTH_CACHE["metrics_date"] == metrics_date_key:
                # Cache hit: skip both queries below (the window-function one over
                # ~276K rows is the one genuinely expensive query in this whole tool
                # set) -- breadth can't have changed since the metrics_date hasn't.
                breadth = _BREADTH_CACHE["breadth"]
            elif latest_metric_date is not None:
                b = await conn.fetchrow(
                    """SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN m.above_ma20 = 1 THEN 1 ELSE 0 END) AS above_20,
                        SUM(CASE WHEN m.above_ma50 = 1 THEN 1 ELSE 0 END) AS above_50,
                        SUM(CASE WHEN m.above_ma200 = 1 THEN 1 ELSE 0 END) AS above_200,
                        SUM(CASE WHEN m.new_high_20d = 1 THEN 1 ELSE 0 END) AS new_high_20d,
                        SUM(CASE WHEN m.new_high_52w = 1 THEN 1 ELSE 0 END) AS new_high_52w,
                        SUM(CASE WHEN m.ret_1d > 0.03 THEN 1 ELSE 0 END) AS up_3,
                        SUM(CASE WHEN m.ret_1d < -0.03 THEN 1 ELSE 0 END) AS down_3
                    FROM stable_metrics m JOIN stable_universe u ON u.ticker = m.ticker
                    WHERE m.date = $1 AND u.theme NOT IN ('Benchmark', 'Scan Only', 'Sector ETF')""",
                    latest_metric_date,
                )
                total = (b["total"] or 0) or 1
                # New lows: not stored in stable_metrics (only highs are), so compute read-time
                # from bars, mirroring the metrics high rule (low <= trailing-min(low), 20/252
                # sessions, 52w guarded by >=200 sessions of history -- matches min_periods=200).
                lo = await conn.fetchrow(
                    """WITH w AS (
                           SELECT b.ticker, b.date, b.l,
                                  MIN(b.l) OVER (PARTITION BY b.ticker ORDER BY b.date
                                                 ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)  AS min_20,
                                  MIN(b.l) OVER (PARTITION BY b.ticker ORDER BY b.date
                                                 ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS min_252,
                                  COUNT(*) OVER (PARTITION BY b.ticker ORDER BY b.date
                                                 ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS n
                           FROM stable_daily_bars b
                           WHERE b.date >= (SELECT MAX(date) - INTERVAL '400 days' FROM stable_daily_bars)
                       )
                       SELECT
                           SUM(CASE WHEN w.n >= 20  AND w.l <= w.min_20  THEN 1 ELSE 0 END) AS new_low_20d,
                           SUM(CASE WHEN w.n >= 200 AND w.l <= w.min_252 THEN 1 ELSE 0 END) AS new_low_52w
                       FROM w
                       JOIN stable_universe u ON u.ticker = w.ticker
                       WHERE w.date = $1 AND u.theme NOT IN ('Benchmark', 'Scan Only', 'Sector ETF')""",
                    latest_metric_date,
                )
                breadth = {
                    "total": b["total"], "up_3": b["up_3"], "down_3": b["down_3"],
                    "new_high_20d": b["new_high_20d"], "new_high_52w": b["new_high_52w"],
                    "new_low_20d": (lo["new_low_20d"] if lo else None),
                    "new_low_52w": (lo["new_low_52w"] if lo else None),
                    "pct_above_50dma": round(100.0 * (b["above_50"] or 0) / total, 1),
                    "pct_above_200dma": round(100.0 * (b["above_200"] or 0) / total, 1),
                    "pct_above_20dma": round(100.0 * (b["above_20"] or 0) / total, 1),
                }
                _BREADTH_CACHE["metrics_date"] = metrics_date_key
                _BREADTH_CACHE["breadth"] = breadth

            dominant, emerging, fading = [], [], []
            if snap:
                rows = await conn.fetch(
                    "SELECT theme, score, status, rank FROM stable_theme_scores WHERE date=$1 AND anchor=$2 ORDER BY rank",
                    snap["date"], snap["anchor"],
                )
                for r in rows:
                    st = (r["status"] or "").upper()
                    item = {"theme": r["theme"], "score": r["score"], "status": r["status"], "rank": r["rank"]}
                    if st in ("DOMINANT", "STRONG / HOT"):
                        dominant.append(item)
                    elif st in ("EMERGING", "IMPROVING"):
                        emerging.append(item)
                    elif st in ("FADING", "DETERIORATING", "WEAK"):
                        fading.append(item)

            # Simple regime label from breadth (>50dma participation)
            p50 = breadth.get("pct_above_50dma")
            regime_label = "UNKNOWN"
            if p50 is not None:
                regime_label = "RISK-ON" if p50 >= 60 else "RISK-OFF" if p50 <= 40 else "NEUTRAL"

            # R-IV.522(c): how many symbols hold each window whole, and DEGRADED
            # below scoring's floor. Cached on metrics_date like breadth — it cannot
            # change until the next nightly writes a new one.
            windows, lag = {}, {}
            if latest_metric_date is not None:
                if _COMPLETENESS_CACHE["metrics_date"] == metrics_date_key:
                    windows = _COMPLETENESS_CACHE["windows"]
                    lag = _COMPLETENESS_CACHE["lag"]
                else:
                    windows = await _window_completeness(conn, latest_metric_date)
                    lag = await _anchor_lag(conn, latest_metric_date)
                    _COMPLETENESS_CACHE["metrics_date"] = metrics_date_key
                    _COMPLETENESS_CACHE["windows"] = windows
                    _COMPLETENESS_CACHE["lag"] = lag

            as_of = snap["as_of"] if snap else None
            anchor = snap["anchor"] if snap else None
            degraded = snap["degraded"] if snap else True
            short_degraded, reason = completeness_verdict(windows, lag)
            degraded = bool(degraded) or short_degraded
            return _envelope(
                as_of, anchor, degraded, feed="nightly",
                regime_label=regime_label,
                thresholds={"risk_on_pct_above_50dma": 60, "risk_off_pct_above_50dma": 40,
                            "big_move_pct": 3.0,
                            "window_complete_floor_pct": _coverage_floor_pct()},
                breadth=breadth,
                window_completeness=windows,
                anchor_lag=lag,
                degraded_reason=reason,
                dominant=dominant[:8], emerging=emerging[:8], fading=fading[:8],
                metrics_date=str(latest_metric_date) if latest_metric_date else None,
            )
    except Exception as e:
        logger.warning("[services.stable] get_regime failed: %s", e)
        return _envelope(None, None, True, feed="nightly", regime_label="UNKNOWN",
                         thresholds={}, breadth={}, dominant=[], emerging=[], fading=[], metrics_date=None)


async def get_theme_members(theme: str, top: int = 5, bottom: int = 5) -> dict:
    """Members of a theme ranked by 1d %, with last price, 1d %, RS vs QQQ.

    Live-overlay fetch is slice-then-fetch, not full-roster-then-slice
    (AEGIS finding, Brief 3): sorts on the last-known ret_1d and takes the
    top+bottom slice BEFORE the yfinance live-price round-trip, so a large
    theme's live-fetch cost is bounded by top+bottom, not the whole roster.

    Known residual limitation (accepted): the CANDIDATE POOL is still
    selected from last-close ranking before the live fetch (same AEGIS cost
    bound). A ticker that was mid-pack at close but is today's true extreme
    won't appear in top/bottom. What IS guaranteed: whatever tickers make it
    into the slice are correctly ranked relative to each other post-overlay
    (min(top ret_1d) >= max(bottom ret_1d) always holds) -- this does not
    widen the pool, it only fixes internal consistency (2026-07-21 fix).
    """
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            latest = await conn.fetchval("SELECT MAX(date) FROM stable_metrics")
            if latest is None:
                return _envelope(None, "close", True, theme=theme, member_count=0, top=[], bottom=[], ranking_basis=None)
            rows = await conn.fetch(
                """SELECT u.ticker, u.name, u.subtheme,
                          m.ret_1d, m.ret_5d, m.rs_qqq_20d,
                          m.above_ma20, m.above_ma50, m.atr_ext_50ma,
                          b.c AS last_price
                   FROM stable_metrics m
                   JOIN stable_universe u ON u.ticker = m.ticker
                   JOIN stable_daily_bars b ON b.ticker = m.ticker AND b.date = m.date
                   WHERE u.theme = $1 AND m.date = $2 AND m.ret_1d IS NOT NULL
                   ORDER BY m.ret_1d DESC NULLS LAST""",
                theme, latest,
            )
            members = [dict(r) for r in rows]
            anchor = "close"
            as_of = datetime.combine(latest, datetime.min.time(), tzinfo=timezone.utc)

            # Slice BEFORE the live fetch -- bounds the external-call cost to
            # top+bottom regardless of the theme's total roster size.
            slice_tickers = set()
            top_slice = members[:top]
            bottom_slice = members[-bottom:][::-1] if members else []
            for m in top_slice:
                slice_tickers.add(m["ticker"])
            for m in bottom_slice:
                slice_tickers.add(m["ticker"])
            slice_members = [m for m in members if m["ticker"] in slice_tickers]

            live = {}
            try:
                from stable_engine.job_status import is_market_hours
                if slice_members and is_market_hours():
                    from stable_engine.live import fetch_live_prices
                    live = await asyncio.to_thread(fetch_live_prices, [m["ticker"] for m in slice_members])
            except Exception as e:
                logger.warning("[services.stable] member live overlay failed for %s: %s", theme, e)
                live = {}
            if live:
                anchor = "provisional"
                as_of = datetime.now(timezone.utc)
                for m in slice_members:
                    lp = live.get(m["ticker"])
                    prior = m.get("last_price")
                    if lp is not None and prior:
                        m["ret_1d"] = (lp / prior) - 1.0
                        m["last_price"] = lp
                # Re-sort the (small) live-updated slice and ACTUALLY re-derive
                # top/bottom membership from the re-sorted order. The prior code
                # refreshed values but kept nightly membership -> top/bottom
                # inversion on reversal days (2026-07-21 Software Infrastructure
                # incident: best 1d name rendered in BOTTOM, worst in TOP).
                slice_members.sort(key=lambda m: (m.get("ret_1d") is None, -(m.get("ret_1d") or 0.0)))
                top_slice = slice_members[:top]
                bottom_slice = slice_members[-bottom:][::-1] if slice_members else []

            return _envelope(
                as_of, anchor, False,
                theme=theme, member_count=len(members),
                top=top_slice, bottom=bottom_slice,
                ranking_basis=("live" if live else f"close@{latest}"),
            )
    except Exception as e:
        logger.warning("[services.stable] get_theme_members failed for %s: %s", theme, e)
        return _envelope(None, "close", True, theme=theme, member_count=0, top=[], bottom=[], ranking_basis=None)


async def get_movers() -> dict:
    """Latest movers snapshot: {gainers:[15], losers:[15]} with theme where applicable.

    Serves the last stored snapshot with an honest data_age -- a failed screener leaves
    the snapshot in place (stale-labeled), never an empty-but-fresh response.
    """
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT side, rank, ticker, pct, price, theme, as_of FROM stable_movers ORDER BY side, rank"
            )
            gainers = [dict(r) for r in rows if r["side"] == "gainer"]
            losers = [dict(r) for r in rows if r["side"] == "loser"]
            as_of = max((r["as_of"] for r in rows if r["as_of"]), default=None)
            age = _age_seconds(as_of)
            degraded = (not rows) or (age is not None and age > 1800)
            return _envelope(as_of, "provisional", degraded, feed="movers",
                             gainers=gainers, losers=losers,
                             count={"gainers": len(gainers), "losers": len(losers)})
    except Exception as e:
        logger.warning("[services.stable] get_movers failed: %s", e)
        return _envelope(None, "provisional", True, feed="movers", gainers=[], losers=[],
                         count={"gainers": 0, "losers": 0})


async def get_rates() -> dict:
    """Latest Treasury yields (percent + bp day change) and the 10y-3m spread."""
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows, as_of, empty = await _strip_rows(conn, ("yield", "spread"))
            yields = [r for r in rows if r["kind"] == "yield"]
            spread = next((r for r in rows if r["kind"] == "spread"), None)
            curve_points = {r["symbol"]: r["value"] for r in yields}
            ghost = await conn.fetch(
                """SELECT DISTINCT ON (symbol) symbol, value FROM stable_intraday_points
                   WHERE symbol IN ('3M','5Y','10Y','30Y') AND ts <= NOW() - INTERVAL '5 days'
                   ORDER BY symbol, ts DESC"""
            )
            curve_5d = {r["symbol"]: r["value"] for r in ghost} or None
            return _envelope(as_of, "provisional", empty, feed="strip", yields=yields, spread=spread, count=len(yields),
                             curve_points=curve_points or None, curve_points_5d_ago=curve_5d)
    except Exception as e:
        logger.warning("[services.stable] get_rates failed: %s", e)
        return _envelope(None, "provisional", True, feed="strip", yields=[], spread=None, count=0,
                         curve_points=None, curve_points_5d_ago=None)


async def get_fx() -> dict:
    """DXY + USDJPY latest level, day change, and intraday series."""
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            latest = await conn.fetch(
                "SELECT symbol, value AS day_change_pct, extra AS level, as_of FROM stable_live_strip WHERE kind='fx' ORDER BY symbol"
            )
            pts = await conn.fetch(
                """SELECT symbol, ts, value FROM stable_intraday_points
                   WHERE symbol IN ('DXY','USDJPY') AND ts >= NOW() - INTERVAL '1 day' ORDER BY symbol, ts"""
            )
            series = {}
            for r in pts:
                series.setdefault(r["symbol"], []).append({"ts": r["ts"].isoformat(), "value": r["value"]})
            as_of = max((r["as_of"] for r in latest if r["as_of"]), default=None)
            fx = [{**dict(r), "series": series.get(r["symbol"], [])} for r in latest]
            return _envelope(as_of, "provisional", len(fx) == 0, feed="strip", fx=fx, count=len(fx))
    except Exception as e:
        logger.warning("[services.stable] get_fx failed: %s", e)
        return _envelope(None, "provisional", True, feed="strip", fx=[], count=0)
