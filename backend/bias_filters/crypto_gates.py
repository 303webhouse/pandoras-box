"""Stater Swap v2 S-2 (R-1) — shadow regime/session gate evaluator.

Called from signals/pipeline.py's process_signal_unified(), AFTER the real
signal is already persisted (S-2 Phase-0 finding 0.7: there's no existing
"crypto branch" to hook -- this is a new conditional the caller adds).
Wrapped by the caller per hard rule 5: any exception here is caught, logged,
and the signal write is never affected.

evaluate_gates() only COMPUTES a verdict and returns a dict for one
crypto_gate_shadow row -- it never mutates the real signal and never writes
to `signals` directly. The dormant enforcement branch (maybe_enforce_gate,
below) is the ONLY code that can touch `signals`, and only when
config["gating_enabled"] is true -- which stays false through all of S-2
(hard rule 1, Done item 11). Unit-tested behind the flag; the flag itself
is never flipped by this module.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LONG_DIRECTIONS = {"LONG", "BUY", "BULLISH"}
_SHORT_DIRECTIONS = {"SHORT", "SELL", "BEARISH"}


async def _latest_regime(conn, symbol: str) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT regime_state, tier FROM crypto_regime_log WHERE symbol = $1 ORDER BY computed_at DESC LIMIT 1",
        symbol,
    )
    return dict(row) if row else None


def _find_strategy_class(strategy: str, strategy_classes: Dict[str, Any]) -> Optional[str]:
    """Exact-match lookup only (Fable amendment A, 2026-07-15) -- no
    case normalization, no fuzzy matching. Returns the class name or None
    (caller treats None as "unclassified")."""
    for class_name, cfg in strategy_classes.items():
        if class_name == "unclassified":
            continue
        if strategy in (cfg.get("strategies") or []):
            return class_name
    return None


async def evaluate_gates(signal_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Evaluate the shadow gate matrix for a persisted crypto signal.
    Returns a dict shaped for one crypto_gate_shadow row, or None if the
    signal's ticker doesn't resolve to a tracked crypto symbol (caller skips
    the insert in that case -- not every asset_class=CRYPTO ticker is
    necessarily one of the six tracked symbols).
    """
    from jobs.crypto_bars import normalize_crypto_ticker
    from utils.crypto_sessions import get_session_state
    from config.crypto_gate_loader import get_gate_config
    from database.postgres_client import get_postgres_client

    raw_ticker = signal_data.get("ticker") or ""
    base = normalize_crypto_ticker(raw_ticker)
    if not base:
        logger.debug("crypto_gates: ticker %s does not resolve to a tracked symbol -- skipping", raw_ticker)
        return None
    symbol = f"{base}-USD"
    master_symbol = "BTC-USD"

    config_version, config = await get_gate_config()
    tiers = config.get("tiers", {})
    tier = tiers.get(symbol)

    now = datetime.now(timezone.utc)
    session_state = get_session_state(now, config)

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        master_row = await _latest_regime(conn, master_symbol)
        symbol_row = (
            master_row if symbol == master_symbol else await _latest_regime(conn, symbol)
        )

    regime_master = (master_row or {}).get("regime_state") or "UNKNOWN"
    regime_symbol = (symbol_row or {}).get("regime_state") or "UNKNOWN"

    direction = (signal_data.get("direction") or "").upper()
    strategy = signal_data.get("strategy") or ""

    reasons: List[str] = []
    would_block = False

    def _block(reason: str) -> None:
        nonlocal would_block
        would_block = True
        if reason not in reasons:
            reasons.append(reason)

    master_rules = config.get("master_rules", {})
    if regime_master == "UNKNOWN" and master_rules.get("unknown_master_blocks_regime_dependent", True):
        _block("REGIME_UNKNOWN")
    elif regime_master == "TREND_DOWN":
        if tier == 3 and master_rules.get("btc_trend_down_blocks_tier3_all_entries", True):
            _block("BTC_TREND_DOWN_T3_BLOCK")
        elif tier == 2 and direction in _LONG_DIRECTIONS and master_rules.get("btc_trend_down_blocks_tier2_longs", True):
            _block("BTC_TREND_DOWN_T2_LONG_BLOCK")

    strategy_classes = config.get("strategy_classes", {})
    class_name = _find_strategy_class(strategy, strategy_classes)
    if class_name is None:
        reasons.append("UNCLASSIFIED_STRATEGY")
    else:
        class_cfg = strategy_classes[class_name]
        if regime_symbol == "UNKNOWN":
            _block("REGIME_UNKNOWN")
        elif direction in _LONG_DIRECTIONS and regime_symbol not in (class_cfg.get("long_allowed_in") or []):
            _block(f"STRATEGY_CLASS_REGIME_MISMATCH:{class_name}:{regime_symbol}")
        elif direction in _SHORT_DIRECTIONS and regime_symbol not in (class_cfg.get("short_allowed_in") or []):
            _block(f"STRATEGY_CLASS_REGIME_MISMATCH:{class_name}:{regime_symbol}")

        if class_cfg.get("requires_event_window") and not session_state["event_windows_active"]:
            _block("SESSION_WINDOW")

    advisories = config.get("advisories", {})
    if session_state["weekend_holiday_flag"] and advisories.get("weekend_holiday_size_reduce"):
        reasons.append("SIZE_REDUCE_WEEKEND")

    verdict = "WOULD_BLOCK" if would_block else "WOULD_PASS"

    return {
        "evaluated_at": now,
        "signal_id": signal_data.get("signal_id"),
        "symbol": symbol,
        "tier": tier,
        "strategy": strategy,
        "strategy_canonical": strategy,  # no aliasing found in 0.6 -- identical today
        "direction": direction,
        "regime_master": regime_master,
        "regime_symbol": regime_symbol,
        "session_partition": session_state["partition"],
        "event_windows": session_state["event_windows_active"],
        "weekend_holiday_flag": session_state["weekend_holiday_flag"],
        "alt_gate": config.get("alt_gate", {}).get("status", "NOT_AVAILABLE"),
        "verdict": verdict,
        "reasons": reasons,
        "config_version": config_version,
    }


async def persist_gate_shadow_row(row: Dict[str, Any]) -> None:
    """INSERT one crypto_gate_shadow row. Never mutates `signals`."""
    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO crypto_gate_shadow
                (evaluated_at, signal_id, symbol, tier, strategy, strategy_canonical,
                 direction, regime_master, regime_symbol, session_partition,
                 event_windows, weekend_holiday_flag, alt_gate, verdict, reasons,
                 config_version)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            """,
            row["evaluated_at"], row["signal_id"], row["symbol"], row["tier"],
            row["strategy"], row["strategy_canonical"], row["direction"],
            row["regime_master"], row["regime_symbol"], row["session_partition"],
            row["event_windows"], row["weekend_holiday_flag"], row["alt_gate"],
            row["verdict"], row["reasons"], row["config_version"],
        )


async def maybe_enforce_gate(signal_data: Dict[str, Any], gate_row: Dict[str, Any], config: dict) -> bool:
    """Flag-off enforcement branch (ships dormant, brief §6.4.4). Only acts
    when config["gating_enabled"] is true AND the verdict is WOULD_BLOCK --
    both conditions are required. Reuses the EXACT existing
    conflict-dismissal persistence convention verbatim (Fable amendment C,
    2026-07-15): status='DISMISSED', dismiss reason appended to the existing
    `notes` column (no new column on `signals`), Redis cache cleared. Returns
    True if a dismissal was performed.

    Never called with gating_enabled=true during S-2 -- the seeded config
    keeps it false through closure (hard rule 1, Done item 11). Exists and
    is unit-tested so the eventual flag-flip (brief §10, NOT executed here)
    is a config change, not a code change.
    """
    if not config.get("gating_enabled"):
        return False
    if gate_row.get("verdict") != "WOULD_BLOCK":
        return False

    signal_id = signal_data.get("signal_id")
    if not signal_id:
        return False

    reasons = gate_row.get("reasons") or []
    dismiss_note = f" | Auto-dismissed: REGIME_GATE:{','.join(reasons)}"

    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE signals
            SET status = 'DISMISSED',
                notes = COALESCE(notes, '') || $1
            WHERE signal_id = $2
            """,
            dismiss_note,
            signal_id,
        )

    try:
        from database.redis_client import get_redis_client

        redis = await get_redis_client()
        if redis:
            await redis.delete(f"signal:{signal_id}")
    except Exception:
        pass  # Redis cleanup is best-effort, matches _check_and_clear_conflicting_signals

    logger.info("REGIME_GATE dismissal: %s -- %s", signal_id, dismiss_note.strip(" |"))
    return True
