"""R-IV.1398(b)1 — the 5-minute ATM-vertical quote grid. TRITON-R2 Stage A.

FAIL-CLOSED UNTIL FUNDED, AND THAT IS THE WHOLE TOP OF THIS FILE
    R-IV.1398(b)1 says report the added calls/day against the 40,000 account cap and the
    shed line BEFORE this ships. So the grid cannot spend a single call until its caller tag
    is in `uw_governor.QUOTAS`, and an unregistered tag is not a missing config -- it is the
    ruling not yet given. `preflight()` refuses on it and names which of the two gates is shut.

    An unregistered tag would otherwise run on DEFAULT_QUOTA 500: the job would quietly spend
    500 unbudgeted calls a day on a path nobody had approved, which is the `outcome_resolver`
    fault already recorded in the quota table -- 2,764 calls in a session on a default meant
    for unknown code paths. Registration is therefore the gate, not a formality.

WHAT IT CAPTURES
    Eight names, NEAREST EXPIRY ONLY, every five minutes from 09:45 to 15:55 ET -- 75 slots --
    and from each chain FOUR contracts: the ATM call and put, and the two short legs one
    implied move out. That is both sides of an ATM vertical, priced at the same instant.

    The existing 30-minute job (`option_quote_capture`) is unchanged and keeps running. It
    answers a different question -- the whole +/-5 strike neighbourhood across 0-3 DTE, twelve
    times a day -- and this one answers "what did the vertical cost at 11:25". Neither is a
    subsample of the other: this grid's time resolution is six times finer and its strike
    coverage is far narrower, deliberately, because that is what fits in the budget.

ONE IMPLIED MOVE, DEFINED ONCE
    "One implied move" here is ONE STANDARD DEVIATION of the underlying to this expiry. Two
    routes compute the same quantity and the one used is recorded on every row:

        straddle  (preferred)  move = (atm_call_mid + atm_put_mid) x sqrt(pi/2)
        iv        (fallback)   move = atm_strike x sigma x sqrt(T)

    sqrt(pi/2) = 1.2533 is not a rule of thumb: an ATM straddle is worth
    S*sigma*sqrt(2T/pi) = 0.7979 x S*sigma*sqrt(T), so dividing by 0.7979 recovers the
    one-sigma move exactly. The two routes therefore mean the same thing and are comparable
    across rows.

    THE STRADDLE IS PREFERRED, and this is the one design choice worth arguing. The IV route
    needs sigma from the vendor's `implied_volatility` field -- plan-tier gated, and seen
    absent -- and needs T, which needs a clock and an annualisation convention that has to
    match the vendor's. On a 0-DTE chain at 15:30 the IV route's answer moves with whether the
    vendor annualised on calendar or trading time; the straddle has no convention in it at
    all. It is the price of the move, quoted by the market, at the instant of capture.

    Neither route is fabricated when it cannot be computed: `implied_move` is NULL,
    `implied_move_method` is 'none', the two ATM rows are still stored, and the short legs are
    simply absent. A NULL with a recorded reason is not a gap (conventions #37/#41).

THE DEGENERATE VERTICAL IS LABELLED, NOT HIDDEN
    Near a 0-DTE close the one-sigma move falls below one strike increment, so the short strike
    rounds back onto the ATM strike. The job then takes the nearest strike STRICTLY beyond ATM
    and sets `short_leg_degenerate`. The spread is real and tradeable; it is just one increment
    wide because the move was smaller than one increment, and a reader must be able to tell
    that from a bug.

CALLS PER DAY, MEASURED BEFORE A LINE OF THIS RAN
    75 slots x 8 tickers x 1 expiry = 600, plus first-slot expiry discovery (below), worst
    case 32 on a Monday -- 632/day. Against a measured hub spend of 13,606-14,075/day
    (/api/uw/spend, UW days 2026-10-20 to 2026-10-23) and an account cap of 40,000.

EXPIRY DISCOVERY RUNS ONCE A DAY, AND THE WINDOW IS 0-7 DTE, NOT 0-3
    The 30-minute job's window is 0-3 DTE by ruling, and for a grid keyed on the NEAREST
    expiry that window has a hole: on a Monday the candidates are Mon/Tue/Wed/Thu, and a name
    whose only expiry is Friday has none of them. Its nearest expiry is 4 DTE, outside the
    window, so the grid would record nothing for it all day while burning four probes finding
    that out. 0-7 reaches Friday from any weekday. The first hit per ticker is remembered for
    the session, so discovery is once a day -- and a probe that finds a chain IS a capture, so
    only the empty probes cost anything.
"""

from __future__ import annotations

import logging
import math
import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

JOB_NAME = "option_quote_grid"

#: Its own tag, so its spend is attributable and it can be shed without touching the
#: 30-minute capture beside it. Registration in QUOTAS is the funding gate; see preflight().
CALLER_TAG = "option_quote_grid"

ENV_FLAG = "OPTION_QUOTE_GRID_ENABLED"

TICKERS: Tuple[str, ...] = ("SPY", "QQQ", "IWM", "SMH", "NVDA", "AAPL", "MSFT", "TSLA")

#: 09:45 -> 15:55 ET every 5 minutes. 75 slots.
SLOT_TIMES_ET: Tuple[time, ...] = tuple(
    time(9 + (45 + 5 * i) // 60, (45 + 5 * i) % 60) for i in range(75)
)

#: Two minutes, for the reason the 30-minute job's 15:59 override carries: the loop's wake-ups
#: land at an arbitrary phase within the minute, so a grace shorter than one poll interval
#: loses slots to phase alone. Two minutes is well under the 5-minute spacing, so no two slots
#: can ever contend, and a capture is always nearer its own slot than the next.
SLOT_GRACE_MINUTES = 2

#: Poll twice per grace window, so no slot depends on a single wake-up landing well.
POLL_SECONDS = 30

DTE_MAX = 7
UW_CONTRACT_CAP = 500

#: Fraction of the registered quota this job will spend in a session. NOT a literal ceiling:
#: a hard-coded number and a ruled quota drift apart, and the quota table is the record. The
#: haircut leaves room for a retry and for the governor's own accounting.
SESSION_CEILING_FRACTION = 0.96

#: sqrt(pi/2). An ATM straddle is worth S*sigma*sqrt(2T/pi); multiplying by this recovers the
#: one-sigma move. Written as the expression so nobody has to trust a decimal literal.
STRADDLE_TO_SIGMA = math.sqrt(math.pi / 2.0)

SECONDS_PER_YEAR = 365.25 * 24 * 3600

MOVE_FROM_STRADDLE = "straddle"
MOVE_FROM_IV = "iv"
MOVE_NONE = "none"

LEG_ATM_CALL = "atm_call"
LEG_ATM_PUT = "atm_put"
LEG_SHORT_CALL = "short_call"
LEG_SHORT_PUT = "short_put"

# ---------------------------------------------------------------------------
# per-session state
# ---------------------------------------------------------------------------

_session_et_date: Optional[str] = None
_calls_used = 0
_slots_done: set = set()
#: ticker -> expiry ISO once found for this session; present and None once 0-7 DTE is spent.
_nearest_expiry: Dict[str, Optional[str]] = {}
#: (ticker, expiry_iso) -> True when probed and empty. Absences only; a hit lands above.
_probed_empty: Dict[Tuple[str, str], bool] = {}
_last_result: Dict[str, object] = {}
_preflight_logged = False


def reset_for_tests() -> None:
    """Clear per-session state. Tests only."""
    global _session_et_date, _calls_used, _slots_done, _nearest_expiry, _probed_empty
    global _last_result, _preflight_logged
    _session_et_date = None
    _calls_used = 0
    _slots_done = set()
    _nearest_expiry = {}
    _probed_empty = {}
    _last_result = {}
    _preflight_logged = False


def _roll_session(et_date: str) -> bool:
    """Start a new session when the ET date changes. True when a roll happened."""
    global _session_et_date, _calls_used, _slots_done, _nearest_expiry, _probed_empty
    if _session_et_date == et_date:
        return False
    _session_et_date = et_date
    _calls_used = 0
    _slots_done = set()
    _nearest_expiry = {}
    _probed_empty = {}
    return True


# ---------------------------------------------------------------------------
# the two gates
# ---------------------------------------------------------------------------

def tag_is_registered() -> bool:
    """Is CALLER_TAG in the governor's quota table?

    Imported inside the call rather than at module scope so the check reads the table AS IT
    IS at the moment of the call -- a test that registers the tag, and a deploy that lands the
    funding ruling, both take effect without a reimport.
    """
    try:
        from integrations.uw_governor import FOREIGN_RESERVE_QUOTAS, QUOTAS
        return CALLER_TAG in QUOTAS or CALLER_TAG in FOREIGN_RESERVE_QUOTAS
    except Exception:                                               # noqa: BLE001
        # An unreadable quota table is not a licence to spend.
        return False


def enabled() -> bool:
    """The env gate. DEFAULT OFF, and `or "false"` because Railway returns '' for an unset
    reference rather than None -- the pattern the whole repo uses for exactly that reason."""
    return (os.getenv(ENV_FLAG) or "false").strip().lower() == "true"


def preflight() -> Optional[str]:
    """None when the grid may run, else the reason it may not.

    Two independent gates, reported separately on purpose: "the ruling has not funded this"
    and "the operator has not switched it on" are different states with different fixes, and
    one message for both is the collapse this register keeps filing.
    """
    if not tag_is_registered():
        return ("caller tag %r is NOT in uw_governor.QUOTAS: R-IV.1398(b)1 requires the "
                "calls/day report and a funding ruling before this grid spends anything. "
                "Refusing rather than running on DEFAULT_QUOTA." % CALLER_TAG)
    if not enabled():
        return "%s is not 'true'" % ENV_FLAG
    return None


def session_ceiling() -> int:
    """Calls this job may spend in a session, derived from the RULED quota, not a literal."""
    if not tag_is_registered():
        return 0
    try:
        from integrations.uw_governor import quota_for
        quota, _tier = quota_for(CALLER_TAG)
    except Exception:                                               # noqa: BLE001
        return 0
    return int(quota * SESSION_CEILING_FRACTION)


# ---------------------------------------------------------------------------
# planning
# ---------------------------------------------------------------------------

def candidate_expiries(session: date, dte_max: int = DTE_MAX) -> List[Tuple[date, int]]:
    """Weekday dates in the 0..dte_max window, nearest first. Weekends carry no expiry."""
    out = []
    for k in range(dte_max + 1):
        d = session + timedelta(days=k)
        if d.weekday() < 5:
            out.append((d, k))
    return out


def next_probe(ticker: str, session: date) -> Optional[Tuple[date, int]]:
    """The (expiry, dte) to try next for this ticker, or None when nothing is left to try.

    Once a hit is remembered this returns it unchanged for the rest of the session, which is
    what makes discovery a once-a-day cost rather than a per-slot one.
    """
    found = _nearest_expiry.get(ticker)
    if found:
        d = date.fromisoformat(found)
        return d, (d - session).days
    if ticker in _nearest_expiry:        # present and None: candidates exhausted today
        return None
    for expiry, dte in candidate_expiries(session):
        if _probed_empty.get((ticker, expiry.isoformat())):
            continue
        return expiry, dte
    _nearest_expiry[ticker] = None
    return None


def plan_pairs(session: date, tickers: Sequence[str] = TICKERS
               ) -> List[Tuple[str, date, int]]:
    """[(ticker, expiry, dte)] for this slot, one per ticker, nearest DTE first.

    Sorted by (dte, ticker) so that when the slot allowance binds, the call dropped belongs to
    the name whose expiry is furthest out -- the least time-critical quote in the slot.
    """
    pairs = []
    for t in tickers:
        nxt = next_probe(t, session)
        if nxt is None:
            continue
        pairs.append((t, nxt[0], nxt[1]))
    pairs.sort(key=lambda p: (p[2], p[0]))
    return pairs


def slot_allowance(calls_used: int, slots_remaining: int, ceiling: int) -> int:
    """`remaining // slots_remaining`: every later slot keeps a share no earlier one can eat.

    The same guarantee the 30-minute job relies on, for the same reason -- the governor sheds
    what arrives last, and what arrives last here is the 15:55 slot.
    """
    if slots_remaining <= 0:
        return 0
    return max(0, max(0, ceiling - calls_used) // slots_remaining)


def due_slot(now_et: datetime) -> Optional[time]:
    """The slot this instant belongs to, or None. Bounded grace; see SLOT_GRACE_MINUTES."""
    if now_et.weekday() >= 5:
        return None
    t = now_et.time()
    due = None
    for s in SLOT_TIMES_ET:
        if t >= s:
            due = s
        else:
            break
    if due is None:
        return None
    age = (datetime.combine(now_et.date(), t)
           - datetime.combine(now_et.date(), due)).total_seconds() / 60.0
    if age > SLOT_GRACE_MINUTES:
        return None
    return due


# ---------------------------------------------------------------------------
# the implied move
# ---------------------------------------------------------------------------

def years_to_expiry(now_et: datetime, expiry: date) -> float:
    """Calendar years from `now_et` to the 16:00 ET close on `expiry`. Never negative.

    Calendar time, matching the convention an annualised IV is quoted in -- mixing a
    trading-day T with a calendar-annualised sigma misprices the move by sqrt(252/365).
    """
    close = datetime.combine(expiry, time(16, 0), tzinfo=ET)
    return max(0.0, (close - now_et).total_seconds()) / SECONDS_PER_YEAR


def implied_move(atm_call: Optional[dict], atm_put: Optional[dict], strike: float,
                 now_et: datetime, expiry: date) -> Tuple[Optional[float], str]:
    """(one-sigma move in points, method). Straddle first, IV second, else (None, 'none')."""
    from jobs.option_quote_capture import _mid

    cm = _mid((atm_call or {}).get("bid"), (atm_call or {}).get("ask"))
    pm = _mid((atm_put or {}).get("bid"), (atm_put or {}).get("ask"))
    if cm is not None and pm is not None and (cm + pm) > 0:
        return (cm + pm) * STRADDLE_TO_SIGMA, MOVE_FROM_STRADDLE

    ivs = [c["iv"] for c in (atm_call, atm_put)
           if c and c.get("iv") is not None and c["iv"] > 0]
    if ivs and strike:
        t = years_to_expiry(now_et, expiry)
        if t > 0:
            sigma = sum(ivs) / len(ivs)
            return strike * sigma * math.sqrt(t), MOVE_FROM_IV
    return None, MOVE_NONE


def short_strike(strikes: Sequence[float], atm: float, move: float,
                 direction: int) -> Tuple[Optional[float], bool]:
    """(the listed strike ~one move out, degenerate?). `direction` is +1 call, -1 put.

    STRICTLY beyond ATM: a short leg at the ATM strike is not a vertical. When the move is
    smaller than one strike increment the target rounds back onto ATM, the adjacent strike is
    taken instead, and `degenerate` says so -- real, tradeable, one increment wide, and
    distinguishable from a bug.
    """
    side = sorted((s for s in strikes if (s - atm) * direction > 0),
                  key=lambda s: abs(s - atm))
    if not side:
        return None, False
    target = atm + direction * abs(move)
    best = min(side, key=lambda s: (abs(s - target), abs(s - atm)))
    return best, best == side[0] and abs(target - atm) < abs(side[0] - atm)


# ---------------------------------------------------------------------------
# one slot
# ---------------------------------------------------------------------------

async def capture_slot(now: Optional[datetime] = None,
                       slot: Optional[time] = None) -> dict:
    """Capture one grid slot. Never raises."""
    global _calls_used, _preflight_logged

    block = preflight()
    if block is not None:
        if not _preflight_logged:
            logger.warning("[oqg] NOT RUNNING: %s", block)
            _preflight_logged = True
        return {"slot": None, "reason": block, "captured": 0, "blocked": True}

    now = now or datetime.now(timezone.utc)
    et = now.astimezone(ET)
    _roll_session(et.date().isoformat())

    slot = slot or due_slot(et)
    if slot is None:
        return {"slot": None, "reason": "no slot due", "captured": 0}
    slot_key = slot.strftime("%H:%M")
    if slot_key in _slots_done:
        return {"slot": slot_key, "reason": "already captured", "captured": 0}

    session = et.date()
    ceiling = session_ceiling()
    remaining_slots = sum(1 for s in SLOT_TIMES_ET if s >= slot)
    allowance = slot_allowance(_calls_used, remaining_slots, ceiling)

    pairs = plan_pairs(session)
    summary = {
        "slot": slot_key, "session_date": session.isoformat(),
        "planned": len(pairs), "allowance": allowance, "ceiling": ceiling,
        "captured": 0, "rows": 0, "absent": 0, "unavailable": 0, "shed": 0,
        "calls": 0, "move_methods": {}, "degenerate": 0, "truncated": [],
    }

    pool = None
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
    except Exception as exc:                                        # noqa: BLE001
        logger.error("[oqg] no db pool, slot %s LOST: %s", slot_key, type(exc).__name__)

    used_here = 0
    for ticker, expiry, dte in pairs:
        if used_here >= allowance:
            summary["shed"] += 1
            continue
        try:
            raw, n_raw = await _fetch(ticker, expiry)
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("[oqg] %s %s fetch failed: %s", ticker, expiry,
                           type(exc).__name__)
            summary["unavailable"] += 1
            continue
        used_here += 1
        _calls_used += 1
        summary["calls"] += 1

        if raw is None:
            summary["unavailable"] += 1
            continue
        if n_raw >= UW_CONTRACT_CAP:
            logger.error("[oqg] %s %s returned %d >= cap %d - CENSORED",
                         ticker, expiry, n_raw, UW_CONTRACT_CAP)
            summary["truncated"].append("%s:%s" % (ticker, expiry.isoformat()))

        from jobs.option_quote_capture import parse_chain
        contracts = parse_chain(raw, ticker, expiry)
        if not contracts:
            # An empty chain is an ABSENT EXPIRY -- a vendor fact, not a failure -- and
            # remembering it is what keeps discovery to once a day.
            _probed_empty[(ticker, expiry.isoformat())] = True
            summary["absent"] += 1
            continue
        _nearest_expiry[ticker] = expiry.isoformat()

        legs, centre, atm_method, move, move_method, degen = build_legs(
            contracts, et, expiry)
        summary["move_methods"][move_method] = \
            summary["move_methods"].get(move_method, 0) + 1
        if degen:
            summary["degenerate"] += 1
        if not legs:
            summary["absent"] += 1
            continue
        written = await _store(pool, session, slot_key, now, ticker, expiry, dte,
                               legs, centre, atm_method, move, move_method, degen, n_raw)
        summary["captured"] += 1
        summary["rows"] += written

    if used_here:
        _slots_done.add(slot_key)
    summary["calls_used_session"] = _calls_used
    _last_result.clear()
    _last_result.update(summary)
    logger.info("[oqg] slot %s: %d/%d captured, %d rows, %d absent, %d unavailable, %d shed, "
                "%d/%d calls", slot_key, summary["captured"], summary["planned"],
                summary["rows"], summary["absent"], summary["unavailable"],
                summary["shed"], _calls_used, ceiling)
    return summary


async def _fetch(ticker: str, expiry: date) -> Tuple[Optional[list], int]:
    """ONE governed, UNCACHED call on this job's own tag.

    `_uw_request`, not `get_options_snapshot`, for the two reasons the 30-minute job records:
    the shared helper hard-codes the `option_contracts` tag (R-IV.1082(b) forbids touching it)
    and it reads a response cache -- and a cached chain stamped with this slot's time is a
    stale quote wearing a fresh timestamp. On a FIVE-minute grid that is worse, not better:
    the whole product is the difference between 11:25 and 11:30.
    """
    from integrations.uw_api import _uw_request

    data = await _uw_request(
        "/api/stock/%s/option-contracts" % ticker.upper(),
        params={"expiry": expiry.isoformat()},
        caller=CALLER_TAG,
    )
    if not data or not isinstance(data, dict) or "data" not in data:
        return None, 0
    raw = data["data"] or []
    return raw, len(raw)


def build_legs(contracts: List[dict], now_et: datetime, expiry: date):
    """(legs, atm_strike, atm_method, move, move_method, degenerate).

    `legs` is up to four (role, contract) pairs. The two ATM rows are stored even when no move
    can be computed: a dated ATM straddle quote is evidence on its own, and withholding it
    because the short leg is missing would lose the slot entirely.
    """
    from jobs.option_quote_capture import atm_strike

    centre, atm_method = atm_strike(contracts)
    if centre is None:
        return [], None, atm_method, None, MOVE_NONE, False

    by_key = {(c["type"], c["strike"]): c for c in contracts}
    atm_c, atm_p = by_key.get(("call", centre)), by_key.get(("put", centre))

    move, move_method = implied_move(atm_c, atm_p, centre, now_et, expiry)

    legs = []
    if atm_c:
        legs.append((LEG_ATM_CALL, atm_c))
    if atm_p:
        legs.append((LEG_ATM_PUT, atm_p))

    degen = False
    if move is not None:
        strikes = sorted({c["strike"] for c in contracts})
        for role, kind, direction in ((LEG_SHORT_CALL, "call", 1),
                                      (LEG_SHORT_PUT, "put", -1)):
            k, d = short_strike(strikes, centre, move, direction)
            degen = degen or d
            if k is not None and (kind, k) in by_key:
                legs.append((role, by_key[(kind, k)]))
    return legs, centre, atm_method, move, move_method, degen


async def _store(pool, session: date, slot_key: str, captured_at: datetime,
                 ticker: str, expiry: date, dte: int, legs, centre: Optional[float],
                 atm_method: str, move: Optional[float], move_method: str,
                 degenerate: bool, n_raw: int) -> int:
    """Insert one (ticker, slot) batch. Never raises."""
    if pool is None:
        return 0
    from jobs.option_quote_capture import _mid

    written = 0
    try:
        async with pool.acquire() as conn:
            for role, r in legs:
                try:
                    await conn.execute(
                        """
                        INSERT INTO option_quote_grid
                            (session_date, slot_et, captured_at, ticker, expiry, dte,
                             leg_role, contract_type, strike, bid, ask, mid, iv, delta,
                             volume, open_interest, atm_strike, atm_method,
                             implied_move, implied_move_method, short_leg_degenerate,
                             raw_contract_count, truncated, caller_tag)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
                                $17,$18,$19,$20,$21,$22,$23,$24)
                        ON CONFLICT (session_date, slot_et, ticker, expiry, leg_role)
                        DO UPDATE SET
                            captured_at = EXCLUDED.captured_at,
                            contract_type = EXCLUDED.contract_type,
                            strike = EXCLUDED.strike,
                            bid = EXCLUDED.bid, ask = EXCLUDED.ask, mid = EXCLUDED.mid,
                            iv = EXCLUDED.iv, delta = EXCLUDED.delta,
                            volume = EXCLUDED.volume,
                            open_interest = EXCLUDED.open_interest,
                            atm_strike = EXCLUDED.atm_strike,
                            atm_method = EXCLUDED.atm_method,
                            implied_move = EXCLUDED.implied_move,
                            implied_move_method = EXCLUDED.implied_move_method,
                            short_leg_degenerate = EXCLUDED.short_leg_degenerate,
                            raw_contract_count = EXCLUDED.raw_contract_count,
                            truncated = EXCLUDED.truncated
                        """,
                        session, slot_key, captured_at, ticker, expiry, dte,
                        role, r["type"], r["strike"], r["bid"], r["ask"],
                        _mid(r["bid"], r["ask"]), r["iv"], r["delta"],
                        int(r["volume"] or 0), int(r["open_interest"] or 0),
                        centre, atm_method, move, move_method, degenerate,
                        n_raw, n_raw >= UW_CONTRACT_CAP, CALLER_TAG,
                    )
                    written += 1
                except Exception as exc:                            # noqa: BLE001
                    logger.warning("[oqg] row insert failed %s %s %s: %s",
                                   ticker, expiry, role, type(exc).__name__)
    except Exception as exc:                                        # noqa: BLE001
        logger.error("[oqg] store failed %s %s: %s", ticker, expiry, type(exc).__name__)
    return written


# ---------------------------------------------------------------------------
# the loop and /health
# ---------------------------------------------------------------------------

async def run_forever() -> None:
    """Wake every POLL_SECONDS, capture a slot when one is due. Catches everything."""
    import asyncio

    await asyncio.sleep(90)
    while True:
        try:
            await capture_slot()
        except Exception as exc:                                    # noqa: BLE001
            logger.error("[oqg] slot error: %s", exc)
        await asyncio.sleep(POLL_SECONDS)


async def capture_status() -> dict:
    """For /health. Reports the session's coverage, not just the last slot.

    The two lessons already paid for by the 30-minute job's surface are carried over:
    expectation is built from the CLOCK, not from `due_slot` (which returns None after the
    last grace and would report `slots_missed: []` all evening), and coverage is the UNION of
    memory and stored rows (memory alone would cry "missed" after every deploy).
    """
    now_et = datetime.now(timezone.utc).astimezone(ET)
    block = preflight()

    is_session_day = now_et.weekday() < 5
    expected = ([s.strftime("%H:%M") for s in SLOT_TIMES_ET if now_et.time() >= s]
                if is_session_day and block is None else [])

    captured, source = set(_slots_done), "memory"
    if block is None:
        try:
            from database.postgres_client import get_postgres_client
            pool = await get_postgres_client()
            if pool is not None:
                async with pool.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT DISTINCT slot_et FROM option_quote_grid"
                        " WHERE session_date = $1::date", now_et.date())
                captured |= {r["slot_et"] for r in rows}
                source = "stored_rows"
        except Exception as exc:                                    # noqa: BLE001
            source = "memory (db unreadable: %s)" % type(exc).__name__

    return {
        "job": JOB_NAME,
        "caller_tag": CALLER_TAG,
        #: The funding gate, ON THE SURFACE. An operator must be able to see that this is
        #: refusing BY RULING rather than broken, without reading the log.
        "blocked": block,
        "tag_registered": tag_is_registered(),
        "env_enabled": enabled(),
        "session_et_date": _session_et_date,
        "slots_total": len(SLOT_TIMES_ET),
        "slots_expected_so_far": len(expected),
        "slots_captured": len(captured),
        "slots_missed": [s for s in expected if s not in captured],
        "coverage_source": source,
        "calls_used_session": _calls_used,
        "ceiling": session_ceiling(),
        "last_slot": dict(_last_result) if _last_result else None,
    }
