"""Triton Step-0 B2 — whale-flow shadow poller.

RTH-only, 120s cadence (loop in main.py). ONE market-wide UW flow-alerts call
per tick (ask-side sweeps >= $250k), dedup-inserted into triton_flow_shadow with
fire-time context (direction, liquidity bucket, spot, prior_5d_ret, liquid20 /
megacap-AI flags, bias/gex snapshot). SHADOW-ONLY, fail-open. Grading is B3.

Budget: the flow-alerts call AND every prior_5d bar-fetch are tagged to the
triton_flow_shadow BACKGROUND governor caller (never rides ohlc_bars).
"""

from __future__ import annotations

import json
import logging
from datetime import date

logger = logging.getLogger("triton_shadow")

MIN_PREMIUM = 250_000
DAILY_CAP = 500          # disk guard: log + stop inserting beyond this many rows/day
PRIOR_LOOKBACK_DAYS = 15  # ~10 sessions — enough for a 5-trading-day prior return


async def run_triton_shadow_poller() -> None:
    """One poller tick. Never raises (fail-open)."""
    from database.postgres_client import get_postgres_client
    from integrations.uw_api import get_flow_alerts
    from config.liquid_universe import LIQUID_UNIVERSE, SEMIS_AI_TECH
    from jobs.triton_shadow_common import (
        _f, classify_bucket, classify_direction, fetch_r_close_index,
    )

    pool = await get_postgres_client()
    if not pool:
        return

    # Daily insert cap (disk guard)
    async with pool.acquire() as conn:
        today_n = await conn.fetchval(
            "SELECT COUNT(*) FROM triton_flow_shadow WHERE created_at >= CURRENT_DATE"
        ) or 0
    if today_n >= DAILY_CAP:
        logger.info("triton_shadow: daily cap %d reached (%d) — skipping tick", DAILY_CAP, today_n)
        return

    try:
        alerts = await get_flow_alerts(min_premium=MIN_PREMIUM, is_ask_side=True, is_sweep=True)
    except Exception as exc:
        logger.warning("triton_shadow: flow-alerts fetch failed: %s", type(exc).__name__)
        return
    if not alerts:
        return

    # Bias snapshot once per tick (market-wide, not per-ticker)
    bias_level = gex_regime = None
    try:
        from utils.bias_snapshot import get_bias_snapshot
        snap = await get_bias_snapshot() or {}
        bias_level = snap.get("bias_level")
        gex_regime = snap.get("gex_regime")
    except Exception:
        pass

    prior5_cache: dict = {}   # ticker -> prior_5d_ret (one bar-fetch/ticker/tick)
    inserted = 0

    for a in alerts:
        try:
            aid = a.get("id")
            ticker = (a.get("ticker") or "").upper()
            if not aid or not ticker:
                continue

            direction = classify_direction(a.get("type"))
            prem = _f(a.get("total_premium"))
            premium_i = int(prem) if prem is not None else None
            spot = _f(a.get("underlying_price"))
            if spot is None:
                spot = _f(a.get("price"))

            # prior_5d_ret (RAW; analysis adjusts by direction) — cached per ticker/tick
            if ticker not in prior5_cache:
                idx = await fetch_r_close_index(ticker, PRIOR_LOOKBACK_DAYS)
                p5 = None
                ds = sorted(idx)
                if len(ds) >= 6 and idx[ds[-6]]:
                    p5 = round((idx[ds[-1]] / idx[ds[-6]] - 1.0) * 100, 4)
                prior5_cache[ticker] = p5
            prior_5d = prior5_cache[ticker]

            raw = {
                "id": aid, "type": a.get("type"), "strike": a.get("strike"),
                "expiry": a.get("expiry"), "alert_rule": a.get("alert_rule"),
                "rule_id": a.get("rule_id"), "sector": a.get("sector"),
                "total_ask_side_prem": a.get("total_ask_side_prem"),
                "total_bid_side_prem": a.get("total_bid_side_prem"),
                "volume": a.get("volume"), "open_interest": a.get("open_interest"),
            }  # selected fields only — never the full payload, never secrets

            async with pool.acquire() as conn:
                res = await conn.execute(
                    """
                    INSERT INTO triton_flow_shadow
                        (uw_alert_id, fired_at, ticker, direction, premium_usd, is_sweep,
                         liquidity_bucket, spot_at_fire, chg_pct_day, prior_5d_ret,
                         is_liquid20, is_megacap_ai, bias_level_at_fire, gex_regime_at_fire, raw)
                    VALUES ($1, $2::text::timestamptz, $3, $4, $5, $6, $7, $8, $9, $10,
                            $11, $12, $13, $14, $15::jsonb)
                    ON CONFLICT (uw_alert_id) DO NOTHING
                    """,
                    aid, a.get("created_at"), ticker, direction, premium_i,
                    bool(a.get("has_sweep")), classify_bucket(ticker, premium_i),
                    spot, None,  # chg_pct_day: not reliably in the alert payload -> null
                    prior_5d, ticker in LIQUID_UNIVERSE, ticker in SEMIS_AI_TECH,
                    bias_level, gex_regime, json.dumps(raw),
                )
            if res and res.endswith(" 1"):   # asyncpg "INSERT 0 1" = new row
                inserted += 1
                if today_n + inserted >= DAILY_CAP:
                    logger.info("triton_shadow: daily cap %d hit mid-tick — stopping", DAILY_CAP)
                    break
        except Exception as exc:
            logger.warning("triton_shadow: row skip (%s): %s", a.get("id"), type(exc).__name__)
            continue

    if inserted:
        logger.info("triton_shadow: +%d new whale prints (%d scanned)", inserted, len(alerts))
