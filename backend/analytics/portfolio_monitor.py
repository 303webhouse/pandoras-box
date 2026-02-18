"""
Daily portfolio snapshot and correlated risk monitor.
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx

from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)


def _direction_sign(direction: str) -> int:
    if (direction or "").upper() in {"SHORT", "SELL"}:
        return -1
    return 1


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_account_sizes() -> Dict[str, float]:
    sizes: Dict[str, float] = {}
    raw = os.getenv("PORTFOLIO_ACCOUNT_SIZES")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for key, value in parsed.items():
                    sizes[str(key).upper()] = _safe_float(value, 0.0)
        except Exception:
            pass
    default_size = _safe_float(os.getenv("PORTFOLIO_ACCOUNT_SIZE", "25000"), 25000.0)
    sizes.setdefault("__DEFAULT__", default_size if default_size > 0 else 25000.0)
    return sizes


async def _load_open_positions(conn) -> List[Dict[str, Any]]:
    trades = await conn.fetch(
        """
        SELECT id, ticker, direction, quantity, entry_price, stop_loss,
               status, account, NULL::TEXT AS broker
        FROM trades
        WHERE LOWER(COALESCE(status, 'open')) = 'open'
        """
    )
    if trades:
        return [dict(row) for row in trades]

    # Fallback to existing positions table when trades is not populated yet.
    positions = await conn.fetch(
        """
        SELECT id, ticker, direction, quantity, entry_price, stop_loss,
               status, NULL::TEXT AS account, broker
        FROM positions
        WHERE status = 'OPEN'
        """
    )
    return [dict(row) for row in positions]


async def _load_sector_map(conn) -> Dict[str, str]:
    rows = await conn.fetch("SELECT symbol, sector FROM watchlist_tickers")
    return {str(row["symbol"]).upper(): str(row["sector"] or "Uncategorized") for row in rows}


def _build_account_snapshot(
    account: str,
    rows: List[Dict[str, Any]],
    sector_map: Dict[str, str],
    account_size: float,
) -> Dict[str, Any]:
    total_positions = len(rows)
    net_delta = 0.0
    total_risk = 0.0
    largest_notional = 0.0

    sector_exposure: Dict[str, float] = defaultdict(float)
    direction_exposure: Dict[str, float] = defaultdict(float)
    correlated_groups: Dict[tuple, Dict[str, float]] = defaultdict(lambda: {"count": 0, "risk": 0.0})

    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        direction = str(row.get("direction") or "LONG").upper()
        qty = max(_safe_float(row.get("quantity"), 1.0), 0.0)
        entry = _safe_float(row.get("entry_price"), 0.0)
        stop = _safe_float(row.get("stop_loss"), entry)
        notional = abs(entry * qty)
        largest_notional = max(largest_notional, notional)

        sign = _direction_sign(direction)
        net_delta += sign * qty

        if sign > 0:
            risk = max(entry - stop, 0.0) * qty
        else:
            risk = max(stop - entry, 0.0) * qty
        total_risk += risk

        sector = sector_map.get(ticker, "Uncategorized")
        sector_exposure[sector] += notional
        direction_exposure["LONG" if sign > 0 else "SHORT"] += notional
        key = (sector, "LONG" if sign > 0 else "SHORT")
        correlated_groups[key]["count"] += 1
        correlated_groups[key]["risk"] += risk

    correlated_positions = 0
    max_correlated_loss = 0.0
    for group in correlated_groups.values():
        if group["count"] >= 3:
            correlated_positions += int(group["count"])
            max_correlated_loss = max(max_correlated_loss, float(group["risk"]))

    risk_pct = (total_risk / account_size) if account_size > 0 else None
    largest_position_pct = (largest_notional / account_size) if account_size > 0 else None

    return {
        "account": account,
        "total_positions": total_positions,
        "net_delta": net_delta,
        "total_risk": total_risk,
        "risk_pct_of_account": risk_pct,
        "largest_position_pct": largest_position_pct,
        "sector_exposure": dict(sector_exposure),
        "direction_exposure": dict(direction_exposure),
        "correlated_positions": correlated_positions,
        "max_correlated_loss": max_correlated_loss,
    }


async def _send_correlated_risk_alert(snapshot: Dict[str, Any]) -> None:
    webhook = os.getenv("PIVOT_ALERT_WEBHOOK_URL") or os.getenv("PORTFOLIO_ALERT_WEBHOOK_URL")
    if not webhook:
        logger.warning(
            "Correlated risk alert for %s (positions=%s risk=%.2f) but no webhook configured",
            snapshot.get("account"),
            snapshot.get("correlated_positions"),
            snapshot.get("max_correlated_loss") or 0.0,
        )
        return

    content = (
        f"WARNING: Correlated risk alert ({snapshot.get('account')}): "
        f"{snapshot.get('correlated_positions')} correlated positions, "
        f"max cluster risk ${_safe_float(snapshot.get('max_correlated_loss')):,.2f}, "
        f"risk pct {(_safe_float(snapshot.get('risk_pct_of_account')) * 100):.2f}%"
    )
    try:
        async with httpx.AsyncClient() as client:
            await client.post(webhook, json={"content": content}, timeout=10.0)
    except Exception as exc:
        logger.warning("Failed to send correlated risk alert: %s", exc)


async def snapshot_portfolio_and_alert() -> Dict[str, Any]:
    account_sizes = _load_account_sizes()
    threshold = _safe_float(os.getenv("CORRELATED_RISK_ALERT_PCT", "0.12"), 0.12)
    now = datetime.now(timezone.utc)

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await _load_open_positions(conn)
        if not rows:
            return {"status": "ok", "snapshots": 0, "message": "no open positions"}

        sector_map = await _load_sector_map(conn)
        by_account: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            account = str(row.get("account") or row.get("broker") or "default").upper()
            by_account[account].append(row)

        snapshots: List[Dict[str, Any]] = []
        for account, account_rows in by_account.items():
            account_size = account_sizes.get(account, account_sizes["__DEFAULT__"])
            snapshot = _build_account_snapshot(account, account_rows, sector_map, account_size)
            snapshots.append(snapshot)

            await conn.execute(
                """
                INSERT INTO portfolio_snapshots (
                    timestamp, account, total_positions, net_delta, total_risk,
                    risk_pct_of_account, largest_position_pct, sector_exposure,
                    direction_exposure, correlated_positions, max_correlated_loss
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10, $11)
                """,
                now,
                snapshot["account"],
                snapshot["total_positions"],
                snapshot["net_delta"],
                snapshot["total_risk"],
                snapshot["risk_pct_of_account"],
                snapshot["largest_position_pct"],
                json.dumps(snapshot["sector_exposure"]),
                json.dumps(snapshot["direction_exposure"]),
                snapshot["correlated_positions"],
                snapshot["max_correlated_loss"],
            )

        for snapshot in snapshots:
            risk_pct = _safe_float(snapshot.get("risk_pct_of_account"), 0.0)
            if snapshot.get("correlated_positions", 0) >= 3 and risk_pct >= threshold:
                await _send_correlated_risk_alert(snapshot)

    return {"status": "ok", "snapshots": len(snapshots), "timestamp": now.isoformat()}
