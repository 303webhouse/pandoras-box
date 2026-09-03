"""STRIKE-SPEC-01 — IB-break -> shadow signal converter + per-ticker watermarks.

Brief: docs/codex-briefs/2026-08-28-strike-spec-01-ib-break-converter-brief.md
Addendum: docs/codex-briefs/2026-09-02-strike-spec-01-addendum.md (spine R-IV.150)

Turns the FIRST qualifying ib_break_up / ib_break_down per ticker/direction/session
from pythia_events into a status='SHADOW' row in the existing signals pipeline --
graded by the canonical 15-min resolver, invisible to every actionable surface --
to collect the n>=50 both-direction sample gating STRIKE promotion.

BINDING CONDITIONS (Titans, non-negotiable -- do not relax without a new ruling):

 1. Write via log_signal() DIRECTLY. NEVER route through process_signal_unified():
    its step-4f conflict check (backend/signals/pipeline.py:851) dismisses live
    opposite-direction rows, which makes the ib_reversal second emission
    structurally impossible.
 2. Every emitted row carries BOTH status='SHADOW' AND the L0 tag
    triggering_factors.l0_shadow.would_suppress=True. Neither alone covers all
    read surfaces.
 3. STRIKE_IB_BREAK is registered in stable_engine/signals_freshness.py
    (SLO 5 days, RTH-gated). An unregistered ~1/day source false-pages the
    persistence watchdog daily.
 4. Per-ticker watermarks ship WITH the converter (R-IV.109(c)). Liveness
    reference = ANY pythia_events row for the ticker in the current session (all
    alert types), NOT IB events only -- a balanced day legitimately produces zero
    IB breaks. This is the OBS-0-class liveness sentinel for this instrument
    (addendum section 1); do not add a second one.
 5. Ticker allowlist is a CODE CONSTANT (not env, not DB). Every entry requires a
    verified dedicated per-symbol TradingView alert (R-IV.109(e)).
 6. expires_at = entry session + 3 trading sessions. Promotion-gate analysis
    treats outcome_resolved_at > expires_at as EXPIRED, not WIN/LOSS.
 7. Validation rejects are converter-level log lines + strike_ib_session_counts
    .rejects. They are NEVER passed to record_attempt() as `rejected` -- that
    would page the persistence alarm on correct behavior. record_attempt() fires
    only on actual INSERT attempts (persisted / db-error / dedupe).
 8. NO UW calls in the converter, v1. Gap-vs-ATR and other score inputs are
    deferred; raw event fields are stored as metadata only.
 9. Shadow-only. Dry-run first RTH session (STRIKE_IB_DRY_RUN=true), then flip
    off. Kill switch: STRIKE_IB_ENABLED=false.

NO DAILY-RATE BAND, and that is deliberate (addendum section 2). Per ticker per
session the IB-break count is structurally {0, 1, 2} with 0 legitimate. A band over
that distribution is a period average wearing a distribution's clothes -- the
ARTEMIS class. strike_ib_session_counts accumulates the real per-ticker daily
distributions from first deploy; any future band derives from THAT table, once
n-gated, never from a period total.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

# R-IV.109(e): every ticker here MUST hold a verified dedicated per-symbol
# TradingView alert. Prey-list / watchlist coverage is NEVER a valid upstream --
# a ~240-symbol watchlist alert has ~39 calc slots and the survivor set reshuffles
# on every watchlist edit, which is how three separate feed outages went
# undetected. Adding a ticker here without a dedicated alert violates the ruling.
STRIKE_TICKER_ALLOWLIST = frozenset({"QQQ", "IWM", "SMH", "DIA", "XLF", "XLK", "XLE", "TLT"})

# Structural max: one emission per ticker per direction per session. Reaching it
# means dedup is broken, not that the market was busy.
SESSION_CAP = 2 * len(STRIKE_TICKER_ALLOWLIST)

CYCLE_SECONDS = 300
BOOT_DELAY_SECONDS = 300
LATCH_TTL = 7200  # ~2h -- one alarm per dead episode, not per cycle

# Watermark alarm does not arm until a ticker has been seen alive this many
# distinct sessions. Absence dates nothing until the expected event rate is
# established across it; below this n the state renders INSUFFICIENT, never OK.
BASELINE_SESSIONS_GATE = 3
ALARM_AFTER_ET = dtime(11, 0)

# Validation bounds (AEGIS A1/A2/A3).
PRICE_LOW_MULT = 0.8
PRICE_HIGH_MULT = 1.2
MAX_IB_HEIGHT_FRAC = 0.05  # ib_height must be <= 5% of price

EXPIRY_SESSIONS = 3
EXPIRY_HOUR_UTC = 20


def _env_flag(name: str, default: str) -> bool:
    """Empty-safe env read. Railway returns '' (not None) for unset references,
    so os.getenv(name, default) yields '' and silently defeats the default."""
    return (os.getenv(name) or default).strip().lower() == "true"


def is_enabled() -> bool:
    return _env_flag("STRIKE_IB_ENABLED", "true")


def is_dry_run() -> bool:
    return _env_flag("STRIKE_IB_DRY_RUN", "false")


# ---------------------------------------------------------------------------
# Pure helpers -- unit-tested without a DB (Task 7).
# ---------------------------------------------------------------------------

def direction_from_alert_type(alert_type: str) -> Optional[str]:
    """Direction derives from alert_type ONLY.

    The payload's own `direction` field is deliberately ignored: it is
    attacker/producer-controlled relative to this consumer, and a mismatch
    between it and alert_type would silently invert the trade.
    """
    if alert_type == "ib_break_up":
        return "LONG"
    if alert_type == "ib_break_down":
        return "SHORT"
    return None


def build_signal_id(ticker: str, session_date: date, direction: str) -> str:
    """Dedup key AND webhook-replay idempotency key -- the same mechanism.

    log_signal()'s ON CONFLICT (signal_id) DO NOTHING absorbs replays and
    restarts, so the converter never pre-checks existence: it attempts the
    insert and reads the boolean.
    """
    suffix = "UP" if direction == "LONG" else "DOWN"
    return f"STRIKE_IB_{ticker}_{session_date:%Y%m%d}_{suffix}"


def next_weekday(d: date) -> date:
    cur = d + timedelta(days=1)
    while cur.weekday() >= 5:
        cur += timedelta(days=1)
    return cur


def compute_expires_at(session_date: date, sessions: int = EXPIRY_SESSIONS) -> datetime:
    """3 trading sessions after session_date, at 20:00 UTC.

    Weekday-increment loop; holidays unmodeled -- the same approximation the
    session helpers in services/read_only/market_profile.py already make, and
    it errs toward expiring late, which reads as EXPIRED rather than as a
    fabricated WIN/LOSS.
    """
    d = session_date
    for _ in range(sessions):
        d = next_weekday(d)
    return datetime(d.year, d.month, d.day, EXPIRY_HOUR_UTC, 0, 0, tzinfo=timezone.utc)


def validate_event(ev: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """AEGIS A1/A2/A3 gate. Returns (ok, reject_reason).

    Reject reasons are ticker + reason only -- never the payload, never
    raw_payload, never a price echo beyond the bounds check.
    """
    ticker = ev.get("ticker")
    if ticker not in STRIKE_TICKER_ALLOWLIST:
        return False, "ticker_not_in_allowlist"

    if direction_from_alert_type(ev.get("alert_type") or "") is None:
        return False, "unrecognized_alert_type"

    ib_high, ib_low, price = ev.get("ib_high"), ev.get("ib_low"), ev.get("price")
    if ib_high is None or ib_low is None:
        return False, "ib_bounds_null"

    ib_height = float(ib_high) - float(ib_low)
    if ib_height <= 0:
        return False, "ib_height_non_positive"

    if price is None:
        return False, "price_null"

    price = float(price)
    if price <= 0:
        return False, "price_non_positive"
    if not (PRICE_LOW_MULT * float(ib_low) <= price <= PRICE_HIGH_MULT * float(ib_high)):
        return False, "price_outside_ib_envelope"

    if ib_height > MAX_IB_HEIGHT_FRAC * price:
        return False, "ib_height_exceeds_price_fraction"

    return True, None


def compute_levels(direction: str, price: float, ib_high: float, ib_low: float) -> Dict[str, float]:
    """Stop at the IB midpoint; targets at 0.5x and 1.0x the IB height."""
    ib_height = ib_high - ib_low
    mid = (ib_high + ib_low) / 2.0
    sign = 1.0 if direction == "LONG" else -1.0
    entry = price
    target_1 = entry + sign * 0.5 * ib_height
    target_2 = entry + sign * 1.0 * ib_height
    risk = abs(entry - mid)
    reward = abs(target_1 - entry)
    return {
        "entry_price": entry,
        "stop_loss": mid,
        "target_1": target_1,
        "target_2": target_2,
        "ib_height": ib_height,
        "risk_reward": round(reward / risk, 4) if risk > 0 else None,
        # Conservative-stop comparison held for promotion review: the opposite IB
        # extreme rather than the midpoint. Stored, never acted on in v1.
        "stop_variant_opposite_extreme": ib_low if direction == "LONG" else ib_high,
    }


def watermark_state(baseline_sessions: int, seen_this_session: bool, latched: bool) -> str:
    """Render state for the /health strike_watermarks block (addendum section 3).

    Below the n-gate the instrument renders its OWN insufficiency rather than
    going silent -- silence during onboarding is indistinguishable from health,
    which is the defect class this board spent the week cataloguing. An absent
    ticker and a healthy ticker must not render the same.
    """
    if latched:
        return "SILENT"
    if baseline_sessions < BASELINE_SESSIONS_GATE:
        return f"INSUFFICIENT n={baseline_sessions}"
    return "OK" if seen_this_session else "SILENT"


def build_signal_data(
    ev: Dict[str, Any],
    direction: str,
    session_date: date,
    is_reversal: bool,
) -> Dict[str, Any]:
    """Assemble the shadow row. No UW calls, no scoring, no enrichment (F8)."""
    price = float(ev["price"])
    ib_high = float(ev["ib_high"])
    ib_low = float(ev["ib_low"])
    lv = compute_levels(direction, price, ib_high, ib_low)
    ts = ev["timestamp"]
    ts_et = ts.astimezone(ET).isoformat() if isinstance(ts, datetime) else None

    return {
        "signal_id": build_signal_id(ev["ticker"], session_date, direction),
        "timestamp": ts,
        "strategy": "STRIKE_IB_BREAK",
        "signal_type": "STRIKE_IB_BREAK",
        "source": "STRIKE_IB_BREAK",
        "ticker": ev["ticker"],
        "asset_class": "EQUITY",
        "direction": direction,
        "entry_price": lv["entry_price"],
        "stop_loss": lv["stop_loss"],
        "target_1": lv["target_1"],
        "target_2": lv["target_2"],
        "risk_reward": lv["risk_reward"],
        "timeframe": "1-3D",
        "status": "SHADOW",
        "feed_tier": "research_log",
        "expires_at": compute_expires_at(session_date),
        "notes": "STRIKE-SPEC-01 shadow — not actionable",
        "triggering_factors": {
            "l0_shadow": {
                "v": 1,
                "mode": "enforce",
                "signal_type": "STRIKE_IB_BREAK",
                "rule": "SUPPRESS",
                "would_suppress": True,
                "is_liquid": None,
                "reason": "STRIKE shadow emission — not promoted",
            },
            "strike": {
                "pythia_event_id": ev.get("id"),
                "ib_high": ib_high,
                "ib_low": ib_low,
                "ib_height": lv["ib_height"],
                "volume_quality": ev.get("volume_quality"),
                "event_ts_et": ts_et,
                "stop_variant_opposite_extreme": lv["stop_variant_opposite_extreme"],
                "ib_reversal": is_reversal,
            },
        },
    }


# ---------------------------------------------------------------------------
# DB-facing: watermarks, emission, loop.
# ---------------------------------------------------------------------------

_COUNTER_COLUMNS = frozenset({"pythia_events", "ib_events", "signals_emitted", "rejects"})


def _session_date(now_et: datetime) -> date:
    """Session date for an ET instant.

    Delegates to the vetted helper rather than re-deriving weekday arithmetic a
    second time -- that re-derivation is exactly how a 26h SLO landed on a
    weekday-only job whose legitimate gap is 72h.
    """
    from services.read_only.market_profile import _current_session_date
    return _current_session_date(now_et)


async def _session_counts_bump(conn, ticker: str, session_date: date, column: str, n: int = 1) -> None:
    """Increment one counter on strike_ib_session_counts, creating the row."""
    if column not in _COUNTER_COLUMNS:
        raise ValueError("refusing unknown counter column: " + str(column))
    await conn.execute(
        """
        INSERT INTO strike_ib_session_counts (ticker, session_date, {col})
        VALUES ($1, $2, $3)
        ON CONFLICT (ticker, session_date)
        DO UPDATE SET {col} = strike_ib_session_counts.{col} + EXCLUDED.{col}
        """.replace("{col}", column),
        ticker, session_date, n,
    )


async def refresh_watermarks(conn, current_session: date) -> Dict[str, Dict[str, Any]]:
    """Update strike_feed_watermarks for every allowlist ticker; return render state.

    Liveness reference is ANY pythia_events row for the ticker in the current
    session (binding condition 4) -- NOT ib_break_* only. A balanced day
    legitimately produces zero IB breaks, so gating liveness on IB events would
    be a trigger that cannot fire on a healthy quiet market.
    """
    states: Dict[str, Dict[str, Any]] = {}
    session_start = datetime.combine(current_session, dtime(0, 0), tzinfo=ET)

    for ticker in sorted(STRIKE_TICKER_ALLOWLIST):
        row = await conn.fetchrow(
            """
            SELECT MAX(timestamp) AS last_any,
                   MAX(timestamp) FILTER (
                       WHERE alert_type IN ('ib_break_up', 'ib_break_down')
                   ) AS last_ib,
                   COUNT(*) FILTER (WHERE timestamp >= $2) AS today_any
            FROM pythia_events
            WHERE ticker = $1
            """,
            ticker, session_start,
        )
        last_any = row["last_any"] if row else None
        last_ib = row["last_ib"] if row else None
        seen_today = bool(row and (row["today_any"] or 0) > 0)

        last_session = None
        if last_any is not None:
            if last_any.tzinfo is None:
                last_any = last_any.replace(tzinfo=timezone.utc)
            last_session = last_any.astimezone(ET).date()

        prev = await conn.fetchrow(
            "SELECT baseline_sessions, last_event_session FROM strike_feed_watermarks WHERE ticker = $1",
            ticker,
        )
        baseline = int(prev["baseline_sessions"]) if prev else 0
        prev_session = prev["last_event_session"] if prev else None
        # Increments only when a NEW session is observed: this counts distinct
        # alive sessions, not cycles. Counting cycles would clear the n-gate in
        # one afternoon and arm the alarm on a ticker never actually seen alive.
        if last_session is not None and last_session != prev_session:
            baseline += 1

        await conn.execute(
            """
            INSERT INTO strike_feed_watermarks
                (ticker, baseline_sessions, last_event_ts, last_event_session,
                 last_ib_event_ts, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (ticker) DO UPDATE SET
                baseline_sessions  = EXCLUDED.baseline_sessions,
                last_event_ts      = EXCLUDED.last_event_ts,
                last_event_session = EXCLUDED.last_event_session,
                last_ib_event_ts   = EXCLUDED.last_ib_event_ts,
                updated_at         = NOW()
            """,
            ticker, baseline, last_any, last_session, last_ib,
        )

        if seen_today:
            await _session_counts_bump(conn, ticker, current_session, "pythia_events", 0)

        states[ticker] = {
            "baseline_sessions": baseline,
            "seen_this_session": seen_today,
            "last_event_ts": last_any.isoformat() if last_any else None,
            "last_ib_event_ts": last_ib.isoformat() if last_ib else None,
        }
    return states


async def _watermark_alarms(redis, states: Dict[str, Dict[str, Any]], now_et: datetime) -> None:
    """Per-ticker latched alarm, mirroring pythia_staleness_watchdog_loop mechanics.

    Armed only after ALARM_AFTER_ET and only once baseline_sessions >= the gate:
    an absence dates nothing until the expected event rate is established across
    it, and below the gate no rate exists to measure against.
    """
    if redis is None or now_et.time() < ALARM_AFTER_ET:
        return
    from bias_engine.anomaly_alerts import send_alert

    for ticker, st in states.items():
        if st["baseline_sessions"] < BASELINE_SESSIONS_GATE:
            continue
        latch_key = "alarm:strike_watermark:" + ticker
        latched = bool(await redis.get(latch_key))
        silent = not st["seen_this_session"]

        if silent and not latched:
            await send_alert(
                "\U0001F6A8 STRIKE watermark: " + ticker + " silent this session",
                ticker + ": no pythia_events row this session (baseline "
                + str(st["baseline_sessions"]) + " sessions). The dedicated "
                "per-symbol TradingView alert may be down - R-IV.109(e).",
                severity="warning",
            )
            await redis.set(latch_key, "1", ex=LATCH_TTL)
            logger.warning("STRIKE watermark alarm FIRED for %s", ticker)
        elif (not silent) and latched:
            await send_alert(
                "✅ STRIKE watermark restored: " + ticker,
                ticker + ": pythia_events flowing again this session.",
                severity="info",
            )
            await redis.delete(latch_key)
            logger.info("STRIKE watermark alarm CLEARED for %s", ticker)


async def strike_watermarks_summary() -> Dict[str, Any]:
    """Read-only render for /health (addendum section 3). Additive; never raises.

    Below the n-gate this reports INSUFFICIENT n=<baseline_sessions> rather than
    going silent. Silence during onboarding is indistinguishable from health,
    and an absent ticker must not render the same as a healthy one.
    """
    try:
        from database.postgres_client import get_postgres_client
        from database.redis_client import get_redis_client

        pool = await get_postgres_client()
        redis = await get_redis_client()
        current_session = _session_date(datetime.now(ET))

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT ticker, baseline_sessions, last_event_session FROM strike_feed_watermarks"
            )
        by_ticker = {r["ticker"]: r for r in rows}

        out: Dict[str, str] = {}
        for ticker in sorted(STRIKE_TICKER_ALLOWLIST):
            r = by_ticker.get(ticker)
            baseline = int(r["baseline_sessions"]) if r else 0
            seen = bool(r and r["last_event_session"] == current_session)
            latched = False
            if redis is not None:
                latched = bool(await redis.get("alarm:strike_watermark:" + ticker))
            out[ticker] = watermark_state(baseline, seen, latched)

        return {
            "gate_sessions": BASELINE_SESSIONS_GATE,
            "session_date": current_session.isoformat(),
            "tickers": out,
        }
    except Exception as e:  # noqa: BLE001 -- /health must never 500 on this block
        return {"error": str(e)}


async def process_events(conn, redis, now_et: datetime) -> Dict[str, int]:
    """One converter cycle. Returns counters for logging and tests."""
    from database.postgres_client import log_signal
    from stable_engine.signals_freshness import record_attempt

    dry = is_dry_run()
    stats = {"seen": 0, "rejected": 0, "emitted": 0, "deduped": 0, "errors": 0}

    events = await conn.fetch(
        """
        SELECT id, ticker, alert_type, price, volume_quality, ib_high, ib_low, timestamp
        FROM pythia_events
        WHERE alert_type IN ('ib_break_up', 'ib_break_down')
          AND timestamp > NOW() - INTERVAL '2 hours'
          AND ticker = ANY($1)
        ORDER BY timestamp
        """,
        sorted(STRIKE_TICKER_ALLOWLIST),
    )

    emitted_ids = set()
    # Per-cycle distinct-event guards for the counter columns. Scoped to the
    # cycle, not the session: a cycle cannot double-count, and cross-cycle
    # repeats are absorbed by the ON CONFLICT on the real insert. Making these
    # session-scoped would need state this loop does not carry, and the fix that
    # actually closes the historical inflation is the backfill from
    # pythia_events named on the DEF's face.
    seen_event_ids = set()
    rejected_event_ids = set()
    for rec in events:
        ev = dict(rec)
        stats["seen"] += 1

        ts = ev.get("timestamp")
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
                ev["timestamp"] = ts
            session_date = _session_date(ts.astimezone(ET))
        else:
            session_date = _session_date(now_et)

        # DEF-STRIKE-IB-EVENTS-OVERCOUNT: count DISTINCT events, not rows-seen.
        # The 2h lookback returns the same event on up to 24 consecutive cycles,
        # so bumping per returned row made the multiplier depend on how long an
        # event survived the window — 24x at 10:31, 2x at 15:55. A time-of-day
        # gradient manufactured entirely by the counter, in the table the
        # addendum designates as the substrate for any future daily-rate band.
        if ev["id"] not in seen_event_ids:
            seen_event_ids.add(ev["id"])
            await _session_counts_bump(conn, ev["ticker"], session_date, "ib_events")

        ok, reason = validate_event(ev)
        if not ok:
            stats["rejected"] += 1
            if ev["id"] not in rejected_event_ids:
                rejected_event_ids.add(ev["id"])
                await _session_counts_bump(conn, ev["ticker"], session_date, "rejects")
            # Binding condition 7: converter-level only. NEVER record_attempt(
            # rejected) here -- a validation reject is CORRECT behavior, and
            # paging the persistence alarm on correct behavior is a false red by
            # construction. record_attempt fires only on real INSERT attempts.
            logger.info("STRIKE reject %s: %s", ev["ticker"], reason)
            continue

        direction = direction_from_alert_type(ev["alert_type"])
        signal_id = build_signal_id(ev["ticker"], session_date, direction)

        if len(emitted_ids) >= SESSION_CAP:
            logger.error(
                "STRIKE session cap %d reached - dedup is broken, halting emission", SESSION_CAP
            )
            if redis is not None and not await redis.get("alarm:strike_session_cap"):
                from bias_engine.anomaly_alerts import send_alert
                await send_alert(
                    "\U0001F6A8 STRIKE session cap hit",
                    "Emissions reached the structural cap (" + str(SESSION_CAP) + "). One row "
                    "per ticker per direction per session is the maximum, so reaching it means "
                    "dedup is broken rather than that the market was busy. Emission halted.",
                    severity="warning",
                )
                await redis.set("alarm:strike_session_cap", "1", ex=LATCH_TTL)
            break

        opposite = "SHORT" if direction == "LONG" else "LONG"
        opposite_id = build_signal_id(ev["ticker"], session_date, opposite)
        is_reversal = opposite_id in emitted_ids or bool(
            await conn.fetchval("SELECT 1 FROM signals WHERE signal_id = $1", opposite_id)
        )

        signal_data = build_signal_data(ev, direction, session_date, is_reversal)

        if dry:
            # DEF-STRIKE-IB-EVENTS-OVERCOUNT, second-order half: this branch used
            # to `continue` BEFORE emitted_ids was populated, so the same event
            # re-logged on every cycle it stayed inside the 2h lookback — up to
            # 24 lines for one event. On 2026-09-03 that rotated the 500-line log
            # buffer and destroyed the very evidence D1 step 4 asks for: the
            # review session's proof was erased by the volume of its own logging.
            #
            # Registering the id here makes dry-run log each event ONCE per
            # session, and — the point spine's log-capture order was really
            # after — makes dry-run EXERCISE THE DEDUP PATH instead of bypassing
            # it. A dry run that skips the mechanism it is meant to rehearse is
            # not a rehearsal.
            if signal_id in emitted_ids:
                continue
            emitted_ids.add(signal_id)
            redacted = {k: v for k, v in signal_data.items() if k != "triggering_factors"}
            logger.info("STRIKE DRY-RUN would emit: %s", redacted)
            continue

        try:
            inserted = await log_signal(signal_data)
        except Exception as e:  # noqa: BLE001
            stats["errors"] += 1
            record_attempt("STRIKE_IB_BREAK", False, str(e))
            logger.error("STRIKE insert failed for %s: %s", signal_id, e)
            continue

        if inserted:
            stats["emitted"] += 1
            emitted_ids.add(signal_id)
            record_attempt("STRIKE_IB_BREAK", True)
            try:
                from signals.pipeline import write_signal_outcome
                await write_signal_outcome(signal_data)
            except Exception as e:  # noqa: BLE001
                logger.warning("STRIKE outcome row failed for %s: %s", signal_id, e)
            await _session_counts_bump(conn, ev["ticker"], session_date, "signals_emitted")
            await conn.execute(
                "UPDATE strike_feed_watermarks SET last_signal_ts = NOW() WHERE ticker = $1",
                ev["ticker"],
            )
        else:
            stats["deduped"] += 1
            # Dedupe is a correct no-op (ON CONFLICT DO NOTHING), never a gap.
            record_attempt("STRIKE_IB_BREAK", False)

    return stats


async def strike_ib_converter_loop() -> None:
    """STRIKE-SPEC-01 converter + per-ticker watermarks. Weekdays 09:30-16:05 ET."""
    from database.postgres_client import get_postgres_client
    from database.redis_client import get_redis_client

    await asyncio.sleep(BOOT_DELAY_SECONDS)
    logger.info(
        "STRIKE-SPEC-01 converter started (enabled=%s dry_run=%s tickers=%d)",
        is_enabled(), is_dry_run(), len(STRIKE_TICKER_ALLOWLIST),
    )

    while True:
        try:
            if is_enabled():
                now_et = datetime.now(ET)
                in_window = (
                    now_et.weekday() < 5
                    and dtime(9, 30) <= now_et.time() <= dtime(16, 5)
                )
                if in_window:
                    pool = await get_postgres_client()
                    redis = await get_redis_client()
                    if pool:
                        current_session = _session_date(now_et)
                        async with pool.acquire() as conn:
                            states = await refresh_watermarks(conn, current_session)
                            stats = await process_events(conn, redis, now_et)
                        await _watermark_alarms(redis, states, now_et)
                        if any(stats.values()):
                            logger.info("STRIKE cycle: %s", stats)
        except Exception as e:  # noqa: BLE001 -- a fault must not kill the loop
            logger.warning("STRIKE converter cycle error: %s", e)
        await asyncio.sleep(CYCLE_SECONDS)
