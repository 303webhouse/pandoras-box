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

import asyncio
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


# ── R-IV.436(b): A ROW WHOSE WINDOW SPANS A CORPORATE ACTION IS HELD, NOT GRADED ──
#
# The same rule the backtest module got at R-IV.432(e), for the same reason and on both
# vendor paths. `spot_at_fire` is a RAW price recorded when the row fired; every bar series
# in use -- UW's and yfinance's alike -- is SPLIT-ADJUSTED AS OF FETCH. A split between the
# fire and the fetch therefore compares two price scales, and the grade is wrong by the split
# ratio. The two KORU rows (ids 38201, 80352; 20-for-1 ex 2026-07-15) are the measured case:
# stored grades of -94% and +95% that are really +13% and -17%.
#
# The fallback makes this urgent rather than theoretical: yfinance serves a series for almost
# anything, so a row that used to fail slowly on an empty UW answer now gets a plausible
# number instead.
#
# UNKNOWN IS NOT "NO EVENTS". When the calendar cannot be read the row is held, with its own
# reason, and tried again next pass -- the grader's other skips work the same way.
#
# R-IV.436(d): the calendar here is yfinance's and the bars may be UW's, so the check is
# already cross-vendor on the UW path. It is a HOLD, never a correction: resolving a held row
# needs an independent price (UW spot, or the raw entry), never this vendor's calendar
# confirming this vendor's bars.
CALENDAR_UNAVAILABLE = "corporate_action_calendar_unavailable"
HELD_CORPORATE_ACTION = "held_corporate_action"


def _split_ex_dates(ticker: str):
    """Ex-dates of split-type actions for a ticker, or None when the calendar cannot be read."""
    try:
        import yfinance as yf

        s = yf.Ticker(ticker).splits
        if s is None:
            return None
        out = set()
        for ts, ratio in s.items():
            try:
                if float(ratio) > 0:
                    out.add(ts.date() if hasattr(ts, "date") else ts)
            except (TypeError, ValueError):
                continue
        return out
    except Exception as exc:  # noqa: BLE001 -- unreadable, not empty
        logger.warning("triton_grader: split calendar unreadable for %s: %s",
                       ticker, type(exc).__name__)
        return None


def spans_corporate_action(ex_dates, fire_date, through):
    """True when an ex-date falls after the fire and at or before the fetch.

    An action ON the fire date is already inside the fire-time price; one after the fetch is
    not in the series yet. Everything between rescales the series under the raw entry.
    """
    return any(fire_date < d <= through for d in (ex_dates or ()))


# ── AMENDMENT 4 (R-IV.521, ordered by R-IV.522(b)) ────────────────────────────
#
# (c) NO SUBSTITUTION INSIDE THE WINDOW. A horizon whose pinned-vendor bar is absent
# stays ungraded. It is called a gap only after THREE SEPARATE REQUESTS have failed
# to return it — separate in time, not three calls in one pass: the vendor served
# different coverage to identical requests days apart (R-IV.517(b)), so a same-pass
# retry would mostly re-ask a cache and name a recoverable absence permanent.
SESSION_GAP_MIN_ATTEMPTS = 3
SESSION_GAP = "UNGRADEABLE-SESSION-GAP"          # Amendment 4(d)'s §P2 class
SESSION_BAR_RETRYING = "session_bar_absent_retrying"
HORIZON_NOT_A_SESSION = "horizon_not_a_session"


async def _count_bar_absence(pool, ticker: str, session_date, provider: str) -> int:
    """Record ONE failed request for that session's bar; return the running total.

    Returns SESSION_GAP_MIN_ATTEMPTS when the store cannot be read. An unreadable
    counter must not be able to hold a horizon open forever — that would convert a
    database blip into an indefinite postponement of the read, and 4(f) already has
    a stated route for a gap. Being loud about a gap is recoverable; silently never
    resolving is not.
    """
    try:
        async with pool.acquire() as conn:
            n = await conn.fetchval(
                """
                INSERT INTO triton_session_bar_attempts
                    (ticker, session_date, provider, attempts)
                VALUES ($1, $2, $3, 1)
                ON CONFLICT (ticker, session_date, provider) DO UPDATE
                   SET attempts = triton_session_bar_attempts.attempts + 1,
                       last_attempt_at = NOW()
                RETURNING attempts
                """,
                ticker, session_date, provider,
            )
        return int(n or SESSION_GAP_MIN_ATTEMPTS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("triton_grader: attempt counter unreadable for %s %s: %s — "
                       "treating the absence as a gap", ticker, session_date,
                       type(exc).__name__)
        return SESSION_GAP_MIN_ATTEMPTS


async def _close_for_session(pool, idx, target, *, ticker: str, provider: str,
                             strict: bool):
    """(close, session_used, gap_reason). `strict` is Amendment 4(c): in-window rows.

    Out-of-window rows keep the neighbour probe exactly as it was (R-IV.522(b)2),
    and now carry the date it used, so a substitution there is recorded rather than
    invisible.
    """
    from jobs.triton_shadow_common import close_on_or_near, close_on_session

    if not strict:
        close, used = close_on_or_near(idx, target)
        return close, used, None
    close = close_on_session(idx, target)
    if close is not None:
        return close, target, None
    n = await _count_bar_absence(pool, ticker, target, provider)
    return None, None, (SESSION_GAP if n >= SESSION_GAP_MIN_ATTEMPTS
                        else SESSION_BAR_RETRYING)


def _gap_text(gaps) -> "str | None":
    """Amendment 4(d)'s pairs: "3d@2026-09-22", so the face needs no re-derivation."""
    if not gaps:
        return None
    return ",".join("%dd@%s" % (k, gaps[k]) for k in sorted(gaps))


async def run_triton_shadow_grader() -> dict:
    """One grading pass. Never raises (fail-open). Returns a small summary."""
    from database.postgres_client import get_postgres_client
    from jobs.triton_shadow_common import (
        fetch_r_close_index, nth_trading_day, horizon_is_session, _f,
        triton_row_pinned, PROVIDER_NONE,
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
              -- T5b Phase C (R-IV.360(2)): rows that can NEVER grade do not get to
              -- occupy the queue. They are the OLDEST ungraded rows -- nothing ever
              -- clears them -- so `ORDER BY fired_at` puts them at the head of
              -- EVERY pass, where they consume GRADE_LIMIT budget forever.
              -- NULL is included deliberately: an unclassified row is not known to
              -- be ungradeable, and excluding it would silently shrink the queue on
              -- the strength of a missing value.
              AND (instrument_class IS NULL OR instrument_class <> 'cash_settled_index')
            ORDER BY fired_at
            LIMIT $1
            """,
            GRADE_LIMIT,
        )
    # DEF-GRADER-QUEUE-CENSORED-AT-LIMIT (R-IV.364(b)). A skip count equal to
    # GRADE_LIMIT measures the LIMIT, not the backlog: on 2026-09-11 the pass
    # reported no_regular_session_bars=1000 against GRADE_LIMIT=1000 with 1,083
    # rows ungraded, and that was read as growth. The queue total is counted
    # separately so `processed` and `outstanding` can never be confused again.
    async with pool.acquire() as conn:
        ungraded_total = await conn.fetchval(
            """
            SELECT count(*) FROM triton_flow_shadow
            WHERE graded_at IS NULL
              AND fired_at IS NOT NULL
              AND fired_at < NOW() - INTERVAL '1 day'
              AND (instrument_class IS NULL OR instrument_class <> 'cash_settled_index')
            """
        )
    selected = len(rows)
    censored = selected >= GRADE_LIMIT
    if censored:
        logger.warning("triton_grader: selection hit GRADE_LIMIT %d of %s ungraded — "
                       "per-reason counts are CENSORED at the limit",
                       GRADE_LIMIT, ungraded_total)

    if not rows:
        # NOT a skip. Nothing was ungraded, which is the healthy steady state.
        return {"graded": 0, "skipped": 0, "skips": {},
                "ungraded_total": ungraded_total, "selected": 0, "censored": False}

    # Group by ticker for batched bar fetches
    by_ticker: dict = {}
    for r in rows:
        by_ticker.setdefault((r["ticker"] or "").upper(), []).append(r)

    today = datetime.now(timezone.utc).date()
    graded = fully = skipped = held = 0
    providers_used: dict = {}
    # Amendment 4(d): the gaps themselves, so the read's face can list ticker,
    # horizon and session. A count would say how many and never which.
    session_gaps: list = []

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

        # R-IV.436(b), BEFORE the fetch: a fully-held ticker costs no vendor call.
        ex_dates = await asyncio.to_thread(_split_ex_dates, ticker)
        if ex_dates is None:
            logger.warning("triton_grader: %s calendar unreadable — holding %d row(s)",
                           ticker, len(group))
            _skip(CALENDAR_UNAVAILABLE, len(group))
            skipped += len(group)
            held += len(group)
            continue
        gradable = []
        for g in group:
            fd = g["fired_at"].date() if hasattr(g["fired_at"], "date") else g["fired_at"]
            if spans_corporate_action(ex_dates, fd, today):
                _skip(HELD_CORPORATE_ACTION)
                skipped += 1
                held += 1
            else:
                gradable.append(g)
        if not gradable:
            continue
        group = gradable

        # R-IV.497(d): the bar vendor is a property of the ROW, not of the run, so
        # a ticker's rows can need two different series. They are fetched
        # separately and never merged — mixing providers inside one measurement is
        # the cross-adjustment seam uw_api.py forbids — and each row reads the one
        # its own fired_at session entitles it to, below.
        _need_pinned = any(triton_row_pinned(g.get("fired_at")) for g in group)
        _need_open = any(not triton_row_pinned(g.get("fired_at")) for g in group)
        idx_pinned, prov_pinned = (
            await fetch_r_close_index(ticker, lookback_days, pinned=True)
            if _need_pinned else ({}, PROVIDER_NONE))
        idx_open, prov_open = (
            await fetch_r_close_index(ticker, lookback_days, pinned=False)
            if _need_open else ({}, PROVIDER_NONE))

        if not idx_pinned and not idx_open:
            # Still reachable AFTER the fallback: UW empty AND yfinance empty.
            # The reason string is unchanged so the 944-row backlog stays
            # comparable across the fix -- a renamed reason would reset the
            # series and make the fallback look effective by discontinuity.
            logger.warning("triton_grader: no 'r' bars for %s (pinned=%s/open=%s) — skip %d",
                           ticker, prov_pinned, prov_open, len(group))
            _skip("no_regular_session_bars", len(group))
            skipped += len(group)
            continue

        for g in group:
            try:
                # This row's series, chosen by its OWN session (R-IV.497(d)).
                is_pinned = triton_row_pinned(g.get("fired_at"))
                idx, provider = (idx_pinned, prov_pinned) if is_pinned else (idx_open, prov_open)
                if not idx:
                    _skip("no_regular_session_bars")
                    skipped += 1
                    continue
                providers_used[provider] = providers_used.get(provider, 0) + 1
                fire_d = g["fired_at"].date() if hasattr(g["fired_at"], "date") else g["fired_at"]
                direction = g["direction"] or "BULL"
                # entry reference: fire-time spot, else fire-date 'r' close.
                # Amendment 4(b): whichever it is, the session it belongs to is
                # recorded. The fire-time spot IS the fire session's price, so that
                # branch is provenance too, not an absence of it.
                entry = _f(g["spot_at_fire"])
                entry_session = fire_d if (entry and entry > 0) else None
                if not entry or entry <= 0:
                    entry, entry_session, _egap = await _close_for_session(
                        pool, idx, fire_d, ticker=ticker, provider=provider,
                        strict=is_pinned)
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
                sess = {1: None, 3: None, 5: None}
                gaps: dict = {}
                for k in HORIZONS:
                    tgt = nth_trading_day(fire_d, k)
                    if tgt > today:
                        continue  # horizon not reached yet
                    any_reachable = True
                    # Amendment 4(c) defines a horizon session as a weekday THE
                    # EXCHANGE TRADED. nth_trading_day walks Mon-Fri with no holiday
                    # calendar, which is only safe while the window holds no holiday
                    # — confirmed, and this refuses rather than trusts the memory.
                    if is_pinned and horizon_is_session(tgt) is not True:
                        gaps[k] = tgt
                        _skip(HORIZON_NOT_A_SESSION)
                        logger.error("triton_grader: row %s horizon %dd lands on %s, "
                                     "which the calendar does not call a session — "
                                     "NOT graded", g["id"], k, tgt)
                        continue
                    close_k, used_k, gap = await _close_for_session(
                        pool, idx, tgt, ticker=ticker, provider=provider,
                        strict=is_pinned)
                    if gap:
                        gaps[k] = tgt
                        _skip(gap)
                        continue
                    if close_k is not None:
                        vals[k] = _dir_adj(entry, close_k, direction)
                        sess[k] = used_k

                for _k, _d in gaps.items():
                    session_gaps.append({"row_id": g["id"], "ticker": ticker,
                                         "horizon": "%dd" % _k, "session": str(_d)})

                if all(v is None for v in vals.values()):
                    _skip("bars_missing_for_reached_horizon" if any_reachable
                          else "horizon_not_reached_yet")
                    skipped += 1
                    continue

                async with pool.acquire() as conn:
                    # R-IV.497(d): a grade a READ has consumed is never overwritten.
                    # The UPDATE is conditional on the row still being ungraded, so a
                    # re-grade cannot replace the figure a Friday read already stood
                    # on. Every grade — first or re-grade — is ALSO appended to
                    # triton_grade_versions, so a re-grade lands beside its
                    # predecessor and both stay readable. Enforced at the WRITE: the
                    # SELECT's `graded_at IS NULL` is today's caller, not a guarantee.
                    status = await conn.execute(
                        """
                        UPDATE triton_flow_shadow
                        SET fwd_ret_1d = COALESCE($2, fwd_ret_1d),
                            fwd_ret_3d = COALESCE($3, fwd_ret_3d),
                            fwd_ret_5d = COALESCE($4, fwd_ret_5d),
                            provider = $5,
                            graded_at  = CASE WHEN $4 IS NOT NULL THEN NOW() ELSE graded_at END
                        WHERE id = $1 AND graded_at IS NULL
                        """,
                        g["id"], vals[1], vals[3], vals[5], provider,
                    )
                    await conn.execute(
                        """
                        INSERT INTO triton_grade_versions
                            (row_id, version, fwd_ret_1d, fwd_ret_3d, fwd_ret_5d,
                             provider, pinned, entry_session,
                             session_1d, session_3d, session_5d, session_gaps)
                        SELECT $1, COALESCE(MAX(version), 0) + 1, $2, $3, $4, $5, $6,
                               $7, $8, $9, $10, $11
                        FROM triton_grade_versions WHERE row_id = $1
                        """,
                        g["id"], vals[1], vals[3], vals[5], provider, is_pinned,
                        entry_session, sess[1], sess[3], sess[5], _gap_text(gaps),
                    )
                    if status and status.strip().endswith(" 0"):
                        logger.info("triton_grader: row %s was already graded — a new "
                                    "version is recorded beside it and the consumed "
                                    "grade is untouched", g["id"])
                graded += 1
                if vals[5] is not None:
                    fully += 1
            except Exception as exc:
                logger.warning("triton_grader: row %s skip: %s", g["id"], type(exc).__name__)
                _skip("row_error:" + type(exc).__name__)
                skipped += 1
                continue

    logger.info("triton_grader: touched=%d fully_graded=%d skipped=%d held=%d reasons=%s providers=%s",
                graded, fully, skipped, held, skips or "{}", providers_used or "{}")
    # providers_used is the fallback's OWN evidence: if it is all "uw" the net
    # was never needed, and if it is all "yfinance" Path A is dead for every
    # ticker -- two very different worlds that a graded-count alone cannot tell
    # apart. Returned so the caller can record it without re-deriving it.
    return {"graded": graded, "fully_graded": fully, "skipped": skipped, "held": held,
            "skips": skips, "providers": providers_used,
            # Amendment 4(d): the gaps, not a count of them.
            "session_gaps": session_gaps,
            # `selected` is what this pass looked at; `ungraded_total` is what
            # exists. When censored is True the skip reasons describe the
            # SELECTION and say nothing about the remainder.
            "ungraded_total": ungraded_total, "selected": selected,
            "censored": censored}
