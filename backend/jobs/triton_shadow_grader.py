"""Triton Step-0 B3 — whale-flow shadow grader.

Daily post-close pass: for triton_flow_shadow rows with graded_at IS NULL, compute
direction-adjusted forward returns (fwd_ret_1d/3d/5d) from 'r'-filtered daily
closes. Batched one bar-fetch per unique ticker (triton_flow_shadow BACKGROUND
caller). Skip-and-retry when a horizon bar doesn't exist yet; graded_at is set
only once the 5d horizon fills (fully graded).

Extends the a3 PATTERN — does NOT modify a3. Writes ONLY triton_flow_shadow
columns; the signals table is UNTOUCHED, no outcome_source writes anywhere.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

logger = logging.getLogger("triton_shadow")

HORIZONS = (1, 3, 5)
GRADE_LIMIT = 1000  # rows/pass ceiling


# T6 (R-IV.287(5)): the bar window is BOUNDED.
#
# It used to be (today - earliest).days + 12, anchored on the oldest ungraded row —
# which the 72 permanently-ungradeable index rows pinned at 2026-07-02, so the
# window grew by one day every day, without bound. T5 removes that anchor; T6 caps
# it anyway, because a bound that depends on another fix staying correct is not a
# bound.
#
# >= 20 TRADING DAYS (the longest horizon T9 introduces) plus buffer, and the
# calendar-day figure comes from T7's calendar, NEVER from a multiplier. `20 * 1.6`
# is the weekday approximation wearing a different constant: right most weeks,
# wrong across every holiday, and hardest to notice for exactly that reason.
GRADER_LOOKBACK_TRADING_DAYS = 25          # 20d horizon + 5 sessions of buffer
GRADER_LOOKBACK_SLACK_DAYS = 5
# Used only when the calendar cannot answer (a date past its stated horizon).
# Deliberately generous: over-fetching costs a larger query, under-fetching drops
# a horizon silently, and those are not symmetric.
GRADER_LOOKBACK_FALLBACK_DAYS = 45


def _bounded_lookback(earliest, today) -> int:
    """min(what the oldest row needs, the T7-derived cap). Never unbounded."""
    needed = (today - earliest).days + 12
    try:
        from stable_engine.market_calendar import calendar_days_covering

        cap = calendar_days_covering(GRADER_LOOKBACK_TRADING_DAYS, today) + GRADER_LOOKBACK_SLACK_DAYS
    except Exception as exc:
        # LOUD. A calendar that cannot answer must not be replaced by a guess in
        # silence -- the fallback is a stated constant, and it says so.
        logger.error(
            "triton_grader: market calendar could not size the lookback (%s: %s) -- "
            "using the stated fallback of %d days, NOT a computed rule",
            type(exc).__name__, exc, GRADER_LOOKBACK_FALLBACK_DAYS)
        cap = GRADER_LOOKBACK_FALLBACK_DAYS
    return max(1, min(needed, cap))


def _dir_adj(entry: float, close: float, direction: str) -> float:
    """Direction-adjusted return %. BULL = raw; BEAR = -raw. Positive = correct."""
    raw = (close - entry) / entry * 100.0
    if (direction or "").upper() == "BEAR":
        raw = -raw
    return round(raw, 4)


async def run_triton_shadow_grader() -> dict:
    """One grading pass. Never raises (fail-open). Returns a small summary."""
    from database.postgres_client import get_postgres_client
    from jobs.triton_shadow_common import (
        fetch_r_close_index, nth_trading_day, close_on_or_near, _f,
    )
    from jobs.instrument_class import classify, is_gradeable

    # T4 (R-IV.289): every skip carries a REASON. A bare count answers "how many
    # did not grade" and not "why", and the two questions have different fixes.
    skips: dict[str, int] = {}

    def _skip(reason: str, n: int = 1) -> None:
        skips[reason] = skips.get(reason, 0) + n

    pool = await get_postgres_client()
    if not pool:
        return {"graded": 0, "skipped": 0, "skips": {"no_db_pool": 1}}

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, ticker, direction, fired_at, spot_at_fire
            FROM triton_flow_shadow
            WHERE graded_at IS NULL
              AND fired_at IS NOT NULL
              AND fired_at < NOW() - INTERVAL '1 day'   -- at least T+1 could exist
            ORDER BY fired_at
            LIMIT $1
            """,
            GRADE_LIMIT,
        )
    if not rows:
        # NOT a skip. Nothing was ungraded, which is the healthy steady state.
        return {"graded": 0, "skipped": 0, "skips": {}}

    # Group by ticker for batched bar fetches
    by_ticker: dict = {}
    for r in rows:
        by_ticker.setdefault((r["ticker"] or "").upper(), []).append(r)

    today = datetime.now(timezone.utc).date()
    graded = fully = skipped = 0
    providers_used: dict = {}

    for ticker, group in by_ticker.items():
        if not ticker:
            _skip("blank_ticker", len(group))
            skipped += len(group)
            continue
        earliest = min(
            (g["fired_at"].date() if hasattr(g["fired_at"], "date") else g["fired_at"])
            for g in group
        )
        lookback_days = _bounded_lookback(earliest, today)
        # ── R-IV.358(b) GUARD: cash-settled index rows are UNGRADEABLE, and the
        # fallback must not go looking for a series that cannot exist. SPX/SPXW/
        # RUT/RUTW/VIX settle in cash and have no tradeable close to grade
        # against; before the fallback they failed slowly, on an empty UW answer.
        # WITH a yfinance net behind them they would fail DIFFERENTLY -- yfinance
        # DOES serve ^SPX-shaped series, so the net would hand back a price and
        # the grader would compute a forward return on an instrument that has no
        # such return. THAT IS WORSE THAN THE SKIP IT REPLACES: a wrong grade
        # inside the sealed population is a registration breach, where a skip is
        # only a gap.
        #
        # The predicate is the CLASSIFIER's, not a second copy of the symbol list
        # -- one author for that set (conventions #9). issue_type is passed as
        # None deliberately: the cash-settled branch is checked FIRST and does not
        # consult it, so this needs no per-ticker vendor call at grade time.
        if not is_gradeable(classify(ticker, None)):
            logger.info("triton_grader: %s is cash-settled — UNGRADEABLE-NO-SERIES, skip %d "
                        "(no fetch attempted)", ticker, len(group))
            _skip("UNGRADEABLE-NO-SERIES", len(group))
            skipped += len(group)
            continue

        idx, provider = await fetch_r_close_index(ticker, lookback_days)
        if not idx:
            # Still reachable AFTER the fallback: UW empty AND yfinance empty.
            # The reason string is unchanged so the 944-row backlog stays
            # comparable across the fix -- a renamed reason would reset the
            # series and make the fallback look effective by discontinuity.
            logger.warning("triton_grader: no 'r' bars for %s (provider=%s) — skip %d",
                           ticker, provider, len(group))
            _skip("no_regular_session_bars", len(group))
            skipped += len(group)
            continue
        providers_used[provider] = providers_used.get(provider, 0) + len(group)

        for g in group:
            try:
                fire_d = g["fired_at"].date() if hasattr(g["fired_at"], "date") else g["fired_at"]
                direction = g["direction"] or "BULL"
                # entry reference: fire-time spot, else fire-date 'r' close
                entry = _f(g["spot_at_fire"])
                if not entry or entry <= 0:
                    entry = close_on_or_near(idx, fire_d)
                if not entry or entry <= 0:
                    _skip("no_entry_price")
                    skipped += 1
                    continue

                vals = {1: None, 3: None, 5: None}
                # T4: a horizon that HAS NOT ARRIVED and a horizon whose BAR IS
                # MISSING both leave vals empty, and they are opposite facts --
                # the first resolves itself tomorrow, the second never does.
                # A single "skipped" count cannot tell them apart, which is how a
                # real bar gap hides inside an expected wait.
                any_reachable = False
                for k in HORIZONS:
                    tgt = nth_trading_day(fire_d, k)
                    if tgt > today:
                        continue  # horizon not reached yet
                    any_reachable = True
                    close_k = close_on_or_near(idx, tgt)
                    if close_k is not None:
                        vals[k] = _dir_adj(entry, close_k, direction)

                if all(v is None for v in vals.values()):
                    _skip("bars_missing_for_reached_horizon" if any_reachable
                          else "horizon_not_reached_yet")
                    skipped += 1
                    continue

                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE triton_flow_shadow
                        SET fwd_ret_1d = COALESCE($2, fwd_ret_1d),
                            fwd_ret_3d = COALESCE($3, fwd_ret_3d),
                            fwd_ret_5d = COALESCE($4, fwd_ret_5d),
                            provider = $5,
                            graded_at  = CASE WHEN $4 IS NOT NULL THEN NOW() ELSE graded_at END
                        WHERE id = $1
                        """,
                        g["id"], vals[1], vals[3], vals[5], provider,
                    )
                graded += 1
                if vals[5] is not None:
                    fully += 1
            except Exception as exc:
                logger.warning("triton_grader: row %s skip: %s", g["id"], type(exc).__name__)
                _skip("row_error:" + type(exc).__name__)
                skipped += 1
                continue

    logger.info("triton_grader: touched=%d fully_graded=%d skipped=%d reasons=%s providers=%s",
                graded, fully, skipped, skips or "{}", providers_used or "{}")
    # providers_used is the fallback's OWN evidence: if it is all "uw" the net
    # was never needed, and if it is all "yfinance" Path A is dead for every
    # ticker -- two very different worlds that a graded-count alone cannot tell
    # apart. Returned so the caller can record it without re-deriving it.
    return {"graded": graded, "fully_graded": fully, "skipped": skipped,
            "skips": skips, "providers": providers_used}
