"""CIRCE'S STEW daily pass (R-IV.421, R-IV.422, R-IV.429(b)) -- B2 daily, SHADOW.

Once per trading session, after the close:

  1. UNIVERSE   tickers PYTHIA has covered in the last few sessions. Location is part of the
                trigger, so a name with no VA cannot pass it; covering it would only add rows
                that are unsurfaceable by construction.
  2. BARS       yfinance daily, fetched fresh, split- and dividend-adjusted (bars_yf's basis).
                A ticker is evaluated only if its last bar IS this session.
  3. TRIGGER    scanners.circes_stew.detect -- pure, no I/O.
  4. JOIN       R-IV.422, one join and no new source: the prior session's VA (pythia_events),
                the sector-rotation regime (the cached rotation, one classifier), IV rank
                (universe cache), and the latest stored flow snapshot. ZERO UW calls.
  5. GATE       location outside|edge passes; mid or unknown does not.
  6. CEILING    more than DAILY_CEILING passing fires in a day is a firehose: NONE are
                surfaced, an alert fires, and the feed STAYS stopped (a latch keyed on the
                gate version) until the gate is tightened and GATE_VERSION bumped.
  7. PERSIST    EVERY geometric trigger is written with its full payload (R-IV.421(e)).
                Surfaced rows carry source=circes_stew; the rest circes_stew_unsurfaced
                with the reason. All are status SHADOW and carry the L0 suppress tag, which
                keeps them off every actionable surface -- the River reads them explicitly
                with /api/trade-ideas?status=SHADOW&source=circes_stew.

Not scored, not sized, never routed through process_signal_unified (no committee, no
Discord trade post, no broadcast). A PENDING outcome row is written so the grader and the
backtest module can grade what the shadow collects.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pytz

from scanners import circes_stew as cs

logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")

JOB_NAME = "circes_stew"
RUN_TIME_ET = (16, 30)            # after the close; clear of the 16:15 job start
RETRY_EVERY_S = 15 * 60
RETRY_UNTIL_HOUR_ET = 20          # last attempts start before 21:00, clear of the nightly
ALARM_FROM_HOUR_ET = 18           # unpublished bars before this are a wait, not a failure
UNIVERSE_SESSIONS = 5             # "recently covered by PYTHIA"
BAR_CALENDAR_DAYS = 75            # ~50 trading days >> N + window + 1
BATCH_SIZE = 100
MIN_SESSION_COVERAGE = 0.5        # below this the session's bars are not published yet

# Bump when the location gate (or anything else that decides surfacing) changes. It
# releases the firehose latch, which is what R-IV.421(d) asks for: the feed continues
# only once the gate has been tightened.
GATE_VERSION = "circe-gate-v1"

PRICE_BASIS = "yfinance daily, auto_adjust=True (split+dividend adjusted), fetched at run time"
FLOW_GAP = ("no per-bar dark-pool or put-sweep store exists; this is the latest stored "
            "flow_events snapshot captured on the fire date, if any")


class SessionBarsUnavailable(RuntimeError):
    """The session's daily bars are not (yet) published. Retryable."""


# ── pure helpers ─────────────────────────────────────────────────────────────

def session_close_utc(session_date: date) -> datetime:
    return ET.localize(datetime.combine(session_date, dtime(16, 0))).astimezone(timezone.utc)


def clean_frame(frame):
    """Rows with a real high, low and close, ascending. None if nothing usable."""
    if frame is None or len(frame) == 0:
        return None
    f = frame.dropna(subset=["h", "l", "c"]).sort_values("date")
    return f if len(f) else None


def va_zone(price: Optional[float], vah: Optional[float], val: Optional[float],
            edge_fraction: float = cs.VA_EDGE_FRACTION) -> Optional[str]:
    """Which side of the VA -- detail for grading; `cs.va_location` is the gate's 3-state."""
    loc = cs.va_location(price, vah, val, edge_fraction)
    if loc is None:
        return None
    if loc == "outside":
        return "above_vah" if price > vah else "below_val"
    if loc == "edge":
        return "upper_edge" if price >= (vah + val) / 2 else "lower_edge"
    return "mid"


def _f(v) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def build_candidate(ticker: str, trig: "cs.Trigger", va: Optional[Dict[str, Any]],
                    rotation: Optional[Dict[str, Any]], sector_etf: Optional[str],
                    universe: Optional[Dict[str, Any]], flow: Optional[Dict[str, Any]],
                    fetched_at: str) -> Dict[str, Any]:
    """Everything known about one trigger, before the ceiling decides surfacing."""
    vah = va.get("vah") if va else None
    val = va.get("val") if va else None
    location = cs.va_location(trig.close, vah, val)
    gate_pass = cs.passes_location_gate(location)
    if gate_pass:
        reason = None
    elif va is None:
        reason = "no_prior_session_va"
    elif location is None:
        reason = "va_unusable"
    else:
        reason = f"location_{location}"

    regime = rotation.get("regime") if rotation else None
    iv_rank = _f((universe or {}).get("iv_rank"))

    payload = {
        "v": 1,
        "strategy": cs.STRATEGY_ID,
        "name": cs.DISPLAY_NAME,
        "lineage": cs.LINEAGE,
        "banner": cs.BANNER,
        "gate_version": GATE_VERSION,
        "timeframe": "B2_daily",
        "n_bars": cs.N_BARS,
        "confirm_window_bars": cs.CONFIRM_BARS,
        "ticker": ticker,
        "direction": trig.direction,
        "trigger": trig.as_dict(),     # level breached, breach bar, close-back-inside bar
        "levels": cs.levels(trig),
        "va": {
            "location": location,
            "zone": va_zone(trig.close, vah, val),
            "located_price": "fire_close",
            "extreme_location": cs.va_location(trig.extreme, vah, val),
            "edge_fraction": cs.VA_EDGE_FRACTION,
            "vah": vah, "val": val, "poc": (va or {}).get("poc"),
            "va_session": (va or {}).get("va_session"),
            "as_of": (va or {}).get("as_of"),
        },
        "sector_rotation": {
            "state": regime,
            "sector_etf": sector_etf,
            "sector_state": (rotation or {}).get("states", {}).get(sector_etf) if sector_etf else None,
            "n_sectors": (rotation or {}).get("n_sectors"),
            "as_of": (rotation or {}).get("as_of"),
        },
        "iv": {
            "iv_rank": iv_rank,
            "source": "universe_cache",
            "as_of": (universe or {}).get("refreshed_at"),
            "structure_hint": cs.structure_hint(iv_rank, trig.direction),
            "role": "structure only, never a filter",
        },
        "flow": flow if flow else {"present": False},
        "flow_gap": FLOW_GAP,
        "price_basis": {"basis": PRICE_BASIS, "fetched_at": fetched_at},
        "gate_pass": gate_pass,
        "gate_reject_reason": reason,
    }
    return {"ticker": ticker, "trigger": trig, "gate_pass": gate_pass,
            "location": location, "regime": regime, "payload": payload}


def decide_surfacing(candidates: List[Dict[str, Any]], latched: Optional[bool],
                     ceiling: int = cs.DAILY_CEILING) -> Tuple[bool, str]:
    """Mark each candidate surfaced / unsurfaced in place. Returns (firehose_today, feed_state).

    `latched` is TRI-STATE: None means the latch could not be read, and an unreadable latch
    does not surface -- this is a shadow feed, so withholding it costs nothing, while
    surfacing through an unknown stop is exactly what the stop exists to prevent. Every
    candidate is persisted either way.
    """
    passing = [c for c in candidates if c["gate_pass"]]
    surfaced, firehose = cs.apply_ceiling(passing, ceiling)
    if firehose:
        state = "firehose"
    elif latched is True:
        state, surfaced = "latched", []
    elif latched is None:
        state, surfaced = "latch_unreadable", []
    else:
        state = "open"
    chosen = {id(c) for c in surfaced}
    for c in candidates:
        c["surfaced"] = id(c) in chosen
        if c["surfaced"]:
            c["unsurfaced_reason"] = None
        elif not c["gate_pass"]:
            c["unsurfaced_reason"] = c["payload"]["gate_reject_reason"]
        else:
            c["unsurfaced_reason"] = {"firehose": "firehose", "latched": "firehose_latched",
                                      "latch_unreadable": "latch_unreadable"}[state]
        c["payload"].update({
            "surfaced": c["surfaced"],
            "unsurfaced_reason": c["unsurfaced_reason"],
            "feed_state": state,
            "passing_today": len(passing),
            "daily_ceiling": ceiling,
        })
    return firehose, state


def build_signal_data(c: Dict[str, Any], session_date: date) -> Dict[str, Any]:
    trig, lv = c["trigger"], c["payload"]["levels"]
    return {
        "signal_id": cs.signal_id(c["ticker"], trig),
        "timestamp": session_close_utc(session_date),
        "strategy": cs.STRATEGY_ID,
        "signal_type": cs.SIGNAL_TYPE,
        "source": cs.SOURCE_SURFACED if c["surfaced"] else cs.SOURCE_UNSURFACED,
        "ticker": c["ticker"],
        "asset_class": "EQUITY",
        "direction": trig.direction,
        "entry_price": lv["entry"],
        "stop_loss": lv["stop"],
        "target_1": lv["target_1"],
        "risk_reward": cs.TARGET_R_MULTIPLE,
        "timeframe": "D",
        "status": "SHADOW",
        "feed_tier": "research_log",
        "notes": cs.BANNER,
        "triggering_factors": {
            # Same belt-and-braces as the STRIKE shadow: status alone does not cover the
            # legacy surfaces that filter only on user_action.
            "l0_shadow": {
                "v": 1, "mode": "enforce", "signal_type": cs.SIGNAL_TYPE, "rule": "SUPPRESS",
                "would_suppress": True, "is_liquid": None,
                "reason": "CIRCE'S STEW shadow -- unbacktested, not promoted",
            },
            "circes_stew": c["payload"],
        },
        # R-IV.422 join, written to its own columns after the insert.
        "va_location": c["location"],
        "sector_rotation_state": c["regime"],
    }


# ── I/O ──────────────────────────────────────────────────────────────────────

def _fetch_bars(tickers: List[str], session_date: date) -> Dict[str, Any]:
    from stable_engine import bars_yf
    start = session_date - timedelta(days=BAR_CALENDAR_DAYS)
    end = session_date + timedelta(days=1)          # yfinance `end` is exclusive
    out: Dict[str, Any] = {}
    for i in range(0, len(tickers), BATCH_SIZE):
        out.update(bars_yf.fetch_batch(tickers[i:i + BATCH_SIZE], start, end))
    return out


async def _universe(conn, session_date: date) -> List[str]:
    since = session_date - timedelta(days=UNIVERSE_SESSIONS * 2)
    rows = await conn.fetch(
        "SELECT DISTINCT ticker FROM pythia_events WHERE timestamp >= $1::timestamptz",
        ET.localize(datetime.combine(since, dtime(0, 0))).astimezone(timezone.utc),
    )
    return sorted({r["ticker"].upper() for r in rows
                   if r["ticker"] and r["ticker"].replace(".", "").isalpha()})


async def firehose_latched(conn) -> Optional[bool]:
    """TRI-STATE. True if any firehose day exists under the current gate version."""
    try:
        found = await conn.fetchval(
            """
            SELECT 1 FROM signals
            WHERE source = $1
              AND triggering_factors -> 'circes_stew' ->> 'feed_state' = 'firehose'
              AND triggering_factors -> 'circes_stew' ->> 'gate_version' = $2
            LIMIT 1
            """,
            cs.SOURCE_UNSURFACED, GATE_VERSION,
        )
        return found is not None
    except Exception as exc:
        logger.warning("[circes_stew] firehose latch unreadable: %s", exc)
        return None


async def _flow_snapshot(conn, ticker: str, session_date: date) -> Optional[Dict[str, Any]]:
    try:
        r = await conn.fetchrow(
            """
            SELECT pc_ratio, call_volume, put_volume, call_premium, put_premium,
                   flow_sentiment, source, captured_at
            FROM flow_events
            WHERE ticker = $1 AND captured_at >= $2::timestamptz AND captured_at < $3::timestamptz
            ORDER BY captured_at DESC LIMIT 1
            """,
            ticker,
            ET.localize(datetime.combine(session_date, dtime(0, 0))).astimezone(timezone.utc),
            ET.localize(datetime.combine(session_date + timedelta(days=1), dtime(0, 0))).astimezone(timezone.utc),
        )
    except Exception as exc:
        logger.debug("[circes_stew] flow read failed for %s: %s", ticker, exc)
        return None
    if r is None:
        return None
    cp, pp = _f(r["call_premium"]), _f(r["put_premium"])
    return {
        "present": True,
        "pc_ratio": _f(r["pc_ratio"]),
        "call_volume": r["call_volume"], "put_volume": r["put_volume"],
        "call_premium": cp, "put_premium": pp,
        "net_put_premium": (pp - cp) if (cp is not None and pp is not None) else None,
        "flow_sentiment": r["flow_sentiment"],
        "source": r["source"],
        "as_of": r["captured_at"].isoformat() if r["captured_at"] else None,
    }


async def _write_join_columns(conn, sd: Dict[str, Any]) -> None:
    """R-IV.422's two columns, by a separate statement: if the boot ALTER was ever skipped
    the signal still persists, and this failure is loud."""
    try:
        await conn.execute(
            "UPDATE signals SET va_location = $2, sector_rotation_state = $3 WHERE signal_id = $1",
            sd["signal_id"], sd.get("va_location"), sd.get("sector_rotation_state"),
        )
    except Exception as exc:
        logger.error("[circes_stew] join columns not written for %s: %s", sd["signal_id"], exc)


async def _alert_firehose(session_date: date, n_passing: int) -> None:
    try:
        from bias_engine.anomaly_alerts import send_alert
        await send_alert(
            "CIRCE'S STEW firehose -- feed stopped",
            f"{n_passing} fires passed the location gate on {session_date} (ceiling "
            f"{cs.DAILY_CEILING}). Nothing was surfaced and the feed stays stopped until the "
            f"location gate is tightened and GATE_VERSION ({GATE_VERSION}) is bumped. Every "
            f"trigger was still persisted.",
            severity="warning",
        )
    except Exception as exc:
        logger.warning("[circes_stew] firehose alert failed: %s", exc)


async def run_circes_stew(session_date: date) -> Dict[str, Any]:
    """One pass. Raises on a failure worth retrying; returns counts otherwise."""
    from database.postgres_client import get_postgres_client, log_signal
    from enrichment.signal_enricher import persist_enrichment
    from enrichment.universe_cache import get_universe_data
    from services.read_only.market_profile import get_prior_session_vas
    from services.read_only.sectors import get_sector_rotation, resolve_sector_etf, rotation_snapshot
    from signals.pipeline import write_signal_outcome
    from stable_engine.signals_freshness import record_attempt

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        tickers = await _universe(conn, session_date)
    if not tickers:
        raise RuntimeError("no PYTHIA-covered tickers in the last %d sessions" % UNIVERSE_SESSIONS)

    fetched_at = datetime.now(timezone.utc).isoformat()
    frames = await asyncio.to_thread(_fetch_bars, tickers, session_date)
    current = {}
    for t, f in frames.items():
        f = clean_frame(f)
        if f is not None and f["date"].iloc[-1] == session_date:
            current[t] = f
    # Coverage is measured against what Yahoo returned at all, so symbols it cannot resolve
    # (PYTHIA also covers non-equities) do not read as an unpublished session.
    if not frames or len(current) / len(frames) < MIN_SESSION_COVERAGE:
        raise SessionBarsUnavailable(
            f"{len(current)}/{len(frames)} returned tickers have a {session_date} bar "
            f"({len(tickers)} requested)")

    triggers = [(t, trig) for t, f in current.items() for trig in cs.detect(f)]
    rotation = rotation_snapshot(await get_sector_rotation())

    candidates = []
    async with pool.acquire() as conn:
        vas = await get_prior_session_vas(conn, [t for t, _ in triggers], session_date)
        for t, trig in triggers:
            candidates.append(build_candidate(
                t, trig, vas.get(t), rotation,
                await resolve_sector_etf(conn, t),
                await get_universe_data(t),
                await _flow_snapshot(conn, t, trig.fire_date),
                fetched_at,
            ))
        latched = await firehose_latched(conn)

    firehose, feed_state = decide_surfacing(candidates, latched)
    if firehose:
        await _alert_firehose(session_date, sum(c["gate_pass"] for c in candidates))

    stats = {"session": session_date.isoformat(), "universe": len(tickers),
             "returned": len(frames), "with_session_bar": len(current), "triggers": len(candidates),
             "gate_pass": sum(c["gate_pass"] for c in candidates),
             "surfaced": 0, "persisted": 0, "deduped": 0, "errors": 0,
             "feed_state": feed_state, "va_known": sum(c["location"] is not None for c in candidates)}

    for c in candidates:
        sd = build_signal_data(c, session_date)
        try:
            inserted = await log_signal(sd)
        except Exception as exc:  # noqa: BLE001
            stats["errors"] += 1
            record_attempt(sd["source"], False, str(exc))
            logger.error("[circes_stew] insert failed for %s: %s", sd["signal_id"], exc)
            continue
        if not inserted:
            stats["deduped"] += 1
            record_attempt(sd["source"], False)
            continue
        stats["persisted"] += 1
        stats["surfaced"] += int(c["surfaced"])
        record_attempt(sd["source"], True)
        async with pool.acquire() as conn:
            await _write_join_columns(conn, sd)
        await persist_enrichment(sd["signal_id"], {
            "iv_rank": c["payload"]["iv"]["iv_rank"],
            "iv_rank_source": "universe_cache",
            "enriched_at": datetime.now(timezone.utc).isoformat(),
        })
        await write_signal_outcome(sd)

    if stats["errors"] and stats["errors"] == len(candidates):
        raise RuntimeError("every CIRCE insert failed: %s" % stats)
    logger.info("[circes_stew] pass complete: %s", stats)
    return stats
