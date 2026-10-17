"""The v1 regime job: read bars, classify the settled close, write one append-only snapshot.

R-IV.1195(b) wires v1 live. This module is the only part that touches the database, so every
rule in §2 stays testable without one.

WHY THE SEED RUNS FROM HERE AND NOT FROM MY LANE. The backfill needs a bar SERIES.
`hub_get_chart_indicators` serves only the newest reading, there is no bar-series route,
R-IV.552(b) forbids direct SQL, and jobs have no HTTP trigger. `stable_daily_bars` is readable
from inside the app and nowhere else, which is why R-IV.1193(d)'s seed count could only be
reported as "computable" until this shipped.

SETTLED CLOSES ONLY, and the check is not this module's opinion. `market_calendar.is_session_settled`
already owns that question (R-IV.1176) and returns three states, so "could not tell" is not
read as "yes".

A REFUSAL IS A ROW. Every run writes to `regime_audit`, including the runs that write no
snapshot. A nightly job that skipped a session silently is the R-IV.1175 fault, and the only way
to tell "it ran and declined" from "it never ran" is for the decline to leave a mark.

DISPLAY ONLY (#42). Nothing gates on what this writes.
"""

from __future__ import annotations

import logging
from datetime import date as _date
from typing import Any, Dict, List, Optional

from jobs.regime_seed import as_date, replay, seed, seed_depth_report
from models.regime_classifier import load_rules
from models.regime_inputs import INDICES, MIN_BARS, SECTORS, Bar, sessions_from_series

logger = logging.getLogger("regime_job")

#: Enough history for the deepest §2 lookback (a 200dma) plus the seed window on top.
BARS_TO_LOAD = 520


#: The indices plus the eleven sector ETFs. The sectors are what make SECTION 2's Uptrend and
#: Melt-up rows answerable at all: without them a steady uptrend classified as NO LABEL, which
#: a synthetic-series dry run surfaced before this shipped.
LOAD_TICKERS = tuple(INDICES) + tuple(SECTORS)


async def load_series(conn, tickers=LOAD_TICKERS, limit: int = BARS_TO_LOAD) -> Dict[str, List[Bar]]:
    """Oldest-first daily bars per ticker from `stable_daily_bars`.

    Ordered ASC in the query rather than reversed afterwards, because the vendor-order landmine
    in this repo (`fetch_crypto_ohlc` returning descending bars into positional slices) came from
    exactly that assumption being made silently somewhere else.
    """
    out: Dict[str, List[Bar]] = {}
    for t in tickers:
        rows = await conn.fetch(
            """SELECT date, o, h, l, c, v
                 FROM stable_daily_bars
                WHERE ticker = $1
                ORDER BY date DESC
                LIMIT $2""", t, int(limit))
        out[t] = [Bar.from_row(r) for r in reversed(rows)]
    return out


async def _audit(conn, *, action: str, detail: str, as_of=None, rows_written: int = 0,
                 rules_version: Optional[str] = None) -> None:
    try:
        await conn.execute(
            """INSERT INTO regime_audit (as_of, rules_version, action, detail, rows_written)
               VALUES ($1, $2, $3, $4, $5)""",
            as_date(as_of), rules_version, action, detail[:2000], int(rows_written))
    except Exception as exc:          # an audit failure must not take the job down with it
        logger.warning("[regime_job] audit write failed (%s): %s", action, type(exc).__name__)


async def run_seed(conn, rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Backfill the label history by replaying the classifier over every classifiable session.

    Returns the depth report plus `written`. Idempotent: a second run writes nothing because of
    the unique key, and says so rather than reporting a fresh success.
    """
    rules = rules or load_rules()
    # THE LOAD CAN FAIL, and a raised exception is an absence again. Audited so the one thing a
    # reader can see -- "no snapshot" -- comes with the reason attached.
    try:
        series = await load_series(conn)
    except Exception as exc:
        detail = "load_series failed: %s: %s" % (type(exc).__name__, exc)
        await _audit(conn, action="refused", detail=detail, rules_version=rules.get("version"))
        logger.warning("[regime_job] seed refused -- %s", detail)
        return {"sessions": 0, "written": 0, "refused": detail}

    counts = {t: len(v) for t, v in series.items()}
    report = seed_depth_report(counts)
    # The per-ticker counts go into the audit detail either way: when the seed refuses, the bar
    # counts ARE the diagnosis, and nothing else in this lane can read that table.
    report = dict(report, bar_counts=counts)

    if report["sessions"] <= 0:
        detail = ("no classifiable session: %s | bars: %s"
                  % (report["reason"], sorted(counts.items())))
        await _audit(conn, action="refused", detail=detail,
                     rules_version=rules.get("version"))
        logger.warning("[regime_job] seed refused -- %s", detail)
        return dict(report, written=0, refused=detail)

    # BOUNDED BY THE CALENDAR, not by what the bar table happens to hold. Left unbounded,
    # `sessions_from_series` marks every session settled -- including today's bar if a
    # provisional snapshot wrote one -- and the seed would stamp an unsettled close as settled,
    # which is the R-IV.1176 fault committed by the thing meant to avoid it.
    from stable_engine.market_calendar import CalendarHorizonError, last_settled_session
    try:
        through = last_settled_session().isoformat()
    except CalendarHorizonError as exc:
        detail = "cannot establish the last settled session (%s)" % exc
        await _audit(conn, action="refused", detail=detail, rules_version=rules.get("version"))
        return dict(report, written=0, refused=detail)

    sessions = sessions_from_series(series, settled_through=through)
    # A WRITE FAILURE IS AUDITED TOO. The first live seed raised inside the INSERT -- an ISO
    # string handed to a DATE column -- and because only the REFUSAL paths audited, it left no
    # row at all: the route could say "no snapshot" and nothing could say why. Finding that
    # needed a dig through deploy logs, which is exactly what the audit table exists to avoid.
    try:
        out = await seed(conn, sessions, rules, seeded=True)
    except Exception as exc:
        detail = ("seed write failed after %d session(s) replayed: %s: %s"
                  % (len(sessions), type(exc).__name__, exc))
        await _audit(conn, action="refused", detail=detail, rules_version=rules.get("version"))
        logger.error("[regime_job] %s", detail)
        return dict(report, written=0, refused=detail)
    detail = ("seeded %d of %d classifiable session(s); %d already present; %d flip(s); %s"
              % (out["written"], report["sessions"], out.get("conflicts", 0), out["flips"],
                 report["reason"]))
    await _audit(conn, action="seed", detail=detail, rows_written=out["written"],
                 rules_version=rules.get("version"),
                 as_of=(sessions[-1]["as_of"] if sessions else None))
    logger.info("[regime_job] %s", detail)
    return dict(report, **out)


async def run_nightly(conn, session_date: Optional[_date] = None,
                      rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Classify ONE settled session and write its snapshot.

    The hysteresis state comes from the stored series, not from memory: this job runs in a
    process that may have just started, and a hysteresis that held its own state would reset its
    counters on every deploy and let a one-session blip through.
    """
    rules = rules or load_rules()
    version = rules.get("version")

    from stable_engine.market_calendar import is_session_settled, settlement_reason

    target = session_date
    series = await load_series(conn)
    spy = series.get("SPY") or []
    if not spy:
        detail = "no SPY bars in stable_daily_bars"
        await _audit(conn, action="refused", detail=detail, rules_version=version)
        return {"written": 0, "refused": detail}

    if target is None:
        newest = spy[-1].date
        target = newest if isinstance(newest, _date) else _date.fromisoformat(str(newest)[:10])

    settled = is_session_settled(target)
    if settled is not True:
        # None means "not a trading day, or past the horizon" -- NOT "yes". R-IV.1176.
        detail = ("refused: %s (is_session_settled=%r)"
                  % (settlement_reason(target), settled))
        await _audit(conn, action="refused", detail=detail, as_of=target, rules_version=version)
        logger.info("[regime_job] nightly %s", detail)
        return {"written": 0, "refused": detail, "as_of": target.isoformat()}

    sessions = sessions_from_series(series, settled_through=target.isoformat())
    if not sessions:
        detail = ("no classifiable session: SPY holds %d bar(s), %d needed"
                  % (len(spy), MIN_BARS))
        await _audit(conn, action="refused", detail=detail, as_of=target, rules_version=version)
        return {"written": 0, "refused": detail, "as_of": target.isoformat()}

    out = replay(sessions, rules)
    # Only the target session is written. The earlier ones were replayed to rebuild the
    # hysteresis state and are already stored (or will be, by the seed).
    row = next((r for r in out["shown"] if r.get("as_of") == target.isoformat()), None)
    if row is None:
        detail = "replay produced no row for %s" % target.isoformat()
        await _audit(conn, action="refused", detail=detail, as_of=target, rules_version=version)
        return {"written": 0, "refused": detail, "as_of": target.isoformat()}

    from jobs.regime_seed import _write_snapshot
    r = await _write_snapshot(conn, row, seeded=False)
    if r is None:
        detail = ("%s already has a %s row; append-only, so nothing was rewritten "
                  "(this run would have said: %s)"
                  % (target.isoformat(), version, row.get("shown_regime")))
        await _audit(conn, action="conflict", detail=detail, as_of=target, rules_version=version)
        logger.info("[regime_job] nightly %s", detail)
        return {"written": 0, "conflict": detail, "as_of": target.isoformat(),
                "shown_regime": row.get("shown_regime")}

    detail = ("%s -> %s (raw %s)%s%s"
              % (target.isoformat(), row.get("shown_regime"), row.get("regime"),
                 "; " + row["change"] if row.get("change") else "",
                 "; " + row["blocked"] if row.get("blocked") else ""))
    await _audit(conn, action="nightly", detail=detail, as_of=target, rows_written=1,
                 rules_version=version)
    logger.info("[regime_job] nightly %s", detail)
    return {"written": 1, "as_of": target.isoformat(), "shown_regime": row.get("shown_regime"),
            "regime": row.get("regime"), "label": row.get("label"),
            "tags": row.get("tags"), "basis": row.get("basis"),
            "change": row.get("change"), "blocked": row.get("blocked")}


async def latest_with_diff(conn, rules_version: Optional[str] = None) -> Dict[str, Any]:
    """The newest snapshot plus the SINCE-YESTERDAY diff (R-IV.1195(b)).

    "Yesterday" is the PREVIOUS STORED SESSION, not `as_of - 1 day`. A calendar day before a
    Monday is a Sunday, which has no label, and a diff against a session that does not exist
    would report every Monday as a change.
    """
    version = rules_version or load_rules().get("version")
    rows = await conn.fetch(
        # `inputs_json` IS IN THE LIST, and was missing from the first live version. The column
        # held the numbers all along; the query did not ask for them, so the card's index strip
        # came back empty and every evidence family reported "no feed in v1" -- a caption
        # asserting an absence that was not real, about two families that do have a feed.
        """SELECT as_of, regime, shown_regime, label, tags, basis, not_evaluable,
                  pending, pending_closes, held_sessions, change, blocked, seeded,
                  inputs_json, created_at
             FROM regime_snapshots
            WHERE rules_version = $1
            ORDER BY as_of DESC
            LIMIT 2""", version)
    if not rows:
        # THE AUDIT ROW IS THE ANSWER TO "WHY NOT". "No snapshot" is a symptom; the run that
        # declined to write one recorded its reason, and surfacing it here is the whole point of
        # auditing refusals rather than letting them be an absence.
        why = "no regime_snapshots row for rules %s" % version
        try:
            a = await conn.fetchrow(
                """SELECT action, detail, created_at FROM regime_audit
                    ORDER BY created_at DESC LIMIT 1""")
            if a is not None:
                why = "%s; last run: %s - %s" % (why, a["action"], a["detail"])
        except Exception as exc:
            why = "%s; regime_audit unreadable (%s)" % (why, type(exc).__name__)
        return {"snapshot": None, "diff": None, "unavailable_reason": why}

    cur = dict(rows[0])
    prev = dict(rows[1]) if len(rows) > 1 else None
    cur["as_of"] = str(cur["as_of"])[:10]
    if prev:
        prev["as_of"] = str(prev["as_of"])[:10]

    if prev is None:
        diff = {"changed": None, "detail": "no previous session stored yet",
                "previous_as_of": None}
    else:
        changed = cur.get("shown_regime") != prev.get("shown_regime")
        gained = sorted(set(cur.get("tags") or []) - set(prev.get("tags") or []))
        lost = sorted(set(prev.get("tags") or []) - set(cur.get("tags") or []))
        parts = []
        if changed:
            parts.append("%s -> %s" % (prev.get("shown_regime"), cur.get("shown_regime")))
        if gained:
            parts.append("+" + ", +".join(gained))
        if lost:
            parts.append("-" + ", -".join(lost))
        diff = {
            "changed": bool(changed),
            "previous_as_of": prev["as_of"],
            "previous_shown_regime": prev.get("shown_regime"),
            "tags_gained": gained,
            "tags_lost": lost,
            "detail": "; ".join(parts) if parts else "no change since %s" % prev["as_of"],
        }
    return {"snapshot": cur, "diff": diff, "rules_version": version}


async def health(conn, rules_version: Optional[str] = None) -> Dict[str, Any]:
    """Health states for the card (R-IV.1195(b)).

    THREE STATES, not two. `stale` is its own answer because a label from eight sessions ago
    served as current is worse than no label: a reader cannot tell the difference, and the
    screen looks healthy either way. That is the fault class this lane has paid for repeatedly.
    """
    version = rules_version or load_rules().get("version")
    try:
        row = await conn.fetchrow(
            """SELECT as_of, shown_regime, settled, created_at
                 FROM regime_snapshots
                WHERE rules_version = $1
                ORDER BY as_of DESC LIMIT 1""", version)
    except Exception as exc:
        return {"state": "unavailable", "reason": "regime_snapshots unreadable (%s)"
                % type(exc).__name__, "as_of": None}

    if row is None:
        return {"state": "unavailable",
                "reason": "no snapshot for rules %s; the seed has not run" % version,
                "as_of": None}

    as_of = row["as_of"]
    as_of_d = as_of if isinstance(as_of, _date) else _date.fromisoformat(str(as_of)[:10])

    from stable_engine.market_calendar import CalendarHorizonError, last_settled_session
    try:
        newest_settled = last_settled_session()
    except CalendarHorizonError as exc:
        return {"state": "unavailable", "as_of": as_of_d.isoformat(),
                "reason": "cannot establish the last settled session (%s)" % exc}

    # LAG IN TRADING DAYS, not calendar days. A Friday label read on Monday is ONE session
    # behind, not three, and a threshold stated in calendar days would call every ordinary
    # Monday stale and every long weekend dead.
    from stable_engine.market_calendar import trading_days_between
    try:
        lag = max(0, trading_days_between(as_of_d, newest_settled))
    except Exception:
        lag = max(0, (newest_settled - as_of_d).days)

    if as_of_d >= newest_settled:
        state, reason = "current", ("labelled through the last settled session (%s)"
                                    % newest_settled.isoformat())
    elif lag <= 1:
        state, reason = "stale", ("1 session behind the last settled session (%s); the nightly "
                                  "job has not run for it yet" % newest_settled.isoformat())
    else:
        state, reason = "dead", ("%d session(s) behind the last settled session (%s)"
                                 % (lag, newest_settled.isoformat()))
    return {"state": state, "reason": reason, "as_of": as_of_d.isoformat(),
            "last_settled_session": newest_settled.isoformat(), "lag_sessions": lag,
            "shown_regime": row["shown_regime"], "rules_version": version}
