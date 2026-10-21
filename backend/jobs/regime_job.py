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

import json
import logging
import re
from datetime import date as _date
from typing import Any, Dict, List, Optional

from jobs.regime_seed import as_date, replay, seed, seed_depth_report
from models.regime_classifier import load_rules
from models.regime_inputs import INDICES, MIN_BARS, SECTORS, Bar, sessions_from_series

logger = logging.getLogger("regime_job")

#: The designated settled-close source (R-IV.1198(d), wired by R-IV.1203(b)). Stamped on
#: every snapshot this job writes, and part of the unique key.
CLOSE_SOURCE = "polygon"

#: Enough history for the deepest §2 lookback (a 200dma) plus the seed window on top.
BARS_TO_LOAD = 520


#: The indices plus the eleven sector ETFs. The sectors are what make SECTION 2's Uptrend and
#: Melt-up rows answerable at all: without them a steady uptrend classified as NO LABEL, which
#: a synthetic-series dry run surfaced before this shipped.
LOAD_TICKERS = tuple(INDICES) + tuple(SECTORS)


async def load_designated_series(conn, tickers=LOAD_TICKERS,
                                 limit: int = BARS_TO_LOAD) -> Dict[str, List[Bar]]:
    """The DESIGNATED settled-close series (R-IV.1203(b)): Polygon, from `regime_daily_bars`.

    One switch point, called by both the seed and the nightly, so the two cannot end up reading
    different sources -- which is how a seeded history and a live label come to disagree with
    nothing reporting it.

    THE SECTOR BREADTH STILL COMES FROM `stable_daily_bars`, deliberately. §2's Uptrend row
    needs eleven sector ETFs above their 50dma, that is a MOVING-AVERAGE question, and
    R-IV.1203(c) rules the fully-adjusted basis correct for moving averages and breadth. Only
    the settled CLOSE had to move. Each source is used for the thing it is right for, and the
    returned dict says which is which.
    """
    from stable_engine import bars_polygon

    out: Dict[str, List[Bar]] = {}
    index_tickers = [t for t in tickers if t in INDICES]
    other = [t for t in tickers if t not in INDICES]
    if index_tickers:
        out.update(await bars_polygon.load_series(conn, index_tickers, limit))
    if other:
        out.update(await _load_adjusted_series(conn, other, limit))
    return out


async def _load_adjusted_series(conn, tickers, limit: int = BARS_TO_LOAD) -> Dict[str, List[Bar]]:
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


async def label_diff(conn, rules_version: Optional[str] = None) -> Dict[str, Any]:
    """Where the new seed's shown label differs from the superseded one, as a list of dates.

    R-IV.1203(b)2 asks for exactly this. Joined on the SESSION, so a date present in only one
    seed is reported as such rather than counted as a difference: the two series cover different
    spans (stable_daily_bars reached 321 sessions, Polygon's entitlement 302), and treating a
    missing session as a changed label would inflate the count with arithmetic.
    """
    version = rules_version or load_rules().get("version")
    try:
        # BOTH as_of COLUMNS ARE SELECTED, not COALESCEd into one. `shown_regime` is
        # legitimately NULL on a session before the first label qualified, so a NULL label
        # cannot distinguish "no row in that seed" from "a row with no label yet". The join
        # key can: when a side contributed no row, that side's as_of is NULL.
        rows = await conn.fetch(
            """SELECT o.as_of AS old_as_of, n.as_of AS new_as_of,
                      o.shown_regime AS old_shown,
                      n.shown_regime AS new_shown
                 FROM (SELECT as_of, shown_regime FROM regime_snapshots
                        WHERE rules_version = $1 AND superseded = TRUE) o
                 FULL OUTER JOIN
                      (SELECT as_of, shown_regime FROM regime_snapshots
                        WHERE rules_version = $1 AND superseded = FALSE) n
                   ON o.as_of = n.as_of
                ORDER BY COALESCE(n.as_of, o.as_of) ASC""", version)
    except Exception as exc:
        return {"error": "regime_snapshots unreadable (%s)" % type(exc).__name__}

    changed, only_old, only_new, same = [], [], [], 0
    for r in rows:
        in_old = r["old_as_of"] is not None
        in_new = r["new_as_of"] is not None
        day = str(r["new_as_of"] or r["old_as_of"])[:10]
        # A session in only ONE seed is a SPAN difference, not a label change. The two series
        # cover different spans (stable_daily_bars reached 321 sessions, Polygon's entitlement
        # 302), and counting a missing session as a changed label would inflate the answer with
        # arithmetic rather than with findings.
        if in_new and not in_old:
            only_new.append(day)
        elif in_old and not in_new:
            only_old.append(day)
        elif r["old_shown"] != r["new_shown"]:
            changed.append({"as_of": day, "old": r["old_shown"], "new": r["new_shown"]})
        else:
            same += 1
    return {
        "changed": changed,
        "changed_count": len(changed),
        "changed_dates": [c["as_of"] for c in changed],
        "unchanged_count": same,
        "sessions_only_in_old_seed": only_old,
        "sessions_only_in_new_seed": only_new,
        "overlap": len(changed) + same,
    }


async def run_seed(conn, rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Backfill the label history by replaying the classifier over every classifiable session.

    Returns the depth report plus `written`. Idempotent: a second run writes nothing because of
    the unique key, and says so rather than reporting a fresh success.
    """
    rules = rules or load_rules()

    # THE SERIES IS FETCHED BEFORE IT IS READ. R-IV.1203(b)1-2: the seed replays the DESIGNATED
    # source, and on a first run `regime_daily_bars` is empty -- so the backfill happens here
    # rather than being a step someone has to remember. Idempotent: the bar store upserts, so a
    # re-run refreshes the same rows instead of multiplying them.
    try:
        from stable_engine import bars_polygon
        have_bars = await conn.fetchval(
            "SELECT COUNT(*) FROM regime_daily_bars WHERE close_source = $1",
            bars_polygon.SOURCE)
        if not have_bars:
            bf = await bars_polygon.backfill(conn, INDICES)
            logger.info("[regime_job] polygon backfill wrote %s bar(s): %s",
                        bf.get("written"), bf.get("per_ticker"))
            await _audit(conn, action="backfill",
                         detail=("polygon backfill: %s" % json.dumps(bf.get("per_ticker") or {})),
                         rows_written=int(bf.get("written") or 0),
                         rules_version=rules.get("version"))
    except Exception as exc:
        detail = "polygon backfill failed: %s: %s" % (type(exc).__name__, exc)
        await _audit(conn, action="refused", detail=detail, rules_version=rules.get("version"))
        logger.error("[regime_job] %s", detail)
        return {"sessions": 0, "written": 0, "refused": detail}

    # THE LOAD CAN FAIL, and a raised exception is an absence again. Audited so the one thing a
    # reader can see -- "no snapshot" -- comes with the reason attached.
    try:
        series = await load_designated_series(conn)
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

    # R-IV.1260(c): v2 fills the inputs the v1 rows already read. The VIX pair is fetched
    # ONCE for the whole replay and passed in by date, because the CRASH row needs both legs
    # on the same session and a per-session fetch would be 302 calls for one series.
    # `uses_v2_inputs`, NOT `== "v2"`. R-IV.1284(c): the literal comparison is False for
    # "v2.1", so the cutover would have stopped building the v2 inputs and reading the VIX pair
    # without saying anything -- and 95 of 304 sessions take a different label on that basis.
    vix_by_date, vix_report = {}, {"skipped": "rules %s does not read the VIX pair"
                                              % rules.get("version")}
    if uses_v2_inputs(rules.get("version")):
        from models.regime_vix import by_date as _vix_by_date

        vix_by_date, vix_report = _vix_by_date()
        await _audit(conn, action="vix_source",
                     detail=json.dumps(vix_report)[:1900],
                     rules_version=rules.get("version"))
    # AUDITED, because the first v2 deploy failed HERE and said nothing. `vix_source` was the
    # last action on the record, and the route could report only "no row for rules v2" — the
    # reason lived in a deploy log. An exception in the session build propagates to the startup
    # task's own except, which logs a warning and writes NO audit row, so the one table that
    # exists to answer "why is there no snapshot" was silent about the only step that failed.
    try:
        sessions = sessions_from_series(series, settled_through=through,
                                        vix_by_date=vix_by_date,
                                        v2=uses_v2_inputs(rules.get("version")))
    except Exception as exc:                                        # noqa: BLE001
        detail = "session build failed: %s: %s" % (type(exc).__name__, exc)
        await _audit(conn, action="refused", detail=detail,
                     rules_version=rules.get("version"))
        logger.error("[regime_job] %s", detail)
        return dict(report, written=0, refused=detail)
    await _audit(conn, action="sessions_built",
                 detail="%d session(s) built for rules %s (v2 inputs: %s, vix dates: %d)"
                        % (len(sessions), rules.get("version"),
                           # The same test the build used. A literal `== "v2"` here would have
                           # AUDITED "v2 inputs: False" on a run that built them, or the
                           # reverse -- an audit row that disagrees with the run it describes
                           # is worse than none, because it is the record a later reader trusts.
                           uses_v2_inputs(rules.get("version")), len(vix_by_date)),
                 rows_written=len(sessions), rules_version=rules.get("version"))
    # A WRITE FAILURE IS AUDITED TOO. The first live seed raised inside the INSERT -- an ISO
    # string handed to a DATE column -- and because only the REFUSAL paths audited, it left no
    # row at all: the route could say "no snapshot" and nothing could say why. Finding that
    # needed a dig through deploy logs, which is exactly what the audit table exists to avoid.
    try:
        out = await seed(conn, sessions, rules, seeded=True, close_source=CLOSE_SOURCE)
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

    # THE TARGET COMES FROM THE CALENDAR, NOT FROM THE BAR TABLE. It used to be the newest
    # stored bar's date, and that breaks the moment the capture below exists: on a nightly run
    # the newest STORED bar is yesterday's, because today's is what this run is about to fetch.
    # The job would have targeted yesterday every single night and never captured a session.
    target = session_date
    if target is None:
        from stable_engine.market_calendar import CalendarHorizonError, last_settled_session
        try:
            target = last_settled_session()
        except CalendarHorizonError as exc:
            detail = "cannot establish the last settled session (%s)" % exc
            await _audit(conn, action="refused", detail=detail, rules_version=version)
            return {"written": 0, "refused": detail}

    # CAPTURE THE SESSION FROM THE DESIGNATED SOURCE FIRST, VERIFIED (R-IV.1203(b)1).
    # The bar has to exist and agree with the UW chart close before any label is computed from
    # it. A mismatch writes nothing and reports DEGRADED -- and the label step then declines
    # too, because labelling an unverified close is the fault this whole ruling is about.
    capture: Dict[str, Any] = {}
    try:
        from stable_engine import bars_polygon
        capture = await bars_polygon.capture_session(conn, target, INDICES)
    except Exception as exc:
        capture = {"degraded": True, "written": 0,
                   "reason": "capture raised: %s: %s" % (type(exc).__name__, exc)}

    # R-IV.1278(b)3: A SESSION THE SOURCE WILL NOT SERVE YET MUST NOT COST THE NIGHT.
    #
    # MEASURED: the nightly ran on both 2026-10-19 (01:31:09Z) and 2026-10-20 (01:33:33Z),
    # asked Polygon for that day's bar at ~21:31 ET, and was refused on all three tickers. On
    # this plan a session is withheld while it is still current -- 5.5 hours after the close is
    # not late enough -- so the target the CALENDAR calls settled is a session the SOURCE does
    # not have. Two nights of audit rows read "DEGRADED, no label written: SPY: HTTP 403" and
    # the card went on showing 10-16 with nothing said.
    #
    # So when the target's bar is unavailable, the run FALLS BACK to the newest settled session
    # that HAS a bar and HAS NO LABEL, and writes that instead. The withheld session is
    # reported as PENDING, not as a failure: it will be served tomorrow, and tomorrow's run
    # will label it. A one-session lag is this plan's entitlement edge and is a fact about the
    # data, not a fault -- which is exactly what (b)4's freshness rule exists to say out loud.
    if capture.get("degraded"):
        pending = target
        fallback = await _newest_labelable_session(conn, version, before=target)
        if fallback is None:
            detail = ("DEGRADED, no label written: %s (and no earlier settled session is "
                      "unlabelled, so there was nothing to fall back to)"
                      % capture.get("reason"))
            await _audit(conn, action="degraded", detail=detail, as_of=target,
                         rules_version=version)
            logger.error("[regime_job] nightly %s", detail)
            return {"written": 0, "degraded": True, "reason": capture.get("reason"),
                    "as_of": target.isoformat(), "pending": pending.isoformat()}
        detail = ("%s is not served yet (%s); falling back to %s, which has a bar and no label"
                  % (pending.isoformat(), capture.get("reason"), fallback.isoformat()))
        await _audit(conn, action="pending_source", detail=detail, as_of=pending,
                     rules_version=version)
        logger.warning("[regime_job] nightly %s", detail)
        target = fallback
        capture = {"degraded": False, "written": 0, "skipped": True,
                   "reason": "bar already stored for %s" % fallback.isoformat()}

    settled = is_session_settled(target)
    if settled is not True:
        # None means "not a trading day, or past the horizon" -- NOT "yes". R-IV.1176.
        detail = ("refused: %s (is_session_settled=%r)"
                  % (settlement_reason(target), settled))
        await _audit(conn, action="refused", detail=detail, as_of=target, rules_version=version)
        logger.info("[regime_job] nightly %s", detail)
        return {"written": 0, "refused": detail, "as_of": target.isoformat()}

    # READ AFTER THE CAPTURE, so the series includes the session just verified and written.
    series = await load_designated_series(conn)
    spy = series.get("SPY") or []
    if not spy:
        detail = "no SPY bars in regime_daily_bars after the capture"
        await _audit(conn, action="refused", detail=detail, as_of=target,
                    rules_version=version)
        return {"written": 0, "refused": detail, "as_of": target.isoformat()}

    # THE CUTOVER GATE (TA-208 item 7 / R-IV.1288(c)). On the FIRST run under a new rules
    # version the starting hysteresis state is inherited from its predecessor -- verified, not
    # copied -- and if the new version disputes that state the job DECLINES and says so rather
    # than seeding or backfilling. Checked before any label is computed, because a run that
    # cannot legitimately start must not write one.
    gate = await cutover_state(conn, str(version), rules=rules)
    if not gate.get("ok"):
        detail = "cutover blocked: %s" % gate.get("reason")
        await _audit(conn, action="cutover_blocked", detail=detail, as_of=target,
                     rules_version=version)
        logger.error("[regime_job] nightly %s", detail)
        return {"written": 0, "needs_ruling": True, "reason": gate.get("reason"),
                "as_of": target.isoformat()}
    if gate.get("inherited"):
        await _audit(conn, action="cutover", detail=gate.get("reason"), as_of=target,
                     rules_version=version)
        logger.info("[regime_job] %s", gate.get("reason"))

    # THE SAME BUILD THE SEED USES (R-IV.1284(c) / TA-208 item 7). This line used to be a bare
    # `sessions_from_series(series, settled_through=...)`, so `v2` defaulted to False and no VIX
    # pair was passed -- 95 of 304 sessions take a different label on that basis, and a cutover
    # that "inherits v2's state and runs nightly from there" would have inherited a state built
    # one way and continued it another.
    sessions, build = await build_sessions(conn, series, rules=rules,
                                           settled_through=target.isoformat())
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
    r = await _write_snapshot(conn, row, seeded=False, close_source=CLOSE_SOURCE)
    if r is None:
        detail = ("%s already has a %s row; append-only, so nothing was rewritten "
                  "(this run would have said: %s)"
                  % (target.isoformat(), version, row.get("shown_regime")))
        await _audit(conn, action="conflict", detail=detail, as_of=target, rules_version=version)
        logger.info("[regime_job] nightly %s", detail)
        return {"written": 0, "conflict": detail, "as_of": target.isoformat(),
                "shown_regime": row.get("shown_regime")}

    # THE BASIS GOES ON THE RECORD WITH THE LABEL. Whether the v2 inputs were built, and how
    # many VIX dates were paired, decide which rows were evaluable -- so a later reader of this
    # row can tell what it was computed from instead of assuming.
    detail = ("%s -> %s (raw %s)%s%s [v2_inputs=%s vix=%s]"
              % (target.isoformat(), row.get("shown_regime"), row.get("regime"),
                 "; " + row["change"] if row.get("change") else "",
                 "; " + row["blocked"] if row.get("blocked") else "",
                 build.get("v2_inputs"),
                 (build.get("vix") or {}).get("paired_dates",
                                              (build.get("vix") or {}).get("error", "n/a"))))
    await _audit(conn, action="nightly", detail=detail, as_of=target, rows_written=1,
                 rules_version=version)
    logger.info("[regime_job] nightly %s", detail)
    return {"written": 1, "as_of": target.isoformat(), "shown_regime": row.get("shown_regime"),
            "regime": row.get("regime"), "label": row.get("label"),
            "tags": row.get("tags"), "basis": row.get("basis"),
            "change": row.get("change"), "blocked": row.get("blocked")}


async def _newest_labelable_session(conn, version: Optional[str], *,
                                    before) -> Optional[Any]:
    """The newest session that HAS a designated bar and NO label, strictly before `before`.

    R-IV.1278(b)3's fallback. Both halves are required and for different reasons:
      * a bar must exist, or the classifier would be asked to label a session it cannot read;
      * a label must NOT exist, because `regime_snapshots` is append-only -- targeting a
        session that already has one would only produce a `conflict` audit row, which is a
        quieter way of doing nothing.

    SPY's series decides, because SPY is the shortest and the 200dma warm-up is measured on it;
    a session QQQ has and SPY does not is not classifiable.
    """
    row = await conn.fetchrow(
        """SELECT b.date
             FROM regime_daily_bars b
            WHERE b.ticker = 'SPY'
              AND b.close_source = $1
              AND b.date < $2
              AND NOT EXISTS (
                    SELECT 1 FROM regime_snapshots s
                     WHERE s.as_of = b.date
                       AND s.rules_version = $3
                       AND s.superseded = FALSE)
            ORDER BY b.date DESC
            LIMIT 1""", CLOSE_SOURCE, before, version)
    return row["date"] if row else None


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
            WHERE rules_version = $1 AND superseded = FALSE
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


#: §2's design target for label churn. R-IV.1198(c) rules NO threshold or hysteresis change on
#: the observed rate -- tuning on observed flips is a fitted parameter wearing a rule's name --
#: so this is recorded as a known gap and nothing adjusts itself to meet it.
FLIPS_PER_YEAR_TARGET = 6
SESSIONS_PER_YEAR = 252


def _closes_from_change(change: Optional[str]) -> Optional[int]:
    """The qualifying close count out of the hysteresis's own `change` sentence.

    Both forms it writes end in "after N closes": "first label after 2 closes" and
    "correction -> uptrend after 2 closes (toward risk, ...)". Returns None rather than a
    guess if the sentence ever stops carrying it, so a changed wording shows as missing data
    instead of a plausible number.
    """
    if not change:
        return None
    m = re.search(r"after (\d+) closes?", change)
    return int(m.group(1)) if m else None


async def flip_history(conn, rules_version: Optional[str] = None) -> Dict[str, Any]:
    """Every session where the shown label changed, oldest-first, with the rate beside it.

    R-IV.1198(c) asks for the list so a reader can see whether the flips are real regime changes
    or chatter between two neighbouring labels. That question needs the FROM and the TO adjacent
    in §2's bear-to-bull order, which is why `from_index`/`to_index`/`neighbours` are published:
    a Correction/Narrow-uptrend pair sitting one step apart is a different fact from a
    Bear/Melt-up pair sitting six apart, and the count alone cannot tell them apart.
    """
    version = rules_version or load_rules().get("version")
    order = list((load_rules().get("order") or []))
    try:
        rows = await conn.fetch(
            """SELECT as_of, shown_regime, regime, change, blocked,
                      pending_closes, held_sessions, tags
                 FROM regime_snapshots
                WHERE rules_version = $1 AND change IS NOT NULL AND superseded = FALSE
                ORDER BY as_of ASC""", version)
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM regime_snapshots WHERE rules_version = $1 "
            "AND superseded = FALSE", version)
    except Exception as exc:
        return {"flips": [], "error": "regime_snapshots unreadable (%s)" % type(exc).__name__}

    flips = []
    prev: Optional[str] = None
    pair_counts: Dict[str, int] = {}
    for r in rows:
        to = r["shown_regime"]
        fi = order.index(prev) if prev in order else None
        ti = order.index(to) if to in order else None
        pair = ("%s<->%s" % tuple(sorted([prev or "(none)", to or "(none)"])))
        pair_counts[pair] = pair_counts.get(pair, 0) + 1
        flips.append({
            "as_of": str(r["as_of"])[:10],
            "from": prev,
            "to": to,
            "from_index": fi,
            "to_index": ti,
            "steps": (abs(ti - fi) if fi is not None and ti is not None else None),
            "neighbours": (fi is not None and ti is not None and abs(ti - fi) == 1),
            "pair": pair,
            # READ FROM THE STORED `change` TEXT, which the hysteresis authored when it wrote
            # the row. `pending_closes` is NOT this number: the hysteresis zeroes it on the
            # session a change fires, so the stored value is 0 on every flip -- a column that
            # cannot vary, which is the vacuous-column fault (DEF-EDGE-SPEC-B2) in a new place.
            # Parsing the text is the ONE route for all 321 seeded rows, because the snapshots
            # are append-only and a column added now could never be filled for them.
            "closes_held": _closes_from_change(r["change"]),
            "held_sessions_before": r["held_sessions"],
            "change": r["change"],
        })
        prev = to

    sessions = int(total or 0)
    years = (sessions / SESSIONS_PER_YEAR) if sessions else None
    rate = (len(flips) / years) if years else None
    # PAIR IDENTITY, NOT ORDER DISTANCE, is what answers the ruling's question. §2's order puts
    # range_chop and melt_up between correction and uptrend, so a correction<->uptrend
    # oscillation scores 3 "steps" and reads as a real regime change -- while being the same
    # two labels trading places over and over, which is exactly the chatter being asked about.
    # The tape never passed through the labels in between, so the distance is an artefact of
    # the ordering rather than a fact about the market.
    repeated = {k: v for k, v in sorted(pair_counts.items(), key=lambda kv: -kv[1]) if v > 1}
    return {
        "flips": flips,
        "count": len(flips),
        "pair_counts": pair_counts,
        "repeated_pairs": repeated,
        "repeated_pair_flips": sum(repeated.values()),
        "sessions": sessions,
        "per_year": (round(rate, 1) if rate is not None else None),
        "design_target_per_year": FLIPS_PER_YEAR_TARGET,
        "known_gap": (
            None if rate is None or rate <= FLIPS_PER_YEAR_TARGET else
            ("observed ~%.0f/yr vs section 2's design target <=%d/yr -- recorded as a KNOWN GAP "
             "(R-IV.1198(c)): no threshold or hysteresis change, because tuning on observed "
             "flips is a fitted parameter wearing a rule's name"
             % (rate, FLIPS_PER_YEAR_TARGET))),
    }


async def record_known_gap(conn, rules_version: Optional[str] = None) -> Optional[str]:
    """Write the flip-rate gap to `regime_audit` once. R-IV.1198(c).

    Idempotent on the ACTION, not on the text: a second call finds the existing row and returns
    None rather than appending a near-duplicate every deploy. The rate moves as sessions
    accumulate, and a row per boot would bury the finding in its own restatements.
    """
    version = rules_version or load_rules().get("version")
    try:
        existing = await conn.fetchval(
            "SELECT id FROM regime_audit WHERE action = 'known_gap' LIMIT 1")
        if existing:
            return None
        hist = await flip_history(conn, version)
        if not hist.get("known_gap"):
            return None
        await _audit(conn, action="known_gap", detail=hist["known_gap"],
                     rules_version=version, rows_written=0)
        return hist["known_gap"]
    except Exception as exc:
        logger.warning("[regime_job] known_gap record failed: %s", type(exc).__name__)
        return None


async def record_interim_families(conn, rules_version: Optional[str] = None) -> Optional[str]:
    """Write the INTERIM status of the STRUCTURE and BREADTH tests to `regime_audit`. R-IV.1198(e).

    Ratified as interim, not as final: §2 names five families and states no per-family test, so
    these two reuse the Correction row's own clauses. Per-family tests get designed at the same
    review as the flip rate. Recorded in the audit so the status is on the record and not only
    in a comment.
    """
    version = rules_version or load_rules().get("version")
    try:
        existing = await conn.fetchval(
            "SELECT id FROM regime_audit WHERE action = 'interim_families' LIMIT 1")
        if existing:
            return None
        fam = load_rules().get("families_v1") or {}
        detail = ("INTERIM (ratified R-IV.1198(e)): STRUCTURE = %s; BREADTH = %s. "
                  "CREDIT/VOL/CARRY have no feed in v1. Per-family tests are designed at the "
                  "same review as the flip rate. Nothing gates on them (#42)."
                  % (fam.get("structure"), fam.get("breadth")))
        await _audit(conn, action="interim_families", detail=detail, rules_version=version)
        return detail
    except Exception as exc:
        logger.warning("[regime_job] interim_families record failed: %s", type(exc).__name__)
        return None


async def audit_notes(conn) -> Dict[str, Any]:
    """The standing notes on the record: the flip-rate known gap and the INTERIM family status.

    R-IV.1198(c) and (e) say to RECORD these. A record nobody can read is a weak record -- and
    checking that they were written at all meant grepping a deploy log that had already stopped
    carrying the line, which is the same problem the seed count had.
    """
    out: Dict[str, Any] = {}
    for action in ("known_gap", "interim_families"):
        try:
            r = await conn.fetchrow(
                """SELECT detail, created_at FROM regime_audit
                    WHERE action = $1 ORDER BY created_at DESC LIMIT 1""", action)
        except Exception as exc:
            out[action] = {"error": "regime_audit unreadable (%s)" % type(exc).__name__}
            continue
        out[action] = (None if r is None else
                       {"detail": r["detail"],
                        "at": r["created_at"].isoformat() if r["created_at"] else None})
    return out


async def seed_run(conn) -> Optional[Dict[str, Any]]:
    """The audit row for the run that seeded the history, if one exists.

    R-IV.1195(b) asks for "the seed count actually executed at deploy", and the first time I
    went looking for it the answer was only in a deploy log that had already rolled off. A
    number a ruling asks to be reported should be readable from the thing that produced it.
    """
    try:
        r = await conn.fetchrow(
            """SELECT as_of, action, detail, rows_written, created_at
                 FROM regime_audit
                WHERE action = 'seed'
                ORDER BY created_at DESC LIMIT 1""")
    except Exception as exc:
        return {"error": "regime_audit unreadable (%s)" % type(exc).__name__}
    if r is None:
        return None
    return {"sessions_written": r["rows_written"], "detail": r["detail"],
            "through": str(r["as_of"])[:10] if r["as_of"] else None,
            "at": r["created_at"].isoformat() if r["created_at"] else None}


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
                WHERE rules_version = $1 AND superseded = FALSE
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


#: Which rules versions build the V2 INPUTS and read the VIX pair. A SET, so a future version
#: has to opt in deliberately: the seed tested `== "v2"`, which is False for "v2.1", so a
#: cutover would silently have stopped building them.
V2_INPUT_VERSIONS = frozenset({"v2", "v2.1"})


def uses_v2_inputs(version: Optional[str]) -> bool:
    return str(version or "") in V2_INPUT_VERSIONS


async def build_sessions(conn, series, *, rules, settled_through: str):
    """The sessions list, built THE SAME WAY for the seed, the nightly and the repair.

    THE SEED AND THE NIGHTLY DISAGREED, and the card has been living with it since the v2
    cut-over. MEASURED over the stored series, 2026-10-21:

        the seed    sessions_from_series(..., vix_by_date=vix, v2=True)
        the nightly sessions_from_series(..., settled_through=...)      <- v2 defaults to False
        result      95 OF 304 SESSIONS take a different label depending on which build ran

    For 2026-10-19 and 10-20 the two disagree outright: the nightly's build says
    `correction / correction` and the seed's says `range_chop / correction`. So the 302 seeded
    rows and every nightly row after them were computed on DIFFERENT INPUTS by the same
    classifier -- two instruments measuring one thing, which is the fault class this board
    files most often, and here it reached the label on the screen.

    One function, three callers, so they cannot drift again. Returns (sessions, report) and the
    report names the VIX state, because an absent VIX pair changes which rows are evaluable and
    a reader of a label is entitled to know it was absent.
    """
    version = rules.get("version")
    vix_by_date: Dict[str, Any] = {}
    vix_report: Dict[str, Any] = {"skipped": "rules %s does not read the VIX pair" % version}
    if uses_v2_inputs(version):
        try:
            from models.regime_vix import by_date as _vix_by_date

            vix_by_date, vix_report = _vix_by_date()
        except Exception as exc:                                    # noqa: BLE001
            vix_by_date, vix_report = {}, {"error": type(exc).__name__}
    sessions = sessions_from_series(series, settled_through=settled_through,
                                    vix_by_date=vix_by_date,
                                    v2=uses_v2_inputs(version))
    return sessions, {"v2_inputs": uses_v2_inputs(version), "vix": vix_report,
                      "sessions": len(sessions)}


#: TA-208 §7's label groups, which must be THE SAME MAP LAB uses. Copied from
#: `scripts/lab/regime_filter.py::GROUPS` rather than re-derived: the card's wording and LAB's
#: scoring have to agree about which labels are bullish, or the same session reads one way on
#: the screen and another in a scorecard.
LABEL_GROUPS = {
    "TREND-UP": ("uptrend", "narrow_uptrend", "melt_up", "recovery"),
    "RANGE": ("range_chop", "correction"),
    "TREND-DOWN/STRESS": ("breakdown", "bear_market", "bear_market_rally", "crash_liquidation"),
}
LABEL_TO_GROUP = {r: g for g, rs in LABEL_GROUPS.items() for r in rs}

#: The word the card prints under a STALE headline, per group. TA-208 §7's own mapping.
GROUP_LAST_READING = {
    "TREND-UP": "BULLISH last reading",
    "TREND-DOWN/STRESS": "BEARISH last reading",
    "RANGE": "NEUTRAL last reading",
}


#: Which version each new one inherits its starting state from, at a cutover. Written down
#: rather than derived from the string, because "the previous version" is a judgement and a
#: wrong guess silently inherits the wrong hysteresis.
CUTOVER_PREDECESSOR = {"v2.1": "v2"}


async def cutover_state(conn, to_version: str, *, rules=None) -> Dict[str, Any]:
    """Can `to_version` inherit its predecessor's state, and does it agree about it?
    TA-208 §7 item 7 / R-IV.1288(c).

    THE INHERITANCE IS VERIFIED, NOT COPIED, and that is deliberate. Copying v2's
    `shown / held_sessions / pending / pending_closes` across asserts nothing: it would hand
    v2.1 a state it never computed, and if v2.1's rules ever diverged the mismatch would be
    invisible precisely because the numbers were copied. Instead the new version RECOMPUTES the
    predecessor's last settled session from the same stored series and the answers are compared.

    IT IS SOUND TO EXPECT AGREEMENT: v2.1's rules file differs from v2's in exactly two leaf
    keys, `.version` and `.hysteresis.stated_cost`, which is asserted by
    `test_regime_v21_r1277`. Every threshold, the hysteresis block and the order are identical,
    so the same series must produce the same shown label and the same counters. If it does not,
    something changed that nobody declared -- and this function REFUSES rather than carrying on,
    which is TA-208's own instruction: "If the job cannot start without a seeded history, STOP
    and ask SPINE. Do not backfill."

    NOTHING IS WRITTEN HERE and no era is replayed onto disk. The walk is in memory, exactly as
    every nightly run already does to rebuild its counters.
    """
    from jobs.regime_seed import replay

    rules = rules or load_rules()
    out: Dict[str, Any] = {"to_version": to_version, "ok": False, "needs_ruling": False}

    have = await conn.fetchval(
        "SELECT COUNT(*) FROM regime_snapshots "
        " WHERE rules_version = $1 AND superseded = FALSE", to_version)
    if have:
        return dict(out, ok=True, inherited=False,
                    reason="%s already has %d current row(s); no cutover needed" % (to_version,
                                                                                    have))

    frm = CUTOVER_PREDECESSOR.get(to_version)
    if not frm:
        return dict(out, needs_ruling=True,
                    reason=("no predecessor is declared for %s, so there is no state to inherit "
                            "and a seed would be required -- which TA-208 item 7 forbids "
                            "without a ruling" % to_version))
    row = await conn.fetchrow(
        """SELECT as_of, shown_regime, regime, held_sessions, pending, pending_closes
             FROM regime_snapshots
            WHERE rules_version = $1 AND superseded = FALSE AND settled IS TRUE
            ORDER BY as_of DESC LIMIT 1""", frm)
    if row is None:
        return dict(out, needs_ruling=True,
                    reason=("%s has no settled row to inherit from, so %s cannot start without "
                            "a seed -- stopping, as TA-208 item 7 directs" % (frm, to_version)))

    anchor = row["as_of"]
    anchor_s = anchor.isoformat() if hasattr(anchor, "isoformat") else str(anchor)
    stored = {"shown_regime": row["shown_regime"], "held_sessions": row["held_sessions"],
              "pending": row["pending"], "pending_closes": row["pending_closes"]}

    series = await load_designated_series(conn)
    sessions, build = await build_sessions(conn, series, rules=rules,
                                           settled_through=anchor_s)
    walked = replay(sessions, rules)
    mine = next((r for r in walked["shown"] if r.get("as_of") == anchor_s), None)
    if mine is None:
        return dict(out, needs_ruling=True, anchor=anchor_s,
                    reason=("%s produced no row for %s, the session it would inherit from"
                            % (to_version, anchor_s)))
    computed = {k: mine.get(k) for k in stored}
    diffs = {k: (stored[k], computed[k]) for k in stored if stored[k] != computed[k]}
    if diffs:
        return dict(out, needs_ruling=True, anchor=anchor_s, stored=stored,
                    computed=computed, differs=diffs, build=build,
                    reason=("%s recomputes %s differently from %s's stored row (%s). The rules "
                            "files differ only in `version` and `stated_cost`, so this should "
                            "be impossible -- something undeclared changed. STOPPING and asking "
                            "SPINE rather than inheriting a state the new version disputes"
                            % (to_version, anchor_s, frm,
                               ", ".join("%s stored=%r computed=%r" % (k, a, b)
                                         for k, (a, b) in sorted(diffs.items())))))
    return dict(out, ok=True, inherited=True, anchor=anchor_s, from_version=frm,
                stored=stored, computed=computed, build=build,
                reason=("%s inherits %s's state at %s and agrees about it exactly (%s). No seed, "
                        "no replay written, no backfill."
                        % (to_version, frm, anchor_s,
                           ", ".join("%s=%r" % (k, v) for k, v in sorted(stored.items())))))


async def unmatched_run(conn, rules_version: Optional[str] = None) -> Dict[str, Any]:
    """How many of the LATEST settled sessions matched no rule at all. TA-208 §7 item 4.

    DERIVED AT READ TIME FROM STORED COLUMNS, no schema change: `regime_snapshots.regime` is the
    RAW label and is NULL when no section-2 row matched, while `shown_regime` carries whatever
    hysteresis is still holding. So a run of NULL raw labels beside a non-null shown one is
    exactly "the card is showing a label no rule currently supports", and the card must say so.

    A DIFFERENT CONDITION FROM `bar_freshness`, and the two must not be confused: that one says
    the DATA stopped arriving, this one says the data arrived and NOTHING MATCHED. A reader who
    sees one headline must not be left thinking it is the other, which is why the strings differ.

    AND BLOCKED IS NOT STALE. When a candidate qualifies and hysteresis holds it, `blocked` is
    non-null and the raw label IS matched -- the card shows the normal label plus the blocked
    chip. Counting that as "no rule matched" would turn the hysteresis working as designed into
    an alarm.
    """
    version = rules_version or load_rules().get("version")
    out: Dict[str, Any] = {"rules_version": version, "run": 0, "last_match_as_of": None,
                           "shown_regime": None, "group": None, "group_word": None,
                           "stale": False, "chip": None}
    try:
        rows = await conn.fetch(
            """SELECT as_of, regime, shown_regime, blocked
                 FROM regime_snapshots
                WHERE rules_version = $1 AND superseded = FALSE AND settled IS TRUE
                ORDER BY as_of DESC
                LIMIT 120""", version)
    except Exception as exc:                                        # noqa: BLE001
        return dict(out, reason="regime_snapshots unreadable (%s)" % type(exc).__name__)
    if not rows:
        return dict(out, reason="no settled snapshot for rules %s" % version)

    run = 0
    for r in rows:
        if r["regime"] is None:
            run += 1
        else:
            out["last_match_as_of"] = (r["as_of"].isoformat()
                                       if hasattr(r["as_of"], "isoformat") else str(r["as_of"]))
            break
    shown = rows[0]["shown_regime"]
    group = LABEL_TO_GROUP.get(str(shown or "").lower())
    out.update(run=run, shown_regime=shown, group=group,
               group_word=GROUP_LAST_READING.get(group or ""))
    if run >= 1:
        out["stale"] = True
        out["chip"] = ("HELD · no rule matched %d session%s · last match %s"
                       % (run, "" if run == 1 else "s",
                          out["last_match_as_of"] or "never"))
        out["reason"] = ("the latest %d settled session%s produced no raw label; the card is "
                         "holding %r, which no rule currently supports"
                         % (run, "" if run == 1 else "s", shown))
    else:
        out["reason"] = ("the latest settled session matched a rule (%r), so the label is not "
                         "held past its evidence" % rows[0]["regime"])
    return out


#: R-IV.1278(b)4. The headline the card shows when the DATA has stopped arriving. The ruling's
#: own words, with the last settled bar's date appended -- a bare "STALE" tells a reader to
#: distrust the screen and nothing about how far back to look.
DATA_STALE_HEADLINE = "DATA STALE · last settled %s"

#: How many trading days the newest designated bar may lag before the headline fires. ONE, not
#: zero, and the reason is this plan's own entitlement edge: Polygon withholds a session while
#: it is still current, so between the close and the next session's release the newest bar is
#: ALWAYS one session old. A threshold of zero would print DATA STALE every single evening and
#: the headline would stop meaning anything within a week.
DATA_STALE_LAG = 1


async def bar_freshness(conn) -> Dict[str, Any]:
    """Is the DESIGNATED BAR SERIES still arriving? R-IV.1278(b)4.

    A DIFFERENT QUESTION FROM `health()`, which measures the newest LABEL's lag. The two come
    apart in the direction that matters: on 2026-10-19 and 10-20 the nightly ran, Polygon
    refused the session, and NO BAR AND NO LABEL were written -- while the card went on showing
    2026-10-16's label with nothing on its face to say the series had stopped. `health` knew
    (it would have read `dead` by the 20th); the HEADLINE did not say so, and the headline is
    what a reader sees.

    So this reads the bar table directly, on the designated source, and returns a headline the
    card prints INSTEAD of a label rather than beside it. Never a silent old label.

    SPY DECIDES, because SPY is the shortest series and the 200dma warm-up is measured on it: a
    session QQQ has and SPY does not is not classifiable, so SPY's newest bar is the newest
    session the classifier could use.
    """
    out: Dict[str, Any] = {"source": CLOSE_SOURCE, "threshold_sessions": DATA_STALE_LAG}
    try:
        row = await conn.fetchrow(
            """SELECT MAX(date) AS newest FROM regime_daily_bars
                WHERE ticker = 'SPY' AND close_source = $1""", CLOSE_SOURCE)
    except Exception as exc:                                        # noqa: BLE001
        # UNREADABLE IS NOT FRESH. The headline fires, because a card that cannot check its own
        # data must not imply it did.
        return dict(out, stale=True, newest_bar=None, lag_sessions=None,
                    headline=DATA_STALE_HEADLINE % "unknown",
                    reason="regime_daily_bars unreadable (%s)" % type(exc).__name__)
    newest = row["newest"] if row else None
    if newest is None:
        return dict(out, stale=True, newest_bar=None, lag_sessions=None,
                    headline=DATA_STALE_HEADLINE % "never",
                    reason="no %s bar for SPY at all" % CLOSE_SOURCE)
    newest_d = newest if isinstance(newest, _date) else _date.fromisoformat(str(newest)[:10])

    from stable_engine.market_calendar import CalendarHorizonError, last_settled_session
    try:
        settled = last_settled_session()
    except CalendarHorizonError as exc:
        return dict(out, stale=True, newest_bar=newest_d.isoformat(), lag_sessions=None,
                    headline=DATA_STALE_HEADLINE % newest_d.isoformat(),
                    reason="cannot establish the last settled session (%s)" % exc)

    # TRADING DAYS, not calendar days -- a Friday bar read on Monday is ONE session behind, and
    # a calendar threshold would call every ordinary Monday stale.
    from stable_engine.market_calendar import trading_days_between
    try:
        lag = max(0, trading_days_between(newest_d, settled))
    except Exception:                                               # noqa: BLE001
        lag = max(0, (settled - newest_d).days)

    stale = lag > DATA_STALE_LAG
    return dict(out, stale=stale, newest_bar=newest_d.isoformat(),
                last_settled_session=settled.isoformat(), lag_sessions=lag,
                headline=(DATA_STALE_HEADLINE % newest_d.isoformat()) if stale else None,
                reason=("the newest %s bar is %s, %d trading session(s) behind the last settled "
                        "session %s" % (CLOSE_SOURCE, newest_d.isoformat(), lag,
                                        settled.isoformat())
                        if stale else
                        "the newest %s bar is %s, %d session(s) behind %s, inside the %d-session "
                        "allowance this plan's withheld current session requires"
                        % (CLOSE_SOURCE, newest_d.isoformat(), lag, settled.isoformat(),
                           DATA_STALE_LAG)))


#: B8 section 7: how many settled sessions the ribbon shows.
RIBBON_SESSIONS = 40


async def ribbon(conn, rules_version: Optional[str] = None) -> Dict[str, Any]:
    """The last RIBBON_SESSIONS settled sessions' shown labels, oldest-first. B8 section 7.

    `superseded = FALSE`, WHICH IS LOAD-BEARING AND NOT BOILERPLATE. Since the 2026-10-17
    re-seed `regime_snapshots` holds TWO GENERATIONS over the same dates -- the current rows
    priced off Polygon and 321 superseded rows priced off stable_daily_bars -- and nothing but
    this flag tells them apart. A ribbon read without it would draw each session twice, from two
    different price bases, and look like a 40-session strip of 80 squares.

    No label is invented for a session that has none: a gap in the strip is a gap.
    """
    version = rules_version or load_rules().get("version")
    try:
        rows = await conn.fetch(
            """SELECT as_of, shown_regime, change, blocked
                 FROM regime_snapshots
                WHERE rules_version = $1 AND superseded = FALSE
                ORDER BY as_of DESC
                LIMIT $2""", version, RIBBON_SESSIONS)
    except Exception as exc:                                        # noqa: BLE001
        return {"sessions": [], "error": "regime_snapshots unreadable (%s)"
                                         % type(exc).__name__}
    out = [{"as_of": r["as_of"].isoformat() if r["as_of"] else None,
            "label": r["shown_regime"],
            "flipped": bool(r["change"]),
            "blocked": bool(r["blocked"])}
           for r in reversed(rows)]
    return {
        "sessions": out,
        "count": len(out),
        "asked_for": RIBBON_SESSIONS,
        "basis": ("the last %d settled sessions from regime_snapshots, current generation "
                  "only (superseded = FALSE): the table holds two generations over the same "
                  "dates since the 2026-10-17 re-seed" % RIBBON_SESSIONS),
        "short_history": len(out) < RIBBON_SESSIONS,
    }


#: B8 §3's Zweig PROXY needs a breadth series, and this is the only module allowed to read
#: `regime_snapshots` (the R-IV.1195 reader allowlist). Keeping the read here rather than
#: widening that allowlist is the point of the guard: it asked whether a new reader was
#: allowed, and the better answer was not to add one.
BREADTH_HISTORY_SESSIONS = 60


async def breadth_history(conn, sessions: int = BREADTH_HISTORY_SESSIONS) -> List[Any]:
    """The stored `pct_above_50dma` series, oldest-first, current generation only.

    `superseded = FALSE` for the same reason the ribbon needs it: the table holds TWO
    GENERATIONS over the same dates since the 2026-10-17 re-seed, and a breadth series read
    without it would interleave two price bases into one thrust test.
    """
    import json as _json

    try:
        rows = await conn.fetch(
            """SELECT inputs_json
                 FROM regime_snapshots
                WHERE superseded = FALSE
                ORDER BY as_of DESC
                LIMIT $1""", sessions)
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[regime] breadth history unreadable: %s", type(exc).__name__)
        return []
    out: List[Any] = []
    for r in reversed(rows):
        blob = r["inputs_json"]
        if isinstance(blob, str):
            try:
                blob = _json.loads(blob)
            except ValueError:
                blob = None
        # THE KEY I FIRST READ DOES NOT EXIST. `breadth.pct_above_50dma` is what the drawer's
        # own line asks for, but `_breadth_block` stores `sectors_above_50dma` (a COUNT) and
        # `sectors_total` -- so the series came back with ZERO observations and §3 said
        # unavailable. It was right to: it reported nothing rather than inventing a series,
        # which is the only reason this was a five-minute fix and not a wrong thrust flag.
        #
        # The percentage is DERIVED from the two stored numbers. And a session whose count is
        # absent stays a HOLE: `sectors_above_50dma` is omitted entirely when fewer than all
        # eleven sector series were usable, because `sectors_above_50dma` refuses a partial
        # count -- so a missing key means "not measurable that day", never zero sectors.
        pct = None
        if isinstance(blob, dict):
            br = blob.get("breadth")
            if isinstance(br, dict):
                count = br.get("sectors_above_50dma")
                total = br.get("sectors_total")
                try:
                    if count is not None and total:
                        pct = 100.0 * float(count) / float(total)
                except (TypeError, ValueError, ZeroDivisionError):
                    pct = None
        out.append(pct)
    return out


async def supersede_other_versions(conn, version: str) -> Dict[str, Any]:
    """Mark every snapshot whose rules_version is NOT `version` as superseded. R-IV.1260(c).

    WHY THIS IS NEEDED AT ALL, and it is the quiet half of a version bump. Every read in this
    lane filters `superseded = FALSE` and does NOT filter rules_version -- the ribbon, the
    breadth history, the flip list. So the instant v2 rows land beside v1's, those reads would
    return BOTH generations over the same dates: a 40-session ribbon of 80 squares, a breadth
    series interleaving two label sets. Marking the old version superseded is what makes
    `superseded = FALSE` mean "the current generation" rather than "everything ever written".

    Audited, with the count, because a silent bulk UPDATE over the label history is exactly the
    kind of write that should leave a mark.
    """
    try:
        n = await conn.fetchval(
            """UPDATE regime_snapshots SET superseded = TRUE
                WHERE rules_version <> $1 AND superseded = FALSE
             RETURNING 1""", version)
        rows = await conn.fetch(
            """SELECT rules_version, COUNT(*) AS n
                 FROM regime_snapshots GROUP BY rules_version ORDER BY rules_version""")
    except Exception as exc:                                        # noqa: BLE001
        return {"error": "%s" % type(exc).__name__}
    # fetchval returns one row of a RETURNING; count properly instead.
    try:
        moved = await conn.fetchval(
            "SELECT COUNT(*) FROM regime_snapshots WHERE rules_version <> $1 "
            "AND superseded = TRUE", version)
    except Exception:                                               # noqa: BLE001
        moved = None
    out = {"version": version, "superseded_rows": moved,
           "by_version": {r["rules_version"]: int(r["n"]) for r in rows}}
    await _audit(conn, action="supersede",
                 detail=json.dumps(out)[:1900], rows_written=int(moved or 0),
                 rules_version=version)
    return out


async def label_counts_by_version(conn) -> Dict[str, Any]:
    """Shown-label counts per rules_version, for R-IV.1260(c)'s v1-beside-v2 report.

    Counts the SHOWN label, not the raw verdict: the shown one is what the card displayed and
    what a flip is counted on. Both versions are reported over their own rows, so a label that
    appears in one and not the other is visible as an absence rather than as a zero that has to
    be inferred.
    """
    try:
        rows = await conn.fetch(
            """SELECT rules_version, close_source, shown_regime,
                      COUNT(*) AS n,
                      COUNT(*) FILTER (WHERE superseded IS TRUE) AS superseded_n
                 FROM regime_snapshots
                WHERE settled IS TRUE
                GROUP BY rules_version, close_source, shown_regime
                ORDER BY rules_version, close_source, shown_regime""")
    except Exception as exc:                                        # noqa: BLE001
        return {"error": "regime_snapshots unreadable (%s)" % type(exc).__name__}
    # GROUPED BY close_source TOO, which is a correction to this very function. Its first
    # version grouped by rules_version alone and reported v1 = 623 against v2 = 302 — because
    # v1 holds TWO GENERATIONS over the same dates: the 302 rows priced off Polygon, and the
    # 321 superseded rows priced off stable_daily_bars from before the 2026-10-17 re-seed.
    # Summing them puts a double-counted column beside a single-counted one and invites the
    # reader to conclude v2 lost 321 sessions. Each generation is reported on its own line so
    # the comparison is like with like.
    out: Dict[str, Any] = {"generations": {}, "basis": (
        "one line per (rules_version, close_source): v1 holds two generations over the same "
        "dates — Polygon and the pre-2026-10-17 stable_daily_bars rows — so a count grouped "
        "by version alone double-counts v1")}
    for r in rows:
        key = "%s/%s" % (r["rules_version"] or "?", r["close_source"] or "?")
        gen = out["generations"].setdefault(key, {"labels": {}, "superseded": 0, "total": 0})
        gen["labels"][r["shown_regime"] or "(none)"] = int(r["n"])
        gen["superseded"] += int(r["superseded_n"] or 0)
        gen["total"] += int(r["n"])
    return out
