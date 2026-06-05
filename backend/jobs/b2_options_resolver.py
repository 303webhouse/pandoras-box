"""B2 options-P&L resolver.

Captures entry and exit marks for signal_options_expressions rows using
live UW chain mid prices (get_spread_value). Writes OPTIONS_PNL outcome data
to the signal_options_expressions table only — never touches signals table.

Shadow mode (B2_SHADOW_MODE=true, default): rows are written for data
collection. options_pnl data is not consumed by any live decision path in
Phase 1. Flip B2_SHADOW_MODE=false in Phase 2 when promoting to live.

Two entry points:
  create_b2_expression(signal_data) — called fire-and-forget from pipeline.py
      at signal creation time. Builds the expression (option type, strikes,
      expiry) and immediately attempts the entry mark capture.
  run_b2_resolver_tick(pool) — called every 15 min from main.py loop.
      Catches missed entry marks (PENDING), captures exit marks when BAR_WALK
      resolves (ENTERED + signals.outcome IS NOT NULL), prunes expired rows.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

B2_SHADOW_MODE = os.getenv("B2_SHADOW_MODE", "true").lower() != "false"

# Signal types that carry no entry/stop/target — skip B2 for these
_SKIP_SIGNAL_TYPES = {"SCOUT_ALERT", "MANUAL"}

# Spread width by underlying price tier (Phase 1: price-based; Phase 2: delta-based)
_WIDTH_TIERS = [(100.0, 5.0), (20.0, 2.5), (0.0, 1.0)]


def _spread_width(underlying_price: float) -> float:
    for threshold, width in _WIDTH_TIERS:
        if underlying_price >= threshold:
            return width
    return 1.0


def _option_type(direction: str) -> str:
    return "call" if direction.upper() in ("LONG", "BUY", "BULLISH") else "put"


def _find_expiry(signal_date: date) -> Optional[str]:
    """First Friday in [8, 21] calendar days from signal_date.

    Falls back to [8, 28] window for tickers with monthly-only expirations.
    Returns ISO date string or None if no Friday found (caller writes NO_EXPIRY).
    """
    for delta in range(8, 29):
        candidate = signal_date + timedelta(days=delta)
        if candidate.weekday() == 4:  # Friday = 4
            return candidate.isoformat()
    return None


# ─── Core mark-capture helpers ───────────────────────────────────────────────

async def _capture_entry_mark(
    pool,
    soe_id: int,
    signal_id: str,
    ticker: str,
    option_type: str,
    long_strike: float,
    short_strike: float,
    expiry: str,
) -> None:
    """Call get_spread_value and write entry_mark to an expression row."""
    from integrations.uw_api import get_spread_value

    structure = f"{option_type}_debit_spread"
    try:
        result = await get_spread_value(ticker, long_strike, short_strike, expiry, structure)
    except Exception as exc:
        logger.debug("b2: entry get_spread_value failed %s: %s", signal_id, exc)
        return

    if not result:
        return
    entry_mark = result.get("spread_value")
    if entry_mark is None or float(entry_mark) <= 0:
        return

    entry_mark = float(entry_mark)
    width = abs(long_strike - short_strike)
    max_profit = round((width - entry_mark) * 100, 4)
    max_loss = round(entry_mark * 100, 4)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE signal_options_expressions
               SET b2_status        = 'ENTERED',
                   entry_mark       = $1,
                   entry_captured_at = NOW(),
                   max_profit       = $2,
                   max_loss         = $3
             WHERE id = $4
               AND b2_status = 'PENDING'
            """,
            entry_mark, max_profit, max_loss, soe_id,
        )
    logger.info(
        "b2: entry captured %s — %s %s/%s %s → %.4f (max_profit=%.2f max_loss=%.2f)",
        signal_id, ticker, long_strike, short_strike, expiry,
        entry_mark, max_profit, max_loss,
    )


async def _capture_exit_mark(
    pool,
    soe_id: int,
    signal_id: str,
    ticker: str,
    option_type: str,
    long_strike: float,
    short_strike: float,
    expiry: str,
    entry_mark: float,
    signal_outcome: str,
) -> None:
    """Call get_spread_value at exit and write exit_mark + options_pnl."""
    from integrations.uw_api import get_spread_value

    structure = f"{option_type}_debit_spread"
    exit_trigger = (
        "TARGET_1"
        if signal_outcome.upper() in ("WIN", "HIT_T1", "HIT_T2")
        else "STOP_LOSS"
    )

    try:
        result = await get_spread_value(ticker, long_strike, short_strike, expiry, structure)
    except Exception as exc:
        logger.debug("b2: exit get_spread_value failed %s: %s", signal_id, exc)
        result = None

    if not result:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE signal_options_expressions
                   SET resolution_notes = 'chain_unavailable_at_exit'
                 WHERE id = $1 AND b2_status = 'ENTERED'
                """,
                soe_id,
            )
        return

    exit_mark = result.get("spread_value")
    if exit_mark is None:
        return

    exit_mark = float(exit_mark)
    options_pnl = round((exit_mark - entry_mark) * 100, 4)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE signal_options_expressions
               SET b2_status        = 'EXITED',
                   exit_mark        = $1,
                   exit_captured_at  = NOW(),
                   exit_trigger     = $2,
                   options_pnl      = $3
             WHERE id = $4
               AND b2_status = 'ENTERED'
            """,
            exit_mark, exit_trigger, options_pnl, soe_id,
        )
    logger.info(
        "b2: exit captured %s — exit=%.4f pnl=%.4f (%s)",
        signal_id, exit_mark, options_pnl, exit_trigger,
    )


# ─── Pipeline entry hook ──────────────────────────────────────────────────────

async def create_b2_expression(signal_data: dict) -> None:
    """Create a B2 expression row for a newly persisted signal.

    Called fire-and-forget via asyncio.ensure_future() from pipeline.py.
    Any failure is logged and swallowed — never breaks the signal pipeline.

    Skips: SCOUT_ALERT, MANUAL, signals missing entry/stop/target,
    signals without a valid ticker or direction.
    """
    signal_id = signal_data.get("signal_id")
    try:
        from database.postgres_client import get_postgres_client
        from integrations.uw_api import get_iv_rank, get_options_snapshot

        ticker = (signal_data.get("ticker") or "").upper()
        direction = (signal_data.get("direction") or "").upper()
        signal_type = signal_data.get("signal_type") or ""
        entry_price = signal_data.get("entry_price")
        stop_loss = signal_data.get("stop_loss")
        target_1 = signal_data.get("target_1")

        if not signal_id or not ticker or not direction:
            return
        if signal_type in _SKIP_SIGNAL_TYPES:
            return
        if not entry_price or not stop_loss or not target_1:
            return

        try:
            entry_f = float(entry_price)
        except (TypeError, ValueError):
            return

        opt_type = _option_type(direction)

        created_raw = signal_data.get("created_at") or datetime.utcnow()
        if isinstance(created_raw, str):
            created_raw = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        created_date = created_raw.date() if hasattr(created_raw, "date") else date.today()

        expiry = _find_expiry(created_date)
        pool = await get_postgres_client()

        if not expiry:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO signal_options_expressions
                        (signal_id, option_type, long_strike, short_strike, expiry,
                         spread_width, underlying_price_at_entry, b2_status, outcome_source)
                    VALUES ($1, $2, 0, 0, CURRENT_DATE, 0, $3, 'NO_EXPIRY', 'OPTIONS_PNL')
                    ON CONFLICT (signal_id) DO NOTHING
                    """,
                    signal_id, opt_type, entry_f,
                )
            logger.debug("b2: NO_EXPIRY for %s", signal_id)
            return

        # Pull chain for delta-based strike selection.
        # Trap raises (e.g. UW 429, network error) the same as a None return so the
        # NO_CHAIN row is always written and the outer except is never triggered by
        # a chain fetch failure alone.
        try:
            chain = await get_options_snapshot(
                ticker, expiration_date=expiry, contract_type=opt_type
            )
        except Exception as chain_exc:
            logger.debug("b2: chain fetch raised for %s: %s", signal_id, chain_exc)
            chain = None

        if not chain:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO signal_options_expressions
                        (signal_id, option_type, long_strike, short_strike, expiry,
                         spread_width, underlying_price_at_entry, b2_status, outcome_source)
                    VALUES ($1, $2, 0, 0, $3::date, 0, $4, 'NO_CHAIN', 'OPTIONS_PNL')
                    ON CONFLICT (signal_id) DO NOTHING
                    """,
                    signal_id, opt_type, expiry, entry_f,
                )
            logger.debug("b2: NO_CHAIN for %s %s %s", signal_id, ticker, expiry)
            return

        # Long leg: closest abs(delta) to 0.30; fall back to moneyness
        long_strike: Optional[float] = None
        best_diff = float("inf")
        for contract in chain:
            greeks = contract.get("greeks") or {}
            delta = greeks.get("delta")
            if delta is None:
                continue
            diff = abs(abs(float(delta)) - 0.30)
            if diff < best_diff:
                best_diff = diff
                details = contract.get("details") or {}
                s = details.get("strike_price")
                if s is not None:
                    long_strike = float(s)

        if long_strike is None:
            # Moneyness fallback: ~2% OTM
            long_strike = round(
                entry_f * 1.02 if opt_type == "call" else entry_f * 0.98, 2
            )

        width = _spread_width(entry_f)
        short_strike = round(
            long_strike + width if opt_type == "call" else long_strike - width, 2
        )

        # Verify short leg exists; widen once if missing
        def _has_strike(ch, strike):
            return any(
                abs(float((c.get("details") or {}).get("strike_price") or 0) - strike) < 0.01
                for c in ch
            )

        if not _has_strike(chain, short_strike):
            short_strike = round(
                short_strike + width if opt_type == "call" else short_strike - width, 2
            )
            if not _has_strike(chain, short_strike):
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO signal_options_expressions
                            (signal_id, option_type, long_strike, short_strike, expiry,
                             spread_width, underlying_price_at_entry, b2_status, outcome_source)
                        VALUES ($1, $2, $3, $4, $5::date, $6, $7, 'NO_SHORT_LEG', 'OPTIONS_PNL')
                        ON CONFLICT (signal_id) DO NOTHING
                        """,
                        signal_id, opt_type, long_strike, short_strike, expiry,
                        abs(long_strike - short_strike), entry_f,
                    )
                logger.debug("b2: NO_SHORT_LEG for %s", signal_id)
                return

        # IV rank: UW returns 0-1 fractional; store as 0-100
        iv_rank_val: Optional[float] = None
        try:
            iv_data = await get_iv_rank(ticker)
            if iv_data:
                latest = iv_data[0] if isinstance(iv_data, list) and iv_data else iv_data
                if isinstance(latest, dict):
                    raw_iv = latest.get("iv_rank_1y")
                    if raw_iv is not None:
                        iv_rank_val = round(float(raw_iv) * 100, 2)
        except Exception:
            pass

        actual_width = abs(long_strike - short_strike)

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO signal_options_expressions
                    (signal_id, option_type, long_strike, short_strike, expiry,
                     spread_width, iv_rank_at_entry, underlying_price_at_entry,
                     b2_status, outcome_source)
                VALUES ($1, $2, $3, $4, $5::date, $6, $7, $8, 'PENDING', 'OPTIONS_PNL')
                ON CONFLICT (signal_id) DO NOTHING
                RETURNING id
                """,
                signal_id, opt_type, long_strike, short_strike, expiry,
                actual_width, iv_rank_val, entry_f,
            )

        if not row:
            return  # ON CONFLICT DO NOTHING — already exists

        soe_id = row["id"]
        logger.info(
            "b2: expression created %s — %s %s %s/%s %s (ivr=%.1f)",
            signal_id, ticker, opt_type, long_strike, short_strike, expiry,
            iv_rank_val or 0,
        )

        # Immediately attempt entry mark capture (best-effort)
        await _capture_entry_mark(
            pool, soe_id, signal_id, ticker,
            opt_type, long_strike, short_strike, expiry,
        )

    except Exception as exc:
        logger.warning("b2: create_b2_expression failed for %s: %s", signal_id or "?", exc)


# ─── 15-min resolver tick ─────────────────────────────────────────────────────

async def run_b2_resolver_tick(pool) -> None:
    """One resolver tick: entry catch-up, exit capture, expiry pruning.

    Called from b2_options_resolver_loop in main.py every 15 min during
    market hours. Each sub-step is independent; failures in one don't block
    the others.
    """
    # 1. Entry catch-up: PENDING rows that didn't get a mark at signal creation
    async with pool.acquire() as conn:
        pending = await conn.fetch(
            """
            SELECT soe.id, soe.signal_id, soe.option_type,
                   soe.long_strike, soe.short_strike, soe.expiry,
                   s.ticker
            FROM signal_options_expressions soe
            JOIN signals s ON s.signal_id = soe.signal_id
            WHERE soe.b2_status = 'PENDING'
              AND soe.expiry >= CURRENT_DATE
            LIMIT 50
            """
        )

    for row in pending:
        try:
            await _capture_entry_mark(
                pool, row["id"], row["signal_id"],
                row["ticker"] or "", row["option_type"],
                float(row["long_strike"]), float(row["short_strike"]),
                row["expiry"].isoformat(),
            )
        except Exception as exc:
            logger.debug("b2: entry catch-up failed %s: %s", row["signal_id"], exc)

    # 2. Exit capture: ENTERED rows where BAR_WALK has resolved on the signal
    async with pool.acquire() as conn:
        resolved = await conn.fetch(
            """
            SELECT soe.id, soe.signal_id, soe.option_type,
                   soe.long_strike, soe.short_strike, soe.expiry, soe.entry_mark,
                   s.ticker, s.outcome
            FROM signal_options_expressions soe
            JOIN signals s ON s.signal_id = soe.signal_id
            WHERE soe.b2_status    = 'ENTERED'
              AND soe.exit_mark    IS NULL
              AND s.outcome        IS NOT NULL
              AND s.outcome_source = 'BAR_WALK'
              AND soe.expiry       >= CURRENT_DATE
            LIMIT 50
            """
        )

    for row in resolved:
        try:
            await _capture_exit_mark(
                pool, row["id"], row["signal_id"],
                row["ticker"] or "", row["option_type"],
                float(row["long_strike"]), float(row["short_strike"]),
                row["expiry"].isoformat(), float(row["entry_mark"] or 0),
                row["outcome"] or "",
            )
        except Exception as exc:
            logger.debug("b2: exit capture failed %s: %s", row["signal_id"], exc)

    # 3. Expiry pruning: ENTERED rows whose option expiry has passed
    async with pool.acquire() as conn:
        pruned = await conn.execute(
            """
            UPDATE signal_options_expressions
               SET b2_status = 'EXPIRED_UNRESOLVED'
             WHERE b2_status = 'ENTERED'
               AND expiry < CURRENT_DATE
            """
        )
    if pruned and pruned != "UPDATE 0":
        logger.info("b2: pruned %s", pruned)

    if pending or resolved:
        logger.info(
            "b2: tick done — entry_catchup=%d exit_capture=%d",
            len(pending), len(resolved),
        )
