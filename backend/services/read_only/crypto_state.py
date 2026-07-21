"""Read-only, DB/cache-backed crypto state accessor — HUB-MCP-CRYPTO-STATE (Path B).

Serves the consolidated per-symbol crypto state (funding / open interest /
basis / liquidations / regime / tape-health / session) for the crypto committee
**without triggering any outbound vendor call.** This is the Path-B design ruled
by Nick 2026-07-21 after Phase 0 established that the live REST endpoint
`/api/crypto/state/{symbol}` fans out to Coinalyze/Binance/OKX (5 vendor fetches,
~10-12 raw HTTP on cold cache) against an unmonitored crypto-vendor budget — an
unacceptable risk for a committee-frequency, phone-triggered tool during the
2026-08-04..15 no-deploy window.

Instead of re-fetching, this reads the values the backend has ALREADY persisted:

  - funding / open_interest / basis / liquidations  <- crypto_cycle_log.cells
        (the cycle engine writes these hourly; cells carry perp_funding,
         open_interest, quarterly_basis, liquidations with their own
         state/stale/as_of/value + the CTA-zone `column` label)
  - regime                                          <- crypto_regime_log
  - tape_health (incl. spot/perp CVD)               <- crypto_tape_health_log
  - session                                         <- utils.crypto_sessions
        (pure clock/config classification; no vendor)

ATR is deliberately NOT served here: it is a live-bars-only field with no
persisted source, so exposing it would require the vendor call Path B exists to
avoid. It is reported as an explicit, honest omission (available=false), never
fabricated, and never rolled into the health status.

Freshness is labeled honestly per the fail-visible principle: a stalled writer
makes the blocks read `stale`/`degraded`, never a fabricated all-clear. Health
is derived FAIL-CLOSED — a missing state field renders as degraded/unknown, the
opposite of the `.get("health_status", "LIVE")` fail-open pattern that hid the
funding cache bug (db5e398) on OI and basis for its entire life.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Freshness thresholds (seconds). The cycle engine writes hourly, so 2 intervals
# is the "genuinely behind" line; regime/tape mirror the live endpoint's own
# thresholds (crypto_market.py:853 / :887) so this tool and that endpoint agree.
CYCLE_STALE_SECONDS = 7200   # 2x the ~hourly cycle cadence
REGIME_STALE_SECONDS = 7200  # matches the live endpoint
TAPE_STALE_SECONDS = 600     # matches the live endpoint

# The four cycle-log cells this tool surfaces, mapped to their block name.
_CYCLE_CELL_FOR_BLOCK = {
    "funding": "perp_funding",
    "open_interest": "open_interest",
    "basis": "quarterly_basis",
    "liquidations": "liquidations",
}


def _parse_iso(ts: Any) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _age_seconds(dt: Optional[datetime], now: datetime) -> Optional[int]:
    if dt is None:
        return None
    return max(0, int((now - dt).total_seconds()))


def _block(status: str, as_of: Optional[datetime], now: datetime, **data) -> Dict[str, Any]:
    """Per-block envelope: {**data, as_of, data_age_seconds, status, degraded}.

    `status` is one of ok/stale/degraded/unavailable and is the single source of
    truth for the block; `degraded` is kept as a convenience boolean (True for
    everything worse than ok) so consumers reading either field agree.
    """
    return {
        **data,
        "as_of": as_of.isoformat() if as_of else None,
        "data_age_seconds": _age_seconds(as_of, now),
        "status": status,
        "degraded": status != "ok",
    }


def _classify(state: Optional[str], stale_flag: Any, row_degraded: Any,
              age: Optional[int], stale_threshold: int) -> str:
    """FAIL-CLOSED per-block status.

    Precedence: a recorded health failure (degraded flag, or a cell state that is
    anything other than the literal "LIVE") beats an age-only staleness. A
    MISSING state (None) is NOT healthy — it resolves to "degraded", never "ok".
    """
    if row_degraded:
        return "degraded"
    if stale_flag:
        return "degraded"
    # state must be exactly "LIVE" to be trusted; None / absent / anything else
    # is degraded. This is the no-fail-open guarantee.
    if state is not None and state != "LIVE":
        return "degraded"
    if state is None:
        return "degraded"
    if age is None:
        return "unavailable"
    if age > stale_threshold:
        return "stale"
    return "ok"


def _cells_to_list(raw: Any) -> list:
    """crypto_cycle_log.cells is jsonb; asyncpg returns it as a str (no codec
    is registered). Handle both str and already-decoded list defensively."""
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    return raw if isinstance(raw, list) else []


async def _read_cycle_blocks(conn, base_symbol: str, now: datetime) -> Tuple[Dict[str, Any], Optional[datetime]]:
    """Read the latest crypto_cycle_log row and derive funding/OI/basis/liq blocks.

    Returns (blocks, cycle_computed_at). Every block is present in the dict; a
    missing row or missing cell yields an honest `unavailable` block, never a
    fabricated value."""
    row = await conn.fetchrow(
        """
        SELECT computed_at, degraded, degrade_reason, cells, tier,
               live_cell_count, min_live_cells
        FROM crypto_cycle_log
        WHERE symbol = $1
        ORDER BY computed_at DESC
        LIMIT 1
        """,
        base_symbol,
    )

    blocks: Dict[str, Any] = {}

    if row is None:
        for block_name in _CYCLE_CELL_FOR_BLOCK:
            blocks[block_name] = _block(
                "unavailable", None, now, value=None, signal=None,
                note="no crypto_cycle_log rows for this symbol yet",
            )
        return blocks, None

    cycle_at = row["computed_at"]
    if cycle_at is not None and cycle_at.tzinfo is None:
        cycle_at = cycle_at.replace(tzinfo=timezone.utc)
    cells = {c.get("signal_id"): c for c in _cells_to_list(row["cells"]) if isinstance(c, dict)}
    row_degraded = bool(row["degraded"])

    for block_name, cell_id in _CYCLE_CELL_FOR_BLOCK.items():
        cell = cells.get(cell_id)
        if cell is None:
            blocks[block_name] = _block(
                "unavailable", None, now, value=None, signal=None,
                note=f"cell '{cell_id}' absent from latest cycle snapshot",
            )
            continue

        cell_as_of = _parse_iso(cell.get("as_of"))
        age = _age_seconds(cell_as_of, now)
        # NOTE: intentionally NO default on state — .get("state") returns None if
        # absent, and _classify treats None as degraded (fail-closed).
        status = _classify(
            state=cell.get("state"),
            stale_flag=cell.get("stale"),
            row_degraded=row_degraded,
            age=age,
            stale_threshold=CYCLE_STALE_SECONDS,
        )

        # Common cell fields; block-specific extras layered on.
        extra: Dict[str, Any] = {
            "value": cell.get("value"),
            "signal": cell.get("signal"),
            "cta_zone": cell.get("column"),  # CAPITULATION/EUPHORIA/... labeled zone
            "source": cell.get("source"),
            "cell_state": cell.get("state"),
        }
        if block_name == "funding":
            extra["sentiment"] = cell.get("sentiment")
        elif block_name == "open_interest":
            extra["divergence"] = cell.get("divergence")
        elif block_name == "liquidations":
            extra["long_pct"] = cell.get("long_pct")
            extra["composition"] = cell.get("composition")

        blocks[block_name] = _block(status, cell_as_of, now, **extra)

    return blocks, cycle_at


async def _read_regime(conn, base_symbol: str, now: datetime) -> Dict[str, Any]:
    """Latest crypto_regime_log row. Keyed by the hyphenated canonical form
    ("BTC-USD") per DEF-FEED-TRIAGE D2 (crypto_market.py:837)."""
    row = await conn.fetchrow(
        """
        SELECT regime_state, computed_at, degraded, degrade_reason
        FROM crypto_regime_log
        WHERE symbol = $1
        ORDER BY computed_at DESC
        LIMIT 1
        """,
        f"{base_symbol}-USD",
    )
    if row is None:
        return _block("unavailable", None, now, state=None, note="no regime rows yet")

    ca = row["computed_at"]
    if ca is not None and ca.tzinfo is None:
        ca = ca.replace(tzinfo=timezone.utc)
    age = _age_seconds(ca, now)
    if row["degraded"]:
        status = "degraded"
    elif age is not None and age > REGIME_STALE_SECONDS:
        status = "stale"
    else:
        status = "ok"
    return _block(
        status, ca, now,
        state=row["regime_state"],
        degrade_reason=row["degrade_reason"],
    )


async def _read_tape_health(conn, base_symbol: str, now: datetime) -> Dict[str, Any]:
    """Latest crypto_tape_health_log row (bare-symbol keyed, per its own writer).
    Carries spot/perp CVD and the spot-vs-perp lead state."""
    row = await conn.fetchrow(
        """
        SELECT state, slope, spot_cvd, perp_cvd, degraded, degrade_reason, computed_at
        FROM crypto_tape_health_log
        WHERE symbol = $1
        ORDER BY computed_at DESC
        LIMIT 1
        """,
        base_symbol,
    )
    if row is None:
        return _block("unavailable", None, now, state=None, note="no tape-health rows yet for this symbol")

    ca = row["computed_at"]
    if ca is not None and ca.tzinfo is None:
        ca = ca.replace(tzinfo=timezone.utc)
    age = _age_seconds(ca, now)
    if row["degraded"]:
        status = "degraded"
    elif age is not None and age > TAPE_STALE_SECONDS:
        status = "stale"
    else:
        status = "ok"
    return _block(
        status, ca, now,
        state=row["state"],
        slope=row["slope"],
        spot_cvd=row["spot_cvd"],
        perp_cvd=row["perp_cvd"],
        degrade_reason=row["degrade_reason"],
    )


async def _read_session(now: datetime) -> Dict[str, Any]:
    """Session classification — pure clock/config compute, no vendor, no DB write."""
    try:
        from config.crypto_gate_loader import get_gate_config
        from utils.crypto_sessions import get_session_state
        _cv, scfg = await get_gate_config()
        sess = get_session_state(now, scfg)
        return _block(
            "ok", now, now,
            state=sess.get("current_session"),
            session_label=sess.get("label"),
            partition=sess.get("partition"),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("crypto_state: session compute failed: %s", exc)
        return _block("degraded", None, now, state=None, error=str(exc))


def _atr_omitted() -> Dict[str, Any]:
    """ATR is a live-bars-only field with no persisted source. Under Path B it is
    an explicit, honest omission — NOT a degraded block (it is excluded from the
    health rollup) and NEVER a fabricated value."""
    return {
        "value": None,
        "available": False,
        "reason": (
            "ATR is derived from live bars and is not persisted; the cache-backed "
            "tool does not fetch it (Path B, zero vendor calls). Use "
            "hub_get_crypto_market_profile for live structural levels."
        ),
    }


async def get_crypto_state(base_symbol: str) -> Dict[str, Any]:
    """Return the DB/cache-backed per-symbol crypto state (no vendor calls).

    `base_symbol` must already be the normalized, tracked base symbol (e.g.
    "BTC") — the MCP tool layer handles normalization + the tracked-universe
    guard before calling this.

    Returns a dict of named blocks plus `cycle_snapshot_at` (the source cycle
    row's computed_at) and `atr` (an explicit omission marker). Each block
    carries its own status/as_of/data_age_seconds/degraded; the top-level
    rollup is the caller's job (worst_status)."""
    from database.postgres_client import get_postgres_client

    now = datetime.now(timezone.utc)
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        cycle_blocks, cycle_at = await _read_cycle_blocks(conn, base_symbol, now)
        regime_block = await _read_regime(conn, base_symbol, now)
        tape_block = await _read_tape_health(conn, base_symbol, now)

    session_block = await _read_session(now)

    return {
        "symbol": base_symbol,
        "session": session_block,
        "funding": cycle_blocks["funding"],
        "open_interest": cycle_blocks["open_interest"],
        "basis": cycle_blocks["basis"],
        "liquidations": cycle_blocks["liquidations"],
        "regime": regime_block,
        "tape_health": tape_block,
        "atr": _atr_omitted(),
        "cycle_snapshot_at": cycle_at.isoformat() if cycle_at else None,
        "generated_at": now.isoformat(),
    }


# The blocks that participate in the top-level health rollup. ATR is excluded by
# design (it is a scope omission, not a health signal); session/regime/tape and
# the four cycle blocks are the real health surface.
ROLLUP_BLOCKS = ("session", "funding", "open_interest", "basis",
                 "liquidations", "regime", "tape_health")
