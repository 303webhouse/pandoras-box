"""Read-only Market Profile accessor — backs the hub_get_market_profile MCP tool (B4 Chunk A).

Reads the latest `pythia_events` row for a ticker. pythia_events is an event log
(one row per PYTHIA Pine alert); the latest row carries the current session's
levels in its columns + raw_payload.

Session-based staleness (B4 Q-A1 resolution):
  - "ok"          : latest event is from the CURRENT session
  - "stale"       : latest event is from a PRIOR session (data still returned,
                    with session_date + event_age_seconds so the caller sees how old)
  - "unavailable" : no row for the ticker

Field locations (verified 2026-06-09 against a live SPY row — Q-A2):
  - vah/val/poc, ib_high/ib_low, va_migration, poor_high/poor_low,
    volume_quality, interpretation, price, alert_type, timestamp → COLUMNS
  - prev_poc/prev_vah/prev_val → ONLY in raw_payload (jsonb), not columns

AEGIS (B4 amendment 2): this layer selects explicit fields only and NEVER
returns raw_payload verbatim. single_prints / day_type are not computed by
Pine v2.3 → always None (never fabricated — GEX lesson).
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

import pytz

logger = logging.getLogger(__name__)

_ET = pytz.timezone("America/New_York")

# DEF-MP-DEAD-RENDERS-AS-QUIET: sessions behind at which a feed stops being
# "quiet" and starts being "not arriving". Two means the feed missed a whole
# completed session AND the current one.
DARK_AFTER_SESSIONS = 2


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _num_or_none(v: Any) -> Optional[float]:
    """Float, but 0/0.0 → None. Pine v2.4 serializes missing levels as nz(x,0);
    a confident zero is not data (B4 amendment — never surface fake levels)."""
    f = _safe_float(v)
    return f if (f is not None and f != 0) else None


def _prev_weekday(d: date) -> date:
    """Most recent weekday strictly before d (skips Sat/Sun). Holidays not handled."""
    cur = d - timedelta(days=1)
    while cur.weekday() >= 5:  # Mon=0 … Fri=4, Sat=5, Sun=6
        cur -= timedelta(days=1)
    return cur


def _sessions_behind(event_session: date, current_session: date) -> int:
    """Trading sessions between an event's session and the session under analysis.

    Counts WEEKDAYS, not calendar days. A Friday event read on Monday is ONE
    session behind, not three — a calendar-day count would call every Monday
    dark, which is the DEF-NIGHTLY-FLATLINE failure applied to a new instrument.
    """
    n = 0
    d = current_session
    while d > event_session:
        d = _prev_weekday(d)
        n += 1
    return n


def classify_freshness(sessions_behind: int) -> str:
    """Three-state freshness verdict. DEF-MP-DEAD-RENDERS-AS-QUIET, R-IV.231(b).

    ok    - from the session under analysis
    stale - exactly one session behind; a genuinely quiet session looks like this
    dark  - DARK_AFTER_SESSIONS or more behind; the feed is not arriving

    Symbol-agnostic by construction: it takes a count, not a ticker, so it cannot
    special-case a roster. There is deliberately no survivor list — the survivor
    set fell every week through 2026-07/08, so a hardcoded roster would be stale
    the week after it shipped and would then assert liveness that no longer holds.
    """
    if sessions_behind == 0:
        return "ok"
    return "stale" if sessions_behind < DARK_AFTER_SESSIONS else "dark"


def _current_session_date(now_et: datetime) -> date:
    """The trading date whose RTH session is current/most-recent as of now_et.

    Weekday at/after 09:30 ET → today (developing session).
    Weekday before 09:30 ET, or weekend → the last completed weekday session.
    Holiday calendar not modeled (approximation; acceptable — a holiday just
    means the "current" session label may lead by one day, which surfaces as
    'stale', the safe direction).
    """
    d = now_et.date()
    after_open = (now_et.hour, now_et.minute) >= (9, 30)
    if now_et.weekday() < 5 and after_open:
        return d
    return _prev_weekday(d) if now_et.weekday() >= 5 or not after_open else d


async def get_market_profile(ticker: str) -> Optional[Dict[str, Any]]:
    """Return the latest MP snapshot for a ticker, or None if no row exists.

    Returns a dict {status, data, staleness_seconds} for the tool layer to wrap.
    None signals 'unavailable' (no row) to the caller.
    """
    tkr = (ticker or "").upper().strip()
    if not tkr:
        return None

    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT ticker, alert_type, price, direction, vah, val, poc,
                   ib_high, ib_low, va_migration, poor_high, poor_low,
                   volume_quality, interpretation, raw_payload, timestamp,
                   -- R-IV.1024(c): the script version the PAYLOAD carried, read from
                   -- `raw_payload` ONLY.
                   --
                   -- IT USED TO READ THE `script_version` COLUMN FIRST, AND THAT TOOK THIS
                   -- SURFACE DOWN. The column is created by an ALTER in the webhook's INSERT
                   -- path, which runs only when a PYTHIA event is ACCEPTED -- and nothing has
                   -- been accepted since the v2.6 cutover started rejecting every alert. So
                   -- the reader required a column that only a currently-dead writer creates,
                   -- and `hub_get_market_profile` returned "column does not exist" for every
                   -- ticker. A READ must never depend on a WRITER having run.
                   --
                   -- `raw_payload` is NOT NULL on every row and carries `script` verbatim, so
                   -- this answers for old and new rows alike with no migration ordering.
                   NULLIF(raw_payload->>'script', '') AS script_version
            FROM pythia_events
            WHERE ticker = $1
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            tkr,
        )

    if row is None:
        return None  # caller → status="unavailable"

    rp = row["raw_payload"] or {}
    if isinstance(rp, str):
        try:
            rp = json.loads(rp)
        except (ValueError, TypeError):
            rp = {}

    ts = row["timestamp"]
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc.astimezone(_ET)
    event_session = ts.astimezone(_ET).date()
    current_session = _current_session_date(now_et)

    # DEF-MP-DEAD-RENDERS-AS-QUIET (R-IV.231(b)): three states, not two.
    #
    # The gate resolves max(timestamp) for THIS ticker at call time and compares
    # it to the session under analysis. There is deliberately NO survivor list:
    # the survivor set fell every week without exception through 2026-07/08, so
    # a hardcoded roster is tripwire decay at feed scale — it would be stale the
    # week after it shipped and would then assert liveness that no longer holds.
    #
    #   ok    — event is from the session under analysis
    #   stale — exactly one session behind; a genuinely quiet session looks like
    #           this, so it is labelled but not alarming
    #   dark  — TWO OR MORE sessions behind. A feed that has missed a full
    #           session plus the current one is not "quiet"; it is not arriving.
    #
    # DARK_AFTER_SESSIONS is a registered predicate (verification-laws section
    # 1.2), so its satisfaction rate over the population it is used on is stated
    # rather than assumed. Measured 2026-09-03 over every ticker in
    # pythia_events: 206 of 212 dark, 6 live — the state it selects is the
    # common case today, which is exactly why the two-state vocabulary failed.
    sessions_behind = _sessions_behind(event_session, current_session)
    status = classify_freshness(sessions_behind)

    age_seconds = int((now_utc - ts).total_seconds())

    # R-IV.1037(c)2: feed health. Computed from the ACCEPTED events table and the
    # rejections table, so it survives a restart -- the R-IV.1033(d) work tracked rejections
    # in process memory only and therefore could not be served at all.
    _feed = await _feed_health(tkr)
    # The script version the payload carried, or None. Bound once so the three
    # fields below cannot disagree about which Pine wrote this row.
    _script = (row["script_version"] or "").strip() or None
    data = {
        "ticker": tkr,
        "poc": _safe_float(row["poc"]),
        "vah": _safe_float(row["vah"]),
        "val": _safe_float(row["val"]),
        # prev_* live in raw_payload only (Q-A2 verified). 0.0 → None (nz-zero scrub).
        "prev_poc": _num_or_none(rp.get("prev_poc")),
        "prev_vah": _num_or_none(rp.get("prev_vah")),
        "prev_val": _num_or_none(rp.get("prev_val")),
        "ib_high": _num_or_none(row["ib_high"]),
        "ib_low": _num_or_none(row["ib_low"]),
        "poor_high": bool(row["poor_high"]) if row["poor_high"] is not None else None,
        "poor_low": bool(row["poor_low"]) if row["poor_low"] is not None else None,
        "va_migration": row["va_migration"],
        "volume_quality": row["volume_quality"],
        "last_event": row["alert_type"],
        "interpretation": row["interpretation"],
        "price_at_event": _safe_float(row["price"]),
        "session_date": event_session.isoformat(),
        "as_of": ts.astimezone(timezone.utc).isoformat(),
        "event_age_seconds": age_seconds,
        # sessions, not seconds: 3,293,950s does not read as 38 days
        "sessions_behind": sessions_behind,
        # R-IV.1037(c)2: feed health, BESIDE the freshness verdict and never folded into it.
        # ok/stale/dark describe the LEVELS (how many sessions behind); they cannot tell a
        # quiet market from a refused feed, which is why the v2.6 cutover's 65 consecutive
        # 401s read as `ok` with sessions_behind 0.
        **_feed,
        # R-IV.1024(c): READ FROM THE DATA. This was the string literal
        # "pythia_webhook_v2.4" plus a note naming v2.4, written when the payload carried no
        # version field at all (verified 2026-06-10). PYTHIA v2.6 adds "script", so the label
        # can and must reflect what produced the row -- and with v2.6 live, a hardcoded v2.4
        # was simply false. A version a reader cannot distrust is worse than none.
        "source": ("pythia_webhook_%s" % _script if _script else "pythia_webhook"),
        "script_version": _script,
        "script_version_note": (
            None if _script else
            "the payload carried no `script` field; this row predates PYTHIA v2.6 or came "
            "from an alert that omits it. NOT inferred from the deploy date."),
        # Explicit null, never fabricated. The note now names the version that actually
        # produced the row instead of asserting one.
        "single_prints": None,
        "day_type": None,
        "note": ("single_prints and day_type are not computed by Pine %s" % _script
                 if _script else
                 "single_prints and day_type are not computed by the Pine script that wrote "
                 "this row (its version was not recorded)"),
    }

    return {"status": status, "data": data, "staleness_seconds": age_seconds}


async def _feed_health(tkr: str = None) -> dict:
    """`feed_health`, `last_accepted_at` and `rejected_since_last_accept`. NEVER raises.

    R-IV.1095(b): EVERY FIELD HERE NOW NAMES ITS SCOPE, because two correct fields side by
    side implied something false.

    `feed_health` is deliberately FEED-WIDE: "is the pipe alive" is not a per-ticker question,
    and R-IV.1037(c)2 created it to catch 65 consecutive 401s that the per-ticker freshness
    verdict reported as `ok`. That scope is right and is kept.

    THE DEFECT WAS SERVING IT UNLABELLED INSIDE A PER-TICKER PAYLOAD. `data` holds SPY's
    levels; `last_accepted_at` held MAX(timestamp) across ALL tickers. On 2026-10-15 a read of
    SPY returned `last_accepted_at 16:34:49Z` while SPY's own newest row was from 10-14 --
    both figures correct, and together they said SPY had just reported. It had not: 31 events
    landed that day across 28 tickers and NONE were core-8. The newest row belonged to SRE.
    So the fix is not a different number, it is the SCOPE of each number, stated:

      feed_health / last_accepted_at / rejected_since_last_accept   FEED-WIDE
      last_accepted_ticker                                          which ticker that was
      this_ticker_last_accepted_at / this_ticker_rejections_since   THIS ticker

    `last_accepted_ticker` alone would have prevented the misreading: the field would have
    said SRE.

    ACQUIRES ITS OWN CONNECTION rather than taking the caller's. The caller's `async with
    pool.acquire() as conn` has already closed by the time this runs, so the name is still
    bound but the connection is back in the pool -- using it would be a use-after-release,
    which fails intermittently under load and looks like a vendor problem.

    An unreadable count returns `unknown` rather than zero: "I could not check" must not read
    as "no rejections", which would report a refused feed as healthy.
    """
    from models.pythia_feed_health import classify
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            last, n = await _feed_counts(conn)
            who = await _last_accepted_ticker(conn)
            mine, mine_n = await _ticker_feed_counts(conn, tkr) if tkr else (None, None)
            newest, all_before, basis = (
                await _ticker_newest_refusal(conn, tkr) if tkr
                else (None, None, "no ticker was requested"))
        out = classify(last, n)
        out["feed_health_scope"] = (
            "FEED-WIDE: feed_health, last_accepted_at and rejected_since_last_accept cover "
            "EVERY ticker, not this one. `this_ticker_last_accepted_at` is this ticker's own "
            "(R-IV.1095(b)).")
        out["last_accepted_ticker"] = who
        out["this_ticker_last_accepted_at"] = (
            mine.astimezone(timezone.utc).isoformat() if mine else None)
        out["this_ticker_rejections_since"] = mine_n
        # R-IV.1109(b). `this_ticker_rejections_since` counts from this ticker's own last
        # ACCEPT; this instant is the newest refusal outright. The pair is what makes a count
        # actionable: "3 refusals" with no instant cannot tell a reader whether they are stale.
        out["this_ticker_newest_refusal_at"] = (
            newest.astimezone(timezone.utc).isoformat() if newest else None)
        out["this_ticker_refusals_all_before_process_start"] = all_before
        out["this_ticker_refusals_basis"] = basis
        # The reference instant the boolean was computed against, so a reader can CHECK it
        # rather than trust it. A boolean whose comparison point is absent from the payload is
        # unverifiable, and this one decides whether the principal recreates an alert.
        _started = _process_started_at()
        out["process_started_at"] = _started.isoformat() if _started else None
        return out
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("feed_health unavailable: %s", type(exc).__name__)
        # THE ERROR PATH MUST RETURN THE SAME SHAPE AS THE SUCCESS PATH. It used to return
        # `classify(None, None)` alone, so a database failure did not merely blank these
        # fields -- it REMOVED them, and an absent key reads to a consumer as "not
        # applicable" rather than "could not determine". Those are different facts, and the
        # one this field exists to report is the second. Caught by
        # test_the_payload_carries_the_instant_the_boolean_and_its_reference.
        out = classify(None, None)
        out["this_ticker_newest_refusal_at"] = None
        out["this_ticker_refusals_all_before_process_start"] = None
        out["this_ticker_refusals_basis"] = (
            "unreadable: %s while reading the feed, so nothing is claimed"
            % type(exc).__name__)
        _started = _process_started_at()
        out["process_started_at"] = _started.isoformat() if _started else None
        return out


async def _last_accepted_ticker(conn):
    """WHICH ticker the feed-wide `last_accepted_at` belongs to. None when unreadable.

    The single field that would have prevented R-IV.1095(b)'s misreading on its own: a reader
    seeing `SRE` next to a SPY request cannot mistake it for SPY.
    """
    try:
        return await conn.fetchval(
            "SELECT ticker FROM pythia_events ORDER BY timestamp DESC LIMIT 1")
    except Exception:                                               # noqa: BLE001
        return None


async def _ticker_feed_counts(conn, tkr: str):
    """(this ticker's last accepted instant, refusals since it). None is NOT zero."""
    try:
        last = await conn.fetchval(
            "SELECT MAX(timestamp) FROM pythia_events WHERE ticker = $1", tkr)
        n = await conn.fetchval(
            "SELECT count(*) FROM pythia_webhook_rejections"
            " WHERE ticker = $1 AND reason NOT LIKE 'OBSERVE:%'"
            "   AND (($2::timestamptz IS NULL) OR rejected_at > $2::timestamptz)", tkr, last)
        return last, (int(n) if n is not None else None)
    except Exception:                                               # noqa: BLE001
        return None, None


async def _ticker_newest_refusal(conn, tkr: str):
    """R-IV.1109(b). (newest real refusal for this ticker, all_before_process_start, basis).

    WHAT THIS AUTOMATES. On 2026-10-15 the question "does any refusal for QQQ fall after the
    16:23:49Z restart?" had to be settled by hand from the log, because the payload could say
    how MANY refusals there were but not WHEN the newest one was. Without the instant, a count
    cannot distinguish "refused before the fix, now fine" from "still being refused" -- and
    those have opposite remedies: one needs nothing, the other needs the alert recreated.

    `OBSERVE:`-prefixed rows are EXCLUDED, as everywhere else in this module: they arrived and
    were LET THROUGH. Counting an allow-through as a refusal would invert the field's meaning.

    THE BOOLEAN IS NEVER VACUOUSLY TRUE. With no refusals on record, "all refusals are before
    the process start" is true of the empty set and would read as a verified all-clear -- a
    claim about a check that had no subject. That is the DEF-EDGE-SPEC-B2 defect exactly, where
    a column counted row-existence twice and answered nothing. So the boolean is None there,
    and `basis` says which of the three Nones applies: no refusals, or unreadable.
    """
    try:
        newest = await conn.fetchval(
            "SELECT MAX(rejected_at) FROM pythia_webhook_rejections"
            " WHERE ticker = $1 AND reason NOT LIKE 'OBSERVE:%'", tkr)
    except Exception:                                               # noqa: BLE001
        return None, None, "unreadable: the refusal table could not be queried"

    if newest is None:
        return None, None, "no real refusal is on record for this ticker"

    started = _process_started_at()
    if started is None:
        return newest, None, "unreadable: this process's start instant is unavailable"

    before = newest < started
    return newest, before, (
        "every refusal for this ticker predates this process's start"
        if before else
        "at least one refusal for this ticker POSTDATES this process's start")


def _process_started_at():
    """This process's start, from the same constant /health reports.

    Imported rather than re-derived: a second `datetime.now()` captured at a different import
    moment would disagree with /health by seconds, and a boolean compared against the wrong
    instant is worse than no boolean -- it would answer the restart question confidently and
    wrongly for any refusal landing in the gap.
    """
    try:
        from build_identity import PROCESS_STARTED_AT
        return PROCESS_STARTED_AT
    except Exception:                                               # noqa: BLE001
        return None


async def _feed_counts(conn):
    """(last accepted timestamp, rejections since it). Separated so the SQL is testable."""
    try:
        last = await conn.fetchval("SELECT MAX(timestamp) FROM pythia_events")
        # REFUSALS ONLY. `WEBHOOK_PYTHIA_ENFORCE` unset means OBSERVE, where a bad secret is
        # ALLOWED THROUGH and recorded under the OBSERVE reason. Counting those here would make
        # feed_health report `rejecting` -- "arriving and being REFUSED" -- while events were
        # landing normally, which is a false alarm in the one field built to prevent false
        # alarms. The observe rows are still written and still readable; they are simply not
        # refusals, so they do not drive this verdict.
        n = await conn.fetchval(
            "SELECT count(*) FROM pythia_webhook_rejections"
            " WHERE (($1::timestamptz IS NULL) OR rejected_at > $1::timestamptz)"
            "   AND reason NOT LIKE 'OBSERVE:%'", last)
        return last, (int(n) if n is not None else None)
    except Exception:                                               # noqa: BLE001
        # The table may not exist yet on a fresh deploy. None is NOT zero.
        return None, None


def _et_midnight_utc(d: date) -> datetime:
    """00:00 America/New_York on `d`, as an aware UTC instant (DST-correct)."""
    return _ET.localize(datetime(d.year, d.month, d.day)).astimezone(timezone.utc)


async def get_prior_session_vas(conn, tickers, session_date: date) -> Dict[str, Dict[str, Any]]:
    """PRIOR-SESSION developing VA for each ticker, as it stood before `session_date`.

    R-IV.422 / Olympus review 2026-04-22 (PYTHIA + PYTHAGORAS): "use PRIOR SESSION developing
    VA at signal time -- cumulative VA introduces lookahead bias." So this never reads a row
    from `session_date` itself: the window is the prior trading day's ET calendar date and
    nothing else. The last event in that window whose VA is usable carries the prior session's
    VA as developed through its final alert.

    A ticker with no usable row in that window is ABSENT from the result -- a stale VA from an
    older session is not the prior session's VA, and is not returned as if it were.
    Pine serializes a missing level as 0, so zero / inverted levels are excluded in SQL.

    Returns {ticker: {vah, val, poc, as_of, va_session}}.
    """
    from stable_engine.market_calendar import previous_trading_day

    prior = previous_trading_day(session_date)
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (ticker) ticker, vah, val, poc, timestamp
        FROM pythia_events
        WHERE ticker = ANY($1::text[])
          AND timestamp >= $2::timestamptz
          AND timestamp <  $3::timestamptz
          AND vah > 0 AND val > 0 AND vah > val
        ORDER BY ticker, timestamp DESC
        """,
        sorted({(t or "").upper() for t in tickers if t}),
        _et_midnight_utc(prior),
        _et_midnight_utc(prior + timedelta(days=1)),
    )
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        ts = r["timestamp"]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        out[r["ticker"]] = {
            "vah": _num_or_none(r["vah"]),
            "val": _num_or_none(r["val"]),
            "poc": _num_or_none(r["poc"]),
            "as_of": ts.astimezone(timezone.utc).isoformat(),
            "va_session": prior.isoformat(),
        }
    return out
