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

    sessions = sessions_from_series(series, settled_through=through)
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
    if capture.get("degraded"):
        detail = "DEGRADED, no label written: %s" % capture.get("reason")
        await _audit(conn, action="degraded", detail=detail, as_of=target,
                     rules_version=version)
        logger.error("[regime_job] nightly %s", detail)
        return {"written": 0, "degraded": True, "reason": capture.get("reason"),
                "as_of": target.isoformat()}

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
    r = await _write_snapshot(conn, row, seeded=False, close_source=CLOSE_SOURCE)
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
        pct = None
        if isinstance(blob, dict):
            br = blob.get("breadth")
            if isinstance(br, dict):
                pct = br.get("pct_above_50dma")
        try:
            out.append(None if pct is None else float(pct))
        except (TypeError, ValueError):
            out.append(None)
    return out
