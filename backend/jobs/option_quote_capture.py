"""R-IV.1082(b) — forward-only option bid/ask capture, 8 names, 0-3 DTE, 12 intraday slots.

THE COLLECTOR LAW APPLIES AND IS THE WHOLE POINT. No vendor call returns yesterday's bid/ask
as they stood at 11:30. A slot not captured is permanently absent, so this job's shedding
behaviour matters more than its throughput -- which is why it sheds on its own terms below
rather than letting the governor do it.

WHAT IT CAPTURES
    SPY QQQ IWM SMH NVDA AAPL MSFT TSLA, every expiry 0-3 DTE, +/-5 strikes around ATM, both
    types: strike, expiry, bid, ask, IV, delta, volume, open interest -- as published AT THE
    SLOT. THIRTEEN slots: 10:00 to 15:30 ET every 30 minutes, plus 15:59 (R-IV.1398(b)1), the
    last minute the book is unambiguously live. The 15:59 slot carries its own, much shorter
    grace; see SLOT_GRACE_OVERRIDE_MINUTES for why the default would have fabricated a close.

ONE CALL PER (TICKER, EXPIRY, SLOT), and it is NOT the shared chain helper
    `integrations.uw_api.get_options_snapshot` would have been the obvious reuse and is wrong
    here, twice over:

      * it hard-codes `caller="option_contracts"`, the DAEDALUS tag R-IV.1082(b) explicitly
        forbids touching. Every call would have been charged to it.
      * it reads and writes a shared response CACHE. A cache hit would hand back a chain
        fetched minutes earlier and this job would store it stamped with the current slot's
        time -- a stale quote wearing a fresh timestamp. For a job whose entire product is
        "what was the spread AT 11:30", that is not an optimisation, it is fabrication.

    So this calls `_uw_request` directly with its own tag and no cache layer.

HOW IT STAYS INSIDE ~300/day WITHOUT LOSING THE CLOSE
    Measured from the expiry calendar before this was written: 144/204/168/132/132 calls
    Mon-Fri if SPY/QQQ/IWM carry daily expiries and the other five are Friday-only (worst day
    204), but 384 on Mon and Tue if all eight turn out to have daily expiries. The second case
    overflows a 300 grant by 84.

    THE GOVERNOR SHEDS THE CALLS THAT ARRIVE LAST, which are the 15:00, 15:30 and 15:59 slots.
    Losing the close is the one loss that cannot be made good, and it would be invisible in the
    stored rows. So the job budgets itself instead:

      per-slot allowance = remaining session budget // remaining slots

    which can never starve the final slot, and within a slot the (ticker, expiry) pairs are
    attempted NEAREST EXPIRY FIRST. An overflow therefore costs the 3-DTE quote, which is
    recoverable tomorrow when it becomes 2-DTE, instead of the 15:30 quote, which is gone.

EXPIRY DISCOVERY COSTS NOTHING EXTRA
    Which expiries exist is a vendor fact, not a calendar fact -- "SMH has a Wednesday expiry"
    is not something to assume. Candidate weekday dates in the 0-3 DTE window are probed in
    DTE order, and a probe IS a capture call: an expiry that exists returns its chain and the
    rows are kept. An expiry that does not returns empty and is remembered as absent for the
    rest of the session, so it is probed once a day, not twelve times.

THE ATM STRIKE COMES FROM THE CHAIN, NOT FROM A SECOND CALL
    Centering +/-5 strikes needs spot, and a quote call per (ticker, slot) would add 96 calls a
    day. The chain already carries delta, and the ATM strike is where |delta| is nearest 0.50.
    Cascade, with the method RECORDED on every row so a later reader knows which was used:
    delta -> put/call parity (the strike minimising |call_mid - put_mid|) -> median strike.
    A row whose centre was chosen by the median fallback is much weaker evidence than one
    centred on delta, and that difference must survive into the data.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

JOB_NAME = "option_quote_capture"

#: Its OWN governor tag. Not `option_contracts` (R-IV.1082(b): do not touch it), not
#: `flow_per_expiry` (which funds it but is a different code path).
CALLER_TAG = "option_quote_capture"

TICKERS: Tuple[str, ...] = ("SPY", "QQQ", "IWM", "SMH", "NVDA", "AAPL", "MSFT", "TSLA")

#: 10:00 -> 15:30 ET every 30 minutes (R-IV.1082(b)), PLUS 15:59 (R-IV.1398(b)1). Thirteen.
#:
#: WHY 15:59 AND NOT 16:00. The spread a trade actually pays is the one on the book while the
#: book is still live. 16:00 is the close itself, and a call issued at 16:00:00 is answered
#: after it -- the first quote outside the session, which is the one quote this series must
#: never contain. 15:59 is the last minute that is unambiguously inside.
SLOT_TIMES_ET: Tuple[time, ...] = tuple(
    time(10 + (30 * i) // 60, (30 * i) % 60) for i in range(12)
) + (time(15, 59),)

DTE_MAX = 3
STRIKE_WINDOW = 5          # +/-5 strikes around ATM

#: How long after its time a slot may still be captured. Under the 30-minute spacing so two
#: slots never contend, and short enough that a capture is always about its own slot.
SLOT_GRACE_MINUTES = 25

#: PER-SLOT OVERRIDE, and the 15:59 slot is the reason it exists.
#:
#: The 25-minute default was written for 30-minute spacing and is SAFE THERE: the last slot was
#: 15:30, so its grace expired at 15:55, inside the session. Applied unchanged to a 15:59 slot
#: it would keep that slot "due" until 16:24 -- and a loop that woke at 16:20, or a Railway
#: deploy that restarted the process at 16:15, would fetch the post-close book, store it, and
#: stamp it `15:59`. Wide, untradeable quotes wearing the label of the closing minute. That is
#: EXACTLY the fabrication the `due_slot` docstring below was written to forbid, and the
#: default would have walked straight into it: the comment naming the hazard is three lines
#: from the constant that would have caused it.
#:
#: TWO MINUTES, not one. The loop wakes every POLL_SECONDS (60), so its wake-ups land at an
#: arbitrary phase within the minute: a one-minute grace is missed outright whenever the phase
#: puts a wake-up at :59:05 and the next at 16:00:05, which is a coin flip on the one slot
#: that cannot be recovered. Two minutes guarantees at least one wake-up inside the window
#: while reaching no further than 16:01 -- where the closing book is still the closing book.
#:
#: And `captured_at` on every row is the real instant regardless. The slot label is the
#: intent; `captured_at` is the measurement, and a reader who cares can always tell a
#: 15:59:12 capture from a 16:00:58 one.
SLOT_GRACE_OVERRIDE_MINUTES = {time(15, 59): 2}
UW_CONTRACT_CAP = 500      # the documented per-call ceiling (uw_api.py)

#: Fraction of the RULED quota this job will spend in a session. R-IV.1415(c)2: its own
#: fail-closed ceiling, like the grid's.
#:
#: THE OLD FORM WAS THE LITERAL 288, which is exactly 0.96 x 300 -- the fraction was already
#: there, frozen into a number. Two faults followed from that. A quota raise did not move the
#: ceiling, so R-IV.1415(c)'s +20 would have funded nothing; and an UNREGISTERED tag would
#: still have spent 288, on the governor's DEFAULT_QUOTA of 500, which is the
#: `outcome_resolver` fault this register already carries. Derived, it is 0 when the tag is
#: absent and follows the table when it is present.
SESSION_CEILING_FRACTION = 0.96


def tag_is_registered() -> bool:
    """Is CALLER_TAG in the governor's quota table? An unreadable table is not a licence."""
    try:
        from integrations.uw_governor import FOREIGN_RESERVE_QUOTAS, QUOTAS
        return CALLER_TAG in QUOTAS or CALLER_TAG in FOREIGN_RESERVE_QUOTAS
    except Exception:                                               # noqa: BLE001
        return False


def session_ceiling() -> int:
    """Calls this job may spend in a session, from the RULED quota. 0 when unregistered."""
    if not tag_is_registered():
        return 0
    try:
        from integrations.uw_governor import quota_for
        quota, _tier = quota_for(CALLER_TAG)
    except Exception:                                               # noqa: BLE001
        return 0
    return int(quota * SESSION_CEILING_FRACTION)

#: How close a call's delta must be to 0.50 before it is trusted as the ATM marker. Beyond
#: this the chain is too sparse or deltas are missing, and the parity fallback is used.
_ATM_DELTA_TOLERANCE = 0.25

ATM_FROM_DELTA = "delta"
ATM_FROM_PARITY = "parity"
ATM_FROM_MEDIAN = "median"

# ---------------------------------------------------------------------------
# per-session state. Reset when the ET date rolls.
# ---------------------------------------------------------------------------

_session_et_date: Optional[str] = None
_calls_used = 0
_slots_done: set = set()
#: (ticker, expiry_iso) -> True when the vendor has served it, False when probed and empty.
_expiry_known: Dict[Tuple[str, str], bool] = {}
_last_result: Dict[str, object] = {}


def reset_for_tests() -> None:
    """Clear per-session state. Tests only."""
    global _session_et_date, _calls_used, _slots_done, _expiry_known, _last_result
    _session_et_date = None
    _calls_used = 0
    _slots_done = set()
    _expiry_known = {}
    _last_result = {}


def _roll_session(et_date: str) -> bool:
    """Start a new session when the ET date changes. True when a roll happened."""
    global _session_et_date, _calls_used, _slots_done, _expiry_known
    if _session_et_date == et_date:
        return False
    _session_et_date = et_date
    _calls_used = 0
    _slots_done = set()
    _expiry_known = {}
    return True


# ---------------------------------------------------------------------------
# planning
# ---------------------------------------------------------------------------

def candidate_expiries(session: date, dte_max: int = DTE_MAX) -> List[Tuple[date, int]]:
    """[(expiry, dte)] for weekday dates within the window, nearest first.

    Weekends are skipped because no contract expires on one. Whether a given weekday actually
    HAS an expiry for a given ticker is the vendor's answer, not this function's.
    """
    out = []
    for k in range(dte_max + 1):
        d = session + timedelta(days=k)
        if d.weekday() < 5:
            out.append((d, k))
    return out


def plan_pairs(session: date, tickers: Sequence[str] = TICKERS) -> List[Tuple[str, date, int]]:
    """[(ticker, expiry, dte)] to attempt this slot, NEAREST EXPIRY FIRST.

    Pairs already known absent for this session are dropped -- probed once a day, not twelve
    times. Ordering is (dte, ticker) so that when the per-slot allowance binds, the call that
    gets dropped is the FARTHEST expiry rather than whichever ticker happened to sort last.
    """
    pairs = []
    for expiry, dte in candidate_expiries(session):
        for t in tickers:
            if _expiry_known.get((t, expiry.isoformat())) is False:
                continue
            pairs.append((t, expiry, dte))
    pairs.sort(key=lambda p: (p[2], p[0]))
    return pairs


def slot_allowance(calls_used: int, slots_remaining: int,
                   ceiling: Optional[int] = None) -> int:
    """How many calls this slot may make.

    `remaining // slots_remaining` is the whole guarantee: every later slot, including the
    15:30 one, keeps a reserved share no earlier slot can consume. A greedy early slot cannot
    eat the close.
    """
    if slots_remaining <= 0:
        return 0
    if ceiling is None:
        ceiling = session_ceiling()
    remaining = max(0, ceiling - calls_used)
    return max(0, remaining // slots_remaining)


def due_slot(now_et: datetime) -> Optional[time]:
    """The slot this instant belongs to, or None.

    A slot stays due for SLOT_GRACE_MINUTES so a loop that wakes late still captures it -- a
    missed wake-up should cost freshness, not the whole slot.

    BUT THE GRACE IS BOUNDED, AND THAT BOUND IS THE POINT. Without it the 15:30 slot would
    still be "due" at 16:30, and a restart after the close would store post-close quotes --
    wide, stale, untradeable -- stamped as the 15:30 snapshot. That is not a late capture, it
    is a fabricated one, and nothing downstream could tell the difference. Same reasoning as
    the uncached fetch: a quote is only evidence about the moment it was published.
    """
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
    if age > SLOT_GRACE_OVERRIDE_MINUTES.get(due, SLOT_GRACE_MINUTES):
        return None
    return due


# ---------------------------------------------------------------------------
# the chain -> rows
# ---------------------------------------------------------------------------

def _f(v) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _mid(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    if bid is None or ask is None:
        return None
    if ask < bid:
        return None
    return (bid + ask) / 2.0


def atm_strike(contracts: List[dict]) -> Tuple[Optional[float], str]:
    """(strike, method). The centre for the +/-5 window, from the chain alone.

    Three routes, best first, and the one used is returned so it lands on every row.
    """
    calls = [c for c in contracts if c.get("type") == "call"]

    # 1. delta nearest 0.50
    with_delta = [c for c in calls if c.get("delta") is not None]
    if with_delta:
        best = min(with_delta, key=lambda c: abs(abs(c["delta"]) - 0.50))
        if abs(abs(best["delta"]) - 0.50) <= _ATM_DELTA_TOLERANCE:
            return best["strike"], ATM_FROM_DELTA

    # 2. put/call parity: the strike where call and put mids are closest
    puts = {c["strike"]: c for c in contracts if c.get("type") == "put"}
    parity = []
    for c in calls:
        p = puts.get(c["strike"])
        if not p:
            continue
        cm, pm = _mid(c.get("bid"), c.get("ask")), _mid(p.get("bid"), p.get("ask"))
        if cm is None or pm is None:
            continue
        parity.append((abs(cm - pm), c["strike"]))
    if parity:
        parity.sort()
        return parity[0][1], ATM_FROM_PARITY

    # 3. median strike -- weak, and labelled so
    strikes = sorted({c["strike"] for c in contracts if c.get("strike") is not None})
    if strikes:
        return strikes[len(strikes) // 2], ATM_FROM_MEDIAN
    return None, ATM_FROM_MEDIAN


def parse_chain(raw: list, ticker: str, expiry: date) -> List[dict]:
    """Flatten UW contracts for ONE expiry. Never raises on a bad contract."""
    from integrations.uw_api import _parse_option_symbol

    out = []
    for c in raw or []:
        try:
            sym = c.get("option_symbol") or ""
            parsed = _parse_option_symbol(sym)
            if not parsed:
                continue
            if parsed["expiry"] != expiry.isoformat():
                continue
            out.append({
                "symbol": sym,
                "ticker": ticker,
                "expiry": expiry,
                "type": parsed["type"],
                "strike": parsed["strike"],
                "bid": _f(c.get("nbbo_bid")),
                "ask": _f(c.get("nbbo_ask")),
                "iv": _f(c.get("implied_volatility")),
                "delta": _f(c.get("delta")),
                "volume": c.get("volume") or 0,
                "open_interest": c.get("open_interest") or 0,
            })
        except Exception:                                           # noqa: BLE001
            continue
    return out


def select_window(contracts: List[dict], window: int = STRIKE_WINDOW
                  ) -> Tuple[List[dict], Optional[float], str]:
    """(+/-window strikes around ATM, both types; atm_strike; atm_method).

    The window counts STRIKES, not dollars, so it adapts to each ticker's strike spacing
    without a per-ticker table.
    """
    centre, method = atm_strike(contracts)
    if centre is None:
        return [], None, method
    strikes = sorted({c["strike"] for c in contracts})
    try:
        i = strikes.index(centre)
    except ValueError:
        return [], centre, method
    keep = set(strikes[max(0, i - window): i + window + 1])
    return [c for c in contracts if c["strike"] in keep], centre, method


# ---------------------------------------------------------------------------
# one call
# ---------------------------------------------------------------------------

async def fetch_expiry(ticker: str, expiry: date) -> Tuple[Optional[list], int]:
    """(raw contracts, raw count). ONE governed, UNCACHED call on this job's own tag.

    `_uw_request` rather than `get_options_snapshot`: see the module docstring. A falsy
    response (including the governor's typed sentinel) comes back as None and the caller
    records the slot as incomplete rather than as empty.
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


# ---------------------------------------------------------------------------
# one slot
# ---------------------------------------------------------------------------

async def capture_slot(now: Optional[datetime] = None,
                       slot: Optional[time] = None) -> dict:
    """Capture one slot. Never raises.

    Returns a summary that distinguishes, deliberately:
      captured        pairs whose rows were stored
      absent          pairs the vendor has no expiry for (a fact, not a failure)
      unavailable     pairs whose call returned nothing (governor, circuit, vendor)
      shed            pairs dropped because the slot's allowance ran out
    `shed` is reported separately from `unavailable` because one is this job's own budgeting
    and the other is something going wrong; a single "missing" count would hide which.
    """
    global _calls_used

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
    # R-IV.1415(c)3: the run opens HERE, past both early returns -- "no slot due" and "already
    # captured" are not runs, and recording them would write ~1,440 rows a day.
    _run_id = None
    try:
        from jobs.job_runs import JOB_OPTION_QUOTE_CAPTURE, start_run
        _run_id = await start_run(JOB_OPTION_QUOTE_CAPTURE, session)
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[oqc] could not open a job_runs record: %s", type(exc).__name__)

    remaining_slots = sum(1 for s in SLOT_TIMES_ET if s >= slot)
    ceiling = session_ceiling()
    allowance = slot_allowance(_calls_used, remaining_slots, ceiling)

    pairs = plan_pairs(session)
    summary = {
        "slot": slot_key, "session_date": session.isoformat(),
        "planned": len(pairs), "allowance": allowance,
        "captured": 0, "rows": 0, "absent": 0, "unavailable": 0, "shed": 0,
        "truncated": [], "calls": 0, "atm_methods": {},
    }

    pool = None
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
    except Exception as exc:                                        # noqa: BLE001
        logger.error("[oqc] no db pool, slot %s LOST: %s", slot_key, type(exc).__name__)

    used_here = 0
    for ticker, expiry, dte in pairs:
        if used_here >= allowance:
            summary["shed"] += 1
            continue
        try:
            raw, n_raw = await fetch_expiry(ticker, expiry)
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("[oqc] %s %s fetch failed: %s", ticker, expiry, type(exc).__name__)
            summary["unavailable"] += 1
            continue
        used_here += 1
        _calls_used += 1
        summary["calls"] += 1

        if raw is None:
            summary["unavailable"] += 1
            continue
        if n_raw >= UW_CONTRACT_CAP:
            # Per-expiry calls should sit far under the cap; if one does not, the capture is
            # censored and that must be visible rather than averaged over later.
            logger.error("[oqc] %s %s returned %d >= cap %d — CENSORED",
                         ticker, expiry, n_raw, UW_CONTRACT_CAP)
            summary["truncated"].append("%s:%s" % (ticker, expiry.isoformat()))

        contracts = parse_chain(raw, ticker, expiry)
        if not contracts:
            _expiry_known[(ticker, expiry.isoformat())] = False
            summary["absent"] += 1
            continue
        _expiry_known[(ticker, expiry.isoformat())] = True

        rows, centre, method = select_window(contracts)
        summary["atm_methods"][method] = summary["atm_methods"].get(method, 0) + 1
        if not rows:
            summary["absent"] += 1
            continue

        written = await _store(pool, session, slot_key, now, ticker, expiry, dte,
                               rows, centre, method, n_raw)
        summary["captured"] += 1
        summary["rows"] += written

    if used_here:
        _slots_done.add(slot_key)
    summary["calls_used_session"] = _calls_used
    summary["ceiling"] = ceiling
    await _finish(_run_id, summary, pool)
    _last_result.clear()
    _last_result.update(summary)
    logger.info("[oqc] slot %s: %d pairs captured, %d rows, %d absent, %d unavailable, "
                "%d shed, %d/%d calls this session",
                slot_key, summary["captured"], summary["rows"], summary["absent"],
                summary["unavailable"], summary["shed"], _calls_used, ceiling)
    return summary


async def _finish(run_id, summary: dict, pool) -> None:
    """Close the slot's job_runs row. Never raises.

    ZERO ROWS IS A FAULT, NOT A SUCCESS -- and under the collector law it is a permanent one:
    the slot it describes cannot be captured again. `completed_defective` is the existing
    vocabulary for "ran to the end and its own output check failed" (R-IV.426(b)), and a
    missing pool is an `error` because the slot is LOST rather than empty.
    """
    if run_id is None:
        return
    try:
        from jobs.job_runs import (STATUS_COMPLETED_DEFECTIVE, STATUS_ERROR, STATUS_OK,
                                   finish_run)
        rows = int(summary.get("rows") or 0)
        if pool is None:
            await finish_run(run_id, STATUS_ERROR, rows_touched=rows,
                             error="no database pool: slot %s is LOST and cannot be recaptured"
                                   % summary.get("slot"))
        elif rows > 0:
            await finish_run(run_id, STATUS_OK, rows_touched=rows)
        else:
            await finish_run(
                run_id, STATUS_COMPLETED_DEFECTIVE, rows_touched=0,
                error="stored no rows (%d absent, %d unavailable, %d shed of %d planned)"
                      % (summary.get("absent") or 0, summary.get("unavailable") or 0,
                         summary.get("shed") or 0, summary.get("planned") or 0))
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[oqc] could not close the job_runs record: %s", type(exc).__name__)


async def _store(pool, session: date, slot_key: str, captured_at: datetime,
                 ticker: str, expiry: date, dte: int, rows: List[dict],
                 centre: Optional[float], method: str, n_raw: int) -> int:
    """Insert one (ticker, expiry, slot) batch. Never raises."""
    if pool is None:
        return 0
    written = 0
    try:
        async with pool.acquire() as conn:
            for r in rows:
                try:
                    await conn.execute(
                        """
                        INSERT INTO option_quote_capture
                            (session_date, slot_et, captured_at, ticker, expiry, dte,
                             contract_type, strike, bid, ask, mid, iv, delta,
                             volume, open_interest, atm_strike, atm_method,
                             raw_contract_count, truncated, caller_tag)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,
                                $16,$17,$18,$19,$20)
                        ON CONFLICT (session_date, slot_et, ticker, expiry,
                                     contract_type, strike)
                        DO UPDATE SET
                            captured_at = EXCLUDED.captured_at,
                            bid = EXCLUDED.bid, ask = EXCLUDED.ask, mid = EXCLUDED.mid,
                            iv = EXCLUDED.iv, delta = EXCLUDED.delta,
                            volume = EXCLUDED.volume,
                            open_interest = EXCLUDED.open_interest,
                            atm_strike = EXCLUDED.atm_strike,
                            atm_method = EXCLUDED.atm_method,
                            raw_contract_count = EXCLUDED.raw_contract_count,
                            truncated = EXCLUDED.truncated
                        """,
                        session, slot_key, captured_at, ticker, expiry, dte,
                        r["type"], r["strike"], r["bid"], r["ask"],
                        _mid(r["bid"], r["ask"]), r["iv"], r["delta"],
                        int(r["volume"] or 0), int(r["open_interest"] or 0),
                        centre, method, n_raw, n_raw >= UW_CONTRACT_CAP, CALLER_TAG,
                    )
                    written += 1
                except Exception as exc:                            # noqa: BLE001
                    logger.warning("[oqc] row insert failed %s %s %s: %s",
                                   ticker, expiry, r.get("strike"), type(exc).__name__)
    except Exception as exc:                                        # noqa: BLE001
        logger.error("[oqc] store failed %s %s: %s", ticker, expiry, type(exc).__name__)
    return written


# ---------------------------------------------------------------------------
# the loop and /health
# ---------------------------------------------------------------------------

POLL_SECONDS = 60


async def run_forever() -> None:
    """Wake every minute, capture a slot when one is due. Catches everything."""
    import asyncio

    await asyncio.sleep(75)
    while True:
        try:
            await capture_slot()
        except Exception as exc:                                    # noqa: BLE001
            logger.error("[oqc] slot error: %s", exc)
        await asyncio.sleep(POLL_SECONDS)


async def capture_status() -> dict:
    """For /health. A FORWARD collection needs a surface that shows a missed slot.

    Reports the session's slot coverage, not just the last result: "the last slot worked" and
    "every slot worked" are different claims and only the second one means the series is
    usable.
    """
    now_et = datetime.now(timezone.utc).astimezone(ET)

    # EXPECTATION IS NOT CAPTURABILITY, and conflating them hid every miss. Built from
    # `due_slot` first, this list went EMPTY after 15:55 ET -- because `due_slot` returns None
    # once the last slot's grace expires -- so from the close until midnight the surface
    # reported `slots_missed: []` no matter how many slots had actually been lost. The quietest
    # possible reading of a totally failed session, at exactly the hour someone would look.
    #
    # A slot is EXPECTED once its time has passed on a weekday, whether or not it can still be
    # captured. Only then does `slots_missed` mean what its name says.
    is_session_day = now_et.weekday() < 5
    expected = ([s.strftime("%H:%M") for s in SLOT_TIMES_ET if now_et.time() >= s]
                if is_session_day else [])

    # THE STORED ROWS ARE THE TRUTH; `_slots_done` IS A PROXY THAT RESETS ON RESTART.
    # Railway restarts on every deploy, so a deploy at 13:00 would empty the in-memory set and
    # this surface would report the morning's slots as MISSED when they were captured and are
    # sitting in the table. That is the same fault as the post-close blindness above, pointing
    # the other way: one hid real misses, this would invent them -- and a surface that cries
    # after every deploy stops being read, which costs the real alarm.
    captured, source = set(_slots_done), "memory"
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        if pool is not None:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT DISTINCT slot_et FROM option_quote_capture"
                    " WHERE session_date = $1::date", now_et.date())
            # Union, not replacement: the DB is authoritative for what was stored, and the
            # in-memory set still knows about a slot captured seconds ago.
            captured |= {r["slot_et"] for r in rows}
            source = "stored_rows"
    except Exception as exc:                                        # noqa: BLE001
        # Named, never silent: "no slot was captured" and "I could not ask" are different
        # claims and only one of them is a fault in the capture.
        source = "memory (db unreadable: %s)" % type(exc).__name__

    missed = [s for s in expected if s not in captured]
    return {
        "job": JOB_NAME,
        "caller_tag": CALLER_TAG,
        "session_et_date": _session_et_date,
        "slots_expected_so_far": len(expected),
        "slots_captured": sorted(captured),
        "slots_missed": missed,
        #: Which of the two sources answered. `memory` after a restart means the figures
        #: describe this process only, not the session -- so the reader knows how far to
        #: trust `slots_missed` instead of assuming it is the session's truth.
        "coverage_source": source,
        "calls_used_session": _calls_used,
        "ceiling": session_ceiling(),
        "tag_registered": tag_is_registered(),
        "last_slot": dict(_last_result) if _last_result else None,
    }
