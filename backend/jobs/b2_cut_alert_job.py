"""The B2 three-day cut alert, wired — TA-141 §3 / R-IV.888(c)1, R-IV.892(e)1.

`models/b2_cut_alert.py` holds the DECISION and is pure. This holds the query, the clock, the
alert and the flag write, which is the whole of what can go wrong operationally.

FOUR THINGS THIS FILE IS CAREFUL ABOUT.

**Open is `open_quantity > 0`, computed from the lots** — never `status`, never a tag
(R-IV.844(d)3). A partial exit leaves a row OPEN with real remaining size, and a status string
has been the wrong question before.

**Realized comes from the closure ledger, not the row.** A partial exit's realized stays on an
OPEN row and the row's own column has been measured under-reporting the book by 107.48. The
decision function totals what it is given; sourcing it correctly is this file's job.

**The flag is written only after the alert is DELIVERED.** Flagging first would convert a failed
webhook into a permanent silence: the row would read "already fired" forever and the prompt
would never arrive. Phase 1's Hermes rule, for the same reason.

**It never closes anything.** The alert is a prompt; the decision module is asserted not to call
any execution path, and this file only ever writes the flag column.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("b2.cut_alert")

ET = ZoneInfo("America/New_York")
FLAG = "B2_CUT_ALERT_ENABLED"
JOB_NAME = "b2_cut_alert"

# R-IV.462(b): every machine writer names itself IN THE TRANSACTION that carries its write.
# Without it the audit trigger reads an empty setting and records 'legacy-ui' -- which is how
# 6,271 UPDATE rows became unattributable, 3,239 of them from the mark job alone. The suite
# caught this file writing anonymously before it shipped.
AUDIT_ACTOR = "b2-cut-alert-job"

# The flag column, added here so the ledger of "already fired" lives on the row it describes.
DDL_FLAG = (
    "ALTER TABLE unified_positions "
    "ADD COLUMN IF NOT EXISTS b2_cut_alerted_at TIMESTAMPTZ"
)

# THE COLUMN NAMES HERE WERE WRONG ON THE FIRST WRITING, and checking the schema rather than
# deploying caught it: `position_lots.quantity` and `position_lot_closures.realized_pnl` do not
# exist. The real names are `qty` and `realized`.
#
# open_quantity is NOT computed here AT ALL. `services/open_quantity.py` exists "so no consumer
# computes it" (R-IV.660(b)2) and does the whole list in one lot query -- a second
# implementation would be a second author of the rule that decides what is still open.
#
# realized DOES come from the closure ledger rather than unified_positions.realized_pnl, because
# a partial exit's realized stays on an OPEN row and the row's column has been measured
# under-reporting the book by 107.48. Same `SUM(c.realized)` shape the abacus and
# unified_positions readers already use.
#
# DUPLICATE_OF is excluded case-insensitively (R-IV.874): a retired duplicate's money counts
# once, on its keeper.
SELECT_SQL = """
SELECT p.position_id,
       p.ticker,
       p.bucket,
       p.status,
       p.entry_date,
       p.expiry,
       p.unrealized_pnl,
       -- TA-161 (R-IV.983(b)): the verdict is now computed from the gated mark, so the
       -- ENTRY BASIS PER UNIT is an input to it rather than something `unrealized_pnl` had
       -- already folded in. Gross of fees, as ruled. `open_quantity` is NOT selected here on
       -- purpose: `services.open_quantity.stamp_open_quantity` is the one author of it
       -- (R-IV.660(b)2) and is already applied to these rows below.
       p.entry_price,
       p.quantity,
       -- TA-152: the run-time mark reader needs the CONTRACT, not just the P&L. Without these
       -- four it could not price anything and every row read
       -- "structure None is not priceable" -- which the unit tests could not catch, because
       -- they hand `decide` a row directly and never go through this query.
       p.structure,
       -- R-IV.1043(f): the B2 cut reads `orientation_at_entry` when it is recorded, so the
       -- query has to SELECT it, or the column exists and this path cannot see it.
       --
       -- `position_orientation` is NOT selected, and must not be: no migration anywhere
       -- creates it. It was the name this code ANTICIPATED while waiting for a column, and
       -- `orientation_at_entry` is the column that actually arrived in R-IV.1043(e).
       -- Selecting the anticipated name would fail the whole query with UndefinedColumn and
       -- take the cut alert down -- the first-boot fault's mirror image, a read waiting on a
       -- writer that is never coming. A test asserts this list carries every column
       -- `orientation()` reads that the schema actually has.
       p.orientation_at_entry,
       p.long_strike,
       p.short_strike,
       p.b2_cut_alerted_at,
       COALESCE((SELECT SUM(c.realized) FROM position_lot_closures c
                  WHERE c.position_id = p.position_id), 0)          AS realized_pnl
  FROM unified_positions p
 WHERE UPPER(COALESCE(p.bucket, '')) = 'B2'
   AND UPPER(COALESCE(p.status, '')) <> 'DUPLICATE_OF'
"""


#: TA-152 columns. The mark the ALERT read, the instant it read it, and what that mark is worth
#: as evidence. Stored so the verdict can be audited against the number it was taken on.
DDL_MARK = """
    ALTER TABLE unified_positions
        ADD COLUMN IF NOT EXISTS mark NUMERIC,
        ADD COLUMN IF NOT EXISTS mark_as_of TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS mark_integrity TEXT,
        ADD COLUMN IF NOT EXISTS mark_integrity_reason TEXT
"""

#: The mark UPDATE is INLINED at its call site, not held here. The audit guard walks string
#: constants containing a write and requires an enclosing named transaction; a module-level
#: constant has none, so it reads as unnamed however carefully the call site is wrapped. The
#: flag write at the bottom of this file follows the same convention.

_OPT_TYPE = {"put_debit_spread": "put", "put_credit_spread": "put", "long_put": "put",
             "call_debit_spread": "call", "call_credit_spread": "call", "long_call": "call"}


async def read_mark_now(row: Dict[str, Any]) -> Dict[str, Any]:
    """THE ALERT'S OWN MARK, read now and stamped with now. NEVER raises.

    TA-152 requires the alert to read its own mark at run time rather than trust the stored one,
    and the reason is arithmetic rather than caution: the hub's mark refreshes run at 09:17 and
    16:47 ET while this alert runs at 16:15 ET -- BETWEEN them. The stored mark at alert time is
    therefore always the MORNING one, which is never "at or after the cut session's close".
    Without this read every B2 row would return UNDETERMINED every single day.

    ONE CHAIN FETCH PER ROW, so the mark and the width of the book it came from are measured
    from the SAME data at the SAME instant. Taking them from two calls would allow a mark from
    one moment to be judged by a book from another, which is the leg-mismatch root
    DEF-NEGATIVE-SPREAD-MARK already closed once.

    The strict `compute_mark` rule is used, not the wider mid fallback: a mark is a claim about
    what the principal holds right now.
    """
    from models.mark_integrity import evaluate as integrity_of

    read_at = datetime.now(timezone.utc)
    out = {"mark": None, "mark_as_of": read_at, "mark_integrity": None,
           "mark_integrity_reason": None, "bid": None, "ask": None}
    ticker = (row.get("ticker") or "").upper()
    structure = (row.get("structure") or "").strip().lower()
    try:
        if not ticker:
            raise ValueError("no ticker")
        if structure == "stock":
            # R-IV.983: via the ONE author of "the current spot". This path used
            # get_snapshot(), which needs a SECOND UW call (/ohlc/1d, caller `ohlc_bars`) that
            # has been seen governor-BLOCKED -- and on 2026-10-13 that returned NO mark for
            # TSLQ, so `mark_integrity` read "unknown" and under TA-161 the cut could not be
            # evaluated at all. /stock-state answers in one call.
            from integrations.spot_price import spot_now
            px, src, vendor_ts = await spot_now(ticker)
            out["mark"] = px
            out["spot_source"] = src
            if vendor_ts:
                out["vendor_timestamp"] = vendor_ts
        elif "+" in structure:
            # A composite row holds two structures; pricing it as one would invent a contract.
            out["mark_integrity"] = "unknown"
            out["mark_integrity_reason"] = (
                "composite structure %r: two structures in one row, so there is no single "
                "contract to price" % row.get("structure"))
            return out
        else:
            opt = _OPT_TYPE.get(structure)
            ls, ss = row.get("long_strike"), row.get("short_strike")
            expiry = row.get("expiry")
            if not opt or ls is None or not expiry:
                raise ValueError("structure %r is not priceable" % row.get("structure"))
            from integrations.uw_api import _find_contract, get_options_snapshot
            from utils.options_math import compute_bid_ask_spread_pct, compute_mark
            strikes = [float(ls)] + ([float(ss)] if ss is not None else [])
            chain = await get_options_snapshot(
                ticker, expiration_date=str(expiry)[:10],
                strike_gte=min(strikes) - 0.5, strike_lte=max(strikes) + 0.5,
                contract_type=opt)
            if not chain:
                raise ValueError("the vendor returned no chain")
            legs, widths = [], []
            for strike in strikes:
                c = _find_contract(chain, strike, str(expiry)[:10], opt)
                if not c:
                    raise ValueError("strike %g not in the vendor's chain" % strike)
                m, why = compute_mark(c)
                if m is None:
                    raise ValueError("%g: %s" % (strike, why))
                legs.append(m)
                w = compute_bid_ask_spread_pct(c)
                q2 = c.get("last_quote") or {}
                from models.mark_integrity import abs_spread
                aw = abs_spread(q2.get("bid"), q2.get("ask"))
                if w is not None and aw is not None:
                    widths.append((w, aw))
                q = c.get("last_quote") or {}
                if out["bid"] is None:
                    out["bid"], out["ask"] = q.get("bid"), q.get("ask")
            net = legs[0] - legs[1] if len(legs) == 2 else legs[0]
            out["mark"] = round(float(net), 4)
            # THE WORST LEG GOVERNS. A spread is only as tradeable as its less tradeable side,
            # so a tight leg must not average away a leg nobody is quoting.
            if widths:
                # (pct, abs) for the worst leg BY PERCENTAGE, kept together so the absolute
                # floor can be applied to the same leg rather than to a different one.
                out["worst_leg"] = max(widths, key=lambda w: w[0])
    except Exception as exc:                                        # noqa: BLE001
        out["mark_integrity"] = "unknown"
        out["mark_integrity_reason"] = "could not read a mark: %s" % exc
        return out

    verdict, reason = integrity_of(out["mark"], mark_as_of=read_at,
                                   bid=out.get("bid"), ask=out.get("ask"), now=read_at)
    # A wide leg is `wide` even when the net happens to look sane.
    worst = out.get("worst_leg")
    if verdict == "ok" and worst is not None:
        from models.mark_integrity import (WIDE_SPREAD_MIN_ABS, WIDE_SPREAD_PCT, is_wide)
        wp, wa = worst
        if is_wide(wp, wa):
            verdict = "wide"
            reason = ("the worst leg's book is %.0f%% of mid and %s wide, over the %.0f%% / %s "
                      "bounds" % (wp, wa, WIDE_SPREAD_PCT, WIDE_SPREAD_MIN_ABS))
    out["mark_integrity"] = verdict
    out["mark_integrity_reason"] = reason
    return out


def is_enabled() -> bool:
    """Empty-safe: Railway returns '' for an unset reference, so `or ""` then compare."""
    return (os.getenv(FLAG) or "").strip().lower() in ("1", "true", "yes", "on")


async def evaluate(now: Optional[datetime] = None, *, pool=None) -> List[Dict[str, Any]]:
    """Every B2 row's verdict. NEVER RAISES. Read-only; writes nothing."""
    from models.b2_cut_alert import decide, is_in_scope

    now = now or datetime.now(ET)
    out: List[Dict[str, Any]] = []
    try:
        if pool is None:
            from database.postgres_client import get_postgres_client
            pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(DDL_FLAG)
            await conn.execute(DDL_MARK)
            rows = [dict(r) for r in await conn.fetch(SELECT_SQL)]
            # The one author for "what is still open", one lot query for the whole list.
            from services.open_quantity import stamp_open_quantity
            await stamp_open_quantity(conn, rows)
    except Exception as exc:                                        # noqa: BLE001
        logger.error("[b2.cut_alert] could not read positions: %s", exc)
        return out

    for row in rows:
        if not is_in_scope(row):
            continue
        # TA-152: the alert reads its OWN mark, now, and stores it before deciding on it.
        fresh = await read_mark_now(row)
        row["mark"] = fresh["mark"]
        row["mark_as_of"] = fresh["mark_as_of"]
        row["mark_integrity"] = fresh["mark_integrity"]
        row["mark_integrity_reason"] = fresh["mark_integrity_reason"]
        try:
            async with pool.acquire() as conn:
                # NAMED, in its own transaction. SET LOCAL only takes effect inside one, and an
                # unnamed UPDATE is recorded by the audit as `legacy-ui` -- the attribution
                # failure R-IV.462(b) exists to prevent. The audit guard caught this write
                # exactly as it caught the flag write under R-IV.892.
                async with conn.transaction():
                    await conn.execute("SELECT set_config('app.actor', $1, true)", AUDIT_ACTOR)
                    await conn.execute(
                        "SELECT set_config('app.reason', $1, true)",
                        "TA-152: the alert's own post-close mark read for the cut session")
                    await conn.execute(
                        "UPDATE unified_positions "
                        "   SET mark = $2, mark_as_of = $3, mark_integrity = $4, "
                        "       mark_integrity_reason = $5 "
                        " WHERE position_id = $1",
                        row.get("position_id"), fresh["mark"], fresh["mark_as_of"],
                        fresh["mark_integrity"], fresh["mark_integrity_reason"])
        except Exception as exc:                                    # noqa: BLE001
            # A mark that could not be STORED was still READ; the verdict stands on it and the
            # failure is recorded rather than turning into a missing mark.
            logger.warning("[b2.cut_alert] could not store the mark for %s: %s",
                           row.get("position_id"), exc)
        verdict = decide(row, now=now)
        verdict["mark_integrity_reason"] = fresh["mark_integrity_reason"]
        verdict["position_id"] = row.get("position_id")
        verdict["ticker"] = row.get("ticker")
        out.append(verdict)
    return out


async def run(now: Optional[datetime] = None, *, pool=None) -> Dict[str, Any]:
    """Evaluate, alert on each NOT_PROFITABLE, flag only what was delivered. NEVER RAISES.

    R-IV.1005(b): the verdict describes the POSITION and alerting is the action taken on it, so
    "have we already alerted" is now a separate field rather than a verdict that displaced the
    P&L answer. This function owns that decision; `decide()` does not.
    """
    from models.b2_cut_alert import NOT_EVALUABLE, NOT_PROFITABLE, UNDETERMINED

    verdicts = await evaluate(now, pool=pool)
    counts: Dict[str, int] = {}
    for v in verdicts:
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1

    # UNDETERMINED is logged at WARNING every pass, deliberately: a position nobody can price at
    # its cut is a gap in the alert's coverage, and a silent gap looks exactly like a pass.
    #
    # NOT_EVALUABLE (TA-161) is logged the same way and for the same reason, but it is a
    # DIFFERENT gap: UNDETERMINED means retry tomorrow, NOT_EVALUABLE means this row cannot be
    # evaluated under the definition at all. Collapsing the two would turn a permanent hole in
    # the coverage into one that merely looks transient.
    for v in verdicts:
        if v["verdict"] in (UNDETERMINED, NOT_EVALUABLE):
            logger.warning("[b2.cut_alert] %s (%s) %s at its cut: %s%s",
                           v.get("ticker"), v.get("position_id"), v["verdict"],
                           v.get("reason"),
                           " [already alerted %s]" % v["b2_cut_alerted_at"]
                           if v.get("already_alerted") else "")

    # The divergence between the two writers of the same fact is reported wherever it is
    # found, on any verdict -- it is the finding TA-161 exists to surface.
    for v in verdicts:
        if v.get("pnl_divergence"):
            d = v["pnl_divergence"]
            logger.warning("[b2.cut_alert] %s (%s) PNL DIVERGENCE: cut_pnl %s @ %s vs "
                           "unrealized_pnl %s @ %s (difference %s)",
                           v.get("ticker"), v.get("position_id"), d.get("cut_pnl"),
                           d.get("cut_pnl_as_of"), d.get("unrealized_pnl"),
                           d.get("unrealized_pnl_as_of"), d.get("difference"))

    fired = 0
    for v in verdicts:
        # NOT_PROFITABLE is the verdict; alerting is the action. A row already alerted on
        # keeps its verdict and is simply not alerted again -- it fires once.
        if v["verdict"] != NOT_PROFITABLE:
            continue
        if v.get("already_alerted"):
            logger.info("[b2.cut_alert] %s (%s) is %s but was already alerted at %s; "
                        "not alerting again", v.get("ticker"), v.get("position_id"),
                        NOT_PROFITABLE, v.get("b2_cut_alerted_at"))
            continue
        if not is_enabled():
            # The flag gates the PUSH, not the evaluation, so a live book can be watched
            # before anything reaches the phone.
            logger.info("[b2.cut_alert] WOULD ALERT (flag off): %s %s", v.get("ticker"),
                        v.get("reason"))
            continue
        if await _deliver(v) and await _mark_fired(v, pool=pool):
            fired += 1

    return {"evaluated": len(verdicts), "by_verdict": counts, "fired": fired,
            "enabled": is_enabled(), "rows_touched": fired}


def _describe_mark(v: Dict[str, Any]) -> str:
    """R-IV.935(c)3: the mark, its timestamp and its flag, printed in the alert body.

    A verdict about money should be auditable from the message that carries it, without going
    to the database to find out which number it was taken on.
    """
    from models.mark_integrity import describe
    return describe(v.get("mark_integrity"), v.get("mark_integrity_reason"),
                    v.get("mark"), v.get("mark_as_of"))


async def _deliver(v: Dict[str, Any]) -> bool:
    """One message. Returns True only on a delivered alert; NEVER RAISES."""
    import httpx

    url = os.getenv("DISCORD_WEBHOOK_ALERTS") or ""
    if not url:
        logger.error("[b2.cut_alert] DISCORD_WEBHOOK_ALERTS not set; %s not alerted",
                     v.get("ticker"))
        return False
    content = (
        "**B2 three-day cut — %s**\n"
        "Total P&L %s at the close of the 3rd full trading session (%s).\n"
        "%s\n"
        "This is a prompt, not an action: nothing has been closed."
        % (v.get("ticker"), v.get("total_pnl"), v.get("cut_session"),
           _describe_mark(v))
    )
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(url, json={"content": content})
        if resp.status_code >= 300:
            logger.error("[b2.cut_alert] discord HTTP %d for %s", resp.status_code,
                         v.get("ticker"))
            return False
    except Exception as exc:                                        # noqa: BLE001
        logger.error("[b2.cut_alert] delivery failed for %s: %s", v.get("ticker"),
                     type(exc).__name__)
        return False

    # R-IV.901(b)2/(b)3: the phone relay runs in parallel until the principal confirms. The
    # ntfy payload is NOT this Discord text -- the Discord line carries the dollar P&L, and a
    # third-party relay must carry no dollar amount, account value or position size. So the
    # phone is told WHICH position and WHAT to do, and the figure stays on the channel we own.
    try:
        from integrations.ntfy_push import is_configured
        from integrations.ntfy_push import send as ntfy_send
        if is_configured():
            await ntfy_send(v.get("ticker") or "?", "B2 three-day cut",
                            "not profitable at the 3rd-session close; review it. "
                            "Nothing has been closed.")
    except Exception as exc:                                        # noqa: BLE001
        # Never affects the Discord verdict: the alert HAS been delivered.
        logger.warning("[b2.cut_alert] ntfy leg failed for %s: %s", v.get("ticker"),
                       type(exc).__name__)
    return True


async def _mark_fired(v: Dict[str, Any], *, pool=None) -> bool:
    """Flag the row. Only reached after a DELIVERED alert, so a webhook failure leaves the row
    un-flagged and the next pass tries again rather than going permanently quiet."""
    try:
        if pool is None:
            from database.postgres_client import get_postgres_client
            pool = await get_postgres_client()
        async with pool.acquire() as conn:
            # SET LOCAL only takes effect inside a transaction; without one the setting is read
            # back empty and the audit falls through to 'legacy-ui'. Scoped to this transaction,
            # so concurrent passes cannot see each other's actor.
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.actor', $1, true)", AUDIT_ACTOR)
                await conn.execute(
                    "SELECT set_config('app.reason', $1, true)",
                    "B2 three-day cut alert delivered for session %s" % (v.get("cut_session"),))
                await conn.execute(
                    "UPDATE unified_positions SET b2_cut_alerted_at = NOW() "
                    "WHERE position_id = $1 AND b2_cut_alerted_at IS NULL",
                    v.get("position_id"))
        return True
    except Exception as exc:                                        # noqa: BLE001
        # The alert WENT OUT and the flag did not. ERROR, because the next pass will send it
        # again -- a duplicate prompt, which is the safe direction but worth knowing about.
        logger.error("[b2.cut_alert] ALERT SENT BUT NOT FLAGGED for %s: %s — it will repeat",
                     v.get("position_id"), type(exc).__name__)
        return False
