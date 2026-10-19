"""The live NOTABLES read. R-IV.1259, wired under R-IV.1265(g)2.

DISPLAY ONLY (#42). Nothing here gates, caps, journals or writes `signals`.

WHAT THIS MODULE IS. `models/notables_cards.py` holds the decisions and takes no I/O; this is
the half that fetches. The split is deliberate: a detector that fetches cannot be tested against
the tape that is supposed to fire it, and every trigger in the ruling has a boundary worth
testing exactly.

EVERY CANDIDATE IS LOGGED, SHOWN OR NOT (R-IV.1259(h)). The drop reasons are the only way the
cap, the one-card-per-ticker rule and the PYTHIA gate are auditable: a surface that logged only
what it displayed could not say whether three candidates were considered or three hundred.

AN INPUT THAT IS ABSENT IS NAMED, NEVER ASSUMED. Each card kind reports into `inputs_missing`
with the reason it could not be evaluated, so "nothing notable happened" and "we could not
look" are different answers on the payload. That distinction is the one this board keeps
filing: a silence that looks like health.

SOURCES, each used for the thing it is right for:
  * `services.read_only.market_profile.get_market_profile` -- per-ticker value area, initial
    balance, and THE TICKER'S OWN PYTHIA STATUS AND AGE. The whole feed reading "flowing" never
    stands in for one ticker's own last update (R-IV.1259(c)2), and this accessor is the only
    thing that answers per ticker.
  * `integrations.yf_15m` -- today's closed 15-minute bars and the prior-day levels, already
    built for Position Watch and already sorting ascending.
  * `stable_daily_bars` -- daily OHLCV for ATR, ADX, DI and the moving-average stack. The
    fully-adjusted basis, which R-IV.1203(c) rules correct for moving averages.
  * `catalyst_events` -- whether the Hermes velocity alarm fired today, as a FACT that already
    happened. This module does not re-derive somebody else's alarm.

NO UW CALL IS MADE HERE. The option strip spends from `notables_strip`'s 50/day (R-IV.1265(d))
and is a separate step; until it is wired every card reports its strip as unavailable with that
reason, which is the honest state rather than an empty strip that looks like a thin chain.
"""
from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from models import notables_cards as nc
from models import notables_log as nlog
from models.notables_strip import UNAVAILABLE_TEXT

logger = logging.getLogger("notables_read")

ET = ZoneInfo("America/New_York")

#: The sector SPDRs, for (c)1's 1.5x-ATR trigger. Index ETFs are excluded from it on purpose:
#: the ruling says "any sector SPDR", and SPY has its own -1% trigger.
SECTOR_SPDRS = ("XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLC", "XLRE")

#: Daily bars to load per ticker: enough for ADX(14), a 200-day average and a prior class.
DAILY_BARS = 260

#: Why the strip is absent until the UW step lands. Named once.
STRIP_NOT_WIRED = ("%s (the option strip is not wired yet; it spends from notables_strip's "
                   "50 calls a day, R-IV.1265(d))" % UNAVAILABLE_TEXT)


def _session_date(now_et: _dt.datetime) -> _dt.date:
    return now_et.date()


async def _daily_bars(conn, tickers: Sequence[str]) -> Dict[str, List[Any]]:
    """Oldest-first daily bars per ticker from `stable_daily_bars`.

    ORDERED ASC IN THE QUERY, not reversed afterwards. The vendor-order landmine in this repo
    (`fetch_crypto_ohlc` returning descending bars into positional slices) came from exactly
    that assumption being made silently somewhere else. `Bar.from_row` is reused so the
    row-to-bar mapping has one author even though the SELECT is this module's own -- importing
    a private loader out of a job would couple a read-only service to a job's internals.
    """
    from models.regime_inputs import Bar

    out: Dict[str, List[Any]] = {}
    for t in tickers:
        try:
            rows = await conn.fetch(
                """SELECT date, o, h, l, c, v
                     FROM stable_daily_bars
                    WHERE ticker = $1
                    ORDER BY date DESC
                    LIMIT $2""", t, int(DAILY_BARS))
            out[t] = [Bar.from_row(r) for r in reversed(rows)]
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("[notables] daily bars for %s unavailable: %s", t, type(exc).__name__)
            out[t] = []
    return out


async def _hermes_fired_today(conn, session_date: _dt.date) -> Dict[str, bool]:
    """Which of SPY/QQQ/SMH had a velocity breach today, from the hub's own record.

    A FACT THAT ALREADY HAPPENED, not a re-derivation. The alarm is Hermes's and re-computing
    its threshold here would give the hub two answers about whether it fired.
    """
    out = {t: False for t in nc.HERMES_TICKERS}
    try:
        rows = await conn.fetch(
            """SELECT DISTINCT UPPER(trigger_ticker) AS t
                 FROM catalyst_events
                WHERE event_type = 'velocity_breach'
                  AND (created_at AT TIME ZONE 'America/New_York')::date = $1""",
            session_date)
        for r in rows:
            if r["t"] in out:
                out[r["t"]] = True
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[notables] hermes read unavailable: %s", type(exc).__name__)
        return {}
    return out


def _pct_move(session: Sequence[Dict[str, Any]]) -> Optional[float]:
    """Today's move, open of the first bar to close of the last CLOSED bar, in percent.

    From the session's own first open rather than from the prior close, deliberately: (c)1's
    sector trigger is about the move the tape has made TODAY, and including the gap would make a
    flat session after a big gap read as a loud move.
    """
    if not session:
        return None
    first = session[0].get("open")
    last = session[-1].get("close")
    if first in (None, 0) or last is None:
        return None
    return round((float(last) - float(first)) / float(first) * 100.0, 3)


def _atr_pct(bars: Sequence[Any]) -> Optional[float]:
    """ATR(14) as a percentage of the latest close, so it compares with a percentage move."""
    from indicators.adx import latest_atr

    if len(bars) < 20:
        return None
    atr = latest_atr([b.h for b in bars], [b.l for b in bars], [b.c for b in bars])
    last = bars[-1].c
    if atr is None or not last:
        return None
    return round(atr / float(last) * 100.0, 4)


def _ma(bars: Sequence[Any], period: int) -> Optional[float]:
    if len(bars) < period:
        return None
    return round(sum(b.c for b in bars[-period:]) / period, 4)


def _trend_inputs(bars: Sequence[Any]) -> Dict[str, Any]:
    """Everything (c)4 needs, with each absence left as None rather than filled.

    The PRIOR values are computed over the series minus its last bar, which is what "crosses"
    and "changes class" mean: a trigger comparing a value against itself can only ever be a
    level test, and (c)4 asks for a change.
    """
    from indicators.adx import latest_adx, latest_di

    if len(bars) < 40:
        return {}
    h = [b.h for b in bars]
    l = [b.l for b in bars]
    c = [b.c for b in bars]
    di = latest_di(h, l, c)
    prior = bars[:-1]
    return {
        "adx": latest_adx(h, l, c),
        "adx_prior": latest_adx(h[:-1], l[:-1], c[:-1]),
        "di_plus": (di[0] if di else None),
        "di_minus": (di[1] if di else None),
        "ma20": _ma(bars, 20), "ma50": _ma(bars, 50), "ma120": _ma(bars, 120),
        "stack_prior": nc.stack_class(_ma(prior, 20), _ma(prior, 50), _ma(prior, 120)),
        "close": bars[-1].c, "close_prior": bars[-2].c,
        "ma200": _ma(bars, 200), "ma200_prior": _ma(prior, 200),
        "volume": bars[-1].v,
        "avg_volume": (round(sum(b.v for b in bars[-20:]) / 20.0, 2)
                       if len(bars) >= 20 and all(b.v is not None for b in bars[-20:])
                       else None),
    }


def _counter_evidence(*, bars: Sequence[Any], trend: Dict[str, Any],
                      session: Sequence[Dict[str, Any]]) -> List[str]:
    """(g): counter-evidence FROM THE SAME DATA. Never invented, so an input we do not have
    produces no line rather than a guess (R-IV.925(b)).

    Returns at least one line whenever anything is known, because `finish_card` refuses a card
    with none -- and a card that cannot state what argues against it should not be shown.
    """
    out: List[str] = []
    adx = trend.get("adx")
    if adx is not None:
        if adx < 20:
            out.append("Daily trend: range (ADX %.1f)" % adx)
        elif adx >= nc.ADX_TREND_LEVEL:
            out.append("Daily trend: trending (ADX %.1f)" % adx)
        else:
            out.append("Daily trend: transition (ADX %.1f)" % adx)
    ma200 = trend.get("ma200")
    close = trend.get("close")
    if ma200 is not None and close is not None:
        out.append("%s the 200-day" % ("Above" if close > ma200 else "Below"))
    vol = trend.get("volume")
    avg = trend.get("avg_volume")
    if vol is not None and avg:
        mult = float(vol) / float(avg)
        if mult < 0.8:
            out.append("Thin volume (%.1fx the 20-day)" % mult)
        elif mult > 1.5:
            out.append("Heavy volume (%.1fx the 20-day)" % mult)
    if session:
        out.append("%d closed bar(s) in the session so far" % len(session))
    return out


async def payload(*, now_et: Optional[_dt.datetime] = None,
                  log: bool = True) -> Dict[str, Any]:
    """The live NOTABLES read. Never raises: an unavailable input is reported, not thrown.

    `log` exists so a read can be taken WITHOUT appending to `notables_log` -- a diagnostic
    read, or a second render inside the same minute, must not double the day's candidate count.
    The surface's own fetch logs; anything else does not.
    """
    now_et = now_et or _dt.datetime.now(ET)
    session_date = _session_date(now_et)
    out: Dict[str, Any] = {
        "live": True,
        "as_of": now_et.isoformat(),
        "session_date": session_date.isoformat(),
        "hours_ok": None,
        "cards": {"context": [], "watch": []},
        "counts": {},
        "inputs_missing": {},
        "strip": {"available": False, "reason": STRIP_NOT_WIRED},
        "basis": ("NOTABLES v2 live read: PYTHIA value areas and initial balance per ticker "
                  "(services.read_only.market_profile), today's closed 15-minute bars "
                  "(yfinance), daily OHLCV for ATR/ADX/stack (stable_daily_bars, fully "
                  "adjusted), and the Hermes velocity record (catalyst_events) -- as of %s ET"
                  % now_et.strftime("%Y-%m-%d %H:%M")),
        "display_only": "display only (#42): nothing gates, caps or journals on these cards",
    }

    allowed, why = nc.in_hours(now_et)
    out["hours_ok"] = allowed
    if not allowed:
        out["reason"] = why
        return out

    from services.notables import NO_STRUCTURE_CARDS, UNIVERSE

    try:
        from database.postgres_client import get_postgres_client

        pool = await get_postgres_client()
    except Exception as exc:                                        # noqa: BLE001
        out["inputs_missing"]["database"] = (
            "the database is unreachable (%s), so no card can be evaluated"
            % type(exc).__name__)
        return out

    tickers = sorted(UNIVERSE)
    # ONE BATCHED BAR FETCH for the whole universe, as yf_15m was built to do: a per-ticker
    # download would be 20 vendor calls for one render.
    bars15: Dict[str, List[Dict[str, Any]]] = {}
    try:
        from integrations import yf_15m

        bars15 = yf_15m.fetch(tickers, days=3)
    except Exception as exc:                                        # noqa: BLE001
        out["inputs_missing"]["intraday_bars"] = (
            "the 15-minute bars could not be fetched (%s); VALUE MOVED and FAILED BREAK cannot "
            "be evaluated" % type(exc).__name__)

    async with pool.acquire() as conn:
        daily = await _daily_bars(conn, tickers)
        hermes = await _hermes_fired_today(conn, session_date)
        if not hermes:
            out["inputs_missing"]["hermes_velocity"] = (
                "the Hermes velocity record could not be read, so the alarm leg of LOUD MOVE is "
                "not evaluated; the SPY breaker and the sector ATR legs are unaffected")
        counts = await nlog.session_counts(conn, session_date)
        shown_today = int(counts.get("shown") or 0)
        shown_tickers = await _tickers_shown_today(conn, session_date)

        candidates: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []

        for ticker in tickers:
            bars = daily.get(ticker) or []
            trend = _trend_inputs(bars)
            session: List[Dict[str, Any]] = []
            prior_hi = prior_lo = None
            if bars15.get(ticker):
                try:
                    from integrations import yf_15m

                    # THE SIGNATURES ARE THE MODULE'S, READ RATHER THAN ASSUMED.
                    # `closed_bars` returns (bars, why) and takes `session_closed`;
                    # `prior_day_level` returns (high, low, basis) in ONE call and not one
                    # call per side. Guessing either would have been the invented-signature
                    # fault this lane has already shipped twice.
                    session, _why = yf_15m.closed_bars(
                        yf_15m.session_bars(bars15[ticker], session_date),
                        now=now_et,
                        session_closed=now_et.time() >= _dt.time(16, 0))
                    prior_hi, prior_lo, _basis = yf_15m.prior_day_level(
                        bars15[ticker], session_date)
                except Exception as exc:                            # noqa: BLE001
                    out["inputs_missing"].setdefault(
                        "session_bars",
                        "a session's bars could not be split (%s)" % type(exc).__name__)

            counter = _counter_evidence(bars=bars, trend=trend, session=session)
            mp = await _market_profile(ticker)

            for card in _cards_for(ticker=ticker, now_et=now_et, session=session,
                                   prior_hi=prior_hi, prior_lo=prior_lo, mp=mp, trend=trend,
                                   atr_pct=_atr_pct(bars), move_pct=_pct_move(session),
                                   hermes_fired=bool(hermes.get(ticker))):
                pythia_ok, pythia_why = (True, None)
                if card["card_kind"] == "VALUE_MOVED":
                    pythia_ok, pythia_why = nc.pythia_gate(
                        status=(mp or {}).get("status"),
                        last_update_et=_mp_updated_et(mp),
                        now_et=now_et,
                        session_days=[session_date])
                shown, drop = nc.may_show(
                    card, now_et=now_et, shown_today=shown_today,
                    tickers_shown_today=shown_tickers, universe=UNIVERSE,
                    no_structure_cards=NO_STRUCTURE_CARDS, held_tickers=(),
                    pythia_ok=pythia_ok, pythia_reason=pythia_why)
                try:
                    finished = nc.finish_card(card, counter_evidence=counter,
                                              stale_if=card.get("stale_if"))
                except ValueError as exc:
                    # A card that cannot state what argues against it is not shown AND is
                    # logged as dropped, so the refusal is visible rather than silent.
                    out["inputs_missing"].setdefault(
                        "counter_evidence",
                        "%s: %s" % (ticker, exc))
                    candidates.append((card, {"shown": False,
                                              "drop_reason": nlog.DROP_NOT_IN_UNIVERSE
                                              if drop is None else drop}))
                    continue
                if shown:
                    lane = "context" if finished["lane"] == nc.LANE_CONTEXT else "watch"
                    out["cards"][lane].append(finished)
                    if finished.get("counts_against_cap"):
                        shown_today += 1
                        shown_tickers = list(shown_tickers) + [ticker]
                candidates.append((finished, {"shown": shown, "drop_reason": drop,
                                              "pythia_reason": pythia_why}))

        # The market-wide line, which is not a ticker card and never meets the cap.
        line = await _rotation_line(conn)
        if line:
            out["cards"]["context"].append(nc.finish_card(line, counter_evidence=[]))
            candidates.append((line, {"shown": True, "drop_reason": None}))

        if log:
            await _log_candidates(conn, candidates, session_date=session_date, now_et=now_et)
            out["counts"] = await nlog.session_counts(conn, session_date)
        else:
            out["counts"] = dict(counts, note="this read did not log; counts are as they were")

    out["counts"]["cap"] = nc.DAILY_TICKER_CAP
    out["counts"]["shown_now"] = len(out["cards"]["watch"])
    return out


async def _tickers_shown_today(conn, session_date: _dt.date) -> List[str]:
    try:
        rows = await conn.fetch(
            "SELECT DISTINCT ticker FROM notables_log "
            " WHERE session_date = $1 AND shown IS TRUE AND ticker IS NOT NULL", session_date)
        return [r["ticker"] for r in rows]
    except Exception:                                               # noqa: BLE001
        return []


async def _market_profile(ticker: str) -> Optional[Dict[str, Any]]:
    try:
        from services.read_only.market_profile import get_market_profile

        return await get_market_profile(ticker)
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[notables] market profile for %s unavailable: %s",
                       ticker, type(exc).__name__)
        return None


def mp_levels(mp: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The accessor's `data` block, or {}. IT IS NESTED, which I had to read to find out.

    `get_market_profile` returns {"status", "data", "staleness_seconds"} -- so `mp["prev_vah"]`
    is None on every ticker and every VALUE MOVED card would silently never fire, with nothing
    to show that the levels were being read from the wrong depth. The status stays at the TOP
    level and the levels are one down; both are read from where they are.
    """
    return (mp or {}).get("data") or {}


def _mp_updated_et(mp: Optional[Dict[str, Any]]) -> Optional[_dt.datetime]:
    """When THIS TICKER's PYTHIA row was last written, in Eastern. None when unknown.

    Derived from the accessor's own `event_age_seconds` rather than from its timestamp string:
    the age is what the accessor measured, and re-parsing a timestamp here would be a second
    answer to the same question.
    """
    age = mp_levels(mp).get("event_age_seconds")
    if age is None:
        return None
    try:
        return _dt.datetime.now(ET) - _dt.timedelta(seconds=float(age))
    except (TypeError, ValueError):
        return None


def _cards_for(*, ticker: str, now_et: _dt.datetime, session: Sequence[Dict[str, Any]],
               prior_hi: Optional[float], prior_lo: Optional[float],
               mp: Optional[Dict[str, Any]], trend: Dict[str, Any],
               atr_pct: Optional[float], move_pct: Optional[float],
               hermes_fired: bool) -> List[Dict[str, Any]]:
    """Every card this ticker produces on this read, in the ruling's own card order."""
    mp = mp_levels(mp)
    closes = [b["close"] for b in session if b.get("close") is not None]
    cards: List[Dict[str, Any]] = []

    loud = nc.loud_move(ticker=ticker, move_pct=move_pct,
                        hermes_velocity_fired=hermes_fired, atr_pct=atr_pct,
                        is_sector_spdr=(ticker in SECTOR_SPDRS))
    if loud:
        cards.append(loud)

    moved = nc.value_moved(
        ticker=ticker, close=(closes[-1] if closes else None),
        prior_value_high=mp.get("prev_vah"), prior_value_low=mp.get("prev_val"),
        ib_high=mp.get("ib_high"), ib_low=mp.get("ib_low"),
        today_value_high=mp.get("vah"), today_value_low=mp.get("val"),
        now_et=now_et)
    if moved:
        cards.append(moved)

    if closes:
        failed = nc.failed_break(ticker=ticker, session_closes=closes, levels={
            "value": (mp.get("prev_vah"), mp.get("prev_val")),
            "ib": (mp.get("ib_high"), mp.get("ib_low")),
            "prior_day": (prior_hi, prior_lo),
        })
        if failed:
            cards.append(failed)

    if trend:
        changed = nc.trend_change(ticker=ticker, **trend)
        if changed:
            cards.append(changed)
    return cards


async def _rotation_line(conn) -> Optional[Dict[str, Any]]:
    """(c)5's Context line, from the hub's own theme table. None when it cannot be evaluated.

    WHAT THE HUB ACTUALLY HAS, read rather than assumed. There is no `stable_themes` table and
    no per-theme data-quality column: the themes live in `stable_theme_scores`, one row per
    (date, anchor, theme), with a `status` and NO prior status. So a status CHANGE is the two
    latest snapshots of the same anchor, paired by theme -- which is a real comparison, where a
    line built on the current status alone would say "rotation shifted" on a day nothing
    shifted.

    THE DATA-QUALITY SUPPRESSION IS PER SNAPSHOT, BECAUSE THAT IS THE GRAIN THE HUB RECORDS.
    (c)5 says themes with data-quality warnings are suppressed; the only such flag here is the
    snapshot's own `degraded`, so a degraded snapshot suppresses the whole line WITH THAT REASON
    rather than being filtered theme by theme against a column that does not exist
    (R-IV.925(b)). Inventing a per-theme flag would be worse than naming the grain.

    The sector-rotation half of (c)5 is NOT evaluated here and says so: this hub stores no
    sector rotation LABEL whose previous value a read can reach, and mapping the regime label
    onto it would be a different claim wearing the ruling's words.
    """
    # THERE IS NO SNAPSHOT TABLE. The snapshot's own columns -- date, anchor, as_of, degraded --
    # live ON `stable_theme_scores`, one copy per theme row, which is how `_latest_snapshot`
    # reads them. My first version of this query selected from `stable_theme_snapshots`, a table
    # that exists nowhere: the third invented-path fault of this session's wiring, after a
    # guessed `yf_15m` signature and a flat read of a nested envelope. All three were caught by
    # reading the source instead of trusting the name.
    try:
        snaps = await conn.fetch(
            "SELECT DISTINCT date, anchor, degraded FROM stable_theme_scores "
            " ORDER BY date DESC LIMIT 2")
    except Exception as exc:                                        # noqa: BLE001
        logger.info("[notables] theme shift not evaluated: %s", type(exc).__name__)
        return None
    if len(snaps) < 2:
        return None
    newest, prior = snaps[0], snaps[1]
    if newest["anchor"] != prior["anchor"]:
        # Two anchors are two different universes; a "change" across them would be a change of
        # measuring stick, not of the market.
        return None
    if newest["degraded"] or prior["degraded"]:
        return None
    try:
        rows = await conn.fetch(
            """SELECT n.theme, n.status AS status, p.status AS prior_status
                 FROM stable_theme_scores n
                 JOIN stable_theme_scores p
                   ON p.theme = n.theme AND p.date = $2 AND p.anchor = n.anchor
                WHERE n.date = $1 AND n.anchor = $3""",
            newest["date"], prior["date"], newest["anchor"])
    except Exception as exc:                                        # noqa: BLE001
        logger.info("[notables] theme statuses not compared: %s", type(exc).__name__)
        return None
    changes = [{"theme": r["theme"], "status": r["status"],
                "status_prior": r["prior_status"], "data_quality_warning": None}
               for r in rows]
    return nc.rotation_shift(theme_changes=changes)


async def _log_candidates(conn, candidates, *, session_date: _dt.date,
                          now_et: _dt.datetime) -> None:
    """Append every candidate, shown or dropped. A failed append costs the record, not the
    display -- the cards are already decided by the time this runs."""
    for card, verdict in candidates:
        try:
            row = nlog.row_for(
                session_date=session_date,
                detected_at=now_et,
                card_kind=card["card_kind"],
                ticker=card.get("ticker"),
                shown=bool(verdict.get("shown")),
                drop_reason=(None if verdict.get("shown")
                             else (verdict.get("drop_reason")
                                   or nlog.DROP_NOT_IN_UNIVERSE)),
                direction=card.get("direction"),
                reasons=card.get("reasons"),
                counter_evidence=card.get("counter_evidence"),
                stale_if=card.get("stale_if"),
                inputs={k: card.get(k) for k in
                        ("close", "level", "side", "move_pct", "atr_multiple", "basis",
                         "level_kind", "stack_class", "stack_prior", "event")
                        if card.get(k) is not None},
                strip_state=STRIP_NOT_WIRED)
        except ValueError as exc:
            logger.warning("[notables] candidate not logged (%s): %s", exc, card.get("ticker"))
            continue
        await nlog.insert(conn, row)
